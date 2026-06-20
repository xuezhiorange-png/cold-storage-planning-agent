# Cooling Load & Equipment Capability Inventory

Audit date: 2026-06-20
Auditor: Hermes Agent (Task 5 pre-work)

## Purpose

This document inventories all existing cooling-load, power, and equipment-related
calculations in the repository. It serves as the baseline for Task 5: deterministic
cooling-load and equipment-capability calculations.

---

## 1. Existing Cooling Load Calculator (Legacy)

| Field | Content |
|---|---|
| **Calculation name** | Cooling load (制冷负荷) |
| **Location** | `backend/src/cold_storage/modules/calculations/domain/service.py` → `CalculationService.run_cooling_load()` |
| **Input** | `CoolingLoadInput` (from `inputs.py`) |
| **Output fields** | `total_cooling_load_kw`, `product_sensible_heat_load_kw`, `safety_margin_load_kw`, plus 8 component loads |
| **Formula** | `sensible = m × c × ΔT / t / 3600` (kJ→kW conversion) |
| **Coefficients** | `product_specific_heat_kj_kg_k`, `safety_margin_factor` (from `CalculationCoefficient`) |
| **Unit** | kW (float) |
| **Assumptions** | All non-sensible loads pre-computed and passed in; safety margin = subtotal × (factor - 1) |
| **Result** | Legacy `CalculationResult` (float-based, no rounding policy) |
| **Status** | Active — used by legacy API route |
| **Included in Task 5** | YES — superseded by new Decimal-based calculator |

### Gaps identified

- Uses `float` arithmetic, not `Decimal`
- No step-by-step traceability (`FormulaReference` only, no `CalculationStep`)
- Non-sensible loads (envelope, infiltration, etc.) are passed in pre-computed —
  no independent calculation of each load component
- No temperature-level grouping
- No installed-power calculation
- No equipment-capability sizing beyond simple redundancy

---

## 2. Existing Equipment Requirement Calculator (Legacy)

| Field | Content |
|---|---|
| **Calculation name** | Equipment requirement (设备能力需求) |
| **Location** | `backend/src/cold_storage/modules/calculations/domain/service.py` → `CalculationService.run_equipment_requirement()` |
| **Input** | `EquipmentRequirementInput` |
| **Output fields** | `evaporator_total_cooling_capacity_kw`, `single_evaporator_capacity_kw`, `compressor_operating_capacity_kw`, `standby_capacity_kw`, `condenser_heat_rejection_capacity_kw` |
| **Formula** | `total = load × redundancy; condenser = total × 1.25` |
| **Coefficients** | `redundancy_factor` |
| **Unit** | kW (float) |
| **Assumptions** | Condenser heat rejection factor hardcoded 1.25 |
| **Result** | Legacy `CalculationResult` (float-based) |
| **Status** | Active — used by legacy API route |
| **Included in Task 5** | YES — superseded by new Decimal-based calculator |

### Gaps identified

- No COP/EER-based compressor input power calculation
- No installed power breakdown
- No temperature-level grouping
- Condenser factor hardcoded 1.25, not from coefficient registry

---

## 3. Power Configuration (Planning Service)

| Field | Content |
|---|---|
| **Calculation name** | Power configuration (用电配置) |
| **Location** | `backend/src/cold_storage/modules/planning/application/service.py` → `build_power_configuration()` |
| **Input** | `zones`, `daily_inbound_mass_kg`, `total_area_m2` |
| **Output fields** | `total_installed_power_kw`, `equipment_rows`, `summary_rows`, `items` |
| **Formula** | Linear scaling: `scale = daily_mass / 25000`; each row × scale |
| **Coefficients** | Hardcoded reference table (40 rows), `defrost_simultaneous_factor=0.30`, `running_simultaneous_factor=0.90` |
| **Unit** | kW (float) |
| **Assumptions** | Reference project at 25 t/day; linear scaling; 30% defrost simultaneous; 90% running simultaneous |
| **Result** | dict (not a CalculationResult) |
| **Status** | Active — used by planning-run endpoint |
| **Included in Task 5** | YES — new installed-power calculator supplements (not replaces) this |

### Coefficients to migrate to registry

| Code | Value | Unit | Notes |
|---|---|---|---|
| `reference_daily_capacity_kg` | 25000 | kg/day | Scaling base |
| `defrost_simultaneous_factor` | 0.30 | ratio | 30% defrost simultaneous |
| `running_simultaneous_factor` | 0.90 | ratio | 90% running simultaneous |

> **Note:** `condenser_heat_rejection_factor` (1.25) has been removed from the
> new equipment calculator — it duplicated the W_compressor term. The legacy
> calculator in `service.py` still uses it for backward compatibility.

---

## 4. Regression Baselines

### Baseline: 25 t/day reference project (power configuration)

| Metric | Value | Unit |
|---|---|---|
| defrost_simultaneous_power | 249.09 | kW(e) |
| running_simultaneous_power | 819.14 | kW(e) |
| refrigeration_total | 1,068.23 | kW(e) |
| production_total | 284.40 | kW(e) |
| grand_total | 1,352.63 | kW(e) |

Source: `docs/audit/coefficient-inventory.md` item 60-104.

### Baseline: Zone planning

| Metric | Value | Unit |
|---|---|---|
| Total design area | 1,813.57 | m² |
| Total positions | 346 | position |

### Baseline: Investment estimate

| Metric | Value | Unit |
|---|---|---|
| Total investment | 6,150,420.50 | CNY |

### Note on historical value differences

装机容量约 1467.47 kW (from early Task 4 report) vs 1,352.63 kW (from
coefficient-inventory.md): These represent different calculation scenarios.
The 1,352.63 kW figure is from the power configuration's 25 t/day reference
scaling. The 1,467.47 kW figure was from a different input case with different
daily mass or zone configuration. They are NOT the same baseline.

投资估算约 3,645,053 CNY (early Task 4) vs 6,150,420.50 CNY (final): These
are different input cases — the lower figure corresponds to a smaller facility
scenario, the higher figure to the full 25 t/day reference.

---

## 5. Coefficient Registry Readiness

### Coefficients needed for Task 5 cooling-load calculations

| Code | Category | Unit | Status |
|---|---|---|---|
| `cooling.wall_u_value` | cooling | W/(m²·K) | Not yet registered |
| `cooling.roof_u_value` | cooling | W/(m²·K) | Not yet registered |
| `cooling.floor_u_value` | cooling | W/(m²·K) | Not yet registered |
| `cooling.product_specific_heat` | cooling | kJ/(kg·K) | Exists as `CalculationCoefficient` |
| `cooling.respiration_heat` | cooling | W/kg | Not yet registered |
| `cooling.air_change_rate` | cooling | 1/h | Not yet registered |
| `cooling.worker_heat_gain` | cooling | W/person | Not yet registered |
| `cooling.design_margin_ratio` | cooling | ratio | Exists as `safety_margin_factor` |
| `cooling.diversity_factor` | cooling | ratio | Not yet registered |
| `cooling.evaporating_temperature_difference` | cooling | K | Not yet registered |
| `equipment.compressor_redundancy_ratio` | equipment | ratio | Exists as `redundancy_factor` |
| `equipment.evaporator_capacity_margin` | equipment | ratio | Not yet registered |
| `equipment.condenser_capacity_margin` | equipment | ratio | Not yet registered |
| `power.compressor_cop` | power | ratio | Not yet registered |
| `power.motor_efficiency` | power | ratio | Not yet registered |

For Task 5, coefficients are accepted via the `CoefficientSet` injection pattern.
Demo/unverified coefficients trigger `requires_review=true` warnings.

---

## 6. Files to create/modify in Task 5

### New files

| File | Purpose |
|---|---|
| `calculations/domain/cooling_load.py` | Decimal-based cooling load calculator |
| `calculations/domain/equipment.py` | Decimal-based equipment capability calculator |
| `calculations/domain/power.py` | Decimal-based installed power calculator |
| `tests/unit/test_cooling_load.py` | Cooling load unit tests |
| `tests/unit/test_equipment.py` | Equipment capability unit tests |
| `tests/unit/test_power.py` | Installed power unit tests |
| `docs/architecture/ADR-013-cooling-load-equipment.md` | Architecture decision record |
| `docs/calculations/cooling-load-specification.md` | Cooling load calculation specification |

### Modified files

| File | Change |
|---|---|
| `calculations/domain/units.py` | Add W, KWH, W_M2_K units |
| `calculations/domain/__init__.py` | Export new modules |
| `calculations/application/service.py` | Orchestrate new calculators |
| `bootstrap/app.py` | Add API routes |
| `docs/TECH_DEBT.md` | Update tech debt status |
