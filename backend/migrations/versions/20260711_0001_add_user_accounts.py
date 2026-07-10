"""add persistent user accounts

Revision ID: 20260711_0001
Revises: 0d903f0dacf9
Create Date: 2026-07-11 00:00:00
"""

from collections.abc import Sequence

import app.persistence.types
import sqlalchemy as sa
from alembic import op

revision: str = "20260711_0001"
down_revision: str | Sequence[str] | None = "0d903f0dacf9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(length=40), nullable=False),
        sa.Column("username", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_until", app.persistence.types.UTCDateTime(), nullable=True),
        sa.Column("last_login_at", app.persistence.types.UTCDateTime(), nullable=True),
        sa.Column("password_updated_at", app.persistence.types.UTCDateTime(), nullable=False),
        sa.Column("created_at", app.persistence.types.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.persistence.types.UTCDateTime(), nullable=False),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_users_status"),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index("ix_users_status_created_at", ["status", "created_at"])


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index("ix_users_status_created_at")
    op.drop_table("users")
