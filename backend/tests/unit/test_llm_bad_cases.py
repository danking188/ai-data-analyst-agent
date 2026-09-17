from app.llm.bad_cases import collect_bad_cases
from app.persistence.repositories.assistant import AssistantRepository
from app.persistence.repositories.projects import ProjectRepository
from app.persistence.session import get_database
from app.persistence.unit_of_work import UnitOfWork


def test_bad_case_export_redacts_secrets_and_personal_email(app_client) -> None:
    del app_client
    session = get_database().session()
    try:
        with UnitOfWork(session):
            project = ProjectRepository(session).create(
                name="Bad cases",
                description=None,
                timezone="Asia/Shanghai",
                language="zh-CN",
                subject_id="user-a",
            )
            repository = AssistantRepository(session)
            conversation = repository.create_conversation(
                project_id=project.project_id,
                title="Feedback",
                dataset_version_id=None,
                subject_id="user-a",
            )
            message = repository.create_message(
                conversation_id=conversation.conversation_id,
                role="assistant",
                status="completed",
                subject_id="user-a",
                content="Contact person@example.com with sk-secret123456789",
            )
            repository.create_feedback(
                project_id=project.project_id,
                message_id=message.message_id,
                rating="not_helpful",
                reason="incorrect",
                comment="Bearer abcdefghijklmnop person@example.com",
                subject_id="user-a",
            )
        cases = collect_bad_cases(session)
        rendered = str(cases)
        assert cases[0]["source"] == "user_feedback"
        assert "person@example.com" not in rendered
        assert "sk-secret" not in rendered
        assert "[REDACTED_SECRET]" in rendered
    finally:
        session.close()
