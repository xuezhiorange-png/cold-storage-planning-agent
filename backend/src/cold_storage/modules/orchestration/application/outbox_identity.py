"""Deterministic event identity and canonical payload hashing for the audit outbox.

Event identity is a content-addressable key built from the business-meaningful
fields of an outbox event.  The same lifecycle transition always produces the
same identity, enabling idempotent writes.

Canonical JSON uses sort_keys=True and compact separators, matching the
existing project convention (json.dumps with sort_keys=True, separators=(',',':')).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any


def ensure_utc_aware(dt: datetime) -> datetime:
    """Normalize a datetime to an aware UTC datetime.

    - If *dt* is naive: assume it is UTC, attach tzinfo.
    - If *dt* is aware but not UTC: convert to UTC (never replace tzinfo).
    - If *dt* is already UTC-aware: return as-is.
    """
    if dt.tzinfo is None:
        # Naive — assume UTC
        return dt.replace(tzinfo=UTC)
    # Aware — convert to UTC (handles DST offsets correctly)
    return dt.astimezone(UTC)


def _strict_json_default(obj: Any) -> Any:
    """Strict JSON serialization default — handles known types, rejects unknown."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _check_nan_inf(obj: Any) -> None:
    """Raise ValueError if the object contains any binary float.

    Audit envelopes must use Decimal for numeric values.
    """
    if isinstance(obj, float):
        raise ValueError(f"Binary float {obj!r} is not allowed in canonical JSON")
    elif isinstance(obj, dict):
        for v in obj.values():
            _check_nan_inf(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _check_nan_inf(v)


def canonical_json(obj: Any) -> str:
    """Return canonical JSON for deterministic hashing.

    Uses sort_keys=True and compact separators, matching the project-wide
    convention found in reports, schemes, and planning_agent modules.

    Raises ValueError for NaN/Infinity floats and TypeError for unknown types.
    """
    _check_nan_inf(obj)
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        default=_strict_json_default,
    )


def compute_payload_hash(payload: dict[str, object]) -> str:
    """SHA-256 hex digest of the canonical JSON payload (payload-only)."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def compute_envelope_hash(
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
) -> str:
    """SHA-256 hex of the canonical JSON of the full frozen envelope."""
    envelope = {
        "event_schema_version": event_schema_version,
        "event_type": event_type,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "actor": actor,
        "correlation_id": correlation_id,
        "occurred_at": (
            ensure_utc_aware(occurred_at).isoformat()
            if isinstance(occurred_at, datetime)
            else occurred_at
        ),
        "request_id": request_id,
        "identity_id": identity_id,
        "attempt_id": attempt_id,
        "calculation_run_id": calculation_run_id,
        "source_binding_id": source_binding_id,
        "payload": payload,
    }
    return hashlib.sha256(canonical_json(envelope).encode("utf-8")).hexdigest()


_EVENT_SCHEMA_VERSION = "1.0"


def build_event_identity(
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    transition_id: str,
    schema_version: str = _EVENT_SCHEMA_VERSION,
) -> str:
    """Build a deterministic event identity from business-meaningful fields.

    Returns a 64-char SHA-256 hex digest of the structured identity
    projection, fitting safely within the VARCHAR(128) database column.

    Identity projection (canonical JSON, sorted keys):
        {
            "aggregate_id": "...",
            "aggregate_type": "...",
            "event_type": "...",
            "schema_version": "...",
            "transition_id": "..."
        }

    This ensures:
    - Same lifecycle transition → same identity (idempotent)
    - Different transitions → different identity
    - Fixed-length output suitable for DB columns and unique constraints
    """
    projection = {
        "aggregate_id": aggregate_id,
        "aggregate_type": aggregate_type,
        "event_type": event_type,
        "schema_version": schema_version,
        "transition_id": transition_id,
    }
    return hashlib.sha256(canonical_json(projection).encode("utf-8")).hexdigest()
