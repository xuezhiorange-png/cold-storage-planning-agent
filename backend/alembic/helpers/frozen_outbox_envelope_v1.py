"""Frozen envelope hashing algorithm v1 for migration 0033.

DO NOT MODIFY THIS FILE WITHOUT WRITING A NEW VERSIONED MODULE.

This module duplicates the deterministic envelope hashing algorithm
that was current at the time migration ``0033_extend_outbox_envelope``
was authored.  The migration must backfill legacy rows using the exact
algorithm that the production dispatcher will recompute — otherwise
envelope hashes will diverge between backfilled rows and newly inserted
rows, and the dispatcher will refuse to materialize the backfilled
events (P0-9 fail-closed contract).

The production application code that drives *new* events lives in the
application layer (the orchestration module's outbox_identity
submodule).  That module is allowed to evolve; this module MUST NOT.
Any change to the canonical hashing algorithm must be introduced as
``_v2`` and consumed by a future migration, never by mutating this file.

Invariants:
    * The algorithm below MUST stay byte-identical to the v1 implementation
      that shipped alongside migration 0033.
    * No imports from the application layer (no ``modules.*`` imports).
    * No external state, no I/O, no global mutable state.
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
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _check_nan_inf_v1(obj: Any) -> None:
    """Raise ValueError if the object contains any binary float (v1 algorithm)."""
    if isinstance(obj, float):
        raise ValueError(f"Binary float {obj!r} is not allowed in canonical JSON")
    elif isinstance(obj, dict):
        for v in obj.values():
            _check_nan_inf_v1(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _check_nan_inf_v1(v)


def canonical_json_v1(obj: Any) -> str:
    """Return canonical JSON for deterministic hashing (v1 algorithm)."""
    _check_nan_inf_v1(obj)
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        default=_strict_json_default_v1,
    )


def _canonical_payload_datetime_v1(obj: Any) -> Any:
    """Recursively normalize datetimes inside payload to UTC ISO-8601 strings."""
    if isinstance(obj, datetime):
        return _ensure_utc_aware_v1(obj).isoformat()
    if isinstance(obj, dict):
        return {k: _canonical_payload_datetime_v1(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_canonical_payload_datetime_v1(v) for v in obj]
    return obj


def compute_envelope_hash_v1(
    *,
    event_schema_version: str,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    actor: str,
    correlation_id: str,
    occurred_at: datetime | str | None,
    request_id: str | None = None,
    identity_id: str | None = None,
    attempt_id: str | None = None,
    calculation_run_id: str | None = None,
    source_binding_id: str | None = None,
    payload: dict[str, object],
    event_identity: str | None = None,
) -> str:
    """SHA-256 hex of the canonical JSON of the full frozen envelope (v1).

    Bit-identical to the v1 implementation that shipped in
    ``outbox_identity.compute_envelope_hash`` at the time migration 0033
    was authored.  Any change to this function is a contract break —
    add a new ``_v2`` module instead.
    """
    envelope = {
        "event_schema_version": event_schema_version,
        "event_type": event_type,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "actor": actor,
        "correlation_id": correlation_id,
        "occurred_at": (
            _ensure_utc_aware_v1(occurred_at).isoformat()
            if isinstance(occurred_at, datetime)
            else occurred_at
        ),
        "event_identity": event_identity,
        "request_id": request_id,
        "identity_id": identity_id,
        "attempt_id": attempt_id,
        "calculation_run_id": calculation_run_id,
        "source_binding_id": source_binding_id,
        "payload": _canonical_payload_datetime_v1(payload),
    }
    return hashlib.sha256(canonical_json_v1(envelope).encode("utf-8")).hexdigest()


def compute_payload_hash_v1(payload: dict[str, object]) -> str:
    """SHA-256 hex digest of the canonical JSON payload (v1 algorithm)."""
    return hashlib.sha256(canonical_json_v1(payload).encode("utf-8")).hexdigest()
