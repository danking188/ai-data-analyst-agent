from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.ids import new_id
from app.domain.errors import not_found, version_conflict
from app.persistence.orm.workflow_models import QualityIssueRow
from app.quality.engine import QualityFinding


class QualityIssueRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def exists_for_version(self, dataset_version_id: str) -> bool:
        return bool(
            self.session.scalar(
                select(func.count())
                .select_from(QualityIssueRow)
                .where(QualityIssueRow.dataset_version_id == dataset_version_id)
            )
        )

    def replace_findings(
        self,
        *,
        project_id: str,
        dataset_version_id: str,
        findings: list[QualityFinding],
    ) -> list[QualityIssueRow]:
        self.session.execute(
            delete(QualityIssueRow).where(QualityIssueRow.dataset_version_id == dataset_version_id)
        )
        now = utc_now()
        rows = [
            QualityIssueRow(
                issue_id=new_id("issue_"),
                project_id=project_id,
                dataset_version_id=dataset_version_id,
                issue_type=finding.issue_type,
                column_name=finding.column,
                severity=finding.severity,
                status="open",
                title=finding.title,
                explanation=finding.explanation,
                metrics_json=finding.metrics,
                sample_rows_json=finding.sample_rows,
                recommendation=finding.recommendation,
                rule_name=finding.rule_name,
                rule_version=finding.rule_version,
                decision_reason=None,
                resolved_by_plan_id=None,
                revision=1,
                created_at=now,
                updated_at=now,
            )
            for finding in findings
        ]
        self.session.add_all(rows)
        self.session.flush()
        return rows

    def list_page(
        self,
        *,
        dataset_version_id: str,
        page: int,
        page_size: int,
        severity: str | None,
        status: str | None,
        issue_type: str | None,
    ) -> tuple[list[QualityIssueRow], int]:
        filters = [QualityIssueRow.dataset_version_id == dataset_version_id]
        if severity is not None:
            filters.append(QualityIssueRow.severity == severity)
        if status is not None:
            filters.append(QualityIssueRow.status == status)
        if issue_type is not None:
            filters.append(QualityIssueRow.issue_type == issue_type)
        total = int(
            self.session.scalar(select(func.count()).select_from(QualityIssueRow).where(*filters))
            or 0
        )
        rows = list(
            self.session.scalars(
                select(QualityIssueRow)
                .where(*filters)
                .order_by(QualityIssueRow.created_at, QualityIssueRow.issue_id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return rows, total

    def get_for_project(self, *, project_id: str, issue_id: str) -> QualityIssueRow:
        row = self.session.scalar(
            select(QualityIssueRow).where(
                QualityIssueRow.project_id == project_id,
                QualityIssueRow.issue_id == issue_id,
            )
        )
        if row is None:
            raise not_found()
        return row

    def update_status(
        self,
        row: QualityIssueRow,
        *,
        status: str,
        reason: str | None,
        expected_revision: int,
    ) -> QualityIssueRow:
        if row.revision != expected_revision:
            raise version_conflict(row.revision)
        row.status = status
        row.decision_reason = reason
        row.revision += 1
        row.updated_at = utc_now()
        self.session.flush()
        return row
