"""Infrastructure adapters for production scheme generation.

Implements SourceBindingReadPort, WeightRevisionReadPort, and
ProductionSchemeRunReadPort using SQLAlchemy ORM.
Repositories MUST NOT commit/rollback/close/create sessions.
"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from cold_storage.modules.orchestration.infrastructure.orm import (
    OrchestrationRunAttemptRecord,
    SourceBindingRecord,
)
from cold_storage.modules.projects.infrastructure.orm import (
    CalculationRunRecord,
)
from cold_storage.modules.schemes.application.production_ports import (
    AttemptSnapshot,
    CalculationRunSnapshot,
    PersistedSchemeRun,
    SchemeCandidateSnapshot,
    SourceBindingSnapshot,
    WeightSetRevisionSnapshot,
)
from cold_storage.modules.schemes.infrastructure.orm import (
    SchemeCandidateRecord,
    SchemeRunRecord,
    SchemeWeightSetRevisionRecord,
)

# ── SourceBindingReadPort adapter ──────────────────────────────────────────


class SqlAlchemySourceBindingReadPort:
    """Read-only adapter for SourceBinding and CalculationRun loading."""

    def load_binding(self, session: Session, /, *, binding_id: str) -> SourceBindingSnapshot | None:
        record = session.execute(
            select(SourceBindingRecord).where(SourceBindingRecord.id == binding_id)
        ).scalar_one_or_none()
        if record is None:
            return None
        return SourceBindingSnapshot(
            id=record.id,
            project_id=record.project_id,
            project_version_id=record.project_version_id,
            execution_snapshot_id=record.execution_snapshot_id,
            coefficient_context_id=record.coefficient_context_id,
            orchestration_identity_id=record.orchestration_identity_id,
            orchestration_run_attempt_id=record.orchestration_run_attempt_id,
            orchestration_fingerprint=record.orchestration_fingerprint,
            zone_calculation_id=record.zone_calculation_id,
            cooling_load_calculation_id=record.cooling_load_calculation_id,
            equipment_calculation_id=record.equipment_calculation_id,
            power_calculation_id=record.power_calculation_id,
            investment_calculation_id=record.investment_calculation_id,
            per_calculation_result_hashes=record.per_calculation_result_hashes or {},
            combined_source_hash=record.combined_source_hash,
            schema_version=record.schema_version,
        )

    def load_calculation_run(
        self, session: Session, /, *, run_id: str
    ) -> CalculationRunSnapshot | None:
        record = session.execute(
            select(CalculationRunRecord).where(CalculationRunRecord.id == run_id)
        ).scalar_one_or_none()
        if record is None:
            return None
        return CalculationRunSnapshot(
            id=record.id,
            project_id=record.project_id,
            project_version_id=record.project_version_id,
            orchestration_identity_id=record.orchestration_identity_id or "",
            orchestration_run_attempt_id=record.orchestration_run_attempt_id or "",
            orchestration_fingerprint=record.orchestration_fingerprint,
            calculator_name=record.calculator_name,
            calculator_version=record.calculator_version,
            calculation_type=record.calculation_type or "",
            result_snapshot=record.result_snapshot or {},
            result_hash=record.result_hash or "",
            schema_version=record.schema_version,
            formulas=record.formulas or [],
            coefficients=record.coefficients or [],
            assumptions=record.assumptions or [],
            warnings=record.warnings or [],
            source_references=record.source_references or [],
            upstream_calculation_ids=cast(
                dict[str, str], (record.provenance or {}).get("upstream_calculation_ids") or {}
            ),
            requires_review=record.requires_review or False,
        )

    def load_attempt(self, session: Session, /, *, attempt_id: str) -> AttemptSnapshot | None:
        record = session.execute(
            select(OrchestrationRunAttemptRecord).where(
                OrchestrationRunAttemptRecord.id == attempt_id
            )
        ).scalar_one_or_none()
        if record is None:
            return None
        return AttemptSnapshot(
            id=record.id,
            identity_id=record.identity_id,
            status=record.status,
            source_binding_id=record.source_binding_id,
        )


# ── WeightRevisionReadPort adapter ────────────────────────────────────────


class SqlAlchemyWeightRevisionReadPort:
    """Read-only adapter for weight-set revision loading."""

    def load_approved_revision(
        self, session: Session, /, *, revision_id: str
    ) -> WeightSetRevisionSnapshot | None:
        record = session.execute(
            select(SchemeWeightSetRevisionRecord).where(
                SchemeWeightSetRevisionRecord.id == revision_id
            )
        ).scalar_one_or_none()
        if record is None:
            return None

        # Parse criteria from content
        from cold_storage.modules.schemes.application.weight_revision_governance import (
            _parse_criteria,
        )

        raw_criteria: list[dict[str, Any]] = record.content.get("criteria", [])  # type: ignore[assignment]
        criteria = _parse_criteria(raw_criteria) if raw_criteria else ()

        return WeightSetRevisionSnapshot(
            id=record.id,
            weight_set_id=record.weight_set_id,
            code=record.code,
            revision=record.revision,
            status=record.status,
            content=record.content or {},
            content_hash=record.content_hash,
            generator_compatibility_version=record.generator_compatibility_version,
            approved_at=record.approved_at,
            approved_by=record.approved_by or "",
            criteria=criteria,
        )


# ── ProductionSchemeRunReadPort adapter ────────────────────────────────────


class SqlAlchemyProductionSchemeRunReadPort:
    """Read-only adapter for loading persisted production scheme runs."""

    def load_production_run(self, session: Session, /, *, run_id: str) -> PersistedSchemeRun | None:
        record = session.execute(
            select(SchemeRunRecord).where(SchemeRunRecord.id == run_id)
        ).scalar_one_or_none()
        if record is None:
            return None

        # Extract profile data from assumption_snapshot
        assumption: dict[str, Any] = dict(record.assumption_snapshot or {})
        raw_codes = assumption.get("profile_codes", ())
        profile_codes: tuple[str, ...] = (
            tuple(raw_codes) if isinstance(raw_codes, (list, tuple)) else ()
        )
        raw_params = assumption.get("profile_parameters", {})
        profile_parameters: dict[str, dict[str, Any]] = (
            dict(raw_params) if isinstance(raw_params, dict) else {}
        )

        # Count candidates and load snapshots
        candidate_records = (
            session.execute(
                select(SchemeCandidateRecord).where(SchemeCandidateRecord.scheme_run_id == run_id)
            )
            .scalars()
            .all()
        )
        candidates_count = len(candidate_records)

        # Load candidates_snapshot from SchemeRunRecord JSON field
        raw_candidates_snapshot = record.candidates_snapshot
        candidates_snapshot: list[dict[str, Any]] = []
        if isinstance(raw_candidates_snapshot, list):
            candidates_snapshot = raw_candidates_snapshot
        elif isinstance(raw_candidates_snapshot, dict):
            candidates_snapshot = [raw_candidates_snapshot]

        # Build score_breakdowns_snapshot from candidate records (original order)
        cand_by_code: dict[str, SchemeCandidateRecord] = {
            c.scheme_code: c for c in candidate_records
        }
        score_breakdowns_snapshot: list[dict[str, Any]] = []
        for cand_dict in candidates_snapshot:
            sc = cand_dict.get("scheme_code", "") if isinstance(cand_dict, dict) else ""
            cand_rec = cand_by_code.get(sc)
            if cand_rec is not None:
                score_breakdowns_snapshot.append(dict(cand_rec.score_breakdown_snapshot))

        return PersistedSchemeRun(
            id=record.id,
            project_id=record.project_id,
            project_version_id=record.project_version_id,
            content_hash=record.content_hash or "",
            source_mode=record.source_mode,
            source_binding_id=record.source_binding_id,
            source_contract_version=record.source_contract_version,
            binding_schema_version=record.binding_schema_version,
            execution_snapshot_id=record.execution_snapshot_id,
            coefficient_context_id=record.coefficient_context_id,
            orchestration_identity_id=record.orchestration_identity_id,
            authoritative_attempt_id=record.authoritative_attempt_id,
            orchestration_fingerprint=record.orchestration_fingerprint,
            zone_calculation_id=record.zone_calculation_id,
            cooling_load_calculation_id=record.cooling_load_calculation_id,
            equipment_calculation_id=record.equipment_calculation_id,
            power_calculation_id=record.power_calculation_id,
            investment_calculation_id=record.investment_calculation_id,
            zone_result_hash=record.zone_result_hash,
            cooling_load_result_hash=record.cooling_load_result_hash,
            equipment_result_hash=record.equipment_result_hash,
            power_result_hash=record.power_result_hash,
            investment_result_hash=record.investment_result_hash,
            combined_source_hash=record.combined_source_hash,
            weight_set_id=record.weight_set_id,
            weight_set_revision_id=record.weight_set_revision_id,
            weight_set_content_hash=record.weight_set_content_hash,
            weight_set_generator_compatibility_version=(
                record.weight_set_generator_compatibility_version
            ),
            generator_version=record.generator_version,
            profile_codes=profile_codes,
            profile_parameters=profile_parameters,
            candidates_count=candidates_count,
            candidates_snapshot=candidates_snapshot,
            score_breakdowns_snapshot=score_breakdowns_snapshot,
            recommended_scheme_code=record.recommended_scheme_code,
        )

    def load_candidates(self, session: Session, /, *, run_id: str) -> list[SchemeCandidateSnapshot]:
        records = (
            session.execute(
                select(SchemeCandidateRecord)
                .where(SchemeCandidateRecord.scheme_run_id == run_id)
                .order_by(SchemeCandidateRecord.scheme_code)
            )
            .scalars()
            .all()
        )

        return [
            SchemeCandidateSnapshot(
                id=rec.id,
                scheme_run_id=rec.scheme_run_id,
                scheme_code=rec.scheme_code,
                profile_code=rec.profile_code,
                feasible=rec.feasible,
                rank=rec.rank,
                total_score=rec.total_score,
                score_breakdown_snapshot=rec.score_breakdown_snapshot or {},
                constraint_results=rec.constraint_results or [],
                result_snapshot=rec.result_snapshot or {},
            )
            for rec in records
        ]
