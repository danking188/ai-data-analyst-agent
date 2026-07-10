from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.api.schemas import Project, ProjectCreate, ProjectPage, ProjectUpdate
from app.core.clock import utc_now
from app.core.ids import new_id
from app.domain.errors import not_found, permission_denied, state_conflict, version_conflict
from app.persistence.orm.models import AuditLogRow, ProjectMemberRow, ProjectRow
from app.persistence.repositories.audit import AuditRepository
from app.persistence.repositories.projects import ProjectRepository


def project_to_schema(row: ProjectRow) -> Project:
    return Project(
        project_id=row.project_id,
        name=row.name,
        description=row.description,
        timezone=row.timezone,
        language=row.language,
        status=row.status,
        current_dataset_version_id=row.current_dataset_version_id,
        revision=row.revision,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class ProjectService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.projects = ProjectRepository(session)
        self.audit = AuditRepository(session)

    def create(
        self,
        payload: ProjectCreate,
        *,
        subject_id: str,
        request_id: str,
    ) -> Project:
        now = utc_now()
        project_id = new_id("prj_")
        row = ProjectRow(
            project_id=project_id,
            name=payload.name,
            description=payload.description,
            timezone=payload.timezone,
            language=payload.language,
            status="active",
            current_dataset_version_id=None,
            revision=1,
            created_by=subject_id,
            created_at=now,
            updated_at=now,
            archived_at=None,
        )
        owner = ProjectMemberRow(
            project_id=project_id,
            subject_id=subject_id,
            role="owner",
            created_at=now,
            created_by=subject_id,
        )
        self.projects.add(row, owner)
        self.audit.add(
            AuditLogRow(
                audit_id=new_id("audit_"),
                project_id=project_id,
                subject_id=subject_id,
                action="project.created",
                object_type="project",
                object_id=project_id,
                result="success",
                request_id=request_id,
                ip_hash=None,
                summary_json={"name": payload.name},
                error_code=None,
                created_at=now,
            )
        )
        self.session.flush()
        return project_to_schema(row)

    def get(self, project_id: str, *, subject_id: str) -> Project:
        result = self.projects.get_for_subject(project_id, subject_id)
        if result is None:
            raise not_found()
        return project_to_schema(result[0])

    def list(
        self,
        *,
        subject_id: str,
        page: int,
        page_size: int,
        status: str | None,
        sort: str | None,
    ) -> ProjectPage:
        sort_field, descending = self._parse_sort(sort)
        result = self.projects.list_for_subject(
            subject_id,
            page=page,
            page_size=page_size,
            status=status,
            sort_field=sort_field,
            descending=descending,
        )
        return ProjectPage(
            items=[project_to_schema(row) for row in result.items],
            page=page,
            page_size=page_size,
            total=result.total,
            has_more=page * page_size < result.total,
        )

    def update(
        self,
        project_id: str,
        payload: ProjectUpdate,
        *,
        expected_revision: int,
        subject_id: str,
        request_id: str,
    ) -> Project:
        result = self.projects.get_for_subject(project_id, subject_id)
        if result is None:
            raise not_found()
        row, role = result
        if role not in {"owner", "editor"}:
            raise permission_denied()
        if row.status != "active":
            raise state_conflict("归档项目不能修改", status=row.status)
        if row.revision != expected_revision:
            raise version_conflict(row.revision)
        values: dict[str, Any] = payload.model_dump(exclude_unset=True)
        if not values:
            return project_to_schema(row)
        updated_at = utc_now()
        if not self.projects.update_if_revision(
            project_id,
            expected_revision,
            values,
            updated_at,
        ):
            self.session.expire_all()
            current = self.projects.get_for_subject(project_id, subject_id)
            raise version_conflict(current[0].revision if current else expected_revision)
        self.audit.add(
            AuditLogRow(
                audit_id=new_id("audit_"),
                project_id=project_id,
                subject_id=subject_id,
                action="project.updated",
                object_type="project",
                object_id=project_id,
                result="success",
                request_id=request_id,
                ip_hash=None,
                summary_json={"changed_fields": sorted(values)},
                error_code=None,
                created_at=updated_at,
            )
        )
        self.session.flush()
        self.session.expire_all()
        refreshed = self.projects.get_for_subject(project_id, subject_id)
        if refreshed is None:
            raise not_found()
        return project_to_schema(refreshed[0])

    def archive(
        self,
        project_id: str,
        *,
        subject_id: str,
        request_id: str,
    ) -> None:
        result = self.projects.get_for_subject(project_id, subject_id)
        if result is None:
            raise not_found()
        row, role = result
        if role != "owner":
            raise permission_denied("只有项目所有者可以归档项目")
        if row.status == "archived":
            return
        now = utc_now()
        self.projects.archive(row, now)
        self.audit.add(
            AuditLogRow(
                audit_id=new_id("audit_"),
                project_id=project_id,
                subject_id=subject_id,
                action="project.archived",
                object_type="project",
                object_id=project_id,
                result="success",
                request_id=request_id,
                ip_hash=None,
                summary_json={},
                error_code=None,
                created_at=now,
            )
        )

    @staticmethod
    def _parse_sort(sort: str | None) -> tuple[str, bool]:
        if sort is None:
            return "updated_at", True
        field, separator, direction = sort.partition(":")
        if (
            separator != ":"
            or field not in ProjectRepository.SORT_FIELDS
            or direction not in {"asc", "desc"}
        ):
            from app.domain.errors import validation_error

            raise validation_error(
                "不支持的排序参数",
                allowed=["created_at:asc|desc", "updated_at:asc|desc", "name:asc|desc"],
            )
        return field, direction == "desc"
