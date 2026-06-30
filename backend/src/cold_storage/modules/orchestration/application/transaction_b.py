"""Transaction B — five-stage calculator execution within a single atomic session.

Executes the DAG  zone → cooling_load → equipment → power → investment
inside one session boundary.  Persists 5 CalculationRuns + 1 SourceBinding,
transitions the attempt to COMPLETED, and emits an audit outbox event.

Failure contract (approved design):
    On any calculator or persistence failure the method raises
    ``TransactionBFailure``.  The caller is responsible for rolling back
    the session — this module never calls ``session.rollback()``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar, Protocol, runtime_checkable

from sqlalchemy.orm import Session

from cold_storage.modules.orchestration.domain.contracts import (
    AttemptStatus,
    OrchestrationResult,
    SourceBindingCandidate,
    StageExecutionDiagnostic,
    StagePersistedResult,
)
from cold_storage.modules.orchestration.domain.dag import (
    CALCULATOR_BINDINGS,
    ORCHESTRATION_STAGE_ORDER,
    STAGE_DEPENDENCIES,
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
from cold_storage.modules.orchestration.infrastructure.repositories import (
    AuditOutboxRepository,
    CalculationRunRepository,
    OrchestrationAttemptRepository,
    SourceBindingRepository,
)
from cold_storage.modules.projects.infrastructure.orm import CalculationRunRecord

# ── Canonical constants ─────────────────────────────────────────────────────

SOURCE_BINDING_SCHEMA_VERSION = "1.0.0"
SOURCE_SNAPSHOT_SCHEMA_VERSION = "1.0.0"


# ── Calculator port protocol ────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class StageExecutionInput:
    """Input for a single stage execution."""

    stage_name: str
    execution_snapshot: dict[str, object]
    coefficient_context: dict[str, object]
    upstream_results: dict[str, StagePersistedResult]  # stage_name → result


@dataclass(frozen=True, slots=True)
class StageExecutionResult:
    """Result of a single stage execution."""

    calculator_name: str
    calculator_version: str
    calculation_type: str
    result_snapshot: dict[str, object]
    input_snapshot: dict[str, object]
    requires_review: bool


@runtime_checkable
class CalculatorPort(Protocol):
    """Port that executes individual calculator stages."""

    def execute_stage(self, *, stage_input: StageExecutionInput) -> StageExecutionResult: ...


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
        outbox_repo: AuditOutboxRepository,
        calculator_port: CalculatorPort,
    ) -> None:
        self._calc_run_repo = calculation_run_repo
        self._source_binding_repo = source_binding_repo
        self._attempt_repo = attempt_repo
        self._outbox_repo = outbox_repo
        self._calculator_port = calculator_port

    # ── Public entry point ──────────────────────────────────────────────

    def execute(
        self,
        session: Session,
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
        execution_snapshot: dict[str, object],
        coefficient_context: dict[str, object],
        calculator_version_vector: dict[str, str],
    ) -> OrchestrationResult:
        """Execute Transaction B atomically.

        On success: persists 5 CalculationRuns + 1 SourceBinding,
        transitions attempt to COMPLETED, returns OrchestrationResult.

        On failure: raises TransactionBFailure (caller must rollback).
        """
        started_at = datetime.now(UTC)

        persisted_stages: list[StagePersistedResult] = []
        upstream_results: dict[str, StagePersistedResult] = {}
        requires_review_by_calculator: dict[str, bool] = {}

        # 1 — Execute each stage in DAG order
        for stage_name in ORCHESTRATION_STAGE_ORDER:
            try:
                _calculator_version = calculator_version_vector[stage_name]
            except KeyError as err:
                raise TransactionBFailure(
                    "TXB_CALCULATOR_VERSION_MISSING",
                    f"No calculator_version for stage {stage_name!r} in version vector",
                    field="calculator_version_vector",
                    details={"stage_name": stage_name},
                ) from err

            stage_input = self._build_stage_input(
                stage_name=stage_name,
                execution_snapshot=execution_snapshot,
                coefficient_context=coefficient_context,
                upstream_results=upstream_results,
            )

            try:
                exec_result = self._calculator_port.execute_stage(stage_input=stage_input)
            except OrchestrationDomainError:
                raise
            except Exception as exc:
                raise TransactionBFailure(
                    "TXB_STAGE_EXECUTION_FAILED",
                    f"Calculator execution failed for stage {stage_name!r}: {exc}",
                    field="calculator_port",
                    details={"stage_name": stage_name, "error": str(exc)},
                ) from exc

            persisted = self._build_persisted_stage(
                session=session,
                project_id=project_id,
                project_version_id=project_version_id,
                execution_snapshot_id=execution_snapshot_id,
                coefficient_context_id=coefficient_context_id,
                orchestration_identity_id=orchestration_identity_id,
                orchestration_attempt_id=orchestration_attempt_id,
                stage_name=stage_name,
                exec_result=exec_result,
            )
            persisted_stages.append(persisted)
            upstream_results[stage_name] = persisted
            requires_review_by_calculator[persisted.calculator_name] = exec_result.requires_review

        # 2 — Build and persist SourceBinding
        slot_ids = {stage.calculator_name: stage.calculation_run_id for stage in persisted_stages}
        per_calc_result_hashes = {
            stage.calculator_name: stage.result_hash for stage in persisted_stages
        }
        combined_hash = result_hash(
            {
                "per_calculation_result_hashes": per_calc_result_hashes,
                "orchestration_fingerprint": orchestration_fingerprint,
            }
        )

        candidate = SourceBindingCandidate(
            identity_id=orchestration_identity_id,
            attempt_id=orchestration_attempt_id,
            fingerprint=orchestration_fingerprint,
            zone_calculation_id=slot_ids["cold_room_zone_plan"],
            cooling_load_calculation_id=slot_ids["cooling_load"],
            equipment_calculation_id=slot_ids["equipment"],
            power_calculation_id=slot_ids["installed_power"],
            investment_calculation_id=slot_ids["investment_estimate"],
            per_calculation_result_hashes=per_calc_result_hashes,
            combined_source_hash=combined_hash,
            schema_version=SOURCE_BINDING_SCHEMA_VERSION,
        )

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

        # 3 — Transition attempt to COMPLETED
        completed_at = datetime.now(UTC)
        self._attempt_repo.update_status(
            session,
            orchestration_attempt_id,
            status=AttemptStatus.COMPLETED,
            source_binding_id=source_binding_id,
            completed_at=completed_at,
        )

        # 4 — Persist completion outbox event
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

        # 5 — Assemble result
        diagnostics = tuple(
            StageExecutionDiagnostic(
                calculator_name=stage.calculator_name,
                execution_status="passed",
                requires_review=requires_review_by_calculator.get(stage.calculator_name, False),
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
            requires_review=any(requires_review_by_calculator.values()),
            persisted_stages=tuple(persisted_stages),
            diagnostics=diagnostics,
            source_binding_id=source_binding_id,
            fingerprint=orchestration_fingerprint,
            started_at=started_at,
            completed_at=completed_at,
        )

    # ── Internal helpers ────────────────────────────────────────────────

    def _build_stage_input(
        self,
        *,
        stage_name: str,
        execution_snapshot: dict[str, object],
        coefficient_context: dict[str, object],
        upstream_results: dict[str, StagePersistedResult],
    ) -> StageExecutionInput:
        """Collect upstream dependencies for *stage_name*."""
        deps = STAGE_DEPENDENCIES[stage_name]
        upstream = {dep: upstream_results[dep] for dep in deps}
        return StageExecutionInput(
            stage_name=stage_name,
            execution_snapshot=execution_snapshot,
            coefficient_context=coefficient_context,
            upstream_results=upstream,
        )

    def _build_persisted_stage(
        self,
        session: Session,
        *,
        project_id: str,
        project_version_id: str,
        execution_snapshot_id: str,
        coefficient_context_id: str,
        orchestration_identity_id: str,
        orchestration_attempt_id: str,
        stage_name: str,
        exec_result: StageExecutionResult,
    ) -> StagePersistedResult:
        """Execute a calculator stage and persist the CalculationRun."""
        calculator_id = CALCULATOR_BINDINGS[stage_name]
        in_hash = result_hash(exec_result.input_snapshot)
        res_hash = result_hash(exec_result.result_snapshot)

        provenance: dict[str, object] = {
            "execution_snapshot_id": execution_snapshot_id,
            "coefficient_context_id": coefficient_context_id,
            "orchestration_identity_id": orchestration_identity_id,
            "orchestration_run_attempt_id": orchestration_attempt_id,
            "upstream_calculation_ids": {},
        }

        calc_run_id = self._calc_run_repo.add(
            session,
            project_id=project_id,
            project_version_id=project_version_id,
            calculator_name=calculator_id,
            calculator_version=exec_result.calculator_version,
            calculation_type=exec_result.calculation_type,
            input_snapshot=dict(exec_result.input_snapshot),
            result_snapshot=dict(exec_result.result_snapshot),
            requires_review=exec_result.requires_review,
            orchestration_identity_id=orchestration_identity_id,
            orchestration_run_attempt_id=orchestration_attempt_id,
            execution_snapshot_id=execution_snapshot_id,
            coefficient_context_id=coefficient_context_id,
            input_hash=in_hash,
            result_hash=res_hash,
            provenance=provenance,
            schema_version=SOURCE_SNAPSHOT_SCHEMA_VERSION,
        )

        return StagePersistedResult(
            calculator_name=calculator_id,
            calculation_run_id=calc_run_id,
            input_hash=in_hash,
            result_hash=res_hash,
            calculator_version=exec_result.calculator_version,
            snapshot_schema_version=SOURCE_SNAPSHOT_SCHEMA_VERSION,
        )


# ── Source Binding Verifier ─────────────────────────────────────────────────


class SourceBindingVerifier:
    """Validates a SourceBindingCandidate against authoritative state.

    Rejects candidates with slot, identity/provenance, upstream dependency,
    schema, hash, or CalculationRun integrity violations.
    """

    # stage_name → (candidate_field, calculator_name, calculation_type)
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

    def verify(
        self,
        *,
        candidate: SourceBindingCandidate,
        project_id: str,
        project_version_id: str,
        execution_snapshot_id: str,
        coefficient_context_id: str,
        orchestration_identity_id: str,
        orchestration_attempt_id: str,
        attempt_status: str,
        is_authoritative_attempt: bool,
        calculation_runs: dict[str, CalculationRunRecord],  # stage_name → record
        expected_fingerprint: str,
    ) -> None:
        """Verify binding integrity.  Raises OrchestrationDomainError on failure."""
        self._verify_candidate_identity(
            candidate=candidate,
            orchestration_identity_id=orchestration_identity_id,
            orchestration_attempt_id=orchestration_attempt_id,
            attempt_status=attempt_status,
            is_authoritative_attempt=is_authoritative_attempt,
            expected_fingerprint=expected_fingerprint,
        )

        self._verify_schema(candidate=candidate, calculation_runs=calculation_runs)

        self._verify_slots(
            candidate=candidate,
            calculation_runs=calculation_runs,
            project_id=project_id,
            project_version_id=project_version_id,
            execution_snapshot_id=execution_snapshot_id,
            coefficient_context_id=coefficient_context_id,
            orchestration_identity_id=orchestration_identity_id,
            orchestration_attempt_id=orchestration_attempt_id,
        )

        self._verify_upstream(calculation_runs=calculation_runs)

        self._verify_hashes(candidate=candidate, calculation_runs=calculation_runs)

        self._verify_calculation_run_completeness(calculation_runs=calculation_runs)

    # ── Identity / provenance validation ──────────────────────────────

    def _verify_candidate_identity(
        self,
        *,
        candidate: SourceBindingCandidate,
        orchestration_identity_id: str,
        orchestration_attempt_id: str,
        attempt_status: str,
        is_authoritative_attempt: bool,
        expected_fingerprint: str,
    ) -> None:
        """Verify candidate-level identity and provenance fields."""
        if candidate.fingerprint != expected_fingerprint:
            raise SourceBindingIdentityMismatchError(
                "fingerprint", expected_fingerprint, candidate.fingerprint
            )

        if not is_authoritative_attempt:
            raise SourceBindingIdentityMismatchError("is_authoritative_attempt", "true", "false")

        if attempt_status != str(AttemptStatus.COMPLETED):
            raise SourceBindingIdentityMismatchError(
                "attempt_status", str(AttemptStatus.COMPLETED), attempt_status
            )

        if candidate.identity_id != orchestration_identity_id:
            raise SourceBindingIdentityMismatchError(
                "identity_id", orchestration_identity_id, candidate.identity_id
            )

        if candidate.attempt_id != orchestration_attempt_id:
            raise SourceBindingIdentityMismatchError(
                "attempt_id", orchestration_attempt_id, candidate.attempt_id
            )

    # ── Schema validation ─────────────────────────────────────────────

    def _verify_schema(
        self,
        *,
        candidate: SourceBindingCandidate,
        calculation_runs: dict[str, CalculationRunRecord],
    ) -> None:
        """Verify binding and source snapshot schema versions."""
        if candidate.schema_version not in self._SUPPORTED_BINDING_SCHEMA_VERSIONS:
            raise UnsupportedSchemaError("binding", candidate.schema_version)

        for stage_name, run in calculation_runs.items():
            sv = run.schema_version
            if sv is None or sv not in self._SUPPORTED_SOURCE_SNAPSHOT_SCHEMA_VERSIONS:
                raise SourceSnapshotSchemaError(
                    sv or "<null>",
                    f"stage {stage_name!r}",
                )

    # ── Slot validation ───────────────────────────────────────────────

    def _verify_slots(
        self,
        *,
        candidate: SourceBindingCandidate,
        calculation_runs: dict[str, CalculationRunRecord],
        project_id: str,
        project_version_id: str,
        execution_snapshot_id: str,
        coefficient_context_id: str,
        orchestration_identity_id: str,
        orchestration_attempt_id: str,
    ) -> None:
        """Verify slot completeness, uniqueness, types, and per-run identity."""
        # ── Missing / empty slot ──────────────────────────────────────
        slot_ids: dict[str, str] = {}
        for stage_name, (candidate_field, _calc_name, _calc_type) in self._SLOT_DEFS.items():
            calc_id: str = getattr(candidate, candidate_field)
            if not calc_id or not calc_id.strip():
                raise TransactionInvariantError(f"Slot {candidate_field!r} is empty")
            slot_ids[stage_name] = calc_id

        # ── Duplicate CalculationRun IDs across slots ─────────────────
        seen: set[str] = set()
        for stage_name, calc_id in slot_ids.items():
            if calc_id in seen:
                raise TransactionInvariantError(
                    f"Duplicate calculation_run_id {calc_id!r} (first seen at stage {stage_name!r})"
                )
            seen.add(calc_id)

        # ── Per-slot CalculationRunRecord validation ──────────────────
        for stage_name, (
            candidate_field,
            expected_calculator,
            expected_type,
        ) in self._SLOT_DEFS.items():
            if stage_name not in calculation_runs:
                raise TransactionInvariantError(f"Missing calculation run for stage {stage_name!r}")

            run = calculation_runs[stage_name]
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

    # ── Per-run identity / provenance ─────────────────────────────────

    def _verify_run_identity(
        self,
        *,
        run: CalculationRunRecord,
        stage_name: str,
        project_id: str,
        project_version_id: str,
        execution_snapshot_id: str,
        coefficient_context_id: str,
        orchestration_identity_id: str,
        orchestration_attempt_id: str,
    ) -> None:
        """Verify a single CalculationRunRecord's identity fields."""
        _ = stage_name  # used for context in error messages upstream

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

    # ── Upstream dependency validation ────────────────────────────────

    def _verify_upstream(
        self,
        *,
        calculation_runs: dict[str, CalculationRunRecord],
    ) -> None:
        """Verify upstream dependency integrity via provenance fields."""
        for stage_name, upstream_keys in STAGE_UPSTREAM_PROVENANCE_KEYS.items():
            if not upstream_keys:
                continue

            if stage_name not in calculation_runs:
                continue  # already caught by slot validation

            run = calculation_runs[stage_name]
            provenance = run.provenance
            if provenance is None:
                raise TransactionInvariantError(
                    f"CalculationRun for stage {stage_name!r} has NULL provenance"
                )

            upstream_ids = provenance.get("upstream_calculation_ids", {})
            if not isinstance(upstream_ids, dict):
                raise TransactionInvariantError(
                    f"CalculationRun for stage {stage_name!r} has non-dict upstream_calculation_ids"
                )

            for upstream_key in upstream_keys:
                if upstream_key not in calculation_runs:
                    raise TransactionInvariantError(
                        f"Missing upstream stage {upstream_key!r} for stage {stage_name!r}"
                    )
                expected_id = calculation_runs[upstream_key].id

                actual_id = upstream_ids.get(upstream_key)
                if actual_id != expected_id:
                    raise TransactionInvariantError(
                        f"Upstream dependency mismatch for stage {stage_name!r}: "
                        f"expected {upstream_key}={expected_id!r}, got {actual_id!r}"
                    )

    # ── Hash validation ───────────────────────────────────────────────

    def _verify_hashes(
        self,
        *,
        candidate: SourceBindingCandidate,
        calculation_runs: dict[str, CalculationRunRecord],
    ) -> None:
        """Verify per-calculation result hashes, key set, and combined hash."""
        expected_calculators = frozenset(
            calc_name for _, (_, calc_name, _) in self._SLOT_DEFS.items()
        )

        # ── Hash map key set tampering (extra or missing keys) ────────
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

        # ── Per-calculation result hash tampering ─────────────────────
        for stage_name, (_, expected_calculator, _) in self._SLOT_DEFS.items():
            if stage_name not in calculation_runs:
                continue  # already caught by slot validation

            run = calculation_runs[stage_name]
            expected_hash = run.result_hash
            actual_hash = candidate.per_calculation_result_hashes.get(expected_calculator)

            if actual_hash != expected_hash:
                raise SourceBindingHashMismatchError(
                    f"per_calculation_result_hashes[{expected_calculator!r}]",
                    expected_hash or "",
                    actual_hash or "",
                )

        # ── Combined hash tampering ───────────────────────────────────
        expected_combined = result_hash(
            {
                "per_calculation_result_hashes": dict(candidate.per_calculation_result_hashes),
                "orchestration_fingerprint": candidate.fingerprint,
            }
        )
        if candidate.combined_source_hash != expected_combined:
            raise SourceBindingHashMismatchError(
                "combined_source_hash",
                expected_combined,
                candidate.combined_source_hash,
            )

    # ── CalculationRun completeness validation ────────────────────────

    def _verify_calculation_run_completeness(
        self,
        *,
        calculation_runs: dict[str, CalculationRunRecord],
    ) -> None:
        """Reject partial or legacy CalculationRuns (orchestration fields NULL)."""
        for stage_name, run in calculation_runs.items():
            self._require_not_null(
                stage_name, run.orchestration_identity_id, "orchestration_identity_id"
            )
            self._require_not_null(
                stage_name, run.orchestration_run_attempt_id, "orchestration_run_attempt_id"
            )
            self._require_not_null(stage_name, run.execution_snapshot_id, "execution_snapshot_id")
            self._require_not_null(stage_name, run.coefficient_context_id, "coefficient_context_id")
            self._require_not_null(stage_name, run.result_hash, "result_hash")
            self._require_not_null(stage_name, run.input_hash, "input_hash")
            self._require_not_null(stage_name, run.provenance, "provenance")
            self._require_not_null(stage_name, run.schema_version, "schema_version")
            self._require_not_null(stage_name, run.calculation_type, "calculation_type")

            # requires_review must be a valid bool (mismatch if not)
            if not isinstance(run.requires_review, bool):
                raise TransactionInvariantError(
                    f"CalculationRun for stage {stage_name!r} has "
                    f"invalid requires_review: {run.requires_review!r}"
                )

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
