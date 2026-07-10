from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import parse_if_match, require_idempotency_key
from app.api.request_context import get_request_id
from app.api.schemas import Project, ProjectCreate, ProjectPage, ProjectUpdate
from app.persistence.repositories.idempotency import IdempotencyRepository
from app.persistence.session import get_session
from app.persistence.unit_of_work import UnitOfWork
from app.security.auth import Principal, authenticate
from app.services.idempotency import (
    IdempotencyService,
    canonical_request_hash,
)
from app.services.projects import ProjectService

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("", response_model=ProjectPage, operation_id="listProjects")
def list_projects(
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort: str | None = None,
    project_status: Annotated[
        Literal["active", "archived"] | None,
        Query(alias="status"),
    ] = None,
) -> ProjectPage:
    return ProjectService(session).list(
        subject_id=principal.subject_id,
        page=page,
        page_size=page_size,
        status=project_status,
        sort=sort,
    )


@router.post(
    "",
    response_model=Project,
    status_code=status.HTTP_201_CREATED,
    operation_id="createProject",
)
def create_project(
    payload: ProjectCreate,
    request: Request,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> Project:
    path = "/api/v1/projects"
    request_hash = canonical_request_hash(payload.model_dump(mode="json"))
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
            return Project.model_validate(replay)
        project = ProjectService(session).create(
            payload,
            subject_id=principal.subject_id,
            request_id=get_request_id(request),
        )
        idempotency.record(
            subject_id=principal.subject_id,
            method="POST",
            path=path,
            key=idempotency_key,
            request_hash=request_hash,
            resource_type="project",
            resource_id=project.project_id,
            response_status=201,
            response_json=project.model_dump(mode="json"),
        )
        return project


@router.get("/{project_id}", response_model=Project, operation_id="getProject")
def get_project(
    project_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
) -> Project:
    return ProjectService(session).get(project_id, subject_id=principal.subject_id)


@router.patch("/{project_id}", response_model=Project, operation_id="updateProject")
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    request: Request,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    expected_revision: Annotated[int, Depends(parse_if_match)],
) -> Project:
    with UnitOfWork(session):
        return ProjectService(session).update(
            project_id,
            payload,
            expected_revision=expected_revision,
            subject_id=principal.subject_id,
            request_id=get_request_id(request),
        )


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="archiveProject",
)
def archive_project(
    project_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    with UnitOfWork(session):
        ProjectService(session).archive(
            project_id,
            subject_id=principal.subject_id,
            request_id=get_request_id(request),
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
