from __future__ import annotations

from datetime import UTC

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.domain.errors import DomainError
from app.persistence.repositories.datasets import DatasetRepository, DatasetVersionDraft
from app.persistence.repositories.idempotency import (
    IdempotencyRepository,
    canonical_request_hash,
)
from app.persistence.repositories.projects import ProjectRepository
from app.persistence.session import get_database
from app.persistence.unit_of_work import UnitOfWork


def test_migrations_create_complete_metadata_schema(app_client: TestClient) -> None:
    del app_client
    table_names = set(inspect(get_database().engine).get_table_names())
    assert {
        "projects",
        "project_members",
        "datasets",
        "dataset_versions",
        "column_schemas",
        "quality_issues",
        "cleaning_plans",
        "cleaning_operations",
        "analysis_specs",
        "analysis_runs",
        "analysis_steps",
        "artifacts",
        "claims",
        "claim_evidence",
        "validation_results",
        "user_decisions",
        "conversation_summaries",
        "jobs",
        "idempotency_keys",
        "audit_logs",
        "alembic_version",
    }.issubset(table_names)


def test_dataset_versions_are_created_then_activated(app_client: TestClient) -> None:
    del app_client
    session = get_database().session()
    try:
        with UnitOfWork(session) as uow:
            project = uow.projects.create(
                name="版本测试",
                description=None,
                timezone="Asia/Shanghai",
                language="zh-CN",
                subject_id="user-1",
            )
            dataset = uow.datasets.create_dataset(
                project_id=project.project_id,
                name="orders.csv",
                source_type="csv",
                subject_id="user-1",
            )
            version = uow.datasets.create_version(
                project_id=project.project_id,
                dataset_id=dataset.dataset_id,
                subject_id="user-1",
                draft=DatasetVersionDraft(
                    source_file_name="orders.csv",
                    source_type="csv",
                    source_storage_key="projects/p1/source/orders.csv",
                    file_hash="sha256:" + "a" * 64,
                    file_size_bytes=1024,
                ),
            )
            assert version.status == "creating"
            assert version.version_number == 1
            uow.datasets.mark_version_ready(
                version,
                data_storage_key="projects/p1/versions/v1/data.parquet",
                data_checksum="sha256:" + "b" * 64,
                row_count=100,
                column_count=8,
            )
            uow.datasets.activate_version(
                project_id=project.project_id,
                dataset_id=dataset.dataset_id,
                version_id=version.version_id,
            )

        assert version.created_at.tzinfo is UTC
        assert version.ready_at is not None
        assert dataset.current_version_id == version.version_id
        assert project.current_dataset_version_id == version.version_id

        with pytest.raises(DomainError) as exc_info:
            DatasetRepository(session).mark_version_failed(
                version,
                failure_code="SHOULD_NOT_CHANGE",
                failure_details={},
            )
        assert exc_info.value.code == "STATE_CONFLICT"
    finally:
        session.close()


def test_derived_version_requires_ready_parent(app_client: TestClient) -> None:
    del app_client
    session = get_database().session()
    try:
        projects = ProjectRepository(session)
        datasets = DatasetRepository(session)
        project = projects.create(
            name="清洗版本",
            description=None,
            timezone="Asia/Shanghai",
            language="zh-CN",
            subject_id="user-1",
        )
        dataset = datasets.create_dataset(
            project_id=project.project_id,
            name="input.xlsx",
            source_type="xlsx",
            subject_id="user-1",
        )
        raw = datasets.create_version(
            project_id=project.project_id,
            dataset_id=dataset.dataset_id,
            subject_id="user-1",
            draft=DatasetVersionDraft(
                source_file_name="input.xlsx",
                source_type="xlsx",
                source_storage_key="source/input.xlsx",
                file_hash="sha256:" + "c" * 64,
                file_size_bytes=2048,
            ),
        )
        with pytest.raises(DomainError) as exc_info:
            datasets.create_version(
                project_id=project.project_id,
                dataset_id=dataset.dataset_id,
                subject_id="user-1",
                draft=DatasetVersionDraft(
                    source_file_name="input.xlsx",
                    source_type="xlsx",
                    source_storage_key="source/input.xlsx",
                    file_hash="sha256:" + "c" * 64,
                    file_size_bytes=2048,
                    parent_version_id=raw.version_id,
                    kind="cleaned",
                ),
            )
        assert exc_info.value.code == "STATE_CONFLICT"
        session.rollback()
    finally:
        session.close()


def test_idempotency_reservation_replays_and_rejects_changed_payload(
    app_client: TestClient,
) -> None:
    del app_client
    session = get_database().session()
    try:
        repository = IdempotencyRepository(session)
        request_hash = canonical_request_hash({"name": "A", "timezone": "Asia/Shanghai"})
        first = repository.reserve(
            subject_id="user-1",
            method="POST",
            path="/api/v1/projects",
            idempotency_key="project-create-001",
            request_hash=request_hash,
        )
        assert first.created is True
        repository.complete(
            first.row,
            response_status=201,
            response={"project_id": "prj_demo"},
            resource_type="project",
            resource_id="prj_demo",
        )
        session.commit()

        replay = repository.reserve(
            subject_id="user-1",
            method="POST",
            path="/api/v1/projects",
            idempotency_key="project-create-001",
            request_hash=request_hash,
        )
        assert replay.created is False
        assert replay.row.response_json == {"project_id": "prj_demo"}

        with pytest.raises(DomainError) as exc_info:
            repository.reserve(
                subject_id="user-1",
                method="POST",
                path="/api/v1/projects",
                idempotency_key="project-create-001",
                request_hash=canonical_request_hash({"name": "B"}),
            )
        assert exc_info.value.code == "IDEMPOTENCY_CONFLICT"
    finally:
        session.close()


def test_unit_of_work_rolls_back_on_error(app_client: TestClient) -> None:
    del app_client
    session = get_database().session()
    project_id: str | None = None
    try:
        with pytest.raises(RuntimeError), UnitOfWork(session) as uow:
            project = uow.projects.create(
                name="应回滚",
                description=None,
                timezone="Asia/Shanghai",
                language="zh-CN",
                subject_id="user-1",
            )
            project_id = project.project_id
            raise RuntimeError("force rollback")
        assert project_id is not None
        assert ProjectRepository(session).get(project_id) is None
    finally:
        session.close()
