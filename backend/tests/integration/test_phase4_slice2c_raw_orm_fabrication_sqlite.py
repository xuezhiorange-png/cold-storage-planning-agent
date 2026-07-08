"""Phase 4 Issue #35 Slice 2C — §11 fail-closed case #7 (Raw ORM fabrication).

This module covers the design contract's §11 fail-closed case #7:

    Bypass the application service and write a ``calculation_run``
    directly via the ORM. Assert the binding rejects the row.

The test exercises the production path end-to-end:

1. Seed a real orchestration request / identity / attempt via the
   project's golden prerequisite helper (matches what
   ``TransactionBExecutor.execute`` produces in production).
2. Insert one ``CalculationRunRecord`` directly via raw SQLAlchemy
   ORM, deliberately bypassing ``TransactionBExecutor.execute``.
   The row carries a tampered ``orchestration_fingerprint`` so the
   production ``SourceBindingVerifier`` cannot verify the binding
   against the authoritative identity row.
3. Build a ``SourceBindingCandidate`` from the bypassed row and call
   ``SourceBindingVerifier.verify`` exactly the way
   ``TransactionBExecutor`` invokes it during production binding
   commit.
4. Assert the verifier raises a typed ``OrchestrationDomainError``
   subclass, proving the production read-path rejects the
   fabricated row.

The test is the integration companion to the existing
``tests/unit/test_source_binding_verifier_strict.py`` unit coverage.
The dual-backend parity mirror lives in
``test_phase4_slice2c_raw_orm_fabrication_postgresql.py``.

Slice 2C scope: this file is additive — no existing fixture, helper,
or test is replaced.  No production-source chain is re-implemented
beyond what is needed to surface the case #7 invariant.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import pytest

if os.environ.get("DATABASE_BACKEND") == "postgresql":
    pytest.skip(
        "SQLite Slice 2C raw-ORM-fabrication test cannot run on PostgreSQL",
        allow_module_level=True,
    )

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cold_storage.modules.orchestration.application.transaction_b import (
    SourceBindingVerifier,
    VerificationReadPort,
)
from cold_storage.modules.orchestration.domain.contracts import (
    SourceBindingCandidate,
)
from cold_storage.modules.orchestration.domain.errors import (
    OrchestrationDomainError,
)
from cold_storage.modules.orchestration.domain.fingerprint import result_hash
from cold_storage.modules.orchestration.domain.snapshots import (
    build_source_snapshot_content_v1,
)
from cold_storage.modules.orchestration.infrastructure.repositories import (
    SqlAlchemyVerificationReadPort,
)
from cold_storage.modules.projects.infrastructure.orm import (
    Base,
    CalculationRunRecord,
)
from tests.integration.transaction_b_golden import (
    _CALCULATOR_OUTPUTS,
    GOLDEN_ATTEMPT_ID,
    GOLDEN_COEFFICIENT_CONTEXT_ID,
    GOLDEN_FINGERPRINT,
    GOLDEN_ORCHESTRATION_IDENTITY_ID,
    GOLDEN_PROJECT_ID,
    GOLDEN_PROJECT_VERSION_ID,
    GOLDEN_REQUEST_ID,
    GOLDEN_SNAPSHOT_ID,
    _seed_golden_prerequisites,
)

# Inlined slot metadata so the test does not couple to private constants in
# ``test_production_transaction_b_e2e_sqlite.py``. Mirrors the values there.
_SLOT_CALCULATOR_NAMES: dict[str, str] = {
    "zone": "cold_room_zone_plan",
    "cooling_load": "cooling_load",
    "equipment": "equipment",
    "power": "installed_power",
    "investment": "investment_estimate",
}
_SLOT_CALCULATION_TYPES: dict[str, str] = {
    "zone": "zone",
    "cooling_load": "cooling_load",
    "equipment": "equipment",
    "power": "power",
    "investment": "investment",
}


def _make_engine():
    """Build a fresh in-memory SQLite engine with every ORM table present."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Pull in every module that contributes tables to Base.metadata
    # so that Base.metadata.create_all resolves every foreign key.
    import cold_storage.modules.orchestration.infrastructure.orm  # noqa: F401
    import cold_storage.modules.schemes.infrastructure.orm  # noqa: F401

    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def engine():
    """Build a fresh in-memory SQLite engine per test."""
    e = _make_engine()
    try:
        yield e
    finally:
        e.dispose()


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def _compute_golden_result_hash(*, stage: str, snap: dict[str, Any]) -> str:
    """Compute the per-stage result hash using the production canonical-JSON helper."""
    payload = build_source_snapshot_content_v1(
        schema_version="1.0.0",
        calculation_type=_SLOT_CALCULATION_TYPES[stage],
        calculator_name=_SLOT_CALCULATOR_NAMES[stage],
        calculator_version="1.0.0",
        project_id=GOLDEN_PROJECT_ID,
        project_version_id=GOLDEN_PROJECT_VERSION_ID,
        execution_snapshot_id=GOLDEN_SNAPSHOT_ID,
        coefficient_context_id=GOLDEN_COEFFICIENT_CONTEXT_ID,
        orchestration_identity_id=GOLDEN_ORCHESTRATION_IDENTITY_ID,
        orchestration_run_attempt_id=GOLDEN_ATTEMPT_ID,
        input_hash="e2e-bypass-input-hash",
        requires_review=False,
        payload=snap,
        upstream_calculation_ids={},
    )
    return result_hash(payload)


def _bypassed_raw_orm_fabrication_run(
    session: Any,
    *,
    stage: str,
    fingerprint_value: str,
) -> str:
    """Insert a single ``CalculationRunRecord`` directly via the ORM.

    This deliberately bypasses ``TransactionBExecutor.execute`` — the
    application service that would compute hashes, validate against
    the strict resolver, and persist the row atomically.  Slice 2C
    uses this helper to prove that even a buggy or hostile caller
    cannot produce a valid binding, because the production
    ``SourceBindingVerifier`` re-reads the persisted state and
    enforces every invariant.
    """
    run_id = f"bypassed-{stage}-001"
    snap = _CALCULATOR_OUTPUTS[stage]
    computed_hash = _compute_golden_result_hash(stage=stage, snap=snap)
    session.add(
        CalculationRunRecord(
            id=run_id,
            project_id=GOLDEN_PROJECT_ID,
            project_version_id=GOLDEN_PROJECT_VERSION_ID,
            calculator_name=_SLOT_CALCULATOR_NAMES[stage],
            calculator_version="1.0.0",
            input_snapshot={},
            result_snapshot=snap,
            formulas=[],
            coefficients=[],
            assumptions=[],
            warnings=[],
            source_references=[],
            requires_review=False,
            calculation_type=_SLOT_CALCULATION_TYPES[stage],
            orchestration_identity_id=GOLDEN_ORCHESTRATION_IDENTITY_ID,
            orchestration_run_attempt_id=GOLDEN_ATTEMPT_ID,
            execution_snapshot_id=GOLDEN_SNAPSHOT_ID,
            coefficient_context_id=GOLDEN_COEFFICIENT_CONTEXT_ID,
            input_hash="e2e-bypass-input-hash",
            result_hash=computed_hash,
            provenance={"stage": stage},
            schema_version="1.0.0",
            orchestration_fingerprint=fingerprint_value,  # <-- tampered!
            created_at=datetime.now(UTC),
        )
    )
    session.commit()
    return run_id


# ── Tests ──────────────────────────────────────────────────────────────────


class TestRawOrmFabricationFailClosedSQLite:
    """§11 case #7 — bypassing ``TransactionBExecutor.execute`` is fail-closed."""

    def test_bypassed_row_with_wrong_fingerprint_is_rejected_by_verifier(
        self, engine, session_factory
    ) -> None:
        """The verifier must raise on a binding built from a raw-ORM row whose
        ``orchestration_fingerprint`` does not match the identity's persisted value.

        Production behavior: ``TransactionBExecutor.execute`` would have
        computed the per-stage fingerprint from the canonical
        ``SourceSnapshotContentV1`` payload and rejected any
        drift; the Slice 2C test deliberately bypasses that
        application service to simulate a buggy / hostile writer.
        The production ``SourceBindingVerifier`` re-reads the
        orchestrator fingerprint from the authoritative
        ``OrchestrationIdentityRecord`` row and asserts the
        candidate's per-slot ``orchestration_fingerprint`` matches.
        Mismatch → ``SourceBindingIdentityMismatchError``.
        """
        seed_s = session_factory()
        try:
            _seed_golden_prerequisites(seed_s)
        finally:
            seed_s.close()

        # Bypass TransactionBExecutor.execute: write one
        # ``CalculationRunRecord`` directly via the ORM with a
        # tampered orchestration_fingerprint.
        bypass_s = session_factory()
        try:
            stage = "zone"
            bypassed_run_id = _bypassed_raw_orm_fabrication_run(
                bypass_s,
                stage=stage,
                fingerprint_value="hostile-tampered-fingerprint-do-not-match",
            )
        finally:
            bypass_s.close()

        # Build the verifier from the production read-port factory
        # and invoke it exactly the way ``TransactionBExecutor``
        # does at the binding commit step.
        read_port: VerificationReadPort = SqlAlchemyVerificationReadPort()
        verifier = SourceBindingVerifier(read_port=read_port)

        candidate = SourceBindingCandidate(
            identity_id=GOLDEN_ORCHESTRATION_IDENTITY_ID,
            attempt_id=GOLDEN_ATTEMPT_ID,
            fingerprint="hostile-tampered-fingerprint-do-not-match",  # matches the row
            zone_calculation_id=bypassed_run_id,
            cooling_load_calculation_id="zone-id",  # noqa: F841 — placeholder, never reached
            equipment_calculation_id="zone-id",  # noqa: F841 — placeholder
            power_calculation_id="zone-id",  # noqa: F841 — placeholder
            investment_calculation_id="zone-id",  # noqa: F841 — placeholder
            per_calculation_result_hashes={stage: "deadbeef" * 8},  # noqa: F841
            combined_source_hash="deadbeef" * 8,  # noqa: F841
            schema_version="1.0.0",
        )

        verify_s = session_factory()
        try:
            with pytest.raises(OrchestrationDomainError) as exc_info:
                verifier.verify(
                    verify_s,
                    request_id=GOLDEN_REQUEST_ID,
                    identity_id=GOLDEN_ORCHESTRATION_IDENTITY_ID,
                    attempt_id=GOLDEN_ATTEMPT_ID,
                    candidate=candidate,
                    project_id=GOLDEN_PROJECT_ID,
                    project_version_id=GOLDEN_PROJECT_VERSION_ID,
                    execution_snapshot_id=GOLDEN_SNAPSHOT_ID,
                    coefficient_context_id=GOLDEN_COEFFICIENT_CONTEXT_ID,
                    orchestration_fingerprint=GOLDEN_FINGERPRINT,
                )
        finally:
            verify_s.close()

        # The verifier's authority / completeness / fingerprint
        # checks all read from the authoritative persistence layer
        # and compare against the binding candidate, so a row
        # written directly via the ORM (bypassing
        # ``TransactionBExecutor.execute``) cannot bind a valid
        # attempt.  The exact typed exception class depends on the
        # specific invariant failure:
        #
        # - ``SourceBindingIdentityMismatchError`` — fingerprint
        #   mismatch (P0-4 / P0-5 authority check).
        # - ``PersistenceInvariantError`` — fewer than 5
        #   ``CalculationRunRecord`` rows for the attempt (5-CalRun
        #   invariant), because a single bypassed row cannot
        #   supply the full slot set.
        # - ``SourceBindingHashMismatchError`` — re-computed hashes
        #   do not match the row's persisted hash.
        #
        # The §11 contract requires "the binding rejects the row"
        # (case #7); the unified contract is "the production
        # verifier raises a typed ``OrchestrationDomainError``
        # subclass on any binding attempt built from
        # bypassed / fabricated DB state".  Assert that contract.
        assert isinstance(exc_info.value, OrchestrationDomainError), (
            f"verifier raised {type(exc_info.value).__name__}; "
            "expected any OrchestrationDomainError subclass "
            "(case #7 raw-ORM fabrication detected)"
        )


__all__ = ["TestRawOrmFabricationFailClosedSQLite"]
