from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.llm.schemas import AssistantAnswer, AssistantPlan


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str
    retryable: bool
    details: dict[str, Any]


class ErrorResponse(BaseModel):
    error: ErrorDetail


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    timestamp: datetime


class ReadinessDependency(BaseModel):
    status: Literal["ok"]
    backend: str


class Readiness(BaseModel):
    status: Literal["ready"]
    database: ReadinessDependency
    object_storage: ReadinessDependency
    timestamp: datetime


class PollingPolicy(BaseModel):
    initial_interval_ms: int
    steady_interval_ms: int
    background_interval_ms: int


class LLMCapabilities(BaseModel):
    evidence_narrative: bool
    assistant: bool


class SystemCapabilities(BaseModel):
    api_version: str
    supported_file_types: list[Literal["csv", "xls", "xlsx", "parquet"]]
    max_upload_bytes: int
    natural_language_analysis: bool
    llm: LLMCapabilities
    auth_enabled: bool
    polling: PollingPolicy


class LoginRequest(StrictModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=500)


class RegisterRequest(StrictModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=12, max_length=128)


class SessionInfo(BaseModel):
    subject_id: str
    expires_in_seconds: int | None = Field(default=None, ge=1)


class AuthConfig(BaseModel):
    registration_enabled: bool


class ProjectCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    timezone: str
    language: Literal["zh-CN", "en-US"]

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value


class ProjectUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    timezone: str | None = None
    language: Literal["zh-CN", "en-US"] | None = None

    @field_validator("name")
    @classmethod
    def strip_optional_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_optional_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> ProjectUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        return self


class Project(BaseModel):
    project_id: str
    name: str
    description: str | None
    timezone: str
    language: str
    status: Literal["active", "archived"]
    current_dataset_version_id: str | None
    revision: int
    created_at: datetime
    updated_at: datetime


class ProjectPage(BaseModel):
    items: list[Project]
    page: int
    page_size: int
    total: int
    has_more: bool


class ParseOptions(StrictModel):
    encoding: str | None = None
    delimiter: str | None = Field(default=None, max_length=4)
    header_row: int = Field(default=0, ge=0)
    sheet_name: str | None = None
    date_format_hint: str | None = None


class Dataset(BaseModel):
    dataset_id: str
    project_id: str
    name: str
    source_type: Literal["csv", "xls", "xlsx", "parquet"]
    status: Literal["active", "archived"]
    current_version_id: str | None
    version_count: int = Field(ge=0)
    created_at: datetime


class DatasetPage(BaseModel):
    items: list[Dataset]
    page: int
    page_size: int
    total: int
    has_more: bool


class DatasetVersion(BaseModel):
    version_id: str
    dataset_id: str
    project_id: str
    version_number: int = Field(ge=1)
    status: Literal["creating", "ready", "failed", "archived"]
    kind: Literal["raw", "cleaned", "modeled"]
    parent_version_id: str | None
    source_file_name: str
    sheet_name: str | None
    file_hash: str
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    operation_summary: str | None
    created_at: datetime


class DatasetVersionPage(BaseModel):
    items: list[DatasetVersion]
    page: int
    page_size: int
    total: int
    has_more: bool


class PreviewColumn(BaseModel):
    name: str
    physical_type: str
    semantic_type: str | None
    masked: bool = False


class DataPreview(BaseModel):
    columns: list[PreviewColumn]
    rows: list[dict[str, Any]]
    next_cursor: str | None
    has_more: bool
    masked_columns: list[str]


class VersionComparisonRequest(StrictModel):
    base_version_id: str = Field(min_length=1)
    compare_version_id: str = Field(min_length=1)
    include_sample_changes: bool = True

    @model_validator(mode="after")
    def require_distinct_versions(self) -> VersionComparisonRequest:
        if self.base_version_id == self.compare_version_id:
            raise ValueError("base_version_id and compare_version_id must differ")
        return self


SemanticType = Literal[
    "numeric",
    "categorical",
    "datetime",
    "boolean",
    "identifier",
    "text",
    "currency",
    "percentage",
    "ordinal",
    "geographic_code",
    "unknown",
]
AnalysisRole = Literal[
    "feature",
    "target",
    "entity_key",
    "time",
    "identifier",
    "text",
    "excluded",
    "undecided",
]


class ColumnSchema(BaseModel):
    name: str
    physical_type: Literal["integer", "float", "string", "boolean", "datetime", "binary", "unknown"]
    semantic_type: SemanticType
    analysis_role: AnalysisRole
    confidence: float = Field(ge=0, le=1)
    evidence: list[str]
    date_format: str | None
    ordinal_values: list[str] | None
    sensitive: bool
    user_confirmed: bool = False


class DatasetSchema(BaseModel):
    dataset_version_id: str
    revision: int = Field(ge=1)
    low_confidence_count: int = Field(ge=0)
    columns: list[ColumnSchema]


SemanticAggregation = Literal[
    "sum", "average", "minimum", "maximum", "count", "distinct_count"
]


class SemanticMetricCreate(StrictModel):
    dataset_version_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    source_column: str | None = Field(default=None, max_length=255)
    aggregation: SemanticAggregation
    unit: str | None = Field(default=None, max_length=40)
    grain_dimensions: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("name", "description")
    @classmethod
    def strip_semantic_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("source_column", "unit")
    @classmethod
    def strip_optional_semantic_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def validate_metric_shape(self) -> SemanticMetricCreate:
        if self.aggregation != "count" and not self.source_column:
            raise ValueError("source_column is required unless aggregation=count")
        if len(self.grain_dimensions) != len(set(self.grain_dimensions)):
            raise ValueError("grain_dimensions must not contain duplicates")
        return self


class SemanticMetricUpdate(StrictModel):
    description: str | None = Field(default=None, min_length=1, max_length=1000)
    unit: str | None = Field(default=None, max_length=40)
    grain_dimensions: list[str] | None = Field(default=None, max_length=8)
    status: Literal["active", "archived"] | None = None

    @field_validator("description")
    @classmethod
    def strip_update_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("description must not be blank")
        return value

    @field_validator("unit")
    @classmethod
    def strip_update_unit(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @model_validator(mode="after")
    def validate_update(self) -> SemanticMetricUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        if self.grain_dimensions is not None and len(self.grain_dimensions) != len(
            set(self.grain_dimensions)
        ):
            raise ValueError("grain_dimensions must not contain duplicates")
        return self


class SemanticMetric(BaseModel):
    metric_id: str
    project_id: str
    dataset_version_id: str
    name: str
    description: str
    source_column: str | None
    aggregation: SemanticAggregation
    unit: str | None
    grain_dimensions: list[str]
    status: Literal["active", "stale", "archived"]
    created_by: str
    created_at: datetime
    updated_at: datetime


class SemanticMetricPage(BaseModel):
    items: list[SemanticMetric]
    page: int
    page_size: int
    total: int
    has_more: bool


class ColumnSchemaPatch(StrictModel):
    column: str = Field(min_length=1)
    semantic_type: SemanticType | None = None
    analysis_role: AnalysisRole | None = None
    date_format: str | None = None
    ordinal_values: list[str] | None = None
    sensitive: bool | None = None

    @field_validator("column")
    @classmethod
    def strip_column(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("column must not be blank")
        return value

    @model_validator(mode="after")
    def require_override(self) -> ColumnSchemaPatch:
        if self.model_fields_set == {"column"}:
            raise ValueError("at least one schema override is required")
        return self


class SchemaPatch(StrictModel):
    changes: list[ColumnSchemaPatch] = Field(min_length=1)
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def reject_duplicate_columns(self) -> SchemaPatch:
        names = [change.column for change in self.changes]
        if len(names) != len(set(names)):
            raise ValueError("changes must not contain duplicate columns")
        return self


QualitySeverity = Literal["low", "medium", "high", "critical"]
QualityStatus = Literal["open", "accepted", "resolved", "ignored"]


class QualityScanRequest(StrictModel):
    analysis_spec_id: str | None = None
    rules: list[str] = Field(default_factory=list)
    force: bool = False


class QualityIssue(BaseModel):
    issue_id: str
    dataset_version_id: str
    issue_type: str
    column: str | None
    severity: QualitySeverity
    status: QualityStatus
    title: str
    explanation: str
    metrics: dict[str, Any]
    sample_rows: list[dict[str, Any]]
    recommendation: str | None
    decision_reason: str | None
    revision: int = Field(ge=1)
    created_at: datetime


class QualityIssueUpdate(StrictModel):
    status: Literal["open", "accepted", "ignored"]
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_ignore_reason(self) -> QualityIssueUpdate:
        if self.status == "ignored" and (self.reason is None or not self.reason.strip()):
            raise ValueError("reason is required when status is ignored")
        if self.reason is not None:
            self.reason = self.reason.strip() or None
        return self


class QualityIssuePage(BaseModel):
    items: list[QualityIssue]
    page: int
    page_size: int
    total: int
    has_more: bool


CleaningOperationType = Literal[
    "impute_missing",
    "drop_duplicates",
    "cast_type",
    "replace_values",
    "normalize_category",
    "filter_rows",
    "add_missing_indicator",
]


class CleaningOperation(StrictModel):
    operation_id: str = Field(min_length=1, max_length=40)
    operation: CleaningOperationType
    column: str | None
    parameters: dict[str, Any]
    reason: str = Field(min_length=1, max_length=2000)
    issue_ids: list[str] = Field(default_factory=list)
    estimated_affected_rows: int = Field(default=0, ge=0)
    risk_level: Literal["low", "medium", "high"]
    reversible: bool = False

    @field_validator("operation_id", "reason")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("column")
    @classmethod
    def strip_optional_column(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class CleaningPlanCreate(StrictModel):
    source_version_id: str = Field(min_length=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    operations: list[CleaningOperation] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def strip_optional_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def reject_duplicate_operations(self) -> CleaningPlanCreate:
        identifiers = [operation.operation_id for operation in self.operations]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("operation_id must be unique within a cleaning plan")
        return self


class CleaningPlanUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    operations: list[CleaningOperation] | None = Field(default=None, min_length=1)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def validate_update(self) -> CleaningPlanUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        if self.operations is not None:
            identifiers = [operation.operation_id for operation in self.operations]
            if len(identifiers) != len(set(identifiers)):
                raise ValueError("operation_id must be unique within a cleaning plan")
        return self


class CleaningDecision(StrictModel):
    decision: Literal["approve", "reject"]
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def normalize_reason(self) -> CleaningDecision:
        if self.reason is not None:
            self.reason = self.reason.strip() or None
        if self.decision == "reject" and self.reason is None:
            raise ValueError("reason is required when rejecting a cleaning plan")
        return self


class CleaningPlan(BaseModel):
    plan_id: str
    project_id: str
    source_version_id: str
    result_version_id: str | None
    name: str
    status: Literal[
        "draft",
        "awaiting_approval",
        "approved",
        "rejected",
        "executing",
        "executed",
        "failed",
    ]
    operations: list[CleaningOperation]
    preview_artifact_id: str | None
    decision: Literal["approve", "reject"] | None
    decision_reason: str | None
    revision: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class CleaningPlanPage(BaseModel):
    items: list[CleaningPlan]
    page: int
    page_size: int
    total: int
    has_more: bool


AnalysisTask = Literal[
    "descriptive",
    "comparison",
    "statistical_test",
    "binary_classification",
    "multiclass_classification",
    "regression",
]
SplitStrategy = Literal["none", "random", "stratified", "temporal", "group"]


class AnalysisSpecBase(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    dataset_version_id: str
    task: AnalysisTask
    target: str | None = None
    entity_key: str | None = None
    time_column: str | None = None
    prediction_time_description: str | None = Field(default=None, max_length=1000)
    split_strategy: SplitStrategy
    group_column: str | None = None
    metrics: list[str]
    included_columns: list[str] = Field(default_factory=list)
    excluded_columns: list[str] = Field(default_factory=list)
    random_seed: int = 42
    causal_interpretation_allowed: Literal[False] = False

    @field_validator("name")
    @classmethod
    def strip_analysis_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @model_validator(mode="after")
    def reject_duplicate_spec_lists(self) -> AnalysisSpecBase:
        for field in ("metrics", "included_columns", "excluded_columns"):
            values = getattr(self, field)
            if len(values) != len(set(values)):
                raise ValueError(f"{field} must not contain duplicates")
        overlap = set(self.included_columns) & set(self.excluded_columns)
        if overlap:
            raise ValueError("included_columns and excluded_columns must not overlap")
        return self


class AnalysisSpecCreate(AnalysisSpecBase):
    pass


class AnalysisSpecUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    dataset_version_id: str | None = None
    task: AnalysisTask | None = None
    target: str | None = None
    entity_key: str | None = None
    time_column: str | None = None
    prediction_time_description: str | None = Field(default=None, max_length=1000)
    split_strategy: SplitStrategy | None = None
    group_column: str | None = None
    metrics: list[str] | None = None
    included_columns: list[str] | None = None
    excluded_columns: list[str] | None = None
    random_seed: int | None = None
    causal_interpretation_allowed: Literal[False] | None = None

    @model_validator(mode="after")
    def require_analysis_update(self) -> AnalysisSpecUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        for field in ("metrics", "included_columns", "excluded_columns"):
            values = getattr(self, field)
            if values is not None and len(values) != len(set(values)):
                raise ValueError(f"{field} must not contain duplicates")
        return self


class AnalysisSpec(AnalysisSpecBase):
    spec_id: str
    project_id: str
    revision: int = Field(ge=1)
    status: Literal["draft", "confirmed", "superseded"]
    validation_warnings: list[str]
    created_at: datetime
    updated_at: datetime


class AnalysisSpecPage(BaseModel):
    items: list[AnalysisSpec]
    page: int
    page_size: int
    total: int
    has_more: bool


class AnalysisRunCreate(StrictModel):
    analysis_spec_id: str
    dataset_version_id: str
    run_kind: Literal["eda", "analysis", "model", "full"] = "full"


class AnalysisStep(BaseModel):
    step_id: str
    name: str
    tool_name: str | None
    tool_version: str | None
    status: Literal[
        "pending",
        "running",
        "succeeded",
        "failed",
        "skipped",
        "blocked",
        "cancelled",
    ]
    order: int = Field(ge=1)
    started_at: datetime | None
    completed_at: datetime | None
    artifact_ids: list[str]
    error: JobError | None = None


class AnalysisRun(BaseModel):
    run_id: str
    project_id: str
    dataset_version_id: str
    analysis_spec_id: str
    source_run_id: str | None
    run_kind: Literal["eda", "analysis", "model", "full"]
    status: Literal["queued", "running", "blocked", "succeeded", "failed", "cancelled"]
    progress: int = Field(ge=0, le=100)
    current_step_id: str | None
    steps: list[AnalysisStep]
    environment: dict[str, Any]
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error: JobError | None


class AnalysisRunPage(BaseModel):
    items: list[AnalysisRun]
    page: int
    page_size: int
    total: int
    has_more: bool


class Artifact(BaseModel):
    artifact_id: str
    project_id: str
    run_id: str | None
    dataset_version_id: str
    type: Literal["metric", "table", "chart", "model", "file", "log", "comparison"]
    name: str
    producer: str
    producer_version: str
    status: Literal["creating", "ready", "failed", "expired"]
    parameters: dict[str, Any]
    result: Any | None
    preview: Any | None
    checksum: str
    downloadable: bool
    created_at: datetime


class ArtifactPage(BaseModel):
    items: list[Artifact]
    page: int
    page_size: int
    total: int
    has_more: bool


class Claim(BaseModel):
    claim_id: str
    project_id: str
    run_id: str
    dataset_version_id: str
    text: str
    level: int = Field(ge=1, le=5)
    evidence_ids: list[str] = Field(min_length=1)
    limitations: list[str]
    validation_status: Literal["pending", "passed", "failed"]
    validation_messages: list[str]
    publication_status: Literal["draft", "published", "withdrawn"]
    created_at: datetime


class ClaimPage(BaseModel):
    items: list[Claim]
    page: int
    page_size: int
    total: int
    has_more: bool


class ReportExportRequest(StrictModel):
    run_id: str
    format: Literal["html", "notebook", "cleaned_data", "manifest", "ai_narrative"]
    claim_ids: list[str] | None = None
    include_code: bool = True
    include_evidence: bool = True
    data_format: Literal["csv", "parquet"] | None = None

    @model_validator(mode="after")
    def validate_data_format(self) -> ReportExportRequest:
        if self.format == "cleaned_data" and self.data_format is None:
            raise ValueError("data_format is required for cleaned_data export")
        if self.format != "cleaned_data" and self.data_format is not None:
            raise ValueError("data_format is only supported for cleaned_data export")
        return self


class Download(BaseModel):
    download_url: str
    file_name: str
    content_type: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    expires_at: datetime


class AssistantConversationCreate(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    dataset_version_id: str | None = None


class AssistantConversationUpdate(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    status: Literal["active", "archived"] | None = None
    dataset_version_id: str | None = None

    @model_validator(mode="after")
    def require_change(self) -> AssistantConversationUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        return self


class AssistantConversation(BaseModel):
    conversation_id: str
    project_id: str
    title: str
    status: Literal["active", "archived"]
    dataset_version_id: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class AssistantConversationPage(BaseModel):
    items: list[AssistantConversation]
    page: int
    page_size: int
    total: int
    has_more: bool


class AssistantMemory(BaseModel):
    conversation_id: str
    dataset_version_id: str | None
    memory_version: str
    session_state: dict[str, Any]
    user_preferences: list[dict[str, Any]]
    verified_facts: list[dict[str, Any]]
    pending_decisions: list[dict[str, Any]]
    updated_at: datetime


class AssistantMessageCreate(StrictModel):
    content: str = Field(min_length=1, max_length=12000)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content must not be blank")
        return value


class AssistantToolCall(BaseModel):
    tool_call_id: str
    tool_name: str
    tool_version: str
    status: Literal["proposed", "approved", "running", "succeeded", "failed", "rejected"]
    requires_confirmation: bool
    arguments: dict[str, Any]
    result: dict[str, Any] | None
    result_resource_type: str | None
    result_resource_id: str | None


class AssistantToolCallUpdate(StrictModel):
    arguments: dict[str, Any]


class AssistantTraceToolCall(BaseModel):
    tool_call_id: str
    llm_run_id: str
    tool_name: str
    tool_version: str
    status: Literal["proposed", "approved", "running", "succeeded", "failed", "rejected"]
    requires_confirmation: bool
    arguments: dict[str, Any]
    result: dict[str, Any] | None
    result_resource_type: str | None
    result_resource_id: str | None
    error: dict[str, Any] | None
    created_at: datetime
    completed_at: datetime | None


class AssistantRunTrace(BaseModel):
    llm_run_id: str
    message_id: str
    project_id: str
    job_id: str | None
    provider: str
    model: str
    prompt_name: str
    prompt_version: str
    status: Literal["running", "awaiting_confirmation", "succeeded", "failed", "cancelled"]
    model_call_count: int = Field(ge=0)
    tool_call_count: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    context_manifest: dict[str, Any]
    error: dict[str, Any] | None
    tool_calls: list[AssistantTraceToolCall]
    created_at: datetime
    completed_at: datetime | None


class AssistantTraceCheck(BaseModel):
    name: Literal[
        "state_transitions",
        "run_terminal_state",
        "tool_call_count",
        "tool_terminal_states",
    ]
    passed: bool
    details: dict[str, Any]


class AssistantTraceReplay(BaseModel):
    trace: AssistantRunTrace
    verified: bool
    replayed_state: str
    checks: list[AssistantTraceCheck]


class AssistantReplayCandidate(StrictModel):
    label: str = Field(min_length=1, max_length=80)
    prompt_variant: Literal["current", "concise", "evidence_auditor"] = "current"
    model: str | None = Field(default=None, min_length=1, max_length=160)


class AssistantTraceCompareRequest(StrictModel):
    candidates: list[AssistantReplayCandidate] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def labels_are_unique(self) -> AssistantTraceCompareRequest:
        labels = [candidate.label for candidate in self.candidates]
        if len(labels) != len(set(labels)):
            raise ValueError("candidate labels must be unique")
        return self


class AssistantReplayCandidateResult(BaseModel):
    label: str
    model: str
    prompt_variant: str
    answer: AssistantAnswer
    citation_valid: bool
    validation_error: str | None
    similarity_to_original: float = Field(ge=0, le=1)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)


class AssistantTraceCompareResult(BaseModel):
    source_message_id: str
    source_run_id: str
    replay_mode: Literal["counterfactual_no_tools"]
    candidates: list[AssistantReplayCandidateResult]


class AssistantMessage(BaseModel):
    message_id: str
    conversation_id: str
    role: Literal["user", "assistant", "system_event", "tool"]
    status: Literal[
        "queued",
        "processing",
        "awaiting_confirmation",
        "completed",
        "failed",
        "cancelled",
    ]
    content: str | None
    plan: AssistantPlan | None
    answer: AssistantAnswer | None
    tool_calls: list[AssistantToolCall]
    parent_message_id: str | None
    job_id: str | None
    created_at: datetime
    completed_at: datetime | None


class AssistantMessagePage(BaseModel):
    items: list[AssistantMessage]
    page: int
    page_size: int
    total: int
    has_more: bool


class AssistantConfirmationRequest(StrictModel):
    decision: Literal["approve", "reject"]
    tool_call_ids: list[str] = Field(default_factory=list, max_length=8)
    reason: str | None = Field(default=None, max_length=2000)

    @field_validator("tool_call_ids")
    @classmethod
    def unique_tool_calls(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("tool_call_ids must be unique")
        return value


class AssistantFeedbackRequest(StrictModel):
    rating: Literal["helpful", "not_helpful"]
    reason: (
        Literal[
            "incorrect",
            "unsupported",
            "incomplete",
            "unsafe",
            "hard_to_understand",
            "other",
        ]
        | None
    ) = None
    comment: str | None = Field(default=None, max_length=2000)


class AssistantFeedback(BaseModel):
    feedback_id: str
    message_id: str
    rating: Literal["helpful", "not_helpful"]
    reason: str | None
    comment: str | None
    created_at: datetime


class AssistantMetrics(BaseModel):
    window_days: int = Field(ge=1, le=90)
    turn_count: int = Field(ge=0)
    succeeded_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    average_latency_ms: int = Field(ge=0)
    p95_latency_ms: int = Field(ge=0)
    tool_call_count: int = Field(ge=0)
    tool_succeeded_count: int = Field(ge=0)
    tool_failed_count: int = Field(ge=0)
    tool_rejected_count: int = Field(ge=0)


class JobError(BaseModel):
    code: str
    message: str
    request_id: str
    retryable: bool
    details: dict[str, Any]


class Job(BaseModel):
    job_id: str
    kind: Literal[
        "dataset_ingestion",
        "version_comparison",
        "quality_scan",
        "cleaning_preview",
        "cleaning_execute",
        "analysis_run",
        "report_export",
        "assistant_turn",
    ]
    status: Literal[
        "queued",
        "running",
        "cancelling",
        "cancelled",
        "blocked",
        "succeeded",
        "failed",
    ]
    progress: int = Field(ge=0, le=100)
    current_step: str | None
    resource_type: str | None
    resource_id: str | None
    retry_after_ms: int | None
    created_at: datetime
    updated_at: datetime
    error: JobError | None


class AssistantTurnAccepted(BaseModel):
    user_message: AssistantMessage | None
    assistant_message: AssistantMessage
    job: Job | None
