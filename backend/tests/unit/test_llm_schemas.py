from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.llm.action_schemas import AnalysisSpecDraft
from app.llm.prompts import get_prompt
from app.llm.schemas import AssistantAnswer, AssistantPlan


def test_prompt_registry_returns_versioned_evidence_boundary() -> None:
    prompt = get_prompt("assistant.answer", "1.0.0")

    assert prompt.identifier == "assistant.answer@1.0.0"
    assert "Never invent metrics" in prompt.system
    assert "untrusted data" in prompt.system


def test_unknown_prompt_is_rejected() -> None:
    with pytest.raises(KeyError, match="unknown prompt"):
        get_prompt("assistant.unknown", "1.0.0")


def test_plan_requires_contiguous_step_positions() -> None:
    with pytest.raises(ValidationError, match="contiguous"):
        AssistantPlan.model_validate(
            {
                "objective": "Analyze sales",
                "dataset_version_id": "ver_1",
                "steps": [
                    {
                        "position": 2,
                        "title": "Inspect schema",
                        "tool_name": "schema.get@1",
                        "purpose": "Understand columns",
                        "requires_confirmation": False,
                    }
                ],
                "estimated_model_calls": 1,
                "estimated_tool_calls": 1,
                "limitations": [],
            }
        )


def test_answer_rejects_unexpected_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        AssistantAnswer.model_validate(
            {
                "summary": "Evidence summary",
                "findings": [],
                "next_actions": [],
                "limitations": [],
                "invented_metric": 99,
            }
        )


def test_analysis_spec_draft_normalizes_common_model_metric_aliases() -> None:
    draft = AnalysisSpecDraft.model_validate(
        {
            "name": "Churn",
            "task": "binary_classification",
            "target": "churned",
            "split_strategy": "stratified",
            "metrics": ["f1_score", "AUC", "precision_recall_auc"],
            "included_columns": ["tenure_months"],
            "excluded_columns": [],
            "rationale": "Predict churn",
        }
    )
    assert draft.metrics == ["f1", "roc_auc", "pr_auc"]
