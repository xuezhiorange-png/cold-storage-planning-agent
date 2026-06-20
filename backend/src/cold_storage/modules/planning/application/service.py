"""Planning orchestration utilities.

Shared calculation helpers used by both the API routes and the demo overview.
These functions are pure and stateless — they receive inputs and return results
without touching databases or external services.
"""

from dataclasses import asdict
from typing import Any

from pydantic import BaseModel

from cold_storage.modules.calculations.domain.investment import (
    InvestmentEstimateInput,
    InvestmentEstimator,
)
from cold_storage.modules.calculations.domain.zone_planning import (
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
)

# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------


def as_float(value: object) -> float:
    if isinstance(value, int | float | str):
        return float(value)
    raise ValueError("value must be numeric")


def zone_number(zone: object, key: str) -> float:
    if not isinstance(zone, dict):
        raise TypeError("zone must be a mapping")
    value = zone[key]
    if isinstance(value, int | float):
        return float(value)
    raise TypeError(f"zone field {key} must be numeric")


def optional_number(value: object) -> float:
    if value is None:
        return 0
    return as_float(value)


# ---------------------------------------------------------------------------
# Zone plan helpers
# ---------------------------------------------------------------------------


def build_zone_plan_from_inputs(
    inputs: dict[str, Any],
    zone_planner: ColdRoomZonePlanner,
) -> Any:
    return zone_planner.plan(
        ColdRoomZonePlanInput(
            daily_inbound_mass_kg=as_float(inputs["daily_inbound_mass_kg"]),
            working_time_h_per_day=as_float(inputs["working_time_h_per_day"]),
            finished_storage_days=as_float(
                inputs.get("finished_storage_days", inputs.get("storage_days"))
            ),
            packaging_storage_days=as_float(inputs.get("packaging_storage_days", 7)),
            precooling_required_ratio=as_float(inputs.get("precooling_required_ratio", 0.8)),
            raw_holding_hours=as_float(inputs.get("raw_holding_hours", 6.6666666667)),
            storage_position_capacity_kg=as_float(inputs.get("storage_position_capacity_kg", 400)),
            secondary_fruit_ratio=as_float(inputs.get("secondary_fruit_ratio", 0.08)),
            frozen_fruit_ratio=as_float(inputs.get("frozen_fruit_ratio", 0.10)),
            frozen_storage_days=as_float(inputs.get("frozen_storage_days", 5)),
            precooling_position_daily_capacity_kg=as_float(
                inputs.get("precooling_position_daily_capacity_kg", 1250)
            ),
            primary_precooling_pallet_weight_kg=as_float(
                inputs.get("primary_precooling_pallet_weight_kg", 220)
            ),
            primary_precooling_hours_per_pallet=as_float(
                inputs.get("primary_precooling_hours_per_pallet", 1)
            ),
            primary_precooling_working_hours_per_day=as_float(
                inputs.get("primary_precooling_working_hours_per_day", 6)
            ),
            secondary_precooling_pallet_weight_kg=as_float(
                inputs.get("secondary_precooling_pallet_weight_kg", 400)
            ),
            secondary_precooling_hours_per_pallet=as_float(
                inputs.get("secondary_precooling_hours_per_pallet", 2)
            ),
            secondary_precooling_working_hours_per_day=as_float(
                inputs.get("secondary_precooling_working_hours_per_day", 16)
            ),
            raw_storage_ratio=as_float(inputs.get("raw_storage_ratio", 0.40)),
            raw_fruit_pallet_weight_kg=as_float(inputs.get("raw_fruit_pallet_weight_kg", 220)),
            finished_goods_pallet_weight_kg=as_float(
                inputs.get("finished_goods_pallet_weight_kg", 400)
            ),
            frozen_goods_pallet_weight_kg=as_float(
                inputs.get("frozen_goods_pallet_weight_kg", 600)
            ),
            secondary_fruit_area_ratio=as_float(inputs.get("secondary_fruit_area_ratio", 0.80)),
            main_packaging_storage_days=as_float(
                inputs.get(
                    "main_packaging_storage_days",
                    inputs.get("packaging_storage_days", 3),
                )
            ),
            auxiliary_packaging_storage_days=as_float(
                inputs.get("auxiliary_packaging_storage_days", 30)
            ),
            packaging_area_factor=as_float(inputs.get("packaging_area_factor", 1.5)),
        )
    )


def build_investment_from_zone_result(
    zone_result: Any,
    investment_estimator: InvestmentEstimator,
    total_power_kw: float,
) -> Any:
    zones = zone_result.result["zones"]
    if not isinstance(zones, list):
        raise ValueError("zone plan result must contain zones")
    total_area = sum(zone_number(zone, "required_area_m2") for zone in zones)
    refrigerated_area = sum(
        zone_number(zone, "required_area_m2")
        for zone in zones
        if isinstance(zone, dict) and zone.get("temperature_band") != "常温"
    )
    frozen_area = sum(
        zone_number(zone, "required_area_m2")
        for zone in zones
        if isinstance(zone, dict) and zone.get("temperature_band") == "-18℃"
    )
    position_count = sum(int(zone_number(zone, "position_count")) for zone in zones)
    return investment_estimator.estimate(
        InvestmentEstimateInput(
            total_area_m2=round(total_area, 2),
            refrigerated_area_m2=round(refrigerated_area, 2),
            frozen_area_m2=round(frozen_area, 2),
            position_count=position_count,
            total_power_kw=total_power_kw,
        )
    )


def planning_run_response(
    inputs: dict[str, Any],
    zone_result: Any,
    investment_result: Any,
) -> dict[str, Any]:
    zones = zone_result.result["zones"]
    if not isinstance(zones, list):
        raise ValueError("zone plan result must contain zones")
    total_area = round(sum(zone_number(zone, "required_area_m2") for zone in zones), 2)
    total_positions = sum(int(zone_number(zone, "position_count")) for zone in zones)
    power_configuration = build_power_configuration(
        zones,
        as_float(inputs["daily_inbound_mass_kg"]),
        total_area,
    )
    return {
        "success": zone_result.success and investment_result.success,
        "input_snapshot": inputs,
        "summary": {
            "total_area_m2": total_area,
            "total_position_count": total_positions,
            "total_investment_cny": investment_result.result["total_investment_cny"],
            "total_power_kw": power_configuration["total_installed_power_kw"],
            "requires_review": zone_result.requires_review or investment_result.requires_review,
        },
        "zone_plan": asdict(zone_result),
        "investment_estimate": asdict(investment_result),
        "power_configuration": power_configuration,
    }


# ---------------------------------------------------------------------------
# Power configuration
# ---------------------------------------------------------------------------


def build_power_configuration(
    zones: list[object],
    daily_inbound_mass_kg: float,
    total_area_m2: float,
) -> dict[str, Any]:
    _ = total_area_m2
    scale = daily_inbound_mass_kg / 25_000
    equipment_rows = [scale_power_row(row, scale) for row in reference_power_rows()]
    apply_precooling_axial_fan_rule(equipment_rows, zones)
    defrost_simultaneous_power = round(
        sum(optional_number(row["defrost_total_power_kw"]) for row in equipment_rows) * 0.30,
        2,
    )
    running_simultaneous_power = round(
        sum(
            as_float(row["total_power_kw"])
            for row in equipment_rows
            if row["section"] == "refrigeration"
        )
        * 0.90,
        2,
    )
    refrigeration_total = round(defrost_simultaneous_power + running_simultaneous_power, 2)
    production_total = round(
        sum(
            as_float(row["total_power_kw"])
            for row in equipment_rows
            if row["section"] == "production"
        )
        * 0.90,
        2,
    )
    grand_total = round(refrigeration_total + production_total, 2)
    summary_rows = [
        {
            "name": "化霜总功率",
            "basis": "按30% 同时化霜",
            "total_power_kw": defrost_simultaneous_power,
        },
        {
            "name": "设备运行功率",
            "basis": "按90% 同时使用系数",
            "total_power_kw": running_simultaneous_power,
        },
        {
            "name": "制冷总功率",
            "basis": "化霜同时系数30% + 设备运行同时系数90%",
            "total_power_kw": refrigeration_total,
        },
        {
            "name": "生产设备总功率",
            "basis": "按90% 同时使用系数",
            "total_power_kw": production_total,
        },
        {"name": "合计", "basis": "", "total_power_kw": grand_total},
    ]
    items = [
        power_item("制冷系统", refrigeration_total, 1),
        power_item("生产设备", production_total, 1),
    ]
    return {
        "equipment_rows": equipment_rows,
        "summary_rows": summary_rows,
        "items": items,
        "total_installed_power_kw": grand_total,
        "total_estimated_demand_kw": grand_total,
        "assumptions": [
            "用电配置按参考项目设备清单演示，默认25吨/天，其他产能按比例缩放。",
            "未替代正式电气设计、设备铭牌功率统计或供配电校核。",
        ],
        "requires_review": True,
    }


def power_item(category: str, installed_power_kw: float, demand_factor: float) -> dict[str, Any]:
    return {
        "category": category,
        "installed_power_kw": round(installed_power_kw, 2),
        "demand_factor": demand_factor,
        "estimated_demand_kw": round(installed_power_kw * demand_factor, 2),
    }


def apply_precooling_axial_fan_rule(
    equipment_rows: list[dict[str, Any]],
    zones: list[object],
) -> None:
    primary_positions = zone_position_count(zones, "primary_precooling_room")
    secondary_positions = zone_position_count(zones, "secondary_precooling_room")
    axial_fan_quantity = (primary_positions + secondary_positions) * 4
    for row in equipment_rows:
        if row["name"] == "轴流风机":
            row["quantity"] = axial_fan_quantity
            row["total_power_kw"] = round(axial_fan_quantity * as_float(row["running_power_kw"]), 2)
            return


def zone_position_count(zones: list[object], zone_code: str) -> int:
    for zone in zones:
        if isinstance(zone, dict) and zone.get("zone_code") == zone_code:
            return int(as_float(zone.get("position_count", 0)))
    return 0


def reference_power_rows() -> list[dict[str, Any]]:
    return [
        equipment_row(
            1,
            "制冷压缩机组",
            "一级预冷、原果暂存间、分选间",
            1,
            None,
            None,
            297.6,
            297.6,
            "refrigeration",
        ),
        equipment_row(
            2,
            "制冷压缩机组",
            "二级预冷间、成品库、出货通道、覆膜间",
            1,
            None,
            None,
            209.6,
            209.6,
            "refrigeration",
        ),
        equipment_row(3, "制冷压缩机组", "成品双温库", 2, None, None, 27.5, 55.0, "refrigeration"),
        equipment_row(4, "制冷压缩机组", "次果暂存区", 1, None, None, 4.21, 4.21, "refrigeration"),
        equipment_row(5, "制冷压缩机组", "冻果间", 1, None, None, 29.4, 29.4, "refrigeration"),
        equipment_row(6, "冷风机", "原果暂存", 3, 4.9, 14.7, 0.75, 2.25, "refrigeration"),
        equipment_row(7, "冷风机", "一级预冷间", 12, 16.0, 192.0, 2.68, 32.16, "refrigeration"),
        equipment_row(8, "冷风机", "分选间", 14, 4.9, 68.6, 0.75, 10.5, "refrigeration"),
        equipment_row(9, "冷风机", "二级预冷间", 14, 21.6, 302.4, 2.68, 37.52, "refrigeration"),
        equipment_row(10, "冷风机", "覆膜间", 3, 21.6, 64.8, 1.796, 5.388, "refrigeration"),
        equipment_row(11, "冷风机", "双温成品库", 4, 25.2, 100.8, 2.68, 10.72, "refrigeration"),
        equipment_row(12, "冷风机", "成品库", 3, 10.0, 30.0, 1.796, 5.388, "refrigeration"),
        equipment_row(13, "冷风机", "次果暂存间", 1, 8.5, 8.5, 1.347, 1.347, "refrigeration"),
        equipment_row(14, "冷风机", "冻果暂存间", 1, 31.5, 31.5, 3.2, 3.2, "refrigeration"),
        equipment_row(15, "冷风机", "出货通道", 2, 8.5, 17.0, 1.347, 2.694, "refrigeration"),
        equipment_row(16, "蒸发冷", "", 1, None, None, 28.0, 28.0, "refrigeration"),
        equipment_row(17, "蒸发冷", "", 1, None, None, 19.0, 19.0, "refrigeration"),
        equipment_row(18, "轴流风机", "", 360, None, None, 0.55, 198.0, "refrigeration"),
        equipment_row(19, "升降平台", "", 3, None, None, 2.2, 6.6, "refrigeration"),
        equipment_row(20, "工业滑升门", "", 3, None, None, 0.4, 1.2, "refrigeration"),
        equipment_row(21, "充气门封", "", 3, None, None, 0.4, 1.2, "refrigeration"),
        equipment_row(22, "电动门", "", 29, None, None, 0.38, 11.02, "refrigeration"),
        equipment_row(23, "快卷门", "", 2, None, None, 0.38, 0.76, "refrigeration"),
        equipment_row(24, "风幕机", "", 10, None, None, 0.38, 3.8, "refrigeration"),
        equipment_row(25, "冷库照明", "", 350, None, None, 0.04, 14.0, "refrigeration"),
        equipment_row(26, "地坪加热丝", "", 1, None, None, 2.0, 2.0, "refrigeration"),
        equipment_row(27, "紫外线灯", "", 190, None, None, 0.08, 15.2, "refrigeration"),
        equipment_row(28, "臭氧", "", 1, None, None, 15.0, 15.0, "refrigeration"),
        equipment_row(29, "加湿", "", 1, None, None, 15.0, 15.0, "refrigeration"),
        equipment_row(35, "折箱机", "", 2, None, None, 12.0, 24.0, "production"),
        equipment_row(36, "枕式包装机", "", 2, None, None, 12.5, 25.0, "production"),
        equipment_row(37, "包装流水线", "", 2, None, None, 7.5, 15.0, "production"),
        equipment_row(38, "筐桶清洗机", "", 2, None, None, 20.0, 40.0, "production"),
        equipment_row(39, "贴标机", "", 2, None, None, 5.0, 10.0, "production"),
        equipment_row(40, "光电分选设备", "", 1, None, None, 65.0, 65.0, "production"),
        equipment_row(41, "定量包装设备", "", 3, None, None, 15.0, 45.0, "production"),
        equipment_row(42, "辅助铺联设备", "", 1, None, None, 40.0, 40.0, "production"),
        equipment_row(43, "空压机", "", 1, None, None, 22.0, 22.0, "production"),
        equipment_row(44, "熏蒸设备", "", 2, None, None, 15.0, 30.0, "production"),
    ]


def equipment_row(
    sequence: int,
    name: str,
    area: str,
    quantity: float,
    defrost_power_kw: float | None,
    defrost_total_power_kw: float | None,
    running_power_kw: float,
    total_power_kw: float,
    section: str,
) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "name": name,
        "area": area,
        "quantity": quantity,
        "defrost_power_kw": defrost_power_kw,
        "defrost_total_power_kw": defrost_total_power_kw,
        "running_power_kw": running_power_kw,
        "total_power_kw": total_power_kw,
        "section": section,
    }


def scale_power_row(row: dict[str, Any], scale: float) -> dict[str, Any]:
    return {
        **row,
        "quantity": scale_value(row["quantity"], scale),
        "defrost_total_power_kw": scale_optional(row["defrost_total_power_kw"], scale),
        "total_power_kw": scale_value(row["total_power_kw"], scale),
    }


def scale_optional(value: object, scale: float) -> float | None:
    if value is None:
        return None
    return scale_value(value, scale)


def scale_value(value: object, scale: float) -> float:
    scaled = as_float(value) * scale
    rounded = round(scaled, 2)
    if rounded.is_integer():
        return int(rounded)
    return rounded


# ---------------------------------------------------------------------------
# Planning request helpers
# ---------------------------------------------------------------------------


def inputs_from_planning_request(
    request: BaseModel,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    inputs = fallback.copy()
    if getattr(request, "inputs", None):
        inputs.update(getattr(request, "inputs", {}))
    inputs.update(flat_planning_input(request))
    if "finished_storage_days" not in inputs and "storage_days" in inputs:
        inputs["finished_storage_days"] = inputs["storage_days"]
    if "packaging_storage_days" not in inputs:
        inputs["packaging_storage_days"] = inputs.get("main_packaging_storage_days", 3)
    if "main_packaging_storage_days" not in inputs:
        inputs["main_packaging_storage_days"] = inputs["packaging_storage_days"]
    if "auxiliary_packaging_storage_days" not in inputs:
        inputs["auxiliary_packaging_storage_days"] = 30
    return inputs


def flat_planning_input(request: BaseModel) -> dict[str, Any]:
    return request.model_dump(
        exclude_none=True,
        exclude={"inputs"},
    )


def demo_inputs() -> dict[str, Any]:
    return {
        "daily_inbound_mass_kg": 25_000,
        "working_time_h_per_day": 16,
        "utilization_factor": 0.85,
        "finished_storage_days": 2.5,
        "packaging_storage_days": 3,
        "main_packaging_storage_days": 3,
        "auxiliary_packaging_storage_days": 30,
        "reserve_factor": 1.05,
        "precooling_required_ratio": 1,
    }
