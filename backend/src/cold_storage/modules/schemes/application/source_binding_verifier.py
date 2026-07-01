"""Source binding verification adapter for SchemeService.

Independently loads a SourceBindingRecord and its five CalculationRun slots,
re-verifies all hashes and contracts, and produces a VerifiedSourceMapping
for scheme generation.  Fails closed on any mismatch.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from cold_storage.modules.schemes.application.production_ports import (
    CalculationRunSnapshot,
    SourceBindingReadPort,
    VerifiedSourceMapping,
)

# ── Slot definitions ───────────────────────────────────────────────────────

_SLOT_STAGE_ORDER: tuple[str, ...] = (
    "zone",
    "cooling_load",
    "equipment",
    "power",
    "investment",
)

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

_SUPPORTED_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1.0.0"})

_SLOT_BINDING_ATTRS: dict[str, str] = {
    "zone": "zone_calculation_id",
    "cooling_load": "cooling_load_calculation_id",
    "equipment": "equipment_calculation_id",
    "power": "power_calculation_id",
    "investment": "investment_calculation_id",
}


# ── Canonical hash helpers ─────────────────────────────────────────────────


def _canonical_json(obj: Any) -> str:
    """Stable JSON serialization: sorted keys, no extra whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _compute_result_hash(result_snapshot: dict[str, Any]) -> str:
    """SHA-256 of the canonical result snapshot."""
    return hashlib.sha256(_canonical_json(result_snapshot).encode()).hexdigest()


def _compute_combined_source_hash(
    per_calc_hashes: Mapping[str, str],
) -> str:
    """SHA-256 of the canonical combined hash map."""
    ordered = {stage: per_calc_hashes[stage] for stage in _SLOT_STAGE_ORDER}
    return hashlib.sha256(_canonical_json(ordered).encode()).hexdigest()


# ── Verification errors ────────────────────────────────────────────────────


class SourceBindingVerificationError(Exception):
    """Base error for source binding verification failures."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class BindingNotFoundError(SourceBindingVerificationError):
    def __init__(self, binding_id: str) -> None:
        super().__init__("binding_not_found", f"SourceBinding {binding_id!r} not found")


class BindingSchemaError(SourceBindingVerificationError):
    def __init__(self, schema_version: str) -> None:
        super().__init__(
            "binding_schema_unsupported",
            f"Binding schema_version {schema_version!r} not in {_SUPPORTED_SCHEMA_VERSIONS}",
        )


class AttemptNotCompletedError(SourceBindingVerificationError):
    def __init__(self, status: str) -> None:
        super().__init__(
            "attempt_not_completed",
            f"Attempt status is {status!r}, expected COMPLETED",
        )


class SlotMissingError(SourceBindingVerificationError):
    def __init__(self, stage: str, slot_id: str) -> None:
        super().__init__(
            "slot_missing",
            f"CalculationRun {slot_id!r} for stage {stage!r} not found",
        )


class SlotTypeError(SourceBindingVerificationError):
    def __init__(self, stage: str, calc_name: str, expected: str) -> None:
        super().__init__(
            "slot_type_mismatch",
            f"Stage {stage!r}: calculator_name={calc_name!r}, expected {expected!r}",
        )


class SlotSchemaError(SourceBindingVerificationError):
    def __init__(self, stage: str, schema_version: str) -> None:
        super().__init__(
            "slot_schema_unsupported",
            f"Stage {stage!r}: schema_version {schema_version!r} not in "
            f"{_SUPPORTED_SCHEMA_VERSIONS}",
        )


class ResultHashMismatchError(SourceBindingVerificationError):
    def __init__(self, stage: str, expected: str, actual: str) -> None:
        super().__init__(
            "result_hash_mismatch",
            f"Stage {stage!r}: expected hash {expected!r}, computed {actual!r}",
        )


class CombinedHashMismatchError(SourceBindingVerificationError):
    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(
            "combined_hash_mismatch",
            f"Combined source hash: expected {expected!r}, computed {actual!r}",
        )


class SlotHashMapMismatchError(SourceBindingVerificationError):
    def __init__(self, expected: dict[str, str], actual: dict[str, str]) -> None:
        super().__init__(
            "per_calc_hash_map_mismatch",
            f"Per-calculation hash map mismatch: expected {expected!r}, got {actual!r}",
        )


class PowerAuthorityMissingError(SourceBindingVerificationError):
    def __init__(self) -> None:
        super().__init__(
            "power_authority_missing",
            "Power result_snapshot missing total_installed_power_kw_e",
        )


# ── Verification adapter ───────────────────────────────────────────────────


def verify_source_binding(
    read_port: SourceBindingReadPort,
    session: Any,
    *,
    binding_id: str,
) -> VerifiedSourceMapping:
    """Load and independently re-verify a SourceBinding.

    Produces a VerifiedSourceMapping with verified hashes and five
    typed result snapshots.  Fails closed on any mismatch.
    """
    # 1. Load binding
    binding = read_port.load_binding(session, binding_id=binding_id)
    if binding is None:
        raise BindingNotFoundError(binding_id)

    # 2. Schema version
    if binding.schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
        raise BindingSchemaError(binding.schema_version)

    # 3. Load attempt and verify authoritative COMPLETED
    attempt = read_port.load_attempt(session, attempt_id=binding.orchestration_run_attempt_id)
    if attempt is None or attempt.status != "COMPLETED":
        raise AttemptNotCompletedError(attempt.status if attempt else "MISSING")

    # 4. Load and verify five CalculationRuns
    slot_ids = {
        "zone": binding.zone_calculation_id,
        "cooling_load": binding.cooling_load_calculation_id,
        "equipment": binding.equipment_calculation_id,
        "power": binding.power_calculation_id,
        "investment": binding.investment_calculation_id,
    }

    runs: dict[str, CalculationRunSnapshot] = {}
    for stage in _SLOT_STAGE_ORDER:
        slot_id = slot_ids[stage]
        run = read_port.load_calculation_run(session, run_id=slot_id)
        if run is None:
            raise SlotMissingError(stage, slot_id)

        # Verify calculator name
        expected_name = _SLOT_CALCULATOR_NAMES[stage]
        if run.calculator_name != expected_name:
            raise SlotTypeError(stage, run.calculator_name, expected_name)

        # Verify calculation type
        expected_type = _SLOT_CALCULATION_TYPES[stage]
        if run.calculation_type != expected_type:
            raise SlotTypeError(stage, run.calculation_type, expected_type)

        # Verify schema version
        if run.schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
            raise SlotSchemaError(stage, run.schema_version or "None")

        # Verify identity fields
        if run.project_id != binding.project_id:
            raise SourceBindingVerificationError(
                "project_mismatch",
                f"Stage {stage!r}: run project_id={run.project_id!r} != "
                f"binding project_id={binding.project_id!r}",
            )
        if run.project_version_id != binding.project_version_id:
            raise SourceBindingVerificationError(
                "version_mismatch",
                f"Stage {stage!r}: run project_version_id={run.project_version_id!r} != "
                f"binding project_version_id={binding.project_version_id!r}",
            )
        if run.orchestration_identity_id != binding.orchestration_identity_id:
            raise SourceBindingVerificationError(
                "identity_mismatch",
                f"Stage {stage!r}: run identity != binding identity",
            )

        # Verify result hash
        computed_hash = _compute_result_hash(run.result_snapshot)
        if computed_hash != run.result_hash:
            raise ResultHashMismatchError(stage, run.result_hash, computed_hash)

        runs[stage] = run

    # 5. Verify per-calculation hash map
    computed_per_calc = {stage: runs[stage].result_hash for stage in _SLOT_STAGE_ORDER}
    if computed_per_calc != binding.per_calculation_result_hashes:
        raise SlotHashMapMismatchError(binding.per_calculation_result_hashes, computed_per_calc)

    # 6. Verify combined source hash
    computed_combined = _compute_combined_source_hash(computed_per_calc)
    if computed_combined != binding.combined_source_hash:
        raise CombinedHashMismatchError(binding.combined_source_hash, computed_combined)

    # 7. Check requires_review — at least one slot with review needed means overall review
    any_review = any(r.requires_review for r in runs.values())

    # 8. Power authority — must have total_installed_power_kw_e
    power_snap = runs["power"].result_snapshot
    if "total_installed_power_kw_e" not in power_snap:
        raise PowerAuthorityMissingError()

    return VerifiedSourceMapping(
        project_id=binding.project_id,
        project_version_id=binding.project_version_id,
        execution_snapshot_id=binding.execution_snapshot_id,
        coefficient_context_id=binding.coefficient_context_id,
        orchestration_identity_id=binding.orchestration_identity_id,
        orchestration_attempt_id=binding.orchestration_run_attempt_id,
        orchestration_fingerprint=binding.orchestration_fingerprint,
        combined_source_hash=binding.combined_source_hash,
        binding_schema_version=binding.schema_version,
        requires_review=any_review,
        zone_result_snapshot=runs["zone"].result_snapshot,
        zone_result_hash=runs["zone"].result_hash,
        cooling_load_result_snapshot=runs["cooling_load"].result_snapshot,
        cooling_load_result_hash=runs["cooling_load"].result_hash,
        equipment_result_snapshot=runs["equipment"].result_snapshot,
        equipment_result_hash=runs["equipment"].result_hash,
        power_result_snapshot=runs["power"].result_snapshot,
        power_result_hash=runs["power"].result_hash,
        investment_result_snapshot=runs["investment"].result_snapshot,
        investment_result_hash=runs["investment"].result_hash,
        per_calculation_result_hashes=computed_per_calc,
        zone_calculation_id=slot_ids["zone"],
        cooling_load_calculation_id=slot_ids["cooling_load"],
        equipment_calculation_id=slot_ids["equipment"],
        power_calculation_id=slot_ids["power"],
        investment_calculation_id=slot_ids["investment"],
    )
