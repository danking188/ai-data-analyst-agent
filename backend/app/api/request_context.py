from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.ids import new_request_id

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{8,80}$")


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
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", new_request_id())
