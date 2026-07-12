from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from app.analysis.modeling import train_and_compare
from app.domain.errors import DomainError


def _context(path: Path, spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "data_path": str(path),
        "data_root": str(path.parent),
        "project_id": "prj_test",
        "run_id": "run_test",
        "dataset_version_id": "dsv_test",
        "analysis_spec": {
            "spec_id": "spec_test",
            "revision": 1,
            "excluded_columns": [],
            **spec,
        },
        "random_seed": 17,
        "parameters": {},
    }


def test_classification_trains_real_candidates_and_serializes_pipeline(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        {
            "amount": list(range(1, 41)),
            "segment": ["a", "b", "c", "a"] * 10,
            "target": ["no"] * 20 + ["yes"] * 20,
        }
    )
    path = tmp_path / "classification.parquet"
    frame.to_parquet(path, index=False)
    result = train_and_compare(
        _context(
            path,
            {
                "task": "binary_classification",
                "target": "target",
                "split_strategy": "stratified",
                "metrics": ["f1", "roc_auc", "pr_auc"],
                "included_columns": ["amount", "segment"],
            },
        )
    )
    model = next(item for item in result["artifacts"] if item["type"] == "model")
    assert model["result"]["model_family"] != "dummy"
    assert model["result"]["leakage_controls"]["test_used_for_selection"] is False
    assert len(model["result"]["candidate_results"]) == 3
    metric = next(item for item in result["artifacts"] if item["type"] == "metric")
    assert metric["result"]["metrics"]["roc_auc"] is not None
    assert result["files"][0]["content"]


def test_regression_group_split_keeps_groups_out_of_holdout(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        {
            "feature": list(range(60)),
            "category": ["x", "y", "z"] * 20,
            "account": [f"g{index // 5}" for index in range(60)],
            "target": [float(index * 2 + (index % 3)) for index in range(60)],
        }
    )
    path = tmp_path / "regression.parquet"
    frame.to_parquet(path, index=False)
    result = train_and_compare(
        _context(
            path,
            {
                "task": "regression",
                "target": "target",
                "split_strategy": "group",
                "group_column": "account",
                "metrics": ["rmse", "mae", "r2"],
                "included_columns": ["feature", "category"],
            },
        )
    )
    model = next(item for item in result["artifacts"] if item["type"] == "model")
    assert model["result"]["split"]["group_overlap"] == 0
    assert model["result"]["model_family"] in {"ridge", "hist_gradient_boosting"}
    metric = next(item for item in result["artifacts"] if item["type"] == "metric")
    assert metric["result"]["metrics"]["rmse"] >= 0


def test_exact_target_copy_is_blocked_as_leakage(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        {
            "leaked_answer": ["no", "yes"] * 10,
            "target": ["no", "yes"] * 10,
        }
    )
    path = tmp_path / "leakage.parquet"
    frame.to_parquet(path, index=False)
    with pytest.raises(DomainError, match="数据泄露"):
        train_and_compare(
            _context(
                path,
                {
                    "task": "binary_classification",
                    "target": "target",
                    "split_strategy": "stratified",
                    "metrics": ["f1"],
                    "included_columns": ["leaked_answer"],
                },
            )
        )
