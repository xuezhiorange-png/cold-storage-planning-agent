"""Canonical JSON serialisation and content hashing.

Deterministic serialisation guarantees that identical inputs always produce
the same canonical JSON bytes and SHA-256 hash, regardless of dict key
insertion order.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


def _default_serializer(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (UUID,)):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Cannot serialise {type(obj).__name__}")


def canonical_json(data: dict[str, Any]) -> str:
    """Return deterministic JSON string with sorted keys and no whitespace."""
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        default=_default_serializer,
        ensure_ascii=False,
    )


def content_hash(data: dict[str, Any]) -> str:
    """SHA-256 hex digest of the canonical JSON representation."""
    canonical = canonical_json(data)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
