from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.clock import utc_now
from app.llm.memory import MEMORY_VERSION, StructuredMemoryManager
from app.persistence.orm.assistant_models import LLMRunRow
from app.persistence.repositories.assistant import AssistantRepository
from app.persistence.repositories.datasets import DatasetRepository, DatasetVersionDraft
from app.persistence.repositories.projects import ProjectRepository
from app.persistence.session import get_database
from app.persistence.unit_of_work import UnitOfWork


def test_structured_memory_keeps_explicit_preferences_and_invalidates_version_facts(
    memory_context,
) -> None:
    session, project, conversation, versions, message = memory_context
    with UnitOfWork(session):
        manager = StructuredMemoryManager(session)
        memory = manager.refresh(
            project_id=project.project_id,
            conversation_id=conversation.conversation_id,
            dataset_version_id=versions[0].version_id,
            messages=[message],
        )
        refreshed = manager.refresh(
            project_id=project.project_id,
            conversation_id=conversation.conversation_id,
            dataset_version_id=versions[1].version_id,
            messages=[message],
        )
        assert memory["memory_version"] == MEMORY_VERSION
        assert {item["value"] for item in memory["user_preferences"]} == {
            "English",
            "concise",
            "table",
        }
        assert refreshed["session_state"]["version_changed"] is True
        assert refreshed["verified_facts"] == []
        assert "请用英文" not in StructuredMemoryManager.prompt_context(refreshed)


@pytest.fixture()
def memory_context(app_client):
    del app_client
    session = get_database().session()
    try:
        with UnitOfWork(session):
            project = ProjectRepository(session).create(
                name="Memory",
                description=None,
                timezone="Asia/Shanghai",
                language="zh-CN",
                subject_id="user-a",
            )
            datasets = DatasetRepository(session)
            dataset_row = datasets.create_dataset(
                project_id=project.project_id,
                name="memory.csv",
                source_type="csv",
                subject_id="user-a",
            )
            versions = []
            for index in (1, 2):
                version = datasets.create_version(
                    project_id=project.project_id,
                    dataset_id=dataset_row.dataset_id,
                    subject_id="user-a",
                    draft=DatasetVersionDraft(
                        source_file_name="memory.csv",
                        source_type="csv",
                        source_storage_key=f"source/{index}.csv",
                        file_hash="sha256:" + str(index) * 64,
                        file_size_bytes=10,
                    ),
                )
                datasets.mark_version_ready(
                    version,
                    data_storage_key=f"versions/{index}.parquet",
                    data_checksum="sha256:" + str(index + 2) * 64,
                    row_count=1,
                    column_count=1,
                )
                versions.append(version)
            repository = AssistantRepository(session)
            conversation = repository.create_conversation(
                project_id=project.project_id,
                title="Memory",
                dataset_version_id=versions[0].version_id,
                subject_id="user-a",
            )
            message = repository.create_message(
                conversation_id=conversation.conversation_id,
                role="user",
                status="completed",
                subject_id="user-a",
                content="请用英文简洁表格回答",
            )
        yield session, project, conversation, versions, message
    finally:
        session.close()


@pytest.mark.parametrize("status", ["proposed", "approved", "succeeded"])
def test_memory_filters_tool_resources_by_original_version_and_expiry(
    memory_context,
    monkeypatch,
    status,
) -> None:
    session, project, conversation, versions, message = memory_context
    now = utc_now()
    monkeypatch.setattr("app.llm.memory.utc_now", lambda: now)
    with UnitOfWork(session):
        run = LLMRunRow(
            llm_run_id="llmr_memory",
            message_id=message.message_id,
            project_id=project.project_id,
            job_id=None,
            provider="fake",
            model="fake",
            prompt_name="assistant",
            prompt_version="1.0.0",
            status="succeeded",
            context_manifest_json={"dataset_version_id": versions[0].version_id},
            created_at=now,
        )
        session.add(run)
        session.flush()
        call = AssistantRepository(session).create_tool_call(
            llm_run_id=run.llm_run_id,
            tool_name="analysis.run",
            tool_version="1.0.0",
            arguments={},
            requires_confirmation=True,
            status=status,
        )
        call.created_at = now
        call.result_resource_type = "analysis_run"
        call.result_resource_id = "run_memory"
        session.flush()
        manager = StructuredMemoryManager(session)

        def refresh(version):
            return manager.refresh(
                project_id=project.project_id,
                conversation_id=conversation.conversation_id,
                dataset_version_id=version.version_id,
                messages=[],
            )

        field = "verified_facts" if status == "succeeded" else "pending_decisions"
        assert refresh(versions[0])[field][0]["source_id"] == call.tool_call_id
        assert refresh(versions[1])[field] == []
        # Repeated refresh must not reintroduce an old decision under the new version.
        assert refresh(versions[1])[field] == []
        switched_back = refresh(versions[0])
        if status == "succeeded":
            assert switched_back[field] == []
        assert refresh(versions[0])[field][0]["source_id"] == call.tool_call_id
        lifetime = timedelta(days=30 if status == "succeeded" else 1)
        monkeypatch.setattr("app.llm.memory.utc_now", lambda: now + lifetime)
        assert refresh(versions[0])[field] == []
        # Expiration removes prompt context, without deleting execution/audit records.
        assert session.get(LLMRunRow, run.llm_run_id) is run
        assert call.status == status


def test_memory_preferences_expire_without_history_refresh_extending_lifetime(
    memory_context,
    monkeypatch,
) -> None:
    session, project, conversation, versions, message = memory_context
    now = message.created_at
    manager = StructuredMemoryManager(session)

    def refresh(messages):
        return manager.refresh(
            project_id=project.project_id,
            conversation_id=conversation.conversation_id,
            dataset_version_id=versions[0].version_id,
            messages=messages,
        )

    with UnitOfWork(session):
        monkeypatch.setattr("app.llm.memory.utc_now", lambda: now)
        initial = refresh([message])
        monkeypatch.setattr("app.llm.memory.utc_now", lambda: now + timedelta(days=1))
        repeated = refresh([message])
        assert repeated["user_preferences"] == initial["user_preferences"]
        monkeypatch.setattr("app.llm.memory.utc_now", lambda: now + timedelta(days=90))
        assert refresh([])["user_preferences"] == []
        assert refresh([message])["user_preferences"] == []
