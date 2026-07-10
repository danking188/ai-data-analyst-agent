from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.ids import new_id
from app.persistence.orm.models import AuditLogRow


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def append(
        self,
        *,
        action: str,
        result: str,
        summary: dict[str, Any],
        project_id: str | None = None,
        subject_id: str | None = None,
        object_type: str | None = None,
        object_id: str | None = None,
        request_id: str | None = None,
        ip_hash: str | None = None,
        error_code: str | None = None,
    ) -> AuditLogRow:
        row = AuditLogRow(
            audit_id=new_id("aud_"),
            project_id=project_id,
            subject_id=subject_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            result=result,
            request_id=request_id,
            ip_hash=ip_hash,
            summary_json=summary,
            error_code=error_code,
            created_at=utc_now(),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def add(self, row: AuditLogRow) -> None:
        self.session.add(row)
        self.session.flush()
