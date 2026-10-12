from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.persistence.session import get_database

BASELINE_REVISION = "20260917_0001"


def _primary_key_columns(connection) -> list[str]:
    rows = connection.execute(text("PRAGMA table_info(cleaning_operations)")).all()
    return [row[1] for row in sorted(rows, key=lambda row: row[5]) if row[5] > 0]


def _operation_count(connection) -> int:
    return int(connection.execute(text("SELECT COUNT(*) FROM cleaning_operations")).scalar_one())


def test_initial_migration_creates_foundation_tables(app_client) -> None:
    del app_client
    database = get_database()
    inspector = inspect(database.engine)
    assert {
        "projects",
        "project_members",
        "datasets",
        "dataset_versions",
        "jobs",
        "idempotency_keys",
        "audit_logs",
        "users",
        "assistant_conversations",
        "assistant_messages",
        "llm_runs",
        "llm_tool_calls",
        "assistant_feedback",
        "semantic_metrics",
        "alembic_version",
    }.issubset(set(inspector.get_table_names()))

    with database.engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 5000


def test_cleaning_operation_identity_is_scoped_to_its_plan(app_client) -> None:
    """F04: the table must accept the same operation_id in two different plans.

    Guards the composite primary key, the constraints that must survive the SQLite table
    rebuild, and the fact that the rebuild is reversible without losing rows.
    """
    from tests.contract.test_cleaning_contract import _operation, _upload_source_version

    headers = {"Authorization": "Bearer test-token"}
    project = app_client.post(
        "/api/v1/projects",
        headers={**headers, "Idempotency-Key": "migration-scope-project"},
        json={
            "name": "迁移测试项目",
            "description": "集成测试",
            "timezone": "Asia/Shanghai",
            "language": "zh-CN",
        },
    ).json()
    project_id = str(project["project_id"])
    version_id = _upload_source_version(app_client, project_id, headers)
    plans_url = f"/api/v1/projects/{project_id}/cleaning-plans"
    created = app_client.post(
        plans_url,
        headers={**headers, "Idempotency-Key": "migration-scope-plan"},
        json={
            "source_version_id": version_id,
            "name": "计划 A",
            "operations": [_operation(operation_id="cleanop_migration_shared")],
        },
    )
    assert created.status_code == 201, created.text

    database = get_database()
    with database.engine.connect() as connection:
        assert _primary_key_columns(connection) == ["plan_id", "operation_id"]
        index_names = {
            row[0]
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='index'")
            ).all()
        }
        table_sql = connection.execute(
            text("SELECT sql FROM sqlite_master WHERE name='cleaning_operations'")
        ).scalar_one()
    assert "uq_cleaning_operation_position" in table_sql
    assert "ck_cleaning_operation_type" in table_sql
    assert "ON DELETE CASCADE" in table_sql.upper()

    config = Config("alembic.ini")
    command.downgrade(config, BASELINE_REVISION)
    with database.engine.connect() as connection:
        assert _primary_key_columns(connection) == ["operation_id"]
        assert _operation_count(connection) == 1

    command.upgrade(config, "head")
    with database.engine.connect() as connection:
        assert _primary_key_columns(connection) == ["plan_id", "operation_id"]
        assert _operation_count(connection) == 1
        surviving = connection.execute(
            text("SELECT operation_id, plan_id FROM cleaning_operations")
        ).one()
    assert surviving == ("cleanop_migration_shared", created.json()["plan_id"])

    # The plan is still readable through the API after the round trip.
    reread = app_client.get(f"{plans_url}/{created.json()['plan_id']}", headers=headers)
    assert reread.status_code == 200, reread.text
    assert [item["operation_id"] for item in reread.json()["operations"]] == [
        "cleanop_migration_shared"
    ]

    # The rebuild must not drop any index that existed before the round trip.
    with database.engine.connect() as connection:
        rebuilt_index_names = {
            row[0]
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='index'")
            ).all()
        }
    assert index_names <= rebuilt_index_names


def test_downgrade_refuses_to_discard_shared_operation_ids(app_client) -> None:
    """F04: rolling the constraint back would have to delete real operations, so it fails closed."""
    import pytest

    from tests.contract.test_cleaning_contract import _operation, _upload_source_version

    headers = {"Authorization": "Bearer test-token"}
    project = app_client.post(
        "/api/v1/projects",
        headers={**headers, "Idempotency-Key": "migration-downgrade-project"},
        json={
            "name": "迁移回退测试项目",
            "description": "集成测试",
            "timezone": "Asia/Shanghai",
            "language": "zh-CN",
        },
    ).json()
    project_id = str(project["project_id"])
    version_id = _upload_source_version(app_client, project_id, headers)
    plans_url = f"/api/v1/projects/{project_id}/cleaning-plans"
    for index in (1, 2):
        created = app_client.post(
            plans_url,
            headers={**headers, "Idempotency-Key": f"migration-downgrade-plan-{index}"},
            json={
                "source_version_id": version_id,
                "name": f"计划 {index}",
                "operations": [_operation(operation_id="cleanop_downgrade_shared")],
            },
        )
        assert created.status_code == 201, created.text

    database = get_database()
    config = Config("alembic.ini")
    with pytest.raises(RuntimeError, match="cleanop_downgrade_shared"):
        command.downgrade(config, BASELINE_REVISION)

    # The refusal must leave the schema and the rows untouched.
    with database.engine.connect() as connection:
        assert _primary_key_columns(connection) == ["plan_id", "operation_id"]
        assert _operation_count(connection) == 2
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "20261011_0001"
