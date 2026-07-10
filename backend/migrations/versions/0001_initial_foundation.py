"""create backend foundation tables

Revision ID: 0001_initial_foundation
Revises:
Create Date: 2026-07-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("project_id", sa.String(40), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("language", sa.String(10), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("current_dataset_version_id", sa.String(40), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_projects_status"),
    )
    op.create_index(
        "ix_projects_status_updated_at",
        "projects",
        ["status", "updated_at"],
    )

    op.create_table(
        "project_members",
        sa.Column("project_id", sa.String(40), nullable=False),
        sa.Column("subject_id", sa.String(160), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.CheckConstraint(
            "role IN ('owner', 'editor', 'viewer')",
            name="ck_project_members_role",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("project_id", "subject_id"),
    )

    op.create_table(
        "datasets",
        sa.Column("dataset_id", sa.String(40), primary_key=True),
        sa.Column("project_id", sa.String(40), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("current_version_id", sa.String(40), nullable=True),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "source_type IN ('csv', 'xls', 'xlsx', 'parquet')",
            name="ck_datasets_type",
        ),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_datasets_status"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_datasets_project_created",
        "datasets",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_datasets_project_status",
        "datasets",
        ["project_id", "status"],
    )

    op.create_table(
        "dataset_versions",
        sa.Column("version_id", sa.String(40), primary_key=True),
        sa.Column("dataset_id", sa.String(40), nullable=False),
        sa.Column("project_id", sa.String(40), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.String(40), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("source_file_name", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("sheet_name", sa.String(255), nullable=True),
        sa.Column("parse_options_json", sa.JSON(), nullable=False),
        sa.Column("source_storage_key", sa.Text(), nullable=False),
        sa.Column("data_storage_key", sa.Text(), nullable=True),
        sa.Column("file_hash", sa.String(71), nullable=False),
        sa.Column("data_checksum", sa.String(71), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=False),
        sa.Column("column_count", sa.Integer(), nullable=False),
        sa.Column("operation_summary", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("ready_at", sa.DateTime(), nullable=True),
        sa.Column("failure_code", sa.String(64), nullable=True),
        sa.Column("failure_detail_json", sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "status IN ('creating', 'ready', 'failed', 'archived')",
            name="ck_dataset_versions_status",
        ),
        sa.CheckConstraint(
            "kind IN ('raw', 'cleaned', 'modeled')",
            name="ck_dataset_versions_kind",
        ),
        sa.CheckConstraint(
            "(kind != 'raw') OR parent_version_id IS NULL",
            name="ck_raw_version_without_parent",
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.dataset_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["parent_version_id"],
            ["dataset_versions.version_id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "dataset_id",
            "version_number",
            name="uq_dataset_versions_number",
        ),
    )
    op.create_index(
        "ix_dataset_versions_project_created",
        "dataset_versions",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_dataset_versions_dataset_status_number",
        "dataset_versions",
        ["dataset_id", "status", "version_number"],
    )
    op.create_index(
        "ix_dataset_versions_file_hash",
        "dataset_versions",
        ["file_hash"],
    )

    op.create_table(
        "jobs",
        sa.Column("job_id", sa.String(40), primary_key=True),
        sa.Column("project_id", sa.String(40), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("current_step", sa.String(160), nullable=True),
        sa.Column("resource_type", sa.String(64), nullable=True),
        sa.Column("resource_id", sa.String(40), nullable=True),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("retry_after_ms", sa.Integer(), nullable=True),
        sa.Column("lease_owner", sa.String(160), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(), nullable=True),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('dataset_ingestion', 'version_comparison', 'quality_scan', "
            "'cleaning_preview', 'cleaning_execute', 'analysis_run', 'report_export')",
            name="ck_jobs_kind",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'cancelling', 'cancelled', "
            "'blocked', 'succeeded', 'failed')",
            name="ck_jobs_status",
        ),
        sa.CheckConstraint("progress BETWEEN 0 AND 100", name="ck_jobs_progress"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_jobs_status_created", "jobs", ["status", "created_at"])
    op.create_index(
        "ix_jobs_project_kind_created",
        "jobs",
        ["project_id", "kind", "created_at"],
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("subject_id", sa.String(160), nullable=False),
        sa.Column("method", sa.String(8), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("request_hash", sa.String(71), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=True),
        sa.Column("resource_id", sa.String(40), nullable=True),
        sa.Column("job_id", sa.String(40), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("subject_id", "method", "path", "idempotency_key"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("audit_id", sa.String(40), primary_key=True),
        sa.Column("project_id", sa.String(40), nullable=True),
        sa.Column("subject_id", sa.String(160), nullable=True),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("object_type", sa.String(64), nullable=True),
        sa.Column("object_id", sa.String(40), nullable=True),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("request_id", sa.String(80), nullable=True),
        sa.Column("ip_hash", sa.String(71), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "result IN ('success', 'denied', 'failed')",
            name="ck_audit_result",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_audit_project_created",
        "audit_logs",
        ["project_id", "created_at"],
    )
    op.create_index("ix_audit_request_id", "audit_logs", ["request_id"])
    op.create_index(
        "ix_audit_object",
        "audit_logs",
        ["object_type", "object_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_object", table_name="audit_logs")
    op.drop_index("ix_audit_request_id", table_name="audit_logs")
    op.drop_index("ix_audit_project_created", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_table("idempotency_keys")
    op.drop_index("ix_jobs_project_kind_created", table_name="jobs")
    op.drop_index("ix_jobs_status_created", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_dataset_versions_file_hash", table_name="dataset_versions")
    op.drop_index(
        "ix_dataset_versions_dataset_status_number",
        table_name="dataset_versions",
    )
    op.drop_index(
        "ix_dataset_versions_project_created",
        table_name="dataset_versions",
    )
    op.drop_table("dataset_versions")
    op.drop_index("ix_datasets_project_status", table_name="datasets")
    op.drop_index("ix_datasets_project_created", table_name="datasets")
    op.drop_table("datasets")
    op.drop_table("project_members")
    op.drop_index("ix_projects_status_updated_at", table_name="projects")
    op.drop_table("projects")
