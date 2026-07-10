from __future__ import annotations

import argparse
import time

from sqlalchemy import select

from app.core.config import get_settings
from app.persistence.orm.models import JobRow
from app.persistence.session import get_database
from app.storage.files import FileStorage
from app.workers.ingestion import DatasetIngestionWorker


def next_ingestion_job_id() -> str | None:
    session = get_database().session()
    try:
        return session.scalar(
            select(JobRow.job_id)
            .where(JobRow.kind == "dataset_ingestion", JobRow.status == "queued")
            .order_by(JobRow.created_at, JobRow.job_id)
            .limit(1)
        )
    finally:
        session.close()


def run_once(worker: DatasetIngestionWorker) -> bool:
    job_id = next_ingestion_job_id()
    return worker.run(job_id) if job_id else False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--worker-id", default="local-ingestion-worker")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args()
    worker = DatasetIngestionWorker(
        get_database(),
        FileStorage(get_settings().data_root),
        worker_id=args.worker_id,
    )
    if args.once:
        run_once(worker)
        return
    while True:
        if not run_once(worker):
            time.sleep(max(args.poll_seconds, 0.1))


if __name__ == "__main__":
    main()
