from __future__ import annotations

from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import DataPreview, PreviewColumn
from app.core.config import Settings
from app.core.cursor import CursorCodec, PreviewCursor
from app.domain.errors import not_found, state_conflict, validation_error
from app.persistence.orm.models import DatasetVersionRow
from app.persistence.orm.workflow_models import ColumnSchemaRow
from app.persistence.repositories.projects import ProjectRepository
from app.storage.files import get_file_storage


class PreviewService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.storage = get_file_storage()
        self.cursor = CursorCodec(settings.jwt_secret)

    def preview(
        self,
        *,
        project_id: str,
        dataset_id: str,
        version_id: str,
        subject_id: str,
        cursor_token: str | None,
        limit: int,
        requested_columns: list[str] | None,
    ) -> DataPreview:
        if ProjectRepository(self.session).get_for_subject(project_id, subject_id) is None:
            raise not_found()
        version = self.session.scalar(
            select(DatasetVersionRow).where(
                DatasetVersionRow.project_id == project_id,
                DatasetVersionRow.dataset_id == dataset_id,
                DatasetVersionRow.version_id == version_id,
            )
        )
        if version is None:
            raise not_found()
        if version.status != "ready" or not version.data_storage_key or not version.data_checksum:
            raise state_conflict("数据版本尚未准备完成", status=version.status)

        path = self.storage.resolve_key(version.data_storage_key)
        parquet = pq.ParquetFile(path)
        available = parquet.schema_arrow.names
        selected = requested_columns or available
        unknown = sorted(set(selected) - set(available))
        if unknown:
            raise validation_error("请求包含不存在的字段", columns=unknown)
        offset = self._offset(cursor_token, version)
        rows = self._read_rows(parquet, selected, offset=offset, limit=limit + 1)
        has_more = len(rows) > limit
        rows = rows[:limit]

        schema_rows = list(
            self.session.scalars(
                select(ColumnSchemaRow)
                .where(
                    ColumnSchemaRow.dataset_version_id == version_id,
                    ColumnSchemaRow.name.in_(selected),
                )
                .order_by(ColumnSchemaRow.ordinal_position)
            )
        )
        schema_by_name = {row.name: row for row in schema_rows}
        masked_columns = [
            name for name in selected if name in schema_by_name and schema_by_name[name].sensitive
        ]
        for row in rows:
            for name in masked_columns:
                if row.get(name) is not None:
                    row[name] = "******"
        next_cursor = (
            self.cursor.encode(
                PreviewCursor(
                    version_id=version_id,
                    offset=offset + limit,
                    checksum=version.data_checksum,
                )
            )
            if has_more
            else None
        )
        return DataPreview(
            columns=[
                PreviewColumn(
                    name=name,
                    physical_type=(
                        schema_by_name[name].physical_type
                        if name in schema_by_name
                        else str(parquet.schema_arrow.field(name).type)
                    ),
                    semantic_type=(
                        schema_by_name[name].semantic_type if name in schema_by_name else None
                    ),
                    masked=name in masked_columns,
                )
                for name in selected
            ],
            rows=rows,
            next_cursor=next_cursor,
            has_more=has_more,
            masked_columns=masked_columns,
        )

    def _offset(self, token: str | None, version: DatasetVersionRow) -> int:
        if token is None:
            return 0
        cursor = self.cursor.decode(token)
        if cursor.version_id != version.version_id or cursor.checksum != version.data_checksum:
            raise validation_error("cursor 与当前数据版本不匹配")
        if cursor.offset < 0:
            raise validation_error("cursor offset 无效")
        return cursor.offset

    @staticmethod
    def _read_rows(
        parquet: pq.ParquetFile,
        columns: list[str],
        *,
        offset: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        remaining_skip = offset
        rows: list[dict[str, Any]] = []
        for group_index in range(parquet.num_row_groups):
            group_rows = parquet.metadata.row_group(group_index).num_rows
            if remaining_skip >= group_rows:
                remaining_skip -= group_rows
                continue
            table = parquet.read_row_group(group_index, columns=columns)
            if remaining_skip:
                table = table.slice(remaining_skip)
                remaining_skip = 0
            needed = limit - len(rows)
            rows.extend(pa.Table.from_batches(table.to_batches()).slice(0, needed).to_pylist())
            if len(rows) >= limit:
                break
        return rows
