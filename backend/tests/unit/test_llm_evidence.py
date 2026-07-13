from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.llm.citations import CitationValidationError, validate_evidence_answer
from app.llm.context import build_evidence_context
from app.llm.narrative import generate_evidence_narrative
from app.llm.provider import FakeLLMProvider
from app.llm.schemas import AssistantAnswer


def evidence_context(*, max_chars: int = 20_000):
    return build_evidence_context(
        project_id="prj_test",
        run_id="run_test",
        dataset_version_id="dsv_test",
        causal_interpretation_allowed=False,
        claims=[
            {
                "claim_id": "claim_accuracy",
                "text": "保留集准确率为 0.8123。",
                "level": 2,
                "evidence_ids": ["art_metric"],
                "limitations": ["仅适用于当前数据版本"],
            }
        ],
        artifacts=[
            {
                "artifact_id": "art_metric",
                "artifact_type": "metric",
                "name": "保留集评估指标",
                "producer": "model.train_compare",
                "producer_version": "2.0.0",
                "checksum": "sha256:test",
                "result": {"metrics": {"accuracy": 0.8123}},
            }
        ],
        max_chars=max_chars,
    )


def valid_answer() -> AssistantAnswer:
    return AssistantAnswer.model_validate(
        {
            "summary": "当前模型已有可验证的保留集表现。",
            "findings": [
                {
                    "text": "保留集准确率为 0.8123。",
                    "claim_level": 2,
                    "citation_ids": ["art_metric"],
                    "limitations": ["仅适用于当前数据版本"],
                }
            ],
            "next_actions": [],
            "limitations": ["不能解释为因果关系"],
        }
    )


def test_context_manifest_contains_only_resource_identity() -> None:
    context = evidence_context()

    assert context.manifest() == {
        "project_id": "prj_test",
        "run_id": "run_test",
        "dataset_version_id": "dsv_test",
        "claim_ids": ["claim_accuracy"],
        "artifact_ids": ["art_metric"],
        "artifact_checksums": {"art_metric": "sha256:test"},
    }
    assert "LLM_API_KEY" not in context.prompt_json()


def test_context_compacts_artifact_results_to_fit_budget() -> None:
    context = build_evidence_context(
        project_id="prj_test",
        run_id="run_test",
        dataset_version_id="dsv_test",
        causal_interpretation_allowed=False,
        claims=[],
        artifacts=[
            {
                "artifact_id": "art_large",
                "artifact_type": "table",
                "name": "Large",
                "producer": "test",
                "producer_version": "1",
                "checksum": "sha256:test",
                "result": {"values": ["x" * 900 for _ in range(20)]},
            }
        ],
        max_chars=700,
    )

    assert context.artifacts[0].result == {"omitted": "context_budget"}
    assert len(context.prompt_json()) <= 700


def test_valid_evidence_answer_passes() -> None:
    validate_evidence_answer(valid_answer(), evidence_context())


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"citation_ids": ["art_unknown"]}, "unknown evidence"),
        ({"text": "保留集准确率为 0.999。"}, "unsupported numbers"),
        ({"text": "该特征导致准确率达到 0.8123。"}, "causal language"),
        ({"citation_ids": []}, "no evidence citation"),
    ],
)
def test_invalid_finding_is_rejected(change: dict[str, object], message: str) -> None:
    answer = valid_answer()
    finding = answer.findings[0].model_copy(update=change)
    changed = answer.model_copy(update={"findings": [finding]})

    with pytest.raises(CitationValidationError, match=message):
        validate_evidence_answer(changed, evidence_context())


def test_summary_number_must_be_established_by_a_finding() -> None:
    answer = valid_answer().model_copy(update={"summary": "准确率达到 0.9。"})

    with pytest.raises(CitationValidationError, match="summary contains numbers"):
        validate_evidence_answer(answer, evidence_context())


def test_narrative_generation_validates_fake_provider_output() -> None:
    provider = FakeLLMProvider([valid_answer().model_dump(mode="json")])

    response = generate_evidence_narrative(
        provider=provider,
        context=evidence_context(),
        model="fake-analysis",
        temperature=0.1,
        timeout_seconds=30,
        max_output_tokens=1000,
    )

    assert response.content.findings[0].citation_ids == ["art_metric"]
    assert "claim_accuracy" in provider.calls[0].messages[1].content


def test_evidence_narrative_eval_baseline_has_required_coverage() -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "llm_eval" / "evidence_narrative_cases.json"
    cases = json.loads(fixture.read_text(encoding="utf-8"))

    assert len(cases) >= 30
    assert {case["category"] for case in cases} >= {
        "eda",
        "classification",
        "regression",
        "quality",
        "safety",
    }
    assert sum(case["category"] == "planning" for case in cases) >= 10
    assert len({case["id"] for case in cases}) == len(cases)
    assert all(case["question"] and case["expected_behavior"] for case in cases)
