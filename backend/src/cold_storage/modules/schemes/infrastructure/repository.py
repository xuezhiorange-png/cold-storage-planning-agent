"""Scheme repository — persistence operations."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

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
        from decimal import Decimal

        from cold_storage.modules.schemes.domain.models import WeightCriterion

        criteria = [
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
            criteria=criteria,
            created_at=rec.created_at,
            approved_at=rec.approved_at,
            requires_review=rec.requires_review,
        )

    # ----- Scheme runs -----

    def save_run(self, run: SchemeRun, candidates: list[SchemeCandidate]) -> SchemeRun:
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
        )
        self._session.merge(run_rec)

        for cand in candidates:
            cand_rec = SchemeCandidateRecord(
                id=f"{run.id}-{cand.scheme_code}",
                scheme_run_id=run.id,
                scheme_code=cand.scheme_code,
                profile_code=cand.profile_code,
                feasible=cand.feasible,
                rank=None,
                total_score=None,
                result_snapshot={
                    "total_area_m2": cand.total_area_m2,
                    "total_position_count": cand.total_position_count,
                    "room_module_count": cand.room_module_count,
                    "door_count": cand.door_count,
                    "partition_length_proxy_m": cand.partition_length_proxy_m,
                    "investment_cny": cand.investment_cny,
                    "installed_power_kw_e": cand.installed_power_kw_e,
                    "design_cooling_load_kw_r": cand.design_cooling_load_kw_r,
                    "compressor_installed_capacity_kw_r": cand.compressor_installed_capacity_kw_r,
                    "condenser_heat_rejection_kw": cand.condenser_heat_rejection_kw,
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
                            "area_m2": rm.area_m2,
                            "position_count": rm.position_count,
                            "storage_capacity_kg": rm.storage_capacity_kg,
                        }
                        for rm in cand.room_modules
                    ],
                },
            )
            self._session.merge(cand_rec)

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
        )
