from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.domain.errors import idempotency_conflict
from app.persistence.orm.models import IdempotencyKeyRow


def canonical_request_hash(payload: Any) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    row: IdempotencyKeyRow
    created: bool


class IdempotencyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def reserve(
        self,
        *,
        subject_id: str,
        method: str,
        path: str,
        idempotency_key: str,
        request_hash: str,
        ttl_hours: int = 24,
    ) -> IdempotencyRecord:
        key = (subject_id, method.upper(), path, idempotency_key)
        existing = self.session.get(IdempotencyKeyRow, key)
        now = utc_now()
        if existing is not None and existing.expires_at <= now:
            self.session.delete(existing)
            self.session.flush()
            existing = None
        if existing is not None:
            if existing.request_hash != request_hash:
                raise idempotency_conflict()
            return IdempotencyRecord(existing, created=False)

        row = IdempotencyKeyRow(
            subject_id=subject_id,
            method=method.upper(),
            path=path,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            resource_type=None,
            resource_id=None,
            job_id=None,
            response_status=None,
            response_json=None,
            created_at=now,
            expires_at=now + timedelta(hours=ttl_hours),
        )
        try:
            with self.session.begin_nested():
                self.session.add(row)
                self.session.flush()
        except IntegrityError:
            concurrent = self.session.scalar(
                select(IdempotencyKeyRow).where(
                    IdempotencyKeyRow.subject_id == subject_id,
                    IdempotencyKeyRow.method == method.upper(),
                    IdempotencyKeyRow.path == path,
                    IdempotencyKeyRow.idempotency_key == idempotency_key,
                )
            )
            if concurrent is None or concurrent.request_hash != request_hash:
                raise idempotency_conflict() from None
            return IdempotencyRecord(concurrent, created=False)
        return IdempotencyRecord(row, created=True)

    def get(
        self,
        *,
        subject_id: str,
        method: str,
        path: str,
        idempotency_key: str,
    ) -> IdempotencyKeyRow | None:
        row = self.session.get(
            IdempotencyKeyRow,
            (subject_id, method.upper(), path, idempotency_key),
        )
        if row is not None and row.expires_at <= utc_now():
            self.session.delete(row)
            self.session.flush()
            return None
        return row

    def add(self, row: IdempotencyKeyRow) -> None:
        self.session.add(row)
        self.session.flush()

    def complete(
        self,
        row: IdempotencyKeyRow,
        *,
        response_status: int,
        response: dict[str, Any],
        resource_type: str | None = None,
        resource_id: str | None = None,
        job_id: str | None = None,
    ) -> None:
        row.response_status = response_status
        row.response_json = response
        row.resource_type = resource_type
        row.resource_id = resource_id
        row.job_id = job_id
        self.session.flush()
