import pytest

from app.core.config import get_settings


def test_csrf_mode_is_strict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CSRF_MODE", "disabled")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="CSRF_MODE"):
            get_settings()
    finally:
        get_settings.cache_clear()


def test_s3_backend_requires_a_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.delenv("S3_BUCKET", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="S3_BUCKET"):
            get_settings()
    finally:
        get_settings.cache_clear()


def test_s3_static_credentials_must_be_configured_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "private-bucket")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "key-only")
    monkeypatch.delenv("S3_SECRET_ACCESS_KEY", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="configured together"):
            get_settings()
    finally:
        get_settings.cache_clear()


def test_external_persistence_rejects_local_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REQUIRE_EXTERNAL_PERSISTENCE", "true")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/app.db")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="PostgreSQL"):
            get_settings()
    finally:
        get_settings.cache_clear()


def test_external_persistence_accepts_postgres_and_s3(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REQUIRE_EXTERNAL_PERSISTENCE", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@db/app")
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "private-bucket")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.require_external_persistence is True
        assert settings.storage_backend == "s3"
    finally:
        get_settings.cache_clear()


def test_llm_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_ENABLED", raising=False)
    monkeypatch.delenv("LLM_API_BASE", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.llm_enabled is False
        assert settings.llm_provider == "openai_compatible"
        assert settings.llm_enable_thinking is None
    finally:
        get_settings.cache_clear()


def test_llm_thinking_control_is_optional_and_strict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_ENABLE_THINKING", "false")
    get_settings.cache_clear()
    try:
        assert get_settings().llm_enable_thinking is False
    finally:
        get_settings.cache_clear()

    monkeypatch.setenv("LLM_ENABLE_THINKING", "sometimes")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="LLM_ENABLE_THINKING"):
            get_settings()
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("missing", ["LLM_API_BASE", "LLM_API_KEY", "LLM_MODEL"])
def test_enabled_llm_requires_provider_configuration(
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_BASE", "https://provider.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "private-provider-key")
    monkeypatch.setenv("LLM_MODEL", "analysis-model")
    monkeypatch.delenv(missing, raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match=missing):
            get_settings()
    finally:
        get_settings.cache_clear()


def test_llm_api_key_is_hidden_from_settings_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_BASE", "https://provider.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "private-provider-key")
    monkeypatch.setenv("LLM_MODEL", "analysis-model")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert "private-provider-key" not in repr(settings)
    finally:
        get_settings.cache_clear()


def test_production_llm_requires_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "104857600")
    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("LOGIN_PASSWORD", "production-password-2026")
    monkeypatch.setenv("JWT_SECRET", "production-jwt-secret-at-least-32-characters")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    monkeypatch.setenv("TRUSTED_HOSTS", "analytics.example.com")
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_BASE", "http://provider.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "private-provider-key")
    monkeypatch.setenv("LLM_MODEL", "analysis-model")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="HTTPS"):
            get_settings()
    finally:
        get_settings.cache_clear()


def test_production_rejects_dev_auth_and_insecure_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "104857600")
    monkeypatch.setenv("TRUSTED_HOSTS", "analytics.example.com")
    monkeypatch.setenv("AUTH_MODE", "dev_token")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="AUTH_MODE=jwt"):
        get_settings()

    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("LOGIN_PASSWORD", "production-password-2026")
    monkeypatch.setenv("JWT_SECRET", "production-jwt-secret-at-least-32-characters")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="SESSION_COOKIE_SECURE"):
            get_settings()
    finally:
        get_settings.cache_clear()
