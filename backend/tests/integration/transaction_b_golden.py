"""Shared helpers for cross-backend golden parity tests.

Both SQLite and PostgreSQL integration tests consume the same golden
artifact and compare against identical fixed inputs and deterministic
calculator outputs.

This module provides:
- Fixed calculator outputs matching typed snapshot schemas
- Seed functions for deterministic DB prerequisites
- Artifact reader for canonical comparison
- Deep-equality assertion helper
- Typed snapshot parse validation
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from cold_storage.modules.orchestration.application.source_snapshots import (
    CoolingLoadSourceSnapshotV1,
    EquipmentSourceSnapshotV1,
    InvestmentSourceSnapshotV1,
    PowerSourceSnapshotV1,
    ZoneSourceSnapshotV1,
)
from cold_storage.modules.orchestration.domain.contracts import (
    AttemptStatus,
    OrchestrationRequestCommand,
    RequestStatus,
)
from cold_storage.modules.orchestration.domain.dag import ORCHESTRATION_STAGE_ORDER
from cold_storage.modules.orchestration.domain.fingerprint import result_hash
from cold_storage.modules.orchestration.infrastructure.orm import (
    CoefficientContextRecord,
    OrchestrationIdentityRecord,
    OrchestrationRequestRecord,
    OrchestrationRunAttemptRecord,
    ProjectVersionExecutionSnapshotRecord,
    SourceBindingRecord,
)
from cold_storage.modules.projects.infrastructure.orm import (
    CalculationRunRecord,
    ProjectRecord,
    ProjectVersionRecord,
)

# ── Golden JSON path ──────────────────────────────────────────────────────

_GOLDEN_PATH = (
    Path(__file__).resolve().parent.parent / "golden" / "transaction_b_cross_backend_v1.json"
)

# ── Fixed identity IDs ────────────────────────────────────────────────────

GOLDEN_PROJECT_ID = "golden-p-001"
GOLDEN_PROJECT_VERSION_ID = "golden-pv-001"
GOLDEN_REQUEST_ID = "golden-req-001"
GOLDEN_SNAPSHOT_ID = "golden-snap-001"
GOLDEN_COEFFICIENT_CONTEXT_ID = "golden-coeff-001"
GOLDEN_ORCHESTRATION_IDENTITY_ID = "golden-orch-001"
GOLDEN_ATTEMPT_ID = "golden-attempt-001"
GOLDEN_FINGERPRINT = "golden-fp-001"

# ── Calculator metadata ───────────────────────────────────────────────────

_CALCULATOR_META: dict[str, dict[str, str]] = {
    "zone": {"calculator_id": "cold_room_zone_plan", "calculator_version": "1.0.0"},
    "cooling_load": {"calculator_id": "cooling_load", "calculator_version": "1.0.0"},
    "equipment": {"calculator_id": "equipment", "calculator_version": "1.0.0"},
    "power": {"calculator_id": "installed_power", "calculator_version": "1.0.0"},
    "investment": {"calculator_id": "investment_estimate", "calculator_version": "1.0.0"},
}

# ── Typed snapshot adapter map ────────────────────────────────────────────

_TYPED_SNAPSHOT_CLS: dict[str, type] = {
    "zone": ZoneSourceSnapshotV1,
    "cooling_load": CoolingLoadSourceSnapshotV1,
    "equipment": EquipmentSourceSnapshotV1,
    "power": PowerSourceSnapshotV1,
    "investment": InvestmentSourceSnapshotV1,
}

# ── Fixed calculator outputs ──────────────────────────────────────────────
# Power fixture uses typed-snapshot-compatible fields (NOT old flat fields).

_CALCULATOR_OUTPUTS: dict[str, dict[str, Any]] = {
    "zone": {
        "daily_inbound_mass_kg": "25000",
        "design_daily_mass_kg": "30000",
        "total_required_area_m2": "1200",
        "total_area_m2": "1400",
        "planning_parameters": {"safety_factor": "1.2"},
        "zones": [
            {
                "zone_code": "Z1",
                "zone_name": "Pre-cooling",
                "temperature_band": "2~8",
                "function": "precooling",
                "daily_throughput_kg_day": "25000",
                "design_storage_mass_kg": "5000",
                "position_count": 20,
                "required_area_m2": "400",
                "requires_review": False,
            },
            {
                "zone_code": "Z2",
                "zone_name": "Cold Storage",
                "temperature_band": "0~2",
                "function": "storage",
                "daily_throughput_kg_day": "25000",
                "design_storage_mass_kg": "25000",
                "position_count": 100,
                "required_area_m2": "800",
                "requires_review": False,
            },
        ],
    },
    "cooling_load": {
        "total_cooling_load_kw": "350.0",
        "safety_margin_load_kw": "35.0",
        "envelope_heat_transfer_load_kw": "80.0",
        "product_sensible_heat_load_kw": "120.0",
        "packaging_load_kw": "20.0",
        "infiltration_load_kw": "30.0",
        "personnel_load_kw": "15.0",
        "lighting_load_kw": "10.0",
        "evaporator_fan_load_kw": "25.0",
        "defrost_additional_load_kw": "10.0",
        "other_configuration_load_kw": "5.0",
    },
    "equipment": {
        "evaporator_total_cooling_capacity_kw": "500.0",
        "evaporator_quantity": 4,
        "single_evaporator_capacity_kw": "125.0",
        "compressor_operating_capacity_kw": "450.0",
        "standby_capacity_kw": "50.0",
        "condenser_heat_rejection_capacity_kw": "550.0",
        "evaporation_temperature_c": "-10.0",
        "condensing_temperature_c": "40.0",
        "defrost_method": "electric",
        "review_requirement": "",
    },
    "power": {
        "total_installed_power_kw_e": "285.0",
        "total_estimated_demand_kw": "220.0",
        "equipment_rows": [
            {
                "sequence": 1,
                "name": "Compressor",
                "area": "machine_room",
                "quantity": "2",
                "running_power_kw": "75.0",
                "total_power_kw": "150.0",
                "section": "refrigeration",
            },
            {
                "sequence": 2,
                "name": "Condenser Fan",
                "area": "outdoor",
                "quantity": "4",
                "running_power_kw": "5.0",
                "total_power_kw": "20.0",
                "section": "refrigeration",
            },
            {
                "sequence": 3,
                "name": "Evaporator Fan",
                "area": "cold_room",
                "quantity": "8",
                "running_power_kw": "3.0",
                "total_power_kw": "24.0",
                "section": "refrigeration",
            },
            {
                "sequence": 4,
                "name": "Lighting",
                "area": "all",
                "quantity": "20",
                "running_power_kw": "1.0",
                "total_power_kw": "20.0",
                "section": "auxiliary",
            },
            {
                "sequence": 5,
                "name": "Defrost Heater",
                "area": "cold_room",
                "quantity": "8",
                "running_power_kw": "8.625",
                "total_power_kw": "69.0",
                "section": "auxiliary",
            },
            {
                "sequence": 6,
                "name": "Door Heater",
                "area": "entrance",
                "quantity": "2",
                "running_power_kw": "1.0",
                "total_power_kw": "2.0",
                "section": "auxiliary",
            },
        ],
        "summary_rows": [
            {
                "name": "Refrigeration",
                "basis": "equipment",
                "total_power_kw": "194.0",
            },
            {
                "name": "Auxiliary",
                "basis": "area",
                "total_power_kw": "91.0",
            },
        ],
        "items": [
            {
                "category": "refrigeration",
                "installed_power_kw": "194.0",
                "demand_factor": "0.85",
                "estimated_demand_kw": "164.9",
            },
            {
                "category": "auxiliary",
                "installed_power_kw": "91.0",
                "demand_factor": "0.60",
                "estimated_demand_kw": "54.6",
            },
        ],
        "assumptions": ["Standard operating conditions for blueberry cold storage"],
    },
    "investment": {
        "total_investment_cny": "12500000",
        "items": [
            {"item_name": "土建部分", "amount_cny": "5000000"},
            {"item_name": "制冷设备", "amount_cny": "4500000"},
            {"item_name": "电气安装", "amount_cny": "1500000"},
            {"item_name": "其他费用", "amount_cny": "1500000"},
        ],
    },
}

# ── Shared traceability fixtures ──────────────────────────────────────────

_REQUIRED_CODES: tuple[str, ...] = (
    "area.auxiliary_area_ratio",
    "area.circulation_allowance_ratio",
    "investment.building_unit_cost",
    "investment.electrical_installation_ratio",
    "investment.other_expenses_ratio",
    "investment.refrigeration_equipment_ratio",
    "pallet.net_load_kg",
    "pallet.turnover_factor",
    "power.design_margin_ratio",
    "power.standby_ratio",
)
_REGISTRY_VERSION = "1.0.0"
_CV_VECTOR: dict[str, str] = {
    "zone": "1.0.0",
    "cooling_load": "1.0.0",
    "equipment": "1.0.0",
    "power": "1.0.0",
    "investment": "1.0.0",
}


# ── Coefficient context builder ───────────────────────────────────────────


def _build_golden_coefficient_content() -> dict[str, object]:
    """Build coefficient context content matching _make_resolved_coefficient()."""
    coefficients: list[dict[str, object]] = []
    for i, code in enumerate(_REQUIRED_CODES, 1):
        coefficients.append(
            {
                "definition_id": f"def-{i:03d}",
                "code": code,
                "revision_id": f"rev-{i:03d}",
                "revision_number": 1,
                "unit": "dimensionless",
                "source_type": "standard",
                "status": "approved",
                "value_decimal": "1.0",
            }
        )

    req_hash = result_hash(
        {
            "registry_version": _REGISTRY_VERSION,
            "calculator_version_vector": dict(_CV_VECTOR),
            "required_codes": list(_REQUIRED_CODES),
        }
    )

    return {
        "source_type": "catalog",
        "validity_status": "approved",
        "project_id": GOLDEN_PROJECT_ID,
        "project_version_id": GOLDEN_PROJECT_VERSION_ID,
        "schema_version": "1.0.0",
        "coefficient_count": len(coefficients),
        "coefficients": coefficients,
        "requirement_registry_version": _REGISTRY_VERSION,
        "calculator_version_vector": dict(_CV_VECTOR),
        "required_codes": list(_REQUIRED_CODES),
        "requirement_hash": req_hash,
    }


# ── Seed golden prerequisites ─────────────────────────────────────────────


def _seed_golden_prerequisites(session: Session) -> None:
    """Seed all prerequisite records for a golden Transaction B run.

    Creates records with fixed IDs in dependency order:
      1. ProjectRecord
      2. ProjectVersionRecord
      3. ProjectVersionExecutionSnapshotRecord
      4. CoefficientContextRecord
      5. OrchestrationIdentityRecord
      6. OrchestrationRunAttemptRecord
      7. OrchestrationRequestRecord (status=ACCEPTED with all required fields)

    The CHECK constraint on orchestration_requests requires:
      status='ACCEPTED' → resolved_project_id, resolved_project_version_id,
        resolved_identity_id, resolved_attempt_id all NOT NULL,
        completed_at NOT NULL, failure_code/field/details NULL.
    """
    # 1. Project
    existing_p = session.execute(
        select(ProjectRecord).where(ProjectRecord.id == GOLDEN_PROJECT_ID)
    ).scalar_one_or_none()
    if not existing_p:
        session.add(
            ProjectRecord(
                id=GOLDEN_PROJECT_ID,
                code="GOLDEN",
                name="Golden Parity Project",
                location="test",
                product_category="blueberry",
                status="active",
                current_version_number=1,
            )
        )

    # 2. ProjectVersion
    existing_pv = session.execute(
        select(ProjectVersionRecord).where(ProjectVersionRecord.id == GOLDEN_PROJECT_VERSION_ID)
    ).scalar_one_or_none()
    if not existing_pv:
        session.add(
            ProjectVersionRecord(
                id=GOLDEN_PROJECT_VERSION_ID,
                project_id=GOLDEN_PROJECT_ID,
                version_number=1,
                change_summary="golden parity version",
                created_by="test",
                status="approved",
                input_snapshot={"throughput_t": "25.0", "product_category": "blueberry"},
            )
        )

    # 3. Execution Snapshot
    input_snapshot: dict[str, object] = {
        "throughput_t": "25.0",
        "product_category": "blueberry",
    }
    existing_snap = session.execute(
        select(ProjectVersionExecutionSnapshotRecord).where(
            ProjectVersionExecutionSnapshotRecord.id == GOLDEN_SNAPSHOT_ID
        )
    ).scalar_one_or_none()
    if not existing_snap:
        session.add(
            ProjectVersionExecutionSnapshotRecord(
                id=GOLDEN_SNAPSHOT_ID,
                project_id=GOLDEN_PROJECT_ID,
                project_version_id=GOLDEN_PROJECT_VERSION_ID,
                version_number=1,
                input_snapshot=input_snapshot,
                input_snapshot_hash=result_hash(input_snapshot),
                schema_version="1.0.0",
                captured_status="approved",
                captured_source_revision=None,
            )
        )

    # 4. Coefficient Context
    coeff_content = _build_golden_coefficient_content()
    existing_coeff = session.execute(
        select(CoefficientContextRecord).where(
            CoefficientContextRecord.id == GOLDEN_COEFFICIENT_CONTEXT_ID
        )
    ).scalar_one_or_none()
    if not existing_coeff:
        session.add(
            CoefficientContextRecord(
                id=GOLDEN_COEFFICIENT_CONTEXT_ID,
                project_id=GOLDEN_PROJECT_ID,
                project_version_id=GOLDEN_PROJECT_VERSION_ID,
                content=coeff_content,
                content_hash=result_hash(coeff_content),
                schema_version="1.0.0",
            )
        )

    # 5. Orchestration Identity
    existing_orch = session.execute(
        select(OrchestrationIdentityRecord).where(
            OrchestrationIdentityRecord.id == GOLDEN_ORCHESTRATION_IDENTITY_ID
        )
    ).scalar_one_or_none()
    if not existing_orch:
        session.add(
            OrchestrationIdentityRecord(
                id=GOLDEN_ORCHESTRATION_IDENTITY_ID,
                fingerprint=GOLDEN_FINGERPRINT,
                execution_snapshot_id=GOLDEN_SNAPSHOT_ID,
                coefficient_context_id=GOLDEN_COEFFICIENT_CONTEXT_ID,
                definition_version="1.0.0",
                calculator_version_vector=dict(_CV_VECTOR),
                status="ACTIVE",
                authoritative_attempt_id=None,
            )
        )

    # 6. Orchestration Run Attempt (RUNNING)
    existing_attempt = session.execute(
        select(OrchestrationRunAttemptRecord).where(
            OrchestrationRunAttemptRecord.id == GOLDEN_ATTEMPT_ID
        )
    ).scalar_one_or_none()
    if not existing_attempt:
        session.add(
            OrchestrationRunAttemptRecord(
                id=GOLDEN_ATTEMPT_ID,
                identity_id=GOLDEN_ORCHESTRATION_IDENTITY_ID,
                attempt_number=1,
                status=AttemptStatus.RUNNING,
                lease_owner="golden-test",
                source_binding_id=None,
                failure_code=None,
                failure_details=None,
            )
        )

    # 7. Orchestration Request (status=ACCEPTED — CHECK constraint satisfied)
    existing_req = session.execute(
        select(OrchestrationRequestRecord).where(OrchestrationRequestRecord.id == GOLDEN_REQUEST_ID)
    ).scalar_one_or_none()
    if not existing_req:
        # Avoid passing None for JSON columns — SQLAlchemy serializes them
        # to the string 'null' instead of SQL NULL, violating CHECK constraints.
        # Use session.execute with text() to insert explicit NULLs.
        from sqlalchemy import text

        session.execute(
            text(
                "INSERT INTO orchestration_requests "
                "(id, requested_project_id, requested_project_version_id, "
                "request_fingerprint, actor, correlation_id, status, "
                "resolved_project_id, resolved_project_version_id, "
                "resolved_identity_id, resolved_attempt_id, "
                "failure_code, failure_field, failure_details, "
                "created_at, completed_at) "
                "VALUES (:id, :rpid, :rpvid, :rfp, :actor, :corr, :status, "
                ":rpid_resolved, :rpvid_resolved, :rid, :raid, "
                "NULL, NULL, NULL, :now, :completed_at)"
            ),
            {
                "id": GOLDEN_REQUEST_ID,
                "rpid": GOLDEN_PROJECT_ID,
                "rpvid": GOLDEN_PROJECT_VERSION_ID,
                "rfp": GOLDEN_FINGERPRINT,
                "actor": "golden-test",
                "corr": "golden-corr-001",
                "status": RequestStatus.ACCEPTED,
                "rpid_resolved": GOLDEN_PROJECT_ID,
                "rpvid_resolved": GOLDEN_PROJECT_VERSION_ID,
                "rid": GOLDEN_ORCHESTRATION_IDENTITY_ID,
                "raid": GOLDEN_ATTEMPT_ID,
                "now": datetime.now(UTC),
                "completed_at": datetime.now(UTC),
            },
        )

    session.commit()


def _make_golden_command() -> OrchestrationRequestCommand:
    """Return an OrchestrationRequestCommand with fixed golden IDs."""
    return OrchestrationRequestCommand(
        project_id=GOLDEN_PROJECT_ID,
        project_version_id=GOLDEN_PROJECT_VERSION_ID,
        coefficient_resolution_context={},
        actor="golden-test",
        correlation_id="golden-corr-001",
    )


# ── Artifact reader ───────────────────────────────────────────────────────


def read_transaction_b_artifact(
    session: Session,
    *,
    attempt_id: str,
) -> dict[str, object]:
    """Read 5 CalculationRun + 1 SourceBinding from DB and build canonical artifact.

    Returns a dict with keys sorted by ORCHESTRATION_STAGE_ORDER:
      result_hashes, combined_source_hash, canonical_result_snapshots,
      upstream_provenance, requires_review, calculator_identity,
      source_snapshot_schema_version, binding_schema_version
    """
    # Load all CalculationRuns for this attempt
    calc_runs: dict[str, CalculationRunRecord] = {}
    for stage_name in ORCHESTRATION_STAGE_ORDER:
        run = session.execute(
            select(CalculationRunRecord).where(
                CalculationRunRecord.orchestration_run_attempt_id == attempt_id,
                CalculationRunRecord.calculation_type == stage_name,
            )
        ).scalar_one_or_none()
        if run is None:
            raise ValueError(f"Missing CalculationRun for stage {stage_name!r}")
        calc_runs[stage_name] = run

    # Load the SourceBinding
    binding = session.execute(
        select(SourceBindingRecord).where(
            SourceBindingRecord.orchestration_run_attempt_id == attempt_id
        )
    ).scalar_one_or_none()
    if binding is None:
        raise ValueError(f"Missing SourceBinding for attempt {attempt_id!r}")

    # Build canonical artifact (no timestamps, deterministic order)
    result_hashes: dict[str, str] = {}
    canonical_result_snapshots: dict[str, dict[str, object]] = {}
    upstream_provenance: dict[str, dict[str, str]] = {}
    requires_review: dict[str, bool] = {}
    calculator_identity: dict[str, dict[str, str]] = {}

    for stage_name in ORCHESTRATION_STAGE_ORDER:
        run = calc_runs[stage_name]
        result_hashes[stage_name] = run.result_hash or ""
        canonical_result_snapshots[stage_name] = run.result_snapshot
        requires_review[stage_name] = run.requires_review
        calculator_identity[stage_name] = {
            "calculator_name": run.calculator_name,
            "calculator_version": run.calculator_version,
            "calculation_type": run.calculation_type or stage_name,
        }
        provenance = run.provenance or {}
        upstream_provenance[stage_name] = dict(provenance.get("upstream_calculation_ids", {}))

    return {
        "result_hashes": result_hashes,
        "combined_source_hash": binding.combined_source_hash,
        "canonical_result_snapshots": canonical_result_snapshots,
        "upstream_provenance": upstream_provenance,
        "requires_review": requires_review,
        "calculator_identity": calculator_identity,
        "source_snapshot_schema_version": binding.schema_version,
        "binding_schema_version": "1.0.0",
    }


# ── Deep equality assertion ───────────────────────────────────────────────


def assert_matches_cross_backend_golden(
    actual: dict[str, object],
    golden: dict[str, object],
) -> None:
    """Assert that *actual* artifact deeply equals *golden*.

    Compares every key and recursively validates nested dicts/lists.
    Raises AssertionError with a descriptive message on mismatch.
    """
    _assert_deep_equal(actual, golden, root_path="")


def _assert_deep_equal(
    actual: object,
    expected: object,
    *,
    root_path: str,
) -> None:
    """Recursive deep-equality check with path reporting."""
    if isinstance(actual, dict) and isinstance(expected, dict):
        actual_keys = set(actual.keys())
        expected_keys = set(expected.keys())
        if actual_keys != expected_keys:
            missing = expected_keys - actual_keys
            extra = actual_keys - expected_keys
            parts: list[str] = []
            if missing:
                parts.append(f"missing keys: {sorted(missing)}")
            if extra:
                parts.append(f"extra keys: {sorted(extra)}")
            raise AssertionError(f"Key mismatch at {root_path!r}: {'; '.join(parts)}")
        for key in sorted(expected.keys()):
            _assert_deep_equal(
                actual[key],
                expected[key],
                root_path=f"{root_path}.{key}" if root_path else key,
            )
    elif isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
        if len(actual) != len(expected):
            raise AssertionError(
                f"Length mismatch at {root_path!r}: actual={len(actual)}, expected={len(expected)}"
            )
        for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
            _assert_deep_equal(a, e, root_path=f"{root_path}[{i}]")
    elif actual != expected:
        raise AssertionError(
            f"Value mismatch at {root_path!r}: actual={actual!r}, expected={expected!r}"
        )


# ── Typed snapshot parse validation ───────────────────────────────────────


def validate_typed_snapshots_parse_all() -> None:
    """Validate that all 5 calculator outputs pass through real typed snapshot adapters.

    Constructs a complete SourceSnapshotV1 subclass for each stage using
    the fixed golden calculator outputs plus binding fields.  Raises on
    Pydantic validation error.
    """
    for stage_name in ORCHESTRATION_STAGE_ORDER:
        snapshot_cls = _TYPED_SNAPSHOT_CLS[stage_name]
        calc_meta = _CALCULATOR_META[stage_name]
        calculator_output = _CALCULATOR_OUTPUTS[stage_name]

        # Build the snapshot with all required binding fields
        # Use dummy but valid binding IDs (not persisted, just for parse validation)
        snapshot_cls(
            project_id="test-p",
            project_version_id="test-pv",
            execution_snapshot_id="test-snap",
            coefficient_context_id="test-coeff",
            orchestration_identity_id="test-orch",
            orchestration_attempt_id="test-attempt",
            orchestration_fingerprint="test-fp",
            source_snapshot_schema_version="1.0.0",
            calculation_type=stage_name,
            calculator_id=calc_meta["calculator_id"],
            calculator_version=calc_meta["calculator_version"],
            requires_review=False,
            result_snapshot=calculator_output,
            formulas=[
                {
                    "formula_id": f"form-{stage_name}-01",
                    "formula_version": "1.0.0",
                    "expression": f"Q = m * cp * dT ({stage_name})",
                    "description": f"Test formula for {stage_name}",
                },
            ],
            coefficients=[
                {
                    "code": "pallet.net_load_kg",
                    "value": "1000",
                    "unit": "kg",
                    "status": "approved",
                    "source_type": "catalog",
                    "source_reference": "test",
                    "requires_review": False,
                    "revision_id": "rev-001",
                },
            ],
            assumptions=[f"Test assumption for {stage_name}"],
            warnings=[],
            source_references=[],
            upstream_calculation_ids={},
        )


# ── Public API ────────────────────────────────────────────────────────────


def load_cross_backend_golden() -> dict[str, Any]:
    """Load the golden artifact from disk."""
    return json.loads(_GOLDEN_PATH.read_text())


def get_fixed_inputs() -> dict[str, Any]:
    """Return the fixed identity inputs for golden tests."""
    golden = load_cross_backend_golden()
    return golden["fixed_inputs"]


def get_stage_data() -> dict[str, Any]:
    """Return the stage data (calculator metadata) for golden tests."""
    golden = load_cross_backend_golden()
    return golden["stage_data"]


def get_calculator_output(stage_name: str) -> dict[str, Any]:
    """Return the fixed calculator output for a given stage."""
    return dict(_CALCULATOR_OUTPUTS[stage_name])


def get_calculator_metadata() -> dict[str, dict[str, str]]:
    """Return the calculator metadata for golden verification."""
    return dict(_CALCULATOR_META)
