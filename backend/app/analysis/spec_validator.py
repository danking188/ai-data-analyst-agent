from __future__ import annotations

from collections.abc import Mapping

from app.api.schemas import AnalysisSpecCreate
from app.domain.errors import validation_error
from app.persistence.orm.workflow_models import ColumnSchemaRow

MODEL_TASKS = {"binary_classification", "multiclass_classification", "regression"}
METRICS_BY_TASK: dict[str, set[str]] = {
    "descriptive": {"count", "mean", "median", "std", "missing_rate", "quantiles"},
    "comparison": {"difference", "percent_change", "p_value", "effect_size"},
    "statistical_test": {"p_value", "effect_size", "confidence_interval"},
    "binary_classification": {
        "accuracy",
        "precision",
        "recall",
        "f1",
        "roc_auc",
        "pr_auc",
        "log_loss",
    },
    "multiclass_classification": {
        "accuracy",
        "precision",
        "recall",
        "f1",
        "log_loss",
    },
    "regression": {"mae", "rmse", "r2", "mape"},
}


def validate_analysis_spec(
    spec: AnalysisSpecCreate,
    *,
    columns: Mapping[str, ColumnSchemaRow],
) -> list[str]:
    names = set(columns)
    referenced = {
        value
        for value in (
            spec.target,
            spec.entity_key,
            spec.time_column,
            spec.group_column,
            *spec.included_columns,
            *spec.excluded_columns,
        )
        if value is not None
    }
    unknown = sorted(referenced - names)
    if unknown:
        raise validation_error("AnalysisSpec 引用了不存在的字段", columns=unknown)

    overlap = sorted(set(spec.included_columns) & set(spec.excluded_columns))
    if overlap:
        raise validation_error("included_columns 与 excluded_columns 不可重叠", columns=overlap)
    if spec.target and spec.target in spec.excluded_columns:
        raise validation_error("目标字段不能被排除", target=spec.target)
    sensitive_features = sorted(
        column for column in spec.included_columns if columns[column].sensitive
    )
    if sensitive_features:
        raise validation_error(
            "敏感字段不能直接作为自动建模特征",
            columns=sensitive_features,
        )

    allowed_metrics = METRICS_BY_TASK[spec.task]
    unsupported = sorted(set(spec.metrics) - allowed_metrics)
    if unsupported:
        raise validation_error(
            "指标与分析任务不兼容",
            task=spec.task,
            metrics=unsupported,
            allowed_metrics=sorted(allowed_metrics),
        )
    if not spec.metrics:
        raise validation_error("至少需要一个评估指标")

    if spec.task in MODEL_TASKS and spec.target is None:
        raise validation_error("建模任务必须指定 target")
    if spec.task not in MODEL_TASKS and spec.target is not None and spec.task == "descriptive":
        raise validation_error("描述性分析不使用 target")
    if spec.task in MODEL_TASKS and spec.split_strategy == "none":
        raise validation_error("建模任务必须配置数据拆分策略")
    if spec.task not in MODEL_TASKS and spec.split_strategy != "none":
        raise validation_error("非建模任务的 split_strategy 必须为 none")
    if spec.split_strategy == "stratified" and "classification" not in spec.task:
        raise validation_error("stratified 仅适用于分类任务")
    if spec.split_strategy == "temporal" and spec.time_column is None:
        raise validation_error("temporal 拆分必须指定 time_column")
    if spec.split_strategy == "group" and spec.group_column is None:
        raise validation_error("group 拆分必须指定 group_column")

    if spec.target is not None:
        target = columns[spec.target]
        if spec.task == "regression" and target.semantic_type != "numeric":
            raise validation_error("回归任务 target 必须为数值字段", target=spec.target)
        if spec.task in {"binary_classification", "multiclass_classification"} and (
            target.semantic_type not in {"categorical", "boolean", "ordinal"}
        ):
            raise validation_error("分类任务 target 必须为离散字段", target=spec.target)

    warnings: list[str] = []
    if spec.task in MODEL_TASKS and not spec.prediction_time_description:
        warnings.append("未描述预测时点；运行前应核对特征可用性以避免时间泄露")
    if spec.split_strategy == "temporal" and spec.time_column is not None:
        time_schema = columns[spec.time_column]
        if time_schema.semantic_type != "datetime":
            raise validation_error("time_column 必须为 datetime 语义字段")
    if spec.entity_key is not None and columns[spec.entity_key].analysis_role != "entity_key":
        warnings.append("entity_key 字段尚未在 Schema 中确认 entity_key 角色")
    return warnings
