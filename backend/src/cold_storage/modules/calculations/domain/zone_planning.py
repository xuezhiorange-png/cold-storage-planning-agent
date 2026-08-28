from dataclasses import asdict, dataclass
from math import ceil

from cold_storage.modules.calculations.domain.result import (
    CalculationError,
    CalculationResult,
    CalculationWarning,
    FormulaReference,
)

VERSION = "1.0.0"
FORMULA_AUTHORITY = "POST-V0.9-P4-charles-zone-area-recut"

PALLET_PITCH_ALONG_WALL_M = 1.2
PALLET_PITCH_DEPTH_M = 1.3
ASPECT_RATIO_MIN = 1.67
ASPECT_RATIO_MAX = 2.40
ASPECT_RATIO_TARGET = 2.0

PRIMARY_PRECOOL_Q_D_KG_DAY = 220 * 6
SECONDARY_PRECOOL_Q_D_KG_DAY = 3200
PRECOOL_SIX_POSITION_ROOM_AREA_M2 = 42
PRECOOL_EIGHT_POSITION_ROOM_AREA_M2 = 56
PRECOOL_SIX_POSITIONS_PER_ROOM = 6
PRECOOL_EIGHT_POSITIONS_PER_ROOM = 8

RAW_STORAGE_RATIO = 0.40
RAW_FRUIT_PALLET_WEIGHT_KG = 220
FINISHED_GOODS_PALLET_WEIGHT_KG = 400
FROZEN_GOODS_PALLET_WEIGHT_KG = 600
SECONDARY_FRUIT_RATIO = 0.10
SECONDARY_FRUIT_STORAGE_DAYS = 2
FROZEN_FRUIT_RATIO = 0.10

RAW_AISLE_M = 2.2
STORAGE_ONE_AISLE_M = 3.0

PACKING_TABLE_PITCH_LONG_M = 5.6
PACKING_TABLE_PITCH_SHORT_M = 3.0
SORTING_CLEARANCE_LONG_M = 3.0 + 5.0
SORTING_CLEARANCE_SHORT_M = 3.0 + 4.6
WORKERS_PER_PACKING_TABLE = 3
PERSON_DAILY_CAPACITY_KG = 384

PACKAGING_POSITION_BASE_AREA_M2 = 1.56

SHIPPING_PALLET_WEIGHT_KG = 400
SHIPPING_PALLETS_PER_TRUCK = 16
SHIPPING_TRUCKS_PER_PLATFORM_PER_DAY = 4
SHIPPING_PLATFORM_AREA_M2 = 50

REPORTING_PRECOOL_SCHEME_ID = "6_position"

OFFICE_AREA_BY_BAND_M2 = (60, 80, 100)
CHANGING_AREA_BY_BAND_M2 = (40, 80, 120)
COATING_AREA_BY_BAND_M2 = (80, 120, 200)
PACKAGING_K_BY_BAND = (2.4, 2.3, 2.2)


@dataclass(frozen=True)
class ColdRoomZonePlanInput:
    daily_inbound_mass_kg: float
    working_time_h_per_day: float
    finished_storage_days: float
    packaging_storage_days: float
    precooling_required_ratio: float
    raw_holding_hours: float = 6.6666666667
    storage_position_capacity_kg: float = 400
    secondary_fruit_ratio: float = 0.08
    frozen_fruit_ratio: float = 0.10
    frozen_storage_days: float = 5
    precooling_position_daily_capacity_kg: float = 1250
    primary_precooling_pallet_weight_kg: float = 220
    primary_precooling_hours_per_pallet: float = 1
    primary_precooling_working_hours_per_day: float = 6
    secondary_precooling_pallet_weight_kg: float = 400
    secondary_precooling_hours_per_pallet: float = 2
    secondary_precooling_working_hours_per_day: float = 16
    raw_storage_ratio: float = RAW_STORAGE_RATIO
    raw_fruit_pallet_weight_kg: float = RAW_FRUIT_PALLET_WEIGHT_KG
    finished_goods_pallet_weight_kg: float = FINISHED_GOODS_PALLET_WEIGHT_KG
    frozen_goods_pallet_weight_kg: float = FROZEN_GOODS_PALLET_WEIGHT_KG
    secondary_fruit_area_ratio: float = 0.80
    pallet_length_m: float = PALLET_PITCH_ALONG_WALL_M
    pallet_width_m: float = 1.0
    pallet_longitudinal_gap_m: float = 0.3
    storage_area_factor: float = 1.2
    precooling_position_area_m2: float = 5.6
    packing_pieces_per_person_hour: float = 16
    packing_weight_per_piece_kg: float = 1.5
    packing_working_hours_per_day: float = 16
    workers_per_packing_table: float = WORKERS_PER_PACKING_TABLE
    packing_table_horizontal_spacing_m: float = PACKING_TABLE_PITCH_LONG_M
    packing_table_vertical_spacing_m: float = PACKING_TABLE_PITCH_SHORT_M
    packing_area_factor: float = 1.5
    main_packaging_storage_days: float = 3
    auxiliary_packaging_storage_days: float = 30
    packaging_area_factor: float = 1.5
    office_fixed_area_m2: float = 60
    changing_fixed_area_m2: float = 100
    coating_fixed_area_m2: float = 120


@dataclass(frozen=True)
class DemoZoneCoefficient:
    code: str
    name: str
    value: float
    unit: str
    notes: str

    def to_reference(self) -> dict[str, object]:
        return {
            "code": self.code,
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "category": "cold_room_zone_planning",
            "source_type": "demo",
            "source_reference": "V1演示规划系数，未作为国家标准或企业正式标准",
            "version": "demo-1",
            "validity_status": "unverified",
            "approval_status": "unverified",
            "requires_review": True,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class PackedRectangleLayout:
    n_need: int
    n_long: int
    n_short: int
    n_actual: int
    unused_cells: int
    required_area_m2: float

    def to_dict(self) -> dict[str, object]:
        return {
            "n_need": self.n_need,
            "n_long": self.n_long,
            "n_short": self.n_short,
            "n_actual": self.n_actual,
            "unused_cells": self.unused_cells,
            "layout": {
                "n_long": self.n_long,
                "n_short": self.n_short,
                "aspect_ratio": round(self.n_long / self.n_short, 4) if self.n_short else 0,
            },
            "required_area_m2": round(self.required_area_m2, 2),
        }


class ColdRoomZonePlanner:
    def __init__(self) -> None:
        self._coefficients = {
            "raw_holding_hours": DemoZoneCoefficient(
                "raw_holding_hours",
                "原果暂存小时数",
                6.6666666667,
                "h",
                "按日入库量折算的演示暂存时间",
            ),
            "raw_area_loading": DemoZoneCoefficient(
                "raw_area_loading",
                "原果暂存单位面积承载量",
                240,
                "kg/m2",
                "POST-V0.9 P4 已替代为托盘矩形排布，不再作为面积依据",
            ),
            "primary_precooling_area_loading": DemoZoneCoefficient(
                "primary_precooling_area_loading",
                "一级预冷间单位面积日处理量",
                620,
                "kg/day/m2",
                "POST-V0.9 P4 已替代为双方案模块面积，不再作为面积依据",
            ),
            "secondary_precooling_area_loading": DemoZoneCoefficient(
                "secondary_precooling_area_loading",
                "二级预冷间单位面积日处理量",
                550,
                "kg/day/m2",
                "POST-V0.9 P4 已替代为双方案模块面积，不再作为面积依据",
            ),
            "sorting_area_loading": DemoZoneCoefficient(
                "sorting_area_loading",
                "分选包装间单位面积日处理量",
                420,
                "kg/day/m2",
                "POST-V0.9 P4 已替代为分选台矩形排布，不再作为面积依据",
            ),
            "coating_area_loading": DemoZoneCoefficient(
                "coating_area_loading",
                "覆膜间单位面积日处理量",
                500,
                "kg/day/m2",
                "POST-V0.9 P4 为吨位分档固定面积，不再作为面积依据",
            ),
            "storage_area_loading": DemoZoneCoefficient(
                "storage_area_loading",
                "成品间单位面积储量",
                216,
                "kg/m2",
                "POST-V0.9 P4 已替代为托盘矩形排布，不再作为面积依据",
            ),
            "secondary_fruit_ratio": DemoZoneCoefficient(
                "secondary_fruit_ratio",
                "次果比例",
                0.08,
                "ratio",
                "POST-V0.9 P4 面积使用硬编码 10%，此演示系数仅保留元数据",
            ),
            "secondary_fruit_area_loading": DemoZoneCoefficient(
                "secondary_fruit_area_loading",
                "次果暂存单位面积承载量",
                220,
                "kg/m2",
                "POST-V0.9 P4 已替代为托盘矩形排布，不再作为面积依据",
            ),
            "frozen_fruit_ratio": DemoZoneCoefficient(
                "frozen_fruit_ratio",
                "冻果比例",
                0.05,
                "ratio",
                "POST-V0.9 P4 面积使用硬编码 10%，此演示系数仅保留元数据",
            ),
            "frozen_storage_days": DemoZoneCoefficient(
                "frozen_storage_days",
                "冻果暂存天数",
                14,
                "day",
                "POST-V0.9 P4 面积使用 operator frozen_storage_days KEY",
            ),
            "frozen_area_loading": DemoZoneCoefficient(
                "frozen_area_loading",
                "冻果间单位面积储量",
                320,
                "kg/m2",
                "POST-V0.9 P4 已替代为托盘矩形排布，不再作为面积依据",
            ),
            "office_area_per_t_day": DemoZoneCoefficient(
                "office_area_per_t_day",
                "办公室单位日处理吨位面积",
                1.2,
                "m2/(t/day)",
                "POST-V0.9 P4 为吨位分档固定面积，不再作为面积依据",
            ),
            "changing_area_per_t_day": DemoZoneCoefficient(
                "changing_area_per_t_day",
                "更衣室单位日处理吨位面积",
                0.8,
                "m2/(t/day)",
                "POST-V0.9 P4 为吨位分档固定面积，不再作为面积依据",
            ),
            "packaging_area_per_t_day": DemoZoneCoefficient(
                "packaging_area_per_t_day",
                "包材库单位吨日库存面积",
                0.6685,
                "m2/(t/day*day)",
                "POST-V0.9 P4 已替代为位面积 1.56×k(M_t)",
            ),
            "precooling_position_daily_capacity_kg": DemoZoneCoefficient(
                "precooling_position_daily_capacity_kg",
                "预冷板位单位日处理量",
                1250,
                "kg/day/position",
                "POST-V0.9 P4 已替代为托盘日处理量公式",
            ),
            "storage_position_capacity_kg": DemoZoneCoefficient(
                "storage_position_capacity_kg",
                "存储板位单位容量",
                500,
                "kg/position",
                "POST-V0.9 P4 已替代为各区域托盘重量",
            ),
        }

    def plan(self, data: ColdRoomZonePlanInput) -> CalculationResult:
        invalid = self._first_non_positive(asdict(data))
        if invalid:
            return CalculationResult(
                success=False,
                calculator_name="cold_room_zone_plan",
                calculator_version=VERSION,
                input=asdict(data),
                result={},
                formula_references=[],
                errors=[
                    CalculationError(
                        "INVALID_ENGINEERING_INPUT",
                        "冷间分区规划输入必须为正数",
                        {"field": invalid},
                    )
                ],
                requires_review=True,
            )

        daily_mass = data.daily_inbound_mass_kg
        mass_tons = daily_mass / 1000
        zones = [
            self._fixed_zone(
                "office",
                "办公室",
                "常温",
                "生产管理、品控记录、访客和日常办公",
                self._area_by_throughput_band(mass_tons, OFFICE_AREA_BY_BAND_M2),
                daily_mass,
            ),
            self._fixed_zone(
                "changing_room",
                "更衣室",
                "常温",
                "人员更衣、洗手消毒和进入洁净作业区缓冲",
                self._area_by_throughput_band(mass_tons, CHANGING_AREA_BY_BAND_M2),
                daily_mass,
            ),
            self._precooling_zone(
                "primary_precooling_room",
                "一级预冷间",
                "8~10℃",
                "田间热初步去除，承接原果入厂后第一段降温",
                daily_mass,
                data.primary_precooling_pallet_weight_kg,
                data.primary_precooling_hours_per_pallet,
                data.primary_precooling_working_hours_per_day,
            ),
            self._precooling_zone(
                "secondary_precooling_room",
                "二级预冷间",
                "1~3℃",
                "进入低温链前的二段降温和温度均衡",
                daily_mass,
                data.secondary_precooling_pallet_weight_kg,
                data.secondary_precooling_hours_per_pallet,
                data.secondary_precooling_working_hours_per_day,
            ),
            self._raw_fruit_buffer_zone(data),
            self._sorting_packaging_zone(data),
            self._fixed_zone(
                "coating_room",
                "覆膜间",
                "1~3℃",
                "覆膜作业和覆膜后低温缓冲",
                self._area_by_throughput_band(mass_tons, COATING_AREA_BY_BAND_M2),
                daily_mass,
            ),
            self._finished_goods_zone(data),
            self._secondary_fruit_buffer_zone(data),
            self._frozen_fruit_zone(data),
            self._packaging_material_zone(data, mass_tons),
            self._shipping_channel_zone(daily_mass),
        ]

        total_area_6 = sum(self._number(zone["required_area_m2"]) for zone in zones)
        total_area_8 = self._total_area_with_eight_position_precool(zones)
        packaging_k = self._packaging_area_factor_k(mass_tons)

        return CalculationResult(
            success=True,
            calculator_name="cold_room_zone_plan",
            calculator_version=VERSION,
            input=asdict(data),
            result={
                "daily_inbound_mass_kg": daily_mass,
                "design_daily_mass_kg": daily_mass,
                "total_required_area_m2": round(total_area_6, 2),
                "total_area_m2": round(total_area_6, 2),
                "total_area_m2_8_position_scheme": round(total_area_8, 2),
                "planning_parameters": {
                    "formula_authority": FORMULA_AUTHORITY,
                    "raw_storage_ratio": data.raw_storage_ratio,
                    "finished_storage_days": data.finished_storage_days,
                    "frozen_storage_days": data.frozen_storage_days,
                    "secondary_fruit_ratio_hardcoded": SECONDARY_FRUIT_RATIO,
                    "secondary_fruit_storage_days_hardcoded": SECONDARY_FRUIT_STORAGE_DAYS,
                    "frozen_fruit_ratio_hardcoded": FROZEN_FRUIT_RATIO,
                    "main_packaging_storage_days": data.main_packaging_storage_days,
                    "auxiliary_packaging_storage_days": data.auxiliary_packaging_storage_days,
                    "primary_precooling_q_d_kg_day": round(
                        data.primary_precooling_pallet_weight_kg
                        / data.primary_precooling_hours_per_pallet
                        * data.primary_precooling_working_hours_per_day,
                        2,
                    ),
                    "secondary_precooling_q_d_kg_day": round(
                        data.secondary_precooling_pallet_weight_kg
                        / data.secondary_precooling_hours_per_pallet
                        * data.secondary_precooling_working_hours_per_day,
                        2,
                    ),
                    "packing_person_daily_capacity_kg": PERSON_DAILY_CAPACITY_KG,
                    "packaging_position_area_m2": round(
                        PACKAGING_POSITION_BASE_AREA_M2 * packaging_k,
                        4,
                    ),
                    "packaging_area_factor_k": packaging_k,
                    "reporting_precool_scheme_id": REPORTING_PRECOOL_SCHEME_ID,
                    "dataclass_override_note": (
                        "Non-default dataclass fields override §4 written-dead "
                        "parameters when explicitly supplied; default path matches §4."
                    ),
                },
                "zones": zones,
            },
            formula_references=[
                FormulaReference(
                    "ZP-001",
                    VERSION,
                    "daily_mass",
                    "日处理量",
                ),
                FormulaReference(
                    "ZP-002",
                    VERSION,
                    "packed_rectangle_layout",
                    "托盘/分选台矩形排布面积",
                ),
                FormulaReference(
                    "ZP-003",
                    VERSION,
                    "dual_precooling_schemes",
                    "一级/二级预冷双方案模块",
                ),
            ],
            coefficients=[item.to_reference() for item in self._coefficients.values()],
            assumptions=[
                (
                    "POST-V0.9 P4 Charles 2026-08-28 书面锁定工时与面积公式；"
                    "operator KEY 仅提供 M、成品天数、冻果天数、包材天数。"
                ),
                "所有区域面积为概念设计阶段估算值，需结合工艺、货架、通道、消防和建筑条件复核。",
            ],
            warnings=[
                CalculationWarning(
                    "DEMO_ASSUMPTIONS_REQUIRE_REVIEW",
                    "冷间分区规划使用未审核演示系数，不能作为正式设计依据。",
                    {"requires_review": True},
                )
            ],
            requires_review=True,
        )

    def _area_by_throughput_band(
        self, mass_tons: float, areas: tuple[float, float, float]
    ) -> float:
        if mass_tons < 25:
            return areas[0]
        if mass_tons < 50:
            return areas[1]
        return areas[2]

    def _packaging_area_factor_k(self, mass_tons: float) -> float:
        return self._area_by_throughput_band(mass_tons, PACKAGING_K_BY_BAND)

    def _fixed_zone(
        self,
        zone_code: str,
        zone_name: str,
        temperature_band: str,
        function: str,
        required_area_m2: float,
        daily_throughput_kg_day: float,
    ) -> dict[str, object]:
        return {
            "zone_code": zone_code,
            "zone_name": zone_name,
            "temperature_band": temperature_band,
            "function": function,
            "daily_throughput_kg_day": round(daily_throughput_kg_day, 2),
            "design_storage_mass_kg": 0,
            "position_count": 0,
            "required_area_m2": round(required_area_m2, 2),
            "requires_review": True,
        }

    def _precooling_zone(
        self,
        zone_code: str,
        zone_name: str,
        temperature_band: str,
        function: str,
        daily_throughput_kg_day: float,
        pallet_weight_kg: float,
        hours_per_pallet: float,
        working_hours_per_day: float,
    ) -> dict[str, object]:
        hourly_capacity = pallet_weight_kg / hours_per_pallet
        daily_capacity = hourly_capacity * working_hours_per_day
        raw_position_count = ceil(daily_throughput_kg_day / daily_capacity)
        schemes = self._precooling_schemes(raw_position_count)
        reporting = next(
            scheme for scheme in schemes if scheme["scheme_id"] == REPORTING_PRECOOL_SCHEME_ID
        )
        return {
            "zone_code": zone_code,
            "zone_name": zone_name,
            "temperature_band": temperature_band,
            "function": function,
            "daily_throughput_kg_day": round(daily_throughput_kg_day, 2),
            "design_storage_mass_kg": 0,
            "pallet_weight_kg": pallet_weight_kg,
            "hours_per_pallet": hours_per_pallet,
            "working_hours_per_day": working_hours_per_day,
            "position_hourly_capacity_kg_h": round(hourly_capacity, 2),
            "position_daily_capacity_kg_day": round(daily_capacity, 2),
            "raw_position_count": raw_position_count,
            "n_need": raw_position_count,
            "reporting_scheme_id": REPORTING_PRECOOL_SCHEME_ID,
            "schemes": schemes,
            "position_count": reporting["position_count"],
            "required_area_m2": reporting["required_area_m2"],
            "requires_review": True,
        }

    def _precooling_schemes(self, n_need: int) -> list[dict[str, object]]:
        return [
            self._precooling_scheme(
                "6_position",
                PRECOOL_SIX_POSITIONS_PER_ROOM,
                PRECOOL_SIX_POSITION_ROOM_AREA_M2,
                n_need,
            ),
            self._precooling_scheme(
                "8_position",
                PRECOOL_EIGHT_POSITIONS_PER_ROOM,
                PRECOOL_EIGHT_POSITION_ROOM_AREA_M2,
                n_need,
            ),
        ]

    def _precooling_scheme(
        self,
        scheme_id: str,
        positions_per_room: int,
        room_area_m2: float,
        n_need: int,
    ) -> dict[str, object]:
        room_count = ceil(n_need / positions_per_room) if n_need > 0 else 0
        position_count = room_count * positions_per_room
        return {
            "scheme_id": scheme_id,
            "positions_per_room": positions_per_room,
            "room_count": room_count,
            "position_count": position_count,
            "required_area_m2": round(room_count * room_area_m2, 2),
        }

    def _raw_fruit_buffer_zone(self, data: ColdRoomZonePlanInput) -> dict[str, object]:
        design_storage_mass = data.daily_inbound_mass_kg * data.raw_storage_ratio
        n_need = (
            0
            if design_storage_mass <= 0
            else ceil(design_storage_mass / data.raw_fruit_pallet_weight_kg)
        )
        layout = self._pack_three_side_aisle_rectangle(n_need, RAW_AISLE_M)
        return self._storage_layout_zone(
            zone_code="raw_fruit_buffer",
            zone_name="原果暂存间",
            temperature_band="8~10℃",
            function="原果短时暂存，平衡收货与预冷节拍",
            daily_throughput_kg_day=data.daily_inbound_mass_kg,
            design_storage_mass_kg=design_storage_mass,
            pallet_weight_kg=data.raw_fruit_pallet_weight_kg,
            layout=layout,
            aisle_layout="three_side_2.2m",
        )

    def _finished_goods_zone(self, data: ColdRoomZonePlanInput) -> dict[str, object]:
        design_storage_mass = (
            data.daily_inbound_mass_kg * (1 - FROZEN_FRUIT_RATIO) * data.finished_storage_days
        )
        n_need = (
            0
            if design_storage_mass <= 0
            else ceil(design_storage_mass / data.finished_goods_pallet_weight_kg)
        )
        layout = self._pack_one_long_side_aisle_rectangle(n_need)
        return self._storage_layout_zone(
            zone_code="finished_goods_room",
            zone_name="成品间",
            temperature_band="1~3℃",
            function="成品周转储存，按库存天数配置",
            daily_throughput_kg_day=data.daily_inbound_mass_kg,
            design_storage_mass_kg=design_storage_mass,
            pallet_weight_kg=data.finished_goods_pallet_weight_kg,
            layout=layout,
            aisle_layout="one_long_side_3m",
            frozen_deduction_ratio=FROZEN_FRUIT_RATIO,
        )

    def _secondary_fruit_buffer_zone(self, data: ColdRoomZonePlanInput) -> dict[str, object]:
        design_storage_mass = (
            data.daily_inbound_mass_kg * SECONDARY_FRUIT_RATIO * SECONDARY_FRUIT_STORAGE_DAYS
        )
        n_need = (
            0
            if design_storage_mass <= 0
            else ceil(design_storage_mass / RAW_FRUIT_PALLET_WEIGHT_KG)
        )
        layout = self._pack_one_long_side_aisle_rectangle(n_need)
        return self._storage_layout_zone(
            zone_code="secondary_fruit_buffer",
            zone_name="次果暂存间",
            temperature_band="8~10℃",
            function="次果临时存放和后续处置等待",
            daily_throughput_kg_day=data.daily_inbound_mass_kg,
            design_storage_mass_kg=design_storage_mass,
            pallet_weight_kg=RAW_FRUIT_PALLET_WEIGHT_KG,
            layout=layout,
            aisle_layout="one_long_side_3m",
            secondary_fruit_ratio=SECONDARY_FRUIT_RATIO,
            secondary_fruit_storage_days=SECONDARY_FRUIT_STORAGE_DAYS,
        )

    def _frozen_fruit_zone(self, data: ColdRoomZonePlanInput) -> dict[str, object]:
        design_storage_mass = (
            data.daily_inbound_mass_kg * FROZEN_FRUIT_RATIO * data.frozen_storage_days
        )
        n_need = (
            0
            if design_storage_mass <= 0
            else ceil(design_storage_mass / data.frozen_goods_pallet_weight_kg)
        )
        layout = self._pack_one_long_side_aisle_rectangle(n_need)
        return self._storage_layout_zone(
            zone_code="frozen_fruit_room",
            zone_name="冻果间",
            temperature_band="-18℃",
            function="冻果库存和冻结品低温储存",
            daily_throughput_kg_day=data.daily_inbound_mass_kg * FROZEN_FRUIT_RATIO,
            design_storage_mass_kg=design_storage_mass,
            pallet_weight_kg=data.frozen_goods_pallet_weight_kg,
            layout=layout,
            aisle_layout="one_long_side_3m",
            frozen_fruit_ratio=FROZEN_FRUIT_RATIO,
            frozen_storage_days=data.frozen_storage_days,
        )

    def _storage_layout_zone(
        self,
        *,
        zone_code: str,
        zone_name: str,
        temperature_band: str,
        function: str,
        daily_throughput_kg_day: float,
        design_storage_mass_kg: float,
        pallet_weight_kg: float,
        layout: PackedRectangleLayout,
        aisle_layout: str,
        **extra: object,
    ) -> dict[str, object]:
        zone = {
            "zone_code": zone_code,
            "zone_name": zone_name,
            "temperature_band": temperature_band,
            "function": function,
            "daily_throughput_kg_day": round(daily_throughput_kg_day, 2),
            "design_storage_mass_kg": round(design_storage_mass_kg, 2),
            "pallet_weight_kg": pallet_weight_kg,
            "aisle_layout": aisle_layout,
            "position_count": layout.n_actual,
            "required_area_m2": round(layout.required_area_m2, 2),
            "requires_review": True,
        }
        zone.update(layout.to_dict())
        zone.update(extra)
        return zone

    def _sorting_packaging_zone(self, data: ColdRoomZonePlanInput) -> dict[str, object]:
        worker_count = ceil(data.daily_inbound_mass_kg / PERSON_DAILY_CAPACITY_KG)
        table_count_need = ceil(worker_count / data.workers_per_packing_table)
        layout = self._pack_sorting_rectangle(table_count_need)
        table_area = PACKING_TABLE_PITCH_LONG_M * PACKING_TABLE_PITCH_SHORT_M
        return {
            "zone_code": "sorting_packaging_room",
            "zone_name": "分选包装间",
            "temperature_band": "8~10℃",
            "function": "分选、称重、包装和在线周转",
            "daily_throughput_kg_day": round(data.daily_inbound_mass_kg, 2),
            "design_storage_mass_kg": 0,
            "worker_count": worker_count,
            "table_count": table_count_need,
            "person_daily_capacity_kg_day": PERSON_DAILY_CAPACITY_KG,
            "packing_table_area_m2": round(table_area, 2),
            "aisle_layout": "four_side_architectural",
            "position_count": layout.n_actual,
            "required_area_m2": round(layout.required_area_m2, 2),
            "requires_review": True,
            **layout.to_dict(),
        }

    def _packaging_material_zone(
        self, data: ColdRoomZonePlanInput, mass_tons: float
    ) -> dict[str, object]:
        position_count = self._packaging_position_count(data)
        packaging_k = self._packaging_area_factor_k(mass_tons)
        position_area_m2 = PACKAGING_POSITION_BASE_AREA_M2 * packaging_k
        return {
            "zone_code": "packaging_material_storage",
            "zone_name": "包材库",
            "temperature_band": "常温",
            "function": "包装材料、纸箱、托盘和辅料存放",
            "daily_throughput_kg_day": round(data.daily_inbound_mass_kg, 2),
            "design_storage_mass_kg": 0,
            "position_count": position_count,
            "packaging_position_area_m2": round(position_area_m2, 4),
            "packaging_area_factor_k": packaging_k,
            "required_area_m2": round(position_count * position_area_m2, 2),
            "requires_review": True,
        }

    def _shipping_channel_zone(self, daily_mass_kg: float) -> dict[str, object]:
        pallet_count = ceil(daily_mass_kg / SHIPPING_PALLET_WEIGHT_KG)
        truck_count = ceil(pallet_count / SHIPPING_PALLETS_PER_TRUCK)
        platform_count = ceil(truck_count / SHIPPING_TRUCKS_PER_PLATFORM_PER_DAY)
        required_area_m2 = platform_count * SHIPPING_PLATFORM_AREA_M2
        return {
            "zone_code": "shipping_channel",
            "zone_name": "出货通道",
            "temperature_band": "1~3℃",
            "function": "成品装车出货月台与通道",
            "daily_throughput_kg_day": round(daily_mass_kg, 2),
            "design_storage_mass_kg": 0,
            "pallet_weight_kg": SHIPPING_PALLET_WEIGHT_KG,
            "pallet_count": pallet_count,
            "truck_count": truck_count,
            "platform_count": platform_count,
            "position_count": platform_count,
            "required_area_m2": round(required_area_m2, 2),
            "requires_review": True,
        }

    def _pack_three_side_aisle_rectangle(
        self, n_need: int, aisle_m: float = RAW_AISLE_M
    ) -> PackedRectangleLayout:
        return self._pack_rectangle(
            n_need,
            lambda n_long, n_short: (
                (n_long * PALLET_PITCH_ALONG_WALL_M + aisle_m + aisle_m)
                * (n_short * PALLET_PITCH_DEPTH_M + aisle_m)
            ),
        )

    def _pack_one_long_side_aisle_rectangle(self, n_need: int) -> PackedRectangleLayout:
        return self._pack_rectangle(
            n_need,
            lambda n_long, n_short: (
                (n_long * PALLET_PITCH_ALONG_WALL_M)
                * (n_short * PALLET_PITCH_DEPTH_M + STORAGE_ONE_AISLE_M)
            ),
        )

    def _pack_sorting_rectangle(self, n_need: int) -> PackedRectangleLayout:
        return self._pack_rectangle(
            n_need,
            lambda n_long, n_short: (
                (max(n_long - 1, 0) * PACKING_TABLE_PITCH_LONG_M + SORTING_CLEARANCE_LONG_M)
                * (max(n_short - 1, 0) * PACKING_TABLE_PITCH_SHORT_M + SORTING_CLEARANCE_SHORT_M)
            ),
        )

    def _pack_rectangle(
        self,
        n_need: int,
        area_fn: object,
    ) -> PackedRectangleLayout:
        if n_need <= 0:
            return PackedRectangleLayout(0, 0, 0, 0, 0, 0.0)

        best: tuple[tuple[int, int, float, float], int, int] | None = None
        for n_long in range(1, n_need + 200):
            for n_short in range(1, n_long + 1):
                n_actual = n_long * n_short
                if n_actual < n_need:
                    continue
                ratio = n_long / n_short
                in_band = ASPECT_RATIO_MIN <= ratio <= ASPECT_RATIO_MAX
                unused_cells = n_actual - n_need
                area = float(area_fn(n_long, n_short))  # type: ignore[operator]
                rank = (
                    0 if in_band else 1,
                    unused_cells,
                    abs(ratio - ASPECT_RATIO_TARGET),
                    area,
                )
                if best is None or rank < best[0]:
                    best = (rank, n_long, n_short)

        assert best is not None
        _, n_long, n_short = best
        n_actual = n_long * n_short
        return PackedRectangleLayout(
            n_need=n_need,
            n_long=n_long,
            n_short=n_short,
            n_actual=n_actual,
            unused_cells=n_actual - n_need,
            required_area_m2=float(area_fn(n_long, n_short)),  # type: ignore[operator]
        )

    def _packaging_position_count(self, data: ColdRoomZonePlanInput) -> int:
        main_coefficients = [
            1 / (1.5 * 1600 * 2),
            1 / (125 * 16 * 2),
            1 / (360 * 20),
            1 / (360 * 60),
            0.3 / 12000,
        ]
        auxiliary_coefficients = [
            4 / (360 * 1450),
            3 / (360 * 250 * 2),
            1.6 / (360 * 800),
            0.1 / (10 * 300 * 2),
            2 / (360 * 900),
        ]
        raw_positions = data.daily_inbound_mass_kg * (
            data.main_packaging_storage_days * sum(main_coefficients)
            + data.auxiliary_packaging_storage_days * sum(auxiliary_coefficients)
        )
        return ceil(raw_positions)

    def _total_area_with_eight_position_precool(self, zones: list[dict[str, object]]) -> float:
        total = 0.0
        for zone in zones:
            zone_code = zone["zone_code"]
            if zone_code in {"primary_precooling_room", "secondary_precooling_room"}:
                schemes = zone["schemes"]
                assert isinstance(schemes, list)
                eight_position = next(
                    scheme
                    for scheme in schemes
                    if isinstance(scheme, dict) and scheme.get("scheme_id") == "8_position"
                )
                total += self._number(eight_position["required_area_m2"])
            else:
                total += self._number(zone["required_area_m2"])
        return total

    def _number(self, value: object) -> float:
        if isinstance(value, int | float):
            return float(value)
        raise TypeError("zone numeric value expected")

    def _first_non_positive(self, values: dict[str, object]) -> str | None:
        for key, value in values.items():
            if isinstance(value, int | float) and value <= 0:
                return key
        return None
