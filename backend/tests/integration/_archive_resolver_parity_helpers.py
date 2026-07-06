"""Shared scenario helpers for the P2 follow-up archive / resolver parity tests.

This module is **test-only**.  It provides the scenario-dict factories
and assertion helpers used by both:

  * tests/integration/test_historical_source_resolver_sqlite.py
  * tests/integration/test_historical_source_resolver_postgresql.py

to drive the 14 parity scenarios required by the P2-1 follow-up
review (and the P2-2 explicit tamper tests for
``weight_set_content_hash`` and ``binding_schema_version``).

The helper intentionally does NOT import any SQLAlchemy or
SQL dialect.  It only operates on the resolver's pure-data input
(``scheme_run_row`` mapping + ``archive_payload`` mapping).  The
caller is responsible for persisting the archive row through the
``ProductionSourceArchiveWritePort``/repository and supplying the
``Session`` to the resolver.

The canonical v1 archive shape constants
(``SCHEMA_VERSION_V1`` and the five-slot ordered tuple) are
re-exported from ``canonical_archive_v1`` so both the SQLite and
PostgreSQL tests see the same value.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from cold_storage.modules.orchestration.application.canonical_archive_v1 import (
    ARCHIVE_SCHEMA_VERSION_V1,
    SOURCE_SLOT_ORDER_V1,
    assemble_archive_payload,
    compute_archive_hash_v1,
)
from cold_storage.modules.orchestration.application.historical_source_resolver import (
    LegacySourceBundle,
    VerifiedArchiveSourceBundle,
    VerifiedOnlineSourceBundle,
)
from cold_storage.modules.orchestration.domain.errors import (
    SchemeRunHistoricalSourceTamperedError,
    SchemeRunHistoricalSourceUnavailableError,
    SchemeSourceArchiveIntegrityError,
    SchemeSourceArchiveUnsupportedSchemaError,
)

# Re-exported for the SQLite/PG test files so they don't have to
# know the canonical-archive module path twice.
SCHEMA_VERSION_V1: str = ARCHIVE_SCHEMA_VERSION_V1
EXPECTED_SLOT_ORDER_V1: tuple[str, ...] = SOURCE_SLOT_ORDER_V1

# ── canonical slot dicts ────────────────────────────────────────────────
# All five slots use the same default result_hash in the "happy" path so
# that the suite has a single source of truth.  Tests that need to tamper
# with a specific slot override ``slot_hashes``.

DEFAULT_SLOT_HASHES: dict[str, str] = {
    "zone": "ZH",
    "cooling_load": "CH",
    "equipment": "EH",
    "power": "PH",
    "investment": "IH",
}

DEFAULT_CALC_IDS: dict[str, str] = {
    "zone": "zcalc",
    "cooling_load": "ccalc",
    "equipment": "ecalc",
    "power": "pcalc",
    "investment": "icalc",
}

# Fixed captured_at so the assembly is fully deterministic in tests.
FIXED_CAPTURED_AT: datetime = datetime(2026, 7, 4, 0, 0, 0, tzinfo=UTC)


def make_ordered_slots(
    slot_hashes: Mapping[str, str] | None = None,
    calc_ids: Mapping[str, str] | None = None,
) -> list[tuple[str, dict[str, str]]]:
    """Return the v1 ordered source_slots sequence.

    Returns a list of ``(slot_name, {calculation_id, result_hash})`` tuples in
    ``SOURCE_SLOT_ORDER_V1`` order.  ``slot_hashes`` and ``calc_ids`` are
    merged with the defaults — pass a partial mapping to override.
    """
    hashes = {**DEFAULT_SLOT_HASHES, **(slot_hashes or {})}
    cids = {**DEFAULT_CALC_IDS, **(calc_ids or {})}
    return [
        (name, {"calculation_id": cids[name], "result_hash": hashes[name]})
        for name in EXPECTED_SLOT_ORDER_V1
    ]


def make_assembled_payload(
    *,
    scheme_run_id: str,
    source_binding_id: str = "binding-1",
    combined_source_hash: str = "combined-h",
    weight_set_content_hash: str = "weight-h",
    binding_schema_version: str = "BSV-1.0",
    slot_hashes: Mapping[str, str] | None = None,
    project_id: str = "proj-1",
    project_version_id: str = "pver-1",
) -> dict[str, Any]:
    """Build a fresh, fully-canonical archive payload via the assembler.

    Hashing is by the application helper so the test is not coupled to
    the migration's frozen helper.  Use ``assemble_with_captured_at`` if
    you need to control the captured_at timestamp.
    """
    slots = make_ordered_slots(slot_hashes=slot_hashes)
    return assemble_archive_payload(
        scheme_run_id=scheme_run_id,
        source_binding_id=source_binding_id,
        source_contract_version="SVC-1.0",
        binding_schema_version=binding_schema_version,
        combined_source_hash=combined_source_hash,
        weight_set_revision_id="rev-1",
        weight_set_content_hash=weight_set_content_hash,
        weight_set_generator_compatibility_version="WG-1.0",
        execution_snapshot_id="snap-1",
        coefficient_context_id="ctx-1",
        orchestration_identity_id="ident-1",
        authoritative_attempt_id="att-1",
        orchestration_fingerprint="fp-1",
        source_slots=slots,
        project_id=project_id,
        project_version_id=project_version_id,
        generator_compatibility_version="GCV-1.0",
        captured_at=FIXED_CAPTURED_AT,
    )


def compute_hash_for_payload(payload: Mapping[str, Any]) -> str:
    """Compute archive_hash = sha256(canonical_json_v1(payload)).

    Thin wrapper that mirrors what the production builder does, kept
    here so test files don't have to import the canonical helper twice.
    """
    return compute_archive_hash_v1(payload)


def make_scheme_run_row(
    *,
    scheme_run_id: str,
    source_mode: str = "production",
    combined_source_hash: str = "combined-h",
    weight_set_content_hash: str = "weight-h",
    binding_schema_version: str = "BSV-1.0",
    slot_hashes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build the scheme_run_row mapping fed to the resolver.

    All five ``*_result_hash`` columns are populated from ``slot_hashes``
    (merged with defaults).  Pass ``slot_hashes={"zone": "WRONG"}`` etc.
    to simulate a per-slot tamper without touching the archive row.
    """
    hashes = {**DEFAULT_SLOT_HASHES, **(slot_hashes or {})}
    return {
        "id": scheme_run_id,
        "source_mode": source_mode,
        "combined_source_hash": combined_source_hash,
        "weight_set_content_hash": weight_set_content_hash,
        "binding_schema_version": binding_schema_version,
        "zone_result_hash": hashes["zone"],
        "cooling_load_result_hash": hashes["cooling_load"],
        "equipment_result_hash": hashes["equipment"],
        "power_result_hash": hashes["power"],
        "investment_result_hash": hashes["investment"],
    }


def make_online_source_lookup(
    *,
    scheme_run_id: str,
    source_binding_id: str = "binding-online",
    combined_source_hash: str = "combined-online",
) -> Any:
    """Build a fake ``OnlineSchemeRunSourceLookupPort`` that returns a
    single record.  Returned callable signature matches the
    ``OnlineSchemeRunSourceLookupPort.find_online_scheme_run_sources``
    Protocol.
    """

    class _FakeLookup:
        def find_online_scheme_run_sources(self, _session: Any, sid: str) -> dict[str, Any] | None:
            if sid != scheme_run_id:
                return None
            return {
                "source_binding_id": source_binding_id,
                "combined_source_hash": combined_source_hash,
                "source_slots": {
                    name: {
                        "calculation_id": DEFAULT_CALC_IDS[name],
                        "result_hash": DEFAULT_SLOT_HASHES[name],
                    }
                    for name in EXPECTED_SLOT_ORDER_V1
                },
            }

    return _FakeLookup()


# ── PG-specific raw-SQL planting helpers ───────────────────────────────
# Used only by the PostgreSQL parity tests.  On PG, the
# ``production_source_archives`` table has 7 foreign keys
# (scheme_run_id, source_binding_id, weight_set_revision_id,
# execution_snapshot_id, coefficient_context_id,
# orchestration_identity_id, authoritative_attempt_id).  To insert
# an archive row without planting the full SourceBinding chain we
# use ``SET session_replication_role = 'replica'`` to disable
# triggers + FK enforcement for the planting transaction only.
# This is the same pattern used by
# ``test_migration_0034_downgrade_guard_hex_postgresql.py``.


def plant_minimal_pg_archive_row(
    engine: Any,
    *,
    scheme_run_id: str,
    payload: dict[str, Any],
    archive_hash: str,
    archive_schema_version: str = ARCHIVE_SCHEMA_VERSION_V1,
) -> None:
    """Plant an archive row in PG by temporarily disabling FK triggers.

    The row's hash + payload come from the application helper, so the
    resolver can recompute + read it back.  This is a **test-only**
    planting helper; it does not exist in production code.
    """
    from sqlalchemy import text as _sql_text

    with engine.begin() as conn:
        conn.execute(_sql_text("SET session_replication_role = 'replica'"))
        conn.execute(
            _sql_text(
                "INSERT INTO production_source_archives ("
                "id, scheme_run_id, source_binding_id, "
                "source_contract_version, archive_schema_version, "
                "archive_payload, archive_hash, "
                "combined_source_hash, weight_set_revision_id, "
                "weight_set_content_hash, binding_schema_version, "
                "execution_snapshot_id, coefficient_context_id, "
                "orchestration_identity_id, authoritative_attempt_id, "
                "orchestration_fingerprint, created_at, "
                "created_by, reason) VALUES ("
                ":aid, :sid, :bid, 'SVC-1.0', :asv, "
                "CAST(:payload AS jsonb), :ahash, :csh, "
                ":wsr, :wch, :bsv, :esi, :cci, :oii, :aai, :fp, :cat, "
                "'parity-test-seed', 'completed')"
            ),
            {
                "aid": str(uuid.uuid4()),
                "sid": scheme_run_id,
                "bid": payload.get("source_binding_id") or "binding-1",
                "asv": archive_schema_version,
                "payload": json.dumps(payload),
                "ahash": archive_hash,
                "csh": payload["combined_source_hash"],
                "wsr": payload.get("weight_set_revision_id") or "rev-1",
                "wch": payload["weight_set_content_hash"],
                "bsv": payload["binding_schema_version"],
                "esi": payload.get("execution_snapshot_id") or "snap-1",
                "cci": payload.get("coefficient_context_id") or "ctx-1",
                "oii": payload.get("orchestration_identity_id") or "ident-1",
                "aai": payload.get("authoritative_attempt_id") or "att-1",
                "fp": payload.get("orchestration_fingerprint") or "fp-1",
                "cat": datetime.now(UTC),
            },
        )
        conn.execute(_sql_text("SET session_replication_role = 'origin'"))


# ── assertion helpers ───────────────────────────────────────────────────


def assert_legacy_bundle(bundle: Any) -> None:
    assert isinstance(bundle, LegacySourceBundle), (
        f"expected LegacySourceBundle, got {type(bundle).__name__}"
    )


def assert_verified_online_bundle(
    bundle: Any,
    *,
    expected_source_binding_id: str,
    expected_combined_source_hash: str,
) -> None:
    assert isinstance(bundle, VerifiedOnlineSourceBundle), (
        f"expected VerifiedOnlineSourceBundle, got {type(bundle).__name__}"
    )
    assert bundle.source_binding_id == expected_source_binding_id
    assert bundle.combined_source_hash == expected_combined_source_hash


def assert_verified_archive_bundle(
    bundle: Any,
    *,
    expected_combined_source_hash: str,
) -> None:
    assert isinstance(bundle, VerifiedArchiveSourceBundle), (
        f"expected VerifiedArchiveSourceBundle, got {type(bundle).__name__}"
    )
    assert bundle.combined_source_hash == expected_combined_source_hash


def assert_unavailable(exc_info: Any) -> None:
    """Assert that the captured exception is a Unavailable error."""
    assert exc_info.type is SchemeRunHistoricalSourceUnavailableError, (
        f"expected SchemeRunHistoricalSourceUnavailableError, got {exc_info.type.__name__}"
    )


def assert_unsupported_schema(exc_info: Any) -> None:
    assert exc_info.type is SchemeSourceArchiveUnsupportedSchemaError, (
        f"expected SchemeSourceArchiveUnsupportedSchemaError, got {exc_info.type.__name__}"
    )


def assert_payload_integrity(exc_info: Any) -> None:
    assert exc_info.type is SchemeSourceArchiveIntegrityError, (
        f"expected SchemeSourceArchiveIntegrityError, got {exc_info.type.__name__}"
    )


def assert_tampered_field(exc_info: Any, *, expected_field: str) -> None:
    """Assert a TamperedError with the expected ``field`` attribute.

    This is the assertion used by the P2-2 follow-up tests for
    ``weight_set_content_hash`` and ``binding_schema_version``.
    """
    assert exc_info.type is SchemeRunHistoricalSourceTamperedError, (
        f"expected SchemeRunHistoricalSourceTamperedError, got {exc_info.type.__name__}"
    )
    actual = exc_info.value.field
    assert actual == expected_field, f"expected tampered field={expected_field!r}, got {actual!r}"


# Module-level constants are filled in below so the imports above don't
# shadow the local ``DEFAULT_SLOT_HASHES`` etc.
__all__ = [
    "ARCHIVE_SCHEMA_VERSION_V1",
    "DEFAULT_CALC_IDS",
    "DEFAULT_SLOT_HASHES",
    "EXPECTED_SLOT_ORDER_V1",
    "FIXED_CAPTURED_AT",
    "SCHEMA_VERSION_V1",
    "SOURCE_SLOT_ORDER_V1",
    "assert_legacy_bundle",
    "assert_payload_integrity",
    "assert_tampered_field",
    "assert_unavailable",
    "assert_unsupported_schema",
    "assert_verified_archive_bundle",
    "assert_verified_online_bundle",
    "compute_hash_for_payload",
    "make_assembled_payload",
    "make_online_source_lookup",
    "make_ordered_slots",
    "make_scheme_run_row",
    "plant_minimal_pg_archive_row",
]
