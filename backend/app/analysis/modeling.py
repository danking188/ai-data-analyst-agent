from __future__ import annotations

import io
import math
import platform
from dataclasses import dataclass
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    log_loss,
    mean_absolute_error,
    mean_absolute_percentage_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import (
    GroupKFold,
    GroupShuffleSplit,
    KFold,
    StratifiedKFold,
    TimeSeriesSplit,
    cross_val_score,
    train_test_split,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from app.domain.errors import state_conflict

MODEL_TASKS = {"binary_classification", "multiclass_classification", "regression"}
LOSS_METRICS = {"log_loss", "mae", "rmse", "mape"}
SCORING = {
    "accuracy": "accuracy",
    "precision": "precision_macro",
    "recall": "recall_macro",
    "f1": "f1_macro",
    "roc_auc": "roc_auc",
    "pr_auc": "average_precision",
    "log_loss": "neg_log_loss",
    "mae": "neg_mean_absolute_error",
    "rmse": "neg_root_mean_squared_error",
    "r2": "r2",
    "mape": "neg_mean_absolute_percentage_error",
}


@dataclass(frozen=True, slots=True)
class SplitData:
    train: pd.DataFrame
    test: pd.DataFrame
    strategy: str
    group_overlap: int | None


def _round(value: float) -> float | None:
    return None if not math.isfinite(value) else round(float(value), 6)


def _feature_columns(frame: pd.DataFrame, spec: dict[str, Any]) -> list[str]:
    target = str(spec["target"])
    requested = [str(value) for value in spec.get("included_columns", [])]
    excluded = {str(value) for value in spec.get("excluded_columns", [])}
    columns = requested or [str(value) for value in frame.columns]
    selected = [column for column in columns if column in frame.columns and column != target]
    selected = [column for column in selected if column not in excluded]
    if not selected:
        raise state_conflict("建模至少需要一个有效特征字段")
    return selected


def _split_frame(frame: pd.DataFrame, spec: dict[str, Any], seed: int) -> SplitData:
    strategy = str(spec.get("split_strategy", "random"))
    target = str(spec["target"])
    if len(frame) < 5:
        raise state_conflict("建模至少需要 5 条 target 非空的样本", sample_count=len(frame))
    test_size = 0.2
    if strategy == "temporal":
        time_column = str(spec.get("time_column") or "")
        if time_column not in frame.columns:
            raise state_conflict("时间拆分缺少有效 time_column")
        ordered = frame.assign(
            __split_time=pd.to_datetime(frame[time_column], errors="coerce", utc=True)
        ).dropna(subset=["__split_time"])
        ordered = ordered.sort_values("__split_time", kind="mergesort").drop(
            columns=["__split_time"]
        )
        test_count = max(1, min(len(ordered) - 1, int(math.ceil(len(ordered) * test_size))))
        return SplitData(ordered.iloc[:-test_count], ordered.iloc[-test_count:], strategy, None)
    if strategy == "group":
        group_column = str(spec.get("group_column") or "")
        if group_column not in frame.columns:
            raise state_conflict("分组拆分缺少有效 group_column")
        groups = frame[group_column].fillna("__missing_group__").astype(str)
        if groups.nunique() < 2:
            raise state_conflict("分组拆分至少需要两个不同 group")
        train_index, test_index = next(
            GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed).split(
                frame, groups=groups
            )
        )
        train, test = frame.iloc[train_index], frame.iloc[test_index]
        overlap = len(set(groups.iloc[train_index]) & set(groups.iloc[test_index]))
        return SplitData(train, test, strategy, overlap)
    stratify = frame[target].astype(str) if strategy == "stratified" else None
    if stratify is not None and (stratify.value_counts() < 2).any():
        raise state_conflict("分层拆分要求每个类别至少有 2 条样本")
    train, test = train_test_split(
        frame,
        test_size=test_size,
        random_state=seed,
        stratify=stratify,
    )
    return SplitData(train, test, strategy, None)


def _reject_exact_target_copies(
    frame: pd.DataFrame,
    columns: list[str],
    target: str,
) -> None:
    copies = []
    for column in columns:
        pair = frame[[column, target]].dropna()
        if len(pair) and pair[column].astype(str).reset_index(drop=True).equals(
            pair[target].astype(str).reset_index(drop=True)
        ):
            copies.append(column)
    if copies:
        raise state_conflict(
            "检测到与 target 完全相同的特征，已阻断潜在数据泄露",
            columns=copies,
            target=target,
        )


def _preprocessor(frame: pd.DataFrame, columns: list[str], *, ordinal: bool) -> ColumnTransformer:
    numeric = [column for column in columns if pd.api.types.is_numeric_dtype(frame[column])]
    categorical = [column for column in columns if column not in numeric]
    transformers: list[tuple[str, Any, list[str]]] = []
    if numeric:
        transformers.append(
            (
                "numeric",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="median")),
                        ("scale", StandardScaler()),
                    ]
                ),
                numeric,
            )
        )
    if categorical:
        encoder: Any = (
            OrdinalEncoder(
                handle_unknown="use_encoded_value",
                unknown_value=-1,
                encoded_missing_value=-1,
            )
            if ordinal
            else OneHotEncoder(
                handle_unknown="infrequent_if_exist",
                min_frequency=2,
                max_categories=50,
            )
        )
        transformers.append(
            (
                "categorical",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        ("encode", encoder),
                    ]
                ),
                categorical,
            )
        )
    return ColumnTransformer(transformers, remainder="drop")


def _candidates(task: str, frame: pd.DataFrame, columns: list[str], seed: int) -> dict[str, Any]:
    linear = _preprocessor(frame, columns, ordinal=False)
    tree = _preprocessor(frame, columns, ordinal=True)
    if task != "regression":
        return {
            "dummy": Pipeline(
                [("preprocess", clone(linear)), ("model", DummyClassifier(strategy="prior"))]
            ),
            "logistic_regression": Pipeline(
                [
                    ("preprocess", clone(linear)),
                    (
                        "model",
                        LogisticRegression(
                            max_iter=1000,
                            class_weight="balanced",
                            random_state=seed,
                        ),
                    ),
                ]
            ),
            "hist_gradient_boosting": Pipeline(
                [
                    ("preprocess", tree),
                    (
                        "model",
                        HistGradientBoostingClassifier(
                            max_iter=150,
                            learning_rate=0.08,
                            random_state=seed,
                        ),
                    ),
                ]
            ),
        }
    return {
        "dummy": Pipeline(
            [("preprocess", clone(linear)), ("model", DummyRegressor(strategy="mean"))]
        ),
        "ridge": Pipeline([("preprocess", clone(linear)), ("model", Ridge(alpha=1.0))]),
        "hist_gradient_boosting": Pipeline(
            [
                ("preprocess", tree),
                (
                    "model",
                    HistGradientBoostingRegressor(
                        max_iter=150,
                        learning_rate=0.08,
                        random_state=seed,
                    ),
                ),
            ]
        ),
    }


def _cv_strategy(
    train: pd.DataFrame,
    spec: dict[str, Any],
    seed: int,
) -> tuple[Any | None, pd.Series | None, int]:
    strategy = str(spec.get("split_strategy", "random"))
    target = str(spec["target"])
    if strategy == "temporal":
        folds = min(3, len(train) - 1)
        return (TimeSeriesSplit(n_splits=folds), None, folds) if folds >= 2 else (None, None, 0)
    if strategy == "group":
        group_column = str(spec.get("group_column") or "")
        groups = train[group_column].fillna("__missing_group__").astype(str)
        folds = min(3, int(groups.nunique()))
        return (GroupKFold(n_splits=folds), groups, folds) if folds >= 2 else (None, None, 0)
    if spec["task"] != "regression":
        minimum_class = int(train[target].astype(str).value_counts().min())
        folds = min(5, minimum_class)
        if folds < 2:
            return None, None, 0
        return StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed), None, folds
    folds = min(5, len(train))
    return KFold(n_splits=folds, shuffle=True, random_state=seed), None, folds


def _classification_metrics(model: Any, features: pd.DataFrame, truth: pd.Series) -> dict[str, Any]:
    prediction = model.predict(features)
    metrics: dict[str, Any] = {
        "accuracy": _round(accuracy_score(truth, prediction)),
        "precision": _round(precision_score(truth, prediction, average="macro", zero_division=0)),
        "recall": _round(recall_score(truth, prediction, average="macro", zero_division=0)),
        "f1": _round(f1_score(truth, prediction, average="macro", zero_division=0)),
    }
    labels = [str(value) for value in model.classes_]
    metrics["confusion_matrix"] = {
        "labels": labels,
        "values": confusion_matrix(truth, prediction, labels=model.classes_).tolist(),
    }
    if hasattr(model, "predict_proba"):
        probability = model.predict_proba(features)
        try:
            metrics["log_loss"] = _round(log_loss(truth, probability, labels=model.classes_))
            if len(model.classes_) == 2:
                positive = model.classes_[1]
                binary_truth = (np.asarray(truth) == positive).astype(int)
                metrics["roc_auc"] = _round(roc_auc_score(binary_truth, probability[:, 1]))
                metrics["pr_auc"] = _round(
                    average_precision_score(binary_truth, probability[:, 1])
                )
                metrics["positive_class"] = str(positive)
            elif len(model.classes_) > 2:
                metrics["roc_auc"] = _round(
                    roc_auc_score(truth, probability, multi_class="ovr", average="weighted")
                )
        except ValueError:
            pass
    return metrics


def _regression_metrics(model: Any, features: pd.DataFrame, truth: pd.Series) -> dict[str, Any]:
    prediction = model.predict(features)
    metrics: dict[str, Any] = {
        "mae": _round(mean_absolute_error(truth, prediction)),
        "rmse": _round(math.sqrt(mean_squared_error(truth, prediction))),
        "r2": _round(r2_score(truth, prediction)),
    }
    non_zero = np.asarray(truth) != 0
    if non_zero.any():
        metrics["mape"] = _round(
            mean_absolute_percentage_error(np.asarray(truth)[non_zero], prediction[non_zero])
        )
    residuals = np.asarray(truth) - np.asarray(prediction)
    metrics["residual_summary"] = {
        "mean": _round(float(np.mean(residuals))),
        "std": _round(float(np.std(residuals))),
        "p05": _round(float(np.quantile(residuals, 0.05))),
        "p95": _round(float(np.quantile(residuals, 0.95))),
    }
    return metrics


def _primary_metric(spec: dict[str, Any]) -> str:
    requested = [str(value) for value in spec.get("metrics", [])]
    return next(
        (value for value in requested if value in SCORING),
        "rmse" if spec["task"] == "regression" else "f1",
    )


def _importance(
    model: Any,
    features: pd.DataFrame,
    truth: pd.Series,
    primary_metric: str,
    seed: int,
) -> list[dict[str, Any]]:
    if len(features) < 2:
        return []
    sample = features.sample(n=min(len(features), 2000), random_state=seed)
    try:
        result = permutation_importance(
            model,
            sample,
            truth.loc[sample.index],
            scoring=SCORING[primary_metric],
            n_repeats=5,
            random_state=seed,
            n_jobs=1,
        )
    except ValueError:
        return []
    rows = [
        {
            "feature": str(feature),
            "importance_mean": _round(float(mean)),
            "importance_std": _round(float(std)),
        }
        for feature, mean, std in zip(
            features.columns, result.importances_mean, result.importances_std, strict=True
        )
    ]
    return sorted(rows, key=lambda row: abs(float(row["importance_mean"] or 0)), reverse=True)[:20]


def train_and_compare(context: dict[str, Any]) -> dict[str, Any]:
    frame = pd.read_parquet(str(context["data_path"]))
    spec = dict(context["analysis_spec"])
    if spec.get("task") not in MODEL_TASKS:
        raise state_conflict("当前任务类型不支持监督建模", task=spec.get("task"))
    target = str(spec["target"])
    if target not in frame.columns:
        raise state_conflict("目标字段不存在", target=target)
    seed = int(context.get("random_seed", 42))
    columns = _feature_columns(frame, spec)
    required = [*columns, target]
    for split_column in (spec.get("time_column"), spec.get("group_column")):
        if split_column and split_column not in required:
            required.append(str(split_column))
    modeling_frame = frame[required].dropna(subset=[target]).copy()
    if spec["task"] == "regression":
        modeling_frame[target] = pd.to_numeric(modeling_frame[target], errors="coerce")
        modeling_frame = modeling_frame.dropna(subset=[target])
    else:
        modeling_frame[target] = modeling_frame[target].astype(str)
        class_count = int(modeling_frame[target].nunique())
        expected = 2 if spec["task"] == "binary_classification" else 3
        if class_count < expected:
            raise state_conflict("分类 target 的有效类别数不足", class_count=class_count)

    _reject_exact_target_copies(modeling_frame, columns, target)

    split = _split_frame(modeling_frame, spec, seed)
    train_x, test_x = split.train[columns], split.test[columns]
    train_y, test_y = split.train[target], split.test[target]
    candidates = _candidates(str(spec["task"]), split.train, columns, seed)
    primary = _primary_metric(spec)
    cv, groups, folds = _cv_strategy(split.train, spec, seed)
    candidate_results: list[dict[str, Any]] = []
    fitted: dict[str, Any] = {}
    for name, pipeline in candidates.items():
        row: dict[str, Any] = {"name": name, "status": "succeeded"}
        try:
            if cv is not None:
                scores = cross_val_score(
                    clone(pipeline),
                    train_x,
                    train_y,
                    cv=cv,
                    groups=groups,
                    scoring=SCORING[primary],
                    n_jobs=1,
                    error_score="raise",
                )
                row["cv_score_mean"] = _round(float(np.mean(scores)))
                row["cv_score_std"] = _round(float(np.std(scores)))
                row["cv_folds"] = folds
            else:
                row.update(
                    status="cv_unavailable",
                    cv_score_mean=None,
                    cv_score_std=None,
                    cv_folds=0,
                )
            fitted[name] = pipeline.fit(train_x, train_y)
        except (TypeError, ValueError) as exc:
            row.update(status="failed", error=str(exc)[:300], cv_score_mean=None)
        candidate_results.append(row)
    usable = [row for row in candidate_results if row["name"] in fitted]
    if not usable:
        raise state_conflict("所有候选模型均训练失败")
    scored = [row for row in usable if row.get("cv_score_mean") is not None]
    selection_pool = (
        [row for row in scored if row["name"] != "dummy"]
        or scored
        or [row for row in usable if row["name"] != "dummy"]
        or usable
    )
    selected_row = max(selection_pool, key=lambda row: float(row.get("cv_score_mean") or -math.inf))
    selected_name = str(selected_row["name"])
    selected_model = fitted[selected_name]
    baseline_model = fitted.get("dummy")
    metric_function = (
        _regression_metrics if spec["task"] == "regression" else _classification_metrics
    )
    selected_metrics = metric_function(selected_model, test_x, test_y)
    baseline_metrics = metric_function(baseline_model, test_x, test_y) if baseline_model else {}
    importance = _importance(selected_model, test_x, test_y, primary, seed)
    comparison = []
    for metric in sorted(set(selected_metrics) & set(baseline_metrics)):
        selected_value = selected_metrics[metric]
        baseline_value = baseline_metrics[metric]
        if isinstance(selected_value, (int, float)) and isinstance(baseline_value, (int, float)):
            raw_delta = float(selected_value) - float(baseline_value)
            comparison.append(
                {
                    "metric": metric,
                    "selected": selected_value,
                    "baseline": baseline_value,
                    "improvement": _round(-raw_delta if metric in LOSS_METRICS else raw_delta),
                    "higher_is_better": metric not in LOSS_METRICS,
                }
            )
    runtime = {"python": platform.python_version(), "scikit_learn": sklearn.__version__}
    bundle = {
        "pipeline": selected_model,
        "metadata": {
            "run_id": context["run_id"],
            "dataset_version_id": context["dataset_version_id"],
            "analysis_spec_id": spec["spec_id"],
            "analysis_spec_revision": spec["revision"],
            "feature_columns": columns,
            "target": target,
            "task": spec["task"],
            "selected_model": selected_name,
            **runtime,
        },
    }
    buffer = io.BytesIO()
    joblib.dump(bundle, buffer, compress=3)
    model_result = {
        "model_family": selected_name,
        "strategy": "train_cv_selection_then_single_holdout_evaluation",
        "task": spec["task"],
        "target": target,
        "feature_columns": columns,
        "candidate_results": candidate_results,
        "primary_metric": primary,
        "split": {
            "strategy": split.strategy,
            "train_rows": int(len(split.train)),
            "test_rows": int(len(split.test)),
            "random_seed": seed,
            "group_overlap": split.group_overlap,
        },
        "cross_validation": {"folds": folds, "selection_scope": "training_partition_only"},
        "preprocessing": {
            "numeric": ["median_imputation", "standard_scaling"],
            "categorical": ["most_frequent_imputation", "unknown_safe_encoding"],
            "fit_scope": "training_partition_only",
        },
        "leakage_controls": {
            "split_before_fit": True,
            "fit_scope": "train_only",
            "model_selection_scope": "train_cross_validation_only",
            "test_used_for_selection": False,
            "target_used_as_feature": False,
            "group_overlap": split.group_overlap,
        },
        "feature_importance": importance,
        "runtime": runtime,
    }
    metric_result = {
        "model": selected_name,
        "primary_metric": primary,
        "metrics": selected_metrics,
        "baseline_metrics": baseline_metrics,
        "comparison": comparison,
        "test_rows": int(len(split.test)),
    }
    charts = [
        {
            "chart_id": "model_vs_dummy",
            "title": "入选模型与 Dummy 保留集对比",
            "chart_type": "bar",
            "encoding": {"x": "metric", "y": "improvement"},
            "data": comparison,
        },
        {
            "chart_id": "permutation_importance",
            "title": "保留集置换重要性",
            "chart_type": "bar",
            "encoding": {"x": "feature", "y": "importance_mean"},
            "data": importance,
        },
    ]
    limitations = [
        "模型选择仅使用训练分区交叉验证，测试分区只用于最终一次评估。",
        "置换重要性描述预测贡献，不代表因果关系。",
        "模型包仅应由可信环境加载，并要求兼容的 Python 与 scikit-learn 版本。",
    ]
    return {
        "artifacts": [
            {
                "type": "model",
                "name": "候选模型选择与模型卡",
                "parameters": {
                    "dataset_version_id": context["dataset_version_id"],
                    "analysis_spec_id": spec["spec_id"],
                    "spec_revision": spec["revision"],
                },
                "result": model_result,
                "preview": {
                    "model_family": selected_name,
                    "primary_metric": primary,
                    "split": model_result["split"],
                },
            },
            {
                "type": "metric",
                "name": "保留集评估指标",
                "parameters": {
                    "dataset_version_id": context["dataset_version_id"],
                    "analysis_spec_id": spec["spec_id"],
                    "requested_metrics": spec.get("metrics", []),
                },
                "result": metric_result,
                "preview": metric_result,
            },
            {
                "type": "comparison",
                "name": "模型候选与 Dummy 比较",
                "parameters": {"primary_metric": primary, "cv_folds": folds},
                "result": {
                    "candidates": candidate_results,
                    "holdout_comparison": comparison,
                    "selection_rule": "maximum training CV score; loss scorers are negated",
                },
                "preview": {"selected_model": selected_name, "candidates": candidate_results},
            },
            {
                "type": "chart",
                "name": "模型评估与解释图表",
                "parameters": {"dataset_version_id": context["dataset_version_id"]},
                "result": {"charts": charts},
                "preview": {"charts": charts},
            },
            {
                "type": "log",
                "name": "模型适用范围与限制",
                "parameters": {"analysis_spec_id": spec["spec_id"]},
                "result": {"limitations": limitations, "causal_interpretation_allowed": False},
                "preview": {"limitations": limitations},
            },
        ],
        "files": [
            {
                "name": "已训练 sklearn Pipeline",
                "file_name": f"{context['run_id']}-model.joblib",
                "content_type": "application/octet-stream",
                "content": buffer.getvalue(),
                "result": {
                    "selected_model": selected_name,
                    "feature_columns": columns,
                    "runtime": runtime,
                    "security": "仅加载本系统生成且校验通过的模型包",
                },
            }
        ],
    }
