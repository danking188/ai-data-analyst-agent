from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_idempotency_key
from app.api.request_context import get_request_id
from app.api.schemas import (
    SemanticMetric,
    SemanticMetricCreate,
    SemanticMetricPage,
    SemanticMetricUpdate,
)
from app.persistence.repositories.idempotency import IdempotencyRepository
from app.persistence.session import get_session
from app.persistence.unit_of_work import UnitOfWork
from app.security.auth import Principal, authenticate
from app.services.idempotency import IdempotencyService, canonical_request_hash
from app.services.semantic_metrics import SemanticMetricService

router = APIRouter(prefix="/projects/{project_id}/semantic-metrics", tags=["Semantics"])


@router.get("", response_model=SemanticMetricPage, operation_id="listSemanticMetrics")
def list_semantic_metrics(
    project_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    dataset_version_id: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> SemanticMetricPage:
    return SemanticMetricService(session).list(
        project_id,
        subject_id=principal.subject_id,
        dataset_version_id=dataset_version_id,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=SemanticMetric,
    status_code=status.HTTP_201_CREATED,
    operation_id="createSemanticMetric",
)
def create_semantic_metric(
    project_id: str,
    payload: SemanticMetricCreate,
    request: Request,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> SemanticMetric:
    path = f"/api/v1/projects/{project_id}/semantic-metrics"
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
            return SemanticMetric.model_validate(replay)
        result = SemanticMetricService(session).create(
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
            resource_type="semantic_metric",
            resource_id=result.metric_id,
            response_status=201,
            response_json=result.model_dump(mode="json"),
        )
        return result


@router.patch("/{metric_id}", response_model=SemanticMetric, operation_id="updateSemanticMetric")
def update_semantic_metric(
    project_id: str,
    metric_id: str,
    payload: SemanticMetricUpdate,
    request: Request,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
) -> SemanticMetric:
    with UnitOfWork(session):
        return SemanticMetricService(session).update(
            project_id,
            metric_id,
            payload,
            subject_id=principal.subject_id,
            request_id=get_request_id(request),
        )
