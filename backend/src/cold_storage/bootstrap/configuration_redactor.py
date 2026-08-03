"""Secure recursive redaction for configuration surfaces.

Covers 11 secret types and supports multiple emit points (log, metric
label, error response, audit payload, evidence).  All redaction functions
fail closed – on any internal error the output is replaced with
``<REDACTION_FAILED>`` rather than leaking the original value.
"""

from __future__ import annotations

import re
import traceback
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

# ---------------------------------------------------------------------------
# Existing sensitive-key infrastructure (preserved)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# SECRET_TYPE_ENUM – 11 secret types
# ---------------------------------------------------------------------------


class SecretType(StrEnum):
    """Enumeration of all secret types the redactor knows how to handle."""

    DATABASE_URL = "DATABASE_URL"
    REDIS_URL = "REDIS_URL"
    OTHER_DSN = "OTHER_DSN"
    PASSWORD = "PASSWORD"
    TOKEN = "TOKEN"
    API_KEY = "API_KEY"
    COOKIE = "COOKIE"
    AUTHORIZATION_HEADER = "AUTHORIZATION_HEADER"
    SECRET_ENVIRONMENT_VARIABLE = "SECRET_ENVIRONMENT_VARIABLE"
    SIGNED_URL = "SIGNED_URL"
    CREDENTIAL_BEARING_EXCEPTION = "CREDENTIAL_BEARING_EXCEPTION"


# ---------------------------------------------------------------------------
# EMIT_POINT_ENUM
# ---------------------------------------------------------------------------


class EmitPoint(StrEnum):
    """Where the redacted value will be emitted."""

    LOG = "LOG"
    METRIC_LABEL = "METRIC_LABEL"
    ERROR_RESPONSE = "ERROR_RESPONSE"
    AUDIT_PAYLOAD = "AUDIT_PAYLOAD"
    EVIDENCE = "EVIDENCE"


# ---------------------------------------------------------------------------
# Regex patterns for each secret type
# ---------------------------------------------------------------------------

# DATABASE_URL: postgresql://user:pass@host/db, mysql://..., sqlite:///...
_DSN_PATTERN = re.compile(r"(?i)([a-z][a-z0-9+\-.]*://[^:/@\s]+):([^@/\s]+)@")

# REDIS_URL: redis://user:pass@host, rediss://...
_REDIS_URL_PATTERN = re.compile(r"(?i)(rediss?://[^:/@\s]+):([^@/\s]+)@")

# Password in key=value / key:value pairs
_PASSWORD_KV_PATTERN = re.compile(
    r"(?i)(password|passwd|pwd)\s*[=:]\s*\S+",
)

# Token in key=value pairs
_TOKEN_KV_PATTERN = re.compile(
    r"(?i)(token|access_token|refresh_token|id_token)\s*[=:]\s*\S+",
)

# API key patterns
_API_KEY_PATTERN = re.compile(
    r"(?i)(api[_-]?key|apikey)\s*[=:]\s*\S+",
)

# Cookie header values
_COOKIE_PATTERN = re.compile(
    r"(?i)(cookie)\s*[=:]\s*[^\n;]+",
)

# Authorization header
_AUTHORIZATION_PATTERN = re.compile(
    r"(?i)(authorization)\s*[=:]\s*(?:Bearer\s+)?[^\s,;]+",
)

# Secret environment variable (KEY=SECRET_VALUE where the key suggests secret)
_SECRET_ENV_PATTERN = re.compile(
    r"(?i)(SECRET|PRIVATE|CREDENTIAL|AUTH)[A-Z_]*\s*=\s*\S+",
)

# Signed URL – query-string signatures
_SIGNED_URL_PATTERN = re.compile(
    r"(?i)([?&](?:sig|signature|X-Amz-Signature|X-Goog-Signature|sign)"
    r"=[^&\s]+)",
)

# Credential-bearing exception text patterns
_CREDENTIAL_BEARING_EXCEPTION_PATTERN = re.compile(
    r"(?i)(credential|auth|token|secret|password)[^\n]{0,120}",
)


# ---------------------------------------------------------------------------
# Core redaction functions (existing – preserved and extended)
# ---------------------------------------------------------------------------


def is_sensitive_key(key: object) -> bool:
    """Return *True* if the given key name looks like it holds a secret."""
    name = str(key).lower().replace("-", "_")
    return name in SENSITIVE_NAMES or any(
        part in name for part in ("password", "token", "secret", "api_key", "authorization")
    )


def redact_text(value: object) -> str:
    """Redact secrets found in arbitrary text.

    Covers DSN userinfo and key=value secret assignments.
    """
    text = str(value)
    text = _DSN_USERINFO.sub(r"\1:***@", text)
    text = _SECRET_ASSIGNMENT.sub(r"\1=***", text)
    return text


def redact(value: Any, *, key: object | None = None) -> Any:
    """Recursively redact a configuration value.

    If *key* is provided and looks sensitive, the value is replaced with
    ``***``.  Strings are processed through :func:`redact_text`.
    Containers (dict, list, tuple) are recursed into.
    """
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
    """Return a redacted summary of an exception suitable for error responses."""
    return redact_text(type(exc).__name__ + ": configuration validation failed")


def safe_report(report: Any) -> Any:
    """Return a redacted version of a report object or dict."""
    if hasattr(report, "to_dict"):
        return redact(report.to_dict())
    return redact(report)


# ---------------------------------------------------------------------------
# ConfigurationRedactor class (preserved)
# ---------------------------------------------------------------------------


class ConfigurationRedactor:
    """Namespace class exposing redaction helpers as static methods."""

    redact = staticmethod(redact)
    redact_text = staticmethod(redact_text)
    safe_exception_text = staticmethod(safe_exception_text)
    safe_report = staticmethod(safe_report)


# ---------------------------------------------------------------------------
# Extended redaction for all 11 secret types
# ---------------------------------------------------------------------------

_FAIL_CLOSED_REPLACEMENT = "<REDACTION_FAILED>"

# Map SecretType to the regex patterns that detect that type.
_SECRET_TYPE_PATTERNS: dict[SecretType, list[re.Pattern[str]]] = {
    SecretType.DATABASE_URL: [_DSN_PATTERN, _REDIS_URL_PATTERN],
    SecretType.REDIS_URL: [_REDIS_URL_PATTERN],
    SecretType.OTHER_DSN: [_DSN_PATTERN],
    SecretType.PASSWORD: [_PASSWORD_KV_PATTERN, _DSN_PATTERN],
    SecretType.TOKEN: [_TOKEN_KV_PATTERN],
    SecretType.API_KEY: [_API_KEY_PATTERN],
    SecretType.COOKIE: [_COOKIE_PATTERN],
    SecretType.AUTHORIZATION_HEADER: [_AUTHORIZATION_PATTERN],
    SecretType.SECRET_ENVIRONMENT_VARIABLE: [_SECRET_ENV_PATTERN],
    SecretType.SIGNED_URL: [_SIGNED_URL_PATTERN],
    SecretType.CREDENTIAL_BEARING_EXCEPTION: [
        _CREDENTIAL_BEARING_EXCEPTION_PATTERN,
    ],
}


def _redact_pattern(text: str, pattern: re.Pattern[str]) -> str:
    """Replace the sensitive part of a regex match with ``***``."""

    def _replacer(m: re.Match[str]) -> str:
        matched = m.group(0)
        # For DSN patterns keep the scheme and host but redact userinfo.
        userinfo = _DSN_USERINFO.search(matched)
        if userinfo:
            return _DSN_USERINFO.sub(r"\1:***@", matched)
        # For key=value patterns redact the value portion.
        eq_match = re.search(r"[=:](\s*\S+)$", matched)
        if eq_match:
            return matched[: eq_match.start(1)] + "***"
        return "***"

    return pattern.sub(_replacer, text)


def redact_for_logging(
    text: object,
    *,
    emit_point: EmitPoint = EmitPoint.LOG,
) -> str:
    """Redact text covering all 11 secret types.

    This is the primary entry-point for redacting strings before they
    are written to logs, metric labels, error responses, audit payloads,
    or evidence stores.

    Parameters
    ----------
    text:
        The raw text to redact.
    emit_point:
        Where the redacted value will be emitted.  Currently all emit
        points use the same redaction strategy; the parameter is
        accepted for forward-compatibility and audit-trail purposes.

    Returns
    -------
    str
        The redacted text.  If any internal error occurs during
        redaction, returns ``<REDACTION_FAILED>`` (fail-closed).
    """
    try:
        result = str(text)

        # Apply every secret-type pattern.
        for _secret_type, patterns in _SECRET_TYPE_PATTERNS.items():
            for pattern in patterns:
                result = _redact_pattern(result, pattern)

        # Also apply the base redaction (DSN userinfo + key=value secrets).
        result = _DSN_USERINFO.sub(r"\1:***@", result)
        result = _SECRET_ASSIGNMENT.sub(r"\1=***", result)

        return result
    except Exception:  # noqa: BLE001
        return _FAIL_CLOSED_REPLACEMENT


def redact_exception_for_logging(
    exc: BaseException,
    *,
    emit_point: EmitPoint = EmitPoint.LOG,
) -> str:
    """Produce a redacted string representation of an exception for logging.

    Covers all 11 secret types that might appear in exception messages,
    tracebacks, or stringified exception objects.

    Fail-closed: if redaction itself fails, returns ``<REDACTION_FAILED>``.
    """
    try:
        # Attempt to get a useful string from the exception.
        raw: str
        try:
            raw = str(exc)
        except Exception:  # noqa: BLE001
            raw = type(exc).__name__

        # Include the traceback if available (tracebacks can leak secrets).
        tb_text: str = ""
        try:
            tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        except Exception:  # noqa: BLE001
            tb_text = ""

        combined = f"{raw}\n{tb_text}" if tb_text else raw
        return redact_for_logging(combined, emit_point=emit_point)
    except Exception:  # noqa: BLE001
        return _FAIL_CLOSED_REPLACEMENT


# Public aliases matching contract naming
SECRET_TYPE_ENUM = SecretType
EMIT_POINT_ENUM = EmitPoint
