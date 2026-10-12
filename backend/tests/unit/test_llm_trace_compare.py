from typing import Any

from pydantic import BaseModel

from app.api.schemas import AssistantReplayCandidate
from app.llm.provider import FakeLLMProvider, LLMMessage, LLMResponse, LLMUsage
from app.llm.schemas import AssistantAnswer
from app.llm.trace_compare import compare_candidate

RECORDED_TOOL_RESULTS: list[dict[str, Any]] = [
    {
        "tool_name": "artifact.search",
        "result": {
            "artifacts": [
                {"artifact_id": "art_metrics", "accuracy": 0.8, "labels": ["no", "yes"]}
            ]
        },
    }
]


class MeteredFakeProvider(FakeLLMProvider):
    """Fake provider that reports usage, so summed attempt costs can be asserted."""

    def generate_structured[ResponseT: BaseModel](
        self,
        *,
        messages: list[LLMMessage],
        response_schema: type[ResponseT],
        model: str,
        temperature: float,
        timeout_seconds: int,
        max_output_tokens: int,
    ) -> LLMResponse[ResponseT]:
        response = super().generate_structured(
            messages=messages,
            response_schema=response_schema,
            model=model,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
        )
        attempt = len(self.calls)
        return LLMResponse(
            provider=response.provider,
            model=response.model,
            request_id=response.request_id,
            content=response.content,
            usage=LLMUsage(input_tokens=100 * attempt, output_tokens=10 * attempt),
            finish_reason=response.finish_reason,
            latency_ms=1000 * attempt,
        )


def _valid_answer() -> dict[str, Any]:
    return {
        "summary": "准确率为 0.8。",
        "findings": [
            {
                "text": "准确率为 0.8。",
                "claim_level": 1,
                "citation_ids": ["art_metrics"],
                "limitations": [],
            }
        ],
        "next_actions": [],
        "limitations": [],
    }


def _counting_answer(count: int) -> dict[str, Any]:
    """A draft that states an array length, the failure the acceptance run hit."""
    return {
        "summary": f"评估集共有 {count} 个标签。",
        "findings": [
            {
                "text": f"评估集共 {count} 个标签，准确率为 0.8。",
                "claim_level": 1,
                "citation_ids": ["art_metrics"],
                "limitations": [],
            }
        ],
        "next_actions": [],
        "limitations": [],
    }


def _compare(provider, **overrides):
    arguments = {
        "provider": provider,
        "candidate": AssistantReplayCandidate(label="current", prompt_variant="current"),
        "default_model": "fake-model",
        "question": "模型效果如何？",
        "recorded_tool_results": RECORDED_TOOL_RESULTS,
        "original_answer": AssistantAnswer(summary="原始回答"),
        "timeout_seconds": 10,
        "max_output_tokens": 1000,
    }
    arguments.update(overrides)
    return compare_candidate(**arguments)


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


def test_invalid_candidate_is_corrected_once() -> None:
    provider = MeteredFakeProvider([_counting_answer(3), _valid_answer()])

    result = _compare(provider)

    assert result.citation_valid is True
    assert result.correction_attempted is True
    assert result.validation_error is None
    assert result.answer.summary == "准确率为 0.8。"
    assert len(provider.calls) == 2
    assert provider.calls[1].temperature == 0
    assert provider.calls[1].schema_name == "AssistantAnswer"
    correction_request = provider.calls[1].messages[1].content
    assert "validation_errors" in correction_request
    assert "unsupported numbers" in correction_request
    assert "allowed_citation_ids" in correction_request
    assert "Never compute, sum, or count a value" in correction_request
    # Both attempts are billed: the comparison must not under-report the cost of a retry.
    assert (result.input_tokens, result.output_tokens, result.latency_ms) == (300, 30, 3000)


def test_candidate_stays_invalid_when_correction_also_fails() -> None:
    provider = MeteredFakeProvider([_counting_answer(3), _counting_answer(5)])

    result = _compare(provider)

    assert result.citation_valid is False
    assert result.correction_attempted is True
    assert result.answer.summary == "评估集共有 5 个标签。"
    assert result.validation_error is not None
    assert "初稿：" in result.validation_error
    assert "纠正后仍不合格：" in result.validation_error
    assert result.validation_error.count("unsupported numbers") == 2
    assert len(provider.calls) == 2


def test_valid_candidate_is_not_regenerated() -> None:
    provider = MeteredFakeProvider([_valid_answer()])

    result = _compare(provider)

    assert result.citation_valid is True
    assert result.correction_attempted is False
    assert len(provider.calls) == 1
    assert (result.input_tokens, result.output_tokens, result.latency_ms) == (100, 10, 1000)
