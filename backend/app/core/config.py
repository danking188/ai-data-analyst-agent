from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePath


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
    database_pool_size: int
    database_max_overflow: int
    database_pool_recycle_seconds: int
    require_external_persistence: bool
    data_root: Path
    storage_backend: str
    storage_cache_root: Path
    s3_bucket: str
    s3_endpoint_url: str | None
    s3_region: str
    s3_access_key_id: str | None
    s3_secret_access_key: str | None
    s3_prefix: str
    s3_force_path_style: bool
    s3_server_side_encryption: str | None
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
        database_pool_size=int(os.getenv("DATABASE_POOL_SIZE", "5")),
        database_max_overflow=int(os.getenv("DATABASE_MAX_OVERFLOW", "10")),
        database_pool_recycle_seconds=int(os.getenv("DATABASE_POOL_RECYCLE_SECONDS", "300")),
        require_external_persistence=os.getenv(
            "REQUIRE_EXTERNAL_PERSISTENCE", "false"
        ).lower()
        in {"1", "true", "yes"},
        data_root=Path(os.getenv("DATA_ROOT", "./data")).resolve(),
        storage_backend=os.getenv("STORAGE_BACKEND", "local").lower(),
        storage_cache_root=Path(
            os.getenv("STORAGE_CACHE_ROOT", "/tmp/datatrace-storage-cache")
        ).resolve(),
        s3_bucket=os.getenv("S3_BUCKET", ""),
        s3_endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
        s3_region=os.getenv("S3_REGION", "auto"),
        s3_access_key_id=os.getenv("S3_ACCESS_KEY_ID") or None,
        s3_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY") or None,
        s3_prefix=os.getenv("S3_PREFIX", "datatrace").strip("/"),
        s3_force_path_style=os.getenv("S3_FORCE_PATH_STYLE", "false").lower()
        in {"1", "true", "yes"},
        s3_server_side_encryption=os.getenv("S3_SERVER_SIDE_ENCRYPTION") or None,
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
    if settings.database_pool_size <= 0:
        raise ValueError("DATABASE_POOL_SIZE must be positive")
    if settings.database_max_overflow < 0:
        raise ValueError("DATABASE_MAX_OVERFLOW must not be negative")
    if settings.database_pool_recycle_seconds <= 0:
        raise ValueError("DATABASE_POOL_RECYCLE_SECONDS must be positive")
    if settings.storage_backend not in {"local", "s3"}:
        raise ValueError("STORAGE_BACKEND must be local or s3")
    if settings.storage_backend == "s3":
        if not settings.s3_bucket:
            raise ValueError("S3_BUCKET is required when STORAGE_BACKEND=s3")
        if bool(settings.s3_access_key_id) != bool(settings.s3_secret_access_key):
            raise ValueError("S3 access key id and secret must be configured together")
        if settings.s3_server_side_encryption not in {None, "AES256", "aws:kms"}:
            raise ValueError("S3_SERVER_SIDE_ENCRYPTION must be AES256 or aws:kms")
        if settings.s3_prefix and ".." in PurePath(settings.s3_prefix).parts:
            raise ValueError("S3_PREFIX must not contain parent path segments")
        if (
            settings.app_env == "production"
            and settings.s3_endpoint_url
            and not settings.s3_endpoint_url.startswith("https://")
        ):
            raise ValueError("S3_ENDPOINT_URL must use HTTPS in production")
    if settings.require_external_persistence:
        if not settings.database_url.startswith(
            ("postgres://", "postgresql://", "postgresql+")
        ):
            raise ValueError(
                "DATABASE_URL must use PostgreSQL when external persistence is required"
            )
        if settings.storage_backend != "s3":
            raise ValueError(
                "STORAGE_BACKEND must be s3 when external persistence is required"
            )
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
