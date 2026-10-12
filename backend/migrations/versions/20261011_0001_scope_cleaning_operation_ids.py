"""scope cleaning operation identifiers to their plan

The API contract only promises that ``operation_id`` is unique within one cleaning plan
(``CleaningPlanCreate``/``CleaningPlanUpdate`` reject duplicates inside a single request),
but the table declared it as a global primary key. Reusing an identifier across two plans of
the same project therefore failed with ``UNIQUE constraint failed:
cleaning_operations.operation_id``, which has no handler and surfaced as HTTP 500.

SQLite cannot alter a primary key in place, so the table is rebuilt explicitly. The
rebuild only widens uniqueness: every existing row already satisfied the stricter global
constraint, so no row can conflict with ``(plan_id, operation_id)``.

Revision ID: 20261011_0001
Revises: 20260917_0001
Create Date: 2026-10-11 21:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261011_0001"
down_revision: str | Sequence[str] | None = "20260917_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "cleaning_operations"
REBUILD_TABLE = "cleaning_operations_scoped"
COLUMNS = (
    "operation_id",
    "plan_id",
    "position",
    "operation",
    "column_name",
    "parameters_json",
    "reason",
    "issue_ids_json",
    "estimated_affected_rows",
    "risk_level",
    "reversible",
)
OPERATION_TYPE_CHECK = (
    "operation IN ('impute_missing', 'drop_duplicates', 'cast_type', 'replace_values', "
    "'normalize_category', 'filter_rows', 'add_missing_indicator')"
)


def _create_table(name: str, primary_key: Sequence[str]) -> None:
    op.create_table(
        name,
        sa.Column("operation_id", sa.String(length=40), nullable=False),
        sa.Column("plan_id", sa.String(length=40), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=40), nullable=False),
        sa.Column("column_name", sa.String(length=255), nullable=True),
        sa.Column("parameters_json", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("issue_ids_json", sa.JSON(), nullable=False),
        sa.Column("estimated_affected_rows", sa.BigInteger(), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("reversible", sa.Boolean(), nullable=False),
        sa.CheckConstraint(OPERATION_TYPE_CHECK, name="ck_cleaning_operation_type"),
        sa.CheckConstraint(
            "risk_level IN ('low', 'medium', 'high')", name="ck_cleaning_operation_risk"
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["cleaning_plans.plan_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint(*primary_key),
        sa.UniqueConstraint("plan_id", "position", name="uq_cleaning_operation_position"),
    )


def _rebuild(primary_key: Sequence[str]) -> None:
    columns = ", ".join(COLUMNS)
    _create_table(REBUILD_TABLE, primary_key)
    op.execute(f"INSERT INTO {REBUILD_TABLE} ({columns}) SELECT {columns} FROM {TABLE}")
    op.drop_table(TABLE)
    op.rename_table(REBUILD_TABLE, TABLE)


def upgrade() -> None:
    _rebuild(["plan_id", "operation_id"])


def downgrade() -> None:
    # The old constraint is only satisfiable if no identifier is shared between plans. Once the
    # widened behaviour has been used, rolling back would have to delete real operations, so
    # refuse instead of destroying data silently.
    duplicate = op.get_bind().execute(
        sa.text(
            "SELECT operation_id FROM cleaning_operations "
            "GROUP BY operation_id HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).scalar()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot restore the global primary key on cleaning_operations: operation_id "
            f"{duplicate!r} is used by more than one cleaning plan. Resolve the duplicate rows "
            "before downgrading to 20260917_0001."
        )
    _rebuild(["operation_id"])
