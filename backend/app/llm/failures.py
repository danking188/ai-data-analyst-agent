from __future__ import annotations

from enum import StrEnum


class AgentFailureCategory(StrEnum):
    """Stable failure taxonomy used by traces, evaluation, and operations."""

    INTENT_ROUTING = "intent_routing"
    PLAN = "plan"
    TOOL_SELECTION = "tool_selection"
    TOOL_ARGUMENT = "tool_argument"
    TOOL_EXECUTION = "tool_execution"
    DATA_VERSION_CONFLICT = "data_version_conflict"
    EVIDENCE_VALIDATION = "evidence_validation"
    CONTEXT = "context"
    PROVIDER = "provider"
    POLICY = "policy"
    USER_DECISION = "user_decision"
    CANCELLATION = "cancellation"
    INTERNAL = "internal"


_EXACT_CATEGORIES = {
    "ASSISTANT_CONFIRMATION_STALE": AgentFailureCategory.DATA_VERSION_CONFLICT,
    "ASSISTANT_DATASET_REQUIRED": AgentFailureCategory.CONTEXT,
    "DATASET_VERSION_REQUIRED": AgentFailureCategory.CONTEXT,
    "JOB_CANCELLED": AgentFailureCategory.CANCELLATION,
    "LLM_CONTEXT_TOO_LARGE": AgentFailureCategory.CONTEXT,
    "LLM_INVALID_PLAN": AgentFailureCategory.PLAN,
    "LLM_INVALID_STATE_TRANSITION": AgentFailureCategory.PLAN,
    "LLM_STEP_LIMIT_EXCEEDED": AgentFailureCategory.PLAN,
    "LLM_TOOL_NOT_ALLOWED": AgentFailureCategory.TOOL_SELECTION,
    "LLM_UNSUPPORTED_ANSWER": AgentFailureCategory.EVIDENCE_VALIDATION,
}


def classify_agent_failure(code: str) -> AgentFailureCategory:
    """Map stable domain/provider error codes to a compact diagnostic category."""

    exact = _EXACT_CATEGORIES.get(code)
    if exact is not None:
        return exact
    if code.startswith(("LLM_TIMEOUT", "LLM_NETWORK", "LLM_PROVIDER", "LLM_RATE_")):
        return AgentFailureCategory.PROVIDER
    if code.startswith(("LLM_AUTHENTICATION", "LLM_REQUEST", "LLM_INVALID_RESPONSE")):
        return AgentFailureCategory.PROVIDER
    if code.startswith(
        ("LLM_BUDGET", "LLM_DAILY_TOKEN_BUDGET", "LLM_TOOL_BUDGET", "LLM_PROJECT_CONCURRENCY")
    ):
        return AgentFailureCategory.POLICY
    if code.startswith("LLM_ACTION_DEPENDENCY"):
        return AgentFailureCategory.TOOL_ARGUMENT
    if code.startswith(("VALIDATION", "INVALID_ARGUMENT")):
        return AgentFailureCategory.TOOL_ARGUMENT
    if code.startswith(("DATASET_VERSION", "VERSION_CONFLICT")):
        return AgentFailureCategory.DATA_VERSION_CONFLICT
    if code.startswith(("LLM_EVIDENCE", "CITATION")):
        return AgentFailureCategory.EVIDENCE_VALIDATION
    if code.startswith(("PERMISSION", "FORBIDDEN", "AUTHORIZATION")):
        return AgentFailureCategory.POLICY
    if code.startswith(("ASSISTANT_CHILD_JOB", "TOOL_")):
        return AgentFailureCategory.TOOL_EXECUTION
    return AgentFailureCategory.INTERNAL
