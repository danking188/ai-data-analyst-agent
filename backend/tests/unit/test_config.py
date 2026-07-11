import pytest

from app.core.config import get_settings


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
