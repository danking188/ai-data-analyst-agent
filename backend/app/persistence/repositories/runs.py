from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.ids import new_id
from app.domain.errors import not_found, state_conflict
from app.persistence.orm.workflow_models import AnalysisRunRow, AnalysisSpecRow, AnalysisStepRow
from app.persistence.repositories.projects import Page

MODEL_TASKS = {"binary_classification", "multiclass_classification", "regression"}


class AnalysisRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        run_id: str,
        project_id: str,
        dataset_version_id: str,
        spec_revision_id: str,
        run_kind: str,
        job_id: str,
        random_seed: int,
        subject_id: str,
    ) -> AnalysisRunRow:
        now = utc_now()
        run = AnalysisRunRow(
            run_id=run_id,
            project_id=project_id,
            dataset_version_id=dataset_version_id,
            analysis_spec_revision_id=spec_revision_id,
            source_run_id=None,
            job_id=job_id,
            run_kind=run_kind,
            status="queued",
            progress=0,
            current_step_id=None,
            random_seed=random_seed,
            environment_json={
                "orchestrator": "analysis-runner",
                "orchestrator_version": "1.0.0",
                "network_access": False,
            },
            error_json=None,
            created_by=subject_id,
            created_at=now,
            started_at=None,
            completed_at=None,
        )
        self.session.add(run)
        self.session.flush()
        steps = [
            AnalysisStepRow(
                step_id=new_id("step_"),
                run_id=run_id,
                position=1,
                name="校验分析输入",
                tool_name="dataset.inspect",
                tool_version="1.0.0",
                status="pending",
                parameters_json={},
                error_json=None,
                started_at=None,
                completed_at=None,
            )
        ]
        if run_kind in {"eda", "full"}:
            steps.append(
                AnalysisStepRow(
                    step_id=new_id("step_"),
                    run_id=run_id,
                    position=2,
                    name="目标驱动 EDA 与统计诊断",
                    tool_name="eda.profile",
                    tool_version="2.0.0",
                    status="pending",
                    parameters_json={
                        "max_numeric_charts": 3,
                        "max_categorical_charts": 3,
                    },
                    error_json=None,
                    started_at=None,
                    completed_at=None,
                )
            )
        spec = self.session.get(AnalysisSpecRow, spec_revision_id)
        if spec is not None and spec.task in MODEL_TASKS and run_kind in {"model", "full"}:
            steps.append(
                AnalysisStepRow(
                    step_id=new_id("step_"),
                    run_id=run_id,
                    position=len(steps) + 1,
                    name="候选模型训练、交叉验证与保留集评估",
                    tool_name="model.train_compare",
                    tool_version="2.0.0",
                    status="pending",
                    parameters_json={"candidates": "task_default", "test_size": 0.2},
                    error_json=None,
                    started_at=None,
                    completed_at=None,
                )
            )
        for step in steps:
            self.session.add(step)
        self.session.flush()
        return run

    def get(self, *, project_id: str, run_id: str) -> AnalysisRunRow:
        row = self.session.scalar(
            select(AnalysisRunRow).where(
                AnalysisRunRow.project_id == project_id,
                AnalysisRunRow.run_id == run_id,
            )
        )
        if row is None:
            raise not_found()
        return row

    def list_page(
        self,
        *,
        project_id: str,
        page: int,
        page_size: int,
        status: str | None,
        dataset_version_id: str | None,
    ) -> Page[AnalysisRunRow]:
        filters = [AnalysisRunRow.project_id == project_id]
        if status is not None:
            filters.append(AnalysisRunRow.status == status)
        if dataset_version_id is not None:
            filters.append(AnalysisRunRow.dataset_version_id == dataset_version_id)
        total = int(
            self.session.scalar(select(func.count()).select_from(AnalysisRunRow).where(*filters))
            or 0
        )
        rows = list(
            self.session.scalars(
                select(AnalysisRunRow)
                .where(*filters)
                .order_by(AnalysisRunRow.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return Page(items=rows, total=total, page=page, page_size=page_size)

    def steps(self, run_id: str) -> list[AnalysisStepRow]:
        return list(
            self.session.scalars(
                select(AnalysisStepRow)
                .where(AnalysisStepRow.run_id == run_id)
                .order_by(AnalysisStepRow.position)
            )
        )

    def start(self, run: AnalysisRunRow, step: AnalysisStepRow) -> None:
        if run.status not in {"queued", "running"} or step.status != "pending":
            raise state_conflict("AnalysisRun 当前状态不可启动")
        now = utc_now()
        run.status = "running"
        run.current_step_id = step.step_id
        if run.started_at is None:
            run.started_at = now
        step.status = "running"
        step.started_at = now
        self.session.flush()

    def succeed_step(self, run: AnalysisRunRow, step: AnalysisStepRow, *, progress: int) -> None:
        now = utc_now()
        step.status = "succeeded"
        step.completed_at = now
        run.progress = progress
        run.current_step_id = None
        self.session.flush()

    def succeed(self, run: AnalysisRunRow, step: AnalysisStepRow) -> None:
        self.succeed_step(run, step, progress=100)
        now = utc_now()
        run.status = "succeeded"
        run.completed_at = now
        self.session.flush()

    def fail(
        self,
        run: AnalysisRunRow,
        step: AnalysisStepRow | None,
        error: dict[str, object],
    ) -> None:
        now = utc_now()
        if step is not None and step.status in {"pending", "running"}:
            step.status = "failed"
            step.error_json = error
            step.completed_at = now
        run.status = "failed"
        run.error_json = error
        run.current_step_id = None
        run.completed_at = now
        self.session.flush()

    def cancel(self, run: AnalysisRunRow) -> None:
        if run.status not in {"queued", "running"}:
            raise state_conflict("当前 AnalysisRun 不可取消", status=run.status)
        now = utc_now()
        run.status = "cancelled"
        run.current_step_id = None
        run.completed_at = now
        for step in self.steps(run.run_id):
            if step.status in {"pending", "running"}:
                step.status = "cancelled"
                step.completed_at = now
        self.session.flush()
