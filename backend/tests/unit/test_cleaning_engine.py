from __future__ import annotations

import pandas as pd
import pytest

from app.api.schemas import CleaningOperation
from app.cleaning.engine import apply_cleaning_operations
from app.cleaning.registry import validate_cleaning_operations
from app.domain.errors import DomainError


def operation(
    kind: str,
    *,
    operation_id: str | None = None,
    column: str | None = "value",
    parameters: dict[str, object] | None = None,
) -> CleaningOperation:
    return CleaningOperation.model_validate(
        {
            "operation_id": operation_id or f"op_{kind}",
            "operation": kind,
            "column": column,
            "parameters": parameters or {},
            "reason": "单元测试",
            "issue_ids": [],
            "estimated_affected_rows": 0,
            "risk_level": "low",
            "reversible": True,
        }
    )


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("mean", 5 / 3),
        ("median", 1.0),
        ("mode", 1.0),
        ("constant", 9.0),
    ],
)
def test_impute_methods(method: str, expected: float) -> None:
    frame = pd.DataFrame({"value": [1.0, None, 3.0, 1.0]})
    parameters: dict[str, object] = {"method": method}
    if method == "constant":
        parameters["value"] = 9
    result = apply_cleaning_operations(
        frame,
        [operation("impute_missing", parameters=parameters)],
    )
    assert result.frame.loc[1, "value"] == pytest.approx(expected)
    assert result.effects[0].affected_rows == 1


def test_drop_duplicates_replace_and_indicator() -> None:
    frame = pd.DataFrame(
        {
            "category": [" A ", " A ", None],
            "value": [1, 1, 2],
        }
    )
    operations = [
        operation(
            "normalize_category",
            operation_id="op_normalize",
            column="category",
            parameters={"mapping": {" A ": "A"}},
        ),
        operation(
            "drop_duplicates",
            operation_id="op_deduplicate",
            column=None,
            parameters={"columns": ["category", "value"], "keep": "last"},
        ),
        operation(
            "add_missing_indicator",
            operation_id="op_indicator",
            column="category",
            parameters={"name": "category_missing"},
        ),
        operation(
            "replace_values",
            operation_id="op_replace",
            column="value",
            parameters={"mapping": {"2": 20, 2: 20}},
        ),
    ]
    result = apply_cleaning_operations(frame, operations)
    assert len(result.frame) == 2
    assert result.frame["category_missing"].tolist() == [False, True]
    assert result.frame["value"].tolist() == [1, 20]


@pytest.mark.parametrize(
    ("target_type", "source", "expected"),
    [
        ("integer", ["1", "2"], "Int64"),
        ("float", ["1.5", "2"], "Float64"),
        ("string", [1, 2], "string"),
        ("boolean", [True, False], "boolean"),
        ("datetime", ["2026-01-01", "2026-01-02"], "datetime64[ns]"),
    ],
)
def test_cast_types(target_type: str, source: list[object], expected: str) -> None:
    parameters: dict[str, object] = {"target_type": target_type}
    if target_type == "datetime":
        parameters["date_format"] = "%Y-%m-%d"
    result = apply_cleaning_operations(
        pd.DataFrame({"value": source}),
        [operation("cast_type", parameters=parameters)],
    )
    assert str(result.frame["value"].dtype) == expected


@pytest.mark.parametrize(
    ("operator", "value", "expected"),
    [
        ("eq", 2, [2]),
        ("ne", 2, [1, 3]),
        ("gt", 1, [2, 3]),
        ("gte", 2, [2, 3]),
        ("lt", 3, [1, 2]),
        ("lte", 2, [1, 2]),
        ("in", [1, 3], [1, 3]),
        ("not_in", [2], [1, 3]),
        ("is_null", None, []),
        ("not_null", None, [1, 2, 3]),
    ],
)
def test_filter_operators(
    operator: str,
    value: object,
    expected: list[int],
) -> None:
    parameters: dict[str, object] = {"operator": operator}
    if operator not in {"is_null", "not_null"}:
        parameters["value"] = value
    result = apply_cleaning_operations(
        pd.DataFrame({"value": [1, 2, 3]}),
        [operation("filter_rows", parameters=parameters)],
    )
    assert result.frame["value"].tolist() == expected


def test_engine_reports_unapplicable_operations() -> None:
    with pytest.raises(DomainError) as cast_error:
        apply_cleaning_operations(
            pd.DataFrame({"value": ["not-a-number"]}),
            [operation("cast_type", parameters={"target_type": "integer"})],
        )
    assert cast_error.value.code == "VALIDATION_ERROR"

    with pytest.raises(DomainError) as mode_error:
        apply_cleaning_operations(
            pd.DataFrame({"value": [None, None]}),
            [operation("impute_missing", parameters={"method": "mode"})],
        )
    assert mode_error.value.code == "VALIDATION_ERROR"


def test_registry_accepts_whitelist_and_rejects_unsafe_parameters() -> None:
    valid = [
        operation("impute_missing", parameters={"method": "mean"}),
        operation(
            "drop_duplicates",
            operation_id="op_drop",
            column=None,
            parameters={"columns": ["value"], "keep": False},
        ),
        operation(
            "cast_type",
            operation_id="op_cast",
            parameters={"target_type": "float"},
        ),
        operation(
            "replace_values",
            operation_id="op_replace",
            parameters={"mapping": {1: 2}},
        ),
        operation(
            "normalize_category",
            operation_id="op_normalize",
            parameters={"mapping": {" a ": "a"}},
        ),
        operation(
            "filter_rows",
            operation_id="op_filter",
            parameters={"operator": "in", "value": [1]},
        ),
        operation(
            "add_missing_indicator",
            operation_id="op_indicator",
            parameters={"name": "value_missing"},
        ),
    ]
    validate_cleaning_operations(
        valid,
        columns={"value"},
        issue_ids=set(),
    )

    invalid_cases = [
        operation("impute_missing", parameters={"method": "unknown"}),
        operation(
            "drop_duplicates",
            column=None,
            parameters={"columns": ["missing"]},
        ),
        operation("cast_type", parameters={"target_type": "object"}),
        operation("replace_values", parameters={"mapping": {}}),
        operation("filter_rows", parameters={"operator": "eval", "value": "x"}),
        operation("add_missing_indicator", parameters={"name": "value"}),
        operation("impute_missing", parameters={"method": "mean", "eval": "unsafe"}),
    ]
    for invalid in invalid_cases:
        with pytest.raises(DomainError):
            validate_cleaning_operations(
                [invalid],
                columns={"value"},
                issue_ids=set(),
            )


def test_registry_validates_columns_issues_and_parameter_shapes() -> None:
    with pytest.raises(DomainError):
        validate_cleaning_operations(
            [operation("impute_missing", column=None, parameters={"method": "mean"})],
            columns={"value"},
            issue_ids=set(),
        )
    with pytest.raises(DomainError):
        validate_cleaning_operations(
            [operation("impute_missing", column="missing", parameters={"method": "mean"})],
            columns={"value"},
            issue_ids=set(),
        )
    with pytest.raises(DomainError):
        validate_cleaning_operations(
            [
                CleaningOperation(
                    **{
                        **operation(
                            "impute_missing",
                            parameters={"method": "constant", "value": 0},
                        ).model_dump(),
                        "issue_ids": ["issue_missing"],
                    }
                )
            ],
            columns={"value"},
            issue_ids=set(),
        )
    with pytest.raises(DomainError):
        validate_cleaning_operations(
            [
                operation(
                    "filter_rows",
                    parameters={"operator": "in", "value": "not-an-array"},
                )
            ],
            columns={"value"},
            issue_ids=set(),
        )
