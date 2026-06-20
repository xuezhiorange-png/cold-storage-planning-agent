from dataclasses import dataclass

from cold_storage.modules.calculations.domain.coefficients import CalculationCoefficient


@dataclass(frozen=True)
class ThroughputInput:
    daily_inbound_mass_kg: float
    working_time_h_per_day: float
    utilization_factor: float


@dataclass(frozen=True)
class InventoryInput:
    daily_inbound_mass_kg: float
    storage_days: float
    reserve_factor: float


@dataclass(frozen=True)
class StorageCapacityInput:
    maximum_design_inventory_kg: float
    effective_volume_loading_kg_m3: CalculationCoefficient
    volume_utilization_factor: CalculationCoefficient
    clear_height_m: float


@dataclass(frozen=True)
class PrecoolingInput:
    daily_inbound_mass_kg: float
    precooling_required_ratio: float
    batch_product_mass_kg: float
    cooling_duration_h: float
    loading_duration_h: float
    unloading_duration_h: float
    working_time_h_per_day: float
    positions_per_room: int
    product_mass_per_position_kg: float
    equipment_utilization_factor: float
    precooling_reserve_factor: float


@dataclass(frozen=True)
class RoomAreaInput:
    maximum_design_inventory_kg: float
    product_mass_per_position_kg: float
    pallet_length_m: float
    pallet_width_m: float
    main_aisle_width_m: float
    secondary_aisle_width_m: float
    wall_clearance_m: float
    equipment_exclusion_area_m2: float
    operation_redundancy_factor: CalculationCoefficient


@dataclass(frozen=True)
class CoolingLoadInput:
    product_mass_kg: float
    inbound_product_temperature_c: float | None
    target_product_temperature_c: float | None
    product_specific_heat_kj_kg_k: CalculationCoefficient | None
    cooling_time_h: float | None
    envelope_heat_transfer_kw: float | None = None
    packaging_load_kw: float | None = None
    infiltration_load_kw: float | None = None
    personnel_load_kw: float | None = None
    lighting_load_kw: float | None = None
    evaporator_fan_load_kw: float | None = None
    defrost_additional_load_kw: float | None = None
    other_configuration_load_kw: float | None = None
    safety_margin_factor: CalculationCoefficient | None = None


@dataclass(frozen=True)
class EquipmentRequirementInput:
    total_cooling_load_kw: float
    evaporator_count: int
    redundancy_factor: CalculationCoefficient
    evaporation_temperature_c: float
    condensing_temperature_c: float
    defrost_method: str
