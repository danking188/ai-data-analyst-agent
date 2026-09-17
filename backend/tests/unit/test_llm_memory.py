from __future__ import annotations

from app.llm.memory import MEMORY_VERSION, StructuredMemoryManager
from app.persistence.repositories.assistant import AssistantRepository
from app.persistence.repositories.datasets import DatasetRepository, DatasetVersionDraft
from app.persistence.repositories.projects import ProjectRepository
from app.persistence.session import get_database
from app.persistence.unit_of_work import UnitOfWork


def test_structured_memory_keeps_explicit_preferences_and_invalidates_version_facts(
    app_client,
) -> None:
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
    finally:
        session.close()
