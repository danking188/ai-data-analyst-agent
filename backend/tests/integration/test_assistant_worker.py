from __future__ import annotations

from app.api.schemas import (
    AssistantConfirmationRequest,
    AssistantConversationCreate,
    AssistantMessageCreate,
)
from app.core.config import get_settings
from app.llm.provider import FakeLLMProvider
from app.persistence.repositories.assistant import AssistantRepository
from app.persistence.repositories.jobs import JobRepository
from app.persistence.repositories.projects import ProjectRepository
from app.persistence.session import get_database
from app.persistence.unit_of_work import UnitOfWork
from app.services.assistant import AssistantService
from app.workers.assistant import AssistantTurnWorker


def _queued_turn(monkeypatch, app_client, question: str) -> tuple[str, str, str]:
    del app_client
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("LLM_MODEL", "fake-model")
    get_settings.cache_clear()
    session = get_database().session()
    try:
        with UnitOfWork(session):
            project = ProjectRepository(session).create(
                name="Assistant Test",
                description=None,
                timezone="Asia/Shanghai",
                language="zh-CN",
                subject_id="user-a",
            )
            service = AssistantService(session, get_settings())
            conversation = service.create_conversation(
                project.project_id,
                AssistantConversationCreate(title="Test"),
                subject_id="user-a",
                request_id="test-request",
            )
            turn = service.create_turn(
                project.project_id,
                conversation.conversation_id,
                AssistantMessageCreate(content=question),
                subject_id="user-a",
                request_id="test-request",
            )
            assert turn.job is not None
            return project.project_id, turn.assistant_message.message_id, turn.job.job_id
    finally:
        session.close()


def test_assistant_worker_completes_project_context_answer(monkeypatch, app_client) -> None:
    project_id, message_id, job_id = _queued_turn(
        monkeypatch, app_client, "这个项目当前绑定了什么数据？"
    )
    provider = FakeLLMProvider(
        [
            {
                "intent": "inspect_data",
                "rationale": "Inspect project context",
                "requires_new_computation": False,
            },
            {
                "summary": "当前会话尚未绑定数据版本。",
                "findings": [],
                "next_actions": [
                    {
                        "label": "选择数据版本",
                        "action_type": "ask",
                        "requires_confirmation": False,
                    }
                ],
                "limitations": ["没有可读取的数据版本"],
            },
        ]
    )
    worker = AssistantTurnWorker(
        get_database(),
        worker_id="test-assistant",
        provider=provider,
        settings=get_settings(),
    )
    assert worker.run(job_id) is True
    session = get_database().session()
    try:
        repository = AssistantRepository(session)
        message = repository.get_message(project_id=project_id, message_id=message_id)
        job = JobRepository(session).get(job_id)
        run = repository.latest_llm_run_for_message(message_id)
        assert message.status == "completed", job.error_json
        assert message.content == "当前会话尚未绑定数据版本。"
        assert job.status == "succeeded"
        assert run is not None and run.model_call_count == 2
        calls = repository.list_tool_calls(run.llm_run_id)
        assert [call.tool_name for call in calls] == ["project.get_context"]
        assert calls[0].requires_confirmation is False
    finally:
        session.close()


def test_assistant_worker_stops_new_computation_at_confirmation(monkeypatch, app_client) -> None:
    project_id, message_id, job_id = _queued_turn(
        monkeypatch, app_client, "为这个项目训练一个分类模型"
    )
    provider = FakeLLMProvider(
        [
            {
                "intent": "plan_analysis",
                "rationale": "A new analysis run is required",
                "requires_new_computation": True,
            },
            {
                "objective": "草拟并运行分类分析",
                "dataset_version_id": None,
                "steps": [
                    {
                        "position": 1,
                        "title": "草拟分析规格",
                        "tool_name": "analysis.draft_spec",
                        "purpose": "明确目标列、切分和指标",
                        "requires_confirmation": True,
                    }
                ],
                "estimated_model_calls": 2,
                "estimated_tool_calls": 1,
                "limitations": ["尚未选择数据版本"],
            },
        ]
    )
    worker = AssistantTurnWorker(
        get_database(),
        worker_id="test-assistant",
        provider=provider,
        settings=get_settings(),
    )
    assert worker.run(job_id) is True
    session = get_database().session()
    try:
        repository = AssistantRepository(session)
        message = repository.get_message(project_id=project_id, message_id=message_id)
        job = JobRepository(session).get(job_id)
        run = repository.latest_llm_run_for_message(message_id)
        assert message.status == "awaiting_confirmation", job.error_json
        assert job.status == "blocked"
        assert run is not None and run.status == "awaiting_confirmation"
        calls = repository.list_tool_calls(run.llm_run_id)
        assert len(calls) == 1
        assert calls[0].tool_name == "analysis.draft_spec"
        assert calls[0].status == "proposed"
        assert calls[0].requires_confirmation is True

        with UnitOfWork(session):
            confirmed = AssistantService(session, get_settings()).confirm_plan(
                project_id,
                message_id,
                AssistantConfirmationRequest(decision="approve"),
                subject_id="user-a",
                request_id="confirm-request",
            )

        session.expire_all()
        message = repository.get_message(project_id=project_id, message_id=message_id)
        run = repository.latest_llm_run_for_message(message_id)
        calls = repository.list_tool_calls(run.llm_run_id) if run else []
        assert message.status == "completed"
        assert message.content == "计划已确认，后续操作将由受控任务继续执行。"
        assert run is not None and run.status == "succeeded"
        assert calls[0].status == "approved"
        assert confirmed.assistant_message.status == "queued"
        assert confirmed.job is not None and confirmed.job.kind == "assistant_turn"
    finally:
        session.close()


def test_assistant_worker_corrects_unsupported_answer_without_repeating_tools(
    monkeypatch, app_client
) -> None:
    project_id, message_id, job_id = _queued_turn(
        monkeypatch, app_client, "这个项目当前是什么状态？"
    )
    provider = FakeLLMProvider(
        [
            {
                "intent": "inspect_data",
                "rationale": "Inspect project context",
                "requires_new_computation": False,
            },
            {
                "summary": "项目有 99 个数据版本。",
                "findings": [
                    {
                        "text": "项目有 99 个数据版本。",
                        "claim_level": 1,
                        "citation_ids": ["invented_source"],
                        "limitations": [],
                    }
                ],
                "next_actions": [],
                "limitations": [],
            },
            {
                "summary": "当前会话尚未绑定数据版本。",
                "findings": [],
                "next_actions": [],
                "limitations": ["项目上下文没有提供可引用的分析证据"],
            },
        ]
    )
    worker = AssistantTurnWorker(
        get_database(),
        worker_id="test-assistant-correction",
        provider=provider,
        settings=get_settings(),
    )
    assert worker.run(job_id) is True

    session = get_database().session()
    try:
        repository = AssistantRepository(session)
        message = repository.get_message(project_id=project_id, message_id=message_id)
        run = repository.latest_llm_run_for_message(message_id)
        assert message.status == "completed"
        assert message.content == "当前会话尚未绑定数据版本。"
        assert run is not None and run.model_call_count == 3
        calls = repository.list_tool_calls(run.llm_run_id)
        assert [call.tool_name for call in calls] == ["project.get_context"]
        assert run.context_manifest_json["orchestration"]["state"] == "complete"
    finally:
        session.close()
