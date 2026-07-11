import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app import __version__
from app.api.schemas import (
    Health,
    PollingPolicy,
    Readiness,
    ReadinessDependency,
    SystemCapabilities,
)
from app.core.clock import utc_now
from app.core.config import Settings, get_settings
from app.domain.errors import DomainError
from app.persistence.session import get_database
from app.security.auth import Principal, authenticate
from app.storage.files import get_file_storage

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health", response_model=Health, operation_id="getHealth")
def get_health() -> Health:
    return Health(status="ok", version=__version__, timestamp=utc_now())


@router.get("/health/ready", response_model=Readiness, operation_id="getReadiness")
def get_readiness(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Readiness:
    database = get_database()
    try:
        with database.engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
        get_file_storage().healthcheck()
    except Exception as exc:
        logger.exception("readiness dependency check failed")
        raise DomainError(
            "DEPENDENCY_UNAVAILABLE",
            "数据库或对象存储暂时不可用",
            503,
            retryable=True,
        ) from exc
    return Readiness(
        status="ready",
        database=ReadinessDependency(status="ok", backend=database.engine.dialect.name),
        object_storage=ReadinessDependency(status="ok", backend=settings.storage_backend),
        timestamp=utc_now(),
    )


@router.get(
    "/system/capabilities",
    response_model=SystemCapabilities,
    operation_id="getCapabilities",
)
def get_capabilities(
    principal: Annotated[Principal, Depends(authenticate)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SystemCapabilities:
    del principal
    return SystemCapabilities(
        api_version="v1",
        supported_file_types=["csv", "xls", "xlsx", "parquet"],
        max_upload_bytes=settings.max_upload_bytes,
        natural_language_analysis=False,
        auth_enabled=settings.auth_enabled,
        polling=PollingPolicy(
            initial_interval_ms=1000,
            steady_interval_ms=3000,
            background_interval_ms=10000,
        ),
    )
