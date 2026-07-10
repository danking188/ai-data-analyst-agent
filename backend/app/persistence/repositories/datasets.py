from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.ids import new_id
from app.domain.errors import not_found, state_conflict, validation_error
from app.persistence.orm.models import DatasetRow, DatasetVersionRow, ProjectRow
from app.persistence.repositories.projects import Page


@dataclass(frozen=True, slots=True)
class DatasetVersionDraft:
    source_file_name: str
    source_type: str
    source_storage_key: str
    file_hash: str
    file_size_bytes: int
    sheet_name: str | None = None
    parse_options: dict[str, Any] | None = None
    parent_version_id: str | None = None
    kind: str = "raw"
    operation_summary: str | None = None


class DatasetRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_dataset(
        self,
        *,
        project_id: str,
        name: str,
        source_type: str,
        subject_id: str,
    ) -> DatasetRow:
        dataset = DatasetRow(
            dataset_id=new_id("ds_"),
            project_id=project_id,
            name=name,
            source_type=source_type,
            status="active",
            current_version_id=None,
            created_by=subject_id,
            created_at=utc_now(),
            archived_at=None,
        )
        self.session.add(dataset)
        self.session.flush()
        return dataset

    def get_dataset(self, *, project_id: str, dataset_id: str) -> DatasetRow:
        dataset = self.session.scalar(
            select(DatasetRow).where(
                DatasetRow.project_id == project_id,
                DatasetRow.dataset_id == dataset_id,
            )
        )
        if dataset is None:
            raise not_found()
        return dataset

    def list_datasets(
        self,
        *,
        project_id: str,
        page: int,
        page_size: int,
    ) -> Page[DatasetRow]:
        total = self.session.scalar(
            select(func.count()).select_from(DatasetRow).where(DatasetRow.project_id == project_id)
        )
        rows = list(
            self.session.scalars(
                select(DatasetRow)
                .where(DatasetRow.project_id == project_id)
                .order_by(DatasetRow.created_at.desc(), DatasetRow.dataset_id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return Page(rows, page, page_size, total or 0)

    def create_version(
        self,
        *,
        project_id: str,
        dataset_id: str,
        subject_id: str,
        draft: DatasetVersionDraft,
    ) -> DatasetVersionRow:
        dataset = self.get_dataset(project_id=project_id, dataset_id=dataset_id)
        if dataset.status != "active":
            raise state_conflict("已归档数据集不能创建新版本")
        if draft.kind == "raw" and draft.parent_version_id is not None:
            raise validation_error("原始版本不能包含父版本")
        if draft.kind != "raw" and draft.parent_version_id is None:
            raise validation_error("衍生版本必须包含父版本")
        if draft.parent_version_id is not None:
            parent = self.get_version(
                project_id=project_id,
                dataset_id=dataset_id,
                version_id=draft.parent_version_id,
            )
            if parent.status != "ready":
                raise state_conflict("只能从 ready 数据版本创建衍生版本")

        next_number = (
            self.session.scalar(
                select(func.coalesce(func.max(DatasetVersionRow.version_number), 0)).where(
                    DatasetVersionRow.dataset_id == dataset_id
                )
            )
            or 0
        ) + 1
        version = DatasetVersionRow(
            version_id=new_id("dsv_"),
            dataset_id=dataset_id,
            project_id=project_id,
            version_number=next_number,
            parent_version_id=draft.parent_version_id,
            status="creating",
            kind=draft.kind,
            source_file_name=draft.source_file_name,
            source_type=draft.source_type,
            sheet_name=draft.sheet_name,
            parse_options_json=draft.parse_options or {},
            source_storage_key=draft.source_storage_key,
            data_storage_key=None,
            file_hash=draft.file_hash,
            data_checksum=None,
            file_size_bytes=draft.file_size_bytes,
            row_count=0,
            column_count=0,
            operation_summary=draft.operation_summary,
            created_by=subject_id,
            created_at=utc_now(),
            ready_at=None,
            failure_code=None,
            failure_detail_json=None,
        )
        self.session.add(version)
        self.session.flush()
        return version

    def get_version(
        self,
        *,
        project_id: str,
        dataset_id: str,
        version_id: str,
    ) -> DatasetVersionRow:
        version = self.session.scalar(
            select(DatasetVersionRow).where(
                DatasetVersionRow.project_id == project_id,
                DatasetVersionRow.dataset_id == dataset_id,
                DatasetVersionRow.version_id == version_id,
            )
        )
        if version is None:
            raise not_found()
        return version

    def list_versions(
        self,
        *,
        project_id: str,
        dataset_id: str,
        page: int,
        page_size: int,
        status: str | None = None,
    ) -> Page[DatasetVersionRow]:
        filters = [
            DatasetVersionRow.project_id == project_id,
            DatasetVersionRow.dataset_id == dataset_id,
        ]
        if status is not None:
            filters.append(DatasetVersionRow.status == status)
        total = self.session.scalar(
            select(func.count()).select_from(DatasetVersionRow).where(*filters)
        )
        rows = list(
            self.session.scalars(
                select(DatasetVersionRow)
                .where(*filters)
                .order_by(DatasetVersionRow.version_number.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return Page(rows, page, page_size, total or 0)

    def mark_version_ready(
        self,
        version: DatasetVersionRow,
        *,
        data_storage_key: str,
        data_checksum: str,
        row_count: int,
        column_count: int,
    ) -> DatasetVersionRow:
        if version.status != "creating":
            raise state_conflict("只有 creating 数据版本可以标记为 ready")
        version.status = "ready"
        version.data_storage_key = data_storage_key
        version.data_checksum = data_checksum
        version.row_count = row_count
        version.column_count = column_count
        version.ready_at = utc_now()
        self.session.flush()
        return version

    def mark_version_failed(
        self,
        version: DatasetVersionRow,
        *,
        failure_code: str,
        failure_details: dict[str, Any],
    ) -> DatasetVersionRow:
        if version.status != "creating":
            raise state_conflict("只有 creating 数据版本可以标记为 failed")
        version.status = "failed"
        version.failure_code = failure_code
        version.failure_detail_json = failure_details
        self.session.flush()
        return version

    def activate_version(
        self,
        *,
        project_id: str,
        dataset_id: str,
        version_id: str,
    ) -> DatasetVersionRow:
        dataset = self.get_dataset(project_id=project_id, dataset_id=dataset_id)
        version = self.get_version(
            project_id=project_id,
            dataset_id=dataset_id,
            version_id=version_id,
        )
        if version.status != "ready":
            raise state_conflict("只有 ready 数据版本可以设为当前版本")
        project = self.session.get(ProjectRow, project_id)
        if project is None:
            raise not_found()
        dataset.current_version_id = version_id
        project.current_dataset_version_id = version_id
        project.updated_at = utc_now()
        project.revision += 1
        self.session.flush()
        return version
