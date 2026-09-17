from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    SemanticMetric,
    SemanticMetricCreate,
    SemanticMetricPage,
    SemanticMetricUpdate,
)
from app.core.clock import utc_now
from app.domain.errors import not_found, permission_denied, state_conflict, validation_error
from app.persistence.orm.models import DatasetVersionRow
from app.persistence.orm.workflow_models import ColumnSchemaRow, SemanticMetricRow
from app.persistence.repositories.audit import AuditRepository
from app.persistence.repositories.projects import ProjectRepository
from app.persistence.repositories.semantic_metrics import SemanticMetricRepository


def semantic_metric_to_schema(row: SemanticMetricRow) -> SemanticMetric:
    return SemanticMetric(
        metric_id=row.metric_id,
        project_id=row.project_id,
        dataset_version_id=row.dataset_version_id,
        name=row.name,
        description=row.description,
        source_column=row.source_column,
        aggregation=row.aggregation,
        unit=row.unit,
        grain_dimensions=row.grain_dimensions_json,
        status=row.status,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SemanticMetricService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.projects = ProjectRepository(session)
        self.metrics = SemanticMetricRepository(session)

    def _require_access(self, project_id: str, subject_id: str, *, edit: bool) -> None:
        membership = self.projects.get_for_subject(project_id, subject_id)
        if membership is None:
            raise not_found()
        project, role = membership
        if edit and project.status != "active":
            raise state_conflict("归档项目不能修改语义指标")
        if edit and role not in {"owner", "editor"}:
            raise permission_denied()

    def _validate_definition(self, project_id: str, payload: SemanticMetricCreate) -> None:
        version = self.session.get(DatasetVersionRow, payload.dataset_version_id)
        if version is None or version.project_id != project_id:
            raise not_found()
        if version.status != "ready":
            raise state_conflict("语义指标只能绑定 ready 数据版本")
        columns = {
            row.name: row
            for row in self.session.scalars(
                select(ColumnSchemaRow).where(
                    ColumnSchemaRow.project_id == project_id,
                    ColumnSchemaRow.dataset_version_id == payload.dataset_version_id,
                )
            )
        }
        if payload.source_column and payload.source_column not in columns:
            raise validation_error("指标引用了不存在的字段", column=payload.source_column)
        missing_dimensions = sorted(set(payload.grain_dimensions) - set(columns))
        if missing_dimensions:
            raise validation_error("指标粒度引用了不存在的字段", columns=missing_dimensions)
        sensitive_dimensions = sorted(
            name for name in payload.grain_dimensions if columns[name].sensitive
        )
        if sensitive_dimensions:
            raise validation_error("敏感字段不能作为默认指标粒度", columns=sensitive_dimensions)
        if payload.source_column and columns[payload.source_column].sensitive:
            raise validation_error("敏感字段不能直接定义为业务指标")
        if payload.aggregation in {"sum", "average", "minimum", "maximum"}:
            source = columns[payload.source_column or ""]
            if source.physical_type not in {"integer", "float"}:
                raise validation_error("该聚合方式只允许数值字段")

    def create(
        self,
        project_id: str,
        payload: SemanticMetricCreate,
        *,
        subject_id: str,
        request_id: str,
    ) -> SemanticMetric:
        self._require_access(project_id, subject_id, edit=True)
        self._validate_definition(project_id, payload)
        existing = self.session.scalar(
            select(SemanticMetricRow.metric_id).where(
                SemanticMetricRow.project_id == project_id,
                SemanticMetricRow.dataset_version_id == payload.dataset_version_id,
                SemanticMetricRow.name == payload.name,
            )
        )
        if existing is not None:
            raise validation_error("当前数据版本已存在同名语义指标", name=payload.name)
        row = self.metrics.create(project_id=project_id, payload=payload, subject_id=subject_id)
        AuditRepository(self.session).append(
            action="semantic_metric.created",
            result="success",
            summary={"name": row.name, "aggregation": row.aggregation},
            project_id=project_id,
            subject_id=subject_id,
            object_type="semantic_metric",
            object_id=row.metric_id,
            request_id=request_id,
        )
        return semantic_metric_to_schema(row)

    def list(
        self,
        project_id: str,
        *,
        subject_id: str,
        dataset_version_id: str | None,
        page: int,
        page_size: int,
    ) -> SemanticMetricPage:
        self._require_access(project_id, subject_id, edit=False)
        result = self.metrics.list(
            project_id=project_id,
            dataset_version_id=dataset_version_id,
            page=page,
            page_size=page_size,
        )
        return SemanticMetricPage(
            items=[semantic_metric_to_schema(row) for row in result.items],
            page=page,
            page_size=page_size,
            total=result.total,
            has_more=result.has_more,
        )

    def update(
        self,
        project_id: str,
        metric_id: str,
        payload: SemanticMetricUpdate,
        *,
        subject_id: str,
        request_id: str,
    ) -> SemanticMetric:
        self._require_access(project_id, subject_id, edit=True)
        row = self.metrics.get(project_id=project_id, metric_id=metric_id)
        values = payload.model_dump(exclude_unset=True)
        if payload.grain_dimensions is not None or payload.status == "active":
            candidate = SemanticMetricCreate(
                dataset_version_id=row.dataset_version_id,
                name=row.name,
                description=payload.description or row.description,
                source_column=row.source_column,
                aggregation=row.aggregation,
                unit=payload.unit if "unit" in values else row.unit,
                grain_dimensions=(
                    payload.grain_dimensions
                    if payload.grain_dimensions is not None
                    else row.grain_dimensions_json
                ),
            )
            self._validate_definition(project_id, candidate)
        for field, value in values.items():
            setattr(row, "grain_dimensions_json" if field == "grain_dimensions" else field, value)
        row.updated_at = utc_now()
        self.session.flush()
        AuditRepository(self.session).append(
            action="semantic_metric.updated",
            result="success",
            summary={"changed_fields": sorted(values)},
            project_id=project_id,
            subject_id=subject_id,
            object_type="semantic_metric",
            object_id=metric_id,
            request_id=request_id,
        )
        return semantic_metric_to_schema(row)

    def revalidate_for_schema(self, project_id: str, dataset_version_id: str) -> int:
        columns = {
            row.name: row
            for row in self.session.scalars(
                select(ColumnSchemaRow).where(
                    ColumnSchemaRow.project_id == project_id,
                    ColumnSchemaRow.dataset_version_id == dataset_version_id,
                )
            )
        }
        rows = self.metrics.list_active_for_version(
            project_id=project_id, dataset_version_id=dataset_version_id
        )
        stale = 0
        for row in rows:
            source = columns.get(row.source_column or "") if row.source_column else None
            invalid_source = row.aggregation != "count" and (
                source is None
                or source.sensitive
                or (
                    row.aggregation in {"sum", "average", "minimum", "maximum"}
                    and source.physical_type not in {"integer", "float"}
                )
            )
            invalid_grain = any(name not in columns for name in row.grain_dimensions_json)
            if invalid_source or invalid_grain:
                row.status = "stale"
                row.updated_at = utc_now()
                stale += 1
        self.session.flush()
        return stale
