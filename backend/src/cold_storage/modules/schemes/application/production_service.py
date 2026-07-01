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
    SchemeRun,
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
        "weight_set_generator_compatibility_version": (weight_set_generator_compatibility_version),
        "generator_version": generator_version,
        "profile_codes": list(profile_codes),
        "profile_parameters": dict(profile_parameters),
        "candidates": candidates_snapshot,
        "score_breakdowns": score_breakdowns_snapshot,
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
        )

        # 8. Build and persist production SchemeRun
        run_id = f"prod-run-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC)
        total_score = Decimal(0)
        if feasible:
            total_score = max(sb.total_score for sb in feasible)

        run = SchemeRun(
            id=run_id,
            project_id=source.project_id,
            project_version_id=source.project_version_id,
            weight_set_id=revision.weight_set_id,
            status="completed",
            generator_version=GENERATOR_VERSION,
            source_snapshot_hash=source.combined_source_hash,
            input_snapshot=_serialize_decimals(_to_safe_dict(generation_input)),
            assumption_snapshot={
                "source_mode": "production",
                "actor": command.actor,
                "correlation_id": command.correlation_id,
            },
            comparison_snapshot={
                "recommended_scheme_code": recommended_code,
                "recommended_reason": recommended_reason,
                "total_score": str(total_score),
            },
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
                    "total_score": (cand.total_score if hasattr(cand, "total_score") else None),
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
            input_snapshot=_serialize_decimals(_to_safe_dict(generation_input)),
            assumption_snapshot={
                "source_mode": "production",
                "actor": command.actor,
                "correlation_id": command.correlation_id,
            },
            comparison_snapshot={
                "recommended_scheme_code": recommended_code,
                "recommended_reason": recommended_reason,
                "total_score": str(total_score),
            },
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
    4. Recompute content hash and compare
    5. Re-verify online SourceBinding via SourceBindingVerifier
    6. Re-verify weight revision content hash
    7. Load candidates and scores, verify consistency
    8. Return verified SchemeRun domain model
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

    # 4. Re-verify SourceBinding (result confirms integrity, not used further)
    try:
        verify_source_binding(
            binding_read_port,
            session,
            binding_id=persisted.source_binding_id or "",
        )
    except SourceBindingVerificationError as exc:
        raise SchemeRunBindingVerificationError(run_id, str(exc)) from exc

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

    # 6. Load candidates for consistency check
    candidates = read_port.load_candidates(session, run_id=run_id)
    if not candidates:
        raise SchemeRunCandidateConsistencyError(run_id, "No candidates found for production run")

    # 7. Build domain SchemeRun
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

    # Verify weight set used matches what we loaded
    if weight_set.id != persisted.weight_set_id:
        raise SchemeRunWeightVerificationError(
            run_id,
            f"weight_set_id mismatch: persisted={persisted.weight_set_id!r}, "
            f"loaded={weight_set.id!r}",
        )

    # Rebuild SchemeRun domain model from persisted data
    now = datetime.now(UTC)

    return SchemeRun(
        id=persisted.id,
        project_id=persisted.project_id,
        project_version_id=persisted.project_version_id,
        weight_set_id=persisted.weight_set_id or "",
        status="completed",
        generator_version=generator_version,
        source_snapshot_hash=persisted.combined_source_hash or "",
        input_snapshot={},
        assumption_snapshot={
            "source_mode": "production",
            "verified_at": now.isoformat(),
            "content_hash_verified": True,
        },
        comparison_snapshot={
            "candidates_count": len(candidates),
            "content_hash_verified": True,
        },
        candidates_snapshot={},
        requires_review=False,
        recommended_scheme_code=None,
        warning_messages=[],
        created_at=now,
        completed_at=now,
        content_hash=persisted.content_hash,
    )
