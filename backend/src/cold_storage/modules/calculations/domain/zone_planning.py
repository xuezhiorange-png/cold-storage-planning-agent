from dataclasses import asdict, dataclass
from math import ceil

from cold_storage.modules.calculations.domain.result import (
    CalculationError,
    CalculationResult,
    CalculationWarning,
    FormulaReference,
)

VERSION = "1.0.0"


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
    raw_storage_ratio: float = 0.40
    raw_fruit_pallet_weight_kg: float = 220
    finished_goods_pallet_weight_kg: float = 400
    frozen_goods_pallet_weight_kg: float = 600
    secondary_fruit_area_ratio: float = 0.80
    pallet_length_m: float = 1.2
    pallet_width_m: float = 1.0
    pallet_longitudinal_gap_m: float = 0.3
    storage_area_factor: float = 1.2
    precooling_position_area_m2: float = 5.6
    packing_pieces_per_person_hour: float = 15
    packing_weight_per_piece_kg: float = 1.5
    packing_working_hours_per_day: float = 16
    workers_per_packing_table: float = 3
    packing_table_horizontal_spacing_m: float = 5.5
    packing_table_vertical_spacing_m: float = 3.5
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
                "包含通道和操作冗余的演示面积指标",
            ),
            "primary_precooling_area_loading": DemoZoneCoefficient(
                "primary_precooling_area_loading",
                "一级预冷间单位面积日处理量",
                620,
                "kg/day/m2",
                "8~10℃预冷段演示面积指标",
            ),
            "secondary_precooling_area_loading": DemoZoneCoefficient(
                "secondary_precooling_area_loading",
                "二级预冷间单位面积日处理量",
                550,
                "kg/day/m2",
                "1~3℃预冷段演示面积指标",
            ),
            "sorting_area_loading": DemoZoneCoefficient(
                "sorting_area_loading",
                "分选包装间单位面积日处理量",
                420,
                "kg/day/m2",
                "8~10℃分选包装演示面积指标",
            ),
            "coating_area_loading": DemoZoneCoefficient(
                "coating_area_loading",
                "覆膜间单位面积日处理量",
                500,
                "kg/day/m2",
                "1~3℃覆膜作业演示面积指标",
            ),
            "storage_area_loading": DemoZoneCoefficient(
                "storage_area_loading",
                "成品间单位面积储量",
                216,
                "kg/m2",
                "由演示有效容积储量、净高和利用系数折算",
            ),
            "secondary_fruit_ratio": DemoZoneCoefficient(
                "secondary_fruit_ratio",
                "次果比例",
                0.08,
                "ratio",
                "按日处理量估算次果暂存量的演示比例",
            ),
            "secondary_fruit_area_loading": DemoZoneCoefficient(
                "secondary_fruit_area_loading",
                "次果暂存单位面积承载量",
                220,
                "kg/m2",
                "8~10℃次果暂存演示面积指标",
            ),
            "frozen_fruit_ratio": DemoZoneCoefficient(
                "frozen_fruit_ratio",
                "冻果比例",
                0.05,
                "ratio",
                "按日处理量估算冻果量的演示比例",
            ),
            "frozen_storage_days": DemoZoneCoefficient(
                "frozen_storage_days",
                "冻果暂存天数",
                14,
                "day",
                "冻果间演示库存天数",
            ),
            "frozen_area_loading": DemoZoneCoefficient(
                "frozen_area_loading",
                "冻果间单位面积储量",
                320,
                "kg/m2",
                "-18℃冻果间演示面积指标",
            ),
            "office_area_per_t_day": DemoZoneCoefficient(
                "office_area_per_t_day",
                "办公室单位日处理吨位面积",
                1.2,
                "m2/(t/day)",
                "按产能粗估办公面积的演示指标",
            ),
            "changing_area_per_t_day": DemoZoneCoefficient(
                "changing_area_per_t_day",
                "更衣室单位日处理吨位面积",
                0.8,
                "m2/(t/day)",
                "按产能粗估更衣面积的演示指标",
            ),
            "packaging_area_per_t_day": DemoZoneCoefficient(
                "packaging_area_per_t_day",
                "包材库单位吨日库存面积",
                0.6685,
                "m2/(t/day*day)",
                "按日处理吨位和包材库存天数粗估包材库面积的演示指标",
            ),
            "precooling_position_daily_capacity_kg": DemoZoneCoefficient(
                "precooling_position_daily_capacity_kg",
                "预冷板位单位日处理量",
                1250,
                "kg/day/position",
                "预冷间板位数量演示指标",
            ),
            "storage_position_capacity_kg": DemoZoneCoefficient(
                "storage_position_capacity_kg",
                "存储板位单位容量",
                500,
                "kg/position",
                "存储区域板位数量演示指标",
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

        design_daily_mass = data.daily_inbound_mass_kg
        raw_storage_mass = data.daily_inbound_mass_kg * data.raw_storage_ratio
        finished_storage_mass = data.daily_inbound_mass_kg * data.finished_storage_days
        frozen_daily_mass = data.daily_inbound_mass_kg * data.frozen_fruit_ratio
        frozen_storage_mass = frozen_daily_mass * data.frozen_storage_days
        storage_position_area = self._storage_position_area_m2(data)
        frozen_position_count = ceil(frozen_storage_mass / data.frozen_goods_pallet_weight_kg)
        frozen_area = frozen_position_count * storage_position_area
        packaging_positions = self._packaging_position_count(data)

        zones = [
            self._support_zone(
                "office",
                "办公室",
                "常温",
                "生产管理、品控记录、访客和日常办公",
                data.office_fixed_area_m2,
                data.daily_inbound_mass_kg,
                "office_area_per_t_day",
            ),
            self._support_zone(
                "changing_room",
                "更衣室",
                "常温",
                "人员更衣、洗手消毒和进入洁净作业区缓冲",
                data.changing_fixed_area_m2,
                data.daily_inbound_mass_kg,
                "changing_area_per_t_day",
            ),
            self._precooling_zone(
                "primary_precooling_room",
                "一级预冷间",
                "8~10℃",
                "田间热初步去除，承接原果入厂后第一段降温",
                data.daily_inbound_mass_kg,
                data.primary_precooling_pallet_weight_kg,
                data.primary_precooling_hours_per_pallet,
                data.primary_precooling_working_hours_per_day,
                data.precooling_position_area_m2,
            ),
            self._precooling_zone(
                "secondary_precooling_room",
                "二级预冷间",
                "1~3℃",
                "进入低温链前的二段降温和温度均衡",
                data.daily_inbound_mass_kg,
                data.secondary_precooling_pallet_weight_kg,
                data.secondary_precooling_hours_per_pallet,
                data.secondary_precooling_working_hours_per_day,
                data.precooling_position_area_m2,
            ),
            self._pallet_storage_zone(
                "raw_fruit_buffer",
                "原果暂存间",
                "8~10℃",
                "原果短时暂存，平衡收货与预冷节拍",
                design_daily_mass,
                raw_storage_mass,
                data.raw_fruit_pallet_weight_kg,
                storage_position_area,
                "raw_area_loading",
            ),
            self._packing_zone(
                "sorting_packaging_room",
                "分选包装间",
                "8~10℃",
                "分选、称重、包装和在线周转",
                data.daily_inbound_mass_kg,
                data,
            ),
            self._support_zone(
                "coating_room",
                "覆膜间",
                "1~3℃",
                "覆膜作业和覆膜后低温缓冲",
                data.coating_fixed_area_m2,
                data.daily_inbound_mass_kg,
                "coating_area_loading",
            ),
            self._pallet_storage_zone(
                "finished_goods_room",
                "成品间",
                "1~3℃",
                "成品周转储存，按库存天数配置",
                data.daily_inbound_mass_kg,
                finished_storage_mass,
                data.finished_goods_pallet_weight_kg,
                storage_position_area,
                "storage_area_loading",
            ),
            self._area_ratio_zone(
                "secondary_fruit_buffer",
                "次果暂存间",
                "8~10℃",
                "次果临时存放和后续处置等待",
                frozen_daily_mass,
                frozen_storage_mass * data.secondary_fruit_area_ratio,
                frozen_area * data.secondary_fruit_area_ratio,
                "secondary_fruit_area_loading",
            ),
            self._pallet_storage_zone(
                "frozen_fruit_room",
                "冻果间",
                "-18℃",
                "冻果库存和冻结品低温储存",
                frozen_daily_mass,
                frozen_storage_mass,
                data.frozen_goods_pallet_weight_kg,
                storage_position_area,
                "frozen_area_loading",
            ),
            self._packaging_material_zone(
                "packaging_material_storage",
                "包材库",
                "常温",
                "包装材料、纸箱、托盘和辅料存放",
                data.daily_inbound_mass_kg,
                packaging_positions,
                self._pallet_base_area_m2(data) * data.packaging_area_factor,
            ),
        ]
        total_area = sum(self._number(zone["required_area_m2"]) for zone in zones)
        return CalculationResult(
            success=True,
            calculator_name="cold_room_zone_plan",
            calculator_version=VERSION,
            input=asdict(data),
            result={
                "daily_inbound_mass_kg": data.daily_inbound_mass_kg,
                "design_daily_mass_kg": design_daily_mass,
                "total_required_area_m2": round(total_area, 2),
                "total_area_m2": round(total_area, 2),
                "planning_parameters": {
                    "raw_storage_ratio": data.raw_storage_ratio,
                    "finished_storage_days": data.finished_storage_days,
                    "main_packaging_storage_days": data.main_packaging_storage_days,
                    "auxiliary_packaging_storage_days": data.auxiliary_packaging_storage_days,
                    "primary_precooling_pallet_weight_kg": (
                        data.primary_precooling_pallet_weight_kg
                    ),
                    "primary_precooling_hours_per_pallet": (
                        data.primary_precooling_hours_per_pallet
                    ),
                    "primary_precooling_working_hours_per_day": (
                        data.primary_precooling_working_hours_per_day
                    ),
                    "secondary_precooling_pallet_weight_kg": (
                        data.secondary_precooling_pallet_weight_kg
                    ),
                    "secondary_precooling_hours_per_pallet": (
                        data.secondary_precooling_hours_per_pallet
                    ),
                    "secondary_precooling_working_hours_per_day": (
                        data.secondary_precooling_working_hours_per_day
                    ),
                    "pallet_base_area_m2": round(self._pallet_base_area_m2(data), 4),
                    "storage_area_factor": data.storage_area_factor,
                    "precooling_position_area_m2": data.precooling_position_area_m2,
                    "packing_area_factor": data.packing_area_factor,
                    "packaging_area_factor": data.packaging_area_factor,
                    "frozen_fruit_ratio": data.frozen_fruit_ratio,
                    "frozen_storage_days": data.frozen_storage_days,
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
                    "storage_mass / demo_area_loading",
                    "按区域承载指标折算面积",
                ),
            ],
            coefficients=[item.to_reference() for item in self._coefficients.values()],
            assumptions=[
                "仅已知产量时，V1 使用演示暂存小时数和演示面积承载指标生成概念规划。",
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
        position_area_m2: float,
    ) -> dict[str, object]:
        hourly_capacity = pallet_weight_kg / hours_per_pallet
        daily_capacity = hourly_capacity * working_hours_per_day
        raw_position_count = ceil(daily_throughput_kg_day / daily_capacity)
        position_count = self._round_precooling_positions(raw_position_count)
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
            "position_count": position_count,
            "required_area_m2": round(position_count * position_area_m2, 2),
            "requires_review": True,
        }

    def _pallet_storage_zone(
        self,
        zone_code: str,
        zone_name: str,
        temperature_band: str,
        function: str,
        daily_throughput_kg_day: float,
        design_storage_mass_kg: float,
        pallet_weight_kg: float,
        position_area_m2: float,
        loading_code: str,
    ) -> dict[str, object]:
        position_count = ceil(design_storage_mass_kg / pallet_weight_kg)
        return {
            "zone_code": zone_code,
            "zone_name": zone_name,
            "temperature_band": temperature_band,
            "function": function,
            "daily_throughput_kg_day": round(daily_throughput_kg_day, 2),
            "design_storage_mass_kg": round(design_storage_mass_kg, 2),
            "pallet_weight_kg": pallet_weight_kg,
            "position_count": position_count,
            "area_basis": self._coefficients[loading_code].to_reference(),
            "required_area_m2": round(position_count * position_area_m2, 2),
            "requires_review": True,
        }

    def _area_ratio_zone(
        self,
        zone_code: str,
        zone_name: str,
        temperature_band: str,
        function: str,
        daily_throughput_kg_day: float,
        design_storage_mass_kg: float,
        required_area_m2: float,
        loading_code: str,
    ) -> dict[str, object]:
        return {
            "zone_code": zone_code,
            "zone_name": zone_name,
            "temperature_band": temperature_band,
            "function": function,
            "daily_throughput_kg_day": round(daily_throughput_kg_day, 2),
            "design_storage_mass_kg": round(design_storage_mass_kg, 2),
            "position_count": 0,
            "area_basis": self._coefficients[loading_code].to_reference(),
            "required_area_m2": round(required_area_m2, 2),
            "requires_review": True,
        }

    def _packing_zone(
        self,
        zone_code: str,
        zone_name: str,
        temperature_band: str,
        function: str,
        daily_throughput_kg_day: float,
        data: ColdRoomZonePlanInput,
    ) -> dict[str, object]:
        person_daily_capacity = (
            data.packing_pieces_per_person_hour
            * data.packing_weight_per_piece_kg
            * data.packing_working_hours_per_day
        )
        worker_count = ceil(daily_throughput_kg_day / person_daily_capacity)
        table_count = ceil(worker_count / data.workers_per_packing_table)
        table_area = data.packing_table_horizontal_spacing_m * data.packing_table_vertical_spacing_m
        required_area = table_count * table_area * data.packing_area_factor
        return {
            "zone_code": zone_code,
            "zone_name": zone_name,
            "temperature_band": temperature_band,
            "function": function,
            "daily_throughput_kg_day": round(daily_throughput_kg_day, 2),
            "design_storage_mass_kg": 0,
            "worker_count": worker_count,
            "table_count": table_count,
            "position_count": 0,
            "person_daily_capacity_kg_day": round(person_daily_capacity, 2),
            "packing_table_area_m2": round(table_area, 2),
            "required_area_m2": round(required_area, 2),
            "requires_review": True,
        }

    def _packaging_material_zone(
        self,
        zone_code: str,
        zone_name: str,
        temperature_band: str,
        function: str,
        daily_throughput_kg_day: float,
        position_count: int,
        position_area_m2: float,
    ) -> dict[str, object]:
        return {
            "zone_code": zone_code,
            "zone_name": zone_name,
            "temperature_band": temperature_band,
            "function": function,
            "daily_throughput_kg_day": round(daily_throughput_kg_day, 2),
            "design_storage_mass_kg": 0,
            "position_count": position_count,
            "required_area_m2": round(position_count * position_area_m2, 2),
            "requires_review": True,
        }

    def _storage_zone(
        self,
        zone_code: str,
        zone_name: str,
        temperature_band: str,
        function: str,
        daily_throughput_kg_day: float,
        design_storage_mass_kg: float,
        loading_code: str,
        storage_position_capacity_kg: float,
    ) -> dict[str, object]:
        required_area = design_storage_mass_kg / self._value(loading_code)
        return {
            "zone_code": zone_code,
            "zone_name": zone_name,
            "temperature_band": temperature_band,
            "function": function,
            "daily_throughput_kg_day": round(daily_throughput_kg_day, 2),
            "design_storage_mass_kg": round(design_storage_mass_kg, 2),
            "position_count": ceil(round(design_storage_mass_kg, 2) / storage_position_capacity_kg),
            "area_basis": self._coefficients[loading_code].to_reference(),
            "required_area_m2": round(required_area, 2),
            "requires_review": True,
        }

    def _throughput_zone(
        self,
        zone_code: str,
        zone_name: str,
        temperature_band: str,
        function: str,
        daily_throughput_kg_day: float,
        loading_code: str,
        precooling_position_daily_capacity_kg: float,
    ) -> dict[str, object]:
        required_area = daily_throughput_kg_day / self._value(loading_code)
        return {
            "zone_code": zone_code,
            "zone_name": zone_name,
            "temperature_band": temperature_band,
            "function": function,
            "daily_throughput_kg_day": round(daily_throughput_kg_day, 2),
            "design_storage_mass_kg": 0,
            "position_count": self._throughput_position_count(
                zone_code,
                daily_throughput_kg_day,
                precooling_position_daily_capacity_kg,
            ),
            "area_basis": self._coefficients[loading_code].to_reference(),
            "required_area_m2": round(required_area, 2),
            "requires_review": True,
        }

    def _support_zone(
        self,
        zone_code: str,
        zone_name: str,
        temperature_band: str,
        function: str,
        required_area_m2: float,
        served_throughput_kg_day: float,
        loading_code: str,
    ) -> dict[str, object]:
        return {
            "zone_code": zone_code,
            "zone_name": zone_name,
            "temperature_band": temperature_band,
            "function": function,
            "daily_throughput_kg_day": round(served_throughput_kg_day, 2),
            "design_storage_mass_kg": 0,
            "position_count": 0,
            "area_basis": self._coefficients[loading_code].to_reference(),
            "required_area_m2": round(required_area_m2, 2),
            "requires_review": True,
        }

    def _value(self, code: str) -> float:
        return self._coefficients[code].value

    def _throughput_position_count(
        self,
        zone_code: str,
        daily_throughput_kg_day: float,
        precooling_position_daily_capacity_kg: float,
    ) -> int:
        if "precooling" not in zone_code:
            return 0
        return ceil(daily_throughput_kg_day / precooling_position_daily_capacity_kg)

    def _pallet_base_area_m2(self, data: ColdRoomZonePlanInput) -> float:
        return data.pallet_length_m * (data.pallet_width_m + data.pallet_longitudinal_gap_m)

    def _storage_position_area_m2(self, data: ColdRoomZonePlanInput) -> float:
        return self._pallet_base_area_m2(data) * data.storage_area_factor

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

    def _round_precooling_positions(self, raw_position_count: int) -> int:
        return min(
            self._round_up_to_multiple(raw_position_count, 6),
            self._round_up_to_multiple(raw_position_count, 8),
        )

    def _round_up_to_multiple(self, value: int, multiple: int) -> int:
        return ceil(value / multiple) * multiple

    def _number(self, value: object) -> float:
        if isinstance(value, int | float):
            return float(value)
        raise TypeError("zone numeric value expected")

    def _first_non_positive(self, values: dict[str, object]) -> str | None:
        for key, value in values.items():
            if isinstance(value, int | float) and value <= 0:
                return key
        return None
