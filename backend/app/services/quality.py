from __future__ import annotations

from sqlalchemy.orm import Session

from app.api.schemas import (
    QualityIssue,
    QualityIssuePage,
    QualityIssueUpdate,
)
from app.core.clock import utc_now
from app.core.ids import new_id
from app.domain.errors import not_found, permission_denied, state_conflict
from app.persistence.orm.models import DatasetVersionRow
from app.persistence.orm.workflow_models import QualityIssueRow, UserDecisionRow
from app.persistence.repositories.audit import AuditRepository
from app.persistence.repositories.projects import ProjectRepository
from app.persistence.repositories.quality import QualityIssueRepository


def quality_issue_to_schema(row: QualityIssueRow) -> QualityIssue:
    return QualityIssue(
        issue_id=row.issue_id,
        dataset_version_id=row.dataset_version_id,
        issue_type=row.issue_type,
        column=row.column_name,
        severity=row.severity,
        status=row.status,
        title=row.title,
        explanation=row.explanation,
        metrics=row.metrics_json,
        sample_rows=row.sample_rows_json,
        recommendation=row.recommendation,
        decision_reason=row.decision_reason,
        revision=row.revision,
        created_at=row.created_at,
    )


class QualityService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.projects = ProjectRepository(session)
        self.issues = QualityIssueRepository(session)

    def require_version_access(
        self,
        project_id: str,
        version_id: str,
        *,
        subject_id: str,
        edit: bool,
    ) -> DatasetVersionRow:
        membership = self.projects.get_for_subject(project_id, subject_id)
        if membership is None:
            raise not_found()
        project, role = membership
        if edit and project.status != "active":
            raise state_conflict("归档项目不能执行质量扫描或处置问题")
        if edit and role not in {"owner", "editor"}:
            raise permission_denied()
        version = self.session.get(DatasetVersionRow, version_id)
        if version is None or version.project_id != project_id:
            raise not_found()
        if version.status != "ready" or not version.data_storage_key:
            raise state_conflict("只有 ready 数据版本可以执行质量操作")
        return version

    def require_issue_access(
        self,
        project_id: str,
        issue_id: str,
        *,
        subject_id: str,
        edit: bool,
    ) -> QualityIssueRow:
        membership = self.projects.get_for_subject(project_id, subject_id)
        if membership is None:
            raise not_found()
        project, role = membership
        if edit and project.status != "active":
            raise state_conflict("归档项目不能处置质量问题")
        if edit and role not in {"owner", "editor"}:
            raise permission_denied()
        return self.issues.get_for_project(project_id=project_id, issue_id=issue_id)

    def list(
        self,
        project_id: str,
        version_id: str,
        *,
        subject_id: str,
        page: int,
        page_size: int,
        severity: str | None,
        status: str | None,
        issue_type: str | None,
    ) -> QualityIssuePage:
        self.require_version_access(
            project_id,
            version_id,
            subject_id=subject_id,
            edit=False,
        )
        rows, total = self.issues.list_page(
            dataset_version_id=version_id,
            page=page,
            page_size=page_size,
            severity=severity,
            status=status,
            issue_type=issue_type,
        )
        return QualityIssuePage(
            items=[quality_issue_to_schema(row) for row in rows],
            page=page,
            page_size=page_size,
            total=total,
            has_more=page * page_size < total,
        )

    def update(
        self,
        project_id: str,
        issue_id: str,
        payload: QualityIssueUpdate,
        *,
        expected_revision: int,
        subject_id: str,
        request_id: str,
    ) -> QualityIssue:
        row = self.require_issue_access(
            project_id,
            issue_id,
            subject_id=subject_id,
            edit=True,
        )
        row = self.issues.update_status(
            row,
            status=payload.status,
            reason=payload.reason,
            expected_revision=expected_revision,
        )
        self.session.add(
            UserDecisionRow(
                decision_id=new_id("decision_"),
                project_id=project_id,
                subject_id=subject_id,
                object_type="quality_issue",
                object_id=issue_id,
                action=payload.status,
                reason=payload.reason,
                payload_json=payload.model_dump(mode="json"),
                created_at=utc_now(),
            )
        )
        AuditRepository(self.session).append(
            action="quality_issue.updated",
            result="success",
            summary={"status": payload.status, "reason": payload.reason},
            project_id=project_id,
            subject_id=subject_id,
            object_type="quality_issue",
            object_id=issue_id,
            request_id=request_id,
        )
        return quality_issue_to_schema(row)
