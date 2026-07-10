from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.spec_validator import validate_analysis_spec
from app.api.schemas import (
    AnalysisSpec,
    AnalysisSpecCreate,
    AnalysisSpecPage,
    AnalysisSpecUpdate,
)
from app.core.clock import utc_now
from app.core.ids import new_id
from app.domain.errors import not_found, permission_denied, state_conflict
from app.persistence.orm.models import DatasetVersionRow
from app.persistence.orm.workflow_models import (
    AnalysisSpecRow,
    ColumnSchemaRow,
    UserDecisionRow,
)
from app.persistence.repositories.analysis_specs import AnalysisSpecRepository
from app.persistence.repositories.audit import AuditRepository
from app.persistence.repositories.projects import ProjectRepository


def analysis_spec_to_schema(row: AnalysisSpecRow) -> AnalysisSpec:
    return AnalysisSpec(
        spec_id=row.spec_id,
        project_id=row.project_id,
        revision=row.revision,
        status=row.status,
        name=row.name,
        dataset_version_id=row.dataset_version_id,
        task=row.task,
        target=row.target,
        entity_key=row.entity_key,
        time_column=row.time_column,
        prediction_time_description=row.prediction_time_description,
        split_strategy=row.split_strategy,
        group_column=row.group_column,
        metrics=row.metrics_json,
        included_columns=row.included_columns_json,
        excluded_columns=row.excluded_columns_json,
        random_seed=row.random_seed,
        causal_interpretation_allowed=False,
        validation_warnings=row.validation_warnings_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _row_payload(row: AnalysisSpecRow) -> dict[str, object]:
    return {
        "name": row.name,
        "dataset_version_id": row.dataset_version_id,
        "task": row.task,
        "target": row.target,
        "entity_key": row.entity_key,
        "time_column": row.time_column,
        "prediction_time_description": row.prediction_time_description,
        "split_strategy": row.split_strategy,
        "group_column": row.group_column,
        "metrics": row.metrics_json,
        "included_columns": row.included_columns_json,
        "excluded_columns": row.excluded_columns_json,
        "random_seed": row.random_seed,
        "causal_interpretation_allowed": False,
    }


class AnalysisSpecService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.projects = ProjectRepository(session)
        self.specs = AnalysisSpecRepository(session)

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
            raise state_conflict("归档项目不能修改 AnalysisSpec")
        if edit and role not in {"owner", "editor"}:
            raise permission_denied()

    def validate(
        self,
        project_id: str,
        payload: AnalysisSpecCreate,
    ) -> list[str]:
        version = self.session.get(DatasetVersionRow, payload.dataset_version_id)
        if version is None or version.project_id != project_id:
            raise not_found()
        if version.status != "ready":
            raise state_conflict("只有 ready 数据版本可以创建 AnalysisSpec")
        columns = {
            row.name: row
            for row in self.session.scalars(
                select(ColumnSchemaRow).where(
                    ColumnSchemaRow.dataset_version_id == payload.dataset_version_id
                )
            )
        }
        if not columns:
            raise state_conflict("数据版本尚未生成字段 Schema")
        return validate_analysis_spec(payload, columns=columns)

    def create(
        self,
        project_id: str,
        payload: AnalysisSpecCreate,
        *,
        subject_id: str,
        request_id: str,
    ) -> AnalysisSpec:
        self.require_project_access(project_id, subject_id, edit=True)
        warnings = self.validate(project_id, payload)
        row = self.specs.create(
            project_id=project_id,
            payload=payload,
            warnings=warnings,
            subject_id=subject_id,
        )
        AuditRepository(self.session).append(
            action="analysis_spec.created",
            result="success",
            summary={"task": payload.task, "warning_count": len(warnings)},
            project_id=project_id,
            subject_id=subject_id,
            object_type="analysis_spec",
            object_id=row.spec_id,
            request_id=request_id,
        )
        return analysis_spec_to_schema(row)

    def list(
        self,
        project_id: str,
        *,
        subject_id: str,
        page: int,
        page_size: int,
        dataset_version_id: str | None,
    ) -> AnalysisSpecPage:
        self.require_project_access(project_id, subject_id, edit=False)
        result = self.specs.list_latest(
            project_id=project_id,
            page=page,
            page_size=page_size,
            dataset_version_id=dataset_version_id,
        )
        return AnalysisSpecPage(
            items=[analysis_spec_to_schema(row) for row in result.items],
            page=page,
            page_size=page_size,
            total=result.total,
            has_more=result.has_more,
        )

    def get(
        self,
        project_id: str,
        spec_id: str,
        *,
        subject_id: str,
        edit: bool = False,
    ) -> AnalysisSpecRow:
        self.require_project_access(project_id, subject_id, edit=edit)
        return self.specs.latest(project_id=project_id, spec_id=spec_id)

    def update(
        self,
        project_id: str,
        spec_id: str,
        payload: AnalysisSpecUpdate,
        *,
        expected_revision: int,
        subject_id: str,
        request_id: str,
    ) -> AnalysisSpec:
        current = self.get(project_id, spec_id, subject_id=subject_id, edit=True)
        merged = _row_payload(current)
        merged.update(payload.model_dump(exclude_unset=True, mode="python"))
        candidate = AnalysisSpecCreate.model_validate(merged)
        warnings = self.validate(project_id, candidate)
        row = self.specs.revise(
            current,
            expected_revision=expected_revision,
            payload=candidate,
            warnings=warnings,
            subject_id=subject_id,
        )
        AuditRepository(self.session).append(
            action="analysis_spec.revised",
            result="success",
            summary={"revision": row.revision, "fields": sorted(payload.model_fields_set)},
            project_id=project_id,
            subject_id=subject_id,
            object_type="analysis_spec",
            object_id=spec_id,
            request_id=request_id,
        )
        return analysis_spec_to_schema(row)

    def confirm(
        self,
        project_id: str,
        spec_id: str,
        *,
        subject_id: str,
        request_id: str,
    ) -> AnalysisSpec:
        current = self.get(project_id, spec_id, subject_id=subject_id, edit=True)
        row = self.specs.confirm(current)
        self.session.add(
            UserDecisionRow(
                decision_id=new_id("decision_"),
                project_id=project_id,
                subject_id=subject_id,
                object_type="analysis_spec",
                object_id=spec_id,
                action="confirm",
                reason=None,
                payload_json={"revision": row.revision},
                created_at=utc_now(),
            )
        )
        AuditRepository(self.session).append(
            action="analysis_spec.confirmed",
            result="success",
            summary={"revision": row.revision, "warning_count": len(row.validation_warnings_json)},
            project_id=project_id,
            subject_id=subject_id,
            object_type="analysis_spec",
            object_id=spec_id,
            request_id=request_id,
        )
        return analysis_spec_to_schema(row)
