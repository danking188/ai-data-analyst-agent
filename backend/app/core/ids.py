from __future__ import annotations

import secrets
import time


def new_id(prefix: str) -> str:
    """Create a sortable, opaque identifier without exposing database internals."""
    timestamp_ms = int(time.time() * 1000)
    entropy = secrets.token_hex(8)
    return f"{prefix}{timestamp_ms:013x}{entropy}"


def new_request_id() -> str:
    return new_id("req_")
