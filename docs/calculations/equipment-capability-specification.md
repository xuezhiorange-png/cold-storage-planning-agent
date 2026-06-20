# Equipment Capability Calculation Specification

Version: 1.0.0
Calculator: `equipment.py`
Module: `cold_storage.modules.calculations.domain.equipment`

## Overview

This calculator computes equipment capability requirements from the cooling load
results produced by `cooling_load.py`. It determines evaporator, compressor, and
condenser capacities for each temperature system group, using `decimal.Decimal`
for all arithmetic to guarantee deterministic, reproducible results.

**Key boundary:** This calculator outputs capacity requirements in kW(r) and
input power in kW(e). It does **not** select manufacturer models or final
equipment types — that is the responsibility of scheme generation (Task 6).

**Input dependency:** Requires the `design_cooling_load_kw_r` for each zone,
which is the output of the cooling load calculator. The equipment calculator
operates downstream of the cooling load calculation.

## Temperature System Grouping

Zones are organized into temperature systems, where each system shares a common
evaporating temperature. Zones within a system typically have similar temperature
requirements (e.g., all medium-temperature rooms at 0–5°C).

```
systems = [
    TemperatureSystemInput(
        system_code="TS-MT",
        system_name="Medium Temperature",
        design_evaporating_temperature=-5,   # °C
        zones=[zone_1, zone_2, ...],
    ),
    ...
]
```

**Rules:**
- Each system has a `design_evaporating_temperature` in °C.
- Zone loads within a system are summed to produce the system simultaneous load.
- Equipment is sized per-system, not per-zone.
- Diversity factor is applied at the zone or system level upstream (in cooling_load.py).

## Evaporator Capacity Requirements

For each temperature system, the total evaporator capacity is the sum of zone
design cooling loads multiplied by an evaporator margin factor.

### Formula

```
system_simultaneous_load = Σ zone.design_cooling_load_kw_r  (per system)
evaporator_total = system_simultaneous_load × evaporator_capacity_margin
single_evaporator = evaporator_total / total_evaporator_count
```

### Units
- `design_cooling_load_kw_r`: kW(r) — from cooling load calculator
- `evaporator_capacity_margin`: dimensionless ratio (from coefficient resolver, required)
- `evaporator_total`: kW(r)
- `single_evaporator`: kW(r)

### Rules
- The margin factor accounts for capacity degradation due to frost buildup,
  defrost cycles, and fouling.
- If the system has zero evaporators, the single evaporator capacity is 0.
- The margin is applied uniformly across all evaporators in the system.

## Compressor Capacity Requirements

The compressor must meet the system simultaneous load. Installed capacity
includes redundancy for reliability.

### Formula

```
compressor_operating = system_simultaneous_load
compressor_installed = compressor_operating × redundancy_ratio
standby = compressor_installed - compressor_operating
```

### Units
- All values in kW(r)
- `redundancy_ratio`: dimensionless (from coefficient resolver, required — N+1 redundancy)

### Rules
- Operating capacity equals the system load — the compressor must meet the
  design load at design conditions.
- Installed capacity = operating × redundancy_ratio.
- Standby capacity = installed − operating (the N+1 reserve).
- Default redundancy ratio of 1.10 provides 10% standby capacity.
- The redundancy is a ratio, not an absolute value — larger systems get
  proportionally more standby.

## Condenser Heat Rejection

The condenser must reject both the refrigeration capacity and the compressor
input power (which becomes heat at the condenser side).

### Formula

```
condenser_base = compressor_operating + compressor_input_power_kw_e
condenser_design = condenser_base × condenser_capacity_margin
```

### Physical Basis

```
Q_condenser = Q_refrigeration + W_compressor_input
```

This follows the first law of thermodynamics for a vapor-compression cycle:
all energy entering the cycle (refrigeration load + compressor work) must be
rejected at the condenser.

### Units
- `compressor_operating`: kW(r) — the actual running load, NOT installed capacity
- `compressor_input_power_kw_e`: kW(e)
- `condenser_capacity_margin`: dimensionless (from coefficient resolver)
- Output: kW (thermal rejection capacity)

### Rules
- Uses `compressor_operating`, NOT `compressor_installed` — standby units do
  not contribute to normal heat rejection.
- The condenser margin provides reserve capacity for high ambient temperatures.
- `condenser_heat_rejection_factor` has been **removed** — it duplicated the
  W_compressor term. The formula is now simply `(Q_ref + W_comp) × margin`.
- N+1 standby capacity is reflected only in `compressor_installed` and
  `compressor_standby`, never in condenser heat rejection.

## COP-Based Input Power Calculation

Compressor electrical input power is derived from the coefficient of performance
(COP), which relates refrigeration output to electrical input.

### Formula

```
compressor_input_power_kw_e = compressor_operating_kw_r / COP
```

### Units
- `compressor_operating_kw_r`: kW(r)
- `COP`: dimensionless ratio (kW(r) / kW(e))
- Output: kW(e)

### Rules
- **COP is required.** If COP is not provided, `CoefficientMissingError` is raised.
- COP ≤ 0 raises `InvalidCalculationInputError` — no silent fallback to 0 kW(e).
- The COP represents the system-level efficiency at design conditions.
- COP values are temperature-dependent and should be specified per temperature
  system or globally.
- COP must be bound to temperature conditions, refrigerant, and part-load state.

### Typical COP Ranges
- Medium temperature (0–5°C): COP 3.0–5.0
- Low temperature (-18–-25°C): COP 1.5–3.0
- Precooling: COP 3.5–5.5

## Coefficient Dependencies

| Code | Required | Default | Description |
|---|---|---|---|
| `equipment.redundancy_ratio` | Yes | — | Compressor N+1 redundancy ratio |
| `equipment.evaporator_capacity_margin` | Yes | — | Evaporator capacity margin |
| `equipment.condenser_capacity_margin` | Yes | — | Condenser capacity margin |
| `power.compressor_cop` | Yes | — | Coefficient of performance |

**Note:** All coefficients are **required** — the calculator raises
`CoefficientMissingError` if any is missing. `condenser_heat_rejection_factor`
has been removed (it duplicated the W_compressor term).

## Error Handling

| Error | Condition |
|---|---|
| `MissingCalculationInputError` | `systems` list is empty |

## Warning Conditions

| Warning Code | Condition | Details |
|---|---|---|
| `DEMO_COEFFICIENT` | Coefficient `revision_status` ≠ "approved" | Reports the coefficient code and metadata |

Every coefficient is checked: if its `revision_status` is not `"approved"`, a
`DEMO_COEFFICIENT` warning is emitted. This ensures that all demo/unverified
values are flagged for review.

## Output Structure

The calculator returns a `CalculationResult` with:

```json
{
  "systems": [
    {
      "system_code": "TS-MT",
      "system_name": "Medium Temperature",
      "design_evaporating_temperature_c": "-5",
      "zones": [...],
      "system_simultaneous_load_kw_r": 120.0,
      "evaporator_total_capacity_kw_r": 132.0,
      "evaporator_count": 8,
      "single_evaporator_capacity_kw_r": 16.5,
      "compressor_operating_capacity_kw_r": 120.0,
      "compressor_installed_capacity_kw_r": 132.0,
      "compressor_standby_capacity_kw_r": 12.0,
      "compressor_input_power_kw_e": 34.286,
      "condenser_heat_rejection_kw": 206.25,
      "defrost_methods": ["electric"]
    }
  ],
  "total_design_load_kw_r": 120.0,
  "total_compressor_capacity_kw_r": 132.0,
  "total_compressor_input_power_kw_e": 34.286,
  "total_condenser_rejection_kw": 206.25
}
```

## Calculation Steps

Each step is recorded as a `CalculationStep` with a unique `step_id`:

| Step ID | Formula | Description |
|---|---|---|
| `EQ-SUM-{system}` | `system_load = Σ zone_design_loads` | Sum zone loads for system |
| `EQ-EVAP-{system}` | `evaporator_total = system_load × margin` | Evaporator capacity with margin |
| `EQ-COMP-{system}` | `installed = operating × redundancy` | Compressor capacity (N+1) |
| `EQ-COP-{system}` | `input_power = refrigeration / COP` | Compressor input power (COP required) |
| `EQ-COND-{system}` | `Q_condenser = (Q_ref + W_comp) × margin` | Condenser heat rejection |
| `EQ-TOTAL` | `total = Σ system capacities` | Total across all systems |
