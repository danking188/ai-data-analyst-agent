from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from app.core.clock import utc_now
from app.core.ids import new_id
from app.persistence.orm.models import JobRow
from app.persistence.session import get_database
from app.services.jobs import JobService


def seed_job(project_id: str, *, status: str, expired: bool = False) -> str:
    now = utc_now()
    job_id = new_id("job_")
    session = get_database().session()
    try:
        session.add(
            JobRow(
                job_id=job_id,
                project_id=project_id,
                kind="quality_scan",
                status=status,
                progress=25,
                current_step="扫描缺失值",
                resource_type=None,
                resource_id=None,
                request_json={},
                retry_after_ms=1000,
                lease_owner="worker-1" if status == "running" else None,
                lease_expires_at=now - timedelta(seconds=1) if expired else None,
                heartbeat_at=now,
                cancel_requested_at=None,
                error_json=None,
                created_by="dev-user",
                created_at=now,
                updated_at=now,
                started_at=now if status == "running" else None,
                completed_at=None,
            )
        )
        session.commit()
    finally:
        session.close()
    return job_id


def test_get_and_cancel_job(
    app_client: TestClient,
    auth_headers: dict[str, str],
    create_project,
) -> None:
    project = create_project(key="job-project")
    job_id = seed_job(str(project["project_id"]), status="queued")

    response = app_client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "queued"

    cancelled = app_client.post(
        f"/api/v1/jobs/{job_id}/cancel",
        headers={**auth_headers, "Idempotency-Key": "cancel-job-001"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    second = app_client.post(
        f"/api/v1/jobs/{job_id}/cancel",
        headers={**auth_headers, "Idempotency-Key": "cancel-job-001"},
    )
    assert second.status_code == 200
    assert second.json() == cancelled.json()


def test_stale_running_job_recovery(
    app_client: TestClient,
    create_project,
) -> None:
    project = create_project(key="recovery-project")
    job_id = seed_job(str(project["project_id"]), status="running", expired=True)
    session = get_database().session()
    try:
        recovered = JobService(session).recover_stale()
        session.commit()
        assert recovered == 1
        row = session.get(JobRow, job_id)
        assert row is not None
        assert row.status == "failed"
        assert row.error_json["code"] == "EXECUTOR_UNAVAILABLE"
    finally:
        session.close()
