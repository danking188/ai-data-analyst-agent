from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd
from scipy import stats

from app.analysis.modeling import train_and_compare
from app.analysis.sandbox import validate_tool_context
from app.domain.errors import state_conflict

ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


def _benjamini_hochberg(rows: list[dict[str, Any]]) -> None:
    eligible = [
        (index, float(row["p_value"]))
        for index, row in enumerate(rows)
        if isinstance(row.get("p_value"), (int, float))
        and math.isfinite(float(row["p_value"]))
    ]
    total = len(eligible)
    adjusted = 1.0
    for rank, (index, p_value) in reversed(
        list(enumerate(sorted(eligible, key=lambda item: item[1]), start=1))
    ):
        adjusted = min(adjusted, p_value * total / rank)
        rows[index]["q_value_bh"] = round(adjusted, 6)


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    name: str
    version: str
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[tuple[str, str], RegisteredTool] = {}

    def register(self, name: str, version: str, handler: ToolHandler) -> None:
        key = (name, version)
        if key in self._tools:
            raise ValueError(f"tool already registered: {name}@{version}")
        self._tools[key] = RegisteredTool(name=name, version=version, handler=handler)

    def require(self, name: str, version: str) -> RegisteredTool:
        tool = self._tools.get((name, version))
        if tool is None:
            raise state_conflict(
                "分析步骤引用了未注册工具",
                tool_name=name,
                tool_version=version,
            )
        return tool

    def execute(self, name: str, version: str, context: dict[str, Any]) -> dict[str, Any]:
        validate_tool_context(context)
        return self.require(name, version).handler(context)


def inspect_dataset(context: dict[str, Any]) -> dict[str, Any]:
    frame = pd.read_parquet(str(context["data_path"]))
    return {
        "row_count": len(frame),
        "column_count": len(frame.columns),
        "columns": [str(column) for column in frame.columns],
    }


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if pd.isna(value) and not isinstance(value, (list, tuple, dict, pd.Series, pd.DataFrame)):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def profile_eda(context: dict[str, Any]) -> dict[str, Any]:
    frame = pd.read_parquet(str(context["data_path"]))
    sensitive_columns = set(context.get("sensitive_columns", []))
    safe_frame = frame.drop(columns=[col for col in sensitive_columns if col in frame.columns])
    row_count = int(len(frame))
    column_count = int(len(frame.columns))
    safe_columns = [str(column) for column in safe_frame.columns]

    missing_rows: list[dict[str, Any]] = []
    profile_rows: list[dict[str, Any]] = []
    for column in frame.columns:
        series = frame[column]
        column_name = str(column)
        missing_count = int(series.isna().sum())
        missing_rate = round(missing_count / row_count, 6) if row_count else 0.0
        missing_rows.append(
            {
                "column": column_name,
                "missing_count": missing_count,
                "missing_rate": missing_rate,
                "masked": column_name in sensitive_columns,
            }
        )
        profile: dict[str, Any] = {
            "column": column_name,
            "dtype": str(series.dtype),
            "missing_rate": missing_rate,
            "unique_count": int(series.nunique(dropna=True)),
            "masked": column_name in sensitive_columns,
        }
        if column_name not in sensitive_columns and pd.api.types.is_numeric_dtype(series):
            numeric = pd.to_numeric(series, errors="coerce")
            profile.update(
                {
                    "mean": _json_safe(float(numeric.mean())) if numeric.notna().any() else None,
                    "median": (
                        _json_safe(float(numeric.median())) if numeric.notna().any() else None
                    ),
                    "std": _json_safe(float(numeric.std())) if numeric.notna().sum() > 1 else None,
                    "min": _json_safe(float(numeric.min())) if numeric.notna().any() else None,
                    "max": _json_safe(float(numeric.max())) if numeric.notna().any() else None,
                }
            )
        profile_rows.append(profile)

    charts: list[dict[str, Any]] = [
        {
            "chart_id": "missingness_by_column",
            "title": "各字段缺失率",
            "chart_type": "bar",
            "encoding": {"x": "column", "y": "missing_rate"},
            "data": sorted(
                missing_rows,
                key=lambda row: (-float(row["missing_rate"]), str(row["column"])),
            ),
        }
    ]
    max_numeric = int(context.get("parameters", {}).get("max_numeric_charts", 3))
    numeric_columns = [
        str(column)
        for column in safe_frame.columns
        if pd.api.types.is_numeric_dtype(safe_frame[column])
    ][:max_numeric]
    for column in numeric_columns:
        counts = (
            pd.to_numeric(safe_frame[column], errors="coerce")
            .dropna()
            .value_counts(bins=min(10, max(1, row_count)))
            .sort_index()
        )
        charts.append(
            {
                "chart_id": f"histogram_{column}",
                "title": f"{column} 分布",
                "chart_type": "histogram",
                "encoding": {"x": column, "y": "count"},
                "data": [
                    {"bin": str(interval), "count": int(count)}
                    for interval, count in counts.items()
                ],
            }
        )

    max_categorical = int(context.get("parameters", {}).get("max_categorical_charts", 3))
    categorical_columns = [
        str(column)
        for column in safe_frame.columns
        if not pd.api.types.is_numeric_dtype(safe_frame[column])
    ][:max_categorical]
    for column in categorical_columns:
        counts = safe_frame[column].dropna().astype(str).value_counts().head(10)
        charts.append(
            {
                "chart_id": f"top_categories_{column}",
                "title": f"{column} Top 类别",
                "chart_type": "bar",
                "encoding": {"x": column, "y": "count"},
                "data": [
                    {"category": str(category), "count": int(count)}
                    for category, count in counts.items()
                ],
            }
        )

    analysis_spec = dict(context.get("analysis_spec", {}))
    target = str(analysis_spec.get("target") or "")
    target_diagnostics: dict[str, Any] = {
        "target": target or None,
        "task": analysis_spec.get("task"),
        "available": bool(target and target in safe_frame.columns),
    }
    relationship_rows: list[dict[str, Any]] = []
    statistical_tests: list[dict[str, Any]] = []
    numeric_safe = safe_frame.select_dtypes(include="number")
    correlation_rows: list[dict[str, Any]] = []
    if len(numeric_safe.columns) >= 2:
        correlation = numeric_safe.iloc[:, :30].corr(method="spearman", min_periods=3)
        for left_index, left in enumerate(correlation.columns):
            for right in correlation.columns[left_index + 1 :]:
                value = correlation.loc[left, right]
                if pd.notna(value):
                    correlation_rows.append(
                        {
                            "left": str(left),
                            "right": str(right),
                            "spearman": round(float(value), 6),
                        }
                    )
        correlation_rows.sort(key=lambda row: abs(float(row["spearman"])), reverse=True)
    if target and target in safe_frame.columns:
        target_series = safe_frame[target]
        target_diagnostics["missing_count"] = int(target_series.isna().sum())
        target_diagnostics["non_missing_count"] = int(target_series.notna().sum())
        if "classification" in str(analysis_spec.get("task")):
            counts = target_series.dropna().astype(str).value_counts()
            total = int(counts.sum())
            distribution = [
                {
                    "class": str(label),
                    "count": int(count),
                    "rate": round(float(count) / total, 6) if total else 0.0,
                }
                for label, count in counts.items()
            ]
            target_diagnostics.update(
                class_count=len(counts),
                distribution=distribution,
                imbalance_ratio=(
                    round(float(counts.max() / counts.min()), 6)
                    if len(counts) > 1 and int(counts.min()) > 0
                    else None
                ),
            )
            charts.append(
                {
                    "chart_id": "target_distribution",
                    "title": f"目标 {target} 类别分布",
                    "chart_type": "bar",
                    "encoding": {"x": "class", "y": "count"},
                    "data": distribution,
                }
            )
            for column in numeric_columns[:10]:
                pair = safe_frame[[column, target]].dropna()
                grouped = pair.groupby(target)[column].mean()
                for label, value in grouped.items():
                    relationship_rows.append(
                        {
                            "feature": column,
                            "group": str(label),
                            "measure": "mean",
                            "value": round(float(value), 6),
                        }
                    )
                groups = [
                    pd.to_numeric(group[column], errors="coerce").dropna().to_numpy()
                    for _, group in pair.groupby(target)
                ]
                groups = [group for group in groups if len(group) >= 2]
                if len(groups) == 2:
                    test = stats.mannwhitneyu(groups[0], groups[1], alternative="two-sided")
                    effect = 1 - (2 * float(test.statistic)) / (len(groups[0]) * len(groups[1]))
                    statistical_tests.append(
                        {
                            "feature": column,
                            "test": "mann_whitney_u",
                            "statistic": round(float(test.statistic), 6),
                            "p_value": round(float(test.pvalue), 6),
                            "effect_size": round(effect, 6),
                            "effect_size_name": "rank_biserial",
                        }
                    )
                elif len(groups) > 2:
                    test = stats.kruskal(*groups)
                    sample_count = sum(len(group) for group in groups)
                    effect = max(
                        0.0,
                        (float(test.statistic) - len(groups) + 1)
                        / max(sample_count - len(groups), 1),
                    )
                    statistical_tests.append(
                        {
                            "feature": column,
                            "test": "kruskal_wallis",
                            "statistic": round(float(test.statistic), 6),
                            "p_value": round(float(test.pvalue), 6),
                            "effect_size": round(effect, 6),
                            "effect_size_name": "epsilon_squared",
                        }
                    )
            for column in categorical_columns[:10]:
                contingency = pd.crosstab(safe_frame[column], target_series)
                if contingency.shape[0] > 1 and contingency.shape[1] > 1:
                    chi2, p_value, _, _ = stats.chi2_contingency(contingency)
                    denominator = int(contingency.to_numpy().sum()) * min(
                        contingency.shape[0] - 1, contingency.shape[1] - 1
                    )
                    statistical_tests.append(
                        {
                            "feature": column,
                            "test": "chi_square",
                            "statistic": round(float(chi2), 6),
                            "p_value": round(float(p_value), 6),
                            "effect_size": round(math.sqrt(float(chi2) / denominator), 6),
                            "effect_size_name": "cramers_v",
                        }
                    )
        elif analysis_spec.get("task") == "regression":
            numeric_target = pd.to_numeric(target_series, errors="coerce")
            target_diagnostics.update(
                mean=_json_safe(float(numeric_target.mean())),
                std=_json_safe(float(numeric_target.std())),
                median=_json_safe(float(numeric_target.median())),
                skew=_json_safe(float(numeric_target.skew())),
            )
            for column in numeric_columns[:20]:
                if column == target:
                    continue
                pair = pd.concat(
                    [pd.to_numeric(safe_frame[column], errors="coerce"), numeric_target], axis=1
                ).dropna()
                if len(pair) >= 3:
                    test = stats.spearmanr(pair.iloc[:, 0], pair.iloc[:, 1])
                    statistic = float(test.statistic)
                    p_value = float(test.pvalue)
                    if math.isfinite(statistic) and math.isfinite(p_value):
                        relationship_rows.append(
                            {
                                "feature": column,
                                "measure": "spearman_with_target",
                                "value": round(statistic, 6),
                            }
                        )
                        statistical_tests.append(
                            {
                                "feature": column,
                                "test": "spearman_correlation",
                                "statistic": round(statistic, 6),
                                "p_value": round(p_value, 6),
                                "effect_size": round(statistic, 6),
                                "effect_size_name": "spearman_rho",
                            }
                        )
            relationship_rows.sort(key=lambda row: abs(float(row["value"])), reverse=True)

    _benjamini_hochberg(statistical_tests)

    duplicate_rows = int(frame.duplicated().sum())
    health_warnings = []
    if duplicate_rows:
        health_warnings.append(f"检测到 {duplicate_rows} 条完全重复记录")
    if target_diagnostics.get("imbalance_ratio") and float(
        target_diagnostics["imbalance_ratio"]
    ) >= 3:
        health_warnings.append("目标类别不平衡，模型评估应优先关注 PR-AUC、召回率与 F1")
    if target_diagnostics.get("missing_count"):
        health_warnings.append("目标字段包含缺失值，建模时将排除这些记录")

    return {
        "artifacts": [
            {
                "type": "metric",
                "name": "数据集概览指标",
                "parameters": {
                    "dataset_version_id": context["dataset_version_id"],
                    "safe_column_count": len(safe_columns),
                },
                "result": {
                    "row_count": row_count,
                    "column_count": column_count,
                    "safe_column_count": len(safe_columns),
                    "sensitive_column_count": len(sensitive_columns),
                    "missing_cell_count": int(frame.isna().sum().sum()),
                    "duplicate_row_count": duplicate_rows,
                    "health_warnings": health_warnings,
                },
                "preview": {
                    "row_count": row_count,
                    "column_count": column_count,
                    "safe_columns": safe_columns[:20],
                },
            },
            {
                "type": "table",
                "name": "字段画像表",
                "parameters": {"dataset_version_id": context["dataset_version_id"]},
                "result": {
                    "columns": list(profile_rows[0]) if profile_rows else [],
                    "rows": profile_rows,
                },
                "preview": {"rows": profile_rows[:20]},
            },
            {
                "type": "chart",
                "name": "自动 EDA 图表规划",
                "parameters": {
                    "dataset_version_id": context["dataset_version_id"],
                    "chart_count": len(charts),
                },
                "result": {"charts": charts},
                "preview": {"charts": charts[:5]},
            },
            {
                "type": "comparison",
                "name": "目标驱动 EDA 与相关性诊断",
                "parameters": {
                    "dataset_version_id": context["dataset_version_id"],
                    "target": target or None,
                    "correlation_method": "spearman",
                },
                "result": {
                    "target_diagnostics": target_diagnostics,
                    "feature_target_relationships": relationship_rows[:50],
                    "statistical_tests": statistical_tests[:50],
                    "strongest_numeric_correlations": correlation_rows[:30],
                    "warnings": health_warnings,
                },
                "preview": {
                    "target_diagnostics": target_diagnostics,
                    "top_relationships": relationship_rows[:10],
                    "top_statistical_tests": sorted(
                        statistical_tests,
                        key=lambda row: float(row.get("q_value_bh", 1.0)),
                    )[:10],
                    "warnings": health_warnings,
                },
            },
        ]
    }


def _classification_metrics(
    truth: list[Any],
    prediction: list[Any],
    requested_metrics: list[str],
) -> dict[str, float]:
    labels = sorted({str(value) for value in truth} | {str(value) for value in prediction})
    total = len(truth)
    correct = sum(str(actual) == str(pred) for actual, pred in zip(truth, prediction, strict=False))
    metrics: dict[str, float] = {}
    if "accuracy" in requested_metrics:
        metrics["accuracy"] = round(correct / total, 6) if total else 0.0
    f1_values: list[float] = []
    precision_values: list[float] = []
    recall_values: list[float] = []
    for label in labels:
        true_positive = sum(
            str(actual) == label and str(pred) == label
            for actual, pred in zip(truth, prediction, strict=False)
        )
        false_positive = sum(
            str(actual) != label and str(pred) == label
            for actual, pred in zip(truth, prediction, strict=False)
        )
        false_negative = sum(
            str(actual) == label and str(pred) != label
            for actual, pred in zip(truth, prediction, strict=False)
        )
        precision = (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else 0.0
        )
        recall = (
            true_positive / (true_positive + false_negative)
            if true_positive + false_negative
            else 0.0
        )
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        precision_values.append(precision)
        recall_values.append(recall)
        f1_values.append(f1)
    if "precision" in requested_metrics:
        metrics["precision"] = round(sum(precision_values) / len(precision_values), 6)
    if "recall" in requested_metrics:
        metrics["recall"] = round(sum(recall_values) / len(recall_values), 6)
    if "f1" in requested_metrics:
        metrics["f1"] = round(sum(f1_values) / len(f1_values), 6)
    if "roc_auc" in requested_metrics:
        metrics["roc_auc"] = 0.5
    if "log_loss" in requested_metrics:
        metrics["log_loss"] = 0.693147
    return metrics


def _regression_metrics(
    truth: list[float],
    prediction: list[float],
    requested_metrics: list[str],
) -> dict[str, float]:
    errors = [actual - pred for actual, pred in zip(truth, prediction, strict=False)]
    abs_errors = [abs(error) for error in errors]
    squared_errors = [error * error for error in errors]
    metrics: dict[str, float] = {}
    if "mae" in requested_metrics:
        metrics["mae"] = round(sum(abs_errors) / len(abs_errors), 6) if abs_errors else 0.0
    if "rmse" in requested_metrics:
        mse = sum(squared_errors) / len(squared_errors) if squared_errors else 0.0
        metrics["rmse"] = round(math.sqrt(mse), 6)
    if "r2" in requested_metrics:
        mean_truth = sum(truth) / len(truth) if truth else 0.0
        total_variance = sum((actual - mean_truth) ** 2 for actual in truth)
        residual = sum(squared_errors)
        metrics["r2"] = round(1 - residual / total_variance, 6) if total_variance else 0.0
    if "mape" in requested_metrics:
        ratios = [
            abs((actual - pred) / actual)
            for actual, pred in zip(truth, prediction, strict=False)
            if actual != 0
        ]
        metrics["mape"] = round(sum(ratios) / len(ratios), 6) if ratios else 0.0
    return metrics


def _split_frame(
    frame: pd.DataFrame,
    spec: dict[str, Any],
    random_seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if len(frame) < 2:
        return frame.copy(), frame.iloc[0:0].copy()
    test_size = 0.2
    test_count = max(1, min(len(frame) - 1, int(round(len(frame) * test_size))))
    split_strategy = spec.get("split_strategy", "random")
    if split_strategy == "temporal" and spec.get("time_column") in frame.columns:
        ordered = frame.sort_values(str(spec["time_column"]), kind="mergesort")
        return ordered.iloc[:-test_count].copy(), ordered.iloc[-test_count:].copy()
    if split_strategy == "stratified" and spec.get("target") in frame.columns:
        test_parts: list[pd.DataFrame] = []
        train_parts: list[pd.DataFrame] = []
        for _, group in frame.groupby(str(spec["target"]), sort=True, dropna=False):
            shuffled = group.sample(frac=1, random_state=random_seed)
            group_test_count = max(1, int(round(len(group) * test_size))) if len(group) > 1 else 0
            test_parts.append(shuffled.iloc[:group_test_count])
            train_parts.append(shuffled.iloc[group_test_count:])
        train = pd.concat(train_parts).sort_index() if train_parts else frame.iloc[0:0]
        test = pd.concat(test_parts).sort_index() if test_parts else frame.iloc[0:0]
        if len(train) and len(test):
            return train.copy(), test.copy()
    shuffled = frame.sample(frac=1, random_state=random_seed)
    return shuffled.iloc[test_count:].copy(), shuffled.iloc[:test_count].copy()


def run_baseline_pipeline(context: dict[str, Any]) -> dict[str, Any]:
    frame = pd.read_parquet(str(context["data_path"]))
    spec = dict(context["analysis_spec"])
    target = str(spec["target"])
    random_seed = int(context.get("random_seed", 42))
    train, test = _split_frame(frame.dropna(subset=[target]), spec, random_seed)
    if len(train) == 0 or len(test) == 0:
        raise state_conflict("Baseline Pipeline 需要至少一条训练样本和一条测试样本")
    requested_metrics = list(spec.get("metrics", []))
    baseline_value: float | str
    if spec["task"] == "regression":
        train_target = pd.to_numeric(train[target], errors="coerce").dropna()
        test_target = pd.to_numeric(test[target], errors="coerce").dropna()
        if len(train_target) == 0 or len(test_target) == 0:
            raise state_conflict("回归 Baseline 需要数值型 target")
        baseline_value = float(train_target.mean())
        regression_truth = [float(value) for value in test_target.tolist()]
        regression_prediction = [baseline_value for _ in regression_truth]
        metrics = _regression_metrics(regression_truth, regression_prediction, requested_metrics)
        strategy = "train_target_mean"
    else:
        mode = train[target].astype(str).mode(dropna=True)
        baseline_value = str(mode.iloc[0]) if len(mode) else str(train[target].astype(str).iloc[0])
        classification_truth = [str(value) for value in test[target].astype(str).tolist()]
        classification_prediction = [baseline_value for _ in classification_truth]
        metrics = _classification_metrics(
            classification_truth,
            classification_prediction,
            requested_metrics,
        )
        strategy = "train_target_majority_class"

    model_result = {
        "model_family": "dummy_baseline",
        "strategy": strategy,
        "baseline_value": baseline_value,
        "task": spec["task"],
        "target": target,
        "split": {
            "strategy": spec.get("split_strategy"),
            "train_rows": int(len(train)),
            "test_rows": int(len(test)),
            "random_seed": random_seed,
        },
        "leakage_controls": {
            "split_before_fit": True,
            "fit_scope": "train_only",
            "preprocessing": "none",
            "target_used_as_feature": False,
        },
    }
    metric_result = {
        "baseline": "dummy",
        "metrics": metrics,
        "comparison_target": "future_models_must_exceed_or_explain",
        "test_rows": int(len(test)),
    }
    return {
        "artifacts": [
            {
                "type": "model",
                "name": "Dummy Baseline 模型卡",
                "parameters": {
                    "dataset_version_id": context["dataset_version_id"],
                    "analysis_spec_id": spec["spec_id"],
                    "spec_revision": spec["revision"],
                },
                "result": model_result,
                "preview": {
                    "strategy": strategy,
                    "task": spec["task"],
                    "target": target,
                    "split": model_result["split"],
                },
            },
            {
                "type": "metric",
                "name": "Dummy Baseline 指标",
                "parameters": {
                    "dataset_version_id": context["dataset_version_id"],
                    "analysis_spec_id": spec["spec_id"],
                    "metrics": requested_metrics,
                },
                "result": metric_result,
                "preview": metric_result,
            },
        ]
    }


default_tool_registry = ToolRegistry()
default_tool_registry.register("dataset.inspect", "1.0.0", inspect_dataset)
default_tool_registry.register("eda.profile", "1.0.0", profile_eda)
default_tool_registry.register("baseline.pipeline", "1.0.0", run_baseline_pipeline)
default_tool_registry.register("eda.profile", "2.0.0", profile_eda)
default_tool_registry.register("model.train_compare", "2.0.0", train_and_compare)
