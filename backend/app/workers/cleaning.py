from __future__ import annotations

import json
from typing import Any

import pandas as pd

from app.api.schemas import CleaningOperation
from app.cleaning.engine import apply_cleaning_operations
from app.domain.errors import DomainError
from app.ingest.parser import DatasetParser
from app.ingest.profiler import profile_frame
from app.persistence.orm.models import DatasetVersionRow
from app.persistence.repositories.jobs import JobRepository
from app.persistence.session import Database, get_database
from app.persistence.unit_of_work import UnitOfWork
from app.storage.files import FileStorage


def _operation_from_row(row: Any) -> CleaningOperation:
    return CleaningOperation(
        operation_id=row.operation_id,
        operation=row.operation,
        column=row.column_name,
        parameters=row.parameters_json,
        reason=row.reason,
        issue_ids=row.issue_ids_json,
        estimated_affected_rows=row.estimated_affected_rows,
        risk_level=row.risk_level,
        reversible=row.reversible,
    )


def _sample_records(
    frame: pd.DataFrame,
    *,
    sensitive_columns: set[str],
    limit: int = 5,
) -> list[dict[str, Any]]:
    sample = frame.head(limit).copy()
    for column in sensitive_columns & set(sample.columns):
        sample[column] = "******"
    return list(json.loads(sample.to_json(orient="records", date_format="iso")))


class CleaningPreviewWorker:
    def __init__(
        self,
        database: Database,
        storage: FileStorage,
        *,
        worker_id: str,
    ) -> None:
        self.database = database
        self.storage = storage
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
                    "清洗预览执行失败",
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
        read_session = self.database.session()
        try:
            job = JobRepository(read_session).get(job_id)
            if job.kind != "cleaning_preview":
                raise DomainError("STATE_CONFLICT", "Job 类型不是清洗预览", 409)
            plan_id = str(job.request_json["cleaning_plan_id"])
            plan = UnitOfWork(read_session).cleaning_plans.get(
                project_id=job.project_id,
                plan_id=plan_id,
            )
            if plan.status != "draft":
                raise DomainError("STATE_CONFLICT", "清洗计划状态不可预览", 409)
            version = UnitOfWork(read_session).datasets.get_version(
                project_id=job.project_id,
                dataset_id=str(job.request_json["dataset_id"]),
                version_id=plan.source_version_id,
            )
            if version.status != "ready" or not version.data_storage_key:
                raise DomainError("STATE_CONFLICT", "来源数据版本尚未就绪", 409)
            operations = [
                _operation_from_row(row)
                for row in UnitOfWork(read_session).cleaning_plans.list_operations(plan_id)
            ]
            sensitive_columns = UnitOfWork(read_session).schemas.sensitive_columns(
                plan.source_version_id
            )
            source_path = self.storage.resolve_key(version.data_storage_key)
            project_id = job.project_id
            version_id = plan.source_version_id
            created_by = job.created_by
        finally:
            read_session.close()

        source = pd.read_parquet(source_path)
        cleaned = apply_cleaning_operations(source, operations)
        result: dict[str, Any] = {
            "cleaning_plan_id": plan_id,
            "source_version_id": version_id,
            "row_count_before": len(source),
            "row_count_after": len(cleaned.frame),
            "column_count_before": len(source.columns),
            "column_count_after": len(cleaned.frame.columns),
            "operations": [
                {
                    "operation_id": effect.operation_id,
                    "operation": effect.operation,
                    "affected_rows": effect.affected_rows,
                    "row_count_before": effect.row_count_before,
                    "row_count_after": effect.row_count_after,
                }
                for effect in cleaned.effects
            ],
            "sample_before": _sample_records(
                source,
                sensitive_columns=sensitive_columns,
            ),
            "sample_after": _sample_records(
                cleaned.frame,
                sensitive_columns=sensitive_columns,
            ),
        }

        write_session = self.database.session()
        try:
            with UnitOfWork(write_session) as uow:
                current_job = uow.jobs.get(job_id)
                current_plan = uow.cleaning_plans.get(
                    project_id=project_id,
                    plan_id=plan_id,
                )
                artifact = uow.artifacts.create_cleaning_preview(
                    project_id=project_id,
                    dataset_version_id=version_id,
                    plan_id=plan_id,
                    result=result,
                )
                uow.cleaning_plans.mark_preview_ready(
                    current_plan,
                    artifact_id=artifact.artifact_id,
                )
                uow.jobs.transition(
                    current_job,
                    status="succeeded",
                    resource_type="artifact",
                    resource_id=artifact.artifact_id,
                )
                uow.audit.append(
                    action="cleaning_plan.previewed",
                    result="success",
                    summary={
                        "row_count_before": len(source),
                        "row_count_after": len(cleaned.frame),
                    },
                    project_id=project_id,
                    subject_id=created_by,
                    object_type="cleaning_plan",
                    object_id=plan_id,
                    request_id=f"job:{job_id}",
                )
        finally:
            write_session.close()

    def _fail(self, job_id: str, error: DomainError) -> None:
        session = self.database.session()
        try:
            with UnitOfWork(session) as uow:
                job = uow.jobs.get(job_id)
                if job.status == "queued":
                    job.status = "running"
                if job.status in {"running", "cancelling"}:
                    uow.jobs.transition(
                        job,
                        status="failed",
                        error={
                            "code": error.code,
                            "message": error.message,
                            "request_id": f"job:{job_id}",
                            "retryable": error.retryable,
                            "details": error.details,
                        },
                    )
        finally:
            session.close()


def process_cleaning_preview_job(job_id: str) -> None:
    from app.core.config import get_settings

    CleaningPreviewWorker(
        get_database(),
        FileStorage(get_settings().data_root),
        worker_id=f"local:{job_id}",
    ).run(job_id)


class CleaningExecuteWorker:
    def __init__(
        self,
        database: Database,
        storage: FileStorage,
        *,
        worker_id: str,
    ) -> None:
        self.database = database
        self.storage = storage
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
                    "清洗执行失败",
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
        read_session = self.database.session()
        try:
            uow = UnitOfWork(read_session)
            job = uow.jobs.get(job_id)
            if job.kind != "cleaning_execute":
                raise DomainError("STATE_CONFLICT", "Job 类型不是清洗执行", 409)
            plan_id = str(job.request_json["cleaning_plan_id"])
            result_version_id = str(job.request_json["result_version_id"])
            plan = uow.cleaning_plans.get(project_id=job.project_id, plan_id=plan_id)
            if plan.status != "executing" or plan.result_version_id != result_version_id:
                raise DomainError("STATE_CONFLICT", "清洗计划不在执行状态", 409)
            source = read_session.get(DatasetVersionRow, plan.source_version_id)
            if source is None or source.status != "ready" or not source.data_storage_key:
                raise DomainError("STATE_CONFLICT", "来源数据版本尚未就绪", 409)
            operations = [
                _operation_from_row(row) for row in uow.cleaning_plans.list_operations(plan_id)
            ]
            source_path = self.storage.resolve_key(source.data_storage_key)
            project_id = job.project_id
            dataset_id = source.dataset_id
            created_by = job.created_by
        finally:
            read_session.close()

        source_frame = pd.read_parquet(source_path)
        cleaned = apply_cleaning_operations(source_frame, operations)
        if cleaned.frame.empty:
            raise DomainError(
                "VALIDATION_ERROR",
                "清洗结果为空，未生成可用数据版本",
                422,
            )
        if cleaned.frame.columns.duplicated().any():
            raise DomainError(
                "VALIDATION_ERROR",
                "清洗结果包含重复字段名",
                422,
            )
        temporary = self.storage.temp_parquet_path(job_id)
        row_count, column_count = DatasetParser().write_verified_parquet(
            cleaned.frame,
            temporary,
        )
        data_key = self.storage.commit_derived_parquet(
            project_id=project_id,
            dataset_id=dataset_id,
            version_id=result_version_id,
            parquet_path=temporary,
        )
        checksum = self.storage.checksum_path(self.storage.resolve_key(data_key))
        profiles = profile_frame(cleaned.frame)

        write_session = self.database.session()
        try:
            with UnitOfWork(write_session) as uow:
                current_job = uow.jobs.get(job_id)
                current_plan = uow.cleaning_plans.get(
                    project_id=project_id,
                    plan_id=plan_id,
                )
                result_version = uow.datasets.get_version(
                    project_id=project_id,
                    dataset_id=dataset_id,
                    version_id=result_version_id,
                )
                uow.schemas.replace_profiles(
                    project_id=project_id,
                    dataset_version_id=result_version_id,
                    profiles=profiles,
                )
                uow.datasets.mark_version_ready(
                    result_version,
                    data_storage_key=data_key,
                    data_checksum=checksum,
                    row_count=row_count,
                    column_count=column_count,
                )
                uow.datasets.activate_version(
                    project_id=project_id,
                    dataset_id=dataset_id,
                    version_id=result_version_id,
                )
                uow.cleaning_plans.mark_executed(current_plan)
                uow.jobs.transition(
                    current_job,
                    status="succeeded",
                    resource_type="dataset_version",
                    resource_id=result_version_id,
                )
                uow.audit.append(
                    action="cleaning_plan.executed",
                    result="success",
                    summary={
                        "row_count_before": len(source_frame),
                        "row_count_after": row_count,
                    },
                    project_id=project_id,
                    subject_id=created_by,
                    object_type="cleaning_plan",
                    object_id=plan_id,
                    request_id=f"job:{job_id}",
                )
        finally:
            write_session.close()

    def _fail(self, job_id: str, error: DomainError) -> None:
        session = self.database.session()
        try:
            with UnitOfWork(session) as uow:
                job = uow.jobs.get(job_id)
                plan = uow.cleaning_plans.get(
                    project_id=job.project_id,
                    plan_id=str(job.request_json["cleaning_plan_id"]),
                )
                result_version = uow.datasets.get_version(
                    project_id=job.project_id,
                    dataset_id=str(job.request_json["dataset_id"]),
                    version_id=str(job.request_json["result_version_id"]),
                )
                if result_version.status == "creating":
                    uow.datasets.mark_version_failed(
                        result_version,
                        failure_code=error.code,
                        failure_details=error.details,
                    )
                if plan.status == "executing":
                    uow.cleaning_plans.mark_failed(plan)
                if job.status == "queued":
                    job.status = "running"
                if job.status in {"running", "cancelling"}:
                    uow.jobs.transition(
                        job,
                        status="failed",
                        error={
                            "code": error.code,
                            "message": error.message,
                            "request_id": f"job:{job_id}",
                            "retryable": error.retryable,
                            "details": error.details,
                        },
                    )
        finally:
            session.close()


def process_cleaning_execute_job(job_id: str) -> None:
    from app.core.config import get_settings

    CleaningExecuteWorker(
        get_database(),
        FileStorage(get_settings().data_root),
        worker_id=f"local:{job_id}",
    ).run(job_id)
