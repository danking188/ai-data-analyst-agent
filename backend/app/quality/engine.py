from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pandas as pd
from pandas.api.types import is_numeric_dtype

RULE_VERSION = "1.0.0"
SUPPORTED_RULES = frozenset(
    {
        "missing_values",
        "duplicate_rows",
        "constant_column",
        "high_cardinality",
        "outlier_iqr",
        "skewed_distribution",
    }
)


@dataclass(frozen=True, slots=True)
class QualityFinding:
    issue_type: str
    column: str | None
    severity: str
    title: str
    explanation: str
    metrics: dict[str, Any]
    sample_rows: list[dict[str, Any]]
    recommendation: str | None
    rule_name: str
    rule_version: str = RULE_VERSION


def _records(frame: pd.DataFrame, indexes: list[Any], *, limit: int = 5) -> list[dict[str, Any]]:
    if not indexes:
        return []
    sample = frame.loc[indexes[:limit]].copy()
    sample.insert(0, "_row_number", [int(index) + 2 for index in sample.index])
    return list(json.loads(sample.to_json(orient="records", date_format="iso")))


def _ratio_severity(ratio: float) -> str:
    if ratio >= 0.5:
        return "critical"
    if ratio >= 0.2:
        return "high"
    if ratio >= 0.05:
        return "medium"
    return "low"


class QualityEngine:
    def scan(
        self,
        frame: pd.DataFrame,
        *,
        rules: list[str] | None = None,
    ) -> list[QualityFinding]:
        enabled = set(rules or SUPPORTED_RULES)
        findings: list[QualityFinding] = []
        row_count = len(frame)
        if row_count == 0:
            return findings

        if "missing_values" in enabled:
            findings.extend(self._missing_values(frame))
        if "duplicate_rows" in enabled:
            duplicate_mask = frame.duplicated(keep=False)
            count = int(duplicate_mask.sum())
            if count:
                ratio = count / row_count
                findings.append(
                    QualityFinding(
                        issue_type="duplicate_rows",
                        column=None,
                        severity=_ratio_severity(ratio),
                        title="检测到重复行",
                        explanation=f"共有 {count} 行属于重复记录，可能影响统计和建模结果。",
                        metrics={"duplicate_row_count": count, "ratio": ratio},
                        sample_rows=_records(frame, frame.index[duplicate_mask].tolist()),
                        recommendation="确认业务主键后删除或合并重复记录。",
                        rule_name="duplicate_rows",
                    )
                )
        if "constant_column" in enabled:
            for column in frame.columns:
                if int(frame[column].nunique(dropna=True)) <= 1:
                    findings.append(
                        QualityFinding(
                            issue_type="constant_column",
                            column=str(column),
                            severity="medium",
                            title=f"字段 {column} 为常量列",
                            explanation="该字段没有有效区分度，通常不应作为分析特征。",
                            metrics={
                                "distinct_non_null_count": int(frame[column].nunique(dropna=True))
                            },
                            sample_rows=[],
                            recommendation="确认业务含义后从分析特征中排除。",
                            rule_name="constant_column",
                        )
                    )
        if "high_cardinality" in enabled:
            findings.extend(self._high_cardinality(frame))
        if "outlier_iqr" in enabled:
            findings.extend(self._outliers(frame))
        if "skewed_distribution" in enabled:
            findings.extend(self._skewed(frame))
        return findings

    @staticmethod
    def _missing_values(frame: pd.DataFrame) -> list[QualityFinding]:
        findings: list[QualityFinding] = []
        for column in frame.columns:
            mask = frame[column].isna()
            count = int(mask.sum())
            if not count:
                continue
            ratio = count / len(frame)
            findings.append(
                QualityFinding(
                    issue_type="missing_values",
                    column=str(column),
                    severity=_ratio_severity(ratio),
                    title=f"字段 {column} 存在缺失值",
                    explanation=f"共有 {count} 行缺失，占全部记录的 {ratio:.2%}。",
                    metrics={"missing_count": count, "ratio": ratio},
                    sample_rows=_records(frame, frame.index[mask].tolist()),
                    recommendation="结合字段业务含义选择填补、增加缺失指示器或过滤记录。",
                    rule_name="missing_values",
                )
            )
        return findings

    @staticmethod
    def _high_cardinality(frame: pd.DataFrame) -> list[QualityFinding]:
        findings: list[QualityFinding] = []
        for column in frame.select_dtypes(include=["object", "string", "category"]).columns:
            non_null = int(frame[column].notna().sum())
            unique = int(frame[column].nunique(dropna=True))
            ratio = unique / non_null if non_null else 0.0
            if unique < 50 or ratio < 0.9:
                continue
            findings.append(
                QualityFinding(
                    issue_type="high_cardinality",
                    column=str(column),
                    severity="medium",
                    title=f"字段 {column} 基数过高",
                    explanation="该分类字段的大部分取值互不相同，直接编码可能导致维度膨胀。",
                    metrics={"distinct_count": unique, "non_null_count": non_null, "ratio": ratio},
                    sample_rows=[],
                    recommendation="确认该字段是否为标识符，或采用聚合、哈希等编码方式。",
                    rule_name="high_cardinality",
                )
            )
        return findings

    @staticmethod
    def _outliers(frame: pd.DataFrame) -> list[QualityFinding]:
        findings: list[QualityFinding] = []
        for column in frame.columns:
            series = frame[column]
            if not is_numeric_dtype(series.dtype) or int(series.notna().sum()) < 4:
                continue
            q1 = float(series.quantile(0.25))
            q3 = float(series.quantile(0.75))
            iqr = q3 - q1
            if iqr <= 0:
                continue
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            mask = series.notna() & ((series < lower) | (series > upper))
            count = int(mask.sum())
            if not count:
                continue
            ratio = count / len(frame)
            findings.append(
                QualityFinding(
                    issue_type="outlier_iqr",
                    column=str(column),
                    severity=_ratio_severity(ratio),
                    title=f"字段 {column} 存在 IQR 异常值",
                    explanation=f"共有 {count} 个值落在四分位距阈值之外。",
                    metrics={
                        "outlier_count": count,
                        "ratio": ratio,
                        "lower_bound": lower,
                        "upper_bound": upper,
                    },
                    sample_rows=_records(frame, frame.index[mask].tolist()),
                    recommendation="核对异常值来源，必要时截尾、变换或保留并使用稳健方法。",
                    rule_name="outlier_iqr",
                )
            )
        return findings

    @staticmethod
    def _skewed(frame: pd.DataFrame) -> list[QualityFinding]:
        findings: list[QualityFinding] = []
        for column in frame.columns:
            series = frame[column]
            if not is_numeric_dtype(series.dtype) or int(series.notna().sum()) < 8:
                continue
            skewness = float(series.skew())
            if pd.isna(skewness) or abs(skewness) < 2:
                continue
            findings.append(
                QualityFinding(
                    issue_type="skewed_distribution",
                    column=str(column),
                    severity="low",
                    title=f"字段 {column} 分布明显偏斜",
                    explanation=f"样本偏度为 {skewness:.3f}，部分统计或模型可能受影响。",
                    metrics={"skewness": skewness},
                    sample_rows=[],
                    recommendation="根据分析目标考虑对数变换或使用稳健统计方法。",
                    rule_name="skewed_distribution",
                )
            )
        return findings
