# Calculation Rounding Policy

> **Audit Date:** 2026-06-20  
> **Codebase Branch:** codex/task-4-core-calculations  
> **Status:** Documentation of current rounding behavior across all calculators

---

## Table of Contents

1. [Overview](#overview)
2. [Rounding Functions Used](#rounding-functions-used)
3. [Zone Planning Rounding](#zone-planning-rounding)
4. [Investment Estimator Rounding](#investment-estimator-rounding)
5. [Power Configuration Rounding](#power-configuration-rounding)
6. [CalculationService Rounding](#calculationservice-rounding)
7. [Consistency Analysis](#consistency-analysis)
8. [Recommendations](#recommendations)

---

## Overview

This document catalogs all rounding behavior in the Cold Storage Planning Agent calculations. The current codebase uses a mix of rounding approaches:

1. **`round(value, 2)`** — Most common, used for area and monetary values
2. **`math.ceil()`** — Used for position counts (always rounds up)
3. **Custom rounding** — Some functions have unique rounding logic
4. **No rounding** — Several intermediate and final values are raw floats

---

## Rounding Functions Used

### Standard Library
- `round(value, ndigits)` — Python built-in, banker's rounding
- `math.ceil(value)` — Ceiling function, rounds up to nearest integer

### Custom Helpers
```python
# Zone Planning
def _round_precooling_positions(self, raw_position_count: int) -> int:
    return min(
        self._round_up_to_multiple(raw_position_count, 6),
        self._round_up_to_multiple(raw_position_count, 8),
    )

def _round_up_to_multiple(self, value: int, multiple: int) -> int:
    return ceil(value / multiple) * multiple

# Power Configuration
def scale_value(value: object, scale: float) -> float:
    scaled = as_float(value) * scale
    rounded = round(scaled, 2)
    if rounded.is_integer():
        return int(rounded)
    return rounded
```

---

## Zone Planning Rounding

### File
`backend/src/cold_storage/modules/calculations/domain/zone_planning.py`

### Input Validation
- **Method**: `_first_non_positive()`
- **Behavior**: Iterates all numeric fields, returns first field with value ≤ 0
- **Result**: Returns `CalculationResult(success=False)` with error

### Position Counts

| Zone Type | Calculation | Rounding | Example |
|-----------|-------------|----------|---------|
| Precooling (raw) | `ceil(daily_throughput / daily_capacity)` | `math.ceil()` | 19 |
| Precooling (final) | `min(ceil(raw/6)*6, ceil(raw/8)*8)` | Custom (multiples of 6 or 8) | 24 |
| Pallet Storage | `ceil(design_storage_mass / pallet_weight)` | `math.ceil()` | 157 |
| Packing (workers) | `ceil(daily_throughput / person_daily_capacity)` | `math.ceil()` | 70 |
| Packing (tables) | `ceil(worker_count / workers_per_table)` | `math.ceil()` | 24 |
| Packaging Material | `ceil(raw_positions)` | `math.ceil()` | 90 |
| Support Zones | Fixed at 0 | N/A | 0 |
| Area Ratio Zones | Fixed at 0 | N/A | 0 |

### Area Values

| Field | Rounding | Precision | Example |
|-------|----------|-----------|---------|
| Zone `required_area_m2` | `round(..., 2)` | 2 decimal places | 134.4 |
| `total_required_area_m2` | `round(..., 2)` | 2 decimal places | 1813.57 |
| `total_area_m2` | `round(..., 2)` | 2 decimal places | 1813.57 |
| `pallet_base_area_m2` | `round(..., 4)` | 4 decimal places | 1.56 |
| `storage_area_factor` | None (input) | N/A | 1.2 |

### Throughput Values

| Field | Rounding | Precision | Example |
|-------|----------|-----------|---------|
| `daily_throughput_kg_day` | `round(..., 2)` | 2 decimal places | 25000.0 |
| `position_hourly_capacity_kg_h` | `round(..., 2)` | 2 decimal places | 220.0 |
| `position_daily_capacity_kg_day` | `round(..., 2)` | 2 decimal places | 1320.0 |
| `person_daily_capacity_kg_day` | `round(..., 2)` | 2 decimal places | 360.0 |
| `packing_table_area_m2` | `round(..., 2)` | 2 decimal places | 19.25 |

### Mass Values

| Field | Rounding | Precision | Example |
|-------|----------|-----------|---------|
| `design_storage_mass_kg` | `round(..., 2)` | 2 decimal places | 62500.0 |

---

## Investment Estimator Rounding

### File
`backend/src/cold_storage/modules/calculations/domain/investment.py`

### Input Validation
- **Method**: `_first_non_positive()`
- **Behavior**: Same as zone planner

### Monetary Values

| Field | Rounding | Precision | Example |
|-------|----------|-----------|---------|
| Each item `amount_cny` | `round(..., 2)` | 2 decimal places | 2532213.00 |
| `total_investment_cny` | `round(..., 2)` | 2 decimal places | 6150420.50 |

### Intermediate Calculations
```python
civil_structure = (total_area_m2 + 1000) * 900  # No intermediate rounding
refrigeration = total_area_m2 * 1400              # No intermediate rounding
power_distribution = total_power_kw * 650         # No intermediate rounding
```

**Note**: Intermediate values are not rounded before summation. Only final item values and total are rounded.

---

## Power Configuration Rounding

### File
`backend/src/cold_storage/modules/planning/application/service.py`

### Scaling Rounding
```python
def scale_value(value: object, scale: float) -> float:
    scaled = as_float(value) * scale
    rounded = round(scaled, 2)
    if rounded.is_integer():
        return int(rounded)  # Convert to int if whole number
    return rounded
```

**Behavior**:
- Scaled values are rounded to 2 decimal places
- If result is a whole number (e.g., 360.0), it's converted to `int` (360)
- This means some `quantity` fields are `int`, others are `float`

### Power Totals

| Field | Rounding | Precision | Example |
|-------|----------|-----------|---------|
| `defrost_simultaneous_power` | `round(..., 2)` | 2 decimal places | 60.0 |
| `running_simultaneous_power` | `round(..., 2)` | 2 decimal places | 1059.97 |
| `refrigeration_total` | `round(..., 2)` | 2 decimal places | 1119.97 |
| `production_total` | `round(..., 2)` | 2 decimal places | 232.66 |
| `grand_total` | `round(..., 2)` | 2 decimal places | 1352.63 |

### Axial Fan Rule
```python
axial_fan_quantity = (primary_positions + secondary_positions) * 4  # Integer arithmetic
axial_fan_total_power = round(axial_fan_quantity * 0.55, 2)         # round to 2 decimals
```

---

## CalculationService Rounding

### File
`backend/src/cold_storage/modules/calculations/domain/service.py`

### Throughput Calculator
- **No explicit rounding** on outputs
- Returns raw float values from division operations

### Inventory Calculator
- **No explicit rounding** on outputs
- Returns raw float values from multiplication operations

### Storage Capacity Calculator
- **No explicit rounding** on outputs
- Returns raw float values from division operations

### Precooling Calculator
- **No explicit rounding** on mass/volume values
- Position counts use `math.ceil()` (integer)

### Room Area Calculator
- **No explicit rounding** on area outputs
- `pallet_count` uses `math.ceil()` (integer)
- Preliminary dimensions use raw `**0.5 * 1.2` and `**0.5 / 1.2`

### Cooling Load Calculator
- **No explicit rounding** on any outputs
- Returns raw float values

### Equipment Requirement Calculator
- **No explicit rounding** on any outputs
- Returns raw float values

---

## Consistency Analysis

### Consistent Patterns ✅

1. **Position counts**: Always use `math.ceil()` — consistent across all calculators
2. **Zone areas**: Always use `round(..., 2)` — consistent within zone planner
3. **Monetary values**: Always use `round(..., 2)` — consistent within investment estimator
4. **Power totals**: Always use `round(..., 2)` — consistent within power configuration

### Inconsistencies ⚠️

1. **Cross-calculator rounding**: `CalculationService` calculators don't round outputs, while `ColdRoomZonePlanner` and `InvestmentEstimator` do
2. **Pallet base area**: Uses `round(..., 4)` in zone planner (higher precision than other areas)
3. **Power scaling**: Converts whole numbers to `int`, creating mixed `int`/`float` types in equipment rows
4. **Input validation duplication**: Both `ColdRoomZonePlanner` and `CalculationService` implement identical `_first_non_positive()` methods

### Missing Rounding ❌

1. **Throughput calculator**: No rounding on `average_hourly_throughput_kg_h` (returns 1562.5)
2. **Storage capacity**: No rounding on volume/area outputs
3. **Room area**: No rounding on final area or dimensions
4. **Cooling load**: No rounding on any load components
5. **Equipment requirement**: No rounding on capacity values

---

## Recommendations

### For New Calculations

1. **Standardize position counts**: Always use `math.ceil()` for integer positions
2. **Standardize areas**: Use `round(..., 2)` for m² values
3. **Standardize masses**: Use `round(..., 2)` for kg values
4. **Standardize monetary values**: Use `round(..., 2)` for CNY values
5. **Standardize power values**: Use `round(..., 2)` for kW values

### For Existing Calculations

1. **Do not change rounding without regression testing** — existing tests assert specific values
2. **Document any changes** in this rounding policy document
3. **Update regression baselines** if rounding changes affect output

### Regression Baseline Preservation

The following values are asserted in tests and MUST NOT change without explicit approval:

```python
# Zone Planner Tests
assert zones[2]["required_area_m2"] == pytest.approx(134.4, abs=0.01)
assert zones[3]["required_area_m2"] == pytest.approx(44.8, abs=0.01)
assert zones[4]["required_area_m2"] == pytest.approx(86.11, abs=0.01)
assert zones[5]["required_area_m2"] == pytest.approx(693, abs=0.01)
assert zones[6]["required_area_m2"] == pytest.approx(120, abs=0.01)
assert zones[7]["required_area_m2"] == pytest.approx(293.9, abs=0.01)
assert zones[8]["required_area_m2"] == pytest.approx(31.45, abs=0.01)
assert zones[9]["required_area_m2"] == pytest.approx(39.31, abs=0.01)
assert zones[10]["required_area_m2"] == pytest.approx(210.6, abs=0.01)
assert result.result["total_area_m2"] == pytest.approx(1813.57, abs=0.01)

# Investment Tests
assert result.result["total_investment_cny"] == pytest.approx(3_645_053.5, abs=1)

# Demo Overview Tests
assert overview["overall_status"]["total_area_m2"] == 1813.57
assert overview["overall_status"]["total_investment_cny"] == 6_150_420.50
assert axial_fan_row["quantity"] == (24 + 8) * 4
assert axial_fan_row["total_power_kw"] == 70.4

# Throughput Tests
assert result.result["average_hourly_throughput_kg_h"] == 1562.5
assert result.result["design_hourly_throughput_kg_h"] == pytest.approx(1838.235294117647)

# Storage Capacity Tests
assert result.result["effective_storage_volume_m3"] == 267.85714285714283
```

---

## Appendix: Rounding Function Reference

### Python `round()`
- **Banker's rounding**: Rounds to nearest even number when exactly halfway
- **Example**: `round(2.5)` → 2, `round(3.5)` → 4
- **With decimals**: `round(1.235, 2)` → 1.24 (in Python 3, rounds to nearest even)

### Python `math.ceil()`
- **Always rounds up**: Returns smallest integer ≥ value
- **Example**: `ceil(19.1)` → 20, `ceil(19.0)` → 19
- **Edge case**: `ceil(19.0000001)` → 20

### Custom `_round_up_to_multiple()`
- **Rounds up to nearest multiple**: `ceil(value / multiple) * multiple`
- **Example**: `_round_up_to_multiple(19, 6)` → 24, `_round_up_to_multiple(19, 8)` → 24
- **Used for**: Precooling position counts (to align with room layouts)

---

## Document History

| Date | Change | Author |
|------|--------|--------|
| 2026-06-20 | Initial audit and documentation | Audit Agent |
