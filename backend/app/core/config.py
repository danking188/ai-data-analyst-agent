from __future__ import annotations

import os
from dataclasses import dataclass, field
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


def _optional_bool(name: str) -> bool | None:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise ValueError(f"{name} must be true or false when configured")


@dataclass(frozen=True, slots=True)
class Settings:
    app_env: str
    api_prefix: str
    database_url: str
    database_pool_size: int
    database_max_overflow: int
    database_pool_recycle_seconds: int
    require_external_persistence: bool
    job_execution_mode: str
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
    csrf_cookie_name: str
    csrf_mode: str
    session_cookie_secure: bool
    session_ttl_seconds: int
    cors_origins: tuple[str, ...]
    trusted_hosts: tuple[str, ...]
    llm_enabled: bool
    llm_provider: str
    llm_api_base: str | None
    llm_api_key: str | None = field(repr=False)
    llm_model: str | None
    llm_structured_output_mode: str
    llm_enable_thinking: bool | None
    llm_temperature: float
    llm_timeout_seconds: int
    llm_max_output_tokens: int
    llm_max_input_tokens: int
    llm_max_calls_per_turn: int
    llm_max_tool_calls_per_turn: int
    llm_max_retries: int
    llm_daily_token_budget_per_user: int
    llm_max_concurrent_turns_per_project: int
    llm_circuit_breaker_failure_threshold: int
    llm_circuit_breaker_cooldown_seconds: int
    llm_allow_masked_samples: bool
    llm_retention_days: int
    llm_archive_inactive_days: int
    llm_canary_subjects: tuple[str, ...]

    @property
    def auth_enabled(self) -> bool:
        return self.auth_mode in {"dev_token", "jwt"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _read_env_file(Path(".env"))
    app_env = os.getenv("APP_ENV", "development")
    settings = Settings(
        app_env=app_env,
        api_prefix=os.getenv("API_PREFIX", "/api/v1"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./data/app.db"),
        database_pool_size=int(os.getenv("DATABASE_POOL_SIZE", "5")),
        database_max_overflow=int(os.getenv("DATABASE_MAX_OVERFLOW", "10")),
        database_pool_recycle_seconds=int(os.getenv("DATABASE_POOL_RECYCLE_SECONDS", "300")),
        require_external_persistence=os.getenv("REQUIRE_EXTERNAL_PERSISTENCE", "false").lower()
        in {"1", "true", "yes"},
        job_execution_mode=os.getenv("JOB_EXECUTION_MODE", "background").lower(),
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
        registration_enabled=os.getenv("REGISTRATION_ENABLED", "false").lower()
        in {"1", "true", "yes"},
        session_cookie_name=os.getenv("SESSION_COOKIE_NAME", "datatrace_session"),
        csrf_cookie_name=os.getenv("CSRF_COOKIE_NAME", "datatrace_csrf"),
        csrf_mode=os.getenv("CSRF_MODE", "double_submit").lower(),
        session_cookie_secure=os.getenv("SESSION_COOKIE_SECURE", "false").lower()
        in {"1", "true", "yes"},
        session_ttl_seconds=int(os.getenv("SESSION_TTL_SECONDS", "43200")),
        cors_origins=tuple(
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
            if origin.strip()
        ),
        trusted_hosts=tuple(
            host.strip()
            for host in os.getenv(
                "TRUSTED_HOSTS",
                "" if app_env == "production" else "localhost,127.0.0.1,testserver",
            ).split(",")
            if host.strip()
        ),
        llm_enabled=os.getenv("LLM_ENABLED", "false").lower() in {"1", "true", "yes"},
        llm_provider=os.getenv("LLM_PROVIDER", "openai_compatible").lower(),
        llm_api_base=os.getenv("LLM_API_BASE") or None,
        llm_api_key=os.getenv("LLM_API_KEY") or None,
        llm_model=os.getenv("LLM_MODEL") or None,
        llm_structured_output_mode=os.getenv("LLM_STRUCTURED_OUTPUT_MODE", "json_schema").lower(),
        llm_enable_thinking=_optional_bool("LLM_ENABLE_THINKING"),
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
        llm_timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS", "120")),
        llm_max_output_tokens=int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "4096")),
        llm_max_input_tokens=int(os.getenv("LLM_MAX_INPUT_TOKENS", "24000")),
        llm_max_calls_per_turn=int(os.getenv("LLM_MAX_CALLS_PER_TURN", "4")),
        llm_max_tool_calls_per_turn=int(os.getenv("LLM_MAX_TOOL_CALLS_PER_TURN", "8")),
        llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
        llm_daily_token_budget_per_user=int(os.getenv("LLM_DAILY_TOKEN_BUDGET_PER_USER", "200000")),
        llm_max_concurrent_turns_per_project=int(
            os.getenv("LLM_MAX_CONCURRENT_TURNS_PER_PROJECT", "2")
        ),
        llm_circuit_breaker_failure_threshold=int(
            os.getenv("LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5")
        ),
        llm_circuit_breaker_cooldown_seconds=int(
            os.getenv("LLM_CIRCUIT_BREAKER_COOLDOWN_SECONDS", "60")
        ),
        llm_allow_masked_samples=os.getenv("LLM_ALLOW_MASKED_SAMPLES", "false").lower()
        in {"1", "true", "yes"},
        llm_retention_days=int(os.getenv("LLM_RETENTION_DAYS", "30")),
        llm_archive_inactive_days=int(os.getenv("LLM_ARCHIVE_INACTIVE_DAYS", "90")),
        llm_canary_subjects=tuple(
            subject.strip()
            for subject in os.getenv("LLM_CANARY_SUBJECTS", "").split(",")
            if subject.strip()
        ),
    )
    if settings.auth_mode not in {"dev_token", "jwt"}:
        raise ValueError("AUTH_MODE must be dev_token or jwt")
    if settings.max_upload_bytes <= 0:
        raise ValueError("MAX_UPLOAD_BYTES must be positive")
    if settings.app_env == "production" and settings.max_upload_bytes > 104_857_600:
        raise ValueError("MAX_UPLOAD_BYTES must not exceed 100 MiB in production")
    if settings.database_pool_size <= 0:
        raise ValueError("DATABASE_POOL_SIZE must be positive")
    if settings.database_max_overflow < 0:
        raise ValueError("DATABASE_MAX_OVERFLOW must not be negative")
    if settings.database_pool_recycle_seconds <= 0:
        raise ValueError("DATABASE_POOL_RECYCLE_SECONDS must be positive")
    if settings.storage_backend not in {"local", "s3"}:
        raise ValueError("STORAGE_BACKEND must be local or s3")
    if settings.job_execution_mode not in {"background", "worker"}:
        raise ValueError("JOB_EXECUTION_MODE must be background or worker")
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
        if not settings.database_url.startswith(("postgres://", "postgresql://", "postgresql+")):
            raise ValueError(
                "DATABASE_URL must use PostgreSQL when external persistence is required"
            )
        if settings.storage_backend != "s3":
            raise ValueError("STORAGE_BACKEND must be s3 when external persistence is required")
    if settings.session_ttl_seconds <= 0:
        raise ValueError("SESSION_TTL_SECONDS must be positive")
    if not settings.session_cookie_name or not settings.csrf_cookie_name:
        raise ValueError("session and CSRF cookie names must not be empty")
    if settings.session_cookie_name == settings.csrf_cookie_name:
        raise ValueError("session and CSRF cookie names must be different")
    if settings.csrf_mode not in {"double_submit", "origin"}:
        raise ValueError("CSRF_MODE must be double_submit or origin")
    if settings.csrf_mode == "origin" and not settings.cors_origins:
        raise ValueError("CORS_ORIGINS is required when CSRF_MODE=origin")
    if not settings.trusted_hosts:
        raise ValueError("TRUSTED_HOSTS must contain at least one host")
    if settings.auth_mode == "jwt" and not settings.login_password:
        raise ValueError("LOGIN_PASSWORD is required when AUTH_MODE=jwt")
    if settings.app_env == "production" and settings.auth_mode != "jwt":
        raise ValueError("AUTH_MODE=jwt is required in production")
    if settings.app_env == "production" and settings.auth_mode == "jwt":
        if not settings.session_cookie_secure:
            raise ValueError("SESSION_COOKIE_SECURE=true is required in production")
        if "*" in settings.trusted_hosts:
            raise ValueError("TRUSTED_HOSTS must not contain wildcard hosts in production")
        if len(settings.jwt_secret) < 32 or settings.jwt_secret.startswith("replace-with-"):
            raise ValueError(
                "JWT_SECRET must be a non-placeholder secret of at least 32 characters"
            )
        if len(settings.login_password) < 12 or settings.login_password.startswith("replace-with-"):
            raise ValueError(
                "LOGIN_PASSWORD must be a non-placeholder password of at least 12 characters"
            )
    if settings.llm_provider not in {"openai_compatible", "fake"}:
        raise ValueError("LLM_PROVIDER must be openai_compatible or fake")
    if settings.llm_structured_output_mode not in {"json_schema", "json_object", "prompt"}:
        raise ValueError("LLM_STRUCTURED_OUTPUT_MODE must be json_schema, json_object, or prompt")
    if not 0 <= settings.llm_temperature <= 2:
        raise ValueError("LLM_TEMPERATURE must be between 0 and 2")
    positive_llm_limits = {
        "LLM_TIMEOUT_SECONDS": settings.llm_timeout_seconds,
        "LLM_MAX_OUTPUT_TOKENS": settings.llm_max_output_tokens,
        "LLM_MAX_INPUT_TOKENS": settings.llm_max_input_tokens,
        "LLM_MAX_CALLS_PER_TURN": settings.llm_max_calls_per_turn,
        "LLM_MAX_TOOL_CALLS_PER_TURN": settings.llm_max_tool_calls_per_turn,
        "LLM_DAILY_TOKEN_BUDGET_PER_USER": settings.llm_daily_token_budget_per_user,
        "LLM_MAX_CONCURRENT_TURNS_PER_PROJECT": settings.llm_max_concurrent_turns_per_project,
        "LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD": settings.llm_circuit_breaker_failure_threshold,
        "LLM_CIRCUIT_BREAKER_COOLDOWN_SECONDS": settings.llm_circuit_breaker_cooldown_seconds,
        "LLM_RETENTION_DAYS": settings.llm_retention_days,
        "LLM_ARCHIVE_INACTIVE_DAYS": settings.llm_archive_inactive_days,
    }
    for name, value in positive_llm_limits.items():
        if value <= 0:
            raise ValueError(f"{name} must be positive")
    if settings.llm_max_retries < 0:
        raise ValueError("LLM_MAX_RETRIES must not be negative")
    if settings.llm_enabled:
        if settings.llm_provider == "fake" and settings.app_env == "production":
            raise ValueError("LLM_PROVIDER=fake is not allowed in production")
        if settings.llm_provider == "openai_compatible":
            if not settings.llm_api_base:
                raise ValueError("LLM_API_BASE is required when LLM is enabled")
            if not settings.llm_api_key:
                raise ValueError("LLM_API_KEY is required when LLM is enabled")
            if not settings.llm_model:
                raise ValueError("LLM_MODEL is required when LLM is enabled")
            if settings.app_env == "production" and not settings.llm_api_base.startswith(
                "https://"
            ):
                raise ValueError("LLM_API_BASE must use HTTPS in production")
    return settings
