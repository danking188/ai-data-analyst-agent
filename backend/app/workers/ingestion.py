from __future__ import annotations

from typing import Any

from app.domain.errors import DomainError
from app.ingest.parser import DatasetParser
from app.ingest.profiler import profile_frame
from app.persistence.repositories.datasets import DatasetRepository
from app.persistence.repositories.jobs import JobRepository
from app.persistence.session import Database, get_database
from app.persistence.unit_of_work import UnitOfWork
from app.storage.files import FileStorage, get_file_storage


class DatasetIngestionWorker:
    def __init__(
        self,
        database: Database,
        storage: FileStorage,
        *,
        worker_id: str,
    ) -> None:
        self.database = database
        self.storage = storage
        self.worker_id = worker_id

    def run(self, job_id: str) -> bool:
        if not self._claim(job_id):
            return False
        try:
            self._process(job_id)
        except DomainError as exc:
            self._fail(job_id, exc)
        except Exception:
            self._fail(
                job_id,
                DomainError(
                    "EXECUTOR_UNAVAILABLE",
                    "数据接入执行失败",
                    500,
                    retryable=True,
                ),
            )
        return True

    def _claim(self, job_id: str) -> bool:
        session = self.database.session()
        try:
            with UnitOfWork(session):
                return JobRepository(session).claim(
                    job_id=job_id,
                    worker_id=self.worker_id,
                    lease_seconds=1800,
                )
        finally:
            session.close()

    def _process(self, job_id: str) -> None:
        read_session = self.database.session()
        try:
            job = JobRepository(read_session).get(job_id)
            if job.kind != "dataset_ingestion":
                raise DomainError("STATE_CONFLICT", "Job 类型不是数据接入", 409)
            dataset_id = str(job.request_json["dataset_id"])
            version_id = str(job.request_json["dataset_version_id"])
            project_id = job.project_id
            created_by = job.created_by
            repository = DatasetRepository(read_session)
            version = repository.get_version(
                project_id=project_id,
                dataset_id=dataset_id,
                version_id=version_id,
            )
            source_path = self.storage.resolve_key(version.source_storage_key)
            source_type = version.source_type
            parse_options = dict(version.parse_options_json)
        finally:
            read_session.close()

        temporary_parquet = self.storage.temp_parquet_path(job_id)
        parsed = DatasetParser().parse(
            source_path,
            source_type=source_type,
            options=parse_options,
        )
        row_count, column_count = DatasetParser().write_verified_parquet(
            parsed.frame,
            temporary_parquet,
        )
        profiles = profile_frame(parsed.frame)
        source_key, data_key = self.storage.commit_ingestion(
            project_id=project_id,
            dataset_id=dataset_id,
            version_id=version_id,
            source_path=source_path,
            parquet_path=temporary_parquet,
            source_type=source_type,
        )
        checksum = self.storage.checksum_path(self.storage.resolve_key(data_key))

        write_session = self.database.session()
        try:
            with UnitOfWork(write_session) as uow:
                current_job = uow.jobs.get(job_id)
                current_version = uow.datasets.get_version(
                    project_id=project_id,
                    dataset_id=dataset_id,
                    version_id=version_id,
                )
                current_version.source_storage_key = source_key
                current_version.parse_options_json = parsed.effective_options
                current_version.sheet_name = parsed.sheet_name
                uow.schemas.replace_profiles(
                    project_id=project_id,
                    dataset_version_id=version_id,
                    profiles=profiles,
                )
                uow.datasets.mark_version_ready(
                    current_version,
                    data_storage_key=data_key,
                    data_checksum=checksum,
                    row_count=row_count,
                    column_count=column_count,
                )
                uow.datasets.activate_version(
                    project_id=job.project_id,
                    dataset_id=dataset_id,
                    version_id=version_id,
                )
                uow.jobs.transition(
                    current_job,
                    status="succeeded",
                    resource_type="dataset_version",
                    resource_id=version_id,
                )
                uow.audit.append(
                    action="dataset.ingested",
                    result="success",
                    summary={"row_count": row_count, "column_count": column_count},
                    project_id=project_id,
                    subject_id=created_by,
                    object_type="dataset_version",
                    object_id=version_id,
                    request_id=f"job:{job_id}",
                )
        finally:
            write_session.close()

    def _fail(self, job_id: str, error: DomainError) -> None:
        session = self.database.session()
        try:
            with UnitOfWork(session) as uow:
                job = uow.jobs.get(job_id)
                version = uow.datasets.get_version(
                    project_id=job.project_id,
                    dataset_id=str(job.request_json["dataset_id"]),
                    version_id=str(job.request_json["dataset_version_id"]),
                )
                source_path = self.storage.resolve_key(version.source_storage_key)
                quarantine_key = self.storage.quarantine(job_id, source_path)
                if quarantine_key is not None:
                    version.source_storage_key = quarantine_key
                if version.status == "creating":
                    uow.datasets.mark_version_failed(
                        version,
                        failure_code=error.code,
                        failure_details=error.details,
                    )
                if job.status == "queued":
                    job.status = "running"
                if job.status in {"running", "cancelling"}:
                    uow.jobs.transition(
                        job,
                        status="failed",
                        error=self._job_error(job_id, error),
                    )
                uow.audit.append(
                    action="dataset.ingestion_failed",
                    result="failed",
                    summary={"retryable": error.retryable},
                    project_id=job.project_id,
                    subject_id=job.created_by,
                    object_type="dataset_version",
                    object_id=version.version_id,
                    request_id=f"job:{job_id}",
                    error_code=error.code,
                )
        finally:
            session.close()

    @staticmethod
    def _job_error(job_id: str, error: DomainError) -> dict[str, Any]:
        return {
            "code": error.code,
            "message": error.message,
            "request_id": f"job:{job_id}",
            "retryable": error.retryable,
            "details": error.details,
        }


def process_ingestion_job(job_id: str) -> None:
    DatasetIngestionWorker(
        get_database(),
        get_file_storage(),
        worker_id=f"local:{job_id}",
    ).run(job_id)
