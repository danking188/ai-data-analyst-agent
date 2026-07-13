from __future__ import annotations

import pytest

from app.analysis.spec_validator import validate_analysis_spec
from app.api.schemas import AnalysisSpecCreate
from app.domain.errors import DomainError
from app.persistence.orm.workflow_models import ColumnSchemaRow


def _column(
    name: str,
    *,
    physical_type: str,
    semantic_type: str,
    unique_count: int,
    non_null_count: int = 100,
) -> ColumnSchemaRow:
    return ColumnSchemaRow(
        column_schema_id=f"col_{name}",
        project_id="prj_test",
        dataset_version_id="dsv_test",
        name=name,
        ordinal_position=0,
        physical_type=physical_type,
        semantic_type=semantic_type,
        analysis_role="feature",
        confidence=0.95,
        evidence_json=[],
        profile_json={
            "unique_count": unique_count,
            "non_null_count": non_null_count,
        },
        date_format=None,
        ordinal_values_json=None,
        sensitive=False,
        user_confirmed=False,
        revision=1,
    )


def _binary_spec() -> AnalysisSpecCreate:
    return AnalysisSpecCreate(
        name="Numeric binary target",
        dataset_version_id="dsv_test",
        task="binary_classification",
        target="churned",
        prediction_time_description="Use only fields known before churn",
        split_strategy="stratified",
        metrics=["roc_auc", "f1"],
        included_columns=["feature"],
        excluded_columns=[],
        random_seed=42,
        causal_interpretation_allowed=False,
    )


def test_binary_classification_accepts_two_value_numeric_target() -> None:
    columns = {
        "churned": _column(
            "churned",
            physical_type="integer",
            semantic_type="numeric",
            unique_count=2,
        ),
        "feature": _column(
            "feature",
            physical_type="float",
            semantic_type="numeric",
            unique_count=90,
        ),
    }

    warnings = validate_analysis_spec(_binary_spec(), columns=columns)

    assert warnings == []


def test_binary_classification_rejects_high_cardinality_numeric_target() -> None:
    columns = {
        "churned": _column(
            "churned",
            physical_type="integer",
            semantic_type="numeric",
            unique_count=80,
        ),
        "feature": _column(
            "feature",
            physical_type="float",
            semantic_type="numeric",
            unique_count=90,
        ),
    }

    with pytest.raises(DomainError, match="分类任务 target 必须为离散字段"):
        validate_analysis_spec(_binary_spec(), columns=columns)
