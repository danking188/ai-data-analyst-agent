from __future__ import annotations

import re
from typing import Annotated

from fastapi import Header

from app.domain.errors import validation_error

IF_MATCH_PATTERN = re.compile(r'^"([1-9][0-9]*)"$')


def parse_if_match(if_match: Annotated[str, Header(alias="If-Match")]) -> int:
    match = IF_MATCH_PATTERN.fullmatch(if_match)
    if not match:
        raise validation_error('If-Match 必须为双引号包围的正整数，例如 "3"')
    return int(match.group(1))


def require_idempotency_key(
    key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> str:
    return key
