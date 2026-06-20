# Core Calculation Inventory

> **Audit Date:** 2026-06-20  
> **Codebase Branch:** codex/task-4-core-calculations  
> **Calculator Version:** 1.0.0  
> **Status:** Complete audit of all deterministic calculations

---

## Table of Contents

1. [Overview](#overview)
2. [Zone Planning Calculator](#zone-planning-calculator)
3. [Investment Estimator](#investment-estimator)
4. [Throughput Calculator](#throughput-calculator)
5. [Inventory Calculator](#inventory-calculator)
6. [Storage Capacity Calculator](#storage-capacity-calculator)
7. [Precooling Calculator](#precooling-calculator)
8. [Room Area Calculator](#room-area-calculator)
9. [Cooling Load Calculator](#cooling-load-calculator)
10. [Equipment Requirement Calculator](#equipment-requirement-calculator)
11. [Power Configuration](#power-configuration)
12. [Regression Baselines](#regression-baselines)
13. [Coefficient Registry](#coefficient-registry)

---

## Overview

All calculations in the Cold Storage Planning Agent are implemented as deterministic Python services. The codebase enforces the following engineering calculation rules:

- Large models must not directly calculate engineering values
- Every calculation result exposes: input, units, formulas, calculator version, coefficients, sources, assumptions, warnings, and review status
- Missing key engineering parameters return explicit errors
- Demo coefficients are marked `source_type=demo`, `validity_status=unverified`, `requires_review=true`

### Calculation Flow

```
Inputs → Validation → Calculation → Result with Metadata
  ↓         ↓              ↓              ↓
User/      Reject ≤0    Apply formulas   Include:
Default    values       with coefficients  - formula_references
values                            - coefficients (source info)
                                  - assumptions
                                  - warnings
                                  - requires_review flag
```

---

## Zone Planning Calculator

### File
`backend/src/cold_storage/modules/calculations/domain/zone_planning.py`

### Calculator Name
`cold_room_zone_plan`

### Version
`1.0.0`

### Input Model
`ColdRoomZonePlanInput` (frozen dataclass)

| Field | Type | Default | Source |
|-------|------|---------|--------|
| `daily_inbound_mass_kg` | float | **required** | User input |
| `working_time_h_per_day` | float | **required** | User input |
| `finished_storage_days` | float | **required** | User input |
| `packaging_storage_days` | float | **required** | User input |
| `precooling_required_ratio` | float | **required** | User input |
| `raw_holding_hours` | float | 6.6666666667 | Hardcoded default |
| `storage_position_capacity_kg` | float | 400 | Hardcoded default |
| `secondary_fruit_ratio` | float | 0.08 | Hardcoded default |
| `frozen_fruit_ratio` | float | 0.10 | Hardcoded default |
| `frozen_storage_days` | float | 5 | Hardcoded default |
| `precooling_position_daily_capacity_kg` | float | 1250 | Hardcoded default |
| `primary_precooling_pallet_weight_kg` | float | 220 | Hardcoded default |
| `primary_precooling_hours_per_pallet` | float | 1 | Hardcoded default |
| `primary_precooling_working_hours_per_day` | float | 6 | Hardcoded default |
| `secondary_precooling_pallet_weight_kg` | float | 400 | Hardcoded default |
| `secondary_precooling_hours_per_pallet` | float | 2 | Hardcoded default |
| `secondary_precooling_working_hours_per_day` | float | 16 | Hardcoded default |
| `raw_storage_ratio` | float | 0.40 | Hardcoded default |
| `raw_fruit_pallet_weight_kg` | float | 220 | Hardcoded default |
| `finished_goods_pallet_weight_kg` | float | 400 | Hardcoded default |
| `frozen_goods_pallet_weight_kg` | float | 600 | Hardcoded default |
| `secondary_fruit_area_ratio` | float | 0.80 | Hardcoded default |
| `pallet_length_m` | float | 1.2 | Hardcoded default |
| `pallet_width_m` | float | 1.0 | Hardcoded default |
| `pallet_longitudinal_gap_m` | float | 0.3 | Hardcoded default |
| `storage_area_factor` | float | 1.2 | Hardcoded default |
| `precooling_position_area_m2` | float | 5.6 | Hardcoded default |
| `packing_pieces_per_person_hour` | float | 15 | Hardcoded default |
| `packing_weight_per_piece_kg` | float | 1.5 | Hardcoded default |
| `packing_working_hours_per_day` | float | 16 | Hardcoded default |
| `workers_per_packing_table` | float | 3 | Hardcoded default |
| `packing_table_horizontal_spacing_m` | float | 5.5 | Hardcoded default |
| `packing_table_vertical_spacing_m` | float | 3.5 | Hardcoded default |
| `packing_area_factor` | float | 1.5 | Hardcoded default |
| `main_packaging_storage_days` | float | 3 | Hardcoded default |
| `auxiliary_packaging_storage_days` | float | 30 | Hardcoded default |
| `packaging_area_factor` | float | 1.5 | Hardcoded default |
| `office_fixed_area_m2` | float | 60 | Hardcoded default |
| `changing_fixed_area_m2` | float | 100 | Hardcoded default |
| `coating_fixed_area_m2` | float | 120 | Hardcoded default |

### Output
`CalculationResult` with `result` containing:
- `daily_inbound_mass_kg`: float
- `design_daily_mass_kg`: float
- `total_required_area_m2`: float (rounded to 2 decimals)
- `total_area_m2`: float (rounded to 2 decimals)
- `planning_parameters`: dict with key input values
- `zones`: list of zone dicts

### Formula References
| ID | Expression | Description |
|----|------------|-------------|
| ZP-001 | `daily_mass` | 日处理量 (Daily throughput) |
| ZP-002 | `storage_mass / demo_area_loading` | 按区域承载指标折算面积 (Area from loading indicator) |

### Zone Calculations

#### 1. Support Zones (Office, Changing Room, Coating Room)
**Method:** `_support_zone()`
- `required_area_m2` = fixed area from input (no calculation)
- `position_count` = 0

#### 2. Precooling Zones (Primary, Secondary)
**Method:** `_precooling_zone()`

**Formulas:**
```
hourly_capacity = pallet_weight_kg / hours_per_pallet
daily_capacity = hourly_capacity * working_hours_per_day
raw_position_count = ceil(daily_throughput_kg_day / daily_capacity)
position_count = round_up_to_multiple(raw_position_count, min(6, 8))
required_area_m2 = position_count * precooling_position_area_m2
```

**Rounding:**
- `raw_position_count`: `math.ceil()`
- `position_count`: `ceil(raw / 6) * 6` and `ceil(raw / 8) * 8`, take minimum
- `required_area_m2`: `round(..., 2)`

**Demo Values (25 t/day):**
- Primary: hourly_capacity=220, daily_capacity=1320, raw_positions=19, positions=24, area=134.4
- Secondary: hourly_capacity=200, daily_capacity=3200, raw_positions=8, positions=8, area=44.8

#### 3. Pallet Storage Zones (Raw Fruit, Finished Goods, Frozen Fruit)
**Method:** `_pallet_storage_zone()`

**Formulas:**
```
position_count = ceil(design_storage_mass_kg / pallet_weight_kg)
storage_position_area_m2 = pallet_length_m * (pallet_width_m + pallet_longitudinal_gap_m) * storage_area_factor
required_area_m2 = position_count * storage_position_area_m2
```

**Coefficients:**
- `raw_area_loading`: 240 kg/m² (demo)
- `storage_area_loading`: 216 kg/m² (demo)
- `frozen_area_loading`: 320 kg/m² (demo)

**Rounding:**
- `position_count`: `math.ceil()`
- `required_area_m2`: `round(..., 2)`

**Demo Values (25 t/day):**
- Raw Fruit Buffer: design_storage=10000 kg, positions=46, area=86.11
- Finished Goods: design_storage=62500 kg, positions=157, area=293.9
- Frozen Fruit: design_storage=12500 kg, positions=21, area=39.31

#### 4. Packing Zone (Sorting & Packaging)
**Method:** `_packing_zone()`

**Formulas:**
```
person_daily_capacity = pieces_per_person_hour * weight_per_piece_kg * working_hours_per_day
worker_count = ceil(daily_throughput_kg_day / person_daily_capacity)
table_count = ceil(worker_count / workers_per_packing_table)
table_area = horizontal_spacing * vertical_spacing
required_area_m2 = table_count * table_area * packing_area_factor
```

**Rounding:**
- `worker_count`: `math.ceil()`
- `table_count`: `math.ceil()`
- `required_area_m2`: `round(..., 2)`

**Demo Values (25 t/day):**
- person_daily_capacity=360 kg, worker_count=70, table_count=24, table_area=19.25, area=693.0

#### 5. Area Ratio Zone (Secondary Fruit Buffer)
**Method:** `_area_ratio_zone()`

**Formulas:**
```
required_area_m2 = frozen_area * secondary_fruit_area_ratio
```

**Demo Values (25 t/day):**
- area=31.45

#### 6. Packaging Material Zone
**Method:** `_packaging_material_zone()`

**Formulas:**
```
pallet_base_area = pallet_length_m * (pallet_width_m + pallet_longitudinal_gap_m)
position_area_m2 = pallet_base_area * packaging_area_factor
required_area_m2 = position_count * position_area_m2
```

**Packaging Position Count:**
```python
main_coefficients = [
    1 / (1.5 * 1600 * 2),    # ~0.0002083
    1 / (125 * 16 * 2),      # ~0.00025
    1 / (360 * 20),           # ~0.0001389
    1 / (360 * 60),           # ~0.0000463
    0.3 / 12000,              # ~0.000025
]
auxiliary_coefficients = [
    4 / (360 * 1450),         # ~0.00000769
    3 / (360 * 250 * 2),     # ~0.00001667
    1.6 / (360 * 800),       # ~0.00000556
    0.1 / (10 * 300 * 2),    # ~0.00001667
    2 / (360 * 900),         # ~0.00000617
]
raw_positions = daily_inbound_mass_kg * (
    main_packaging_storage_days * sum(main_coefficients)
    + auxiliary_packaging_storage_days * sum(auxiliary_coefficients)
)
position_count = ceil(raw_positions)
```

**Rounding:**
- `position_count`: `math.ceil()`
- `required_area_m2`: `round(..., 2)`

**Demo Values (25 t/day):**
- position_count=90, area=210.6

### Output Rounding Summary
| Field | Rounding | Example |
|-------|----------|---------|
| `total_required_area_m2` | `round(..., 2)` | 1813.57 |
| `total_area_m2` | `round(..., 2)` | 1813.57 |
| Zone `required_area_m2` | `round(..., 2)` | varies |
| Zone `position_count` | `math.ceil()` (integer) | varies |
| Zone `daily_throughput_kg_day` | `round(..., 2)` | 25000.0 |

### Error Handling
- Rejects any input field ≤ 0 with `INVALID_ENGINEERING_INPUT` error
- Returns `CalculationResult(success=False, ...)` with error details

### Warnings
- `DEMO_ASSUMPTIONS_REQUIRE_REVIEW`: Always set for this calculator

---

## Investment Estimator

### File
`backend/src/cold_storage/modules/calculations/domain/investment.py`

### Calculator Name
`investment_estimate`

### Version
`1.0.0`

### Input Model
`InvestmentEstimateInput` (frozen dataclass)

| Field | Type | Source |
|-------|------|--------|
| `total_area_m2` | float | From zone plan result |
| `refrigerated_area_m2` | float | Sum of non-常温 zones |
| `frozen_area_m2` | float | Sum of -18℃ zones |
| `position_count` | int | Sum of all zone positions |
| `total_power_kw` | float | From power configuration |

### Demo Coefficients

| Code | Name | Value | Unit | Notes |
|------|------|-------|------|-------|
| `building_envelope_cost_cny_m2` | 土建及钢结构单价 | 900 | CNY/m² | Per total area + 1000m² |
| `refrigeration_cost_cny_m2` | 冷库制冷设备单价 | 1400 | CNY/m² | Per total area |
| `power_distribution_cost_cny_kw` | 高低压配电单价 | 650 | CNY/kW | Per total power |
| `monitoring_opening_supplies_cny` | 监控及开厂物资固定投资 | 200000 | CNY | Fixed |

### Formulas
```
civil_structure = (total_area_m2 + 1000) * 900
refrigeration = total_area_m2 * 1400
power_distribution = total_power_kw * 650
dormitory_living = 0  # Not implemented
monitoring_opening_supplies = 200000

total_investment_cny = civil_structure + refrigeration + power_distribution
                       + dormitory_living + monitoring_opening_supplies
```

### Rounding
- Each item: `round(..., 2)`
- Total: `round(..., 2)`

### Output
```python
{
    "total_investment_cny": float,
    "items": [
        {"item_name": "土建及钢结构", "amount_cny": float},
        {"item_name": "冷库制冷设备", "amount_cny": float},
        {"item_name": "高低压配电", "amount_cny": float},
        {"item_name": "住宿及生活区", "amount_cny": 0},
        {"item_name": "监控及开厂物资", "amount_cny": float},
    ]
}
```

### Demo Values (Total Area=1813.57, Power=1352.63)
- 土建及钢结构: 2,532,213.00 CNY
- 冷库制冷设备: 2,538,998.00 CNY
- 高低压配电: 879,209.50 CNY
- 住宿及生活区: 0 CNY
- 监控及开厂物资: 200,000.00 CNY
- **Total: 6,150,420.50 CNY**

### Formula References
| ID | Expression | Description |
|----|------------|-------------|
| IE-001 | `area_or_position_quantity * demo_unit_cost` | 按面积和板位数量估算分项投资 |

### Warnings
- `DEMO_INVESTMENT_REQUIRES_REVIEW`: Always set

---

## Throughput Calculator

### File
`backend/src/cold_storage/modules/calculations/domain/service.py`

### Calculator Name
`throughput`

### Version
`1.0.0`

### Input Model
`ThroughputInput` (frozen dataclass)

| Field | Type | Source |
|-------|------|--------|
| `daily_inbound_mass_kg` | float | User input |
| `working_time_h_per_day` | float | User input |
| `utilization_factor` | float | User input (0-1) |

### Formulas
```
average_hourly_throughput_kg_h = daily_inbound_mass_kg / working_time_h_per_day
design_hourly_throughput_kg_h = average / utilization_factor
capacity_margin_ratio = max((design - average) / design, 0)
```

### Rounding
- No explicit rounding (returns raw float)

### Demo Values (25000 kg, 16h, 0.85 utilization)
- `average_hourly_throughput_kg_h`: 1562.5
- `design_hourly_throughput_kg_h`: 1838.235294117647
- `capacity_margin_ratio`: 0.15

### Formula References
| ID | Expression | Description |
|----|------------|-------------|
| TH-001 | `daily_mass / working_hours` | 平均小时处理量 |
| TH-002 | `average / utilization` | 设计小时处理量 |

---

## Inventory Calculator

### File
`backend/src/cold_storage/modules/calculations/domain/service.py`

### Calculator Name
`inventory`

### Version
`1.0.0`

### Input Model
`InventoryInput` (frozen dataclass)

| Field | Type | Source |
|-------|------|--------|
| `daily_inbound_mass_kg` | float | User input |
| `storage_days` | float | User input |
| `reserve_factor` | float | User input (>1.0) |

### Formulas
```
base_inventory_kg = daily_inbound_mass_kg * storage_days
maximum_design_inventory_kg = base * reserve_factor
```

### Rounding
- No explicit rounding

### Formula References
| ID | Expression | Description |
|----|------------|-------------|
| IN-001 | `daily_mass * storage_days` | 基准库存量 |
| IN-002 | `base * reserve` | 最大设计库存量 |

---

## Storage Capacity Calculator

### File
`backend/src/cold_storage/modules/calculations/domain/service.py`

### Calculator Name
`storage_capacity`

### Version
`1.0.0`

### Input Model
`StorageCapacityInput` (frozen dataclass)

| Field | Type | Source |
|-------|------|--------|
| `maximum_design_inventory_kg` | float | From inventory calculator |
| `effective_volume_loading_kg_m3` | CalculationCoefficient | From coefficient registry |
| `volume_utilization_factor` | CalculationCoefficient | From coefficient registry |
| `clear_height_m` | float | User input |

### Formulas
```
effective_storage_volume_m3 = maximum_design_inventory_kg / effective_volume_loading_kg_m3.value
nominal_storage_volume_m3 = effective / volume_utilization_factor.value
preliminary_floor_area_m2 = nominal / clear_height_m
```

### Rounding
- No explicit rounding

### Demo Values (75000 kg, 280 kg/m³, 0.72 ratio, 4.5m height)
- `effective_storage_volume_m3`: 267.85714285714283
- `nominal_storage_volume_m3`: 372.02380952380946
- `preliminary_floor_area_m2`: 82.672

### Formula References
| ID | Expression | Description |
|----|------------|-------------|
| SC-001 | `inventory / loading` | 有效储存容积 |
| SC-002 | `effective / utilization` | 公称容积 |

---

## Precooling Calculator

### File
`backend/src/cold_storage/modules/calculations/domain/service.py`

### Calculator Name
`precooling`

### Version
`1.0.0`

### Input Model
`PrecoolingInput` (frozen dataclass)

| Field | Type | Source |
|-------|------|--------|
| `daily_inbound_mass_kg` | float | User input |
| `precooling_required_ratio` | float | User input (0-1) |
| `batch_product_mass_kg` | float | User input |
| `cooling_duration_h` | float | User input |
| `loading_duration_h` | float | User input |
| `unloading_duration_h` | float | User input |
| `working_time_h_per_day` | float | User input |
| `positions_per_room` | int | User input |
| `product_mass_per_position_kg` | float | User input |
| `equipment_utilization_factor` | float | User input (0-1) |
| `precooling_reserve_factor` | float | User input (>1.0) |

### Formulas
```
daily_precooling_mass_kg = daily_inbound_mass_kg * precooling_required_ratio
complete_cycle_h = cooling_duration_h + loading_duration_h + unloading_duration_h
daily_available_batches = (working_time_h_per_day / complete_cycle_h) * equipment_utilization_factor
concurrent_batches = ceil(daily_precooling_mass_kg * precooling_reserve_factor
                          / batch_product_mass_kg / daily_available_batches)
required_positions = ceil(concurrent_batches * batch_product_mass_kg
                          / product_mass_per_position_kg)
required_precooling_rooms = ceil(required_positions / positions_per_room)
actual_daily_capacity_kg = (rooms * positions_per_room * product_mass_per_position_kg
                            * daily_available_batches)
reserve_capacity_kg = actual_daily_capacity_kg - daily_precooling_mass_kg
```

### Rounding
- `concurrent_batches`: `math.ceil()`
- `required_positions`: `math.ceil()`
- `required_precooling_rooms`: `math.ceil()`

### Formula References
| ID | Expression | Description |
|----|------------|-------------|
| PC-001 | `daily_mass * required_ratio` | 每日需预冷量 |
| PC-002 | `cooling + loading + unloading` | 单批完整周期 |

---

## Room Area Calculator

### File
`backend/src/cold_storage/modules/calculations/domain/service.py`

### Calculator Name
`room_area`

### Version
`1.0.0`

### Input Model
`RoomAreaInput` (frozen dataclass)

| Field | Type | Source |
|-------|------|--------|
| `maximum_design_inventory_kg` | float | From inventory calculator |
| `product_mass_per_position_kg` | float | User input |
| `pallet_length_m` | float | User input |
| `pallet_width_m` | float | User input |
| `main_aisle_width_m` | float | User input |
| `secondary_aisle_width_m` | float | User input |
| `wall_clearance_m` | float | User input |
| `equipment_exclusion_area_m2` | float | User input |
| `operation_redundancy_factor` | CalculationCoefficient | From coefficient registry |

### Formulas
```
pallet_count = ceil(maximum_design_inventory_kg / product_mass_per_position_kg)
goods_net_area_m2 = pallet_count * pallet_length_m * pallet_width_m
main_aisle_area_m2 = main_aisle_width_m * max(pallet_length_m * ceil(pallet_count**0.5), 1)
secondary_aisle_area_m2 = secondary_aisle_width_m * max(pallet_width_m * ceil(pallet_count**0.5), 1)
wall_clearance_area_m2 = wall_clearance_m * 4 * max(pallet_length_m * ceil(pallet_count**0.5), 1)
subtotal = goods + main_aisle + secondary_aisle + wall_clearance + equipment_exclusion
room_internal_total_area_m2 = subtotal * operation_redundancy_factor.value
preliminary_length = total**0.5 * 1.2
preliminary_width = total**0.5 / 1.2
```

### Rounding
- `pallet_count`: `math.ceil()`
- No explicit rounding on area outputs

### Formula References
| ID | Expression | Description |
|----|------------|-------------|
| RA-001 | `area components sum` | 冷间面积分项 |

---

## Cooling Load Calculator

### File
`backend/src/cold_storage/modules/calculations/domain/service.py`

### Calculator Name
`cooling_load`

### Version
`1.0.0`

### Input Model
`CoolingLoadInput` (frozen dataclass)

| Field | Type | Source |
|-------|------|--------|
| `product_mass_kg` | float | User input |
| `inbound_product_temperature_c` | float \| None | User input (required) |
| `target_product_temperature_c` | float \| None | User input (required) |
| `product_specific_heat_kj_kg_k` | CalculationCoefficient \| None | From coefficient registry (required) |
| `cooling_time_h` | float \| None | User input (required) |
| `envelope_heat_transfer_kw` | float \| None | User input (optional, default 0) |
| `packaging_load_kw` | float \| None | User input (optional, default 0) |
| `infiltration_load_kw` | float \| None | User input (optional, default 0) |
| `personnel_load_kw` | float \| None | User input (optional, default 0) |
| `lighting_load_kw` | float \| None | User input (optional, default 0) |
| `evaporator_fan_load_kw` | float \| None | User input (optional, default 0) |
| `defrost_additional_load_kw` | float \| None | User input (optional, default 0) |
| `other_configuration_load_kw` | float \| None | User input (optional, default 0) |
| `safety_margin_factor` | CalculationCoefficient \| None | From coefficient registry (required) |

### Formulas
```
product_sensible_heat_load_kw = (
    product_mass_kg * product_specific_heat_kj_kg_k.value
    * (inbound_product_temperature_c - target_product_temperature_c)
    / cooling_time_h / 3600
)
subtotal = envelope_heat_transfer_load_kw + product_sensible_heat_load_kw
           + packaging_load_kw + infiltration_load_kw + personnel_load_kw
           + lighting_load_kw + evaporator_fan_load_kw
           + defrost_additional_load_kw + other_configuration_load_kw
safety_margin_load_kw = subtotal * (safety_margin_factor.value - 1)
total_cooling_load_kw = subtotal + safety_margin_load_kw
```

### Rounding
- No explicit rounding

### Error Handling
- Returns `MISSING_ENGINEERING_PARAMETER` error if required fields are None

### Formula References
| ID | Expression | Description |
|----|------------|-------------|
| CL-001 | `m*c*dT/t` | 产品显热负荷 |

---

## Equipment Requirement Calculator

### File
`backend/src/cold_storage/modules/calculations/domain/service.py`

### Calculator Name
`equipment`

### Version
`1.0.0`

### Input Model
`EquipmentRequirementInput` (frozen dataclass)

| Field | Type | Source |
|-------|------|--------|
| `total_cooling_load_kw` | float | From cooling load calculator |
| `evaporator_count` | int | User input |
| `redundancy_factor` | CalculationCoefficient | From coefficient registry |
| `evaporation_temperature_c` | float | User input |
| `condensing_temperature_c` | float | User input |
| `defrost_method` | str | User input |

### Formulas
```
evaporator_total_cooling_capacity_kw = total_cooling_load_kw * redundancy_factor.value
single_evaporator_capacity_kw = evaporator_total_cooling_capacity_kw / evaporator_count
compressor_operating_capacity_kw = total_cooling_load_kw
standby_capacity_kw = evaporator_total_cooling_capacity_kw - total_cooling_load_kw
condenser_heat_rejection_capacity_kw = evaporator_total_cooling_capacity_kw * 1.25
```

### Rounding
- No explicit rounding

### Formula References
| ID | Expression | Description |
|----|------------|-------------|
| EQ-001 | `load * redundancy` | 设备能力需求 |

---

## Power Configuration

### File
`backend/src/cold_storage/modules/planning/application/service.py`

### Function
`build_power_configuration()`

### Inputs
- `zones`: list of zone dicts from zone plan
- `daily_inbound_mass_kg`: float
- `total_area_m2`: float (unused in current implementation)

### Formulas
```
scale = daily_inbound_mass_kg / 25000

# Scale all equipment rows by scale factor
equipment_rows = [scale_power_row(row, scale) for row in reference_power_rows()]

# Apply axial fan rule based on precooling positions
axial_fan_quantity = (primary_positions + secondary_positions) * 4
axial_fan_total_power = axial_fan_quantity * 0.55

# Calculate power totals
defrost_simultaneous_power = sum(defrost_total_power for refrigeration rows) * 0.30
running_simultaneous_power = sum(total_power for refrigeration rows) * 0.90
refrigeration_total = defrost_simultaneous_power + running_simultaneous_power
production_total = sum(total_power for production rows) * 0.90
grand_total = refrigeration_total + production_total
```

### Hardcoded Equipment List
Reference equipment list contains 39 items with:
- Sequence numbers, names, areas
- Quantities (some scaled, some fixed)
- Defrost power values
- Running power values
- Section classification (refrigeration/production)

### Scaling
```python
def scale_value(value: object, scale: float) -> float:
    scaled = as_float(value) * scale
    rounded = round(scaled, 2)
    if rounded.is_integer():
        return int(rounded)
    return rounded
```

### Rounding
- `defrost_simultaneous_power`: `round(..., 2)`
- `running_simultaneous_power`: `round(..., 2)`
- `refrigeration_total`: `round(..., 2)`
- `production_total`: `round(..., 2)`
- `grand_total`: `round(..., 2)`
- Each scaled value: `round(..., 2)` with integer conversion if whole number

### Demo Values (25 t/day)
- Axial Fan Quantity: 128 (from (24+8)*4)
- Axial Fan Total Power: 70.4 kW
- Total Installed Power: 1352.63 kW

---

## Regression Baselines

### Demo Scenario (25 t/day blueberry facility)

#### Zone Plan Baseline
```json
{
  "total_area_m2": 1813.57,
  "zones": {
    "办公室": {"area": 60.0, "positions": 0},
    "更衣室": {"area": 100.0, "positions": 0},
    "一级预冷间": {"area": 134.4, "positions": 24},
    "二级预冷间": {"area": 44.8, "positions": 8},
    "原果暂存间": {"area": 86.11, "positions": 46},
    "分选包装间": {"area": 693.0, "positions": 0},
    "覆膜间": {"area": 120.0, "positions": 0},
    "成品间": {"area": 293.9, "positions": 157},
    "次果暂存间": {"area": 31.45, "positions": 0},
    "冻果间": {"area": 39.31, "positions": 21},
    "包材库": {"area": 210.6, "positions": 90}
  }
}
```

#### Power Configuration Baseline
```json
{
  "total_installed_power_kw": 1352.63,
  "axial_fan_quantity": 128,
  "axial_fan_total_power_kw": 70.4
}
```

#### Investment Baseline
```json
{
  "total_investment_cny": 6150420.50,
  "items": {
    "土建及钢结构": 2532213.00,
    "冷库制冷设备": 2538998.00,
    "高低压配电": 879209.50,
    "住宿及生活区": 0,
    "监控及开厂物资": 200000.00
  }
}
```

#### Throughput Baseline
```json
{
  "average_hourly_throughput_kg_h": 1562.5,
  "design_hourly_throughput_kg_h": 1838.235294117647,
  "capacity_margin_ratio": 0.15
}
```

---

## Coefficient Registry

### Zone Planning Coefficients

| Code | Name | Value | Unit | Category |
|------|------|-------|------|----------|
| `raw_holding_hours` | 原果暂存小时数 | 6.6666666667 | h | cold_room_zone_planning |
| `raw_area_loading` | 原果暂存单位面积承载量 | 240 | kg/m² | cold_room_zone_planning |
| `primary_precooling_area_loading` | 一级预冷间单位面积日处理量 | 620 | kg/day/m² | cold_room_zone_planning |
| `secondary_precooling_area_loading` | 二级预冷间单位面积日处理量 | 550 | kg/day/m² | cold_room_zone_planning |
| `sorting_area_loading` | 分选包装间单位面积日处理量 | 420 | kg/day/m² | cold_room_zone_planning |
| `coating_area_loading` | 覆膜间单位面积日处理量 | 500 | kg/day/m² | cold_room_zone_planning |
| `storage_area_loading` | 成品间单位面积储量 | 216 | kg/m² | cold_room_zone_planning |
| `secondary_fruit_ratio` | 次果比例 | 0.08 | ratio | cold_room_zone_planning |
| `secondary_fruit_area_loading` | 次果暂存单位面积承载量 | 220 | kg/m² | cold_room_zone_planning |
| `frozen_fruit_ratio` | 冻果比例 | 0.05 | ratio | cold_room_zone_planning |
| `frozen_storage_days` | 冻果暂存天数 | 14 | day | cold_room_zone_planning |
| `frozen_area_loading` | 冻果间单位面积储量 | 320 | kg/m² | cold_room_zone_planning |
| `office_area_per_t_day` | 办公室单位日处理吨位面积 | 1.2 | m²/(t/day) | cold_room_zone_planning |
| `changing_area_per_t_day` | 更衣室单位日处理吨位面积 | 0.8 | m²/(t/day) | cold_room_zone_planning |
| `packaging_area_per_t_day` | 包材库单位吨日库存面积 | 0.6685 | m²/(t/day*day) | cold_room_zone_planning |
| `precooling_position_daily_capacity_kg` | 预冷板位单位日处理量 | 1250 | kg/day/position | cold_room_zone_planning |
| `storage_position_capacity_kg` | 存储板位单位容量 | 500 | kg/position | cold_room_zone_planning |

### Investment Coefficients

| Code | Name | Value | Unit | Category |
|------|------|-------|------|----------|
| `building_envelope_cost_cny_m2` | 土建及钢结构单价 | 900 | CNY/m² | investment |
| `refrigeration_cost_cny_m2` | 冷库制冷设备单价 | 1400 | CNY/m² | investment |
| `power_distribution_cost_cny_kw` | 高低压配电单价 | 650 | CNY/kW | investment |
| `monitoring_opening_supplies_cny` | 监控及开厂物资固定投资 | 200000 | CNY | investment |

### All Demo Coefficients
- **source_type**: `demo`
- **validity_status**: `unverified`
- **approval_status**: `unverified`
- **requires_review**: `true`
- **source_reference**: `V1演示规划系数，未作为国家标准或企业正式标准`

---

## Notes

### Hardcoded vs Coefficient-Driven

**Zone Planning:** Most inputs have hardcoded defaults in `ColdRoomZonePlanInput`, but the planner also maintains a separate `_coefficients` dict with `DemoZoneCoefficient` objects. Some calculations use input values directly (e.g., `pallet_weight_kg`), while others reference the coefficient dict (e.g., `raw_area_loading`). This dual approach is a noted technical debt.

**Investment:** All unit costs are hardcoded in `InvestmentEstimator._coefficients` dict.

**Power Configuration:** Equipment list and power values are entirely hardcoded in `reference_power_rows()`. Only scaling is dynamic.

### Input Sources

1. **From User/API**: `daily_inbound_mass_kg`, `working_time_h_per_day`, `utilization_factor`, `finished_storage_days`, etc.
2. **From Coefficient Registry**: `effective_volume_loading_kg_m3`, `volume_utilization_factor`, `operation_redundancy_factor`, `product_specific_heat_kj_kg_k`, `safety_margin_factor`, `redundancy_factor`
3. **Hardcoded Defaults**: Most zone planning parameters have defaults in the input dataclass
4. **Hardcoded Constants**: Equipment power values, investment unit costs, packaging material coefficients

### Error Handling Pattern

All calculators follow the same pattern:
1. Validate inputs (reject ≤ 0 for numeric fields)
2. Return `CalculationResult(success=False, ...)` with `CalculationError` on failure
3. On success, return `CalculationResult(success=True, ...)` with full metadata
