from enum import StrEnum


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class ProjectRole(StrEnum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class JobKind(StrEnum):
    DATASET_INGESTION = "dataset_ingestion"
    VERSION_COMPARISON = "version_comparison"
    QUALITY_SCAN = "quality_scan"
    CLEANING_PREVIEW = "cleaning_preview"
    CLEANING_EXECUTE = "cleaning_execute"
    ANALYSIS_RUN = "analysis_run"
    REPORT_EXPORT = "report_export"


TERMINAL_JOB_STATUSES = {
    JobStatus.CANCELLED,
    JobStatus.BLOCKED,
    JobStatus.SUCCEEDED,
    JobStatus.FAILED,
}
