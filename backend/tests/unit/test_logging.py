from __future__ import annotations

import json
import logging

from app.core.logging import JsonFormatter


def test_json_formatter_includes_proxy_host_context() -> None:
    record = logging.LogRecord(
        name="app.requests",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request completed",
        args=(),
        exc_info=None,
    )
    record.host = "internal-service"
    record.forwarded_host = "analytics.example.com"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["host"] == "internal-service"
    assert payload["forwarded_host"] == "analytics.example.com"
