"""add assistant runtime persistence

Revision ID: 20260713_0001
Revises: 20260711_0001
Create Date: 2026-07-13 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.persistence.types

revision: str = "20260713_0001"
down_revision: str | Sequence[str] | None = "20260711_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_JOB_KINDS = (
    "kind IN ('dataset_ingestion', 'version_comparison', 'quality_scan', "
    "'cleaning_preview', 'cleaning_execute', 'analysis_run', 'report_export')"
)
NEW_JOB_KINDS = OLD_JOB_KINDS[:-1] + ", 'assistant_turn')"


def upgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_constraint("ck_jobs_kind", type_="check")
        batch_op.create_check_constraint("ck_jobs_kind", NEW_JOB_KINDS)

    op.create_table(
        "assistant_conversations",
        sa.Column("conversation_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("dataset_version_id", sa.String(length=40), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("created_at", app.persistence.types.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.persistence.types.UTCDateTime(), nullable=False),
        sa.Column("archived_at", app.persistence.types.UTCDateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_assistant_conversations_status",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"], ["dataset_versions.version_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("conversation_id"),
    )
    with op.batch_alter_table("assistant_conversations", schema=None) as batch_op:
        batch_op.create_index(
            "ix_assistant_conversations_project_updated", ["project_id", "updated_at"]
        )
        batch_op.create_index("ix_assistant_conversations_project_status", ["project_id", "status"])

    op.create_table(
        "assistant_messages",
        sa.Column("message_id", sa.String(length=40), nullable=False),
        sa.Column("conversation_id", sa.String(length=40), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("content_json", sa.JSON(), nullable=True),
        sa.Column("parent_message_id", sa.String(length=40), nullable=True),
        sa.Column("job_id", sa.String(length=40), nullable=True),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("created_at", app.persistence.types.UTCDateTime(), nullable=False),
        sa.Column("completed_at", app.persistence.types.UTCDateTime(), nullable=True),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system_event', 'tool')",
            name="ck_assistant_messages_role",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'awaiting_confirmation', "
            "'completed', 'failed', 'cancelled')",
            name="ck_assistant_messages_status",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["assistant_conversations.conversation_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["parent_message_id"], ["assistant_messages.message_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("message_id"),
    )
    with op.batch_alter_table("assistant_messages", schema=None) as batch_op:
        batch_op.create_index(
            "ix_assistant_messages_conversation_created", ["conversation_id", "created_at"]
        )
        batch_op.create_index("ix_assistant_messages_job", ["job_id"])

    op.create_table(
        "llm_runs",
        sa.Column("llm_run_id", sa.String(length=40), nullable=False),
        sa.Column("message_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("job_id", sa.String(length=40), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("prompt_name", sa.String(length=120), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("model_call_count", sa.Integer(), nullable=False),
        sa.Column("tool_call_count", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("context_manifest_json", sa.JSON(), nullable=False),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("created_at", app.persistence.types.UTCDateTime(), nullable=False),
        sa.Column("completed_at", app.persistence.types.UTCDateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'awaiting_confirmation', 'succeeded', 'failed', 'cancelled')",
            name="ck_llm_runs_status",
        ),
        sa.CheckConstraint("model_call_count >= 0", name="ck_llm_runs_model_call_count"),
        sa.CheckConstraint("tool_call_count >= 0", name="ck_llm_runs_tool_call_count"),
        sa.CheckConstraint("input_tokens >= 0", name="ck_llm_runs_input_tokens"),
        sa.CheckConstraint("output_tokens >= 0", name="ck_llm_runs_output_tokens"),
        sa.CheckConstraint("latency_ms >= 0", name="ck_llm_runs_latency_ms"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["message_id"], ["assistant_messages.message_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("llm_run_id"),
    )
    with op.batch_alter_table("llm_runs", schema=None) as batch_op:
        batch_op.create_index("ix_llm_runs_project_created", ["project_id", "created_at"])
        batch_op.create_index("ix_llm_runs_message_created", ["message_id", "created_at"])
        batch_op.create_index("ix_llm_runs_job", ["job_id"])

    op.create_table(
        "llm_tool_calls",
        sa.Column("tool_call_id", sa.String(length=40), nullable=False),
        sa.Column("llm_run_id", sa.String(length=40), nullable=False),
        sa.Column("provider_tool_call_id", sa.String(length=160), nullable=True),
        sa.Column("tool_name", sa.String(length=160), nullable=False),
        sa.Column("tool_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False),
        sa.Column("arguments_json", sa.JSON(), nullable=False),
        sa.Column("result_resource_type", sa.String(length=64), nullable=True),
        sa.Column("result_resource_id", sa.String(length=40), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("approved_by", sa.String(length=160), nullable=True),
        sa.Column("approved_at", app.persistence.types.UTCDateTime(), nullable=True),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("created_at", app.persistence.types.UTCDateTime(), nullable=False),
        sa.Column("completed_at", app.persistence.types.UTCDateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('proposed', 'approved', 'running', 'succeeded', 'failed', 'rejected')",
            name="ck_llm_tool_calls_status",
        ),
        sa.ForeignKeyConstraint(["llm_run_id"], ["llm_runs.llm_run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tool_call_id"),
        sa.UniqueConstraint(
            "llm_run_id", "provider_tool_call_id", name="uq_llm_tool_calls_provider_id"
        ),
    )
    with op.batch_alter_table("llm_tool_calls", schema=None) as batch_op:
        batch_op.create_index("ix_llm_tool_calls_run_created", ["llm_run_id", "created_at"])
        batch_op.create_index("ix_llm_tool_calls_status", ["status"])

    op.create_table(
        "assistant_feedback",
        sa.Column("feedback_id", sa.String(length=40), nullable=False),
        sa.Column("message_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("rating", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("created_at", app.persistence.types.UTCDateTime(), nullable=False),
        sa.CheckConstraint(
            "rating IN ('helpful', 'not_helpful')", name="ck_assistant_feedback_rating"
        ),
        sa.CheckConstraint(
            "reason IS NULL OR reason IN ('incorrect', 'unsupported', 'incomplete', "
            "'unsafe', 'hard_to_understand', 'other')",
            name="ck_assistant_feedback_reason",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"], ["assistant_messages.message_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("feedback_id"),
        sa.UniqueConstraint(
            "message_id", "created_by", name="uq_assistant_feedback_message_subject"
        ),
    )
    with op.batch_alter_table("assistant_feedback", schema=None) as batch_op:
        batch_op.create_index("ix_assistant_feedback_project_created", ["project_id", "created_at"])


def downgrade() -> None:
    with op.batch_alter_table("assistant_feedback", schema=None) as batch_op:
        batch_op.drop_index("ix_assistant_feedback_project_created")
    op.drop_table("assistant_feedback")
    with op.batch_alter_table("llm_tool_calls", schema=None) as batch_op:
        batch_op.drop_index("ix_llm_tool_calls_status")
        batch_op.drop_index("ix_llm_tool_calls_run_created")
    op.drop_table("llm_tool_calls")
    with op.batch_alter_table("llm_runs", schema=None) as batch_op:
        batch_op.drop_index("ix_llm_runs_job")
        batch_op.drop_index("ix_llm_runs_message_created")
        batch_op.drop_index("ix_llm_runs_project_created")
    op.drop_table("llm_runs")
    with op.batch_alter_table("assistant_messages", schema=None) as batch_op:
        batch_op.drop_index("ix_assistant_messages_job")
        batch_op.drop_index("ix_assistant_messages_conversation_created")
    op.drop_table("assistant_messages")
    with op.batch_alter_table("assistant_conversations", schema=None) as batch_op:
        batch_op.drop_index("ix_assistant_conversations_project_status")
        batch_op.drop_index("ix_assistant_conversations_project_updated")
    op.drop_table("assistant_conversations")
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_constraint("ck_jobs_kind", type_="check")
        batch_op.create_check_constraint("ck_jobs_kind", OLD_JOB_KINDS)
