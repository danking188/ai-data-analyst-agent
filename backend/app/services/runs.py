from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    AnalysisRun,
    AnalysisRunCreate,
    AnalysisRunPage,
    AnalysisStep,
    JobError,
)
from app.domain.errors import not_found, permission_denied, state_conflict
from app.persistence.orm.models import DatasetVersionRow
from app.persistence.orm.workflow_models import (
    AnalysisRunRow,
    AnalysisSpecRow,
    ArtifactRow,
)
from app.persistence.repositories.projects import ProjectRepository
from app.persistence.repositories.runs import AnalysisRunRepository


class AnalysisRunService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.projects = ProjectRepository(session)
        self.runs = AnalysisRunRepository(session)

    def require_project_access(
        self,
        project_id: str,
        subject_id: str,
        *,
        edit: bool,
    ) -> None:
        membership = self.projects.get_for_subject(project_id, subject_id)
        if membership is None:
            raise not_found()
        project, role = membership
        if edit and project.status != "active":
            raise state_conflict("归档项目不能启动或取消分析运行")
        if edit and role not in {"owner", "editor"}:
            raise permission_denied()

    def require_confirmed_spec(
        self,
        project_id: str,
        payload: AnalysisRunCreate,
    ) -> AnalysisSpecRow:
        spec = self.session.scalar(
            select(AnalysisSpecRow)
            .where(
                AnalysisSpecRow.project_id == project_id,
                AnalysisSpecRow.spec_id == payload.analysis_spec_id,
            )
            .order_by(AnalysisSpecRow.revision.desc())
            .limit(1)
        )
        if spec is None:
            raise not_found()
        if spec.status != "confirmed":
            raise state_conflict("只有 confirmed AnalysisSpec 可以启动运行", status=spec.status)
        if spec.dataset_version_id != payload.dataset_version_id:
            raise state_conflict("运行数据版本必须与已确认 AnalysisSpec 一致")
        version = self.session.get(DatasetVersionRow, payload.dataset_version_id)
        if (
            version is None
            or version.project_id != project_id
            or version.status != "ready"
            or not version.data_storage_key
        ):
            raise state_conflict("运行数据版本尚未就绪")
        return spec

    def to_schema(self, row: AnalysisRunRow) -> AnalysisRun:
        spec = self.session.get(AnalysisSpecRow, row.analysis_spec_revision_id)
        if spec is None:
            raise state_conflict("AnalysisRun 引用的 AnalysisSpec 修订不存在")
        artifacts = list(
            self.session.scalars(
                select(ArtifactRow.artifact_id).where(ArtifactRow.run_id == row.run_id)
            )
        )
        steps = [
            AnalysisStep(
                step_id=step.step_id,
                name=step.name,
                tool_name=step.tool_name,
                tool_version=step.tool_version,
                status=step.status,
                order=step.position,
                started_at=step.started_at,
                completed_at=step.completed_at,
                artifact_ids=artifacts,
                error=JobError.model_validate(step.error_json) if step.error_json else None,
            )
            for step in self.runs.steps(row.run_id)
        ]
        return AnalysisRun(
            run_id=row.run_id,
            project_id=row.project_id,
            dataset_version_id=row.dataset_version_id,
            analysis_spec_id=spec.spec_id,
            source_run_id=row.source_run_id,
            run_kind=row.run_kind,
            status=row.status,
            progress=row.progress,
            current_step_id=row.current_step_id,
            steps=steps,
            environment=row.environment_json,
            created_at=row.created_at,
            started_at=row.started_at,
            completed_at=row.completed_at,
            error=JobError.model_validate(row.error_json) if row.error_json else None,
        )

    def get(
        self,
        project_id: str,
        run_id: str,
        *,
        subject_id: str,
        edit: bool = False,
    ) -> AnalysisRunRow:
        self.require_project_access(project_id, subject_id, edit=edit)
        return self.runs.get(project_id=project_id, run_id=run_id)

    def list(
        self,
        project_id: str,
        *,
        subject_id: str,
        page: int,
        page_size: int,
        status: str | None,
        dataset_version_id: str | None,
    ) -> AnalysisRunPage:
        self.require_project_access(project_id, subject_id, edit=False)
        result = self.runs.list_page(
            project_id=project_id,
            page=page,
            page_size=page_size,
            status=status,
            dataset_version_id=dataset_version_id,
        )
        return AnalysisRunPage(
            items=[self.to_schema(row) for row in result.items],
            page=page,
            page_size=page_size,
            total=result.total,
            has_more=result.has_more,
        )
