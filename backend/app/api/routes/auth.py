from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.schemas import LoginRequest, RegisterRequest, SessionInfo
from app.core.config import Settings, get_settings
from app.domain.errors import DomainError
from app.persistence.session import get_session as get_database_session
from app.security.auth import (
    Principal,
    authenticate,
    create_session_token,
)
from app.services.accounts import AccountService

router = APIRouter(prefix="/auth", tags=["Auth"])


def _set_session_cookie(
    response: Response,
    *,
    subject_id: str,
    settings: Settings,
) -> int:
    token, max_age = create_session_token(subject_id, settings)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return max_age


@router.post(
    "/register",
    response_model=SessionInfo,
    status_code=status.HTTP_201_CREATED,
    operation_id="register",
)
def register(
    payload: RegisterRequest,
    response: Response,
    session: Annotated[Session, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionInfo:
    if settings.auth_mode != "jwt" or not settings.registration_enabled:
        raise DomainError("STATE_CONFLICT", "当前部署未开放账号注册", 409)
    user = AccountService(session).register(username=payload.username, password=payload.password)
    session.commit()
    max_age = _set_session_cookie(response, subject_id=user.username, settings=settings)
    return SessionInfo(subject_id=user.username, expires_in_seconds=max_age)


@router.post("/login", response_model=SessionInfo, operation_id="login")
def login(
    payload: LoginRequest,
    response: Response,
    session: Annotated[Session, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionInfo:
    if settings.auth_mode != "jwt":
        raise DomainError("STATE_CONFLICT", "当前部署未启用账号登录", 409)
    user = AccountService(session).authenticate(
        username=payload.username,
        password=payload.password,
    )
    session.commit()
    max_age = _set_session_cookie(response, subject_id=user.username, settings=settings)
    return SessionInfo(subject_id=user.username, expires_in_seconds=max_age)


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
