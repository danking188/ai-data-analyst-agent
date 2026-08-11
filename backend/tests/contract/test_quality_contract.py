from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.persistence.orm.models import AuditLogRow
from app.persistence.orm.workflow_models import UserDecisionRow
from tests.contract.test_openapi_alignment import assert_matches_schema, load_contract


def _upload_quality_dataset(
    client: TestClient,
    headers: dict[str, str],
    project_id: str,
) -> str:
    response = client.post(
        f"/api/v1/projects/{project_id}/datasets",
        headers={**headers, "Idempotency-Key": "quality-upload-001"},
        files={
            "file": (
                "quality.csv",
                BytesIO(
                    b"id,value,constant,returned\n"
                    b"1,10,x,false\n2,,x,true\n2,,x,true\n3,1000,x,false\n4,11,x,false\n"
                ),
                "text/csv",
            )
        },
    )
    assert response.status_code == 202, response.text
    job = client.get(
        f"/api/v1/jobs/{response.json()['job_id']}",
        headers=headers,
    ).json()
    assert job["status"] == "succeeded"
    return str(job["resource_id"])


def test_quality_scan_list_filter_and_decision_flow(
    app_client: TestClient,
    auth_headers: dict[str, str],
    create_project,
) -> None:
    contract = load_contract()
    project = create_project(key="quality-contract-project")
    project_id = str(project["project_id"])
    version_id = _upload_quality_dataset(app_client, auth_headers, project_id)
    scan_url = f"/api/v1/projects/{project_id}/dataset-versions/{version_id}/quality-scans"

    started = app_client.post(
        scan_url,
        headers={**auth_headers, "Idempotency-Key": "quality-scan-001"},
        json={},
    )
    assert started.status_code == 202, started.text
    assert_matches_schema(contract, "Job", started.json())
    job = app_client.get(
        f"/api/v1/jobs/{started.json()['job_id']}",
        headers=auth_headers,
    ).json()
    assert job["status"] == "succeeded"
    assert job["resource_type"] == "quality_scan"
    assert job["resource_id"] == version_id

    issues_url = f"/api/v1/projects/{project_id}/dataset-versions/{version_id}/quality-issues"
    listed = app_client.get(issues_url, headers=auth_headers)
    assert listed.status_code == 200
    page = listed.json()
    assert_matches_schema(contract, "QualityIssuePage", page)
    issue_types = {item["issue_type"] for item in page["items"]}
    assert {"missing_values", "duplicate_rows", "constant_column"} <= issue_types

    missing_only = app_client.get(
        issues_url,
        headers=auth_headers,
        params={"issue_type": "missing_values", "status": "open"},
    )
    assert missing_only.status_code == 200
    assert missing_only.json()["total"] == 1
    issue = missing_only.json()["items"][0]
    assert issue["metrics"]["missing_count"] == 2

    issue_url = f"/api/v1/projects/{project_id}/quality-issues/{issue['issue_id']}"
    no_reason = app_client.patch(
        issue_url,
        headers={**auth_headers, "If-Match": '"1"'},
        json={"status": "ignored"},
    )
    assert no_reason.status_code == 422

    updated = app_client.patch(
        issue_url,
        headers={**auth_headers, "If-Match": '"1"'},
        json={"status": "ignored", "reason": "业务允许该字段缺失"},
    )
    assert updated.status_code == 200
    assert_matches_schema(contract, "QualityIssue", updated.json())
    assert updated.json()["status"] == "ignored"
    assert updated.json()["revision"] == 2

    stale = app_client.patch(
        issue_url,
        headers={**auth_headers, "If-Match": '"1"'},
        json={"status": "open"},
    )
    assert stale.status_code == 412
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"

    from app.persistence.session import get_database

    session = get_database().session()
    try:
        decisions = session.scalar(
            select(func.count())
            .select_from(UserDecisionRow)
            .where(
                UserDecisionRow.object_type == "quality_issue",
                UserDecisionRow.object_id == issue["issue_id"],
            )
        )
        audits = session.scalar(
            select(func.count())
            .select_from(AuditLogRow)
            .where(
                AuditLogRow.action == "quality_issue.updated",
                AuditLogRow.object_id == issue["issue_id"],
            )
        )
        assert decisions == 1
        assert audits == 1
    finally:
        session.close()


def test_quality_scan_validates_rules_and_requires_force_for_rescan(
    app_client: TestClient,
    auth_headers: dict[str, str],
    create_project,
) -> None:
    project = create_project(key="quality-rules-project")
    project_id = str(project["project_id"])
    version_id = _upload_quality_dataset(app_client, auth_headers, project_id)
    url = f"/api/v1/projects/{project_id}/dataset-versions/{version_id}/quality-scans"

    invalid = app_client.post(
        url,
        headers={**auth_headers, "Idempotency-Key": "quality-invalid-rule"},
        json={"rules": ["imaginary_llm_rule"]},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"

    first = app_client.post(
        url,
        headers={**auth_headers, "Idempotency-Key": "quality-first-scan"},
        json={"rules": ["missing_values"]},
    )
    assert first.status_code == 202

    duplicate = app_client.post(
        url,
        headers={**auth_headers, "Idempotency-Key": "quality-second-scan"},
        json={"rules": ["missing_values"]},
    )
    assert duplicate.status_code == 409

    forced = app_client.post(
        url,
        headers={**auth_headers, "Idempotency-Key": "quality-forced-scan"},
        json={"rules": ["constant_column"], "force": True},
    )
    assert forced.status_code == 202
    forced_job = app_client.get(
        f"/api/v1/jobs/{forced.json()['job_id']}",
        headers=auth_headers,
    ).json()
    assert forced_job["status"] == "succeeded"

    issues = app_client.get(
        f"/api/v1/projects/{project_id}/dataset-versions/{version_id}/quality-issues",
        headers=auth_headers,
    ).json()
    assert {item["issue_type"] for item in issues["items"]} == {"constant_column"}
