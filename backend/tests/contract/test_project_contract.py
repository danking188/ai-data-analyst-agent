from __future__ import annotations

from fastapi.testclient import TestClient

from tests.contract.test_system_contract import assert_error_contract


def test_project_crud_and_idempotency(
    app_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    body = {
        "name": "客户流失分析",
        "description": "测试项目",
        "timezone": "Asia/Shanghai",
        "language": "zh-CN",
    }
    headers = {**auth_headers, "Idempotency-Key": "create-project-001"}
    created = app_client.post("/api/v1/projects", headers=headers, json=body)
    assert created.status_code == 201
    project = created.json()
    assert set(project) == {
        "project_id",
        "name",
        "description",
        "timezone",
        "language",
        "status",
        "current_dataset_version_id",
        "revision",
        "created_at",
        "updated_at",
    }
    assert project["project_id"].startswith("prj_")
    assert project["revision"] == 1

    replay = app_client.post("/api/v1/projects", headers=headers, json=body)
    assert replay.status_code == 201
    assert replay.json() == project

    conflicting = app_client.post(
        "/api/v1/projects",
        headers=headers,
        json={**body, "name": "不同项目"},
    )
    assert conflicting.status_code == 409
    assert conflicting.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    listed = app_client.get("/api/v1/projects", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json()["items"] == [project]
    assert listed.json()["total"] == 1
    assert listed.json()["has_more"] is False

    fetched = app_client.get(
        f"/api/v1/projects/{project['project_id']}",
        headers=auth_headers,
    )
    assert fetched.status_code == 200

    updated = app_client.patch(
        f"/api/v1/projects/{project['project_id']}",
        headers={**auth_headers, "If-Match": '"1"'},
        json={"name": "客户流失分析（更新）"},
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2
    assert updated.json()["name"] == "客户流失分析（更新）"

    stale = app_client.patch(
        f"/api/v1/projects/{project['project_id']}",
        headers={**auth_headers, "If-Match": '"1"'},
        json={"name": "不应成功"},
    )
    assert stale.status_code == 412
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"
    assert stale.json()["error"]["details"]["current_revision"] == 2

    archived = app_client.delete(
        f"/api/v1/projects/{project['project_id']}",
        headers=auth_headers,
    )
    assert archived.status_code == 204
    assert archived.content == b""

    rejected = app_client.patch(
        f"/api/v1/projects/{project['project_id']}",
        headers={**auth_headers, "If-Match": '"3"'},
        json={"name": "归档后修改"},
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "STATE_CONFLICT"


def test_project_validation_uses_error_contract(
    app_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = app_client.post(
        "/api/v1/projects",
        headers={**auth_headers, "Idempotency-Key": "validation-key"},
        json={
            "name": " ",
            "timezone": "Mars/Olympus",
            "language": "xx",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert_error_contract(response.json())


def test_if_match_is_required_and_strict(
    app_client: TestClient,
    auth_headers: dict[str, str],
    create_project,
) -> None:
    project = create_project(key="if-match-project")
    project_id = project["project_id"]
    missing = app_client.patch(
        f"/api/v1/projects/{project_id}",
        headers=auth_headers,
        json={"name": "新名称"},
    )
    assert missing.status_code == 422
    assert_error_contract(missing.json())

    malformed = app_client.patch(
        f"/api/v1/projects/{project_id}",
        headers={**auth_headers, "If-Match": "1"},
        json={"name": "新名称"},
    )
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "VALIDATION_ERROR"
