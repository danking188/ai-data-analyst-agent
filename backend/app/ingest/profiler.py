from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import pandas as pd
from pandas.api import types as ptypes

SENSITIVE_NAME = re.compile(
    r"(^|_)(email|phone|mobile|name|address|id_card|identity)(_|$)|邮箱|手机号|姓名|地址|身份证",
    re.IGNORECASE,
)
IDENTIFIER_NAME = re.compile(r"(^|_)(id|code|key|uuid)(_|$)|编号|编码", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ColumnProfile:
    name: str
    position: int
    physical_type: str
    semantic_type: str
    analysis_role: str
    confidence: float
    evidence: list[str]
    sensitive: bool
    profile: dict[str, Any]


def profile_frame(frame: pd.DataFrame) -> list[ColumnProfile]:
    return [
        _profile_series(str(name), position, frame[name])
        for position, name in enumerate(frame.columns)
    ]


def _profile_series(name: str, position: int, series: pd.Series[Any]) -> ColumnProfile:
    non_null = series.dropna()
    row_count = len(series)
    unique_count = int(non_null.nunique(dropna=True))
    unique_ratio = unique_count / len(non_null) if len(non_null) else 0.0
    physical = _physical_type(series)
    sensitive = bool(SENSITIVE_NAME.search(name))
    evidence = [f"pandas_dtype={series.dtype}", f"unique_ratio={unique_ratio:.4f}"]

    if physical == "datetime":
        semantic, role, confidence = "datetime", "time", 0.98
    elif physical == "boolean":
        semantic, role, confidence = "boolean", "feature", 0.98
    elif IDENTIFIER_NAME.search(name) or (unique_ratio >= 0.98 and physical == "string"):
        semantic, role, confidence = "identifier", "identifier", 0.9
        evidence.append("字段名或唯一性符合标识符特征")
    elif physical in {"integer", "float"}:
        semantic, role, confidence = "numeric", "feature", 0.95
    elif unique_count <= min(50, max(2, int(row_count * 0.05))):
        semantic, role, confidence = "categorical", "feature", 0.85
    else:
        semantic, role, confidence = "text", "text", 0.8

    return ColumnProfile(
        name=name,
        position=position,
        physical_type=physical,
        semantic_type=semantic,
        analysis_role=role,
        confidence=confidence,
        evidence=evidence,
        sensitive=sensitive,
        profile={
            "row_count": row_count,
            "non_null_count": int(series.notna().sum()),
            "null_count": int(series.isna().sum()),
            "null_ratio": float(series.isna().mean()) if row_count else 0.0,
            "unique_count": unique_count,
        },
    )


def _physical_type(series: pd.Series[Any]) -> str:
    if ptypes.is_bool_dtype(series.dtype):
        return "boolean"
    if ptypes.is_integer_dtype(series.dtype):
        return "integer"
    if ptypes.is_float_dtype(series.dtype):
        return "float"
    if ptypes.is_datetime64_any_dtype(series.dtype):
        return "datetime"
    if ptypes.is_string_dtype(series.dtype) or ptypes.is_object_dtype(series.dtype):
        return "string"
    return "unknown"
