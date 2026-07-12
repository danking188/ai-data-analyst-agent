from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.analysis.tool_registry import profile_eda


def test_target_driven_eda_emits_effect_sizes_and_multiple_test_correction(
    tmp_path: Path,
) -> None:
    frame = pd.DataFrame(
        {
            "signal": list(range(30)),
            "noise": [index % 4 for index in range(30)],
            "segment": ["a", "b", "c"] * 10,
            "target": ["no"] * 15 + ["yes"] * 15,
        }
    )
    path = tmp_path / "eda.parquet"
    frame.to_parquet(path, index=False)
    result = profile_eda(
        {
            "data_path": str(path),
            "data_root": str(tmp_path),
            "dataset_version_id": "dsv_test",
            "analysis_spec": {
                "task": "binary_classification",
                "target": "target",
            },
            "sensitive_columns": [],
            "parameters": {},
        }
    )
    diagnostic = next(
        artifact for artifact in result["artifacts"] if artifact["type"] == "comparison"
    )
    tests = diagnostic["result"]["statistical_tests"]
    assert tests
    assert all("effect_size" in test for test in tests)
    assert all("q_value_bh" in test for test in tests)
    assert diagnostic["result"]["target_diagnostics"]["class_count"] == 2
