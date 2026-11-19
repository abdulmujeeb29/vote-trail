"""JSON logging with request IDs and redaction of phones, keys and tokens."""

from __future__ import annotations

import contextvars
import json
import logging
import re

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_PATTERNS = [
    (re.compile(r"\+?234\d{10}"), "[phone]"),
    (re.compile(r"\b0[789][01]\d{8}\b"), "[phone]"),
    (
        re.compile(
            r"(?i)(api[_-]?key|token|secret|password|authorization)([\"'=:\s]+)([^\s\"',]+)"
        ),
        r"\1\2[redacted]",
    ),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "[redacted]"),
]


def redact(text: str) -> str:
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload)
