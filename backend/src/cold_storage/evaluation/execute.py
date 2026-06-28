"""Per-scenario production workflow orchestration.

Runs each manifest scenario through real production services and produces
a ScenarioExecutionResult with raw output and normalized stage ledger.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from cold_storage.evaluation.models import EvaluationScenario
from cold_storage.evaluation.sqlite_scope import SqliteScope
from cold_storage.modules.calculations.application.service import (
    CoreCalculationService,
)
from cold_storage.modules.calculations.domain.cooling_load import (
    CoefficientSet,
    CoolingLoadCalcInput,
    ZoneCoolingLoadInput,
    calculate_cooling_load,
)
from cold_storage.modules.calculations.domain.equipment import (
    EquipmentCapabilityCalcInput,
    EquipmentCoefficientSet,
    TemperatureSystemInput,
    ZoneEquipmentInput,
    calculate_equipment_capability,
)
from cold_storage.modules.calculations.domain.inventory import (
    InventoryCalcInput,
)
from cold_storage.modules.calculations.domain.investment import (
    InvestmentEstimateInput,
    InvestmentEstimator,
)
from cold_storage.modules.calculations.domain.pallets import (
    PalletCalcInput,
)
from cold_storage.modules.calculations.domain.power import (
    InstalledPowerCalcInput,
    calculate_installed_power,
)
from cold_storage.modules.calculations.domain.precooling import (
    PrecoolingCalcInput,
)
from cold_storage.modules.calculations.domain.throughput import (
    ThroughputCalcInput,
)
from cold_storage.modules.calculations.domain.zone_planning import (
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
)
from cold_storage.modules.projects.infrastructure.database import (
    DatabaseProjectService,
)
from cold_storage.modules.projects.infrastructure.orm import (
    CalculationRunRecord,
    ProjectVersionRecord,
)

# ---------------------------------------------------------------------------
# ScenarioExecutionResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ScenarioExecutionResult:
    """Complete result of running one evaluation scenario.

    raw_output: Full production service output including correlation_id,
        input_snapshot, calculated_at — untouched by normalization.
    outcome: success | review_required | blocked | validation_error
    stage_ledger: dict mapping stage name → {status, review_required, ...}
    """

    raw_output: dict[str, Any]
    outcome: str
    stage_ledger: dict[str, dict[str, Any]]
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage-ledger entry builder
# ---------------------------------------------------------------------------


def _stage_entry(
    status: str,
    *,
    review_required: bool = False,
    detail: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {"status": status, "review_required": review_required}
    if detail:
        entry["detail"] = detail
    if error:
        entry["error"] = error
    return entry


# ---------------------------------------------------------------------------
# Decimal helper
# ---------------------------------------------------------------------------


def _to_decimal(value: object) -> Any:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return Decimal(str(int(value)))
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str) and value.strip():
        return Decimal(value)
    return Decimal("0")


# ---------------------------------------------------------------------------
# JSON-safe conversion helpers
# ---------------------------------------------------------------------------


def _json_safe(obj: Any) -> Any:
    """Convert an object to a JSON-safe primitive."""
    from datetime import datetime as dt
    from decimal import Decimal as D

    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, D):
        return str(obj)
    if isinstance(obj, dt):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if hasattr(obj, "__dict__"):
        return _json_safe(obj.__dict__)
    return str(obj)


# ---------------------------------------------------------------------------
# Helper: temperature_band → temperature_level mapping for SchemeService
# ---------------------------------------------------------------------------


def _map_temperature_level(temperature_band: str, zone_code: str) -> str:
    """Map zone_plan temperature_band to SchemeService-compatible temperature_level."""
    t = str(temperature_band).strip()
    if t == "-18℃" or t == "-25℃":
        return "frozen"
    if "precooling" in str(zone_code).lower():
        return "precooling"
    if t in ("8~10℃", "1~3℃", "0~5℃"):
        return "medium_temperature"
    if t == "常温":
        return "ambient"
    return "medium_temperature"


def _map_process_compatibility(zone_code: str, function: str) -> str:
    """Derive process_compatibility from zone function."""
    f = str(function).lower()
    c = str(zone_code).lower()
    if "precooling" in c or "precooling" in f or "预冷" in function:
        return "raw"
    if "raw" in c or "原果" in function or "暂存" in function:
        return "raw"
    if "frozen" in c or "冻果" in function or "冷冻" in function:
        return "finished"
    if any(kw in f for kw in ("finished", "storage", "成品", "冷藏", "cold room")):
        return "finished"
    return "general"


# ---------------------------------------------------------------------------
# Helper: persist a CalculationRunRecord
# ---------------------------------------------------------------------------


def _persist_calculation(
    *,
    session: Any,
    project_id: str,
    version_number: int,
    calculator_name: str,
    calculator_version: str,
    input_snapshot: dict[str, Any],
    result_snapshot: dict[str, Any],
    formulas: list[dict[str, Any]],
    coefficients: list[dict[str, Any]],
    assumptions: list[str],
    warnings: list[dict[str, Any]],
    source_references: list[dict[str, Any]],
    requires_review: bool,
) -> CalculationRunRecord:
    """Create and persist a CalculationRunRecord."""
    version_record = (
        session.query(ProjectVersionRecord)
        .filter_by(
            project_id=project_id,
            version_number=version_number,
        )
        .first()
    )
    if version_record is None:
        raise ValueError(
            f"ProjectVersionRecord not found for project={project_id} version={version_number}"
        )

    record = CalculationRunRecord(
        id=str(uuid4()),
        project_id=project_id,
        project_version_id=version_record.id,
        calculator_name=calculator_name,
        calculator_version=calculator_version,
        input_snapshot=input_snapshot,
        result_snapshot=result_snapshot,
        formulas=formulas,
        coefficients=coefficients,
        assumptions=assumptions,
        warnings=warnings,
        source_references=source_references,
        requires_review=requires_review,
        created_at=datetime.now(UTC),
    )
    session.add(record)
    session.commit()
    return record


# ---------------------------------------------------------------------------
# Cooling load coefficient defaults (demo)
# ---------------------------------------------------------------------------

DEMO_COOLING_COEFFICIENTS: dict[str, Any] = {
    "wall_u_value": "0.35",
    "roof_u_value": "0.30",
    "floor_u_value": "0.40",
    "product_specific_heat": "3.60",
    "respiration_heat": "0.05",
    "air_change_rate": "0.5",
    "worker_heat_gain": "120",
    "design_margin_ratio": "1.15",
    "diversity_factor": "0.85",
    "motor_efficiency": "0.90",
}

# ---------------------------------------------------------------------------
# Equipment coefficient defaults (demo)
# ---------------------------------------------------------------------------

DEMO_EQUIPMENT_COEFFICIENTS = EquipmentCoefficientSet(
    redundancy_ratio=Decimal("1.20"),
    evaporator_capacity_margin=Decimal("1.15"),
    condenser_capacity_margin=Decimal("1.10"),
    compressor_cop=Decimal("3.5"),
)

# ---------------------------------------------------------------------------
# Scenario executor
# ---------------------------------------------------------------------------


def run_evaluation_scenario(
    scenario: EvaluationScenario,
    fixture: dict[str, Any],
    scope: SqliteScope,
) -> ScenarioExecutionResult:
    """Run a single evaluation scenario through production services.

    Returns a ScenarioExecutionResult with:
      - raw_output: complete production service output (no fields removed)
      - outcome: success | review_required | blocked | validation_error
      - stage_ledger: dict mapping stage name → status/review_required
      - errors: list of error strings
    """
    engine = scope.engine
    Session = scope.Session

    errors: list[str] = []
    stage_ledger: dict[str, dict[str, Any]] = {}

    result: dict[str, Any] = {
        "scenario_id": scenario.scenario_id,
        "fixture_revision": fixture.get("fixture_revision", 1),
        "outcome": "success",
        "stage_ledger": stage_ledger,
        "project": {},
        "version": {},
        "validation_result": {},
        "calculation_results": {},
        "errors": errors,
    }

    try:
        project_svc = DatabaseProjectService(engine)

        # ------------------------------------------------------------------
        # Stage: project
        # ------------------------------------------------------------------
        project_data = fixture.get("project", {})
        try:
            project = project_svc.create_project(
                name=project_data.get("name", "Synthetic Project"),
                location=project_data.get("location", ""),
                product_category=project_data.get("product_category", "blueberry"),
            )
            stage_ledger["project"] = _stage_entry("passed")
            result["project"] = {
                "id": project.id,
                "code": project.code,
                "name": project.name,
                "location": project.location,
                "product_category": project.product_category,
            }
        except Exception as exc:
            stage_ledger["project"] = _stage_entry("failed", error=str(exc))
            errors.append(f"project: {exc}")
            result["outcome"] = "blocked"
            return ScenarioExecutionResult(
                raw_output=result,
                outcome="blocked",
                stage_ledger=stage_ledger,
                errors=errors,
            )

        # ------------------------------------------------------------------
        # Stage: version
        # ------------------------------------------------------------------
        version_data = fixture.get("version", {})
        try:
            version = project_svc.create_version(
                project_id=project.id,
                change_summary=version_data.get("change_summary", "Evaluation run"),
                created_by=version_data.get("created_by", "evaluation-system"),
            )
            stage_ledger["version"] = _stage_entry("passed")
            result["version"] = {
                "id": version.id,
                "version_number": version.version_number,
                "status": version.status,
                "change_summary": version.change_summary,
            }
        except Exception as exc:
            stage_ledger["version"] = _stage_entry("failed", error=str(exc))
            errors.append(f"version: {exc}")
            result["outcome"] = "blocked"
            return ScenarioExecutionResult(
                raw_output=result,
                outcome="blocked",
                stage_ledger=stage_ledger,
                errors=errors,
            )

        # ------------------------------------------------------------------
        # Stage: validation
        # ------------------------------------------------------------------
        inputs_raw = fixture.get("inputs", {})
        project_svc.save_inputs(project.id, version.version_number, inputs_raw, "evaluation-system")

        validation = project_svc.validate_inputs(inputs_raw)
        is_valid = validation.get("valid", True)
        result["validation_result"] = {
            "valid": is_valid,
            "missing_fields": validation.get("missing_fields", []),
            "tentative_fields": validation.get("tentative_fields", []),
        }

        if not is_valid:
            stage_ledger["validation"] = _stage_entry("passed", detail="validation_error")
            result["outcome"] = "validation_error"
            return ScenarioExecutionResult(
                raw_output=result,
                outcome="validation_error",
                stage_ledger=stage_ledger,
                errors=errors,
            )
        else:
            stage_ledger["validation"] = _stage_entry("passed", detail="valid")

        # ------------------------------------------------------------------
        # Stage: planning (core calculations)
        # ------------------------------------------------------------------
        if "planning" in scenario.required_stages:
            try:
                calc_svc = CoreCalculationService()
                tp_input = ThroughputCalcInput(
                    peak_output_kg_per_day=_to_decimal(inputs_raw.get("daily_inbound_mass_kg", 0)),
                    processing_hours_per_day=_to_decimal(
                        inputs_raw.get("working_time_h_per_day", 16)
                    ),
                    shift_count=int(inputs_raw.get("shift_count", 1)),
                    effective_working_ratio=_to_decimal(
                        inputs_raw.get(
                            "effective_working_ratio", inputs_raw.get("utilization_factor", "0.95")
                        )
                    ),
                )
                inv_input = InventoryCalcInput(
                    daily_inbound_quantity=_to_decimal(
                        inputs_raw.get(
                            "daily_inbound_mass_kg", inputs_raw.get("daily_inbound_quantity", 0)
                        )
                    ),
                    daily_outbound_quantity=_to_decimal(
                        inputs_raw.get(
                            "daily_outbound_quantity", inputs_raw.get("daily_inbound_mass_kg", 0)
                        )
                    ),
                    turnover_days=_to_decimal(
                        inputs_raw.get("finished_storage_days", inputs_raw.get("turnover_days", 7))
                    ),
                    safety_stock_days=_to_decimal(inputs_raw.get("safety_stock_days", 0)),
                    storage_ratio=_to_decimal(inputs_raw.get("storage_ratio", 1.0)),
                    inventory_peak_factor=_to_decimal(inputs_raw.get("inventory_peak_factor", 1.0)),
                )
                pallet_input = PalletCalcInput(
                    design_inventory=_to_decimal(inputs_raw.get("design_inventory", 200000)),
                    net_product_per_pallet=_to_decimal(
                        inputs_raw.get("net_product_per_pallet", 1000)
                    ),
                )
                precool_input = PrecoolingCalcInput(
                    precooled_quantity_per_day=_to_decimal(
                        inputs_raw.get("daily_inbound_mass_kg", 0)
                    ),
                )
                power_input = InstalledPowerCalcInput(
                    compressor_input_power_kw_e=_to_decimal(
                        fixture.get("installed_power_input", {}).get(
                            "compressor_input_power_kw_e", 0
                        )
                    ),
                    processing_equipment_power_kw_e=_to_decimal(
                        fixture.get("installed_power_input", {}).get(
                            "processing_equipment_power_kw_e", 0
                        )
                    ),
                )

                orchestration_result = calc_svc.orchestrate_core_calculation(
                    throughput_input=tp_input,
                    inventory_input=inv_input,
                    pallet_input=pallet_input,
                    precooling_input=precool_input,
                    installed_power_input=power_input,
                )

                calc_results: dict[str, Any] = {
                    "success": orchestration_result.success,
                }
                stage_review = False
                for calc_name in [
                    "throughput",
                    "inventory",
                    "pallets",
                    "precooling",
                    "installed_power",
                ]:
                    calc_obj = getattr(orchestration_result, calc_name, None)
                    if calc_obj is not None:
                        obj_dict = asdict(calc_obj)
                        calced_at = obj_dict.get("calculated_at", datetime.now(UTC))
                        obj_dict["calculated_at"] = (
                            calced_at.isoformat()
                            if hasattr(calced_at, "isoformat")
                            else str(calced_at)
                        )
                        # Preserve ALL fields including correlation_id and input_snapshot
                        # for raw output.  Normalization handles exclusions later.
                        calc_results[calc_name] = _json_safe(obj_dict)
                        if getattr(calc_obj, "requires_review", False):
                            stage_review = True

                result["calculation_results"] = calc_results
                stage_ledger["planning"] = _stage_entry(
                    "passed" if orchestration_result.success else "failed",
                    review_required=stage_review,
                    detail="core_calculations_complete",
                )

                if not orchestration_result.success:
                    result.setdefault("outcome", "blocked")
            except Exception as exc:
                errors.append(f"planning: {exc}")
                stage_ledger["planning"] = _stage_entry("failed", error=str(exc))
                result["outcome"] = "blocked"

        # ------------------------------------------------------------------
        # Stage: zone_plan (ColdRoomZonePlanner)
        # ------------------------------------------------------------------
        zone_result = None  # scoped for downstream stages
        if "zone_plan" in scenario.required_stages:
            try:
                zone_planner = ColdRoomZonePlanner()
                zone_plan_input = ColdRoomZonePlanInput(
                    daily_inbound_mass_kg=float(inputs_raw.get("daily_inbound_mass_kg", 10000)),
                    working_time_h_per_day=float(inputs_raw.get("working_time_h_per_day", 16)),
                    finished_storage_days=float(
                        inputs_raw.get("finished_storage_days", inputs_raw.get("storage_days", 2.5))
                    ),
                    packaging_storage_days=float(inputs_raw.get("packaging_storage_days", 3)),
                    precooling_required_ratio=float(
                        inputs_raw.get("precooling_required_ratio", 0.8)
                    ),
                    raw_holding_hours=float(inputs_raw.get("raw_holding_hours", 6.6666666667)),
                    storage_position_capacity_kg=float(
                        inputs_raw.get("storage_position_capacity_kg", 400)
                    ),
                    secondary_fruit_ratio=float(inputs_raw.get("secondary_fruit_ratio", 0.08)),
                    frozen_fruit_ratio=float(inputs_raw.get("frozen_fruit_ratio", 0.10)),
                    frozen_storage_days=float(inputs_raw.get("frozen_storage_days", 5)),
                    precooling_position_daily_capacity_kg=float(
                        inputs_raw.get("precooling_position_daily_capacity_kg", 1250)
                    ),
                    primary_precooling_pallet_weight_kg=float(
                        inputs_raw.get("primary_precooling_pallet_weight_kg", 220)
                    ),
                    primary_precooling_hours_per_pallet=float(
                        inputs_raw.get("primary_precooling_hours_per_pallet", 1)
                    ),
                    primary_precooling_working_hours_per_day=float(
                        inputs_raw.get("primary_precooling_working_hours_per_day", 6)
                    ),
                    secondary_precooling_pallet_weight_kg=float(
                        inputs_raw.get("secondary_precooling_pallet_weight_kg", 400)
                    ),
                    secondary_precooling_hours_per_pallet=float(
                        inputs_raw.get("secondary_precooling_hours_per_pallet", 2)
                    ),
                    secondary_precooling_working_hours_per_day=float(
                        inputs_raw.get("secondary_precooling_working_hours_per_day", 16)
                    ),
                    raw_storage_ratio=float(inputs_raw.get("raw_storage_ratio", 0.40)),
                    raw_fruit_pallet_weight_kg=float(
                        inputs_raw.get("raw_fruit_pallet_weight_kg", 220)
                    ),
                    finished_goods_pallet_weight_kg=float(
                        inputs_raw.get("finished_goods_pallet_weight_kg", 400)
                    ),
                    frozen_goods_pallet_weight_kg=float(
                        inputs_raw.get("frozen_goods_pallet_weight_kg", 600)
                    ),
                    secondary_fruit_area_ratio=float(
                        inputs_raw.get("secondary_fruit_area_ratio", 0.80)
                    ),
                )
                zone_result = zone_planner.plan(zone_plan_input)

                result["zone_plan"] = _json_safe(asdict(zone_result))
                stage_ledger["zone_plan"] = _stage_entry(
                    "passed" if zone_result.success else "failed",
                    review_required=zone_result.requires_review,
                    detail="zone_plan_complete",
                )

                # Persist zone result as CalculationRunRecord for SchemeService
                if zone_result.success:
                    try:
                        zones_raw = zone_result.result.get("zones", [])
                        zone_results_for_scheme = []
                        for z in zones_raw:
                            zc = str(z.get("zone_code", ""))
                            zn = str(z.get("zone_name", "Unknown"))
                            tb = str(z.get("temperature_band", ""))
                            zfunc = str(z.get("function", ""))
                            zone_results_for_scheme.append(
                                {
                                    "zone_code": zc,
                                    "zone_name": zn,
                                    "temperature_level": _map_temperature_level(tb, zc),
                                    "area_m2": float(z.get("required_area_m2", 0)),
                                    "position_count": int(z.get("position_count", 0)),
                                    "storage_capacity_kg": float(
                                        z.get("design_storage_mass_kg", 0)
                                    ),
                                    "process_compatibility": _map_process_compatibility(zc, zfunc),
                                    "hygiene_zone": "standard",
                                }
                            )

                        zone_result_snapshot: dict[str, Any] = {
                            "zone_results": zone_results_for_scheme,
                            "total_daily_throughput_kg_day": float(
                                zone_result.result.get("daily_inbound_mass_kg", 0)
                            ),
                        }

                        with Session() as session:
                            _persist_calculation(
                                session=session,
                                project_id=project.id,
                                version_number=version.version_number,
                                calculator_name="zone",
                                calculator_version=zone_result.calculator_version,
                                input_snapshot=asdict(zone_plan_input),
                                result_snapshot=zone_result_snapshot,
                                formulas=[asdict(f) for f in zone_result.formula_references],
                                coefficients=zone_result.coefficients,
                                assumptions=zone_result.assumptions,
                                warnings=[asdict(w) for w in zone_result.warnings],
                                source_references=zone_result.source_references,
                                requires_review=zone_result.requires_review,
                            )
                    except Exception as exc:
                        errors.append(f"zone_persist: {exc}")

            except Exception as exc:
                errors.append(f"zone_plan: {exc}")
                stage_ledger["zone_plan"] = _stage_entry("failed", error=str(exc))
                result["outcome"] = "blocked"

        # ------------------------------------------------------------------
        # Stage: power (installed power calculator)
        # ------------------------------------------------------------------
        power_result = None  # scoped for downstream stages
        if "power" in scenario.required_stages:
            try:
                power_input = InstalledPowerCalcInput(
                    compressor_input_power_kw_e=_to_decimal(
                        fixture.get("installed_power_input", {}).get(
                            "compressor_input_power_kw_e", 0
                        )
                    ),
                    processing_equipment_power_kw_e=_to_decimal(
                        fixture.get("installed_power_input", {}).get(
                            "processing_equipment_power_kw_e", 0
                        )
                    ),
                )
                power_result = calculate_installed_power(power_input)
                result["power"] = _json_safe(power_result.to_dict())
                stage_ledger["power"] = _stage_entry(
                    "passed" if power_result.success else "failed",
                    review_required=power_result.requires_review,
                    detail="power_configuration_complete",
                )
            except Exception as exc:
                errors.append(f"power: {exc}")
                stage_ledger["power"] = _stage_entry("failed", error=str(exc))
                result["outcome"] = "blocked"

        # ------------------------------------------------------------------
        # Stage: cooling_load (persisted for SchemeService, not an eval stage)
        # ------------------------------------------------------------------
        cooling_load_result = None
        if (
            "zone_plan" in stage_ledger
            and stage_ledger["zone_plan"]["status"] == "passed"
            and zone_result is not None
            and zone_result.success
        ):
            try:
                zones = zone_result.result.get("zones", [])
                if zones:
                    # Build TemperatureLevel mapping
                    from cold_storage.modules.calculations.domain.cooling_load import (
                        TemperatureLevel as TL,
                    )

                    temp_map = {
                        "-18℃": TL.LOW_TEMPERATURE,
                        "0~4℃": TL.MEDIUM_TEMPERATURE,
                        "0~5℃": TL.MEDIUM_TEMPERATURE,
                    }

                    cl_zones: list[ZoneCoolingLoadInput] = []
                    for z in zones:
                        zc = str(z.get("zone_code", "Z1"))
                        zn = str(z.get("zone_name", "Unknown"))
                        tb = str(z.get("temperature_band", ""))
                        if tb == "常温":
                            continue
                        area = Decimal(str(z.get("required_area_m2", 100)))
                        tl = temp_map.get(tb, TL.MEDIUM_TEMPERATURE)

                        cl_zones.append(
                            ZoneCoolingLoadInput(
                                zone_code=zc,
                                zone_name=zn,
                                temperature_level=tl,
                                zone_area=area,
                                room_height=Decimal("6.0"),
                                wall_area=area * Decimal("1.5"),
                                roof_area=area,
                                floor_area=area,
                                u_value_wall=Decimal("0.35"),
                                u_value_roof=Decimal("0.30"),
                                u_value_floor=Decimal("0.40"),
                                outdoor_design_temperature=Decimal("35.0"),
                                room_design_temperature=(
                                    Decimal("-18.0") if tb == "-18℃" else Decimal("0.0")
                                ),
                                operating_hours_per_day=Decimal(
                                    str(inputs_raw.get("working_time_h_per_day", 16))
                                ),
                                product_mass_per_day=Decimal("0"),
                                product_entry_temperature=Decimal("20.0"),
                                product_target_temperature=Decimal("0.0"),
                                cooling_duration=Decimal("8.0"),
                                packaging_mass=Decimal("0"),
                                worker_count=0,
                                worker_heat_gain=Decimal("120"),
                                lighting_power=Decimal("0"),
                                equipment_power=Decimal("0"),
                                fan_motor_power=Decimal("0"),
                                motor_efficiency=Decimal("0.90"),
                            )
                        )

                    cs = CoefficientSet(
                        wall_u_value=Decimal("0.35"),
                        roof_u_value=Decimal("0.30"),
                        floor_u_value=Decimal("0.40"),
                        product_specific_heat=Decimal("3.60"),
                        respiration_heat=Decimal("0.05"),
                        air_change_rate=Decimal("0.5"),
                        worker_heat_gain=Decimal("120"),
                        design_margin_ratio=Decimal("1.15"),
                        diversity_factor=Decimal("0.85"),
                        motor_efficiency=Decimal("0.90"),
                    )

                    cl_input = CoolingLoadCalcInput(zones=cl_zones, coefficients=cs)
                    cooling_load_result = calculate_cooling_load(cl_input)

                    # Compute derived values for SchemeService
                    zone_list = cooling_load_result.result.get("zones", [])
                    sensible_total = 0.0
                    latent_total = 0.0
                    infiltration_total = 0.0
                    for zr in zone_list:
                        sensible_total += float(
                            zr.get("transmission_load_kw_r", 0)
                            + zr.get("product_load_kw_r", 0)
                            + zr.get("sensible_infiltration_load_kw_r", 0)
                            + zr.get("internal_load_kw_r", 0)
                            + zr.get("defrost_load_kw_r", 0)
                        )
                        latent_total += float(zr.get("latent_infiltration_load_kw_r", 0))
                        infiltration_total += float(zr.get("infiltration_load_kw_r", 0))

                    cooling_result_snapshot: dict[str, Any] = {
                        "design_cooling_load_kw_r": float(
                            cooling_load_result.result.get("design_refrigeration_load_kw_r", 0)
                        ),
                        "sensible_load_kw_r": sensible_total,
                        "latent_load_kw_r": latent_total,
                        "infiltration_load_kw_r": infiltration_total,
                    }

                    # Persist as CalculationRunRecord
                    with Session() as session:
                        _persist_calculation(
                            session=session,
                            project_id=project.id,
                            version_number=version.version_number,
                            calculator_name="cooling_load",
                            calculator_version=cooling_load_result.calculator_version,
                            input_snapshot=cooling_load_result.input_snapshot,
                            result_snapshot=cooling_result_snapshot,
                            formulas=[s.to_dict() for s in cooling_load_result.steps],
                            coefficients=[
                                c.to_dict() for c in cooling_load_result.coefficient_references
                            ],
                            assumptions=cooling_load_result.assumptions,
                            warnings=[w.to_dict() for w in cooling_load_result.warnings],
                            source_references=[],
                            requires_review=cooling_load_result.requires_review,
                        )
                else:
                    errors.append("cooling_load: no zones from zone_plan")
            except Exception as exc:
                errors.append(f"cooling_load: {exc}")

        # ------------------------------------------------------------------
        # Stage: equipment (persisted for SchemeService, not an eval stage)
        # ------------------------------------------------------------------
        equipment_result = None
        if cooling_load_result is not None and cooling_load_result.success:
            try:
                # Group zone cooling load results into temperature systems
                cl_zones_raw: Any = cooling_load_result.result.get("zones", [])
                level_groups: dict[str, list[dict[str, Any]]] = {}
                for zr in cl_zones_raw:
                    tl_str: str = str(zr.get("temperature_level", "medium_temperature"))
                    level_groups.setdefault(tl_str, []).append(zr)

                systems: list[TemperatureSystemInput] = []
                for level_code, level_zones in level_groups.items():
                    zone_inputs: list[ZoneEquipmentInput] = []
                    for zr in level_zones:
                        design_load = Decimal(str(zr.get("subtotal_load_kw_r", 0)))
                        zone_inputs.append(
                            ZoneEquipmentInput(
                                zone_code=str(zr.get("zone_code", "")),
                                zone_name=str(zr.get("zone_name", "")),
                                design_cooling_load_kw_r=design_load,
                                evaporator_count=1,
                                evaporation_temperature_c=(
                                    Decimal("-25")
                                    if level_code == "low_temperature"
                                    else Decimal("-10")
                                ),
                                defrost_method=(
                                    "hot_gas" if level_code == "low_temperature" else "off_cycle"
                                ),
                            )
                        )

                    systems.append(
                        TemperatureSystemInput(
                            system_code=f"sys-{level_code}",
                            system_name=f"{level_code.replace('_', ' ').title()} System",
                            design_evaporating_temperature=(
                                Decimal("-25")
                                if level_code == "low_temperature"
                                else Decimal("-10")
                            ),
                            zones=zone_inputs,
                        )
                    )

                if systems:
                    eq_input = EquipmentCapabilityCalcInput(
                        systems=systems,
                        coefficients=DEMO_EQUIPMENT_COEFFICIENTS,
                    )
                    equipment_result = calculate_equipment_capability(eq_input)

                    equipment_result_snapshot: dict[str, Any] = {
                        "compressor_operating_capacity_kw_r": float(
                            equipment_result.result.get("total_design_load_kw_r", 0)
                        ),
                        "compressor_installed_capacity_kw_r": float(
                            equipment_result.result.get("total_compressor_capacity_kw_r", 0)
                        ),
                        "compressor_standby_capacity_kw_r": float(
                            equipment_result.result.get("total_compressor_capacity_kw_r", 0)
                            - equipment_result.result.get("total_design_load_kw_r", 0)
                        ),
                        "condenser_heat_rejection_kw": float(
                            equipment_result.result.get("total_condenser_rejection_kw", 0)
                        ),
                        "installed_power_kw_e": float(
                            equipment_result.result.get("total_compressor_input_power_kw_e", 0)
                        ),
                    }

                    with Session() as session:
                        _persist_calculation(
                            session=session,
                            project_id=project.id,
                            version_number=version.version_number,
                            calculator_name="equipment",
                            calculator_version=equipment_result.calculator_version,
                            input_snapshot=equipment_result.input_snapshot,
                            result_snapshot=equipment_result_snapshot,
                            formulas=[s.to_dict() for s in equipment_result.steps],
                            coefficients=[
                                c.to_dict() for c in equipment_result.coefficient_references
                            ],
                            assumptions=equipment_result.assumptions,
                            warnings=[w.to_dict() for w in equipment_result.warnings],
                            source_references=[],
                            requires_review=equipment_result.requires_review,
                        )
                else:
                    errors.append("equipment: no temperature systems to process")
            except Exception as exc:
                errors.append(f"equipment: {exc}")

        # ------------------------------------------------------------------
        # Stage: investment (InvestmentEstimator)
        # ------------------------------------------------------------------
        if "investment" in scenario.required_stages:
            try:
                if "zone_plan" in stage_ledger and stage_ledger["zone_plan"]["status"] == "passed":
                    assert zone_result is not None  # guaranteed by stage ledger
                    zones = zone_result.result.get("zones", [])
                    if zones:
                        total_area = round(
                            sum(float(z.get("required_area_m2", 0)) for z in zones), 2
                        )
                        refrigerated_area = round(
                            sum(
                                float(z.get("required_area_m2", 0))
                                for z in zones
                                if z.get("temperature_band") != "常温"
                            ),
                            2,
                        )
                        frozen_area = round(
                            sum(
                                float(z.get("required_area_m2", 0))
                                for z in zones
                                if z.get("temperature_band") == "-18℃"
                            ),
                            2,
                        )
                        position_count = sum(int(z.get("position_count", 0)) for z in zones)

                        # Use real power result — total_installed_power_kw_e from the
                        # power stage result dict.  REQUIRED: no zero-value fallback.
                        if (
                            "power" in stage_ledger
                            and stage_ledger["power"]["status"] == "passed"
                            and power_result is not None
                        ):
                            total_power_val = power_result.result.get(
                                "total_installed_power_kw_e", 0
                            )
                            total_power_kw = float(total_power_val)
                        else:
                            # Power stage not available — cannot compute investment.
                            # This is an explicit error, not a silent fallback.
                            stage_ledger["investment"] = _stage_entry(
                                "failed",
                                detail="power_stage_not_available_for_investment",
                                error=(
                                    "Power result required for"
                                    " investment calculation but not available."
                                ),
                            )
                            errors.append("investment: power stage result not available")
                            raise RuntimeError(
                                "Power stage result required for investment calculation"
                            )

                        investment_estimator = InvestmentEstimator()
                        invest_result = investment_estimator.estimate(
                            InvestmentEstimateInput(
                                total_area_m2=total_area,
                                refrigerated_area_m2=refrigerated_area,
                                frozen_area_m2=frozen_area,
                                position_count=position_count,
                                total_power_kw=total_power_kw,
                            )
                        )
                        result["investment"] = _json_safe(asdict(invest_result))
                        stage_ledger["investment"] = _stage_entry(
                            "passed" if invest_result.success else "failed",
                            review_required=invest_result.requires_review,
                            detail="investment_estimate_complete",
                        )

                        # Persist investment result as CalculationRunRecord
                        if invest_result.success:
                            try:
                                invest_result_snapshot: dict[str, Any] = {
                                    "total_investment_cny": float(
                                        invest_result.result.get("total_investment_cny", 0)
                                    ),
                                    "zone_investments": {},
                                }
                                with Session() as session:
                                    _persist_calculation(
                                        session=session,
                                        project_id=project.id,
                                        version_number=version.version_number,
                                        calculator_name="investment",
                                        calculator_version=invest_result.calculator_version,
                                        input_snapshot=invest_result.input,
                                        result_snapshot=invest_result_snapshot,
                                        formulas=[
                                            asdict(f) for f in invest_result.formula_references
                                        ],
                                        coefficients=invest_result.coefficients,
                                        assumptions=invest_result.assumptions,
                                        warnings=[asdict(w) for w in invest_result.warnings],
                                        source_references=invest_result.source_references,
                                        requires_review=invest_result.requires_review,
                                    )
                            except Exception as exc:
                                errors.append(f"investment_persist: {exc}")
                    else:
                        stage_ledger["investment"] = _stage_entry(
                            "failed", detail="no_zones_from_zone_plan"
                        )
                else:
                    stage_ledger["investment"] = _stage_entry(
                        "skipped", detail="zone_plan_not_available"
                    )
            except Exception as exc:
                errors.append(f"investment: {exc}")
                stage_ledger["investment"] = _stage_entry("failed", error=str(exc))
                result["outcome"] = "blocked"

        # ------------------------------------------------------------------
        # Stage: schemes (SchemeService)
        # ------------------------------------------------------------------
        if "schemes" in scenario.required_stages:
            try:
                scheme_config = fixture.get("scheme_run")
                if scheme_config:
                    from cold_storage.bootstrap.scheme_seed import demo_weight_set
                    from cold_storage.modules.schemes.application.service import (
                        SchemeService,
                    )
                    from cold_storage.modules.schemes.infrastructure.repository import (
                        SchemeRepository,
                    )

                    with Session() as session:
                        repo = SchemeRepository(session)
                        repo.save_weight_set(demo_weight_set())
                        session.commit()

                        scheme_svc = SchemeService(session)
                        scheme_result = scheme_svc.generate_scheme_run(
                            project_id=project.id,
                            version=version.version_number,
                            profile_codes=scheme_config.get("profile_codes", []),
                            weight_set_id=scheme_config.get("weight_set_id", "demo-weight-set-001"),
                            profile_parameters=scheme_config.get("profile_parameters", {}),
                        )
                        # Preserve raw output — candidate_id MUST be preserved
                        result["scheme_run"] = _json_safe(scheme_result)
                        stage_ledger["schemes"] = _stage_entry(
                            "passed",
                            detail="scheme_generation_complete",
                        )
            except Exception as exc:
                errors.append(f"schemes: {exc}")
                stage_ledger["schemes"] = _stage_entry(
                    "failed",
                    error=str(exc),
                )
                result["outcome"] = "blocked"

        # ------------------------------------------------------------------
        # Final outcome determination — production contract semantics
        # ------------------------------------------------------------------
        # 1. Any required stage failed/blocked → blocked
        all_required_passed = all(
            stage_ledger.get(stage, {}).get("status") == "passed"
            for stage in scenario.required_stages
        )
        if not all_required_passed:
            result["outcome"] = "blocked"
        # 2. Any required stage has requires_review=true → review_required
        elif any(
            stage_ledger.get(stage, {}).get("review_required", False)
            for stage in scenario.required_stages
        ):
            result["outcome"] = "review_required"
        # 3. Otherwise → success
        else:
            result["outcome"] = "success"

    except Exception as exc:
        errors.append(f"unexpected_error: {exc}")
        result["outcome"] = "blocked"

    result["errors"] = errors
    return ScenarioExecutionResult(
        raw_output=result,
        outcome=result["outcome"],
        stage_ledger=stage_ledger,
        errors=errors,
    )
