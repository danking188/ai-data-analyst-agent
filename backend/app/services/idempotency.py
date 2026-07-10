from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

from app.core.clock import utc_now
from app.domain.errors import idempotency_conflict
from app.persistence.orm.models import IdempotencyKeyRow
from app.persistence.repositories.idempotency import IdempotencyRepository


def canonical_request_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


class IdempotencyService:
    def __init__(self, repository: IdempotencyRepository) -> None:
        self.repository = repository

    def replay_or_none(
        self,
        *,
        subject_id: str,
        method: str,
        path: str,
        key: str,
        request_hash: str,
    ) -> dict[str, Any] | None:
        existing = self.repository.get(
            subject_id=subject_id,
            method=method,
            path=path,
            idempotency_key=key,
        )
        if existing is None:
            return None
        if existing.request_hash != request_hash:
            raise idempotency_conflict()
        return existing.response_json

    def record(
        self,
        *,
        subject_id: str,
        method: str,
        path: str,
        key: str,
        request_hash: str,
        resource_type: str,
        resource_id: str,
        response_status: int,
        response_json: dict[str, Any],
    ) -> None:
        now = utc_now()
        self.repository.add(
            IdempotencyKeyRow(
                subject_id=subject_id,
                method=method,
                path=path,
                idempotency_key=key,
                request_hash=request_hash,
                resource_type=resource_type,
                resource_id=resource_id,
                job_id=None,
                response_status=response_status,
                response_json=response_json,
                created_at=now,
                expires_at=now + timedelta(hours=24),
            )
        )
