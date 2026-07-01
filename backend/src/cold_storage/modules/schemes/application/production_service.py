"""Production scheme generation service.

Entry point: generate_production_scheme_run()

Follows the production trust boundary:
  verified source_binding_id + approved weight_set_revision_id
  → independently verify binding + five source calculations
  → map typed snapshots to scheme domain
  → generate, validate, score schemes
  → atomically persist production SchemeRun with complete provenance

Repositories MUST NOT commit/rollback/close/create sessions.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from cold_storage.modules.schemes.application.production_ports import (
    GenerateProductionSchemeCommand,
    ProductionSchemeRunRepository,
    SourceBindingReadPort,
    WeightRevisionReadPort,
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


# ── Content hash computation ───────────────────────────────────────────────


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _compute_production_content_hash(
    *,
    source_binding_id: str,
    weight_set_revision_id: str,
    combined_source_hash: str,
    weight_set_content_hash: str,
    candidates_snapshot: Any,
    score_breakdowns_snapshot: Any,
    profile_codes: tuple[str, ...],
    profile_parameters: dict[str, dict[str, Any]],
) -> str:
    """Compute content hash covering production source + weight identity."""
    content = {
        "source_binding_id": source_binding_id,
        "weight_set_revision_id": weight_set_revision_id,
        "combined_source_hash": combined_source_hash,
        "weight_set_content_hash": weight_set_content_hash,
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
    """Service for production scheme generation with verified source binding."""

    def __init__(
        self,
        session: Any,
        *,
        binding_read_port: SourceBindingReadPort,
        weight_revision_read_port: WeightRevisionReadPort,
        run_repository: ProductionSchemeRunRepository,
    ) -> None:
        self._session = session
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
        5. Persist production SchemeRun with complete provenance
        """
        # 1. Verify SourceBinding
        try:
            source = verify_source_binding(
                self._binding_port,
                self._session,
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
                self._session,
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

        # 7. Compute content hash
        content_hash = _compute_production_content_hash(
            source_binding_id=command.source_binding_id,
            weight_set_revision_id=command.weight_set_revision_id,
            combined_source_hash=source.combined_source_hash,
            weight_set_content_hash=revision.content_hash,
            candidates_snapshot=candidates_snapshot,
            score_breakdowns_snapshot=score_breakdowns_snapshot,
            profile_codes=command.profile_codes,
            profile_parameters={k: dict(v) for k, v in command.profile_parameters.items()},
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
                    "total_score": cand.total_score if hasattr(cand, "total_score") else None,
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

        # Persist via repository port (no ORM dependency)
        self._run_repo.save_production_run(
            self._session,
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
            weight_set_revision_id=command.weight_set_revision_id,
            weight_set_content_hash=revision.content_hash,
            weight_set_generator_compatibility_version=revision.generator_compatibility_version,
            combined_source_hash=source.combined_source_hash,
            candidates=candidate_data,
        )

        return run
