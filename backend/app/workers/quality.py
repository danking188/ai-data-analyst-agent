from __future__ import annotations

from typing import Any

import pandas as pd

from app.domain.errors import DomainError
from app.persistence.orm.models import DatasetVersionRow
from app.persistence.repositories.jobs import JobRepository
from app.persistence.session import Database, get_database
from app.persistence.unit_of_work import UnitOfWork
from app.quality.engine import QualityEngine
from app.storage.files import FileStorage


class QualityScanWorker:
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
                    "质量扫描执行失败",
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
            if job.kind != "quality_scan":
                raise DomainError("STATE_CONFLICT", "Job 类型不是质量扫描", 409)
            version_id = str(job.request_json["dataset_version_id"])
            version = read_session.get(DatasetVersionRow, version_id)
            if (
                version is None
                or version.project_id != job.project_id
                or version.status != "ready"
                or not version.data_storage_key
            ):
                raise DomainError("STATE_CONFLICT", "数据版本尚未就绪", 409)
            data_path = self.storage.resolve_key(version.data_storage_key)
            rules = list(job.request_json.get("rules") or [])
            force = bool(job.request_json.get("force", False))
            project_id = job.project_id
            created_by = job.created_by
        finally:
            read_session.close()

        frame = pd.read_parquet(data_path)
        findings = QualityEngine().scan(frame, rules=rules)

        write_session = self.database.session()
        try:
            with UnitOfWork(write_session) as uow:
                current_job = uow.jobs.get(job_id)
                if uow.quality_issues.exists_for_version(version_id) and not force:
                    raise DomainError(
                        "STATE_CONFLICT",
                        "该数据版本已存在质量扫描结果；如需重扫请设置 force=true",
                        409,
                    )
                rows = uow.quality_issues.replace_findings(
                    project_id=project_id,
                    dataset_version_id=version_id,
                    findings=findings,
                )
                uow.jobs.transition(
                    current_job,
                    status="succeeded",
                    resource_type="quality_scan",
                    resource_id=version_id,
                )
                uow.audit.append(
                    action="quality.scan_completed",
                    result="success",
                    summary={"issue_count": len(rows), "rules": rules or "all"},
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
                if job.status == "queued":
                    job.status = "running"
                if job.status in {"running", "cancelling"}:
                    uow.jobs.transition(
                        job,
                        status="failed",
                        error=self._job_error(job_id, error),
                    )
                uow.audit.append(
                    action="quality.scan_failed",
                    result="failed",
                    summary={"retryable": error.retryable},
                    project_id=job.project_id,
                    subject_id=job.created_by,
                    object_type="dataset_version",
                    object_id=str(job.request_json.get("dataset_version_id")),
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


def process_quality_scan_job(job_id: str) -> None:
    from app.core.config import get_settings

    QualityScanWorker(
        get_database(),
        FileStorage(get_settings().data_root),
        worker_id=f"local:{job_id}",
    ).run(job_id)
