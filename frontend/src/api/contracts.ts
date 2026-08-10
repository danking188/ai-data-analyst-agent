/**
 * Centralized frontend contract aliases.
 *
 * Source of truth: docs/api/openapi.yaml. Keep page components importing from
 * this module only. `pnpm generate:api` can additionally generate the complete
 * OpenAPI declaration file for contract diffing.
 */
export type ProjectStatus = "active" | "archived";
export type DatasetStatus = "active" | "archived";
export type DatasetVersionStatus = "creating" | "ready" | "failed" | "archived";
export type DatasetVersionKind = "raw" | "cleaned" | "modeled";
export type JobStatus =
  | "queued"
  | "running"
  | "cancelling"
  | "cancelled"
  | "blocked"
  | "succeeded"
  | "failed";
export type QualitySeverity = "low" | "medium" | "high" | "critical";
export type QualityIssueStatus = "open" | "accepted" | "resolved" | "ignored";
export type PhysicalType =
  | "integer"
  | "float"
  | "string"
  | "boolean"
  | "datetime"
  | "binary"
  | "unknown";
export type SemanticType =
  | "numeric"
  | "categorical"
  | "datetime"
  | "boolean"
  | "identifier"
  | "text"
  | "currency"
  | "percentage"
  | "ordinal"
  | "geographic_code"
  | "unknown";
export type AnalysisRole =
  | "feature"
  | "target"
  | "entity_key"
  | "time"
  | "identifier"
  | "text"
  | "excluded"
  | "undecided";

export interface Page<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  has_more: boolean;
}

export interface SystemCapabilities {
  api_version: string;
  supported_file_types: Array<"csv" | "xls" | "xlsx" | "parquet">;
  max_upload_bytes: number;
  natural_language_analysis: boolean;
  llm: {
    evidence_narrative: boolean;
    assistant: boolean;
  };
  auth_enabled: boolean;
  polling: {
    initial_interval_ms: number;
    steady_interval_ms: number;
    background_interval_ms: number;
  };
}

export interface AuthConfig {
  registration_enabled: boolean;
}

export interface Project {
  project_id: string;
  name: string;
  description: string | null;
  timezone: string;
  language: "zh-CN" | "en-US";
  status: ProjectStatus;
  current_dataset_version_id: string | null;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  description?: string | null;
  timezone: string;
  language: "zh-CN" | "en-US";
}

export interface Dataset {
  dataset_id: string;
  project_id: string;
  name: string;
  source_type: "csv" | "xls" | "xlsx" | "parquet";
  status: DatasetStatus;
  current_version_id: string | null;
  version_count: number;
  created_at: string;
}

export interface DatasetVersion {
  version_id: string;
  dataset_id: string;
  project_id: string;
  version_number: number;
  status: DatasetVersionStatus;
  kind: DatasetVersionKind;
  parent_version_id: string | null;
  source_file_name: string;
  sheet_name: string | null;
  file_hash: string;
  row_count: number;
  column_count: number;
  operation_summary: string | null;
  created_at: string;
}

export interface PreviewColumn {
  name: string;
  physical_type: string;
  semantic_type: string | null;
  masked: boolean;
}

export interface DataPreview {
  columns: PreviewColumn[];
  rows: Record<string, unknown>[];
  next_cursor: string | null;
  has_more: boolean;
  masked_columns: string[];
}

export interface ColumnSchema {
  name: string;
  physical_type: PhysicalType;
  semantic_type: SemanticType;
  analysis_role: AnalysisRole;
  confidence: number;
  evidence: string[];
  date_format: string | null;
  ordinal_values: string[] | null;
  sensitive: boolean;
  user_confirmed: boolean;
}

export interface DatasetSchema {
  dataset_version_id: string;
  revision: number;
  low_confidence_count: number;
  columns: ColumnSchema[];
}

export interface SchemaPatch {
  changes: Array<{
    column: string;
    semantic_type?: SemanticType;
    analysis_role?: AnalysisRole;
    date_format?: string | null;
    ordinal_values?: string[] | null;
    sensitive?: boolean;
  }>;
  reason?: string | null;
}

export type CleaningOperationType =
  | "impute_missing"
  | "drop_duplicates"
  | "cast_type"
  | "replace_values"
  | "normalize_category"
  | "filter_rows"
  | "add_missing_indicator";

export interface CleaningOperation {
  operation_id: string;
  operation: CleaningOperationType;
  column: string | null;
  parameters: Record<string, unknown>;
  reason: string;
  issue_ids: string[];
  estimated_affected_rows: number;
  risk_level: "low" | "medium" | "high";
  reversible: boolean;
}

export interface CleaningPlan {
  plan_id: string;
  project_id: string;
  source_version_id: string;
  result_version_id: string | null;
  name: string;
  status: "draft" | "awaiting_approval" | "approved" | "rejected" | "executing" | "executed" | "failed";
  operations: CleaningOperation[];
  preview_artifact_id: string | null;
  decision: "approve" | "reject" | null;
  decision_reason: string | null;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface AnalysisSpecInput {
  name: string;
  dataset_version_id: string;
  task: "descriptive" | "comparison" | "statistical_test" | "binary_classification" | "multiclass_classification" | "regression";
  target: string | null;
  entity_key: string | null;
  time_column: string | null;
  prediction_time_description: string | null;
  split_strategy: "none" | "random" | "stratified" | "temporal" | "group";
  group_column: string | null;
  metrics: string[];
  included_columns: string[];
  excluded_columns: string[];
  random_seed: number;
  causal_interpretation_allowed: false;
}

export interface AnalysisSpec extends AnalysisSpecInput {
  spec_id: string;
  project_id: string;
  revision: number;
  status: "draft" | "confirmed" | "superseded";
  validation_warnings: string[];
  created_at: string;
  updated_at: string;
}

export interface QualityIssue {
  issue_id: string;
  dataset_version_id: string;
  issue_type: string;
  column: string | null;
  severity: QualitySeverity;
  status: QualityIssueStatus;
  title: string;
  explanation: string;
  metrics: Record<string, unknown>;
  sample_rows: Record<string, unknown>[];
  recommendation: string | null;
  decision_reason: string | null;
  revision: number;
  created_at: string;
}

export interface ErrorDetail {
  code: string;
  message: string;
  request_id: string;
  retryable: boolean;
  details: Record<string, unknown>;
}

export interface Job {
  job_id: string;
  kind:
    | "dataset_ingestion"
    | "version_comparison"
    | "quality_scan"
    | "cleaning_preview"
    | "cleaning_execute"
    | "analysis_run"
    | "report_export"
    | "assistant_turn";
  status: JobStatus;
  progress: number;
  current_step: string | null;
  resource_type: string | null;
  resource_id: string | null;
  retry_after_ms: number | null;
  created_at: string;
  updated_at: string;
  error: ErrorDetail | null;
}

export interface AnalysisRun {
  run_id: string;
  project_id: string;
  dataset_version_id: string;
  analysis_spec_id: string;
  source_run_id: string | null;
  run_kind: "eda" | "analysis" | "model" | "full";
  status: "queued" | "running" | "blocked" | "succeeded" | "failed" | "cancelled";
  progress: number;
  current_step_id: string | null;
  steps: Array<{
    step_id: string;
    name: string;
    tool_name: string | null;
    tool_version: string | null;
    status: "pending" | "running" | "succeeded" | "failed" | "skipped" | "blocked" | "cancelled";
    order: number;
    started_at: string | null;
    completed_at: string | null;
    artifact_ids: string[];
    error: ErrorDetail | null;
  }>;
  environment: Record<string, unknown>;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error: ErrorDetail | null;
}

export interface Artifact {
  artifact_id: string;
  project_id: string;
  run_id: string | null;
  dataset_version_id: string;
  type: "metric" | "table" | "chart" | "model" | "file" | "log" | "comparison";
  name: string;
  producer: string;
  producer_version: string;
  status: "creating" | "ready" | "failed" | "expired";
  parameters: Record<string, unknown>;
  result: unknown;
  preview: unknown;
  checksum: string;
  downloadable: boolean;
  created_at: string;
}

export interface Claim {
  claim_id: string;
  project_id: string;
  run_id: string;
  dataset_version_id: string;
  text: string;
  level: 1 | 2 | 3 | 4 | 5;
  evidence_ids: string[];
  limitations: string[];
  validation_status: "pending" | "passed" | "failed";
  validation_messages: string[];
  publication_status: "draft" | "published" | "withdrawn";
  created_at: string;
}

export interface Download {
  download_url: string;
  file_name: string;
  content_type: string;
  expires_at: string;
}

export interface SessionInfo {
  subject_id: string;
  expires_in_seconds: number | null;
}

export interface ReportExportInput {
  run_id: string;
  format: "html" | "notebook" | "cleaned_data" | "manifest" | "ai_narrative";
  claim_ids: string[];
  include_code: boolean;
  include_evidence: boolean;
  data_format: "csv" | "parquet" | null;
}

export interface AssistantConversation {
  conversation_id: string;
  project_id: string;
  title: string;
  status: "active" | "archived";
  dataset_version_id: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface AssistantPlanStep {
  position: number;
  title: string;
  tool_name: string | null;
  purpose: string;
  requires_confirmation: boolean;
}

export interface AssistantPlan {
  objective: string;
  dataset_version_id: string | null;
  steps: AssistantPlanStep[];
  estimated_model_calls: number;
  estimated_tool_calls: number;
  limitations: string[];
}

export interface AssistantFinding {
  text: string;
  claim_level: number;
  citation_ids: string[];
  limitations: string[];
}

export interface AssistantAnswer {
  summary: string;
  findings: AssistantFinding[];
  next_actions: Array<{
    label: string;
    action_type: "ask" | "draft_spec" | "run_analysis" | "draft_cleaning" | "export_report";
    requires_confirmation: boolean;
  }>;
  limitations: string[];
}

export interface AssistantToolCall {
  tool_call_id: string;
  tool_name: string;
  tool_version: string;
  status: "proposed" | "approved" | "running" | "succeeded" | "failed" | "rejected";
  requires_confirmation: boolean;
  arguments: Record<string, unknown>;
  result: Record<string, unknown> | null;
  result_resource_type: string | null;
  result_resource_id: string | null;
}

export interface AssistantMessage {
  message_id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system_event" | "tool";
  status: "queued" | "processing" | "awaiting_confirmation" | "completed" | "failed" | "cancelled";
  content: string | null;
  plan: AssistantPlan | null;
  answer: AssistantAnswer | null;
  tool_calls: AssistantToolCall[];
  parent_message_id: string | null;
  job_id: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface AssistantTurnAccepted {
  user_message: AssistantMessage | null;
  assistant_message: AssistantMessage;
  job: Job | null;
}

export interface AssistantFeedback {
  feedback_id: string;
  message_id: string;
  rating: "helpful" | "not_helpful";
  reason: string | null;
  comment: string | null;
  created_at: string;
}

export interface AssistantMetrics {
  window_days: number;
  turn_count: number;
  succeeded_count: number;
  failed_count: number;
  input_tokens: number;
  output_tokens: number;
  average_latency_ms: number;
  p95_latency_ms: number;
  tool_call_count: number;
  tool_succeeded_count: number;
  tool_failed_count: number;
  tool_rejected_count: number;
}
