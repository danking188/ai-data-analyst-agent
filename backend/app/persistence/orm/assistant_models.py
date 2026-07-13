from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
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


class AssistantConversationRow(Base):
    __tablename__ = "assistant_conversations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_assistant_conversations_status",
        ),
        Index(
            "ix_assistant_conversations_project_updated",
            "project_id",
            "updated_at",
        ),
        Index(
            "ix_assistant_conversations_project_status",
            "project_id",
            "status",
        ),
    )

    conversation_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    dataset_version_id: Mapped[str | None] = mapped_column(
        String(40),
        ForeignKey("dataset_versions.version_id", ondelete="RESTRICT"),
        nullable=True,
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class AssistantMessageRow(Base):
    __tablename__ = "assistant_messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant', 'system_event', 'tool')",
            name="ck_assistant_messages_role",
        ),
        CheckConstraint(
            "status IN ('queued', 'processing', 'awaiting_confirmation', "
            "'completed', 'failed', 'cancelled')",
            name="ck_assistant_messages_status",
        ),
        Index(
            "ix_assistant_messages_conversation_created",
            "conversation_id",
            "created_at",
        ),
        Index("ix_assistant_messages_job", "job_id"),
    )

    message_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("assistant_conversations.conversation_id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    parent_message_id: Mapped[str | None] = mapped_column(
        String(40),
        ForeignKey("assistant_messages.message_id", ondelete="RESTRICT"),
        nullable=True,
    )
    job_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("jobs.job_id", ondelete="RESTRICT"), nullable=True
    )
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class LLMRunRow(Base):
    __tablename__ = "llm_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'awaiting_confirmation', 'succeeded', 'failed', 'cancelled')",
            name="ck_llm_runs_status",
        ),
        CheckConstraint("model_call_count >= 0", name="ck_llm_runs_model_call_count"),
        CheckConstraint("tool_call_count >= 0", name="ck_llm_runs_tool_call_count"),
        CheckConstraint("input_tokens >= 0", name="ck_llm_runs_input_tokens"),
        CheckConstraint("output_tokens >= 0", name="ck_llm_runs_output_tokens"),
        CheckConstraint("latency_ms >= 0", name="ck_llm_runs_latency_ms"),
        Index("ix_llm_runs_project_created", "project_id", "created_at"),
        Index("ix_llm_runs_message_created", "message_id", "created_at"),
        Index("ix_llm_runs_job", "job_id"),
    )

    llm_run_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    message_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("assistant_messages.message_id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False
    )
    job_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("jobs.job_id", ondelete="RESTRICT"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_name: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    model_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    context_manifest_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class LLMToolCallRow(Base):
    __tablename__ = "llm_tool_calls"
    __table_args__ = (
        CheckConstraint(
            "status IN ('proposed', 'approved', 'running', 'succeeded', 'failed', 'rejected')",
            name="ck_llm_tool_calls_status",
        ),
        UniqueConstraint(
            "llm_run_id",
            "provider_tool_call_id",
            name="uq_llm_tool_calls_provider_id",
        ),
        Index("ix_llm_tool_calls_run_created", "llm_run_id", "created_at"),
        Index("ix_llm_tool_calls_status", "status"),
    )

    tool_call_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    llm_run_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("llm_runs.llm_run_id", ondelete="CASCADE"), nullable=False
    )
    provider_tool_call_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    tool_name: Mapped[str] = mapped_column(String(160), nullable=False)
    tool_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, nullable=False)
    arguments_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result_resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_resource_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class AssistantFeedbackRow(Base):
    __tablename__ = "assistant_feedback"
    __table_args__ = (
        CheckConstraint(
            "rating IN ('helpful', 'not_helpful')",
            name="ck_assistant_feedback_rating",
        ),
        CheckConstraint(
            "reason IS NULL OR reason IN ('incorrect', 'unsupported', 'incomplete', "
            "'unsafe', 'hard_to_understand', 'other')",
            name="ck_assistant_feedback_reason",
        ),
        UniqueConstraint("message_id", "created_by", name="uq_assistant_feedback_message_subject"),
        Index("ix_assistant_feedback_project_created", "project_id", "created_at"),
    )

    feedback_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    message_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("assistant_messages.message_id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False
    )
    rating: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class LLMProviderStateRow(Base):
    __tablename__ = "llm_provider_states"
    __table_args__ = (
        CheckConstraint(
            "status IN ('closed', 'open', 'half_open')",
            name="ck_llm_provider_states_status",
        ),
    )

    provider: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    opened_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
