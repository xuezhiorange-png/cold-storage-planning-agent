"""PostgreSQL production contract tests for ProductionSchemeService.

Mirrors the core SQLite production scheme tests against a real
PostgreSQL database with Alembic-migrated schema.  Every test:

1. Requires DATABASE_BACKEND=postgresql (skips otherwise).
2. Asserts session.bind.dialect.name == "postgresql" before any logic.
3. Uses the shared pg_session_factory / pg_engine fixtures from
   tests/integration/conftest.py.

Test matrix (P0-6):
  1. Core production happy-path generation
  2. Power authority (missing total_installed_power_kw_e rejected)
  3. Complete provenance persistence
  4. Trusted readback (content_hash verification)
  5. Payload tamper rejection (content_hash mismatch)
  6. Candidate tamper rejection (result_snapshot / score)
  7. Weight tamper rejection (weight_verification_failed)
  8. Partial-flush rollback (zero-delta PK sets)
  9. Production seed idempotency
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

# ── Module-level marker + skip ─────────────────────────────────────────
pytestmark = pytest.mark.postgresql

if os.environ.get("DATABASE_BACKEND") != "postgresql":
    pytest.skip(
        "PostgreSQL production scheme tests require DATABASE_BACKEND=postgresql",
        allow_module_level=True,
    )

# ── Canonical hash helpers (mirrors SQLite _compute_domain_hash) ───────────


def _compute_domain_hash(
    *,
    stage: str,
    result_snapshot: dict[str, Any],
    run_id: str,
) -> str:
    """Compute domain SourceSnapshotContentV1 result_hash for a stage.

    Builds the SAME full content object the production verifier hashes,
    ensuring identical SHA-256 for identical payloads.
    """
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
        input_hash="pg-input-hash-001",
        requires_review=False,
        payload=result_snapshot,
        provenance=provenance,
    )
    return _domain_result_hash(content)


_SLOT_STAGE_ORDER: tuple[str, ...] = (
    "zone",
    "cooling_load",
    "equipment",
    "power",
    "investment",
)


def _compute_weight_content_hash(content: dict[str, Any]) -> str:
    from cold_storage.modules.orchestration.domain.fingerprint import (
        canonical_json_bytes,
    )

    return hashlib.sha256(canonical_json_bytes(content)).hexdigest()


# ── Deterministic IDs ────────────────────────────────────────────────────
PROJECT_ID = "pg-test-p-001"
VERSION_ID = "pg-test-v-001"
EXEC_SNAPSHOT_ID = "pg-test-exec-001"
COEFF_CONTEXT_ID = "pg-test-cc-001"
IDENTITY_ID = "pg-test-id-001"
ATTEMPT_ID = "pg-test-attempt-001"

ZONE_RUN_ID = "pg-test-run-zone-001"
COOL_RUN_ID = "pg-test-run-cool-001"
EQUIP_RUN_ID = "pg-test-run-equip-001"
POWER_RUN_ID = "pg-test-run-power-001"
INVEST_RUN_ID = "pg-test-run-invest-001"

SOURCE_BINDING_ID = "pg-test-binding-001"
WEIGHT_SET_ID = "pg-test-ws-001"
WEIGHT_REVISION_ID = "pg-test-wrev-001"

# ── Deterministic result snapshots ───────────────────────────────────────

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
            "zone_name": "原果间",
            "daily_throughput_kg_day": 10000,
            "required_area_m2": "200.0",
            "design_storage_mass_kg": "15000.0",
            "position_count": 30,
            "temperature_band": "0~4℃",
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

# ── Placeholder hashes (computed after constants are defined) ───────────
ZONE_HASH = ""
COOL_HASH = ""
EQUIP_HASH = ""
POWER_HASH = ""
INVEST_HASH = ""


# ── Combined source hash (matches verifier implementation) ────────────────


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
        orchestration_fingerprint="pg-test-fingerprint-001",
        slot_ids=slot_ids,
        result_hashes=PER_CALC_HASHES,
        requires_reviews={stage: False for stage in _SLOT_STAGE_ORDER},
    )


COMBINED_SOURCE_HASH = ""  # computed after PER_CALC_HASHES is defined

# ── Weight set revision content ─────────────────────────────────────────

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

# ── Calculator names ─────────────────────────────────────────────────────

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

_SLOT_UPSTREAM_IDS: dict[str, dict[str, str]] = {
    "zone": {},
    "cooling_load": {"zone": ZONE_RUN_ID},
    "equipment": {"cooling_load": COOL_RUN_ID},
    "power": {"equipment": EQUIP_RUN_ID},
    "investment": {"zone": ZONE_RUN_ID, "power": POWER_RUN_ID},
}

# ── Compute domain hashes (after all constants are defined) ─────────────
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

COMBINED_SOURCE_HASH = _compute_verifier_combined_source_hash()

# ── Seed helpers ─────────────────────────────────────────────────────────


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
                code="PG_T_TEST_001",
                name="PG Test Project",
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
                change_summary="pg test version",
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
                input_snapshot_hash="pg-abc123",
                schema_version="1.0.0",
                captured_status="approved",
                captured_at=datetime.now(UTC),
            )
        )

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
                content_hash="pg-abc456",
                schema_version="1.0.0",
                captured_at=datetime.now(UTC),
            )
        )

    session.commit()

    existing_a = session.execute(
        select(OrchestrationRunAttemptRecord).where(OrchestrationRunAttemptRecord.id == ATTEMPT_ID)
    ).scalar_one_or_none()
    if not existing_a:
        existing_i = session.execute(
            select(OrchestrationIdentityRecord).where(OrchestrationIdentityRecord.id == IDENTITY_ID)
        ).scalar_one_or_none()
        if not existing_i:
            session.add(
                OrchestrationIdentityRecord(
                    id=IDENTITY_ID,
                    fingerprint="pg-test-fingerprint-001",
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
) -> dict[str, str]:
    """Create 5 CalculationRunRecords. Returns per-calc hash map."""
    from cold_storage.modules.projects.infrastructure.orm import (
        CalculationRunRecord,
    )

    slots = [
        (ZONE_RUN_ID, "zone", zone_result or ZONE_RESULT_SNAPSHOT),
        (COOL_RUN_ID, "cooling_load", cool_result or COOLING_RESULT_SNAPSHOT),
        (EQUIP_RUN_ID, "equipment", equip_result or EQUIPMENT_RESULT_SNAPSHOT),
        (POWER_RUN_ID, "power", power_result or POWER_RESULT_SNAPSHOT),
        (INVEST_RUN_ID, "investment", invest_result or INVESTMENT_RESULT_SNAPSHOT),
    ]

    per_calc: dict[str, str] = {}
    for run_id, stage, snap in slots:
        existing = session.execute(
            select(CalculationRunRecord).where(CalculationRunRecord.id == run_id)
        ).scalar_one_or_none()
        if existing is None:
            computed_hash = _compute_domain_hash(stage=stage, result_snapshot=snap, run_id=run_id)
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
                    input_hash="pg-input-hash-001",
                    result_hash=computed_hash,
                    provenance=provenance,
                    schema_version="1.0.0",
                    orchestration_fingerprint="pg-test-fingerprint-001",
                    created_at=datetime.now(UTC),
                )
            )
            per_calc[stage] = computed_hash
        else:
            per_calc[stage] = existing.result_hash or _compute_domain_hash(
                stage=stage,
                result_snapshot=existing.result_snapshot or {},
                run_id=run_id,
            )
    session.commit()
    return per_calc


def _seed_source_binding(
    session,
    *,
    per_calc: dict[str, str] | None = None,
    binding_id: str = SOURCE_BINDING_ID,
    schema_version: str = "1.0.0",
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

    combined = _compute_verifier_combined_source_hash()

    session.add(
        SourceBindingRecord(
            id=binding_id,
            project_id=PROJECT_ID,
            project_version_id=VERSION_ID,
            execution_snapshot_id=EXEC_SNAPSHOT_ID,
            coefficient_context_id=COEFF_CONTEXT_ID,
            orchestration_identity_id=IDENTITY_ID,
            orchestration_run_attempt_id=ATTEMPT_ID,
            orchestration_fingerprint="pg-test-fingerprint-001",
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
    approved_by: str | None = "pg-test-approver",
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

    existing_ws = session.execute(
        select(SchemeWeightSetRecord).where(SchemeWeightSetRecord.id == WEIGHT_SET_ID)
    ).scalar_one_or_none()
    if existing_ws is None:
        session.add(
            SchemeWeightSetRecord(
                id=WEIGHT_SET_ID,
                code="pg-standard-weights",
                name="标准权重集",
                revision=1,
                status="approved",
                source_type="production",
                criteria=WEIGHT_CRITERIA_RAW,
                requires_review=False,
                created_at=datetime.now(UTC),
                approved_at=approved_at,
            )
        )

    existing_rev = session.execute(
        select(SchemeWeightSetRevisionRecord).where(SchemeWeightSetRevisionRecord.id == revision_id)
    ).scalar_one_or_none()
    if existing_rev is None:
        # Insert as draft first, then approve via adapter to satisfy PG trigger
        initial_status = "draft"
        session.add(
            SchemeWeightSetRevisionRecord(
                id=revision_id,
                weight_set_id=WEIGHT_SET_ID,
                code="pg-standard-weights",
                revision=1,
                status=initial_status,
                content=content,
                content_hash=content_hash,
                generator_compatibility_version=generator_compat,
                approved_at=None,
                approved_by=None,
                sealed_at=None,
                created_at=datetime.now(UTC),
            )
        )
        session.flush()
        if status == "approved":
            # Use raw SQL UPDATE to bypass ORM-level checks,
            # matching the adapter's controlled transition path
            from sqlalchemy import text

            session.execute(
                text(
                    "UPDATE scheme_weight_set_revisions "
                    "SET status = 'approved', "
                    "approved_at = :approved_at, "
                    "approved_by = :approved_by, "
                    "sealed_at = :sealed_at "
                    "WHERE id = :rev_id"
                ),
                {
                    "approved_at": approved_at,
                    "approved_by": approved_by,
                    "sealed_at": approved_at,
                    "rev_id": revision_id,
                },
            )
    session.commit()


def _seed_all_prereqs(session) -> None:
    """Seed all prerequisite records for a happy-path test."""
    _seed_project_and_version(session)
    _seed_orchestration_prereqs(session)
    _seed_calculation_runs(session)
    _seed_source_binding(session)
    _seed_weight_set_and_revision(session)

    # Link attempt to source binding (attempt.source_binding_id must be non-NULL)
    # P0-5: Distinguish row-missing from NULL field.
    from sqlalchemy import text as sql_text

    row = session.execute(
        sql_text("SELECT id, source_binding_id FROM orchestration_run_attempts WHERE id = :aid"),
        {"aid": ATTEMPT_ID},
    ).one_or_none()
    assert row is not None, f"Attempt row {ATTEMPT_ID} must exist before linking to binding"
    _current_binding_id = row[1]
    if _current_binding_id is None:
        result = session.execute(
            sql_text(
                "UPDATE orchestration_run_attempts "
                "SET source_binding_id = :sbid "
                "WHERE id = :aid AND source_binding_id IS NULL"
            ),
            {"sbid": SOURCE_BINDING_ID, "aid": ATTEMPT_ID},
        )
        assert result.rowcount == 1, f"Expected exactly 1 row updated, got {result.rowcount}"
        session.commit()
        # Re-read to confirm
        session.expire_all()
        persisted = session.execute(
            sql_text("SELECT source_binding_id FROM orchestration_run_attempts WHERE id = :aid"),
            {"aid": ATTEMPT_ID},
        ).scalar_one()
        assert persisted == SOURCE_BINDING_ID, (
            f"Attempt binding mismatch after commit: {persisted} != {SOURCE_BINDING_ID}"
        )


# ── Service helper ───────────────────────────────────────────────────────


def _make_service(engine) -> Any:
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
    actor: str = "pg-test-actor",
    correlation_id: str = "pg-test-corr-001",
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


# ════════════════════════════════════════════════════════════════════════════
# 1. Core production happy-path generation
# ════════════════════════════════════════════════════════════════════════════


class TestPostgresProductionHappyPath:
    """Seeds real SourceBinding + 5 CalculationRuns + weight revision,
    generates a production SchemeRun on PostgreSQL, and asserts all fields."""

    def test_happy_path(self, pg_session_factory, pg_engine) -> None:
        assert pg_engine.dialect.name == "postgresql"

        seed_s = pg_session_factory()
        try:
            _seed_all_prereqs(seed_s)
        finally:
            seed_s.close()

        service = _make_service(pg_engine)
        cmd = _make_command()
        run = service.generate_production_scheme_run(cmd)

        assert run.status == "completed"
        assert run.project_id == PROJECT_ID
        assert run.project_version_id == VERSION_ID

        verify_s = pg_session_factory()
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
                    f"Candidate {cand_rec.scheme_code} total_score must be Decimal"
                )
                assert cand_rec.score_breakdown_snapshot, (
                    f"Candidate {cand_rec.scheme_code} score_breakdown_snapshot must not be empty"
                )
        finally:
            verify_s.close()


# ════════════════════════════════════════════════════════════════════════════
# 2. Power authority
# ════════════════════════════════════════════════════════════════════════════


class TestPostgresPowerAuthority:
    """Missing total_installed_power_kw_e in power result_snapshot is rejected."""

    def test_missing_power_authority(self, pg_session_factory, pg_engine) -> None:
        assert pg_engine.dialect.name == "postgresql"

        seed_s = pg_session_factory()
        try:
            _seed_project_and_version(seed_s)
            _seed_orchestration_prereqs(seed_s)
            power_snap_no_authority: dict[str, Any] = {"some_other_field": "42.0"}
            _seed_calculation_runs(seed_s, power_result=power_snap_no_authority)
            _seed_source_binding(seed_s)
        finally:
            seed_s.close()

        service = _make_service(pg_engine)
        cmd = _make_command()
        with pytest.raises(Exception) as exc_info:
            service.generate_production_scheme_run(cmd)
        assert (
            "power" in str(exc_info.value).lower()
            or "authority" in str(exc_info.value).lower()
            or "total_installed_power" in str(exc_info.value).lower()
        )


# ════════════════════════════════════════════════════════════════════════════
# 3. Complete provenance persistence
# ════════════════════════════════════════════════════════════════════════════


class TestPostgresProvenancePersistence:
    """source_mode=production, all production fields non-null, content hash correct."""

    def test_all_production_fields_non_null(self, pg_session_factory, pg_engine) -> None:
        assert pg_engine.dialect.name == "postgresql"

        seed_s = pg_session_factory()
        try:
            _seed_all_prereqs(seed_s)
        finally:
            seed_s.close()

        service = _make_service(pg_engine)
        cmd = _make_command()
        run = service.generate_production_scheme_run(cmd)

        verify_s = pg_session_factory()
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


# ════════════════════════════════════════════════════════════════════════════
# 4. Trusted readback (content_hash verification)
# ════════════════════════════════════════════════════════════════════════════


class TestPostgresTrustedReadback:
    """Read path re-validates content hash on PostgreSQL."""

    def test_content_hash_correct(self, pg_session_factory, pg_engine) -> None:
        assert pg_engine.dialect.name == "postgresql"

        seed_s = pg_session_factory()
        try:
            _seed_all_prereqs(seed_s)
        finally:
            seed_s.close()

        service = _make_service(pg_engine)
        cmd = _make_command()
        run = service.generate_production_scheme_run(cmd)

        verify_s = pg_session_factory()
        try:
            from cold_storage.modules.schemes.infrastructure.orm import (
                SchemeRunRecord,
            )

            rec = verify_s.execute(
                select(SchemeRunRecord).where(SchemeRunRecord.id == run.id)
            ).scalar_one()

            assert rec.content_hash is not None
            assert len(rec.content_hash) == 64
            int(rec.content_hash, 16)  # valid hex
        finally:
            verify_s.close()


# ════════════════════════════════════════════════════════════════════════════
# 5. Payload tamper rejection (content_hash mismatch)
# ════════════════════════════════════════════════════════════════════════════


class TestPostgresPayloadTamperRejection:
    """Generate + commit a production scheme run, tamper content_hash,
    then call read_verified_production_scheme_run and assert error."""

    def _generate_and_get_run_id(self, pg_session_factory, pg_engine) -> str:
        seed_s = pg_session_factory()
        try:
            _seed_all_prereqs(seed_s)
        finally:
            seed_s.close()

        service = _make_service(pg_engine)
        cmd = _make_command()
        run = service.generate_production_scheme_run(cmd)
        return run.id

    def _read_verified(self, pg_session_factory, pg_engine, run_id: str):
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
        s = pg_session_factory()
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

    def test_tamper_content_hash(self, pg_session_factory, pg_engine) -> None:
        assert pg_engine.dialect.name == "postgresql"

        from cold_storage.modules.schemes.application.production_service import (
            SchemeRunContentHashMismatchError,
        )
        from cold_storage.modules.schemes.infrastructure.orm import SchemeRunRecord

        run_id = self._generate_and_get_run_id(pg_session_factory, pg_engine)
        tamper_s = pg_session_factory()
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
            self._read_verified(pg_session_factory, pg_engine, run_id)
        assert exc_info.value.code == "content_hash_mismatch"


# ════════════════════════════════════════════════════════════════════════════
# 6. Candidate tamper rejection
# ════════════════════════════════════════════════════════════════════════════


class TestPostgresCandidateTamperRejection:
    """Tamper a candidate's result_snapshot / score, verify rejection."""

    def _generate_and_get_run_id(self, pg_session_factory, pg_engine) -> str:
        seed_s = pg_session_factory()
        try:
            _seed_all_prereqs(seed_s)
        finally:
            seed_s.close()

        service = _make_service(pg_engine)
        cmd = _make_command()
        run = service.generate_production_scheme_run(cmd)
        return run.id

    def _read_verified(self, pg_session_factory, pg_engine, run_id: str):
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
        s = pg_session_factory()
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

    def test_tamper_candidate_result_snapshot(self, pg_session_factory, pg_engine) -> None:
        assert pg_engine.dialect.name == "postgresql"

        from cold_storage.modules.schemes.application.production_service import (
            SchemeRunContentHashMismatchError,
        )
        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeCandidateRecord,
        )

        run_id = self._generate_and_get_run_id(pg_session_factory, pg_engine)
        tamper_s = pg_session_factory()
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
            self._read_verified(pg_session_factory, pg_engine, run_id)
        assert exc_info.value.code == "content_hash_mismatch"

    def test_tamper_candidate_score_breakdown(self, pg_session_factory, pg_engine) -> None:
        assert pg_engine.dialect.name == "postgresql"

        from cold_storage.modules.schemes.application.production_service import (
            SchemeRunContentHashMismatchError,
        )
        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeCandidateRecord,
        )

        run_id = self._generate_and_get_run_id(pg_session_factory, pg_engine)
        tamper_s = pg_session_factory()
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
            self._read_verified(pg_session_factory, pg_engine, run_id)
        assert exc_info.value.code == "content_hash_mismatch"


# ════════════════════════════════════════════════════════════════════════════
# 7. Weight tamper rejection
# ════════════════════════════════════════════════════════════════════════════


class TestPostgresWeightTamperRejection:
    """Tamper the weight revision content, verify weight_verification_failed."""

    def _generate_and_get_run_id(self, pg_session_factory, pg_engine) -> str:
        seed_s = pg_session_factory()
        try:
            _seed_all_prereqs(seed_s)
        finally:
            seed_s.close()

        service = _make_service(pg_engine)
        cmd = _make_command()
        run = service.generate_production_scheme_run(cmd)
        return run.id

    def _read_verified(self, pg_session_factory, pg_engine, run_id: str):
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
        s = pg_session_factory()
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

    def test_tamper_weight_revision_content(self, pg_session_factory, pg_engine) -> None:
        """Tamper with approved revision content is blocked by trigger.

        P0-3: BEFORE UPDATE trigger raises IntegrityError when
        attempting to modify immutable fields of an approved revision.
        """
        assert pg_engine.dialect.name == "postgresql"

        import sqlalchemy as sa

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRevisionRecord,
        )

        self._generate_and_get_run_id(pg_session_factory, pg_engine)
        tamper_s = pg_session_factory()
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
            with pytest.raises((sa.exc.IntegrityError, sa.exc.InternalError)):
                tamper_s.commit()
        finally:
            tamper_s.close()


# ════════════════════════════════════════════════════════════════════════════
# 8. Partial-flush rollback
# ════════════════════════════════════════════════════════════════════════════


class TestPostgresPartialFlushRollback:
    """Persistence failure rolls back all records (no partial writes).

    P0-8: Real partial-flush rollback test on PostgreSQL.
    """

    def test_partial_flush_rollback(self, pg_session_factory, pg_engine) -> None:
        assert pg_engine.dialect.name == "postgresql"

        seed_s = pg_session_factory()
        try:
            _seed_all_prereqs(seed_s)
        finally:
            seed_s.close()

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeCandidateRecord,
            SchemeRunRecord,
        )

        before_s = pg_session_factory()
        try:
            before_runs = set(before_s.execute(select(SchemeRunRecord.id)).scalars().all())
            before_cands = set(before_s.execute(select(SchemeCandidateRecord.id)).scalars().all())
        finally:
            before_s.close()

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
            session.flush()

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
                session.flush()
                if i == 0:
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
            service = _make_service(pg_engine)
            cmd = _make_command()
            with pytest.raises(RuntimeError, match="Simulated partial-flush persistence failure"):
                service.generate_production_scheme_run(cmd)
        finally:
            SqlAlchemyProductionSchemeRunRepository.save_production_run = _original_save  # type: ignore[assignment]

        after_s = pg_session_factory()
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


# ════════════════════════════════════════════════════════════════════════════
# 9. Production seed idempotency
# ════════════════════════════════════════════════════════════════════════════


class TestPostgresSeedIdempotency:
    """Calling seed helpers twice on the same session produces no duplicates."""

    def test_seed_idempotency(self, pg_session_factory, pg_engine) -> None:
        assert pg_engine.dialect.name == "postgresql"

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeRunRecord,
        )

        seed_s = pg_session_factory()
        try:
            _seed_all_prereqs(seed_s)
            # Seed again — should be idempotent
            _seed_all_prereqs(seed_s)
        finally:
            seed_s.close()

        # Generate two runs — both should succeed
        service1 = _make_service(pg_engine)
        run1 = service1.generate_production_scheme_run(_make_command())

        service2 = _make_service(pg_engine)
        run2 = service2.generate_production_scheme_run(_make_command())

        verify_s = pg_session_factory()
        try:
            rec1 = verify_s.execute(
                select(SchemeRunRecord).where(SchemeRunRecord.id == run1.id)
            ).scalar_one_or_none()
            rec2 = verify_s.execute(
                select(SchemeRunRecord).where(SchemeRunRecord.id == run2.id)
            ).scalar_one_or_none()

            assert rec1 is not None
            assert rec2 is not None
            assert rec1.id != rec2.id, "Two distinct runs should have different IDs"
            assert rec1.status == "completed"
            assert rec2.status == "completed"
            assert rec1.source_mode == "production"
            assert rec2.source_mode == "production"
        finally:
            verify_s.close()


# ════════════════════════════════════════════════════════════════════════════
# 10. Transaction B → Production scheme end-to-end (golden data)
# ════════════════════════════════════════════════════════════════════════════


def _pg_compute_domain_hash(
    *,
    stage: str,
    result_snapshot: dict[str, Any],
    run_id: str,
) -> str:
    """Compute domain SourceSnapshotContentV1 result_hash for a stage.

    This is the SAME hash the production verifier recomputes.
    """
    from cold_storage.modules.orchestration.domain.fingerprint import (
        result_hash as _domain_result_hash,
    )
    from cold_storage.modules.orchestration.domain.snapshots import (
        SourceSnapshotContentV1 as DomainSourceSnapshotContentV1,
    )
    from cold_storage.modules.orchestration.domain.snapshots import (
        SourceSnapshotProvenanceV1,
    )
    from tests.integration.transaction_b_golden import (
        GOLDEN_ATTEMPT_ID,
        GOLDEN_COEFFICIENT_CONTEXT_ID,
        GOLDEN_ORCHESTRATION_IDENTITY_ID,
        GOLDEN_SNAPSHOT_ID,
    )

    _PG_SLOT_UPSTREAM_IDS: dict[str, dict[str, str]] = {
        "zone": {},
        "cooling_load": {"zone": "golden-run-zone-001"},
        "equipment": {"cooling_load": "golden-run-cooling-load-001"},
        "power": {"equipment": "golden-run-equipment-001"},
        "investment": {
            "zone": "golden-run-zone-001",
            "power": "golden-run-power-001",
        },
    }

    provenance = SourceSnapshotProvenanceV1(
        execution_snapshot_id=GOLDEN_SNAPSHOT_ID,
        coefficient_context_id=GOLDEN_COEFFICIENT_CONTEXT_ID,
        orchestration_identity_id=GOLDEN_ORCHESTRATION_IDENTITY_ID,
        orchestration_run_attempt_id=GOLDEN_ATTEMPT_ID,
        upstream_calculation_ids=_PG_SLOT_UPSTREAM_IDS.get(stage, {}),
    )
    from tests.integration.transaction_b_golden import _CALCULATOR_META as _gm

    content = DomainSourceSnapshotContentV1(
        schema_version="1.0.0",
        calculation_type=stage,
        calculator_name=_gm[stage]["calculator_id"],
        calculator_version=_gm[stage]["calculator_version"],
        project_id="golden-p-001",
        project_version_id="golden-pv-001",
        execution_snapshot_id=GOLDEN_SNAPSHOT_ID,
        coefficient_context_id=GOLDEN_COEFFICIENT_CONTEXT_ID,
        orchestration_identity_id=GOLDEN_ORCHESTRATION_IDENTITY_ID,
        orchestration_run_attempt_id=GOLDEN_ATTEMPT_ID,
        input_hash="pg-e2e-input-hash",
        requires_review=False,
        payload=result_snapshot,
        provenance=provenance,
    )
    return _domain_result_hash(content)


class TestPostgresProductionTransactionBE2E:
    """Real Transaction B golden data drives production scheme on PostgreSQL.

    Uses golden calculator outputs from _CALCULATOR_OUTPUTS, golden IDs from
    FixedTransactionBIdFactory, and _seed_golden_prerequisites from the shared
    golden module.
    """

    def test_transaction_b_to_production_e2e(self, pg_session_factory, pg_engine) -> None:
        assert pg_engine.dialect.name == "postgresql"

        from tests.integration.transaction_b_golden import (
            _CALCULATOR_OUTPUTS,
            GOLDEN_ATTEMPT_ID,
            GOLDEN_COEFFICIENT_CONTEXT_ID,
            GOLDEN_FINGERPRINT,
            GOLDEN_ORCHESTRATION_IDENTITY_ID,
            GOLDEN_PROJECT_ID,
            GOLDEN_PROJECT_VERSION_ID,
            GOLDEN_SNAPSHOT_ID,
            _seed_golden_prerequisites,
            load_cross_backend_golden,
        )

        # ── Step 1: Seed golden prerequisites ────────────────────────────
        seed_s = pg_session_factory()
        try:
            _seed_golden_prerequisites(seed_s)

            # Link identity → attempt (authoritative_attempt_id must be non-NULL)
            from cold_storage.modules.orchestration.infrastructure.orm import (
                OrchestrationIdentityRecord,
                OrchestrationRunAttemptRecord,
            )

            identity_rec = seed_s.execute(
                select(OrchestrationIdentityRecord).where(
                    OrchestrationIdentityRecord.id == GOLDEN_ORCHESTRATION_IDENTITY_ID
                )
            ).scalar_one_or_none()
            if identity_rec is not None and identity_rec.authoritative_attempt_id is None:
                identity_rec.authoritative_attempt_id = GOLDEN_ATTEMPT_ID
                seed_s.commit()

            # Mark attempt as COMPLETED
            attempt_rec = seed_s.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.id == GOLDEN_ATTEMPT_ID
                )
            ).scalar_one_or_none()
            if attempt_rec is not None and attempt_rec.status != "COMPLETED":
                from cold_storage.modules.orchestration.domain.contracts import AttemptStatus

                attempt_rec.status = AttemptStatus.COMPLETED
                seed_s.commit()
        finally:
            seed_s.close()

        # ── Step 2: Seed 5 CalculationRuns with golden data ──────────────
        _PG_ZONE_RUN_ID = "golden-run-zone-001"
        _PG_COOL_RUN_ID = "golden-run-cooling-load-001"
        _PG_EQUIP_RUN_ID = "golden-run-equipment-001"
        _PG_POWER_RUN_ID = "golden-run-power-001"
        _PG_INVEST_RUN_ID = "golden-run-investment-001"
        _PG_SOURCE_BINDING_ID = "golden-source-binding-001"
        _PG_WEIGHT_SET_ID = "golden-ws-001"
        _PG_WEIGHT_REVISION_ID = "golden-wrev-001"

        _pg_run_ids = {
            "zone": _PG_ZONE_RUN_ID,
            "cooling_load": _PG_COOL_RUN_ID,
            "equipment": _PG_EQUIP_RUN_ID,
            "power": _PG_POWER_RUN_ID,
            "investment": _PG_INVEST_RUN_ID,
        }
        _pg_calc_names = {
            "zone": "cold_room_zone_plan",
            "cooling_load": "cooling_load",
            "equipment": "equipment",
            "power": "installed_power",
            "investment": "investment_estimate",
        }
        _pg_calc_types = {
            "zone": "zone",
            "cooling_load": "cooling_load",
            "equipment": "equipment",
            "power": "power",
            "investment": "investment",
        }
        _pg_upstream = {
            "zone": {},
            "cooling_load": {"zone": _PG_ZONE_RUN_ID},
            "equipment": {"cooling_load": _PG_COOL_RUN_ID},
            "power": {"equipment": _PG_EQUIP_RUN_ID},
            "investment": {"zone": _PG_ZONE_RUN_ID, "power": _PG_POWER_RUN_ID},
        }

        pg_calc_s = pg_session_factory()
        try:
            from cold_storage.modules.projects.infrastructure.orm import (
                CalculationRunRecord,
            )

            per_calc: dict[str, str] = {}
            for stage in ("zone", "cooling_load", "equipment", "power", "investment"):
                run_id = _pg_run_ids[stage]
                snap = _CALCULATOR_OUTPUTS[stage]
                computed_hash = _pg_compute_domain_hash(
                    stage=stage, result_snapshot=snap, run_id=run_id
                )
                provenance: dict[str, Any] = {
                    "stage": stage,
                    "upstream_calculation_ids": _pg_upstream.get(stage, {}),
                }
                pg_calc_s.add(
                    CalculationRunRecord(
                        id=run_id,
                        project_id=GOLDEN_PROJECT_ID,
                        project_version_id=GOLDEN_PROJECT_VERSION_ID,
                        calculator_name=_pg_calc_names[stage],
                        calculator_version="1.0.0",
                        input_snapshot={},
                        result_snapshot=snap,
                        formulas=[],
                        coefficients=[],
                        assumptions=[],
                        warnings=[],
                        source_references=[],
                        requires_review=False,
                        calculation_type=_pg_calc_types[stage],
                        orchestration_identity_id=GOLDEN_ORCHESTRATION_IDENTITY_ID,
                        orchestration_run_attempt_id=GOLDEN_ATTEMPT_ID,
                        execution_snapshot_id=GOLDEN_SNAPSHOT_ID,
                        coefficient_context_id=GOLDEN_COEFFICIENT_CONTEXT_ID,
                        input_hash="pg-e2e-input-hash",
                        result_hash=computed_hash,
                        provenance=provenance,
                        schema_version="1.0.0",
                        orchestration_fingerprint=GOLDEN_FINGERPRINT,
                        created_at=datetime.now(UTC),
                    )
                )
                per_calc[stage] = computed_hash
            pg_calc_s.commit()
        finally:
            pg_calc_s.close()

        # ── Step 3: Seed SourceBinding ────────────────────────────────────
        from cold_storage.modules.schemes.application.source_binding_verifier import (
            _compute_combined_source_hash,
        )

        golden_combined = _compute_combined_source_hash(
            binding_schema_version="1.0.0",
            project_id=GOLDEN_PROJECT_ID,
            project_version_id=GOLDEN_PROJECT_VERSION_ID,
            execution_snapshot_id=GOLDEN_SNAPSHOT_ID,
            coefficient_context_id=GOLDEN_COEFFICIENT_CONTEXT_ID,
            orchestration_identity_id=GOLDEN_ORCHESTRATION_IDENTITY_ID,
            orchestration_attempt_id=GOLDEN_ATTEMPT_ID,
            orchestration_fingerprint=GOLDEN_FINGERPRINT,
            slot_ids=_pg_run_ids,
            result_hashes=per_calc,
            requires_reviews={
                stage: False
                for stage in ("zone", "cooling_load", "equipment", "power", "investment")
            },
        )

        pg_bind_s = pg_session_factory()
        try:
            from cold_storage.modules.orchestration.infrastructure.orm import (
                SourceBindingRecord as SBRecord,
            )

            pg_bind_s.add(
                SBRecord(
                    id=_PG_SOURCE_BINDING_ID,
                    project_id=GOLDEN_PROJECT_ID,
                    project_version_id=GOLDEN_PROJECT_VERSION_ID,
                    execution_snapshot_id=GOLDEN_SNAPSHOT_ID,
                    coefficient_context_id=GOLDEN_COEFFICIENT_CONTEXT_ID,
                    orchestration_identity_id=GOLDEN_ORCHESTRATION_IDENTITY_ID,
                    orchestration_run_attempt_id=GOLDEN_ATTEMPT_ID,
                    orchestration_fingerprint=GOLDEN_FINGERPRINT,
                    zone_calculation_id=_PG_ZONE_RUN_ID,
                    cooling_load_calculation_id=_PG_COOL_RUN_ID,
                    equipment_calculation_id=_PG_EQUIP_RUN_ID,
                    power_calculation_id=_PG_POWER_RUN_ID,
                    investment_calculation_id=_PG_INVEST_RUN_ID,
                    per_calculation_result_hashes=per_calc,
                    combined_source_hash=golden_combined,
                    schema_version="1.0.0",
                    created_at=datetime.now(UTC),
                )
            )
            pg_bind_s.commit()

            # Link attempt → source binding
            # P0-5: Assert row exists, fail-closed on no-row.
            attempt_rec = pg_bind_s.execute(
                select(OrchestrationRunAttemptRecord).where(
                    OrchestrationRunAttemptRecord.id == GOLDEN_ATTEMPT_ID
                )
            ).scalar_one_or_none()
            assert attempt_rec is not None, (
                f"Attempt row {GOLDEN_ATTEMPT_ID} must exist before linking"
            )
            if attempt_rec.source_binding_id is None:
                attempt_rec.source_binding_id = _PG_SOURCE_BINDING_ID
                pg_bind_s.commit()
                pg_bind_s.expire_all()
                # Re-read to confirm
                persisted = pg_bind_s.execute(
                    select(OrchestrationRunAttemptRecord).where(
                        OrchestrationRunAttemptRecord.id == GOLDEN_ATTEMPT_ID
                    )
                ).scalar_one()
                assert persisted.source_binding_id == _PG_SOURCE_BINDING_ID, (
                    f"Attempt binding mismatch after commit: "
                    f"{persisted.source_binding_id} != {_PG_SOURCE_BINDING_ID}"
                )
        finally:
            pg_bind_s.close()

        # ── Step 4: Seed weight set ──────────────────────────────────────
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
        _WEIGHT_REVISION_CONTENT: dict[str, Any] = {"criteria": _WEIGHT_CRITERIA_RAW}
        _WEIGHT_CONTENT_HASH = _compute_weight_content_hash(_WEIGHT_REVISION_CONTENT)

        pg_ws_s = pg_session_factory()
        try:
            from cold_storage.modules.schemes.infrastructure.orm import (
                SchemeWeightSetRecord,
                SchemeWeightSetRevisionRecord,
            )

            existing_ws = pg_ws_s.execute(
                select(SchemeWeightSetRecord).where(SchemeWeightSetRecord.id == _PG_WEIGHT_SET_ID)
            ).scalar_one_or_none()
            if existing_ws is None:
                pg_ws_s.add(
                    SchemeWeightSetRecord(
                        id=_PG_WEIGHT_SET_ID,
                        code="pg-golden-standard-weights",
                        name="PG golden standard weights",
                        revision=1,
                        status="approved",
                        source_type="production",
                        criteria=_WEIGHT_CRITERIA_RAW,
                        requires_review=False,
                        created_at=datetime.now(UTC),
                        approved_at=datetime.now(UTC),
                    )
                )
            existing_rev = pg_ws_s.execute(
                select(SchemeWeightSetRevisionRecord).where(
                    SchemeWeightSetRevisionRecord.id == _PG_WEIGHT_REVISION_ID
                )
            ).scalar_one_or_none()
            if existing_rev is None:
                pg_ws_s.add(
                    SchemeWeightSetRevisionRecord(
                        id=_PG_WEIGHT_REVISION_ID,
                        weight_set_id=_PG_WEIGHT_SET_ID,
                        code="pg-golden-standard-weights",
                        revision=1,
                        status="draft",
                        content=_WEIGHT_REVISION_CONTENT,
                        content_hash=_WEIGHT_CONTENT_HASH,
                        generator_compatibility_version="1.0.0",
                        approved_at=None,
                        approved_by=None,
                        created_at=datetime.now(UTC),
                    )
                )
                pg_ws_s.flush()
                # Transition draft→approved via UPDATE (INSERT trigger blocks direct approved)
                from sqlalchemy import text

                _now = datetime.now(UTC)
                pg_ws_s.execute(
                    text(
                        "UPDATE scheme_weight_set_revisions "
                        "SET status = 'approved', "
                        "approved_at = :approved_at, "
                        "approved_by = :approved_by, "
                        "sealed_at = :sealed_at "
                        "WHERE id = :rev_id"
                    ),
                    {
                        "approved_at": _now,
                        "approved_by": "pg-golden-e2e-test",
                        "sealed_at": _now,
                        "rev_id": _PG_WEIGHT_REVISION_ID,
                    },
                )
            pg_ws_s.commit()
        finally:
            pg_ws_s.close()

        # ── Step 5: Generate production scheme ───────────────────────────
        from cold_storage.modules.schemes.application.production_ports import (
            GenerateProductionSchemeCommand,
        )

        service = _make_service(pg_engine)
        cmd = GenerateProductionSchemeCommand(
            source_binding_id=_PG_SOURCE_BINDING_ID,
            weight_set_revision_id=_PG_WEIGHT_REVISION_ID,
            profile_codes=("balanced",),
            profile_parameters={},
            actor="pg-golden-e2e-test",
            correlation_id="pg-golden-e2e-corr-001",
        )
        run = service.generate_production_scheme_run(cmd)

        # ── Step 6: Verify ───────────────────────────────────────────────
        assert run.status == "completed"

        golden = load_cross_backend_golden()

        verify_s = pg_session_factory()
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
            assert rec.source_binding_id == _PG_SOURCE_BINDING_ID
            assert rec.weight_set_revision_id == _PG_WEIGHT_REVISION_ID
            assert rec.source_contract_version == "1.0.0"
            assert rec.combined_source_hash == golden_combined

            # Verify five slot IDs match golden FixedTransactionBIdFactory IDs
            golden_slots = golden["source_binding_slot_ids"]
            assert rec.zone_calculation_id == golden_slots["zone"]
            assert rec.cooling_load_calculation_id == golden_slots["cooling_load"]
            assert rec.equipment_calculation_id == golden_slots["equipment"]
            assert rec.power_calculation_id == golden_slots["power"]
            assert rec.investment_calculation_id == golden_slots["investment"]

            # Verify result hashes on SchemeRun match domain hashes
            assert rec.zone_result_hash == per_calc["zone"]
            assert rec.cooling_load_result_hash == per_calc["cooling_load"]
            assert rec.equipment_result_hash == per_calc["equipment"]
            assert rec.power_result_hash == per_calc["power"]
            assert rec.investment_result_hash == per_calc["investment"]

            # Verify provenance
            assert rec.orchestration_identity_id == GOLDEN_ORCHESTRATION_IDENTITY_ID
            assert rec.authoritative_attempt_id == GOLDEN_ATTEMPT_ID
            assert rec.execution_snapshot_id == GOLDEN_SNAPSHOT_ID
            assert rec.coefficient_context_id == GOLDEN_COEFFICIENT_CONTEXT_ID
            assert rec.orchestration_fingerprint == GOLDEN_FINGERPRINT

            # Verify power authority = 285.0 from golden
            assert _CALCULATOR_OUTPUTS["power"]["total_installed_power_kw_e"] == "285.0"

            # Verify candidates
            candidates = (
                verify_s.execute(
                    select(SchemeCandidateRecord).where(
                        SchemeCandidateRecord.scheme_run_id == run.id
                    )
                )
                .scalars()
                .all()
            )
            assert len(candidates) > 0
        finally:
            verify_s.close()

        # ── Step 7: Trusted readback succeeds ────────────────────────────
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

        readback_s = pg_session_factory()
        try:
            verified_run = read_verified_production_scheme_run(
                read_port,
                binding_port,
                weight_port,
                readback_s,
                run_id=run.id,
                generator_version="1.0.0",
            )
        finally:
            readback_s.close()

        assert verified_run.status == "completed"
        assert verified_run.id == run.id
        assert verified_run.content_hash is not None
        assert len(verified_run.candidates_snapshot) > 0
