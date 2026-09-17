"""add agent structured semantics foundation

Revision ID: 20260917_0001
Revises: 20260713_0002
Create Date: 2026-09-17 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.persistence.types

revision: str = "20260917_0001"
down_revision: str | Sequence[str] | None = "20260713_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "semantic_metrics",
        sa.Column("metric_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("dataset_version_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_column", sa.String(length=255), nullable=True),
        sa.Column("aggregation", sa.String(length=24), nullable=False),
        sa.Column("unit", sa.String(length=40), nullable=True),
        sa.Column("grain_dimensions_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("created_at", app.persistence.types.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.persistence.types.UTCDateTime(), nullable=False),
        sa.CheckConstraint(
            "aggregation IN ('sum', 'average', 'minimum', 'maximum', 'count', 'distinct_count')",
            name="ck_semantic_metrics_aggregation",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'stale', 'archived')",
            name="ck_semantic_metrics_status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"], ["dataset_versions.version_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("metric_id"),
        sa.UniqueConstraint(
            "project_id",
            "dataset_version_id",
            "name",
            name="uq_semantic_metric_version_name",
        ),
    )
    with op.batch_alter_table("semantic_metrics", schema=None) as batch_op:
        batch_op.create_index(
            "ix_semantic_metrics_project_version",
            ["project_id", "dataset_version_id", "status"],
        )


def downgrade() -> None:
    with op.batch_alter_table("semantic_metrics", schema=None) as batch_op:
        batch_op.drop_index("ix_semantic_metrics_project_version")
    op.drop_table("semantic_metrics")
