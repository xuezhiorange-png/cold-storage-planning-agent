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
from typing import Any


def canonical_json(obj: Any) -> str:
    """Return canonical JSON for deterministic hashing.

    Uses sort_keys=True and compact separators, matching the project-wide
    convention found in reports, schemes, and planning_agent modules.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def compute_payload_hash(payload: dict[str, object]) -> str:
    """SHA-256 hex digest of the canonical JSON payload envelope."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


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

    The identity is structured as:
        {schema_version}:{event_type}:{aggregate_type}:{aggregate_id}:{transition_id}

    This ensures:
    - Same lifecycle transition → same identity (idempotent)
    - Different transitions → different identity
    - Schema evolution can change the version prefix
    """
    return f"{schema_version}:{event_type}:{aggregate_type}:{aggregate_id}:{transition_id}"
