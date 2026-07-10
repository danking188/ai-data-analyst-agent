from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient


def assert_error_contract(payload: dict[str, object]) -> None:
    error = payload["error"]
    assert isinstance(error, dict)
    assert set(error) == {"code", "message", "request_id", "retryable", "details"}
    assert isinstance(error["request_id"], str)


def test_health_is_public_and_contract_shaped(app_client: TestClient) -> None:
    response = app_client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"]
    datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
    assert response.headers["X-Request-Id"].startswith("req_")


def test_capabilities_requires_bearer(
    app_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    unauthorized = app_client.get("/api/v1/system/capabilities")
    assert unauthorized.status_code == 401
    assert_error_contract(unauthorized.json())

    response = app_client.get("/api/v1/system/capabilities", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "api_version": "v1",
        "supported_file_types": ["csv", "xls", "xlsx", "parquet"],
        "max_upload_bytes": 524288000,
        "natural_language_analysis": False,
        "auth_enabled": True,
        "polling": {
            "initial_interval_ms": 1000,
            "steady_interval_ms": 3000,
            "background_interval_ms": 10000,
        },
    }


def test_unknown_route_uses_standard_error(app_client: TestClient) -> None:
    response = app_client.get("/api/v1/not-real")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert_error_contract(response.json())
