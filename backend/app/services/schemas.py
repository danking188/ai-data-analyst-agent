from __future__ import annotations

from sqlalchemy.orm import Session

from app.api.schemas import ColumnSchema, DatasetSchema, SchemaPatch
from app.core.clock import utc_now
from app.core.ids import new_id
from app.domain.errors import not_found, permission_denied, state_conflict
from app.persistence.orm.models import DatasetVersionRow
from app.persistence.orm.workflow_models import ColumnSchemaRow, UserDecisionRow
from app.persistence.repositories.audit import AuditRepository
from app.persistence.repositories.projects import ProjectRepository
from app.persistence.repositories.schemas import ColumnSchemaRepository

LOW_CONFIDENCE_THRESHOLD = 0.85


def _column_to_schema(row: ColumnSchemaRow) -> ColumnSchema:
    return ColumnSchema(
        name=row.name,
        physical_type=row.physical_type,
        semantic_type=row.semantic_type,
        analysis_role=row.analysis_role,
        confidence=row.confidence,
        evidence=row.evidence_json,
        date_format=row.date_format,
        ordinal_values=row.ordinal_values_json,
        sensitive=row.sensitive,
        user_confirmed=row.user_confirmed,
    )


def _dataset_schema(version_id: str, rows: list[ColumnSchemaRow]) -> DatasetSchema:
    if not rows:
        raise not_found("字段 Schema 尚未生成")
    return DatasetSchema(
        dataset_version_id=version_id,
        revision=max(row.revision for row in rows),
        low_confidence_count=sum(
            row.confidence < LOW_CONFIDENCE_THRESHOLD and not row.user_confirmed for row in rows
        ),
        columns=[_column_to_schema(row) for row in rows],
    )


class SchemaService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.projects = ProjectRepository(session)
        self.schemas = ColumnSchemaRepository(session)

    def _require_access(
        self,
        project_id: str,
        version_id: str,
        subject_id: str,
        *,
        edit: bool,
    ) -> None:
        membership = self.projects.get_for_subject(project_id, subject_id)
        if membership is None:
            raise not_found()
        project, role = membership
        if edit and project.status != "active":
            raise state_conflict("归档项目不能修改字段 Schema")
        if edit and role not in {"owner", "editor"}:
            raise permission_denied()
        version = self.session.get(DatasetVersionRow, version_id)
        if version is None or version.project_id != project_id:
            raise not_found()
        if version.status != "ready":
            raise state_conflict("只有 ready 数据版本具有可编辑字段 Schema")

    def get(self, project_id: str, version_id: str, *, subject_id: str) -> DatasetSchema:
        self._require_access(project_id, version_id, subject_id, edit=False)
        return _dataset_schema(version_id, self.schemas.list_for_version(version_id))

    def update(
        self,
        project_id: str,
        version_id: str,
        payload: SchemaPatch,
        *,
        expected_revision: int,
        subject_id: str,
        request_id: str,
    ) -> DatasetSchema:
        self._require_access(project_id, version_id, subject_id, edit=True)
        changes = [
            change.model_dump(exclude_unset=True, mode="python") for change in payload.changes
        ]
        rows = self.schemas.apply_overrides(
            dataset_version_id=version_id,
            expected_revision=expected_revision,
            changes=changes,
        )
        now = utc_now()
        rows_by_name = {row.name: row for row in rows}
        for change in payload.changes:
            row = rows_by_name[change.column]
            self.session.add(
                UserDecisionRow(
                    decision_id=new_id("decision_"),
                    project_id=project_id,
                    subject_id=subject_id,
                    object_type="column_schema",
                    object_id=row.column_schema_id,
                    action="override",
                    reason=payload.reason,
                    payload_json=change.model_dump(exclude_unset=True, mode="json"),
                    created_at=now,
                )
            )
        AuditRepository(self.session).append(
            action="dataset_schema.updated",
            result="success",
            summary={
                "columns": [change.column for change in payload.changes],
                "reason": payload.reason,
            },
            project_id=project_id,
            subject_id=subject_id,
            object_type="dataset_version",
            object_id=version_id,
            request_id=request_id,
        )
        return _dataset_schema(version_id, rows)
