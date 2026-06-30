"""Transaction B — five-stage calculator execution within a single atomic session.

Executes the DAG  zone → cooling_load → equipment → power → investment
inside one session boundary.  Persists 5 CalculationRuns + 1 SourceBinding,
transitions the attempt to COMPLETED, and emits an audit outbox event.

Failure contract (approved design):
    On any calculator or persistence failure the method raises
    ``TransactionBFailure``.  The caller is responsible for rolling back
    the session — this module never calls ``session.rollback()``.

Architecture:
    This module is part of the application layer.  It MUST NOT import
    ``sqlalchemy``, ORM models, or ``Session``.  All database interaction
    goes through repository ABCs and the ``VerificationReadPort`` protocol.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar, Protocol, runtime_checkable

from cold_storage.modules.orchestration.application.ports import (
    AuditOutboxRepository,
    CalculationRunRepository,
    OrchestrationAttemptRepository,
    OrchestrationIdentityRepository,
    SourceBindingRepository,
)
from cold_storage.modules.orchestration.application.source_snapshots import (
    CoolingLoadSourceSnapshotV1,
    EquipmentSourceSnapshotV1,
    InvestmentSourceSnapshotV1,
    PowerSourceSnapshotV1,
    SourceSnapshotContentV1,
    ZoneSourceSnapshotV1,
)
from cold_storage.modules.orchestration.domain.contracts import (
    AttemptStatus,
    OrchestrationResult,
    SourceBindingCandidate,
    StageExecutionDiagnostic,
    StagePersistedResult,
    validate_provenance_keys,
)
from cold_storage.modules.orchestration.domain.dag import (
    ORCHESTRATION_STAGE_ORDER,
    STAGE_UPSTREAM_PROVENANCE_KEYS,
)
from cold_storage.modules.orchestration.domain.errors import (
    OrchestrationDomainError,
    SourceBindingHashMismatchError,
    SourceBindingIdentityMismatchError,
    SourceBindingSlotTypeError,
    SourceSnapshotSchemaError,
    TransactionInvariantError,
    UnsupportedSchemaError,
)
from cold_storage.modules.orchestration.domain.fingerprint import result_hash

# ── Canonical constants ─────────────────────────────────────────────────────

SOURCE_BINDING_SCHEMA_VERSION: str = "1.0.0"
SOURCE_SNAPSHOT_SCHEMA_VERSION: str = "1.0.0"

# ── Private stage metadata ──────────────────────────────────────────────────

# stage_name → (calculator_name, calculator_version, calculation_type)
_EXPECTED_CALCULATOR_IDENTITY: Mapping[str, tuple[str, str, str]] = {
    "zone": ("cold_room_zone_plan", "1.0.0", "zone"),
    "cooling_load": ("cooling_load", "1.0.0", "cooling_load"),
    "equipment": ("equipment", "1.0.0", "equipment"),
    "power": ("installed_power", "1.0.0", "power"),
    "investment": ("investment_estimate", "1.0.0", "investment"),
}

# stage_name → Pydantic snapshot subclass for typed content
_STAGE_SNAPSHOT_CLS: Mapping[str, type[SourceSnapshotContentV1]] = {
    "zone": ZoneSourceSnapshotV1,
    "cooling_load": CoolingLoadSourceSnapshotV1,
    "equipment": EquipmentSourceSnapshotV1,
    "power": PowerSourceSnapshotV1,
    "investment": InvestmentSourceSnapshotV1,
}

# stage_name → candidate_field_name  (for SourceBindingCandidate attribute lookup)
_STAGE_CANDIDATE_FIELD: Mapping[str, str] = {
    "zone": "zone_calculation_id",
    "cooling_load": "cooling_load_calculation_id",
    "equipment": "equipment_calculation_id",
    "power": "power_calculation_id",
    "investment": "investment_calculation_id",
}


# ── Calculator port protocol ────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class StageExecutionResult:
    """Immutable result from a calculator stage execution."""

    calculator_name: str
    calculator_version: str
    calculation_type: str
    result_snapshot: dict[str, Any]
    formulas: list[dict[str, Any]]
    coefficients: list[dict[str, Any]]
    assumptions: list[str]
    warnings: list[dict[str, Any]]
    source_references: list[dict[str, Any]]
    requires_review: bool


@runtime_checkable
class CalculatorPort(Protocol):
    """Port that executes individual calculator stages.

    Implementations live in the infrastructure layer.  The port receives
    the full execution snapshot, coefficient context, and upstream
    ``StagePersistedResult`` objects for dependency injection.
    """

    def execute_stage(
        self,
        *,
        stage_name: str,
        execution_snapshot: dict[str, Any],
        coefficient_context: dict[str, Any],
        upstream_results: dict[str, StagePersistedResult],
    ) -> StageExecutionResult: ...


# ── Verification read models ────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CalculationRunSnapshot:
    """Immutable read model for a CalculationRun.

    Carries all fields needed by the ``SourceBindingVerifier`` to re-parse
    the typed source snapshot and re-compute the result hash.
    """

    id: str
    calculator_name: str
    calculator_version: str
    calculation_type: str
    result_snapshot: dict[str, Any]
    result_hash: str | None
    orchestration_identity_id: str | None
    orchestration_run_attempt_id: str | None
    execution_snapshot_id: str | None
    coefficient_context_id: str | None
    orchestration_fingerprint: str | None
    requires_review: bool
    schema_version: str | None
    # Payload fields for typed snapshot re-parsing
    project_id: str
    project_version_id: str
    formulas: list[dict[str, Any]]
    coefficients: list[dict[str, Any]]
    assumptions: list[str]
    warnings: list[dict[str, Any]]
    source_references: list[dict[str, Any]]
    upstream_calculation_ids: dict[str, str]


@dataclass(frozen=True, slots=True)
class VerificationState:
    """Immutable read model for SourceBinding verification.

    Loaded by the ``VerificationReadPort`` from the current database state.
    Contains request, identity, attempt, and five CalculationRun snapshots.
    """

    request_status: str
    resolved_identity_id: str | None
    resolved_attempt_id: str | None
    identity_fingerprint: str
    identity_execution_snapshot_id: str
    identity_coefficient_context_id: str
    identity_authoritative_attempt_id: str | None
    attempt_identity_id: str
    attempt_status: str
    attempt_source_binding_id: str | None
    calculation_runs: dict[str, CalculationRunSnapshot]  # stage_name → snapshot


class VerificationReadPort(Protocol):
    """Port for loading verification state from the database.

    Implementations live in the infrastructure layer.  The ``session``
    parameter is opaque (not typed as ``Session``) to keep the application
    layer free of SQLAlchemy imports.
    """

    def load_verification_state(
        self,
        session: Any,
        /,
        *,
        request_id: str,
        identity_id: str,
        attempt_id: str,
    ) -> VerificationState: ...


# ── Failure signal ──────────────────────────────────────────────────────────


class TransactionBFailure(Exception):
    """Structured failure signal raised by :meth:`TransactionBExecutor.execute`.

    Carries a machine-readable ``code``, a ``field`` locator, and structured
    ``details``.  The caller MUST roll back the session after catching this.
    """

    __slots__ = ("code", "field", "details")

    def __init__(
        self,
        code: str,
        message: str,
        *,
        field: str,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.field = field
        self.details: dict[str, object] = details if details is not None else {}


# ── Combined source hash helper ─────────────────────────────────────────────


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
    """Compute the combined source hash that binds all verification-critical fields.

    The hash covers: binding schema, project/version identity, execution
    snapshot, coefficient context, orchestration identity/attempt/fingerprint,
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


# ── Source Binding Verifier ─────────────────────────────────────────────────


class SourceBindingVerifier:
    """Validates a SourceBindingCandidate against authoritative database state.

    Self-loads all verification data from the database via a
    ``VerificationReadPort``.  Rejects candidates with:

    - Authority / identity violations
    - Slot completeness / uniqueness / type errors
    - Project / version / snapshot / context / identity / attempt mismatches
    - Typed snapshot re-parse failures
    - Result hash recomputation mismatches
    - Upstream provenance errors
    - Combined source hash tampering
    - requires_review inconsistencies
    - Extra / missing stages
    """

    # stage_name → (candidate_field, expected_calculator_name, expected_calculation_type)
    _SLOT_DEFS: ClassVar[dict[str, tuple[str, str, str]]] = {
        "zone": ("zone_calculation_id", "cold_room_zone_plan", "zone"),
        "cooling_load": ("cooling_load_calculation_id", "cooling_load", "cooling_load"),
        "equipment": ("equipment_calculation_id", "equipment", "equipment"),
        "power": ("power_calculation_id", "installed_power", "power"),
        "investment": ("investment_calculation_id", "investment_estimate", "investment"),
    }

    _SUPPORTED_BINDING_SCHEMA_VERSIONS: ClassVar[frozenset[str]] = frozenset(
        {SOURCE_BINDING_SCHEMA_VERSION}
    )
    _SUPPORTED_SOURCE_SNAPSHOT_SCHEMA_VERSIONS: ClassVar[frozenset[str]] = frozenset(
        {SOURCE_SNAPSHOT_SCHEMA_VERSION}
    )

    def __init__(self, *, read_port: VerificationReadPort) -> None:
        self._read_port = read_port

    # ── Public entry point ──────────────────────────────────────────────

    def verify(
        self,
        session: Any,
        /,
        *,
        request_id: str,
        identity_id: str,
        attempt_id: str,
        candidate: SourceBindingCandidate,
        project_id: str,
        project_version_id: str,
        execution_snapshot_id: str,
        coefficient_context_id: str,
        orchestration_fingerprint: str,
    ) -> None:
        """Verify binding integrity against authoritative database state.

        Raises ``OrchestrationDomainError`` on any verification failure.
        """
        # ── Load authoritative state from DB ───────────────────────────
        state = self._read_port.load_verification_state(
            session,
            request_id=request_id,
            identity_id=identity_id,
            attempt_id=attempt_id,
        )

        # ── 1. Authority checks (P0-5) ─────────────────────────────────
        self._verify_authority(
            state=state,
            identity_id=identity_id,
            attempt_id=attempt_id,
            orchestration_fingerprint=orchestration_fingerprint,
        )

        # ── 2. Candidate fingerprint matches identity (category 12) ────
        if candidate.fingerprint != orchestration_fingerprint:
            raise SourceBindingIdentityMismatchError(
                "fingerprint", orchestration_fingerprint, candidate.fingerprint
            )

        # ── 3. Candidate identity / attempt match ──────────────────────
        if candidate.identity_id != identity_id:
            raise SourceBindingIdentityMismatchError(
                "identity_id", identity_id, candidate.identity_id
            )
        if candidate.attempt_id != attempt_id:
            raise SourceBindingIdentityMismatchError("attempt_id", attempt_id, candidate.attempt_id)

        # ── 4. No extra / missing stages (category 10) ─────────────────
        expected_stages = frozenset(ORCHESTRATION_STAGE_ORDER)
        actual_stages = frozenset(state.calculation_runs.keys())
        if actual_stages != expected_stages:
            missing = expected_stages - actual_stages
            extra = actual_stages - expected_stages
            parts: list[str] = []
            if missing:
                parts.append(f"missing: {sorted(missing)}")
            if extra:
                parts.append(f"extra: {sorted(extra)}")
            raise TransactionInvariantError(f"Stage set mismatch: {'; '.join(parts)}")

        # ── 5. Slot completeness, types, identity (categories 1, 2, 3) ─
        self._verify_slots(
            candidate=candidate,
            state=state,
            project_id=project_id,
            project_version_id=project_version_id,
            execution_snapshot_id=execution_snapshot_id,
            coefficient_context_id=coefficient_context_id,
            orchestration_identity_id=identity_id,
            orchestration_attempt_id=attempt_id,
        )

        # ── 6. Schema, re-parse, result hash (categories 4, 5) ─────────
        self._verify_schema_and_hashes(
            candidate=candidate,
            state=state,
            orchestration_fingerprint=orchestration_fingerprint,
        )

        # ── 7. Upstream provenance (category 6) ────────────────────────
        self._verify_upstream_provenance(state=state)

        # ── 8. Hash map key set + combined hash (categories 7, 8) ──────
        self._verify_combined_hash(
            candidate=candidate,
            state=state,
            project_id=project_id,
            project_version_id=project_version_id,
            execution_snapshot_id=execution_snapshot_id,
            coefficient_context_id=coefficient_context_id,
            orchestration_identity_id=identity_id,
            orchestration_attempt_id=attempt_id,
            orchestration_fingerprint=orchestration_fingerprint,
        )

        # ── 9. requires_review consistency (category 9) ────────────────
        self._verify_requires_review(state=state)

        # ── 10. Completeness (non-null orchestration fields) ───────────
        self._verify_completeness(state=state)

    # ── Authority checks ────────────────────────────────────────────────

    def _verify_authority(
        self,
        *,
        state: VerificationState,
        identity_id: str,
        attempt_id: str,
        orchestration_fingerprint: str,
    ) -> None:
        """Verify request, identity, and attempt authority (P0-5)."""
        from cold_storage.modules.orchestration.domain.contracts import RequestStatus

        if state.request_status != str(RequestStatus.ACCEPTED):
            raise TransactionInvariantError(
                f"Request status is {state.request_status!r}, expected ACCEPTED"
            )
        if state.resolved_identity_id != identity_id:
            raise SourceBindingIdentityMismatchError(
                "resolved_identity_id",
                identity_id,
                state.resolved_identity_id or "",
            )
        if state.resolved_attempt_id != attempt_id:
            raise SourceBindingIdentityMismatchError(
                "resolved_attempt_id",
                attempt_id,
                state.resolved_attempt_id or "",
            )
        if state.identity_fingerprint != orchestration_fingerprint:
            raise SourceBindingIdentityMismatchError(
                "identity_fingerprint",
                orchestration_fingerprint,
                state.identity_fingerprint,
            )
        if state.attempt_status != str(AttemptStatus.RUNNING):
            raise TransactionInvariantError(
                f"Attempt status is {state.attempt_status!r}, expected RUNNING"
            )
        if state.attempt_identity_id != identity_id:
            raise SourceBindingIdentityMismatchError(
                "attempt_identity_id",
                identity_id,
                state.attempt_identity_id,
            )

    # ── Slot validation ─────────────────────────────────────────────────

    def _verify_slots(
        self,
        *,
        candidate: SourceBindingCandidate,
        state: VerificationState,
        project_id: str,
        project_version_id: str,
        execution_snapshot_id: str,
        coefficient_context_id: str,
        orchestration_identity_id: str,
        orchestration_attempt_id: str,
    ) -> None:
        """Verify slot completeness, uniqueness, types, and per-run identity."""
        # ── Collect slot IDs from candidate ─────────────────────────────
        slot_ids: dict[str, str] = {}
        for stage_name, (candidate_field, _calc_name, _calc_type) in self._SLOT_DEFS.items():
            calc_id: str = getattr(candidate, candidate_field)
            if not calc_id or not calc_id.strip():
                raise TransactionInvariantError(f"Slot {candidate_field!r} is empty")
            slot_ids[stage_name] = calc_id

        # ── Duplicate CalculationRun IDs across slots ───────────────────
        seen: set[str] = set()
        for stage_name, calc_id in slot_ids.items():
            if calc_id in seen:
                raise TransactionInvariantError(
                    f"Duplicate calculation_run_id {calc_id!r} (first seen at stage {stage_name!r})"
                )
            seen.add(calc_id)

        # ── Per-slot CalculationRun validation ──────────────────────────
        for stage_name, (
            candidate_field,
            expected_calculator,
            expected_type,
        ) in self._SLOT_DEFS.items():
            run = state.calculation_runs[stage_name]
            calc_id = slot_ids[stage_name]

            # Candidate's ID must match the record's ID
            if run.id != calc_id:
                raise TransactionInvariantError(
                    f"Slot {candidate_field!r}: candidate ID {calc_id!r} "
                    f"does not match record ID {run.id!r}"
                )

            # Wrong calculation type
            if run.calculation_type != expected_type:
                raise SourceBindingSlotTypeError(
                    stage_name, expected_type, run.calculation_type or ""
                )

            # Wrong calculator ID
            if run.calculator_name != expected_calculator:
                raise SourceBindingSlotTypeError(
                    stage_name, expected_calculator, run.calculator_name
                )

            # Per-run identity / provenance
            self._verify_run_identity(
                run=run,
                stage_name=stage_name,
                project_id=project_id,
                project_version_id=project_version_id,
                execution_snapshot_id=execution_snapshot_id,
                coefficient_context_id=coefficient_context_id,
                orchestration_identity_id=orchestration_identity_id,
                orchestration_attempt_id=orchestration_attempt_id,
            )

    # ── Per-run identity / provenance ───────────────────────────────────

    def _verify_run_identity(
        self,
        *,
        run: CalculationRunSnapshot,
        stage_name: str,
        project_id: str,
        project_version_id: str,
        execution_snapshot_id: str,
        coefficient_context_id: str,
        orchestration_identity_id: str,
        orchestration_attempt_id: str,
    ) -> None:
        """Verify a single CalculationRun's identity fields."""
        _ = stage_name

        if run.project_id != project_id:
            raise SourceBindingIdentityMismatchError("project_id", project_id, run.project_id)
        if run.project_version_id != project_version_id:
            raise SourceBindingIdentityMismatchError(
                "project_version_id", project_version_id, run.project_version_id
            )
        if run.execution_snapshot_id != execution_snapshot_id:
            raise SourceBindingIdentityMismatchError(
                "execution_snapshot_id",
                execution_snapshot_id,
                run.execution_snapshot_id or "",
            )
        if run.coefficient_context_id != coefficient_context_id:
            raise SourceBindingIdentityMismatchError(
                "coefficient_context_id",
                coefficient_context_id,
                run.coefficient_context_id or "",
            )
        if run.orchestration_identity_id != orchestration_identity_id:
            raise SourceBindingIdentityMismatchError(
                "orchestration_identity_id",
                orchestration_identity_id,
                run.orchestration_identity_id or "",
            )
        if run.orchestration_run_attempt_id != orchestration_attempt_id:
            raise SourceBindingIdentityMismatchError(
                "orchestration_run_attempt_id",
                orchestration_attempt_id,
                run.orchestration_run_attempt_id or "",
            )

    # ── Schema + re-parse + result hash ─────────────────────────────────

    def _verify_schema_and_hashes(
        self,
        *,
        candidate: SourceBindingCandidate,
        state: VerificationState,
        orchestration_fingerprint: str,
    ) -> None:
        """Verify binding schema, re-parse typed snapshots, re-compute result hashes."""
        # ── Binding schema version ──────────────────────────────────────
        if candidate.schema_version not in self._SUPPORTED_BINDING_SCHEMA_VERSIONS:
            raise UnsupportedSchemaError("binding", candidate.schema_version)

        # ── Per-stage: schema, re-parse, result hash ────────────────────
        for stage_name in ORCHESTRATION_STAGE_ORDER:
            run = state.calculation_runs[stage_name]

            # Schema version check
            sv = run.schema_version
            if sv is None or sv not in self._SUPPORTED_SOURCE_SNAPSHOT_SCHEMA_VERSIONS:
                raise SourceSnapshotSchemaError(
                    sv or "<null>",
                    f"stage {stage_name!r}",
                )

            # Re-parse typed snapshot from persisted data
            snapshot_cls = _STAGE_SNAPSHOT_CLS[stage_name]
            fingerprint = run.orchestration_fingerprint or orchestration_fingerprint
            try:
                snapshot = snapshot_cls(
                    project_id=run.project_id,
                    project_version_id=run.project_version_id,
                    execution_snapshot_id=run.execution_snapshot_id or "",
                    coefficient_context_id=run.coefficient_context_id or "",
                    orchestration_identity_id=run.orchestration_identity_id or "",
                    orchestration_attempt_id=run.orchestration_run_attempt_id or "",
                    orchestration_fingerprint=fingerprint,
                    source_snapshot_schema_version="1.0.0",
                    calculation_type=run.calculation_type or "",
                    calculator_id=run.calculator_name,
                    calculator_version=run.calculator_version,
                    requires_review=run.requires_review,
                    result_snapshot=run.result_snapshot,
                    formulas=run.formulas,  # type: ignore[arg-type]
                    coefficients=run.coefficients,  # type: ignore[arg-type]
                    assumptions=run.assumptions,
                    warnings=run.warnings,  # type: ignore[arg-type]
                    source_references=run.source_references,  # type: ignore[arg-type]
                    upstream_calculation_ids=dict(run.upstream_calculation_ids),
                )
            except Exception as exc:
                raise SourceSnapshotSchemaError(
                    sv,
                    f"Failed to re-parse typed snapshot for stage {stage_name!r}: {exc}",
                ) from exc

            # Re-compute result hash from persisted typed snapshot
            recomputed_hash = snapshot.result_hash()
            if recomputed_hash != run.result_hash:
                raise SourceBindingHashMismatchError(
                    f"result_hash[{stage_name!r}]",
                    run.result_hash or "",
                    recomputed_hash,
                )

    # ── Upstream provenance ─────────────────────────────────────────────

    def _verify_upstream_provenance(
        self,
        *,
        state: VerificationState,
    ) -> None:
        """Verify exact upstream dependency provenance for each stage."""
        for stage_name, upstream_keys in STAGE_UPSTREAM_PROVENANCE_KEYS.items():
            if not upstream_keys:
                continue

            run = state.calculation_runs[stage_name]
            upstream_ids = run.upstream_calculation_ids

            for upstream_key in upstream_keys:
                if upstream_key not in state.calculation_runs:
                    raise TransactionInvariantError(
                        f"Missing upstream stage {upstream_key!r} for stage {stage_name!r}"
                    )
                expected_id = state.calculation_runs[upstream_key].id
                actual_id = upstream_ids.get(upstream_key)
                if actual_id != expected_id:
                    raise TransactionInvariantError(
                        f"Upstream dependency mismatch for stage {stage_name!r}: "
                        f"expected {upstream_key}={expected_id!r}, got {actual_id!r}"
                    )

    # ── Combined hash + hash map key set ────────────────────────────────

    def _verify_combined_hash(
        self,
        *,
        candidate: SourceBindingCandidate,
        state: VerificationState,
        project_id: str,
        project_version_id: str,
        execution_snapshot_id: str,
        coefficient_context_id: str,
        orchestration_identity_id: str,
        orchestration_attempt_id: str,
        orchestration_fingerprint: str,
    ) -> None:
        """Verify per-calculation result hashes, key set, and combined hash."""
        expected_calculators = frozenset(
            calc_name for _, (_, calc_name, _) in self._SLOT_DEFS.items()
        )

        # ── Hash map key set tampering (extra or missing keys) ──────────
        actual_keys = frozenset(candidate.per_calculation_result_hashes.keys())
        if actual_keys != expected_calculators:
            missing = expected_calculators - actual_keys
            extra = actual_keys - expected_calculators
            parts: list[str] = []
            if missing:
                parts.append(f"missing: {sorted(missing)}")
            if extra:
                parts.append(f"extra: {sorted(extra)}")
            raise SourceBindingHashMismatchError(
                "per_calculation_result_hashes",
                str(sorted(expected_calculators)),
                "; ".join(parts),
            )

        # ── Per-calculation result hash tampering ───────────────────────
        for stage_name, (_, expected_calculator, _) in self._SLOT_DEFS.items():
            run = state.calculation_runs[stage_name]
            expected_hash = run.result_hash
            actual_hash = candidate.per_calculation_result_hashes.get(expected_calculator)
            if actual_hash != expected_hash:
                raise SourceBindingHashMismatchError(
                    f"per_calculation_result_hashes[{expected_calculator!r}]",
                    expected_hash or "",
                    actual_hash or "",
                )

        # ── Re-compute combined source hash ─────────────────────────────
        slot_ids: dict[str, str] = {}
        result_hashes_map: dict[str, str] = {}
        requires_reviews: dict[str, bool] = {}
        for stage_name in ORCHESTRATION_STAGE_ORDER:
            run = state.calculation_runs[stage_name]
            slot_ids[stage_name] = run.id
            result_hashes_map[stage_name] = run.result_hash or ""
            requires_reviews[stage_name] = run.requires_review

        expected_combined = _compute_combined_source_hash(
            binding_schema_version=candidate.schema_version,
            project_id=project_id,
            project_version_id=project_version_id,
            execution_snapshot_id=execution_snapshot_id,
            coefficient_context_id=coefficient_context_id,
            orchestration_identity_id=orchestration_identity_id,
            orchestration_attempt_id=orchestration_attempt_id,
            orchestration_fingerprint=orchestration_fingerprint,
            slot_ids=slot_ids,
            result_hashes=result_hashes_map,
            requires_reviews=requires_reviews,
        )
        if candidate.combined_source_hash != expected_combined:
            raise SourceBindingHashMismatchError(
                "combined_source_hash",
                expected_combined,
                candidate.combined_source_hash,
            )

    # ── requires_review consistency ─────────────────────────────────────

    def _verify_requires_review(
        self,
        *,
        state: VerificationState,
    ) -> None:
        """Verify requires_review is a valid bool on every CalculationRun."""
        for stage_name, run in state.calculation_runs.items():
            if not isinstance(run.requires_review, bool):
                raise TransactionInvariantError(
                    f"CalculationRun for stage {stage_name!r} has "
                    f"invalid requires_review: {run.requires_review!r}"
                )

    # ── Completeness validation ─────────────────────────────────────────

    def _verify_completeness(
        self,
        *,
        state: VerificationState,
    ) -> None:
        """Reject partial or legacy CalculationRuns (orchestration fields NULL)."""
        for stage_name, run in state.calculation_runs.items():
            self._require_not_null(
                stage_name, run.orchestration_identity_id, "orchestration_identity_id"
            )
            self._require_not_null(
                stage_name,
                run.orchestration_run_attempt_id,
                "orchestration_run_attempt_id",
            )
            self._require_not_null(stage_name, run.execution_snapshot_id, "execution_snapshot_id")
            self._require_not_null(stage_name, run.coefficient_context_id, "coefficient_context_id")
            self._require_not_null(stage_name, run.result_hash, "result_hash")
            self._require_not_null(stage_name, run.schema_version, "schema_version")
            self._require_not_null(stage_name, run.calculation_type, "calculation_type")

    @staticmethod
    def _require_not_null(
        stage_name: str,
        value: str | object | None,
        field_name: str,
    ) -> None:
        """Raise TransactionInvariantError if *value* is None."""
        if value is None:
            raise TransactionInvariantError(
                f"CalculationRun for stage {stage_name!r} has NULL "
                f"{field_name} (partial/legacy run)"
            )


# ── Transaction B executor ──────────────────────────────────────────────────


class TransactionBExecutor:
    """Executes the five-stage DAG within a single atomic transaction.

    On success: persists 5 CalculationRuns + 1 SourceBinding,
    transitions attempt to COMPLETED, returns OrchestrationResult.

    On failure: raises TransactionBFailure (caller must rollback).
    """

    def __init__(
        self,
        *,
        calculation_run_repo: CalculationRunRepository,
        source_binding_repo: SourceBindingRepository,
        attempt_repo: OrchestrationAttemptRepository,
        identity_repo: OrchestrationIdentityRepository,
        outbox_repo: AuditOutboxRepository,
        calculator_port: CalculatorPort,
        verifier: SourceBindingVerifier,
    ) -> None:
        self._calc_run_repo = calculation_run_repo
        self._source_binding_repo = source_binding_repo
        self._attempt_repo = attempt_repo
        self._identity_repo = identity_repo
        self._outbox_repo = outbox_repo
        self._calculator_port = calculator_port
        self._verifier = verifier

    # ── Public entry point ──────────────────────────────────────────────

    def execute(
        self,
        session: Any,
        /,
        *,
        request_id: str,
        project_id: str,
        project_version_id: str,
        execution_snapshot_id: str,
        coefficient_context_id: str,
        orchestration_identity_id: str,
        orchestration_attempt_id: str,
        orchestration_fingerprint: str,
        execution_snapshot: dict[str, Any],
        coefficient_context: dict[str, Any],
    ) -> OrchestrationResult:
        """Execute Transaction B atomically.

        On success: persists 5 CalculationRuns + 1 SourceBinding,
        transitions attempt to COMPLETED, returns OrchestrationResult.

        On failure: raises TransactionBFailure (caller must rollback).
        """
        started_at = datetime.now(UTC)

        # 1 — Load authoritative version vector from identity repo (P0-6)
        calculator_version_vector = self._identity_repo.get_calculator_version_vector(
            session,
            identity_id=orchestration_identity_id,
        )
        self._validate_version_vector(calculator_version_vector)

        persisted_stages: list[StagePersistedResult] = []
        upstream_results: dict[str, StagePersistedResult] = {}
        calc_ids: dict[str, str] = {}
        result_hashes: dict[str, str] = {}
        requires_reviews: dict[str, bool] = {}

        # Pre-compute input hash components
        exec_snapshot_hash = result_hash(execution_snapshot)

        # 2 — Execute each stage in DAG order (P0-1)
        for stage_name in ORCHESTRATION_STAGE_ORDER:
            # Build upstream calculation IDs for this stage
            upstream_calc_ids = self._build_upstream_calculation_ids(stage_name, calc_ids)

            # Validate provenance keys (P0-3)
            try:
                validate_provenance_keys(stage_name, upstream_calc_ids)
            except ValueError as exc:
                raise TransactionBFailure(
                    "TXB_PROVENANCE_INVALID",
                    f"Provenance key validation failed for stage {stage_name!r}: {exc}",
                    field="upstream_calculation_ids",
                    details={"stage_name": stage_name, "error": str(exc)},
                ) from exc

            # Execute stage via calculator port
            try:
                exec_result = self._calculator_port.execute_stage(
                    stage_name=stage_name,
                    execution_snapshot=execution_snapshot,
                    coefficient_context=coefficient_context,
                    upstream_results=dict(upstream_results),
                )
            except OrchestrationDomainError:
                raise
            except Exception as exc:
                raise TransactionBFailure(
                    "TXB_STAGE_EXECUTION_FAILED",
                    f"Calculator execution failed for stage {stage_name!r}: {exc}",
                    field="calculator_port",
                    details={"stage_name": stage_name, "error": str(exc)},
                ) from exc

            # Validate calculator identity (P0-8, P0-6)
            self._validate_calculator_identity(stage_name, exec_result, calculator_version_vector)

            # Build typed snapshot (P0-1 — typed snapshots as ONLY production path)
            snapshot = self._build_typed_snapshot(
                stage_name=stage_name,
                exec_result=exec_result,
                project_id=project_id,
                project_version_id=project_version_id,
                execution_snapshot_id=execution_snapshot_id,
                coefficient_context_id=coefficient_context_id,
                orchestration_identity_id=orchestration_identity_id,
                orchestration_attempt_id=orchestration_attempt_id,
                orchestration_fingerprint=orchestration_fingerprint,
                upstream_calculation_ids=upstream_calc_ids,
            )

            # Compute result hash from typed content (P0-6)
            typed_result_hash = snapshot.result_hash()

            # Compute input hash from stage-specific inputs
            stage_input: dict[str, object] = {
                "execution_snapshot_hash": exec_snapshot_hash,
                "coefficient_context_hash": result_hash(coefficient_context),
                "upstream_calculation_ids": upstream_calc_ids,
            }
            input_hash = result_hash(stage_input)

            # Persist CalculationRun with REAL traceability data (P0-1)
            calc_run_id = self._calc_run_repo.add(
                session,
                project_id=project_id,
                project_version_id=project_version_id,
                calculator_name=exec_result.calculator_name,
                calculator_version=exec_result.calculator_version,
                calculation_type=exec_result.calculation_type,
                input_snapshot=stage_input,
                result_snapshot=dict(exec_result.result_snapshot),
                requires_review=exec_result.requires_review,
                orchestration_identity_id=orchestration_identity_id,
                orchestration_run_attempt_id=orchestration_attempt_id,
                execution_snapshot_id=execution_snapshot_id,
                coefficient_context_id=coefficient_context_id,
                input_hash=input_hash,
                result_hash=typed_result_hash,
                provenance={
                    "execution_snapshot_id": execution_snapshot_id,
                    "coefficient_context_id": coefficient_context_id,
                    "orchestration_identity_id": orchestration_identity_id,
                    "orchestration_run_attempt_id": orchestration_attempt_id,
                    "orchestration_fingerprint": orchestration_fingerprint,
                    "upstream_calculation_ids": dict(upstream_calc_ids),
                },
                schema_version=SOURCE_SNAPSHOT_SCHEMA_VERSION,
                orchestration_fingerprint=orchestration_fingerprint,
                formulas=exec_result.formulas,
                coefficients=exec_result.coefficients,
                assumptions=exec_result.assumptions,
                warnings=exec_result.warnings,
                source_references=exec_result.source_references,
            )

            persisted = StagePersistedResult(
                calculator_name=exec_result.calculator_name,
                calculation_run_id=calc_run_id,
                input_hash=input_hash,
                result_hash=typed_result_hash,
                calculator_version=exec_result.calculator_version,
                snapshot_schema_version=SOURCE_SNAPSHOT_SCHEMA_VERSION,
            )
            persisted_stages.append(persisted)
            upstream_results[stage_name] = persisted
            calc_ids[stage_name] = calc_run_id
            result_hashes[stage_name] = typed_result_hash
            requires_reviews[stage_name] = exec_result.requires_review

        # 3 — Build SourceBindingCandidate (P0-4, P0-6)
        slot_ids_map = {
            stage.calculator_name: stage.calculation_run_id for stage in persisted_stages
        }
        per_calc_result_hashes = {
            stage.calculator_name: stage.result_hash for stage in persisted_stages
        }
        combined_hash = _compute_combined_source_hash(
            binding_schema_version=SOURCE_BINDING_SCHEMA_VERSION,
            project_id=project_id,
            project_version_id=project_version_id,
            execution_snapshot_id=execution_snapshot_id,
            coefficient_context_id=coefficient_context_id,
            orchestration_identity_id=orchestration_identity_id,
            orchestration_attempt_id=orchestration_attempt_id,
            orchestration_fingerprint=orchestration_fingerprint,
            slot_ids=calc_ids,
            result_hashes=result_hashes,
            requires_reviews=requires_reviews,
        )

        candidate = SourceBindingCandidate(
            identity_id=orchestration_identity_id,
            attempt_id=orchestration_attempt_id,
            fingerprint=orchestration_fingerprint,
            zone_calculation_id=slot_ids_map["cold_room_zone_plan"],
            cooling_load_calculation_id=slot_ids_map["cooling_load"],
            equipment_calculation_id=slot_ids_map["equipment"],
            power_calculation_id=slot_ids_map["installed_power"],
            investment_calculation_id=slot_ids_map["investment_estimate"],
            per_calculation_result_hashes=per_calc_result_hashes,
            combined_source_hash=combined_hash,
            schema_version=SOURCE_BINDING_SCHEMA_VERSION,
        )

        # 4 — Verify via verifier BEFORE persisting (P0-4)
        try:
            self._verifier.verify(
                session,
                request_id=request_id,
                identity_id=orchestration_identity_id,
                attempt_id=orchestration_attempt_id,
                candidate=candidate,
                project_id=project_id,
                project_version_id=project_version_id,
                execution_snapshot_id=execution_snapshot_id,
                coefficient_context_id=coefficient_context_id,
                orchestration_fingerprint=orchestration_fingerprint,
            )
        except OrchestrationDomainError:
            raise
        except Exception as exc:
            raise TransactionBFailure(
                "TXB_VERIFICATION_FAILED",
                f"SourceBinding verification failed: {exc}",
                field="source_binding",
                details={"error": str(exc)},
            ) from exc

        # 5 — Persist SourceBinding
        source_binding_id = self._source_binding_repo.add(
            session,
            project_id=project_id,
            project_version_id=project_version_id,
            execution_snapshot_id=execution_snapshot_id,
            coefficient_context_id=coefficient_context_id,
            orchestration_identity_id=orchestration_identity_id,
            orchestration_run_attempt_id=orchestration_attempt_id,
            orchestration_fingerprint=orchestration_fingerprint,
            zone_calculation_id=candidate.zone_calculation_id,
            cooling_load_calculation_id=candidate.cooling_load_calculation_id,
            equipment_calculation_id=candidate.equipment_calculation_id,
            power_calculation_id=candidate.power_calculation_id,
            investment_calculation_id=candidate.investment_calculation_id,
            per_calculation_result_hashes=dict(candidate.per_calculation_result_hashes),
            combined_source_hash=candidate.combined_source_hash,
            schema_version=candidate.schema_version,
        )

        # 6 — CAS attempt → COMPLETED (P0-5)
        completed_at = datetime.now(UTC)
        cas_ok = self._attempt_repo.complete_attempt_cas(
            session,
            attempt_id=orchestration_attempt_id,
            identity_id=orchestration_identity_id,
            source_binding_id=source_binding_id,
            completed_at=completed_at,
        )
        if not cas_ok:
            raise TransactionBFailure(
                "TXB_CAS_FAILED",
                "Attempt CAS to COMPLETED failed (concurrent modification or wrong state)",
                field="attempt_status",
                details={"attempt_id": orchestration_attempt_id},
            )

        # 7 — Set identity.authoritative_attempt_id (CAS, P0-7)
        cas_identity_ok = self._identity_repo.set_authoritative_attempt(
            session,
            identity_id=orchestration_identity_id,
            attempt_id=orchestration_attempt_id,
        )
        if not cas_identity_ok:
            raise TransactionBFailure(
                "TXB_CAS_IDENTITY_FAILED",
                "set_authoritative_attempt CAS failed "
                "(identity not ACTIVE or attempt not COMPLETED)",
                field="identity_authoritative_attempt",
                details={
                    "identity_id": orchestration_identity_id,
                    "attempt_id": orchestration_attempt_id,
                },
            )

        # 8 — Persist completion outbox event
        self._outbox_repo.add(
            session,
            event_type="orchestration.attempt.completed",
            aggregate_type="OrchestrationRunAttempt",
            aggregate_id=orchestration_attempt_id,
            payload={
                "source_binding_id": source_binding_id,
                "combined_source_hash": candidate.combined_source_hash,
                "stage_result_hashes": {
                    stage.calculator_name: stage.result_hash for stage in persisted_stages
                },
            },
            request_id=request_id,
            identity_id=orchestration_identity_id,
            attempt_id=orchestration_attempt_id,
            source_binding_id=source_binding_id,
        )

        # 9 — Assemble result
        diagnostics = tuple(
            StageExecutionDiagnostic(
                calculator_name=stage.calculator_name,
                execution_status="passed",
                requires_review=requires_reviews.get(
                    _stage_name_for_calculator(stage.calculator_name), False
                ),
                input_hash=stage.input_hash,
                result_hash=stage.result_hash,
            )
            for stage in persisted_stages
        )

        return OrchestrationResult(
            request_id=request_id,
            identity_id=orchestration_identity_id,
            attempt_id=orchestration_attempt_id,
            attempt_number=None,
            status="COMPLETED",
            requires_review=any(requires_reviews.values()),
            persisted_stages=tuple(persisted_stages),
            diagnostics=diagnostics,
            source_binding_id=source_binding_id,
            fingerprint=orchestration_fingerprint,
            started_at=started_at,
            completed_at=completed_at,
        )

    # ── Internal helpers ────────────────────────────────────────────────

    def _validate_version_vector(self, version_vector: dict[str, str]) -> None:
        """Validate that the version vector key set is exactly the five stages."""
        expected_keys = frozenset(ORCHESTRATION_STAGE_ORDER)
        actual_keys = frozenset(version_vector.keys())
        if actual_keys != expected_keys:
            missing = expected_keys - actual_keys
            extra = actual_keys - expected_keys
            parts: list[str] = []
            if missing:
                parts.append(f"missing: {sorted(missing)}")
            if extra:
                parts.append(f"extra: {sorted(extra)}")
            raise TransactionBFailure(
                "TXB_VERSION_VECTOR_INVALID",
                f"Calculator version vector key set mismatch: {'; '.join(parts)}",
                field="calculator_version_vector",
                details={
                    "expected": sorted(expected_keys),
                    "actual": sorted(actual_keys),
                },
            )

    def _validate_calculator_identity(
        self,
        stage_name: str,
        exec_result: StageExecutionResult,
        version_vector: dict[str, str],
    ) -> None:
        """Validate that calculator_name, version, and type match expectations.

        The calculator_version is validated against the authoritative
        version vector from the identity record (P0-6).
        """
        expected_name, _expected_version, expected_type = _EXPECTED_CALCULATOR_IDENTITY[stage_name]
        expected_version = version_vector[stage_name]
        if exec_result.calculator_name != expected_name:
            raise TransactionBFailure(
                "TXB_CALCULATOR_IDENTITY_MISMATCH",
                f"Stage {stage_name!r}: expected calculator_name={expected_name!r}, "
                f"got {exec_result.calculator_name!r}",
                field="calculator_name",
                details={
                    "stage_name": stage_name,
                    "expected": expected_name,
                    "actual": exec_result.calculator_name,
                },
            )
        if exec_result.calculator_version != expected_version:
            raise TransactionBFailure(
                "TXB_CALCULATOR_IDENTITY_MISMATCH",
                f"Stage {stage_name!r}: expected calculator_version={expected_version!r}, "
                f"got {exec_result.calculator_version!r}",
                field="calculator_version",
                details={
                    "stage_name": stage_name,
                    "expected": expected_version,
                    "actual": exec_result.calculator_version,
                },
            )
        if exec_result.calculation_type != expected_type:
            raise TransactionBFailure(
                "TXB_CALCULATOR_IDENTITY_MISMATCH",
                f"Stage {stage_name!r}: expected calculation_type={expected_type!r}, "
                f"got {exec_result.calculation_type!r}",
                field="calculation_type",
                details={
                    "stage_name": stage_name,
                    "expected": expected_type,
                    "actual": exec_result.calculation_type,
                },
            )

    def _build_upstream_calculation_ids(
        self,
        stage_name: str,
        calc_ids: dict[str, str],
    ) -> dict[str, str]:
        """Build upstream_calculation_ids for a stage from previously persisted IDs."""
        upstream_keys = STAGE_UPSTREAM_PROVENANCE_KEYS[stage_name]
        return {key: calc_ids[key] for key in upstream_keys}

    def _build_typed_snapshot(
        self,
        *,
        stage_name: str,
        exec_result: StageExecutionResult,
        project_id: str,
        project_version_id: str,
        execution_snapshot_id: str,
        coefficient_context_id: str,
        orchestration_identity_id: str,
        orchestration_attempt_id: str,
        orchestration_fingerprint: str,
        upstream_calculation_ids: dict[str, str],
    ) -> SourceSnapshotContentV1:
        """Build a typed source snapshot for a stage.

        Uses the Pydantic subclass for the stage, which enforces Literal
        type constraints on calculator_id, calculator_version, and
        calculation_type.
        """
        snapshot_cls = _STAGE_SNAPSHOT_CLS[stage_name]
        calc_name, _calc_version, calc_type = _EXPECTED_CALCULATOR_IDENTITY[stage_name]
        return snapshot_cls(
            project_id=project_id,
            project_version_id=project_version_id,
            execution_snapshot_id=execution_snapshot_id,
            coefficient_context_id=coefficient_context_id,
            orchestration_identity_id=orchestration_identity_id,
            orchestration_attempt_id=orchestration_attempt_id,
            orchestration_fingerprint=orchestration_fingerprint,
            source_snapshot_schema_version="1.0.0",
            calculation_type=calc_type,
            calculator_id=calc_name,
            calculator_version=exec_result.calculator_version,
            requires_review=exec_result.requires_review,
            result_snapshot=exec_result.result_snapshot,
            formulas=exec_result.formulas,  # type: ignore[arg-type]
            coefficients=exec_result.coefficients,  # type: ignore[arg-type]
            assumptions=exec_result.assumptions,
            warnings=exec_result.warnings,  # type: ignore[arg-type]
            source_references=exec_result.source_references,  # type: ignore[arg-type]
            upstream_calculation_ids=dict(upstream_calculation_ids),
        )


# ── Helpers ─────────────────────────────────────────────────────────────────

# calculator_name → stage_name  (reverse lookup for diagnostics)
_CALCULATOR_TO_STAGE: Mapping[str, str] = {
    v: k
    for k, v in {
        "zone": "cold_room_zone_plan",
        "cooling_load": "cooling_load",
        "equipment": "equipment",
        "power": "installed_power",
        "investment": "investment_estimate",
    }.items()
}


def _stage_name_for_calculator(calculator_name: str) -> str:
    """Look up the stage name for a calculator name."""
    stage = _CALCULATOR_TO_STAGE.get(calculator_name)
    if stage is None:
        raise ValueError(f"Unknown calculator_name {calculator_name!r}")
    return stage
