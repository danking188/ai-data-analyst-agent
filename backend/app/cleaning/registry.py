from __future__ import annotations

from collections.abc import Set
from typing import Any

from app.api.schemas import CleaningOperation
from app.domain.errors import validation_error

CAST_TYPES = {"integer", "float", "string", "boolean", "datetime"}
FILTER_OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "is_null", "not_null"}
IMPUTE_METHODS = {"mean", "median", "mode", "constant"}


def validate_cleaning_operations(
    operations: list[CleaningOperation],
    *,
    columns: set[str],
    issue_ids: set[str],
) -> None:
    for operation in operations:
        _validate_operation(operation, columns=columns)
        unknown_issues = sorted(set(operation.issue_ids) - issue_ids)
        if unknown_issues:
            raise validation_error(
                "清洗操作引用了不存在的质量问题",
                operation_id=operation.operation_id,
                issue_ids=unknown_issues,
            )


def _require_column(operation: CleaningOperation, columns: set[str]) -> str:
    if operation.column is None:
        raise validation_error(
            "该清洗操作必须指定字段",
            operation_id=operation.operation_id,
        )
    if operation.column not in columns:
        raise validation_error(
            "清洗操作引用了不存在的字段",
            operation_id=operation.operation_id,
            column=operation.column,
        )
    return operation.column


def _only_parameters(
    operation: CleaningOperation,
    *,
    allowed: set[str],
    required: Set[str] = frozenset(),
) -> dict[str, Any]:
    parameters = operation.parameters
    unknown = sorted(set(parameters) - allowed)
    missing = sorted(required - set(parameters))
    if unknown or missing:
        raise validation_error(
            "清洗操作参数不符合白名单",
            operation_id=operation.operation_id,
            unknown_parameters=unknown,
            missing_parameters=missing,
        )
    return parameters


def _validate_operation(operation: CleaningOperation, *, columns: set[str]) -> None:
    if operation.operation == "impute_missing":
        _require_column(operation, columns)
        parameters = _only_parameters(
            operation,
            allowed={"method", "value"},
            required={"method"},
        )
        method = parameters["method"]
        if method not in IMPUTE_METHODS:
            raise validation_error("不支持的缺失值填补方法", method=method)
        if method == "constant" and "value" not in parameters:
            raise validation_error("constant 填补必须提供 value")
        if method != "constant" and "value" in parameters:
            raise validation_error("只有 constant 填补可以提供 value")
        return

    if operation.operation == "drop_duplicates":
        parameters = _only_parameters(operation, allowed={"columns", "keep"})
        selected = parameters.get("columns")
        if selected is not None:
            if not isinstance(selected, list) or not selected:
                raise validation_error("columns 必须为非空字段数组")
            unknown = sorted(set(selected) - columns)
            if unknown:
                raise validation_error("去重字段不存在", columns=unknown)
        if parameters.get("keep", "first") not in {"first", "last", False}:
            raise validation_error("keep 仅支持 first、last 或 false")
        return

    if operation.operation == "cast_type":
        _require_column(operation, columns)
        parameters = _only_parameters(
            operation,
            allowed={"target_type", "date_format"},
            required={"target_type"},
        )
        if parameters["target_type"] not in CAST_TYPES:
            raise validation_error("不支持的目标类型", target_type=parameters["target_type"])
        return

    if operation.operation in {"replace_values", "normalize_category"}:
        _require_column(operation, columns)
        parameters = _only_parameters(
            operation,
            allowed={"mapping"},
            required={"mapping"},
        )
        if not isinstance(parameters["mapping"], dict) or not parameters["mapping"]:
            raise validation_error("mapping 必须为非空对象")
        return

    if operation.operation == "filter_rows":
        _require_column(operation, columns)
        parameters = _only_parameters(
            operation,
            allowed={"operator", "value"},
            required={"operator"},
        )
        operator = parameters["operator"]
        if operator not in FILTER_OPERATORS:
            raise validation_error("不支持的筛选操作符", operator=operator)
        requires_value = operator not in {"is_null", "not_null"}
        if requires_value != ("value" in parameters):
            raise validation_error("当前筛选操作符的 value 参数不正确")
        if operator in {"in", "not_in"} and not isinstance(parameters.get("value"), list):
            raise validation_error("in/not_in 的 value 必须为数组")
        return

    if operation.operation == "add_missing_indicator":
        column = _require_column(operation, columns)
        parameters = _only_parameters(operation, allowed={"name"})
        name = parameters.get("name", f"{column}_is_missing")
        if not isinstance(name, str) or not name.strip():
            raise validation_error("缺失指示字段名称不能为空")
        if name in columns:
            raise validation_error("缺失指示字段已存在", column=name)
        return

    raise validation_error("不支持的清洗操作", operation=operation.operation)
