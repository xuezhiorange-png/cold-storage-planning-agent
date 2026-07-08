"""Test-side pre-existing-context seed helpers for A1 live-database tests.

Scope and authority
===================

This module is **strictly test-side** and exists solely to support the
Path A / Task 11B Implementation Slice A1 live-database happy-path
tests in ``backend/tests/evaluation/test_path_a_adapter.py``.  It is
**not** part of the evaluation production surface.

**Authority boundary (A1 follow-up slice):**

* This file is the **only** location in ``backend/tests/evaluation/``
  that is allowed to write pre-existing production rows for the A1
  live-database happy-path tests, per the narrow architecture-test
  carve-out documented in
  ``backend/tests/architecture/test_phase1_identity_foundation_boundary.py``.

* It is **not** imported by production code, the evaluation adapter, or
  the evaluation runner.  The architecture boundary tests enforce this
  import-direction discipline (raw-ORM fabrication ban).

* It does **not** implement a full pipeline.  It only seeds the minimum
  pre-existing production context required for the A1-2a adapter to
  call ``ProductionSchemeService.generate_production_scheme_run``
  end-to-end on a real SQLite database.

* It does **not** restore or substitute for
  ``backend/src/cold_storage/evaluation/production_seeding.py`` — that
  file must remain absent (per A1 design contract §6 explicit
  exclusions).

Helper naming
=============

Every helper in this module is named with a leading underscore and the
``seed_a1_`` prefix to make the test-only intent unambiguous.

Helpers
=======

* :func:`engine` (pytest fixture) — temp SQLite file with Alembic head
  schema.
* :func:`session_factory` (pytest fixture) — ``sessionmaker`` bound to
  the engine.
* :func:`seed_a1_all_prereqs` — public entry point that seeds the full
  pre-existing context chain.

The seed chain (in dependency order):

1. ``ProjectRecord`` + ``ProjectVersionRecord``
2. ``ProjectVersionExecutionSnapshotRecord``
3. ``CoefficientContextRecord``
4. ``OrchestrationIdentityRecord`` (with status=ACTIVE)
5. ``OrchestrationRunAttemptRecord`` (with status=COMPLETED)
6. 5 × ``CalculationRunRecord`` (zone / cooling_load / equipment /
   power / investment)
7. ``SourceBindingRecord`` (with per-calc hashes + combined source
   hash matching production ``SourceBindingVerifier``)
8. ``SchemeWeightSetRecord`` (status=approved) + draft
   ``SchemeWeightSetRevisionRecord`` (then UPDATE to approved because
   the production INSERT trigger blocks direct approved status).

See :mod:`backend.tests.integration.test_production_scheme_sqlite` for
the integration-test sibling that this helper was distilled from.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Skip the entire helper module when running under PostgreSQL CI job —
# the engine fixture only provisions SQLite, so importing / defining
# fixtures on a postgresql CI job would otherwise spin up an unused
# SQLite file. The live PostgreSQL test would need a separate fixture
# (not in scope for A1 follow-up slice).
if os.environ.get("DATABASE_BACKEND") == "postgresql":
    pytest.skip(
        "A1 live-database seed helpers only provision SQLite; "
        "the live PostgreSQL test is out of scope for this slice.",
        allow_module_level=True,
    )

BACKEND_DIR = Path(__file__).resolve().parents[2]

# ── Deterministic IDs (A1 test-only) ───────────────────────────────────────

PROJECT_ID = "a1-test-p-001"
VERSION_ID = "a1-test-v-001"
EXEC_SNAPSHOT_ID = "a1-test-exec-001"
COEFF_CONTEXT_ID = "a1-test-cc-001"
IDENTITY_ID = "a1-test-id-001"
ATTEMPT_ID = "a1-test-attempt-001"

ZONE_RUN_ID = "a1-test-run-zone-001"
COOL_RUN_ID = "a1-test-run-cool-001"
EQUIP_RUN_ID = "a1-test-run-equip-001"
POWER_RUN_ID = "a1-test-run-power-001"
INVEST_RUN_ID = "a1-test-run-invest-001"

SOURCE_BINDING_ID = "a1-test-binding-001"
WEIGHT_SET_ID = "a1-test-ws-001"
WEIGHT_REVISION_ID = "a1-test-wrev-001"

FINGERPRINT = "a1-test-fingerprint-001"

# ── Stage result snapshots (A1 test-only, minimum-viable) ─────────────────
#
# These snapshots match the shape that the production
# ``SourceBindingVerifier`` and downstream ``SchemeRun`` post-conditions
# expect, distilled from the integration test
# ``tests/integration/test_production_scheme_sqlite.py``.  All numeric
# values are JSON-safe strings (per the domain
# ``canonical_json_bytes`` rule that rejects binary ``float``).

ZONE_RESULT_SNAPSHOT: dict[str, Any] = {
    "daily_inbound_mass_kg": 10000,
    "design_daily_mass_kg": 10000,
    "total_required_area_m2": "200.0",
    "total_area_m2": "200.0",
    "planning_parameters": {
        "pallet_weight_kg": 500,
        "working_hours_per_day": 8,
    },
    "zones": [
        {
            "zone_code": "Z1",
            "zone_name": "a1-zone-001",
            "daily_throughput_kg_day": 10000,
            "required_area_m2": "200.0",
            "design_storage_mass_kg": "15000.0",
            "position_count": 30,
            "temperature_band": "0~4C",
            "function": "storage",
            "process_compatibility": "blueberry",
            "hygiene_zone": "food_grade",
        }
    ],
}

COOLING_RESULT_SNAPSHOT: dict[str, Any] = {
    "total_cooling_load_kw": "25.0",
    "safety_margin_load_kw": "2.5",
    "envelope_heat_transfer_load_kw": "3.0",
    "product_sensible_heat_load_kw": "18.0",
    "packaging_load_kw": "1.0",
    "infiltration_load_kw": "3.0",
    "personnel_load_kw": "0.5",
    "lighting_load_kw": "0.3",
    "evaporator_fan_load_kw": "1.2",
    "defrost_additional_load_kw": "0.4",
    "other_configuration_load_kw": "0.1",
    "latent_load_kw": "0.0",
}

EQUIPMENT_RESULT_SNAPSHOT: dict[str, Any] = {
    "evaporator_total_cooling_capacity_kw": "30.0",
    "evaporator_quantity": 2,
    "single_evaporator_capacity_kw": "15.0",
    "compressor_operating_capacity_kw": "22.0",
    "compressor_installed_capacity_kw": "25.0",
    "standby_capacity_kw": "8.0",
    "condenser_heat_rejection_capacity_kw": "30.0",
    "evaporation_temperature_c": "-5.0",
    "condensing_temperature_c": "40.0",
    "defrost_method": "electric",
    "review_requirement": "",
}

POWER_RESULT_SNAPSHOT: dict[str, Any] = {
    "total_installed_power_kw_e": "200.0",
    "total_estimated_demand_kw": "160.0",
    "equipment_rows": [],
    "summary_rows": [],
    "items": [],
    "assumptions": [],
}

INVESTMENT_RESULT_SNAPSHOT: dict[str, Any] = {
    "total_investment_cny": "6000000.0",
    "items": [
        {"item_name": "building", "amount_cny": "3000000.0"},
        {"item_name": "equipment", "amount_cny": "2000000.0"},
        {"item_name": "other", "amount_cny": "1000000.0"},
    ],
}

# ── Weight revision content (A1 test-only) ────────────────────────────────

_WEIGHT_CRITERIA_RAW: list[dict[str, Any]] = [
    {
        "criterion_code": "total_area_m2",
        "weight": "0.20",
        "direction": "lower_is_better",
        "normalization_method": "min_max",
        "hard_constraint": False,
    },
    {
        "criterion_code": "investment_cny",
        "weight": "0.30",
        "direction": "lower_is_better",
        "normalization_method": "min_max",
        "hard_constraint": False,
    },
    {
        "criterion_code": "total_position_count",
        "weight": "0.15",
        "direction": "higher_is_better",
        "normalization_method": "min_max",
        "hard_constraint": False,
    },
    {
        "criterion_code": "room_module_count",
        "weight": "0.10",
        "direction": "lower_is_better",
        "normalization_method": "min_max",
        "hard_constraint": False,
    },
    {
        "criterion_code": "door_count",
        "weight": "0.05",
        "direction": "lower_is_better",
        "normalization_method": "min_max",
        "hard_constraint": False,
    },
    {
        "criterion_code": "partition_length_proxy_m",
        "weight": "0.05",
        "direction": "lower_is_better",
        "normalization_method": "min_max",
        "hard_constraint": False,
    },
    {
        "criterion_code": "installed_power_kw_e",
        "weight": "0.15",
        "direction": "lower_is_better",
        "normalization_method": "min_max",
        "hard_constraint": False,
    },
]

WEIGHT_REVISION_CONTENT: dict[str, Any] = {"criteria": _WEIGHT_CRITERIA_RAW}

# ── Calculator name / type maps (A1 test-only) ────────────────────────────

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

_SLOT_STAGE_ORDER: tuple[str, ...] = (
    "zone",
    "cooling_load",
    "equipment",
    "power",
    "investment",
)

_SLOT_UPSTREAM_IDS: dict[str, dict[str, str]] = {
    "zone": {},
    "cooling_load": {"zone": ZONE_RUN_ID},
    "equipment": {"cooling_load": COOL_RUN_ID},
    "power": {"equipment": EQUIP_RUN_ID},
    "investment": {"zone": ZONE_RUN_ID, "power": POWER_RUN_ID},
}

_SLOT_RESULTS: dict[str, dict[str, Any]] = {
    "zone": ZONE_RESULT_SNAPSHOT,
    "cooling_load": COOLING_RESULT_SNAPSHOT,
    "equipment": EQUIPMENT_RESULT_SNAPSHOT,
    "power": POWER_RESULT_SNAPSHOT,
    "investment": INVESTMENT_RESULT_SNAPSHOT,
}


# ── Canonical hash helpers (test-only) ────────────────────────────────────


def _compute_domain_hash(
    *, stage: str, result_snapshot: dict[str, Any], run_id: str
) -> str:
    """Compute the production domain-layer canonical hash for a stage.

    Uses the same ``build_source_snapshot_content_v1`` builder that the
    production ``SourceBindingVerifier`` and Transaction B executor
    use, ensuring identical SHA-256 hashes.

    The fields populated here (schema_version, project_id, etc.) must
    match the values used when the production verifier recomputes the
    hash in ``verify_source_binding``. The A1 test pre-seeds all of
    them on the ``CalculationRunRecord`` row; the verifier reads them
    back via the same read port.
    """
    from cold_storage.modules.orchestration.domain.fingerprint import (
        result_hash,
    )
    from cold_storage.modules.orchestration.domain.snapshots import (
        build_source_snapshot_content_v1,
    )

    content = build_source_snapshot_content_v1(
        schema_version="1.0.0",
        calculation_type=_SLOT_CALCULATION_TYPES[stage],
        calculator_name=_SLOT_CALCULATOR_NAMES[stage],
        calculator_version="1.0.0",
        project_id=PROJECT_ID,
        project_version_id=VERSION_ID,
        execution_snapshot_id=EXEC_SNAPSHOT_ID,
        coefficient_context_id=COEFF_CONTEXT_ID,
        orchestration_identity_id=IDENTITY_ID,
        orchestration_run_attempt_id=ATTEMPT_ID,
        input_hash="a1-input-hash-001",
        requires_review=False,
        payload=result_snapshot,
        upstream_calculation_ids=_SLOT_UPSTREAM_IDS.get(stage, {}),
    )
    return result_hash(content)


def _compute_weight_content_hash(content: dict[str, Any]) -> str:
    """Compute the canonical SHA-256 of weight-set revision content."""
    from cold_storage.modules.orchestration.domain.fingerprint import (
        canonical_json_bytes,
    )

    return hashlib.sha256(canonical_json_bytes(content)).hexdigest()


# ── Fixtures (A1 test-only) ───────────────────────────────────────────────


@pytest.fixture()
def a1_engine() -> Engine:
    """Temp SQLite file with Alembic head schema for A1 live-DB tests.

    The engine is disposed and the temp file removed after the test.
    Foreign-key enforcement is enabled via ``PRAGMA foreign_keys=ON``
    so that the production schema constraints are exercised.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    env = os.environ.copy()
    env["SQLITE_PATH"] = str(db_path)
    env["DATABASE_BACKEND"] = "sqlite"
    env.pop("DATABASE_URL", None)
    # pytest adds ``src`` to sys.path via pyproject.toml's
    # ``pythonpath = ["src"]`` config; the alembic subprocess must
    # see the same sys.path so that ``cold_storage.*`` imports
    # resolve in alembic's env.py.
    src_path = (BACKEND_DIR / "src").resolve()
    existing_pp = env.get("PYTHONPATH", "")
    pp_parts = [str(src_path)] + ([existing_pp] if existing_pp else [])
    env["PYTHONPATH"] = os.pathsep.join(pp_parts)
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0:
        db_path.unlink(missing_ok=True)
        pytest.fail(f"Alembic failed: {r.stderr}")
    e = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(e, "connect")
    def _pragma(dbapi_conn, _rec):  # pragma: no cover (PRAGMA hook)
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    yield e
    e.dispose()
    db_path.unlink(missing_ok=True)


@pytest.fixture()
def a1_session_factory(a1_engine: Engine) -> Callable[[], Session]:
    """``sessionmaker`` bound to the A1 test engine (``expire_on_commit=False``)."""
    return sessionmaker(bind=a1_engine, expire_on_commit=False)


# ── Pre-seed chain (A1 test-only) ─────────────────────────────────────────


def _compute_a1_combined_source_hash() -> str:
    """Compute the combined source hash matching the production verifier."""
    from cold_storage.modules.schemes.application.source_binding_verifier import (
        _compute_combined_source_hash,
    )

    slot_ids = {
        "zone": ZONE_RUN_ID,
        "cooling_load": COOL_RUN_ID,
        "equipment": EQUIP_RUN_ID,
        "power": POWER_RUN_ID,
        "investment": INVEST_RUN_ID,
    }
    per_calc_hashes: dict[str, str] = {
        stage: _compute_domain_hash(
            stage=stage,
            result_snapshot=_SLOT_RESULTS[stage],
            run_id=slot_ids[stage],
        )
        for stage in _SLOT_STAGE_ORDER
    }
    return _compute_combined_source_hash(
        binding_schema_version="1.0.0",
        project_id=PROJECT_ID,
        project_version_id=VERSION_ID,
        execution_snapshot_id=EXEC_SNAPSHOT_ID,
        coefficient_context_id=COEFF_CONTEXT_ID,
        orchestration_identity_id=IDENTITY_ID,
        orchestration_attempt_id=ATTEMPT_ID,
        orchestration_fingerprint=FINGERPRINT,
        slot_ids=slot_ids,
        result_hashes=per_calc_hashes,
        requires_reviews={stage: False for stage in _SLOT_STAGE_ORDER},
    )


def seed_a1_project_and_version(session: Session) -> None:
    """Create the A1 test project + version (idempotent)."""
    from cold_storage.modules.projects.infrastructure.orm import (
        ProjectRecord,
        ProjectVersionRecord,
    )

    existing = session.execute(
        select(ProjectRecord).where(ProjectRecord.id == PROJECT_ID)
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            ProjectRecord(
                id=PROJECT_ID,
                code="A1_TEST_001",
                name="A1 Test Project",
                location="test",
                product_category="blueberry",
                status="active",
                current_version_number=1,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
    existing_v = session.execute(
        select(ProjectVersionRecord).where(ProjectVersionRecord.id == VERSION_ID)
    ).scalar_one_or_none()
    if existing_v is None:
        session.add(
            ProjectVersionRecord(
                id=VERSION_ID,
                project_id=PROJECT_ID,
                version_number=1,
                change_summary="a1 test version",
                created_by="a1-test",
                status="approved",
                created_at=datetime.now(UTC),
                input_snapshot={
                    "throughput_t": "25.0",
                    "product_category": "blueberry",
                },
            )
        )
    session.commit()


def seed_a1_orchestration_prereqs(session: Session) -> None:
    """Create snapshot / coefficient-context / identity / attempt for A1."""
    from cold_storage.modules.orchestration.infrastructure.orm import (
        CoefficientContextRecord,
        OrchestrationIdentityRecord,
        OrchestrationRunAttemptRecord,
        ProjectVersionExecutionSnapshotRecord,
    )

    existing = session.execute(
        select(ProjectVersionExecutionSnapshotRecord).where(
            ProjectVersionExecutionSnapshotRecord.id == EXEC_SNAPSHOT_ID
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            ProjectVersionExecutionSnapshotRecord(
                id=EXEC_SNAPSHOT_ID,
                project_id=PROJECT_ID,
                project_version_id=VERSION_ID,
                version_number=1,
                input_snapshot={"throughput_t": "25.0"},
                input_snapshot_hash="a1-snap-hash-001",
                schema_version="1.0.0",
                captured_status="approved",
                captured_at=datetime.now(UTC),
            )
        )

    existing_cc = session.execute(
        select(CoefficientContextRecord).where(
            CoefficientContextRecord.id == COEFF_CONTEXT_ID
        )
    ).scalar_one_or_none()
    if existing_cc is None:
        session.add(
            CoefficientContextRecord(
                id=COEFF_CONTEXT_ID,
                project_id=PROJECT_ID,
                project_version_id=VERSION_ID,
                content={"coefficients": []},
                content_hash="a1-cc-hash-001",
                schema_version="1.0.0",
                captured_at=datetime.now(UTC),
            )
        )
    session.commit()

    existing_i = session.execute(
        select(OrchestrationIdentityRecord).where(
            OrchestrationIdentityRecord.id == IDENTITY_ID
        )
    ).scalar_one_or_none()
    if existing_i is None:
        session.add(
            OrchestrationIdentityRecord(
                id=IDENTITY_ID,
                fingerprint=FINGERPRINT,
                execution_snapshot_id=EXEC_SNAPSHOT_ID,
                coefficient_context_id=COEFF_CONTEXT_ID,
                definition_version="1.0.0",
                calculator_version_vector={
                    "zone": "1.0.0",
                    "cooling_load": "1.0.0",
                    "equipment": "1.0.0",
                    "power": "1.0.0",
                    "investment": "1.0.0",
                },
                status="ACTIVE",
                created_at=datetime.now(UTC),
            )
        )

    existing_a = session.execute(
        select(OrchestrationRunAttemptRecord).where(
            OrchestrationRunAttemptRecord.id == ATTEMPT_ID
        )
    ).scalar_one_or_none()
    if existing_a is None:
        session.add(
            OrchestrationRunAttemptRecord(
                id=ATTEMPT_ID,
                identity_id=IDENTITY_ID,
                attempt_number=1,
                status="COMPLETED",
                heartbeat_at=datetime.now(UTC),
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                database_backend="sqlite",
                correlation_id="a1-test-corr-001",
            )
        )
        session.commit()

        identity_rec = session.execute(
            select(OrchestrationIdentityRecord).where(
                OrchestrationIdentityRecord.id == IDENTITY_ID
            )
        ).scalar_one()
        identity_rec.authoritative_attempt_id = ATTEMPT_ID
        session.commit()


def seed_a1_calculation_runs(session: Session) -> dict[str, str]:
    """Create the 5 ``CalculationRunRecord`` rows for the A1 test. Returns per-calc hash map."""
    from cold_storage.modules.projects.infrastructure.orm import (
        CalculationRunRecord,
    )

    slot_ids = {
        "zone": ZONE_RUN_ID,
        "cooling_load": COOL_RUN_ID,
        "equipment": EQUIP_RUN_ID,
        "power": POWER_RUN_ID,
        "investment": INVEST_RUN_ID,
    }
    per_calc: dict[str, str] = {}
    for stage in _SLOT_STAGE_ORDER:
        run_id = slot_ids[stage]
        snap = _SLOT_RESULTS[stage]
        computed_hash = _compute_domain_hash(
            stage=stage, result_snapshot=snap, run_id=run_id
        )
        per_calc[stage] = computed_hash
        existing = session.execute(
            select(CalculationRunRecord).where(CalculationRunRecord.id == run_id)
        ).scalar_one_or_none()
        if existing is not None:
            continue
        provenance: dict[str, Any] = {
            "stage": stage,
            "upstream_calculation_ids": _SLOT_UPSTREAM_IDS.get(stage, {}),
        }
        session.add(
            CalculationRunRecord(
                id=run_id,
                project_id=PROJECT_ID,
                project_version_id=VERSION_ID,
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
                orchestration_identity_id=IDENTITY_ID,
                orchestration_run_attempt_id=ATTEMPT_ID,
                execution_snapshot_id=EXEC_SNAPSHOT_ID,
                coefficient_context_id=COEFF_CONTEXT_ID,
                input_hash="a1-input-hash-001",
                result_hash=computed_hash,
                provenance=provenance,
                schema_version="1.0.0",
                orchestration_fingerprint=FINGERPRINT,
                created_at=datetime.now(UTC),
            )
        )
    session.commit()
    return per_calc


def seed_a1_source_binding(
    session: Session, *, per_calc: dict[str, str] | None = None
) -> None:
    """Create the A1 ``SourceBindingRecord`` (idempotent)."""
    from cold_storage.modules.orchestration.infrastructure.orm import (
        OrchestrationRunAttemptRecord,
        SourceBindingRecord,
    )

    per_calc = per_calc or {
        stage: _compute_domain_hash(
            stage=stage, result_snapshot=_SLOT_RESULTS[stage], run_id=slot_id
        )
        for stage, slot_id in (
            ("zone", ZONE_RUN_ID),
            ("cooling_load", COOL_RUN_ID),
            ("equipment", EQUIP_RUN_ID),
            ("power", POWER_RUN_ID),
            ("investment", INVEST_RUN_ID),
        )
    }

    existing = session.execute(
        select(SourceBindingRecord).where(
            SourceBindingRecord.id == SOURCE_BINDING_ID
        )
    ).scalar_one_or_none()
    if existing is not None:
        return

    combined = _compute_a1_combined_source_hash()
    session.add(
        SourceBindingRecord(
            id=SOURCE_BINDING_ID,
            project_id=PROJECT_ID,
            project_version_id=VERSION_ID,
            execution_snapshot_id=EXEC_SNAPSHOT_ID,
            coefficient_context_id=COEFF_CONTEXT_ID,
            orchestration_identity_id=IDENTITY_ID,
            orchestration_run_attempt_id=ATTEMPT_ID,
            orchestration_fingerprint=FINGERPRINT,
            zone_calculation_id=ZONE_RUN_ID,
            cooling_load_calculation_id=COOL_RUN_ID,
            equipment_calculation_id=EQUIP_RUN_ID,
            power_calculation_id=POWER_RUN_ID,
            investment_calculation_id=INVEST_RUN_ID,
            per_calculation_result_hashes=per_calc,
            combined_source_hash=combined,
            schema_version="1.0.0",
            created_at=datetime.now(UTC),
        )
    )
    session.commit()

    # P0-2: attempt.source_binding_id must be non-NULL.
    attempt_rec = session.execute(
        select(OrchestrationRunAttemptRecord).where(
            OrchestrationRunAttemptRecord.id == ATTEMPT_ID
        )
    ).scalar_one_or_none()
    if attempt_rec is not None and attempt_rec.source_binding_id is None:
        attempt_rec.source_binding_id = SOURCE_BINDING_ID
        session.commit()


def seed_a1_weight_set_and_revision(session: Session) -> None:
    """Create the A1 ``SchemeWeightSetRecord`` + approved revision."""
    from cold_storage.modules.schemes.infrastructure.orm import (
        SchemeWeightSetRecord,
        SchemeWeightSetRevisionRecord,
    )

    content_hash = _compute_weight_content_hash(WEIGHT_REVISION_CONTENT)
    approved_at = datetime.now(UTC)
    approved_by = "a1-test-approver"

    existing_ws = session.execute(
        select(SchemeWeightSetRecord).where(SchemeWeightSetRecord.id == WEIGHT_SET_ID)
    ).scalar_one_or_none()
    if existing_ws is None:
        session.add(
            SchemeWeightSetRecord(
                id=WEIGHT_SET_ID,
                code="a1-standard-weights",
                name="A1 Standard Weights",
                revision=1,
                status="approved",
                source_type="production",
                criteria=_WEIGHT_CRITERIA_RAW,
                requires_review=False,
                created_at=datetime.now(UTC),
                approved_at=approved_at,
            )
        )

    existing_rev = session.execute(
        select(SchemeWeightSetRevisionRecord).where(
            SchemeWeightSetRevisionRecord.id == WEIGHT_REVISION_ID
        )
    ).scalar_one_or_none()
    if existing_rev is None:
        # Production INSERT trigger blocks direct approved status, so
        # insert as draft first then UPDATE to approved.
        session.add(
            SchemeWeightSetRevisionRecord(
                id=WEIGHT_REVISION_ID,
                weight_set_id=WEIGHT_SET_ID,
                code="a1-standard-weights",
                revision=1,
                status="draft",
                content=WEIGHT_REVISION_CONTENT,
                content_hash=content_hash,
                generator_compatibility_version="1.0.0",
                approved_at=None,
                approved_by=None,
                sealed_at=None,
                created_at=datetime.now(UTC),
            )
        )
        session.flush()
        session.execute(
            text(
                "UPDATE scheme_weight_set_revisions "
                "SET status = 'approved', "
                "approved_at = :approved_at, "
                "approved_by = :approved_by "
                "WHERE id = :rev_id"
            ),
            {
                "approved_at": approved_at,
                "approved_by": approved_by,
                "rev_id": WEIGHT_REVISION_ID,
            },
        )
    session.commit()


def seed_a1_all_prereqs(session: Session) -> None:
    """Seed the full pre-existing production context chain for the A1 live-DB tests.

    Public entry point.  Calls the per-stage helpers in dependency order.
    """
    seed_a1_project_and_version(session)
    seed_a1_orchestration_prereqs(session)
    per_calc = seed_a1_calculation_runs(session)
    seed_a1_source_binding(session, per_calc=per_calc)
    seed_a1_weight_set_and_revision(session)


__all__ = [
    "a1_engine",
    "a1_session_factory",
    "seed_a1_all_prereqs",
    "seed_a1_project_and_version",
    "seed_a1_orchestration_prereqs",
    "seed_a1_calculation_runs",
    "seed_a1_source_binding",
    "seed_a1_weight_set_and_revision",
    "PROJECT_ID",
    "VERSION_ID",
    "EXEC_SNAPSHOT_ID",
    "COEFF_CONTEXT_ID",
    "IDENTITY_ID",
    "ATTEMPT_ID",
    "ZONE_RUN_ID",
    "COOL_RUN_ID",
    "EQUIP_RUN_ID",
    "POWER_RUN_ID",
    "INVEST_RUN_ID",
    "SOURCE_BINDING_ID",
    "WEIGHT_SET_ID",
    "WEIGHT_REVISION_ID",
]
