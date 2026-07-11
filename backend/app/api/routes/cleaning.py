from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import parse_if_match, require_idempotency_key
from app.api.request_context import get_request_id
from app.api.schemas import (
    CleaningDecision,
    CleaningPlan,
    CleaningPlanCreate,
    CleaningPlanPage,
    CleaningPlanUpdate,
    Job,
)
from app.core.ids import new_id
from app.domain.errors import state_conflict
from app.persistence.repositories.idempotency import IdempotencyRepository
from app.persistence.repositories.jobs import JobRepository
from app.persistence.session import get_session
from app.persistence.unit_of_work import UnitOfWork
from app.security.auth import Principal, authenticate
from app.services.cleaning import CleaningService
from app.services.idempotency import IdempotencyService, canonical_request_hash
from app.services.jobs import job_to_schema
from app.workers.cleaning import (
    process_cleaning_execute_job,
    process_cleaning_preview_job,
)
from app.workers.dispatch import schedule_job

router = APIRouter(prefix="/projects/{project_id}/cleaning-plans", tags=["Cleaning"])


@router.get("", response_model=CleaningPlanPage, operation_id="listCleaningPlans")
def list_cleaning_plans(
    project_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    source_version_id: str | None = None,
) -> CleaningPlanPage:
    return CleaningService(session).list(
        project_id,
        subject_id=principal.subject_id,
        page=page,
        page_size=page_size,
        source_version_id=source_version_id,
    )


@router.post(
    "",
    response_model=CleaningPlan,
    status_code=status.HTTP_201_CREATED,
    operation_id="createCleaningPlan",
)
def create_cleaning_plan(
    project_id: str,
    payload: CleaningPlanCreate,
    request: Request,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CleaningPlan:
    path = f"/api/v1/projects/{project_id}/cleaning-plans"
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
            return CleaningPlan.model_validate(replay)
        result = CleaningService(session).create(
            project_id,
            payload,
            subject_id=principal.subject_id,
            request_id=get_request_id(request),
        )
        idempotency.record(
            subject_id=principal.subject_id,
            method=request.method,
            path=path,
            key=idempotency_key,
            request_hash=request_hash,
            resource_type="cleaning_plan",
            resource_id=result.plan_id,
            response_status=201,
            response_json=result.model_dump(mode="json"),
        )
        return result


@router.get("/{plan_id}", response_model=CleaningPlan, operation_id="getCleaningPlan")
def get_cleaning_plan(
    project_id: str,
    plan_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
) -> CleaningPlan:
    service = CleaningService(session)
    row = service.get(project_id, plan_id, subject_id=principal.subject_id)
    return service.to_schema(row)


@router.patch("/{plan_id}", response_model=CleaningPlan, operation_id="updateCleaningPlan")
def update_cleaning_plan(
    project_id: str,
    plan_id: str,
    payload: CleaningPlanUpdate,
    request: Request,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    expected_revision: Annotated[int, Depends(parse_if_match)],
) -> CleaningPlan:
    with UnitOfWork(session):
        return CleaningService(session).update(
            project_id,
            plan_id,
            payload,
            expected_revision=expected_revision,
            subject_id=principal.subject_id,
            request_id=get_request_id(request),
        )


@router.post(
    "/{plan_id}/preview",
    response_model=Job,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="previewCleaningPlan",
)
def preview_cleaning_plan(
    project_id: str,
    plan_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> Job:
    service = CleaningService(session)
    plan = service.get(project_id, plan_id, subject_id=principal.subject_id, edit=True)
    if plan.status != "draft":
        raise state_conflict("只有 draft 清洗计划可以生成预览", status=plan.status)
    version = service.require_source_version(project_id, plan.source_version_id)
    path = f"/api/v1/projects/{project_id}/cleaning-plans/{plan_id}/preview"
    request_hash = canonical_request_hash({"plan_id": plan_id, "revision": plan.revision})
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
            kind="cleaning_preview",
            request={
                "cleaning_plan_id": plan_id,
                "dataset_id": version.dataset_id,
            },
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
        schedule_job(background_tasks, process_cleaning_preview_job, job.job_id)
        return job


@router.post(
    "/{plan_id}/decision",
    response_model=CleaningPlan,
    operation_id="decideCleaningPlan",
)
def decide_cleaning_plan(
    project_id: str,
    plan_id: str,
    payload: CleaningDecision,
    request: Request,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> CleaningPlan:
    path = f"/api/v1/projects/{project_id}/cleaning-plans/{plan_id}/decision"
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
            return CleaningPlan.model_validate(replay)
        result = CleaningService(session).decide(
            project_id,
            plan_id,
            payload,
            subject_id=principal.subject_id,
            request_id=get_request_id(request),
        )
        idempotency.record(
            subject_id=principal.subject_id,
            method=request.method,
            path=path,
            key=idempotency_key,
            request_hash=request_hash,
            resource_type="cleaning_plan",
            resource_id=plan_id,
            response_status=200,
            response_json=result.model_dump(mode="json"),
        )
        return result


@router.post(
    "/{plan_id}/execute",
    response_model=Job,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="executeCleaningPlan",
)
def execute_cleaning_plan(
    project_id: str,
    plan_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> Job:
    path = f"/api/v1/projects/{project_id}/cleaning-plans/{plan_id}/execute"
    request_hash = canonical_request_hash({"cleaning_plan_id": plan_id})
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
        service = CleaningService(session)
        plan, result_version = service.prepare_execution(
            project_id,
            plan_id,
            subject_id=principal.subject_id,
        )
        job_row = JobRepository(session).create(
            project_id=project_id,
            kind="cleaning_execute",
            request={
                "cleaning_plan_id": plan.plan_id,
                "dataset_id": result_version.dataset_id,
                "result_version_id": result_version.version_id,
            },
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
        schedule_job(background_tasks, process_cleaning_execute_job, job.job_id)
        return job
