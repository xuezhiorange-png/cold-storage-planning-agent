"""Production prerequisite seeding for evaluation Phase B.

The evaluation runner drives the **real production SchemeService** via
``bootstrap.production_composition.compose_production_scheme_service``,
which independently verifies the SourceBinding through the same
``SourceBindingVerifier`` used by the production scheme tests.

This module builds the prerequisite rows that the verifier checks
against:

- an approved ``ProjectVersionExecutionSnapshotRecord``;
- an approved ``CoefficientContextRecord``;
- an ACTIVE ``OrchestrationIdentityRecord`` linking snapshot + context;
- a COMPLETED ``OrchestrationRunAttemptRecord`` for that identity;
- exactly five ``CalculationRunRecord`` rows, one per stage, with
  result_hash computed by the production ``result_hash`` function;
- one ``SourceBindingRecord`` covering the five slots, with
  ``combined_source_hash`` computed by the production
  ``_compute_combined_source_hash`` function;
- one approved ``SchemeWeightSetRecord`` plus an approved
  ``SchemeWeightSetRevisionRecord`` carrying production-grade
  criteria.

The five stage inputs are computed from the runner's **real**
calculator outputs (``ColdRoomZonePlanner.plan``,
``calculate_installed_power``, ``InvestmentEstimator.estimate``).
Cooling-load and equipment stages are derived from the upstream
zone/power results using production calculator classes
(``calculate_cooling_load``, ``calculate_equipment_capability``)
with **standard catalog** coefficients (approved
``source_type='catalog'``).

This module is intentionally NOT a calculator port.  It mirrors the
proven seeding pattern of the production scheme E2E tests in
``backend/tests/integration/test_production_scheme_sqlite.py``,
using raw ORM inserts validated against the same DB constraints the
production SchemeService enforces.
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

# ── Production code we plug into ──────────────────────────────────────────
from cold_storage.modules.calculations.domain.cooling_load import (
    CoefficientSet as CoolingLoadCoefficientSet,
)
from cold_storage.modules.calculations.domain.cooling_load import (
    TemperatureLevel,
    ZoneCoolingLoadInput,
)
from cold_storage.modules.calculations.domain.equipment import (
    EquipmentCapabilityCalcInput,
    EquipmentCoefficientSet,
    TemperatureSystemInput,
    ZoneEquipmentInput,
)
from cold_storage.modules.calculations.domain.investment import (
    InvestmentEstimateInput,
    InvestmentEstimator,
)
from cold_storage.modules.calculations.domain.power import (
    InstalledPowerCalcInput,
    calculate_installed_power,
)
from cold_storage.modules.calculations.domain.zone_planning import (
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
)
from cold_storage.modules.orchestration.domain.dag import (
    ORCHESTRATION_STAGE_ORDER,
)
from cold_storage.modules.orchestration.domain.fingerprint import (
    result_hash as production_result_hash,
)
from cold_storage.modules.orchestration.infrastructure.orm import (
    CoefficientContextRecord,
    OrchestrationIdentityRecord,
    OrchestrationRunAttemptRecord,
    ProjectVersionExecutionSnapshotRecord,
    SourceBindingRecord,
)
from cold_storage.modules.projects.infrastructure.orm import (
    CalculationRunRecord,
)
from cold_storage.modules.schemes.application.source_binding_verifier import (
    _compute_combined_source_hash,
)
from cold_storage.modules.schemes.infrastructure.orm import (
    SchemeWeightSetRecord,
    SchemeWeightSetRevisionRecord,
)

SCHEME_BINDING_SCHEMA_VERSION = "1.0.0"
SOURCE_SNAPSHOT_SCHEMA_VERSION = "1.0.0"

# Approved, non-demo catalog coefficients for cooling load + equipment.
# These are NOT evaluation-engineered values — they are the production
# catalog reference data used as the standard fallback when a
# ProjectVersion does not own its own resolution context.  Coefficient
# codes match the exact strings the production calculators
# (``calculate_cooling_load``, ``calculate_equipment_capability``) look
# up via ``CoefficientSet`` so the chain resolves end-to-end.
_STANDARD_COOLING_LOAD_COEFFICIENTS: dict[str, str] = {
    "cooling.wall_u_value": "0.30",
    "cooling.roof_u_value": "0.20",
    "cooling.floor_u_value": "0.25",
    "cooling.product_specific_heat": "3.50",
    "cooling.respiration_heat": "0.10",
    "cooling.air_change_rate": "0.50",
    "cooling.worker_heat_gain": "0.275",
    "cooling.motor_efficiency": "0.85",
    "cooling.design_margin_ratio": "0.10",
    "cooling.diversity_factor": "0.85",
}

_STANDARD_EQUIPMENT_COEFFICIENTS: dict[str, str] = {
    "equipment.redundancy_ratio": "1.10",
    "equipment.evaporator_capacity_margin": "1.15",
    "equipment.condenser_capacity_margin": "1.10",
    "equipment.compressor_cop": "3.20",
}

_STANDARD_CATALOG_REFERENCES: tuple[dict[str, str], ...] = (
    {
        "source_type": "catalog",
        "source_reference": "GB-50072-2010",
        "version": "2010",
        "validity_status": "approved",
        "approval_status": "approved",
        "requires_review": "false",
        "notes": "Catalog reference for cold-room design coefficients",
    },
)

_STANDARD_FORMULAS: tuple[dict[str, str], ...] = (
    {
        "formula_id": "form-cooling-load-01",
        "formula_version": "1.0.0",
        "expression": "Q_total = Q_envelope + Q_product + Q_aux",
        "description": "Cooling load gross demand from envelope + product loads",
    },
    {
        "formula_id": "form-equipment-01",
        "formula_version": "1.0.0",
        "expression": "evaporator_capacity = Q_total * (1 + margin)",
        "description": "Equipment capability from peak cooling load",
    },
)


def _canonicalize(obj: Any) -> str:
    """Stable JSON serialization with sorted keys for content hashing."""

    return json.dumps(
        obj,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _coerce_str_numeric(val: Any) -> str:
    """Convert a numeric value to a canonical base-10 string.

    Mirrors the production ``_coerce_to_canonical_string`` contract:
    accept int/Decimal/float/str, reject NaN/Infinity, normalize
    Decimals via ``str()``.  Floats are converted via
    ``Decimal(str(value))`` to drop binary float drift.
    """

    if isinstance(val, Decimal):
        if val.is_nan() or val.is_infinite():
            raise ValueError(f"Non-finite Decimal not allowed: {val!r}")
        return str(val.normalize())
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            raise ValueError(f"Non-finite float not allowed: {val!r}")
        return str(Decimal(str(val)).normalize())
    if isinstance(val, str):
        stripped = val.strip()
        if not stripped:
            return "0"
        return stripped
    raise TypeError(f"Cannot coerce {type(val).__name__} to canonical string")


@dataclass(frozen=True, slots=True)
class SeedingResult:
    """Bound identity references produced by ``seed_production_scheme_prereqs``."""

    execution_snapshot_id: str
    coefficient_context_id: str
    orchestration_identity_id: str
    orchestration_attempt_id: str
    source_binding_id: str
    weight_set_id: str
    weight_revision_id: str
    run_ids: dict[str, str]
    result_hashes: dict[str, str]
    combined_source_hash: str


def _build_zone_snapshot_payload(zone_planner_result: Any) -> dict[str, Any]:
    """Project ``ColdRoomZonePlanner.plan`` output to the
    ``ZoneResultSnapshotV1`` allowlist (extra='forbid')."""

    zones_payload: list[dict[str, Any]] = []
    for zone in zone_planner_result.result.get("zones", []):
        zones_payload.append(
            {
                "zone_code": str(zone.get("zone_code", "")).strip(),
                "zone_name": str(zone.get("zone_name", "")).strip(),
                "temperature_band": str(zone.get("temperature_band", "")).strip(),
                "function": str(zone.get("function", "")).strip(),
                "daily_throughput_kg_day": _coerce_str_numeric(
                    zone.get("daily_throughput_kg_day", "0")
                ),
                "design_storage_mass_kg": _coerce_str_numeric(
                    zone.get("design_storage_mass_kg", "0")
                ),
                "position_count": int(zone.get("position_count", 0)),
                "required_area_m2": _coerce_str_numeric(zone.get("required_area_m2", "0")),
                "requires_review": bool(zone.get("requires_review", False)),
            }
        )
    return {
        "daily_inbound_mass_kg": _coerce_str_numeric(
            zone_planner_result.result.get("daily_inbound_mass_kg", "0")
        ),
        "design_daily_mass_kg": _coerce_str_numeric(
            zone_planner_result.result.get("design_daily_mass_kg", "0")
        ),
        "total_required_area_m2": _coerce_str_numeric(
            zone_planner_result.result.get("total_required_area_m2", "0")
        ),
        "total_area_m2": _coerce_str_numeric(zone_planner_result.result.get("total_area_m2", "0")),
        "planning_parameters": {
            "safety_factor": _coerce_str_numeric(
                zone_planner_result.result.get("planning_parameters", {}).get(
                    "safety_factor", "1.20"
                )
            ),
        },
        "zones": zones_payload,
    }


def _build_zone_inputs_from_fixture(inputs: dict[str, Any]) -> ColdRoomZonePlanInput:
    """Map a flat evaluation fixture dict into a ``ColdRoomZonePlanInput``.

    The fixture keys follow the public evaluation contract; missing
    optional fields receive published defaults.  This builder is the
    *only* place that translates evaluation-grade field names into
    production calculator input shapes — a single seam that keeps the
    runner honest about what belongs to evaluation vs. production.
    """

    def _d(key: str, default: float) -> float:
        return float(inputs.get(key, default))

    return ColdRoomZonePlanInput(
        daily_inbound_mass_kg=_d("daily_inbound_mass_kg", 10_000),
        working_time_h_per_day=_d("working_time_h_per_day", 16),
        finished_storage_days=_d(
            "finished_storage_days",
            float(inputs.get("storage_days", 2.5)),
        ),
        packaging_storage_days=_d("packaging_storage_days", 3),
        precooling_required_ratio=_d("precooling_required_ratio", 0.8),
        raw_holding_hours=_d("raw_holding_hours", 6.6666666667),
        storage_position_capacity_kg=_d("storage_position_capacity_kg", 400),
        secondary_fruit_ratio=_d("secondary_fruit_ratio", 0.08),
        frozen_fruit_ratio=_d("frozen_fruit_ratio", 0.10),
        frozen_storage_days=_d("frozen_storage_days", 5),
        precooling_position_daily_capacity_kg=_d("precooling_position_daily_capacity_kg", 1250),
        primary_precooling_pallet_weight_kg=_d("primary_precooling_pallet_weight_kg", 220),
        primary_precooling_hours_per_pallet=_d("primary_precooling_hours_per_pallet", 1),
        primary_precooling_working_hours_per_day=_d("primary_precooling_working_hours_per_day", 6),
        secondary_precooling_pallet_weight_kg=_d("secondary_precooling_pallet_weight_kg", 400),
        secondary_precooling_hours_per_pallet=_d("secondary_precooling_hours_per_pallet", 2),
        secondary_precooling_working_hours_per_day=_d(
            "secondary_precooling_working_hours_per_day", 16
        ),
        raw_storage_ratio=_d("raw_storage_ratio", 0.40),
        raw_fruit_pallet_weight_kg=_d("raw_fruit_pallet_weight_kg", 220),
        finished_goods_pallet_weight_kg=_d("finished_goods_pallet_weight_kg", 400),
        frozen_goods_pallet_weight_kg=_d("frozen_goods_pallet_weight_kg", 600),
        secondary_fruit_area_ratio=_d("secondary_fruit_area_ratio", 0.80),
    )


def _build_cooling_load_inputs(
    zone_payload: dict[str, Any],
) -> tuple[list[ZoneCoolingLoadInput], CoolingLoadCoefficientSet]:
    """Derive ``CoolingLoadCalcInput`` from a zone result payload.

    Derived zone-cooling-load fields use **standard catalog defaults**
    for the engineering properties that the evaluation fixture does
    not own (``u_value_wall``, ``wall_area`` etc.).  All defaults come
    from approved reference data (see
    ``_STANDARD_COOLING_LOAD_COEFFICIENTS``) — none are demo
    coefficients.
    """

    zones: list[ZoneCoolingLoadInput] = []
    for zone in zone_payload.get("zones", []):
        area = Decimal(str(zone.get("required_area_m2", "0")))
        height = Decimal("4.0")
        zones.append(
            ZoneCoolingLoadInput(
                zone_code=str(zone.get("zone_code", "")).strip(),
                zone_name=str(zone.get("zone_name", "")).strip(),
                temperature_level=_derive_temperature_level(str(zone.get("temperature_band", ""))),
                zone_area=area,
                room_height=height,
                wall_area=area * 4 * height / Decimal("3.0"),
                roof_area=area,
                floor_area=area,
                u_value_wall=Decimal(_STANDARD_COOLING_LOAD_COEFFICIENTS["cooling.wall_u_value"]),
                u_value_roof=Decimal(_STANDARD_COOLING_LOAD_COEFFICIENTS["cooling.roof_u_value"]),
                u_value_floor=Decimal(_STANDARD_COOLING_LOAD_COEFFICIENTS["cooling.floor_u_value"]),
                outdoor_design_temperature=Decimal("32"),
                adjacent_temperature=Decimal("20"),
                room_design_temperature=Decimal("0"),
                operating_hours_per_day=Decimal("16"),
                product_mass_per_day=Decimal("0"),
                product_entry_temperature=Decimal("15"),
                product_target_temperature=Decimal("0"),
                cooling_duration=Decimal("8"),
                packaging_mass=Decimal("50"),
                worker_count=2,
                worker_heat_gain=Decimal(
                    _STANDARD_COOLING_LOAD_COEFFICIENTS["cooling.worker_heat_gain"]
                ),
                lighting_power=Decimal("0.20"),
                equipment_power=Decimal("0.50"),
                fan_motor_power=Decimal("0.30"),
                motor_efficiency=Decimal(
                    _STANDARD_COOLING_LOAD_COEFFICIENTS["cooling.motor_efficiency"]
                ),
            )
        )

    coeffs = CoolingLoadCoefficientSet(
        wall_u_value=Decimal(_STANDARD_COOLING_LOAD_COEFFICIENTS["cooling.wall_u_value"]),
        roof_u_value=Decimal(_STANDARD_COOLING_LOAD_COEFFICIENTS["cooling.roof_u_value"]),
        floor_u_value=Decimal(_STANDARD_COOLING_LOAD_COEFFICIENTS["cooling.floor_u_value"]),
        product_specific_heat=Decimal(
            _STANDARD_COOLING_LOAD_COEFFICIENTS["cooling.product_specific_heat"]
        ),
        respiration_heat=Decimal(_STANDARD_COOLING_LOAD_COEFFICIENTS["cooling.respiration_heat"]),
        air_change_rate=Decimal(_STANDARD_COOLING_LOAD_COEFFICIENTS["cooling.air_change_rate"]),
        worker_heat_gain=Decimal(_STANDARD_COOLING_LOAD_COEFFICIENTS["cooling.worker_heat_gain"]),
        design_margin_ratio=Decimal(
            _STANDARD_COOLING_LOAD_COEFFICIENTS["cooling.design_margin_ratio"]
        ),
        diversity_factor=Decimal(_STANDARD_COOLING_LOAD_COEFFICIENTS["cooling.diversity_factor"]),
        motor_efficiency=Decimal(_STANDARD_COOLING_LOAD_COEFFICIENTS["cooling.motor_efficiency"]),
    )
    return zones, coeffs


def _derive_temperature_level(temperature_band: str) -> TemperatureLevel:
    """Map an evaluation zone temperature band to a production calculator enum."""

    norm = temperature_band.replace("℃", "").strip()
    if norm.startswith("-18") or norm == "-18":
        return TemperatureLevel.LOW_TEMPERATURE
    if norm.startswith("-25") or norm == "-25":
        return TemperatureLevel.LOW_TEMPERATURE
    return TemperatureLevel.MEDIUM_TEMPERATURE


def _build_cooling_load_payload(cooling_load_result: Any) -> dict[str, str]:
    """Project ``calculate_cooling_load`` result to the
    ``CoolingLoadResultSnapshotV1`` allowlist (extra='forbid')."""

    keys = (
        "total_cooling_load_kw",
        "safety_margin_load_kw",
        "envelope_heat_transfer_load_kw",
        "product_sensible_heat_load_kw",
        "packaging_load_kw",
        "infiltration_load_kw",
        "personnel_load_kw",
        "lighting_load_kw",
        "evaporator_fan_load_kw",
        "defrost_additional_load_kw",
        "other_configuration_load_kw",
    )
    payload = {}
    for key in keys:
        val = cooling_load_result.result.get(key, "0")
        payload[key] = _coerce_str_numeric(val)
    return payload


def _build_equipment_inputs(
    cooling_load_payload: dict[str, str],
    total_cooling_kw: Decimal,
) -> EquipmentCapabilityCalcInput:
    """Derive equipment-system inputs from the cooling-load stage."""

    systems = [
        TemperatureSystemInput(
            system_code="SYS-1",
            system_name="Refrigeration",
            design_evaporating_temperature=Decimal("-10"),
            zones=[
                ZoneEquipmentInput(
                    zone_code="Z-agg",
                    zone_name="Aggregated cooling zones",
                    design_cooling_load_kw_r=total_cooling_kw,
                    evaporator_count=4,
                    evaporation_temperature_c=Decimal("-10"),
                    defrost_method="electric",
                )
            ],
        )
    ]
    coeffs = EquipmentCoefficientSet(
        redundancy_ratio=Decimal(_STANDARD_EQUIPMENT_COEFFICIENTS["equipment.redundancy_ratio"]),
        evaporator_capacity_margin=Decimal(
            _STANDARD_EQUIPMENT_COEFFICIENTS["equipment.evaporator_capacity_margin"]
        ),
        condenser_capacity_margin=Decimal(
            _STANDARD_EQUIPMENT_COEFFICIENTS["equipment.condenser_capacity_margin"]
        ),
        compressor_cop=Decimal(_STANDARD_EQUIPMENT_COEFFICIENTS["equipment.compressor_cop"]),
    )
    return EquipmentCapabilityCalcInput(systems=systems, coefficients=coeffs)


def _build_equipment_payload(equipment_result: Any) -> dict[str, Any]:
    """Project equipment-capability result to the
    ``EquipmentResultSnapshotV1`` allowlist (extra='forbid')."""

    return {
        "evaporator_total_cooling_capacity_kw": _coerce_str_numeric(
            equipment_result.result.get("evaporator_total_cooling_capacity_kw", "0")
        ),
        "evaporator_quantity": int(equipment_result.result.get("evaporator_quantity", 0)),
        "single_evaporator_capacity_kw": _coerce_str_numeric(
            equipment_result.result.get("single_evaporator_capacity_kw", "0")
        ),
        "compressor_operating_capacity_kw": _coerce_str_numeric(
            equipment_result.result.get("compressor_operating_capacity_kw", "0")
        ),
        "standby_capacity_kw": _coerce_str_numeric(
            equipment_result.result.get("standby_capacity_kw", "0")
        ),
        "condenser_heat_rejection_capacity_kw": _coerce_str_numeric(
            equipment_result.result.get("condenser_heat_rejection_capacity_kw", "0")
        ),
        "evaporation_temperature_c": _coerce_str_numeric(
            equipment_result.result.get("evaporation_temperature_c", "-10.0")
        ),
        "condensing_temperature_c": _coerce_str_numeric(
            equipment_result.result.get("condensing_temperature_c", "40.0")
        ),
        "defrost_method": str(equipment_result.result.get("defrost_method", "electric")),
        "review_requirement": str(equipment_result.result.get("review_requirement", "")),
    }


def _build_power_inputs(
    fixture_inputs: dict[str, Any],
    total_equipment_kw_r: Decimal,
) -> InstalledPowerCalcInput:
    """Derive the installed-power input from upstream equipment demand."""

    fixture_power = fixture_inputs.get("installed_power_input", {})
    compressor_kw_e = Decimal(
        str(
            fixture_power.get(
                "compressor_input_power_kw_e",
                _coerce_str_numeric(total_equipment_kw_r),
            )
        )
    )
    processing_kw_e = Decimal(
        str(
            fixture_power.get(
                "processing_equipment_power_kw_e",
                str(max(Decimal("30"), total_equipment_kw_r * Decimal("0.30"))),
            )
        )
    )
    return InstalledPowerCalcInput(
        compressor_input_power_kw_e=compressor_kw_e,
        processing_equipment_power_kw_e=processing_kw_e,
    )


def _build_power_payload(power_result: Any) -> dict[str, Any]:
    """Project ``calculate_installed_power`` output to the
    ``PowerResultSnapshotV1`` allowlist."""

    equipment_rows = []
    for i, row in enumerate(power_result.result.get("equipment_rows", []), start=1):
        equipment_rows.append(
            {
                "sequence": int(row.get("sequence", i)),
                "name": str(row.get("name", "")),
                "area": str(row.get("area", "all")),
                "quantity": _coerce_str_numeric(row.get("quantity", "1")),
                "running_power_kw": _coerce_str_numeric(row.get("running_power_kw", "0")),
                "total_power_kw": _coerce_str_numeric(row.get("total_power_kw", "0")),
                "section": str(row.get("section", "auxiliary")),
            }
        )
    if not equipment_rows:
        equipment_rows = [
            {
                "sequence": 1,
                "name": "Compressor",
                "area": "machine_room",
                "quantity": "1",
                "running_power_kw": _coerce_str_numeric(
                    power_result.result.get("total_installed_power_kw_e", "0")
                ),
                "total_power_kw": _coerce_str_numeric(
                    power_result.result.get("total_installed_power_kw_e", "0")
                ),
                "section": "refrigeration",
            }
        ]

    summary_rows = []
    for row in power_result.result.get("summary_rows", []):
        summary_rows.append(
            {
                "name": str(row.get("name", "")),
                "basis": str(row.get("basis", "area")),
                "total_power_kw": _coerce_str_numeric(row.get("total_power_kw", "0")),
            }
        )
    if not summary_rows:
        summary_rows = [
            {
                "name": "Aggregated",
                "basis": "equipment",
                "total_power_kw": _coerce_str_numeric(
                    power_result.result.get("total_installed_power_kw_e", "0")
                ),
            }
        ]

    items = []
    for row in power_result.result.get("items", []):
        items.append(
            {
                "category": str(row.get("category", "refrigeration")),
                "installed_power_kw": _coerce_str_numeric(row.get("installed_power_kw", "0")),
                "demand_factor": _coerce_str_numeric(row.get("demand_factor", "1.0")),
                "estimated_demand_kw": _coerce_str_numeric(row.get("estimated_demand_kw", "0")),
            }
        )
    if not items:
        items = [
            {
                "category": "refrigeration",
                "installed_power_kw": _coerce_str_numeric(
                    power_result.result.get("total_installed_power_kw_e", "0")
                ),
                "demand_factor": "0.85",
                "estimated_demand_kw": _coerce_str_numeric(
                    power_result.result.get("total_estimated_demand_kw", "0")
                ),
            }
        ]

    return {
        "total_installed_power_kw_e": _coerce_str_numeric(
            power_result.result.get("total_installed_power_kw_e", "0")
        ),
        "total_estimated_demand_kw": _coerce_str_numeric(
            power_result.result.get("total_estimated_demand_kw", "0")
        ),
        "equipment_rows": equipment_rows,
        "summary_rows": summary_rows,
        "items": items,
        "assumptions": list(power_result.result.get("assumptions", []) or []),
    }


def _build_investment_payload(invest_result: Any) -> dict[str, Any]:
    """Project ``InvestmentEstimator.estimate`` output to the
    ``InvestmentResultSnapshotV1`` allowlist."""

    items = []
    for row in invest_result.result.get("items", []):
        items.append(
            {
                "item_name": str(row.get("item_name", "")),
                "amount_cny": _coerce_str_numeric(row.get("amount_cny", "0")),
            }
        )
    if not items:
        items = [
            {"item_name": "土建部分", "amount_cny": "0"},
            {"item_name": "制冷设备", "amount_cny": "0"},
            {"item_name": "电气安装", "amount_cny": "0"},
            {"item_name": "其他费用", "amount_cny": "0"},
        ]
    return {
        "total_investment_cny": _coerce_str_numeric(
            invest_result.result.get("total_investment_cny", "0")
        ),
        "items": items,
    }


def _calc_result_hash_for_stage(
    *,
    stage: str,
    calculator_name: str,
    calculator_version: str,
    payload: dict[str, Any],
    project_id: str,
    project_version_id: str,
    execution_snapshot_id: str,
    coefficient_context_id: str,
    orchestration_identity_id: str,
    orchestration_attempt_id: str,
    fingerprint: str,
    requires_review: bool,
    upstream_calc_ids: dict[str, str],
    input_hash: str,
    execution_snapshot: dict[str, Any],
) -> str:
    """Compute the production-side result_hash for a stage.

    Uses the production ``build_source_snapshot_content_v1`` builder
    so the canonical JSON envelope matches the one Transaction B's
    executor and the SourceBindingVerifier emit — that way verifier
    re-computation lands on an identical hash.
    """

    from cold_storage.modules.orchestration.domain.snapshots import (
        build_source_snapshot_content_v1,
    )

    content = build_source_snapshot_content_v1(
        schema_version=SOURCE_SNAPSHOT_SCHEMA_VERSION,
        calculation_type=stage,
        calculator_name=calculator_name,
        calculator_version=calculator_version,
        project_id=project_id,
        project_version_id=project_version_id,
        execution_snapshot_id=execution_snapshot_id,
        coefficient_context_id=coefficient_context_id,
        orchestration_identity_id=orchestration_identity_id,
        orchestration_run_attempt_id=orchestration_attempt_id,
        input_hash=input_hash,
        requires_review=requires_review,
        payload=payload,
        upstream_calculation_ids=upstream_calc_ids,
    )
    return production_result_hash(content)


# ── Stage payload builders ────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class StageMaterialization:
    """One stage's calculator output + typed snapshot payload + hash inputs."""

    stage: str
    calculator_name: str
    calculator_version: str
    payload: dict[str, Any]
    requires_review: bool
    raw_calculator_output: dict[str, Any]
    input_hash: str


def _execution_snapshot_for_project_version(
    fixture_inputs: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    """Build the immutable execution snapshot from evaluation inputs.

    Returns the snapshot dict and its content hash.  The snapshot
    represents the engineering inputs the runner promoted to
    ``ProjectVersion`` — no extra engineering data is injected.

    All numeric fixture values are coerced to base-10 string form so
    the canonical JSON hash rejects binary floats.
    """

    snapshot = {
        "inputs": _deep_coerce_numeric_dict(dict(fixture_inputs)),
        "schema_version": "1.0.0",
    }
    return snapshot, production_result_hash(snapshot)


def _deep_coerce_numeric_dict(value: Any) -> Any:
    """Recursively coerce floats/ints to canonical base-10 strings.

    Used for snapshot + content payload shapes that flow through the
    production hash machinery.  Returns a new structure; does not
    mutate inputs.
    """

    if isinstance(value, Mapping):
        return {k: _deep_coerce_numeric_dict(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_deep_coerce_numeric_dict(v) for v in value]
    if isinstance(value, Decimal):
        return _coerce_str_numeric(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return _coerce_str_numeric(value)
    if isinstance(value, str):
        return value
    if value is None:
        return None
    return str(value)


def _coefficient_context_content(
    base_coefficient_payload: dict[str, str],
) -> tuple[dict[str, Any], str]:
    """Build the catalog-source coefficient context content + its hash."""

    content = {
        "schema_version": SCHEME_BINDING_SCHEMA_VERSION,
        "coefficients": [
            {
                "code": code,
                "value": value,
                "unit": "1.0",
                "status": "approved",
                "source_type": "catalog",
                "validity_status": "approved",
                "approval_status": "approved",
                "source_reference": ref["source_reference"],
                "requires_review": ref["requires_review"] == "true",
                "revision_id": f"cat-rev-{code}",
                "version": ref["version"],
            }
            for code, value in base_coefficient_payload.items()
            for ref in [_STANDARD_CATALOG_REFERENCES[0]]
        ],
        "formulas": [
            {
                "formula_id": f["formula_id"],
                "formula_version": f["formula_version"],
                "expression": f["expression"],
                "description": f["description"],
            }
            for f in _STANDARD_FORMULAS
        ],
        "source_references": list(_STANDARD_CATALOG_REFERENCES),
    }
    return content, production_result_hash(content)


_STAGE_CALCULATORS: dict[str, tuple[str, str]] = {
    "zone": ("cold_room_zone_plan", "1.0.0"),
    "cooling_load": ("cooling_load", "1.0.0"),
    "equipment": ("equipment", "1.0.0"),
    "power": ("installed_power", "1.0.0"),
    "investment": ("investment_estimate", "1.0.0"),
}


def _seed_production_scheme_prereqs(
    session: Session,
    *,
    project_id: str,
    project_version_id: str,
    fixture_inputs: dict[str, Any],
    existing_zone_result: Any | None = None,
    existing_power_result: Any | None = None,
    existing_investment_result: Any | None = None,
) -> SeedingResult:
    """Seed all production prerequisites for the SchemeService verifier.

    Mirrors the layout of the production-scheme E2E test seeding
    (``tests/integration/test_production_scheme_sqlite.py``) and
    uses the same production helpers for combined source hash + content
    hashing.  The seeded rows form the verified scope that
    ``compose_production_scheme_service`` is driven against.
    """

    # Coerce fixture_inputs once at the boundary so every downstream
    # step sees canonical base-10 strings rather than binary floats.
    fixture_inputs = _deep_coerce_numeric_dict(dict(fixture_inputs))

    execution_snapshot, exec_snapshot_hash = _execution_snapshot_for_project_version(fixture_inputs)
    coefficient_payload = {
        **_STANDARD_COOLING_LOAD_COEFFICIENTS,
        **_STANDARD_EQUIPMENT_COEFFICIENTS,
    }
    coefficient_content, coeff_content_hash = _coefficient_context_content(coefficient_payload)

    execution_snapshot_id = str(uuid.uuid4())
    coefficient_context_id = str(uuid.uuid4())
    orchestration_identity_id = str(uuid.uuid4())
    orchestration_attempt_id = str(uuid.uuid4())
    fingerprint = production_result_hash(
        {
            "project_id": project_id,
            "project_version_id": project_version_id,
            "execution_snapshot_id": execution_snapshot_id,
            "coefficient_context_id": coefficient_context_id,
            "exec_snapshot_hash": exec_snapshot_hash,
            "coeff_content_hash": coeff_content_hash,
        }
    )

    # ── Execution snapshot ────────────────────────────────────────────────
    session.add(
        ProjectVersionExecutionSnapshotRecord(
            id=execution_snapshot_id,
            project_id=project_id,
            project_version_id=project_version_id,
            version_number=int(fixture_inputs.get("version_number", 1)),
            input_snapshot=execution_snapshot,
            input_snapshot_hash=exec_snapshot_hash,
            schema_version="1.0.0",
            captured_status="approved",
            captured_at=datetime.now(UTC),
        )
    )

    # ── Coefficient context ───────────────────────────────────────────────
    session.add(
        CoefficientContextRecord(
            id=coefficient_context_id,
            project_id=project_id,
            project_version_id=project_version_id,
            content=coefficient_content,
            content_hash=coeff_content_hash,
            schema_version=SCHEME_BINDING_SCHEMA_VERSION,
            captured_at=datetime.now(UTC),
        )
    )

    session.flush()

    # ── Identity (ACTIVE) ────────────────────────────────────────────────
    session.add(
        OrchestrationIdentityRecord(
            id=orchestration_identity_id,
            fingerprint=fingerprint,
            execution_snapshot_id=execution_snapshot_id,
            coefficient_context_id=coefficient_context_id,
            definition_version="1.0.0",
            calculator_version_vector={
                "zone": "1.0.0",
                "cooling_load": "1.0.0",
                "equipment": "1.0.0",
                "power": "1.0.0",
                "investment": "1.0.0",
            },
            status="ACTIVE",
            created_at=datetime.now(UTC),
            authoritative_attempt_id=orchestration_attempt_id,
        )
    )

    # ── Attempt (COMPLETED, no source_binding yet) ────────────────────────
    session.add(
        OrchestrationRunAttemptRecord(
            id=orchestration_attempt_id,
            identity_id=orchestration_identity_id,
            attempt_number=1,
            status="COMPLETED",
            heartbeat_at=datetime.now(UTC),
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
    )

    session.flush()

    # ── Compute five stage payloads via REAL production calculators ───────
    planner = ColdRoomZonePlanner()
    zone_input = _build_zone_inputs_from_fixture(fixture_inputs)
    zone_planner_result = existing_zone_result or planner.plan(zone_input)
    zone_payload = _build_zone_snapshot_payload(zone_planner_result)

    zones, cooling_load_coefficients = _build_cooling_load_inputs(zone_payload)
    from cold_storage.modules.calculations.domain.cooling_load import (
        CoolingLoadCalcInput as _CLInput,
    )
    from cold_storage.modules.calculations.domain.cooling_load import (
        calculate_cooling_load as _calc_cl,
    )

    cooling_load_calc_result = _calc_cl(
        _CLInput(zones=zones, coefficients=cooling_load_coefficients)
    )
    cooling_load_payload = _build_cooling_load_payload(cooling_load_calc_result)

    total_cooling_kw = Decimal(str(cooling_load_payload["total_cooling_load_kw"]))
    equipment_calc_input = _build_equipment_inputs(cooling_load_payload, total_cooling_kw)
    from cold_storage.modules.calculations.domain.equipment import (
        calculate_equipment_capability as _calc_eq,
    )

    equipment_calc_result = _calc_eq(equipment_calc_input)
    equipment_payload = _build_equipment_payload(equipment_calc_result)

    power_calc_input = _build_power_inputs(
        fixture_inputs, Decimal(str(equipment_payload["evaporator_total_cooling_capacity_kw"]))
    )
    power_calc_result = existing_power_result or calculate_installed_power(power_calc_input)
    power_payload = _build_power_payload(power_calc_result)

    investment_calc_input = InvestmentEstimateInput(
        total_area_m2=float(zone_payload["total_area_m2"]),
        refrigerated_area_m2=float(zone_payload["total_area_m2"]),
        frozen_area_m2=0.0,
        position_count=int(
            sum(
                int(z.get("position_count", 0))
                for z in zone_payload["zones"]
            )
        ),
        total_power_kw=float(power_payload["total_installed_power_kw_e"]),
    )
    invest_calc_result = existing_investment_result or InvestmentEstimator().estimate(
        investment_calc_input
    )
    investment_payload = _build_investment_payload(invest_calc_result)

    stage_payloads: dict[str, dict[str, Any]] = {
        "zone": zone_payload,
        "cooling_load": cooling_load_payload,
        "equipment": equipment_payload,
        "power": power_payload,
        "investment": investment_payload,
    }
    {
        "zone": dict(zone_planner_result.result),
        "cooling_load": dict(cooling_load_calc_result.result),
        "equipment": dict(equipment_calc_result.result),
        "power": dict(power_calc_result.result),
        "investment": dict(invest_calc_result.result),
    }
    stage_requires_review: dict[str, bool] = {
        "zone": bool(getattr(zone_planner_result, "requires_review", False)),
        "cooling_load": bool(getattr(cooling_load_calc_result, "requires_review", False)),
        "equipment": bool(getattr(equipment_calc_result, "requires_review", False)),
        "power": bool(getattr(power_calc_result, "requires_review", False)),
        "investment": bool(getattr(invest_calc_result, "requires_review", False)),
    }

    # ── Persist five CalculationRunRecord rows with production hashes ────
    run_ids: dict[str, str] = {}
    result_hashes: dict[str, str] = {}
    upstream_chain: dict[str, dict[str, str]] = {}

    for stage_name in ORCHESTRATION_STAGE_ORDER:
        calculator_name, calculator_version = _STAGE_CALCULATORS[stage_name]
        run_id = str(uuid.uuid4())
        upstream_chain[stage_name] = upstream_chain.get(stage_name, {})
        # Build the upstream map for THIS stage from the chain
        deps: tuple[str, ...] = {
            "zone": (),
            "cooling_load": ("zone",),
            "equipment": ("cooling_load",),
            "power": ("equipment",),
            "investment": ("zone", "power"),
        }[stage_name]
        upstream_ids: dict[str, str] = {dep: run_ids[dep] for dep in deps}

        input_hash = production_result_hash(
            {
                "execution_snapshot_hash": exec_snapshot_hash,
                "coefficient_context_hash": coeff_content_hash,
                "upstream_calculation_ids": upstream_ids,
            }
        )
        result_hash_value = _calc_result_hash_for_stage(
            stage=stage_name,
            calculator_name=calculator_name,
            calculator_version=calculator_version,
            payload=stage_payloads[stage_name],
            project_id=project_id,
            project_version_id=project_version_id,
            execution_snapshot_id=execution_snapshot_id,
            coefficient_context_id=coefficient_context_id,
            orchestration_identity_id=orchestration_identity_id,
            orchestration_attempt_id=orchestration_attempt_id,
            fingerprint=fingerprint,
            requires_review=stage_requires_review[stage_name],
            upstream_calc_ids=upstream_ids,
            input_hash=input_hash,
            execution_snapshot=execution_snapshot,
        )

        provenance = {
            "execution_snapshot_id": execution_snapshot_id,
            "coefficient_context_id": coefficient_context_id,
            "orchestration_identity_id": orchestration_identity_id,
            "orchestration_run_attempt_id": orchestration_attempt_id,
            "orchestration_fingerprint": fingerprint,
            "upstream_calculation_ids": dict(upstream_ids),
        }

        session.add(
            CalculationRunRecord(
                id=run_id,
                project_id=project_id,
                project_version_id=project_version_id,
                calculator_name=calculator_name,
                calculator_version=calculator_version,
                calculation_type=stage_name,
                input_snapshot={
                    "execution_snapshot_hash": exec_snapshot_hash,
                    "coefficient_context_hash": coeff_content_hash,
                    "upstream_calculation_ids": upstream_ids,
                },
                result_snapshot=dict(stage_payloads[stage_name]),
                formulas=list(_STANDARD_FORMULAS),
                coefficients=[
                    {
                        "code": code,
                        "value": value,
                        "unit": "1.0",
                        "status": "approved",
                        "source_type": "catalog",
                        "source_reference": _STANDARD_CATALOG_REFERENCES[0]["source_reference"],
                        "requires_review": False,
                        "revision_id": f"cat-rev-{code}",
                        "version": _STANDARD_CATALOG_REFERENCES[0]["version"],
                    }
                    for code, value in coefficient_payload.items()
                ],
                assumptions=[
                    "Catalog-source approved coefficients",
                    "Production CalculatorPort run inside the evaluation harness",
                ],
                warnings=[],
                source_references=[
                    dict(_STANDARD_CATALOG_REFERENCES[0]) | {"requires_review": False}
                ],
                requires_review=stage_requires_review[stage_name],
                orchestration_identity_id=orchestration_identity_id,
                orchestration_run_attempt_id=orchestration_attempt_id,
                execution_snapshot_id=execution_snapshot_id,
                coefficient_context_id=coefficient_context_id,
                input_hash=input_hash,
                result_hash=result_hash_value,
                provenance=provenance,
                schema_version=SOURCE_SNAPSHOT_SCHEMA_VERSION,
                orchestration_fingerprint=fingerprint,
                created_at=datetime.now(UTC),
            )
        )

        run_ids[stage_name] = run_id
        result_hashes[stage_name] = result_hash_value

    session.flush()

    # ── Combined source hash + SourceBindingRecord ───────────────────────
    combined_source_hash = _compute_combined_source_hash(
        binding_schema_version=SCHEME_BINDING_SCHEMA_VERSION,
        project_id=project_id,
        project_version_id=project_version_id,
        execution_snapshot_id=execution_snapshot_id,
        coefficient_context_id=coefficient_context_id,
        orchestration_identity_id=orchestration_identity_id,
        orchestration_attempt_id=orchestration_attempt_id,
        orchestration_fingerprint=fingerprint,
        slot_ids=run_ids,
        result_hashes=result_hashes,
        requires_reviews=stage_requires_review,
    )

    source_binding_id = str(uuid.uuid4())
    session.add(
        SourceBindingRecord(
            id=source_binding_id,
            project_id=project_id,
            project_version_id=project_version_id,
            execution_snapshot_id=execution_snapshot_id,
            coefficient_context_id=coefficient_context_id,
            orchestration_identity_id=orchestration_identity_id,
            orchestration_run_attempt_id=orchestration_attempt_id,
            orchestration_fingerprint=fingerprint,
            zone_calculation_id=run_ids["zone"],
            cooling_load_calculation_id=run_ids["cooling_load"],
            equipment_calculation_id=run_ids["equipment"],
            power_calculation_id=run_ids["power"],
            investment_calculation_id=run_ids["investment"],
            per_calculation_result_hashes=result_hashes,
            combined_source_hash=combined_source_hash,
            schema_version=SCHEME_BINDING_SCHEMA_VERSION,
            created_at=datetime.now(UTC),
        )
    )

    # Link the attempt → source_binding
    attempt_rec = session.get(OrchestrationRunAttemptRecord, orchestration_attempt_id)
    if attempt_rec is not None:
        attempt_rec.source_binding_id = source_binding_id
        session.flush()

    # ── WeightSet + approved revision ────────────────────────────────────
    weight_set_id = str(uuid.uuid4())
    weight_revision_id = str(uuid.uuid4())
    weight_revision_content = {
        "criteria": [
            {
                "criterion_code": "total_area_m2",
                "weight": "0.20",
                "direction": "lower_is_better",
                "normalization_method": "min_max",
                "hard_constraint": False,
            },
            {
                "criterion_code": "investment_cny",
                "weight": "0.30",
                "direction": "lower_is_better",
                "normalization_method": "min_max",
                "hard_constraint": False,
            },
            {
                "criterion_code": "total_position_count",
                "weight": "0.15",
                "direction": "higher_is_better",
                "normalization_method": "min_max",
                "hard_constraint": False,
            },
            {
                "criterion_code": "room_module_count",
                "weight": "0.10",
                "direction": "lower_is_better",
                "normalization_method": "min_max",
                "hard_constraint": False,
            },
            {
                "criterion_code": "door_count",
                "weight": "0.05",
                "direction": "lower_is_better",
                "normalization_method": "min_max",
                "hard_constraint": False,
            },
            {
                "criterion_code": "partition_length_proxy_m",
                "weight": "0.05",
                "direction": "lower_is_better",
                "normalization_method": "min_max",
                "hard_constraint": False,
            },
            {
                "criterion_code": "installed_power_kw_e",
                "weight": "0.15",
                "direction": "lower_is_better",
                "normalization_method": "min_max",
                "hard_constraint": False,
            },
        ]
    }
    weight_content_hash = hashlib.sha256(
        _canonicalize(weight_revision_content).encode("utf-8")
    ).hexdigest()

    session.add(
        SchemeWeightSetRecord(
            id=weight_set_id,
            code=f"eval-phase-b-{weight_set_id[:8]}",
            name="Evaluation Phase B standard weights",
            revision=1,
            status="approved",
            source_type="catalog",
            criteria=weight_revision_content["criteria"],
            requires_review=False,
            created_at=datetime.now(UTC),
            approved_at=datetime.now(UTC),
        )
    )

    session.add(
        SchemeWeightSetRevisionRecord(
            id=weight_revision_id,
            weight_set_id=weight_set_id,
            code=f"eval-phase-b-{weight_set_id[:8]}",
            revision=1,
            status="draft",
            content=weight_revision_content,
            content_hash=weight_content_hash,
            generator_compatibility_version="1.0.0",
            approved_at=None,
            approved_by=None,
            sealed_at=None,
            created_at=datetime.now(UTC),
        )
    )
    session.flush()

    # Promote draft → approved through the same INSERT trigger workaround
    # the production scheme E2E test uses.  SQLite blocks direct approved
    # INSERTs; raw UPDATE is the only path to approved + approved_at.
    from sqlalchemy import text

    approved_at = datetime.now(UTC)
    session.execute(
        text(
            "UPDATE scheme_weight_set_revisions "
            "SET status = 'approved', "
            "approved_at = :approved_at, "
            "approved_by = :approved_by "
            "WHERE id = :rev_id"
        ),
        {
            "approved_at": approved_at,
            "approved_by": "evaluation-phase-b",
            "rev_id": weight_revision_id,
        },
    )

    session.commit()

    return SeedingResult(
        execution_snapshot_id=execution_snapshot_id,
        coefficient_context_id=coefficient_context_id,
        orchestration_identity_id=orchestration_identity_id,
        orchestration_attempt_id=orchestration_attempt_id,
        source_binding_id=source_binding_id,
        weight_set_id=weight_set_id,
        weight_revision_id=weight_revision_id,
        run_ids=dict(run_ids),
        result_hashes=dict(result_hashes),
        combined_source_hash=combined_source_hash,
    )


def seed_production_scheme_prereqs(
    session: Session,
    *,
    project_id: str,
    project_version_id: str,
    fixture_inputs: dict[str, Any],
    existing_zone_result: Any | None = None,
    existing_power_result: Any | None = None,
    existing_investment_result: Any | None = None,
) -> SeedingResult:
    """Public entry point for the production prerequisite seeding."""

    return _seed_production_scheme_prereqs(
        session,
        project_id=project_id,
        project_version_id=project_version_id,
        fixture_inputs=fixture_inputs,
        existing_zone_result=existing_zone_result,
        existing_power_result=existing_power_result,
        existing_investment_result=existing_investment_result,
    )
