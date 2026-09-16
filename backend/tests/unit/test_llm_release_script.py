from scripts.evaluate_llm_release import _compact_tool_calls


def test_live_report_compacts_tool_results_but_keeps_gate_fields() -> None:
    compacted = _compact_tool_calls(
        [
            {
                "tool_call_id": "tool_1",
                "tool_name": "artifact.search",
                "status": "succeeded",
                "requires_confirmation": False,
                "arguments": {"query": "metric"},
                "result": {
                    "resource_type": "artifact",
                    "resource_id": "art_1",
                    "status": "ready",
                    "items": [{"large": "payload"}],
                },
            }
        ]
    )

    assert compacted == [
        {
            "tool_call_id": "tool_1",
            "tool_name": "artifact.search",
            "status": "succeeded",
            "requires_confirmation": False,
            "arguments": {"query": "metric"},
            "result_resource": {
                "resource_type": "artifact",
                "resource_id": "art_1",
                "status": "ready",
            },
        }
    ]
