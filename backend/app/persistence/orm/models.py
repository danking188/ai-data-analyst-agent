from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.persistence.types import UTCDateTime


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'disabled')", name="ck_users_status"),
        UniqueConstraint("username", name="uq_users_username"),
        Index("ix_users_status_created_at", "status", "created_at"),
    )

    user_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    username: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    password_updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ProjectRow(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="ck_projects_status"),
        Index("ix_projects_status_updated_at", "status", "updated_at"),
    )

    project_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    current_dataset_version_id: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
        comment="Application-validated pointer; intentionally not an FK to avoid a DDL cycle.",
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class ProjectMemberRow(Base):
    __tablename__ = "project_members"
    __table_args__ = (
        CheckConstraint("role IN ('owner', 'editor', 'viewer')", name="ck_project_members_role"),
    )

    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.project_id", ondelete="RESTRICT"), primary_key=True
    )
    subject_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)


class DatasetRow(Base):
    __tablename__ = "datasets"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('csv', 'xls', 'xlsx', 'parquet')",
            name="ck_datasets_type",
        ),
        CheckConstraint("status IN ('active', 'archived')", name="ck_datasets_status"),
        Index("ix_datasets_project_created", "project_id", "created_at"),
        Index("ix_datasets_project_status", "project_id", "status"),
    )

    dataset_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    current_version_id: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
        comment="Application-validated pointer; intentionally not an FK to avoid a DDL cycle.",
    )
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class DatasetVersionRow(Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (
        UniqueConstraint("dataset_id", "version_number", name="uq_dataset_versions_number"),
        CheckConstraint(
            "status IN ('creating', 'ready', 'failed', 'archived')",
            name="ck_dataset_versions_status",
        ),
        CheckConstraint("kind IN ('raw', 'cleaned', 'modeled')", name="ck_dataset_versions_kind"),
        CheckConstraint(
            "(kind != 'raw') OR parent_version_id IS NULL",
            name="ck_raw_version_without_parent",
        ),
        Index("ix_dataset_versions_project_created", "project_id", "created_at"),
        Index(
            "ix_dataset_versions_dataset_status_number",
            "dataset_id",
            "status",
            "version_number",
        ),
        Index("ix_dataset_versions_file_hash", "file_hash"),
    )

    version_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("datasets.dataset_id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("dataset_versions.version_id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    sheet_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parse_options_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source_storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    data_storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    data_checksum: Mapped[str | None] = mapped_column(String(71), nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    row_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False)
    operation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    ready_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_detail_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class JobRow(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('dataset_ingestion', 'version_comparison', 'quality_scan', "
            "'cleaning_preview', 'cleaning_execute', 'analysis_run', 'report_export', "
            "'assistant_turn')",
            name="ck_jobs_kind",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'cancelling', 'cancelled', "
            "'blocked', 'succeeded', 'failed')",
            name="ck_jobs_status",
        ),
        CheckConstraint("progress BETWEEN 0 AND 100", name="ck_jobs_progress"),
        Index("ix_jobs_status_created", "status", "created_at"),
        Index("ix_jobs_project_kind_created", "project_id", "kind", "created_at"),
    )

    job_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False)
    current_step: Mapped[str | None] = mapped_column(String(160), nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    retry_after_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(160), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class IdempotencyKeyRow(Base):
    __tablename__ = "idempotency_keys"

    subject_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    method: Mapped[str] = mapped_column(String(8), primary_key=True)
    path: Mapped[str] = mapped_column(String(500), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    job_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("jobs.job_id", ondelete="RESTRICT"), nullable=True
    )
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class AuditLogRow(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint("result IN ('success', 'denied', 'failed')", name="ck_audit_result"),
        Index("ix_audit_project_created", "project_id", "created_at"),
        Index("ix_audit_request_id", "request_id"),
        Index("ix_audit_object", "object_type", "object_id", "created_at"),
    )

    audit_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=True
    )
    subject_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    object_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    object_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(71), nullable=True)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
