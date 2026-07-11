from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.api.dependencies import require_idempotency_key
from app.api.schemas import (
    DataPreview,
    Dataset,
    DatasetPage,
    DatasetVersion,
    DatasetVersionPage,
    Job,
    ParseOptions,
    VersionComparisonRequest,
)
from app.core.config import Settings, get_settings
from app.core.ids import new_id
from app.domain.errors import validation_error
from app.persistence.repositories.datasets import DatasetRepository, DatasetVersionDraft
from app.persistence.repositories.idempotency import IdempotencyRepository
from app.persistence.repositories.jobs import JobRepository
from app.persistence.session import get_session
from app.persistence.unit_of_work import UnitOfWork
from app.security.auth import Principal, authenticate
from app.services.datasets import DatasetService
from app.services.idempotency import IdempotencyService, canonical_request_hash
from app.services.jobs import job_to_schema
from app.services.preview import PreviewService
from app.storage.files import get_file_storage
from app.workers.comparison import process_version_comparison_job
from app.workers.dispatch import schedule_job
from app.workers.ingestion import process_ingestion_job

router = APIRouter(prefix="/projects/{project_id}/datasets", tags=["Datasets"])


def parse_multipart_options(raw: str | None) -> ParseOptions:
    if raw is None or not raw.strip():
        return ParseOptions()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise validation_error("parse_options 必须为合法 JSON") from exc
    if not isinstance(value, dict):
        raise validation_error("parse_options 必须为 JSON 对象")
    return ParseOptions.model_validate(value)


@router.get("", response_model=DatasetPage, operation_id="listDatasets")
def list_datasets(
    project_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> DatasetPage:
    return DatasetService(session).list(
        project_id,
        subject_id=principal.subject_id,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=Job,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="uploadDataset",
)
async def upload_dataset(
    project_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File()],
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    dataset_name: Annotated[str | None, Form(max_length=120)] = None,
    parse_options: Annotated[str | None, Form()] = None,
) -> Job:
    service = DatasetService(session)
    service.require_project_role(project_id, principal.subject_id, editable=True)
    if dataset_name is not None:
        dataset_name = dataset_name.strip()
        if not dataset_name:
            raise validation_error("dataset_name 不能为空")
    job_id = new_id("job_")
    storage = get_file_storage()
    staged = await storage.stage_upload(
        file,
        job_id=job_id,
        max_bytes=settings.max_upload_bytes,
    )
    options = parse_multipart_options(parse_options)
    payload_hash = canonical_request_hash(
        {
            "project_id": project_id,
            "file_hash": staged.sha256,
            "dataset_name": dataset_name,
            "parse_options": options.model_dump(mode="json"),
        }
    )
    path = f"/api/v1/projects/{project_id}/datasets"
    idempotency = IdempotencyService(IdempotencyRepository(session))
    try:
        with UnitOfWork(session):
            replay = idempotency.replay_or_none(
                subject_id=principal.subject_id,
                method="POST",
                path=path,
                key=idempotency_key,
                request_hash=payload_hash,
            )
            if replay is not None:
                storage.remove_staged(job_id)
                return Job.model_validate(replay)
            repository = DatasetRepository(session)
            dataset = repository.create_dataset(
                project_id=project_id,
                name=(dataset_name or Path(staged.display_name).stem)[:120],
                source_type=staged.source_type,
                subject_id=principal.subject_id,
            )
            version = repository.create_version(
                project_id=project_id,
                dataset_id=dataset.dataset_id,
                subject_id=principal.subject_id,
                draft=DatasetVersionDraft(
                    source_file_name=staged.display_name,
                    source_type=staged.source_type,
                    source_storage_key=staged.storage_key,
                    file_hash=staged.sha256,
                    file_size_bytes=staged.size_bytes,
                    sheet_name=options.sheet_name,
                    parse_options=options.model_dump(mode="json"),
                    operation_summary="原始文件上传",
                ),
            )
            job_row = JobRepository(session).create(
                project_id=project_id,
                kind="dataset_ingestion",
                request={
                    "dataset_id": dataset.dataset_id,
                    "dataset_version_id": version.version_id,
                },
                subject_id=principal.subject_id,
                job_id=job_id,
            )
            job = job_to_schema(job_row)
            idempotency.record(
                subject_id=principal.subject_id,
                method="POST",
                path=path,
                key=idempotency_key,
                request_hash=payload_hash,
                resource_type="job",
                resource_id=job.job_id,
                response_status=202,
                response_json=job.model_dump(mode="json"),
            )
            schedule_job(background_tasks, process_ingestion_job, job.job_id)
            return job
    except Exception:
        storage.remove_staged(job_id)
        raise


@router.get("/{dataset_id}", response_model=Dataset, operation_id="getDataset")
def get_dataset(
    project_id: str,
    dataset_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
) -> Dataset:
    return DatasetService(session).get(
        project_id,
        dataset_id,
        subject_id=principal.subject_id,
    )


@router.get(
    "/{dataset_id}/versions",
    response_model=DatasetVersionPage,
    operation_id="listDatasetVersions",
)
def list_dataset_versions(
    project_id: str,
    dataset_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    version_status: Annotated[
        Literal["creating", "ready", "failed", "archived"] | None,
        Query(alias="status"),
    ] = None,
) -> DatasetVersionPage:
    return DatasetService(session).list_versions(
        project_id,
        dataset_id,
        subject_id=principal.subject_id,
        page=page,
        page_size=page_size,
        status=version_status,
    )


@router.get(
    "/{dataset_id}/versions/{version_id}",
    response_model=DatasetVersion,
    operation_id="getDatasetVersion",
)
def get_dataset_version(
    project_id: str,
    dataset_id: str,
    version_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
) -> DatasetVersion:
    return DatasetService(session).get_version(
        project_id,
        dataset_id,
        version_id,
        subject_id=principal.subject_id,
    )


@router.post(
    "/{dataset_id}/versions/{version_id}/activate",
    response_model=Dataset,
    operation_id="activateDatasetVersion",
)
def activate_dataset_version(
    project_id: str,
    dataset_id: str,
    version_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> Dataset:
    path = f"/api/v1/projects/{project_id}/datasets/{dataset_id}/versions/{version_id}/activate"
    request_hash = canonical_request_hash(
        {
            "project_id": project_id,
            "dataset_id": dataset_id,
            "version_id": version_id,
        }
    )
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
            return Dataset.model_validate(replay)
        result = DatasetService(session).activate_version(
            project_id,
            dataset_id,
            version_id,
            subject_id=principal.subject_id,
        )
        idempotency.record(
            subject_id=principal.subject_id,
            method=request.method,
            path=path,
            key=idempotency_key,
            request_hash=request_hash,
            resource_type="dataset",
            resource_id=dataset_id,
            response_status=200,
            response_json=result.model_dump(mode="json"),
        )
        return result


@router.post(
    "/{dataset_id}/version-comparisons",
    response_model=Job,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="compareDatasetVersions",
)
def compare_dataset_versions(
    project_id: str,
    dataset_id: str,
    payload: VersionComparisonRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> Job:
    service = DatasetService(session)
    service.require_project_role(project_id, principal.subject_id, editable=True)
    path = f"/api/v1/projects/{project_id}/datasets/{dataset_id}/version-comparisons"
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
        repository = DatasetRepository(session)
        repository.get_version(
            project_id=project_id,
            dataset_id=dataset_id,
            version_id=payload.base_version_id,
        )
        repository.get_version(
            project_id=project_id,
            dataset_id=dataset_id,
            version_id=payload.compare_version_id,
        )
        job_row = JobRepository(session).create(
            project_id=project_id,
            kind="version_comparison",
            request={
                "dataset_id": dataset_id,
                **payload.model_dump(mode="json"),
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
        schedule_job(background_tasks, process_version_comparison_job, job.job_id)
        return job


@router.get(
    "/{dataset_id}/versions/{version_id}/preview",
    response_model=DataPreview,
    operation_id="previewDatasetVersion",
)
def preview_dataset_version(
    project_id: str,
    dataset_id: str,
    version_id: str,
    principal: Annotated[Principal, Depends(authenticate)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    columns: str | None = None,
) -> DataPreview:
    requested_columns = (
        [name.strip() for name in columns.split(",") if name.strip()]
        if columns is not None
        else None
    )
    if columns is not None and not requested_columns:
        raise validation_error("columns 不能为空")
    return PreviewService(session, settings).preview(
        project_id=project_id,
        dataset_id=dataset_id,
        version_id=version_id,
        subject_id=principal.subject_id,
        cursor_token=cursor,
        limit=limit,
        requested_columns=requested_columns,
    )
