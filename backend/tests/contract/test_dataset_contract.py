from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient

from tests.contract.test_system_contract import assert_error_contract


def upload_csv(
    client: TestClient,
    project_id: str,
    headers: dict[str, str],
    *,
    key: str,
    content: bytes = b"name,value\nalice,1\nbob,2\n",
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/projects/{project_id}/datasets",
        headers={**headers, "Idempotency-Key": key},
        files={"file": ("sample.csv", BytesIO(content), "text/csv")},
        data={"dataset_name": "示例数据"},
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_upload_creates_job_dataset_and_version(
    app_client: TestClient,
    auth_headers: dict[str, str],
    create_project,
) -> None:
    project = create_project(key="upload-project")
    project_id = str(project["project_id"])
    job = upload_csv(
        app_client,
        project_id,
        auth_headers,
        key="upload-csv-0001",
    )
    assert job["job_id"].startswith("job_")
    assert job["kind"] == "dataset_ingestion"
    assert job["status"] == "queued"

    datasets = app_client.get(
        f"/api/v1/projects/{project_id}/datasets",
        headers=auth_headers,
    )
    assert datasets.status_code == 200
    dataset_page = datasets.json()
    assert dataset_page["total"] == 1
    dataset = dataset_page["items"][0]
    assert dataset["name"] == "示例数据"
    assert dataset["source_type"] == "csv"
    assert dataset["version_count"] == 1

    versions = app_client.get(
        f"/api/v1/projects/{project_id}/datasets/{dataset['dataset_id']}/versions",
        headers=auth_headers,
    )
    assert versions.status_code == 200
    version = versions.json()["items"][0]
    assert version["status"] == "ready"
    assert version["kind"] == "raw"
    assert version["file_hash"].startswith("sha256:")
    assert version["source_file_name"] == "sample.csv"
    assert version["row_count"] == 2
    assert version["column_count"] == 2

    fetched = app_client.get(
        f"/api/v1/projects/{project_id}/datasets/"
        f"{dataset['dataset_id']}/versions/{version['version_id']}",
        headers=auth_headers,
    )
    assert fetched.status_code == 200
    assert fetched.json() == version

    completed_job = app_client.get(
        f"/api/v1/jobs/{job['job_id']}",
        headers=auth_headers,
    )
    assert completed_job.status_code == 200
    assert completed_job.json()["status"] == "succeeded"
    assert completed_job.json()["resource_id"] == version["version_id"]

    first_page = app_client.get(
        f"/api/v1/projects/{project_id}/datasets/{dataset['dataset_id']}/"
        f"versions/{version['version_id']}/preview",
        headers=auth_headers,
        params={"limit": 1},
    )
    assert first_page.status_code == 200
    assert first_page.json()["rows"] == [{"name": "******", "value": 1}]
    assert first_page.json()["masked_columns"] == ["name"]
    assert first_page.json()["has_more"] is True
    assert first_page.json()["next_cursor"]

    second_page = app_client.get(
        f"/api/v1/projects/{project_id}/datasets/{dataset['dataset_id']}/"
        f"versions/{version['version_id']}/preview",
        headers=auth_headers,
        params={"limit": 1, "cursor": first_page.json()["next_cursor"]},
    )
    assert second_page.status_code == 200
    assert second_page.json()["rows"] == [{"name": "******", "value": 2}]
    assert second_page.json()["has_more"] is False


def test_upload_is_idempotent(
    app_client: TestClient,
    auth_headers: dict[str, str],
    create_project,
) -> None:
    project = create_project(key="upload-idempotency-project")
    project_id = str(project["project_id"])
    first = upload_csv(
        app_client,
        project_id,
        auth_headers,
        key="same-upload-key",
    )
    second = upload_csv(
        app_client,
        project_id,
        auth_headers,
        key="same-upload-key",
    )
    assert second == first

    datasets = app_client.get(
        f"/api/v1/projects/{project_id}/datasets",
        headers=auth_headers,
    ).json()
    assert datasets["total"] == 1


def test_activate_ready_version_is_idempotent(
    app_client: TestClient,
    auth_headers: dict[str, str],
    create_project,
) -> None:
    project = create_project(key="activate-project")
    project_id = str(project["project_id"])
    upload_csv(
        app_client,
        project_id,
        auth_headers,
        key="activate-upload",
    )
    dataset = app_client.get(
        f"/api/v1/projects/{project_id}/datasets",
        headers=auth_headers,
    ).json()["items"][0]
    version = app_client.get(
        f"/api/v1/projects/{project_id}/datasets/{dataset['dataset_id']}/versions",
        headers=auth_headers,
    ).json()["items"][0]
    url = (
        f"/api/v1/projects/{project_id}/datasets/{dataset['dataset_id']}/"
        f"versions/{version['version_id']}/activate"
    )
    headers = {**auth_headers, "Idempotency-Key": "activate-version-001"}
    first = app_client.post(url, headers=headers)
    second = app_client.post(url, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert first.json()["current_version_id"] == version["version_id"]


def test_upload_rejects_unsupported_and_mismatched_files(
    app_client: TestClient,
    auth_headers: dict[str, str],
    create_project,
) -> None:
    project = create_project(key="upload-errors-project")
    project_id = str(project["project_id"])
    unsupported = app_client.post(
        f"/api/v1/projects/{project_id}/datasets",
        headers={**auth_headers, "Idempotency-Key": "unsupported-file"},
        files={"file": ("notes.txt", BytesIO(b"hello"), "text/plain")},
    )
    assert unsupported.status_code == 415
    assert unsupported.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
    assert_error_contract(unsupported.json())

    corrupted = app_client.post(
        f"/api/v1/projects/{project_id}/datasets",
        headers={**auth_headers, "Idempotency-Key": "corrupted-xlsx"},
        files={
            "file": (
                "broken.xlsx",
                BytesIO(b"this is not a zip workbook"),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert corrupted.status_code == 422
    assert corrupted.json()["error"]["code"] == "FILE_CORRUPTED"
    assert_error_contract(corrupted.json())
