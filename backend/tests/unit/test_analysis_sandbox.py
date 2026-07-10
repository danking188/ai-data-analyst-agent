from __future__ import annotations

import pytest

from app.analysis.sandbox import validate_safe_expression, validate_tool_context
from app.domain.errors import DomainError


def test_tool_context_rejects_paths_outside_data_root(tmp_path) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    outside = tmp_path / "outside.parquet"
    outside.write_text("not parquet")
    with pytest.raises(DomainError) as raised:
        validate_tool_context({"data_root": str(data_root), "data_path": str(outside)})
    assert raised.value.code == "STATE_CONFLICT"


def test_tool_context_rejects_code_and_network_parameters(tmp_path) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    data_path = data_root / "data.parquet"
    data_path.write_text("not parquet")
    with pytest.raises(DomainError) as raised:
        validate_tool_context(
            {
                "data_root": str(data_root),
                "data_path": str(data_path),
                "parameters": {"python_expression": "__import__('os')"},
            }
        )
    assert raised.value.code == "VALIDATION_ERROR"
    with pytest.raises(DomainError):
        validate_tool_context(
            {
                "data_root": str(data_root),
                "data_path": str(data_path),
                "parameters": {"endpoint": "https://example.com"},
            }
        )


def test_ast_expression_validator_allows_safe_comparisons_and_rejects_calls() -> None:
    validate_safe_expression("age >= 18 and score < 100")
    with pytest.raises(DomainError) as raised:
        validate_safe_expression("__import__('os').system('whoami')")
    assert raised.value.code == "VALIDATION_ERROR"
    assert raised.value.details["node_type"] in {"Call", "Attribute"}
