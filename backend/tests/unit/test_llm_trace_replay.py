from __future__ import annotations

from app.llm.trace_replay import replay_agent_trace


def test_trace_replay_accepts_complete_grounded_turn() -> None:
    result = replay_agent_trace(
        manifest={
            "orchestration": {
                "state": "complete",
                "transitions": [
                    {"position": 1, "from": "plan", "to": "execute"},
                    {"position": 2, "from": "execute", "to": "check"},
                    {"position": 3, "from": "check", "to": "summarize"},
                    {"position": 4, "from": "summarize", "to": "complete"},
                ],
            }
        },
        run_status="succeeded",
        stored_tool_call_count=1,
        tool_statuses=["succeeded"],
    )

    assert result["verified"] is True
    assert result["replayed_state"] == "complete"


def test_trace_replay_reports_tampered_transition_and_unfinished_tool() -> None:
    result = replay_agent_trace(
        manifest={
            "orchestration": {
                "state": "complete",
                "transitions": [
                    {"position": 2, "from": "plan", "to": "complete"},
                ],
            }
        },
        run_status="succeeded",
        stored_tool_call_count=2,
        tool_statuses=["running"],
    )

    assert result["verified"] is False
    failed = {check["name"] for check in result["checks"] if not check["passed"]}
    assert failed == {
        "state_transitions",
        "tool_call_count",
        "tool_terminal_states",
    }
