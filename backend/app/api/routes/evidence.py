from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.dependencies import require_idempotency_key
from app.api.schemas import Artifact, ArtifactPage, Claim, ClaimPage, Download
from app.core.clock import utc_now
from app.core.config import Settings, get_settings
from app.persistence.repositories.idempotency import IdempotencyRepository
from app.persistence.session import get_session
from app.persistence.unit_of_work import UnitOfWork
from app.security.auth import Principal, authenticate
from app.services.evidence import EvidenceService
from app.services.idempotency import IdempotencyService, canonical_request_hash
from app.storage.files import get_file_storage

router = APIRouter(prefix="/projects/{project_id}", tags=["Evidence"])


@router.get(
    "/runs/{run_id}/artifacts",
    response_model=ArtifactPage,
    operation_id="listArtifacts",
)
def list_artifacts(
    project_id: str,
    run_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    artifact_type: Annotated[
        Literal["metric", "table", "chart", "model", "file", "log", "comparison"] | None,
        Query(alias="type"),
    ] = None,
) -> ArtifactPage:
    return EvidenceService(session).list_artifacts(
        project_id,
        run_id,
        subject_id=principal.subject_id,
        page=page,
        page_size=page_size,
        artifact_type=artifact_type,
    )


@router.get(
    "/artifacts/{artifact_id}",
    response_model=Artifact,
    operation_id="getArtifact",
)
def get_artifact(
    project_id: str,
    artifact_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
) -> Artifact:
    return EvidenceService(session).get_artifact(
        project_id,
        artifact_id,
        subject_id=principal.subject_id,
    )


@router.post(
    "/artifacts/{artifact_id}/download",
    response_model=Download,
    operation_id="createArtifactDownload",
)
def create_artifact_download(
    project_id: str,
    artifact_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> Download:
    path = f"/api/v1/projects/{project_id}/artifacts/{artifact_id}/download"
    request_hash = canonical_request_hash({"artifact_id": artifact_id})
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
            return Download.model_validate(replay)
        expires_at = utc_now() + timedelta(minutes=30)
        download_url = (
            f"{settings.api_prefix}/projects/{project_id}/artifacts/{artifact_id}/file"
        )
        result = EvidenceService(session).create_download(
            project_id,
            artifact_id,
            subject_id=principal.subject_id,
            download_url=download_url,
            expires_at=expires_at,
        )
        idempotency.record(
            subject_id=principal.subject_id,
            method=request.method,
            path=path,
            key=idempotency_key,
            request_hash=request_hash,
            resource_type="artifact",
            resource_id=artifact_id,
            response_status=200,
            response_json=result.model_dump(mode="json"),
        )
        return result


@router.get(
    "/artifacts/{artifact_id}/file",
    name="download_artifact_file",
    operation_id="downloadArtifactFile",
    response_class=FileResponse,
)
def download_artifact_file(
    project_id: str,
    artifact_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
) -> FileResponse:
    artifact = EvidenceService(session).get_downloadable_artifact(
        project_id,
        artifact_id,
        subject_id=principal.subject_id,
    )
    result = artifact.result_json if isinstance(artifact.result_json, dict) else {}
    return FileResponse(
        get_file_storage().resolve_key(str(artifact.storage_key)),
        media_type=result.get("content_type"),
        filename=str(result.get("file_name") or f"{artifact_id}.artifact"),
    )


@router.get(
    "/runs/{run_id}/claims",
    response_model=ClaimPage,
    operation_id="listClaims",
)
def list_claims(
    project_id: str,
    run_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    validation_status: Annotated[
        Literal["pending", "passed", "failed"] | None,
        Query(),
    ] = None,
) -> ClaimPage:
    return EvidenceService(session).list_claims(
        project_id,
        run_id,
        subject_id=principal.subject_id,
        page=page,
        page_size=page_size,
        validation_status=validation_status,
    )


@router.get(
    "/claims/{claim_id}",
    response_model=Claim,
    operation_id="getClaim",
)
def get_claim(
    project_id: str,
    claim_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
) -> Claim:
    return EvidenceService(session).get_claim(
        project_id,
        claim_id,
        subject_id=principal.subject_id,
    )
