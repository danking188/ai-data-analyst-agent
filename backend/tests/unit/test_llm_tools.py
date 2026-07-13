from __future__ import annotations

import pytest

from app.domain.errors import DomainError
from app.llm.tools import AssistantToolContext, AssistantToolRegistry
from app.persistence.repositories.projects import ProjectRepository
from app.persistence.session import get_database
from app.persistence.unit_of_work import UnitOfWork


def test_read_only_tool_registry_is_project_bound(app_client) -> None:
    del app_client
    session = get_database().session()
    try:
        with UnitOfWork(session) as uow:
            first = uow.projects.create(
                name="First",
                description=None,
                timezone="Asia/Shanghai",
                language="zh-CN",
                subject_id="user-a",
            )
            second = uow.projects.create(
                name="Second",
                description=None,
                timezone="Asia/Shanghai",
                language="zh-CN",
                subject_id="user-b",
            )
        registry = AssistantToolRegistry(session)
        result = registry.execute(
            "project.get_context",
            context=AssistantToolContext(first.project_id, None),
        )
        assert result.data["project"]["project_id"] == first.project_id
        assert result.data["project"]["name"] == "First"
        assert result.data["project"]["project_id"] != second.project_id
    finally:
        session.close()


def test_tool_registry_rejects_unknown_and_extra_arguments(app_client) -> None:
    del app_client
    session = get_database().session()
    try:
        project = ProjectRepository(session).create(
            name="Project",
            description=None,
            timezone="Asia/Shanghai",
            language="zh-CN",
            subject_id="user-a",
        )
        session.commit()
        registry = AssistantToolRegistry(session)
        with pytest.raises(DomainError, match="未被允许"):
            registry.execute(
                "shell.execute",
                context=AssistantToolContext(project.project_id, None),
            )
        with pytest.raises(ValueError):
            registry.execute(
                "project.get_context",
                context=AssistantToolContext(project.project_id, None),
                arguments={"url": "https://example.com"},
            )
    finally:
        session.close()
