from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    AssistantConfirmationRequest,
    AssistantConversation,
    AssistantConversationCreate,
    AssistantConversationPage,
    AssistantConversationUpdate,
    AssistantFeedback,
    AssistantFeedbackRequest,
    AssistantMessage,
    AssistantMessageCreate,
    AssistantMessagePage,
    AssistantMetrics,
    AssistantToolCall,
    AssistantToolCallUpdate,
    AssistantTurnAccepted,
)
from app.core.config import Settings
from app.domain.errors import DomainError, not_found, permission_denied, state_conflict
from app.llm.actions import AssistantActionRegistry
from app.persistence.orm.assistant_models import (
    AssistantConversationRow,
    AssistantFeedbackRow,
    AssistantMessageRow,
    LLMToolCallRow,
)
from app.persistence.orm.models import DatasetVersionRow, ProjectRow
from app.persistence.repositories.assistant import AssistantRepository
from app.persistence.repositories.audit import AuditRepository
from app.persistence.repositories.jobs import JobRepository
from app.persistence.repositories.projects import ProjectRepository
from app.services.jobs import job_to_schema


def conversation_to_schema(row: AssistantConversationRow) -> AssistantConversation:
    return AssistantConversation(
        conversation_id=row.conversation_id,
        project_id=row.project_id,
        title=row.title,
        status=row.status,
        dataset_version_id=row.dataset_version_id,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        archived_at=row.archived_at,
    )


def feedback_to_schema(row: AssistantFeedbackRow) -> AssistantFeedback:
    return AssistantFeedback(
        feedback_id=row.feedback_id,
        message_id=row.message_id,
        rating=row.rating,
        reason=row.reason,
        comment=row.comment,
        created_at=row.created_at,
    )


class AssistantService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.assistant = AssistantRepository(session)
        self.projects = ProjectRepository(session)
        self.jobs = JobRepository(session)
        self.audit = AuditRepository(session)

    def list_conversations(
        self, project_id: str, *, subject_id: str, page: int, page_size: int
    ) -> AssistantConversationPage:
        self._require_member(project_id, subject_id)
        result = self.assistant.list_conversations(
            project_id=project_id, page=page, page_size=page_size
        )
        return AssistantConversationPage(
            items=[conversation_to_schema(row) for row in result.items],
            page=page,
            page_size=page_size,
            total=result.total,
            has_more=result.has_more,
        )

    def create_conversation(
        self,
        project_id: str,
        payload: AssistantConversationCreate,
        *,
        subject_id: str,
        request_id: str,
    ) -> AssistantConversation:
        self._require_enabled(subject_id)
        project, _ = self._require_member(project_id, subject_id)
        version_id = payload.dataset_version_id or project.current_dataset_version_id
        self._validate_version(project_id, version_id)
        row = self.assistant.create_conversation(
            project_id=project_id,
            title=(payload.title or "新分析会话").strip(),
            dataset_version_id=version_id,
            subject_id=subject_id,
        )
        self.audit.append(
            action="assistant.conversation_created",
            result="success",
            summary={"dataset_version_id": version_id},
            project_id=project_id,
            subject_id=subject_id,
            object_type="assistant_conversation",
            object_id=row.conversation_id,
            request_id=request_id,
        )
        return conversation_to_schema(row)

    def get_conversation(
        self, project_id: str, conversation_id: str, *, subject_id: str
    ) -> AssistantConversation:
        self._require_member(project_id, subject_id)
        return conversation_to_schema(
            self.assistant.get_conversation(project_id=project_id, conversation_id=conversation_id)
        )

    def update_conversation(
        self,
        project_id: str,
        conversation_id: str,
        payload: AssistantConversationUpdate,
        *,
        subject_id: str,
        request_id: str,
    ) -> AssistantConversation:
        self._require_member(project_id, subject_id)
        row = self.assistant.get_conversation(
            project_id=project_id, conversation_id=conversation_id
        )
        values = payload.model_dump(exclude_unset=True)
        if "dataset_version_id" in values:
            self._validate_version(project_id, payload.dataset_version_id)
        updated = self.assistant.update_conversation(
            row,
            title=payload.title,
            status=payload.status,
            dataset_version_id=payload.dataset_version_id,
            dataset_version_changed="dataset_version_id" in values,
        )
        self.audit.append(
            action="assistant.conversation_updated",
            result="success",
            summary={"changed_fields": sorted(values)},
            project_id=project_id,
            subject_id=subject_id,
            object_type="assistant_conversation",
            object_id=conversation_id,
            request_id=request_id,
        )
        return conversation_to_schema(updated)

    def list_messages(
        self,
        project_id: str,
        conversation_id: str,
        *,
        subject_id: str,
        page: int,
        page_size: int,
    ) -> AssistantMessagePage:
        self._require_member(project_id, subject_id)
        self.assistant.get_conversation(project_id=project_id, conversation_id=conversation_id)
        result = self.assistant.list_messages(
            conversation_id=conversation_id, page=page, page_size=page_size
        )
        return AssistantMessagePage(
            items=[self.message_to_schema(row) for row in result.items],
            page=page,
            page_size=page_size,
            total=result.total,
            has_more=result.has_more,
        )

    def create_turn(
        self,
        project_id: str,
        conversation_id: str,
        payload: AssistantMessageCreate,
        *,
        subject_id: str,
        request_id: str,
    ) -> AssistantTurnAccepted:
        self._require_enabled(subject_id)
        self._require_member(project_id, subject_id)
        self._require_turn_capacity(project_id, subject_id)
        conversation = self.assistant.get_conversation(
            project_id=project_id, conversation_id=conversation_id
        )
        if conversation.status != "active":
            raise state_conflict("归档会话不能继续提问")
        user_message = self.assistant.create_message(
            conversation_id=conversation_id,
            role="user",
            status="completed",
            content=payload.content,
            subject_id=subject_id,
        )
        assistant_message = self.assistant.create_message(
            conversation_id=conversation_id,
            role="assistant",
            status="queued",
            subject_id=subject_id,
            parent_message_id=user_message.message_id,
        )
        job = self.jobs.create(
            project_id=project_id,
            kind="assistant_turn",
            request={
                "mode": "initial",
                "conversation_id": conversation_id,
                "user_message_id": user_message.message_id,
                "assistant_message_id": assistant_message.message_id,
            },
            subject_id=subject_id,
        )
        self.assistant.update_message(assistant_message, job_id=job.job_id)
        if conversation.title == "新分析会话":
            self.assistant.update_conversation(
                conversation, title=self._question_title(payload.content)
            )
        self.audit.append(
            action="assistant.turn_created",
            result="success",
            summary={"job_id": job.job_id},
            project_id=project_id,
            subject_id=subject_id,
            object_type="assistant_message",
            object_id=assistant_message.message_id,
            request_id=request_id,
        )
        return AssistantTurnAccepted(
            user_message=self.message_to_schema(user_message),
            assistant_message=self.message_to_schema(assistant_message),
            job=job_to_schema(job),
        )

    def confirm_plan(
        self,
        project_id: str,
        message_id: str,
        payload: AssistantConfirmationRequest,
        *,
        subject_id: str,
        request_id: str,
    ) -> AssistantTurnAccepted:
        self._require_enabled(subject_id)
        self._require_editor(project_id, subject_id)
        self._require_turn_capacity(project_id, subject_id)
        message = self.assistant.get_message(project_id=project_id, message_id=message_id)
        if message.status != "awaiting_confirmation":
            raise state_conflict("当前消息没有等待确认的计划", status=message.status)
        conversation = self.assistant.get_conversation(
            project_id=project_id,
            conversation_id=message.conversation_id,
        )
        latest_run = self.assistant.latest_llm_run_for_message(message_id)
        planned_version_id = (
            latest_run.context_manifest_json.get("dataset_version_id") if latest_run else None
        )
        if planned_version_id != conversation.dataset_version_id:
            raise state_conflict(
                "数据版本已变化，请基于当前版本重新生成计划",
                planned_dataset_version_id=planned_version_id,
                current_dataset_version_id=conversation.dataset_version_id,
            )
        requested = set(payload.tool_call_ids) if payload.tool_call_ids else None
        rows = self.assistant.get_tool_calls_for_message(
            message_id=message_id, tool_call_ids=requested
        )
        if not rows or (requested is not None and len(rows) != len(requested)):
            raise not_found("待确认的工具调用不存在")
        self.assistant.decide_tool_calls(rows, decision=payload.decision, subject_id=subject_id)
        if latest_run is not None and latest_run.status == "awaiting_confirmation":
            self.assistant.finish_llm_run(
                latest_run,
                status="succeeded",
                model_call_count=latest_run.model_call_count,
                tool_call_count=latest_run.tool_call_count,
                input_tokens=latest_run.input_tokens,
                output_tokens=latest_run.output_tokens,
                latency_ms=latest_run.latency_ms,
            )
        if payload.decision == "reject":
            summary = "计划已按你的选择取消，未执行任何数据或分析变更。"
            answer = {
                "summary": summary,
                "findings": [],
                "next_actions": [],
                "limitations": [payload.reason] if payload.reason else [],
            }
            self.assistant.update_message(
                message,
                status="completed",
                content=summary,
                content_json={"plan": (message.content_json or {}).get("plan"), "answer": answer},
            )
            result = AssistantTurnAccepted(
                user_message=None,
                assistant_message=self.message_to_schema(message),
                job=None,
            )
        else:
            self.assistant.update_message(
                message,
                status="completed",
                content="计划已确认，后续操作将由受控任务继续执行。",
            )
            continuation = self.assistant.create_message(
                conversation_id=message.conversation_id,
                role="assistant",
                status="queued",
                subject_id=subject_id,
                parent_message_id=message.message_id,
            )
            job = self.jobs.create(
                project_id=project_id,
                kind="assistant_turn",
                request={
                    "mode": "confirmed",
                    "source_message_id": message.message_id,
                    "assistant_message_id": continuation.message_id,
                    "tool_call_ids": [row.tool_call_id for row in rows],
                },
                subject_id=subject_id,
            )
            self.assistant.update_message(continuation, job_id=job.job_id)
            result = AssistantTurnAccepted(
                user_message=None,
                assistant_message=self.message_to_schema(continuation),
                job=job_to_schema(job),
            )
        self.audit.append(
            action="assistant.plan_decided",
            result="success",
            summary={"decision": payload.decision, "tool_call_count": len(rows)},
            project_id=project_id,
            subject_id=subject_id,
            object_type="assistant_message",
            object_id=message_id,
            request_id=request_id,
        )
        return result

    def retry_message(
        self,
        project_id: str,
        message_id: str,
        *,
        subject_id: str,
        request_id: str,
    ) -> AssistantTurnAccepted:
        self._require_enabled(subject_id)
        self._require_member(project_id, subject_id)
        self._require_turn_capacity(project_id, subject_id)
        source = self.assistant.get_message(project_id=project_id, message_id=message_id)
        if source.role != "assistant" or source.status not in {"failed", "cancelled"}:
            raise state_conflict("只能重试失败或已取消的 Assistant 消息")
        if not source.parent_message_id:
            raise state_conflict("找不到原始问题")
        retry = self.assistant.create_message(
            conversation_id=source.conversation_id,
            role="assistant",
            status="queued",
            subject_id=subject_id,
            parent_message_id=source.parent_message_id,
        )
        job = self.jobs.create(
            project_id=project_id,
            kind="assistant_turn",
            request={
                "mode": "retry",
                "source_message_id": source.message_id,
                "user_message_id": source.parent_message_id,
                "assistant_message_id": retry.message_id,
            },
            subject_id=subject_id,
        )
        self.assistant.update_message(retry, job_id=job.job_id)
        self.audit.append(
            action="assistant.turn_retried",
            result="success",
            summary={"source_message_id": message_id, "job_id": job.job_id},
            project_id=project_id,
            subject_id=subject_id,
            object_type="assistant_message",
            object_id=retry.message_id,
            request_id=request_id,
        )
        return AssistantTurnAccepted(
            user_message=None,
            assistant_message=self.message_to_schema(retry),
            job=job_to_schema(job),
        )

    def cancel_message(
        self,
        project_id: str,
        message_id: str,
        *,
        subject_id: str,
        request_id: str,
    ) -> AssistantMessage:
        self._require_member(project_id, subject_id)
        message = self.assistant.get_message(project_id=project_id, message_id=message_id)
        if message.status not in {"queued", "processing"} or not message.job_id:
            raise state_conflict("当前消息不可取消", status=message.status)
        job = self.jobs.get_for_project(project_id=project_id, job_id=message.job_id)
        if job.status == "queued":
            self.jobs.transition(job, status="cancelled")
            self.assistant.update_message(message, status="cancelled")
        elif job.status == "running":
            self.jobs.request_cancel(job)
        else:
            raise state_conflict("当前任务不可取消", status=job.status)
        self.audit.append(
            action="assistant.turn_cancel_requested",
            result="success",
            summary={"job_id": job.job_id},
            project_id=project_id,
            subject_id=subject_id,
            object_type="assistant_message",
            object_id=message_id,
            request_id=request_id,
        )
        return self.message_to_schema(message)

    def create_feedback(
        self,
        project_id: str,
        message_id: str,
        payload: AssistantFeedbackRequest,
        *,
        subject_id: str,
        request_id: str,
    ) -> AssistantFeedback:
        self._require_member(project_id, subject_id)
        message = self.assistant.get_message(project_id=project_id, message_id=message_id)
        if message.role != "assistant" or message.status != "completed":
            raise state_conflict("只能评价已完成的 Assistant 回答")
        row = self.assistant.create_feedback(
            project_id=project_id,
            message_id=message_id,
            rating=payload.rating,
            reason=payload.reason,
            comment=payload.comment,
            subject_id=subject_id,
        )
        self.audit.append(
            action="assistant.feedback_created",
            result="success",
            summary={"rating": payload.rating, "reason": payload.reason},
            project_id=project_id,
            subject_id=subject_id,
            object_type="assistant_message",
            object_id=message_id,
            request_id=request_id,
        )
        return feedback_to_schema(row)

    def update_tool_call(
        self,
        project_id: str,
        tool_call_id: str,
        payload: AssistantToolCallUpdate,
        *,
        subject_id: str,
        request_id: str,
    ) -> AssistantToolCall:
        self._require_enabled(subject_id)
        self._require_editor(project_id, subject_id)
        call = self.assistant.get_tool_call_for_project(
            project_id=project_id, tool_call_id=tool_call_id
        )
        run = self.assistant.get_llm_run(call.llm_run_id)
        message = self.assistant.get_message(project_id=project_id, message_id=run.message_id)
        conversation = self.assistant.get_conversation(
            project_id=project_id,
            conversation_id=message.conversation_id,
        )
        canonical = AssistantActionRegistry(self.session).validate_arguments(
            call.tool_name,
            payload.arguments,
            project_id=project_id,
            dataset_version_id=conversation.dataset_version_id,
        )
        self.assistant.update_tool_call_arguments(call, canonical)
        self.audit.append(
            action="assistant.tool_call_updated",
            result="success",
            summary={"tool_name": call.tool_name},
            project_id=project_id,
            subject_id=subject_id,
            object_type="llm_tool_call",
            object_id=tool_call_id,
            request_id=request_id,
        )
        return self.tool_call_to_schema(call)

    def message_to_schema(self, row: AssistantMessageRow) -> AssistantMessage:
        content_json = row.content_json or {}
        run = self.assistant.latest_llm_run_for_message(row.message_id)
        calls = self.assistant.list_tool_calls(run.llm_run_id) if run else []
        return AssistantMessage(
            message_id=row.message_id,
            conversation_id=row.conversation_id,
            role=row.role,
            status=row.status,
            content=row.content,
            plan=content_json.get("plan"),
            answer=content_json.get("answer"),
            tool_calls=[self.tool_call_to_schema(call) for call in calls],
            parent_message_id=row.parent_message_id,
            job_id=row.job_id,
            created_at=row.created_at,
            completed_at=row.completed_at,
        )

    @staticmethod
    def tool_call_to_schema(call: LLMToolCallRow) -> AssistantToolCall:
        return AssistantToolCall(
            tool_call_id=call.tool_call_id,
            tool_name=call.tool_name,
            tool_version=call.tool_version,
            status=call.status,
            requires_confirmation=call.requires_confirmation,
            arguments=call.arguments_json,
            result=call.result_json,
            result_resource_type=call.result_resource_type,
            result_resource_id=call.result_resource_id,
        )

    def metrics(
        self, project_id: str, *, subject_id: str, window_days: int
    ) -> AssistantMetrics:
        self._require_member(project_id, subject_id)
        since = datetime.now(UTC) - timedelta(days=window_days)
        return AssistantMetrics(
            window_days=window_days,
            **self.assistant.project_metrics(project_id=project_id, since=since),
        )

    def _require_enabled(self, subject_id: str) -> None:
        if not self.settings.llm_enabled:
            raise DomainError("LLM_DISABLED", "大语言模型功能尚未启用", 409)
        if (
            self.settings.llm_canary_subjects
            and subject_id not in self.settings.llm_canary_subjects
        ):
            raise permission_denied("当前账号尚未进入 Assistant 灰度范围")

    def _require_turn_capacity(self, project_id: str, subject_id: str) -> None:
        active = self.assistant.active_turn_count(project_id=project_id)
        if active >= self.settings.llm_max_concurrent_turns_per_project:
            raise DomainError(
                "LLM_PROJECT_CONCURRENCY_LIMIT",
                "当前项目已达 Assistant 并发上限",
                429,
                retryable=True,
                details={"active_turns": active},
            )
        now = datetime.now(UTC)
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        consumed = self.assistant.daily_tokens_for_subject(
            subject_id=subject_id, since=since
        )
        if consumed >= self.settings.llm_daily_token_budget_per_user:
            raise DomainError(
                "LLM_DAILY_TOKEN_BUDGET_EXCEEDED",
                "今日 Assistant Token 配额已用完",
                429,
                details={"consumed_tokens": consumed},
            )

    def _require_member(self, project_id: str, subject_id: str) -> tuple[ProjectRow, str]:
        result = self.projects.get_for_subject(project_id, subject_id)
        if result is None:
            raise not_found()
        return result

    def _require_editor(self, project_id: str, subject_id: str) -> None:
        _, role = self._require_member(project_id, subject_id)
        if role not in {"owner", "editor"}:
            raise permission_denied()

    def _validate_version(self, project_id: str, version_id: str | None) -> None:
        if version_id is None:
            return
        exists = self.session.scalar(
            select(DatasetVersionRow.version_id).where(
                DatasetVersionRow.project_id == project_id,
                DatasetVersionRow.version_id == version_id,
            )
        )
        if exists is None:
            raise not_found("数据版本不存在")

    @staticmethod
    def _question_title(content: str) -> str:
        compact = " ".join(content.split())
        return compact[:157] + "..." if len(compact) > 160 else compact
