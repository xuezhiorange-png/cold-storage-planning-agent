"""Secure recursive redaction for configuration surfaces."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

SENSITIVE_NAMES: frozenset[str] = frozenset(
    {
        "password",
        "postgres_password",
        "database_url",
        "redis_url",
        "openai_api_key",
        "api_key",
        "token",
        "secret",
        "authorization",
    }
)
_SECRET_ASSIGNMENT = re.compile(r"(?i)(password|token|secret|api[_-]?key|authorization)=([^&\s]+)")
_DSN_USERINFO = re.compile(r"(?i)(://[^:/@]+):([^@]+)@")


def is_sensitive_key(key: object) -> bool:
    name = str(key).lower().replace("-", "_")
    return name in SENSITIVE_NAMES or any(
        part in name for part in ("password", "token", "secret", "api_key", "authorization")
    )


def redact_text(value: object) -> str:
    text = str(value)
    text = _DSN_USERINFO.sub(r"\1:***@", text)
    return _SECRET_ASSIGNMENT.sub(r"\1=***", text)


def redact(value: Any, *, key: object | None = None) -> Any:
    if key is not None and is_sensitive_key(key):
        return "***" if value not in (None, "") else value
    if isinstance(value, Mapping):
        return {str(k): redact(v, key=k) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact(v) for v in value)
    if isinstance(value, str):
        return redact_text(value)
    return value


def safe_exception_text(exc: BaseException) -> str:
    return redact_text(type(exc).__name__ + ": configuration validation failed")


def safe_report(report: Any) -> Any:
    if hasattr(report, "to_dict"):
        return redact(report.to_dict())
    return redact(report)


class ConfigurationRedactor:
    redact = staticmethod(redact)
    redact_text = staticmethod(redact_text)
    safe_exception_text = staticmethod(safe_exception_text)
    safe_report = staticmethod(safe_report)
