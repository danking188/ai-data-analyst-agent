from app.api.schemas import AssistantReplayCandidate
from app.llm.provider import FakeLLMProvider
from app.llm.schemas import AssistantAnswer
from app.llm.trace_compare import compare_candidate


def test_counterfactual_replay_uses_recorded_tools_without_executing_them() -> None:
    provider = FakeLLMProvider(
        [
            {
                "summary": "准确率为 0.8。",
                "findings": [
                    {
                        "text": "准确率为 0.8。",
                        "claim_level": 1,
                        "citation_ids": ["art_1"],
                        "limitations": [],
                    }
                ],
                "next_actions": [],
                "limitations": [],
            }
        ]
    )
    result = compare_candidate(
        provider=provider,
        candidate=AssistantReplayCandidate(label="auditor", prompt_variant="evidence_auditor"),
        default_model="fake-model",
        question="模型效果如何？",
        recorded_tool_results=[
            {
                "tool_name": "artifact.search",
                "result": {"artifacts": [{"artifact_id": "art_1", "accuracy": 0.8}]},
            }
        ],
        original_answer=AssistantAnswer(summary="原始回答"),
        timeout_seconds=10,
        max_output_tokens=1000,
    )
    assert result.citation_valid is True
    assert result.model == "fake-model"
    assert len(provider.calls) == 1
    assert "recorded_tool_results" in provider.calls[0].messages[1].content
