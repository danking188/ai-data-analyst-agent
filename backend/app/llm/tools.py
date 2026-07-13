from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.errors import DomainError, not_found
from app.persistence.orm.models import DatasetVersionRow, ProjectRow
from app.persistence.orm.workflow_models import (
    AnalysisRunRow,
    ArtifactRow,
    ClaimRow,
    ColumnSchemaRow,
    QualityIssueRow,
)


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyArguments(ToolArguments):
    pass


class VersionArguments(ToolArguments):
    dataset_version_id: str | None = None


class QualityArguments(VersionArguments):
    severity: Literal["low", "medium", "high", "critical"] | None = None
    status: Literal["open", "accepted", "resolved", "ignored"] | None = None
    limit: int = Field(default=20, ge=1, le=50)


class ArtifactSearchArguments(VersionArguments):
    run_id: str | None = None
    artifact_type: (
        Literal["metric", "table", "chart", "model", "file", "log", "comparison"] | None
    ) = None
    limit: int = Field(default=20, ge=1, le=50)


class ClaimSearchArguments(VersionArguments):
    run_id: str | None = None
    limit: int = Field(default=20, ge=1, le=50)


class RunStatusArguments(ToolArguments):
    run_id: str | None = None
    limit: int = Field(default=10, ge=1, le=20)


@dataclass(frozen=True, slots=True)
class AssistantToolContext:
    project_id: str
    dataset_version_id: str | None


@dataclass(frozen=True, slots=True)
class AssistantToolResult:
    tool_name: str
    tool_version: str
    data: dict[str, Any]
    citation_sources: dict[str, str]
    resource_type: str | None = None
    resource_id: str | None = None


@dataclass(frozen=True, slots=True)
class AssistantToolDefinition:
    name: str
    version: str
    arguments_schema: type[ToolArguments]
    read_only: bool = True
    requires_confirmation: bool = False


DEFINITIONS = {
    item.name: item
    for item in (
        AssistantToolDefinition("project.get_context", "1.0.0", EmptyArguments),
        AssistantToolDefinition("schema.get", "1.0.0", VersionArguments),
        AssistantToolDefinition("quality.list_issues", "1.0.0", QualityArguments),
        AssistantToolDefinition("artifact.search", "1.0.0", ArtifactSearchArguments),
        AssistantToolDefinition("claim.search", "1.0.0", ClaimSearchArguments),
        AssistantToolDefinition("run.get_status", "1.0.0", RunStatusArguments),
    )
}


class AssistantToolRegistry:
    """Project-bound, read-only tools available to the P2 assistant runtime."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @property
    def definitions(self) -> tuple[AssistantToolDefinition, ...]:
        return tuple(DEFINITIONS.values())

    def execute(
        self,
        tool_name: str,
        *,
        context: AssistantToolContext,
        arguments: dict[str, Any] | None = None,
    ) -> AssistantToolResult:
        definition = DEFINITIONS.get(tool_name)
        if definition is None or not definition.read_only:
            raise DomainError(
                "LLM_TOOL_NOT_ALLOWED",
                "请求的工具未被允许",
                409,
                details={"tool_name": tool_name},
            )
        parsed = definition.arguments_schema.model_validate(arguments or {})
        handler = getattr(self, f"_{tool_name.replace('.', '_')}")
        return cast(AssistantToolResult, handler(context, parsed))

    def _project_get_context(
        self, context: AssistantToolContext, arguments: EmptyArguments
    ) -> AssistantToolResult:
        del arguments
        project = self.session.scalar(
            select(ProjectRow).where(ProjectRow.project_id == context.project_id)
        )
        if project is None:
            raise not_found()
        version = None
        if context.dataset_version_id:
            version = self._version(context, context.dataset_version_id)
        data = {
            "project": {
                "project_id": project.project_id,
                "name": project.name,
                "language": project.language,
                "timezone": project.timezone,
            },
            "dataset_version": self._version_data(version) if version else None,
        }
        return AssistantToolResult("project.get_context", "1.0.0", data, {})

    def _schema_get(
        self, context: AssistantToolContext, arguments: VersionArguments
    ) -> AssistantToolResult:
        version_id = self._resolve_version(context, arguments.dataset_version_id)
        rows = list(
            self.session.scalars(
                select(ColumnSchemaRow)
                .where(
                    ColumnSchemaRow.project_id == context.project_id,
                    ColumnSchemaRow.dataset_version_id == version_id,
                )
                .order_by(ColumnSchemaRow.ordinal_position)
            )
        )
        data = {
            "dataset_version_id": version_id,
            "columns": [
                {
                    "column_schema_id": row.column_schema_id,
                    "name": row.name,
                    "physical_type": row.physical_type,
                    "semantic_type": row.semantic_type,
                    "analysis_role": row.analysis_role,
                    "sensitive": row.sensitive,
                    "profile": row.profile_json,
                }
                for row in rows
            ],
        }
        sources = {
            row.column_schema_id: str(data["columns"][index]) for index, row in enumerate(rows)
        }
        return AssistantToolResult(
            "schema.get", "1.0.0", data, sources, "dataset_version", version_id
        )

    def _quality_list_issues(
        self, context: AssistantToolContext, arguments: QualityArguments
    ) -> AssistantToolResult:
        version_id = self._resolve_version(context, arguments.dataset_version_id)
        filters = [
            QualityIssueRow.project_id == context.project_id,
            QualityIssueRow.dataset_version_id == version_id,
        ]
        if arguments.severity:
            filters.append(QualityIssueRow.severity == arguments.severity)
        if arguments.status:
            filters.append(QualityIssueRow.status == arguments.status)
        rows = list(
            self.session.scalars(
                select(QualityIssueRow)
                .where(*filters)
                .order_by(QualityIssueRow.severity.desc(), QualityIssueRow.issue_id)
                .limit(arguments.limit)
            )
        )
        issues = [
            {
                "issue_id": row.issue_id,
                "issue_type": row.issue_type,
                "column": row.column_name,
                "severity": row.severity,
                "status": row.status,
                "title": row.title,
                "explanation": row.explanation,
                "metrics": row.metrics_json,
                "recommendation": row.recommendation,
            }
            for row in rows
        ]
        return AssistantToolResult(
            "quality.list_issues",
            "1.0.0",
            {"dataset_version_id": version_id, "issues": issues},
            {row.issue_id: str(issues[index]) for index, row in enumerate(rows)},
            "dataset_version",
            version_id,
        )

    def _artifact_search(
        self, context: AssistantToolContext, arguments: ArtifactSearchArguments
    ) -> AssistantToolResult:
        filters = [ArtifactRow.project_id == context.project_id, ArtifactRow.status == "ready"]
        if arguments.dataset_version_id or context.dataset_version_id:
            filters.append(
                ArtifactRow.dataset_version_id
                == self._resolve_version(context, arguments.dataset_version_id)
            )
        if arguments.run_id:
            filters.append(ArtifactRow.run_id == arguments.run_id)
        if arguments.artifact_type:
            filters.append(ArtifactRow.type == arguments.artifact_type)
        rows = list(
            self.session.scalars(
                select(ArtifactRow)
                .where(*filters)
                .order_by(ArtifactRow.created_at.desc(), ArtifactRow.artifact_id)
                .limit(arguments.limit)
            )
        )
        artifacts = [
            {
                "artifact_id": row.artifact_id,
                "run_id": row.run_id,
                "dataset_version_id": row.dataset_version_id,
                "type": row.type,
                "name": row.name,
                "producer": row.producer,
                "result": row.result_json,
            }
            for row in rows
        ]
        return AssistantToolResult(
            "artifact.search",
            "1.0.0",
            {"artifacts": artifacts},
            {row.artifact_id: str(artifacts[index]) for index, row in enumerate(rows)},
        )

    def _claim_search(
        self, context: AssistantToolContext, arguments: ClaimSearchArguments
    ) -> AssistantToolResult:
        filters = [
            ClaimRow.project_id == context.project_id,
            ClaimRow.validation_status == "passed",
        ]
        if arguments.dataset_version_id or context.dataset_version_id:
            filters.append(
                ClaimRow.dataset_version_id
                == self._resolve_version(context, arguments.dataset_version_id)
            )
        if arguments.run_id:
            filters.append(ClaimRow.run_id == arguments.run_id)
        rows = list(
            self.session.scalars(
                select(ClaimRow)
                .where(*filters)
                .order_by(ClaimRow.created_at.desc(), ClaimRow.claim_id)
                .limit(arguments.limit)
            )
        )
        claims = [
            {
                "claim_id": row.claim_id,
                "run_id": row.run_id,
                "dataset_version_id": row.dataset_version_id,
                "text": row.text,
                "level": row.level,
                "limitations": row.limitations_json,
            }
            for row in rows
        ]
        return AssistantToolResult(
            "claim.search",
            "1.0.0",
            {"claims": claims},
            {row.claim_id: row.text for row in rows},
        )

    def _run_get_status(
        self, context: AssistantToolContext, arguments: RunStatusArguments
    ) -> AssistantToolResult:
        filters = [AnalysisRunRow.project_id == context.project_id]
        if arguments.run_id:
            filters.append(AnalysisRunRow.run_id == arguments.run_id)
        rows = list(
            self.session.scalars(
                select(AnalysisRunRow)
                .where(*filters)
                .order_by(AnalysisRunRow.created_at.desc(), AnalysisRunRow.run_id)
                .limit(1 if arguments.run_id else arguments.limit)
            )
        )
        if arguments.run_id and not rows:
            raise not_found()
        runs = [
            {
                "run_id": row.run_id,
                "dataset_version_id": row.dataset_version_id,
                "run_kind": row.run_kind,
                "status": row.status,
                "progress": row.progress,
                "created_at": row.created_at.isoformat(),
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            }
            for row in rows
        ]
        return AssistantToolResult(
            "run.get_status",
            "1.0.0",
            {"runs": runs},
            {row.run_id: str(runs[index]) for index, row in enumerate(rows)},
        )

    def _resolve_version(self, context: AssistantToolContext, requested: str | None) -> str:
        version_id = requested or context.dataset_version_id
        if not version_id:
            raise DomainError(
                "ASSISTANT_DATASET_REQUIRED",
                "请先为会话选择一个数据版本",
                409,
            )
        self._version(context, version_id)
        return version_id

    def _version(self, context: AssistantToolContext, version_id: str) -> DatasetVersionRow:
        row = self.session.scalar(
            select(DatasetVersionRow).where(
                DatasetVersionRow.project_id == context.project_id,
                DatasetVersionRow.version_id == version_id,
            )
        )
        if row is None:
            raise not_found()
        return row

    @staticmethod
    def _version_data(row: DatasetVersionRow) -> dict[str, Any]:
        return {
            "version_id": row.version_id,
            "dataset_id": row.dataset_id,
            "status": row.status,
            "kind": row.kind,
            "row_count": row.row_count,
            "column_count": row.column_count,
        }
