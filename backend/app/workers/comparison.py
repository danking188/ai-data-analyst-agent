from __future__ import annotations

import json
from typing import Any

import pandas as pd

from app.domain.errors import DomainError
from app.persistence.repositories.jobs import JobRepository
from app.persistence.session import Database, get_database
from app.persistence.unit_of_work import UnitOfWork
from app.storage.files import FileStorage, get_file_storage


def _masked_records(
    frame: pd.DataFrame,
    *,
    sensitive_columns: set[str],
    limit: int = 5,
) -> list[dict[str, Any]]:
    sample = frame.head(limit).copy()
    for column in sensitive_columns & set(sample.columns):
        sample[column] = "******"
    return list(json.loads(sample.to_json(orient="records", date_format="iso")))


class VersionComparisonWorker:
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
                    "版本比较执行失败",
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
            uow = UnitOfWork(read_session)
            job = uow.jobs.get(job_id)
            if job.kind != "version_comparison":
                raise DomainError("STATE_CONFLICT", "Job 类型不是版本比较", 409)
            dataset_id = str(job.request_json["dataset_id"])
            base_version_id = str(job.request_json["base_version_id"])
            compare_version_id = str(job.request_json["compare_version_id"])
            base = uow.datasets.get_version(
                project_id=job.project_id,
                dataset_id=dataset_id,
                version_id=base_version_id,
            )
            compare = uow.datasets.get_version(
                project_id=job.project_id,
                dataset_id=dataset_id,
                version_id=compare_version_id,
            )
            if (
                base.status != "ready"
                or compare.status != "ready"
                or not base.data_storage_key
                or not compare.data_storage_key
            ):
                raise DomainError("STATE_CONFLICT", "只能比较 ready 数据版本", 409)
            base_path = self.storage.resolve_key(base.data_storage_key)
            compare_path = self.storage.resolve_key(compare.data_storage_key)
            sensitive_columns = uow.schemas.sensitive_columns(
                base_version_id
            ) | uow.schemas.sensitive_columns(compare_version_id)
            include_samples = bool(job.request_json.get("include_sample_changes", True))
            project_id = job.project_id
            created_by = job.created_by
        finally:
            read_session.close()

        base_frame = pd.read_parquet(base_path)
        compare_frame = pd.read_parquet(compare_path)
        base_columns = set(map(str, base_frame.columns))
        compare_columns = set(map(str, compare_frame.columns))
        common_columns = sorted(base_columns & compare_columns)
        type_changes = [
            {
                "column": column,
                "base_type": str(base_frame[column].dtype),
                "compare_type": str(compare_frame[column].dtype),
            }
            for column in common_columns
            if str(base_frame[column].dtype) != str(compare_frame[column].dtype)
        ]
        missing_changes = [
            {
                "column": column,
                "base_missing": int(base_frame[column].isna().sum()),
                "compare_missing": int(compare_frame[column].isna().sum()),
            }
            for column in common_columns
            if int(base_frame[column].isna().sum()) != int(compare_frame[column].isna().sum())
        ]
        result: dict[str, Any] = {
            "dataset_id": dataset_id,
            "base_version_id": base_version_id,
            "compare_version_id": compare_version_id,
            "row_count": {
                "base": len(base_frame),
                "compare": len(compare_frame),
                "delta": len(compare_frame) - len(base_frame),
            },
            "column_count": {
                "base": len(base_frame.columns),
                "compare": len(compare_frame.columns),
                "delta": len(compare_frame.columns) - len(base_frame.columns),
            },
            "added_columns": sorted(compare_columns - base_columns),
            "removed_columns": sorted(base_columns - compare_columns),
            "type_changes": type_changes,
            "missing_value_changes": missing_changes,
            "sample_changes": (
                {
                    "base": _masked_records(
                        base_frame,
                        sensitive_columns=sensitive_columns,
                    ),
                    "compare": _masked_records(
                        compare_frame,
                        sensitive_columns=sensitive_columns,
                    ),
                }
                if include_samples
                else None
            ),
        }

        write_session = self.database.session()
        try:
            with UnitOfWork(write_session) as uow:
                current_job = uow.jobs.get(job_id)
                artifact = uow.artifacts.create_version_comparison(
                    project_id=project_id,
                    dataset_version_id=compare_version_id,
                    base_version_id=base_version_id,
                    result=result,
                )
                uow.jobs.transition(
                    current_job,
                    status="succeeded",
                    resource_type="artifact",
                    resource_id=artifact.artifact_id,
                )
                uow.audit.append(
                    action="dataset_versions.compared",
                    result="success",
                    summary={
                        "base_version_id": base_version_id,
                        "compare_version_id": compare_version_id,
                    },
                    project_id=project_id,
                    subject_id=created_by,
                    object_type="artifact",
                    object_id=artifact.artifact_id,
                    request_id=f"job:{job_id}",
                )
        finally:
            write_session.close()

    def _fail(self, job_id: str, error: DomainError) -> None:
        session = self.database.session()
        try:
            with UnitOfWork(session) as uow:
                job = uow.jobs.get(job_id)
                if job.status == "queued":
                    job.status = "running"
                if job.status in {"running", "cancelling"}:
                    uow.jobs.transition(
                        job,
                        status="failed",
                        error={
                            "code": error.code,
                            "message": error.message,
                            "request_id": f"job:{job_id}",
                            "retryable": error.retryable,
                            "details": error.details,
                        },
                    )
        finally:
            session.close()


def process_version_comparison_job(job_id: str) -> None:
    VersionComparisonWorker(
        get_database(),
        get_file_storage(),
        worker_id=f"local:{job_id}",
    ).run(job_id)
