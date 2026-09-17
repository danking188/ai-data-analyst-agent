from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import SemanticMetricCreate
from app.core.clock import utc_now
from app.core.ids import new_id
from app.domain.errors import not_found
from app.persistence.orm.workflow_models import SemanticMetricRow
from app.persistence.repositories.projects import Page


class SemanticMetricRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self, *, project_id: str, payload: SemanticMetricCreate, subject_id: str
    ) -> SemanticMetricRow:
        now = utc_now()
        row = SemanticMetricRow(
            metric_id=new_id("metric_"),
            project_id=project_id,
            dataset_version_id=payload.dataset_version_id,
            name=payload.name,
            description=payload.description,
            source_column=payload.source_column,
            aggregation=payload.aggregation,
            unit=payload.unit,
            grain_dimensions_json=payload.grain_dimensions,
            status="active",
            created_by=subject_id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def list(
        self,
        *,
        project_id: str,
        dataset_version_id: str | None,
        page: int,
        page_size: int,
        include_archived: bool = False,
    ) -> Page[SemanticMetricRow]:
        filters = [SemanticMetricRow.project_id == project_id]
        if dataset_version_id is not None:
            filters.append(SemanticMetricRow.dataset_version_id == dataset_version_id)
        if not include_archived:
            filters.append(SemanticMetricRow.status != "archived")
        total = int(
            self.session.scalar(
                select(func.count()).select_from(SemanticMetricRow).where(*filters)
            )
            or 0
        )
        rows = list(
            self.session.scalars(
                select(SemanticMetricRow)
                .where(*filters)
                .order_by(SemanticMetricRow.name, SemanticMetricRow.metric_id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return Page(items=rows, page=page, page_size=page_size, total=total)

    def get(self, *, project_id: str, metric_id: str) -> SemanticMetricRow:
        row = self.session.scalar(
            select(SemanticMetricRow).where(
                SemanticMetricRow.project_id == project_id,
                SemanticMetricRow.metric_id == metric_id,
            )
        )
        if row is None:
            raise not_found()
        return row

    def list_active_for_version(
        self, *, project_id: str, dataset_version_id: str
    ) -> Sequence[SemanticMetricRow]:
        return list(
            self.session.scalars(
                select(SemanticMetricRow)
                .where(
                    SemanticMetricRow.project_id == project_id,
                    SemanticMetricRow.dataset_version_id == dataset_version_id,
                    SemanticMetricRow.status == "active",
                )
                .order_by(SemanticMetricRow.name)
            )
        )
