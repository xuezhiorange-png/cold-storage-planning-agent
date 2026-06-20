"""Scheme application service — orchestrates generation, validation, scoring, persistence."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy.orm import Session

from cold_storage.modules.schemes.domain.errors import (
    WeightSetError,
)
from cold_storage.modules.schemes.domain.generator import (
    GENERATOR_VERSION,
    generate_schemes,
)
from cold_storage.modules.schemes.domain.models import (
    CoolingLoadResult,
    EquipmentResult,
    InvestmentResult,
    SchemeCandidate,
    SchemeComparisonResult,
    SchemeGenerationInput,
    SchemeRun,
    ZoneResult,
)
from cold_storage.modules.schemes.domain.scoring import (
    score_candidates,
    stable_sort_key,
    validate_weight_set,
)
from cold_storage.modules.schemes.domain.validation import validate_candidate
from cold_storage.modules.schemes.infrastructure.repository import SchemeRepository


class SchemeService:
    def __init__(self, session: Session) -> None:
        self._repo = SchemeRepository(session)
        self._session = session

    def generate_scheme_run(
        self,
        project_id: str,
        project_version_id: str,
        profile_codes: list[str],
        weight_set_id: str,
        profile_parameters: dict[str, dict[str, Any]],
        source_calculation_ids: dict[str, str],
        source_snapshot_hashes: dict[str, str],
        zone_results_raw: list[dict[str, Any]],
        investment_raw: dict[str, Any],
        cooling_load_raw: dict[str, Any],
        equipment_raw: dict[str, Any],
        total_daily_throughput_kg_day: float,
        total_storage_capacity_kg: float,
        total_position_count: int,
    ) -> dict[str, Any]:
        """Full scheme generation pipeline — generate, validate, score, persist."""

        # 1. Parse source snapshots
        zone_results = [
            ZoneResult(
                zone_code=z["zone_code"],
                zone_name=z["zone_name"],
                temperature_level=z["temperature_level"],
                area_m2=z["area_m2"],
                position_count=z["position_count"],
                storage_capacity_kg=z["storage_capacity_kg"],
                process_compatibility=z.get("process_compatibility", "general"),
                hygiene_zone=z.get("hygiene_zone", "standard"),
            )
            for z in zone_results_raw
        ]
        investment = InvestmentResult(
            total_investment_cny=investment_raw.get("total_investment_cny", 0),
            zone_investments=investment_raw.get("zone_investments", {}),
        )
        cooling_load = CoolingLoadResult(
            design_cooling_load_kw_r=cooling_load_raw.get("design_cooling_load_kw_r", 0),
            sensible_load_kw_r=cooling_load_raw.get("sensible_load_kw_r", 0),
            latent_load_kw_r=cooling_load_raw.get("latent_load_kw_r", 0),
            infiltration_load_kw_r=cooling_load_raw.get("infiltration_load_kw_r", 0),
        )
        equipment = EquipmentResult(
            compressor_operating_capacity_kw_r=equipment_raw.get(
                "compressor_operating_capacity_kw_r", 0
            ),
            compressor_installed_capacity_kw_r=equipment_raw.get(
                "compressor_installed_capacity_kw_r", 0
            ),
            condenser_heat_rejection_kw=equipment_raw.get("condenser_heat_rejection_kw", 0),
            installed_power_kw_e=equipment_raw.get("installed_power_kw_e", 0),
        )

        # 2. Build generation input
        input_data = SchemeGenerationInput(
            project_id=project_id,
            project_version_id=project_version_id,
            weight_set_id=weight_set_id,
            profile_codes=profile_codes,
            profile_parameters=profile_parameters,
            source_calculation_ids=source_calculation_ids,
            source_snapshot_hashes=source_snapshot_hashes,
            zone_results=zone_results,
            investment_result=investment,
            cooling_load_result=cooling_load,
            equipment_result=equipment,
            generator_version=GENERATOR_VERSION,
            total_daily_throughput_kg_day=total_daily_throughput_kg_day,
            total_storage_capacity_kg=total_storage_capacity_kg,
            total_position_count=total_position_count,
        )

        # 3. Load weight set
        ws = self._repo.get_weight_set(weight_set_id)
        if ws is None:
            raise WeightSetError(f"Weight set '{weight_set_id}' not found")
        validate_weight_set(ws)

        # 4. Generate candidates
        candidates = generate_schemes(input_data)

        # 5. Validate each candidate
        zone_map = {z.zone_code: z for z in zone_results}
        for i, cand in enumerate(candidates):
            constraints = validate_candidate(cand, input_data, zone_map)
            feasible = all(c.passed for c in constraints)
            candidates[i] = SchemeCandidate(
                scheme_code=cand.scheme_code,
                scheme_name=cand.scheme_name,
                profile_code=cand.profile_code,
                feasible=feasible,
                constraint_results=constraints,
                room_modules=cand.room_modules,
                zone_assignments=cand.zone_assignments,
                total_area_m2=cand.total_area_m2,
                total_position_count=cand.total_position_count,
                room_module_count=cand.room_module_count,
                door_count=cand.door_count,
                partition_length_proxy_m=cand.partition_length_proxy_m,
                daily_throughput_kg_day=cand.daily_throughput_kg_day,
                investment_cny=cand.investment_cny,
                installed_power_kw_e=cand.installed_power_kw_e,
                design_cooling_load_kw_r=cand.design_cooling_load_kw_r,
                compressor_installed_capacity_kw_r=cand.compressor_installed_capacity_kw_r,
                condenser_heat_rejection_kw=cand.condenser_heat_rejection_kw,
                metrics=cand.metrics,
                assumptions=cand.assumptions,
                warnings=cand.warnings,
                requires_review=cand.requires_review,
            )

        # 6. Score
        score_breakdowns = score_candidates(candidates, ws)

        # 7. Recommend
        feasible_breakdowns = [
            sb
            for sb in score_breakdowns
            if any(c.scheme_code == sb.scheme_code and c.feasible for c in candidates)
        ]
        if feasible_breakdowns:
            sorted_breakdowns = sorted(
                feasible_breakdowns,
                key=lambda sb: stable_sort_key(sb, candidates),
            )
            recommended_code = sorted_breakdowns[0].scheme_code
            recommended_reason = f"Highest score ({sorted_breakdowns[0].total_score})"
            requires_review = any(c.requires_review for c in candidates)
        else:
            recommended_code = None
            recommended_reason = "NO_FEASIBLE_SCHEME"
            requires_review = True

        # 8. Build comparison (kept for reference)
        _comparison = SchemeComparisonResult(
            candidates=candidates,
            score_breakdowns=score_breakdowns,
            recommended_scheme_code=recommended_code,
            recommended_reason=recommended_reason,
            requires_review=requires_review,
        )

        # 9. Proceed to create run record

        # 10. Create run record
        source_hash = sha256(str(sorted(source_snapshot_hashes.items())).encode()).hexdigest()[:16]

        run = SchemeRun(
            project_id=project_id,
            project_version_id=project_version_id,
            weight_set_id=weight_set_id,
            status="completed",
            generator_version=GENERATOR_VERSION,
            source_snapshot_hash=source_hash,
            input_snapshot=asdict(input_data)
            if hasattr(input_data, "__dataclass_fields__")
            else {},
            assumption_snapshot={"profiles": profile_codes, "weight_set_id": weight_set_id},
            comparison_snapshot={
                "recommended_scheme_code": recommended_code,
                "recommended_reason": recommended_reason,
                "score_breakdowns": [
                    {"scheme_code": sb.scheme_code, "total_score": str(sb.total_score)}
                    for sb in score_breakdowns
                ],
            },
            candidates_snapshot={},
            requires_review=requires_review,
            recommended_scheme_code=recommended_code,
            warning_messages=[],
            completed_at=datetime.now(UTC),
        )

        self._repo.save_run(run, candidates)
        self._session.commit()

        # 11. Build response
        return {
            "run_id": run.id,
            "project_id": project_id,
            "project_version_id": project_version_id,
            "status": "completed",
            "recommended_scheme_code": recommended_code,
            "schemes": [
                {
                    "scheme_code": c.scheme_code,
                    "scheme_name": c.scheme_name,
                    "profile_code": c.profile_code,
                    "feasible": c.feasible,
                    "total_area_m2": c.total_area_m2,
                    "total_position_count": c.total_position_count,
                    "room_module_count": c.room_module_count,
                    "door_count": c.door_count,
                    "investment_cny": c.investment_cny,
                    "installed_power_kw_e": c.installed_power_kw_e,
                    "design_cooling_load_kw_r": c.design_cooling_load_kw_r,
                    "compressor_installed_capacity_kw_r": c.compressor_installed_capacity_kw_r,
                    "condenser_heat_rejection_kw": c.condenser_heat_rejection_kw,
                    "requires_review": c.requires_review,
                    "constraint_results": [
                        {"code": cr.constraint_code, "passed": cr.passed, "detail": cr.detail}
                        for cr in c.constraint_results
                    ],
                    "assumptions": c.assumptions,
                    "warnings": c.warnings,
                }
                for c in candidates
            ],
            "score_breakdowns": [
                {
                    "scheme_code": sb.scheme_code,
                    "total_score": str(sb.total_score),
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
                for sb in score_breakdowns
            ],
            "assumptions": {"profiles": profile_codes},
            "source_snapshots": source_snapshot_hashes,
            "warnings": [],
            "requires_review": requires_review,
        }

    def get_scheme_run(self, run_id: str) -> dict[str, Any] | None:
        run = self._repo.get_run(run_id)
        if run is None:
            return None
        candidates = self._repo.get_candidates(run_id)
        return {
            "run_id": run.id,
            "project_id": run.project_id,
            "project_version_id": run.project_version_id,
            "status": run.status,
            "recommended_scheme_code": run.recommended_scheme_code,
            "requires_review": run.requires_review,
            "candidates": [
                {
                    "scheme_code": c.scheme_code,
                    "feasible": c.feasible,
                    "result_snapshot": c.result_snapshot,
                }
                for c in candidates
            ],
        }

    def list_scheme_runs(self, project_version_id: str) -> list[dict[str, Any]]:
        runs = self._repo.list_runs(project_version_id)
        return [
            {
                "run_id": r.id,
                "status": r.status,
                "recommended_scheme_code": r.recommended_scheme_code,
                "created_at": r.created_at.isoformat(),
                "requires_review": r.requires_review,
            }
            for r in runs
        ]

    def get_comparison(self, run_id: str) -> dict[str, Any] | None:
        run = self._repo.get_run(run_id)
        if run is None:
            return None
        return {
            "run_id": run.id,
            "comparison_snapshot": run.comparison_snapshot,
        }
