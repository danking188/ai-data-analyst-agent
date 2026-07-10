from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.dependencies import parse_if_match
from app.api.request_context import get_request_id
from app.api.schemas import DatasetSchema, SchemaPatch
from app.persistence.session import get_session
from app.persistence.unit_of_work import UnitOfWork
from app.security.auth import Principal, authenticate
from app.services.schemas import SchemaService

router = APIRouter(
    prefix="/projects/{project_id}/dataset-versions/{version_id}/schema",
    tags=["Schema"],
)


@router.get("", response_model=DatasetSchema, operation_id="getDatasetSchema")
def get_dataset_schema(
    project_id: str,
    version_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
) -> DatasetSchema:
    return SchemaService(session).get(
        project_id,
        version_id,
        subject_id=principal.subject_id,
    )


@router.patch("", response_model=DatasetSchema, operation_id="updateDatasetSchema")
def update_dataset_schema(
    project_id: str,
    version_id: str,
    payload: SchemaPatch,
    request: Request,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    expected_revision: Annotated[int, Depends(parse_if_match)],
) -> DatasetSchema:
    with UnitOfWork(session):
        return SchemaService(session).update(
            project_id,
            version_id,
            payload,
            expected_revision=expected_revision,
            subject_id=principal.subject_id,
            request_id=get_request_id(request),
        )
