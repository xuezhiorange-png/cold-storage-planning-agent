"""Frozen scheme source archive canonical hashing algorithm v1 for migration 0034.

DO NOT MODIFY THIS FILE WITHOUT WRITING A NEW VERSIONED MODULE.

This module duplicates the deterministic archive_payload canonicalisation
algorithm current at the time migration ``0034_add_production_source_archives``
was authored.  Any migration that writes or back-fills
``production_source_archives.archive_hash`` MUST compute the hash using this
exact algorithm so future reads (resolver / downgrade guard) recompute the
identical hash.  Diverging from this algorithm would silently corrupt
historical source identity verification.

The production application code that drives *new* archive writes lives in
the application layer
(``orchestration.application.canonical_archive_v1``).  That module is
allowed to evolve; this module MUST NOT.

Invariants:
    * The algorithm below MUST stay byte-identical to the v1 implementation
      that shipped alongside migration 0034.
    * No imports from the application layer (no ``modules.*`` imports).
    * No external state, no I/O, no global mutable state.
    * No dict-iteration order dependence: the payload schema is fixed-shape
      and assembled by callers via explicit key-value tuples, NOT dict
      iteration.  This module only provides ``canonical_json_v1`` and the
      archive_hash computation.  Callers are responsible for assembling the
      payload in a deterministic order.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any


def _ensure_utc_aware_v1(dt: datetime) -> datetime:
    """Normalize a datetime to an aware UTC datetime (v1 algorithm)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _strict_json_default_v1(obj: Any) -> Any:
    """Strict JSON serialization default — handles known types, rejects unknown."""
    if isinstance(obj, datetime):
        return _ensure_utc_aware_v1(obj).isoformat()
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _check_no_binary_float_v1(obj: Any) -> None:
    """Raise ValueError if the object contains any binary float (v1 algorithm).

    archive_payload MUST NOT contain binary floats (NaN, Inf, or finite
    floats) because their JSON serialization is implementation-defined.
    Engineering values must be stored as ``Decimal`` or as ``str``.
    """
    if isinstance(obj, float):
        raise ValueError(f"Binary float {obj!r} is not allowed in canonical archive_payload")
    if isinstance(obj, dict):
        for v in obj.values():
            _check_no_binary_float_v1(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _check_no_binary_float_v1(v)


def canonical_json_v1(obj: Any) -> str:
    """Return canonical JSON for deterministic archive_hash computation.

    Same rules as ``frozen_outbox_envelope_v1.canonical_json_v1``:
        * sort_keys=True, separators=(",", ":")
        * datetime -> UTC ISO-8601 string
        * Decimal -> normalised base-10 string
        * no binary float allowed (recursive check)
        * unknown object types raise TypeError
    """
    _check_no_binary_float_v1(obj)
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        default=_strict_json_default_v1,
    )


# The five source_slots in FIXED order (zone, cooling_load, equipment,
# power, investment).  Order is part of the algorithm contract.
SOURCE_SLOT_ORDER_V1: tuple[str, ...] = (
    "zone",
    "cooling_load",
    "equipment",
    "power",
    "investment",
)


def compute_archive_hash_v1(archive_payload: dict[str, Any]) -> str:
    """Return the SHA-256 hex digest of the canonical archive_payload.

    The archive_payload dict MUST be already in fixed shape (i.e. the
    ``source_slots`` sub-dict must list the five slots in SOURCE_SLOT_ORDER_V1
    order at the dict-literal construction site; this function does NOT
    re-sort the slot sub-dict because the caller is responsible for the
    payload shape).

    Top-level dict ordering IS canonicalised by ``canonical_json_v1``
    (``sort_keys=True``).
    """
    if not isinstance(archive_payload, dict):
        raise ValueError(f"archive_payload must be dict, got {type(archive_payload).__name__}")
    canonical = canonical_json_v1(archive_payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
