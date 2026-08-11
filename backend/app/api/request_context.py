from __future__ import annotations

import logging
import re
import secrets
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import Settings
from app.core.ids import new_request_id

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{8,80}$")
logger = logging.getLogger("app.requests")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        supplied = request.headers.get("X-Request-Id")
        request_id = (
            supplied if supplied and REQUEST_ID_PATTERN.fullmatch(supplied) else new_request_id()
        )
        request.state.request_id = request_id
        started_at = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - started_at) * 1000, 2)
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Process-Time-Ms"] = str(duration_ms)
        logger.info(
            "request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "host": request.headers.get("host", "")[:255],
                "forwarded_host": request.headers.get("x-forwarded-host", "")[:255],
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response


class CSRFMiddleware(BaseHTTPMiddleware):
    """Require a double-submit token for state changes authenticated by cookies."""

    _safe_methods = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
    _public_paths = frozenset({"/auth/login", "/auth/register"})

    def __init__(self, app: object, *, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.settings = settings

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        relative_path = request.url.path.removeprefix(self.settings.api_prefix)
        has_bearer = request.headers.get("Authorization", "").lower().startswith("bearer ")
        uses_session_cookie = bool(request.cookies.get(self.settings.session_cookie_name))
        requires_token = (
            request.method not in self._safe_methods
            and relative_path not in self._public_paths
            and uses_session_cookie
            and not has_bearer
        )
        if requires_token:
            cookie_token = request.cookies.get(self.settings.csrf_cookie_name, "")
            header_token = request.headers.get("X-CSRF-Token", "")
            if not cookie_token or not header_token or not secrets.compare_digest(
                cookie_token,
                header_token,
            ):
                request_id = getattr(request.state, "request_id", new_request_id())
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "code": "CSRF_VALIDATION_FAILED",
                            "message": "请求安全校验失败，请刷新页面后重试",
                            "request_id": request_id,
                            "retryable": False,
                            "details": {},
                        }
                    },
                    headers={"X-Request-Id": request_id},
                )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, *, enable_hsts: bool) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.enable_hsts = enable_hsts

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; connect-src 'self'; font-src 'self' data:; "
            "worker-src 'self' blob:; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'none'; form-action 'self'",
        )
        if self.enable_hsts:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", new_request_id())
