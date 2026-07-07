"""Phase 4 Issue #35 Slice 2C — §11 fail-closed case #7 (Raw ORM fabrication, PG mirror).

This module is the dual-backend parity mirror of
``test_phase4_slice2c_raw_orm_fabrication_sqlite.py``.  It runs the
same §11 case #7 raw-ORM-bypass assertion against a real PostgreSQL
test database (PG service in the ``backend-postgresql`` CI job) to
prove the production ``SourceBindingVerifier`` rejects a row written
directly via the ORM on both backends.

Skipped locally when ``DATABASE_BACKEND != postgresql`` and no PG
fixture is available; the canonical CI is the
``backend-postgresql`` job at
``.github/workflows/ci.yml``.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

if os.environ.get("DATABASE_BACKEND") != "postgresql":
    pytest.skip(
        "PG Slice 2C raw-ORM-fabrication test requires DATABASE_BACKEND=postgresql",
        allow_module_level=True,
    )

from sqlalchemy import text

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
from cold_storage.modules.orchestration.infrastructure.repositories import (
    SqlAlchemyVerificationReadPort,
)
from cold_storage.modules.projects.infrastructure.orm import (
    Base,
    CalculationRunRecord,
)

# Mirrors of the golden constants used by the SQLite mirror.  The PG
# mirror does not import the SQLite-specific transactional_b_golden
# fixture (which carries SQLite-style session semantics) and instead
# defers the matching constants to the PG test fixtures / CI backend.
GOLDEN_PROJECT_ID = "golden-p-001"
GOLDEN_PROJECT_VERSION_ID = "golden-pv-001"
GOLDEN_REQUEST_ID = "golden-req-001"
GOLDEN_SNAPSHOT_ID = "golden-snap-001"
GOLDEN_COEFFICIENT_CONTEXT_ID = "golden-coeff-001"
GOLDEN_ORCHESTRATION_IDENTITY_ID = "golden-orch-001"
GOLDEN_ATTEMPT_ID = "golden-attempt-001"
GOLDEN_FINGERPRINT = "golden-fp-001"

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


def _bypassed_raw_orm_fabrication_run(
    session: Any,
    *,
    stage: str,
    fingerprint_value: str,
) -> str:
    """See SQLite mirror — same write strategy, isolated for PG."""
    run_id = f"pg-bypassed-{stage}-001"
    session.add(
        CalculationRunRecord(
            id=run_id,
            project_id=GOLDEN_PROJECT_ID,
            project_version_id=GOLDEN_PROJECT_VERSION_ID,
            calculator_name=_SLOT_CALCULATOR_NAMES[stage],
            calculator_version="1.0.0",
            input_snapshot={},
            result_snapshot={"bypass_value": "999"},
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
            input_hash="pg-e2e-bypass-input-hash",
            result_hash="not-a-real-hash",  # intentionally wrong → verifier mismatch
            provenance={"stage": stage},
            schema_version="1.0.0",
            orchestration_fingerprint=fingerprint_value,  # tampered!
        )
    )
    session.commit()
    return run_id


class TestRawOrmFabricationFailClosedPostgreSQL:
    """PG parity: §11 case #7 raw-ORM fabrication is fail-closed on PG too."""

    def test_bypassed_row_with_wrong_fingerprint_is_rejected_on_pg(
        self, pg_session_factory, pg_engine
    ) -> None:
        """PG parity for ``test_phase4_slice2c_raw_orm_fabrication_sqlite``.

        The PG mirror only verifies the binding commit path fails
        closed; it does not seed the golden project / version /
        snapshot / context / request / identity / attempt because
        doing so would couple the two test files to a shared
        fixture and lose the §11 case #7 "bypass the application
        service" semantics — the bypassed row is the point of the
        test, not the surrounding seed.
        """
        bypass_s = pg_session_factory()
        try:
            # Defensive schema bootstrap. The PG conftest typically
            # runs ``alembic upgrade head`` before the test session,
            # but the CI backend-postgresql job's ``pg_engine`` fixture
            # may already have the tables present; either way
            # ``metadata.create_all`` is a no-op.
            from cold_storage.modules.orchestration.infrastructure import (  # noqa: F401
                orm as _ensure_imported,  # noqa: F841 — import for table registration
            )
            from cold_storage.modules.schemes.infrastructure import (  # noqa: F401
                orm as _ensure_schemes_imported,  # noqa: F841 — import for table registration
            )

            Base.metadata.create_all(pg_engine)

            # Insert a minimal request / identity / attempt skeleton
            # so the verification port can locate the attempt
            # referenced by the bypassed CalculationRunRecord row.
            bypass_s.execute(
                text(
                    "INSERT INTO orchestration_run_attempts "
                    "(id, identity_id, attempt_number, status, started_at) "
                    "VALUES (:id, :identity_id, :attempt_number, :status, NOW())"
                ),
                {
                    "id": GOLDEN_ATTEMPT_ID,
                    "identity_id": GOLDEN_ORCHESTRATION_IDENTITY_ID,
                    "attempt_number": 1,
                    "status": "RUNNING",
                },
            )
            bypass_s.commit()

            stage = "zone"
            bypassed_run_id = _bypassed_raw_orm_fabrication_run(
                bypass_s,
                stage=stage,
                fingerprint_value="pg-hostile-tampered-fingerprint",
            )
        finally:
            bypass_s.close()

        read_port: VerificationReadPort = SqlAlchemyVerificationReadPort()
        verifier = SourceBindingVerifier(read_port=read_port)

        candidate = SourceBindingCandidate(
            identity_id=GOLDEN_ORCHESTRATION_IDENTITY_ID,
            attempt_id=GOLDEN_ATTEMPT_ID,
            fingerprint="pg-hostile-tampered-fingerprint",
            zone_calculation_id=bypassed_run_id,
            cooling_load_calculation_id="placeholder",  # noqa: F841
            equipment_calculation_id="placeholder",  # noqa: F841
            power_calculation_id="placeholder",  # noqa: F841
            investment_calculation_id="placeholder",  # noqa: F841
            per_calculation_result_hashes={stage: "deadbeef" * 8},  # noqa: F841
            combined_source_hash="deadbeef" * 8,  # noqa: F841
            schema_version="1.0.0",
        )

        verify_s = pg_session_factory()
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

        assert isinstance(exc_info.value, OrchestrationDomainError), (
            f"verifier raised {type(exc_info.value).__name__}; "
            "expected any OrchestrationDomainError subclass "
            "(case #7 raw-ORM fabrication detected on PG)"
        )


__all__ = ["TestRawOrmFabricationFailClosedPostgreSQL"]
