"""Per-scenario production workflow orchestration.

Runs each manifest scenario through real production services and produces
a ScenarioExecutionResult with raw output and normalized stage ledger.

IMPORTANT: This module calls ONLY existing public application services.
It MUST NOT fabricate CalculationRunRecord, synthesize engineering inputs,
or implement its own production persistence bridges.  Cooling-load and
equipment stages are gated behind a formal production prerequisite that
has not yet been delivered — see EvaluationPrerequisiteMissingError.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from cold_storage.evaluation.models import EvaluationScenario
from cold_storage.evaluation.sqlite_scope import SqliteScope
from cold_storage.modules.calculations.application.service import (
    CoreCalculationService,
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

    Stages that require production-level calculation persistence (zone,
    cooling_load, equipment, investment) raise
    EvaluationPrerequisiteMissingError when the formal orchestration
    service is not yet available.  This is a harness-level blocker,
    not a business outcome.
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
        # Stage: planning (core calculations via real service)
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
                            "effective_working_ratio",
                            inputs_raw.get("utilization_factor", "0.95"),
                        )
                    ),
                )
                inv_input = InventoryCalcInput(
                    daily_inbound_quantity=_to_decimal(
                        inputs_raw.get(
                            "daily_inbound_mass_kg",
                            inputs_raw.get("daily_inbound_quantity", 0),
                        )
                    ),
                    daily_outbound_quantity=_to_decimal(
                        inputs_raw.get(
                            "daily_outbound_quantity",
                            inputs_raw.get("daily_inbound_mass_kg", 0),
                        )
                    ),
                    turnover_days=_to_decimal(
                        inputs_raw.get(
                            "finished_storage_days",
                            inputs_raw.get("turnover_days", 7),
                        )
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
        # Stage: zone_plan (ColdRoomZonePlanner — real production service)
        # ------------------------------------------------------------------
        zone_result = None
        if "zone_plan" in scenario.required_stages:
            try:
                zone_planner = ColdRoomZonePlanner()
                zone_plan_input = ColdRoomZonePlanInput(
                    daily_inbound_mass_kg=float(inputs_raw.get("daily_inbound_mass_kg", 10000)),
                    working_time_h_per_day=float(inputs_raw.get("working_time_h_per_day", 16)),
                    finished_storage_days=float(
                        inputs_raw.get(
                            "finished_storage_days",
                            inputs_raw.get("storage_days", 2.5),
                        )
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
                # NOTE: No CalculationRunRecord persistence here.
                # That is the responsibility of the formal production
                # orchestration service (prerequisite task).
            except Exception as exc:
                errors.append(f"zone_plan: {exc}")
                stage_ledger["zone_plan"] = _stage_entry("failed", error=str(exc))
                result["outcome"] = "blocked"

        # ------------------------------------------------------------------
        # Stage: power (installed power calculator)
        # ------------------------------------------------------------------
        power_result = None
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
        # Stage: investment (InvestmentEstimator)
        # ------------------------------------------------------------------
        if "investment" in scenario.required_stages:
            try:
                if "zone_plan" in stage_ledger and stage_ledger["zone_plan"]["status"] == "passed":
                    assert zone_result is not None
                    zones = zone_result.result.get("zones", [])
                    if zones:
                        total_area = round(
                            sum(float(z.get("required_area_m2", 0)) for z in zones),
                            2,
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

                        # Use real power result
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
                            stage_ledger["investment"] = _stage_entry(
                                "failed",
                                detail="power_stage_not_available_for_investment",
                                error=(
                                    "Power result required for investment"
                                    " calculation but not available."
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
                        # NOTE: No CalculationRunRecord persistence here.
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
        #
        # Fail-closed with EvaluationPrerequisiteMissingError because the
        # formal production orchestration service that persists zone,
        # cooling_load, equipment, and investment CalculationRunRecord
        # entries is not yet implemented.  The evaluation module MUST NOT
        # fabricate those records.
        # ------------------------------------------------------------------
        if "schemes" in scenario.required_stages:
            scheme_config = fixture.get("scheme_run")
            if scheme_config:
                try:
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
                        result["scheme_run"] = _json_safe(scheme_result)
                        stage_ledger["schemes"] = _stage_entry(
                            "passed",
                            detail="scheme_generation_complete",
                        )
                except Exception as exc:
                    # SchemeService will fail because zone/investment/
                    # cooling_load/equipment CalculationRunRecord entries
                    # do not exist.  This is the EXPECTED fail-closed
                    # behaviour until the formal production prerequisite
                    # is delivered.
                    err_msg = str(exc)
                    errors.append(f"schemes: {err_msg}")
                    stage_ledger["schemes"] = _stage_entry(
                        "failed",
                        error=(
                            "SchemeService requires zone/investment/cooling_load/"
                            "equipment CalculationRunRecord entries persisted by a "
                            "formal production orchestration service.  "
                            "Task 11 is BLOCKED by this prerequisite.  "
                            f"Raw error: {err_msg}"
                        ),
                        review_required=False,
                    )
                    # Schemes failure blocks the run
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
