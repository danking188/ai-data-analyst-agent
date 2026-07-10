from __future__ import annotations

from sqlalchemy.orm import Session

from app.api.schemas import ReportExportRequest
from app.domain.errors import not_found, permission_denied, state_conflict, validation_error
from app.persistence.repositories.claims import ClaimRepository
from app.persistence.repositories.projects import ProjectRepository
from app.persistence.repositories.runs import AnalysisRunRepository


class ReportService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.projects = ProjectRepository(session)
        self.runs = AnalysisRunRepository(session)
        self.claims = ClaimRepository(session)

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
            raise state_conflict("归档项目不能创建报告导出")
        if edit and role not in {"owner", "editor"}:
            raise permission_denied()

    def validate_export_request(
        self,
        project_id: str,
        payload: ReportExportRequest,
    ) -> list[str]:
        run = self.runs.get(project_id=project_id, run_id=payload.run_id)
        if run.status != "succeeded":
            raise state_conflict("只有 succeeded AnalysisRun 可以导出报告", status=run.status)
        selected_claim_ids = payload.claim_ids
        if selected_claim_ids is None:
            page = self.claims.list_for_run(
                project_id=project_id,
                run_id=payload.run_id,
                page=1,
                page_size=100,
                validation_status="passed",
            )
            selected_claim_ids = [claim.claim_id for claim in page.items]
        if not selected_claim_ids and payload.format in {"html", "notebook", "manifest"}:
            raise validation_error("报告导出至少需要一条已验证结论")
        for claim_id in selected_claim_ids:
            claim = self.claims.get(project_id=project_id, claim_id=claim_id)
            if claim.run_id != payload.run_id:
                raise validation_error("claim_ids 包含不属于当前运行的结论", claim_id=claim_id)
            if claim.validation_status != "passed":
                raise validation_error("报告不能包含验证失败或待验证结论", claim_id=claim_id)
            if not self.claims.evidence_ids(claim_id):
                raise validation_error("报告不能包含无证据结论", claim_id=claim_id)
        return selected_claim_ids
