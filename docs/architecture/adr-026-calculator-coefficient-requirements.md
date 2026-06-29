# ADR-026: Calculator Coefficient Requirements Registry

- Status: Accepted (frozen 2026-06-29)

## Context

The orchestration service needs to know which coefficient codes each calculator
requires before dispatching a calculation run. Previously this was a
product-level placeholder (PEAK_FACTOR) with no formal contract between
calculators and the coefficient catalog. The orchestration service had no
deterministic way to resolve which coefficient definitions must be loaded for a
given calculator version.

This ADR formalizes the calculator→coefficient requirement contract, replacing
the placeholder with a frozen registry backed by real codes from the coefficient
catalog seed data.

## Decision

A frozen registry maps `(calculator_name, calculator_version)` tuples to
required coefficient definition codes. All codes in the registry correspond to
real `CoefficientDefinitionRecord` entries in the coefficient catalog seed data.

### Registry

| Calculator | Version | Required Coefficient Codes |
|---|---|---|
| zone | 1.0.0 | `area.circulation_allowance_ratio`, `area.auxiliary_area_ratio` |
| cooling_load | 1.0.0 | `power.design_margin_ratio` |
| equipment | 1.0.0 | `pallet.net_load_kg`, `pallet.turnover_factor` |
| power | 1.0.0 | `power.design_margin_ratio`, `power.standby_ratio` |
| investment | 1.0.0 | `investment.building_unit_cost`, `investment.refrigeration_equipment_ratio`, `investment.electrical_installation_ratio`, `investment.other_expenses_ratio` |

### Code Purposes

| Code | Purpose |
|---|---|
| `area.circulation_allowance_ratio` | Zone calculator: ratio of circulation area to gross area |
| `area.auxiliary_area_ratio` | Zone calculator: ratio of auxiliary area to gross area |
| `power.design_margin_ratio` | Cooling load / power calculator: safety margin on design capacity |
| `pallet.net_load_kg` | Equipment calculator: net load per pallet in kilograms |
| `pallet.turnover_factor` | Equipment calculator: pallet turnover multiplier |
| `power.standby_ratio` | Power calculator: standby power as fraction of rated power |
| `investment.building_unit_cost` | Investment calculator: building cost per square meter |
| `investment.refrigeration_equipment_ratio` | Investment calculator: refrigeration equipment cost ratio |
| `investment.electrical_installation_ratio` | Investment calculator: electrical installation cost ratio |
| `investment.other_expenses_ratio` | Investment calculator: other project expenses ratio |

### Shared Codes

`power.design_margin_ratio` is intentionally shared between `cooling_load` and
`power` calculators. This is the only cross-calculator code sharing in the
current registry.

### Implementation

The registry is implemented as `REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION` in
`backend/src/cold_storage/modules/orchestration/application/coefficient_contracts.py`.

The helper `derive_required_codes_for_version_vector()` derives the full
deduplicated set of required codes from a calculator version vector
(e.g., `_CALCULATOR_VERSION_VECTOR`).

## Change Rules

1. **Registry version bump required**: Any change to
   `REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION` must bump
   `_REQUIREMENT_REGISTRY_VERSION`.
2. **Orchestration definition version**: The orchestration definition version
   (`_ORCHESTRATION_DEFINITION_VERSION`) must be updated when the registry
   changes.
3. **ADR update**: This document must be updated to reflect any registry
   changes.
4. **Integration test**: The catalog existence test
   (`test_calculator_contract.py`) must pass with all referenced codes present
   as active definitions in the database.

## Scope

This is a new authority frozen in this phase. The registry is not derived from
existing production calculator consumer code, which is not yet implemented.
Production calculator consumer code (Task 11+) will verify these bindings at
runtime.

## Consequences

### Positive

- Orchestration service has a deterministic contract for coefficient requirements
- Integration tests verify catalog existence before dispatch
- Registry changes are auditable and version-controlled
- Clear separation between calculator identity and its coefficient dependencies

### Negative

- Registry must be manually kept in sync with calculator implementations
- Adding a new calculator requires both code and registry updates

## References

- ADR-011: Engineering Coefficient Registry
- `backend/src/cold_storage/modules/orchestration/application/coefficient_contracts.py`
- `backend/src/cold_storage/modules/orchestration/application/service.py` (`_CALCULATOR_VERSION_VECTOR`)
- `backend/tests/integration/test_calculator_contract.py`
