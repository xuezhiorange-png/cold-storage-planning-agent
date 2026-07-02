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
    feasible = [
        c
        for c in candidates
        if c.feasible and not c.score_breakdown_snapshot.get("diagnostic_only", False)
    ]
    if not feasible and persisted.recommended_scheme_code:
        raise SchemeRunCandidateConsistencyError(
            run_id,
            f"recommended_scheme_code {persisted.recommended_scheme_code!r} "
            f"set but no feasible candidates exist",
        )
    if feasible and not persisted.recommended_scheme_code:
        raise SchemeRunCandidateConsistencyError(
            run_id,
            "feasible candidates exist but recommended_scheme_code is None",
        )
    if feasible:
        # Sort using Decimal stable_sort_key logic (same as generation path)
        feasible.sort(
            key=lambda c: (
                -(Decimal(str(c.total_score)) if c.total_score is not None else Decimal(0)),
                Decimal(str(c.score_breakdown_snapshot.get("investment_cny", 0)))
                if c.score_breakdown_snapshot.get("investment_cny") is not None
                else Decimal(0),
                Decimal(str(c.score_breakdown_snapshot.get("installed_power_kw_e", 0)))
                if c.score_breakdown_snapshot.get("installed_power_kw_e") is not None
                else Decimal(0),
                c.scheme_code,
            )
        )
        expected_recommended = feasible[0].scheme_code
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
