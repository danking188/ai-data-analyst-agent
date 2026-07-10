from __future__ import annotations

import json
from io import BytesIO

import pandas as pd
from fastapi.testclient import TestClient
from openpyxl import Workbook


def project_id(create_project, key: str) -> str:
    return str(create_project(key=key)["project_id"])


def workbook_bytes(*, multiple_sheets: bool) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Orders"
    sheet.append(["email", "amount"])
    sheet.append(["a@example.com", 12.5])
    if multiple_sheets:
        customers = workbook.create_sheet("Customers")
        customers.append(["customer_id", "segment"])
        customers.append(["c-1", "premium"])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def parquet_bytes() -> bytes:
    output = BytesIO()
    pd.DataFrame({"category": ["A", "B"], "score": [0.1, 0.2]}).to_parquet(
        output,
        index=False,
    )
    return output.getvalue()


def upload(
    client: TestClient,
    *,
    project_id: str,
    headers: dict[str, str],
    key: str,
    filename: str,
    content: bytes,
    parse_options: dict[str, object] | None = None,
) -> dict[str, object]:
    data = {}
    if parse_options is not None:
        data["parse_options"] = json.dumps(parse_options)
    response = client.post(
        f"/api/v1/projects/{project_id}/datasets",
        headers={**headers, "Idempotency-Key": key},
        files={"file": (filename, BytesIO(content), "application/octet-stream")},
        data=data,
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_xlsx_and_parquet_ingestion(
    app_client: TestClient,
    auth_headers: dict[str, str],
    create_project,
) -> None:
    project = project_id(create_project, "format-project")
    xlsx_job = upload(
        app_client,
        project_id=project,
        headers=auth_headers,
        key="xlsx-upload",
        filename="orders.xlsx",
        content=workbook_bytes(multiple_sheets=False),
    )
    parquet_job = upload(
        app_client,
        project_id=project,
        headers=auth_headers,
        key="parquet-upload",
        filename="scores.parquet",
        content=parquet_bytes(),
    )
    for job in (xlsx_job, parquet_job):
        response = app_client.get(f"/api/v1/jobs/{job['job_id']}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "succeeded"


def test_multi_sheet_workbook_requires_selection(
    app_client: TestClient,
    auth_headers: dict[str, str],
    create_project,
) -> None:
    project = project_id(create_project, "sheet-project")
    failed = upload(
        app_client,
        project_id=project,
        headers=auth_headers,
        key="multi-sheet-failed",
        filename="multi.xlsx",
        content=workbook_bytes(multiple_sheets=True),
    )
    failed_status = app_client.get(
        f"/api/v1/jobs/{failed['job_id']}",
        headers=auth_headers,
    ).json()
    assert failed_status["status"] == "failed"
    assert failed_status["error"]["code"] == "SHEET_REQUIRED"
    assert failed_status["error"]["details"]["sheets"] == ["Orders", "Customers"]

    succeeded = upload(
        app_client,
        project_id=project,
        headers=auth_headers,
        key="multi-sheet-selected",
        filename="multi.xlsx",
        content=workbook_bytes(multiple_sheets=True),
        parse_options={"sheet_name": "Customers"},
    )
    succeeded_status = app_client.get(
        f"/api/v1/jobs/{succeeded['job_id']}",
        headers=auth_headers,
    ).json()
    assert succeeded_status["status"] == "succeeded"


def test_sensitive_preview_is_masked(
    app_client: TestClient,
    auth_headers: dict[str, str],
    create_project,
) -> None:
    project = project_id(create_project, "mask-project")
    job = upload(
        app_client,
        project_id=project,
        headers=auth_headers,
        key="mask-upload",
        filename="contacts.xlsx",
        content=workbook_bytes(multiple_sheets=False),
    )
    completed = app_client.get(
        f"/api/v1/jobs/{job['job_id']}",
        headers=auth_headers,
    ).json()
    version_id = completed["resource_id"]
    datasets = app_client.get(
        f"/api/v1/projects/{project}/datasets",
        headers=auth_headers,
    ).json()
    dataset_id = datasets["items"][0]["dataset_id"]
    preview = app_client.get(
        f"/api/v1/projects/{project}/datasets/{dataset_id}/versions/{version_id}/preview",
        headers=auth_headers,
    )
    assert preview.status_code == 200
    assert preview.json()["masked_columns"] == ["email"]
    assert preview.json()["rows"][0]["email"] == "******"
