from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.schemas import CleaningOperation
from app.core.clock import utc_now
from app.core.ids import new_id
from app.domain.errors import not_found, state_conflict, version_conflict
from app.persistence.orm.workflow_models import CleaningOperationRow, CleaningPlanRow
from app.persistence.repositories.projects import Page


class CleaningPlanRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        project_id: str,
        source_version_id: str,
        name: str,
        operations: list[CleaningOperation],
        subject_id: str,
    ) -> CleaningPlanRow:
        now = utc_now()
        plan = CleaningPlanRow(
            plan_id=new_id("cln_"),
            project_id=project_id,
            source_version_id=source_version_id,
            result_version_id=None,
            name=name,
            status="draft",
            preview_artifact_id=None,
            decision=None,
            decision_reason=None,
            decided_by=None,
            decided_at=None,
            revision=1,
            created_by=subject_id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(plan)
        self.session.flush()
        self._replace_operations(plan.plan_id, operations)
        return plan

    def get(self, *, project_id: str, plan_id: str) -> CleaningPlanRow:
        plan = self.session.scalar(
            select(CleaningPlanRow).where(
                CleaningPlanRow.project_id == project_id,
                CleaningPlanRow.plan_id == plan_id,
            )
        )
        if plan is None:
            raise not_found()
        return plan

    def list_page(
        self,
        *,
        project_id: str,
        page: int,
        page_size: int,
        source_version_id: str | None,
    ) -> Page[CleaningPlanRow]:
        filters = [CleaningPlanRow.project_id == project_id]
        if source_version_id is not None:
            filters.append(CleaningPlanRow.source_version_id == source_version_id)
        total = int(
            self.session.scalar(select(func.count()).select_from(CleaningPlanRow).where(*filters))
            or 0
        )
        rows = list(
            self.session.scalars(
                select(CleaningPlanRow)
                .where(*filters)
                .order_by(CleaningPlanRow.created_at.desc(), CleaningPlanRow.plan_id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return Page(rows, page, page_size, total)

    def list_operations(self, plan_id: str) -> list[CleaningOperationRow]:
        return list(
            self.session.scalars(
                select(CleaningOperationRow)
                .where(CleaningOperationRow.plan_id == plan_id)
                .order_by(CleaningOperationRow.position)
            )
        )

    def update_draft(
        self,
        plan: CleaningPlanRow,
        *,
        expected_revision: int,
        name: str | None,
        operations: list[CleaningOperation] | None,
    ) -> CleaningPlanRow:
        if plan.revision != expected_revision:
            raise version_conflict(plan.revision)
        if plan.status != "draft":
            raise state_conflict("只有 draft 清洗计划可以编辑", status=plan.status)
        if name is not None:
            plan.name = name
        if operations is not None:
            self._replace_operations(plan.plan_id, operations)
            plan.preview_artifact_id = None
        plan.revision += 1
        plan.updated_at = utc_now()
        self.session.flush()
        return plan

    def mark_preview_ready(
        self,
        plan: CleaningPlanRow,
        *,
        artifact_id: str,
    ) -> CleaningPlanRow:
        if plan.status != "draft":
            raise state_conflict("只有 draft 清洗计划可以生成预览", status=plan.status)
        plan.status = "awaiting_approval"
        plan.preview_artifact_id = artifact_id
        plan.revision += 1
        plan.updated_at = utc_now()
        self.session.flush()
        return plan

    def decide(
        self,
        plan: CleaningPlanRow,
        *,
        decision: str,
        reason: str | None,
        subject_id: str,
    ) -> CleaningPlanRow:
        if plan.status != "awaiting_approval" or plan.preview_artifact_id is None:
            raise state_conflict(
                "只有已生成预览且等待审批的清洗计划可以决策",
                status=plan.status,
            )
        now = utc_now()
        plan.status = "approved" if decision == "approve" else "rejected"
        plan.decision = decision
        plan.decision_reason = reason
        plan.decided_by = subject_id
        plan.decided_at = now
        plan.revision += 1
        plan.updated_at = now
        self.session.flush()
        return plan

    def mark_executing(
        self,
        plan: CleaningPlanRow,
        *,
        result_version_id: str,
    ) -> CleaningPlanRow:
        if plan.status != "approved":
            raise state_conflict(
                "只有 approved 清洗计划可以执行",
                status=plan.status,
            )
        plan.status = "executing"
        plan.result_version_id = result_version_id
        plan.revision += 1
        plan.updated_at = utc_now()
        self.session.flush()
        return plan

    def mark_executed(self, plan: CleaningPlanRow) -> CleaningPlanRow:
        if plan.status != "executing" or plan.result_version_id is None:
            raise state_conflict("清洗计划不在执行状态", status=plan.status)
        plan.status = "executed"
        plan.revision += 1
        plan.updated_at = utc_now()
        self.session.flush()
        return plan

    def mark_failed(self, plan: CleaningPlanRow) -> CleaningPlanRow:
        if plan.status != "executing":
            raise state_conflict("清洗计划不在执行状态", status=plan.status)
        plan.status = "failed"
        plan.revision += 1
        plan.updated_at = utc_now()
        self.session.flush()
        return plan

    def _replace_operations(
        self,
        plan_id: str,
        operations: list[CleaningOperation],
    ) -> None:
        self.session.execute(
            delete(CleaningOperationRow).where(CleaningOperationRow.plan_id == plan_id)
        )
        rows = [
            CleaningOperationRow(
                operation_id=operation.operation_id,
                plan_id=plan_id,
                position=position,
                operation=operation.operation,
                column_name=operation.column,
                parameters_json=operation.parameters,
                reason=operation.reason,
                issue_ids_json=operation.issue_ids,
                estimated_affected_rows=operation.estimated_affected_rows,
                risk_level=operation.risk_level,
                reversible=operation.reversible,
            )
            for position, operation in enumerate(operations)
        ]
        self.session.add_all(rows)
        self.session.flush()
