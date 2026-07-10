from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    CleaningDecision,
    CleaningOperation,
    CleaningPlan,
    CleaningPlanCreate,
    CleaningPlanPage,
    CleaningPlanUpdate,
)
from app.cleaning.registry import validate_cleaning_operations
from app.core.clock import utc_now
from app.core.ids import new_id
from app.domain.errors import not_found, permission_denied, state_conflict
from app.persistence.orm.models import DatasetVersionRow
from app.persistence.orm.workflow_models import (
    CleaningOperationRow,
    CleaningPlanRow,
    ColumnSchemaRow,
    QualityIssueRow,
    UserDecisionRow,
)
from app.persistence.repositories.audit import AuditRepository
from app.persistence.repositories.cleaning import CleaningPlanRepository
from app.persistence.repositories.datasets import DatasetRepository, DatasetVersionDraft
from app.persistence.repositories.projects import ProjectRepository


def operation_to_schema(row: CleaningOperationRow) -> CleaningOperation:
    return CleaningOperation(
        operation_id=row.operation_id,
        operation=row.operation,
        column=row.column_name,
        parameters=row.parameters_json,
        reason=row.reason,
        issue_ids=row.issue_ids_json,
        estimated_affected_rows=row.estimated_affected_rows,
        risk_level=row.risk_level,
        reversible=row.reversible,
    )


class CleaningService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.projects = ProjectRepository(session)
        self.plans = CleaningPlanRepository(session)

    def require_project_access(
        self,
        project_id: str,
        subject_id: str,
        *,
        edit: bool,
    ) -> None:
        membership = self.projects.get_for_subject(project_id, subject_id)
        if membership is None:
            raise not_found()
        project, role = membership
        if edit and project.status != "active":
            raise state_conflict("归档项目不能修改清洗计划")
        if edit and role not in {"owner", "editor"}:
            raise permission_denied()

    def require_source_version(
        self,
        project_id: str,
        version_id: str,
    ) -> DatasetVersionRow:
        version = self.session.get(DatasetVersionRow, version_id)
        if version is None or version.project_id != project_id:
            raise not_found()
        if version.status != "ready" or not version.data_storage_key:
            raise state_conflict("只有 ready 数据版本可以创建清洗计划")
        return version

    def to_schema(self, row: CleaningPlanRow) -> CleaningPlan:
        return CleaningPlan(
            plan_id=row.plan_id,
            project_id=row.project_id,
            source_version_id=row.source_version_id,
            result_version_id=row.result_version_id,
            name=row.name,
            status=row.status,
            operations=[
                operation_to_schema(operation)
                for operation in self.plans.list_operations(row.plan_id)
            ],
            preview_artifact_id=row.preview_artifact_id,
            decision=row.decision,
            decision_reason=row.decision_reason,
            revision=row.revision,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def list(
        self,
        project_id: str,
        *,
        subject_id: str,
        page: int,
        page_size: int,
        source_version_id: str | None,
    ) -> CleaningPlanPage:
        self.require_project_access(project_id, subject_id, edit=False)
        result = self.plans.list_page(
            project_id=project_id,
            page=page,
            page_size=page_size,
            source_version_id=source_version_id,
        )
        return CleaningPlanPage(
            items=[self.to_schema(row) for row in result.items],
            page=page,
            page_size=page_size,
            total=result.total,
            has_more=result.has_more,
        )

    def get(
        self,
        project_id: str,
        plan_id: str,
        *,
        subject_id: str,
        edit: bool = False,
    ) -> CleaningPlanRow:
        self.require_project_access(project_id, subject_id, edit=edit)
        return self.plans.get(project_id=project_id, plan_id=plan_id)

    def create(
        self,
        project_id: str,
        payload: CleaningPlanCreate,
        *,
        subject_id: str,
        request_id: str,
    ) -> CleaningPlan:
        self.require_project_access(project_id, subject_id, edit=True)
        self.require_source_version(project_id, payload.source_version_id)
        self._validate_operations(payload.source_version_id, payload.operations)
        row = self.plans.create(
            project_id=project_id,
            source_version_id=payload.source_version_id,
            name=payload.name or "数据清洗计划",
            operations=payload.operations,
            subject_id=subject_id,
        )
        AuditRepository(self.session).append(
            action="cleaning_plan.created",
            result="success",
            summary={"operation_count": len(payload.operations)},
            project_id=project_id,
            subject_id=subject_id,
            object_type="cleaning_plan",
            object_id=row.plan_id,
            request_id=request_id,
        )
        return self.to_schema(row)

    def update(
        self,
        project_id: str,
        plan_id: str,
        payload: CleaningPlanUpdate,
        *,
        expected_revision: int,
        subject_id: str,
        request_id: str,
    ) -> CleaningPlan:
        row = self.get(project_id, plan_id, subject_id=subject_id, edit=True)
        if payload.operations is not None:
            self._validate_operations(row.source_version_id, payload.operations)
        row = self.plans.update_draft(
            row,
            expected_revision=expected_revision,
            name=payload.name,
            operations=payload.operations,
        )
        AuditRepository(self.session).append(
            action="cleaning_plan.updated",
            result="success",
            summary={"fields": sorted(payload.model_fields_set)},
            project_id=project_id,
            subject_id=subject_id,
            object_type="cleaning_plan",
            object_id=plan_id,
            request_id=request_id,
        )
        return self.to_schema(row)

    def decide(
        self,
        project_id: str,
        plan_id: str,
        payload: CleaningDecision,
        *,
        subject_id: str,
        request_id: str,
    ) -> CleaningPlan:
        row = self.get(project_id, plan_id, subject_id=subject_id, edit=True)
        row = self.plans.decide(
            row,
            decision=payload.decision,
            reason=payload.reason,
            subject_id=subject_id,
        )
        self.session.add(
            UserDecisionRow(
                decision_id=new_id("decision_"),
                project_id=project_id,
                subject_id=subject_id,
                object_type="cleaning_plan",
                object_id=plan_id,
                action=payload.decision,
                reason=payload.reason,
                payload_json=payload.model_dump(mode="json"),
                created_at=utc_now(),
            )
        )
        AuditRepository(self.session).append(
            action="cleaning_plan.decided",
            result="success",
            summary=payload.model_dump(mode="json"),
            project_id=project_id,
            subject_id=subject_id,
            object_type="cleaning_plan",
            object_id=plan_id,
            request_id=request_id,
        )
        return self.to_schema(row)

    def prepare_execution(
        self,
        project_id: str,
        plan_id: str,
        *,
        subject_id: str,
    ) -> tuple[CleaningPlanRow, DatasetVersionRow]:
        plan = self.get(project_id, plan_id, subject_id=subject_id, edit=True)
        source = self.require_source_version(project_id, plan.source_version_id)
        if plan.status != "approved":
            raise state_conflict("只有 approved 清洗计划可以执行", status=plan.status)
        result = DatasetRepository(self.session).create_version(
            project_id=project_id,
            dataset_id=source.dataset_id,
            subject_id=subject_id,
            draft=DatasetVersionDraft(
                source_file_name=source.source_file_name,
                source_type=source.source_type,
                source_storage_key=source.source_storage_key,
                file_hash=source.file_hash,
                file_size_bytes=source.file_size_bytes,
                sheet_name=source.sheet_name,
                parse_options=source.parse_options_json,
                parent_version_id=source.version_id,
                kind="cleaned",
                operation_summary=f"执行清洗计划：{plan.name}",
            ),
        )
        self.plans.mark_executing(plan, result_version_id=result.version_id)
        return plan, result

    def _validate_operations(
        self,
        version_id: str,
        operations: Sequence[CleaningOperation],
    ) -> None:
        columns = set(
            self.session.scalars(
                select(ColumnSchemaRow.name).where(ColumnSchemaRow.dataset_version_id == version_id)
            )
        )
        issue_ids = set(
            self.session.scalars(
                select(QualityIssueRow.issue_id).where(
                    QualityIssueRow.dataset_version_id == version_id
                )
            )
        )
        validate_cleaning_operations(
            list(operations),
            columns=columns,
            issue_ids=issue_ids,
        )
