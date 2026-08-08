"""Canonical JSON serialization for release-candidate evidence artifacts.

Implements the deterministic serialization contract frozen in
``TASK-012-V0.2-SLICE2-RELEASE-CANDIDATE-BUILD-AND-PROVENANCE-EVIDENCE-GAP-CONTRACT-FREEZE-R1``
Section 8.2:

* UTF-8 encoded, ASCII-safe (``ensure_ascii=True``).
* Deterministic key order (the caller supplies an already-ordered mapping).
* Exactly one trailing newline.
* Duplicate JSON keys are rejected.
* Absolute paths in artifact ``relative_path`` entries are rejected.
* Secret values (DSN userinfo, ``password=`` / ``token=`` style assignments)
  are rejected.  Secret detection delegates to the existing redaction
  authority :mod:`cold_storage.bootstrap.configuration_redactor` (read-only
  reuse — that module is not modified by this scope).

This module is the lowest layer of the ``release`` package; every other
release module imports :class:`ReleaseEvidenceError` and the canonical
helpers from here.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from cold_storage.bootstrap.configuration_redactor import redact_text

# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class ReleaseEvidenceError(Exception):
    """Base class for every release-evidence failure.

    Callers branch on ``failure_code`` (an ``RC_*`` code from the frozen
    error table) rather than parsing ``str(exc)``.  ``detail`` never
    carries secrets, DSNs, or unsafe paths.
    """

    failure_code: str = "RC_RELEASE_EVIDENCE_ERROR"

    def __init__(self, *, failure_code: str, detail: str = "") -> None:
        self.failure_code = failure_code
        self.detail = detail
        super().__init__(detail or failure_code)


class CanonicalSerializationError(ReleaseEvidenceError):
    """Raised when canonical serialization / parsing rules are violated."""

    failure_code = "RC_CANONICAL_SERIALIZATION_ERROR"


# ---------------------------------------------------------------------------
# Canonical serialization helpers
# ---------------------------------------------------------------------------

#: ASCII-only, compact separators, no extra whitespace.  Keys are emitted in
#: the order they appear in the supplied mapping (callers build ordered
#: dicts explicitly per the frozen schema field order).
_CANONICAL_SEPARATORS = (",", ":")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """``object_pairs_hook`` that rejects duplicate JSON keys."""
    seen: set[str] = set()
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise CanonicalSerializationError(
                failure_code="DUPLICATE_JSON_KEY",
                detail=f"duplicate JSON key: {key!r}",
            )
        seen.add(key)
        out[key] = value
    return out


def load_json_strict(raw: str) -> dict[str, Any]:
    """Parse JSON rejecting duplicate keys.

    Raises :class:`CanonicalSerializationError` with
    ``failure_code='DUPLICATE_JSON_KEY'`` on duplicate keys.  The caller
    is responsible for mapping this to the schema-specific error code
    (e.g. ``RC_ARTIFACT_DUPLICATE_KEY``).
    """
    if not isinstance(raw, str):
        raise CanonicalSerializationError(
            failure_code="NON_STRING_INPUT",
            detail="canonical JSON input must be a str",
        )
    try:
        data = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise CanonicalSerializationError(
            failure_code="MALFORMED_JSON",
            detail=f"malformed JSON: {exc.msg}",
        ) from exc
    if not isinstance(data, dict):
        raise CanonicalSerializationError(
            failure_code="NON_OBJECT_ROOT",
            detail="canonical JSON root must be an object",
        )
    return data


def canonical_dumps(ordered_obj: Mapping[str, Any]) -> str:
    """Serialize an already-ordered mapping to canonical JSON text.

    The mapping MUST already be ordered by the caller per the frozen
    schema field order.  Output is ASCII-safe (``ensure_ascii=True``),
    compact, and ends with exactly one trailing newline.
    """
    if not isinstance(ordered_obj, Mapping):
        raise CanonicalSerializationError(
            failure_code="NON_OBJECT_INPUT",
            detail="canonical serialization requires a mapping",
        )
    body = json.dumps(ordered_obj, ensure_ascii=True, separators=_CANONICAL_SEPARATORS)
    return body + "\n"


def canonical_bytes(ordered_obj: Mapping[str, Any]) -> bytes:
    """Return the canonical UTF-8 byte sequence (including trailing newline)."""
    return canonical_dumps(ordered_obj).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest of *data*."""
    return hashlib.sha256(data).hexdigest()


def to_digest_str(hexdigest: str) -> str:
    """Return ``sha256:<hexdigest>`` for a bare hex digest."""
    return f"sha256:{hexdigest}"


def sha256_digest_str(data: bytes) -> str:
    """Return ``sha256:<hex>`` for the given bytes."""
    return to_digest_str(sha256_hex(data))


def canonical_digest(ordered_obj: Mapping[str, Any]) -> str:
    """Return ``sha256:<hex>`` of the canonical byte sequence of *ordered_obj*."""
    return sha256_digest_str(canonical_bytes(ordered_obj))


# ---------------------------------------------------------------------------
# Content validators (absolute-path + secret rejection)
# ---------------------------------------------------------------------------

_SECRET_FIELD_NAMES = frozenset(
    {
        "password",
        "postgres_password",
        "database_url",
        "cold_storage_database_url",
        "redis_url",
        "dsn",
        "api_key",
        "api_keys",
        "token",
        "tokens",
        "private_key",
        "private_keys",
        "secret",
        "authorization",
    }
)


def _looks_like_secret_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    if lowered in _SECRET_FIELD_NAMES:
        return True
    return any(
        part in lowered
        for part in (
            "password",
            "token",
            "secret",
            "api_key",
            "authorization",
            "dsn",
            "private_key",
        )
    )


def _string_contains_secret(value: str) -> bool:
    """True if redaction would alter the value (i.e. a secret is embedded)."""
    if not isinstance(value, str):
        return False
    return redact_text(value) != value


def reject_secret_values(obj: Any, *, path: str = "") -> None:
    """Recursively reject secret-bearing keys or embedded secret strings.

    Raises :class:`CanonicalSerializationError` with
    ``failure_code='SECRET_VALUE_DETECTED'``.
    """
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            child_path = f"{path}.{key}" if path else str(key)
            if _looks_like_secret_key(str(key)) and value not in (None, "", []):
                raise CanonicalSerializationError(
                    failure_code="SECRET_VALUE_DETECTED",
                    detail=f"secret-bearing field present: {child_path}",
                )
            reject_secret_values(value, path=child_path)
        return
    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            reject_secret_values(item, path=f"{path}[{index}]")
    elif isinstance(obj, str):
        if _string_contains_secret(obj):
            raise CanonicalSerializationError(
                failure_code="SECRET_VALUE_DETECTED",
                detail=f"secret value detected in field: {path or '<root>'}",
            )


def reject_absolute_paths(artifacts: list[Mapping[str, Any]]) -> None:
    """Reject absolute paths in artifact ``relative_path`` entries.

    Raises :class:`CanonicalSerializationError` with
    ``failure_code='ABSOLUTE_PATH_REJECTED'``.
    """
    for index, entry in enumerate(artifacts):
        if not isinstance(entry, Mapping):
            raise CanonicalSerializationError(
                failure_code="ABSOLUTE_PATH_REJECTED",
                detail=f"artifact entry {index} is not an object",
            )
        rel = entry.get("relative_path")
        if not isinstance(rel, str) or not rel:
            raise CanonicalSerializationError(
                failure_code="ABSOLUTE_PATH_REJECTED",
                detail=f"artifact entry {index} missing relative_path",
            )
        if rel.startswith("/") or rel.startswith("\\"):
            raise CanonicalSerializationError(
                failure_code="ABSOLUTE_PATH_REJECTED",
                detail=f"absolute path rejected: {rel}",
            )
