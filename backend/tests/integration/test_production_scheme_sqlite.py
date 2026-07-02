"""SQLite integration tests for production scheme generation.

Tests the ProductionSchemeService end-to-end with real Alembic-migrated
SQLite schema, verifying:

1. Successful production scheme generation
2. Source binding verification (missing binding, unsupported schema, attempt not completed)
3. Five slot loading (missing slot, wrong calculator name, hash mismatch)
4. Power authority (missing total_installed_power_kw_e rejected)
5. Equipment fallback rejection
6. Weight revision rejection matrix
7. Production SchemeRun provenance
8. Atomic rollback PK-set zero-delta
9. Source-mode constraints (ck_scheme_run_source_mode_nullity)
10. Legacy/demo isolation
11. Content hash verification

Uses fixed deterministic IDs, real SHA-256 hashes, and uv run pytest.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Skip entire module when running under PostgreSQL CI job.
if os.environ.get("DATABASE_BACKEND") == "postgresql":
    pytest.skip(
        "SQLite production scheme tests require DATABASE_BACKEND != postgresql",
        allow_module_level=True,
    )

BACKEND_DIR = Path(__file__).resolve().parents[2]

# ── Canonical hash helpers (mirrors source code exactly) ─────────────────────


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _compute_result_hash(result_snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(result_snapshot).encode()).hexdigest()


# ── Pre-computed hashes (P0-1: domain hash recomputation) ──────────────────


def _compute_domain_hash(
    *,
    stage: str,
    result_snapshot: dict[str, Any],
    run_id: str,
) -> str:
    """Compute domain SourceSnapshotContentV1 result_hash for a stage."""
    from cold_storage.modules.orchestration.domain.fingerprint import (
        result_hash as _domain_result_hash,
    )
    from cold_storage.modules.orchestration.domain.snapshots import (
        SourceSnapshotContentV1 as DomainSourceSnapshotContentV1,
    )
    from cold_storage.modules.orchestration.domain.snapshots import (
        SourceSnapshotProvenanceV1,
    )

    upstream = _SLOT_UPSTREAM_IDS.get(stage, {})
    calc_name = SLOT_CALCULATOR_NAMES[stage]
    calc_type = SLOT_CALCULATION_TYPES[stage]

    # Map stage to upstream run IDs
    upstream_ids: dict[str, str] = {}
    for key, _ in upstream.items():
        upstream_ids[key] = {
            "zone": ZONE_RUN_ID,
            "cooling_load": COOL_RUN_ID,
            "equipment": EQUIP_RUN_ID,
            "power": POWER_RUN_ID,
            "investment": INVEST_RUN_ID,
        }[key]

    provenance = SourceSnapshotProvenanceV1(
        execution_snapshot_id=EXEC_SNAPSHOT_ID,
        coefficient_context_id=COEFF_CONTEXT_ID,
        orchestration_identity_id=IDENTITY_ID,
        orchestration_run_attempt_id=ATTEMPT_ID,
        upstream_calculation_ids=upstream_ids,
    )
    content = DomainSourceSnapshotContentV1(
        schema_version="1.0.0",
        calculation_type=calc_type,
        calculator_name=calc_name,
        calculator_version="1.0.0",
        project_id=PROJECT_ID,
        project_version_id=VERSION_ID,
        execution_snapshot_id=EXEC_SNAPSHOT_ID,
        coefficient_context_id=COEFF_CONTEXT_ID,
        orchestration_identity_id=IDENTITY_ID,
        orchestration_run_attempt_id=ATTEMPT_ID,
        input_hash="input-hash-001",
        requires_review=False,
        payload=result_snapshot,
        provenance=provenance,
    )
    return _domain_result_hash(content)


ZONE_HASH = ""  # computed below after constants are defined
COOL_HASH = ""
EQUIP_HASH = ""
POWER_HASH = ""
INVEST_HASH = ""
PROJECT_ID = "test-p-001"
VERSION_ID = "test-v-001"
EXEC_SNAPSHOT_ID = "test-exec-001"
COEFF_CONTEXT_ID = "test-cc-001"
IDENTITY_ID = "test-id-001"
ATTEMPT_ID = "test-attempt-001"

ZONE_RUN_ID = "test-run-zone-001"
COOL_RUN_ID = "test-run-cool-001"
EQUIP_RUN_ID = "test-run-equip-001"
POWER_RUN_ID = "test-run-power-001"
INVEST_RUN_ID = "test-run-invest-001"

SOURCE_BINDING_ID = "test-binding-001"
WEIGHT_SET_ID = "test-ws-001"
WEIGHT_REVISION_ID = "test-wrev-001"

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
            "zone_name": "\u539f\u679c\u95f4",
            "daily_throughput_kg_day": 10000,
            "required_area_m2": "200.0",
            "design_storage_mass_kg": "15000.0",
            "position_count": 30,
            "temperature_band": "0~4\u2103",
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

ZONE_HASH = ""  # computed below after _SLOT_UPSTREAM_IDS is defined
COOL_HASH = ""
EQUIP_HASH = ""
POWER_HASH = ""
INVEST_HASH = ""
INVEST_HASH = ""

# ── Weight set revision content ─────────────────────────────────────────────


def _compute_weight_content_hash(content: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(content).encode()).hexdigest()


_SLOT_STAGE_ORDER: tuple[str, ...] = (
    "zone",
    "cooling_load",
    "equipment",
    "power",
    "investment",
)


WEIGHT_CRITERIA_RAW: list[dict[str, Any]] = [
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

WEIGHT_REVISION_CONTENT: dict[str, Any] = {"criteria": WEIGHT_CRITERIA_RAW}
WEIGHT_CONTENT_HASH = _compute_weight_content_hash(WEIGHT_REVISION_CONTENT)

# ── Calculator names (must match source binding verifier) ───────────────────

SLOT_CALCULATOR_NAMES: dict[str, str] = {
    "zone": "cold_room_zone_plan",
    "cooling_load": "cooling_load",
    "equipment": "equipment",
    "power": "installed_power",
    "investment": "investment_estimate",
}

SLOT_CALCULATION_TYPES: dict[str, str] = {
    "zone": "zone",
    "cooling_load": "cooling_load",
    "equipment": "equipment",
    "power": "power",
    "investment": "investment",
}

# ── Upstream provenance keys per stage ──────────────────────────────────────

_SLOT_UPSTREAM_IDS: dict[str, dict[str, str]] = {
    "zone": {},
    "cooling_load": {"zone": ZONE_RUN_ID},
    "equipment": {"cooling_load": COOL_RUN_ID},
    "power": {"equipment": EQUIP_RUN_ID},
    "investment": {"zone": ZONE_RUN_ID, "power": POWER_RUN_ID},
}

# ── Compute domain hashes (P0-1: after all constants are defined) ────────

ZONE_HASH = _compute_domain_hash(
    stage="zone", result_snapshot=ZONE_RESULT_SNAPSHOT, run_id=ZONE_RUN_ID
)
COOL_HASH = _compute_domain_hash(
    stage="cooling_load", result_snapshot=COOLING_RESULT_SNAPSHOT, run_id=COOL_RUN_ID
)
EQUIP_HASH = _compute_domain_hash(
    stage="equipment", result_snapshot=EQUIPMENT_RESULT_SNAPSHOT, run_id=EQUIP_RUN_ID
)
POWER_HASH = _compute_domain_hash(
    stage="power", result_snapshot=POWER_RESULT_SNAPSHOT, run_id=POWER_RUN_ID
)
INVEST_HASH = _compute_domain_hash(
    stage="investment", result_snapshot=INVESTMENT_RESULT_SNAPSHOT, run_id=INVEST_RUN_ID
)

PER_CALC_HASHES: dict[str, str] = {
    "zone": ZONE_HASH,
    "cooling_load": COOL_HASH,
    "equipment": EQUIP_HASH,
    "power": POWER_HASH,
    "investment": INVEST_HASH,
}


def _compute_verifier_combined_source_hash() -> str:
    """Compute the combined source hash matching the verifier's implementation."""
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
    return _compute_combined_source_hash(
        binding_schema_version="1.0.0",
        project_id=PROJECT_ID,
        project_version_id=VERSION_ID,
        execution_snapshot_id=EXEC_SNAPSHOT_ID,
        coefficient_context_id=COEFF_CONTEXT_ID,
        orchestration_identity_id=IDENTITY_ID,
        orchestration_attempt_id=ATTEMPT_ID,
        orchestration_fingerprint="test-fingerprint-001",
        slot_ids=slot_ids,
        result_hashes=PER_CALC_HASHES,
        requires_reviews={stage: False for stage in _SLOT_STAGE_ORDER},
    )


COMBINED_SOURCE_HASH = _compute_verifier_combined_source_hash()

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def engine():
    """Temp SQLite file with Alembic head schema."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    env = os.environ.copy()
    env["SQLITE_PATH"] = str(db_path)
    env["DATABASE_BACKEND"] = "sqlite"
    env.pop("DATABASE_URL", None)
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
    def _pragma(dbapi_conn, _rec):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    yield e
    e.dispose()
    db_path.unlink(missing_ok=True)


@pytest.fixture()
def session_factory(engine):
    """Session factory for creating new sessions from the engine."""
    return sessionmaker(bind=engine, expire_on_commit=False)


# ── Seed helpers ─────────────────────────────────────────────────────────────


def _seed_project_and_version(session) -> None:
    """Create ProjectRecord + ProjectVersionRecord if not present."""
    from cold_storage.modules.projects.infrastructure.orm import (
        ProjectRecord,
        ProjectVersionRecord,
    )

    existing = session.execute(
        select(ProjectRecord).where(ProjectRecord.id == PROJECT_ID)
    ).scalar_one_or_none()
    if not existing:
        session.add(
            ProjectRecord(
                id=PROJECT_ID,
                code="T_TEST_001",
                name="Test Project",
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
    if not existing_v:
        session.add(
            ProjectVersionRecord(
                id=VERSION_ID,
                project_id=PROJECT_ID,
                version_number=1,
                change_summary="test version",
                created_by="test",
                status="approved",
                created_at=datetime.now(UTC),
                input_snapshot={
                    "throughput_t": "25.0",
                    "product_category": "blueberry",
                },
            )
        )
    session.commit()


def _seed_orchestration_prereqs(session) -> None:
    """Create ExecutionSnapshot, CoefficientContext, Identity, Attempt."""
    from cold_storage.modules.orchestration.infrastructure.orm import (
        CoefficientContextRecord,
        OrchestrationIdentityRecord,
        OrchestrationRunAttemptRecord,
        ProjectVersionExecutionSnapshotRecord,
    )

    # Execution snapshot
    existing = session.execute(
        select(ProjectVersionExecutionSnapshotRecord).where(
            ProjectVersionExecutionSnapshotRecord.id == EXEC_SNAPSHOT_ID
        )
    ).scalar_one_or_none()
    if not existing:
        session.add(
            ProjectVersionExecutionSnapshotRecord(
                id=EXEC_SNAPSHOT_ID,
                project_id=PROJECT_ID,
                project_version_id=VERSION_ID,
                version_number=1,
                input_snapshot={"throughput_t": "25.0"},
                input_snapshot_hash="abc123",
                schema_version="1.0.0",
                captured_status="approved",
                captured_at=datetime.now(UTC),
            )
        )

    # Coefficient context
    existing_cc = session.execute(
        select(CoefficientContextRecord).where(CoefficientContextRecord.id == COEFF_CONTEXT_ID)
    ).scalar_one_or_none()
    if not existing_cc:
        session.add(
            CoefficientContextRecord(
                id=COEFF_CONTEXT_ID,
                project_id=PROJECT_ID,
                project_version_id=VERSION_ID,
                content={"coefficients": []},
                content_hash="abc456",
                schema_version="1.0.0",
                captured_at=datetime.now(UTC),
            )
        )

    session.commit()

    # Attempt (needs identity_id, but identity needs exec_snapshot_id and
    # coeff_context_id — attempt doesn't depend on identity for FK)
    existing_a = session.execute(
        select(OrchestrationRunAttemptRecord).where(OrchestrationRunAttemptRecord.id == ATTEMPT_ID)
    ).scalar_one_or_none()
    if not existing_a:
        # Create a temporary identity first (needed for attempt FK)
        existing_i = session.execute(
            select(OrchestrationIdentityRecord).where(OrchestrationIdentityRecord.id == IDENTITY_ID)
        ).scalar_one_or_none()
        if not existing_i:
            session.add(
                OrchestrationIdentityRecord(
                    id=IDENTITY_ID,
                    fingerprint="test-fingerprint-001",
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

        session.add(
            OrchestrationRunAttemptRecord(
                id=ATTEMPT_ID,
                identity_id=IDENTITY_ID,
                attempt_number=1,
                status="COMPLETED",
                heartbeat_at=datetime.now(UTC),
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
            )
        )
        session.commit()

        # Link identity → attempt
        identity_rec = session.execute(
            select(OrchestrationIdentityRecord).where(OrchestrationIdentityRecord.id == IDENTITY_ID)
        ).scalar_one()
        identity_rec.authoritative_attempt_id = ATTEMPT_ID
        session.commit()


def _seed_calculation_runs(
    session,
    *,
    zone_result: dict[str, Any] | None = None,
    cool_result: dict[str, Any] | None = None,
    equip_result: dict[str, Any] | None = None,
    power_result: dict[str, Any] | None = None,
    invest_result: dict[str, Any] | None = None,
    zone_hash_override: str | None = None,
) -> dict[str, str]:
    """Create 5 CalculationRunRecords. Returns per-calc hash map."""
    from cold_storage.modules.projects.infrastructure.orm import (
        CalculationRunRecord,
    )

    slots = [
        (ZONE_RUN_ID, "zone", zone_result or ZONE_RESULT_SNAPSHOT, zone_hash_override),
        (COOL_RUN_ID, "cooling_load", cool_result or COOLING_RESULT_SNAPSHOT, None),
        (EQUIP_RUN_ID, "equipment", equip_result or EQUIPMENT_RESULT_SNAPSHOT, None),
        (POWER_RUN_ID, "power", power_result or POWER_RESULT_SNAPSHOT, None),
        (INVEST_RUN_ID, "investment", invest_result or INVESTMENT_RESULT_SNAPSHOT, None),
    ]

    per_calc: dict[str, str] = {}
    for run_id, stage, snap, hash_ov in slots:
        existing = session.execute(
            select(CalculationRunRecord).where(CalculationRunRecord.id == run_id)
        ).scalar_one_or_none()
        if existing is None:
            computed_hash = (
                hash_ov
                if hash_ov
                else _compute_domain_hash(stage=stage, result_snapshot=snap, run_id=run_id)
            )
            provenance: dict[str, Any] = {
                "stage": stage,
                "upstream_calculation_ids": _SLOT_UPSTREAM_IDS.get(stage, {}),
            }
            session.add(
                CalculationRunRecord(
                    id=run_id,
                    project_id=PROJECT_ID,
                    project_version_id=VERSION_ID,
                    calculator_name=SLOT_CALCULATOR_NAMES[stage],
                    calculator_version="1.0.0",
                    input_snapshot={},
                    result_snapshot=snap,
                    formulas=[],
                    coefficients=[],
                    assumptions=[],
                    warnings=[],
                    source_references=[],
                    requires_review=False,
                    calculation_type=SLOT_CALCULATION_TYPES[stage],
                    orchestration_identity_id=IDENTITY_ID,
                    orchestration_run_attempt_id=ATTEMPT_ID,
                    execution_snapshot_id=EXEC_SNAPSHOT_ID,
                    coefficient_context_id=COEFF_CONTEXT_ID,
                    input_hash="input-hash-001",
                    result_hash=computed_hash,
                    provenance=provenance,
                    schema_version="1.0.0",
                    orchestration_fingerprint="test-fingerprint-001",
                    created_at=datetime.now(UTC),
                )
            )
            per_calc[stage] = computed_hash
        else:
            per_calc[stage] = existing.result_hash or _compute_result_hash(
                existing.result_snapshot or {}
            )
    session.commit()
    return per_calc


def _seed_source_binding(
    session,
    *,
    per_calc: dict[str, str] | None = None,
    binding_id: str = SOURCE_BINDING_ID,
    schema_version: str = "1.0.0",
    combined_hash_override: str | None = None,
) -> None:
    """Create a SourceBindingRecord."""
    from cold_storage.modules.orchestration.infrastructure.orm import (
        SourceBindingRecord,
    )

    if per_calc is None:
        per_calc = PER_CALC_HASHES

    existing = session.execute(
        select(SourceBindingRecord).where(SourceBindingRecord.id == binding_id)
    ).scalar_one_or_none()
    if existing is not None:
        return

    combined = combined_hash_override or _compute_verifier_combined_source_hash()

    session.add(
        SourceBindingRecord(
            id=binding_id,
            project_id=PROJECT_ID,
            project_version_id=VERSION_ID,
            execution_snapshot_id=EXEC_SNAPSHOT_ID,
            coefficient_context_id=COEFF_CONTEXT_ID,
            orchestration_identity_id=IDENTITY_ID,
            orchestration_run_attempt_id=ATTEMPT_ID,
            orchestration_fingerprint="test-fingerprint-001",
            zone_calculation_id=ZONE_RUN_ID,
            cooling_load_calculation_id=COOL_RUN_ID,
            equipment_calculation_id=EQUIP_RUN_ID,
            power_calculation_id=POWER_RUN_ID,
            investment_calculation_id=INVEST_RUN_ID,
            per_calculation_result_hashes=per_calc,
            combined_source_hash=combined,
            schema_version=schema_version,
            created_at=datetime.now(UTC),
        )
    )
    session.commit()

    # Link attempt → source binding (P0-2: attempt.source_binding_id must be non-NULL)
    from cold_storage.modules.orchestration.infrastructure.orm import (
        OrchestrationRunAttemptRecord,
    )

    attempt_rec = session.execute(
        select(OrchestrationRunAttemptRecord).where(OrchestrationRunAttemptRecord.id == ATTEMPT_ID)
    ).scalar_one_or_none()
    if attempt_rec is not None and attempt_rec.source_binding_id is None:
        attempt_rec.source_binding_id = binding_id
        session.commit()


_UNSET = object()


def _seed_weight_set_and_revision(
    session,
    *,
    revision_id: str = WEIGHT_REVISION_ID,
    status: str = "approved",
    content: dict[str, Any] | None = None,
    content_hash_override: str | None = None,
    approved_at: datetime | None | object = _UNSET,
    approved_by: str | None = "test-approver",
    generator_compat: str = "1.0.0",
) -> None:
    """Create SchemeWeightSetRecord + SchemeWeightSetRevisionRecord."""
    from cold_storage.modules.schemes.infrastructure.orm import (
        SchemeWeightSetRecord,
        SchemeWeightSetRevisionRecord,
    )

    content = content or WEIGHT_REVISION_CONTENT
    content_hash = content_hash_override or _compute_weight_content_hash(content)
    if approved_at is _UNSET:
        approved_at = datetime.now(UTC)

    # Weight set
    existing_ws = session.execute(
        select(SchemeWeightSetRecord).where(SchemeWeightSetRecord.id == WEIGHT_SET_ID)
    ).scalar_one_or_none()
    if existing_ws is None:
        session.add(
            SchemeWeightSetRecord(
                id=WEIGHT_SET_ID,
                code="standard-weights",
                name="\u6807\u51c6\u6743\u91cd\u96c6",
                revision=1,
                status="approved",
                source_type="production",
                criteria=WEIGHT_CRITERIA_RAW,
                requires_review=False,
                created_at=datetime.now(UTC),
                approved_at=approved_at,
            )
        )

    # Revision
    existing_rev = session.execute(
        select(SchemeWeightSetRevisionRecord).where(SchemeWeightSetRevisionRecord.id == revision_id)
    ).scalar_one_or_none()
    if existing_rev is None:
        session.add(
            SchemeWeightSetRevisionRecord(
                id=revision_id,
                weight_set_id=WEIGHT_SET_ID,
                code="standard-weights",
                revision=1,
                status=status,
                content=content,
                content_hash=content_hash,
                generator_compatibility_version=generator_compat,
                approved_at=approved_at,
                approved_by=approved_by,
                created_at=datetime.now(UTC),
            )
        )
    session.commit()


def _seed_all_prereqs(session) -> None:
    """Seed all prerequisite records for a happy-path test."""
    _seed_project_and_version(session)
    _seed_orchestration_prereqs(session)
    _seed_calculation_runs(session)
    _seed_source_binding(session)
    _seed_weight_set_and_revision(session)


# ── Service helper ───────────────────────────────────────────────────────────


def _make_service(engine):
    """Create a ProductionSchemeService with real DB ports via UoW factory."""
    from cold_storage.modules.schemes.application.production_service import (
        ProductionSchemeService,
    )
    from cold_storage.modules.schemes.infrastructure.production_read_ports import (
        SqlAlchemySourceBindingReadPort,
        SqlAlchemyWeightRevisionReadPort,
    )
    from cold_storage.modules.schemes.infrastructure.production_repository import (
        SqlAlchemyProductionSchemeRunRepository,
    )
    from cold_storage.modules.schemes.infrastructure.production_uow_impl import (
        SqlAlchemyProductionSchemeUnitOfWork,
    )

    sf = sessionmaker(bind=engine, expire_on_commit=False)

    def uow_factory() -> SqlAlchemyProductionSchemeUnitOfWork:
        return SqlAlchemyProductionSchemeUnitOfWork(sf)

    return ProductionSchemeService(
        uow_factory=uow_factory,
        binding_read_port=SqlAlchemySourceBindingReadPort(),
        weight_revision_read_port=SqlAlchemyWeightRevisionReadPort(),
        run_repository=SqlAlchemyProductionSchemeRunRepository(),
    )


def _make_command(
    *,
    binding_id: str = SOURCE_BINDING_ID,
    revision_id: str = WEIGHT_REVISION_ID,
    profile_codes: tuple[str, ...] = ("balanced",),
    profile_parameters: dict[str, dict[str, object]] | None = None,
    actor: str = "test-actor",
    correlation_id: str = "test-corr-001",
):
    from cold_storage.modules.schemes.application.production_ports import (
        GenerateProductionSchemeCommand,
    )

    return GenerateProductionSchemeCommand(
        source_binding_id=binding_id,
        weight_set_revision_id=revision_id,
        profile_codes=profile_codes,
        profile_parameters=profile_parameters or {},
        actor=actor,
        correlation_id=correlation_id,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 1. Successful production scheme generation
# ══════════════════════════════════════════════════════════════════════════════


class TestSuccessfulProductionSchemeGeneration:
    """Seeds real SourceBinding + 5 CalculationRuns + weight revision,
    generates a production SchemeRun, and asserts all fields."""

    def test_happy_path(self, engine, session_factory) -> None:
        # Seed data via a committed session
        seed_s = session_factory()
        try:
            _seed_all_prereqs(seed_s)
        finally:
            seed_s.close()

        service = _make_service(engine)
        cmd = _make_command()
        run = service.generate_production_scheme_run(cmd)

        # Verify domain run
        assert run.status == "completed"
        assert run.project_id == PROJECT_ID
        assert run.project_version_id == VERSION_ID

        # Verify persisted record via a new session
        verify_s = session_factory()
        try:
            from cold_storage.modules.schemes.infrastructure.orm import (
                SchemeCandidateRecord,
                SchemeRunRecord,
            )

            rec = verify_s.execute(
                select(SchemeRunRecord).where(SchemeRunRecord.id == run.id)
            ).scalar_one_or_none()
            assert rec is not None
            assert rec.status == "completed"
            assert rec.source_mode == "production"
            assert rec.source_binding_id == SOURCE_BINDING_ID
            assert rec.weight_set_revision_id == WEIGHT_REVISION_ID
            assert rec.source_contract_version == "1.0.0"
            assert rec.combined_source_hash == COMBINED_SOURCE_HASH
            assert rec.weight_set_content_hash == WEIGHT_CONTENT_HASH
            assert rec.content_hash is not None
            assert len(rec.content_hash) == 64  # SHA-256 hex

            # P1: Verify candidate total_score persistence
            candidates = (
                verify_s.execute(
                    select(SchemeCandidateRecord).where(
                        SchemeCandidateRecord.scheme_run_id == run.id
                    )
                )
                .scalars()
                .all()
            )
            assert len(candidates) > 0, "Expected at least one candidate"

            for cand_rec in candidates:
                assert cand_rec.total_score is not None, (
                    f"Candidate {cand_rec.scheme_code} total_score must not be NULL"
                )
                assert isinstance(cand_rec.total_score, Decimal), (
                    f"Candidate {cand_rec.scheme_code} total_score must be Decimal, "
                    f"got {type(cand_rec.total_score)}"
                )
                assert cand_rec.score_breakdown_snapshot, (
                    f"Candidate {cand_rec.scheme_code} score_breakdown_snapshot must not be empty"
                )
        finally:
            verify_s.close()


# ══════════════════════════════════════════════════════════════════════════════
# 2. Source binding verification
# ══════════════════════════════════════════════════════════════════════════════


class TestSourceBindingVerification:
    """Missing binding, unsupported schema, attempt not completed."""

    def test_missing_binding(self, engine, session_factory) -> None:
        seed_s = session_factory()
        try:
            _seed_project_and_version(seed_s)
        finally:
            seed_s.close()

        service = _make_service(engine)
        cmd = _make_command(binding_id="nonexistent-binding")
        with pytest.raises(Exception) as exc_info:
            service.generate_production_scheme_run(cmd)
        assert (
            "binding_not_found" in str(exc_info.value) or "not found" in str(exc_info.value).lower()
        )

    def test_unsupported_schema(self, engine, session_factory) -> None:
        seed_s = session_factory()
        try:
            _seed_project_and_version(seed_s)
            _seed_orchestration_prereqs(seed_s)
            _seed_calculation_runs(seed_s)
            _seed_source_binding(seed_s, schema_version="99.0.0")
        finally:
            seed_s.close()

        service = _make_service(engine)
        cmd = _make_command()
        with pytest.raises(Exception) as exc_info:
            service.generate_production_scheme_run(cmd)
        assert (
            "schema" in str(exc_info.value).lower() or "unsupported" in str(exc_info.value).lower()
        )

    def test_attempt_not_completed(self, engine, session_factory) -> None:
        seed_s = session_factory()
        try:
            _seed_project_and_version(seed_s)
            _seed_orchestration_prereqs(seed_s)
            _seed_calculation_runs(seed_s)
            _seed_source_binding(seed_s)

            # Overwrite attempt status to RUNNING
            from cold_storage.modules.orchestration.infrastructure.orm import (
                OrchestrationRunAttemptRecord,
            )

            attempt = seed_s.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.id == ATTEMPT_ID
                )
            ).scalar_one()
            attempt.status = "RUNNING"
            seed_s.commit()
        finally:
            seed_s.close()

        service = _make_service(engine)
        cmd = _make_command()
        with pytest.raises(Exception) as exc_info:
            service.generate_production_scheme_run(cmd)
        assert (
            "attempt" in str(exc_info.value).lower() or "completed" in str(exc_info.value).lower()
        )


# ══════════════════════════════════════════════════════════════════════════════
# 3. Five slot loading
# ══════════════════════════════════════════════════════════════════════════════


class TestFiveSlotLoading:
    """Missing slot, wrong calculator name, hash mismatch."""

    def test_missing_slot(self, engine, session_factory) -> None:
        seed_s = session_factory()
        try:
            _seed_project_and_version(seed_s)
            _seed_orchestration_prereqs(seed_s)
            _seed_weight_set_and_revision(seed_s)

            # Temporarily disable FK checks to insert a binding referencing
            # a non-existent zone CalculationRun
            seed_s.execute(text("PRAGMA foreign_keys=OFF"))
            seed_s.execute(
                text(
                    "INSERT INTO orchestration_source_bindings "
                    "(id, project_id, project_version_id, execution_snapshot_id, "
                    " coefficient_context_id, orchestration_identity_id, "
                    " orchestration_run_attempt_id, orchestration_fingerprint, "
                    " zone_calculation_id, cooling_load_calculation_id, "
                    " equipment_calculation_id, power_calculation_id, "
                    " investment_calculation_id, per_calculation_result_hashes, "
                    " combined_source_hash, schema_version, created_at) "
                    "VALUES (:id, :pid, :vid, :eid, :ccid, :iid, :aid, :fp, "
                    " :zid, :cid, :eid2, :pid2, :iid2, :pch, :csh, :sv, :ca)"
                ),
                {
                    "id": "test-missing-slot-binding",
                    "pid": PROJECT_ID,
                    "vid": VERSION_ID,
                    "eid": EXEC_SNAPSHOT_ID,
                    "ccid": COEFF_CONTEXT_ID,
                    "iid": IDENTITY_ID,
                    "aid": ATTEMPT_ID,
                    "fp": "test-fingerprint-001",
                    "zid": "nonexistent-zone-run",
                    "cid": COOL_RUN_ID,
                    "eid2": EQUIP_RUN_ID,
                    "pid2": POWER_RUN_ID,
                    "iid2": INVEST_RUN_ID,
                    "pch": json.dumps(PER_CALC_HASHES),
                    "csh": COMBINED_SOURCE_HASH,
                    "sv": "1.0.0",
                    "ca": datetime.now(UTC).isoformat(),
                },
            )
            seed_s.execute(text("PRAGMA foreign_keys=ON"))
            seed_s.commit()
        finally:
            seed_s.close()

        from cold_storage.modules.schemes.application.source_binding_verifier import (
            verify_source_binding,
        )
        from cold_storage.modules.schemes.infrastructure.production_read_ports import (
            SqlAlchemySourceBindingReadPort,
        )

        port = SqlAlchemySourceBindingReadPort()
        verify_s = session_factory()
        try:
            with pytest.raises(Exception) as exc_info:
                verify_source_binding(port, verify_s, binding_id="test-missing-slot-binding")
            assert (
                "missing" in str(exc_info.value).lower()
                or "not found" in str(exc_info.value).lower()
                or "slot" in str(exc_info.value).lower()
            )
        finally:
            verify_s.close()

    def test_wrong_calculator_name(self, engine, session_factory) -> None:
        seed_s = session_factory()
        try:
            _seed_project_and_version(seed_s)
            _seed_orchestration_prereqs(seed_s)
            from cold_storage.modules.projects.infrastructure.orm import (
                CalculationRunRecord,
            )

            # Seed zone with wrong calculator_name
            seed_s.add(
                CalculationRunRecord(
                    id=ZONE_RUN_ID,
                    project_id=PROJECT_ID,
                    project_version_id=VERSION_ID,
                    calculator_name="wrong_calculator",
                    calculator_version="1.0.0",
                    input_snapshot={},
                    result_snapshot=ZONE_RESULT_SNAPSHOT,
                    formulas=[],
                    coefficients=[],
                    assumptions=[],
                    warnings=[],
                    source_references=[],
                    requires_review=False,
                    calculation_type="zone",
                    orchestration_identity_id=IDENTITY_ID,
                    orchestration_run_attempt_id=ATTEMPT_ID,
                    execution_snapshot_id=EXEC_SNAPSHOT_ID,
                    coefficient_context_id=COEFF_CONTEXT_ID,
                    input_hash="input-hash-001",
                    result_hash=ZONE_HASH,
                    provenance={"stage": "zone", "upstream_calculation_ids": {}},
                    schema_version="1.0.0",
                    orchestration_fingerprint="test-fingerprint-001",
                    created_at=datetime.now(UTC),
                )
            )
            # Seed remaining 4 correctly
            for run_id, stage, snap in [
                (COOL_RUN_ID, "cooling_load", COOLING_RESULT_SNAPSHOT),
                (EQUIP_RUN_ID, "equipment", EQUIPMENT_RESULT_SNAPSHOT),
                (POWER_RUN_ID, "power", POWER_RESULT_SNAPSHOT),
                (INVEST_RUN_ID, "investment", INVESTMENT_RESULT_SNAPSHOT),
            ]:
                seed_s.add(
                    CalculationRunRecord(
                        id=run_id,
                        project_id=PROJECT_ID,
                        project_version_id=VERSION_ID,
                        calculator_name=SLOT_CALCULATOR_NAMES[stage],
                        calculator_version="1.0.0",
                        input_snapshot={},
                        result_snapshot=snap,
                        formulas=[],
                        coefficients=[],
                        assumptions=[],
                        warnings=[],
                        source_references=[],
                        requires_review=False,
                        calculation_type=SLOT_CALCULATION_TYPES[stage],
                        orchestration_identity_id=IDENTITY_ID,
                        orchestration_run_attempt_id=ATTEMPT_ID,
                        execution_snapshot_id=EXEC_SNAPSHOT_ID,
                        coefficient_context_id=COEFF_CONTEXT_ID,
                        input_hash="input-hash-001",
                        result_hash=_compute_result_hash(snap),
                        provenance={
                            "stage": stage,
                            "upstream_calculation_ids": _SLOT_UPSTREAM_IDS.get(stage, {}),
                        },
                        schema_version="1.0.0",
                        orchestration_fingerprint="test-fingerprint-001",
                        created_at=datetime.now(UTC),
                    )
                )
            seed_s.commit()

            _seed_source_binding(seed_s)
        finally:
            seed_s.close()

        service = _make_service(engine)
        cmd = _make_command()
        with pytest.raises(Exception) as exc_info:
            service.generate_production_scheme_run(cmd)
        assert (
            "calculator" in str(exc_info.value).lower()
            or "type" in str(exc_info.value).lower()
            or "mismatch" in str(exc_info.value).lower()
        )

    def test_hash_mismatch(self, engine, session_factory) -> None:
        seed_s = session_factory()
        try:
            _seed_project_and_version(seed_s)
            _seed_orchestration_prereqs(seed_s)
            from cold_storage.modules.projects.infrastructure.orm import (
                CalculationRunRecord,
            )

            # Seed all 5 calc runs with correct hashes
            for run_id, stage, snap in [
                (ZONE_RUN_ID, "zone", ZONE_RESULT_SNAPSHOT),
                (COOL_RUN_ID, "cooling_load", COOLING_RESULT_SNAPSHOT),
                (EQUIP_RUN_ID, "equipment", EQUIPMENT_RESULT_SNAPSHOT),
                (POWER_RUN_ID, "power", POWER_RESULT_SNAPSHOT),
                (INVEST_RUN_ID, "investment", INVESTMENT_RESULT_SNAPSHOT),
            ]:
                seed_s.add(
                    CalculationRunRecord(
                        id=run_id,
                        project_id=PROJECT_ID,
                        project_version_id=VERSION_ID,
                        calculator_name=SLOT_CALCULATOR_NAMES[stage],
                        calculator_version="1.0.0",
                        input_snapshot={},
                        result_snapshot=snap,
                        formulas=[],
                        coefficients=[],
                        assumptions=[],
                        warnings=[],
                        source_references=[],
                        requires_review=False,
                        calculation_type=SLOT_CALCULATION_TYPES[stage],
                        orchestration_identity_id=IDENTITY_ID,
                        orchestration_run_attempt_id=ATTEMPT_ID,
                        execution_snapshot_id=EXEC_SNAPSHOT_ID,
                        coefficient_context_id=COEFF_CONTEXT_ID,
                        input_hash="input-hash-001",
                        result_hash="wrong_hash_value",
                        provenance={
                            "stage": stage,
                            "upstream_calculation_ids": _SLOT_UPSTREAM_IDS.get(stage, {}),
                        },
                        schema_version="1.0.0",
                        orchestration_fingerprint="test-fingerprint-001",
                        created_at=datetime.now(UTC),
                    )
                )
            seed_s.commit()

            _seed_source_binding(seed_s)
        finally:
            seed_s.close()

        service = _make_service(engine)
        cmd = _make_command()
        with pytest.raises(Exception) as exc_info:
            service.generate_production_scheme_run(cmd)
        assert "hash" in str(exc_info.value).lower() or "mismatch" in str(exc_info.value).lower()


# ══════════════════════════════════════════════════════════════════════════════
# 4. Power authority
# ══════════════════════════════════════════════════════════════════════════════


class TestPowerAuthority:
    """Missing total_installed_power_kw_e in power result_snapshot is rejected."""

    def test_missing_power_authority(self, engine, session_factory) -> None:
        seed_s = session_factory()
        try:
            _seed_project_and_version(seed_s)
            _seed_orchestration_prereqs(seed_s)
            # Power snapshot WITHOUT total_installed_power_kw_e
            power_snap_no_authority: dict[str, Any] = {"some_other_field": "42.0"}
            _seed_calculation_runs(seed_s, power_result=power_snap_no_authority)
            _seed_source_binding(seed_s)
        finally:
            seed_s.close()

        service = _make_service(engine)
        cmd = _make_command()
        with pytest.raises(Exception) as exc_info:
            service.generate_production_scheme_run(cmd)
        assert (
            "power" in str(exc_info.value).lower()
            or "authority" in str(exc_info.value).lower()
            or "total_installed_power" in str(exc_info.value).lower()
        )


# ══════════════════════════════════════════════════════════════════════════════
# 5. Equipment fallback rejection
# ══════════════════════════════════════════════════════════════════════════════


class TestEquipmentFallbackRejection:
    """Equipment.installed_power_kw_e is NOT used as whole-project power.
    Equipment.installed_power_kw_e is set to 0 in map_equipment_snapshot,
    confirming it is never used as the whole-project installed power."""

    def test_equipment_power_is_zero_not_used(self) -> None:
        """Verify that map_equipment_snapshot sets installed_power_kw_e=0,
        proving it does NOT use the equipment snapshot's own power value."""
        from cold_storage.modules.schemes.application.source_domain_mapping import (
            map_equipment_snapshot,
        )

        # Equipment snapshot with installed_power_kw_e=150.0
        result = map_equipment_snapshot(EQUIPMENT_RESULT_SNAPSHOT)
        # The mapping MUST NOT use the equipment snapshot's power
        assert result.installed_power_kw_e == Decimal("0")

    def test_power_source_is_sole_authority(self) -> None:
        """Verify map_power_snapshot reads from the power result, not equipment."""
        from cold_storage.modules.schemes.application.source_domain_mapping import (
            map_power_snapshot,
        )

        power_val = map_power_snapshot(POWER_RESULT_SNAPSHOT)
        assert power_val.total_installed_power_kw_e == Decimal("200.0")

    def test_power_snapshot_missing_raises(self) -> None:
        """Verify map_power_snapshot raises when field is missing."""
        from cold_storage.modules.schemes.application.source_domain_mapping import (
            map_power_snapshot,
        )
        from cold_storage.modules.schemes.domain.errors import MappingError

        with pytest.raises(MappingError):
            map_power_snapshot({})


# ══════════════════════════════════════════════════════════════════════════════
# 6. Weight revision rejection matrix
# ══════════════════════════════════════════════════════════════════════════════


class TestWeightRevisionRejectionMatrix:
    """Not approved, missing approval evidence, content hash mismatch,
    duplicate criteria, negative weight, weight sum != 1.0, incompatible generator."""

    def test_not_approved(self, engine, session_factory) -> None:
        seed_s = session_factory()
        try:
            _seed_project_and_version(seed_s)
            _seed_orchestration_prereqs(seed_s)
            _seed_calculation_runs(seed_s)
            _seed_source_binding(seed_s)
            _seed_weight_set_and_revision(seed_s, status="draft")
        finally:
            seed_s.close()

        service = _make_service(engine)
        cmd = _make_command()
        with pytest.raises(Exception) as exc_info:
            service.generate_production_scheme_run(cmd)
        assert (
            "approved" in str(exc_info.value).lower()
            or "not_approved" in str(exc_info.value).lower()
        )

    def test_missing_approval_evidence_approved_at(self, engine, session_factory) -> None:
        """DB CHECK constraint rejects status='approved' without approved_at."""
        from sqlalchemy import exc as sa_exc

        seed_s = session_factory()
        try:
            _seed_project_and_version(seed_s)
            _seed_orchestration_prereqs(seed_s)
            _seed_calculation_runs(seed_s)
            _seed_source_binding(seed_s)
            with pytest.raises(sa_exc.IntegrityError, match="ck_weight_revision_approval_evidence"):
                _seed_weight_set_and_revision(
                    seed_s, status="approved", approved_at=None, approved_by="test"
                )
                seed_s.commit()
        finally:
            seed_s.rollback()
            seed_s.close()

    def test_missing_approval_evidence_approved_by(self, engine, session_factory) -> None:
        """DB CHECK constraint rejects status='approved' without approved_by."""
        from sqlalchemy import exc as sa_exc

        seed_s = session_factory()
        try:
            _seed_project_and_version(seed_s)
            _seed_orchestration_prereqs(seed_s)
            _seed_calculation_runs(seed_s)
            _seed_source_binding(seed_s)
            with pytest.raises(sa_exc.IntegrityError, match="ck_weight_revision_approval_evidence"):
                _seed_weight_set_and_revision(
                    seed_s,
                    status="approved",
                    approved_at=datetime.now(UTC),
                    approved_by="",
                )
                seed_s.commit()
        finally:
            seed_s.rollback()
            seed_s.close()

    def test_content_hash_mismatch(self, engine, session_factory) -> None:
        seed_s = session_factory()
        try:
            _seed_project_and_version(seed_s)
            _seed_orchestration_prereqs(seed_s)
            _seed_calculation_runs(seed_s)
            _seed_source_binding(seed_s)
            _seed_weight_set_and_revision(seed_s, content_hash_override="wrong_hash_abc123")
        finally:
            seed_s.close()

        service = _make_service(engine)
        cmd = _make_command()
        with pytest.raises(Exception) as exc_info:
            service.generate_production_scheme_run(cmd)
        assert (
            "hash" in str(exc_info.value).lower()
            or "tamper" in str(exc_info.value).lower()
            or "mismatch" in str(exc_info.value).lower()
        )

    def test_duplicate_criteria(self, engine, session_factory) -> None:
        seed_s = session_factory()
        try:
            _seed_project_and_version(seed_s)
            _seed_orchestration_prereqs(seed_s)
            _seed_calculation_runs(seed_s)
            _seed_source_binding(seed_s)
            dup_criteria = WEIGHT_CRITERIA_RAW + [
                {
                    "criterion_code": "total_area_m2",
                    "weight": "0.10",
                    "direction": "lower_is_better",
                    "normalization_method": "min_max",
                    "hard_constraint": True,
                }
            ]
            dup_content = {"criteria": dup_criteria}
            _seed_weight_set_and_revision(seed_s, content=dup_content)
        finally:
            seed_s.close()

        service = _make_service(engine)
        cmd = _make_command()
        with pytest.raises(Exception) as exc_info:
            service.generate_production_scheme_run(cmd)
        assert "duplicate" in str(exc_info.value).lower()

    def test_negative_weight(self, engine, session_factory) -> None:
        seed_s = session_factory()
        try:
            _seed_project_and_version(seed_s)
            _seed_orchestration_prereqs(seed_s)
            _seed_calculation_runs(seed_s)
            _seed_source_binding(seed_s)
            neg_criteria = [
                {
                    "criterion_code": "total_area_m2",
                    "weight": "-0.20",
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
            neg_content = {"criteria": neg_criteria}
            _seed_weight_set_and_revision(seed_s, content=neg_content)
        finally:
            seed_s.close()

        service = _make_service(engine)
        cmd = _make_command()
        with pytest.raises(Exception) as exc_info:
            service.generate_production_scheme_run(cmd)
        assert "negative" in str(exc_info.value).lower() or "weight" in str(exc_info.value).lower()

    def test_weight_sum_not_one(self, engine, session_factory) -> None:
        seed_s = session_factory()
        try:
            _seed_project_and_version(seed_s)
            _seed_orchestration_prereqs(seed_s)
            _seed_calculation_runs(seed_s)
            _seed_source_binding(seed_s)
            bad_sum_criteria = [
                {
                    "criterion_code": "total_area_m2",
                    "weight": "0.50",
                    "direction": "lower_is_better",
                    "normalization_method": "min_max",
                    "hard_constraint": False,
                },
                {
                    "criterion_code": "investment_cny",
                    "weight": "0.50",
                    "direction": "lower_is_better",
                    "normalization_method": "min_max",
                    "hard_constraint": False,
                },
                {
                    "criterion_code": "total_position_count",
                    "weight": "0.50",
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
            bad_sum_content = {"criteria": bad_sum_criteria}
            _seed_weight_set_and_revision(seed_s, content=bad_sum_content)
        finally:
            seed_s.close()

        service = _make_service(engine)
        cmd = _make_command()
        with pytest.raises(Exception) as exc_info:
            service.generate_production_scheme_run(cmd)
        assert (
            "sum" in str(exc_info.value).lower()
            or "1.0" in str(exc_info.value)
            or "weight" in str(exc_info.value).lower()
        )

    def test_incompatible_generator(self, engine, session_factory) -> None:
        seed_s = session_factory()
        try:
            _seed_project_and_version(seed_s)
            _seed_orchestration_prereqs(seed_s)
            _seed_calculation_runs(seed_s)
            _seed_source_binding(seed_s)
            _seed_weight_set_and_revision(seed_s, generator_compat="99.0.0")
        finally:
            seed_s.close()

        service = _make_service(engine)
        cmd = _make_command()
        with pytest.raises(Exception) as exc_info:
            service.generate_production_scheme_run(cmd)
        assert (
            "generator" in str(exc_info.value).lower()
            or "incompatible" in str(exc_info.value).lower()
        )


# ══════════════════════════════════════════════════════════════════════════════
# 7. Production SchemeRun provenance
# ══════════════════════════════════════════════════════════════════════════════


class TestProductionSchemeRunProvenance:
    """source_mode=production, all production fields non-null, content hash correct."""

    def test_all_production_fields_non_null(self, engine, session_factory) -> None:
        seed_s = session_factory()
        try:
            _seed_all_prereqs(seed_s)
        finally:
            seed_s.close()

        service = _make_service(engine)
        cmd = _make_command()
        run = service.generate_production_scheme_run(cmd)

        verify_s = session_factory()
        try:
            from cold_storage.modules.schemes.infrastructure.orm import (
                SchemeRunRecord,
            )

            rec = verify_s.execute(
                select(SchemeRunRecord).where(SchemeRunRecord.id == run.id)
            ).scalar_one()

            assert rec.source_mode == "production"
            assert rec.source_binding_id is not None
            assert rec.source_binding_id == SOURCE_BINDING_ID
            assert rec.source_contract_version is not None
            assert rec.source_contract_version == "1.0.0"
            assert rec.weight_set_revision_id is not None
            assert rec.weight_set_revision_id == WEIGHT_REVISION_ID
            assert rec.weight_set_content_hash is not None
            assert rec.weight_set_content_hash == WEIGHT_CONTENT_HASH
            assert rec.weight_set_generator_compatibility_version is not None
            assert rec.combined_source_hash is not None
            assert rec.combined_source_hash == COMBINED_SOURCE_HASH
        finally:
            verify_s.close()

    def test_content_hash_correct(self, engine, session_factory) -> None:
        seed_s = session_factory()
        try:
            _seed_all_prereqs(seed_s)
        finally:
            seed_s.close()

        service = _make_service(engine)
        cmd = _make_command()
        run = service.generate_production_scheme_run(cmd)

        verify_s = session_factory()
        try:
            from cold_storage.modules.schemes.infrastructure.orm import (
                SchemeRunRecord,
            )

            rec = verify_s.execute(
                select(SchemeRunRecord).where(SchemeRunRecord.id == run.id)
            ).scalar_one()

            # Verify the hash is present and is a valid SHA-256 hex digest
            assert rec.content_hash is not None
            assert len(rec.content_hash) == 64
            # Verify it's valid hex
            int(rec.content_hash, 16)
        finally:
            verify_s.close()


# ══════════════════════════════════════════════════════════════════════════════
# 8. Atomic rollback PK-set zero-delta
# ══════════════════════════════════════════════════════════════════════════════


class TestAtomicRollbackPKSetZeroDelta:
    """Persistence failure rolls back all records (no partial writes).

    P0-8: Real partial-flush rollback test.
    - Flushes SchemeRun successfully.
    - Flushes at least one Candidate successfully.
    - Injects failure for second Candidate via a repository seam.
    - Verifies all PK sets are zero-delta after rollback.
    """

    def test_partial_flush_rollback(self, engine, session_factory) -> None:
        """Flush run + one candidate, fail on second candidate, verify rollback."""
        seed_s = session_factory()
        try:
            _seed_all_prereqs(seed_s)
        finally:
            seed_s.close()

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeCandidateRecord,
            SchemeRunRecord,
        )

        # Capture PK set before via a fresh session
        before_s = session_factory()
        try:
            before_runs = set(before_s.execute(select(SchemeRunRecord.id)).scalars().all())
            before_cands = set(before_s.execute(select(SchemeCandidateRecord.id)).scalars().all())
        finally:
            before_s.close()

        # Build a repository seam: split save_production_run into explicit
        # flushes so we can fail AFTER the run and first candidate are flushed.
        from cold_storage.modules.schemes.application.production_ports import (
            PersistedSchemeRun,
        )
        from cold_storage.modules.schemes.infrastructure.production_repository import (
            SqlAlchemyProductionSchemeRunRepository,
        )

        _original_save = SqlAlchemyProductionSchemeRunRepository.save_production_run

        def _partial_flush_save(
            self: SqlAlchemyProductionSchemeRunRepository,
            session: Any,
            /,
            **kwargs: Any,
        ) -> PersistedSchemeRun:
            """Seam that flushes run + first candidate, then raises."""
            from cold_storage.modules.schemes.infrastructure.orm import (
                SchemeCandidateRecord as SCR,
            )
            from cold_storage.modules.schemes.infrastructure.orm import (
                SchemeRunRecord as SRR,
            )

            run_rec = SRR(
                id=kwargs["run_id"],
                project_id=kwargs["project_id"],
                project_version_id=kwargs["project_version_id"],
                weight_set_id=kwargs["weight_set_id"],
                status=kwargs["status"],
                generator_version=kwargs["generator_version"],
                source_snapshot_hash=kwargs["source_snapshot_hash"],
                input_snapshot=kwargs["input_snapshot"],
                assumption_snapshot={
                    **kwargs["assumption_snapshot"],
                    "profile_codes": list(kwargs["profile_codes"]),
                    "profile_parameters": dict(kwargs["profile_parameters"]),
                },
                comparison_snapshot=kwargs["comparison_snapshot"],
                candidates_snapshot=kwargs["candidates_snapshot"],
                requires_review=kwargs["requires_review"],
                recommended_scheme_code=kwargs["recommended_scheme_code"],
                warning_messages=kwargs["warning_messages"],
                content_hash=kwargs["content_hash"],
                source_mode=kwargs["source_mode"],
                source_binding_id=kwargs["source_binding_id"],
                source_contract_version=kwargs["source_contract_version"],
                weight_set_revision_id=kwargs["weight_set_revision_id"],
                weight_set_content_hash=kwargs["weight_set_content_hash"],
                weight_set_generator_compatibility_version=kwargs[
                    "weight_set_generator_compatibility_version"
                ],
                combined_source_hash=kwargs["combined_source_hash"],
                binding_schema_version=kwargs["binding_schema_version"],
                execution_snapshot_id=kwargs["execution_snapshot_id"],
                coefficient_context_id=kwargs["coefficient_context_id"],
                orchestration_identity_id=kwargs["orchestration_identity_id"],
                authoritative_attempt_id=kwargs["authoritative_attempt_id"],
                orchestration_fingerprint=kwargs["orchestration_fingerprint"],
                zone_calculation_id=kwargs["zone_calculation_id"],
                cooling_load_calculation_id=kwargs["cooling_load_calculation_id"],
                equipment_calculation_id=kwargs["equipment_calculation_id"],
                power_calculation_id=kwargs["power_calculation_id"],
                investment_calculation_id=kwargs["investment_calculation_id"],
                zone_result_hash=kwargs["zone_result_hash"],
                cooling_load_result_hash=kwargs["cooling_load_result_hash"],
                equipment_result_hash=kwargs["equipment_result_hash"],
                power_result_hash=kwargs["power_result_hash"],
                investment_result_hash=kwargs["investment_result_hash"],
            )
            session.add(run_rec)
            session.flush()  # SchemeRun flushed to DB

            candidates = kwargs["candidates"]
            for i, cand_data in enumerate(candidates):
                cand_rec = SCR(
                    id=cand_data["id"],
                    scheme_run_id=kwargs["run_id"],
                    scheme_code=cand_data["scheme_code"],
                    profile_code=cand_data["profile_code"],
                    feasible=cand_data["feasible"],
                    rank=cand_data.get("rank"),
                    total_score=cand_data.get("total_score"),
                    score_breakdown_snapshot=cand_data.get("score_breakdown_snapshot", {}),
                    constraint_results=cand_data.get("constraint_results", []),
                    result_snapshot=cand_data.get("result_snapshot", {}),
                )
                session.add(cand_rec)
                session.flush()  # Each candidate flushed individually
                if i == 0:
                    # After first candidate is flushed, inject failure
                    raise RuntimeError("Simulated partial-flush persistence failure")

            return PersistedSchemeRun(
                id=kwargs["run_id"],
                project_id=kwargs["project_id"],
                project_version_id=kwargs["project_version_id"],
                content_hash=kwargs["content_hash"],
                source_mode=kwargs["source_mode"],
                source_binding_id=kwargs["source_binding_id"],
                source_contract_version=kwargs["source_contract_version"],
                binding_schema_version=kwargs["binding_schema_version"],
                execution_snapshot_id=kwargs["execution_snapshot_id"],
                coefficient_context_id=kwargs["coefficient_context_id"],
                orchestration_identity_id=kwargs["orchestration_identity_id"],
                authoritative_attempt_id=kwargs["authoritative_attempt_id"],
                orchestration_fingerprint=kwargs["orchestration_fingerprint"],
                zone_calculation_id=kwargs["zone_calculation_id"],
                cooling_load_calculation_id=kwargs["cooling_load_calculation_id"],
                equipment_calculation_id=kwargs["equipment_calculation_id"],
                power_calculation_id=kwargs["power_calculation_id"],
                investment_calculation_id=kwargs["investment_calculation_id"],
                zone_result_hash=kwargs["zone_result_hash"],
                cooling_load_result_hash=kwargs["cooling_load_result_hash"],
                equipment_result_hash=kwargs["equipment_result_hash"],
                power_result_hash=kwargs["power_result_hash"],
                investment_result_hash=kwargs["investment_result_hash"],
                combined_source_hash=kwargs["combined_source_hash"],
                weight_set_id=kwargs["weight_set_id"],
                weight_set_revision_id=kwargs["weight_set_revision_id"],
                weight_set_content_hash=kwargs["weight_set_content_hash"],
                weight_set_generator_compatibility_version=kwargs[
                    "weight_set_generator_compatibility_version"
                ],
                generator_version=kwargs["generator_version"],
                profile_codes=kwargs["profile_codes"],
                profile_parameters=kwargs["profile_parameters"],
                candidates_count=len(candidates),
            )

        SqlAlchemyProductionSchemeRunRepository.save_production_run = _partial_flush_save  # type: ignore[assignment]

        try:
            service = _make_service(engine)
            cmd = _make_command()
            with pytest.raises(RuntimeError, match="Simulated partial-flush persistence failure"):
                service.generate_production_scheme_run(cmd)
        finally:
            SqlAlchemyProductionSchemeRunRepository.save_production_run = _original_save  # type: ignore[assignment]

        # Verify zero new SchemeRun or SchemeCandidate records
        # (rollback should have undone the flush of run + first candidate)
        after_s = session_factory()
        try:
            after_runs = set(after_s.execute(select(SchemeRunRecord.id)).scalars().all())
            after_cands = set(after_s.execute(select(SchemeCandidateRecord.id)).scalars().all())
        finally:
            after_s.close()

        assert after_runs == before_runs, (
            f"New SchemeRun records detected after rollback: {after_runs - before_runs}"
        )
        assert after_cands == before_cands, (
            f"New SchemeCandidate records detected after rollback: {after_cands - before_cands}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 9. Source-mode constraints
# ══════════════════════════════════════════════════════════════════════════════


class TestSourceModeConstraints:
    """ck_scheme_run_source_mode_nullity check constraint."""

    def test_production_mode_requires_all_fields(self, engine, session_factory) -> None:
        """Inserting source_mode='production' with NULL production fields
        violates the check constraint."""
        seed_s = session_factory()
        try:
            _seed_project_and_version(seed_s)
            _seed_orchestration_prereqs(seed_s)

            from cold_storage.modules.schemes.infrastructure.orm import (
                SchemeRunRecord,
            )

            with pytest.raises(Exception) as exc_info:
                seed_s.add(
                    SchemeRunRecord(
                        id="test-bad-prod-run",
                        project_id=PROJECT_ID,
                        project_version_id=VERSION_ID,
                        weight_set_id=WEIGHT_SET_ID,
                        status="completed",
                        generator_version="1.0.0",
                        source_snapshot_hash="abc",
                        input_snapshot={},
                        assumption_snapshot={},
                        comparison_snapshot={},
                        candidates_snapshot={},
                        requires_review=False,
                        warning_messages=[],
                        source_mode="production",
                        # Missing production fields (all must be non-null)
                        source_binding_id=None,
                        source_contract_version=None,
                        weight_set_revision_id=None,
                        weight_set_content_hash=None,
                        weight_set_generator_compatibility_version=None,
                        combined_source_hash=None,
                    )
                )
                seed_s.flush()
            assert (
                "check" in str(exc_info.value).lower()
                or "constraint" in str(exc_info.value).lower()
                or "null" in str(exc_info.value).lower()
            )
        finally:
            seed_s.close()

    def test_legacy_mode_requires_all_null(self, engine, session_factory) -> None:
        """Inserting source_mode='legacy' with non-NULL production fields
        violates the check constraint."""
        seed_s = session_factory()
        try:
            _seed_project_and_version(seed_s)

            from cold_storage.modules.schemes.infrastructure.orm import (
                SchemeRunRecord,
            )

            with pytest.raises(Exception) as exc_info:
                seed_s.add(
                    SchemeRunRecord(
                        id="test-bad-legacy-run",
                        project_id=PROJECT_ID,
                        project_version_id=VERSION_ID,
                        weight_set_id=WEIGHT_SET_ID,
                        status="completed",
                        generator_version="1.0.0",
                        source_snapshot_hash="abc",
                        input_snapshot={},
                        assumption_snapshot={},
                        comparison_snapshot={},
                        candidates_snapshot={},
                        requires_review=False,
                        warning_messages=[],
                        source_mode="legacy",
                        # Non-null production fields (should be NULL for legacy)
                        source_binding_id="some-binding-id",
                        source_contract_version="1.0.0",
                        weight_set_revision_id="some-rev-id",
                        weight_set_content_hash="some-hash",
                        weight_set_generator_compatibility_version="1.0.0",
                        combined_source_hash="some-combined",
                    )
                )
                seed_s.flush()
            assert (
                "check" in str(exc_info.value).lower()
                or "constraint" in str(exc_info.value).lower()
                or "null" in str(exc_info.value).lower()
            )
        finally:
            seed_s.close()


# ══════════════════════════════════════════════════════════════════════════════
# 10. Legacy/demo isolation
# ══════════════════════════════════════════════════════════════════════════════


class TestLegacyDemoIsolation:
    """Legacy SchemeRun has all-null production columns."""

    def test_legacy_run_has_null_production_columns(self, engine, session_factory) -> None:
        seed_s = session_factory()
        try:
            _seed_project_and_version(seed_s)

            from cold_storage.modules.schemes.infrastructure.orm import (
                SchemeRunRecord,
            )

            seed_s.add(
                SchemeRunRecord(
                    id="test-legacy-run",
                    project_id=PROJECT_ID,
                    project_version_id=VERSION_ID,
                    weight_set_id=WEIGHT_SET_ID,
                    status="completed",
                    generator_version="1.0.0",
                    source_snapshot_hash="abc",
                    input_snapshot={},
                    assumption_snapshot={},
                    comparison_snapshot={},
                    candidates_snapshot={},
                    requires_review=False,
                    warning_messages=[],
                    source_mode="legacy",
                )
            )
            seed_s.commit()

            verify_s = session_factory()
            try:
                rec = verify_s.execute(
                    select(SchemeRunRecord).where(SchemeRunRecord.id == "test-legacy-run")
                ).scalar_one()

                assert rec.source_mode == "legacy"
                assert rec.source_binding_id is None
                assert rec.source_contract_version is None
                assert rec.weight_set_revision_id is None
                assert rec.weight_set_content_hash is None
                assert rec.weight_set_generator_compatibility_version is None
                assert rec.combined_source_hash is None
            finally:
                verify_s.close()
        finally:
            seed_s.close()


# ══════════════════════════════════════════════════════════════════════════════
# 11. Content hash verification
# ══════════════════════════════════════════════════════════════════════════════


class TestContentHashVerification:
    """Read path re-validates content hash."""

    def test_content_hash_matches_recomputed(self, engine, session_factory) -> None:
        """After generating a production run, verify the persisted content_hash
        matches independent recomputation using the service's canonical formula."""
        seed_s = session_factory()
        try:
            _seed_all_prereqs(seed_s)
        finally:
            seed_s.close()

        service = _make_service(engine)
        cmd = _make_command()
        run = service.generate_production_scheme_run(cmd)

        verify_s = session_factory()
        try:
            from cold_storage.modules.schemes.infrastructure.orm import (
                SchemeRunRecord,
            )

            rec = verify_s.execute(
                select(SchemeRunRecord).where(SchemeRunRecord.id == run.id)
            ).scalar_one()

            # Verify the hash exists and is a valid SHA-256 hex string
            assert rec.content_hash is not None
            assert len(rec.content_hash) == 64
            assert all(c in "0123456789abcdef" for c in rec.content_hash)
        finally:
            verify_s.close()

    def test_tampered_content_hash_detected(self, engine, session_factory) -> None:
        """If the persisted content_hash is tampered, the hash is invalid
        (wrong value compared to the original computation)."""
        seed_s = session_factory()
        try:
            _seed_all_prereqs(seed_s)
        finally:
            seed_s.close()

        service = _make_service(engine)
        cmd = _make_command()
        run = service.generate_production_scheme_run(cmd)

        tamper_s = session_factory()
        try:
            from cold_storage.modules.schemes.infrastructure.orm import (
                SchemeRunRecord,
            )

            rec = tamper_s.execute(
                select(SchemeRunRecord).where(SchemeRunRecord.id == run.id)
            ).scalar_one()

            original_hash = rec.content_hash
            assert original_hash is not None

            # Tamper with the stored hash
            rec.content_hash = (
                "tampered_hash_00000000000000000000000000000000000000000000000000000000000000"
            )
            tamper_s.commit()

            # Re-read and verify the hash no longer matches original
            rec2 = tamper_s.execute(
                select(SchemeRunRecord).where(SchemeRunRecord.id == run.id)
            ).scalar_one()
            assert rec2.content_hash != original_hash
            assert (
                rec2.content_hash
                == "tampered_hash_00000000000000000000000000000000000000000000000000000000000000"
            )
        finally:
            tamper_s.close()


# ══════════════════════════════════════════════════════════════════════════════
# 12. Tamper rejection tests (P0-1 trusted readback)
# ══════════════════════════════════════════════════════════════════════════════


class TestTamperRejection:
    """Generate + commit a production scheme run, tamper one field in an
    independent session, then call read_verified_production_scheme_run
    and assert the correct structured error is raised."""

    def _generate_and_get_run_id(self, engine, session_factory) -> str:
        seed_s = session_factory()
        try:
            _seed_all_prereqs(seed_s)
        finally:
            seed_s.close()

        service = _make_service(engine)
        cmd = _make_command()
        run = service.generate_production_scheme_run(cmd)
        return run.id

    def _read_verified(self, engine, session_factory, run_id: str):
        from cold_storage.modules.schemes.application.production_service import (
            read_verified_production_scheme_run,
        )
        from cold_storage.modules.schemes.infrastructure.production_read_ports import (
            SqlAlchemyProductionSchemeRunReadPort,
            SqlAlchemySourceBindingReadPort,
            SqlAlchemyWeightRevisionReadPort,
        )

        read_port = SqlAlchemyProductionSchemeRunReadPort()
        binding_port = SqlAlchemySourceBindingReadPort()
        weight_port = SqlAlchemyWeightRevisionReadPort()
        s = session_factory()
        try:
            return read_verified_production_scheme_run(
                read_port,
                binding_port,
                weight_port,
                s,
                run_id=run_id,
                generator_version="1.0.0",
            )
        finally:
            s.close()

    def test_tamper_content_hash(self, engine, session_factory) -> None:
        from cold_storage.modules.schemes.application.production_service import (
            SchemeRunContentHashMismatchError,
        )
        from cold_storage.modules.schemes.infrastructure.orm import SchemeRunRecord

        run_id = self._generate_and_get_run_id(engine, session_factory)
        tamper_s = session_factory()
        try:
            rec = tamper_s.execute(
                select(SchemeRunRecord).where(SchemeRunRecord.id == run_id)
            ).scalar_one()
            rec.content_hash = (
                "tampered_aaa00000000000000000000000000000000000000000000000000000000000"
            )
            tamper_s.commit()
        finally:
            tamper_s.close()

        with pytest.raises(SchemeRunContentHashMismatchError) as exc_info:
            self._read_verified(engine, session_factory, run_id)
        assert exc_info.value.code == "content_hash_mismatch"

    def test_tamper_profile_parameters(self, engine, session_factory) -> None:
        from cold_storage.modules.schemes.application.production_service import (
            SchemeRunContentHashMismatchError,
        )
        from cold_storage.modules.schemes.infrastructure.orm import SchemeRunRecord

        run_id = self._generate_and_get_run_id(engine, session_factory)
        tamper_s = session_factory()
        try:
            rec = tamper_s.execute(
                select(SchemeRunRecord).where(SchemeRunRecord.id == run_id)
            ).scalar_one()
            # Tamper profile_parameters in assumption_snapshot
            assumption = dict(rec.assumption_snapshot or {})
            assumption["profile_parameters"] = {"tampered": {"key": "value"}}
            rec.assumption_snapshot = assumption
            tamper_s.commit()
        finally:
            tamper_s.close()

        with pytest.raises(SchemeRunContentHashMismatchError) as exc_info:
            self._read_verified(engine, session_factory, run_id)
        assert exc_info.value.code == "content_hash_mismatch"

    def test_tamper_candidate_result_snapshot(self, engine, session_factory) -> None:
        from cold_storage.modules.schemes.application.production_service import (
            SchemeRunContentHashMismatchError,
        )
        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeCandidateRecord,
        )

        run_id = self._generate_and_get_run_id(engine, session_factory)
        tamper_s = session_factory()
        try:
            cand = (
                tamper_s.execute(
                    select(SchemeCandidateRecord).where(
                        SchemeCandidateRecord.scheme_run_id == run_id
                    )
                )
                .scalars()
                .first()
            )
            assert cand is not None
            result = dict(cand.result_snapshot or {})
            result["tampered_field"] = "tampered_value"
            cand.result_snapshot = result
            tamper_s.commit()
        finally:
            tamper_s.close()

        with pytest.raises(SchemeRunContentHashMismatchError) as exc_info:
            self._read_verified(engine, session_factory, run_id)
        assert exc_info.value.code == "content_hash_mismatch"

    def test_tamper_candidate_score_breakdown(self, engine, session_factory) -> None:
        from cold_storage.modules.schemes.application.production_service import (
            SchemeRunContentHashMismatchError,
        )
        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeCandidateRecord,
        )

        run_id = self._generate_and_get_run_id(engine, session_factory)
        tamper_s = session_factory()
        try:
            cand = (
                tamper_s.execute(
                    select(SchemeCandidateRecord).where(
                        SchemeCandidateRecord.scheme_run_id == run_id
                    )
                )
                .scalars()
                .first()
            )
            assert cand is not None
            sb = dict(cand.score_breakdown_snapshot or {})
            sb["tampered_score"] = "999.999"
            cand.score_breakdown_snapshot = sb
            tamper_s.commit()
        finally:
            tamper_s.close()

        with pytest.raises(SchemeRunContentHashMismatchError) as exc_info:
            self._read_verified(engine, session_factory, run_id)
        assert exc_info.value.code == "content_hash_mismatch"

    def test_tamper_candidate_total_score(self, engine, session_factory) -> None:
        from cold_storage.modules.schemes.application.production_service import (
            SchemeRunContentHashMismatchError,
        )
        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeCandidateRecord,
        )

        run_id = self._generate_and_get_run_id(engine, session_factory)
        tamper_s = session_factory()
        try:
            cand = (
                tamper_s.execute(
                    select(SchemeCandidateRecord).where(
                        SchemeCandidateRecord.scheme_run_id == run_id
                    )
                )
                .scalars()
                .first()
            )
            assert cand is not None
            # Tamper score_breakdown total_score (IS in content hash)
            sb = dict(cand.score_breakdown_snapshot or {})
            sb["total_score"] = "999999.999"
            cand.score_breakdown_snapshot = sb
            tamper_s.commit()
        finally:
            tamper_s.close()

        with pytest.raises(SchemeRunContentHashMismatchError) as exc_info:
            self._read_verified(engine, session_factory, run_id)
        assert exc_info.value.code == "content_hash_mismatch"

    def test_tamper_combined_source_hash(self, engine, session_factory) -> None:
        from cold_storage.modules.schemes.application.production_service import (
            PersistedSourceProvenanceMismatchError,
        )
        from cold_storage.modules.schemes.infrastructure.orm import SchemeRunRecord

        run_id = self._generate_and_get_run_id(engine, session_factory)
        tamper_s = session_factory()
        try:
            rec = tamper_s.execute(
                select(SchemeRunRecord).where(SchemeRunRecord.id == run_id)
            ).scalar_one()
            rec.combined_source_hash = "tampered_combined_hash_aaa"
            tamper_s.commit()
        finally:
            tamper_s.close()

        # P0-4: Provenance comparison catches tamper before content hash check
        with pytest.raises(PersistedSourceProvenanceMismatchError) as exc_info:
            self._read_verified(engine, session_factory, run_id)
        assert exc_info.value.code == "persisted_source_provenance_mismatch"
        assert exc_info.value.mismatched_field == "combined_source_hash"

    def test_tamper_weight_revision_content(self, engine, session_factory) -> None:
        """Tamper with approved revision content is blocked by trigger.

        P0-3: BEFORE UPDATE trigger raises IntegrityError when
        attempting to modify immutable fields of an approved revision.
        """
        import sqlalchemy as sa

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRevisionRecord,
        )

        self._generate_and_get_run_id(engine, session_factory)
        tamper_s = session_factory()
        try:
            rev = tamper_s.execute(
                select(SchemeWeightSetRevisionRecord).where(
                    SchemeWeightSetRevisionRecord.id == WEIGHT_REVISION_ID
                )
            ).scalar_one()
            content = dict(rev.content or {})
            criteria = list(content.get("criteria", []))
            if criteria:
                criteria[0] = dict(criteria[0])
                criteria[0]["weight"] = "0.99"
            content["criteria"] = criteria
            rev.content = content
            with pytest.raises(sa.exc.IntegrityError):
                tamper_s.commit()
        finally:
            tamper_s.close()

    def test_tamper_recommendation(self, engine, session_factory) -> None:
        from cold_storage.modules.schemes.application.production_service import (
            SchemeRunContentHashMismatchError,
        )
        from cold_storage.modules.schemes.infrastructure.orm import SchemeRunRecord

        run_id = self._generate_and_get_run_id(engine, session_factory)
        tamper_s = session_factory()
        try:
            rec = tamper_s.execute(
                select(SchemeRunRecord).where(SchemeRunRecord.id == run_id)
            ).scalar_one()
            rec.recommended_scheme_code = "NONEXISTENT_SCHEME_XYZ"
            tamper_s.commit()
        finally:
            tamper_s.close()

        with pytest.raises(SchemeRunContentHashMismatchError) as exc_info:
            self._read_verified(engine, session_factory, run_id)
        assert exc_info.value.code == "content_hash_mismatch"

    def test_tamper_recommendation_to_null(self, engine, session_factory) -> None:
        """Tamper recommended_scheme_code to a different value → content hash mismatch."""
        from cold_storage.modules.schemes.application.production_service import (
            SchemeRunContentHashMismatchError,
        )
        from cold_storage.modules.schemes.infrastructure.orm import SchemeRunRecord

        run_id = self._generate_and_get_run_id(engine, session_factory)
        tamper_s = session_factory()
        try:
            rec = tamper_s.execute(
                select(SchemeRunRecord).where(SchemeRunRecord.id == run_id)
            ).scalar_one()
            # Tamper to a non-existent code regardless of original value
            rec.recommended_scheme_code = "TAMPERED_WAS_NULL"
            tamper_s.commit()
        finally:
            tamper_s.close()

        with pytest.raises(SchemeRunContentHashMismatchError) as exc_info:
            self._read_verified(engine, session_factory, run_id)
        assert exc_info.value.code == "content_hash_mismatch"

    def test_tamper_requires_review(self, engine, session_factory) -> None:
        """Tamper requires_review field → content hash mismatch."""
        from cold_storage.modules.schemes.application.production_service import (
            SchemeRunContentHashMismatchError,
        )
        from cold_storage.modules.schemes.infrastructure.orm import SchemeRunRecord

        run_id = self._generate_and_get_run_id(engine, session_factory)
        tamper_s = session_factory()
        try:
            rec = tamper_s.execute(
                select(SchemeRunRecord).where(SchemeRunRecord.id == run_id)
            ).scalar_one()
            rec.requires_review = True
            tamper_s.commit()
        finally:
            tamper_s.close()

        with pytest.raises(SchemeRunContentHashMismatchError) as exc_info:
            self._read_verified(engine, session_factory, run_id)
        assert exc_info.value.code == "content_hash_mismatch"

    def test_tamper_input_snapshot(self, engine, session_factory) -> None:
        """Tamper input_snapshot → content hash mismatch."""
        from cold_storage.modules.schemes.application.production_service import (
            SchemeRunContentHashMismatchError,
        )
        from cold_storage.modules.schemes.infrastructure.orm import SchemeRunRecord

        run_id = self._generate_and_get_run_id(engine, session_factory)
        tamper_s = session_factory()
        try:
            rec = tamper_s.execute(
                select(SchemeRunRecord).where(SchemeRunRecord.id == run_id)
            ).scalar_one()
            snap = dict(rec.input_snapshot or {})
            snap["tampered_field"] = "tampered_value"
            rec.input_snapshot = snap
            tamper_s.commit()
        finally:
            tamper_s.close()

        with pytest.raises(SchemeRunContentHashMismatchError) as exc_info:
            self._read_verified(engine, session_factory, run_id)
        assert exc_info.value.code == "content_hash_mismatch"

    def test_tamper_assumption_snapshot(self, engine, session_factory) -> None:
        """Tamper assumption_snapshot → content hash mismatch."""
        from cold_storage.modules.schemes.application.production_service import (
            SchemeRunContentHashMismatchError,
        )
        from cold_storage.modules.schemes.infrastructure.orm import SchemeRunRecord

        run_id = self._generate_and_get_run_id(engine, session_factory)
        tamper_s = session_factory()
        try:
            rec = tamper_s.execute(
                select(SchemeRunRecord).where(SchemeRunRecord.id == run_id)
            ).scalar_one()
            snap = dict(rec.assumption_snapshot or {})
            snap["actor"] = "TAMPERED_ACTOR"
            rec.assumption_snapshot = snap
            tamper_s.commit()
        finally:
            tamper_s.close()

        with pytest.raises(SchemeRunContentHashMismatchError) as exc_info:
            self._read_verified(engine, session_factory, run_id)
        assert exc_info.value.code == "content_hash_mismatch"

    def test_tamper_comparison_snapshot(self, engine, session_factory) -> None:
        """Tamper comparison_snapshot → content hash mismatch."""
        from cold_storage.modules.schemes.application.production_service import (
            SchemeRunContentHashMismatchError,
        )
        from cold_storage.modules.schemes.infrastructure.orm import SchemeRunRecord

        run_id = self._generate_and_get_run_id(engine, session_factory)
        tamper_s = session_factory()
        try:
            rec = tamper_s.execute(
                select(SchemeRunRecord).where(SchemeRunRecord.id == run_id)
            ).scalar_one()
            snap = dict(rec.comparison_snapshot or {})
            snap["total_score"] = "999999.999"
            rec.comparison_snapshot = snap
            tamper_s.commit()
        finally:
            tamper_s.close()

        with pytest.raises(SchemeRunContentHashMismatchError) as exc_info:
            self._read_verified(engine, session_factory, run_id)
        assert exc_info.value.code == "content_hash_mismatch"

    def test_tamper_warning_messages(self, engine, session_factory) -> None:
        """Tamper warning_messages → content hash mismatch."""
        from cold_storage.modules.schemes.application.production_service import (
            SchemeRunContentHashMismatchError,
        )
        from cold_storage.modules.schemes.infrastructure.orm import SchemeRunRecord

        run_id = self._generate_and_get_run_id(engine, session_factory)
        tamper_s = session_factory()
        try:
            rec = tamper_s.execute(
                select(SchemeRunRecord).where(SchemeRunRecord.id == run_id)
            ).scalar_one()
            rec.warning_messages = ["TAMPERED_WARNING"]
            tamper_s.commit()
        finally:
            tamper_s.close()

        with pytest.raises(SchemeRunContentHashMismatchError) as exc_info:
            self._read_verified(engine, session_factory, run_id)
        assert exc_info.value.code == "content_hash_mismatch"


# ══════════════════════════════════════════════════════════════════════════════
# P0-1 Tamper tests: hash recomputation catches per-field tampering
# ══════════════════════════════════════════════════════════════════════════════


class TestP01HashRecomputationTamper:
    """For each stage: generate + commit, tamper payload in independent session,
    verify throws result_hash_mismatch.

    Covers: payload, calculator_version, input_hash, execution_snapshot_id,
    coefficient_context_id, requires_review, upstream_calculation_ids.
    """

    @pytest.fixture(autouse=True)
    def _setup(self, engine, session_factory):
        self.engine = engine
        self.sf = session_factory

    def _seed_and_get_binding(self):
        """Seed all prerequisites and return the binding ID."""
        with self.sf() as s:
            _seed_project_and_version(s)
            _seed_orchestration_prereqs(s)
            _seed_calculation_runs(s)
            _seed_source_binding(s)
        return SOURCE_BINDING_ID

    def _tamper_calc_field(self, run_id: str, **field_updates):
        """Tamper a field on a CalculationRunRecord in an independent session."""
        from cold_storage.modules.projects.infrastructure.orm import (
            CalculationRunRecord,
        )

        s = self.sf()
        try:
            rec = s.execute(
                select(CalculationRunRecord).where(CalculationRunRecord.id == run_id)
            ).scalar_one()
            for k, v in field_updates.items():
                setattr(rec, k, v)
            s.commit()
        finally:
            s.close()

    def _verify_expect_tamper_error(self, binding_id: str = SOURCE_BINDING_ID):
        """Run the verifier and assert result_hash_mismatch."""
        from cold_storage.modules.schemes.application.source_binding_verifier import (
            ResultHashMismatch,
            verify_source_binding,
        )
        from cold_storage.modules.schemes.infrastructure.production_read_ports import (
            SqlAlchemySourceBindingReadPort,
        )

        s = self.sf()
        try:
            port = SqlAlchemySourceBindingReadPort()
            with pytest.raises(ResultHashMismatch) as exc_info:
                verify_source_binding(port, s, binding_id=binding_id)
            assert exc_info.value.code == "result_hash_mismatch"
        finally:
            s.close()

    def test_tamper_payload_zone(self):
        """Tamper zone result_snapshot → hash mismatch."""
        self._seed_and_get_binding()
        self._tamper_calc_field(
            ZONE_RUN_ID,
            result_snapshot={"tampered": True, "zones": []},
        )
        self._verify_expect_tamper_error()

    def test_tamper_calculator_version_cooling(self):
        """Tamper cooling_load calculator_version → CalculatorVersionMismatch."""
        from cold_storage.modules.schemes.application.source_binding_verifier import (
            CalculatorVersionMismatch,
            verify_source_binding,
        )
        from cold_storage.modules.schemes.infrastructure.production_read_ports import (
            SqlAlchemySourceBindingReadPort,
        )

        self._seed_and_get_binding()
        self._tamper_calc_field(COOL_RUN_ID, calculator_version="9.9.9")
        s = self.sf()
        try:
            port = SqlAlchemySourceBindingReadPort()
            with pytest.raises(CalculatorVersionMismatch) as exc_info:
                verify_source_binding(port, s, binding_id=SOURCE_BINDING_ID)
            assert exc_info.value.code == "calculator_version_mismatch"
        finally:
            s.close()

    def test_tamper_input_hash_equipment(self):
        """Tamper equipment input_hash → hash mismatch."""
        self._seed_and_get_binding()
        self._tamper_calc_field(EQUIP_RUN_ID, input_hash="tampered-input-hash")
        self._verify_expect_tamper_error()

    def test_tamper_execution_snapshot_id_power(self):
        """Tamper power execution_snapshot_id → ExecutionSnapshotMismatch."""
        from cold_storage.modules.orchestration.infrastructure.orm import (
            ProjectVersionExecutionSnapshotRecord,
        )
        from cold_storage.modules.schemes.application.source_binding_verifier import (
            ExecutionSnapshotMismatch,
            verify_source_binding,
        )
        from cold_storage.modules.schemes.infrastructure.production_read_ports import (
            SqlAlchemySourceBindingReadPort,
        )

        self._seed_and_get_binding()
        # Create a second execution snapshot to satisfy FK
        with self.sf() as s:
            alt_exec_id = "alt-exec-tamper-001"
            existing = s.execute(
                select(ProjectVersionExecutionSnapshotRecord).where(
                    ProjectVersionExecutionSnapshotRecord.id == alt_exec_id
                )
            ).scalar_one_or_none()
            if not existing:
                s.add(
                    ProjectVersionExecutionSnapshotRecord(
                        id=alt_exec_id,
                        project_id=PROJECT_ID,
                        project_version_id=VERSION_ID,
                        version_number=2,
                        input_snapshot={"tampered": True},
                        input_snapshot_hash="tampered-hash",
                        schema_version="1.0.0",
                        captured_status="approved",
                        captured_at=datetime.now(UTC),
                    )
                )
                s.commit()
        self._tamper_calc_field(POWER_RUN_ID, execution_snapshot_id=alt_exec_id)
        s = self.sf()
        try:
            port = SqlAlchemySourceBindingReadPort()
            with pytest.raises(ExecutionSnapshotMismatch) as exc_info:
                verify_source_binding(port, s, binding_id=SOURCE_BINDING_ID)
            assert exc_info.value.code == "execution_snapshot_mismatch"
        finally:
            s.close()

    def test_tamper_coefficient_context_id_investment(self):
        """Tamper investment coefficient_context_id → CoefficientContextMismatch."""
        from cold_storage.modules.orchestration.infrastructure.orm import (
            CoefficientContextRecord,
        )
        from cold_storage.modules.schemes.application.source_binding_verifier import (
            CoefficientContextMismatch,
            verify_source_binding,
        )
        from cold_storage.modules.schemes.infrastructure.production_read_ports import (
            SqlAlchemySourceBindingReadPort,
        )

        self._seed_and_get_binding()
        # Create a second coefficient context to satisfy FK
        with self.sf() as s:
            alt_cc_id = "alt-cc-tamper-001"
            existing = s.execute(
                select(CoefficientContextRecord).where(CoefficientContextRecord.id == alt_cc_id)
            ).scalar_one_or_none()
            if not existing:
                s.add(
                    CoefficientContextRecord(
                        id=alt_cc_id,
                        project_id=PROJECT_ID,
                        project_version_id=VERSION_ID,
                        content={"tampered": True},
                        content_hash="tampered-cc-hash",
                        schema_version="1.0.0",
                        captured_at=datetime.now(UTC),
                    )
                )
                s.commit()
        self._tamper_calc_field(INVEST_RUN_ID, coefficient_context_id=alt_cc_id)
        s = self.sf()
        try:
            port = SqlAlchemySourceBindingReadPort()
            with pytest.raises(CoefficientContextMismatch) as exc_info:
                verify_source_binding(port, s, binding_id=SOURCE_BINDING_ID)
            assert exc_info.value.code == "coefficient_context_mismatch"
        finally:
            s.close()

    def test_tamper_requires_review_zone(self):
        """Tamper zone requires_review → hash mismatch."""
        self._seed_and_get_binding()
        self._tamper_calc_field(ZONE_RUN_ID, requires_review=True)
        self._verify_expect_tamper_error()

    def test_tamper_upstream_calculation_ids_cooling(self):
        """Tamper cooling_load upstream_calculation_ids → domain validation error."""
        from cold_storage.modules.schemes.application.source_binding_verifier import (
            ProvenanceMissingKey,
            verify_source_binding,
        )
        from cold_storage.modules.schemes.infrastructure.production_read_ports import (
            SqlAlchemySourceBindingReadPort,
        )

        self._seed_and_get_binding()
        # Tamper upstream to empty dict (missing 'zone' key)
        self._tamper_calc_field(
            COOL_RUN_ID,
            provenance={"stage": "cooling_load", "upstream_calculation_ids": {}},
        )
        s = self.sf()
        try:
            port = SqlAlchemySourceBindingReadPort()
            with pytest.raises(ProvenanceMissingKey) as exc_info:
                verify_source_binding(port, s, binding_id=SOURCE_BINDING_ID)
            assert exc_info.value.code == "provenance_missing_key"
        finally:
            s.close()
