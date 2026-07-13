from __future__ import annotations

from datetime import timedelta

import pytest

from app.api.schemas import AssistantConversationCreate, AssistantMessageCreate
from app.core.clock import utc_now
from app.core.config import get_settings
from app.domain.errors import DomainError
from app.persistence.orm.assistant_models import LLMProviderStateRow
from app.persistence.repositories.assistant import AssistantRepository
from app.persistence.repositories.projects import ProjectRepository
from app.persistence.session import get_database
from app.persistence.unit_of_work import UnitOfWork
from app.services.assistant import AssistantService
from app.workers.assistant_retention import AssistantRetentionWorker


def test_project_concurrency_limit_rejects_a_second_queued_turn(
    monkeypatch, app_client
) -> None:
    del app_client
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("LLM_MODEL", "fake-model")
    monkeypatch.setenv("LLM_MAX_CONCURRENT_TURNS_PER_PROJECT", "1")
    get_settings.cache_clear()
    session = get_database().session()
    try:
        with UnitOfWork(session):
            project = ProjectRepository(session).create(
                name="Quota Test",
                description=None,
                timezone="Asia/Shanghai",
                language="zh-CN",
                subject_id="user-a",
            )
            service = AssistantService(session, get_settings())
            conversation = service.create_conversation(
                project.project_id,
                AssistantConversationCreate(title="Quota"),
                subject_id="user-a",
                request_id="test",
            )
            service.create_turn(
                project.project_id,
                conversation.conversation_id,
                AssistantMessageCreate(content="first"),
                subject_id="user-a",
                request_id="test",
            )
            with pytest.raises(DomainError) as captured:
                service.create_turn(
                    project.project_id,
                    conversation.conversation_id,
                    AssistantMessageCreate(content="second"),
                    subject_id="user-a",
                    request_id="test",
                )
            assert captured.value.code == "LLM_PROJECT_CONCURRENCY_LIMIT"
    finally:
        session.close()


def test_provider_circuit_breaker_opens_and_recovers_after_cooldown(app_client) -> None:
    del app_client
    session = get_database().session()
    try:
        with UnitOfWork(session):
            repository = AssistantRepository(session)
            repository.record_provider_failure(provider="test-provider", threshold=2)
            repository.record_provider_failure(provider="test-provider", threshold=2)
            with pytest.raises(DomainError):
                repository.require_provider_available(
                    provider="test-provider", cooldown_seconds=60
                )
            state = session.get(LLMProviderStateRow, "test-provider")
            assert state is not None
            state.opened_at = utc_now() - timedelta(seconds=61)
            repository.require_provider_available(
                provider="test-provider", cooldown_seconds=60
            )
            assert state.status == "half_open"
            repository.record_provider_success(provider="test-provider")
            assert state.status == "closed"
            assert state.consecutive_failures == 0
    finally:
        session.close()


def test_retention_archives_inactive_conversations_and_scrubs_call_payloads(
    monkeypatch, app_client
) -> None:
    del app_client
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("LLM_MODEL", "fake-model")
    monkeypatch.setenv("LLM_RETENTION_DAYS", "1")
    monkeypatch.setenv("LLM_ARCHIVE_INACTIVE_DAYS", "1")
    get_settings.cache_clear()
    old = utc_now() - timedelta(days=2)
    session = get_database().session()
    try:
        with UnitOfWork(session):
            project = ProjectRepository(session).create(
                name="Retention Test",
                description=None,
                timezone="Asia/Shanghai",
                language="zh-CN",
                subject_id="user-a",
            )
            service = AssistantService(session, get_settings())
            conversation = service.create_conversation(
                project.project_id,
                AssistantConversationCreate(title="Retention"),
                subject_id="user-a",
                request_id="test",
            )
            turn = service.create_turn(
                project.project_id,
                conversation.conversation_id,
                AssistantMessageCreate(content="inspect"),
                subject_id="user-a",
                request_id="test",
            )
            repository = AssistantRepository(session)
            conversation_row = repository.get_conversation(
                project_id=project.project_id,
                conversation_id=conversation.conversation_id,
            )
            conversation_row.updated_at = old
            assert turn.job is not None
            run = repository.create_llm_run(
                message_id=turn.assistant_message.message_id,
                project_id=project.project_id,
                job_id=turn.job.job_id,
                provider="fake",
                model="fake-model",
                prompt_name="assistant.intent",
                prompt_version="1.0.0",
                context_manifest={"dataset_version_id": None, "private": "scrub-me"},
            )
            run.created_at = old
            call = repository.create_tool_call(
                llm_run_id=run.llm_run_id,
                tool_name="project.get_context",
                tool_version="1.0.0",
                arguments={"private": "scrub-me"},
                requires_confirmation=False,
                status="running",
            )
            repository.finish_tool_call(
                call, status="succeeded", result={"private": "scrub-me"}
            )
    finally:
        session.close()

    result = AssistantRetentionWorker(get_database(), settings=get_settings()).run()
    assert result == {
        "archived_conversations": 1,
        "scrubbed_runs": 1,
        "scrubbed_tool_calls": 1,
    }
    assert AssistantRetentionWorker(get_database(), settings=get_settings()).run() == {
        "archived_conversations": 0,
        "scrubbed_runs": 0,
        "scrubbed_tool_calls": 0,
    }
    verify = get_database().session()
    try:
        repository = AssistantRepository(verify)
        conversation_row = repository.get_conversation(
            project_id=project.project_id,
            conversation_id=conversation.conversation_id,
        )
        retained_run = repository.latest_llm_run_for_message(
            turn.assistant_message.message_id
        )
        assert conversation_row.status == "archived"
        assert retained_run is not None
        assert retained_run.context_manifest_json["retained"] is True
        retained_call = repository.list_tool_calls(retained_run.llm_run_id)[0]
        assert retained_call.arguments_json == {"retained": True}
        assert retained_call.result_json == {"retained": True}
    finally:
        verify.close()
