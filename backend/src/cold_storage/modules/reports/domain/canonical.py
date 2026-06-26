"""Canonical JSON serialisation and content hashing.

Deterministic serialisation guarantees that identical inputs always produce
the same canonical JSON bytes and SHA-256 hash, regardless of dict key
insertion order.

Also provides a ``golden_serialize`` function (and its dict-building helper
``golden_dict``) that converts dataclass instances to plain dicts with every
field always present (no omission of None/empty).  The golden serialiser is
used by mutation / golden-file tests to detect unintended changes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass
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


# ---------------------------------------------------------------------------
# Golden serialiser — every dataclass field always present
# ---------------------------------------------------------------------------


def _val(obj: Any) -> Any:
    """Recursively convert a canonical dataclass value to a plain JSON-able type.

    Dataclasses → dict (all fields, including None/empty).
    Decimals → str.
    Tuples  → list.
    Sets    → sorted list (deterministic).
    ApprovalSnapshot → dict via its ``to_dict()`` method.
    None    → None.
    Everything else → as-is.
    """
    if obj is None:
        return None
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (datetime, UUID)):
        return _default_serializer(obj)
    if isinstance(obj, tuple):
        return [_val(item) for item in obj]
    if isinstance(obj, set):
        return sorted(obj)
    if is_dataclass(obj):
        return _golden_dataclass_to_dict(obj)
    if isinstance(obj, dict):
        return {k: _val(v) for k, v in obj.items()}
    if isinstance(obj, (list,)):
        return [_val(item) for item in obj]
    return obj


def _golden_dataclass_to_dict(dc: Any) -> dict[str, Any]:
    """Convert a dataclass to a dict, always including all fields.

    Every field is written to the output dict, even when the value is ``None``,
    ``\"\"``, ``0``, ``()``, ``[]``, or ``{}``.
    """
    result: dict[str, Any] = {}
    for f in fields(dc):
        value = getattr(dc, f.name)
        result[f.name] = _val(value)
    return result


def golden_dict(model: Any) -> dict[str, Any]:
    """Convert a ``CanonicalReportRenderModel`` (or any canonical dataclass) to a
    plain nested dict with **every field always present**.

    Fields whose value is ``None``, an empty string, an empty tuple, an empty
    list, or an empty dict are still included in the output.  This guarantees
    that golden-file comparisons can distinguish *empty* (e.g. ``approved_by=""``)
    from *missing* (key absent).
    """
    return _val(model)  # type: ignore[no-any-return]


def golden_json(model: Any) -> str:
    """Return deterministic golden JSON string for a ``CanonicalReportRenderModel``.

    The output always includes **all fields** of every canonical dataclass,
    down to the deepest nested value.
    """
    return canonical_json(golden_dict(model))
