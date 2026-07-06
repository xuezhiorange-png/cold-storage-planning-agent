"""Scheme repository — persistence operations.

Key invariants:
- Completed runs are immutable: ``save_run`` refuses to overwrite a record
  whose ``status == 'completed'``.
- Candidate records persist ``rank``, ``total_score``, ``score_breakdown_snapshot``,
  and ``constraint_results`` for full traceability.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from cold_storage.modules.schemes.domain.errors import CompletedRunImmutabilityError
from cold_storage.modules.schemes.domain.models import (
    SchemeCandidate,
    SchemeRun,
    SchemeWeightSet,
)
from cold_storage.modules.schemes.infrastructure.orm import (
    SchemeCandidateRecord,
    SchemeRunRecord,
    SchemeWeightSetRecord,
)


def _json_safe(val: Any) -> Any:
    """Recursively convert Decimal values to strings for JSON serialization."""
    if isinstance(val, Decimal):
        return str(val)
    if isinstance(val, dict):
        return {k: _json_safe(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_json_safe(item) for item in val]
    return val


class SchemeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ----- Weight sets -----

    def save_weight_set(self, ws: SchemeWeightSet) -> SchemeWeightSet:
        rec = SchemeWeightSetRecord(
            id=ws.id,
            code=ws.code,
            name=ws.name,
            revision=ws.revision,
            status=ws.status,
            source_type=ws.source_type,
            criteria=[
                {
                    "code": c.criterion_code,
                    "weight": str(c.weight),
                    "direction": c.direction,
                    "normalization_method": c.normalization_method,
                    "hard_constraint": c.hard_constraint,
                    "description": c.description,
                }
                for c in ws.criteria
            ],
            requires_review=ws.requires_review,
            approved_at=ws.approved_at,
        )
        self._session.merge(rec)
        self._session.flush()
        return ws

    def get_weight_set(self, ws_id: str) -> SchemeWeightSet | None:
        rec = self._session.get(SchemeWeightSetRecord, ws_id)
        if rec is None:
            return None
        return self._to_weight_set(rec)

    def list_weight_sets(self) -> list[SchemeWeightSet]:
        stmt = select(SchemeWeightSetRecord).order_by(SchemeWeightSetRecord.created_at)
        recs = self._session.execute(stmt).scalars().all()
        return [self._to_weight_set(r) for r in recs]

    def _to_weight_set(self, rec: SchemeWeightSetRecord) -> SchemeWeightSet:
        # Rebuild WeightCriterion list
        from cold_storage.modules.schemes.domain.models import WeightCriterion

        criteria_list = [
            WeightCriterion(
                criterion_code=str(c["code"]),
                weight=Decimal(str(c["weight"])),
                direction=str(c["direction"]),
                normalization_method=str(c.get("normalization_method", "min_max")),
                hard_constraint=bool(c.get("hard_constraint", False)),
                description=str(c.get("description", "")),
            )
            for c in rec.criteria
        ]
        return SchemeWeightSet(
            id=rec.id,
            code=rec.code,
            name=rec.name,
            revision=rec.revision,
            status=rec.status,
            source_type=rec.source_type,
            criteria=criteria_list,
            created_at=rec.created_at,
            approved_at=rec.approved_at,
            requires_review=rec.requires_review,
        )

    # ----- Scheme runs -----

    def save_run(
        self,
        run: SchemeRun,
        candidates: list[SchemeCandidate],
        score_breakdowns: list[Any] | None = None,
        ranks: dict[str, int] | None = None,
    ) -> SchemeRun:
        """Persist a scheme run and its candidates.

        Raises ``CompletedRunImmutabilityError`` if a completed run with the
        same ID already exists.
        """
        existing = self._session.get(SchemeRunRecord, run.id)
        if existing is not None:
            raise CompletedRunImmutabilityError(run.id)

        run_rec = SchemeRunRecord(
            id=run.id,
            project_id=run.project_id,
            project_version_id=run.project_version_id,
            weight_set_id=run.weight_set_id,
            status=run.status,
            generator_version=run.generator_version,
            source_snapshot_hash=run.source_snapshot_hash,
            input_snapshot=run.input_snapshot,
            assumption_snapshot=run.assumption_snapshot,
            comparison_snapshot=run.comparison_snapshot,
            candidates_snapshot=run.candidates_snapshot,
            requires_review=run.requires_review,
            recommended_scheme_code=run.recommended_scheme_code,
            warning_messages=run.warning_messages,
            completed_at=run.completed_at,
            content_hash=run.content_hash,
            database_backend=run.database_backend,
        )
        self._session.add(run_rec)

        # Build lookup for score breakdowns
        sb_map: dict[str, Any] = {}
        if score_breakdowns:
            for sb in score_breakdowns:
                sb_map[sb.scheme_code] = sb

        for cand in candidates:
            sb = sb_map.get(cand.scheme_code)
            rank = (ranks or {}).get(cand.scheme_code)

            # Build score breakdown snapshot
            score_snapshot: dict[str, object] = {}
            if sb is not None:
                score_snapshot = {
                    "scheme_code": sb.scheme_code,
                    "total_score": str(sb.total_score),
                    "diagnostic_only": getattr(sb, "diagnostic_only", False),
                    "criteria": [
                        {
                            "criterion_code": cs.criterion_code,
                            "raw_value": str(cs.raw_value),
                            "unit": cs.unit,
                            "direction": cs.direction,
                            "weight": str(cs.weight),
                            "min_value": str(cs.min_value),
                            "max_value": str(cs.max_value),
                            "normalized_score": str(cs.normalized_score),
                            "weighted_contribution": str(cs.weighted_contribution),
                            "formula": cs.formula,
                        }
                        for cs in sb.criterion_scores
                    ],
                }

            # Build constraint results snapshot
            constraint_snapshot = [
                {
                    "constraint_code": cr.constraint_code,
                    "passed": cr.passed,
                    "detail": cr.detail,
                    "expected": _json_safe(cr.expected),
                    "actual": _json_safe(cr.actual),
                }
                for cr in cand.constraint_results
            ]

            # Build result snapshot
            result_snapshot: dict[str, object] = {
                "total_area_m2": str(cand.total_area_m2),
                "total_position_count": cand.total_position_count,
                "room_module_count": cand.room_module_count,
                "door_count": cand.door_count,
                "partition_length_proxy_m": str(cand.partition_length_proxy_m),
                "investment_cny": str(cand.investment_cny),
                "installed_power_kw_e": str(cand.installed_power_kw_e),
                "design_cooling_load_kw_r": str(cand.design_cooling_load_kw_r),
                "compressor_operating_capacity_kw_r": str(cand.compressor_operating_capacity_kw_r),
                "compressor_installed_capacity_kw_r": str(cand.compressor_installed_capacity_kw_r),
                "compressor_standby_capacity_kw_r": str(cand.compressor_standby_capacity_kw_r),
                "condenser_heat_rejection_kw": str(cand.condenser_heat_rejection_kw),
                "feasible": cand.feasible,
                "requires_review": cand.requires_review,
                "assumptions": cand.assumptions,
                "warnings": cand.warnings,
                "room_modules": [
                    {
                        "room_code": rm.room_code,
                        "room_name": rm.room_name,
                        "zone_codes": rm.zone_codes,
                        "temperature_level": rm.temperature_level,
                        "area_m2": str(rm.area_m2),
                        "position_count": rm.position_count,
                        "storage_capacity_kg": str(rm.storage_capacity_kg),
                        "design_cooling_load_kw_r": str(rm.design_cooling_load_kw_r),
                        "compressor_operating_capacity_kw_r": str(
                            rm.compressor_operating_capacity_kw_r
                        ),
                        "compressor_installed_capacity_kw_r": str(
                            rm.compressor_installed_capacity_kw_r
                        ),
                        "process_compatibility": rm.process_compatibility,
                        "hygiene_zone": rm.hygiene_zone,
                        "door_count": rm.door_count,
                        "partition_length_proxy_m": str(rm.partition_length_proxy_m),
                    }
                    for rm in cand.room_modules
                ],
            }

            cand_rec = SchemeCandidateRecord(
                id=f"{run.id}-{cand.scheme_code}",
                scheme_run_id=run.id,
                scheme_code=cand.scheme_code,
                profile_code=cand.profile_code,
                feasible=cand.feasible,
                rank=rank,
                total_score=sb.total_score if sb else None,
                score_breakdown_snapshot=score_snapshot,
                constraint_results=constraint_snapshot,
                result_snapshot=result_snapshot,
            )
            existing_cand = self._session.get(SchemeCandidateRecord, cand_rec.id)
            if existing_cand is not None:
                raise CompletedRunImmutabilityError(
                    f"Candidate {cand_rec.scheme_code} already exists in run {run.id}"
                )
            self._session.add(cand_rec)

        self._session.flush()
        return run

    def get_run(self, run_id: str) -> SchemeRun | None:
        rec = self._session.get(SchemeRunRecord, run_id)
        if rec is None:
            return None
        return self._to_run(rec)

    def list_runs(self, project_version_id: str) -> list[SchemeRun]:
        stmt = (
            select(SchemeRunRecord)
            .where(SchemeRunRecord.project_version_id == project_version_id)
            .order_by(SchemeRunRecord.created_at)
        )
        recs = self._session.execute(stmt).scalars().all()
        return [self._to_run(r) for r in recs]

    def get_candidates(self, run_id: str) -> list[SchemeCandidateRecord]:
        stmt = (
            select(SchemeCandidateRecord)
            .where(SchemeCandidateRecord.scheme_run_id == run_id)
            .order_by(SchemeCandidateRecord.scheme_code)
        )
        return list(self._session.execute(stmt).scalars().all())

    def get_completed_runs_for_project(self, project_id: str) -> list[SchemeRun]:
        """Return completed runs for a project, newest first."""
        stmt = (
            select(SchemeRunRecord)
            .where(
                SchemeRunRecord.project_id == project_id,
                SchemeRunRecord.status == "completed",
            )
            .order_by(SchemeRunRecord.created_at.desc())
        )
        recs = self._session.execute(stmt).scalars().all()
        return [self._to_run(r) for r in recs]

    def _to_run(self, rec: SchemeRunRecord) -> SchemeRun:
        return SchemeRun(
            id=rec.id,
            project_id=rec.project_id,
            project_version_id=rec.project_version_id,
            weight_set_id=rec.weight_set_id,
            status=rec.status,
            generator_version=rec.generator_version,
            source_snapshot_hash=rec.source_snapshot_hash,
            input_snapshot=rec.input_snapshot,
            assumption_snapshot=rec.assumption_snapshot,
            comparison_snapshot=rec.comparison_snapshot,
            candidates_snapshot=rec.candidates_snapshot,
            requires_review=rec.requires_review,
            created_at=rec.created_at,
            completed_at=rec.completed_at,
            recommended_scheme_code=rec.recommended_scheme_code,
            warning_messages=[str(w) for w in rec.warning_messages],
            content_hash=rec.content_hash,
            # Phase 1 (Task 11B) readback: the column is NOT NULL
            # after 0035+0036, so a missing value indicates a
            # corrupted row. Surface empty and let the kw_only
            # SchemeRun field fail-closed downstream.
            database_backend=rec.database_backend or "",
        )
