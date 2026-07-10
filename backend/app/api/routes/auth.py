from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.schemas import LoginRequest, SessionInfo
from app.core.config import Settings, get_settings
from app.domain.errors import DomainError
from app.security.auth import (
    Principal,
    authenticate,
    create_session_token,
    verify_login,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=SessionInfo, operation_id="login")
def login(
    payload: LoginRequest,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionInfo:
    if settings.auth_mode != "jwt":
        raise DomainError("STATE_CONFLICT", "当前部署未启用账号登录", 409)
    if not verify_login(payload.username, payload.password, settings):
        raise DomainError("AUTH_REQUIRED", "用户名或密码错误", 401)
    token, max_age = create_session_token(payload.username, settings)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return SessionInfo(subject_id=payload.username, expires_in_seconds=max_age)


@router.get("/session", response_model=SessionInfo, operation_id="getSession")
def get_session(
    principal: Annotated[Principal, Depends(authenticate)],
) -> SessionInfo:
    return SessionInfo(subject_id=principal.subject_id)


@router.post("/logout", status_code=204, operation_id="logout")
def logout(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
