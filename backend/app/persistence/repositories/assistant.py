from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.ids import new_id
from app.domain.errors import DomainError, not_found, state_conflict
from app.persistence.orm.assistant_models import (
    AssistantConversationRow,
    AssistantFeedbackRow,
    AssistantMessageRow,
    LLMProviderStateRow,
    LLMRunRow,
    LLMToolCallRow,
)
from app.persistence.orm.models import JobRow
from app.persistence.repositories.projects import Page


class AssistantRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_conversation(
        self,
        *,
        project_id: str,
        title: str,
        dataset_version_id: str | None,
        subject_id: str,
    ) -> AssistantConversationRow:
        now = utc_now()
        row = AssistantConversationRow(
            conversation_id=new_id("conv_"),
            project_id=project_id,
            title=title,
            status="active",
            dataset_version_id=dataset_version_id,
            summary=None,
            created_by=subject_id,
            created_at=now,
            updated_at=now,
            archived_at=None,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def list_conversations(
        self, *, project_id: str, page: int, page_size: int
    ) -> Page[AssistantConversationRow]:
        total = int(
            self.session.scalar(
                select(func.count())
                .select_from(AssistantConversationRow)
                .where(AssistantConversationRow.project_id == project_id)
            )
            or 0
        )
        rows = list(
            self.session.scalars(
                select(AssistantConversationRow)
                .where(AssistantConversationRow.project_id == project_id)
                .order_by(
                    AssistantConversationRow.updated_at.desc(),
                    AssistantConversationRow.conversation_id,
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return Page(items=rows, page=page, page_size=page_size, total=total)

    def get_conversation(
        self, *, project_id: str, conversation_id: str
    ) -> AssistantConversationRow:
        row = self.session.scalar(
            select(AssistantConversationRow).where(
                AssistantConversationRow.project_id == project_id,
                AssistantConversationRow.conversation_id == conversation_id,
            )
        )
        if row is None:
            raise not_found()
        return row

    def update_conversation(
        self,
        row: AssistantConversationRow,
        *,
        title: str | None = None,
        status: str | None = None,
        dataset_version_id: str | None = None,
        dataset_version_changed: bool = False,
        summary: str | None = None,
    ) -> AssistantConversationRow:
        now = utc_now()
        if title is not None:
            row.title = title
        if dataset_version_changed:
            row.dataset_version_id = dataset_version_id
        if summary is not None:
            row.summary = summary
        if status is not None and status != row.status:
            row.status = status
            row.archived_at = now if status == "archived" else None
        row.updated_at = now
        self.session.flush()
        return row

    def create_message(
        self,
        *,
        conversation_id: str,
        role: str,
        status: str,
        subject_id: str,
        content: str | None = None,
        content_json: dict[str, Any] | None = None,
        parent_message_id: str | None = None,
        job_id: str | None = None,
    ) -> AssistantMessageRow:
        now = utc_now()
        row = AssistantMessageRow(
            message_id=new_id("msg_"),
            conversation_id=conversation_id,
            role=role,
            status=status,
            content=content,
            content_json=content_json,
            parent_message_id=parent_message_id,
            job_id=job_id,
            created_by=subject_id,
            created_at=now,
            completed_at=now if status == "completed" else None,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def get_message(self, *, project_id: str, message_id: str) -> AssistantMessageRow:
        row = self.session.scalar(
            select(AssistantMessageRow)
            .join(
                AssistantConversationRow,
                AssistantConversationRow.conversation_id == AssistantMessageRow.conversation_id,
            )
            .where(
                AssistantConversationRow.project_id == project_id,
                AssistantMessageRow.message_id == message_id,
            )
        )
        if row is None:
            raise not_found()
        return row

    def list_messages(
        self, *, conversation_id: str, page: int, page_size: int
    ) -> Page[AssistantMessageRow]:
        total = int(
            self.session.scalar(
                select(func.count())
                .select_from(AssistantMessageRow)
                .where(AssistantMessageRow.conversation_id == conversation_id)
            )
            or 0
        )
        rows = list(
            self.session.scalars(
                select(AssistantMessageRow)
                .where(AssistantMessageRow.conversation_id == conversation_id)
                .order_by(AssistantMessageRow.created_at, AssistantMessageRow.message_id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return Page(items=rows, page=page, page_size=page_size, total=total)

    def conversation_messages(
        self, conversation_id: str, *, limit: int
    ) -> list[AssistantMessageRow]:
        rows = list(
            self.session.scalars(
                select(AssistantMessageRow)
                .where(AssistantMessageRow.conversation_id == conversation_id)
                .order_by(
                    AssistantMessageRow.created_at.desc(),
                    AssistantMessageRow.message_id.desc(),
                )
                .limit(limit)
            )
        )
        rows.reverse()
        return rows

    def update_message(
        self,
        row: AssistantMessageRow,
        *,
        status: str | None = None,
        content: str | None = None,
        content_json: dict[str, Any] | None = None,
        job_id: str | None = None,
    ) -> AssistantMessageRow:
        if status is not None:
            row.status = status
            row.completed_at = utc_now() if status in {"completed", "failed", "cancelled"} else None
        if content is not None:
            row.content = content
        if content_json is not None:
            row.content_json = content_json
        if job_id is not None:
            row.job_id = job_id
        self.session.flush()
        return row

    def create_llm_run(
        self,
        *,
        message_id: str,
        project_id: str,
        job_id: str,
        provider: str,
        model: str,
        prompt_name: str,
        prompt_version: str,
        context_manifest: dict[str, Any],
    ) -> LLMRunRow:
        row = LLMRunRow(
            llm_run_id=new_id("llmr_"),
            message_id=message_id,
            project_id=project_id,
            job_id=job_id,
            provider=provider,
            model=model,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            status="running",
            model_call_count=0,
            tool_call_count=0,
            input_tokens=0,
            output_tokens=0,
            latency_ms=0,
            context_manifest_json=context_manifest,
            error_json=None,
            created_at=utc_now(),
            completed_at=None,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def get_llm_run(self, llm_run_id: str) -> LLMRunRow:
        row = self.session.get(LLMRunRow, llm_run_id)
        if row is None:
            raise not_found()
        return row

    def latest_llm_run_for_message(self, message_id: str) -> LLMRunRow | None:
        return self.session.scalar(
            select(LLMRunRow)
            .where(LLMRunRow.message_id == message_id)
            .order_by(LLMRunRow.created_at.desc(), LLMRunRow.llm_run_id.desc())
            .limit(1)
        )

    def finish_llm_run(
        self,
        row: LLMRunRow,
        *,
        status: str,
        model_call_count: int,
        tool_call_count: int,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        error: dict[str, Any] | None = None,
    ) -> LLMRunRow:
        row.status = status
        row.model_call_count = model_call_count
        row.tool_call_count = tool_call_count
        row.input_tokens = input_tokens
        row.output_tokens = output_tokens
        row.latency_ms = latency_ms
        row.error_json = error
        if status in {"succeeded", "failed", "cancelled"}:
            row.completed_at = utc_now()
        self.session.flush()
        return row

    def update_llm_run_manifest(
        self, row: LLMRunRow, values: dict[str, Any]
    ) -> LLMRunRow:
        row.context_manifest_json = {**row.context_manifest_json, **values}
        self.session.flush()
        return row

    def daily_tokens_for_subject(self, *, subject_id: str, since: datetime) -> int:
        return int(
            self.session.scalar(
                select(func.coalesce(func.sum(LLMRunRow.input_tokens + LLMRunRow.output_tokens), 0))
                .join(
                    AssistantMessageRow,
                    AssistantMessageRow.message_id == LLMRunRow.message_id,
                )
                .where(
                    AssistantMessageRow.created_by == subject_id,
                    LLMRunRow.created_at >= since,
                )
            )
            or 0
        )

    def active_turn_count(self, *, project_id: str) -> int:
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(JobRow)
                .where(
                    JobRow.project_id == project_id,
                    JobRow.kind == "assistant_turn",
                    JobRow.status.in_({"queued", "running", "cancelling"}),
                )
            )
            or 0
        )

    def require_provider_available(
        self, *, provider: str, cooldown_seconds: int
    ) -> None:
        row = self.session.get(LLMProviderStateRow, provider)
        if row is None or row.status == "closed":
            return
        now = utc_now()
        if row.opened_at and now >= row.opened_at + timedelta(seconds=cooldown_seconds):
            row.status = "half_open"
            row.updated_at = now
            self.session.flush()
            return
        raise DomainError(
            "LLM_PROVIDER_CIRCUIT_OPEN",
            "大语言模型服务暂时熔断，请稍后重试",
            503,
            retryable=True,
            details={
                "provider": provider,
                "retry_after_seconds": cooldown_seconds,
            },
        )

    def record_provider_success(self, *, provider: str) -> None:
        row = self.session.get(LLMProviderStateRow, provider)
        now = utc_now()
        if row is None:
            row = LLMProviderStateRow(
                provider=provider,
                status="closed",
                consecutive_failures=0,
                opened_at=None,
                updated_at=now,
            )
            self.session.add(row)
        else:
            row.status = "closed"
            row.consecutive_failures = 0
            row.opened_at = None
            row.updated_at = now
        self.session.flush()

    def record_provider_failure(self, *, provider: str, threshold: int) -> None:
        row = self.session.get(LLMProviderStateRow, provider)
        now = utc_now()
        if row is None:
            row = LLMProviderStateRow(
                provider=provider,
                status="closed",
                consecutive_failures=0,
                opened_at=None,
                updated_at=now,
            )
            self.session.add(row)
        row.consecutive_failures += 1
        row.updated_at = now
        if row.consecutive_failures >= threshold:
            row.status = "open"
            row.opened_at = now
        self.session.flush()

    def project_metrics(self, *, project_id: str, since: datetime) -> dict[str, Any]:
        runs = list(
            self.session.scalars(
                select(LLMRunRow).where(
                    LLMRunRow.project_id == project_id,
                    LLMRunRow.created_at >= since,
                )
            )
        )
        run_ids = [row.llm_run_id for row in runs]
        calls = (
            list(
                self.session.scalars(
                    select(LLMToolCallRow).where(LLMToolCallRow.llm_run_id.in_(run_ids))
                )
            )
            if run_ids
            else []
        )
        latencies = sorted(row.latency_ms for row in runs)
        p95_index = max(0, min(len(latencies) - 1, int(len(latencies) * 0.95) - 1))
        return {
            "turn_count": len(runs),
            "succeeded_count": sum(row.status == "succeeded" for row in runs),
            "failed_count": sum(row.status == "failed" for row in runs),
            "input_tokens": sum(row.input_tokens for row in runs),
            "output_tokens": sum(row.output_tokens for row in runs),
            "average_latency_ms": int(sum(latencies) / len(latencies)) if latencies else 0,
            "p95_latency_ms": latencies[p95_index] if latencies else 0,
            "tool_call_count": len(calls),
            "tool_succeeded_count": sum(row.status == "succeeded" for row in calls),
            "tool_failed_count": sum(row.status == "failed" for row in calls),
            "tool_rejected_count": sum(row.status == "rejected" for row in calls),
        }

    def apply_retention(
        self, *, scrub_before: datetime, archive_before: datetime
    ) -> dict[str, int]:
        conversations = list(
            self.session.scalars(
                select(AssistantConversationRow).where(
                    AssistantConversationRow.status == "active",
                    AssistantConversationRow.updated_at < archive_before,
                )
            )
        )
        now = utc_now()
        for conversation in conversations:
            conversation.status = "archived"
            conversation.archived_at = now

        runs = list(
            self.session.scalars(
                select(LLMRunRow).where(
                    LLMRunRow.created_at < scrub_before,
                    LLMRunRow.context_manifest_json != {},
                )
            )
        )
        run_ids = [run.llm_run_id for run in runs]
        for run in runs:
            manifest = run.context_manifest_json
            run.context_manifest_json = {
                "retained": True,
                "project_id": run.project_id,
                "dataset_version_id": manifest.get("dataset_version_id"),
                "resource_ids": manifest.get("resource_ids", []),
            }
        calls = (
            list(
                self.session.scalars(
                    select(LLMToolCallRow).where(LLMToolCallRow.llm_run_id.in_(run_ids))
                )
            )
            if run_ids
            else []
        )
        for call in calls:
            call.arguments_json = {"retained": True}
            call.result_json = {"retained": True} if call.result_json is not None else None
            call.error_json = None
        self.session.flush()
        return {
            "archived_conversations": len(conversations),
            "scrubbed_runs": len(runs),
            "scrubbed_tool_calls": len(calls),
        }

    def create_tool_call(
        self,
        *,
        llm_run_id: str,
        tool_name: str,
        tool_version: str,
        arguments: dict[str, Any],
        requires_confirmation: bool,
        status: str = "proposed",
        provider_tool_call_id: str | None = None,
    ) -> LLMToolCallRow:
        row = LLMToolCallRow(
            tool_call_id=new_id("tool_"),
            llm_run_id=llm_run_id,
            provider_tool_call_id=provider_tool_call_id,
            tool_name=tool_name,
            tool_version=tool_version,
            status=status,
            requires_confirmation=requires_confirmation,
            arguments_json=arguments,
            result_resource_type=None,
            result_resource_id=None,
            result_json=None,
            approved_by=None,
            approved_at=None,
            error_json=None,
            created_at=utc_now(),
            completed_at=None,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def list_tool_calls(self, llm_run_id: str) -> list[LLMToolCallRow]:
        return list(
            self.session.scalars(
                select(LLMToolCallRow)
                .where(LLMToolCallRow.llm_run_id == llm_run_id)
                .order_by(LLMToolCallRow.created_at, LLMToolCallRow.tool_call_id)
            )
        )

    def get_tool_call(self, tool_call_id: str) -> LLMToolCallRow:
        row = self.session.get(LLMToolCallRow, tool_call_id)
        if row is None:
            raise not_found()
        return row

    def get_tool_call_for_project(self, *, project_id: str, tool_call_id: str) -> LLMToolCallRow:
        row = self.session.scalar(
            select(LLMToolCallRow)
            .join(LLMRunRow, LLMRunRow.llm_run_id == LLMToolCallRow.llm_run_id)
            .where(
                LLMRunRow.project_id == project_id,
                LLMToolCallRow.tool_call_id == tool_call_id,
            )
        )
        if row is None:
            raise not_found()
        return row

    def update_tool_call_arguments(
        self, row: LLMToolCallRow, arguments: dict[str, Any]
    ) -> LLMToolCallRow:
        if row.status != "proposed":
            raise state_conflict(
                "只有待确认的工具调用可以编辑",
                tool_call_id=row.tool_call_id,
                status=row.status,
            )
        row.arguments_json = arguments
        self.session.flush()
        return row

    def finish_tool_call(
        self,
        row: LLMToolCallRow,
        *,
        status: str,
        result: dict[str, Any] | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        error: dict[str, Any] | None = None,
    ) -> LLMToolCallRow:
        row.status = status
        row.result_json = result
        row.result_resource_type = resource_type
        row.result_resource_id = resource_id
        row.error_json = error
        row.completed_at = utc_now() if status in {"succeeded", "failed", "rejected"} else None
        self.session.flush()
        return row

    def decide_tool_calls(
        self,
        rows: list[LLMToolCallRow],
        *,
        decision: str,
        subject_id: str,
    ) -> None:
        now = utc_now()
        target_status = "approved" if decision == "approve" else "rejected"
        for row in rows:
            if row.status != "proposed":
                raise state_conflict(
                    "工具调用已经处理",
                    tool_call_id=row.tool_call_id,
                    status=row.status,
                )
            row.status = target_status
            row.approved_by = subject_id
            row.approved_at = now
            row.completed_at = now if target_status == "rejected" else None
        self.session.flush()

    def get_tool_calls_for_message(
        self, *, message_id: str, tool_call_ids: set[str] | None = None
    ) -> list[LLMToolCallRow]:
        filters = [LLMRunRow.message_id == message_id]
        if tool_call_ids is not None:
            filters.append(LLMToolCallRow.tool_call_id.in_(tool_call_ids))
        return list(
            self.session.scalars(
                select(LLMToolCallRow)
                .join(LLMRunRow, LLMRunRow.llm_run_id == LLMToolCallRow.llm_run_id)
                .where(*filters)
                .order_by(LLMToolCallRow.created_at, LLMToolCallRow.tool_call_id)
            )
        )

    def create_feedback(
        self,
        *,
        project_id: str,
        message_id: str,
        rating: str,
        reason: str | None,
        comment: str | None,
        subject_id: str,
    ) -> AssistantFeedbackRow:
        existing = self.session.scalar(
            select(AssistantFeedbackRow).where(
                AssistantFeedbackRow.message_id == message_id,
                AssistantFeedbackRow.created_by == subject_id,
            )
        )
        if existing is not None:
            raise state_conflict("已经提交过该回答的反馈")
        row = AssistantFeedbackRow(
            feedback_id=new_id("fb_"),
            message_id=message_id,
            project_id=project_id,
            rating=rating,
            reason=reason,
            comment=comment,
            created_by=subject_id,
            created_at=utc_now(),
        )
        self.session.add(row)
        self.session.flush()
        return row
