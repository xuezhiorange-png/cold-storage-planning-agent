# Cooling Load Calculation Specification

Version: 1.0.0
Calculator: `cooling_load.py`
Module: `cold_storage.modules.calculations.domain.cooling_load`

## Overview

This calculator computes the refrigeration load for cold rooms, organized by
temperature level. It is deterministic, Decimal-based, and produces step-by-step
traceable results.

## Load Components

### 1. Envelope (Transmission) Load

**Formula:**
```
Q_wall = U_wall × A_wall × (T_outdoor - T_room)
Q_roof = U_roof × A_roof × (T_outdoor - T_room)
Q_floor = U_floor × A_floor × max(T_adjacent - T_room, 0)
Q_transmission = Q_wall + Q_roof + Q_floor
```

**Units:**
- U-value: W/(m²·K)
- Area: m²
- Temperature: °C
- Load: kW(r) (after ÷ 1000)

**Rules:**
- Wall temperature difference = outdoor - room.
- Floor temperature difference = adjacent - room (clamped to ≥ 0).
- If adjacent temperature is not provided, use outdoor temperature.
- U-values must come from CoefficientSet or project input.

### 2. Product Load

**Formula:**
```
Q_product_sensible = m × c × ΔT / (t × 3600)
Q_packaging = m_pkg × c_pkg × ΔT / (t × 3600)
Q_respiration = m × q_respiration / 1000
Q_product = Q_product_sensible + Q_packaging + Q_respiration
```

**Units:**
- m: kg/day
- c: kJ/(kg·K)
- ΔT: °C (entry - target)
- t: hours (cooling duration)
- q_respiration: W/kg

**Rules:**
- Entry temperature must be ≥ target temperature.
- Cooling duration must be > 0.
- Respiration heat is only calculated for medium-temperature and precooling zones.
- Packaging load is proportional to packaging mass.

### 3. Infiltration/Ventilation Load

**Formula:**
```
V̇ = air_change_rate × volume × door_factor × curtain_factor
Q_infiltration = ρ × V̇ × cp × ΔT / 3600
```

**Units:**
- air_change_rate: 1/h
- volume: m³ (zone_area × room_height if not provided)
- ρ: 1.2 kg/m³ (air density)
- cp: 1.006 kJ/(kg·K) (air specific heat)

**Rules:**
- Only sensible infiltration is currently calculated (latent omitted).
- Door opening factor and air curtain factor multiply the base airflow.
- Air change rate comes from CoefficientSet.

### 4. Internal Load

**Formula:**
```
Q_people = worker_count × heat_gain × operating_fraction / 1000
Q_lighting = lighting_power × operating_fraction / 1000
Q_equipment = equipment_power × operating_fraction × (1 - motor_efficiency) / 1000
Q_fans = fan_motor_power × operating_fraction / 1000
Q_internal = Q_people + Q_lighting + Q_equipment + Q_fans
```

**Rules:**
- Equipment dissipation = electrical input × (1 - efficiency).
- Not all electrical power becomes heat load.
- Fan motor power becomes 100% heat load in the cold room.

### 5. Defrost Load

**Formula:**
```
Q_defrost = P_defrost × t_defrost × (1 - recovery) / operating_hours / 1000
```

**Rules:**
- Average defrost load over the operating day.
- Heat recovery fraction reduces the net defrost load.

## Zone Subtotal

```
Q_zone = Q_transmission + Q_product + Q_infiltration + Q_internal + Q_defrost
```

## Temperature Level Grouping

Zones are grouped by `TemperatureLevel`:
- `medium_temperature` (0~5°C)
- `low_temperature` (-18~-25°C)
- `precooling` (0~5°C)
- `special_process` (other)

Each group:
```
Q_level = Σ Q_zone (within level)
Q_level_diversified = Q_level × diversity_factor
```

## Design Load

```
Q_total_diversified = Σ Q_level_diversified
Q_design_margin = Q_total_diversified × (design_margin_ratio - 1)
Q_design_refrigeration = Q_total_diversified + Q_design_margin
```

## Coefficient Dependencies

| Code | Required | Default | Source |
|---|---|---|---|
| `cooling.wall_u_value` | Yes | — | CoefficientSet |
| `cooling.roof_u_value` | Yes | — | CoefficientSet |
| `cooling.floor_u_value` | Yes | — | CoefficientSet |
| `cooling.product_specific_heat` | If product_mass > 0 | — | CoefficientSet |
| `cooling.respiration_heat` | No | None | CoefficientSet |
| `cooling.air_change_rate` | Yes | — | CoefficientSet |
| `cooling.worker_heat_gain` | Yes | — | CoefficientSet |
| `cooling.design_margin_ratio` | No | 1.10 | CoefficientSet |
| `cooling.diversity_factor` | No | 1.0 | CoefficientSet |
| `power.motor_efficiency` | Yes | — | CoefficientSet |

## Error Handling

| Error | Condition |
|---|---|
| `MissingCalculationInputError` | zones list is empty |
| `CoefficientMissingError` | Required coefficient not provided |
| `InvalidCalculationInputError` | Negative temperature difference, entry < target |

## Warning Conditions

| Warning | Condition |
|---|---|
| `DEMO_COEFFICIENT` | Coefficient source_type ≠ "approved" |
| `ZERO_COOLING_DURATION` | cooling_duration = 0 |
| `NO_COEFFICIENT_SOURCES` | No source metadata provided |
