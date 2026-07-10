from __future__ import annotations

from sqlalchemy import select

from app.persistence.orm.workflow_models import AnalysisSpecRow, UserDecisionRow
from app.persistence.session import get_database
from tests.contract.test_dataset_contract import upload_csv
from tests.contract.test_openapi_alignment import assert_matches_schema, load_contract


def _upload_analysis_version(client, headers: dict[str, str], project_id: str) -> str:
    job = upload_csv(
        client,
        project_id,
        headers,
        key="analysis-spec-source",
        content=(b"feature,target,segment\n1,yes,a\n2,no,a\n3,yes,b\n4,no,b\n5,yes,a\n6,no,b\n"),
    )
    completed = client.get(
        f"/api/v1/jobs/{job['job_id']}",
        headers=headers,
    ).json()
    assert completed["status"] == "succeeded"
    return str(completed["resource_id"])


def _valid_spec(version_id: str) -> dict[str, object]:
    return {
        "name": "用户转化分类",
        "dataset_version_id": version_id,
        "task": "binary_classification",
        "target": "target",
        "prediction_time_description": "使用事件发生前已经可用的特征预测转化",
        "split_strategy": "stratified",
        "metrics": ["accuracy", "f1"],
        "included_columns": ["feature", "segment"],
        "excluded_columns": [],
        "random_seed": 42,
        "causal_interpretation_allowed": False,
    }


def test_analysis_spec_revision_confirmation_and_audit(
    app_client,
    auth_headers: dict[str, str],
    create_project,
) -> None:
    contract = load_contract()
    project = create_project(key="analysis-spec-project")
    project_id = str(project["project_id"])
    version_id = _upload_analysis_version(app_client, auth_headers, project_id)
    url = f"/api/v1/projects/{project_id}/analysis-specs"
    payload = _valid_spec(version_id)

    created = app_client.post(
        url,
        headers={**auth_headers, "Idempotency-Key": "analysis-spec-create"},
        json=payload,
    )
    assert created.status_code == 201, created.text
    spec = created.json()
    assert_matches_schema(contract, "AnalysisSpec", spec)
    assert spec["revision"] == 1
    assert spec["status"] == "draft"
    assert spec["validation_warnings"] == []

    replay = app_client.post(
        url,
        headers={**auth_headers, "Idempotency-Key": "analysis-spec-create"},
        json=payload,
    )
    assert replay.status_code == 201
    assert replay.json()["spec_id"] == spec["spec_id"]

    updated = app_client.patch(
        f"{url}/{spec['spec_id']}",
        headers={**auth_headers, "If-Match": '"1"'},
        json={"name": "用户转化分类 v2", "metrics": ["accuracy", "roc_auc"]},
    )
    assert updated.status_code == 200, updated.text
    revised = updated.json()
    assert_matches_schema(contract, "AnalysisSpec", revised)
    assert revised["revision"] == 2
    assert revised["name"] == "用户转化分类 v2"

    stale = app_client.patch(
        f"{url}/{spec['spec_id']}",
        headers={**auth_headers, "If-Match": '"1"'},
        json={"name": "过期编辑"},
    )
    assert stale.status_code == 412
    assert stale.json()["error"]["details"]["current_revision"] == 2

    listed = app_client.get(
        url,
        headers=auth_headers,
        params={"dataset_version_id": version_id},
    )
    assert listed.status_code == 200
    assert_matches_schema(contract, "AnalysisSpecPage", listed.json())
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["revision"] == 2

    confirmed = app_client.post(
        f"{url}/{spec['spec_id']}/confirm",
        headers={**auth_headers, "Idempotency-Key": "analysis-spec-confirm"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"

    immutable = app_client.patch(
        f"{url}/{spec['spec_id']}",
        headers={**auth_headers, "If-Match": '"2"'},
        json={"name": "不应成功"},
    )
    assert immutable.status_code == 409

    session = get_database().session()
    try:
        revisions = list(
            session.scalars(
                select(AnalysisSpecRow)
                .where(AnalysisSpecRow.spec_id == spec["spec_id"])
                .order_by(AnalysisSpecRow.revision)
            )
        )
        assert [(row.revision, row.status) for row in revisions] == [
            (1, "superseded"),
            (2, "confirmed"),
        ]
        decision = session.scalar(
            select(UserDecisionRow).where(
                UserDecisionRow.object_type == "analysis_spec",
                UserDecisionRow.object_id == spec["spec_id"],
            )
        )
        assert decision is not None
        assert decision.action == "confirm"
    finally:
        session.close()


def test_analysis_spec_rejects_incompatible_fields_and_metrics(
    app_client,
    auth_headers: dict[str, str],
    create_project,
) -> None:
    project = create_project(key="analysis-spec-validation-project")
    project_id = str(project["project_id"])
    version_id = _upload_analysis_version(app_client, auth_headers, project_id)
    url = f"/api/v1/projects/{project_id}/analysis-specs"

    invalid_metric = _valid_spec(version_id)
    invalid_metric["metrics"] = ["rmse"]
    response = app_client.post(
        url,
        headers={**auth_headers, "Idempotency-Key": "analysis-invalid-metric"},
        json=invalid_metric,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    missing_target = _valid_spec(version_id)
    missing_target["target"] = None
    response = app_client.post(
        url,
        headers={**auth_headers, "Idempotency-Key": "analysis-missing-target"},
        json=missing_target,
    )
    assert response.status_code == 422

    bad_split = _valid_spec(version_id)
    bad_split["split_strategy"] = "temporal"
    response = app_client.post(
        url,
        headers={**auth_headers, "Idempotency-Key": "analysis-bad-split"},
        json=bad_split,
    )
    assert response.status_code == 422

    unknown_column = _valid_spec(version_id)
    unknown_column["included_columns"] = ["not_a_column"]
    response = app_client.post(
        url,
        headers={**auth_headers, "Idempotency-Key": "analysis-unknown-column"},
        json=unknown_column,
    )
    assert response.status_code == 422
