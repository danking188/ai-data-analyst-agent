from __future__ import annotations

from fastapi.testclient import TestClient

from app.security.auth import Principal, authenticate


def test_project_is_hidden_from_non_member(
    app_client: TestClient,
    auth_headers: dict[str, str],
    create_project,
) -> None:
    project = create_project(key="hidden-project")
    app = app_client.app
    app.dependency_overrides[authenticate] = lambda: Principal(subject_id="other-user")
    try:
        response = app_client.get(
            f"/api/v1/projects/{project['project_id']}",
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(authenticate, None)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
