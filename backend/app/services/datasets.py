from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    Dataset,
    DatasetPage,
    DatasetVersion,
    DatasetVersionPage,
)
from app.domain.errors import not_found, permission_denied, state_conflict
from app.persistence.orm.models import DatasetRow, DatasetVersionRow
from app.persistence.repositories.datasets import DatasetRepository
from app.persistence.repositories.projects import ProjectRepository


def dataset_to_schema(row: DatasetRow, version_count: int) -> Dataset:
    return Dataset(
        dataset_id=row.dataset_id,
        project_id=row.project_id,
        name=row.name,
        source_type=row.source_type,
        status=row.status,
        current_version_id=row.current_version_id,
        version_count=version_count,
        created_at=row.created_at,
    )


def version_to_schema(row: DatasetVersionRow) -> DatasetVersion:
    return DatasetVersion(
        version_id=row.version_id,
        dataset_id=row.dataset_id,
        project_id=row.project_id,
        version_number=row.version_number,
        status=row.status,
        kind=row.kind,
        parent_version_id=row.parent_version_id,
        source_file_name=row.source_file_name,
        sheet_name=row.sheet_name,
        file_hash=row.file_hash,
        row_count=row.row_count,
        column_count=row.column_count,
        operation_summary=row.operation_summary,
        created_at=row.created_at,
    )


class DatasetService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.datasets = DatasetRepository(session)
        self.projects = ProjectRepository(session)

    def require_project_role(
        self,
        project_id: str,
        subject_id: str,
        *,
        editable: bool,
    ) -> str:
        result = self.projects.get_for_subject(project_id, subject_id)
        if result is None:
            raise not_found()
        project, role = result
        if project.status != "active" and editable:
            raise state_conflict("归档项目不能创建数据")
        if editable and role not in {"owner", "editor"}:
            raise permission_denied()
        return role

    def list(
        self,
        project_id: str,
        *,
        subject_id: str,
        page: int,
        page_size: int,
    ) -> DatasetPage:
        self.require_project_role(project_id, subject_id, editable=False)
        result = self.datasets.list_datasets(
            project_id=project_id,
            page=page,
            page_size=page_size,
        )
        count_rows: list[tuple[str, int]] = list(
            self.session.execute(
                select(DatasetVersionRow.dataset_id, func.count())
                .where(DatasetVersionRow.dataset_id.in_([row.dataset_id for row in result.items]))
                .group_by(DatasetVersionRow.dataset_id)
            ).tuples()
        )
        counts = dict(count_rows)
        return DatasetPage(
            items=[
                dataset_to_schema(row, int(counts.get(row.dataset_id, 0))) for row in result.items
            ],
            page=result.page,
            page_size=result.page_size,
            total=result.total,
            has_more=result.has_more,
        )

    def get(
        self,
        project_id: str,
        dataset_id: str,
        *,
        subject_id: str,
    ) -> Dataset:
        self.require_project_role(project_id, subject_id, editable=False)
        row = self.datasets.get_dataset(project_id=project_id, dataset_id=dataset_id)
        count = self.session.scalar(
            select(func.count())
            .select_from(DatasetVersionRow)
            .where(DatasetVersionRow.dataset_id == dataset_id)
        )
        return dataset_to_schema(row, int(count or 0))

    def list_versions(
        self,
        project_id: str,
        dataset_id: str,
        *,
        subject_id: str,
        page: int,
        page_size: int,
        status: str | None,
    ) -> DatasetVersionPage:
        self.require_project_role(project_id, subject_id, editable=False)
        self.datasets.get_dataset(project_id=project_id, dataset_id=dataset_id)
        result = self.datasets.list_versions(
            project_id=project_id,
            dataset_id=dataset_id,
            page=page,
            page_size=page_size,
            status=status,
        )
        return DatasetVersionPage(
            items=[version_to_schema(row) for row in result.items],
            page=result.page,
            page_size=result.page_size,
            total=result.total,
            has_more=result.has_more,
        )

    def get_version(
        self,
        project_id: str,
        dataset_id: str,
        version_id: str,
        *,
        subject_id: str,
    ) -> DatasetVersion:
        self.require_project_role(project_id, subject_id, editable=False)
        row = self.datasets.get_version(
            project_id=project_id,
            dataset_id=dataset_id,
            version_id=version_id,
        )
        return version_to_schema(row)

    def activate_version(
        self,
        project_id: str,
        dataset_id: str,
        version_id: str,
        *,
        subject_id: str,
    ) -> Dataset:
        self.require_project_role(project_id, subject_id, editable=True)
        self.datasets.activate_version(
            project_id=project_id,
            dataset_id=dataset_id,
            version_id=version_id,
        )
        dataset = self.datasets.get_dataset(project_id=project_id, dataset_id=dataset_id)
        count = self.session.scalar(
            select(func.count())
            .select_from(DatasetVersionRow)
            .where(DatasetVersionRow.dataset_id == dataset_id)
        )
        return dataset_to_schema(dataset, int(count or 0))
