from sqlalchemy import inspect, text

from app.persistence.session import get_database


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
        "alembic_version",
    }.issubset(set(inspector.get_table_names()))

    with database.engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 5000
