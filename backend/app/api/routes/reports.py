from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_idempotency_key
from app.api.schemas import Job, ReportExportRequest
from app.core.ids import new_id
from app.persistence.repositories.idempotency import IdempotencyRepository
from app.persistence.repositories.jobs import JobRepository
from app.persistence.session import get_session
from app.persistence.unit_of_work import UnitOfWork
from app.security.auth import Principal, authenticate
from app.services.idempotency import IdempotencyService, canonical_request_hash
from app.services.jobs import job_to_schema
from app.services.reports import ReportService
from app.workers.reports import process_report_export_job

router = APIRouter(prefix="/projects/{project_id}/reports", tags=["Reports"])


@router.post(
    "",
    response_model=Job,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="createReportExport",
)
def create_report_export(
    project_id: str,
    payload: ReportExportRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> Job:
    service = ReportService(session)
    service.require_project_access(project_id, principal.subject_id, edit=True)
    selected_claim_ids = service.validate_export_request(project_id, payload)
    request_payload = payload.model_dump(mode="json")
    request_payload["claim_ids"] = selected_claim_ids
    path = f"/api/v1/projects/{project_id}/reports"
    request_hash = canonical_request_hash(request_payload)
    idempotency = IdempotencyService(IdempotencyRepository(session))
    with UnitOfWork(session):
        replay = idempotency.replay_or_none(
            subject_id=principal.subject_id,
            method=request.method,
            path=path,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            return Job.model_validate(replay)
        job_row = JobRepository(session).create(
            project_id=project_id,
            kind="report_export",
            request=request_payload,
            subject_id=principal.subject_id,
            job_id=new_id("job_"),
        )
        job = job_to_schema(job_row)
        idempotency.record(
            subject_id=principal.subject_id,
            method=request.method,
            path=path,
            key=idempotency_key,
            request_hash=request_hash,
            resource_type="job",
            resource_id=job.job_id,
            response_status=202,
            response_json=job.model_dump(mode="json"),
        )
        background_tasks.add_task(process_report_export_job, job.job_id)
        return job
