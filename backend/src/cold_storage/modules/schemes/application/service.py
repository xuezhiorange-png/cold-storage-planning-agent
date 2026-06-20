"""Scheme application service — orchestrates generation, validation, scoring, persistence.

Trust boundary: the service reads all engineering data from the database.
The client only provides ``profile_codes``, ``weight_set_id``, and
``profile_parameters``.  Zone results, investment, cooling load, and
equipment data are loaded from persisted Task 4 / Task 5 calculation runs.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any

from sqlalchemy.orm import Session

from cold_storage.modules.projects.infrastructure.orm import (
    CalculationRunRecord,
    ProjectRecord,
    ProjectVersionRecord,
)
from cold_storage.modules.schemes.domain.errors import (
    ProjectNotFoundError,
    ProjectVersionNotFoundError,
    SourceCalculationMissingError,
    WeightSetError,
)
from cold_storage.modules.schemes.domain.generator import GENERATOR_VERSION, generate_schemes
from cold_storage.modules.schemes.domain.models import (
    CoolingLoadResult,
    EquipmentResult,
    InvestmentResult,
    SchemeCandidate,
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


def _cast_dict(val: object) -> dict[str, object]:
    """Cast a JSON dict value to the expected type."""
    if isinstance(val, dict):
        return val
    return {}


def _cast_list_dict(val: object) -> list[dict[str, object]]:
    """Cast a JSON list value to the expected type."""
    if isinstance(val, list):
        return val
    return []


# Required calculation types for trust boundary
_REQUIRED_CALC_TYPES = frozenset({"zone", "investment", "cooling_load", "equipment"})


class SchemeService:
    def __init__(self, session: Session) -> None:
        self._repo = SchemeRepository(session)
        self._session = session

    # ------------------------------------------------------------------
    # Internal helpers — DB reads
    # ------------------------------------------------------------------

    def _load_project(self, project_id: str) -> ProjectRecord:
        proj = self._session.get(ProjectRecord, project_id)
        if proj is None:
            raise ProjectNotFoundError(project_id)
        return proj

    def _load_version(self, project_id: str, version_number: int) -> ProjectVersionRecord:
        stmt = self._session.query(ProjectVersionRecord).filter(
            ProjectVersionRecord.project_id == project_id,
            ProjectVersionRecord.version_number == version_number,
        )
        ver = stmt.first()
        if ver is None:
            raise ProjectVersionNotFoundError(project_id, version_number)
        return ver

    def _load_calculation(
        self,
        project_version_id: str,
        calculator_name: str,
    ) -> CalculationRunRecord:
        stmt = (
            self._session.query(CalculationRunRecord)
            .filter(
                CalculationRunRecord.project_version_id == project_version_id,
                CalculationRunRecord.calculator_name == calculator_name,
            )
            .order_by(CalculationRunRecord.created_at.desc())
        )
        rec = stmt.first()
        if rec is None:
            raise SourceCalculationMissingError(calculator_name)
        return rec

    def _load_all_calculations(self, project_version_id: str) -> dict[str, CalculationRunRecord]:
        """Load all calculation runs for a version, keyed by calculator_name."""
        stmt = self._session.query(CalculationRunRecord).filter(
            CalculationRunRecord.project_version_id == project_version_id
        )
        recs = stmt.all()
        result: dict[str, CalculationRunRecord] = {}
        for rec in recs:
            # Keep the latest per calculator_name
            if rec.calculator_name not in result:
                result[rec.calculator_name] = rec
        return result

    def _compute_snapshot_hash(self, calculations: dict[str, CalculationRunRecord]) -> str:
        """Compute a deterministic hash from all persisted calculation result snapshots."""
        parts: list[str] = []
        for name in sorted(calculations.keys()):
            calc = calculations[name]
            result_json = str(sorted(calc.result_snapshot.items())) if calc.result_snapshot else ""
            parts.append(f"{name}={result_json}")
        combined = "|".join(parts)
        return sha256(combined.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_scheme_run(
        self,
        project_id: str,
        version: int,
        profile_codes: list[str],
        weight_set_id: str,
        profile_parameters: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Full scheme generation pipeline.

        The client provides ONLY: profile_codes, weight_set_id, profile_parameters.
        All engineering data is read from the database.
        """

        # 1. Load and validate project + version
        self._load_project(project_id)
        version_record = self._load_version(project_id, version)
        project_version_id = version_record.id

        # 2. Load all required calculations from DB
        calculations = self._load_all_calculations(project_version_id)

        # Verify all required calculation types exist
        for calc_type in _REQUIRED_CALC_TYPES:
            if calc_type not in calculations:
                raise SourceCalculationMissingError(calc_type)

        zone_calc = calculations["zone"]
        invest_calc = calculations["investment"]
        cool_calc = calculations["cooling_load"]
        equip_calc = calculations["equipment"]

        # 3. Parse zone results from persisted snapshot
        zone_snapshots_raw = zone_calc.result_snapshot.get("zone_results", [])
        zone_snapshots = _cast_list_dict(zone_snapshots_raw)
        if not zone_snapshots:
            raise SourceCalculationMissingError("zone_results")

        zone_results = [
            ZoneResult(
                zone_code=str(z["zone_code"]),
                zone_name=str(z["zone_name"]),
                temperature_level=str(z["temperature_level"]),
                area_m2=_to_decimal(z["area_m2"]),
                position_count=int(str(z["position_count"])),
                storage_capacity_kg=_to_decimal(z["storage_capacity_kg"]),
                process_compatibility=str(z.get("process_compatibility", "general")),
                hygiene_zone=str(z.get("hygiene_zone", "standard")),
            )
            for z in zone_snapshots
        ]

        # 4. Parse investment result
        invest_snap = _cast_dict(invest_calc.result_snapshot)
        total_investment = _to_decimal(invest_snap.get("total_investment_cny", 0))
        zone_investments = {
            str(k): _to_decimal(v)
            for k, v in _cast_dict(invest_snap.get("zone_investments", {})).items()
        }
        investment = InvestmentResult(
            total_investment_cny=total_investment,
            zone_investments=zone_investments,
        )

        # 5. Parse cooling load result
        cool_snap = _cast_dict(cool_calc.result_snapshot)
        cooling_load = CoolingLoadResult(
            design_cooling_load_kw_r=_to_decimal(cool_snap.get("design_cooling_load_kw_r", 0)),
            sensible_load_kw_r=_to_decimal(cool_snap.get("sensible_load_kw_r", 0)),
            latent_load_kw_r=_to_decimal(cool_snap.get("latent_load_kw_r", 0)),
            infiltration_load_kw_r=_to_decimal(cool_snap.get("infiltration_load_kw_r", 0)),
        )

        # 6. Parse equipment result
        equip_snap = _cast_dict(equip_calc.result_snapshot)
        operating = _to_decimal(equip_snap.get("compressor_operating_capacity_kw_r", 0))
        installed = _to_decimal(equip_snap.get("compressor_installed_capacity_kw_r", 0))
        standby = installed - operating  # derived: standby = installed - operating
        equipment = EquipmentResult(
            compressor_operating_capacity_kw_r=operating,
            compressor_installed_capacity_kw_r=installed,
            compressor_standby_capacity_kw_r=standby,
            condenser_heat_rejection_kw=_to_decimal(
                equip_snap.get("condenser_heat_rejection_kw", 0)
            ),
            installed_power_kw_e=_to_decimal(equip_snap.get("installed_power_kw_e", 0)),
        )

        # 7. Compute totals from zone results
        total_positions = sum(z.position_count for z in zone_results)
        total_capacity: Decimal = sum((z.storage_capacity_kg for z in zone_results), Decimal("0"))

        # 8. Compute source snapshot hash from DB data (not client-provided)
        source_hash = self._compute_snapshot_hash(calculations)

        # 9. Build source calculation IDs from loaded records
        source_calc_ids = {name: calc.id for name, calc in calculations.items()}
        source_snap_hashes = {
            name: sha256(str(sorted(calc.result_snapshot.items())).encode()).hexdigest()[:16]
            for name, calc in calculations.items()
        }

        # 10. Build generation input
        input_data = SchemeGenerationInput(
            project_id=project_id,
            project_version_id=project_version_id,
            weight_set_id=weight_set_id,
            profile_codes=profile_codes,
            profile_parameters=profile_parameters,
            source_calculation_ids=source_calc_ids,
            source_snapshot_hashes=source_snap_hashes,
            zone_results=zone_results,
            investment_result=investment,
            cooling_load_result=cooling_load,
            equipment_result=equipment,
            generator_version=GENERATOR_VERSION,
            total_daily_throughput_kg_day=_to_decimal(
                zone_calc.result_snapshot.get("total_daily_throughput_kg_day", 0)
            ),
            total_storage_capacity_kg=total_capacity,
            total_position_count=total_positions,
        )

        # 11. Load and validate weight set
        ws = self._repo.get_weight_set(weight_set_id)
        if ws is None:
            raise WeightSetError(f"Weight set '{weight_set_id}' not found")
        validate_weight_set(ws)

        # 12. Generate candidates
        candidates = generate_schemes(input_data)

        # 13. Validate each candidate
        zone_map = {z.zone_code: z for z in zone_results}
        for i, cand in enumerate(candidates):
            constraints = validate_candidate(cand, input_data, zone_map)
            feasible = all(c.passed for c in constraints)
            # Recreate with updated feasible and constraint_results
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
                compressor_operating_capacity_kw_r=cand.compressor_operating_capacity_kw_r,
                compressor_installed_capacity_kw_r=cand.compressor_installed_capacity_kw_r,
                compressor_standby_capacity_kw_r=cand.compressor_standby_capacity_kw_r,
                condenser_heat_rejection_kw=cand.condenser_heat_rejection_kw,
                metrics=cand.metrics,
                assumptions=cand.assumptions,
                warnings=cand.warnings,
                requires_review=cand.requires_review,
            )

        # 14. Score — infeasible candidates get diagnostic_only scores
        score_breakdowns = score_candidates(candidates, ws)

        # 15. Recommend
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

        # 16. Build ranks
        ranks: dict[str, int] = {}
        if feasible_breakdowns:
            sorted_all = sorted(
                feasible_breakdowns,
                key=lambda sb: stable_sort_key(sb, candidates),
            )
            for rank_idx, sb in enumerate(sorted_all, 1):
                ranks[sb.scheme_code] = rank_idx

        # 17. Build comparison snapshot
        comparison_snapshot: dict[str, object] = {
            "recommended_scheme_code": recommended_code,
            "recommended_reason": recommended_reason,
            "candidates": [
                {
                    "scheme_code": c.scheme_code,
                    "rank": ranks.get(c.scheme_code),
                    "total_score": str(
                        next(
                            (
                                sb.total_score
                                for sb in score_breakdowns
                                if sb.scheme_code == c.scheme_code
                            ),
                            None,
                        )
                    ),
                    "feasible": c.feasible,
                    "requires_review": c.requires_review,
                }
                for c in candidates
            ],
            "score_breakdowns": [
                {
                    "scheme_code": sb.scheme_code,
                    "total_score": str(sb.total_score),
                    "diagnostic_only": getattr(sb, "diagnostic_only", False),
                }
                for sb in score_breakdowns
            ],
        }
        if not feasible_breakdowns:
            comparison_snapshot["warnings"] = ["NO_FEASIBLE_SCHEME"]

        # 18. Create run record
        run = SchemeRun(
            project_id=project_id,
            project_version_id=project_version_id,
            weight_set_id=weight_set_id,
            status="completed",
            generator_version=GENERATOR_VERSION,
            source_snapshot_hash=source_hash,
            input_snapshot=_safe_asdict(input_data),
            assumption_snapshot={"profiles": profile_codes, "weight_set_id": weight_set_id},
            comparison_snapshot=comparison_snapshot,
            candidates_snapshot={},
            requires_review=requires_review,
            recommended_scheme_code=recommended_code,
            warning_messages=[],
            completed_at=datetime.now(UTC),
        )

        self._repo.save_run(run, candidates, score_breakdowns=score_breakdowns, ranks=ranks)
        self._session.commit()

        # 19. Build response
        resp: dict[str, Any] = _build_response(
            run,
            candidates,
            score_breakdowns,
            recommended_code,
            recommended_reason,
            requires_review,
            profile_codes,
            source_snap_hashes,
        )
        return resp

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
                    "rank": c.rank,
                    "total_score": str(c.total_score) if c.total_score is not None else None,
                    "result_snapshot": c.result_snapshot,
                    "score_breakdown_snapshot": c.score_breakdown_snapshot,
                    "constraint_results": c.constraint_results,
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


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _to_decimal(val: Any) -> Any:
    """Convert a value to Decimal, handling str/int/float."""
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


def _safe_asdict(obj: Any) -> dict[str, Any]:
    """Convert a dataclass to dict, handling Decimal serialization."""
    if hasattr(obj, "__dataclass_fields__"):
        d = asdict(obj)
        result: dict[str, Any] = _serialize_decimals(d)
    return result
    return {}


def _serialize_decimals(d: Any) -> Any:
    """Recursively convert Decimal values to strings for JSON."""
    if isinstance(d, Decimal):
        return str(d)
    if isinstance(d, dict):
        return {k: _serialize_decimals(v) for k, v in d.items()}
    if isinstance(d, list):
        return [_serialize_decimals(item) for item in d]
    return d


def _build_response(
    run: SchemeRun,
    candidates: list[SchemeCandidate],
    score_breakdowns: list[Any],
    recommended_code: str | None,
    recommended_reason: str | None,
    requires_review: bool,
    profile_codes: list[str],
    source_snap_hashes: dict[str, str],
) -> dict[str, Any]:
    """Build the API response dict."""
    return {
        "run_id": run.id,
        "project_id": run.project_id,
        "project_version_id": run.project_version_id,
        "status": "completed",
        "recommended_scheme_code": recommended_code,
        "schemes": [
            {
                "scheme_code": c.scheme_code,
                "scheme_name": c.scheme_name,
                "profile_code": c.profile_code,
                "feasible": c.feasible,
                "total_area_m2": str(c.total_area_m2),
                "total_position_count": c.total_position_count,
                "room_module_count": c.room_module_count,
                "door_count": c.door_count,
                "investment_cny": str(c.investment_cny),
                "installed_power_kw_e": str(c.installed_power_kw_e),
                "design_cooling_load_kw_r": str(c.design_cooling_load_kw_r),
                "compressor_operating_capacity_kw_r": str(c.compressor_operating_capacity_kw_r),
                "compressor_installed_capacity_kw_r": str(c.compressor_installed_capacity_kw_r),
                "compressor_standby_capacity_kw_r": str(c.compressor_standby_capacity_kw_r),
                "condenser_heat_rejection_kw": str(c.condenser_heat_rejection_kw),
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
            for sb in score_breakdowns
        ],
        "assumptions": {"profiles": profile_codes},
        "source_snapshots": source_snap_hashes,
        "warnings": [],
        "requires_review": requires_review,
    }
