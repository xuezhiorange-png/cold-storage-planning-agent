from dataclasses import asdict
from math import ceil
from typing import Any

from cold_storage.modules.calculations.domain.coefficients import CalculationCoefficient
from cold_storage.modules.calculations.domain.inputs import (
    CoolingLoadInput,
    EquipmentRequirementInput,
    InventoryInput,
    PrecoolingInput,
    RoomAreaInput,
    StorageCapacityInput,
    ThroughputInput,
)
from cold_storage.modules.calculations.domain.result import (
    CalculationError,
    CalculationResult,
    CalculationWarning,
    FormulaReference,
)

VERSION = "1.0.0"


class CalculationService:
    def run_throughput(self, data: ThroughputInput) -> CalculationResult:
        invalid = self._first_non_positive(asdict(data))
        if invalid:
            return self._invalid("throughput", asdict(data), invalid)
        average = data.daily_inbound_mass_kg / data.working_time_h_per_day
        design = average / data.utilization_factor
        return CalculationResult(
            success=True,
            calculator_name="throughput",
            calculator_version=VERSION,
            input=asdict(data),
            result={
                "average_hourly_throughput_kg_h": average,
                "design_hourly_throughput_kg_h": design,
                "capacity_margin_ratio": max((design - average) / design, 0),
            },
            formula_references=[
                FormulaReference("TH-001", VERSION, "daily_mass / working_hours", "平均小时处理量"),
                FormulaReference("TH-002", VERSION, "average / utilization", "设计小时处理量"),
            ],
        )

    def run_inventory(self, data: InventoryInput) -> CalculationResult:
        invalid = self._first_non_positive(asdict(data))
        if invalid:
            return self._invalid("inventory", asdict(data), invalid)
        base = data.daily_inbound_mass_kg * data.storage_days
        maximum = base * data.reserve_factor
        return CalculationResult(
            success=True,
            calculator_name="inventory",
            calculator_version=VERSION,
            input=asdict(data),
            result={
                "base_inventory_kg": base,
                "maximum_design_inventory_kg": maximum,
            },
            formula_references=[
                FormulaReference("IN-001", VERSION, "daily_mass * storage_days", "基准库存量"),
                FormulaReference("IN-002", VERSION, "base * reserve", "最大设计库存量"),
            ],
        )

    def run_storage_capacity(self, data: StorageCapacityInput) -> CalculationResult:
        raw = {
            "maximum_design_inventory_kg": data.maximum_design_inventory_kg,
            "effective_volume_loading_kg_m3": data.effective_volume_loading_kg_m3.to_reference(),
            "volume_utilization_factor": data.volume_utilization_factor.to_reference(),
            "clear_height_m": data.clear_height_m,
        }
        invalid = self._first_non_positive(
            {
                "maximum_design_inventory_kg": data.maximum_design_inventory_kg,
                "effective_volume_loading_kg_m3": data.effective_volume_loading_kg_m3.value,
                "volume_utilization_factor": data.volume_utilization_factor.value,
                "clear_height_m": data.clear_height_m,
            }
        )
        if invalid:
            return self._invalid("storage_capacity", raw, invalid)
        effective = data.maximum_design_inventory_kg / data.effective_volume_loading_kg_m3.value
        nominal = effective / data.volume_utilization_factor.value
        area = nominal / data.clear_height_m
        warnings, assumptions, requires_review = self._coefficient_review(
            [data.effective_volume_loading_kg_m3, data.volume_utilization_factor]
        )
        return CalculationResult(
            success=True,
            calculator_name="storage_capacity",
            calculator_version=VERSION,
            input=raw,
            result={
                "effective_storage_volume_m3": effective,
                "nominal_storage_volume_m3": nominal,
                "preliminary_floor_area_m2": area,
                "capacity_margin_ratio": 0,
            },
            formula_references=[
                FormulaReference("SC-001", VERSION, "inventory / loading", "有效储存容积"),
                FormulaReference("SC-002", VERSION, "effective / utilization", "公称容积"),
            ],
            coefficients=[
                data.effective_volume_loading_kg_m3.to_reference(),
                data.volume_utilization_factor.to_reference(),
            ],
            assumptions=assumptions,
            warnings=warnings,
            requires_review=requires_review,
        )

    def run_precooling(self, data: PrecoolingInput) -> CalculationResult:
        invalid = self._first_non_positive(asdict(data))
        if invalid:
            return self._invalid("precooling", asdict(data), invalid)
        required = data.daily_inbound_mass_kg * data.precooling_required_ratio
        cycle = data.cooling_duration_h + data.loading_duration_h + data.unloading_duration_h
        batches_per_day = data.working_time_h_per_day / cycle * data.equipment_utilization_factor
        concurrent_batches = ceil(
            required * data.precooling_reserve_factor / data.batch_product_mass_kg / batches_per_day
        )
        positions = ceil(
            concurrent_batches * data.batch_product_mass_kg / data.product_mass_per_position_kg
        )
        rooms = ceil(positions / data.positions_per_room)
        actual = (
            rooms * data.positions_per_room * data.product_mass_per_position_kg * batches_per_day
        )
        return CalculationResult(
            success=True,
            calculator_name="precooling",
            calculator_version=VERSION,
            input=asdict(data),
            result={
                "daily_precooling_mass_kg": required,
                "batch_product_mass_kg": data.batch_product_mass_kg,
                "complete_cycle_h": cycle,
                "daily_available_batches": batches_per_day,
                "concurrent_batches": concurrent_batches,
                "required_positions": positions,
                "required_precooling_rooms": rooms,
                "actual_daily_capacity_kg": actual,
                "reserve_capacity_kg": actual - required,
            },
            formula_references=[
                FormulaReference("PC-001", VERSION, "daily_mass * required_ratio", "每日需预冷量"),
                FormulaReference(
                    "PC-002", VERSION, "cooling + loading + unloading", "单批完整周期"
                ),
            ],
        )

    def run_room_area(self, data: RoomAreaInput) -> CalculationResult:
        raw = asdict(data)
        invalid = self._first_non_positive(
            {
                "maximum_design_inventory_kg": data.maximum_design_inventory_kg,
                "product_mass_per_position_kg": data.product_mass_per_position_kg,
                "pallet_length_m": data.pallet_length_m,
                "pallet_width_m": data.pallet_width_m,
                "operation_redundancy_factor": data.operation_redundancy_factor.value,
            }
        )
        if invalid:
            return self._invalid("room_area", raw, invalid)
        pallet_count = ceil(data.maximum_design_inventory_kg / data.product_mass_per_position_kg)
        goods_area = pallet_count * data.pallet_length_m * data.pallet_width_m
        main_aisle = data.main_aisle_width_m * max(
            data.pallet_length_m * ceil(pallet_count**0.5), 1
        )
        secondary_aisle = data.secondary_aisle_width_m * max(
            data.pallet_width_m * ceil(pallet_count**0.5), 1
        )
        wall_clearance = (
            data.wall_clearance_m * 4 * max(data.pallet_length_m * ceil(pallet_count**0.5), 1)
        )
        subtotal = (
            goods_area
            + main_aisle
            + secondary_aisle
            + wall_clearance
            + data.equipment_exclusion_area_m2
        )
        total = subtotal * data.operation_redundancy_factor.value
        warnings, assumptions, requires_review = self._coefficient_review(
            [data.operation_redundancy_factor]
        )
        return CalculationResult(
            success=True,
            calculator_name="room_area",
            calculator_version=VERSION,
            input=raw,
            result={
                "goods_net_area_m2": goods_area,
                "main_aisle_area_m2": main_aisle,
                "secondary_aisle_area_m2": secondary_aisle,
                "wall_clearance_area_m2": wall_clearance,
                "equipment_exclusion_area_m2": data.equipment_exclusion_area_m2,
                "operation_redundancy_area_m2": total - subtotal,
                "room_internal_total_area_m2": total,
                "preliminary_length_width_combination": {
                    "length_m": total**0.5 * 1.2,
                    "width_m": total**0.5 / 1.2,
                },
            },
            formula_references=[
                FormulaReference("RA-001", VERSION, "area components sum", "冷间面积分项")
            ],
            coefficients=[data.operation_redundancy_factor.to_reference()],
            assumptions=assumptions,
            warnings=warnings,
            requires_review=requires_review,
        )

    def run_cooling_load(self, data: CoolingLoadInput) -> CalculationResult:
        raw = asdict(data)
        missing = [
            field
            for field in (
                "inbound_product_temperature_c",
                "target_product_temperature_c",
                "product_specific_heat_kj_kg_k",
                "cooling_time_h",
                "safety_margin_factor",
            )
            if getattr(data, field) is None
        ]
        if missing:
            return CalculationResult(
                success=False,
                calculator_name="cooling_load",
                calculator_version=VERSION,
                input=raw,
                result={},
                formula_references=[],
                errors=[
                    CalculationError(
                        "MISSING_ENGINEERING_PARAMETER",
                        "制冷负荷计算缺少必要参数",
                        {"fields": missing},
                    )
                ],
                requires_review=True,
            )
        assert data.product_specific_heat_kj_kg_k is not None
        assert data.safety_margin_factor is not None
        assert data.inbound_product_temperature_c is not None
        assert data.target_product_temperature_c is not None
        assert data.cooling_time_h is not None
        sensible = (
            data.product_mass_kg
            * data.product_specific_heat_kj_kg_k.value
            * (data.inbound_product_temperature_c - data.target_product_temperature_c)
            / data.cooling_time_h
            / 3600
        )
        components = {
            "envelope_heat_transfer_load_kw": data.envelope_heat_transfer_kw or 0,
            "product_sensible_heat_load_kw": sensible,
            "packaging_load_kw": data.packaging_load_kw or 0,
            "infiltration_load_kw": data.infiltration_load_kw or 0,
            "personnel_load_kw": data.personnel_load_kw or 0,
            "lighting_load_kw": data.lighting_load_kw or 0,
            "evaporator_fan_load_kw": data.evaporator_fan_load_kw or 0,
            "defrost_additional_load_kw": data.defrost_additional_load_kw or 0,
            "other_configuration_load_kw": data.other_configuration_load_kw or 0,
        }
        subtotal = sum(components.values())
        margin = subtotal * (data.safety_margin_factor.value - 1)
        warnings, assumptions, requires_review = self._coefficient_review(
            [data.product_specific_heat_kj_kg_k, data.safety_margin_factor]
        )
        return CalculationResult(
            success=True,
            calculator_name="cooling_load",
            calculator_version=VERSION,
            input=raw,
            result={
                **components,
                "safety_margin_load_kw": margin,
                "total_cooling_load_kw": subtotal + margin,
            },
            formula_references=[FormulaReference("CL-001", VERSION, "m*c*dT/t", "产品显热负荷")],
            coefficients=[
                data.product_specific_heat_kj_kg_k.to_reference(),
                data.safety_margin_factor.to_reference(),
            ],
            assumptions=assumptions,
            warnings=warnings,
            requires_review=requires_review,
        )

    def run_equipment_requirement(self, data: EquipmentRequirementInput) -> CalculationResult:
        raw = asdict(data)
        invalid = self._first_non_positive(
            {
                "total_cooling_load_kw": data.total_cooling_load_kw,
                "evaporator_count": data.evaporator_count,
                "redundancy_factor": data.redundancy_factor.value,
            }
        )
        if invalid:
            return self._invalid("equipment", raw, invalid)
        total = data.total_cooling_load_kw * data.redundancy_factor.value
        warnings, assumptions, requires_review = self._coefficient_review([data.redundancy_factor])
        return CalculationResult(
            success=True,
            calculator_name="equipment",
            calculator_version=VERSION,
            input=raw,
            result={
                "evaporator_total_cooling_capacity_kw": total,
                "evaporator_quantity": data.evaporator_count,
                "single_evaporator_capacity_kw": total / data.evaporator_count,
                "compressor_operating_capacity_kw": data.total_cooling_load_kw,
                "standby_capacity_kw": total - data.total_cooling_load_kw,
                "condenser_heat_rejection_capacity_kw": total * 1.25,
                "evaporation_temperature_c": data.evaporation_temperature_c,
                "condensing_temperature_c": data.condensing_temperature_c,
                "defrost_method": data.defrost_method,
                "review_requirement": "仅为能力需求，不代表最终厂家型号或施工图设计",
            },
            formula_references=[
                FormulaReference("EQ-001", VERSION, "load * redundancy", "设备能力需求")
            ],
            coefficients=[data.redundancy_factor.to_reference()],
            assumptions=assumptions,
            warnings=warnings,
            requires_review=requires_review,
        )

    def _invalid(self, name: str, raw: dict[str, Any], field: str) -> CalculationResult:
        return CalculationResult(
            success=False,
            calculator_name=name,
            calculator_version=VERSION,
            input=raw,
            result={},
            formula_references=[],
            errors=[
                CalculationError(
                    "INVALID_ENGINEERING_INPUT",
                    "工程输入必须为正数",
                    {"field": field},
                )
            ],
            requires_review=True,
        )

    def _first_non_positive(self, values: dict[str, Any]) -> str | None:
        for key, value in values.items():
            if isinstance(value, int | float) and value <= 0:
                return key
        return None

    def _coefficient_review(
        self, coefficients: list[CalculationCoefficient]
    ) -> tuple[list[CalculationWarning], list[str], bool]:
        warnings: list[CalculationWarning] = []
        assumptions: list[str] = []
        for coefficient in coefficients:
            if not coefficient.is_approved or coefficient.requires_review:
                assumptions.append(f"{coefficient.code} 使用未审核演示系数，需专业人员复核。")
                warnings.append(
                    CalculationWarning(
                        "COEFFICIENT_REQUIRES_REVIEW",
                        "计算使用了未批准或需复核的系数",
                        {"coefficient_code": coefficient.code},
                    )
                )
        return warnings, assumptions, bool(warnings)
