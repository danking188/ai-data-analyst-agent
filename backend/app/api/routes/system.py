from typing import Annotated

from fastapi import APIRouter, Depends

from app import __version__
from app.api.schemas import Health, PollingPolicy, SystemCapabilities
from app.core.clock import utc_now
from app.core.config import Settings, get_settings
from app.security.auth import Principal, authenticate

router = APIRouter()


@router.get("/health", response_model=Health, operation_id="getHealth")
def get_health() -> Health:
    return Health(status="ok", version=__version__, timestamp=utc_now())


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
