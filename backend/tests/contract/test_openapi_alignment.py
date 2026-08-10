from __future__ import annotations

from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from app.main import create_app

CONTRACT_PATH = Path(__file__).parents[3] / "docs" / "api" / "openapi.yaml"


def load_contract() -> dict[str, object]:
    with CONTRACT_PATH.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    assert isinstance(loaded, dict)
    return loaded


def contract_schema(contract: dict[str, object], name: str) -> dict[str, object]:
    components = contract["components"]
    assert isinstance(components, dict)
    schemas = components["schemas"]
    assert isinstance(schemas, dict)
    schema = schemas[name]
    assert isinstance(schema, dict)
    return schema


def assert_matches_schema(
    contract: dict[str, object],
    schema_name: str,
    payload: dict[str, object],
) -> None:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": f"#/components/schemas/{schema_name}",
        "components": contract["components"],
    }
    Draft202012Validator(schema).validate(payload)


def test_implemented_operation_ids_exist_in_shared_contract() -> None:
    contract = load_contract()
    paths = contract["paths"]
    assert isinstance(paths, dict)
    contract_operation_ids = {
        operation["operationId"]
        for path_item in paths.values()
        if isinstance(path_item, dict)
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"} and isinstance(operation, dict)
    }
    generated_paths = create_app().openapi()["paths"]
    implemented = {
        operation["operationId"]
        for path_item in generated_paths.values()
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    }
    assert implemented <= contract_operation_ids
    assert {
        "getHealth",
        "getReadiness",
        "getAuthConfig",
        "getCapabilities",
        "listProjects",
        "createProject",
        "getProject",
        "updateProject",
        "archiveProject",
        "getJob",
        "cancelJob",
    } <= implemented


def test_runtime_payloads_match_shared_schemas(
    app_client,
    auth_headers: dict[str, str],
    create_project,
) -> None:
    contract = load_contract()
    health = app_client.get("/api/v1/health").json()
    assert_matches_schema(contract, "Health", health)

    capabilities = app_client.get(
        "/api/v1/system/capabilities",
        headers=auth_headers,
    ).json()
    assert_matches_schema(contract, "SystemCapabilities", capabilities)

    project = create_project(key="schema-project")
    assert_matches_schema(contract, "Project", project)

    page = app_client.get("/api/v1/projects", headers=auth_headers).json()
    assert_matches_schema(contract, "ProjectPage", page)
