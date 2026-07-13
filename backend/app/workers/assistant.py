from __future__ import annotations

import json
import logging
from typing import Any

from app.analysis.tool_registry import default_tool_registry
from app.core.config import Settings, get_settings
from app.domain.errors import DomainError
from app.llm.action_schemas import AnalysisSpecDraft, CleaningPlanDraft, FeatureSuggestionDraft
from app.llm.actions import AssistantActionRegistry
from app.llm.citations import CitationValidationError, validate_answer_sources
from app.llm.factory import get_llm_provider
from app.llm.orchestrator import AgentState, AgentTrace, ContextCompactor
from app.llm.policy import AssistantBudget
from app.llm.prompts import get_prompt
from app.llm.provider import LLMMessage, LLMProvider, LLMProviderError, LLMResponse
from app.llm.schemas import AssistantAnswer, AssistantIntent, AssistantPlan
from app.llm.tools import AssistantToolContext, AssistantToolRegistry, AssistantToolResult
from app.persistence.orm.assistant_models import AssistantMessageRow
from app.persistence.repositories.jobs import JobRepository
from app.persistence.session import Database, get_database
from app.persistence.unit_of_work import UnitOfWork
from app.storage.files import get_file_storage
from app.workers.analysis import AnalysisRunWorker
from app.workers.cleaning import CleaningExecuteWorker, CleaningPreviewWorker

PLANNED_WRITE_TOOLS = {
    "analysis.draft_spec",
    "analysis.run",
    "cleaning.draft_plan",
    "cleaning.execute",
    "feature_engineering.suggest",
    "report.export",
}

logger = logging.getLogger(__name__)


class AssistantTurnWorker:
    def __init__(
        self,
        database: Database,
        *,
        worker_id: str,
        provider: LLMProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.database = database
        self.worker_id = worker_id
        self.settings = settings or get_settings()
        self.provider = provider if provider is not None else get_llm_provider()
        self._active_budget: AssistantBudget | None = None
        self._active_run_id: str | None = None

    def run(self, job_id: str) -> bool:
        self._active_budget = None
        self._active_run_id = None
        if not self._claim(job_id):
            return False
        try:
            self._require_provider_available()
            self._process(job_id)
            self._record_provider_success()
        except LLMProviderError as exc:
            self._record_provider_failure()
            self._fail(
                job_id,
                DomainError(exc.code, "大语言模型服务暂时无法完成本轮请求", 502, exc.retryable),
            )
        except CitationValidationError:
            self._fail(
                job_id,
                DomainError(
                    "LLM_UNSUPPORTED_ANSWER",
                    "模型回答未通过证据校验，请重试或缩小问题范围",
                    409,
                ),
            )
        except DomainError as exc:
            if exc.code != "JOB_CANCELLED":
                self._fail(job_id, exc)
        except Exception:
            self._fail(
                job_id,
                DomainError(
                    "EXECUTOR_UNAVAILABLE",
                    "Assistant 执行失败",
                    500,
                    retryable=True,
                ),
            )
        return True

    def _claim(self, job_id: str) -> bool:
        session = self.database.session()
        try:
            with UnitOfWork(session):
                return JobRepository(session).claim(
                    job_id=job_id,
                    worker_id=self.worker_id,
                    lease_seconds=max(self.settings.llm_timeout_seconds * 3, 300),
                )
        finally:
            session.close()

    def _process(self, job_id: str) -> None:
        if self.provider is None or not self.settings.llm_model:
            raise DomainError("LLM_DISABLED", "大语言模型功能尚未启用", 409)
        check_session = self.database.session()
        try:
            checked_job = JobRepository(check_session).get(job_id)
            if checked_job.kind != "assistant_turn":
                raise DomainError("STATE_CONFLICT", "Job 类型不是 Assistant Turn", 409)
            mode = str(checked_job.request_json.get("mode", "initial"))
        finally:
            check_session.close()
        if mode == "confirmed":
            self._process_confirmed(job_id)
            return
        session = self.database.session()
        try:
            with UnitOfWork(session) as uow:
                job = uow.jobs.get(job_id)
                message_id = str(job.request_json["assistant_message_id"])
                user_message_id = str(job.request_json["user_message_id"])
                assistant = uow.assistant.get_message(
                    project_id=job.project_id, message_id=message_id
                )
                user = uow.assistant.get_message(
                    project_id=job.project_id, message_id=user_message_id
                )
                conversation = uow.assistant.get_conversation(
                    project_id=job.project_id,
                    conversation_id=assistant.conversation_id,
                )
                uow.assistant.update_message(assistant, status="processing")
                history = uow.assistant.conversation_messages(
                    conversation.conversation_id, limit=100
                )
                compacted = ContextCompactor().compact(
                    history, existing_summary=conversation.summary
                )
                if compacted.compacted_count:
                    uow.assistant.update_conversation(
                        conversation, summary=compacted.summary
                    )
                context_manifest = {
                    "project_id": job.project_id,
                    "conversation_id": conversation.conversation_id,
                    "dataset_version_id": conversation.dataset_version_id,
                    "history_message_ids": compacted.message_ids,
                    "compacted_message_count": compacted.compacted_count,
                    "orchestration": AgentTrace().manifest(),
                }
                llm_run = uow.assistant.create_llm_run(
                    message_id=message_id,
                    project_id=job.project_id,
                    job_id=job_id,
                    provider=self.settings.llm_provider,
                    model=self.settings.llm_model or "",
                    prompt_name="assistant.intent",
                    prompt_version="1.0.0",
                    context_manifest=context_manifest,
                )
                uow.jobs.heartbeat(
                    job=job,
                    worker_id=self.worker_id,
                    progress=10,
                    current_step="识别问题意图",
                    lease_seconds=max(self.settings.llm_timeout_seconds * 3, 300),
                )
                project_id = job.project_id
                dataset_version_id = conversation.dataset_version_id
                question = user.content or ""
                run_id = llm_run.llm_run_id
                history_payload = compacted.recent_messages
                if compacted.summary:
                    history_payload.insert(
                        0,
                        {"role": "system", "content": f"历史会话摘要:\n{compacted.summary}"},
                    )
        finally:
            session.close()

        trace = AgentTrace(max_steps=self.settings.llm_max_tool_calls_per_turn)
        budget = AssistantBudget(
            max_model_calls=self.settings.llm_max_calls_per_turn,
            max_tool_calls=self.settings.llm_max_tool_calls_per_turn,
            max_total_tokens=self.settings.llm_max_input_tokens
            + self.settings.llm_max_output_tokens,
        )
        self._active_budget = budget
        self._active_run_id = run_id
        budget.require_model_capacity()
        intent_response = self._generate_intent(question, history_payload)
        self._record_response(budget, intent_response)
        self._ensure_active(job_id, run_id, budget)
        intent = intent_response.content

        if intent.requires_new_computation or intent.intent in {
            "plan_analysis",
            "draft_cleaning",
            "export_report",
        }:
            budget.require_model_capacity()
            plan_response = self._generate_plan(
                question=question,
                intent=intent,
                dataset_version_id=dataset_version_id,
            )
            self._record_response(budget, plan_response)
            arguments = self._prepare_action_arguments(
                question=question,
                project_id=project_id,
                dataset_version_id=dataset_version_id,
                plan=plan_response.content,
                budget=budget,
            )
            trace.move(AgentState.EXECUTE, detail="awaiting_user_confirmation")
            self._persist_trace(run_id, trace)
            self._persist_plan(job_id, run_id, plan_response.content, arguments, budget)
            return

        trace.move(AgentState.EXECUTE, detail="read_only_tools")
        tool_results = self._execute_read_tools(
            project_id=project_id,
            dataset_version_id=dataset_version_id,
            intent=intent,
            budget=budget,
            llm_run_id=run_id,
        )
        self._ensure_active(job_id, run_id, budget)
        budget.require_model_capacity()
        answer_response = self._generate_answer(
            question=question,
            intent=intent,
            tool_results=tool_results,
        )
        self._record_response(budget, answer_response)
        sources = {
            source_id: source
            for result in tool_results
            for source_id, source in result.citation_sources.items()
        }
        trace.move(AgentState.CHECK, detail="citation_validation")
        try:
            validate_answer_sources(answer_response.content, sources)
            answer = answer_response.content
        except CitationValidationError:
            budget.require_model_capacity()
            correction_response = self._generate_answer_correction(
                question=question,
                draft=answer_response.content,
                tool_results=tool_results,
            )
            self._record_response(budget, correction_response)
            validate_answer_sources(correction_response.content, sources)
            answer = correction_response.content
        trace.move(AgentState.SUMMARIZE, detail="persist_grounded_answer")
        trace.move(AgentState.COMPLETE)
        self._persist_trace(run_id, trace)
        self._persist_answer(job_id, run_id, answer, budget)

    def _process_confirmed(self, job_id: str) -> None:
        session = self.database.session()
        try:
            with UnitOfWork(session) as uow:
                job = uow.jobs.get(job_id)
                message_id = str(job.request_json["assistant_message_id"])
                source_message_id = str(job.request_json["source_message_id"])
                requested_ids = {str(value) for value in job.request_json["tool_call_ids"]}
                message = uow.assistant.get_message(
                    project_id=job.project_id, message_id=message_id
                )
                source = uow.assistant.get_message(
                    project_id=job.project_id, message_id=source_message_id
                )
                conversation = uow.assistant.get_conversation(
                    project_id=job.project_id,
                    conversation_id=message.conversation_id,
                )
                calls = uow.assistant.get_tool_calls_for_message(
                    message_id=source_message_id,
                    tool_call_ids=requested_ids,
                )
                if len(calls) != len(requested_ids) or any(
                    call.status != "approved" for call in calls
                ):
                    raise DomainError(
                        "ASSISTANT_CONFIRMATION_STALE",
                        "确认内容已变化，请刷新后重新确认",
                        409,
                    )
                uow.assistant.update_message(message, status="processing")
                run = uow.assistant.create_llm_run(
                    message_id=message_id,
                    project_id=job.project_id,
                    job_id=job_id,
                    provider=self.settings.llm_provider,
                    model=self.settings.llm_model or "",
                    prompt_name="assistant.execute",
                    prompt_version="1.0.0",
                    context_manifest={
                        "source_message_id": source.message_id,
                        "dataset_version_id": conversation.dataset_version_id,
                        "tool_call_ids": [call.tool_call_id for call in calls],
                    },
                )
                project_id = job.project_id
                subject_id = job.created_by
                dataset_version_id = conversation.dataset_version_id
                run_id = run.llm_run_id
                ordered_ids = [call.tool_call_id for call in calls]
        finally:
            session.close()

        trace = AgentTrace(max_steps=self.settings.llm_max_tool_calls_per_turn)
        trace.move(AgentState.EXECUTE, detail="confirmed_actions")
        resources: dict[str, str] = {}
        results: list[dict[str, Any]] = []
        for position, tool_call_id in enumerate(ordered_ids, start=1):
            call_session = self.database.session()
            try:
                with UnitOfWork(call_session) as uow:
                    call = uow.assistant.get_tool_call(tool_call_id)
                    if call.status != "approved":
                        raise DomainError(
                            "ASSISTANT_CONFIRMATION_STALE",
                            "工具调用不再处于已确认状态",
                            409,
                        )
                    call.status = "running"
                    call_session.flush()
                    execution = AssistantActionRegistry(call_session).execute(
                        call.tool_name,
                        call.arguments_json,
                        project_id=project_id,
                        dataset_version_id=dataset_version_id,
                        subject_id=subject_id,
                        request_id=f"job:{job_id}:tool:{tool_call_id}",
                        resources=resources,
                    )
                    child_job_id = execution.child_job_id
                    child_job_kind = execution.child_job_kind
                    execution_result = execution.result
                    resource_type = execution.resource_type
                    resource_id = execution.resource_id
                if child_job_id and child_job_kind:
                    self._run_child_job(child_job_kind, child_job_id)
                    self._require_child_success(child_job_id)
                finish_session = self.database.session()
                try:
                    with UnitOfWork(finish_session) as uow:
                        call = uow.assistant.get_tool_call(tool_call_id)
                        uow.assistant.finish_tool_call(
                            call,
                            status="succeeded",
                            result=execution_result,
                            resource_type=resource_type,
                            resource_id=resource_id,
                        )
                        job = uow.jobs.get(job_id)
                        uow.jobs.heartbeat(
                            job=job,
                            worker_id=self.worker_id,
                            progress=min(15 + int(position / len(ordered_ids) * 75), 90),
                            current_step=f"执行受控工具 {position}/{len(ordered_ids)}",
                            lease_seconds=1800,
                        )
                finally:
                    finish_session.close()
                if resource_type and resource_id:
                    resources[resource_type] = resource_id
                results.append(
                    {
                        "tool_name": execution.tool_name,
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                        "result": execution_result,
                    }
                )
            except Exception as exc:
                self._mark_tool_failed(tool_call_id, exc)
                raise
            finally:
                call_session.close()

        summary = self._execution_summary(results)
        trace.move(AgentState.CHECK, detail="child_jobs_succeeded")
        answer = AssistantAnswer(
            summary=summary,
            findings=[],
            next_actions=[],
            limitations=["所有计算均由确定性 Worker 执行；请在对应资源页面查看完整结果。"],
        )
        budget = AssistantBudget(
            max_model_calls=self.settings.llm_max_calls_per_turn,
            max_tool_calls=self.settings.llm_max_tool_calls_per_turn,
            max_total_tokens=self.settings.llm_max_input_tokens
            + self.settings.llm_max_output_tokens,
        )
        budget.tool_calls = len(results)
        self._active_budget = budget
        self._active_run_id = run_id
        trace.move(AgentState.SUMMARIZE, detail="deterministic_execution_summary")
        trace.move(AgentState.COMPLETE)
        self._persist_trace(run_id, trace)
        self._persist_answer(job_id, run_id, answer, budget)

    def _generate_intent(
        self, question: str, history_payload: list[dict[str, str]]
    ) -> LLMResponse[AssistantIntent]:
        prompt = get_prompt("assistant.intent", "1.0.0")
        return self._provider().generate_structured(
            messages=[
                LLMMessage(role="system", content=prompt.system),
                LLMMessage(
                    role="user",
                    content=self._bounded_json(
                        {
                            "task": "Classify the current user request.",
                            "question": question,
                            "recent_conversation": history_payload,
                        }
                    ),
                ),
            ],
            response_schema=AssistantIntent,
            model=self.settings.llm_model or "",
            temperature=self.settings.llm_temperature,
            timeout_seconds=self.settings.llm_timeout_seconds,
            max_output_tokens=min(self.settings.llm_max_output_tokens, 1000),
        )

    def _generate_plan(
        self,
        *,
        question: str,
        intent: AssistantIntent,
        dataset_version_id: str | None,
    ) -> LLMResponse[AssistantPlan]:
        prompt = get_prompt("assistant.plan", "1.0.0")
        return self._provider().generate_structured(
            messages=[
                LLMMessage(role="system", content=prompt.system),
                LLMMessage(
                    role="user",
                    content=self._bounded_json(
                        {
                            "question": question,
                            "intent": intent.model_dump(mode="json"),
                            "dataset_version_id": dataset_version_id,
                            "allowed_tools": sorted(PLANNED_WRITE_TOOLS),
                            "rules": [
                                "Use only allowed_tools.",
                                "Every write or computation step requires confirmation.",
                                "Do not claim that any step has already run.",
                            ],
                        }
                    ),
                ),
            ],
            response_schema=AssistantPlan,
            model=self.settings.llm_model or "",
            temperature=self.settings.llm_temperature,
            timeout_seconds=self.settings.llm_timeout_seconds,
            max_output_tokens=self.settings.llm_max_output_tokens,
        )

    def _generate_answer(
        self,
        *,
        question: str,
        intent: AssistantIntent,
        tool_results: list[AssistantToolResult],
    ) -> LLMResponse[AssistantAnswer]:
        prompt = get_prompt("assistant.answer", "1.0.0")
        return self._provider().generate_structured(
            messages=[
                LLMMessage(role="system", content=prompt.system),
                LLMMessage(
                    role="user",
                    content=self._bounded_json(
                        {
                            "question": question,
                            "intent": intent.model_dump(mode="json"),
                            "tool_results": [
                                {
                                    "tool": result.tool_name,
                                    "data": result.data,
                                    "citation_ids": sorted(result.citation_sources),
                                }
                                for result in tool_results
                            ],
                            "rules": [
                                "Every finding must cite supplied citation_ids.",
                                "Use an empty findings list when there is no evidence.",
                                "Do not include unsupported numeric or causal claims.",
                            ],
                        }
                    ),
                ),
            ],
            response_schema=AssistantAnswer,
            model=self.settings.llm_model or "",
            temperature=self.settings.llm_temperature,
            timeout_seconds=self.settings.llm_timeout_seconds,
            max_output_tokens=self.settings.llm_max_output_tokens,
        )

    def _generate_answer_correction(
        self,
        *,
        question: str,
        draft: AssistantAnswer,
        tool_results: list[AssistantToolResult],
    ) -> LLMResponse[AssistantAnswer]:
        prompt = get_prompt("assistant.answer_correction", "1.0.0")
        return self._provider().generate_structured(
            messages=[
                LLMMessage(role="system", content=prompt.system),
                LLMMessage(
                    role="user",
                    content=self._bounded_json(
                        {
                            "question": question,
                            "invalid_draft": draft.model_dump(mode="json"),
                            "tool_results": [
                                {
                                    "tool": result.tool_name,
                                    "data": result.data,
                                    "citation_ids": sorted(result.citation_sources),
                                }
                                for result in tool_results
                            ],
                            "rules": [
                                "This is the only correction attempt.",
                                "Do not request or repeat tools.",
                                "Remove every unsupported statement.",
                            ],
                        }
                    ),
                ),
            ],
            response_schema=AssistantAnswer,
            model=self.settings.llm_model or "",
            temperature=0,
            timeout_seconds=self.settings.llm_timeout_seconds,
            max_output_tokens=self.settings.llm_max_output_tokens,
        )

    def _prepare_action_arguments(
        self,
        *,
        question: str,
        project_id: str,
        dataset_version_id: str | None,
        plan: AssistantPlan,
        budget: AssistantBudget,
    ) -> dict[int, dict[str, Any]]:
        arguments: dict[int, dict[str, Any]] = {}
        if dataset_version_id is None:
            return {
                step.position: {"purpose": step.purpose, "position": step.position}
                for step in plan.steps
            }
        context = self._proposal_context(project_id, dataset_version_id)
        for step in plan.steps:
            if step.tool_name == "analysis.draft_spec":
                budget.require_model_capacity()
                analysis_response = self._generate_analysis_spec(question, context)
                self._record_response(budget, analysis_response)
                candidate = analysis_response.content.model_dump(mode="json")
            elif step.tool_name == "cleaning.draft_plan":
                budget.require_model_capacity()
                cleaning_response = self._generate_cleaning_plan(question, context)
                self._record_response(budget, cleaning_response)
                candidate = cleaning_response.content.model_dump(mode="json")
            elif step.tool_name == "feature_engineering.suggest":
                budget.require_model_capacity()
                feature_response = self._generate_feature_suggestions(question, context)
                self._record_response(budget, feature_response)
                candidate = feature_response.content.model_dump(mode="json")
            elif step.tool_name == "analysis.run":
                candidate = {"run_kind": "full"}
            elif step.tool_name == "cleaning.execute":
                candidate = {}
            else:
                candidate = {"purpose": step.purpose, "position": step.position}
            validation_session = self.database.session()
            try:
                candidate = AssistantActionRegistry(validation_session).validate_arguments(
                    step.tool_name or "",
                    candidate,
                    project_id=project_id,
                    dataset_version_id=dataset_version_id,
                )
            finally:
                validation_session.close()
            arguments[step.position] = candidate
        return arguments

    def _generate_analysis_spec(
        self, question: str, context: dict[str, Any]
    ) -> LLMResponse[AnalysisSpecDraft]:
        prompt = get_prompt("assistant.analysis_spec", "1.0.0")
        return self._provider().generate_structured(
            messages=[
                LLMMessage(role="system", content=prompt.system),
                LLMMessage(
                    role="user",
                    content=self._bounded_json(
                        {
                            "question": question,
                            "schema_and_quality": context,
                            "rules": [
                                "Use only supplied column names.",
                                "Classification targets must be discrete; regression targets "
                                "must be numeric.",
                                "Exclude identifiers, sensitive fields, post-outcome fields, "
                                "and target proxies.",
                                "Use task-compatible metrics and an appropriate split strategy.",
                            ],
                        }
                    ),
                ),
            ],
            response_schema=AnalysisSpecDraft,
            model=self.settings.llm_model or "",
            temperature=self.settings.llm_temperature,
            timeout_seconds=self.settings.llm_timeout_seconds,
            max_output_tokens=self.settings.llm_max_output_tokens,
        )

    def _generate_cleaning_plan(
        self, question: str, context: dict[str, Any]
    ) -> LLMResponse[CleaningPlanDraft]:
        prompt = get_prompt("assistant.cleaning_plan", "1.0.0")
        return self._provider().generate_structured(
            messages=[
                LLMMessage(role="system", content=prompt.system),
                LLMMessage(
                    role="user",
                    content=self._bounded_json(
                        {
                            "question": question,
                            "schema_and_quality": context,
                            "allowed_parameter_rules": {
                                "impute_missing": ["method", "value only for constant"],
                                "drop_duplicates": ["columns", "keep"],
                                "cast_type": ["target_type", "date_format"],
                                "replace_values": ["mapping"],
                                "normalize_category": ["mapping"],
                                "filter_rows": ["operator", "value when required"],
                                "add_missing_indicator": ["name"],
                            },
                            "rules": [
                                "Reference only supplied quality issue identifiers.",
                                "Prefer reversible, minimal operations.",
                                "Mark row deletion and filters as high risk when material.",
                            ],
                        }
                    ),
                ),
            ],
            response_schema=CleaningPlanDraft,
            model=self.settings.llm_model or "",
            temperature=self.settings.llm_temperature,
            timeout_seconds=self.settings.llm_timeout_seconds,
            max_output_tokens=self.settings.llm_max_output_tokens,
        )

    def _generate_feature_suggestions(
        self, question: str, context: dict[str, Any]
    ) -> LLMResponse[FeatureSuggestionDraft]:
        prompt = get_prompt("assistant.feature_suggestions", "1.0.0")
        return self._provider().generate_structured(
            messages=[
                LLMMessage(role="system", content=prompt.system),
                LLMMessage(
                    role="user",
                    content=self._bounded_json(
                        {
                            "question": question,
                            "schema_and_quality": context,
                            "rules": [
                                "Use only supplied columns.",
                                "Do not use target-dependent encoding or post-outcome information.",
                                "Return suggestions and rationale, never executable code.",
                            ],
                        }
                    ),
                ),
            ],
            response_schema=FeatureSuggestionDraft,
            model=self.settings.llm_model or "",
            temperature=self.settings.llm_temperature,
            timeout_seconds=self.settings.llm_timeout_seconds,
            max_output_tokens=self.settings.llm_max_output_tokens,
        )

    def _proposal_context(self, project_id: str, dataset_version_id: str) -> dict[str, Any]:
        session = self.database.session()
        try:
            registry = AssistantToolRegistry(session)
            context = AssistantToolContext(project_id, dataset_version_id)
            schema = registry.execute("schema.get", context=context)
            quality = registry.execute(
                "quality.list_issues",
                context=context,
                arguments={"limit": 50, "status": "open"},
            )
            return {"schema": schema.data, "quality": quality.data}
        finally:
            session.close()

    def _execute_read_tools(
        self,
        *,
        project_id: str,
        dataset_version_id: str | None,
        intent: AssistantIntent,
        budget: AssistantBudget,
        llm_run_id: str,
    ) -> list[AssistantToolResult]:
        names = self._tools_for_intent(intent.intent, dataset_version_id)
        results: list[AssistantToolResult] = []
        session = self.database.session()
        try:
            with UnitOfWork(session) as uow:
                registry = AssistantToolRegistry(session)
                context = AssistantToolContext(project_id, dataset_version_id)
                for name in names:
                    budget.reserve_tool_call()
                    call = uow.assistant.create_tool_call(
                        llm_run_id=llm_run_id,
                        tool_name=name,
                        tool_version="1.0.0",
                        arguments={},
                        requires_confirmation=False,
                        status="running",
                    )
                    result = registry.execute(name, context=context)
                    uow.assistant.finish_tool_call(
                        call,
                        status="succeeded",
                        result=result.data,
                        resource_type=result.resource_type,
                        resource_id=result.resource_id,
                    )
                    results.append(result)
        finally:
            session.close()
        return results

    def _persist_plan(
        self,
        job_id: str,
        llm_run_id: str,
        plan: AssistantPlan,
        arguments: dict[int, dict[str, Any]],
        budget: AssistantBudget,
    ) -> None:
        if any(
            step.tool_name not in PLANNED_WRITE_TOOLS or not step.requires_confirmation
            for step in plan.steps
        ):
            raise DomainError(
                "LLM_INVALID_PLAN",
                "模型生成的计划包含未允许或未确认的操作",
                409,
            )
        session = self.database.session()
        try:
            with UnitOfWork(session) as uow:
                job = uow.jobs.get(job_id)
                run = uow.assistant.get_llm_run(llm_run_id)
                message = uow.assistant.get_message(
                    project_id=job.project_id, message_id=run.message_id
                )
                for step in plan.steps:
                    budget.reserve_tool_call()
                    uow.assistant.create_tool_call(
                        llm_run_id=llm_run_id,
                        tool_name=step.tool_name or "",
                        tool_version="1.0.0",
                        arguments=arguments[step.position],
                        requires_confirmation=True,
                    )
                uow.assistant.update_message(
                    message,
                    status="awaiting_confirmation",
                    content="已生成执行计划，确认前不会运行任何分析或数据变更。",
                    content_json={"plan": plan.model_dump(mode="json"), "answer": None},
                )
                uow.assistant.finish_llm_run(
                    run,
                    status="awaiting_confirmation",
                    model_call_count=budget.model_calls,
                    tool_call_count=budget.tool_calls,
                    input_tokens=budget.input_tokens,
                    output_tokens=budget.output_tokens,
                    latency_ms=budget.latency_ms,
                )
                uow.jobs.transition(
                    job,
                    status="blocked",
                    resource_type="assistant_message",
                    resource_id=message.message_id,
                )
        finally:
            session.close()

    def _run_child_job(self, kind: str, job_id: str) -> None:
        storage = get_file_storage()
        worker_id = f"{self.worker_id}:assistant-child"
        if kind == "analysis_run":
            AnalysisRunWorker(
                self.database,
                storage,
                default_tool_registry,
                worker_id=worker_id,
            ).run(job_id)
            return
        if kind == "cleaning_preview":
            CleaningPreviewWorker(self.database, storage, worker_id=worker_id).run(job_id)
            return
        if kind == "cleaning_execute":
            CleaningExecuteWorker(self.database, storage, worker_id=worker_id).run(job_id)
            return
        raise DomainError(
            "LLM_TOOL_NOT_ALLOWED",
            "受控操作生成了未知子任务",
            409,
            details={"kind": kind},
        )

    def _require_child_success(self, job_id: str) -> None:
        session = self.database.session()
        try:
            job = JobRepository(session).get(job_id)
            if job.status != "succeeded":
                error = job.error_json or {}
                raise DomainError(
                    str(error.get("code", "ASSISTANT_CHILD_JOB_FAILED")),
                    "受控数据任务未成功完成",
                    409,
                    retryable=bool(error.get("retryable", False)),
                    details={"child_job_id": job_id, "child_status": job.status},
                )
        finally:
            session.close()

    def _mark_tool_failed(self, tool_call_id: str, error: Exception) -> None:
        session = self.database.session()
        try:
            with UnitOfWork(session) as uow:
                call = uow.assistant.get_tool_call(tool_call_id)
                if call.status == "running":
                    code = error.code if isinstance(error, DomainError) else "EXECUTOR_UNAVAILABLE"
                    uow.assistant.finish_tool_call(
                        call,
                        status="failed",
                        error={"code": code, "retryable": getattr(error, "retryable", False)},
                    )
        finally:
            session.close()

    @staticmethod
    def _execution_summary(results: list[dict[str, Any]]) -> str:
        labels = {
            "analysis.draft_spec": "分析规格已创建",
            "analysis.run": "真实分析与建模运行已完成",
            "cleaning.draft_plan": "清洗计划与真实影响预览已生成",
            "cleaning.execute": "清洗计划已执行并生成新数据版本",
            "feature_engineering.suggest": "特征工程建议 Artifact 已生成",
        }
        completed = [labels.get(str(item["tool_name"]), str(item["tool_name"])) for item in results]
        return "；".join(completed) + "。"

    def _persist_answer(
        self,
        job_id: str,
        llm_run_id: str,
        answer: AssistantAnswer,
        budget: AssistantBudget,
    ) -> None:
        session = self.database.session()
        try:
            with UnitOfWork(session) as uow:
                job = uow.jobs.get(job_id)
                run = uow.assistant.get_llm_run(llm_run_id)
                message = uow.assistant.get_message(
                    project_id=job.project_id, message_id=run.message_id
                )
                uow.assistant.update_message(
                    message,
                    status="completed",
                    content=answer.summary,
                    content_json={"plan": None, "answer": answer.model_dump(mode="json")},
                )
                uow.assistant.finish_llm_run(
                    run,
                    status="succeeded",
                    model_call_count=budget.model_calls,
                    tool_call_count=budget.tool_calls,
                    input_tokens=budget.input_tokens,
                    output_tokens=budget.output_tokens,
                    latency_ms=budget.latency_ms,
                )
                uow.jobs.transition(
                    job,
                    status="succeeded",
                    resource_type="assistant_message",
                    resource_id=message.message_id,
                )
                uow.audit.append(
                    action="assistant.turn_completed",
                    result="success",
                    summary={
                        "model_calls": budget.model_calls,
                        "tool_calls": budget.tool_calls,
                        "input_tokens": budget.input_tokens,
                        "output_tokens": budget.output_tokens,
                    },
                    project_id=job.project_id,
                    subject_id=job.created_by,
                    object_type="assistant_message",
                    object_id=message.message_id,
                    request_id=f"job:{job_id}",
                )
                logger.info(
                    "assistant_turn_completed",
                    extra={
                        "project_id": job.project_id,
                        "job_id": job_id,
                        "message_id": message.message_id,
                        "model_calls": budget.model_calls,
                        "tool_calls": budget.tool_calls,
                        "input_tokens": budget.input_tokens,
                        "output_tokens": budget.output_tokens,
                        "latency_ms": budget.latency_ms,
                    },
                )
        finally:
            session.close()

    def _ensure_active(self, job_id: str, llm_run_id: str, budget: AssistantBudget) -> None:
        session = self.database.session()
        try:
            with UnitOfWork(session) as uow:
                job = uow.jobs.get(job_id)
                if job.status == "cancelling":
                    run = uow.assistant.get_llm_run(llm_run_id)
                    message = uow.assistant.get_message(
                        project_id=job.project_id, message_id=run.message_id
                    )
                    uow.assistant.update_message(message, status="cancelled")
                    uow.assistant.finish_llm_run(
                        run,
                        status="cancelled",
                        model_call_count=budget.model_calls,
                        tool_call_count=budget.tool_calls,
                        input_tokens=budget.input_tokens,
                        output_tokens=budget.output_tokens,
                        latency_ms=budget.latency_ms,
                    )
                    uow.jobs.transition(job, status="cancelled")
                    raise DomainError("JOB_CANCELLED", "Assistant Turn 已取消", 409)
                uow.jobs.heartbeat(
                    job=job,
                    worker_id=self.worker_id,
                    progress=min(30 + budget.model_calls * 20 + budget.tool_calls * 5, 90),
                    current_step="读取证据并生成回答",
                    lease_seconds=max(self.settings.llm_timeout_seconds * 3, 300),
                )
        finally:
            session.close()

    def _fail(self, job_id: str, error: DomainError) -> None:
        session = self.database.session()
        try:
            with UnitOfWork(session) as uow:
                job = uow.jobs.get(job_id)
                message_id = str(job.request_json.get("assistant_message_id", ""))
                if message_id:
                    message = uow.assistant.get_message(
                        project_id=job.project_id, message_id=message_id
                    )
                    if message.status not in {"completed", "cancelled"}:
                        uow.assistant.update_message(
                            message,
                            status="failed",
                            content="本轮分析未完成，请稍后重试。",
                        )
                    run = uow.assistant.latest_llm_run_for_message(message_id)
                    if run and run.status not in {"succeeded", "failed", "cancelled"}:
                        budget = (
                            self._active_budget
                            if self._active_run_id == run.llm_run_id
                            else None
                        )
                        uow.assistant.finish_llm_run(
                            run,
                            status="failed",
                            model_call_count=budget.model_calls if budget else run.model_call_count,
                            tool_call_count=budget.tool_calls if budget else run.tool_call_count,
                            input_tokens=budget.input_tokens if budget else run.input_tokens,
                            output_tokens=budget.output_tokens if budget else run.output_tokens,
                            latency_ms=budget.latency_ms if budget else run.latency_ms,
                            error={"code": error.code, "retryable": error.retryable},
                        )
                if job.status == "queued":
                    job.status = "running"
                if job.status in {"running", "cancelling"}:
                    uow.jobs.transition(
                        job,
                        status="failed",
                        error={
                            "code": error.code,
                            "message": error.message,
                            "request_id": f"job:{job_id}",
                            "retryable": error.retryable,
                            "details": error.details,
                        },
                    )
                uow.audit.append(
                    action="assistant.turn_failed",
                    result="failed",
                    summary={"job_id": job_id},
                    project_id=job.project_id,
                    subject_id=job.created_by,
                    object_type="assistant_message",
                    object_id=message_id or None,
                    request_id=f"job:{job_id}",
                    error_code=error.code,
                )
                logger.warning(
                    "assistant_turn_failed",
                    extra={
                        "project_id": job.project_id,
                        "job_id": job_id,
                        "message_id": message_id or None,
                        "error_code": error.code,
                        "retryable": error.retryable,
                    },
                )
        finally:
            session.close()

    def _persist_trace(self, llm_run_id: str, trace: AgentTrace) -> None:
        session = self.database.session()
        try:
            with UnitOfWork(session) as uow:
                run = uow.assistant.get_llm_run(llm_run_id)
                uow.assistant.update_llm_run_manifest(
                    run, {"orchestration": trace.manifest()}
                )
        finally:
            session.close()

    def _require_provider_available(self) -> None:
        session = self.database.session()
        try:
            with UnitOfWork(session) as uow:
                uow.assistant.require_provider_available(
                    provider=self.settings.llm_provider,
                    cooldown_seconds=self.settings.llm_circuit_breaker_cooldown_seconds,
                )
        finally:
            session.close()

    def _record_provider_success(self) -> None:
        session = self.database.session()
        try:
            with UnitOfWork(session) as uow:
                uow.assistant.record_provider_success(provider=self.settings.llm_provider)
        finally:
            session.close()

    def _record_provider_failure(self) -> None:
        session = self.database.session()
        try:
            with UnitOfWork(session) as uow:
                uow.assistant.record_provider_failure(
                    provider=self.settings.llm_provider,
                    threshold=self.settings.llm_circuit_breaker_failure_threshold,
                )
        finally:
            session.close()

    @staticmethod
    def _record_response(budget: AssistantBudget, response: LLMResponse[Any]) -> None:
        budget.record_model_call(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=response.latency_ms,
        )

    @staticmethod
    def _tools_for_intent(intent: str, version_id: str | None) -> list[str]:
        if intent == "answer_from_evidence":
            return ["artifact.search", "claim.search"] if version_id else ["run.get_status"]
        if intent == "inspect_data":
            return (
                ["project.get_context", "schema.get", "quality.list_issues"]
                if version_id
                else ["project.get_context"]
            )
        if intent == "explain_model":
            return ["artifact.search", "claim.search", "run.get_status"]
        return ["project.get_context"]

    def _bounded_json(self, payload: dict[str, Any]) -> str:
        encoded = json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))
        max_chars = self.settings.llm_max_input_tokens * 4
        if len(encoded) > max_chars:
            raise DomainError(
                "LLM_CONTEXT_TOO_LARGE",
                "当前会话上下文过长，请新建会话或缩小问题范围",
                409,
            )
        return encoded

    @staticmethod
    def _history_payload(rows: list[AssistantMessageRow]) -> list[dict[str, str]]:
        return [
            {"role": row.role, "content": (row.content or "")[:2000]}
            for row in rows
            if row.role in {"user", "assistant"} and row.content
        ]

    def _provider(self) -> LLMProvider:
        if self.provider is None:
            raise DomainError("LLM_DISABLED", "大语言模型功能尚未启用", 409)
        return self.provider


def process_assistant_turn_job(job_id: str) -> None:
    AssistantTurnWorker(get_database(), worker_id="fastapi-background-assistant").run(job_id)
