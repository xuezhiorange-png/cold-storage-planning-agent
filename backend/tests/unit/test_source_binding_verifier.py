"""Unit tests for SourceBindingVerifier — strict tamper matrix, authority, provenance.

Tests the ``SourceBindingVerifier`` in isolation using a mock
``VerificationReadPort`` that returns pre-built ``VerificationState`` objects.

Covers:
- Slot integrity (completeness, uniqueness, type matching)
- Identity integrity (project/version/snapshot/context/identity/attempt mismatches)
- Attempt authority (status lifecycle, identity-active gate)
- Hash integrity (result hash, per-calc hashes, combined hash, schema version)
- Stage set integrity (missing/extra stages, duplicate types, legacy partial runs)
- Upstream provenance (exact key sets per stage)
- Power authority (Pydantic model field validation, NaN/Infinity rejection)
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest
from pydantic import ValidationError

from cold_storage.modules.orchestration.application.source_snapshots import (
    CoolingLoadSourceSnapshotV1,
    EquipmentSourceSnapshotV1,
    InvestmentSourceSnapshotV1,
    PowerSourceSnapshotV1,
    ZoneSourceSnapshotV1,
)
from cold_storage.modules.orchestration.application.transaction_b import (
    SOURCE_BINDING_SCHEMA_VERSION,
    SOURCE_SNAPSHOT_SCHEMA_VERSION,
    CalculationRunSnapshot,
    SourceBindingVerifier,
    VerificationState,
    _compute_combined_source_hash,
)
from cold_storage.modules.orchestration.domain.contracts import (
    AttemptStatus,
    RequestStatus,
    SourceBindingCandidate,
)
from cold_storage.modules.orchestration.domain.dag import ORCHESTRATION_STAGE_ORDER
from cold_storage.modules.orchestration.domain.errors import (
    SourceBindingHashMismatchError,
    SourceBindingIdentityMismatchError,
    SourceBindingSlotTypeError,
    SourceSnapshotSchemaError,
    TransactionInvariantError,
    UnsupportedSchemaError,
)

# ── Canonical test constants ──────────────────────────────────────────────

_PID = "proj-001"
_PVID = "pver-001"
_ESID = "esnap-001"
_CCID = "cctx-001"
_IDENT = "ident-001"
_ATT = "att-001"
_FP = "fp-abc123"
_REQ = "req-001"

# stage → (run_id, calculator_name, calculator_version, calculation_type)
_STAGE_META: dict[str, tuple[str, str, str, str]] = {
    "zone": ("run-z-001", "cold_room_zone_plan", "1.0.0", "zone"),
    "cooling_load": ("run-cl-001", "cooling_load", "1.0.0", "cooling_load"),
    "equipment": ("run-eq-001", "equipment", "1.0.0", "equipment"),
    "power": ("run-pow-001", "installed_power", "1.0.0", "power"),
    "investment": ("run-inv-001", "investment_estimate", "1.0.0", "investment"),
}

# ── Realistic result snapshot dicts (parseable by Pydantic models) ────────


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


_RESULT_SNAPSHOTS: dict[str, dict[str, Any]] = {
    "zone": _zone_result(),
    "cooling_load": _cooling_load_result(),
    "equipment": _equipment_result(),
    "power": _power_result(),
    "investment": _investment_result(),
}

# ── Traceability fixtures ─────────────────────────────────────────────────


def _formulas(stage: str) -> list[dict[str, Any]]:
    return [
        {
            "formula_id": f"f-{stage}-01",
            "formula_version": "1.0.0",
            "expression": "Q = m * cp * dT",
            "description": f"Heat load for {stage}",
        }
    ]


def _coefficients() -> list[dict[str, Any]]:
    return [
        {
            "code": "pallet.net_load_kg",
            "value": "1000",
            "unit": "kg",
            "status": "approved",
            "source_type": "standard",
            "source_reference": "ref-1",
            "requires_review": False,
            "revision_id": "rev-001",
        }
    ]


def _warnings(stage: str) -> list[dict[str, Any]]:
    return [
        {
            "code": f"WARN_{stage.upper()}",
            "message": f"Review {stage}",
            "details": {},
        }
    ]


def _source_refs() -> list[dict[str, Any]]:
    return [
        {
            "source_type": "standard",
            "source_reference": "GB-2024",
            "version": "2024",
            "validity_status": "approved",
            "approval_status": "approved",
            "requires_review": False,
            "notes": "",
        }
    ]


def _assumptions(stage: str) -> list[str]:
    return [f"Assumption for {stage}"]


# ── Pydantic snapshot class map ───────────────────────────────────────────

_SNAPSHOT_CLS: dict[str, type] = {
    "zone": ZoneSourceSnapshotV1,
    "cooling_load": CoolingLoadSourceSnapshotV1,
    "equipment": EquipmentSourceSnapshotV1,
    "power": PowerSourceSnapshotV1,
    "investment": InvestmentSourceSnapshotV1,
}

# ── Upstream provenance map ───────────────────────────────────────────────


def _upstream_for(stage: str) -> dict[str, str]:
    """Return the correct upstream_calculation_ids for *stage*."""
    if stage == "zone":
        return {}
    if stage == "cooling_load":
        return {"zone": _STAGE_META["zone"][0]}
    if stage == "equipment":
        return {"cooling_load": _STAGE_META["cooling_load"][0]}
    if stage == "power":
        return {"equipment": _STAGE_META["equipment"][0]}
    if stage == "investment":
        return {
            "zone": _STAGE_META["zone"][0],
            "power": _STAGE_META["power"][0],
        }
    raise ValueError(f"Unknown stage: {stage}")


# ── CalculationRunSnapshot builder ────────────────────────────────────────


def _build_run(stage: str) -> CalculationRunSnapshot:
    """Build a valid CalculationRunSnapshot with correct result_hash."""
    run_id, calc_name, calc_ver, calc_type = _STAGE_META[stage]

    # Construct the Pydantic typed snapshot to compute result_hash
    snapshot = _SNAPSHOT_CLS[stage](
        project_id=_PID,
        project_version_id=_PVID,
        execution_snapshot_id=_ESID,
        coefficient_context_id=_CCID,
        orchestration_identity_id=_IDENT,
        orchestration_attempt_id=_ATT,
        orchestration_fingerprint=_FP,
        source_snapshot_schema_version="1.0.0",
        calculation_type=calc_type,
        calculator_id=calc_name,
        calculator_version=calc_ver,
        requires_review=False,
        result_snapshot=_RESULT_SNAPSHOTS[stage],
        formulas=_formulas(stage),
        coefficients=_coefficients(),
        assumptions=_assumptions(stage),
        warnings=_warnings(stage),
        source_references=_source_refs(),
        upstream_calculation_ids=_upstream_for(stage),
    )
    computed_hash = snapshot.result_hash()

    return CalculationRunSnapshot(
        id=run_id,
        calculator_name=calc_name,
        calculator_version=calc_ver,
        calculation_type=calc_type,
        result_snapshot=_RESULT_SNAPSHOTS[stage],
        result_hash=computed_hash,
        orchestration_identity_id=_IDENT,
        orchestration_run_attempt_id=_ATT,
        execution_snapshot_id=_ESID,
        coefficient_context_id=_CCID,
        orchestration_fingerprint=_FP,
        requires_review=False,
        schema_version=SOURCE_SNAPSHOT_SCHEMA_VERSION,
        project_id=_PID,
        project_version_id=_PVID,
        formulas=_formulas(stage),
        coefficients=_coefficients(),
        assumptions=_assumptions(stage),
        warnings=_warnings(stage),
        source_references=_source_refs(),
        upstream_calculation_ids=_upstream_for(stage),
    )


def _build_all_runs() -> dict[str, CalculationRunSnapshot]:
    """Build all five valid CalculationRunSnapshots keyed by stage name."""
    return {stage: _build_run(stage) for stage in ORCHESTRATION_STAGE_ORDER}


# ── VerificationState builder ─────────────────────────────────────────────


def _build_state(**overrides: Any) -> VerificationState:
    """Build a valid VerificationState, optionally overriding top-level fields."""
    state = VerificationState(
        request_status=str(RequestStatus.ACCEPTED),
        resolved_identity_id=_IDENT,
        resolved_attempt_id=_ATT,
        identity_fingerprint=_FP,
        identity_execution_snapshot_id=_ESID,
        identity_coefficient_context_id=_CCID,
        identity_authoritative_attempt_id=_ATT,
        attempt_identity_id=_IDENT,
        attempt_status=str(AttemptStatus.RUNNING),
        attempt_source_binding_id=None,
        calculation_runs=_build_all_runs(),
    )
    if overrides:
        state = dataclasses.replace(state, **overrides)
    return state


def _build_state_with_modified_run(stage: str, **run_overrides: Any) -> VerificationState:
    """Build a state where one CalculationRunSnapshot is modified.

    If the overrides affect the Pydantic model content (e.g. upstream_calculation_ids)
    but do NOT break Pydantic Literal constraints, the result_hash is recomputed
    so that schema+hash verification passes.
    """
    runs = _build_all_runs()
    old_run = runs[stage]

    # Fields whose change requires recomputing the result_hash because they
    # are included in the Pydantic model, but which do NOT break validation.
    _safe_rehash_fields = {
        "upstream_calculation_ids",
        "requires_review",
    }
    needs_rehash = (
        bool(set(run_overrides) & _safe_rehash_fields) and "result_hash" not in run_overrides
    )

    new_run = dataclasses.replace(old_run, **run_overrides)

    if needs_rehash:
        # Recompute result_hash from the modified run's data
        snapshot_cls = _SNAPSHOT_CLS[stage]
        fp = new_run.orchestration_fingerprint or _FP
        snapshot = snapshot_cls(
            project_id=new_run.project_id,
            project_version_id=new_run.project_version_id,
            execution_snapshot_id=new_run.execution_snapshot_id or "",
            coefficient_context_id=new_run.coefficient_context_id or "",
            orchestration_identity_id=new_run.orchestration_identity_id or "",
            orchestration_attempt_id=new_run.orchestration_run_attempt_id or "",
            orchestration_fingerprint=fp,
            source_snapshot_schema_version="1.0.0",
            calculation_type=new_run.calculation_type or "",
            calculator_id=new_run.calculator_name,
            calculator_version=new_run.calculator_version,
            requires_review=new_run.requires_review,
            result_snapshot=new_run.result_snapshot,
            formulas=new_run.formulas,
            coefficients=new_run.coefficients,
            assumptions=new_run.assumptions,
            warnings=new_run.warnings,
            source_references=new_run.source_references,
            upstream_calculation_ids=dict(new_run.upstream_calculation_ids),
        )
        new_run = dataclasses.replace(new_run, result_hash=snapshot.result_hash())

    runs[stage] = new_run
    return _build_state(calculation_runs=runs)


def _build_state_with_runs(runs: dict[str, CalculationRunSnapshot]) -> VerificationState:
    """Build a state with custom calculation_runs."""
    return _build_state(calculation_runs=runs)


# ── SourceBindingCandidate builder ────────────────────────────────────────


def _build_candidate(state: VerificationState, **overrides: Any) -> SourceBindingCandidate:
    """Build a valid candidate matching the state, optionally overriding fields."""
    runs = state.calculation_runs

    slot_ids = {stage: runs[stage].id for stage in ORCHESTRATION_STAGE_ORDER}
    result_hashes = {stage: runs[stage].result_hash or "" for stage in ORCHESTRATION_STAGE_ORDER}
    requires_reviews = {stage: runs[stage].requires_review for stage in ORCHESTRATION_STAGE_ORDER}

    # per_calculation_result_hashes: calculator_name → result_hash
    per_calc: dict[str, str] = {}
    for stage in ORCHESTRATION_STAGE_ORDER:
        run = runs[stage]
        per_calc[run.calculator_name] = run.result_hash or ""

    combined = _compute_combined_source_hash(
        binding_schema_version=SOURCE_BINDING_SCHEMA_VERSION,
        project_id=_PID,
        project_version_id=_PVID,
        execution_snapshot_id=_ESID,
        coefficient_context_id=_CCID,
        orchestration_identity_id=_IDENT,
        orchestration_attempt_id=_ATT,
        orchestration_fingerprint=_FP,
        slot_ids=slot_ids,
        result_hashes=result_hashes,
        requires_reviews=requires_reviews,
    )

    candidate = SourceBindingCandidate(
        identity_id=_IDENT,
        attempt_id=_ATT,
        fingerprint=_FP,
        zone_calculation_id=slot_ids["zone"],
        cooling_load_calculation_id=slot_ids["cooling_load"],
        equipment_calculation_id=slot_ids["equipment"],
        power_calculation_id=slot_ids["power"],
        investment_calculation_id=slot_ids["investment"],
        per_calculation_result_hashes=per_calc,
        combined_source_hash=combined,
        schema_version=SOURCE_BINDING_SCHEMA_VERSION,
    )
    if overrides:
        candidate = dataclasses.replace(candidate, **overrides)
    return candidate


# ── Mock VerificationReadPort ─────────────────────────────────────────────


class _MockVerificationReadPort:
    """Returns a pre-built ``VerificationState`` regardless of arguments."""

    def __init__(self, state: VerificationState) -> None:
        self._state = state

    def load_verification_state(
        self, session: Any, /, *, request_id: str, identity_id: str, attempt_id: str
    ) -> VerificationState:
        return self._state


# ── Verifier + verify helper ──────────────────────────────────────────────


def _make_verifier(state: VerificationState) -> SourceBindingVerifier:
    return SourceBindingVerifier(read_port=_MockVerificationReadPort(state))


def _run_verify(
    verifier: SourceBindingVerifier,
    candidate: SourceBindingCandidate,
    *,
    project_id: str = _PID,
    project_version_id: str = _PVID,
    execution_snapshot_id: str = _ESID,
    coefficient_context_id: str = _CCID,
    orchestration_fingerprint: str = _FP,
    identity_id: str = _IDENT,
    attempt_id: str = _ATT,
) -> None:
    """Run ``verify`` with sensible defaults."""
    verifier.verify(
        None,  # session (positional-only)
        request_id=_REQ,
        identity_id=identity_id,
        attempt_id=attempt_id,
        candidate=candidate,
        project_id=project_id,
        project_version_id=project_version_id,
        execution_snapshot_id=execution_snapshot_id,
        coefficient_context_id=coefficient_context_id,
        orchestration_fingerprint=orchestration_fingerprint,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Test class: Slot integrity
# ═══════════════════════════════════════════════════════════════════════════


class TestVerifierSlotIntegrity:
    """Slot completeness, uniqueness, calculator type, and calculator name."""

    def test_missing_slot(self) -> None:
        """calculation_runs dict missing one stage → TransactionInvariantError."""
        runs = _build_all_runs()
        del runs["equipment"]
        state = _build_state_with_runs(runs)
        # Candidate still references the equipment slot, but stage set check
        # (step 4) fires first because the state has only 4 stages.
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(TransactionInvariantError, match="Stage set mismatch"):
            _run_verify(verifier, candidate)

    def test_empty_slot_id(self) -> None:
        """Candidate has empty string for a slot → TransactionInvariantError."""
        state = _build_state()
        candidate = _build_candidate(state, zone_calculation_id="")
        verifier = _make_verifier(state)
        with pytest.raises(TransactionInvariantError, match="Slot .* is empty"):
            _run_verify(verifier, candidate)

    def test_duplicate_slot_id(self) -> None:
        """Two slots point to the same CalculationRun ID → TransactionInvariantError."""
        state = _build_state()
        # Give both zone and cooling_load the same ID
        candidate = _build_candidate(
            state,
            cooling_load_calculation_id=_STAGE_META["zone"][0],
        )
        verifier = _make_verifier(state)
        with pytest.raises(TransactionInvariantError, match="Duplicate calculation_run_id"):
            _run_verify(verifier, candidate)

    def test_wrong_calculation_type(self) -> None:
        """run.calculation_type != expected → SourceBindingSlotTypeError."""
        # Tamper the cooling_load run's calculation_type
        state = _build_state_with_modified_run("cooling_load", calculation_type="zone")
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingSlotTypeError):
            _run_verify(verifier, candidate)

    def test_wrong_calculator_name(self) -> None:
        """run.calculator_name != expected → SourceBindingSlotTypeError."""
        state = _build_state_with_modified_run("equipment", calculator_name="wrong_calculator")
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingSlotTypeError):
            _run_verify(verifier, candidate)

    def test_wrong_calculator_version(self) -> None:
        """run.calculator_version mismatch → no error at verifier level.

        The verifier checks calculation_type and calculator_name but NOT
        calculator_version in ``_verify_slots``.  The version is checked
        implicitly during Pydantic re-parse in ``_verify_schema_and_hashes``
        (Literal["1.0.0"] on each subclass).
        """
        state = _build_state_with_modified_run("zone", calculator_version="999.0.0")
        # The Pydantic model has calculator_version: Literal["1.0.0"],
        # so a mismatched version causes a re-parse failure.
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        with pytest.raises((SourceSnapshotSchemaError, Exception)):
            _run_verify(verifier, candidate)

    def test_equipment_in_power_slot(self) -> None:
        """Equipment run placed in power slot → SourceBindingSlotTypeError."""
        # Replace the power run with one that has equipment's type/name
        state = _build_state_with_modified_run(
            "power",
            calculation_type="equipment",
            calculator_name="equipment",
        )
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingSlotTypeError):
            _run_verify(verifier, candidate)

    def test_valid_slots_pass(self) -> None:
        """All 5 correct slots → no error."""
        state = _build_state()
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        # Should not raise
        _run_verify(verifier, candidate)


# ═══════════════════════════════════════════════════════════════════════════
# Test class: Identity integrity
# ═══════════════════════════════════════════════════════════════════════════


class TestVerifierIdentityIntegrity:
    """Per-run identity fields and candidate identity/attempt matching."""

    def test_wrong_project_id(self) -> None:
        """run.project_id != expected → SourceBindingIdentityMismatchError."""
        state = _build_state()
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingIdentityMismatchError, match="project_id"):
            _run_verify(verifier, candidate, project_id="WRONG_PROJECT")

    def test_wrong_project_version_id(self) -> None:
        state = _build_state()
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingIdentityMismatchError, match="project_version_id"):
            _run_verify(verifier, candidate, project_version_id="WRONG_PVER")

    def test_wrong_execution_snapshot_id(self) -> None:
        state = _build_state()
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingIdentityMismatchError, match="execution_snapshot_id"):
            _run_verify(verifier, candidate, execution_snapshot_id="WRONG_ESNAP")

    def test_wrong_coefficient_context_id(self) -> None:
        state = _build_state()
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingIdentityMismatchError, match="coefficient_context_id"):
            _run_verify(verifier, candidate, coefficient_context_id="WRONG_CCTX")

    def test_wrong_orchestration_identity_id(self) -> None:
        """run.orchestration_identity_id != expected → mismatch."""
        # Tamper one run's orchestration_identity_id to differ from the
        # identity_id parameter.  Authority check passes because
        # state.resolved_identity_id == identity_id.
        state = _build_state_with_modified_run("zone", orchestration_identity_id="WRONG_ORCH_IDENT")
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingIdentityMismatchError, match="orchestration_identity_id"):
            _run_verify(verifier, candidate)

    def test_wrong_orchestration_attempt_id(self) -> None:
        state = _build_state_with_modified_run(
            "equipment", orchestration_run_attempt_id="WRONG_ORCH_ATT"
        )
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        with pytest.raises(
            SourceBindingIdentityMismatchError, match="orchestration_run_attempt_id"
        ):
            _run_verify(verifier, candidate)

    def test_wrong_orchestration_fingerprint(self) -> None:
        # Change identity_fingerprint in the state so the authority check
        # catches it (state.identity_fingerprint != orchestration_fingerprint).
        state = _build_state(identity_fingerprint="WRONG_STATE_FP")
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingIdentityMismatchError, match="identity_fingerprint"):
            _run_verify(verifier, candidate)

    def test_attempt_not_belonging_to_identity(self) -> None:
        """attempt.identity_id != identity_id → SourceBindingIdentityMismatchError."""
        state = _build_state(attempt_identity_id="other-ident-999")
        candidate = _build_candidate(_build_state())  # valid candidate
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingIdentityMismatchError, match="attempt_identity_id"):
            _run_verify(verifier, candidate)


# ═══════════════════════════════════════════════════════════════════════════
# Test class: Attempt authority
# ═══════════════════════════════════════════════════════════════════════════


class TestVerifierAttemptAuthority:
    """Attempt status lifecycle and identity-active gate."""

    def test_attempt_status_pending(self) -> None:
        """attempt.status=PENDING → TransactionInvariantError.

        PENDING is not a valid AttemptStatus member but the verifier
        checks ``!= RUNNING`` so any non-RUNNING string is rejected.
        """
        state = _build_state(attempt_status="PENDING")
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(TransactionInvariantError, match="Attempt status"):
            _run_verify(verifier, candidate)

    def test_attempt_status_blocked(self) -> None:
        state = _build_state(attempt_status=str(AttemptStatus.BLOCKED))
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(TransactionInvariantError, match="Attempt status"):
            _run_verify(verifier, candidate)

    def test_attempt_status_failed(self) -> None:
        state = _build_state(attempt_status=str(AttemptStatus.FAILED))
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(TransactionInvariantError, match="Attempt status"):
            _run_verify(verifier, candidate)

    def test_attempt_status_completed(self) -> None:
        """COMPLETED (not RUNNING) → TransactionInvariantError."""
        state = _build_state(attempt_status=str(AttemptStatus.COMPLETED))
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(TransactionInvariantError, match="Attempt status"):
            _run_verify(verifier, candidate)

    def test_identity_inactive(self) -> None:
        """Identity superseded (resolved_identity_id=None) → mismatch error.

        When the identity is inactive/superseded the request no longer
        resolves to it, so ``resolved_identity_id`` will not match.
        """
        state = _build_state(resolved_identity_id=None)
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingIdentityMismatchError, match="resolved_identity_id"):
            _run_verify(verifier, candidate)


# ═══════════════════════════════════════════════════════════════════════════
# Test class: Hash integrity
# ═══════════════════════════════════════════════════════════════════════════


class TestVerifierHashIntegrity:
    """Result hash, per-calculation hash map, combined hash, schema version."""

    def test_result_hash_tampered(self) -> None:
        """Stored hash differs from recomputed → SourceBindingHashMismatchError."""
        state = _build_state()
        # Tamper one run's result_hash
        tampered_runs = dict(state.calculation_runs)
        tampered_runs["zone"] = dataclasses.replace(
            tampered_runs["zone"], result_hash="tampered_hash_value"
        )
        tampered_state = _build_state(calculation_runs=tampered_runs)

        # Candidate must pass steps 1-5; use original state for candidate
        # build (so slot IDs and identity match).
        candidate = _build_candidate(state)
        verifier = _make_verifier(tampered_state)
        with pytest.raises(SourceBindingHashMismatchError, match="result_hash"):
            _run_verify(verifier, candidate)

    def test_per_calc_hash_missing_key(self) -> None:
        """Candidate missing a calculator key → SourceBindingHashMismatchError."""
        state = _build_state()
        candidate = _build_candidate(state)
        # Remove one key from per_calculation_result_hashes
        tampered_hashes = dict(candidate.per_calculation_result_hashes)
        del tampered_hashes["cold_room_zone_plan"]
        tampered_candidate = dataclasses.replace(
            candidate, per_calculation_result_hashes=tampered_hashes
        )
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingHashMismatchError, match="per_calculation_result_hashes"):
            _run_verify(verifier, tampered_candidate)

    def test_per_calc_hash_extra_key(self) -> None:
        """Candidate has extra calculator key → SourceBindingHashMismatchError."""
        state = _build_state()
        candidate = _build_candidate(state)
        tampered_hashes = dict(candidate.per_calculation_result_hashes)
        tampered_hashes["bogus_calculator"] = "bogus_hash"
        tampered_candidate = dataclasses.replace(
            candidate, per_calculation_result_hashes=tampered_hashes
        )
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingHashMismatchError, match="per_calculation_result_hashes"):
            _run_verify(verifier, tampered_candidate)

    def test_per_calc_hash_wrong_value(self) -> None:
        """Wrong hash value → SourceBindingHashMismatchError."""
        state = _build_state()
        candidate = _build_candidate(state)
        tampered_hashes = dict(candidate.per_calculation_result_hashes)
        tampered_hashes["installed_power"] = "wrong_hash_value"
        tampered_candidate = dataclasses.replace(
            candidate, per_calculation_result_hashes=tampered_hashes
        )
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingHashMismatchError, match="per_calculation_result_hashes"):
            _run_verify(verifier, tampered_candidate)

    def test_combined_hash_tampered(self) -> None:
        """combined_source_hash wrong → SourceBindingHashMismatchError."""
        state = _build_state()
        candidate = _build_candidate(state, combined_source_hash="tampered_combined_hash")
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingHashMismatchError, match="combined_source_hash"):
            _run_verify(verifier, candidate)

    def test_binding_schema_unsupported(self) -> None:
        """Wrong schema_version → UnsupportedSchemaError."""
        state = _build_state()
        candidate = _build_candidate(state, schema_version="999.0.0")
        verifier = _make_verifier(state)
        with pytest.raises(UnsupportedSchemaError):
            _run_verify(verifier, candidate)


# ═══════════════════════════════════════════════════════════════════════════
# Test class: Stage set integrity
# ═══════════════════════════════════════════════════════════════════════════


class TestVerifierStageSetIntegrity:
    """Missing/extra stages, duplicate calculation types, legacy partial runs."""

    def test_missing_stage(self) -> None:
        """Only 4 runs → TransactionInvariantError."""
        runs = _build_all_runs()
        del runs["investment"]
        state = _build_state_with_runs(runs)
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(TransactionInvariantError, match="Stage set mismatch"):
            _run_verify(verifier, candidate)

    def test_extra_stage(self) -> None:
        """6 runs → TransactionInvariantError."""
        runs = _build_all_runs()
        # Add a bogus extra stage
        runs["bogus"] = dataclasses.replace(
            runs["zone"], id="run-bogus-001", calculation_type="bogus"
        )
        state = _build_state_with_runs(runs)
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(TransactionInvariantError, match="Stage set mismatch"):
            _run_verify(verifier, candidate)

    def test_duplicate_calculation_type(self) -> None:
        """Two runs with same calculation_type → TransactionInvariantError.

        Replacing a stage's calculation_type causes the stage set check to
        pass (same 5 stage names), but the slot type check catches the
        mismatch: e.g., ``cooling_load`` stage has ``calculation_type="zone"``
        which != expected ``"cooling_load"``.
        """
        state = _build_state_with_modified_run("cooling_load", calculation_type="zone")
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingSlotTypeError):
            _run_verify(verifier, candidate)

    def test_legacy_partial_run(self) -> None:
        """Orchestration fields NULL → rejected by the verifier.

        The verifier checks these fields in multiple earlier steps
        (slot type, run identity, schema+hash) before the final
        completeness sweep.  The first NULL field triggers the
        earliest applicable check.
        """
        state = _build_state_with_modified_run(
            "power",
            orchestration_identity_id=None,
            orchestration_run_attempt_id=None,
            execution_snapshot_id=None,
            coefficient_context_id=None,
            result_hash=None,
            schema_version=None,
            calculation_type=None,
        )
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        # The first check to fire depends on field → step mapping.
        # calculation_type=None → SourceBindingSlotTypeError (step 5).
        with pytest.raises(
            (
                TransactionInvariantError,
                SourceBindingSlotTypeError,
                SourceBindingIdentityMismatchError,
                SourceBindingHashMismatchError,
                SourceSnapshotSchemaError,
            )
        ):
            _run_verify(verifier, candidate)


# ═══════════════════════════════════════════════════════════════════════════
# Test class: Upstream provenance
# ═══════════════════════════════════════════════════════════════════════════


class TestVerifierUpstreamProvenance:
    """Exact upstream dependency provenance for each stage."""

    def test_zone_has_empty_provenance(self) -> None:
        """Zone upstream = {} → pass (zone is the DAG root)."""
        state = _build_state()
        # Zone's upstream is already {} in the valid fixture
        assert state.calculation_runs["zone"].upstream_calculation_ids == {}
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        _run_verify(verifier, candidate)

    def test_cooling_load_provenance(self) -> None:
        """{zone: zone_id} → pass."""
        state = _build_state()
        cl_upstream = state.calculation_runs["cooling_load"].upstream_calculation_ids
        assert cl_upstream == {"zone": _STAGE_META["zone"][0]}
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        _run_verify(verifier, candidate)

    def test_equipment_provenance(self) -> None:
        """{cooling_load: cl_id} → pass."""
        state = _build_state()
        eq_upstream = state.calculation_runs["equipment"].upstream_calculation_ids
        assert eq_upstream == {"cooling_load": _STAGE_META["cooling_load"][0]}
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        _run_verify(verifier, candidate)

    def test_power_provenance(self) -> None:
        """{equipment: eq_id} → pass."""
        state = _build_state()
        pow_upstream = state.calculation_runs["power"].upstream_calculation_ids
        assert pow_upstream == {"equipment": _STAGE_META["equipment"][0]}
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        _run_verify(verifier, candidate)

    def test_investment_provenance(self) -> None:
        """{zone: z_id, power: p_id} → pass."""
        state = _build_state()
        inv_upstream = state.calculation_runs["investment"].upstream_calculation_ids
        assert inv_upstream == {
            "zone": _STAGE_META["zone"][0],
            "power": _STAGE_META["power"][0],
        }
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        _run_verify(verifier, candidate)

    def test_missing_upstream_key(self) -> None:
        """cooling_load missing zone upstream → TransactionInvariantError."""
        state = _build_state_with_modified_run("cooling_load", upstream_calculation_ids={})
        # Rebuild candidate to match the tampered state's result hashes
        # (changing upstream doesn't change result_hash for this test since
        # the hash is recomputed from the Pydantic model which uses the
        # state's stored hash — but we need the candidate to pass steps 1-6).
        # Use original state for candidate so IDs and hashes are correct.
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(TransactionInvariantError, match="Provenance key set mismatch"):
            _run_verify(verifier, candidate)

    def test_extra_upstream_key(self) -> None:
        """Zone has extra upstream key -> TransactionInvariantError.

        Zone provenance keys are frozenset(). Adding an extra key
        triggers the exact key-set mismatch check.
        """
        tampered_upstream = {
            "extra_stage": "bogus-run-id",
        }
        state = _build_state_with_modified_run("zone", upstream_calculation_ids=tampered_upstream)
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(TransactionInvariantError, match="Provenance key set mismatch"):
            _run_verify(verifier, candidate)


# ═══════════════════════════════════════════════════════════════════════════
# Test class: Power authority
# ═══════════════════════════════════════════════════════════════════════════


class TestVerifierPowerAuthority:
    """Power-specific authority fields and Pydantic model validation."""

    def test_power_missing_authority_field(self) -> None:
        """PowerResultSnapshotV1 missing total_installed_power_kw_e → ValidationError.

        Tests the Pydantic model directly (not the verifier).
        """
        bad_snapshot = dict(_power_result())
        del bad_snapshot["total_installed_power_kw_e"]
        with pytest.raises(ValidationError):
            PowerSourceSnapshotV1(
                project_id=_PID,
                project_version_id=_PVID,
                execution_snapshot_id=_ESID,
                coefficient_context_id=_CCID,
                orchestration_identity_id=_IDENT,
                orchestration_attempt_id=_ATT,
                orchestration_fingerprint=_FP,
                source_snapshot_schema_version="1.0.0",
                calculation_type="power",
                calculator_id="installed_power",
                calculator_version="1.0.0",
                requires_review=False,
                result_snapshot=bad_snapshot,
                formulas=_formulas("power"),
                coefficients=_coefficients(),
                assumptions=_assumptions("power"),
                warnings=_warnings("power"),
                source_references=_source_refs(),
                upstream_calculation_ids=_upstream_for("power"),
            )

    def test_power_nan_authority_field(self) -> None:
        """NaN value for total_installed_power_kw_e → ValueError."""
        bad_snapshot = dict(_power_result())
        bad_snapshot["total_installed_power_kw_e"] = "NaN"
        with pytest.raises((ValueError, ValidationError)):
            PowerSourceSnapshotV1(
                project_id=_PID,
                project_version_id=_PVID,
                execution_snapshot_id=_ESID,
                coefficient_context_id=_CCID,
                orchestration_identity_id=_IDENT,
                orchestration_attempt_id=_ATT,
                orchestration_fingerprint=_FP,
                source_snapshot_schema_version="1.0.0",
                calculation_type="power",
                calculator_id="installed_power",
                calculator_version="1.0.0",
                requires_review=False,
                result_snapshot=bad_snapshot,
                formulas=_formulas("power"),
                coefficients=_coefficients(),
                assumptions=_assumptions("power"),
                warnings=_warnings("power"),
                source_references=_source_refs(),
                upstream_calculation_ids=_upstream_for("power"),
            )

    def test_power_infinity_authority_field(self) -> None:
        """Infinity value for total_installed_power_kw_e → ValueError."""
        bad_snapshot = dict(_power_result())
        bad_snapshot["total_installed_power_kw_e"] = "Infinity"
        with pytest.raises((ValueError, ValidationError)):
            PowerSourceSnapshotV1(
                project_id=_PID,
                project_version_id=_PVID,
                execution_snapshot_id=_ESID,
                coefficient_context_id=_CCID,
                orchestration_identity_id=_IDENT,
                orchestration_attempt_id=_ATT,
                orchestration_fingerprint=_FP,
                source_snapshot_schema_version="1.0.0",
                calculation_type="power",
                calculator_id="installed_power",
                calculator_version="1.0.0",
                requires_review=False,
                result_snapshot=bad_snapshot,
                formulas=_formulas("power"),
                coefficients=_coefficients(),
                assumptions=_assumptions("power"),
                warnings=_warnings("power"),
                source_references=_source_refs(),
                upstream_calculation_ids=_upstream_for("power"),
            )

    def test_equipment_run_in_power_slot(self) -> None:
        """Equipment calc placed in power slot → SourceBindingSlotTypeError."""
        state = _build_state_with_modified_run(
            "power",
            calculation_type="equipment",
            calculator_name="equipment",
        )
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingSlotTypeError):
            _run_verify(verifier, candidate)

    def test_investment_uses_equipment_id_instead_of_power(self) -> None:
        """Investment provenance has equipment ID for power key → error.

        Investment depends on {zone, power}.  If the power upstream key
        points to the equipment run's ID instead of the power run's ID,
        the verifier detects the mismatch.
        """
        tampered_upstream = {
            "zone": _STAGE_META["zone"][0],
            "power": _STAGE_META["equipment"][0],  # wrong: equipment ID instead of power
        }
        state = _build_state_with_modified_run(
            "investment", upstream_calculation_ids=tampered_upstream
        )
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(TransactionInvariantError, match="Upstream dependency mismatch"):
            _run_verify(verifier, candidate)


# ═══════════════════════════════════════════════════════════════════════════
# Test class: Tamper matrix — extended
# ═══════════════════════════════════════════════════════════════════════════


class TestVerifierTamperMatrixExtended:
    """Extended tamper matrix: result_snapshot content, requires_review,
    source snapshot schema, extra upstream keys, non-authoritative attempt.
    """

    def test_result_snapshot_content_tamper_zone(self) -> None:
        """Modify a value in zone result_snapshot → result_hash mismatch.

        The stored hash was computed from the original data.  Tampering
        the result_snapshot content causes the re-parsed Pydantic model
        to produce a different hash.
        """
        state = _build_state()
        tampered_runs = dict(state.calculation_runs)
        zone_run = tampered_runs["zone"]
        tampered_result = dict(zone_run.result_snapshot)
        tampered_result["total_area_m2"] = "999999"
        tampered_runs["zone"] = dataclasses.replace(zone_run, result_snapshot=tampered_result)
        tampered_state = _build_state(calculation_runs=tampered_runs)
        candidate = _build_candidate(state)
        verifier = _make_verifier(tampered_state)
        with pytest.raises(SourceBindingHashMismatchError, match="result_hash"):
            _run_verify(verifier, candidate)

    def test_result_snapshot_content_tamper_power(self) -> None:
        """Modify power authority field in result_snapshot → result_hash mismatch."""
        state = _build_state()
        tampered_runs = dict(state.calculation_runs)
        power_run = tampered_runs["power"]
        tampered_result = dict(power_run.result_snapshot)
        tampered_result["total_installed_power_kw_e"] = "999999.0"
        tampered_runs["power"] = dataclasses.replace(power_run, result_snapshot=tampered_result)
        tampered_state = _build_state(calculation_runs=tampered_runs)
        candidate = _build_candidate(state)
        verifier = _make_verifier(tampered_state)
        with pytest.raises(SourceBindingHashMismatchError, match="result_hash"):
            _run_verify(verifier, candidate)

    def test_result_snapshot_content_tamper_investment(self) -> None:
        """Modify investment total in result_snapshot → result_hash mismatch."""
        state = _build_state()
        tampered_runs = dict(state.calculation_runs)
        inv_run = tampered_runs["investment"]
        tampered_result = dict(inv_run.result_snapshot)
        tampered_result["total_investment_cny"] = "1"
        tampered_runs["investment"] = dataclasses.replace(inv_run, result_snapshot=tampered_result)
        tampered_state = _build_state(calculation_runs=tampered_runs)
        candidate = _build_candidate(state)
        verifier = _make_verifier(tampered_state)
        with pytest.raises(SourceBindingHashMismatchError, match="result_hash"):
            _run_verify(verifier, candidate)

    def test_requires_review_mismatch(self) -> None:
        """requires_review differs between state and candidate → hash mismatch.

        The state has requires_review=True for power (hash recomputed).
        The candidate was built from original state (requires_review=False).
        Per-calculation result hash mismatch catches the discrepancy.
        """
        original_state = _build_state()
        state = _build_state_with_modified_run("power", requires_review=True)
        candidate = _build_candidate(original_state)
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingHashMismatchError):
            _run_verify(verifier, candidate)

    def test_requires_review_mismatch_zone(self) -> None:
        """requires_review differs for zone → combined hash mismatch.

        Zone's result_hash does not change (zone's Pydantic model includes
        requires_review, but the hash is recomputed).  The combined hash
        includes requires_reviews for all stages, so a mismatch in zone
        causes combined hash failure.
        """
        original_state = _build_state()
        state = _build_state_with_modified_run("zone", requires_review=True)
        candidate = _build_candidate(original_state)
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingHashMismatchError):
            _run_verify(verifier, candidate)

    def test_source_snapshot_schema_unsupported(self) -> None:
        """Run's schema_version is unsupported → SourceSnapshotSchemaError."""
        state = _build_state_with_modified_run("zone", schema_version="999.0.0")
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(SourceSnapshotSchemaError):
            _run_verify(verifier, candidate)

    def test_source_snapshot_schema_null(self) -> None:
        """Run's schema_version is None → SourceSnapshotSchemaError."""
        state = _build_state_with_modified_run("cooling_load", schema_version=None)
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(SourceSnapshotSchemaError):
            _run_verify(verifier, candidate)

    def test_extra_upstream_key_caught_by_hash(self) -> None:
        """Extra upstream key without hash recompute → result_hash mismatch.

        cooling_load normally has {zone: id}.  Adding an extra key
        {zone: id, bogus: id} changes the Pydantic model's canonical
        output, causing the stored hash to not match the re-parsed hash.
        """
        original_state = _build_state()
        tampered_runs = dict(original_state.calculation_runs)
        cl_run = tampered_runs["cooling_load"]
        tampered_upstream = dict(cl_run.upstream_calculation_ids)
        tampered_upstream["bogus"] = "bogus-run-id"
        tampered_runs["cooling_load"] = dataclasses.replace(
            cl_run, upstream_calculation_ids=tampered_upstream
        )
        # Do NOT recompute hash — stored hash is from original data
        tampered_state = _build_state(calculation_runs=tampered_runs)
        candidate = _build_candidate(original_state)
        verifier = _make_verifier(tampered_state)
        with pytest.raises(SourceBindingHashMismatchError, match="result_hash"):
            _run_verify(verifier, candidate)

    def test_wrong_upstream_id_for_investment_zone_key(self) -> None:
        """Investment's zone upstream key points to wrong run → mismatch.

        Investment depends on {zone: zone_id, power: power_id}.
        If zone key points to cooling_load's ID instead of zone's ID,
        the verifier detects the mismatch.
        """
        tampered_upstream = {
            "zone": _STAGE_META["cooling_load"][0],  # wrong: points to cooling_load
            "power": _STAGE_META["power"][0],
        }
        state = _build_state_with_modified_run(
            "investment", upstream_calculation_ids=tampered_upstream
        )
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(TransactionInvariantError, match="Upstream dependency mismatch"):
            _run_verify(verifier, candidate)

    def test_wrong_upstream_id_for_equipment_key(self) -> None:
        """Equipment's cooling_load upstream points to zone ID → mismatch."""
        tampered_upstream = {
            "cooling_load": _STAGE_META["zone"][0],  # wrong: points to zone
        }
        state = _build_state_with_modified_run(
            "equipment", upstream_calculation_ids=tampered_upstream
        )
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(TransactionInvariantError, match="Upstream dependency mismatch"):
            _run_verify(verifier, candidate)

    def test_non_authoritative_attempt_mismatch(self) -> None:
        """resolved_attempt_id does not match attempt_id → mismatch.

        When the state's resolved_attempt_id differs from the attempt
        being verified, the verifier rejects it.
        """
        state = _build_state(resolved_attempt_id="other-attempt-999")
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingIdentityMismatchError, match="resolved_attempt_id"):
            _run_verify(verifier, candidate)


# ═══════════════════════════════════════════════════════════════════════════
# Test class: Slot integrity — per-stage coverage
# ═══════════════════════════════════════════════════════════════════════════


class TestVerifierSlotIntegrityPerStage:
    """Per-stage wrong calculation_type and wrong calculator_name coverage.

    Ensures every stage is individually tested for type/calculator mismatches.
    """

    def test_zone_wrong_calculation_type(self) -> None:
        """zone run has calculation_type != 'zone' → SourceBindingSlotTypeError."""
        state = _build_state_with_modified_run("zone", calculation_type="cooling_load")
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingSlotTypeError):
            _run_verify(verifier, candidate)

    def test_power_wrong_calculation_type(self) -> None:
        """power run has calculation_type != 'power' → SourceBindingSlotTypeError."""
        state = _build_state_with_modified_run("power", calculation_type="zone")
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingSlotTypeError):
            _run_verify(verifier, candidate)

    def test_investment_wrong_calculation_type(self) -> None:
        """investment run has calculation_type != 'investment' → SourceBindingSlotTypeError."""
        state = _build_state_with_modified_run("investment", calculation_type="power")
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingSlotTypeError):
            _run_verify(verifier, candidate)

    def test_zone_wrong_calculator_name(self) -> None:
        """zone run has wrong calculator_name → SourceBindingSlotTypeError."""
        state = _build_state_with_modified_run("zone", calculator_name="wrong_calc")
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingSlotTypeError):
            _run_verify(verifier, candidate)

    def test_cooling_load_wrong_calculator_name(self) -> None:
        """cooling_load run has wrong calculator_name → SourceBindingSlotTypeError."""
        state = _build_state_with_modified_run("cooling_load", calculator_name="wrong_calc")
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingSlotTypeError):
            _run_verify(verifier, candidate)

    def test_power_wrong_calculator_name(self) -> None:
        """power run has wrong calculator_name → SourceBindingSlotTypeError."""
        state = _build_state_with_modified_run("power", calculator_name="wrong_calc")
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingSlotTypeError):
            _run_verify(verifier, candidate)

    def test_investment_wrong_calculator_name(self) -> None:
        """investment run has wrong calculator_name → SourceBindingSlotTypeError."""
        state = _build_state_with_modified_run("investment", calculator_name="wrong_calc")
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingSlotTypeError):
            _run_verify(verifier, candidate)


# ═══════════════════════════════════════════════════════════════════════════
# Test class: Exact upstream provenance mapping
# ═══════════════════════════════════════════════════════════════════════════


class TestVerifierUpstreamProvenanceExact:
    """Exact upstream dependency provenance mapping per stage.

    DAG topology (from dag.py):
        zone -> {}                          (DAG root)
        cooling_load -> {zone}              (depends on zone)
        equipment -> {cooling_load}         (depends on cooling_load)
        power -> {equipment}                (depends on equipment)
        investment -> {zone, power}         (depends on zone + power)

    Tests verify both the correct mapping passes AND deviations are rejected.
    """

    def test_exact_mapping_zone_empty(self) -> None:
        """zone upstream = {} → pass (zone is DAG root, no dependencies)."""
        state = _build_state()
        zone_run = state.calculation_runs["zone"]
        assert zone_run.upstream_calculation_ids == {}, "Zone must have empty upstream (DAG root)"
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        _run_verify(verifier, candidate)

    def test_exact_mapping_cooling_load_zone(self) -> None:
        """cooling_load upstream = {zone: zone_run_id} → pass."""
        state = _build_state()
        cl_run = state.calculation_runs["cooling_load"]
        zone_run_id = state.calculation_runs["zone"].id
        assert cl_run.upstream_calculation_ids == {"zone": zone_run_id}
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        _run_verify(verifier, candidate)

    def test_exact_mapping_equipment_cooling_load(self) -> None:
        """equipment upstream = {cooling_load: cl_run_id} → pass."""
        state = _build_state()
        eq_run = state.calculation_runs["equipment"]
        cl_run_id = state.calculation_runs["cooling_load"].id
        assert eq_run.upstream_calculation_ids == {"cooling_load": cl_run_id}
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        _run_verify(verifier, candidate)

    def test_exact_mapping_power_equipment(self) -> None:
        """power upstream = {equipment: eq_run_id} → pass."""
        state = _build_state()
        pow_run = state.calculation_runs["power"]
        eq_run_id = state.calculation_runs["equipment"].id
        assert pow_run.upstream_calculation_ids == {"equipment": eq_run_id}
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        _run_verify(verifier, candidate)

    def test_exact_mapping_investment_zone_and_power(self) -> None:
        """investment upstream = {zone: z_id, power: p_id} → pass."""
        state = _build_state()
        inv_run = state.calculation_runs["investment"]
        zone_run_id = state.calculation_runs["zone"].id
        pow_run_id = state.calculation_runs["power"].id
        assert inv_run.upstream_calculation_ids == {
            "zone": zone_run_id,
            "power": pow_run_id,
        }
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        _run_verify(verifier, candidate)

    def test_missing_upstream_zone_for_cooling_load_rejected(self) -> None:
        """cooling_load missing zone key → TransactionInvariantError."""
        state = _build_state_with_modified_run("cooling_load", upstream_calculation_ids={})
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(TransactionInvariantError, match="Provenance key set mismatch"):
            _run_verify(verifier, candidate)

    def test_missing_upstream_cooling_load_for_equipment_rejected(self) -> None:
        """equipment missing cooling_load key → TransactionInvariantError."""
        state = _build_state_with_modified_run("equipment", upstream_calculation_ids={})
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(TransactionInvariantError, match="Provenance key set mismatch"):
            _run_verify(verifier, candidate)

    def test_missing_upstream_equipment_for_power_rejected(self) -> None:
        """power missing equipment key → TransactionInvariantError."""
        state = _build_state_with_modified_run("power", upstream_calculation_ids={})
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(TransactionInvariantError, match="Provenance key set mismatch"):
            _run_verify(verifier, candidate)

    def test_missing_upstream_zone_for_investment_rejected(self) -> None:
        """investment missing zone key (only has power) → TransactionInvariantError."""
        tampered = {"power": _STAGE_META["power"][0]}
        state = _build_state_with_modified_run("investment", upstream_calculation_ids=tampered)
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(TransactionInvariantError, match="Provenance key set mismatch"):
            _run_verify(verifier, candidate)

    def test_missing_upstream_power_for_investment_rejected(self) -> None:
        """investment missing power key (only has zone) → TransactionInvariantError."""
        tampered = {"zone": _STAGE_META["zone"][0]}
        state = _build_state_with_modified_run("investment", upstream_calculation_ids=tampered)
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(TransactionInvariantError, match="Provenance key set mismatch"):
            _run_verify(verifier, candidate)

    def test_wrong_stage_upstream_key_rejected(self) -> None:
        """cooling_load has upstream key 'equipment' instead of 'zone' → mismatch.

        The verifier looks for the 'zone' key (from STAGE_UPSTREAM_PROVENANCE_KEYS),
        finds it missing → TransactionInvariantError.
        """
        tampered = {"equipment": _STAGE_META["equipment"][0]}
        state = _build_state_with_modified_run("cooling_load", upstream_calculation_ids=tampered)
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(TransactionInvariantError, match="Provenance key set mismatch"):
            _run_verify(verifier, candidate)

    def test_wrong_upstream_value_for_zone_key_rejected(self) -> None:
        """cooling_load has zone key but wrong run ID → mismatch."""
        tampered = {"zone": _STAGE_META["equipment"][0]}  # wrong: equipment ID
        state = _build_state_with_modified_run("cooling_load", upstream_calculation_ids=tampered)
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(TransactionInvariantError, match="Upstream dependency mismatch"):
            _run_verify(verifier, candidate)

    def test_extra_upstream_key_caught_by_hash(self) -> None:
        """Extra upstream key without hash recompute -> hash mismatch.

        An extra key changes the Pydantic model's canonical output,
        causing the stored hash to not match the re-computed hash.
        The hash check runs before provenance, so it catches this first.
        """
        original_state = _build_state()
        tampered_runs = dict(original_state.calculation_runs)
        cl_run = tampered_runs["cooling_load"]
        tampered_upstream = dict(cl_run.upstream_calculation_ids)
        tampered_upstream["bogus_extra"] = "bogus-run-id"
        tampered_runs["cooling_load"] = dataclasses.replace(
            cl_run, upstream_calculation_ids=tampered_upstream
        )
        tampered_state = _build_state(calculation_runs=tampered_runs)
        candidate = _build_candidate(original_state)
        verifier = _make_verifier(tampered_state)
        with pytest.raises(SourceBindingHashMismatchError, match="result_hash"):
            _run_verify(verifier, candidate)


# ═══════════════════════════════════════════════════════════════════════════
# Test class: Power authority — negative tests
# ═══════════════════════════════════════════════════════════════════════════


class TestVerifierPowerAuthorityNegative:
    """Power authority negative tests.

    Covers:
    - Power stage missing from runs
    - Equipment CalculationRun placed in power slot (type + calculator)
    - Power calculator/name/type/version mismatches
    - Power payload missing authority field
    - Investment using wrong Power upstream ID
    - Equipment compressor power must not be fallback
    """

    def test_power_stage_missing_from_runs(self) -> None:
        """Power stage deleted from calculation_runs → Stage set mismatch."""
        runs = _build_all_runs()
        del runs["power"]
        state = _build_state_with_runs(runs)
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(TransactionInvariantError, match="Stage set mismatch"):
            _run_verify(verifier, candidate)

    def test_equipment_type_in_power_slot(self) -> None:
        """Equipment calculation_type in power slot → SourceBindingSlotTypeError."""
        state = _build_state_with_modified_run(
            "power",
            calculation_type="equipment",
            calculator_name="installed_power",
        )
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingSlotTypeError):
            _run_verify(verifier, candidate)

    def test_equipment_calculator_in_power_slot(self) -> None:
        """Equipment calculator_name in power slot → SourceBindingSlotTypeError."""
        state = _build_state_with_modified_run(
            "power",
            calculation_type="power",
            calculator_name="equipment",
        )
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingSlotTypeError):
            _run_verify(verifier, candidate)

    def test_power_wrong_calculator_name(self) -> None:
        """Power calculator_name != 'installed_power' → SourceBindingSlotTypeError."""
        state = _build_state_with_modified_run("power", calculator_name="wrong_power_calc")
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingSlotTypeError):
            _run_verify(verifier, candidate)

    def test_power_wrong_calculation_type(self) -> None:
        """Power calculation_type != 'power' → SourceBindingSlotTypeError."""
        state = _build_state_with_modified_run("power", calculation_type="zone")
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        with pytest.raises(SourceBindingSlotTypeError):
            _run_verify(verifier, candidate)

    def test_power_wrong_calculator_version(self) -> None:
        """Power calculator_version != '1.0.0' → Pydantic Literal error.

        The Pydantic model PowerSourceSnapshotV1 has
        calculator_version: Literal["1.0.0"], so a mismatched version
        causes a re-parse failure → SourceSnapshotSchemaError.
        """
        state = _build_state_with_modified_run("power", calculator_version="2.0.0")
        candidate = _build_candidate(state)
        verifier = _make_verifier(state)
        with pytest.raises((SourceSnapshotSchemaError, Exception)):
            _run_verify(verifier, candidate)

    def test_power_result_missing_total_installed_power_kw_e(self) -> None:
        """Power result_snapshot missing total_installed_power_kw_e → ValidationError.

        The PowerResultSnapshotV1 Pydantic model requires
        total_installed_power_kw_e as a mandatory field.
        """
        bad_snapshot = dict(_power_result())
        del bad_snapshot["total_installed_power_kw_e"]
        with pytest.raises(ValidationError):
            PowerSourceSnapshotV1(
                project_id=_PID,
                project_version_id=_PVID,
                execution_snapshot_id=_ESID,
                coefficient_context_id=_CCID,
                orchestration_identity_id=_IDENT,
                orchestration_attempt_id=_ATT,
                orchestration_fingerprint=_FP,
                source_snapshot_schema_version="1.0.0",
                calculation_type="power",
                calculator_id="installed_power",
                calculator_version="1.0.0",
                requires_review=False,
                result_snapshot=bad_snapshot,
                formulas=_formulas("power"),
                coefficients=_coefficients(),
                assumptions=_assumptions("power"),
                warnings=_warnings("power"),
                source_references=_source_refs(),
                upstream_calculation_ids=_upstream_for("power"),
            )

    def test_investment_uses_wrong_power_upstream_id(self) -> None:
        """Investment upstream power key points to equipment ID → mismatch.

        Investment depends on {zone, power}.  If the power key points to
        the equipment run's ID instead of the power run's ID, the verifier
        detects the mismatch.
        """
        tampered_upstream = {
            "zone": _STAGE_META["zone"][0],
            "power": _STAGE_META["equipment"][0],  # wrong: equipment ID
        }
        state = _build_state_with_modified_run(
            "investment", upstream_calculation_ids=tampered_upstream
        )
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(TransactionInvariantError, match="Upstream dependency mismatch"):
            _run_verify(verifier, candidate)

    def test_investment_upstream_power_points_to_cooling_load(self) -> None:
        """Investment upstream power key points to cooling_load ID → mismatch."""
        tampered_upstream = {
            "zone": _STAGE_META["zone"][0],
            "power": _STAGE_META["cooling_load"][0],  # wrong: cooling_load ID
        }
        state = _build_state_with_modified_run(
            "investment", upstream_calculation_ids=tampered_upstream
        )
        candidate = _build_candidate(_build_state())
        verifier = _make_verifier(state)
        with pytest.raises(TransactionInvariantError, match="Upstream dependency mismatch"):
            _run_verify(verifier, candidate)

    def test_equipment_compressor_power_not_fallback(self) -> None:
        """Equipment result with fallback compressor power → hash mismatch.

        If the equipment result_snapshot's compressor_operating_capacity_kw
        is tampered to a fallback value (e.g. '0'), the stored hash no
        longer matches the re-parsed Pydantic model's hash.  This ensures
        that any replacement of real compressor power with a fallback
        sentinel is detected by hash integrity.
        """
        state = _build_state()
        tampered_runs = dict(state.calculation_runs)
        eq_run = tampered_runs["equipment"]
        tampered_result = dict(eq_run.result_snapshot)
        tampered_result["compressor_operating_capacity_kw"] = "0.0"  # fallback sentinel
        tampered_runs["equipment"] = dataclasses.replace(eq_run, result_snapshot=tampered_result)
        # Do NOT recompute hash — stored hash is from original data
        tampered_state = _build_state(calculation_runs=tampered_runs)
        candidate = _build_candidate(state)
        verifier = _make_verifier(tampered_state)
        with pytest.raises(SourceBindingHashMismatchError, match="result_hash"):
            _run_verify(verifier, candidate)

    def test_power_result_total_installed_power_kw_e_nan(self) -> None:
        """NaN for total_installed_power_kw_e → ValueError/ValidationError."""
        bad_snapshot = dict(_power_result())
        bad_snapshot["total_installed_power_kw_e"] = "NaN"
        with pytest.raises((ValueError, ValidationError)):
            PowerSourceSnapshotV1(
                project_id=_PID,
                project_version_id=_PVID,
                execution_snapshot_id=_ESID,
                coefficient_context_id=_CCID,
                orchestration_identity_id=_IDENT,
                orchestration_attempt_id=_ATT,
                orchestration_fingerprint=_FP,
                source_snapshot_schema_version="1.0.0",
                calculation_type="power",
                calculator_id="installed_power",
                calculator_version="1.0.0",
                requires_review=False,
                result_snapshot=bad_snapshot,
                formulas=_formulas("power"),
                coefficients=_coefficients(),
                assumptions=_assumptions("power"),
                warnings=_warnings("power"),
                source_references=_source_refs(),
                upstream_calculation_ids=_upstream_for("power"),
            )

    def test_power_result_total_installed_power_kw_e_infinity(self) -> None:
        """Infinity for total_installed_power_kw_e → ValueError/ValidationError."""
        bad_snapshot = dict(_power_result())
        bad_snapshot["total_installed_power_kw_e"] = "Infinity"
        with pytest.raises((ValueError, ValidationError)):
            PowerSourceSnapshotV1(
                project_id=_PID,
                project_version_id=_PVID,
                execution_snapshot_id=_ESID,
                coefficient_context_id=_CCID,
                orchestration_identity_id=_IDENT,
                orchestration_attempt_id=_ATT,
                orchestration_fingerprint=_FP,
                source_snapshot_schema_version="1.0.0",
                calculation_type="power",
                calculator_id="installed_power",
                calculator_version="1.0.0",
                requires_review=False,
                result_snapshot=bad_snapshot,
                formulas=_formulas("power"),
                coefficients=_coefficients(),
                assumptions=_assumptions("power"),
                warnings=_warnings("power"),
                source_references=_source_refs(),
                upstream_calculation_ids=_upstream_for("power"),
            )
