from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _read_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    app_env: str
    api_prefix: str
    database_url: str
    data_root: Path
    max_upload_bytes: int
    auth_mode: str
    dev_auth_token: str
    jwt_secret: str
    jwt_algorithm: str
    jwt_audience: str
    jwt_issuer: str
    login_username: str
    login_password: str
    registration_enabled: bool
    session_cookie_name: str
    session_cookie_secure: bool
    session_ttl_seconds: int
    cors_origins: tuple[str, ...]

    @property
    def auth_enabled(self) -> bool:
        return self.auth_mode in {"dev_token", "jwt"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _read_env_file(Path(".env"))
    settings = Settings(
        app_env=os.getenv("APP_ENV", "development"),
        api_prefix=os.getenv("API_PREFIX", "/api/v1"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./data/app.db"),
        data_root=Path(os.getenv("DATA_ROOT", "./data")).resolve(),
        max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", "524288000")),
        auth_mode=os.getenv("AUTH_MODE", "dev_token"),
        dev_auth_token=os.getenv("DEV_AUTH_TOKEN", "local-development-token"),
        jwt_secret=os.getenv("JWT_SECRET", "development-only-secret"),
        jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
        jwt_audience=os.getenv("JWT_AUDIENCE", "ai-data-analyst"),
        jwt_issuer=os.getenv("JWT_ISSUER", "ai-data-analyst"),
        login_username=os.getenv("LOGIN_USERNAME", "analyst"),
        login_password=os.getenv("LOGIN_PASSWORD", ""),
        registration_enabled=os.getenv("REGISTRATION_ENABLED", "true").lower()
        in {"1", "true", "yes"},
        session_cookie_name=os.getenv("SESSION_COOKIE_NAME", "datatrace_session"),
        session_cookie_secure=os.getenv("SESSION_COOKIE_SECURE", "false").lower()
        in {"1", "true", "yes"},
        session_ttl_seconds=int(os.getenv("SESSION_TTL_SECONDS", "43200")),
        cors_origins=tuple(
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
            if origin.strip()
        ),
    )
    if settings.auth_mode not in {"dev_token", "jwt"}:
        raise ValueError("AUTH_MODE must be dev_token or jwt")
    if settings.max_upload_bytes <= 0:
        raise ValueError("MAX_UPLOAD_BYTES must be positive")
    if settings.session_ttl_seconds <= 0:
        raise ValueError("SESSION_TTL_SECONDS must be positive")
    if settings.auth_mode == "jwt" and not settings.login_password:
        raise ValueError("LOGIN_PASSWORD is required when AUTH_MODE=jwt")
    if settings.app_env == "production" and settings.auth_mode == "jwt":
        if len(settings.jwt_secret) < 32 or settings.jwt_secret.startswith("replace-with-"):
            raise ValueError(
                "JWT_SECRET must be a non-placeholder secret of at least 32 characters"
            )
        if len(settings.login_password) < 12 or settings.login_password.startswith("replace-with-"):
            raise ValueError(
                "LOGIN_PASSWORD must be a non-placeholder password of at least 12 characters"
            )
    return settings
