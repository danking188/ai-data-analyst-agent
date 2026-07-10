from __future__ import annotations

import re
import unicodedata
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.domain.errors import DomainError
from app.persistence.orm import UserRow
from app.persistence.repositories.users import UserRepository
from app.security.passwords import hash_password, verify_password

USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,31}$")
MAX_LOGIN_FAILURES = 5
LOCKOUT_MINUTES = 15


def normalize_username(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def validate_registration(username: str, password: str) -> str:
    normalized = normalize_username(username)
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise DomainError(
            "VALIDATION_ERROR",
            "用户名须为 3-32 位字母、数字、点、下划线或连字符，并以字母或数字开头",
            422,
        )
    if not 12 <= len(password) <= 128:
        raise DomainError("VALIDATION_ERROR", "密码长度须为 12-128 个字符", 422)
    if normalized in password.casefold():
        raise DomainError("VALIDATION_ERROR", "密码不能包含用户名", 422)
    return normalized


class AccountService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = UserRepository(session)

    def register(self, *, username: str, password: str) -> UserRow:
        normalized = validate_registration(username, password)
        if self.users.get_by_username(normalized) is not None:
            raise DomainError("USERNAME_TAKEN", "该用户名已被注册", 409)
        try:
            return self.users.create(username=normalized, password_hash=hash_password(password))
        except IntegrityError as exc:
            self.session.rollback()
            raise DomainError("USERNAME_TAKEN", "该用户名已被注册", 409) from exc

    def authenticate(self, *, username: str, password: str) -> UserRow:
        normalized = normalize_username(username)
        row = self.users.get_by_username(normalized)
        if row is None or row.status != "active":
            raise DomainError("AUTH_REQUIRED", "用户名或密码错误", 401)
        now = utc_now()
        if row.locked_until is not None and row.locked_until > now:
            raise DomainError("ACCOUNT_LOCKED", "登录失败次数过多，请稍后再试", 423)
        if not verify_password(password, row.password_hash):
            next_attempt = row.failed_login_attempts + 1
            locked_until = (
                now + timedelta(minutes=LOCKOUT_MINUTES)
                if next_attempt >= MAX_LOGIN_FAILURES
                else None
            )
            self.users.record_login_failure(row, locked_until=locked_until)
            self.session.commit()
            raise DomainError("AUTH_REQUIRED", "用户名或密码错误", 401)
        self.users.record_login_success(row)
        return row

    def ensure_bootstrap_user(self, *, username: str, password: str) -> None:
        normalized = normalize_username(username)
        if self.users.get_by_username(normalized) is not None:
            return
        self.users.create(username=normalized, password_hash=hash_password(password))
