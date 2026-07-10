from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_idempotency_key
from app.api.request_context import get_request_id
from app.api.schemas import AnalysisRun, AnalysisRunCreate, AnalysisRunPage, Job
from app.core.ids import new_id
from app.persistence.repositories.idempotency import IdempotencyRepository
from app.persistence.repositories.jobs import JobRepository
from app.persistence.repositories.runs import AnalysisRunRepository
from app.persistence.session import get_session
from app.persistence.unit_of_work import UnitOfWork
from app.security.auth import Principal, authenticate
from app.services.idempotency import IdempotencyService, canonical_request_hash
from app.services.jobs import job_to_schema
from app.services.runs import AnalysisRunService
from app.workers.analysis import process_analysis_run_job

router = APIRouter(prefix="/projects/{project_id}/runs", tags=["Runs"])


@router.get("", response_model=AnalysisRunPage, operation_id="listRuns")
def list_runs(
    project_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    run_status: Annotated[
        Literal["queued", "running", "blocked", "succeeded", "failed", "cancelled"] | None,
        Query(alias="status"),
    ] = None,
    dataset_version_id: str | None = None,
) -> AnalysisRunPage:
    return AnalysisRunService(session).list(
        project_id,
        subject_id=principal.subject_id,
        page=page,
        page_size=page_size,
        status=run_status,
        dataset_version_id=dataset_version_id,
    )


@router.post(
    "",
    response_model=Job,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="createRun",
)
def create_run(
    project_id: str,
    payload: AnalysisRunCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> Job:
    service = AnalysisRunService(session)
    service.require_project_access(project_id, principal.subject_id, edit=True)
    spec = service.require_confirmed_spec(project_id, payload)
    path = f"/api/v1/projects/{project_id}/runs"
    request_hash = canonical_request_hash(payload.model_dump(mode="json"))
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
        run_id = new_id("run_")
        job_row = JobRepository(session).create(
            project_id=project_id,
            kind="analysis_run",
            request={"run_id": run_id},
            subject_id=principal.subject_id,
            job_id=new_id("job_"),
        )
        AnalysisRunRepository(session).create(
            run_id=run_id,
            project_id=project_id,
            dataset_version_id=payload.dataset_version_id,
            spec_revision_id=spec.spec_revision_id,
            run_kind=payload.run_kind,
            job_id=job_row.job_id,
            random_seed=spec.random_seed,
            subject_id=principal.subject_id,
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
        background_tasks.add_task(process_analysis_run_job, job.job_id)
        return job


@router.get("/{run_id}", response_model=AnalysisRun, operation_id="getRun")
def get_run(
    project_id: str,
    run_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
) -> AnalysisRun:
    service = AnalysisRunService(session)
    row = service.get(project_id, run_id, subject_id=principal.subject_id)
    return service.to_schema(row)


@router.post("/{run_id}/cancel", response_model=AnalysisRun, operation_id="cancelRun")
def cancel_run(
    project_id: str,
    run_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> AnalysisRun:
    service = AnalysisRunService(session)
    run = service.get(project_id, run_id, subject_id=principal.subject_id, edit=True)
    path = f"/api/v1/projects/{project_id}/runs/{run_id}/cancel"
    request_hash = canonical_request_hash({"run_id": run_id})
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
            return AnalysisRun.model_validate(replay)
        AnalysisRunRepository(session).cancel(run)
        if run.job_id:
            job = JobRepository(session).get(run.job_id)
            if job.status in {"queued", "running"}:
                JobRepository(session).request_cancel(job)
            if job.status == "cancelling":
                JobRepository(session).transition(job, status="cancelled")
        result = service.to_schema(run)
        UnitOfWork(session).audit.append(
            action="analysis_run.cancelled",
            result="success",
            summary={},
            project_id=project_id,
            subject_id=principal.subject_id,
            object_type="analysis_run",
            object_id=run_id,
            request_id=get_request_id(request),
        )
        idempotency.record(
            subject_id=principal.subject_id,
            method=request.method,
            path=path,
            key=idempotency_key,
            request_hash=request_hash,
            resource_type="analysis_run",
            resource_id=run_id,
            response_status=200,
            response_json=result.model_dump(mode="json"),
        )
        return result
