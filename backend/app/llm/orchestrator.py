from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.domain.errors import DomainError
from app.persistence.orm.assistant_models import AssistantMessageRow


class AgentState(StrEnum):
    PLAN = "plan"
    EXECUTE = "execute"
    CHECK = "check"
    SUMMARIZE = "summarize"
    COMPLETE = "complete"
    FAILED = "failed"


_ALLOWED_TRANSITIONS = {
    AgentState.PLAN: {AgentState.EXECUTE, AgentState.CHECK, AgentState.FAILED},
    AgentState.EXECUTE: {AgentState.CHECK, AgentState.FAILED},
    AgentState.CHECK: {AgentState.SUMMARIZE, AgentState.FAILED},
    AgentState.SUMMARIZE: {AgentState.COMPLETE, AgentState.FAILED},
    AgentState.COMPLETE: set(),
    AgentState.FAILED: set(),
}


@dataclass(slots=True)
class AgentTrace:
    max_steps: int = 8
    state: AgentState = AgentState.PLAN
    transitions: list[dict[str, Any]] = field(default_factory=list)

    def move(self, target: AgentState, *, detail: str | None = None) -> None:
        if target not in _ALLOWED_TRANSITIONS[self.state]:
            raise DomainError(
                "LLM_INVALID_STATE_TRANSITION",
                "Assistant 编排器进入了非法状态",
                409,
                details={"from": self.state.value, "to": target.value},
            )
        if len(self.transitions) >= self.max_steps:
            raise DomainError("LLM_STEP_LIMIT_EXCEEDED", "Assistant 已达到最大执行步数", 409)
        self.transitions.append(
            {"position": len(self.transitions) + 1, "from": self.state.value, "to": target.value,
             "detail": detail}
        )
        self.state = target

    def manifest(self) -> dict[str, Any]:
        return {"state": self.state.value, "transitions": self.transitions}


@dataclass(frozen=True, slots=True)
class CompactedContext:
    summary: str | None
    recent_messages: list[dict[str, str]]
    message_ids: list[str]
    compacted_count: int


class ContextCompactor:
    def __init__(self, *, recent_limit: int = 12, max_summary_chars: int = 6000) -> None:
        self.recent_limit = recent_limit
        self.max_summary_chars = max_summary_chars

    def compact(
        self, rows: list[AssistantMessageRow], *, existing_summary: str | None
    ) -> CompactedContext:
        eligible = [
            row for row in rows if row.role in {"user", "assistant"} and row.content
        ]
        older = eligible[:-self.recent_limit]
        recent = eligible[-self.recent_limit :]
        summary_parts = [existing_summary.strip()] if existing_summary else []
        for row in older:
            role = "用户" if row.role == "user" else "Assistant"
            summary_parts.append(f"{role}: {(row.content or '').strip()[:500]}")
        summary = "\n".join(part for part in summary_parts if part)
        if len(summary) > self.max_summary_chars:
            summary = summary[-self.max_summary_chars :]
        return CompactedContext(
            summary=summary or None,
            recent_messages=[
                {"role": row.role, "content": (row.content or "")[:2000]} for row in recent
            ],
            message_ids=[row.message_id for row in recent],
            compacted_count=len(older),
        )
