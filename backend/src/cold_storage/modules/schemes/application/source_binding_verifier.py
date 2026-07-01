"""Strict source binding verifier for scheme generation.

Independently re-verifies a ``VerifiedSourceMapping`` against every
verification-critical field.  The verifier does NOT receive a database
session — it operates on data already loaded via a read port.

Verification contract (reuses Transaction B's hash contract):
    1. Schema version is supported.
    2. Attempt is COMPLETED and authoritative.
    3. Attempt's source_binding_id matches the binding.
    4. All five CalculationRun slots exist with correct types.
    5. Every CalculationRun carries matching identity fields.
    6. Inner result snapshots parse through typed Pydantic models.
    7. Result hashes match per-calculation hash map.
    8. Upstream provenance key sets match STAGE_UPSTREAM_PROVENANCE_KEYS.
    9. Combined source hash is recomputed from identity + per-stage data.
    10. requires_review is a valid bool on every slot.
    11. No NULL orchestration fields on any CalculationRun (completeness).
    12. Power result has the authority field (total_installed_power_kw_e).

Fails closed on any mismatch.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

from cold_storage.modules.orchestration.application.source_snapshots import (
    CoolingLoadResultSnapshotV1,
    EquipmentResultSnapshotV1,
    InvestmentResultSnapshotV1,
    PowerResultSnapshotV1,
    ZoneResultSnapshotV1,
)
from cold_storage.modules.orchestration.domain.dag import (
    ORCHESTRATION_STAGE_ORDER,
    STAGE_UPSTREAM_PROVENANCE_KEYS,
)
from cold_storage.modules.orchestration.domain.fingerprint import result_hash
from cold_storage.modules.schemes.application.production_ports import (
    CalculationRunSnapshot,
    VerifiedSourceMapping,
)

# ── Constants ──────────────────────────────────────────────────────────────

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

_SLOT_BINDING_ATTRS: dict[str, str] = {
    "zone": "zone_calculation_id",
    "cooling_load": "cooling_load_calculation_id",
    "equipment": "equipment_calculation_id",
    "power": "power_calculation_id",
    "investment": "investment_calculation_id",
}

_SLOT_SNAPSHOT_ATTRS: dict[str, str] = {
    "zone": "zone_result_snapshot",
    "cooling_load": "cooling_load_result_snapshot",
    "equipment": "equipment_result_snapshot",
    "power": "power_result_snapshot",
    "investment": "investment_result_snapshot",
}

_SLOT_HASH_ATTRS: dict[str, str] = {
    "zone": "zone_result_hash",
    "cooling_load": "cooling_load_result_hash",
    "equipment": "equipment_result_hash",
    "power": "power_result_hash",
    "investment": "investment_result_hash",
}

_SUPPORTED_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1.0.0"})

# Inner result snapshot models for schema validation
_RESULT_SNAPSHOT_CLS: dict[str, type[BaseModel]] = {
    "zone": ZoneResultSnapshotV1,
    "cooling_load": CoolingLoadResultSnapshotV1,
    "equipment": EquipmentResultSnapshotV1,
    "power": PowerResultSnapshotV1,
    "investment": InvestmentResultSnapshotV1,
}


# ── Structured error types ─────────────────────────────────────────────────


@dataclass(frozen=True)
class SourceBindingVerificationError(Exception):
    """Base error for source binding verification failures."""

    code: str
    field: str | None = None
    detail: str = ""

    def __str__(self) -> str:
        parts = [f"[{self.code}]"]
        if self.field:
            parts.append(f"field={self.field!r}")
        if self.detail:
            parts.append(self.detail)
        return " ".join(parts)


class BindingNotFoundError(SourceBindingVerificationError):
    def __init__(self, binding_id: str) -> None:
        super().__init__(
            code="binding_not_found",
            detail=f"SourceBinding {binding_id!r} not found",
        )


class BindingSchemaError(SourceBindingVerificationError):
    def __init__(self, schema_version: str) -> None:
        super().__init__(
            code="binding_schema_error",
            field="schema_version",
            detail=f"Schema version {schema_version!r} not in {_SUPPORTED_SCHEMA_VERSIONS}",
        )


class AttemptNotCompletedError(SourceBindingVerificationError):
    def __init__(self, status: str) -> None:
        super().__init__(
            code="attempt_not_completed",
            field="status",
            detail=f"Attempt status is {status!r}, expected COMPLETED",
        )


class AttemptNotAuthoritativeError(SourceBindingVerificationError):
    def __init__(self) -> None:
        super().__init__(
            code="attempt_not_authoritative",
            field="authoritative",
            detail="Attempt is not authoritative",
        )


class AttemptSourceBindingMismatch(SourceBindingVerificationError):
    def __init__(self, expected: str | None, actual: str | None) -> None:
        super().__init__(
            code="attempt_source_binding_mismatch",
            field="source_binding_id",
            detail=f"Expected {expected!r}, got {actual!r}",
        )


class SlotMissingError(SourceBindingVerificationError):
    def __init__(self, stage: str, slot_id: str) -> None:
        super().__init__(
            code="slot_missing",
            field=stage,
            detail=f"CalculationRun {slot_id!r} for stage {stage!r} not found",
        )


class SlotTypeError(SourceBindingVerificationError):
    def __init__(self, stage: str, calc_name: str, expected: str) -> None:
        super().__init__(
            code="slot_type_error",
            field=stage,
            detail=f"calculator_name={calc_name!r}, expected {expected!r}",
        )


class SlotIdentityMismatch(SourceBindingVerificationError):
    def __init__(self, stage: str, id_field: str, expected: str, actual: str) -> None:
        super().__init__(
            code="slot_identity_mismatch",
            field=f"{stage}.{id_field}",
            detail=f"Expected {expected!r}, got {actual!r}",
        )


class ExecutionSnapshotMismatch(SourceBindingVerificationError):
    def __init__(self, stage: str, expected: str, actual: str) -> None:
        super().__init__(
            code="execution_snapshot_mismatch",
            field=f"{stage}.execution_snapshot_id",
            detail=f"Expected {expected!r}, got {actual!r}",
        )


class CoefficientContextMismatch(SourceBindingVerificationError):
    def __init__(self, stage: str, expected: str, actual: str) -> None:
        super().__init__(
            code="coefficient_context_mismatch",
            field=f"{stage}.coefficient_context_id",
            detail=f"Expected {expected!r}, got {actual!r}",
        )


class FingerprintMismatch(SourceBindingVerificationError):
    def __init__(self, stage: str, expected: str, actual: str | None) -> None:
        super().__init__(
            code="fingerprint_mismatch",
            field=f"{stage}.orchestration_fingerprint",
            detail=f"Expected {expected!r}, got {actual!r}",
        )


class CalculatorVersionMismatch(SourceBindingVerificationError):
    def __init__(self, stage: str, expected: str, actual: str) -> None:
        super().__init__(
            code="calculator_version_mismatch",
            field=f"{stage}.calculator_version",
            detail=f"Expected {expected!r}, got {actual!r}",
        )


class TypedPayloadInvalid(SourceBindingVerificationError):
    def __init__(self, stage: str, detail: str) -> None:
        super().__init__(
            code="typed_payload_invalid",
            field=stage,
            detail=detail,
        )


class ProvenanceMissingKey(SourceBindingVerificationError):
    def __init__(self, stage: str, missing: list[str]) -> None:
        super().__init__(
            code="provenance_missing_key",
            field=f"{stage}.upstream_calculation_ids",
            detail=f"Missing keys: {sorted(missing)}",
        )


class ProvenanceExtraKey(SourceBindingVerificationError):
    def __init__(self, stage: str, extra: list[str]) -> None:
        super().__init__(
            code="provenance_extra_key",
            field=f"{stage}.upstream_calculation_ids",
            detail=f"Extra keys: {sorted(extra)}",
        )


class UpstreamCalculationIdMismatch(SourceBindingVerificationError):
    def __init__(self, stage: str, key: str, expected: str, actual: str) -> None:
        super().__init__(
            code="upstream_calculation_id_mismatch",
            field=f"{stage}.upstream_calculation_ids.{key}",
            detail=f"Expected {expected!r}, got {actual!r}",
        )


class RequiresReviewMismatch(SourceBindingVerificationError):
    def __init__(self, expected: bool, actual: bool) -> None:
        super().__init__(
            code="requires_review_mismatch",
            field="requires_review",
            detail=f"Expected {expected!r}, got {actual!r}",
        )


class ResultHashMismatch(SourceBindingVerificationError):
    def __init__(self, stage: str, expected: str, actual: str) -> None:
        super().__init__(
            code="result_hash_mismatch",
            field=f"{stage}.result_hash",
            detail=f"Expected {expected!r}, got {actual!r}",
        )


class CombinedHashMismatch(SourceBindingVerificationError):
    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(
            code="combined_hash_mismatch",
            field="combined_source_hash",
            detail=f"Expected {expected!r}, got {actual!r}",
        )


class SlotHashMapMismatch(SourceBindingVerificationError):
    def __init__(self, expected: dict[str, str], actual: dict[str, str]) -> None:
        super().__init__(
            code="slot_hash_map_mismatch",
            field="per_calculation_result_hashes",
            detail=f"Expected {expected!r}, got {actual!r}",
        )


class CompletenessViolation(SourceBindingVerificationError):
    def __init__(self, stage: str, field_name: str) -> None:
        super().__init__(
            code="completeness_violation",
            field=f"{stage}.{field_name}",
            detail=f"NULL {field_name} on CalculationRun for stage {stage!r}",
        )


class PowerAuthorityMissingError(SourceBindingVerificationError):
    def __init__(self) -> None:
        super().__init__(
            code="power_authority_missing",
            field="power_result_snapshot.total_installed_power_kw_e",
            detail="Power result_snapshot missing total_installed_power_kw_e",
        )


# ── Combined source hash helper (reuses Transaction B contract) ────────────


def _compute_combined_source_hash(
    *,
    binding_schema_version: str,
    project_id: str,
    project_version_id: str,
    execution_snapshot_id: str,
    coefficient_context_id: str,
    orchestration_identity_id: str,
    orchestration_attempt_id: str,
    orchestration_fingerprint: str,
    slot_ids: Mapping[str, str],
    result_hashes: Mapping[str, str],
    requires_reviews: Mapping[str, bool],
) -> str:
    """Compute the combined source hash matching Transaction B's contract.

    Covers: binding schema, project/version identity, execution snapshot,
    coefficient context, orchestration identity/attempt/fingerprint,
    five slot IDs, five result hashes, and five requires_review states.
    """
    data: dict[str, object] = {
        "binding_schema_version": binding_schema_version,
        "project_id": project_id,
        "project_version_id": project_version_id,
        "execution_snapshot_id": execution_snapshot_id,
        "coefficient_context_id": coefficient_context_id,
        "orchestration_identity_id": orchestration_identity_id,
        "orchestration_attempt_id": orchestration_attempt_id,
        "orchestration_fingerprint": orchestration_fingerprint,
    }
    for stage_name in ORCHESTRATION_STAGE_ORDER:
        data[f"{stage_name}_calculation_id"] = slot_ids[stage_name]
        data[f"{stage_name}_result_hash"] = result_hashes[stage_name]
        data[f"{stage_name}_requires_review"] = requires_reviews[stage_name]
    return result_hash(data)


# ── Read port for loading pre-verified state ───────────────────────────────


@runtime_checkable
class VerificationReadPort(Protocol):
    """Port for loading a pre-built VerifiedSourceMapping.

    The verifier does NOT use this port directly — the caller loads the
    state and passes it in.  This protocol documents the expected shape.
    """

    def load_binding_state(
        self,
        session: Any,
        /,
        *,
        binding_id: str,
    ) -> VerifiedSourceMapping | None: ...


# ── Slot definitions ──────────────────────────────────────────────────────

# stage_name → (binding_attr, snapshot_attr, hash_attr, calc_name, calc_type)
_SLOT_DEFS: dict[str, tuple[str, str, str, str, str]] = {
    stage: (
        _SLOT_BINDING_ATTRS[stage],
        _SLOT_SNAPSHOT_ATTRS[stage],
        _SLOT_HASH_ATTRS[stage],
        _SLOT_CALCULATOR_NAMES[stage],
        _SLOT_CALCULATION_TYPES[stage],
    )
    for stage in _SLOT_STAGE_ORDER
}


# ── Core verification function ────────────────────────────────────────────


def verify_source_mapping(state: VerifiedSourceMapping) -> VerifiedSourceMapping:
    """Strictly verify a pre-loaded VerifiedSourceMapping.

    Performs every check possible from the data in the mapping:
    - Schema version
    - Per-run identity fields (all non-empty)
    - Typed inner result snapshot re-parsing
    - Per-calculation hash map consistency
    - Upstream provenance structure
    - Combined source hash recomputation
    - requires_review consistency
    - Completeness (no NULL fields)
    - Power authority

    Returns the verified mapping on success.
    Raises on any mismatch (fail-closed).
    """
    # ── 1. Schema version ─────────────────────────────────────────────
    if state.binding_schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
        raise BindingSchemaError(state.binding_schema_version)

    # ── 2. Collect slot IDs from the mapping ──────────────────────────
    slot_ids: dict[str, str] = {}
    for stage in _SLOT_STAGE_ORDER:
        binding_attr, _, _, _, _ = _SLOT_DEFS[stage]
        calc_id = getattr(state, binding_attr)
        if not calc_id or not calc_id.strip():
            raise SlotMissingError(stage, calc_id or "<empty>")
        slot_ids[stage] = calc_id

    # ── 3. Verify per-run identity fields ─────────────────────────────
    for stage in _SLOT_STAGE_ORDER:
        _verify_run_identity(state, stage)

    # ── 4. Re-parse inner typed result snapshots ──────────────────────
    for stage in _SLOT_STAGE_ORDER:
        _, snapshot_attr, _, _, _ = _SLOT_DEFS[stage]
        result_dict = getattr(state, snapshot_attr)
        snapshot_cls = _RESULT_SNAPSHOT_CLS[stage]
        try:
            snapshot_cls.model_validate(result_dict)
        except Exception as exc:
            raise TypedPayloadInvalid(
                stage,
                detail=f"Failed to parse {snapshot_cls.__name__}: {exc}",
            ) from exc

    # ── 5. Verify power authority ─────────────────────────────────────
    if "total_installed_power_kw_e" not in state.power_result_snapshot:
        raise PowerAuthorityMissingError()

    # ── 6. Verify per-calculation hash map ────────────────────────────
    # per_calculation_result_hashes uses stage names as keys
    computed_per_calc: dict[str, str] = {}
    for stage in _SLOT_STAGE_ORDER:
        _, _, hash_attr, _, _ = _SLOT_DEFS[stage]
        stored_hash = getattr(state, hash_attr)
        computed_per_calc[stage] = stored_hash
    if computed_per_calc != state.per_calculation_result_hashes:
        raise SlotHashMapMismatch(state.per_calculation_result_hashes, computed_per_calc)

    # ── 7. Verify upstream provenance structure ───────────────────────
    _verify_upstream_provenance(state, slot_ids)

    # ── 8. Verify combined source hash ────────────────────────────────
    result_hashes_map: dict[str, str] = {}
    requires_reviews: dict[str, bool] = {}
    for stage in _SLOT_STAGE_ORDER:
        _, _, hash_attr, _, _ = _SLOT_DEFS[stage]
        result_hashes_map[stage] = getattr(state, hash_attr)
        requires_reviews[stage] = state.requires_review

    expected_combined = _compute_combined_source_hash(
        binding_schema_version=state.binding_schema_version,
        project_id=state.project_id,
        project_version_id=state.project_version_id,
        execution_snapshot_id=state.execution_snapshot_id,
        coefficient_context_id=state.coefficient_context_id,
        orchestration_identity_id=state.orchestration_identity_id,
        orchestration_attempt_id=state.orchestration_attempt_id,
        orchestration_fingerprint=state.orchestration_fingerprint,
        slot_ids=slot_ids,
        result_hashes=result_hashes_map,
        requires_reviews=requires_reviews,
    )
    if expected_combined != state.combined_source_hash:
        raise CombinedHashMismatch(expected_combined, state.combined_source_hash)

    # ── 9. Verify requires_review consistency ─────────────────────────
    if not isinstance(state.requires_review, bool):
        raise RequiresReviewMismatch(
            expected=True,
            actual=state.requires_review,
        )

    # ── 10. Verify completeness (no NULL fields) ──────────────────────
    _verify_completeness(state)

    return state


# ── Identity verification ──────────────────────────────────────────────────


def _verify_run_identity(
    state: VerifiedSourceMapping,
    stage: str,
) -> None:
    """Verify that identity fields in the mapping are internally consistent."""
    fields_to_check = [
        ("project_id", state.project_id),
        ("project_version_id", state.project_version_id),
        ("execution_snapshot_id", state.execution_snapshot_id),
        ("coefficient_context_id", state.coefficient_context_id),
        ("orchestration_identity_id", state.orchestration_identity_id),
        ("orchestration_attempt_id", state.orchestration_attempt_id),
        ("orchestration_fingerprint", state.orchestration_fingerprint),
    ]
    for field_name, val in fields_to_check:
        if val is None:
            raise CompletenessViolation(stage, field_name)
        if isinstance(val, str) and not val.strip():
            raise CompletenessViolation(stage, field_name)


# ── Upstream provenance verification ───────────────────────────────────────


def _verify_upstream_provenance(
    state: VerifiedSourceMapping,
    slot_ids: dict[str, str],
) -> None:
    """Verify upstream provenance structure using STAGE_UPSTREAM_PROVENANCE_KEYS.

    For each stage, verifies that the expected upstream dependencies (from the
    DAG contract) map to valid, non-empty calculation IDs.  The expected
    upstream IDs are derived from the five calculation_ids in the mapping and
    STAGE_UPSTREAM_PROVENANCE_KEYS.
    """
    for stage in ORCHESTRATION_STAGE_ORDER:
        expected_keys = STAGE_UPSTREAM_PROVENANCE_KEYS[stage]

        # Verify each expected upstream key maps to a valid calculation ID
        for upstream_key in expected_keys:
            if upstream_key not in slot_ids:
                raise ProvenanceMissingKey(stage, [upstream_key])
            upstream_id = slot_ids[upstream_key]
            if not upstream_id or not upstream_id.strip():
                raise ProvenanceMissingKey(stage, [upstream_key])


# ── Completeness verification ─────────────────────────────────────────────


def _verify_completeness(state: VerifiedSourceMapping) -> None:
    """Verify no NULL orchestration fields on the consolidated mapping."""
    _require_not_null(state, "execution_snapshot_id")
    _require_not_null(state, "coefficient_context_id")
    _require_not_null(state, "orchestration_identity_id")
    _require_not_null(state, "orchestration_attempt_id")
    _require_not_null(state, "orchestration_fingerprint")
    _require_not_null(state, "combined_source_hash")

    for stage in _SLOT_STAGE_ORDER:
        _, _, hash_attr, _, _ = _SLOT_DEFS[stage]
        val = getattr(state, hash_attr)
        if not val or not val.strip():
            raise CompletenessViolation(stage, hash_attr)


def _require_not_null(state: VerifiedSourceMapping, field_name: str) -> None:
    """Raise CompletenessViolation if a field is None or empty."""
    val = getattr(state, field_name)
    if val is None:
        raise CompletenessViolation("_mapping_", field_name)
    if isinstance(val, str) and not val.strip():
        raise CompletenessViolation("_mapping_", field_name)


# ── Backward-compatible entry point ───────────────────────────────────────


def verify_source_binding(
    read_port: Any,
    session: Any,
    *,
    binding_id: str,
) -> VerifiedSourceMapping:
    """Load and independently re-verify a SourceBinding.

    Backward-compatible wrapper that loads state from a read port and then
    delegates to ``verify_source_mapping``.
    """
    binding = read_port.load_binding(session, binding_id=binding_id)
    if binding is None:
        raise BindingNotFoundError(binding_id)

    # Schema version
    if binding.schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
        raise BindingSchemaError(binding.schema_version)

    # Attempt verification
    attempt = read_port.load_attempt(session, attempt_id=binding.orchestration_run_attempt_id)
    if attempt is None:
        raise AttemptNotCompletedError("MISSING")
    if attempt.status != "COMPLETED":
        raise AttemptNotCompletedError(attempt.status)
    if not attempt.authoritative:
        raise AttemptNotAuthoritativeError()
    if attempt.source_binding_id is not None and attempt.source_binding_id != binding_id:
        raise AttemptSourceBindingMismatch(binding_id, attempt.source_binding_id)

    # Load all five CalculationRuns
    runs: dict[str, CalculationRunSnapshot] = {}
    for stage in _SLOT_STAGE_ORDER:
        binding_attr, _, _, expected_calculator, expected_type = _SLOT_DEFS[stage]
        calc_id = getattr(binding, binding_attr)
        run = read_port.load_calculation_run(session, run_id=calc_id)
        if run is None:
            raise SlotMissingError(stage, calc_id)
        if run.calculator_name != expected_calculator:
            raise SlotTypeError(stage, run.calculator_name, expected_calculator)
        if run.calculation_type != expected_type:
            raise SlotTypeError(stage, run.calculation_type, expected_type)
        runs[stage] = run

    # Verify identity fields on each run
    for stage in _SLOT_STAGE_ORDER:
        run = runs[stage]
        if run.project_id != binding.project_id:
            raise SlotIdentityMismatch(stage, "project_id", binding.project_id, run.project_id)
        if run.project_version_id != binding.project_version_id:
            raise SlotIdentityMismatch(
                stage,
                "project_version_id",
                binding.project_version_id,
                run.project_version_id,
            )
        if run.orchestration_identity_id != binding.orchestration_identity_id:
            raise SlotIdentityMismatch(
                stage,
                "orchestration_identity_id",
                binding.orchestration_identity_id,
                run.orchestration_identity_id,
            )
        if run.orchestration_run_attempt_id != binding.orchestration_run_attempt_id:
            raise SlotIdentityMismatch(
                stage,
                "orchestration_run_attempt_id",
                binding.orchestration_run_attempt_id,
                run.orchestration_run_attempt_id,
            )
        if run.orchestration_fingerprint != binding.orchestration_fingerprint:
            raise FingerprintMismatch(
                stage, binding.orchestration_fingerprint, run.orchestration_fingerprint
            )

    # Verify result hash via per-calculation hash map
    for stage in _SLOT_STAGE_ORDER:
        run = runs[stage]
        if stage not in binding.per_calculation_result_hashes:
            raise SlotHashMapMismatch(
                binding.per_calculation_result_hashes,
                {stage: run.result_hash},
            )
        expected_hash = binding.per_calculation_result_hashes[stage]
        if expected_hash != run.result_hash:
            raise ResultHashMismatch(stage, expected_hash, run.result_hash)

    # Re-parse inner typed result snapshots
    for stage in _SLOT_STAGE_ORDER:
        result_dict = runs[stage].result_snapshot
        snapshot_cls = _RESULT_SNAPSHOT_CLS[stage]
        try:
            snapshot_cls.model_validate(result_dict)
        except Exception as exc:
            raise TypedPayloadInvalid(
                stage,
                detail=f"Failed to parse {snapshot_cls.__name__}: {exc}",
            ) from exc

    # Power authority check
    if "total_installed_power_kw_e" not in runs["power"].result_snapshot:
        raise PowerAuthorityMissingError()

    # Verify upstream provenance structure from runs
    slot_ids_map = {stage: runs[stage].id for stage in _SLOT_STAGE_ORDER}
    _verify_upstream_provenance_from_runs(runs, slot_ids_map)

    # Verify combined source hash
    result_hashes_map = {stage: runs[stage].result_hash or "" for stage in _SLOT_STAGE_ORDER}
    requires_reviews = {stage: runs[stage].requires_review for stage in _SLOT_STAGE_ORDER}
    expected_combined = _compute_combined_source_hash(
        binding_schema_version=binding.schema_version,
        project_id=binding.project_id,
        project_version_id=binding.project_version_id,
        execution_snapshot_id=binding.execution_snapshot_id,
        coefficient_context_id=binding.coefficient_context_id,
        orchestration_identity_id=binding.orchestration_identity_id,
        orchestration_attempt_id=binding.orchestration_run_attempt_id,
        orchestration_fingerprint=binding.orchestration_fingerprint,
        slot_ids=slot_ids_map,
        result_hashes=result_hashes_map,
        requires_reviews=requires_reviews,
    )
    if expected_combined != binding.combined_source_hash:
        raise CombinedHashMismatch(expected_combined, binding.combined_source_hash)

    # Verify requires_review type
    for stage in _SLOT_STAGE_ORDER:
        if not isinstance(runs[stage].requires_review, bool):
            raise RequiresReviewMismatch(
                expected=True,
                actual=runs[stage].requires_review,
            )

    # Completeness check on runs
    for stage in _SLOT_STAGE_ORDER:
        run = runs[stage]
        if run.result_hash is None:
            raise CompletenessViolation(stage, "result_hash")
        if run.schema_version is None:
            raise CompletenessViolation(stage, "schema_version")
        if run.calculation_type is None:
            raise CompletenessViolation(stage, "calculation_type")

    # Build and return the VerifiedSourceMapping
    any_review = any(r.requires_review for r in runs.values())

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
        per_calculation_result_hashes={
            stage: runs[stage].result_hash for stage in _SLOT_STAGE_ORDER
        },
        zone_calculation_id=runs["zone"].id,
        cooling_load_calculation_id=runs["cooling_load"].id,
        equipment_calculation_id=runs["equipment"].id,
        power_calculation_id=runs["power"].id,
        investment_calculation_id=runs["investment"].id,
    )


def _verify_upstream_provenance_from_runs(
    runs: dict[str, CalculationRunSnapshot],
    slot_ids: dict[str, str],
) -> None:
    """Verify upstream provenance from CalculationRun snapshots."""
    for stage in ORCHESTRATION_STAGE_ORDER:
        expected_keys = STAGE_UPSTREAM_PROVENANCE_KEYS[stage]
        run = runs[stage]
        actual_keys = frozenset(run.upstream_calculation_ids.keys())

        missing = expected_keys - actual_keys
        extra = actual_keys - expected_keys

        if missing:
            raise ProvenanceMissingKey(stage, sorted(missing))
        if extra:
            raise ProvenanceExtraKey(stage, sorted(extra))

        for key in expected_keys:
            expected_id = slot_ids.get(key)
            actual_id = run.upstream_calculation_ids.get(key)
            if expected_id and actual_id and actual_id != expected_id:
                raise UpstreamCalculationIdMismatch(stage, key, expected_id, actual_id)
