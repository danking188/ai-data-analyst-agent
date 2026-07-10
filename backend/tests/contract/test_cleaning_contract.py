from __future__ import annotations

from fastapi.testclient import TestClient

from app.persistence.orm.workflow_models import ArtifactRow
from app.persistence.session import get_database
from tests.contract.test_dataset_contract import upload_csv
from tests.contract.test_openapi_alignment import assert_matches_schema, load_contract


def _upload_source_version(
    client: TestClient,
    project_id: str,
    headers: dict[str, str],
) -> str:
    job = upload_csv(
        client,
        project_id,
        headers,
        key="cleaning-source-upload",
        content=b"name,value\nalice,1\nbob,\nbob,\n",
    )
    completed = client.get(
        f"/api/v1/jobs/{job['job_id']}",
        headers=headers,
    ).json()
    assert completed["status"] == "succeeded"
    return str(completed["resource_id"])


def _operation(
    *,
    operation_id: str = "cleanop_fill_value",
    column: str = "value",
) -> dict[str, object]:
    return {
        "operation_id": operation_id,
        "operation": "impute_missing",
        "column": column,
        "parameters": {"method": "constant", "value": 0},
        "reason": "缺失值会影响后续统计",
        "issue_ids": [],
        "estimated_affected_rows": 2,
        "risk_level": "low",
        "reversible": True,
    }


def test_cleaning_plan_preview_and_approval_flow(
    app_client: TestClient,
    auth_headers: dict[str, str],
    create_project,
) -> None:
    contract = load_contract()
    project = create_project(key="cleaning-flow-project")
    project_id = str(project["project_id"])
    version_id = _upload_source_version(app_client, project_id, auth_headers)
    plans_url = f"/api/v1/projects/{project_id}/cleaning-plans"

    created = app_client.post(
        plans_url,
        headers={**auth_headers, "Idempotency-Key": "cleaning-create-001"},
        json={
            "source_version_id": version_id,
            "name": "补齐缺失并去重",
            "operations": [
                _operation(),
                {
                    "operation_id": "cleanop_drop_duplicates",
                    "operation": "drop_duplicates",
                    "column": None,
                    "parameters": {"columns": ["name", "value"], "keep": "first"},
                    "reason": "移除完全重复的记录",
                    "issue_ids": [],
                    "estimated_affected_rows": 1,
                    "risk_level": "medium",
                    "reversible": False,
                },
            ],
        },
    )
    assert created.status_code == 201, created.text
    plan = created.json()
    assert_matches_schema(contract, "CleaningPlan", plan)
    assert plan["status"] == "draft"
    assert plan["revision"] == 1

    replay = app_client.post(
        plans_url,
        headers={**auth_headers, "Idempotency-Key": "cleaning-create-001"},
        json={
            "source_version_id": version_id,
            "name": "补齐缺失并去重",
            "operations": [
                _operation(),
                {
                    "operation_id": "cleanop_drop_duplicates",
                    "operation": "drop_duplicates",
                    "column": None,
                    "parameters": {"columns": ["name", "value"], "keep": "first"},
                    "reason": "移除完全重复的记录",
                    "issue_ids": [],
                    "estimated_affected_rows": 1,
                    "risk_level": "medium",
                    "reversible": False,
                },
            ],
        },
    )
    assert replay.status_code == 201
    assert replay.json() == plan

    updated = app_client.patch(
        f"{plans_url}/{plan['plan_id']}",
        headers={**auth_headers, "If-Match": '"1"'},
        json={"name": "已确认参数的清洗计划"},
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2

    preview = app_client.post(
        f"{plans_url}/{plan['plan_id']}/preview",
        headers={**auth_headers, "Idempotency-Key": "cleaning-preview-001"},
    )
    assert preview.status_code == 202, preview.text
    assert_matches_schema(contract, "Job", preview.json())
    completed = app_client.get(
        f"/api/v1/jobs/{preview.json()['job_id']}",
        headers=auth_headers,
    ).json()
    assert completed["status"] == "succeeded"
    assert completed["resource_type"] == "artifact"

    awaiting = app_client.get(
        f"{plans_url}/{plan['plan_id']}",
        headers=auth_headers,
    )
    assert awaiting.status_code == 200
    assert awaiting.json()["status"] == "awaiting_approval"
    assert awaiting.json()["preview_artifact_id"] == completed["resource_id"]
    assert awaiting.json()["revision"] == 3

    session = get_database().session()
    try:
        artifact = session.get(ArtifactRow, completed["resource_id"])
        assert artifact is not None
        assert artifact.result_json["row_count_before"] == 3
        assert artifact.result_json["row_count_after"] == 2
        assert artifact.result_json["sample_before"][0]["name"] == "******"
        assert artifact.result_json["sample_after"][0]["name"] == "******"
    finally:
        session.close()

    approved = app_client.post(
        f"{plans_url}/{plan['plan_id']}/decision",
        headers={**auth_headers, "Idempotency-Key": "cleaning-decision-001"},
        json={"decision": "approve", "reason": "预览结果符合预期"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["decision"] == "approve"
    assert approved.json()["revision"] == 4

    execution = app_client.post(
        f"{plans_url}/{plan['plan_id']}/execute",
        headers={**auth_headers, "Idempotency-Key": "cleaning-execute-001"},
    )
    assert execution.status_code == 202, execution.text
    assert_matches_schema(contract, "Job", execution.json())
    execution_job = app_client.get(
        f"/api/v1/jobs/{execution.json()['job_id']}",
        headers=auth_headers,
    ).json()
    assert execution_job["status"] == "succeeded"
    assert execution_job["resource_type"] == "dataset_version"
    assert execution_job["resource_id"] != version_id

    executed = app_client.get(
        f"{plans_url}/{plan['plan_id']}",
        headers=auth_headers,
    ).json()
    assert executed["status"] == "executed"
    assert executed["result_version_id"] == execution_job["resource_id"]
    assert executed["revision"] == 6

    datasets = app_client.get(
        f"/api/v1/projects/{project_id}/datasets",
        headers=auth_headers,
    ).json()
    dataset = datasets["items"][0]
    assert dataset["current_version_id"] == execution_job["resource_id"]
    versions = app_client.get(
        f"/api/v1/projects/{project_id}/datasets/{dataset['dataset_id']}/versions",
        headers=auth_headers,
    ).json()
    result_version = versions["items"][0]
    assert result_version["version_id"] == execution_job["resource_id"]
    assert result_version["parent_version_id"] == version_id
    assert result_version["kind"] == "cleaned"
    assert result_version["status"] == "ready"
    assert result_version["row_count"] == 2

    comparison = app_client.post(
        f"/api/v1/projects/{project_id}/datasets/{dataset['dataset_id']}/version-comparisons",
        headers={**auth_headers, "Idempotency-Key": "version-comparison-001"},
        json={
            "base_version_id": version_id,
            "compare_version_id": result_version["version_id"],
            "include_sample_changes": True,
        },
    )
    assert comparison.status_code == 202, comparison.text
    comparison_job = app_client.get(
        f"/api/v1/jobs/{comparison.json()['job_id']}",
        headers=auth_headers,
    ).json()
    assert comparison_job["status"] == "succeeded"
    assert comparison_job["resource_type"] == "artifact"
    session = get_database().session()
    try:
        artifact = session.get(ArtifactRow, comparison_job["resource_id"])
        assert artifact is not None
        comparison_result = artifact.result_json
        assert comparison_result["row_count"]["delta"] == -1
        assert comparison_result["missing_value_changes"] == [
            {"column": "value", "base_missing": 2, "compare_missing": 0}
        ]
        assert comparison_result["sample_changes"]["base"][0]["name"] == "******"
        assert comparison_result["sample_changes"]["compare"][0]["name"] == "******"
    finally:
        session.close()

    immutable = app_client.patch(
        f"{plans_url}/{plan['plan_id']}",
        headers={**auth_headers, "If-Match": '"6"'},
        json={"name": "不应成功"},
    )
    assert immutable.status_code == 409
    assert immutable.json()["error"]["code"] == "STATE_CONFLICT"


def test_cleaning_plan_validates_registry_and_preview_before_decision(
    app_client: TestClient,
    auth_headers: dict[str, str],
    create_project,
) -> None:
    project = create_project(key="cleaning-validation-project")
    project_id = str(project["project_id"])
    version_id = _upload_source_version(app_client, project_id, auth_headers)
    url = f"/api/v1/projects/{project_id}/cleaning-plans"

    unknown_column = app_client.post(
        url,
        headers={**auth_headers, "Idempotency-Key": "cleaning-invalid-column"},
        json={
            "source_version_id": version_id,
            "operations": [_operation(column="missing_column")],
        },
    )
    assert unknown_column.status_code == 422
    assert unknown_column.json()["error"]["code"] == "VALIDATION_ERROR"

    unsafe_parameters = app_client.post(
        url,
        headers={**auth_headers, "Idempotency-Key": "cleaning-invalid-params"},
        json={
            "source_version_id": version_id,
            "operations": [
                {
                    **_operation(operation_id="cleanop_unsafe"),
                    "parameters": {
                        "method": "constant",
                        "value": 0,
                        "python_expression": "__import__('os')",
                    },
                }
            ],
        },
    )
    assert unsafe_parameters.status_code == 422

    valid = app_client.post(
        url,
        headers={**auth_headers, "Idempotency-Key": "cleaning-valid-draft"},
        json={
            "source_version_id": version_id,
            "operations": [_operation(operation_id="cleanop_valid_draft")],
        },
    )
    assert valid.status_code == 201
    plan_id = valid.json()["plan_id"]

    premature = app_client.post(
        f"{url}/{plan_id}/decision",
        headers={**auth_headers, "Idempotency-Key": "cleaning-premature-decision"},
        json={"decision": "approve"},
    )
    assert premature.status_code == 409

    reject_without_reason = app_client.post(
        f"{url}/{plan_id}/decision",
        headers={**auth_headers, "Idempotency-Key": "cleaning-reject-no-reason"},
        json={"decision": "reject"},
    )
    assert reject_without_reason.status_code == 422


def test_failed_cleaning_execution_never_activates_result_version(
    app_client: TestClient,
    auth_headers: dict[str, str],
    create_project,
) -> None:
    project = create_project(key="cleaning-failure-project")
    project_id = str(project["project_id"])
    source_version_id = _upload_source_version(app_client, project_id, auth_headers)
    plans_url = f"/api/v1/projects/{project_id}/cleaning-plans"
    created = app_client.post(
        plans_url,
        headers={**auth_headers, "Idempotency-Key": "cleaning-empty-create"},
        json={
            "source_version_id": source_version_id,
            "operations": [
                {
                    "operation_id": "cleanop_filter_everything",
                    "operation": "filter_rows",
                    "column": "value",
                    "parameters": {"operator": "eq", "value": 999999},
                    "reason": "验证空结果不变量",
                    "issue_ids": [],
                    "estimated_affected_rows": 3,
                    "risk_level": "high",
                    "reversible": False,
                }
            ],
        },
    )
    assert created.status_code == 201
    plan_id = created.json()["plan_id"]

    preview = app_client.post(
        f"{plans_url}/{plan_id}/preview",
        headers={**auth_headers, "Idempotency-Key": "cleaning-empty-preview"},
    )
    assert preview.status_code == 202
    preview_job = app_client.get(
        f"/api/v1/jobs/{preview.json()['job_id']}",
        headers=auth_headers,
    ).json()
    assert preview_job["status"] == "succeeded"

    approved = app_client.post(
        f"{plans_url}/{plan_id}/decision",
        headers={**auth_headers, "Idempotency-Key": "cleaning-empty-approve"},
        json={"decision": "approve", "reason": "故意触发不变量测试"},
    )
    assert approved.status_code == 200

    execution = app_client.post(
        f"{plans_url}/{plan_id}/execute",
        headers={**auth_headers, "Idempotency-Key": "cleaning-empty-execute"},
    )
    assert execution.status_code == 202
    failed_job = app_client.get(
        f"/api/v1/jobs/{execution.json()['job_id']}",
        headers=auth_headers,
    ).json()
    assert failed_job["status"] == "failed"
    assert failed_job["error"]["code"] == "VALIDATION_ERROR"

    failed_plan = app_client.get(
        f"{plans_url}/{plan_id}",
        headers=auth_headers,
    ).json()
    assert failed_plan["status"] == "failed"
    assert failed_plan["result_version_id"] is not None

    datasets = app_client.get(
        f"/api/v1/projects/{project_id}/datasets",
        headers=auth_headers,
    ).json()
    dataset = datasets["items"][0]
    assert dataset["current_version_id"] == source_version_id
    versions = app_client.get(
        f"/api/v1/projects/{project_id}/datasets/{dataset['dataset_id']}/versions",
        headers=auth_headers,
    ).json()["items"]
    failed_version = next(
        version for version in versions if version["version_id"] == failed_plan["result_version_id"]
    )
    assert failed_version["status"] == "failed"
