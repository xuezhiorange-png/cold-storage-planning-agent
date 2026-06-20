# Electrical Installed Capacity Calculation Specification

Version: 1.0.0
Calculator: `power.py`
Module: `cold_storage.modules.calculations.domain.power`

## Overview

This calculator computes the total installed electrical power (kW(e)) for the
cold storage facility. It aggregates power from all equipment categories —
refrigeration, processing, lighting, and auxiliary — and estimates peak demand
using demand factors.

**Key boundary:** This calculator outputs **kW(e) — electrical installed power**.
It does **not** output energy consumption (kWh) or daily electricity usage.
It does **not** determine transformer sizing or maximum demand unless provided
as explicit inputs with demand factors.

**Unit discipline:** kW(r) ≠ kW(e). Refrigeration capacity (kW(r)) and
electrical power (kW(e)) are fundamentally distinct metrics connected by COP.

## Input Categories

The installed power calculator accepts power values for seven categories, each
in kW(e):

### 1. Compressor Input Power (`compressor_input_power_kw_e`)
- Source: Equipment capability calculator (from COP calculation)
- Unit: kW(e)
- Description: Electrical power consumed by compressors to produce refrigeration

### 2. Evaporator Fan Power (`evaporator_fan_power_kw_e`)
- Source: Equipment specification or user input
- Unit: kW(e)
- Description: Power for air-moving fans across all evaporator units

### 3. Condenser Fan Power (`condenser_fan_power_kw_e`)
- Source: Equipment specification or user input
- Unit: kW(e)
- Description: Power for condenser fan motors (air-cooled or evaporative)

### 4. Pump Power (`pump_power_kw_e`)
- Source: Equipment specification or user input
- Unit: kW(e)
- Description: Power for coolant circulation pumps (glycol, brine, etc.)

### 5. Defrost Power (`defrost_power_kw_e`)
- Source: Equipment specification or user input
- Unit: kW(e)
- Description: Power for defrost systems (electric heaters, hot gas, etc.)

### 6. Processing Equipment Power (`processing_equipment_power_kw_e`)
- Source: User input or equipment list
- Unit: kW(e)
- Description: Production line equipment (sorting, packing, labeling, etc.)

### 7. Lighting Power (`lighting_power_kw_e`)
- Source: User input
- Unit: kW(e)
- Description: Facility lighting for work areas, storage, and common spaces

### 8. Other Auxiliary Power (`other_auxiliary_power_kw_e`)
- Source: User input
- Unit: kW(e)
- Description: Miscellaneous auxiliary equipment (controls, IT, HVAC for offices, etc.)

## Total Installed Power Formula

```
P_refrigeration = compressor + evaporator_fans + condenser_fans + pumps + defrost
P_processing = processing_equipment_power
P_lighting = lighting_power
P_auxiliary = other_auxiliary_power

P_total = P_refrigeration + P_processing + P_lighting + P_auxiliary
```

All values in kW(e). The sum is a simple arithmetic addition — no demand
factor is applied to installed power. Each category is independently totaled
before summation.

## Estimated Peak Demand with Demand Factors

Peak demand accounts for the fact that not all equipment runs simultaneously.
Demand factors reduce the installed power to a realistic peak usage estimate.

### Formula

```
refrigeration_demand = P_refrigeration × refrigeration_demand_factor
production_demand = P_processing × production_demand_factor

peak_demand = refrigeration_demand + production_demand + P_lighting + P_auxiliary
```

### Demand Factor Defaults
| Category | Default Factor | Rationale |
|---|---|---|
| Refrigeration | 0.90 | Compressors cycle; defrost reduces simultaneous load |
| Production | 0.90 | Production lines may not all run at peak simultaneously |
| Lighting | 1.0 (implicit) | Lighting is typically always on during operations |
| Auxiliary | 1.0 (implicit) | Auxiliary loads are generally constant |

### Rules
- Demand factors are between 0 and 1 (inclusive).
- Lighting and auxiliary are always counted at 100% — they don't have
  demand factors in this model.
- The peak demand value is used for transformer and switchgear sizing
  guidance, not for energy consumption calculations.

## kW(e) Unit Verification Rules

All input fields in `InstalledPowerCalcInput` must be in kW(e). The calculator
does **not** perform unit conversion. Specific rules:

1. **All fields default to 0 kW(e).** If a category has no equipment, it
   contributes nothing to the total.
2. **No unit conversion is performed.** Callers must ensure values are in
   kW(e), not W, MW, or kW(r).
3. **kW(r) ≠ kW(e).** Refrigeration capacity (kW(r)) from the cooling load
   calculator must **not** be mixed into power inputs. The only link between
   them is COP: `kW(e) = kW(r) / COP`.
4. **Compressor input power must come from the equipment capability calculator.**
   Using raw cooling load values (kW(r)) as kW(e) inputs would be incorrect.

## Equipment Item Breakdown Structure

For detailed traceability, an optional `equipment_items` list provides per-item
breakdown:

```python
@dataclass(frozen=True)
class PowerEquipmentItem:
    name: str                    # e.g., "Compressor Unit #1"
    category: str                # "refrigeration", "production", "lighting", "auxiliary"
    quantity: int                # Number of identical units
    unit_power_kw_e: Decimal     # kW(e) per unit
    demand_factor: Decimal       # Fraction of time running simultaneously (0–1)
```

### Derived Values
```
total_power_kw_e = quantity × unit_power_kw_e
demand_power_kw_e = total_power_kw_e × demand_factor
```

The equipment item list is **informational** — it does not affect the aggregate
totals (which use the top-level category fields). It provides a parallel
breakdown for audit and verification purposes.

## Coefficient Dependencies

This calculator has **no coefficient dependencies** in the current version.
All inputs are explicit values provided by the caller.

Future versions may introduce coefficients for:
- Default demand factors per category
- Equipment efficiency benchmarks
- Load diversity profiles

## Warning Conditions

| Warning Code | Condition | Details |
|---|---|---|
| `DEFAULT_DEMAND_FACTOR` | `defrost_power > 0` AND `refrigeration_demand_factor > 0.5` | Suggests demand factor may be too high when defrost cycles reduce simultaneous operation |

## Error Handling

This calculator does not raise domain exceptions. All inputs default to zero.
If no equipment power is provided, the calculator returns zero installed power
and zero peak demand with a valid result.

| Condition | Behavior |
|---|---|
| All inputs zero | Returns valid result with all values = 0 |
| No equipment items | Returns valid result without item breakdown |
| Invalid demand factors (negative, > 1) | No validation in current version — caller responsibility |

## Output Structure

The calculator returns a `CalculationResult` with:

```json
{
  "refrigeration_system_installed_power_kw_e": 200.5,
  "process_equipment_installed_power_kw_e": 50.0,
  "lighting_installed_power_kw_e": 15.0,
  "auxiliary_installed_power_kw_e": 5.0,
  "total_installed_power_kw_e": 270.5,
  "estimated_peak_demand_kw_e": 250.45,
  "equipment_items": [
    {
      "name": "Compressor Unit #1",
      "category": "refrigeration",
      "quantity": 2,
      "unit_power_kw_e": "45.0",
      "total_power_kw_e": "90.0",
      "demand_factor": "0.9",
      "demand_power_kw_e": "81.0"
    }
  ]
}
```

## Calculation Steps

Each step is recorded as a `CalculationStep`:

| Step ID | Formula | Description |
|---|---|---|
| `PW-REFRIG` | `P_refrig = compressor + fans + condenser_fans + pumps + defrost` | Refrigeration system installed power |
| `PW-PROC` | `P_process = processing_equipment_power` | Processing equipment installed power |
| `PW-LIGHT` | `P_lighting = lighting_power` | Lighting installed power |
| `PW-AUX` | `P_aux = other_auxiliary_power` | Auxiliary installed power |
| `PW-TOTAL` | `P_total = refrig + process + lighting + aux` | Total installed electrical power |
| `PW-DEMAND` | `peak = refrig×df + process×df + lighting + aux` | Estimated peak demand |
