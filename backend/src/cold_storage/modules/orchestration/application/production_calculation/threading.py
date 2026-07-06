"""Task 11B Phase 2 — threading helpers for production calculation adapters.

Helpers here exist to ensure every calculation call carries the
identity fields required by the future persistence layer
(``actor``, ``correlation_id``, ``database_backend``) and that the
deterministic ``content_hash`` is computed from a stable canonical
JSON encoding of the adapter payload.

These helpers are pure functions.  They do not read from the
database, do not write to the database, and do not import the
production ORM.  They take only typed inputs and return typed
outputs.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Final

# Identifiers that the future persistence layer will treat as NOT NULL.
# The Phase 1 contract (PR #37 migrations 0035+0036+0037) removed
# Python/server defaults for these columns, so the application layer
# is responsible for supplying them on every write path.
REQUIRED_IDENTITY_FIELDS: Final[tuple[str, ...]] = (
    "actor",
    "correlation_id",
    "database_backend",
)


def assert_identity_complete(
    *,
    actor: str,
    correlation_id: str,
    database_backend: str,
) -> None:
    """Raise ``InvalidProjectInputError`` if any identity field is empty.

    Used at every adapter boundary to fail closed when the
    projection helper has not been threaded with all three
    identity fields.  The frozen contract (PR #37) requires
    these fields to be non-empty on every write.
    """
    from cold_storage.modules.orchestration.application.production_calculation.errors import (
        InvalidProjectInputError,
    )

    if not actor:
        raise InvalidProjectInputError(field_name="actor", reason="actor must be non-empty")
    if not correlation_id:
        raise InvalidProjectInputError(
            field_name="correlation_id",
            reason="correlation_id must be non-empty",
        )
    if not database_backend:
        raise InvalidProjectInputError(
            field_name="database_backend",
            reason="database_backend must be non-empty (sqlite | postgresql)",
        )


def canonical_json(payload: Mapping[str, Any]) -> str:
    """Deterministic JSON encoding for ``content_hash`` derivation.

    Sorts keys, uses compact separators, and rejects non-JSON
    values so adapters cannot accidentally leak Python types
    (Decimal, datetime, …) into the hash.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=_json_default,
    )


def _json_default(value: object) -> Any:
    """Serialise types that json does not natively support.

    Supports ``str``, ``int``, ``float``, ``bool``, ``None`` and
    anything with an ``isoformat`` method (datetime-like).
    """
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        return iso()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON-serialisable")


def compute_content_hash(payload: Mapping[str, Any]) -> str:
    """Return the canonical ``content_hash`` for an adapter payload.

    The hash is the hex-encoded SHA-256 of the canonical JSON
    encoding.  Identical payloads (regardless of dict key order)
    produce identical hashes.
    """
    encoded = canonical_json(payload).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def assert_database_backend_supported(database_backend: str) -> None:
    """Validate the ``database_backend`` value is one of the supported dialects.

    The frozen contract (PR #37) records only two production
    dialects — ``sqlite`` and ``postgresql`` — so the threading
    helper rejects any other value at the adapter boundary.
    """
    from cold_storage.modules.orchestration.application.production_calculation.errors import (
        InvalidProjectInputError,
    )

    if database_backend not in {"sqlite", "postgresql"}:
        raise InvalidProjectInputError(
            field_name="database_backend",
            reason=f"unsupported database_backend={database_backend!r}",
        )
