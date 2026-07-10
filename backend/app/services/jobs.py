from __future__ import annotations

from sqlalchemy.orm import Session

from app.api.schemas import Job, JobError
from app.core.clock import utc_now
from app.domain.enums import TERMINAL_JOB_STATUSES, JobStatus
from app.domain.errors import DomainError, not_found
from app.persistence.orm.models import JobRow
from app.persistence.repositories.jobs import JobRepository


def job_to_schema(row: JobRow) -> Job:
    error = JobError.model_validate(row.error_json) if row.error_json else None
    return Job(
        job_id=row.job_id,
        kind=row.kind,
        status=row.status,
        progress=row.progress,
        current_step=row.current_step,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        retry_after_ms=row.retry_after_ms,
        created_at=row.created_at,
        updated_at=row.updated_at,
        error=error,
    )


class JobService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.jobs = JobRepository(session)

    def get(self, job_id: str, *, subject_id: str) -> Job:
        row = self.jobs.get_for_subject(job_id, subject_id)
        if row is None:
            raise not_found()
        return job_to_schema(row)

    def cancel(self, job_id: str, *, subject_id: str) -> Job:
        row = self.jobs.get_for_subject(job_id, subject_id)
        if row is None:
            raise not_found()
        status = JobStatus(row.status)
        if status in TERMINAL_JOB_STATUSES:
            raise DomainError("JOB_NOT_CANCELLABLE", "任务已进入不可取消状态", 409)
        now = utc_now()
        if status == JobStatus.QUEUED:
            row.status = JobStatus.CANCELLED.value
            row.completed_at = now
        else:
            row.status = JobStatus.CANCELLING.value
            row.cancel_requested_at = now
        row.updated_at = now
        self.session.flush()
        return job_to_schema(row)

    def recover_stale(self) -> int:
        return self.jobs.recover_stale(utc_now())
