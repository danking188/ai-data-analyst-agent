from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient


@pytest.fixture()
def app_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    database_path = tmp_path / "app.db"
    data_root = tmp_path / "data"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("API_PREFIX", "/api/v1")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("AUTH_MODE", "dev_token")
    monkeypatch.setenv("DEV_AUTH_TOKEN", "test-token")

    from app.core.config import get_settings
    from app.persistence.session import get_database

    get_database.cache_clear()
    get_settings.cache_clear()

    config = Config("alembic.ini")
    command.upgrade(config, "head")

    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        yield client

    database = get_database()
    database.engine.dispose()
    get_database.cache_clear()
    get_settings.cache_clear()
    os.environ.pop("DATABASE_URL", None)


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


@pytest.fixture()
def create_project(app_client: TestClient, auth_headers: dict[str, str]):
    def factory(
        *,
        name: str = "测试项目",
        key: str = "project-key-0001",
    ) -> dict[str, object]:
        response = app_client.post(
            "/api/v1/projects",
            headers={**auth_headers, "Idempotency-Key": key},
            json={
                "name": name,
                "description": "集成测试",
                "timezone": "Asia/Shanghai",
                "language": "zh-CN",
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    return factory
