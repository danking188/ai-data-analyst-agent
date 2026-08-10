from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.exc import OperationalError
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import __version__
from app.api.error_handlers import register_error_handlers
from app.api.request_context import CSRFMiddleware, RequestIdMiddleware, SecurityHeadersMiddleware
from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.persistence.session import get_database
from app.persistence.unit_of_work import UnitOfWork
from app.services.accounts import AccountService
from app.services.jobs import JobService
from app.static import SPAStaticFiles

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    del app
    database = get_database()
    session = database.session()
    try:
        with UnitOfWork(session):
            settings = get_settings()
            if settings.auth_mode == "jwt":
                AccountService(session).ensure_bootstrap_user(
                    username=settings.login_username,
                    password=settings.login_password,
                )
            recovered = JobService(session).recover_stale()
            if recovered:
                logger.warning("recovered %s stale jobs", recovered)
    except OperationalError:
        session.rollback()
        logger.warning("database is not migrated yet; stale job recovery skipped")
    finally:
        session.close()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(production=settings.app_env == "production")
    app = FastAPI(
        title="AI Data Analyst Agent API",
        version=__version__,
        description="Contract-first backend for evidence-based data analysis.",
        lifespan=lifespan,
        docs_url=None if settings.app_env == "production" else "/docs",
        redoc_url=None if settings.app_env == "production" else "/redoc",
        openapi_url=None if settings.app_env == "production" else "/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "If-Match",
            "X-CSRF-Token",
            "X-Request-Id",
        ],
        expose_headers=["X-Request-Id", "X-Process-Time-Ms"],
    )
    app.add_middleware(CSRFMiddleware, settings=settings)
    app.add_middleware(
        SecurityHeadersMiddleware,
        enable_hsts=settings.app_env == "production" and settings.session_cookie_secure,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.trusted_hosts))
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    frontend_dist = os.getenv("FRONTEND_DIST_DIR")
    if frontend_dist:
        app.mount("/", SPAStaticFiles(directory=frontend_dist, html=True), name="frontend")
    return app


app = create_app()
