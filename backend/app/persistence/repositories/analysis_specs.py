from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import AnalysisSpecCreate
from app.core.clock import utc_now
from app.core.ids import new_id
from app.domain.errors import not_found, state_conflict, version_conflict
from app.persistence.orm.workflow_models import AnalysisSpecRow
from app.persistence.repositories.projects import Page


class AnalysisSpecRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        project_id: str,
        payload: AnalysisSpecCreate,
        warnings: list[str],
        subject_id: str,
    ) -> AnalysisSpecRow:
        now = utc_now()
        spec_id = new_id("spec_")
        row = self._row_from_payload(
            spec_id=spec_id,
            revision=1,
            project_id=project_id,
            payload=payload,
            warnings=warnings,
            subject_id=subject_id,
            created_at=now,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def latest(self, *, project_id: str, spec_id: str) -> AnalysisSpecRow:
        row = self.session.scalar(
            select(AnalysisSpecRow)
            .where(
                AnalysisSpecRow.project_id == project_id,
                AnalysisSpecRow.spec_id == spec_id,
            )
            .order_by(AnalysisSpecRow.revision.desc())
            .limit(1)
        )
        if row is None:
            raise not_found()
        return row

    def list_latest(
        self,
        *,
        project_id: str,
        page: int,
        page_size: int,
        dataset_version_id: str | None,
    ) -> Page[AnalysisSpecRow]:
        latest_revisions = (
            select(
                AnalysisSpecRow.spec_id.label("spec_id"),
                func.max(AnalysisSpecRow.revision).label("revision"),
            )
            .where(AnalysisSpecRow.project_id == project_id)
            .group_by(AnalysisSpecRow.spec_id)
            .subquery()
        )
        filters = [AnalysisSpecRow.project_id == project_id]
        if dataset_version_id is not None:
            filters.append(AnalysisSpecRow.dataset_version_id == dataset_version_id)
        base = (
            select(AnalysisSpecRow)
            .join(
                latest_revisions,
                (latest_revisions.c.spec_id == AnalysisSpecRow.spec_id)
                & (latest_revisions.c.revision == AnalysisSpecRow.revision),
            )
            .where(*filters)
        )
        total = int(self.session.scalar(select(func.count()).select_from(base.subquery())) or 0)
        items = list(
            self.session.scalars(
                base.order_by(AnalysisSpecRow.updated_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return Page(items=items, total=total, page=page, page_size=page_size)

    def revise(
        self,
        current: AnalysisSpecRow,
        *,
        expected_revision: int,
        payload: AnalysisSpecCreate,
        warnings: list[str],
        subject_id: str,
    ) -> AnalysisSpecRow:
        if current.revision != expected_revision:
            raise version_conflict(current.revision)
        if current.status != "draft":
            raise state_conflict("只有 draft AnalysisSpec 可以编辑", status=current.status)
        current.status = "superseded"
        current.updated_at = utc_now()
        row = self._row_from_payload(
            spec_id=current.spec_id,
            revision=current.revision + 1,
            project_id=current.project_id,
            payload=payload,
            warnings=warnings,
            subject_id=subject_id,
            created_at=current.created_at,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def confirm(self, current: AnalysisSpecRow) -> AnalysisSpecRow:
        if current.status != "draft":
            raise state_conflict("只有 draft AnalysisSpec 可以确认", status=current.status)
        current.status = "confirmed"
        current.updated_at = utc_now()
        self.session.flush()
        return current

    @staticmethod
    def _row_from_payload(
        *,
        spec_id: str,
        revision: int,
        project_id: str,
        payload: AnalysisSpecCreate,
        warnings: list[str],
        subject_id: str,
        created_at: datetime,
    ) -> AnalysisSpecRow:
        now = utc_now()
        return AnalysisSpecRow(
            spec_revision_id=f"{spec_id}:r{revision}",
            spec_id=spec_id,
            revision=revision,
            project_id=project_id,
            dataset_version_id=payload.dataset_version_id,
            name=payload.name,
            status="draft",
            task=payload.task,
            target=payload.target,
            entity_key=payload.entity_key,
            time_column=payload.time_column,
            prediction_time_description=payload.prediction_time_description,
            split_strategy=payload.split_strategy,
            group_column=payload.group_column,
            metrics_json=payload.metrics,
            included_columns_json=payload.included_columns,
            excluded_columns_json=payload.excluded_columns,
            random_seed=payload.random_seed,
            causal_interpretation_allowed=payload.causal_interpretation_allowed,
            validation_warnings_json=warnings,
            created_by=subject_id,
            created_at=created_at,
            updated_at=now,
        )
