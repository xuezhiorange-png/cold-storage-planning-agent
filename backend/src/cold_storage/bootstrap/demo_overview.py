from dataclasses import asdict
from typing import Any

from cold_storage.modules.calculations.domain.inputs import ThroughputInput
from cold_storage.modules.calculations.domain.investment import (
    InvestmentEstimateInput,
    InvestmentEstimator,
)
from cold_storage.modules.calculations.domain.service import CalculationService
from cold_storage.modules.calculations.domain.zone_planning import (
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
)
from cold_storage.modules.planning_agent.application.agent_service import PlanningAgentService
from cold_storage.modules.planning_agent.infrastructure.fake_gateways import FakeModelGateway


def build_demo_overview() -> dict[str, Any]:
    throughput = CalculationService().run_throughput(
        ThroughputInput(
            daily_inbound_mass_kg=25_000,
            working_time_h_per_day=16,
            utilization_factor=0.85,
        )
    )
    zone_plan = ColdRoomZonePlanner().plan(
        ColdRoomZonePlanInput(
            daily_inbound_mass_kg=25_000,
            working_time_h_per_day=16,
            finished_storage_days=2.5,
            packaging_storage_days=3,
            main_packaging_storage_days=3,
            auxiliary_packaging_storage_days=30,
            precooling_required_ratio=1,
        )
    )
    zones = zone_plan.result["zones"]
    if not isinstance(zones, list):
        raise TypeError("demo zone plan must contain zones")
    total_area_m2 = _number(zone_plan.result["total_required_area_m2"])
    refrigerated_area_m2 = sum(
        _zone_number(zone, "required_area_m2")
        for zone in zones
        if isinstance(zone, dict) and zone.get("temperature_band") != "常温"
    )
    frozen_area_m2 = sum(
        _zone_number(zone, "required_area_m2")
        for zone in zones
        if isinstance(zone, dict) and zone.get("temperature_band") == "-18℃"
    )
    position_count = sum(int(_zone_number(zone, "position_count")) for zone in zones)
    power_configuration = _build_power_configuration(zones, 25_000, total_area_m2)
    investment = InvestmentEstimator().estimate(
        InvestmentEstimateInput(
            total_area_m2=total_area_m2,
            refrigerated_area_m2=round(refrigerated_area_m2, 2),
            frozen_area_m2=round(frozen_area_m2, 2),
            position_count=position_count,
            total_power_kw=_number(power_configuration["total_installed_power_kw"]),
        )
    )
    agent_response = PlanningAgentService(FakeModelGateway()).handle_message(
        "新建蓝莓项目，日入库25吨，每天工作16小时"
    )
    modules = [
        _module(
            "项目管理",
            "ready",
            {"project_code": "P0001", "project_name": "蓝莓加工中心演示项目"},
        ),
        _module(
            "设计参数",
            "review",
            {"daily_inbound_mass_kg": 25_000, "working_time_h_per_day": 16},
        ),
        _module(
            "参数完整度",
            "review",
            {
                "missing_fields": ["room_design_temperature_c"],
                "tentative_fields": [],
            },
        ),
        _module("确定性计算", "ready", asdict(throughput)),
        _module(
            "冷间区域规划",
            "review",
            {"zones": zones, "total_required_area_m2": total_area_m2},
        ),
        _module("投资测算", "review", investment.result),
        _module("用电配置", "review", power_configuration),
        _module(
            "方案生成",
            "review",
            {"schemes": ["少量大冷间方案", "多个小冷间方案", "平衡方案"]},
        ),
        _module(
            "知识依据",
            "review",
            {"documents": ["蓝莓冷链演示资料.md"], "requires_ocr": False},
        ),
        _module("规划Agent", "ready", asdict(agent_response)),
        _module(
            "报告输出",
            "review",
            {"word_report": "方案书草稿.docx", "excel_report": "计算书草稿.xlsx"},
        ),
        _module("版本历史", "ready", {"current_version": 1, "status": "draft"}),
        _module(
            "审计记录",
            "ready",
            {"events": ["create_project", "save_design_inputs", "run_project_calculations"]},
        ),
    ]
    return {
        "project": {
            "code": "P0001",
            "name": "蓝莓加工厂",
            "location": "山东",
            "product_category": "blueberry",
            "planting_area_mu": 1250,
            "yield_per_thousand_mu_tons": 20,
            "peak_yield_tons": 25,
            "main_varieties": ["蓝莓"],
            "overview_text": (
                "蓝莓加工厂覆盖定植面积1250亩，按20吨/千亩对应峰值产量25吨，主要定植品种为蓝莓"
            ),
        },
        "overall_status": {
            "module_count": len(modules),
            "ready_count": sum(1 for module in modules if module["status"] == "ready"),
            "requires_review_count": sum(1 for module in modules if module["status"] == "review"),
            "total_area_m2": total_area_m2,
            "total_position_count": position_count,
            "total_investment_cny": investment.result["total_investment_cny"],
            "total_power_kw": power_configuration["total_installed_power_kw"],
            "requires_review": True,
        },
        "modules": modules,
    }


def _module(module: str, status: str, sample: dict[str, Any]) -> dict[str, Any]:
    return {"module": module, "status": status, "sample": sample}


def _zone_number(zone: object, key: str) -> float:
    if not isinstance(zone, dict):
        raise TypeError("zone must be a mapping")
    return _number(zone[key])


def _number(value: object) -> float:
    if isinstance(value, int | float):
        return float(value)
    raise TypeError("numeric value expected")


def _build_power_configuration(
    zones: list[object],
    daily_inbound_mass_kg: float,
    total_area_m2: float,
) -> dict[str, Any]:
    _ = total_area_m2
    scale = daily_inbound_mass_kg / 25_000
    equipment_rows = [_scale_power_row(row, scale) for row in _reference_power_rows()]
    _apply_precooling_axial_fan_rule(equipment_rows, zones)
    defrost_power = round(
        sum(_optional_number(row["defrost_total_power_kw"]) for row in equipment_rows) * 0.30,
        2,
    )
    running_power = round(
        sum(
            _number(row["total_power_kw"])
            for row in equipment_rows
            if row["section"] == "refrigeration"
        )
        * 0.90,
        2,
    )
    refrigeration_total = round(defrost_power + running_power, 2)
    production_total = round(
        sum(
            _number(row["total_power_kw"])
            for row in equipment_rows
            if row["section"] == "production"
        )
        * 0.90,
        2,
    )
    grand_total = round(refrigeration_total + production_total, 2)
    summary_rows = [
        {"name": "化霜总功率", "basis": "按30% 同时化霜", "total_power_kw": defrost_power},
        {"name": "设备运行功率", "basis": "按90% 同时使用系数", "total_power_kw": running_power},
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
        _power_item("制冷系统", refrigeration_total, 1),
        _power_item("生产设备", production_total, 1),
    ]
    return {
        "equipment_rows": equipment_rows,
        "summary_rows": summary_rows,
        "items": items,
        "total_installed_power_kw": grand_total,
        "total_estimated_demand_kw": grand_total,
        "requires_review": True,
    }


def _power_item(category: str, installed_power_kw: float, demand_factor: float) -> dict[str, Any]:
    return {
        "category": category,
        "installed_power_kw": round(installed_power_kw, 2),
        "demand_factor": demand_factor,
        "estimated_demand_kw": round(installed_power_kw * demand_factor, 2),
    }


def _apply_precooling_axial_fan_rule(
    equipment_rows: list[dict[str, Any]],
    zones: list[object],
) -> None:
    primary_positions = _zone_position_count(zones, "primary_precooling_room")
    secondary_positions = _zone_position_count(zones, "secondary_precooling_room")
    axial_fan_quantity = (primary_positions + secondary_positions) * 4
    for row in equipment_rows:
        if row["name"] == "轴流风机":
            row["quantity"] = axial_fan_quantity
            row["total_power_kw"] = round(
                axial_fan_quantity * _number(row["running_power_kw"]), 2
            )
            return


def _zone_position_count(zones: list[object], zone_code: str) -> int:
    for zone in zones:
        if isinstance(zone, dict) and zone.get("zone_code") == zone_code:
            return int(_number(zone.get("position_count", 0)))
    return 0


def _reference_power_rows() -> list[dict[str, Any]]:
    return [
        _equipment_row(
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
        _equipment_row(
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
        _equipment_row(3, "制冷压缩机组", "成品双温库", 2, None, None, 27.5, 55.0, "refrigeration"),
        _equipment_row(4, "制冷压缩机组", "次果暂存区", 1, None, None, 4.21, 4.21, "refrigeration"),
        _equipment_row(5, "制冷压缩机组", "冻果间", 1, None, None, 29.4, 29.4, "refrigeration"),
        _equipment_row(6, "冷风机", "原果暂存", 3, 4.9, 14.7, 0.75, 2.25, "refrigeration"),
        _equipment_row(7, "冷风机", "一级预冷间", 12, 16.0, 192.0, 2.68, 32.16, "refrigeration"),
        _equipment_row(8, "冷风机", "分选间", 14, 4.9, 68.6, 0.75, 10.5, "refrigeration"),
        _equipment_row(9, "冷风机", "二级预冷间", 14, 21.6, 302.4, 2.68, 37.52, "refrigeration"),
        _equipment_row(10, "冷风机", "覆膜间", 3, 21.6, 64.8, 1.796, 5.388, "refrigeration"),
        _equipment_row(11, "冷风机", "双温成品库", 4, 25.2, 100.8, 2.68, 10.72, "refrigeration"),
        _equipment_row(12, "冷风机", "成品库", 3, 10.0, 30.0, 1.796, 5.388, "refrigeration"),
        _equipment_row(13, "冷风机", "次果暂存间", 1, 8.5, 8.5, 1.347, 1.347, "refrigeration"),
        _equipment_row(14, "冷风机", "冻果暂存间", 1, 31.5, 31.5, 3.2, 3.2, "refrigeration"),
        _equipment_row(15, "冷风机", "出货通道", 2, 8.5, 17.0, 1.347, 2.694, "refrigeration"),
        _equipment_row(16, "蒸发冷", "", 1, None, None, 28.0, 28.0, "refrigeration"),
        _equipment_row(17, "蒸发冷", "", 1, None, None, 19.0, 19.0, "refrigeration"),
        _equipment_row(18, "轴流风机", "", 360, None, None, 0.55, 198.0, "refrigeration"),
        _equipment_row(19, "升降平台", "", 3, None, None, 2.2, 6.6, "refrigeration"),
        _equipment_row(20, "工业滑升门", "", 3, None, None, 0.4, 1.2, "refrigeration"),
        _equipment_row(21, "充气门封", "", 3, None, None, 0.4, 1.2, "refrigeration"),
        _equipment_row(22, "电动门", "", 29, None, None, 0.38, 11.02, "refrigeration"),
        _equipment_row(23, "快卷门", "", 2, None, None, 0.38, 0.76, "refrigeration"),
        _equipment_row(24, "风幕机", "", 10, None, None, 0.38, 3.8, "refrigeration"),
        _equipment_row(25, "冷库照明", "", 350, None, None, 0.04, 14.0, "refrigeration"),
        _equipment_row(26, "地坪加热丝", "", 1, None, None, 2.0, 2.0, "refrigeration"),
        _equipment_row(27, "紫外线灯", "", 190, None, None, 0.08, 15.2, "refrigeration"),
        _equipment_row(28, "臭氧", "", 1, None, None, 15.0, 15.0, "refrigeration"),
        _equipment_row(29, "加湿", "", 1, None, None, 15.0, 15.0, "refrigeration"),
        _equipment_row(35, "折箱机", "", 2, None, None, 12.0, 24.0, "production"),
        _equipment_row(36, "枕式包装机", "", 2, None, None, 12.5, 25.0, "production"),
        _equipment_row(37, "包装流水线", "", 2, None, None, 7.5, 15.0, "production"),
        _equipment_row(38, "筐桶清洗机", "", 2, None, None, 20.0, 40.0, "production"),
        _equipment_row(39, "贴标机", "", 2, None, None, 5.0, 10.0, "production"),
        _equipment_row(40, "光电分选设备", "", 1, None, None, 65.0, 65.0, "production"),
        _equipment_row(41, "定量包装设备", "", 3, None, None, 15.0, 45.0, "production"),
        _equipment_row(42, "辅助铺联设备", "", 1, None, None, 40.0, 40.0, "production"),
        _equipment_row(43, "空压机", "", 1, None, None, 22.0, 22.0, "production"),
        _equipment_row(44, "熏蒸设备", "", 2, None, None, 15.0, 30.0, "production"),
    ]


def _equipment_row(
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


def _scale_power_row(row: dict[str, Any], scale: float) -> dict[str, Any]:
    return {
        **row,
        "quantity": _scale_value(row["quantity"], scale),
        "defrost_total_power_kw": _scale_optional(row["defrost_total_power_kw"], scale),
        "total_power_kw": _scale_value(row["total_power_kw"], scale),
    }


def _scale_optional(value: object, scale: float) -> float | None:
    if value is None:
        return None
    return _scale_value(value, scale)


def _scale_value(value: object, scale: float) -> float:
    scaled = _number(value) * scale
    rounded = round(scaled, 2)
    if rounded.is_integer():
        return int(rounded)
    return rounded


def _optional_number(value: object) -> float:
    if value is None:
        return 0
    return _number(value)
