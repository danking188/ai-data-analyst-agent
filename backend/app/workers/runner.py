from __future__ import annotations

import argparse
import logging
import socket
import time
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select

from app.analysis.tool_registry import default_tool_registry
from app.persistence.orm.models import JobRow
from app.persistence.session import Database, get_database
from app.persistence.unit_of_work import UnitOfWork
from app.services.jobs import JobService
from app.storage.files import FileStorage, get_file_storage
from app.workers.analysis import AnalysisRunWorker
from app.workers.assistant import AssistantTurnWorker
from app.workers.assistant_retention import AssistantRetentionWorker
from app.workers.cleaning import CleaningExecuteWorker, CleaningPreviewWorker
from app.workers.comparison import VersionComparisonWorker
from app.workers.ingestion import DatasetIngestionWorker
from app.workers.quality import QualityScanWorker
from app.workers.reports import ReportExportWorker


class JobWorker(Protocol):
    def run(self, job_id: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class QueuedJob:
    job_id: str
    kind: str


SUPPORTED_JOB_KINDS = (
    "dataset_ingestion",
    "quality_scan",
    "cleaning_preview",
    "cleaning_execute",
    "analysis_run",
    "version_comparison",
    "report_export",
    "assistant_turn",
)
logger = logging.getLogger(__name__)


def recover_stale_jobs(database: Database) -> int:
    session = database.session()
    try:
        with UnitOfWork(session):
            recovered = JobService(session).recover_stale()
        if recovered:
            logger.warning("recovered %s stale jobs", recovered)
        return recovered
    finally:
        session.close()


def next_queued_job(database: Database) -> QueuedJob | None:
    session = database.session()
    try:
        row = session.execute(
            select(JobRow.job_id, JobRow.kind)
            .where(JobRow.kind.in_(SUPPORTED_JOB_KINDS), JobRow.status == "queued")
            .order_by(JobRow.created_at, JobRow.job_id)
            .limit(1)
        ).one_or_none()
        return QueuedJob(job_id=str(row.job_id), kind=str(row.kind)) if row else None
    finally:
        session.close()


def build_workers(
    database: Database,
    storage: FileStorage,
    *,
    worker_id: str,
) -> dict[str, JobWorker]:
    return {
        "dataset_ingestion": DatasetIngestionWorker(database, storage, worker_id=worker_id),
        "quality_scan": QualityScanWorker(database, storage, worker_id=worker_id),
        "cleaning_preview": CleaningPreviewWorker(database, storage, worker_id=worker_id),
        "cleaning_execute": CleaningExecuteWorker(database, storage, worker_id=worker_id),
        "analysis_run": AnalysisRunWorker(
            database,
            storage,
            default_tool_registry,
            worker_id=worker_id,
        ),
        "version_comparison": VersionComparisonWorker(database, storage, worker_id=worker_id),
        "report_export": ReportExportWorker(database, storage, worker_id=worker_id),
        "assistant_turn": AssistantTurnWorker(database, worker_id=worker_id),
    }


def run_once(database: Database, workers: dict[str, JobWorker]) -> bool:
    queued = next_queued_job(database)
    return workers[queued.kind].run(queued.job_id) if queued else False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--worker-id", default=f"{socket.gethostname()}-worker")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args()
    database = get_database()
    workers = build_workers(
        database,
        get_file_storage(),
        worker_id=args.worker_id,
    )
    if args.once:
        run_once(database, workers)
        AssistantRetentionWorker(database).run()
        return
    retention = AssistantRetentionWorker(database)
    next_retention_at = 0.0
    next_recovery_at = 0.0
    while True:
        now = time.monotonic()
        if now >= next_recovery_at:
            recover_stale_jobs(database)
            next_recovery_at = now + 60
        if now >= next_retention_at:
            retention.run()
            next_retention_at = now + 3600
        if not run_once(database, workers):
            time.sleep(max(args.poll_seconds, 0.1))


if __name__ == "__main__":
    main()
