from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


class Database:
    def __init__(
        self,
        url: str,
        *,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_recycle_seconds: int = 300,
    ) -> None:
        url = normalize_database_url(url)
        if url.startswith("sqlite:///"):
            db_path = Path(url.removeprefix("sqlite:///"))
            if db_path.parent != Path("."):
                db_path.parent.mkdir(parents=True, exist_ok=True)
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        engine_options: dict[str, object] = {
            "connect_args": connect_args,
            "pool_pre_ping": True,
        }
        if url.startswith("postgresql+"):
            engine_options.update(
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_recycle=pool_recycle_seconds,
            )
        self.engine = create_engine(url, **engine_options)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            autoflush=False,
            expire_on_commit=False,
        )
        if url.startswith("sqlite"):
            self._configure_sqlite(self.engine)

    @staticmethod
    def _configure_sqlite(engine: Engine) -> None:
        @event.listens_for(engine, "connect")
        def set_sqlite_pragmas(dbapi_connection: object, connection_record: object) -> None:
            del connection_record
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("PRAGMA busy_timeout = 5000")
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute("PRAGMA synchronous = NORMAL")
            cursor.close()

    def session(self) -> Session:
        return self.session_factory()


@lru_cache(maxsize=1)
def get_database() -> Database:
    settings = get_settings()
    return Database(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_recycle_seconds=settings.database_pool_recycle_seconds,
    )


def get_session() -> Generator[Session, None, None]:
    session = get_database().session()
    try:
        yield session
    finally:
        session.close()
