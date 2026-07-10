from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.ids import new_id
from app.domain.errors import not_found, version_conflict
from app.ingest.profiler import ColumnProfile
from app.persistence.orm.workflow_models import ColumnSchemaRow


class ColumnSchemaRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_profiles(
        self,
        *,
        project_id: str,
        dataset_version_id: str,
        profiles: list[ColumnProfile],
    ) -> list[ColumnSchemaRow]:
        self.session.execute(
            delete(ColumnSchemaRow).where(ColumnSchemaRow.dataset_version_id == dataset_version_id)
        )
        now = utc_now()
        rows = [
            ColumnSchemaRow(
                column_schema_id=new_id("col_"),
                project_id=project_id,
                dataset_version_id=dataset_version_id,
                name=profile.name,
                ordinal_position=profile.position,
                physical_type=profile.physical_type,
                semantic_type=profile.semantic_type,
                analysis_role=profile.analysis_role,
                confidence=profile.confidence,
                evidence_json=profile.evidence,
                profile_json=profile.profile,
                date_format=None,
                ordinal_values_json=None,
                sensitive=profile.sensitive,
                user_confirmed=False,
                revision=1,
                created_at=now,
                updated_at=now,
            )
            for profile in profiles
        ]
        self.session.add_all(rows)
        self.session.flush()
        return rows

    def list_for_version(self, dataset_version_id: str) -> list[ColumnSchemaRow]:
        return list(
            self.session.scalars(
                select(ColumnSchemaRow)
                .where(ColumnSchemaRow.dataset_version_id == dataset_version_id)
                .order_by(ColumnSchemaRow.ordinal_position)
            )
        )

    def current_revision(self, dataset_version_id: str) -> int:
        revision = self.session.scalar(
            select(func.max(ColumnSchemaRow.revision)).where(
                ColumnSchemaRow.dataset_version_id == dataset_version_id
            )
        )
        if revision is None:
            raise not_found("字段 Schema 尚未生成")
        return int(revision)

    def apply_overrides(
        self,
        *,
        dataset_version_id: str,
        expected_revision: int,
        changes: list[dict[str, object]],
    ) -> list[ColumnSchemaRow]:
        rows = self.list_for_version(dataset_version_id)
        if not rows:
            raise not_found("字段 Schema 尚未生成")
        current_revision = max(row.revision for row in rows)
        if current_revision != expected_revision:
            raise version_conflict(current_revision)

        rows_by_name = {row.name: row for row in rows}
        unknown = [
            str(change["column"]) for change in changes if change["column"] not in rows_by_name
        ]
        if unknown:
            raise not_found(f"字段不存在：{', '.join(unknown)}")

        now = utc_now()
        allowed = {
            "semantic_type",
            "analysis_role",
            "date_format",
            "ordinal_values",
            "sensitive",
        }
        for change in changes:
            row = rows_by_name[str(change["column"])]
            for field, value in change.items():
                if field not in allowed:
                    continue
                target = "ordinal_values_json" if field == "ordinal_values" else field
                setattr(row, target, value)
            row.user_confirmed = True
            row.updated_at = now

        next_revision = current_revision + 1
        for row in rows:
            row.revision = next_revision
        self.session.flush()
        return rows

    def sensitive_columns(self, dataset_version_id: str) -> set[str]:
        return set(
            self.session.scalars(
                select(ColumnSchemaRow.name).where(
                    ColumnSchemaRow.dataset_version_id == dataset_version_id,
                    ColumnSchemaRow.sensitive.is_(True),
                )
            )
        )
