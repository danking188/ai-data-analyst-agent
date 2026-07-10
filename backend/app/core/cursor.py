from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass

from app.domain.errors import validation_error


@dataclass(frozen=True, slots=True)
class PreviewCursor:
    version_id: str
    offset: int
    checksum: str


class CursorCodec:
    def __init__(self, secret: str) -> None:
        self.secret = secret.encode("utf-8")

    def encode(self, cursor: PreviewCursor) -> str:
        payload = json.dumps(
            {
                "version_id": cursor.version_id,
                "offset": cursor.offset,
                "checksum": cursor.checksum,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        signature = hmac.new(self.secret, payload, hashlib.sha256).digest()
        return self._b64(payload + signature)

    def decode(self, token: str) -> PreviewCursor:
        try:
            decoded = self._unb64(token)
            payload, signature = decoded[:-32], decoded[-32:]
            expected = hmac.new(self.secret, payload, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError("invalid signature")
            value = json.loads(payload)
            return PreviewCursor(
                version_id=str(value["version_id"]),
                offset=int(value["offset"]),
                checksum=str(value["checksum"]),
            )
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise validation_error("cursor 无效或已过期") from exc

    @staticmethod
    def _b64(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    @staticmethod
    def _unb64(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
