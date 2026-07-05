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
    * ``source_slots`` MUST be assembled by callers as an ordered
      sequence of ``(slot_name, slot_payload)`` tuples in
      ``SOURCE_SLOT_ORDER_V1`` order.  This module does NOT validate
      the order — that responsibility is the caller's.  The
      archive_hash commits to the order via JSON's list-preserving
      serialisation; top-level dict keys are sorted alphabetically
      while nested lists preserve insertion order.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
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

    Ordered sequences (lists/tuples) of ``(name, payload)`` pairs are
    preserved verbatim in the JSON output — list elements are
    serialised in iteration order.  Top-level dict keys remain sorted
    alphabetically.
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


def prepare_ordered_source_slots_v1(
    source_slots: Sequence[tuple[str, Mapping[str, str]]],
) -> list[list[Any]]:
    """Convert a (name, payload) sequence into the JSON-safe list form.

    Returns ``[[name, payload_dict], ...]`` so the JSON encoder writes
    a list literal — order preserved, structure preserved.

    Validation of (a) named-set completeness, (b) named-set order, and
    (c) per-slot payload keys (``calculation_id`` + ``result_hash``) is
    the caller's responsibility.  This helper only normalises the
    in-memory representation into the JSON-safe form the algorithm
    binds to.
    """
    prepared: list[list[Any]] = []
    for entry in source_slots:
        if not isinstance(entry, (tuple, list)) or len(entry) != 2:
            raise ValueError(
                f"source_slots entry must be (name, payload) tuple, got {type(entry).__name__}"
            )
        name, payload = entry
        if not isinstance(name, str):
            raise ValueError(f"source_slots name must be str, got {type(name).__name__}")
        if not isinstance(payload, Mapping):
            raise ValueError(f"source_slots payload must be Mapping, got {type(payload).__name__}")
        prepared.append([name, dict(payload)])
    return prepared


def compute_archive_hash_v1(archive_payload: dict[str, Any]) -> str:
    """Return the SHA-256 hex digest of the canonical archive_payload.

    The archive_payload dict MUST be already in fixed shape (i.e. the
    ``source_slots`` field MUST be the JSON-safe list returned by
    ``prepare_ordered_source_slots_v1``; the algorithm binds to the
    order).  This function does NOT re-sort the slot sequence; the
    caller assembles it in ``SOURCE_SLOT_ORDER_V1`` order.

    Top-level dict ordering IS canonicalised by ``canonical_json_v1``
    (``sort_keys=True``).
    """
    if not isinstance(archive_payload, dict):
        raise ValueError(f"archive_payload must be dict, got {type(archive_payload).__name__}")
    canonical = canonical_json_v1(archive_payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
