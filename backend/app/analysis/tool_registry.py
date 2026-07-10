from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.analysis.sandbox import validate_tool_context
from app.domain.errors import state_conflict

ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


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
