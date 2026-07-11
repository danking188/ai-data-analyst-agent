from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import parse_if_match, require_idempotency_key
from app.api.request_context import get_request_id
from app.api.schemas import (
    Job,
    QualityIssue,
    QualityIssuePage,
    QualityIssueUpdate,
    QualityScanRequest,
)
from app.core.ids import new_id
from app.domain.errors import state_conflict, validation_error
from app.persistence.repositories.idempotency import IdempotencyRepository
from app.persistence.repositories.jobs import JobRepository
from app.persistence.session import get_session
from app.persistence.unit_of_work import UnitOfWork
from app.quality.engine import SUPPORTED_RULES
from app.security.auth import Principal, authenticate
from app.services.idempotency import IdempotencyService, canonical_request_hash
from app.services.jobs import job_to_schema
from app.services.quality import QualityService
from app.workers.dispatch import schedule_job
from app.workers.quality import process_quality_scan_job

router = APIRouter(prefix="/projects/{project_id}", tags=["Quality"])


@router.post(
    "/dataset-versions/{version_id}/quality-scans",
    response_model=Job,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="createQualityScan",
)
def create_quality_scan(
    project_id: str,
    version_id: str,
    payload: QualityScanRequest,
    background_tasks: BackgroundTasks,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> Job:
    QualityService(session).require_version_access(
        project_id,
        version_id,
        subject_id=principal.subject_id,
        edit=True,
    )
    unknown_rules = sorted(set(payload.rules) - SUPPORTED_RULES)
    if unknown_rules:
        raise validation_error(
            "包含不支持的质量规则",
            unsupported_rules=unknown_rules,
            supported_rules=sorted(SUPPORTED_RULES),
        )
    path = f"/api/v1/projects/{project_id}/dataset-versions/{version_id}/quality-scans"
    request_hash = canonical_request_hash(
        {
            "project_id": project_id,
            "version_id": version_id,
            **payload.model_dump(mode="json"),
        }
    )
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
        if QualityService(session).issues.exists_for_version(version_id) and not payload.force:
            raise state_conflict("该数据版本已存在质量扫描结果；如需重扫请设置 force=true")
        job_row = JobRepository(session).create(
            project_id=project_id,
            kind="quality_scan",
            request={
                "dataset_version_id": version_id,
                **payload.model_dump(mode="json"),
            },
            subject_id=principal.subject_id,
            job_id=new_id("job_"),
        )
        job = job_to_schema(job_row)
        idempotency.record(
            subject_id=principal.subject_id,
            method="POST",
            path=path,
            key=idempotency_key,
            request_hash=request_hash,
            resource_type="job",
            resource_id=job.job_id,
            response_status=202,
            response_json=job.model_dump(mode="json"),
        )
        schedule_job(background_tasks, process_quality_scan_job, job.job_id)
        return job


@router.get(
    "/dataset-versions/{version_id}/quality-issues",
    response_model=QualityIssuePage,
    operation_id="listQualityIssues",
)
def list_quality_issues(
    project_id: str,
    version_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    severity: Literal["low", "medium", "high", "critical"] | None = None,
    issue_status: Annotated[
        Literal["open", "accepted", "resolved", "ignored"] | None,
        Query(alias="status"),
    ] = None,
    issue_type: str | None = None,
) -> QualityIssuePage:
    return QualityService(session).list(
        project_id,
        version_id,
        subject_id=principal.subject_id,
        page=page,
        page_size=page_size,
        severity=severity,
        status=issue_status,
        issue_type=issue_type,
    )


@router.patch(
    "/quality-issues/{issue_id}",
    response_model=QualityIssue,
    operation_id="updateQualityIssue",
)
def update_quality_issue(
    project_id: str,
    issue_id: str,
    payload: QualityIssueUpdate,
    request: Request,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    expected_revision: Annotated[int, Depends(parse_if_match)],
) -> QualityIssue:
    with UnitOfWork(session):
        return QualityService(session).update(
            project_id,
            issue_id,
            payload,
            expected_revision=expected_revision,
            subject_id=principal.subject_id,
            request_id=get_request_id(request),
        )
