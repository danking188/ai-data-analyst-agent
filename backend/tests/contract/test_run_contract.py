from __future__ import annotations

import pytest
from sqlalchemy import select

from app.analysis.tool_registry import ToolRegistry
from app.core.ids import new_id
from app.domain.errors import DomainError
from app.persistence.orm.workflow_models import AnalysisSpecRow
from app.persistence.repositories.claims import ClaimRepository
from app.persistence.session import get_database
from app.persistence.unit_of_work import UnitOfWork
from app.workers.reports import ReportExportWorker
from tests.contract.test_analysis_spec_contract import (
    _upload_analysis_version,
    _valid_spec,
)
from tests.contract.test_openapi_alignment import assert_matches_schema, load_contract


def _confirmed_spec(client, headers: dict[str, str], project_id: str, version_id: str) -> str:
    url = f"/api/v1/projects/{project_id}/analysis-specs"
    created = client.post(
        url,
        headers={**headers, "Idempotency-Key": f"run-spec-{project_id}"},
        json=_valid_spec(version_id),
    )
    assert created.status_code == 201, created.text
    spec_id = str(created.json()["spec_id"])
    confirmed = client.post(
        f"{url}/{spec_id}/confirm",
        headers={**headers, "Idempotency-Key": f"run-confirm-{project_id}"},
    )
    assert confirmed.status_code == 200
    return spec_id


def test_analysis_run_create_execute_get_and_list(
    app_client,
    auth_headers: dict[str, str],
    create_project,
) -> None:
    contract = load_contract()
    project = create_project(key="analysis-run-project")
    project_id = str(project["project_id"])
    version_id = _upload_analysis_version(app_client, auth_headers, project_id)
    spec_id = _confirmed_spec(
        app_client,
        auth_headers,
        project_id,
        version_id,
    )
    url = f"/api/v1/projects/{project_id}/runs"
    payload = {
        "analysis_spec_id": spec_id,
        "dataset_version_id": version_id,
        "run_kind": "full",
    }

    started = app_client.post(
        url,
        headers={**auth_headers, "Idempotency-Key": "analysis-run-create"},
        json=payload,
    )
    assert started.status_code == 202, started.text
    assert_matches_schema(contract, "Job", started.json())
    job = app_client.get(
        f"/api/v1/jobs/{started.json()['job_id']}",
        headers=auth_headers,
    ).json()
    assert job["status"] == "succeeded"
    assert job["resource_type"] == "analysis_run"

    fetched = app_client.get(
        f"{url}/{job['resource_id']}",
        headers=auth_headers,
    )
    assert fetched.status_code == 200
    run = fetched.json()
    assert_matches_schema(contract, "AnalysisRun", run)
    assert run["status"] == "succeeded"
    assert run["progress"] == 100
    assert run["analysis_spec_id"] == spec_id
    assert run["steps"][0]["tool_name"] == "dataset.inspect"
    assert run["steps"][0]["status"] == "succeeded"
    assert run["steps"][1]["tool_name"] == "eda.profile"
    assert run["steps"][1]["status"] == "succeeded"
    assert run["steps"][1]["tool_version"] == "2.0.0"
    assert run["steps"][2]["tool_name"] == "model.train_compare"
    assert run["steps"][2]["tool_version"] == "2.0.0"
    assert run["steps"][2]["status"] == "succeeded"
    assert run["environment"]["network_access"] is False
    assert run["steps"][2]["artifact_ids"]

    artifacts = app_client.get(
        f"{url}/{job['resource_id']}/artifacts",
        headers=auth_headers,
    )
    assert artifacts.status_code == 200
    artifact_page = artifacts.json()
    assert_matches_schema(contract, "ArtifactPage", artifact_page)
    assert artifact_page["total"] == 10
    assert {item["type"] for item in artifact_page["items"]} == {
        "metric",
        "table",
        "chart",
        "model",
        "comparison",
        "file",
        "log",
    }
    chart = next(item for item in artifact_page["items"] if item["type"] == "chart")
    assert chart["run_id"] == job["resource_id"]
    assert chart["dataset_version_id"] == version_id
    assert chart["parameters"]["dataset_version_id"] == version_id
    assert chart["result"]["charts"]
    model = next(item for item in artifact_page["items"] if item["type"] == "model")
    assert model["result"]["model_family"] in {
        "logistic_regression",
        "hist_gradient_boosting",
    }
    assert model["result"]["split"]["train_rows"] > 0
    assert model["result"]["split"]["test_rows"] > 0
    assert model["result"]["leakage_controls"]["split_before_fit"] is True
    assert model["result"]["leakage_controls"]["fit_scope"] == "train_only"
    assert model["result"]["leakage_controls"]["test_used_for_selection"] is False
    assert model["result"]["cross_validation"]["selection_scope"] == (
        "training_partition_only"
    )
    metric = next(
        item for item in artifact_page["items"] if item["name"] == "保留集评估指标"
    )
    assert metric["result"]["metrics"]["accuracy"] is not None
    assert metric["result"]["baseline_metrics"]["accuracy"] is not None
    comparison = next(
        item
        for item in artifact_page["items"]
        if item["type"] == "comparison" and "candidates" in item["result"]
    )
    assert {candidate["name"] for candidate in comparison["result"]["candidates"]} == {
        "dummy",
        "logistic_regression",
        "hist_gradient_boosting",
    }
    model_file = next(item for item in artifact_page["items"] if item["type"] == "file")
    assert model_file["downloadable"] is True
    assert model_file["result"]["file_name"].endswith(".joblib")

    fetched_artifact = app_client.get(
        f"/api/v1/projects/{project_id}/artifacts/{chart['artifact_id']}",
        headers=auth_headers,
    )
    assert fetched_artifact.status_code == 200
    assert_matches_schema(contract, "Artifact", fetched_artifact.json())
    assert fetched_artifact.json()["artifact_id"] == chart["artifact_id"]

    chart_only = app_client.get(
        f"{url}/{job['resource_id']}/artifacts",
        headers=auth_headers,
        params={"type": "chart"},
    )
    assert chart_only.status_code == 200
    assert chart_only.json()["total"] == 2

    claims = app_client.get(
        f"{url}/{job['resource_id']}/claims",
        headers=auth_headers,
    )
    assert claims.status_code == 200
    claim_page = claims.json()
    assert_matches_schema(contract, "ClaimPage", claim_page)
    assert claim_page["total"] == 2
    assert {claim["validation_status"] for claim in claim_page["items"]} == {"passed"}
    assert all(claim["evidence_ids"] for claim in claim_page["items"])

    fetched_claim = app_client.get(
        f"/api/v1/projects/{project_id}/claims/{claim_page['items'][0]['claim_id']}",
        headers=auth_headers,
    )
    assert fetched_claim.status_code == 200
    assert_matches_schema(contract, "Claim", fetched_claim.json())
    assert fetched_claim.json()["evidence_ids"]

    export = app_client.post(
        f"/api/v1/projects/{project_id}/reports",
        headers={**auth_headers, "Idempotency-Key": "report-export-html"},
        json={
            "run_id": job["resource_id"],
            "format": "html",
            "claim_ids": [claim["claim_id"] for claim in claim_page["items"]],
            "include_code": True,
            "include_evidence": True,
        },
    )
    assert export.status_code == 202, export.text
    assert_matches_schema(contract, "Job", export.json())
    export_job = app_client.get(
        f"/api/v1/jobs/{export.json()['job_id']}",
        headers=auth_headers,
    ).json()
    assert export_job["status"] == "succeeded"
    assert export_job["resource_type"] == "artifact"
    exported_artifact = app_client.get(
        f"/api/v1/projects/{project_id}/artifacts/{export_job['resource_id']}",
        headers=auth_headers,
    )
    assert exported_artifact.status_code == 200
    assert exported_artifact.json()["type"] == "file"
    assert exported_artifact.json()["downloadable"] is True
    assert exported_artifact.json()["result"]["content_type"].startswith("text/html")

    download = app_client.post(
        f"/api/v1/projects/{project_id}/artifacts/{export_job['resource_id']}/download",
        headers={**auth_headers, "Idempotency-Key": "artifact-download-html"},
    )
    assert download.status_code == 200
    assert_matches_schema(contract, "Download", download.json())
    assert download.json()["file_name"].endswith(".html")
    downloaded_file = app_client.get(download.json()["download_url"])
    assert downloaded_file.status_code == 200
    assert downloaded_file.headers["content-type"].startswith("text/html")
    assert b"AI Data Analyst" in downloaded_file.content

    replay = app_client.post(
        url,
        headers={**auth_headers, "Idempotency-Key": "analysis-run-create"},
        json=payload,
    )
    assert replay.status_code == 202
    assert replay.json()["job_id"] == started.json()["job_id"]

    listed = app_client.get(
        url,
        headers=auth_headers,
        params={"status": "succeeded", "dataset_version_id": version_id},
    )
    assert listed.status_code == 200
    assert_matches_schema(contract, "AnalysisRunPage", listed.json())
    assert listed.json()["total"] == 1


def test_run_requires_confirmed_spec_and_queued_run_can_be_cancelled(
    app_client,
    auth_headers: dict[str, str],
    create_project,
) -> None:
    contract = load_contract()
    project = create_project(key="analysis-run-cancel-project")
    project_id = str(project["project_id"])
    version_id = _upload_analysis_version(app_client, auth_headers, project_id)
    specs_url = f"/api/v1/projects/{project_id}/analysis-specs"
    draft = app_client.post(
        specs_url,
        headers={**auth_headers, "Idempotency-Key": "run-draft-spec"},
        json=_valid_spec(version_id),
    )
    assert draft.status_code == 201
    rejected = app_client.post(
        f"/api/v1/projects/{project_id}/runs",
        headers={**auth_headers, "Idempotency-Key": "run-with-draft"},
        json={
            "analysis_spec_id": draft.json()["spec_id"],
            "dataset_version_id": version_id,
        },
    )
    assert rejected.status_code == 409

    confirmed = app_client.post(
        f"{specs_url}/{draft.json()['spec_id']}/confirm",
        headers={**auth_headers, "Idempotency-Key": "run-draft-confirm"},
    )
    assert confirmed.status_code == 200

    database = get_database()
    session = database.session()
    try:
        spec = session.scalar(
            select(AnalysisSpecRow)
            .where(AnalysisSpecRow.spec_id == draft.json()["spec_id"])
            .order_by(AnalysisSpecRow.revision.desc())
        )
        assert spec is not None
        run_id = new_id("run_")
        with UnitOfWork(session) as uow:
            job = uow.jobs.create(
                project_id=project_id,
                kind="analysis_run",
                request={"run_id": run_id},
                subject_id="dev-user",
            )
            uow.runs.create(
                run_id=run_id,
                project_id=project_id,
                dataset_version_id=version_id,
                spec_revision_id=spec.spec_revision_id,
                run_kind="full",
                job_id=job.job_id,
                random_seed=spec.random_seed,
                subject_id="dev-user",
            )
    finally:
        session.close()

    cancelled = app_client.post(
        f"/api/v1/projects/{project_id}/runs/{run_id}/cancel",
        headers={**auth_headers, "Idempotency-Key": "queued-run-cancel"},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert_matches_schema(contract, "AnalysisRun", cancelled.json())
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["steps"][0]["status"] == "cancelled"


def test_tool_registry_rejects_unregistered_tools() -> None:
    registry = ToolRegistry()
    with pytest.raises(DomainError) as raised:
        registry.execute("python.arbitrary", "latest", {})
    assert raised.value.code == "STATE_CONFLICT"
    assert raised.value.details["tool_name"] == "python.arbitrary"


def test_claim_validator_requires_evidence_for_numeric_claims() -> None:
    assert ClaimRepository.validate_claim_text("准确率达到 0.5", []) == [
        "结论包含数字，但没有绑定任何证据 Artifact"
    ]
    assert ClaimRepository.validate_claim_text("准确率达到 0.5", ["art_abc"]) == []


def test_notebook_export_contains_executable_rerun_entrypoint() -> None:
    notebook = ReportExportWorker._notebook(
        {
            "project_id": "prj_test",
            "run_id": "run_test",
            "dataset_version_id": "dsv_test",
        },
        [],
        {"include_code": True},
    )
    source = "".join(notebook["cells"][-1]["source"])
    assert "entrypoint placeholder" not in source
    assert "api_request" in source
    assert "analysis_spec_id" in source
    assert "Idempotency-Key" in source
