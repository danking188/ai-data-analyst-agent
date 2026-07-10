from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.request_context import get_request_id
from app.domain.errors import DomainError

logger = logging.getLogger(__name__)


def error_payload(
    request: Request,
    *,
    code: str,
    message: str,
    retryable: bool,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": get_request_id(request),
            "retryable": retryable,
            "details": details or {},
        }
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(
                request,
                code=exc.code,
                message=exc.message,
                retryable=exc.retryable,
                details=exc.details,
            ),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        details = {
            "fields": [
                {
                    "location": [str(part) for part in error["loc"]],
                    "message": error["msg"],
                    "type": error["type"],
                }
                for error in exc.errors()
            ]
        }
        return JSONResponse(
            status_code=422,
            content=error_payload(
                request,
                code="VALIDATION_ERROR",
                message="请求参数校验失败",
                retryable=False,
                details=details,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            code, message = "RESOURCE_NOT_FOUND", "资源不存在或无权访问"
        elif exc.status_code == 405:
            code, message = "METHOD_NOT_ALLOWED", "请求方法不受支持"
        else:
            code, message = "HTTP_ERROR", "请求无法处理"
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(
                request,
                code=code,
                message=message,
                retryable=False,
            ),
        )

    @app.exception_handler(OperationalError)
    async def handle_database_operational_error(
        request: Request,
        exc: OperationalError,
    ) -> JSONResponse:
        logger.exception(
            "database operational error",
            extra={"request_id": get_request_id(request)},
        )
        return JSONResponse(
            status_code=503,
            content=error_payload(
                request,
                code="DATABASE_UNAVAILABLE",
                message="数据库暂时不可用",
                retryable=True,
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unexpected error", extra={"request_id": get_request_id(request)})
        return JSONResponse(
            status_code=500,
            content=error_payload(
                request,
                code="INTERNAL_ERROR",
                message="服务发生未预期错误",
                retryable=False,
            ),
        )
