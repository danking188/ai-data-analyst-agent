from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated, Any

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.clock import utc_now
from app.core.config import Settings, get_settings
from app.domain.errors import DomainError


@dataclass(frozen=True, slots=True)
class Principal:
    subject_id: str


bearer = HTTPBearer(auto_error=False)


def _auth_error(message: str = "需要有效的 Bearer 凭证") -> DomainError:
    return DomainError("AUTH_REQUIRED", message, 401)


def authenticate(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    token = None
    if credentials is not None and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    if token is None:
        token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise _auth_error()
    if settings.auth_mode == "dev_token":
        if token != settings.dev_auth_token:
            raise _auth_error("开发凭证无效")
        return Principal(subject_id="dev-user")

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
    except jwt.PyJWTError as exc:
        raise _auth_error("登录凭证无效或已过期") from exc
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise _auth_error("登录凭证缺少主体")
    return Principal(subject_id=subject)


def verify_login(username: str, password: str, settings: Settings) -> bool:
    return hmac.compare_digest(username, settings.login_username) and hmac.compare_digest(
        password,
        settings.login_password,
    )


def create_session_token(subject_id: str, settings: Settings) -> tuple[str, int]:
    expires_at = utc_now() + timedelta(seconds=settings.session_ttl_seconds)
    token = jwt.encode(
        {
            "sub": subject_id,
            "iat": utc_now(),
            "exp": expires_at,
            "aud": settings.jwt_audience,
            "iss": settings.jwt_issuer,
            "kind": "session",
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token, settings.session_ttl_seconds
