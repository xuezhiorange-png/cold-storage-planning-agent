# Task 5: Cooling-load and equipment-capability calculations

## Latest verified commit
`86671d666391b2fdf69c30581ea14a4734e51fcf` — workflow run `27877791004` — all 4 jobs pass.

## Required calculation inputs
All project design inputs are **required** with no hidden code defaults:
- `outdoor_design_temperature`, `room_design_temperature`
- `product_entry_temperature`, `product_target_temperature`, `cooling_duration`
- `operating_hours_per_day`, `temperature_level`
- `design_margin_ratio`, `diversity_factor` (from coefficient resolver)
- `packaging_specific_heat` (required when packaging_mass > 0)

Physical constants are named (`AIR_DENSITY_KG_M3`, `AIR_SPECIFIC_HEAT_KJ_KG_K`,
`STANDARD_ATMOSPHERIC_PRESSURE_PA`).

## Coefficient governance
- `source_type` represents data provenance only (standard, book, manufacturer, etc.)
- `revision_status` is used for approval checks (`requires_review = status != "approved"`)
- `CoefficientReference` carries both fields for traceability
- `manufacturer + approved` is legal; `standard + unverified` triggers review

## COP validation
- **COP is required.** `CoefficientMissingError` if absent.
- COP ≤ 0 → `InvalidCalculationInputError`. No silent fallback to 0 kW(e).
- Formula: `compressor_input_power_kw_e = compressor_operating_capacity_kw_r / COP`

## Condenser heat-rejection formula
```
condenser_base = compressor_operating + compressor_input_power_kw_e
condenser_design = condenser_base × condenser_capacity_margin
```
- Uses `compressor_operating`, NOT `compressor_installed`
- **`condenser_heat_rejection_factor` has been removed** (duplicated W_compressor)
- N+1 standby does not enter normal condenser heat rejection
- Margin applied once

## Latent infiltration load
Implemented via psychrometric enthalpy method:
```
Q_total = mass_flow × (h_out - h_in) / 3600
Q_sensible = ρ × V̇ × cp × ΔT / 3600
Q_latent = Q_total - Q_sensible
```
- `_humidity_ratio()` raises `InvalidCalculationInputError` when atmospheric pressure ≤ vapor pressure
- Negative latent (outdoor enthalpy < indoor) triggers `NEGATIVE_LATENT_LOAD` warning, clamped to 0
- Missing humidity → sensible-only mode with `requires_review`

## PostgreSQL integration tests
**12 tests, 0 skipped**, running against real PostgreSQL 16 via `psycopg2`:
- `test_dialect_is_postgresql` — engine dialect assertion
- `test_can_execute_query` — connectivity
- `test_alembic_version_table_exists` — migration integrity
- `test_coefficient_tables_exist` — schema check
- `test_decimal_precision_in_json` — Decimal round-trip
- `test_json_snapshot_structure` — nested JSON persistence
- `test_project_version_snapshot_persistence` — ProjectVersion ORM with JSONB
- `test_coefficient_revision_persistence` — CoefficientDefinition + Revision ORM
- `test_rollback_does_not_persist` — transaction rollback on real table
- `test_committed_data_persists` — commit verification
- `test_unique_constraint_enforced` — IntegrityError on duplicate code
- `test_foreign_key_constraint` — IntegrityError on invalid definition_id

## SQLite verification
**363 passed, 12 skipped, 0 failed.**

## Frontend verification
11 tests passed. lint / typecheck / build all pass.

## Security remediation
- Git history cleaned: `.config/gh/` removed, token-bearing commits rewritten
- `git grep` secret scan: zero hits
- PR #7 contains no credentials

## Regression baselines
- Zone area: 1,813.57 m²
- Pallet positions: 346
- Legacy installed capacity: 1,352.63 kW(e)
- Legacy investment estimate: 6,150,420.50 CNY
- Legacy calculator preserved unchanged in `service.py`

## Documentation
All docs updated: ADR-013, equipment spec, cooling-load spec, cooling-load inventory,
TECH_DEBT, EXECUTION_PLAN. Formula descriptions match code exactly.
