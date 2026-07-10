from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.ids import new_id
from app.domain.enums import TERMINAL_JOB_STATUSES
from app.domain.errors import not_found, state_conflict
from app.persistence.orm.models import JobRow, ProjectMemberRow

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running", "cancelling", "cancelled", "failed"},
    "running": {"cancelling", "blocked", "succeeded", "failed"},
    "cancelling": {"cancelled", "failed"},
    "blocked": set(),
    "cancelled": set(),
    "succeeded": set(),
    "failed": set(),
}


class JobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        project_id: str,
        kind: str,
        request: dict[str, Any],
        subject_id: str,
        job_id: str | None = None,
    ) -> JobRow:
        now = utc_now()
        job = JobRow(
            job_id=job_id or new_id("job_"),
            project_id=project_id,
            kind=kind,
            status="queued",
            progress=0,
            current_step=None,
            resource_type=None,
            resource_id=None,
            request_json=request,
            retry_after_ms=None,
            lease_owner=None,
            lease_expires_at=None,
            heartbeat_at=None,
            cancel_requested_at=None,
            error_json=None,
            created_by=subject_id,
            created_at=now,
            updated_at=now,
            started_at=None,
            completed_at=None,
        )
        self.session.add(job)
        self.session.flush()
        return job

    def get(self, job_id: str) -> JobRow:
        job = self.session.get(JobRow, job_id)
        if job is None:
            raise not_found()
        return job

    def get_for_project(self, *, project_id: str, job_id: str) -> JobRow:
        job = self.session.scalar(
            select(JobRow).where(JobRow.project_id == project_id, JobRow.job_id == job_id)
        )
        if job is None:
            raise not_found()
        return job

    def get_for_subject(self, job_id: str, subject_id: str) -> JobRow | None:
        return self.session.scalar(
            select(JobRow)
            .join(
                ProjectMemberRow,
                ProjectMemberRow.project_id == JobRow.project_id,
            )
            .where(
                JobRow.job_id == job_id,
                ProjectMemberRow.subject_id == subject_id,
            )
        )

    def claim(
        self,
        *,
        job_id: str,
        worker_id: str,
        lease_seconds: int = 60,
    ) -> bool:
        now = utc_now()
        result = self.session.execute(
            update(JobRow)
            .where(JobRow.job_id == job_id, JobRow.status == "queued")
            .values(
                status="running",
                lease_owner=worker_id,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                heartbeat_at=now,
                started_at=now,
                updated_at=now,
            )
        )
        self.session.flush()
        return bool(getattr(result, "rowcount", 0) == 1)

    def heartbeat(
        self,
        *,
        job: JobRow,
        worker_id: str,
        progress: int,
        current_step: str | None,
        lease_seconds: int = 60,
    ) -> None:
        if job.status != "running" or job.lease_owner != worker_id:
            raise state_conflict("当前 worker 不持有此 Job")
        if not 0 <= progress <= 100:
            raise ValueError("progress must be between 0 and 100")
        now = utc_now()
        job.progress = progress
        job.current_step = current_step
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        job.updated_at = now
        self.session.flush()

    def transition(
        self,
        job: JobRow,
        *,
        status: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        error: dict[str, Any] | None = None,
    ) -> JobRow:
        if status not in _ALLOWED_TRANSITIONS[job.status]:
            raise state_conflict(
                "Job 状态迁移不合法",
                current_status=job.status,
                requested_status=status,
            )
        now = utc_now()
        job.status = status
        job.updated_at = now
        if status == "succeeded":
            job.progress = 100
            job.resource_type = resource_type
            job.resource_id = resource_id
        if status == "failed":
            job.error_json = error
        if status in {item.value for item in TERMINAL_JOB_STATUSES}:
            job.completed_at = now
            job.lease_owner = None
            job.lease_expires_at = None
        self.session.flush()
        return job

    def request_cancel(self, job: JobRow) -> JobRow:
        if job.status not in {"queued", "running"}:
            raise state_conflict("当前 Job 状态不可取消", current_status=job.status)
        now = utc_now()
        job.status = "cancelling"
        job.cancel_requested_at = now
        job.updated_at = now
        self.session.flush()
        return job

    def recover_expired_leases(self) -> int:
        now = utc_now()
        error = {
            "code": "EXECUTOR_UNAVAILABLE",
            "message": "执行器租约已过期",
            "retryable": True,
            "details": {},
        }
        result = self.session.execute(
            update(JobRow)
            .where(
                JobRow.status.in_(("running", "cancelling")),
                JobRow.lease_expires_at.is_not(None),
                JobRow.lease_expires_at < now,
            )
            .values(
                status="failed",
                error_json=error,
                completed_at=now,
                updated_at=now,
                lease_owner=None,
                lease_expires_at=None,
            )
        )
        self.session.flush()
        return int(getattr(result, "rowcount", 0) or 0)

    def recover_stale(self, now: object) -> int:
        error = {
            "code": "EXECUTOR_UNAVAILABLE",
            "message": "执行器租约已过期，任务未能恢复",
            "request_id": "system-recovery",
            "retryable": True,
            "details": {},
        }
        result = self.session.execute(
            update(JobRow)
            .where(
                JobRow.status.in_(("running", "cancelling")),
                JobRow.lease_expires_at.is_not(None),
                JobRow.lease_expires_at < now,
            )
            .values(
                status="failed",
                error_json=error,
                completed_at=now,
                updated_at=now,
                lease_owner=None,
                lease_expires_at=None,
            )
        )
        self.session.flush()
        return int(getattr(result, "rowcount", 0) or 0)
