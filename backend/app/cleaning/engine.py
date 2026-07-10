from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.api.schemas import CleaningOperation
from app.domain.errors import validation_error


@dataclass(frozen=True, slots=True)
class OperationEffect:
    operation_id: str
    operation: str
    affected_rows: int
    row_count_before: int
    row_count_after: int


@dataclass(frozen=True, slots=True)
class CleaningResult:
    frame: pd.DataFrame
    effects: list[OperationEffect]


def apply_cleaning_operations(
    frame: pd.DataFrame,
    operations: list[CleaningOperation],
) -> CleaningResult:
    current = frame.copy(deep=True)
    effects: list[OperationEffect] = []
    for operation in operations:
        before = len(current)
        current, affected = _apply_operation(current, operation)
        effects.append(
            OperationEffect(
                operation_id=operation.operation_id,
                operation=operation.operation,
                affected_rows=affected,
                row_count_before=before,
                row_count_after=len(current),
            )
        )
    return CleaningResult(frame=current, effects=effects)


def _apply_operation(
    frame: pd.DataFrame,
    operation: CleaningOperation,
) -> tuple[pd.DataFrame, int]:
    column = operation.column
    parameters = operation.parameters
    try:
        if operation.operation == "impute_missing":
            assert column is not None
            mask = frame[column].isna()
            method = parameters["method"]
            if method == "mean":
                value = frame[column].mean()
            elif method == "median":
                value = frame[column].median()
            elif method == "mode":
                modes = frame[column].mode(dropna=True)
                if modes.empty:
                    raise validation_error("字段不存在可用于众数填补的值", column=column)
                value = modes.iloc[0]
            else:
                value = parameters["value"]
            result = frame.copy()
            result.loc[mask, column] = value
            return result, int(mask.sum())

        if operation.operation == "drop_duplicates":
            columns = parameters.get("columns")
            keep = parameters.get("keep", "first")
            duplicate_mask = frame.duplicated(subset=columns, keep=keep)
            return frame.loc[~duplicate_mask].copy(), int(duplicate_mask.sum())

        if operation.operation == "cast_type":
            assert column is not None
            result = frame.copy()
            target = parameters["target_type"]
            if target == "integer":
                result[column] = pd.to_numeric(result[column], errors="raise").astype("Int64")
            elif target == "float":
                result[column] = pd.to_numeric(result[column], errors="raise").astype("Float64")
            elif target == "datetime":
                result[column] = pd.to_datetime(
                    result[column],
                    format=parameters.get("date_format"),
                    errors="raise",
                )
            elif target == "boolean":
                result[column] = result[column].astype("boolean")
            else:
                result[column] = result[column].astype("string")
            return result, int(result[column].notna().sum())

        if operation.operation in {"replace_values", "normalize_category"}:
            assert column is not None
            mapping = parameters["mapping"]
            mask = frame[column].isin(mapping)
            result = frame.copy()
            result[column] = result[column].replace(mapping)
            return result, int(mask.sum())

        if operation.operation == "filter_rows":
            assert column is not None
            keep_mask = _filter_mask(frame[column], parameters["operator"], parameters.get("value"))
            return frame.loc[keep_mask].copy(), int((~keep_mask).sum())

        if operation.operation == "add_missing_indicator":
            assert column is not None
            result = frame.copy()
            name = str(parameters.get("name", f"{column}_is_missing"))
            result[name] = result[column].isna()
            return result, int(result[name].sum())
    except (TypeError, ValueError, KeyError) as exc:
        raise validation_error(
            "清洗操作无法应用到当前数据",
            operation_id=operation.operation_id,
            column=column,
        ) from exc

    raise validation_error("不支持的清洗操作", operation=operation.operation)


def _filter_mask(series: pd.Series[Any], operator: str, value: Any) -> pd.Series[Any]:
    if operator == "eq":
        return series == value
    if operator == "ne":
        return series != value
    if operator == "gt":
        return series > value
    if operator == "gte":
        return series >= value
    if operator == "lt":
        return series < value
    if operator == "lte":
        return series <= value
    if operator == "in":
        return series.isin(value)
    if operator == "not_in":
        return ~series.isin(value)
    if operator == "is_null":
        return series.isna()
    if operator == "not_null":
        return series.notna()
    raise validation_error("不支持的筛选操作符", operator=operator)
