from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from app.llm.schemas import StrictLLMModel


class AnalysisSpecDraft(StrictLLMModel):
    name: str = Field(min_length=1, max_length=120)
    task: Literal[
        "descriptive",
        "comparison",
        "statistical_test",
        "binary_classification",
        "multiclass_classification",
        "regression",
    ]
    target: str | None = None
    entity_key: str | None = None
    time_column: str | None = None
    prediction_time_description: str | None = Field(default=None, max_length=1000)
    split_strategy: Literal["none", "random", "stratified", "temporal", "group"]
    group_column: str | None = None
    metrics: list[str] = Field(min_length=1, max_length=12)
    included_columns: list[str] = Field(default_factory=list, max_length=200)
    excluded_columns: list[str] = Field(default_factory=list, max_length=200)
    random_seed: int = Field(default=42, ge=0, le=2_147_483_647)
    rationale: str = Field(min_length=1, max_length=2000)
    leakage_warnings: list[str] = Field(default_factory=list, max_length=20)
    validation_warnings: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("metrics", mode="before")
    @classmethod
    def normalize_metric_aliases(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        aliases = {
            "f1_score": "f1",
            "f1_macro": "f1",
            "auc": "roc_auc",
            "roc-auc": "roc_auc",
            "prauc": "pr_auc",
            "precision_recall_auc": "pr_auc",
            "mean_absolute_error": "mae",
            "mean_squared_error": "mse",
            "root_mean_squared_error": "rmse",
            "r_squared": "r2",
        }
        normalized = [str(metric).strip().lower() for metric in value]
        return [aliases.get(metric, metric) for metric in normalized]

    @model_validator(mode="after")
    def validate_column_sets(self) -> AnalysisSpecDraft:
        for field in ("metrics", "included_columns", "excluded_columns"):
            values = getattr(self, field)
            if len(values) != len(set(values)):
                raise ValueError(f"{field} must not contain duplicates")
        if set(self.included_columns) & set(self.excluded_columns):
            raise ValueError("included_columns and excluded_columns must not overlap")
        return self


class CleaningOperationDraft(StrictLLMModel):
    operation: Literal[
        "impute_missing",
        "drop_duplicates",
        "cast_type",
        "replace_values",
        "normalize_category",
        "filter_rows",
        "add_missing_indicator",
    ]
    column: str | None = None
    parameters: dict[str, Any]
    reason: str = Field(min_length=1, max_length=2000)
    issue_ids: list[str] = Field(default_factory=list, max_length=20)
    risk_level: Literal["low", "medium", "high"]
    reversible: bool


class CleaningPlanDraft(StrictLLMModel):
    name: str = Field(min_length=1, max_length=120)
    operations: list[CleaningOperationDraft] = Field(min_length=1, max_length=20)
    rationale: str = Field(min_length=1, max_length=2000)
    limitations: list[str] = Field(default_factory=list, max_length=20)


class FeatureSuggestion(StrictLLMModel):
    name: str = Field(min_length=1, max_length=160)
    source_columns: list[str] = Field(min_length=1, max_length=20)
    transformation: Literal[
        "missing_indicator",
        "log_transform",
        "binning",
        "interaction",
        "datetime_parts",
        "frequency_encoding",
        "target_independent_aggregation",
    ]
    rationale: str = Field(min_length=1, max_length=2000)
    leakage_risk: Literal["low", "medium", "high"]
    leakage_note: str = Field(min_length=1, max_length=1000)


class FeatureSuggestionDraft(StrictLLMModel):
    title: str = Field(min_length=1, max_length=160)
    suggestions: list[FeatureSuggestion] = Field(min_length=1, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=20)
