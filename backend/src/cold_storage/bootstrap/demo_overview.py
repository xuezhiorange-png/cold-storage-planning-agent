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
from cold_storage.modules.planning.application.service import (
    build_power_configuration,
    zone_number,
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
        zone_number(zone, "required_area_m2")
        for zone in zones
        if isinstance(zone, dict) and zone.get("temperature_band") != "常温"
    )
    frozen_area_m2 = sum(
        zone_number(zone, "required_area_m2")
        for zone in zones
        if isinstance(zone, dict) and zone.get("temperature_band") == "-18℃"
    )
    position_count = sum(int(zone_number(zone, "position_count")) for zone in zones)
    power_configuration = build_power_configuration(zones, 25_000, total_area_m2)
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


def _number(value: object) -> float:
    if isinstance(value, int | float):
        return float(value)
    raise TypeError("numeric value expected")
