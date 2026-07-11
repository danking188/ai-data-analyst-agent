from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.analysis.tool_registry import ToolRegistry, default_tool_registry
from app.core.clock import utc_now
from app.domain.errors import DomainError
from app.persistence.orm.models import DatasetVersionRow
from app.persistence.orm.workflow_models import AnalysisSpecRow, ArtifactRow, ColumnSchemaRow
from app.persistence.repositories.jobs import JobRepository
from app.persistence.session import Database, get_database
from app.persistence.unit_of_work import UnitOfWork
from app.storage.files import FileStorage, get_file_storage


class AnalysisRunWorker:
    def __init__(
        self,
        database: Database,
        storage: FileStorage,
        registry: ToolRegistry,
        *,
        worker_id: str,
    ) -> None:
        self.database = database
        self.storage = storage
        self.registry = registry
        self.worker_id = worker_id

    def run(self, job_id: str) -> bool:
        if not self._claim(job_id):
            return False
        try:
            self._process(job_id)
        except DomainError as exc:
            self._fail(job_id, exc)
        except Exception:
            self._fail(
                job_id,
                DomainError(
                    "EXECUTOR_UNAVAILABLE",
                    "分析运行执行失败",
                    500,
                    retryable=True,
                ),
            )
        return True

    def _claim(self, job_id: str) -> bool:
        session = self.database.session()
        try:
            with UnitOfWork(session):
                return JobRepository(session).claim(
                    job_id=job_id,
                    worker_id=self.worker_id,
                    lease_seconds=1800,
                )
        finally:
            session.close()

    def _process(self, job_id: str) -> None:
        session = self.database.session()
        try:
            with UnitOfWork(session) as uow:
                job = uow.jobs.get(job_id)
                if job.kind != "analysis_run":
                    raise DomainError("STATE_CONFLICT", "Job 类型不是分析运行", 409)
                run = uow.runs.get(
                    project_id=job.project_id,
                    run_id=str(job.request_json["run_id"]),
                )
                version = session.get(DatasetVersionRow, run.dataset_version_id)
                if version is None or not version.data_storage_key:
                    raise DomainError("STATE_CONFLICT", "运行数据版本尚未就绪", 409)
                data_path = self.storage.resolve_key(version.data_storage_key)
                project_id = job.project_id
                created_by = job.created_by
                run_id = run.run_id
                dataset_version_id = run.dataset_version_id
                spec = session.get(AnalysisSpecRow, run.analysis_spec_revision_id)
                if spec is None:
                    raise DomainError("STATE_CONFLICT", "AnalysisSpec 修订不存在", 409)
                analysis_spec = {
                    "spec_id": spec.spec_id,
                    "revision": spec.revision,
                    "task": spec.task,
                    "target": spec.target,
                    "entity_key": spec.entity_key,
                    "time_column": spec.time_column,
                    "split_strategy": spec.split_strategy,
                    "group_column": spec.group_column,
                    "metrics": spec.metrics_json,
                    "included_columns": spec.included_columns_json,
                    "excluded_columns": spec.excluded_columns_json,
                }
                random_seed = spec.random_seed
                sensitive_columns = [
                    row.name
                    for row in session.scalars(
                        select(ColumnSchemaRow).where(
                            ColumnSchemaRow.dataset_version_id == dataset_version_id,
                            ColumnSchemaRow.sensitive.is_(True),
                        )
                    )
                ]
            completed_tools: list[str] = []
            pending_steps = self._pending_steps(project_id, run_id)
            steps_total = len(pending_steps)
            for index, step_snapshot in enumerate(pending_steps, start=1):
                with UnitOfWork(session) as uow:
                    job = uow.jobs.get(job_id)
                    run = uow.runs.get(project_id=project_id, run_id=run_id)
                    if run.status == "cancelled" or job.status == "cancelling":
                        if job.status in {"running", "cancelling"}:
                            uow.jobs.transition(job, status="cancelled")
                        return
                    step = next(
                        item
                        for item in uow.runs.steps(run_id)
                        if item.step_id == step_snapshot["step_id"]
                    )
                    uow.runs.start(run, step)
                    tool_name = str(step.tool_name)
                    tool_version = str(step.tool_version)
                    parameters = dict(step.parameters_json)
                result = self.registry.execute(
                    tool_name,
                    tool_version,
                    {
                        "data_path": str(data_path),
                        "data_root": str(self.storage.data_root),
                        "project_id": project_id,
                        "run_id": run_id,
                        "dataset_version_id": dataset_version_id,
                        "parameters": parameters,
                        "sensitive_columns": sensitive_columns,
                        "analysis_spec": analysis_spec,
                        "random_seed": random_seed,
                    },
                )
                with UnitOfWork(session) as uow:
                    job = uow.jobs.get(job_id)
                    run = uow.runs.get(project_id=project_id, run_id=run_id)
                    step = next(
                        item
                        for item in uow.runs.steps(run_id)
                        if item.step_id == step_snapshot["step_id"]
                    )
                    if run.status == "cancelled" or job.status == "cancelling":
                        if job.status in {"running", "cancelling"}:
                            uow.jobs.transition(job, status="cancelled")
                        return
                    for artifact_payload in result.get("artifacts", []):
                        uow.artifacts.create_analysis_artifact(
                            project_id=project_id,
                            run_id=run_id,
                            dataset_version_id=dataset_version_id,
                            artifact_type=str(artifact_payload["type"]),
                            name=str(artifact_payload["name"]),
                            producer=tool_name,
                            producer_version=tool_version,
                            parameters=dict(artifact_payload.get("parameters", {})),
                            result=artifact_payload.get("result"),
                            preview=artifact_payload.get("preview"),
                        )
                    progress = int(index / max(steps_total, 1) * 100)
                    uow.runs.succeed_step(run, step, progress=progress)
                    completed_tools.append(f"{tool_name}@{tool_version}")
            with UnitOfWork(session) as uow:
                job = uow.jobs.get(job_id)
                run = uow.runs.get(project_id=project_id, run_id=run_id)
                if run.status == "cancelled":
                    if job.status in {"running", "cancelling"}:
                        uow.jobs.transition(job, status="cancelled")
                    return
                steps = uow.runs.steps(run_id)
                if steps:
                    final_step = steps[-1]
                    if final_step.status != "succeeded":
                        uow.runs.succeed_step(run, final_step, progress=100)
                self._create_claims(uow, project_id=project_id, run_id=run_id)
                run.status = "succeeded"
                run.progress = 100
                run.current_step_id = None
                run.completed_at = utc_now()
                uow.jobs.transition(
                    job,
                    status="succeeded",
                    resource_type="analysis_run",
                    resource_id=run_id,
                )
                uow.audit.append(
                    action="analysis_run.completed",
                    result="success",
                    summary={"tools": completed_tools},
                    project_id=project_id,
                    subject_id=created_by,
                    object_type="analysis_run",
                    object_id=run_id,
                    request_id=f"job:{job_id}",
                )
        finally:
            session.close()

    def _steps(self, project_id: str, run_id: str) -> list[dict[str, Any]]:
        session = self.database.session()
        try:
            run = UnitOfWork(session).runs.get(project_id=project_id, run_id=run_id)
            return [
                {"step_id": step.step_id, "status": step.status}
                for step in UnitOfWork(session).runs.steps(run.run_id)
            ]
        finally:
            session.close()

    def _pending_steps(self, project_id: str, run_id: str) -> list[dict[str, Any]]:
        return [step for step in self._steps(project_id, run_id) if step["status"] == "pending"]

    @staticmethod
    def _create_claims(uow: UnitOfWork, *, project_id: str, run_id: str) -> None:
        artifacts = list(
            uow.session.scalars(
                select(ArtifactRow).where(
                    ArtifactRow.project_id == project_id,
                    ArtifactRow.run_id == run_id,
                    ArtifactRow.status == "ready",
                )
            )
        )
        by_name = {artifact.name: artifact for artifact in artifacts}
        overview = by_name.get("数据集概览指标")
        if overview is not None and isinstance(overview.result_json, dict):
            row_count = overview.result_json.get("row_count")
            column_count = overview.result_json.get("column_count")
            uow.claims.create_validated(
                project_id=project_id,
                run_id=run_id,
                dataset_version_id=overview.dataset_version_id,
                text=f"当前数据版本包含 {row_count} 行、{column_count} 列。",
                level=1,
                evidence_ids=[overview.artifact_id],
                limitations=["该结论仅反映当前数据版本的持久化快照。"],
            )
        baseline_metric = by_name.get("Dummy Baseline 指标")
        baseline_model = by_name.get("Dummy Baseline 模型卡")
        if baseline_metric is not None and isinstance(baseline_metric.result_json, dict):
            metric_values = baseline_metric.result_json.get("metrics", {})
            if isinstance(metric_values, dict) and metric_values:
                metric_text = "、".join(
                    f"{name}={value}" for name, value in sorted(metric_values.items())
                )
                evidence_ids = [baseline_metric.artifact_id]
                if baseline_model is not None:
                    evidence_ids.append(baseline_model.artifact_id)
                uow.claims.create_validated(
                    project_id=project_id,
                    run_id=run_id,
                    dataset_version_id=baseline_metric.dataset_version_id,
                    text=f"Dummy Baseline 在测试集上的指标为 {metric_text}。",
                    level=2,
                    evidence_ids=evidence_ids,
                    limitations=[
                        "Dummy Baseline 仅作为后续模型对照，不代表业务可部署模型。",
                        "指标基于当前 AnalysisSpec 的确定性数据拆分。",
                    ],
                )

    def _fail(self, job_id: str, error: DomainError) -> None:
        session = self.database.session()
        try:
            with UnitOfWork(session) as uow:
                job = uow.jobs.get(job_id)
                run = uow.runs.get(
                    project_id=job.project_id,
                    run_id=str(job.request_json["run_id"]),
                )
                steps = uow.runs.steps(run.run_id)
                payload = self._error(job_id, error)
                if run.status not in {"succeeded", "failed", "cancelled"}:
                    uow.runs.fail(run, steps[0] if steps else None, payload)
                if job.status in {"running", "cancelling"}:
                    uow.jobs.transition(job, status="failed", error=payload)
                uow.audit.append(
                    action="analysis_run.failed",
                    result="failed",
                    summary={"retryable": error.retryable},
                    project_id=job.project_id,
                    subject_id=job.created_by,
                    object_type="analysis_run",
                    object_id=run.run_id,
                    request_id=f"job:{job_id}",
                    error_code=error.code,
                )
        finally:
            session.close()

    @staticmethod
    def _error(job_id: str, error: DomainError) -> dict[str, Any]:
        return {
            "code": error.code,
            "message": error.message,
            "request_id": f"job:{job_id}",
            "retryable": error.retryable,
            "details": error.details,
        }


def process_analysis_run_job(job_id: str) -> None:
    AnalysisRunWorker(
        get_database(),
        get_file_storage(),
        default_tool_registry,
        worker_id=f"local:{job_id}",
    ).run(job_id)
