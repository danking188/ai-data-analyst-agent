from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.security.passwords import verify_password


def test_origin_csrf_mode_uses_one_session_cookie(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("API_PREFIX", "/api/v1")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'origin-auth.db'}")
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("LOGIN_USERNAME", "pilot")
    monkeypatch.setenv("LOGIN_PASSWORD", "test-password")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-at-least-32-characters")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("CSRF_MODE", "origin")
    monkeypatch.setenv("CORS_ORIGINS", "http://testserver")

    from app.core.config import get_settings
    from app.persistence.session import get_database

    get_settings.cache_clear()
    get_database.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")

    from app.main import create_app

    try:
        with TestClient(create_app()) as client:
            logged_in = client.post(
                "/api/v1/auth/login",
                json={"username": "pilot", "password": "test-password"},
            )
            assert logged_in.status_code == 200
            assert client.cookies.get("datatrace_session")
            assert client.cookies.get("datatrace_csrf") is None

            project_payload = {
                "name": "Origin 项目",
                "timezone": "Asia/Shanghai",
                "language": "zh-CN",
            }
            missing_origin = client.post(
                "/api/v1/projects",
                headers={"Idempotency-Key": "origin-missing"},
                json=project_payload,
            )
            assert missing_origin.status_code == 403

            wrong_origin = client.post(
                "/api/v1/projects",
                headers={
                    "Idempotency-Key": "origin-wrong",
                    "Origin": "https://evil.example",
                },
                json=project_payload,
            )
            assert wrong_origin.status_code == 403

            created = client.post(
                "/api/v1/projects",
                headers={
                    "Idempotency-Key": "origin-valid",
                    "Origin": "http://testserver",
                },
                json=project_payload,
            )
            assert created.status_code == 201

            logged_out = client.post(
                "/api/v1/auth/logout",
                headers={"Origin": "http://testserver"},
            )
            assert logged_out.status_code == 204
            assert client.get("/api/v1/auth/session").status_code == 401
    finally:
        get_database().engine.dispose()
        get_database.cache_clear()
        get_settings.cache_clear()


def test_jwt_login_cookie_session_and_logout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("API_PREFIX", "/api/v1")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'auth.db'}")
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("LOGIN_USERNAME", "analyst")
    monkeypatch.setenv("LOGIN_PASSWORD", "test-password")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-at-least-32-characters")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("REGISTRATION_ENABLED", "true")

    from app.core.config import get_settings
    from app.persistence.session import get_database

    get_settings.cache_clear()
    get_database.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")

    from app.main import create_app

    with TestClient(create_app()) as client:
        auth_config = client.get("/api/v1/auth/config")
        assert auth_config.status_code == 200
        assert auth_config.json() == {"registration_enabled": True}

        rejected = client.post(
            "/api/v1/auth/login",
            json={"username": "analyst", "password": "wrong"},
        )
        assert rejected.status_code == 401

        logged_in = client.post(
            "/api/v1/auth/login",
            json={"username": "analyst", "password": "test-password"},
        )
        assert logged_in.status_code == 200
        assert logged_in.json()["subject_id"] == "analyst"
        assert "datatrace_session=" in logged_in.headers["set-cookie"]
        csrf_token = client.cookies.get("datatrace_csrf")
        assert csrf_token

        session = client.get("/api/v1/auth/session")
        assert session.status_code == 200
        assert session.json()["subject_id"] == "analyst"

        csrf_rejected = client.post(
            "/api/v1/projects",
            headers={"Idempotency-Key": "cookie-auth-project"},
            json={
                "name": "Cookie 项目",
                "timezone": "Asia/Shanghai",
                "language": "zh-CN",
            },
        )
        assert csrf_rejected.status_code == 403
        assert csrf_rejected.json()["error"]["code"] == "CSRF_VALIDATION_FAILED"

        created = client.post(
            "/api/v1/projects",
            headers={
                "Idempotency-Key": "cookie-auth-project",
                "X-CSRF-Token": csrf_token,
            },
            json={
                "name": "Cookie 项目",
                "timezone": "Asia/Shanghai",
                "language": "zh-CN",
            },
        )
        assert created.status_code == 201

        logged_out = client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": csrf_token},
        )
        assert logged_out.status_code == 204
        assert client.get("/api/v1/auth/session").status_code == 401

        registered = client.post(
            "/api/v1/auth/register",
            json={"username": "New.User", "password": "safe-password-2026"},
        )
        assert registered.status_code == 201
        assert registered.json()["subject_id"] == "new.user"
        assert "datatrace_session=" in registered.headers["set-cookie"]

        projects = client.get("/api/v1/projects")
        assert projects.status_code == 200
        assert projects.json()["total"] == 0

        duplicate = client.post(
            "/api/v1/auth/register",
            json={"username": "new.user", "password": "another-password-2026"},
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "USERNAME_TAKEN"

        from app.persistence.orm import UserRow

        session = get_database().session()
        try:
            stored = session.scalar(select(UserRow).where(UserRow.username == "new.user"))
            assert stored is not None
            assert stored.password_hash.startswith("scrypt$")
            assert "safe-password-2026" not in stored.password_hash
            assert verify_password("safe-password-2026", stored.password_hash)
            assert not verify_password(
                "safe-password-2026",
                stored.password_hash.replace("$16384$", "$32768$"),
            )
            assert stored.last_login_at is None
        finally:
            session.close()

    with TestClient(create_app()) as restarted_client:
        persisted_login = restarted_client.post(
            "/api/v1/auth/login",
            json={"username": "NEW.USER", "password": "safe-password-2026"},
        )
        assert persisted_login.status_code == 200
        assert persisted_login.json()["subject_id"] == "new.user"

        for _ in range(5):
            failed = restarted_client.post(
                "/api/v1/auth/login",
                json={"username": "analyst", "password": "wrong-password"},
            )
            assert failed.status_code == 401
        locked = restarted_client.post(
            "/api/v1/auth/login",
            json={"username": "analyst", "password": "test-password"},
        )
        assert locked.status_code == 423
        assert locked.json()["error"]["code"] == "ACCOUNT_LOCKED"

    get_database().engine.dispose()
    get_database.cache_clear()
    get_settings.cache_clear()
