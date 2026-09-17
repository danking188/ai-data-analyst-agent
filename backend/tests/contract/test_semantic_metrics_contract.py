from __future__ import annotations

from tests.contract.test_schema_contract import _upload_schema_dataset


def test_semantic_metric_is_version_bound_and_schema_validated(
    app_client, auth_headers, create_project
) -> None:
    project = create_project(key="semantic-project")
    project_id = str(project["project_id"])
    version_id = _upload_schema_dataset(app_client, auth_headers, project_id)
    url = f"/api/v1/projects/{project_id}/semantic-metrics"

    created = app_client.post(
        url,
        headers={**auth_headers, "Idempotency-Key": "metric-revenue-1"},
        json={
            "dataset_version_id": version_id,
            "name": "房产总价",
            "description": "按邮编粒度汇总的房产价格",
            "source_column": "price",
            "aggregation": "sum",
            "unit": "CNY",
            "grain_dimensions": ["zip_code"],
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "active"

    replayed = app_client.post(
        url,
        headers={**auth_headers, "Idempotency-Key": "metric-revenue-1"},
        json={
            "dataset_version_id": version_id,
            "name": "房产总价",
            "description": "按邮编粒度汇总的房产价格",
            "source_column": "price",
            "aggregation": "sum",
            "unit": "CNY",
            "grain_dimensions": ["zip_code"],
        },
    )
    assert replayed.status_code == 201
    assert replayed.json()["metric_id"] == created.json()["metric_id"]

    listed = app_client.get(
        f"{url}?dataset_version_id={version_id}", headers=auth_headers
    )
    assert listed.status_code == 200
    assert [item["name"] for item in listed.json()["items"]] == ["房产总价"]

    sensitive = app_client.post(
        url,
        headers={**auth_headers, "Idempotency-Key": "metric-email-1"},
        json={
            "dataset_version_id": version_id,
            "name": "邮箱数",
            "description": "敏感字段不应成为指标",
            "source_column": "email",
            "aggregation": "distinct_count",
            "grain_dimensions": [],
        },
    )
    assert sensitive.status_code == 422


def test_schema_change_marks_incompatible_metric_stale(
    app_client, auth_headers, create_project
) -> None:
    project = create_project(key="semantic-stale-project")
    project_id = str(project["project_id"])
    version_id = _upload_schema_dataset(app_client, auth_headers, project_id)
    url = f"/api/v1/projects/{project_id}/semantic-metrics"
    created = app_client.post(
        url,
        headers={**auth_headers, "Idempotency-Key": "metric-stale-1"},
        json={
            "dataset_version_id": version_id,
            "name": "平均房价",
            "description": "平均房价",
            "source_column": "price",
            "aggregation": "average",
            "grain_dimensions": [],
        },
    )
    assert created.status_code == 201
    schema = app_client.get(
        f"/api/v1/projects/{project_id}/dataset-versions/{version_id}/schema",
        headers=auth_headers,
    ).json()
    changed = app_client.patch(
        f"/api/v1/projects/{project_id}/dataset-versions/{version_id}/schema",
        headers={**auth_headers, "If-Match": f'"{schema["revision"]}"'},
        json={
            "changes": [
                {"column": "price", "semantic_type": "text", "sensitive": True}
            ]
        },
    )
    assert changed.status_code == 200
    listed = app_client.get(url, headers=auth_headers).json()["items"]
    assert listed[0]["status"] == "stale"
