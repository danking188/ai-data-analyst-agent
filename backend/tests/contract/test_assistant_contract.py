from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import get_settings


def test_assistant_mutations_are_disabled_without_provider(
    app_client: TestClient,
    auth_headers: dict[str, str],
    create_project,
) -> None:
    project = create_project(key="assistant-disabled-project")
    response = app_client.post(
        f"/api/v1/projects/{project['project_id']}/assistant/conversations",
        headers={**auth_headers, "Idempotency-Key": "assistant-disabled"},
        json={},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "LLM_DISABLED"
    metrics = app_client.get(
        f"/api/v1/projects/{project['project_id']}/assistant/metrics?window_days=7",
        headers=auth_headers,
    )
    assert metrics.status_code == 200
    assert metrics.json() == {
        "window_days": 7,
        "turn_count": 0,
        "succeeded_count": 0,
        "failed_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "average_latency_ms": 0,
        "p95_latency_ms": 0,
        "tool_call_count": 0,
        "tool_succeeded_count": 0,
        "tool_failed_count": 0,
        "tool_rejected_count": 0,
    }


def test_assistant_conversation_turn_cancel_retry_and_idempotency(
    app_client: TestClient,
    auth_headers: dict[str, str],
    create_project,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("LLM_MODEL", "fake-model")
    monkeypatch.setenv("JOB_EXECUTION_MODE", "worker")
    get_settings.cache_clear()
    try:
        project = create_project(key="assistant-contract-project")
        project_id = project["project_id"]
        create_headers = {**auth_headers, "Idempotency-Key": "create-conversation"}
        created = app_client.post(
            f"/api/v1/projects/{project_id}/assistant/conversations",
            headers=create_headers,
            json={"title": "销售分析"},
        )
        assert created.status_code == 201, created.text
        conversation = created.json()
        assert conversation["title"] == "销售分析"
        assert conversation["status"] == "active"
        assert conversation["dataset_version_id"] is None
        replay = app_client.post(
            f"/api/v1/projects/{project_id}/assistant/conversations",
            headers=create_headers,
            json={"title": "销售分析"},
        )
        assert replay.status_code == 201
        assert replay.json() == conversation

        turn_headers = {**auth_headers, "Idempotency-Key": "assistant-turn-one"}
        turn = app_client.post(
            f"/api/v1/projects/{project_id}/assistant/conversations/"
            f"{conversation['conversation_id']}/messages",
            headers=turn_headers,
            json={"content": "检查当前数据质量"},
        )
        assert turn.status_code == 202, turn.text
        accepted = turn.json()
        assert accepted["user_message"]["status"] == "completed"
        assert accepted["assistant_message"]["status"] == "queued"
        assert accepted["job"]["kind"] == "assistant_turn"
        replay_turn = app_client.post(
            f"/api/v1/projects/{project_id}/assistant/conversations/"
            f"{conversation['conversation_id']}/messages",
            headers=turn_headers,
            json={"content": "检查当前数据质量"},
        )
        assert replay_turn.status_code == 202
        assert replay_turn.json() == accepted

        listed = app_client.get(
            f"/api/v1/projects/{project_id}/assistant/conversations/"
            f"{conversation['conversation_id']}/messages",
            headers=auth_headers,
        )
        assert listed.status_code == 200
        assert listed.json()["total"] == 2
        assert [item["role"] for item in listed.json()["items"]] == ["user", "assistant"]

        assistant_message_id = accepted["assistant_message"]["message_id"]
        cancelled = app_client.post(
            f"/api/v1/projects/{project_id}/assistant/messages/{assistant_message_id}/cancel",
            headers={**auth_headers, "Idempotency-Key": "cancel-turn-one"},
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"

        retried = app_client.post(
            f"/api/v1/projects/{project_id}/assistant/messages/{assistant_message_id}/retry",
            headers={**auth_headers, "Idempotency-Key": "retry-turn-one"},
        )
        assert retried.status_code == 202
        assert retried.json()["assistant_message"]["status"] == "queued"
        assert retried.json()["job"]["kind"] == "assistant_turn"

        archived = app_client.patch(
            f"/api/v1/projects/{project_id}/assistant/conversations/"
            f"{conversation['conversation_id']}",
            headers=auth_headers,
            json={"status": "archived"},
        )
        assert archived.status_code == 200
        assert archived.json()["status"] == "archived"
    finally:
        get_settings.cache_clear()
