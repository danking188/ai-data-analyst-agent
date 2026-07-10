from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import require_idempotency_key
from app.api.schemas import Job
from app.persistence.repositories.idempotency import IdempotencyRepository
from app.persistence.session import get_session
from app.persistence.unit_of_work import UnitOfWork
from app.security.auth import Principal, authenticate
from app.services.idempotency import IdempotencyService, canonical_request_hash
from app.services.jobs import JobService

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("/{job_id}", response_model=Job, operation_id="getJob")
def get_job(
    job_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
) -> Job:
    return JobService(session).get(job_id, subject_id=principal.subject_id)


@router.post("/{job_id}/cancel", response_model=Job, operation_id="cancelJob")
def cancel_job(
    job_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> Job:
    path = f"/api/v1/jobs/{job_id}/cancel"
    request_hash = canonical_request_hash({})
    idempotency = IdempotencyService(IdempotencyRepository(session))
    with UnitOfWork(session):
        replay = idempotency.replay_or_none(
            subject_id=principal.subject_id,
            method="POST",
            path=path,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            return Job.model_validate(replay)
        job = JobService(session).cancel(job_id, subject_id=principal.subject_id)
        idempotency.record(
            subject_id=principal.subject_id,
            method="POST",
            path=path,
            key=idempotency_key,
            request_hash=request_hash,
            resource_type="job",
            resource_id=job.job_id,
            response_status=200,
            response_json=job.model_dump(mode="json"),
        )
        return job
