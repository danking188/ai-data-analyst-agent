from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DomainError(Exception):
    code: str
    message: str
    status_code: int
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message


def not_found(message: str = "资源不存在或无权访问") -> DomainError:
    return DomainError("RESOURCE_NOT_FOUND", message, 404)


def permission_denied(message: str = "无操作权限") -> DomainError:
    return DomainError("PERMISSION_DENIED", message, 403)


def state_conflict(message: str, **details: Any) -> DomainError:
    return DomainError("STATE_CONFLICT", message, 409, details=details)


def version_conflict(current_revision: int) -> DomainError:
    return DomainError(
        "VERSION_CONFLICT",
        "资源已被修改，请刷新后重试",
        412,
        details={"current_revision": current_revision},
    )


def idempotency_conflict() -> DomainError:
    return DomainError(
        "IDEMPOTENCY_CONFLICT",
        "同一幂等键不能用于不同请求",
        409,
    )


def validation_error(message: str, **details: Any) -> DomainError:
    return DomainError("VALIDATION_ERROR", message, 422, details=details)
