"""Canonical JSON serialization and SHA-256 hashing for orchestration contracts.

Rules (from approved design §5):
- UTF-8 JSON.
- Object keys sorted lexicographically.
- No insignificant whitespace.
- Arrays preserve declared semantic order.
- ``Decimal`` → normalized base-10 string (no binary float).
- ``datetime`` → RFC 3339 UTC with ``Z`` suffix; naive rejected.
- ``date`` → ISO ``YYYY-MM-DD``.
- Enums → exact string value.
- UUIDs/identifiers → lowercase canonical string.
- Non-finite numeric values (NaN, Inf, -Inf) are REJECTED.
- Duplicate logical keys after normalization → REJECTED.
- Schema-defined exact key sets reject missing or extra keys where stated.

``result_hash`` = hex-encoded SHA-256 of the UTF-8 bytes of the canonical JSON.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

# ── Type aliases ────────────────────────────────────────────────────────────

JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
CanonicalInput = Mapping[str, Any] | list[Any] | str | int | float | bool | None


# ── Public API ──────────────────────────────────────────────────────────────


def canonical_json_bytes(obj: object) -> bytes:
    """Return the canonical UTF-8 JSON bytes for *obj*."""
    canonical = _canonicalize(obj)
    return json.dumps(
        canonical,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def result_hash(obj: object) -> str:
    """Return the hex-encoded SHA-256 of the canonical JSON of *obj*."""
    return hashlib.sha256(canonical_json_bytes(obj)).hexdigest()


# ── Canonicalization ────────────────────────────────────────────────────────


def _canonicalize(value: object) -> JsonValue:
    """Recursively canonicalize a Python object into a JSON-safe value."""
    if isinstance(value, (dict, Mapping)):
        # Detect duplicate logical keys after normalization
        _check_duplicate_keys(value)
        return {k: _canonicalize(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(v) for v in value]
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, Decimal):
        normalized = value.normalize()
        _sign, _digits, exp = normalized.as_tuple()
        if isinstance(exp, int) and exp > 0:
            return str(int(normalized))
        return str(normalized)
    if isinstance(value, float):
        if value != value or value == float("inf") or value == float("-inf"):
            raise ValueError(f"Non-finite float not allowed in canonical JSON: {value!r}")
        raise TypeError(
            f"Binary float {value!r} not allowed in canonical JSON — use Decimal instead"
        )
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise TypeError(
                f"Naive datetime not allowed in canonical JSON: {value!r}. "
                f"Use timezone-aware datetimes."
            )
        # Convert to UTC and format with Z suffix
        utc_value = value.astimezone(UTC)
        return utc_value.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value).lower()
    if isinstance(value, (str, int, bool)):
        return value
    if value is None:
        return value
    if hasattr(value, "__dataclass_fields__"):
        return {
            f.name: _canonicalize(getattr(value, f.name))
            for f in sorted(value.__dataclass_fields__.values(), key=lambda f: f.name)
        }
    raise TypeError(f"Cannot canonicalize type {type(value).__name__}: {value!r}")


# ── Duplicate key detection ─────────────────────────────────────────────────


def _check_duplicate_keys(mapping: Mapping[str, object]) -> None:
    """Detect duplicate logical keys after case normalization.

    Two distinct original keys that normalize to the same canonical key
    (case-insensitive match) are rejected as ambiguous.
    """
    seen: dict[str, str] = {}
    for original_key in mapping:
        normalized = original_key.lower() if isinstance(original_key, str) else str(original_key)
        if normalized in seen:
            raise ValueError(
                f"Duplicate logical key: {original_key!r} and {seen[normalized]!r} "
                f"both normalize to {normalized!r}"
            )
        seen[normalized] = original_key
