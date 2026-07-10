from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.ids import new_id
from app.domain.errors import version_conflict
from app.persistence.orm.models import ProjectMemberRow, ProjectRow


@dataclass(frozen=True, slots=True)
class Page[T]:
    items: list[T]
    page: int
    page_size: int
    total: int

    @property
    def has_more(self) -> bool:
        return self.page * self.page_size < self.total


class ProjectRepository:
    SORT_FIELDS = {"created_at", "updated_at", "name"}

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        name: str,
        description: str | None,
        timezone: str,
        language: str,
        subject_id: str,
    ) -> ProjectRow:
        now = utc_now()
        project = ProjectRow(
            project_id=new_id("prj_"),
            name=name,
            description=description,
            timezone=timezone,
            language=language,
            status="active",
            current_dataset_version_id=None,
            revision=1,
            created_by=subject_id,
            created_at=now,
            updated_at=now,
            archived_at=None,
        )
        member = ProjectMemberRow(
            project_id=project.project_id,
            subject_id=subject_id,
            role="owner",
            created_at=now,
            created_by=subject_id,
        )
        self.session.add(project)
        self.session.flush()
        self.session.add(member)
        self.session.flush()
        return project

    def get(self, project_id: str) -> ProjectRow | None:
        return self.session.get(ProjectRow, project_id)

    def add(self, project: ProjectRow, owner: ProjectMemberRow) -> None:
        self.session.add(project)
        self.session.flush()
        self.session.add(owner)
        self.session.flush()

    def get_for_subject(self, project_id: str, subject_id: str) -> tuple[ProjectRow, str] | None:
        statement = (
            select(ProjectRow, ProjectMemberRow.role)
            .join(
                ProjectMemberRow,
                ProjectMemberRow.project_id == ProjectRow.project_id,
            )
            .where(
                ProjectRow.project_id == project_id,
                ProjectMemberRow.subject_id == subject_id,
            )
        )
        result = self.session.execute(statement).one_or_none()
        if result is None:
            return None
        return result[0], result[1]

    def role_for_subject(self, project_id: str, subject_id: str) -> str | None:
        return self.session.scalar(
            select(ProjectMemberRow.role).where(
                ProjectMemberRow.project_id == project_id,
                ProjectMemberRow.subject_id == subject_id,
            )
        )

    def list_for_subject(
        self,
        subject_id: str,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        sort_field: str = "updated_at",
        descending: bool = True,
    ) -> Page[ProjectRow]:
        filters = [ProjectMemberRow.subject_id == subject_id]
        if status is not None:
            filters.append(ProjectRow.status == status)
        base = (
            select(ProjectRow)
            .join(
                ProjectMemberRow,
                ProjectMemberRow.project_id == ProjectRow.project_id,
            )
            .where(*filters)
        )
        total = self.session.scalar(
            select(func.count())
            .select_from(ProjectRow)
            .join(
                ProjectMemberRow,
                ProjectMemberRow.project_id == ProjectRow.project_id,
            )
            .where(*filters)
        )
        sort_column = getattr(ProjectRow, sort_field)
        ordering = sort_column.desc() if descending else sort_column.asc()
        rows = list(
            self.session.scalars(
                base.order_by(ordering, ProjectRow.project_id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return Page(items=rows, page=page, page_size=page_size, total=total or 0)

    def update(
        self,
        project: ProjectRow,
        *,
        expected_revision: int,
        values: dict[str, object],
    ) -> ProjectRow:
        if project.revision != expected_revision:
            raise version_conflict(project.revision)
        allowed = {"name", "description", "timezone", "language"}
        for field, value in values.items():
            if field not in allowed:
                continue
            setattr(project, field, value)
        project.revision += 1
        project.updated_at = utc_now()
        self.session.flush()
        return project

    def update_if_revision(
        self,
        project_id: str,
        expected_revision: int,
        values: dict[str, object],
        updated_at: datetime,
    ) -> bool:
        allowed = {"name", "description", "timezone", "language"}
        safe_values = {key: value for key, value in values.items() if key in allowed}
        result = self.session.execute(
            update(ProjectRow)
            .where(
                ProjectRow.project_id == project_id,
                ProjectRow.revision == expected_revision,
            )
            .values(
                **safe_values,
                revision=expected_revision + 1,
                updated_at=updated_at,
            )
        )
        self.session.flush()
        return bool(getattr(result, "rowcount", 0) == 1)

    def archive(
        self,
        project: ProjectRow,
        archived_at: datetime | None = None,
    ) -> None:
        if project.status == "archived":
            return
        now = archived_at or utc_now()
        project.status = "archived"
        project.archived_at = now
        project.updated_at = now
        project.revision += 1
        self.session.flush()

    def add_member(
        self,
        *,
        project_id: str,
        subject_id: str,
        role: str,
        created_by: str,
    ) -> ProjectMemberRow:
        member = ProjectMemberRow(
            project_id=project_id,
            subject_id=subject_id,
            role=role,
            created_at=utc_now(),
            created_by=created_by,
        )
        self.session.add(member)
        self.session.flush()
        return member
