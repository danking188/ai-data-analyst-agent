from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.orm.models import Base
from app.persistence.types import UTCDateTime


class ColumnSchemaRow(Base):
    __tablename__ = "column_schemas"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "name", name="uq_column_schema_version_name"),
        CheckConstraint(
            "physical_type IN ('integer', 'float', 'string', 'boolean', "
            "'datetime', 'binary', 'unknown')",
            name="ck_column_schema_physical_type",
        ),
        CheckConstraint(
            "semantic_type IN ('numeric', 'categorical', 'datetime', 'boolean', "
            "'identifier', 'text', 'currency', 'percentage', 'ordinal', "
            "'geographic_code', 'unknown')",
            name="ck_column_schema_semantic_type",
        ),
        CheckConstraint(
            "analysis_role IN ('feature', 'target', 'entity_key', 'time', "
            "'identifier', 'text', 'excluded', 'undecided')",
            name="ck_column_schema_analysis_role",
        ),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_column_schema_confidence"),
        Index("ix_column_schema_version_role", "dataset_version_id", "analysis_role"),
    )

    column_schema_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False
    )
    dataset_version_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("dataset_versions.version_id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ordinal_position: Mapped[int] = mapped_column(Integer, nullable=False)
    physical_type: Mapped[str] = mapped_column(String(24), nullable=False)
    semantic_type: Mapped[str] = mapped_column(String(32), nullable=False)
    analysis_role: Mapped[str] = mapped_column(String(24), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    profile_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    date_format: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ordinal_values_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    user_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class QualityIssueRow(Base):
    __tablename__ = "quality_issues"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_quality_issue_severity",
        ),
        CheckConstraint(
            "status IN ('open', 'accepted', 'resolved', 'ignored')",
            name="ck_quality_issue_status",
        ),
        Index(
            "ix_quality_issue_version_status_severity",
            "dataset_version_id",
            "status",
            "severity",
        ),
        Index("ix_quality_issue_project_created", "project_id", "created_at"),
    )

    issue_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False
    )
    dataset_version_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("dataset_versions.version_id", ondelete="RESTRICT"),
        nullable=False,
    )
    issue_type: Mapped[str] = mapped_column(String(64), nullable=False)
    column_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    sample_rows_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_name: Mapped[str] = mapped_column(String(160), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by_plan_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("cleaning_plans.plan_id", ondelete="RESTRICT"), nullable=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class CleaningPlanRow(Base):
    __tablename__ = "cleaning_plans"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'awaiting_approval', 'approved', 'rejected', "
            "'executing', 'executed', 'failed')",
            name="ck_cleaning_plan_status",
        ),
        CheckConstraint(
            "decision IS NULL OR decision IN ('approve', 'reject')",
            name="ck_cleaning_plan_decision",
        ),
        Index("ix_cleaning_plan_project_created", "project_id", "created_at"),
        Index("ix_cleaning_plan_source_status", "source_version_id", "status"),
    )

    plan_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False
    )
    source_version_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("dataset_versions.version_id", ondelete="RESTRICT"),
        nullable=False,
    )
    result_version_id: Mapped[str | None] = mapped_column(
        String(40),
        ForeignKey("dataset_versions.version_id", ondelete="RESTRICT"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    preview_artifact_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("artifacts.artifact_id", ondelete="RESTRICT"), nullable=True
    )
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class CleaningOperationRow(Base):
    __tablename__ = "cleaning_operations"
    __table_args__ = (
        UniqueConstraint("plan_id", "position", name="uq_cleaning_operation_position"),
        CheckConstraint(
            "operation IN ('impute_missing', 'drop_duplicates', 'cast_type', "
            "'replace_values', 'normalize_category', 'filter_rows', "
            "'add_missing_indicator')",
            name="ck_cleaning_operation_type",
        ),
        CheckConstraint(
            "risk_level IN ('low', 'medium', 'high')",
            name="ck_cleaning_operation_risk",
        ),
    )

    operation_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    plan_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("cleaning_plans.plan_id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    operation: Mapped[str] = mapped_column(String(40), nullable=False)
    column_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parameters_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    issue_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    estimated_affected_rows: Mapped[int] = mapped_column(BigInteger, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    reversible: Mapped[bool] = mapped_column(Boolean, nullable=False)


class AnalysisSpecRow(Base):
    __tablename__ = "analysis_specs"
    __table_args__ = (
        UniqueConstraint("spec_id", "revision", name="uq_analysis_spec_revision"),
        CheckConstraint(
            "task IN ('descriptive', 'comparison', 'statistical_test', "
            "'binary_classification', 'multiclass_classification', 'regression')",
            name="ck_analysis_spec_task",
        ),
        CheckConstraint(
            "split_strategy IN ('none', 'random', 'stratified', 'temporal', 'group')",
            name="ck_analysis_spec_split",
        ),
        CheckConstraint(
            "status IN ('draft', 'confirmed', 'superseded')",
            name="ck_analysis_spec_status",
        ),
        Index("ix_analysis_spec_project_created", "project_id", "created_at"),
        Index("ix_analysis_spec_version_status", "dataset_version_id", "status"),
    )

    spec_revision_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    spec_id: Mapped[str] = mapped_column(String(40), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False
    )
    dataset_version_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("dataset_versions.version_id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    task: Mapped[str] = mapped_column(String(32), nullable=False)
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entity_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    time_column: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prediction_time_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    split_strategy: Mapped[str] = mapped_column(String(16), nullable=False)
    group_column: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metrics_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    included_columns_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    excluded_columns_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    random_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    causal_interpretation_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    validation_warnings_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class AnalysisRunRow(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        CheckConstraint(
            "run_kind IN ('eda', 'analysis', 'model', 'full')",
            name="ck_analysis_run_kind",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'blocked', 'succeeded', 'failed', 'cancelled')",
            name="ck_analysis_run_status",
        ),
        CheckConstraint("progress BETWEEN 0 AND 100", name="ck_analysis_run_progress"),
        Index("ix_analysis_run_project_created", "project_id", "created_at"),
        Index("ix_analysis_run_version_status", "dataset_version_id", "status"),
    )

    run_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False
    )
    dataset_version_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("dataset_versions.version_id", ondelete="RESTRICT"),
        nullable=False,
    )
    analysis_spec_revision_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("analysis_specs.spec_revision_id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_run_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("analysis_runs.run_id", ondelete="RESTRICT"), nullable=True
    )
    job_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("jobs.job_id", ondelete="RESTRICT"), nullable=True
    )
    run_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False)
    current_step_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    random_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    environment_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class AnalysisStepRow(Base):
    __tablename__ = "analysis_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "position", name="uq_analysis_step_position"),
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', "
            "'skipped', 'blocked', 'cancelled')",
            name="ck_analysis_step_status",
        ),
        Index("ix_analysis_step_run_status", "run_id", "status"),
    )

    step_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("analysis_runs.run_id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    tool_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    parameters_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class ArtifactRow(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        CheckConstraint(
            "type IN ('metric', 'table', 'chart', 'model', 'file', 'log', 'comparison')",
            name="ck_artifact_type",
        ),
        CheckConstraint(
            "status IN ('creating', 'ready', 'failed', 'expired')",
            name="ck_artifact_status",
        ),
        Index("ix_artifact_run_type", "run_id", "type"),
        Index("ix_artifact_version_created", "dataset_version_id", "created_at"),
    )

    artifact_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("analysis_runs.run_id", ondelete="RESTRICT"), nullable=True
    )
    dataset_version_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("dataset_versions.version_id", ondelete="RESTRICT"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    producer: Mapped[str] = mapped_column(String(160), nullable=False)
    producer_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    parameters_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    preview_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum: Mapped[str] = mapped_column(String(71), nullable=False)
    downloadable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    ready_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class ClaimRow(Base):
    __tablename__ = "claims"
    __table_args__ = (
        CheckConstraint("level BETWEEN 1 AND 5", name="ck_claim_level"),
        CheckConstraint(
            "validation_status IN ('pending', 'passed', 'failed')",
            name="ck_claim_validation_status",
        ),
        CheckConstraint(
            "publication_status IN ('draft', 'published', 'withdrawn')",
            name="ck_claim_publication_status",
        ),
        Index("ix_claim_run_validation", "run_id", "validation_status"),
        Index("ix_claim_version_publication", "dataset_version_id", "publication_status"),
    )

    claim_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("analysis_runs.run_id", ondelete="RESTRICT"), nullable=False
    )
    dataset_version_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("dataset_versions.version_id", ondelete="RESTRICT"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    limitations_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(16), nullable=False)
    validation_messages_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    publication_status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ClaimEvidenceRow(Base):
    __tablename__ = "claim_evidence"

    claim_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("claims.claim_id", ondelete="CASCADE"), primary_key=True
    )
    artifact_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("artifacts.artifact_id", ondelete="RESTRICT"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class ValidationResultRow(Base):
    __tablename__ = "validation_results"
    __table_args__ = (
        CheckConstraint(
            "status IN ('passed', 'failed')",
            name="ck_validation_result_status",
        ),
        Index("ix_validation_result_claim_created", "claim_id", "created_at"),
    )

    validation_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False
    )
    claim_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("claims.claim_id", ondelete="CASCADE"), nullable=False
    )
    validator: Mapped[str] = mapped_column(String(160), nullable=False)
    validator_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class UserDecisionRow(Base):
    __tablename__ = "user_decisions"
    __table_args__ = (
        Index("ix_user_decision_object", "object_type", "object_id", "created_at"),
        Index("ix_user_decision_project_created", "project_id", "created_at"),
    )

    decision_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False
    )
    subject_id: Mapped[str] = mapped_column(String(160), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str] = mapped_column(String(40), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ConversationSummaryRow(Base):
    __tablename__ = "conversation_summaries"
    __table_args__ = (
        UniqueConstraint("project_id", "conversation_id", name="uq_conversation_summary"),
        Index("ix_conversation_summary_project_updated", "project_id", "updated_at"),
    )

    summary_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False
    )
    conversation_id: Mapped[str] = mapped_column(String(80), nullable=False)
    dataset_version_id: Mapped[str | None] = mapped_column(
        String(40),
        ForeignKey("dataset_versions.version_id", ondelete="RESTRICT"),
        nullable=True,
    )
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    structured_context_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    last_message_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
