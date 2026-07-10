from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.ids import new_id
from app.persistence.orm import UserRow


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_username(self, username: str) -> UserRow | None:
        return self.session.scalar(select(UserRow).where(UserRow.username == username))

    def create(self, *, username: str, password_hash: str) -> UserRow:
        now = utc_now()
        row = UserRow(
            user_id=new_id("usr_"),
            username=username,
            password_hash=password_hash,
            status="active",
            failed_login_attempts=0,
            locked_until=None,
            last_login_at=None,
            password_updated_at=now,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def record_login_success(self, row: UserRow) -> None:
        now = utc_now()
        row.failed_login_attempts = 0
        row.locked_until = None
        row.last_login_at = now
        row.updated_at = now
        self.session.flush()

    def record_login_failure(self, row: UserRow, *, locked_until: datetime | None) -> None:
        row.failed_login_attempts += 1
        row.locked_until = locked_until
        row.updated_at = utc_now()
        self.session.flush()
