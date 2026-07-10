from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient

from tests.contract.test_openapi_alignment import (
    assert_matches_schema,
    load_contract,
)


def _upload_schema_dataset(
    client: TestClient,
    headers: dict[str, str],
    project_id: str,
) -> str:
    response = client.post(
        f"/api/v1/projects/{project_id}/datasets",
        headers={**headers, "Idempotency-Key": "schema-upload-001"},
        files={
            "file": (
                "houses.csv",
                BytesIO(
                    b"zip_code,price,email\n"
                    b"10001,500000,a@example.com\n"
                    b"10002,600000,b@example.com\n"
                ),
                "text/csv",
            )
        },
    )
    assert response.status_code == 202
    job = client.get(
        f"/api/v1/jobs/{response.json()['job_id']}",
        headers=headers,
    ).json()
    assert job["status"] == "succeeded"
    return str(job["resource_id"])


def test_schema_get_override_and_revision_conflict(
    app_client: TestClient,
    auth_headers: dict[str, str],
    create_project,
) -> None:
    contract = load_contract()
    project = create_project(key="schema-contract-project")
    project_id = str(project["project_id"])
    version_id = _upload_schema_dataset(
        app_client,
        auth_headers,
        project_id,
    )
    url = f"/api/v1/projects/{project_id}/dataset-versions/{version_id}/schema"

    fetched = app_client.get(url, headers=auth_headers)
    assert fetched.status_code == 200
    schema = fetched.json()
    assert_matches_schema(contract, "DatasetSchema", schema)
    assert schema["revision"] == 1
    assert [column["name"] for column in schema["columns"]] == [
        "zip_code",
        "price",
        "email",
    ]
    assert next(column for column in schema["columns"] if column["name"] == "email")["sensitive"]

    updated = app_client.patch(
        url,
        headers={**auth_headers, "If-Match": '"1"'},
        json={
            "changes": [
                {
                    "column": "zip_code",
                    "semantic_type": "geographic_code",
                    "analysis_role": "feature",
                }
            ],
            "reason": "邮编不具备连续数值含义",
        },
    )
    assert updated.status_code == 200
    updated_schema = updated.json()
    assert_matches_schema(contract, "DatasetSchema", updated_schema)
    assert updated_schema["revision"] == 2
    zip_code = next(column for column in updated_schema["columns"] if column["name"] == "zip_code")
    assert zip_code["semantic_type"] == "geographic_code"
    assert zip_code["user_confirmed"] is True

    stale = app_client.patch(
        url,
        headers={**auth_headers, "If-Match": '"1"'},
        json={
            "changes": [
                {
                    "column": "price",
                    "semantic_type": "currency",
                }
            ]
        },
    )
    assert stale.status_code == 412
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"
    assert stale.json()["error"]["details"]["current_revision"] == 2


def test_schema_override_rejects_unknown_column(
    app_client: TestClient,
    auth_headers: dict[str, str],
    create_project,
) -> None:
    project = create_project(key="schema-unknown-project")
    project_id = str(project["project_id"])
    version_id = _upload_schema_dataset(app_client, auth_headers, project_id)
    response = app_client.patch(
        f"/api/v1/projects/{project_id}/dataset-versions/{version_id}/schema",
        headers={**auth_headers, "If-Match": '"1"'},
        json={
            "changes": [
                {
                    "column": "does_not_exist",
                    "semantic_type": "categorical",
                }
            ]
        },
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
