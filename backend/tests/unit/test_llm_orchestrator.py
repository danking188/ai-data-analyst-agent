from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.errors import DomainError
from app.llm.orchestrator import AgentState, AgentTrace, ContextCompactor
from app.persistence.orm.assistant_models import AssistantMessageRow


def _message(position: int, role: str, content: str) -> AssistantMessageRow:
    now = datetime(2026, 7, 13, tzinfo=UTC)
    return AssistantMessageRow(
        message_id=f"msg_{position}",
        conversation_id="conv_1",
        role=role,
        status="completed",
        content=content,
        content_json=None,
        parent_message_id=None,
        job_id=None,
        created_by="user-a",
        created_at=now,
        completed_at=now,
    )


def test_agent_trace_enforces_bounded_state_transitions() -> None:
    trace = AgentTrace(max_steps=4)
    trace.move(AgentState.EXECUTE)
    trace.move(AgentState.CHECK)
    trace.move(AgentState.SUMMARIZE)
    trace.move(AgentState.COMPLETE)
    assert trace.manifest()["state"] == "complete"
    assert len(trace.manifest()["transitions"]) == 4

    with pytest.raises(DomainError, match="非法状态"):
        trace.move(AgentState.PLAN)


def test_context_compactor_preserves_summary_and_recent_message_ids() -> None:
    rows = [_message(index, "user" if index % 2 else "assistant", f"content-{index}")
            for index in range(1, 18)]
    compacted = ContextCompactor(recent_limit=4).compact(
        rows, existing_summary="dataset_version_id=ver_123"
    )
    assert compacted.compacted_count == 13
    assert compacted.message_ids == ["msg_14", "msg_15", "msg_16", "msg_17"]
    assert compacted.summary is not None
    assert "dataset_version_id=ver_123" in compacted.summary
    assert "content-13" in compacted.summary
    assert [item["content"] for item in compacted.recent_messages] == [
        "content-14",
        "content-15",
        "content-16",
        "content-17",
    ]
