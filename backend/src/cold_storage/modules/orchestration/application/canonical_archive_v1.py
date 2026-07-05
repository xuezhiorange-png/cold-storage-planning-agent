"""Application-level canonical archive hash and payload assembly.

Mirrors the v1 algorithm from
``alembic/helpers/frozen_scheme_source_archive_v1.py``.  The two
implementations MUST produce identical hashes for identical payloads;
the application layer owns forward writes, the migration helper owns
backfill writes.  Both implement the same algorithms so the SHA-256 hex
is byte-stable across migration and runtime.

The helper module is intentionally duplicated here (rather than imported)
so the application layer stays free of out-of-tree dependencies, and so
this module can evolve to ``_v2`` without forcing a migration to do the
same.  A future migration that needs the updated algorithm must import
its own _v2 helper from alembic/helpers/.

Invariants:
    * Application layer must not import sqlalchemy.
    * Application layer must not import from
      ``cold_storage.modules.orchestration.infrastructure``.
    * If you change the algorithm below, create ``canonical_archive_v2``
      alongside — DO NOT modify this file in place.
    * ``source_slots`` MUST be an ordered sequence of ``(slot_name,
      slot_payload)`` tuples in ``SOURCE_SLOT_ORDER_V1`` order.  The
      archive hash binds to this order; reordering yields a different
      hash and the resolver treats it as a tamper.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from cold_storage.modules.orchestration.domain.errors import (
    SourceArchiveBuildError,
)

# Application-level schema constants.  These MUST match what migration
# 0034 enforces via CHECK constraint
# (ck_archive_schema_version_v1).
ARCHIVE_SCHEMA_VERSION_V1: str = "SchemeSourceArchiveV1"

# Allowed archive reasons.  Mirrors migration 0034 CHECK
# (ck_archive_reason_values).
REASON_COMPLETED: str = "completed"
REASON_PRE_DOWNGRADE: str = "pre_downgrade"
ALLOWED_REASONS: frozenset[str] = frozenset({REASON_COMPLETED, REASON_PRE_DOWNGRADE})

# The five source_slots in FIXED order.  Order is part of the algorithm
# contract.  The hash commits to this order; reordering the sequence
# is detectable as a tamper.
SOURCE_SLOT_ORDER_V1: tuple[str, ...] = (
    "zone",
    "cooling_load",
    "equipment",
    "power",
    "investment",
)


# ── Canonical hashing (mirrors alembic/helpers/frozen_scheme_source_archive_v1) ─


def _ensure_utc_aware_v1(dt: datetime) -> datetime:
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
    if isinstance(obj, float):
        raise ValueError(f"Binary float {obj!r} is not allowed in canonical archive_payload")
    if isinstance(obj, dict):
        for v in obj.values():
            _check_no_binary_float_v1(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _check_no_binary_float_v1(v)


def canonical_json_v1(obj: Any) -> str:
    """Return canonical JSON for deterministic archive_hash computation."""
    _check_no_binary_float_v1(obj)
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        default=_strict_json_default_v1,
    )


def _validate_ordered_source_slots_v1(
    source_slots: Sequence[tuple[str, Mapping[str, str]]],
) -> list[list[Any]]:
    """Validate the ordered source_slots sequence and return a JSON-safe form.

    Raises :class:`SourceArchiveBuildError` on:
        * a missing slot from ``SOURCE_SLOT_ORDER_V1``
        * an unexpected slot
        * a wrong slot order
        * a non-list input
        * a slot payload missing either ``calculation_id`` or ``result_hash``

    Returns the same data as ``[[name, payload_dict], ...]`` so the JSON
    encoder writes a list literal — order preserved, structure preserved.
    """
    if not isinstance(source_slots, Sequence) or isinstance(source_slots, (str, bytes)):
        raise SourceArchiveBuildError(
            f"source_slots must be ordered sequence of (name, payload) tuples, "
            f"got {type(source_slots).__name__}"
        )

    expected = list(SOURCE_SLOT_ORDER_V1)
    seen_names: list[str] = []
    prepared: list[list[Any]] = []
    for index, entry in enumerate(source_slots):
        if not isinstance(entry, (tuple, list)) or len(entry) != 2:
            raise SourceArchiveBuildError(
                f"source_slots[{index}] must be (name, payload) tuple, got {type(entry).__name__}"
            )
        name, payload = entry
        if not isinstance(name, str):
            raise SourceArchiveBuildError(
                f"source_slots[{index}] name must be str, got {type(name).__name__}"
            )
        if not isinstance(payload, Mapping):
            raise SourceArchiveBuildError(
                f"source_slots[{index}] payload must be Mapping, got {type(payload).__name__}"
            )
        if "calculation_id" not in payload or "result_hash" not in payload:
            raise SourceArchiveBuildError(
                f"source_slots[{index}]={name!r} must carry both "
                f"'calculation_id' and 'result_hash'; got keys {sorted(payload.keys())}"
            )
        seen_names.append(name)
        prepared.append([name, dict(payload)])

    expected_set = set(expected)
    seen_set = set(seen_names)
    missing = expected_set - seen_set
    extra = seen_set - expected_set
    msg_parts: list[str] = []
    if missing:
        msg_parts.append(f"missing={sorted(missing)}")
    if extra:
        msg_parts.append(f"extra={sorted(extra)}")
    if msg_parts:
        raise SourceArchiveBuildError(
            f"source_slots name set must match {expected} ({', '.join(msg_parts)})"
        )

    if seen_names != expected:
        # Order matters: name set is right but permutation is wrong.
        raise SourceArchiveBuildError(
            f"source_slots order must be exactly {expected}, got {seen_names}"
        )

    return prepared


def compute_archive_hash_v1(archive_payload: dict[str, Any]) -> str:
    """Return the SHA-256 hex digest of the canonical archive_payload.

    The archive_payload dict MUST be already in fixed shape
    (assembled by ``assemble_archive_payload`` below).

    Top-level dict keys are canonicalised by ``canonical_json_v1``
    (``sort_keys=True``); nested ordered sequences of
    ``(name, payload)`` pairs are preserved as lists in the JSON output.
    """
    if not isinstance(archive_payload, dict):
        raise SourceArchiveBuildError(
            f"archive_payload must be dict, got {type(archive_payload).__name__}"
        )
    canonical = canonical_json_v1(archive_payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_archive_hash(archive_payload: dict[str, Any]) -> str:
    """Public alias for compute_archive_hash_v1."""
    return compute_archive_hash_v1(archive_payload)


# ── Payload assembly ────────────────────────────────────────────────────────


def assemble_archive_payload(
    *,
    scheme_run_id: str,
    source_binding_id: str | None,
    source_contract_version: str,
    binding_schema_version: str | None,
    combined_source_hash: str | None,
    weight_set_revision_id: str | None,
    weight_set_content_hash: str | None,
    weight_set_generator_compatibility_version: str | None,
    execution_snapshot_id: str | None,
    coefficient_context_id: str | None,
    orchestration_identity_id: str | None,
    authoritative_attempt_id: str | None,
    orchestration_fingerprint: str | None,
    source_slots: Sequence[tuple[str, Mapping[str, str]]],
    project_id: str,
    project_version_id: str,
    generator_compatibility_version: str,
    captured_at: datetime,
) -> dict[str, Any]:
    """Assemble a fixed-shape archive_payload dict for SchemeSourceArchiveV1.

    ``source_slots`` MUST be an ordered sequence of ``(slot_name,
    slot_payload)`` tuples.  See
    :data:`SOURCE_SLOT_ORDER_V1` for the canonical order.  Hash
    computation commits to this order.
    """
    prepared_slots = _validate_ordered_source_slots_v1(source_slots)

    return {
        "schema": ARCHIVE_SCHEMA_VERSION_V1,
        "scheme_run_id": scheme_run_id,
        "source_binding_id": source_binding_id,
        "source_contract_version": source_contract_version,
        "binding_schema_version": binding_schema_version,
        "combined_source_hash": combined_source_hash,
        "weight_set_revision_id": weight_set_revision_id,
        "weight_set_content_hash": weight_set_content_hash,
        "weight_set_generator_compatibility_version": (weight_set_generator_compatibility_version),
        "execution_snapshot_id": execution_snapshot_id,
        "coefficient_context_id": coefficient_context_id,
        "orchestration_identity_id": orchestration_identity_id,
        "authoritative_attempt_id": authoritative_attempt_id,
        "orchestration_fingerprint": orchestration_fingerprint,
        "source_slots": prepared_slots,
        "project_id": project_id,
        "project_version_id": project_version_id,
        "generator_compatibility_version": generator_compatibility_version,
        "captured_at": _ensure_utc_aware_v1(captured_at).isoformat(),
    }


def slots_from_iterable(
    source_slots: Iterable[tuple[str, Mapping[str, str]]],
) -> list[tuple[str, dict[str, str]]]:
    """Materialise an iterable of (name, payload) into a list in iteration order.

    The resolver and test fixtures use this when reconstructing the
    ``source_slots`` view for the canonical_hash calculation in the read
    path.  Hash computation tolerates any iterable providing a stable
    iteration order; this helper makes the intent explicit and isolates
    the (rare) case where the caller passed a generator.
    """
    return [(name, dict(payload)) for name, payload in source_slots]
