from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import parse_if_match, require_idempotency_key
from app.api.request_context import get_request_id
from app.api.schemas import (
    AnalysisSpec,
    AnalysisSpecCreate,
    AnalysisSpecPage,
    AnalysisSpecUpdate,
)
from app.persistence.repositories.idempotency import IdempotencyRepository
from app.persistence.session import get_session
from app.persistence.unit_of_work import UnitOfWork
from app.security.auth import Principal, authenticate
from app.services.analysis_specs import AnalysisSpecService, analysis_spec_to_schema
from app.services.idempotency import IdempotencyService, canonical_request_hash

router = APIRouter(prefix="/projects/{project_id}/analysis-specs", tags=["Analysis"])


@router.get("", response_model=AnalysisSpecPage, operation_id="listAnalysisSpecs")
def list_analysis_specs(
    project_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    dataset_version_id: str | None = None,
) -> AnalysisSpecPage:
    return AnalysisSpecService(session).list(
        project_id,
        subject_id=principal.subject_id,
        page=page,
        page_size=page_size,
        dataset_version_id=dataset_version_id,
    )


@router.post(
    "",
    response_model=AnalysisSpec,
    status_code=status.HTTP_201_CREATED,
    operation_id="createAnalysisSpec",
)
def create_analysis_spec(
    project_id: str,
    payload: AnalysisSpecCreate,
    request: Request,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> AnalysisSpec:
    path = f"/api/v1/projects/{project_id}/analysis-specs"
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
            return AnalysisSpec.model_validate(replay)
        result = AnalysisSpecService(session).create(
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
            resource_type="analysis_spec",
            resource_id=result.spec_id,
            response_status=201,
            response_json=result.model_dump(mode="json"),
        )
        return result


@router.get("/{spec_id}", response_model=AnalysisSpec, operation_id="getAnalysisSpec")
def get_analysis_spec(
    project_id: str,
    spec_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
) -> AnalysisSpec:
    row = AnalysisSpecService(session).get(
        project_id,
        spec_id,
        subject_id=principal.subject_id,
    )
    return analysis_spec_to_schema(row)


@router.patch("/{spec_id}", response_model=AnalysisSpec, operation_id="updateAnalysisSpec")
def update_analysis_spec(
    project_id: str,
    spec_id: str,
    payload: AnalysisSpecUpdate,
    request: Request,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    expected_revision: Annotated[int, Depends(parse_if_match)],
) -> AnalysisSpec:
    with UnitOfWork(session):
        return AnalysisSpecService(session).update(
            project_id,
            spec_id,
            payload,
            expected_revision=expected_revision,
            subject_id=principal.subject_id,
            request_id=get_request_id(request),
        )


@router.post(
    "/{spec_id}/confirm",
    response_model=AnalysisSpec,
    operation_id="confirmAnalysisSpec",
)
def confirm_analysis_spec(
    project_id: str,
    spec_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> AnalysisSpec:
    path = f"/api/v1/projects/{project_id}/analysis-specs/{spec_id}/confirm"
    current = AnalysisSpecService(session).get(
        project_id,
        spec_id,
        subject_id=principal.subject_id,
        edit=True,
    )
    request_hash = canonical_request_hash({"spec_id": spec_id, "revision": current.revision})
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
            return AnalysisSpec.model_validate(replay)
        result = AnalysisSpecService(session).confirm(
            project_id,
            spec_id,
            subject_id=principal.subject_id,
            request_id=get_request_id(request),
        )
        idempotency.record(
            subject_id=principal.subject_id,
            method=request.method,
            path=path,
            key=idempotency_key,
            request_hash=request_hash,
            resource_type="analysis_spec",
            resource_id=spec_id,
            response_status=200,
            response_json=result.model_dump(mode="json"),
        )
        return result
