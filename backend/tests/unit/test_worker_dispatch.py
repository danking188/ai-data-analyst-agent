from __future__ import annotations

from typing import cast

import pytest
from fastapi import BackgroundTasks

from app.core.config import get_settings
from app.persistence.session import Database
from app.storage.files import FileStorage
from app.workers.dispatch import schedule_job
from app.workers.runner import (
    SUPPORTED_JOB_KINDS,
    JobWorker,
    QueuedJob,
    build_workers,
    run_once,
)


def test_schedule_job_uses_background_tasks_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JOB_EXECUTION_MODE", raising=False)
    get_settings.cache_clear()
    tasks = BackgroundTasks()

    schedule_job(tasks, lambda job_id: None, "job_1")

    assert len(tasks.tasks) == 1
    get_settings.cache_clear()


def test_schedule_job_leaves_work_for_runner_in_worker_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JOB_EXECUTION_MODE", "worker")
    get_settings.cache_clear()
    tasks = BackgroundTasks()

    schedule_job(tasks, lambda job_id: None, "job_1")

    assert tasks.tasks == []
    get_settings.cache_clear()


def test_build_workers_covers_every_supported_job_kind() -> None:
    workers = build_workers(
        cast(Database, object()),
        cast(FileStorage, object()),
        worker_id="test-worker",
    )

    assert set(workers) == set(SUPPORTED_JOB_KINDS)


class RecordingWorker:
    def __init__(self) -> None:
        self.job_ids: list[str] = []

    def run(self, job_id: str) -> bool:
        self.job_ids.append(job_id)
        return True


def test_run_once_dispatches_job_to_matching_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = RecordingWorker()
    monkeypatch.setattr(
        "app.workers.runner.next_queued_job",
        lambda database: QueuedJob("job_1", "quality_scan"),
    )

    handled = run_once(
        cast(Database, object()),
        {"quality_scan": cast(JobWorker, worker)},
    )

    assert handled is True
    assert worker.job_ids == ["job_1"]
