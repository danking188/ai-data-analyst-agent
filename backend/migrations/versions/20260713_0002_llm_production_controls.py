"""add llm production controls

Revision ID: 20260713_0002
Revises: 20260713_0001
Create Date: 2026-07-13 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.persistence.types

revision: str = "20260713_0002"
down_revision: str | Sequence[str] | None = "20260713_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_provider_states",
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("opened_at", app.persistence.types.UTCDateTime(), nullable=True),
        sa.Column("updated_at", app.persistence.types.UTCDateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('closed', 'open', 'half_open')",
            name="ck_llm_provider_states_status",
        ),
        sa.PrimaryKeyConstraint("provider"),
    )


def downgrade() -> None:
    op.drop_table("llm_provider_states")
