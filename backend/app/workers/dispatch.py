from __future__ import annotations

from collections.abc import Callable

from fastapi import BackgroundTasks

from app.core.config import get_settings


def schedule_job(
    background_tasks: BackgroundTasks,
    task: Callable[[str], None],
    job_id: str,
) -> None:
    if get_settings().job_execution_mode == "background":
        background_tasks.add_task(task, job_id)
