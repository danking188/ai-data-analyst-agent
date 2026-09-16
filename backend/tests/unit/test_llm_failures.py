from app.llm.failures import AgentFailureCategory, classify_agent_failure


def test_failure_taxonomy_maps_representative_agent_failures() -> None:
    assert classify_agent_failure("LLM_INVALID_PLAN") == AgentFailureCategory.PLAN
    assert classify_agent_failure("LLM_TOOL_NOT_ALLOWED") == AgentFailureCategory.TOOL_SELECTION
    assert classify_agent_failure("LLM_UNSUPPORTED_ANSWER") == (
        AgentFailureCategory.EVIDENCE_VALIDATION
    )
    assert classify_agent_failure("ASSISTANT_CONFIRMATION_STALE") == (
        AgentFailureCategory.DATA_VERSION_CONFLICT
    )
    assert classify_agent_failure("LLM_TIMEOUT") == AgentFailureCategory.PROVIDER
    assert classify_agent_failure("LLM_DAILY_TOKEN_BUDGET_EXCEEDED") == (
        AgentFailureCategory.POLICY
    )


def test_failure_taxonomy_has_stable_internal_fallback() -> None:
    assert classify_agent_failure("SOMETHING_NEW") == AgentFailureCategory.INTERNAL
