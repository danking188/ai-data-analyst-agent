from __future__ import annotations

from typing import Any

_ALLOWED_TRANSITIONS = {
    "plan": {"execute", "check", "failed"},
    "execute": {"check", "failed"},
    "check": {"summarize", "failed"},
    "summarize": {"complete", "failed"},
    "complete": set(),
    "failed": set(),
}


def replay_agent_trace(
    *,
    manifest: dict[str, Any],
    run_status: str,
    stored_tool_call_count: int,
    tool_statuses: list[str],
) -> dict[str, Any]:
    """Rebuild and verify a persisted Agent trace without re-running side effects."""
    checks: list[dict[str, Any]] = []
    orchestration = manifest.get("orchestration")
    transitions = orchestration.get("transitions") if isinstance(orchestration, dict) else None
    final_state = orchestration.get("state") if isinstance(orchestration, dict) else None

    transition_issues: list[str] = []
    current = "plan"
    if not isinstance(transitions, list):
        transition_issues.append("missing_orchestration_transitions")
        transitions = []
    for expected_position, transition in enumerate(transitions, start=1):
        if not isinstance(transition, dict):
            transition_issues.append(f"transition_{expected_position}_not_an_object")
            continue
        position = transition.get("position")
        source = transition.get("from")
        target = transition.get("to")
        if position != expected_position:
            transition_issues.append(f"transition_{expected_position}_position_mismatch")
        if source != current:
            transition_issues.append(f"transition_{expected_position}_source_mismatch")
        if target not in _ALLOWED_TRANSITIONS.get(str(source), set()):
            transition_issues.append(f"transition_{expected_position}_illegal")
        if isinstance(target, str):
            current = target
    if final_state != current:
        transition_issues.append("final_state_mismatch")
    checks.append(
        {
            "name": "state_transitions",
            "passed": not transition_issues,
            "details": {"issues": transition_issues, "replayed_state": current},
        }
    )

    expected_states = {
        "succeeded": {"complete"},
        "failed": {"failed"},
        "awaiting_confirmation": {"execute"},
        "cancelled": {"plan", "execute", "check", "summarize", "failed"},
        "running": {"plan", "execute", "check", "summarize"},
    }
    allowed_states = expected_states.get(run_status, set())
    status_matches = current in allowed_states if allowed_states else False
    checks.append(
        {
            "name": "run_terminal_state",
            "passed": status_matches,
            "details": {
                "run_status": run_status,
                "replayed_state": current,
                "expected_states": sorted(allowed_states),
            },
        }
    )

    observed_tool_call_count = len(tool_statuses)
    checks.append(
        {
            "name": "tool_call_count",
            "passed": observed_tool_call_count == stored_tool_call_count,
            "details": {
                "stored": stored_tool_call_count,
                "observed": observed_tool_call_count,
            },
        }
    )
    unfinished = [
        status
        for status in tool_statuses
        if status in {"approved", "running"}
        or (run_status == "succeeded" and status == "proposed")
    ]
    checks.append(
        {
            "name": "tool_terminal_states",
            "passed": not unfinished,
            "details": {"unfinished_statuses": unfinished},
        }
    )
    return {
        "verified": all(bool(check["passed"]) for check in checks),
        "replayed_state": current,
        "checks": checks,
    }
