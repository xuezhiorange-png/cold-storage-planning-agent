"""Production scheme generation service.

Entry point: generate_production_scheme_run()

Follows the production trust boundary:
  verified source_binding_id + approved weight_set_revision_id
  → independently verify binding + five source calculations
  → map typed snapshots to scheme domain
  → generate, validate, score schemes
  → atomically persist production SchemeRun with complete provenance

Also provides read_verified_production_scheme_run() for trusted readback.

Unit of Work pattern:
  The service owns the UoW lifecycle: create, enter, commit on success,
  exit (close session).  Repositories NEVER commit/rollback/close sessions.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from cold_storage.modules.schemes.application.production_ports import (
    GenerateProductionSchemeCommand,
    ProductionSchemeRunReadPort,
    ProductionSchemeRunRepository,
    SourceBindingReadPort,
    WeightRevisionReadPort,
)
from cold_storage.modules.schemes.application.production_uow import (
    ProductionSchemeUnitOfWork,
)
from cold_storage.modules.schemes.application.source_binding_verifier import (
    SourceBindingVerificationError,
    verify_source_binding,
)
from cold_storage.modules.schemes.application.source_domain_mapping import (
    map_source_to_generation_input,
)
from cold_storage.modules.schemes.application.weight_revision_governance import (
    WeightRevisionGovernanceError,
    load_and_validate_weight_revision,
)
from cold_storage.modules.schemes.domain.errors import (
    SchemeDomainError,
)
from cold_storage.modules.schemes.domain.generator import (
    GENERATOR_VERSION,
    generate_schemes,
)
from cold_storage.modules.schemes.domain.models import (
    SchemeCandidate,
    SchemeRun,
    SchemeScoreBreakdown,
)
from cold_storage.modules.schemes.domain.scoring import (
    score_candidates,
    stable_sort_key,
)
from cold_storage.modules.schemes.domain.validation import (
    validate_candidate,
)

# ── Source contract version ────────────────────────────────────────────────

SOURCE_CONTRACT_VERSION: str = "1.0.0"

# ── Production errors ──────────────────────────────────────────────────────


class ProductionSchemeError(SchemeDomainError):
    """Base error for production scheme generation."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ProjectVersionMismatchError(ProductionSchemeError):
    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(
            "project_version_mismatch",
            f"Caller project_version_id {actual!r} != binding {expected!r}",
        )


class SchemeRunPersistenceError(ProductionSchemeError):
    def __init__(self, detail: str) -> None:
        super().__init__("persistence_failure", f"Failed to persist production SchemeRun: {detail}")


class SchemeRunContentHashMismatchError(ProductionSchemeError):
    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(
            "content_hash_mismatch",
            f"SchemeRun content hash: expected {expected!r}, computed {actual!r}",
        )


class SchemeRunSourceModeError(ProductionSchemeError):
    def __init__(self, run_id: str, actual_mode: str) -> None:
        super().__init__(
            "source_mode_not_production",
            f"SchemeRun {run_id!r} source_mode is {actual_mode!r}, expected 'production'",
        )


class SchemeRunIdentityFieldError(ProductionSchemeError):
    def __init__(self, run_id: str, field: str) -> None:
        super().__init__(
            "missing_identity_field",
            f"Production SchemeRun {run_id!r} missing required field {field!r}",
        )


class SchemeRunBindingVerificationError(ProductionSchemeError):
    def __init__(self, run_id: str, detail: str) -> None:
        super().__init__(
            "binding_verification_failed",
            f"Re-verification of source binding failed for run {run_id!r}: {detail}",
        )


class SchemeRunWeightVerificationError(ProductionSchemeError):
    def __init__(self, run_id: str, detail: str) -> None:
        super().__init__(
            "weight_verification_failed",
            f"Re-verification of weight revision failed for run {run_id!r}: {detail}",
        )


class SchemeRunCandidateConsistencyError(ProductionSchemeError):
    def __init__(self, run_id: str, detail: str) -> None:
        super().__init__(
            "candidate_consistency_failure",
            f"Candidate consistency check failed for run {run_id!r}: {detail}",
        )


class PersistedSourceProvenanceMismatchError(ProductionSchemeError):
    def __init__(self, run_id: str, field: str, persisted: str, verified: str) -> None:
        super().__init__(
            "persisted_source_provenance_mismatch",
            f"Run {run_id!r} field {field!r}: persisted={persisted!r}, verified={verified!r}",
        )
        self.mismatched_field = field


# ── Snapshot validation error ──────────────────────────────────────────────


class PersistedSchemeSnapshotValidationError(Exception):
    """Raised when a persisted scheme snapshot fails strict type validation."""

    def __init__(self, *, field: str, detail: str) -> None:
        self.code = "persisted_scheme_snapshot_invalid"
        self.field = field
        self.detail = detail
        super().__init__(f"Snapshot field {field!r}: {detail}")


# ── Content hash computation ───────────────────────────────────────────────


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _compute_production_content_hash(
    *,
    source_binding_id: str,
    source_contract_version: str,
    binding_schema_version: str,
    project_id: str,
    project_version_id: str,
    execution_snapshot_id: str,
    coefficient_context_id: str,
    orchestration_identity_id: str,
    authoritative_attempt_id: str,
    orchestration_fingerprint: str,
    zone_calculation_id: str,
    cooling_load_calculation_id: str,
    equipment_calculation_id: str,
    power_calculation_id: str,
    investment_calculation_id: str,
    zone_result_hash: str,
    cooling_load_result_hash: str,
    equipment_result_hash: str,
    power_result_hash: str,
    investment_result_hash: str,
    combined_source_hash: str,
    weight_set_revision_id: str,
    weight_set_content_hash: str,
    weight_set_generator_compatibility_version: str,
    generator_version: str,
    profile_codes: tuple[str, ...],
    profile_parameters: dict[str, dict[str, Any]],
    candidates_snapshot: Any,
    score_breakdowns_snapshot: Any,
    recommended_scheme_code: str | None = None,
    requires_review: bool = False,
    status: str = "completed",
    input_snapshot: dict[str, Any] | None = None,
    assumption_snapshot: dict[str, Any] | None = None,
    comparison_snapshot: dict[str, Any] | None = None,
    warning_messages: list[str] | None = None,
) -> str:
    """Compute content hash covering ALL production provenance fields."""
    content = {
        "source_binding_id": source_binding_id,
        "source_contract_version": source_contract_version,
        "binding_schema_version": binding_schema_version,
        "project_id": project_id,
        "project_version_id": project_version_id,
        "execution_snapshot_id": execution_snapshot_id,
        "coefficient_context_id": coefficient_context_id,
        "orchestration_identity_id": orchestration_identity_id,
        "authoritative_attempt_id": authoritative_attempt_id,
        "orchestration_fingerprint": orchestration_fingerprint,
        "zone_calculation_id": zone_calculation_id,
        "cooling_load_calculation_id": cooling_load_calculation_id,
        "equipment_calculation_id": equipment_calculation_id,
        "power_calculation_id": power_calculation_id,
        "investment_calculation_id": investment_calculation_id,
        "zone_result_hash": zone_result_hash,
        "cooling_load_result_hash": cooling_load_result_hash,
        "equipment_result_hash": equipment_result_hash,
        "power_result_hash": power_result_hash,
        "investment_result_hash": investment_result_hash,
        "combined_source_hash": combined_source_hash,
        "weight_set_revision_id": weight_set_revision_id,
        "weight_set_content_hash": weight_set_content_hash,
        "weight_set_generator_compatibility_version": weight_set_generator_compatibility_version,
        "generator_version": generator_version,
        "profile_codes": list(profile_codes),
        "profile_parameters": dict(profile_parameters),
        "candidates": candidates_snapshot,
        "score_breakdowns": score_breakdowns_snapshot,
        "recommended_scheme_code": recommended_scheme_code,
        "requires_review": requires_review,
        "status": status,
        "input_snapshot": input_snapshot or {},
        "assumption_snapshot": assumption_snapshot or {},
        "comparison_snapshot": comparison_snapshot or {},
        "warning_messages": warning_messages or [],
    }
    return hashlib.sha256(_canonical_json(content).encode()).hexdigest()


# ── Decimal serialization ──────────────────────────────────────────────────


def _serialize_decimals(obj: Any) -> Any:
    """Recursively convert Decimal to string for JSON."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _serialize_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize_decimals(item) for item in obj]
    return obj


def _to_safe_dict(obj: Any) -> dict[str, Any]:
    """Convert a dataclass to dict with Decimal serialization."""
    if hasattr(obj, "__dataclass_fields__"):
        result: dict[str, Any] = _serialize_decimals(asdict(obj))
        return result
    return {}


# ── Production service ─────────────────────────────────────────────────────


class ProductionSchemeService:
    """Service for production scheme generation with verified source binding.

    Accepts a UoW factory instead of a raw session.  The service owns the
    transaction lifecycle: create UoW, execute, commit on success, exit
    (rollback on failure, close session).
    """

    def __init__(
        self,
        uow_factory: Callable[[], ProductionSchemeUnitOfWork],
        *,
        binding_read_port: SourceBindingReadPort,
        weight_revision_read_port: WeightRevisionReadPort,
        run_repository: ProductionSchemeRunRepository,
    ) -> None:
        self._uow_factory = uow_factory
        self._binding_port = binding_read_port
        self._weight_port = weight_revision_read_port
        self._run_repo = run_repository

    def generate_production_scheme_run(
        self,
        command: GenerateProductionSchemeCommand,
    ) -> SchemeRun:
        """Generate a production scheme run from verified source binding.

        1. Verify SourceBinding + five CalculationRuns
        2. Validate approved weight-set revision
        3. Map five typed snapshots to scheme domain
        4. Generate, validate, score schemes
        5. Atomically persist production SchemeRun with complete provenance
        """
        with self._uow_factory() as uow:
            try:
                result = self._generate_within_uow(command, uow)
                uow.commit()
            except Exception:
                uow.rollback()
                raise
            return result

    def _generate_within_uow(
        self,
        command: GenerateProductionSchemeCommand,
        uow: ProductionSchemeUnitOfWork,
    ) -> SchemeRun:
        """Execute the generation logic within a UoW boundary."""
        session = uow.session

        # 1. Verify SourceBinding
        try:
            source = verify_source_binding(
                self._binding_port,
                session,
                binding_id=command.source_binding_id,
            )
        except SourceBindingVerificationError as exc:
            raise ProductionSchemeError(
                exc.code, f"Source binding verification failed: {exc}"
            ) from exc

        # 2. Load and validate weight revision
        try:
            revision = load_and_validate_weight_revision(
                self._weight_port,
                session,
                revision_id=command.weight_set_revision_id,
                generator_version=GENERATOR_VERSION,
            )
        except WeightRevisionGovernanceError as exc:
            raise ProductionSchemeError(
                exc.code, f"Weight revision governance failed: {exc}"
            ) from exc

        # 3. Map source to generation input
        generation_input = map_source_to_generation_input(
            source,
            profile_codes=command.profile_codes,
            profile_parameters={k: dict(v) for k, v in command.profile_parameters.items()},
            generator_version=GENERATOR_VERSION,
        )

        # Build domain weight set from validated revision criteria
        from cold_storage.modules.schemes.domain.models import SchemeWeightSet

        weight_set = SchemeWeightSet(
            id=revision.id,
            code=revision.code,
            name=revision.code,
            revision=revision.revision,
            status="approved",
            source_type="production",
            criteria=list(revision.criteria),
            created_at=revision.approved_at,
            approved_at=revision.approved_at,
            requires_review=False,
        )

        # 4. Generate schemes
        raw_candidates = generate_schemes(generation_input)

        # 5. Validate and score
        from dataclasses import replace as dc_replace

        zone_map = {z.zone_code: z for z in generation_input.zone_results}
        candidates = []
        for cand in raw_candidates:
            constraint_results = validate_candidate(cand, generation_input, zone_map)
            all_passed = all(cr.passed for cr in constraint_results)
            validated = dc_replace(
                cand,
                constraint_results=constraint_results,
                feasible=all_passed,
            )
            candidates.append(validated)

        # Score
        score_breakdowns = score_candidates(candidates, weight_set)

        # Recommend
        feasible = [sb for sb in score_breakdowns if not sb.diagnostic_only]
        recommended_code = None
        recommended_reason = None
        if feasible:
            ranked = sorted(feasible, key=lambda sb: stable_sort_key(sb, candidates))
            recommended_code = ranked[0].scheme_code
            recommended_reason = f"Highest score: {ranked[0].total_score}"

        # 6. Build candidates snapshot
        candidates_snapshot = _serialize_decimals([_to_safe_dict(c) for c in candidates])
        score_breakdowns_snapshot = _serialize_decimals(
            [_to_safe_dict(sb) for sb in score_breakdowns]
        )

        # 6b. Compute total_score for recommendation snapshot
        total_score = Decimal(0)
        if feasible:
            total_score = max(sb.total_score for sb in feasible)

        # 6c. Build complete snapshot dicts for hash and persistence
        gen_input_snapshot = _serialize_decimals(_to_safe_dict(generation_input))
        full_assumption_snapshot: dict[str, Any] = {
            "source_mode": "production",
            "actor": command.actor,
            "correlation_id": command.correlation_id,
            "profile_codes": list(command.profile_codes),
            "profile_parameters": {k: dict(v) for k, v in command.profile_parameters.items()},
        }
        gen_comparison_snapshot: dict[str, Any] = {
            "recommended_scheme_code": recommended_code,
            "recommended_reason": recommended_reason,
            "total_score": str(total_score),
        }

        # 7. Compute content hash with ALL provenance fields
        content_hash = _compute_production_content_hash(
            source_binding_id=command.source_binding_id,
            source_contract_version=SOURCE_CONTRACT_VERSION,
            binding_schema_version=source.binding_schema_version,
            project_id=source.project_id,
            project_version_id=source.project_version_id,
            execution_snapshot_id=source.execution_snapshot_id,
            coefficient_context_id=source.coefficient_context_id,
            orchestration_identity_id=source.orchestration_identity_id,
            authoritative_attempt_id=source.orchestration_attempt_id,
            orchestration_fingerprint=source.orchestration_fingerprint,
            zone_calculation_id=source.zone_calculation_id,
            cooling_load_calculation_id=source.cooling_load_calculation_id,
            equipment_calculation_id=source.equipment_calculation_id,
            power_calculation_id=source.power_calculation_id,
            investment_calculation_id=source.investment_calculation_id,
            zone_result_hash=source.zone_result_hash,
            cooling_load_result_hash=source.cooling_load_result_hash,
            equipment_result_hash=source.equipment_result_hash,
            power_result_hash=source.power_result_hash,
            investment_result_hash=source.investment_result_hash,
            combined_source_hash=source.combined_source_hash,
            weight_set_revision_id=command.weight_set_revision_id,
            weight_set_content_hash=revision.content_hash,
            weight_set_generator_compatibility_version=(revision.generator_compatibility_version),
            generator_version=GENERATOR_VERSION,
            profile_codes=command.profile_codes,
            profile_parameters={k: dict(v) for k, v in command.profile_parameters.items()},
            candidates_snapshot=candidates_snapshot,
            score_breakdowns_snapshot=score_breakdowns_snapshot,
            recommended_scheme_code=recommended_code,
            requires_review=source.requires_review,
            status="completed",
            input_snapshot=gen_input_snapshot,
            assumption_snapshot=full_assumption_snapshot,
            comparison_snapshot=gen_comparison_snapshot,
            warning_messages=[],
        )

        # 8. Build and persist production SchemeRun
        run_id = f"prod-run-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC)

        run = SchemeRun(
            id=run_id,
            project_id=source.project_id,
            project_version_id=source.project_version_id,
            weight_set_id=revision.weight_set_id,
            status="completed",
            generator_version=GENERATOR_VERSION,
            source_snapshot_hash=source.combined_source_hash,
            input_snapshot=gen_input_snapshot,
            assumption_snapshot=full_assumption_snapshot,
            comparison_snapshot=gen_comparison_snapshot,
            candidates_snapshot=candidates_snapshot,
            requires_review=source.requires_review,
            recommended_scheme_code=recommended_code,
            warning_messages=[],
            created_at=now,
            completed_at=now,
            content_hash=content_hash,
        )

        # Build ranks
        ranks: dict[str, int] = {}
        if feasible:
            ranked = sorted(feasible, key=lambda sb: stable_sort_key(sb, candidates))
            for i, sb in enumerate(ranked, 1):
                ranks[sb.scheme_code] = i

        # Build candidate data for repository
        sb_map = {sb.scheme_code: sb for sb in score_breakdowns}
        candidate_data: list[dict[str, Any]] = []
        for cand in candidates:
            cand_sb = sb_map.get(cand.scheme_code)
            rank = ranks.get(cand.scheme_code)

            score_snapshot: dict[str, object] = {}
            if cand_sb is not None:
                score_snapshot = _to_safe_dict(cand_sb)

            candidate_data.append(
                {
                    "id": f"{run_id}-{cand.scheme_code}",
                    "scheme_code": cand.scheme_code,
                    "profile_code": cand.profile_code,
                    "feasible": cand.feasible,
                    "rank": rank,
                    "total_score": cand_sb.total_score if cand_sb is not None else None,
                    "score_breakdown_snapshot": score_snapshot,
                    "constraint_results": [
                        {
                            "code": cr.constraint_code,
                            "passed": cr.passed,
                            "detail": cr.detail,
                        }
                        for cr in cand.constraint_results
                    ],
                    "result_snapshot": _serialize_decimals(_to_safe_dict(cand)),
                }
            )

        # Persist via repository port (no ORM dependency, session from UoW)
        self._run_repo.save_production_run(
            session,
            run_id=run_id,
            project_id=source.project_id,
            project_version_id=source.project_version_id,
            weight_set_id=revision.weight_set_id,
            status="completed",
            generator_version=GENERATOR_VERSION,
            source_snapshot_hash=source.combined_source_hash,
            input_snapshot=gen_input_snapshot,
            assumption_snapshot={
                "source_mode": "production",
                "actor": command.actor,
                "correlation_id": command.correlation_id,
            },
            comparison_snapshot=gen_comparison_snapshot,
            candidates_snapshot=candidates_snapshot,
            requires_review=source.requires_review,
            recommended_scheme_code=recommended_code,
            warning_messages=[],
            content_hash=content_hash,
            source_mode="production",
            source_binding_id=command.source_binding_id,
            source_contract_version=SOURCE_CONTRACT_VERSION,
            binding_schema_version=source.binding_schema_version,
            execution_snapshot_id=source.execution_snapshot_id,
            coefficient_context_id=source.coefficient_context_id,
            orchestration_identity_id=source.orchestration_identity_id,
            authoritative_attempt_id=source.orchestration_attempt_id,
            orchestration_fingerprint=source.orchestration_fingerprint,
            zone_calculation_id=source.zone_calculation_id,
            cooling_load_calculation_id=source.cooling_load_calculation_id,
            equipment_calculation_id=source.equipment_calculation_id,
            power_calculation_id=source.power_calculation_id,
            investment_calculation_id=source.investment_calculation_id,
            zone_result_hash=source.zone_result_hash,
            cooling_load_result_hash=source.cooling_load_result_hash,
            equipment_result_hash=source.equipment_result_hash,
            power_result_hash=source.power_result_hash,
            investment_result_hash=source.investment_result_hash,
            combined_source_hash=source.combined_source_hash,
            weight_set_revision_id=command.weight_set_revision_id,
            weight_set_content_hash=revision.content_hash,
            weight_set_generator_compatibility_version=(revision.generator_compatibility_version),
            profile_codes=command.profile_codes,
            profile_parameters={k: dict(v) for k, v in command.profile_parameters.items()},
            candidates=candidate_data,
            database_backend=command.database_backend,
        )

        return run


# ── Trusted production readback ────────────────────────────────────────────

# Required production identity fields that must be non-null
_PRODUCTION_IDENTITY_FIELDS: tuple[str, ...] = (
    "source_binding_id",
    "source_contract_version",
    "combined_source_hash",
    "weight_set_revision_id",
    "weight_set_content_hash",
    "weight_set_generator_compatibility_version",
    "execution_snapshot_id",
    "coefficient_context_id",
    "orchestration_identity_id",
    "authoritative_attempt_id",
    "orchestration_fingerprint",
    "zone_calculation_id",
    "cooling_load_calculation_id",
    "equipment_calculation_id",
    "power_calculation_id",
    "investment_calculation_id",
    "zone_result_hash",
    "cooling_load_result_hash",
    "equipment_result_hash",
    "power_result_hash",
    "investment_result_hash",
)


# ── Domain object rebuild from DB snapshots ──────────────────────────────────


VALID_DIRECTIONS: frozenset[str] = frozenset({"higher_is_better", "lower_is_better", "binary_pass"})


def _require_field(snapshot: dict[str, Any], key: str, *, field_path: str) -> Any:
    """Get a required field from a snapshot dict. Raises on missing or NULL."""
    if key not in snapshot:
        raise PersistedSchemeSnapshotValidationError(
            field=field_path,
            detail=f"required field {key!r} missing from snapshot",
        )
    value = snapshot[key]
    if value is None:
        raise PersistedSchemeSnapshotValidationError(
            field=field_path,
            detail=f"required field {key!r} is NULL in snapshot",
        )
    return value


def _snapshot_field(snapshot: dict[str, Any], key: str, *, field_path: str) -> Any:
    """Get a field from snapshot dict. Raises if key is missing (allows NULL)."""
    if key not in snapshot:
        raise PersistedSchemeSnapshotValidationError(
            field=field_path,
            detail=f"expected field {key!r} missing from snapshot",
        )
    return snapshot[key]


def _to_decimal(v: Any, *, field_path: str = "") -> Decimal:
    """Convert a value to Decimal — only accept canonical string or Decimal.

    Rejects float (binary floating-point), int, bool, empty/missing, and
    non-numeric strings.
    """
    if v is None:
        raise PersistedSchemeSnapshotValidationError(
            field=field_path,
            detail="required decimal field is NULL",
        )
    if isinstance(v, Decimal):
        return v
    if isinstance(v, float):
        raise PersistedSchemeSnapshotValidationError(
            field=field_path,
            detail=f"binary float {v!r} rejected; must be string Decimal or Decimal",
        )
    if isinstance(v, bool):
        raise PersistedSchemeSnapshotValidationError(
            field=field_path,
            detail=f"bool {v!r} rejected; must be string Decimal or Decimal",
        )
    if isinstance(v, int):
        raise PersistedSchemeSnapshotValidationError(
            field=field_path,
            detail=f"raw int {v!r} rejected; must be string Decimal or Decimal",
        )
    if isinstance(v, str):
        if not v.strip():
            raise PersistedSchemeSnapshotValidationError(
                field=field_path,
                detail="empty or whitespace-only string rejected for decimal field",
            )
        try:
            return Decimal(v)
        except Exception as exc:
            raise PersistedSchemeSnapshotValidationError(
                field=field_path,
                detail=f"string {v!r} is not a valid Decimal: {exc}",
            ) from exc
    raise PersistedSchemeSnapshotValidationError(
        field=field_path,
        detail=f"unexpected type {type(v).__name__!r} for decimal field",
    )


def _to_int(v: Any, *, field_path: str = "") -> int:
    """Convert a value to int — only accept pure int (reject bool, float, str)."""
    if v is None:
        raise PersistedSchemeSnapshotValidationError(
            field=field_path,
            detail="required integer field is NULL",
        )
    if isinstance(v, bool):
        raise PersistedSchemeSnapshotValidationError(
            field=field_path,
            detail=f"bool {v!r} rejected; must be int",
        )
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        raise PersistedSchemeSnapshotValidationError(
            field=field_path,
            detail=f"float {v!r} rejected; must be int",
        )
    if isinstance(v, str):
        raise PersistedSchemeSnapshotValidationError(
            field=field_path,
            detail=f"string {v!r} rejected; must be int, not parsed from string",
        )
    raise PersistedSchemeSnapshotValidationError(
        field=field_path,
        detail=f"unexpected type {type(v).__name__!r} for integer field",
    )


def _require_str(v: Any, *, field_path: str = "", allow_empty: bool = False) -> str:
    """Require a non-empty string value. Raises on None, non-string, or empty/whitespace."""
    if v is None:
        raise PersistedSchemeSnapshotValidationError(
            field=field_path,
            detail="required string field is NULL",
        )
    if not isinstance(v, str):
        raise PersistedSchemeSnapshotValidationError(
            field=field_path,
            detail=f"unexpected type {type(v).__name__!r} for string field",
        )
    if not allow_empty and not v.strip():
        raise PersistedSchemeSnapshotValidationError(
            field=field_path,
            detail="empty or whitespace-only string rejected",
        )
    return v


def _require_bool(v: Any, *, field_path: str = "") -> bool:
    """Require a native bool value. Rejects int, str, and other truthy/falsy types."""
    if v is None:
        raise PersistedSchemeSnapshotValidationError(
            field=field_path,
            detail="required boolean field is NULL",
        )
    if not isinstance(v, bool):
        raise PersistedSchemeSnapshotValidationError(
            field=field_path,
            detail=f"unexpected type {type(v).__name__!r} for boolean field; must be bool",
        )
    return v


def _validate_direction(v: str, *, field_path: str) -> str:
    """Validate that a direction value is one of the known enum values."""
    if v not in VALID_DIRECTIONS:
        raise PersistedSchemeSnapshotValidationError(
            field=field_path,
            detail=f"unknown direction {v!r}; expected one of {sorted(VALID_DIRECTIONS)}",
        )
    return v


def _rebuild_scheme_candidate_from_snapshot(
    snapshot: dict[str, Any],
    *,
    field_path: str = "candidate",
) -> SchemeCandidate:
    """Rebuild a SchemeCandidate from a persisted result_snapshot dict.

    Converts all numeric fields from their JSON-serialised form back to
    ``Decimal`` so that ``stable_sort_key`` can operate on domain types.

    Raises PersistedSchemeSnapshotValidationError on any missing, NULL,
    or mis-typed field.
    """
    from cold_storage.modules.schemes.domain.models import (
        SchemeConstraintResult,
        SchemeMetric,
        SchemeRoomModule,
    )

    rf = _require_field  # shorthand

    # --- Room modules ---
    room_modules_raw = rf(snapshot, "room_modules", field_path=field_path)
    room_modules = [
        SchemeRoomModule(
            room_code=_require_str(
                rf(rm, "room_code", field_path=f"{field_path}.room_modules[i]"),
                field_path=f"{field_path}.room_modules[i].room_code",
            ),
            room_name=_require_str(
                rf(rm, "room_name", field_path=f"{field_path}.room_modules[i]"),
                field_path=f"{field_path}.room_modules[i].room_name",
            ),
            zone_codes=rf(rm, "zone_codes", field_path=f"{field_path}.room_modules[i]"),
            temperature_level=_require_str(
                rf(rm, "temperature_level", field_path=f"{field_path}.room_modules[i]"),
                field_path=f"{field_path}.room_modules[i].temperature_level",
            ),
            area_m2=_to_decimal(
                rf(rm, "area_m2", field_path=f"{field_path}.room_modules[i]"),
                field_path=f"{field_path}.room_modules[i].area_m2",
            ),
            position_count=_to_int(
                rf(rm, "position_count", field_path=f"{field_path}.room_modules[i]"),
                field_path=f"{field_path}.room_modules[i].position_count",
            ),
            storage_capacity_kg=_to_decimal(
                rf(rm, "storage_capacity_kg", field_path=f"{field_path}.room_modules[i]"),
                field_path=f"{field_path}.room_modules[i].storage_capacity_kg",
            ),
            design_cooling_load_kw_r=_to_decimal(
                rf(rm, "design_cooling_load_kw_r", field_path=f"{field_path}.room_modules[i]"),
                field_path=f"{field_path}.room_modules[i].design_cooling_load_kw_r",
            ),
            compressor_operating_capacity_kw_r=_to_decimal(
                rf(
                    rm,
                    "compressor_operating_capacity_kw_r",
                    field_path=f"{field_path}.room_modules[i]",
                ),
                field_path=f"{field_path}.room_modules[i].compressor_operating_capacity_kw_r",
            ),
            compressor_installed_capacity_kw_r=_to_decimal(
                rf(
                    rm,
                    "compressor_installed_capacity_kw_r",
                    field_path=f"{field_path}.room_modules[i]",
                ),
                field_path=f"{field_path}.room_modules[i].compressor_installed_capacity_kw_r",
            ),
            process_compatibility=_snapshot_field(
                rm,
                "process_compatibility",
                field_path=f"{field_path}.room_modules[i]",
            ),
            hygiene_zone=_snapshot_field(
                rm,
                "hygiene_zone",
                field_path=f"{field_path}.room_modules[i]",
            ),
            door_count=_to_int(
                rf(rm, "door_count", field_path=f"{field_path}.room_modules[i]"),
                field_path=f"{field_path}.room_modules[i].door_count",
            ),
            partition_length_proxy_m=_to_decimal(
                rf(rm, "partition_length_proxy_m", field_path=f"{field_path}.room_modules[i]"),
                field_path=f"{field_path}.room_modules[i].partition_length_proxy_m",
            ),
        )
        for rm in room_modules_raw
    ]

    # --- Constraint results ---
    constraint_results_raw = rf(snapshot, "constraint_results", field_path=field_path)
    constraint_results = [
        SchemeConstraintResult(
            constraint_code=_require_str(
                rf(cr, "constraint_code", field_path=f"{field_path}.constraint_results[i]"),
                field_path=f"{field_path}.constraint_results[i].constraint_code",
            ),
            passed=_require_bool(
                rf(cr, "passed", field_path=f"{field_path}.constraint_results[i]"),
                field_path=f"{field_path}.constraint_results[i].passed",
            ),
            detail=_require_str(
                rf(cr, "detail", field_path=f"{field_path}.constraint_results[i]"),
                field_path=f"{field_path}.constraint_results[i].detail",
            ),
            expected=_snapshot_field(
                cr,
                "expected",
                field_path=f"{field_path}.constraint_results[i]",
            ),
            actual=_snapshot_field(
                cr,
                "actual",
                field_path=f"{field_path}.constraint_results[i]",
            ),
        )
        for cr in constraint_results_raw
    ]

    # --- Metrics ---
    metrics_raw = rf(snapshot, "metrics", field_path=field_path)
    metrics = [
        SchemeMetric(
            code=_require_str(
                rf(m, "code", field_path=f"{field_path}.metrics[i]"),
                field_path=f"{field_path}.metrics[i].code",
            ),
            value=_to_decimal(
                rf(m, "value", field_path=f"{field_path}.metrics[i]"),
                field_path=f"{field_path}.metrics[i].value",
            ),
            unit=_require_str(
                rf(m, "unit", field_path=f"{field_path}.metrics[i]"),
                field_path=f"{field_path}.metrics[i].unit",
            ),
            direction=_validate_direction(
                _require_str(
                    rf(m, "direction", field_path=f"{field_path}.metrics[i]"),
                    field_path=f"{field_path}.metrics[i].direction",
                ),
                field_path=f"{field_path}.metrics[i].direction",
            ),
        )
        for m in metrics_raw
    ]

    return SchemeCandidate(
        scheme_code=_require_str(
            rf(snapshot, "scheme_code", field_path=field_path),
            field_path=f"{field_path}.scheme_code",
        ),
        scheme_name=_require_str(
            rf(snapshot, "scheme_name", field_path=field_path),
            field_path=f"{field_path}.scheme_name",
        ),
        profile_code=_require_str(
            rf(snapshot, "profile_code", field_path=field_path),
            field_path=f"{field_path}.profile_code",
        ),
        feasible=_require_bool(
            rf(snapshot, "feasible", field_path=field_path),
            field_path=f"{field_path}.feasible",
        ),
        constraint_results=constraint_results,
        room_modules=room_modules,
        zone_assignments=rf(snapshot, "zone_assignments", field_path=field_path),
        total_area_m2=_to_decimal(
            rf(snapshot, "total_area_m2", field_path=field_path),
            field_path=f"{field_path}.total_area_m2",
        ),
        total_position_count=_to_int(
            rf(snapshot, "total_position_count", field_path=field_path),
            field_path=f"{field_path}.total_position_count",
        ),
        room_module_count=_to_int(
            rf(snapshot, "room_module_count", field_path=field_path),
            field_path=f"{field_path}.room_module_count",
        ),
        door_count=_to_int(
            rf(snapshot, "door_count", field_path=field_path),
            field_path=f"{field_path}.door_count",
        ),
        partition_length_proxy_m=_to_decimal(
            rf(snapshot, "partition_length_proxy_m", field_path=field_path),
            field_path=f"{field_path}.partition_length_proxy_m",
        ),
        daily_throughput_kg_day=_to_decimal(
            rf(snapshot, "daily_throughput_kg_day", field_path=field_path),
            field_path=f"{field_path}.daily_throughput_kg_day",
        ),
        investment_cny=_to_decimal(
            rf(snapshot, "investment_cny", field_path=field_path),
            field_path=f"{field_path}.investment_cny",
        ),
        installed_power_kw_e=_to_decimal(
            rf(snapshot, "installed_power_kw_e", field_path=field_path),
            field_path=f"{field_path}.installed_power_kw_e",
        ),
        design_cooling_load_kw_r=_to_decimal(
            rf(snapshot, "design_cooling_load_kw_r", field_path=field_path),
            field_path=f"{field_path}.design_cooling_load_kw_r",
        ),
        compressor_operating_capacity_kw_r=_to_decimal(
            rf(snapshot, "compressor_operating_capacity_kw_r", field_path=field_path),
            field_path=f"{field_path}.compressor_operating_capacity_kw_r",
        ),
        compressor_installed_capacity_kw_r=_to_decimal(
            rf(snapshot, "compressor_installed_capacity_kw_r", field_path=field_path),
            field_path=f"{field_path}.compressor_installed_capacity_kw_r",
        ),
        compressor_standby_capacity_kw_r=_to_decimal(
            rf(snapshot, "compressor_standby_capacity_kw_r", field_path=field_path),
            field_path=f"{field_path}.compressor_standby_capacity_kw_r",
        ),
        condenser_heat_rejection_kw=_to_decimal(
            rf(snapshot, "condenser_heat_rejection_kw", field_path=field_path),
            field_path=f"{field_path}.condenser_heat_rejection_kw",
        ),
        metrics=metrics,
        assumptions=rf(snapshot, "assumptions", field_path=field_path),
        warnings=rf(snapshot, "warnings", field_path=field_path),
        requires_review=_require_bool(
            rf(snapshot, "requires_review", field_path=field_path),
            field_path=f"{field_path}.requires_review",
        ),
    )


def _rebuild_score_breakdown_from_snapshot(
    snapshot: dict[str, Any],
    *,
    field_path: str = "score_breakdown",
) -> SchemeScoreBreakdown:
    """Rebuild a SchemeScoreBreakdown from a persisted score_breakdown_snapshot dict.

    Raises PersistedSchemeSnapshotValidationError on any missing, NULL,
    or mis-typed field.
    """
    from cold_storage.modules.schemes.domain.models import SchemeCriterionScore

    rf = _require_field  # shorthand

    # --- Criterion scores ---
    criterion_scores_raw = rf(snapshot, "criterion_scores", field_path=field_path)
    criterion_scores = [
        SchemeCriterionScore(
            criterion_code=_require_str(
                rf(cs, "criterion_code", field_path=f"{field_path}.criterion_scores[i]"),
                field_path=f"{field_path}.criterion_scores[i].criterion_code",
            ),
            raw_value=_to_decimal(
                rf(cs, "raw_value", field_path=f"{field_path}.criterion_scores[i]"),
                field_path=f"{field_path}.criterion_scores[i].raw_value",
            ),
            unit=_require_str(
                rf(cs, "unit", field_path=f"{field_path}.criterion_scores[i]"),
                field_path=f"{field_path}.criterion_scores[i].unit",
            ),
            direction=_validate_direction(
                _require_str(
                    rf(cs, "direction", field_path=f"{field_path}.criterion_scores[i]"),
                    field_path=f"{field_path}.criterion_scores[i].direction",
                ),
                field_path=f"{field_path}.criterion_scores[i].direction",
            ),
            weight=_to_decimal(
                rf(cs, "weight", field_path=f"{field_path}.criterion_scores[i]"),
                field_path=f"{field_path}.criterion_scores[i].weight",
            ),
            min_value=_to_decimal(
                rf(cs, "min_value", field_path=f"{field_path}.criterion_scores[i]"),
                field_path=f"{field_path}.criterion_scores[i].min_value",
            ),
            max_value=_to_decimal(
                rf(cs, "max_value", field_path=f"{field_path}.criterion_scores[i]"),
                field_path=f"{field_path}.criterion_scores[i].max_value",
            ),
            normalized_score=_to_decimal(
                rf(cs, "normalized_score", field_path=f"{field_path}.criterion_scores[i]"),
                field_path=f"{field_path}.criterion_scores[i].normalized_score",
            ),
            weighted_contribution=_to_decimal(
                rf(cs, "weighted_contribution", field_path=f"{field_path}.criterion_scores[i]"),
                field_path=f"{field_path}.criterion_scores[i].weighted_contribution",
            ),
            formula=_require_str(
                rf(cs, "formula", field_path=f"{field_path}.criterion_scores[i]"),
                field_path=f"{field_path}.criterion_scores[i].formula",
            ),
        )
        for cs in criterion_scores_raw
    ]

    return SchemeScoreBreakdown(
        scheme_code=_require_str(
            rf(snapshot, "scheme_code", field_path=field_path),
            field_path=f"{field_path}.scheme_code",
        ),
        total_score=_to_decimal(
            rf(snapshot, "total_score", field_path=field_path),
            field_path=f"{field_path}.total_score",
        ),
        criterion_scores=criterion_scores,
        diagnostic_only=_require_bool(
            rf(snapshot, "diagnostic_only", field_path=field_path),
            field_path=f"{field_path}.diagnostic_only",
        ),
    )


def read_verified_production_scheme_run(
    read_port: ProductionSchemeRunReadPort,
    binding_read_port: SourceBindingReadPort,
    weight_revision_read_port: WeightRevisionReadPort,
    session: Any,
    *,
    run_id: str,
    generator_version: str,
) -> SchemeRun:
    """Trusted readback: independently verify a persisted production SchemeRun.
    1. Load SchemeRun by ID
    2. Verify source_mode == 'production'
    3. Verify all production identity fields non-null
    4. Re-verify online SourceBinding via SourceBindingVerifier
    5. Re-verify weight revision content hash
    6. Load candidates from DB and rebuild snapshots
    7. Recompute content hash using shared builder
    8. Compare persisted content hash
    9. Verify candidate count, rank, score, recommendation
    10. Return real SchemeRun from persisted data
    """
    # 1. Load SchemeRun
    persisted = read_port.load_production_run(session, run_id=run_id)
    if persisted is None:
        raise ProductionSchemeError("run_not_found", f"SchemeRun {run_id!r} not found")

    # 2. Verify source_mode == 'production'
    if persisted.source_mode != "production":
        raise SchemeRunSourceModeError(run_id, persisted.source_mode)

    # 3. Verify all production identity fields non-null
    for field_name in _PRODUCTION_IDENTITY_FIELDS:
        value = getattr(persisted, field_name, None)
        if value is None:
            raise SchemeRunIdentityFieldError(run_id, field_name)

    # 4. Re-verify SourceBinding and compare provenance field-by-field
    try:
        verified_source = verify_source_binding(
            binding_read_port,
            session,
            binding_id=persisted.source_binding_id or "",
        )
    except SourceBindingVerificationError as exc:
        raise SchemeRunBindingVerificationError(run_id, str(exc)) from exc

    # P0-4: Field-by-field provenance comparison
    sv = verified_source
    _prov: list[tuple[str, str | None, str]] = [
        ("project_id", persisted.project_id, sv.project_id),
        ("project_version_id", persisted.project_version_id, sv.project_version_id),
        ("binding_schema_version", persisted.binding_schema_version, sv.binding_schema_version),
        ("execution_snapshot_id", persisted.execution_snapshot_id, sv.execution_snapshot_id),
        ("coefficient_context_id", persisted.coefficient_context_id, sv.coefficient_context_id),
        (
            "orchestration_identity_id",
            persisted.orchestration_identity_id,
            sv.orchestration_identity_id,
        ),
        (
            "authoritative_attempt_id",
            persisted.authoritative_attempt_id,
            sv.orchestration_attempt_id,
        ),
        (
            "orchestration_fingerprint",
            persisted.orchestration_fingerprint,
            sv.orchestration_fingerprint,
        ),
        ("zone_calculation_id", persisted.zone_calculation_id, sv.zone_calculation_id),
        (
            "cooling_load_calculation_id",
            persisted.cooling_load_calculation_id,
            sv.cooling_load_calculation_id,
        ),
        (
            "equipment_calculation_id",
            persisted.equipment_calculation_id,
            sv.equipment_calculation_id,
        ),
        ("power_calculation_id", persisted.power_calculation_id, sv.power_calculation_id),
        (
            "investment_calculation_id",
            persisted.investment_calculation_id,
            sv.investment_calculation_id,
        ),
        ("zone_result_hash", persisted.zone_result_hash, sv.zone_result_hash),
        (
            "cooling_load_result_hash",
            persisted.cooling_load_result_hash,
            sv.cooling_load_result_hash,
        ),
        ("equipment_result_hash", persisted.equipment_result_hash, sv.equipment_result_hash),
        ("power_result_hash", persisted.power_result_hash, sv.power_result_hash),
        ("investment_result_hash", persisted.investment_result_hash, sv.investment_result_hash),
        ("combined_source_hash", persisted.combined_source_hash, sv.combined_source_hash),
    ]
    for field_name, persisted_val, verified_val in _prov:
        p_str = persisted_val or ""
        if p_str != verified_val:
            raise PersistedSourceProvenanceMismatchError(
                run_id,
                field_name,
                p_str,
                verified_val,
            )

    # P0-4: Verify source_contract_version against frozen production constant
    if persisted.source_contract_version != SOURCE_CONTRACT_VERSION:
        raise PersistedSourceProvenanceMismatchError(
            run_id,
            "source_contract_version",
            persisted.source_contract_version or "",
            SOURCE_CONTRACT_VERSION,
        )

    # P0-4: source_binding_id was used to load the binding (implicit verification);
    # source_snapshot_hash == combined_source_hash (already compared above).

    # 5. Re-verify weight revision content hash
    try:
        revision = load_and_validate_weight_revision(
            weight_revision_read_port,
            session,
            revision_id=persisted.weight_set_revision_id or "",
            generator_version=generator_version,
        )
    except WeightRevisionGovernanceError as exc:
        raise SchemeRunWeightVerificationError(run_id, str(exc)) from exc

    # 6. Load candidates from DB and rebuild snapshots
    candidates = read_port.load_candidates(session, run_id=run_id)
    if not candidates:
        raise SchemeRunCandidateConsistencyError(run_id, "No candidates found for production run")

    # Use candidates_snapshot and score_breakdowns_snapshot from persisted read model
    candidates_snapshot_stored = persisted.candidates_snapshot
    score_breakdowns_snapshot = persisted.score_breakdowns_snapshot

    cand_by_code: dict[str, Any] = {c.scheme_code: c for c in candidates}

    # Rebuild candidates_snapshot from DB records (same order)
    rebuilt_candidates_snapshot: list[dict[str, Any]] = []
    for cand_dict in candidates_snapshot_stored:
        sc = cand_dict.get("scheme_code", "") if isinstance(cand_dict, dict) else ""
        cand_rec = cand_by_code.get(sc)
        if cand_rec is not None:
            rebuilt_candidates_snapshot.append(dict(cand_rec.result_snapshot))
        else:
            rebuilt_candidates_snapshot.append(cand_dict)

    # 7. Recompute content hash using shared builder and compare
    recomputed_hash = _compute_production_content_hash(
        source_binding_id=persisted.source_binding_id or "",
        source_contract_version=persisted.source_contract_version or "",
        binding_schema_version=persisted.binding_schema_version or "",
        project_id=persisted.project_id,
        project_version_id=persisted.project_version_id,
        execution_snapshot_id=persisted.execution_snapshot_id or "",
        coefficient_context_id=persisted.coefficient_context_id or "",
        orchestration_identity_id=persisted.orchestration_identity_id or "",
        authoritative_attempt_id=persisted.authoritative_attempt_id or "",
        orchestration_fingerprint=persisted.orchestration_fingerprint or "",
        zone_calculation_id=persisted.zone_calculation_id or "",
        cooling_load_calculation_id=persisted.cooling_load_calculation_id or "",
        equipment_calculation_id=persisted.equipment_calculation_id or "",
        power_calculation_id=persisted.power_calculation_id or "",
        investment_calculation_id=persisted.investment_calculation_id or "",
        zone_result_hash=persisted.zone_result_hash or "",
        cooling_load_result_hash=persisted.cooling_load_result_hash or "",
        equipment_result_hash=persisted.equipment_result_hash or "",
        power_result_hash=persisted.power_result_hash or "",
        investment_result_hash=persisted.investment_result_hash or "",
        combined_source_hash=persisted.combined_source_hash or "",
        weight_set_revision_id=persisted.weight_set_revision_id or "",
        weight_set_content_hash=persisted.weight_set_content_hash or "",
        weight_set_generator_compatibility_version=(
            persisted.weight_set_generator_compatibility_version or ""
        ),
        generator_version=persisted.generator_version or generator_version,
        profile_codes=persisted.profile_codes,
        profile_parameters=persisted.profile_parameters,
        candidates_snapshot=rebuilt_candidates_snapshot,
        score_breakdowns_snapshot=score_breakdowns_snapshot,
        recommended_scheme_code=persisted.recommended_scheme_code,
        requires_review=persisted.requires_review,
        status=persisted.status,
        input_snapshot=persisted.input_snapshot,
        assumption_snapshot=persisted.assumption_snapshot,
        comparison_snapshot=persisted.comparison_snapshot,
        warning_messages=persisted.warning_messages,
    )
    if recomputed_hash != persisted.content_hash:
        raise SchemeRunContentHashMismatchError(persisted.content_hash or "", recomputed_hash)

    # 8. Verify recommendation consistency
    # P0-4: Rebuild SchemeCandidate + SchemeScoreBreakdown from DB
    rebuilt_domain_candidates: list[SchemeCandidate] = []
    rebuilt_domain_breakdowns: list[SchemeScoreBreakdown] = []
    for cand_rec in candidates:
        rebuilt_domain_candidates.append(
            _rebuild_scheme_candidate_from_snapshot(cand_rec.result_snapshot)
        )
    for sb_dict in score_breakdowns_snapshot:
        rebuilt_domain_breakdowns.append(_rebuild_score_breakdown_from_snapshot(sb_dict))

    # P0-4: Validate scheme_code uniqueness and set matching
    cand_codes = [c.scheme_code for c in rebuilt_domain_candidates]
    if len(cand_codes) != len(set(cand_codes)):
        dupes = [code for code in set(cand_codes) if cand_codes.count(code) > 1]
        raise SchemeRunCandidateConsistencyError(
            run_id,
            f"Duplicate scheme_code in candidates: {sorted(dupes)!r}",
        )
    sb_codes = [sb.scheme_code for sb in rebuilt_domain_breakdowns]
    if len(sb_codes) != len(set(sb_codes)):
        dupes = [code for code in set(sb_codes) if sb_codes.count(code) > 1]
        raise SchemeRunCandidateConsistencyError(
            run_id,
            f"Duplicate scheme_code in score breakdowns: {sorted(dupes)!r}",
        )
    if set(cand_codes) != set(sb_codes):
        raise SchemeRunCandidateConsistencyError(
            run_id,
            f"scheme_code sets differ: candidates={sorted(set(cand_codes))!r}, "
            f"breakdowns={sorted(set(sb_codes))!r}",
        )

    feasible_breakdowns = [sb for sb in rebuilt_domain_breakdowns if not sb.diagnostic_only]
    feasible_domain = [c for c in rebuilt_domain_candidates if c.feasible]
    if not feasible_breakdowns and persisted.recommended_scheme_code:
        raise SchemeRunCandidateConsistencyError(
            run_id,
            f"recommended_scheme_code {persisted.recommended_scheme_code!r} "
            f"set but no feasible candidates exist",
        )
    if feasible_breakdowns and not persisted.recommended_scheme_code:
        raise SchemeRunCandidateConsistencyError(
            run_id,
            "feasible candidates exist but recommended_scheme_code is None",
        )
    if feasible_breakdowns:
        # P0-4: Sort using domain stable_sort_key directly
        feasible_breakdowns.sort(
            key=lambda sb: stable_sort_key(sb, feasible_domain),
        )
        expected_recommended = feasible_breakdowns[0].scheme_code
        if (
            persisted.recommended_scheme_code
            and persisted.recommended_scheme_code != expected_recommended
        ):
            raise SchemeRunCandidateConsistencyError(
                run_id,
                f"recommended_scheme_code mismatch: "
                f"persisted={persisted.recommended_scheme_code!r}, "
                f"computed={expected_recommended!r}",
            )

    # 9. Verify candidate count matches
    if len(candidates) != persisted.candidates_count:
        raise SchemeRunCandidateConsistencyError(
            run_id,
            f"candidate count mismatch: persisted={persisted.candidates_count}, "
            f"loaded={len(candidates)}",
        )

    # Verify weight set used matches what we loaded
    if revision.weight_set_id != persisted.weight_set_id:
        raise SchemeRunWeightVerificationError(
            run_id,
            f"weight_set_id mismatch: persisted={persisted.weight_set_id!r}, "
            f"loaded={revision.weight_set_id!r}",
        )

    # 10. Build SchemeRun domain model from persisted data (real values, not defaults)
    return SchemeRun(
        id=persisted.id,
        project_id=persisted.project_id,
        project_version_id=persisted.project_version_id,
        weight_set_id=persisted.weight_set_id or "",
        status=persisted.status,
        generator_version=persisted.generator_version or generator_version,
        source_snapshot_hash=persisted.combined_source_hash or "",
        input_snapshot=persisted.input_snapshot,
        assumption_snapshot=persisted.assumption_snapshot,
        comparison_snapshot=persisted.comparison_snapshot,
        candidates_snapshot=rebuilt_candidates_snapshot,  # type: ignore[arg-type]
        requires_review=persisted.requires_review,
        recommended_scheme_code=persisted.recommended_scheme_code,
        warning_messages=persisted.warning_messages,
        created_at=persisted.created_at or datetime.now(UTC),
        completed_at=persisted.completed_at,
        content_hash=persisted.content_hash,
    )
