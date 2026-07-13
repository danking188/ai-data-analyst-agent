from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    AnalysisRunCreate,
    AnalysisSpecCreate,
    CleaningDecision,
    CleaningOperation,
    CleaningPlanCreate,
)
from app.core.ids import new_id
from app.domain.errors import DomainError, validation_error
from app.llm.action_schemas import (
    AnalysisSpecDraft,
    CleaningPlanDraft,
    FeatureSuggestionDraft,
)
from app.persistence.orm.workflow_models import ColumnSchemaRow
from app.persistence.repositories.jobs import JobRepository
from app.persistence.repositories.runs import AnalysisRunRepository
from app.services.analysis_specs import AnalysisSpecService
from app.services.cleaning import CleaningService
from app.services.runs import AnalysisRunService


class _StrictActionArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalysisRunArguments(_StrictActionArgs):
    run_kind: str = Field(default="full", pattern="^(eda|analysis|model|full)$")
    analysis_spec_id: str | None = None


class EmptyActionArguments(_StrictActionArgs):
    pass


@dataclass(frozen=True, slots=True)
class ActionExecution:
    tool_name: str
    resource_type: str | None
    resource_id: str | None
    result: dict[str, Any]
    child_job_id: str | None = None
    child_job_kind: str | None = None


class AssistantActionRegistry:
    """Validated P3 actions that delegate to the existing deterministic services."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def validate_arguments(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        project_id: str,
        dataset_version_id: str | None,
    ) -> dict[str, Any]:
        version_id = self._require_version(dataset_version_id)
        if tool_name == "analysis.draft_spec":
            analysis_draft = AnalysisSpecDraft.model_validate(arguments)
            analysis_payload = self.analysis_spec_payload(analysis_draft, version_id)
            warnings = AnalysisSpecService(self.session).validate(project_id, analysis_payload)
            return {
                **analysis_draft.model_dump(mode="json"),
                "validation_warnings": warnings,
            }
        if tool_name == "analysis.run":
            return AnalysisRunArguments.model_validate(arguments).model_dump(mode="json")
        if tool_name == "cleaning.draft_plan":
            cleaning_draft = CleaningPlanDraft.model_validate(arguments)
            cleaning_payload = self.cleaning_plan_payload(cleaning_draft, version_id)
            cleaning_service = CleaningService(self.session)
            cleaning_service.require_source_version(project_id, version_id)
            cleaning_service._validate_operations(version_id, cleaning_payload.operations)
            return cleaning_draft.model_dump(mode="json")
        if tool_name == "cleaning.execute":
            return EmptyActionArguments.model_validate(arguments).model_dump(mode="json")
        if tool_name == "feature_engineering.suggest":
            draft = FeatureSuggestionDraft.model_validate(arguments)
            rows = list(
                self.session.scalars(
                    select(ColumnSchemaRow).where(
                        ColumnSchemaRow.project_id == project_id,
                        ColumnSchemaRow.dataset_version_id == version_id,
                    )
                )
            )
            columns = {row.name: row for row in rows}
            referenced = {
                column for suggestion in draft.suggestions for column in suggestion.source_columns
            }
            unknown = sorted(referenced - set(columns))
            if unknown:
                raise validation_error("特征建议引用了不存在的字段", columns=unknown)
            sensitive = sorted(column for column in referenced if columns[column].sensitive)
            if sensitive:
                raise validation_error("敏感字段不能进入自动特征建议", columns=sensitive)
            return draft.model_dump(mode="json")
        raise DomainError(
            "LLM_TOOL_NOT_ALLOWED",
            "请求的受控操作未被允许",
            409,
            details={"tool_name": tool_name},
        )

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        project_id: str,
        dataset_version_id: str | None,
        subject_id: str,
        request_id: str,
        resources: dict[str, str],
    ) -> ActionExecution:
        canonical = self.validate_arguments(
            tool_name,
            arguments,
            project_id=project_id,
            dataset_version_id=dataset_version_id,
        )
        version_id = self._require_version(dataset_version_id)
        if tool_name == "analysis.draft_spec":
            analysis_draft = AnalysisSpecDraft.model_validate(canonical)
            created_spec = AnalysisSpecService(self.session).create(
                project_id,
                self.analysis_spec_payload(analysis_draft, version_id),
                subject_id=subject_id,
                request_id=request_id,
            )
            return ActionExecution(
                tool_name,
                "analysis_spec",
                created_spec.spec_id,
                {
                    "analysis_spec": created_spec.model_dump(mode="json"),
                    "rationale": analysis_draft.rationale,
                },
            )
        if tool_name == "analysis.run":
            parsed = AnalysisRunArguments.model_validate(canonical)
            spec_id = parsed.analysis_spec_id or resources.get("analysis_spec")
            if spec_id is None:
                raise DomainError(
                    "LLM_ACTION_DEPENDENCY_MISSING", "运行分析前缺少 AnalysisSpec", 409
                )
            spec_service = AnalysisSpecService(self.session)
            current = spec_service.get(project_id, spec_id, subject_id=subject_id, edit=True)
            if current.status == "draft":
                spec_service.confirm(
                    project_id,
                    spec_id,
                    subject_id=subject_id,
                    request_id=request_id,
                )
            payload = AnalysisRunCreate(
                analysis_spec_id=spec_id,
                dataset_version_id=version_id,
                run_kind=parsed.run_kind,
            )
            run_service = AnalysisRunService(self.session)
            confirmed_spec = run_service.require_confirmed_spec(project_id, payload)
            run_id = new_id("run_")
            job = JobRepository(self.session).create(
                project_id=project_id,
                kind="analysis_run",
                request={"run_id": run_id},
                subject_id=subject_id,
                job_id=new_id("job_"),
            )
            AnalysisRunRepository(self.session).create(
                run_id=run_id,
                project_id=project_id,
                dataset_version_id=version_id,
                spec_revision_id=confirmed_spec.spec_revision_id,
                run_kind=parsed.run_kind,
                job_id=job.job_id,
                random_seed=confirmed_spec.random_seed,
                subject_id=subject_id,
            )
            return ActionExecution(
                tool_name,
                "analysis_run",
                run_id,
                {"run_id": run_id, "analysis_spec_id": spec_id, "job_id": job.job_id},
                child_job_id=job.job_id,
                child_job_kind="analysis_run",
            )
        if tool_name == "cleaning.draft_plan":
            cleaning_draft = CleaningPlanDraft.model_validate(canonical)
            cleaning_service = CleaningService(self.session)
            created_plan = cleaning_service.create(
                project_id,
                self.cleaning_plan_payload(cleaning_draft, version_id),
                subject_id=subject_id,
                request_id=request_id,
            )
            source = cleaning_service.require_source_version(project_id, version_id)
            job = JobRepository(self.session).create(
                project_id=project_id,
                kind="cleaning_preview",
                request={
                    "cleaning_plan_id": created_plan.plan_id,
                    "dataset_id": source.dataset_id,
                },
                subject_id=subject_id,
                job_id=new_id("job_"),
            )
            return ActionExecution(
                tool_name,
                "cleaning_plan",
                created_plan.plan_id,
                {
                    "cleaning_plan": created_plan.model_dump(mode="json"),
                    "preview_job_id": job.job_id,
                },
                child_job_id=job.job_id,
                child_job_kind="cleaning_preview",
            )
        if tool_name == "cleaning.execute":
            EmptyActionArguments.model_validate(canonical)
            plan_id = resources.get("cleaning_plan")
            if plan_id is None:
                raise DomainError(
                    "LLM_ACTION_DEPENDENCY_MISSING", "执行清洗前缺少 CleaningPlan", 409
                )
            cleaning_service = CleaningService(self.session)
            current_plan = cleaning_service.get(
                project_id, plan_id, subject_id=subject_id, edit=True
            )
            if current_plan.status == "awaiting_approval":
                cleaning_service.decide(
                    project_id,
                    plan_id,
                    CleaningDecision(decision="approve", reason="用户已确认 Assistant 受控计划"),
                    subject_id=subject_id,
                    request_id=request_id,
                )
            executing_plan, result_version = cleaning_service.prepare_execution(
                project_id,
                plan_id,
                subject_id=subject_id,
            )
            job = JobRepository(self.session).create(
                project_id=project_id,
                kind="cleaning_execute",
                request={
                    "cleaning_plan_id": executing_plan.plan_id,
                    "dataset_id": result_version.dataset_id,
                    "result_version_id": result_version.version_id,
                },
                subject_id=subject_id,
                job_id=new_id("job_"),
            )
            return ActionExecution(
                tool_name,
                "dataset_version",
                result_version.version_id,
                {
                    "cleaning_plan_id": executing_plan.plan_id,
                    "result_version_id": result_version.version_id,
                    "job_id": job.job_id,
                },
                child_job_id=job.job_id,
                child_job_kind="cleaning_execute",
            )
        if tool_name == "feature_engineering.suggest":
            suggestion = FeatureSuggestionDraft.model_validate(canonical)
            artifact = self._create_feature_artifact(
                project_id=project_id,
                dataset_version_id=version_id,
                suggestion=suggestion,
            )
            return ActionExecution(
                tool_name,
                "artifact",
                artifact.artifact_id,
                {"artifact_id": artifact.artifact_id, **suggestion.model_dump(mode="json")},
            )
        raise DomainError("LLM_TOOL_NOT_ALLOWED", "请求的受控操作未被允许", 409)

    @staticmethod
    def analysis_spec_payload(
        draft: AnalysisSpecDraft, dataset_version_id: str
    ) -> AnalysisSpecCreate:
        values = draft.model_dump(
            exclude={"rationale", "leakage_warnings", "validation_warnings"},
            mode="python",
        )
        return AnalysisSpecCreate(
            dataset_version_id=dataset_version_id,
            causal_interpretation_allowed=False,
            **values,
        )

    @staticmethod
    def cleaning_plan_payload(
        draft: CleaningPlanDraft, dataset_version_id: str
    ) -> CleaningPlanCreate:
        operations = [
            CleaningOperation(
                operation_id=new_id("clnop_"),
                operation=item.operation,
                column=item.column,
                parameters=item.parameters,
                reason=item.reason,
                issue_ids=item.issue_ids,
                estimated_affected_rows=0,
                risk_level=item.risk_level,
                reversible=item.reversible,
            )
            for item in draft.operations
        ]
        return CleaningPlanCreate(
            source_version_id=dataset_version_id,
            name=draft.name,
            operations=operations,
        )

    def _create_feature_artifact(
        self,
        *,
        project_id: str,
        dataset_version_id: str,
        suggestion: FeatureSuggestionDraft,
    ) -> Any:
        from app.persistence.repositories.artifacts import ArtifactRepository

        return ArtifactRepository(self.session).create_assistant_artifact(
            project_id=project_id,
            dataset_version_id=dataset_version_id,
            name=suggestion.title,
            producer="feature_engineering.suggest",
            result=suggestion.model_dump(mode="json"),
        )

    @staticmethod
    def _require_version(dataset_version_id: str | None) -> str:
        if dataset_version_id is None:
            raise DomainError("DATASET_VERSION_REQUIRED", "该操作需要绑定 ready 数据版本", 409)
        return dataset_version_id
