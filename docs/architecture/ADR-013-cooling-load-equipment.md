# ADR-013: Deterministic Cooling Load and Equipment Capability Calculators

Date: 2026-06-20
Status: Accepted
Deciders: Hermes Agent (Task 5)

## Context

Task 5 requires deterministic, traceable cooling-load and equipment-capability
calculations. The existing legacy calculators (`CalculationService.run_cooling_load`
and `run_equipment_requirement`) use `float` arithmetic, lack step-by-step
traceability, and have hardcoded coefficients. The power configuration is a
linear scaling of a reference equipment table.

## Decision

### 1. Three new calculators

| Calculator | Module | Purpose |
|---|---|---|
| `cooling_load` | `calculations/domain/cooling_load.py` | Envelope, product, infiltration, internal, defrost loads |
| `equipment` | `calculations/domain/equipment.py` | Evaporator, compressor, condenser capability |
| `power` | `calculations/domain/power.py` | Installed electrical power (kW(e)) |

### 2. Deterministic boundary

- All calculations use `decimal.Decimal` for reproducibility.
- Pure functions: no database, network, or LLM access.
- Input validation raises domain exceptions.
- Each calculation step is recorded as a `CalculationStep`.

### 3. Unit discipline

| Quantity | Unit | Symbol |
|---|---|---|
| Refrigeration load | kilowatt (refrigeration) | kW(r) |
| Equipment capability | kilowatt (refrigeration) | kW(r) |
| Electrical power | kilowatt (electric) | kW(e) |
| Energy consumption | kilowatt-hour | kWh |

kW(r) ≠ kW(e): refrigeration capacity and electrical power are distinct metrics.

### 4. Rounding policy

- Intermediate results: no rounding (full Decimal precision).
- Final results: `ROUND_HALF_UP` to 3 decimal places for kW values.
- Positions/people: `math.ceil()`.
- Areas: 2 decimal places.
- The legacy `build_power_configuration()` retains `round(..., 2)` for backward
  compatibility.

### 5. CoefficientSet injection

All engineering parameters come from a `CoefficientSet` dataclass injected at
call time. Demo/unverified coefficients trigger `requires_review=true` warnings.
Missing required coefficients raise `CoefficientMissingError`.

### 6. Temperature level grouping

Zones are grouped by temperature level (medium, low, precooling, special).
Each group has its own simultaneous load. Diversity factor is applied per group,
not globally.

### 7. Installed power (kW(e))

The `InstalledPowerCalcInput` aggregates:
- Compressor input power (from COP)
- Evaporator fan power
- Condenser fan power
- Pump power
- Defrost power
- Processing equipment power
- Lighting power
- Other auxiliary power

Estimated peak demand uses demand factors per category.

### 8. API endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/projects/{id}/versions/{v}/calculations/cooling-load` | Calculate + persist |
| GET | `/api/v1/projects/{id}/versions/{v}/calculations/cooling-load` | Retrieve |
| POST | `/api/v1/calculations/cooling-load/preview` | Preview (no save) |

Input parsing is in `cooling_load_api.py` (application layer), keeping
engineering formulas out of `app.py`.

### 9. Backward compatibility

- Legacy `run_cooling_load` and `run_equipment_requirement` are preserved.
- `build_power_configuration()` is preserved (linear scaling of reference table).
- New calculators supplement, not replace, existing results.
- Existing API routes are not modified.
- Task 4 calculation snapshots are not overwritten.

## Consequences

### Positive
- Deterministic, reproducible results.
- Full traceability of every calculation step.
- Clear unit discipline prevents kW(r)/kW(e) confusion.
- Coefficient registry integration enables governance.

### Negative
- Three new domain modules increase code surface.
- API input parsing duplicated in `cooling_load_api.py` and `app.py`.
- Architecture test patterns needed updating.

### Risks
- Demo coefficients may produce unrealistic results if not reviewed.
- COP-based power calculation depends on reliable COP values.

## Alternatives considered

1. **Extend legacy `CalculationService`**: Rejected — would couple new calculators
   to float-based legacy patterns and make Decimal migration harder.
2. **Single monolithic calculator**: Rejected — violates single-responsibility and
   makes independent testing difficult.
3. **Move all API parsing into app.py**: Rejected — violates architecture boundary
   (engineering formulas in API layer).
