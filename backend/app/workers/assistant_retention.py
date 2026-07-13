from __future__ import annotations

from datetime import timedelta

from app.core.clock import utc_now
from app.core.config import Settings, get_settings
from app.persistence.session import Database
from app.persistence.unit_of_work import UnitOfWork


class AssistantRetentionWorker:
    def __init__(self, database: Database, *, settings: Settings | None = None) -> None:
        self.database = database
        self.settings = settings or get_settings()

    def run(self) -> dict[str, int]:
        now = utc_now()
        session = self.database.session()
        try:
            with UnitOfWork(session) as uow:
                return uow.assistant.apply_retention(
                    scrub_before=now - timedelta(days=self.settings.llm_retention_days),
                    archive_before=now
                    - timedelta(days=self.settings.llm_archive_inactive_days),
                )
        finally:
            session.close()
