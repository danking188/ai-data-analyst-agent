from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient


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

    from app.core.config import get_settings
    from app.persistence.session import get_database

    get_settings.cache_clear()
    get_database.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")

    from app.main import create_app

    with TestClient(create_app()) as client:
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

        session = client.get("/api/v1/auth/session")
        assert session.status_code == 200
        assert session.json()["subject_id"] == "analyst"

        created = client.post(
            "/api/v1/projects",
            headers={"Idempotency-Key": "cookie-auth-project"},
            json={
                "name": "Cookie 项目",
                "timezone": "Asia/Shanghai",
                "language": "zh-CN",
            },
        )
        assert created.status_code == 201

        logged_out = client.post("/api/v1/auth/logout")
        assert logged_out.status_code == 204
        assert client.get("/api/v1/auth/session").status_code == 401

    get_database().engine.dispose()
    get_database.cache_clear()
    get_settings.cache_clear()
