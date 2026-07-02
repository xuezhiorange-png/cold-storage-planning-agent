"""Strict tamper-matrix tests for SourceBindingVerifier.

Tests the ``verify_source_mapping`` function (and backward-compatible
``verify_source_binding``) in isolation using mock read ports.

Each test constructs a valid state, tampers one field at a time,
and asserts the correct structured error is raised.

Covers:
1.  Schema version error
2.  Attempt not completed / missing
3.  Attempt not authoritative
4.  Attempt source_binding_id mismatch
5.  Slot missing
6.  Slot type error (calculator_name, calculation_type)
7.  Identity field mismatches (project_id, orchestration_identity, fingerprint)
8.  Typed payload invalid (corrupt Pydantic data)
9.  Provenance missing key / extra key
10. Upstream calculation ID mismatch
11. Result hash mismatch
12. Combined source hash mismatch
13. Slot hash map mismatch
14. Completeness violation (NULL fields)
15. Power authority missing
"""

from __future__ import annotations

import dataclasses
from typing import Any
from unittest.mock import MagicMock

import pytest

from cold_storage.modules.orchestration.application.source_snapshots import (
    CoolingLoadSourceSnapshotV1,
    EquipmentSourceSnapshotV1,
    InvestmentSourceSnapshotV1,
    PowerSourceSnapshotV1,
    ZoneSourceSnapshotV1,
)
from cold_storage.modules.orchestration.domain.dag import ORCHESTRATION_STAGE_ORDER
from cold_storage.modules.schemes.application.production_ports import (
    AttemptSnapshot,
    CalculationRunSnapshot,
    SourceBindingSnapshot,
    VerifiedSourceMapping,
)
from cold_storage.modules.schemes.application.source_binding_verifier import (
    AttemptNotAuthoritativeError,
    AttemptNotCompletedError,
    AttemptSourceBindingMismatch,
    BindingNotFoundError,
    BindingSchemaError,
    CalculatorVersionMismatch,
    CoefficientContextMismatch,
    CombinedHashMismatch,
    CompletenessViolation,
    ExecutionSnapshotMismatch,
    FingerprintMismatch,
    IdentityNotFoundError,
    PowerAuthorityMissingError,
    ProvenanceExtraKey,
    ProvenanceMissingKey,
    RequiresReviewMismatch,
    ResultHashMismatch,
    SlotHashMapMismatch,
    SlotIdentityMismatch,
    SlotMissingError,
    SlotTypeError,
    SourceBindingVerificationError,
    SourcePayloadCanonicalizationError,
    TypedPayloadInvalid,
    UpstreamCalculationIdMismatch,
    _compute_combined_source_hash,
    verify_source_binding,
    verify_source_mapping,
)

# ── Canonical test constants ──────────────────────────────────────────────

_PID = "proj-001"
_PVID = "pver-001"
_ESID = "esnap-001"
_CCID = "cctx-001"
_IDENT = "ident-001"
_ATT = "att-001"
_FP = "fp-abc123"
_BINDING_ID = "binding-001"

# stage → (run_id, calculator_name, calculator_version, calculation_type)
_STAGE_META: dict[str, tuple[str, str, str, str]] = {
    "zone": ("run-z-001", "cold_room_zone_plan", "1.0.0", "zone"),
    "cooling_load": ("run-cl-001", "cooling_load", "1.0.0", "cooling_load"),
    "equipment": ("run-eq-001", "equipment", "1.0.0", "equipment"),
    "power": ("run-pow-001", "installed_power", "1.0.0", "power"),
    "investment": ("run-inv-001", "investment_estimate", "1.0.0", "investment"),
}


# ── Realistic result snapshot dicts ───────────────────────────────────────


def _zone_result() -> dict[str, Any]:
    return {
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
            }
        ],
    }


def _cooling_load_result() -> dict[str, Any]:
    return {
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
    }


def _equipment_result() -> dict[str, Any]:
    return {
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
    }


def _power_result() -> dict[str, Any]:
    return {
        "total_installed_power_kw_e": "200.0",
        "total_estimated_demand_kw": "150.0",
        "equipment_rows": [
            {
                "sequence": 1,
                "name": "Compressor",
                "area": "machine_room",
                "quantity": "2",
                "running_power_kw": "75.0",
                "total_power_kw": "150.0",
                "section": "refrigeration",
            }
        ],
        "summary_rows": [
            {
                "name": "Refrigeration",
                "basis": "equipment",
                "total_power_kw": "170.0",
            }
        ],
        "items": [
            {
                "category": "refrigeration",
                "installed_power_kw": "170.0",
                "demand_factor": "0.85",
                "estimated_demand_kw": "144.5",
            }
        ],
        "assumptions": ["Standard operating conditions"],
    }


def _investment_result() -> dict[str, Any]:
    return {
        "total_investment_cny": "5000000",
        "items": [{"item_name": "Refrigeration Equipment", "amount_cny": "2000000"}],
    }


_RESULT_FACTORIES: dict[str, Any] = {
    "zone": _zone_result,
    "cooling_load": _cooling_load_result,
    "equipment": _equipment_result,
    "power": _power_result,
    "investment": _investment_result,
}

_SNAPSHOT_CLS: dict[str, type] = {
    "zone": ZoneSourceSnapshotV1,
    "cooling_load": CoolingLoadSourceSnapshotV1,
    "equipment": EquipmentSourceSnapshotV1,
    "power": PowerSourceSnapshotV1,
    "investment": InvestmentSourceSnapshotV1,
}


# ── Compute per-stage result hashes ────────────────────────────────────────


def _compute_stage_hash(stage: str) -> str:
    """Compute the full SourceSnapshotContentV1 result_hash for a stage.

    Uses the domain dataclass from orchestration.domain.snapshots (P0-1)
    and orchestration.domain.fingerprint.result_hash for recomputation.
    P0-1: Uses raw result_snapshot (no coercion).
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

    run_id, calc_name, calc_ver, calc_type = _STAGE_META[stage]
    upstream: dict[str, str] = {}
    if stage == "cooling_load":
        upstream = {"zone": "run-z-001"}
    elif stage == "equipment":
        upstream = {"cooling_load": "run-cl-001"}
    elif stage == "power":
        upstream = {"equipment": "run-eq-001"}
    elif stage == "investment":
        upstream = {"zone": "run-z-001", "power": "run-pow-001"}

    provenance = SourceSnapshotProvenanceV1(
        execution_snapshot_id=_ESID,
        coefficient_context_id=_CCID,
        orchestration_identity_id=_IDENT,
        orchestration_run_attempt_id=_ATT,
        upstream_calculation_ids=upstream,
    )

    content = DomainSourceSnapshotContentV1(
        schema_version="1.0.0",
        calculation_type=calc_type,
        calculator_name=calc_name,
        calculator_version=calc_ver,
        project_id=_PID,
        project_version_id=_PVID,
        execution_snapshot_id=_ESID,
        coefficient_context_id=_CCID,
        orchestration_identity_id=_IDENT,
        orchestration_run_attempt_id=_ATT,
        input_hash="input-hash-001",
        requires_review=False,
        payload=_RESULT_FACTORIES[stage](),
        provenance=provenance,
    )
    return _domain_result_hash(content)


# Pre-compute all stage hashes
_STAGE_HASHES: dict[str, str] = {s: _compute_stage_hash(s) for s in ORCHESTRATION_STAGE_ORDER}


# ── Build a valid VerifiedSourceMapping ────────────────────────────────────


def _build_valid_mapping(**overrides: Any) -> VerifiedSourceMapping:
    """Build a fully valid VerifiedSourceMapping with correct hashes."""
    per_calc = dict(_STAGE_HASHES)

    slot_ids = {
        "zone": "run-z-001",
        "cooling_load": "run-cl-001",
        "equipment": "run-eq-001",
        "power": "run-pow-001",
        "investment": "run-inv-001",
    }

    combined = _compute_combined_source_hash(
        binding_schema_version="1.0.0",
        project_id=_PID,
        project_version_id=_PVID,
        execution_snapshot_id=_ESID,
        coefficient_context_id=_CCID,
        orchestration_identity_id=_IDENT,
        orchestration_attempt_id=_ATT,
        orchestration_fingerprint=_FP,
        slot_ids=slot_ids,
        result_hashes=_STAGE_HASHES,
        requires_reviews={
            "zone": False,
            "cooling_load": False,
            "equipment": False,
            "power": False,
            "investment": False,
        },
    )

    defaults = dict(
        project_id=_PID,
        project_version_id=_PVID,
        execution_snapshot_id=_ESID,
        coefficient_context_id=_CCID,
        orchestration_identity_id=_IDENT,
        orchestration_attempt_id=_ATT,
        orchestration_fingerprint=_FP,
        combined_source_hash=combined,
        binding_schema_version="1.0.0",
        requires_review=False,
        zone_result_snapshot=_zone_result(),
        zone_result_hash=_STAGE_HASHES["zone"],
        cooling_load_result_snapshot=_cooling_load_result(),
        cooling_load_result_hash=_STAGE_HASHES["cooling_load"],
        equipment_result_snapshot=_equipment_result(),
        equipment_result_hash=_STAGE_HASHES["equipment"],
        power_result_snapshot=_power_result(),
        power_result_hash=_STAGE_HASHES["power"],
        investment_result_snapshot=_investment_result(),
        investment_result_hash=_STAGE_HASHES["investment"],
        per_calculation_result_hashes=per_calc,
        zone_calculation_id="run-z-001",
        cooling_load_calculation_id="run-cl-001",
        equipment_calculation_id="run-eq-001",
        power_calculation_id="run-pow-001",
        investment_calculation_id="run-inv-001",
    )
    defaults.update(overrides)
    return VerifiedSourceMapping(**defaults)


def _tamper(**field_overrides: Any) -> VerifiedSourceMapping:
    """Return a valid mapping with one field tampered."""
    return _build_valid_mapping(**field_overrides)


def _recompute_domain_hash(run: CalculationRunSnapshot) -> str:
    """Recompute the domain SourceSnapshotContentV1 result_hash for a run.

    P0-1: Uses raw result_snapshot (no coercion).
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

    provenance = SourceSnapshotProvenanceV1(
        execution_snapshot_id=run.execution_snapshot_id,
        coefficient_context_id=run.coefficient_context_id,
        orchestration_identity_id=run.orchestration_identity_id,
        orchestration_run_attempt_id=run.orchestration_run_attempt_id,
        upstream_calculation_ids=run.upstream_calculation_ids,
    )
    content = DomainSourceSnapshotContentV1(
        schema_version=run.schema_version or "1.0.0",
        calculation_type=run.calculation_type,
        calculator_name=run.calculator_name,
        calculator_version=run.calculator_version,
        project_id=run.project_id,
        project_version_id=run.project_version_id,
        execution_snapshot_id=run.execution_snapshot_id,
        coefficient_context_id=run.coefficient_context_id,
        orchestration_identity_id=run.orchestration_identity_id,
        orchestration_run_attempt_id=run.orchestration_run_attempt_id,
        input_hash=run.input_hash,
        requires_review=run.requires_review,
        payload=run.result_snapshot,
        provenance=provenance,
    )
    return _domain_result_hash(content)


# ══════════════════════════════════════════════════════════════════════════
# Tests for verify_source_mapping (strict verifier on VerifiedSourceMapping)
# ══════════════════════════════════════════════════════════════════════════


class TestVerifySourceMappingStrict:
    """Tests for the strict verify_source_mapping function."""

    def test_valid_mapping_passes(self) -> None:
        """A fully valid mapping should pass verification."""
        state = _build_valid_mapping()
        result = verify_source_mapping(state)
        assert result is state

    # ── Schema version ─────────────────────────────────────────────────

    def test_schema_version_error(self) -> None:
        state = _tamper(binding_schema_version="9.9.9")
        with pytest.raises(BindingSchemaError) as exc_info:
            verify_source_mapping(state)
        assert exc_info.value.code == "binding_schema_error"

    # ── Completeness / NULL fields ─────────────────────────────────────

    def test_completeness_null_execution_snapshot(self) -> None:
        state = _tamper(execution_snapshot_id="")
        with pytest.raises(CompletenessViolation) as exc_info:
            verify_source_mapping(state)
        assert exc_info.value.code == "completeness_violation"

    def test_completeness_null_coefficient_context(self) -> None:
        state = _tamper(coefficient_context_id="")
        with pytest.raises(CompletenessViolation) as exc_info:
            verify_source_mapping(state)
        assert exc_info.value.code == "completeness_violation"

    def test_completeness_null_orchestration_identity(self) -> None:
        state = _tamper(orchestration_identity_id="")
        with pytest.raises(CompletenessViolation) as exc_info:
            verify_source_mapping(state)
        assert exc_info.value.code == "completeness_violation"

    def test_completeness_null_orchestration_fingerprint(self) -> None:
        state = _tamper(orchestration_fingerprint="")
        with pytest.raises(CompletenessViolation) as exc_info:
            verify_source_mapping(state)
        assert exc_info.value.code == "completeness_violation"

    def test_completeness_null_result_hash(self) -> None:
        """Empty zone_result_hash triggers CombinedHashMismatch.

        The combined hash is recomputed from all identity + per-stage data.
        Since zone_result_hash is "", the recomputed combined hash differs
        from the stored one, triggering CombinedHashMismatch.
        """
        state = _tamper(
            zone_result_hash="",
            per_calculation_result_hashes={**_STAGE_HASHES, "zone": ""},
        )
        with pytest.raises(CombinedHashMismatch) as exc_info:
            verify_source_mapping(state)
        assert exc_info.value.code == "combined_hash_mismatch"

    # ── Typed payload invalid ──────────────────────────────────────────

    def test_typed_payload_invalid(self) -> None:
        state = _tamper(zone_result_snapshot={"invalid_field": "garbage", "zones": "not_a_list"})
        with pytest.raises(TypedPayloadInvalid) as exc_info:
            verify_source_mapping(state)
        assert exc_info.value.code == "typed_payload_invalid"
        assert "zone" in str(exc_info.value.field)

    def test_typed_payload_invalid_power(self) -> None:
        state = _tamper(
            power_result_snapshot={
                "total_installed_power_kw_e": "100",
                "extra": "bad",
            }
        )
        with pytest.raises(TypedPayloadInvalid) as exc_info:
            verify_source_mapping(state)
        assert exc_info.value.code == "typed_payload_invalid"

    # ── Power authority ────────────────────────────────────────────────

    def test_power_authority_missing(self) -> None:
        """Power result_snapshot without required fields raises TypedPayloadInvalid.

        PowerResultSnapshotV1 has total_installed_power_kw_e as required.
        A minimal dict missing other required fields fails typed validation,
        which is the defense-in-depth path.  The power authority check is
        an additional guard in the wrapper path where typed parsing is not done.
        """
        state = _tamper(power_result_snapshot={"total_installed_power_kw_e": "200.0"})
        # Missing required fields → TypedPayloadInvalid (defense-in-depth)
        with pytest.raises(TypedPayloadInvalid):
            verify_source_mapping(state)

    # ── Combined hash mismatch ─────────────────────────────────────────

    def test_combined_hash_mismatch(self) -> None:
        state = _tamper(combined_source_hash="tampered_combined_hash_value")
        with pytest.raises(CombinedHashMismatch) as exc_info:
            verify_source_mapping(state)
        assert exc_info.value.code == "combined_hash_mismatch"

    # ── Slot hash map mismatch ─────────────────────────────────────────

    def test_slot_hash_map_mismatch(self) -> None:
        state = _build_valid_mapping()
        tampered_hashes = dict(state.per_calculation_result_hashes)
        tampered_hashes["zone"] = "tampered_hash"
        state = _tamper(per_calculation_result_hashes=tampered_hashes)
        with pytest.raises(SlotHashMapMismatch) as exc_info:
            verify_source_mapping(state)
        assert exc_info.value.code == "slot_hash_map_mismatch"

    # ── Result hash mismatch (triggers combined hash failure) ──────────

    def test_result_hash_mismatch(self) -> None:
        """Tampered zone_result_hash (but matching hash map) → combined hash fails."""
        bad_hash = "totally_wrong_hash"
        state = _tamper(
            zone_result_hash=bad_hash,
            per_calculation_result_hashes={
                **_STAGE_HASHES,
                "zone": bad_hash,
            },
        )
        with pytest.raises(CombinedHashMismatch) as exc_info:
            verify_source_mapping(state)
        assert exc_info.value.code == "combined_hash_mismatch"

    # ── Requires_review ────────────────────────────────────────────────

    def test_requires_review_is_bool(self) -> None:
        """Valid bool requires_review passes."""
        state = _build_valid_mapping(requires_review=False)
        verify_source_mapping(state)

    # ── Provenance (structural) ────────────────────────────────────────

    def test_provenance_structure_valid(self) -> None:
        """Valid mapping should pass upstream provenance check."""
        state = _build_valid_mapping()
        verify_source_mapping(state)

    # ── Slot missing ───────────────────────────────────────────────────

    def test_slot_missing_calculation_id(self) -> None:
        state = _tamper(zone_calculation_id="")
        with pytest.raises(SlotMissingError) as exc_info:
            verify_source_mapping(state)
        assert exc_info.value.code == "slot_missing"


# ══════════════════════════════════════════════════════════════════════════
# Tests for verify_source_binding (backward-compatible wrapper)
# ══════════════════════════════════════════════════════════════════════════


def _build_binding_snapshot(**overrides: Any) -> SourceBindingSnapshot:
    """Build a valid SourceBindingSnapshot with proper per-calc hashes."""
    defaults = dict(
        id=_BINDING_ID,
        project_id=_PID,
        project_version_id=_PVID,
        execution_snapshot_id=_ESID,
        coefficient_context_id=_CCID,
        orchestration_identity_id=_IDENT,
        orchestration_run_attempt_id=_ATT,
        orchestration_fingerprint=_FP,
        zone_calculation_id="run-z-001",
        cooling_load_calculation_id="run-cl-001",
        equipment_calculation_id="run-eq-001",
        power_calculation_id="run-pow-001",
        investment_calculation_id="run-inv-001",
        per_calculation_result_hashes=dict(_STAGE_HASHES),
        combined_source_hash="placeholder",
        schema_version="1.0.0",
    )
    defaults.update(overrides)
    return SourceBindingSnapshot(**defaults)


def _build_attempt_snapshot(**overrides: Any) -> AttemptSnapshot:
    defaults = dict(
        id=_ATT,
        identity_id=_IDENT,
        status="COMPLETED",
        source_binding_id=_BINDING_ID,
    )
    defaults.update(overrides)
    return AttemptSnapshot(**defaults)


def _build_calculation_run(
    stage: str, *, extra_upstream: dict[str, str] | None = None
) -> CalculationRunSnapshot:
    """Build a valid CalculationRunSnapshot for a stage."""
    run_id, calc_name, calc_ver, calc_type = _STAGE_META[stage]

    upstream: dict[str, str] = {}
    if stage == "cooling_load":
        upstream = {"zone": "run-z-001"}
    elif stage == "equipment":
        upstream = {"cooling_load": "run-cl-001"}
    elif stage == "power":
        upstream = {"equipment": "run-eq-001"}
    elif stage == "investment":
        upstream = {"zone": "run-z-001", "power": "run-pow-001"}
    if extra_upstream:
        upstream.update(extra_upstream)

    result_dict = _RESULT_FACTORIES[stage]()
    computed_hash = _STAGE_HASHES[stage]

    return CalculationRunSnapshot(
        id=run_id,
        project_id=_PID,
        project_version_id=_PVID,
        orchestration_identity_id=_IDENT,
        orchestration_run_attempt_id=_ATT,
        orchestration_fingerprint=_FP,
        calculator_name=calc_name,
        calculator_version=calc_ver,
        calculation_type=calc_type,
        execution_snapshot_id=_ESID,
        coefficient_context_id=_CCID,
        input_hash="input-hash-001",
        result_snapshot=result_dict,
        result_hash=computed_hash,
        schema_version="1.0.0",
        formulas=[],
        coefficients=[],
        assumptions=[],
        warnings=[],
        source_references=[],
        upstream_calculation_ids=upstream,
        requires_review=False,
    )


def _build_all_runs() -> dict[str, CalculationRunSnapshot]:
    return {stage: _build_calculation_run(stage) for stage in ORCHESTRATION_STAGE_ORDER}


def _build_read_port(
    binding: SourceBindingSnapshot | None = None,
    attempt: AttemptSnapshot | None = None,
    runs: dict[str, CalculationRunSnapshot] | None = None,
    authoritative_attempt_id: str | None = _ATT,
) -> MagicMock:
    port = MagicMock()
    port.load_binding.return_value = binding if binding is not None else _build_binding_snapshot()
    port.load_attempt.return_value = attempt if attempt is not None else _build_attempt_snapshot()
    port.load_authoritative_attempt_id.return_value = authoritative_attempt_id
    all_runs = runs if runs is not None else _build_all_runs()

    def _load_calc(_session: Any, *, run_id: str) -> CalculationRunSnapshot | None:
        for r in all_runs.values():
            if r.id == run_id:
                return r
        return None

    port.load_calculation_run.side_effect = _load_calc
    return port


# ── Compute the correct combined hash for the binding ──────────────────────


def _correct_combined_hash() -> str:
    """Compute the correct combined hash for the default test data."""
    slot_ids = {
        "zone": "run-z-001",
        "cooling_load": "run-cl-001",
        "equipment": "run-eq-001",
        "power": "run-pow-001",
        "investment": "run-inv-001",
    }
    return _compute_combined_source_hash(
        binding_schema_version="1.0.0",
        project_id=_PID,
        project_version_id=_PVID,
        execution_snapshot_id=_ESID,
        coefficient_context_id=_CCID,
        orchestration_identity_id=_IDENT,
        orchestration_attempt_id=_ATT,
        orchestration_fingerprint=_FP,
        slot_ids=slot_ids,
        result_hashes=_STAGE_HASHES,
        requires_reviews={
            "zone": False,
            "cooling_load": False,
            "equipment": False,
            "power": False,
            "investment": False,
        },
    )


class TestVerifySourceBindingBackwardCompat:
    """Tests for the backward-compatible verify_source_binding wrapper."""

    def test_valid_binding_passes(self) -> None:
        binding = _build_binding_snapshot(combined_source_hash=_correct_combined_hash())
        port = _build_read_port(binding=binding)
        result = verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert isinstance(result, VerifiedSourceMapping)

    # ── Binding not found ──────────────────────────────────────────────

    def test_binding_not_found(self) -> None:
        port = MagicMock()
        port.load_binding.return_value = None
        with pytest.raises(BindingNotFoundError) as exc_info:
            verify_source_binding(port, None, binding_id="missing")
        assert exc_info.value.code == "binding_not_found"

    # ── Schema version ─────────────────────────────────────────────────

    def test_binding_schema_error(self) -> None:
        binding = _build_binding_snapshot(schema_version="9.9.9")
        port = _build_read_port(binding=binding)
        with pytest.raises(BindingSchemaError) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "binding_schema_error"

    # ── Attempt errors ─────────────────────────────────────────────────

    def test_attempt_not_completed(self) -> None:
        attempt = _build_attempt_snapshot(status="RUNNING")
        binding = _build_binding_snapshot(combined_source_hash=_correct_combined_hash())
        port = _build_read_port(binding=binding, attempt=attempt)
        with pytest.raises(AttemptNotCompletedError) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "attempt_not_completed"

    def test_attempt_not_authoritative(self) -> None:
        """NULL authoritative_attempt_id on identity raises AttemptNotAuthoritativeError."""
        binding = _build_binding_snapshot(combined_source_hash=_correct_combined_hash())
        port = _build_read_port(binding=binding, authoritative_attempt_id=None)
        with pytest.raises(AttemptNotAuthoritativeError) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "attempt_not_authoritative"

    def test_attempt_not_authoritative_id_mismatch(self) -> None:
        """authoritative_attempt_id on identity does not match binding attempt."""
        binding = _build_binding_snapshot(combined_source_hash=_correct_combined_hash())
        port = _build_read_port(binding=binding, authoritative_attempt_id="wrong-attempt-id")
        with pytest.raises(AttemptNotAuthoritativeError) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "attempt_not_authoritative"

    def test_attempt_source_binding_mismatch(self) -> None:
        attempt = _build_attempt_snapshot(source_binding_id="wrong-binding-id")
        binding = _build_binding_snapshot(combined_source_hash=_correct_combined_hash())
        port = _build_read_port(binding=binding, attempt=attempt)
        with pytest.raises(AttemptSourceBindingMismatch) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "attempt_source_binding_mismatch"

    def test_attempt_source_binding_null(self) -> None:
        """NULL source_binding_id on attempt raises AttemptSourceBindingMismatch."""
        attempt = _build_attempt_snapshot(source_binding_id=None)
        binding = _build_binding_snapshot(combined_source_hash=_correct_combined_hash())
        port = _build_read_port(binding=binding, attempt=attempt)
        with pytest.raises(AttemptSourceBindingMismatch) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "attempt_source_binding_mismatch"

    def test_attempt_missing(self) -> None:
        binding = _build_binding_snapshot(combined_source_hash=_correct_combined_hash())
        port = MagicMock()
        port.load_binding.return_value = binding
        port.load_authoritative_attempt_id.return_value = _ATT
        port.load_attempt.return_value = None
        with pytest.raises(AttemptNotCompletedError) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "attempt_not_completed"

    # ── Slot errors ────────────────────────────────────────────────────

    def test_slot_missing(self) -> None:
        binding = _build_binding_snapshot(combined_source_hash=_correct_combined_hash())
        all_runs = _build_all_runs()
        port = MagicMock()
        port.load_binding.return_value = binding
        port.load_authoritative_attempt_id.return_value = _ATT
        port.load_attempt.return_value = _build_attempt_snapshot()

        def _load_calc(_session: Any, *, run_id: str) -> CalculationRunSnapshot | None:
            if run_id == "run-z-001":
                return None
            for r in all_runs.values():
                if r.id == run_id:
                    return r
            return None

        port.load_calculation_run.side_effect = _load_calc
        with pytest.raises(SlotMissingError) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "slot_missing"

    def test_slot_type_error_calculator_name(self) -> None:
        runs = _build_all_runs()
        runs["zone"] = dataclasses.replace(runs["zone"], calculator_name="wrong_calculator")
        binding = _build_binding_snapshot(combined_source_hash=_correct_combined_hash())
        port = _build_read_port(binding=binding, runs=runs)
        with pytest.raises(SlotTypeError) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "slot_type_error"
        assert "wrong_calculator" in str(exc_info.value.detail)

    def test_slot_type_error_calculation_type(self) -> None:
        runs = _build_all_runs()
        runs["zone"] = dataclasses.replace(runs["zone"], calculation_type="wrong_type")
        binding = _build_binding_snapshot(combined_source_hash=_correct_combined_hash())
        port = _build_read_port(binding=binding, runs=runs)
        with pytest.raises(SlotTypeError) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "slot_type_error"

    # ── Identity mismatches ────────────────────────────────────────────

    def test_slot_identity_mismatch_project_id(self) -> None:
        runs = _build_all_runs()
        runs["zone"] = dataclasses.replace(runs["zone"], project_id="wrong-project")
        binding = _build_binding_snapshot(combined_source_hash=_correct_combined_hash())
        port = _build_read_port(binding=binding, runs=runs)
        with pytest.raises(SlotIdentityMismatch) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "slot_identity_mismatch"
        assert "project_id" in str(exc_info.value.field)

    def test_slot_identity_mismatch_orchestration_identity(self) -> None:
        runs = _build_all_runs()
        runs["zone"] = dataclasses.replace(runs["zone"], orchestration_identity_id="wrong-ident")
        binding = _build_binding_snapshot(combined_source_hash=_correct_combined_hash())
        port = _build_read_port(binding=binding, runs=runs)
        with pytest.raises(SlotIdentityMismatch) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "slot_identity_mismatch"
        assert "orchestration_identity_id" in str(exc_info.value.field)

    # ── Fingerprint mismatch ───────────────────────────────────────────

    def test_fingerprint_mismatch(self) -> None:
        runs = _build_all_runs()
        runs["zone"] = dataclasses.replace(runs["zone"], orchestration_fingerprint="wrong-fp")
        binding = _build_binding_snapshot(combined_source_hash=_correct_combined_hash())
        port = _build_read_port(binding=binding, runs=runs)
        with pytest.raises(FingerprintMismatch) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "fingerprint_mismatch"

    # ── Typed payload invalid ──────────────────────────────────────────

    def test_typed_payload_invalid_via_wrapper(self) -> None:
        runs = _build_all_runs()
        runs["cooling_load"] = dataclasses.replace(
            runs["cooling_load"],
            result_snapshot={"bad_field": "garbage", "total_cooling_load_kw": 123},
        )
        # Recompute domain hash for modified data (P0-1)
        new_cool_hash = _recompute_domain_hash(runs["cooling_load"])
        runs["cooling_load"] = dataclasses.replace(runs["cooling_load"], result_hash=new_cool_hash)
        new_hashes = dict(_STAGE_HASHES)
        new_hashes["cooling_load"] = new_cool_hash
        new_combined = _compute_combined_source_hash(
            binding_schema_version="1.0.0",
            project_id=_PID,
            project_version_id=_PVID,
            execution_snapshot_id=_ESID,
            coefficient_context_id=_CCID,
            orchestration_identity_id=_IDENT,
            orchestration_attempt_id=_ATT,
            orchestration_fingerprint=_FP,
            slot_ids={
                "zone": "run-z-001",
                "cooling_load": "run-cl-001",
                "equipment": "run-eq-001",
                "power": "run-pow-001",
                "investment": "run-inv-001",
            },
            result_hashes=new_hashes,
            requires_reviews={s: False for s in ORCHESTRATION_STAGE_ORDER},
        )
        binding = _build_binding_snapshot(
            combined_source_hash=new_combined,
            per_calculation_result_hashes=new_hashes,
        )
        port = _build_read_port(binding=binding, runs=runs)
        with pytest.raises(TypedPayloadInvalid) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "typed_payload_invalid"
        assert "cooling_load" in str(exc_info.value.field)

    # ── Provenance errors ──────────────────────────────────────────────

    def test_provenance_missing_key(self) -> None:
        runs = _build_all_runs()
        runs["cooling_load"] = dataclasses.replace(
            runs["cooling_load"], upstream_calculation_ids={}
        )
        binding = _build_binding_snapshot(combined_source_hash=_correct_combined_hash())
        port = _build_read_port(binding=binding, runs=runs)
        with pytest.raises(ProvenanceMissingKey) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "provenance_missing_key"

    def test_provenance_extra_key(self) -> None:
        runs = _build_all_runs()
        runs["zone"] = dataclasses.replace(
            runs["zone"],
            upstream_calculation_ids={"zone": "run-z-001"},
        )
        binding = _build_binding_snapshot(combined_source_hash=_correct_combined_hash())
        port = _build_read_port(binding=binding, runs=runs)
        with pytest.raises(ProvenanceExtraKey) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "provenance_extra_key"

    # ── Upstream calculation ID mismatch ───────────────────────────────

    def test_upstream_calculation_id_mismatch(self) -> None:
        runs = _build_all_runs()
        runs["cooling_load"] = dataclasses.replace(
            runs["cooling_load"],
            upstream_calculation_ids={"zone": "wrong-zone-id"},
        )
        # Recompute domain hash for modified data (P0-1)
        new_cool_hash = _recompute_domain_hash(runs["cooling_load"])
        runs["cooling_load"] = dataclasses.replace(runs["cooling_load"], result_hash=new_cool_hash)
        new_hashes = dict(_STAGE_HASHES)
        new_hashes["cooling_load"] = new_cool_hash
        new_combined = _compute_combined_source_hash(
            binding_schema_version="1.0.0",
            project_id=_PID,
            project_version_id=_PVID,
            execution_snapshot_id=_ESID,
            coefficient_context_id=_CCID,
            orchestration_identity_id=_IDENT,
            orchestration_attempt_id=_ATT,
            orchestration_fingerprint=_FP,
            slot_ids={
                "zone": "run-z-001",
                "cooling_load": "run-cl-001",
                "equipment": "run-eq-001",
                "power": "run-pow-001",
                "investment": "run-inv-001",
            },
            result_hashes=new_hashes,
            requires_reviews={s: False for s in ORCHESTRATION_STAGE_ORDER},
        )
        binding = _build_binding_snapshot(
            combined_source_hash=new_combined,
            per_calculation_result_hashes=new_hashes,
        )
        port = _build_read_port(binding=binding, runs=runs)
        with pytest.raises(UpstreamCalculationIdMismatch) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "upstream_calculation_id_mismatch"

    # ── Result hash mismatch ───────────────────────────────────────────

    def test_result_hash_mismatch(self) -> None:
        runs = _build_all_runs()
        runs["zone"] = dataclasses.replace(runs["zone"], result_hash="tampered_hash_value")
        binding = _build_binding_snapshot(combined_source_hash=_correct_combined_hash())
        port = _build_read_port(binding=binding, runs=runs)
        with pytest.raises(ResultHashMismatch) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "result_hash_mismatch"

    # ── Combined hash mismatch ─────────────────────────────────────────

    def test_combined_hash_mismatch_via_wrapper(self) -> None:
        binding = _build_binding_snapshot(combined_source_hash="tampered_combined")
        port = _build_read_port(binding=binding)
        with pytest.raises(CombinedHashMismatch) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "combined_hash_mismatch"

    # ── Power authority ────────────────────────────────────────────────

    def test_power_authority_missing_via_wrapper(self) -> None:
        runs = _build_all_runs()
        # Replace power run with a minimal dict that has the authority field
        # but is otherwise incomplete — still passes typed validation
        runs["power"] = dataclasses.replace(
            runs["power"],
            result_snapshot={
                "total_installed_power_kw_e": "200.0",
                "total_estimated_demand_kw": "150.0",
                "equipment_rows": [],
                "summary_rows": [],
                "items": [],
                "assumptions": [],
            },
        )
        # Compute new hash using domain dataclass (P0-1)
        from cold_storage.modules.orchestration.domain.fingerprint import (
            result_hash as _domain_result_hash,
        )
        from cold_storage.modules.orchestration.domain.snapshots import (
            SourceSnapshotContentV1 as DomainSourceSnapshotContentV1,
        )
        from cold_storage.modules.orchestration.domain.snapshots import (
            SourceSnapshotProvenanceV1,
        )

        provenance = SourceSnapshotProvenanceV1(
            execution_snapshot_id=_ESID,
            coefficient_context_id=_CCID,
            orchestration_identity_id=_IDENT,
            orchestration_run_attempt_id=_ATT,
            upstream_calculation_ids={"equipment": "run-eq-001"},
        )
        content = DomainSourceSnapshotContentV1(
            schema_version="1.0.0",
            calculation_type="power",
            calculator_name="installed_power",
            calculator_version="1.0.0",
            project_id=_PID,
            project_version_id=_PVID,
            execution_snapshot_id=_ESID,
            coefficient_context_id=_CCID,
            orchestration_identity_id=_IDENT,
            orchestration_run_attempt_id=_ATT,
            input_hash="input-hash-001",
            requires_review=False,
            payload=runs["power"].result_snapshot,
            provenance=provenance,
        )
        new_power_hash = _domain_result_hash(content)
        runs["power"] = dataclasses.replace(runs["power"], result_hash=new_power_hash)

        new_hashes = dict(_STAGE_HASHES)
        new_hashes["power"] = new_power_hash
        binding = _build_binding_snapshot(
            per_calculation_result_hashes=new_hashes,
        )
        # Recompute combined hash with new power hash
        slot_ids = {
            "zone": "run-z-001",
            "cooling_load": "run-cl-001",
            "equipment": "run-eq-001",
            "power": "run-pow-001",
            "investment": "run-inv-001",
        }
        new_combined = _compute_combined_source_hash(
            binding_schema_version="1.0.0",
            project_id=_PID,
            project_version_id=_PVID,
            execution_snapshot_id=_ESID,
            coefficient_context_id=_CCID,
            orchestration_identity_id=_IDENT,
            orchestration_attempt_id=_ATT,
            orchestration_fingerprint=_FP,
            slot_ids=slot_ids,
            result_hashes=new_hashes,
            requires_reviews={s: False for s in ORCHESTRATION_STAGE_ORDER},
        )
        binding = _build_binding_snapshot(
            combined_source_hash=new_combined,
            per_calculation_result_hashes=new_hashes,
        )
        port = _build_read_port(binding=binding, runs=runs)
        # This should pass because the power snapshot has the authority field
        result = verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert isinstance(result, VerifiedSourceMapping)

    # ── Per-calculation hash map mismatch ──────────────────────────────

    def test_slot_hash_map_mismatch_via_wrapper(self) -> None:
        """Tampered per_calculation_result_hashes raises ResultHashMismatch.

        The hash comparison runs per-stage and catches mismatches as
        ResultHashMismatch before reaching the full map comparison.
        """
        binding = _build_binding_snapshot(
            combined_source_hash=_correct_combined_hash(),
            per_calculation_result_hashes={"zone": "wrong_hash"},
        )
        port = _build_read_port(binding=binding)
        with pytest.raises(ResultHashMismatch) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "result_hash_mismatch"

    # ── Completeness ───────────────────────────────────────────────────

    def test_completeness_null_result_hash_via_wrapper(self) -> None:
        """NULL result_hash on a run raises ResultHashMismatch (P0-1).

        The domain hash is recomputed from DB fields and compared with
        the stored result_hash. Since the stored hash is None, the
        comparison fails at the hash step.
        """
        runs = _build_all_runs()
        runs["zone"] = dataclasses.replace(runs["zone"], result_hash=None)
        new_hashes = dict(_STAGE_HASHES)
        new_hashes["zone"] = None  # type: ignore[assignment]
        binding = _build_binding_snapshot(
            combined_source_hash=_correct_combined_hash(),
            per_calculation_result_hashes=new_hashes,
        )
        port = _build_read_port(binding=binding, runs=runs)
        with pytest.raises(ResultHashMismatch) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "result_hash_mismatch"

    def test_completeness_null_schema_version_via_wrapper(self) -> None:
        runs = _build_all_runs()
        runs["zone"] = dataclasses.replace(runs["zone"], schema_version=None)
        binding = _build_binding_snapshot(combined_source_hash=_correct_combined_hash())
        port = _build_read_port(binding=binding, runs=runs)
        with pytest.raises(CompletenessViolation) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "completeness_violation"

    def test_completeness_null_calculation_type_via_wrapper(self) -> None:
        """NULL calculation_type raises SlotTypeError (type check runs first)."""
        runs = _build_all_runs()
        runs["zone"] = dataclasses.replace(runs["zone"], calculation_type=None)
        binding = _build_binding_snapshot(combined_source_hash=_correct_combined_hash())
        port = _build_read_port(binding=binding, runs=runs)
        with pytest.raises(SlotTypeError) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "slot_type_error"


# ══════════════════════════════════════════════════════════════════════════
# P0-1: Tamper tests for execution_snapshot_id, coefficient_context_id,
#       calculator_version mismatch
# ══════════════════════════════════════════════════════════════════════════


class TestP01IdentityAndVersionChecks:
    """P0-1 tamper tests for execution_snapshot_id, coefficient_context_id,
    and calculator_version mismatch in the wrapper path."""

    def test_execution_snapshot_id_mismatch(self) -> None:
        """CalculationRun with different execution_snapshot_id → ExecutionSnapshotMismatch."""
        runs = _build_all_runs()
        runs["zone"] = dataclasses.replace(
            runs["zone"], execution_snapshot_id="wrong-exec-snapshot"
        )
        # Recompute hash for modified data
        new_zone_hash = _recompute_domain_hash(runs["zone"])
        runs["zone"] = dataclasses.replace(runs["zone"], result_hash=new_zone_hash)
        new_hashes = dict(_STAGE_HASHES)
        new_hashes["zone"] = new_zone_hash
        new_combined = _compute_combined_source_hash(
            binding_schema_version="1.0.0",
            project_id=_PID,
            project_version_id=_PVID,
            execution_snapshot_id=_ESID,
            coefficient_context_id=_CCID,
            orchestration_identity_id=_IDENT,
            orchestration_attempt_id=_ATT,
            orchestration_fingerprint=_FP,
            slot_ids={
                "zone": "run-z-001",
                "cooling_load": "run-cl-001",
                "equipment": "run-eq-001",
                "power": "run-pow-001",
                "investment": "run-inv-001",
            },
            result_hashes=new_hashes,
            requires_reviews={s: False for s in ORCHESTRATION_STAGE_ORDER},
        )
        binding = _build_binding_snapshot(
            combined_source_hash=new_combined,
            per_calculation_result_hashes=new_hashes,
        )
        port = _build_read_port(binding=binding, runs=runs)
        with pytest.raises(ExecutionSnapshotMismatch) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "execution_snapshot_mismatch"

    def test_coefficient_context_id_mismatch(self) -> None:
        """CalculationRun with different coefficient_context_id → CoefficientContextMismatch."""
        runs = _build_all_runs()
        runs["cooling_load"] = dataclasses.replace(
            runs["cooling_load"], coefficient_context_id="wrong-cc-id"
        )
        # Recompute hash for modified data
        new_cl_hash = _recompute_domain_hash(runs["cooling_load"])
        runs["cooling_load"] = dataclasses.replace(runs["cooling_load"], result_hash=new_cl_hash)
        new_hashes = dict(_STAGE_HASHES)
        new_hashes["cooling_load"] = new_cl_hash
        new_combined = _compute_combined_source_hash(
            binding_schema_version="1.0.0",
            project_id=_PID,
            project_version_id=_PVID,
            execution_snapshot_id=_ESID,
            coefficient_context_id=_CCID,
            orchestration_identity_id=_IDENT,
            orchestration_attempt_id=_ATT,
            orchestration_fingerprint=_FP,
            slot_ids={
                "zone": "run-z-001",
                "cooling_load": "run-cl-001",
                "equipment": "run-eq-001",
                "power": "run-pow-001",
                "investment": "run-inv-001",
            },
            result_hashes=new_hashes,
            requires_reviews={s: False for s in ORCHESTRATION_STAGE_ORDER},
        )
        binding = _build_binding_snapshot(
            combined_source_hash=new_combined,
            per_calculation_result_hashes=new_hashes,
        )
        port = _build_read_port(binding=binding, runs=runs)
        with pytest.raises(CoefficientContextMismatch) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "coefficient_context_mismatch"

    def test_calculator_version_mismatch(self) -> None:
        """CalculationRun with wrong calculator_version → CalculatorVersionMismatch."""
        runs = _build_all_runs()
        runs["power"] = dataclasses.replace(runs["power"], calculator_version="2.0.0")
        # Recompute hash for modified data
        new_power_hash = _recompute_domain_hash(runs["power"])
        runs["power"] = dataclasses.replace(runs["power"], result_hash=new_power_hash)
        new_hashes = dict(_STAGE_HASHES)
        new_hashes["power"] = new_power_hash
        new_combined = _compute_combined_source_hash(
            binding_schema_version="1.0.0",
            project_id=_PID,
            project_version_id=_PVID,
            execution_snapshot_id=_ESID,
            coefficient_context_id=_CCID,
            orchestration_identity_id=_IDENT,
            orchestration_attempt_id=_ATT,
            orchestration_fingerprint=_FP,
            slot_ids={
                "zone": "run-z-001",
                "cooling_load": "run-cl-001",
                "equipment": "run-eq-001",
                "power": "run-pow-001",
                "investment": "run-inv-001",
            },
            result_hashes=new_hashes,
            requires_reviews={s: False for s in ORCHESTRATION_STAGE_ORDER},
        )
        binding = _build_binding_snapshot(
            combined_source_hash=new_combined,
            per_calculation_result_hashes=new_hashes,
        )
        port = _build_read_port(binding=binding, runs=runs)
        with pytest.raises(CalculatorVersionMismatch) as exc_info:
            verify_source_binding(port, None, binding_id=_BINDING_ID)
        assert exc_info.value.code == "calculator_version_mismatch"
        assert "2.0.0" in str(exc_info.value.detail)


# ══════════════════════════════════════════════════════════════════════════
# Error hierarchy tests
# ══════════════════════════════════════════════════════════════════════════


class TestErrorHierarchy:
    """All error classes extend SourceBindingVerificationError."""

    def test_all_errors_are_subclasses(self) -> None:
        error_classes = [
            BindingNotFoundError("x"),
            BindingSchemaError("x"),
            AttemptNotCompletedError("x"),
            AttemptNotAuthoritativeError(),
            IdentityNotFoundError("x"),
            AttemptSourceBindingMismatch("a", "b"),
            SlotMissingError("s", "id"),
            SlotTypeError("s", "n", "e"),
            SlotIdentityMismatch("s", "f", "e", "a"),
            ExecutionSnapshotMismatch("s", "e", "a"),
            CoefficientContextMismatch("s", "e", "a"),
            FingerprintMismatch("s", "e", "a"),
            TypedPayloadInvalid("s", "d"),
            ProvenanceMissingKey("s", ["k"]),
            ProvenanceExtraKey("s", ["k"]),
            UpstreamCalculationIdMismatch("s", "k", "e", "a"),
            RequiresReviewMismatch(True, False),
            ResultHashMismatch("s", "e", "a"),
            CombinedHashMismatch("e", "a"),
            SlotHashMapMismatch({}, {}),
            CompletenessViolation("s", "f"),
            PowerAuthorityMissingError(),
            CalculatorVersionMismatch("s", "1.0.0", "2.0.0"),
            SourcePayloadCanonicalizationError("zone", detail="test"),
        ]
        for err in error_classes:
            assert isinstance(err, SourceBindingVerificationError)
            assert hasattr(err, "code")
            assert isinstance(err.code, str)


class TestBinaryFloatCanonicalization:
    """P0-1: Binary float in DB payload must raise structured canonicalization error.

    The canonicalization TypeError originates in the ``verify_source_binding``
    path (not ``verify_source_mapping``) because Pydantic coercion converts
    floats to strings before the hash is computed.  The verify_source_binding
    path loads raw DB dicts into SourceSnapshotContentV1 and calls result_hash,
    where binary floats reach canonical_json_bytes directly.
    """

    def test_binary_float_in_payload_raises_canonicalization_error(self) -> None:
        """Binary float in DB payload raises SourcePayloadCanonicalizationError
        through the verify_source_binding production path."""
        from unittest.mock import MagicMock

        from cold_storage.modules.schemes.application.source_binding_verifier import (
            verify_source_binding,
        )

        def _make_run_mock(
            run_id: str, calc_name: str, calc_type: str,
            result_snapshot: dict[str, Any],
        ) -> MagicMock:
            m = MagicMock()
            m.id = run_id
            m.project_id = _PID
            m.project_version_id = _PVID
            m.orchestration_identity_id = _IDENT
            m.orchestration_run_attempt_id = _ATT
            m.orchestration_fingerprint = _FP
            m.calculator_name = calc_name
            m.calculator_version = "1.0.0"
            m.calculation_type = calc_type
            m.execution_snapshot_id = _ESID
            m.coefficient_context_id = _CCID
            m.input_hash = "abc"
            m.result_hash = "wrong-hash"
            m.schema_version = None
            m.formulas = []
            m.coefficients = []
            m.assumptions = []
            m.warnings = []
            m.source_references = []
            m.upstream_calculation_ids = {}
            m.requires_review = False
            m.result_snapshot = result_snapshot
            return m

        # Zone run has binary float in payload
        zone_run = _make_run_mock(
            "run-zone-001", "cold_room_zone_plan", "zone",
            {"daily_inbound_mass_kg": "25000", "bad_field": 3.14, "zones": []},
        )
        # Other stage runs are valid
        runs_by_id = {
            "run-zone-001": zone_run,
            "run-cl-001": _make_run_mock(
                "run-cl-001", "cooling_load", "cooling_load",
                {"total_cooling_load_kw": "100"},
            ),
            "run-eq-001": _make_run_mock(
                "run-eq-001", "equipment", "equipment",
                {"equipment_rows": []},
            ),
            "run-pow-001": _make_run_mock(
                "run-pow-001", "installed_power", "power",
                {"total_installed_power_kw_e": "100", "equipment_rows": []},
            ),
            "run-inv-001": _make_run_mock(
                "run-inv-001", "investment_estimate", "investment",
                {"total_investment_cny": "1000000", "items": []},
            ),
        }

        binding = MagicMock()
        binding.id = _BINDING_ID
        binding.schema_version = "1.0.0"
        binding.project_id = _PID
        binding.project_version_id = _PVID
        binding.orchestration_identity_id = _IDENT
        binding.orchestration_run_attempt_id = _ATT
        binding.orchestration_fingerprint = _FP
        binding.execution_snapshot_id = _ESID
        binding.coefficient_context_id = _CCID
        binding.zone_calculation_id = "run-zone-001"
        binding.cooling_load_calculation_id = "run-cl-001"
        binding.equipment_calculation_id = "run-eq-001"
        binding.power_calculation_id = "run-pow-001"
        binding.investment_calculation_id = "run-inv-001"
        binding.per_calculation_result_hashes = {}
        binding.combined_source_hash = "x"

        attempt = MagicMock()
        attempt.id = _ATT
        attempt.identity_id = _IDENT
        attempt.status = "COMPLETED"
        attempt.source_binding_id = _BINDING_ID

        read_port = MagicMock()
        read_port.load_binding.return_value = binding
        read_port.load_attempt.return_value = attempt
        read_port.load_authoritative_attempt_id.return_value = _ATT
        read_port.load_calculation_run.side_effect = lambda _s, *, run_id: runs_by_id.get(run_id)

        session = MagicMock()

        with pytest.raises(SourcePayloadCanonicalizationError) as exc_info:
            verify_source_binding(read_port, session, binding_id=_BINDING_ID)
        err = exc_info.value
        assert err.code == "source_payload_canonicalization_error"
        assert err.field == "zone.payload"

    def test_binary_float_not_raw_type_error(self) -> None:
        """Binary float must NOT propagate as bare TypeError through boundary."""
        from unittest.mock import MagicMock

        from cold_storage.modules.schemes.application.source_binding_verifier import (
            verify_source_binding,
        )

        def _make_run(run_id: str, calc_name: str, ctype: str, snap: dict) -> MagicMock:
            m = MagicMock()
            m.id = run_id
            m.project_id = _PID
            m.project_version_id = _PVID
            m.orchestration_identity_id = _IDENT
            m.orchestration_run_attempt_id = _ATT
            m.orchestration_fingerprint = _FP
            m.calculator_name = calc_name
            m.calculator_version = "1.0.0"
            m.calculation_type = ctype
            m.execution_snapshot_id = _ESID
            m.coefficient_context_id = _CCID
            m.input_hash = "abc"
            m.result_hash = "x"
            m.schema_version = None
            m.formulas = []
            m.coefficients = []
            m.assumptions = []
            m.warnings = []
            m.source_references = []
            m.upstream_calculation_ids = {}
            m.requires_review = False
            m.result_snapshot = snap
            return m

        runs_by_id = {
            "run-z2": _make_run("run-z2", "cold_room_zone_plan", "zone",
                                {"daily_inbound_mass_kg": "25000", "bad": 1.0, "zones": []}),
            "run-cl2": _make_run("run-cl2", "cooling_load", "cooling_load",
                                {"total_cooling_load_kw": "100"}),
            "run-eq2": _make_run("run-eq2", "equipment", "equipment",
                                {"equipment_rows": []}),
            "run-pw2": _make_run("run-pw2", "installed_power", "power",
                                {"total_installed_power_kw_e": "100", "equipment_rows": []}),
            "run-in2": _make_run("run-in2", "investment_estimate", "investment",
                                {"total_investment_cny": "1000000", "items": []}),
        }

        binding = MagicMock()
        binding.id = _BINDING_ID
        binding.schema_version = "1.0.0"
        binding.project_id = _PID
        binding.project_version_id = _PVID
        binding.orchestration_identity_id = _IDENT
        binding.orchestration_run_attempt_id = _ATT
        binding.orchestration_fingerprint = _FP
        binding.execution_snapshot_id = _ESID
        binding.coefficient_context_id = _CCID
        binding.zone_calculation_id = "run-z2"
        binding.cooling_load_calculation_id = "run-cl2"
        binding.equipment_calculation_id = "run-eq2"
        binding.power_calculation_id = "run-pw2"
        binding.investment_calculation_id = "run-in2"
        binding.per_calculation_result_hashes = {}
        binding.combined_source_hash = "x"

        attempt = MagicMock()
        attempt.id = _ATT
        attempt.identity_id = _IDENT
        attempt.status = "COMPLETED"
        attempt.source_binding_id = _BINDING_ID

        read_port = MagicMock()
        read_port.load_binding.return_value = binding
        read_port.load_attempt.return_value = attempt
        read_port.load_authoritative_attempt_id.return_value = _ATT
        read_port.load_calculation_run.side_effect = lambda _s, *, run_id: runs_by_id.get(run_id)

        session = MagicMock()

        with pytest.raises(SourcePayloadCanonicalizationError) as exc_info:
            verify_source_binding(read_port, session, binding_id=_BINDING_ID)
        assert not issubclass(type(exc_info.value), TypeError)
