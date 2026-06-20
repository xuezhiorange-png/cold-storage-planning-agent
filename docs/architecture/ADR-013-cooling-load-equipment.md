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

## Detailed Design

### Cooling load boundary (what is calculated, what is not)

**Calculated by cooling_load.py:**
- Envelope (transmission) load: wall, roof, floor heat gain via U × A × ΔT
- Product load: sensible cooling + packaging thermal mass + respiration heat
- Infiltration/ventilation load: air change rate × volume × ΔT
- Internal loads: people, lighting, equipment dissipation, evaporator fans
- Defrost load: averaged over operating hours with heat recovery deduction
- Temperature level grouping with per-level diversity factor
- Design margin applied to total diversified load

**Not calculated (out of scope):**
- Solar radiation load on roof (assumed included in U-value or outdoor temp)
- Floor heat gain from equipment movement or forklift traffic
- Startup/pull-down transient loads
- Safety factors beyond the design margin ratio
- Equipment selection or manufacturer model matching

### kW(r) vs kW(e) vs kWh distinction (detailed explanation)

| Metric | Unit | What It Measures | Where Produced |
|---|---|---|---|
| Refrigeration load | kW(r) | Rate of heat removal from cold rooms | `cooling_load.py` |
| Equipment capability | kW(r) | Rate of heat removal at equipment level | `equipment.py` |
| Compressor input power | kW(e) | Electrical power consumed by compressors | `equipment.py` (via COP) |
| Installed power | kW(e) | Total electrical connected load | `power.py` |
| Energy consumption | kWh | Total energy over time | Not in Task 5 scope |

**Critical distinction:** kW(r) and kW(e) are connected by COP but are not
interchangeable. A compressor with 100 kW(r) capacity might consume 30 kW(e)
(COP ≈ 3.3). The cooling load calculator outputs kW(r); the installed power
calculator outputs kW(e). Mixing these units would produce incorrect results.

**kWh is explicitly out of scope.** The calculators produce instantaneous
power/rate values (kW), not energy totals (kWh). Energy consumption requires
operating profiles, run-hour schedules, and seasonal variation — a separate
calculation module.

### Temperature system grouping rules

Zones are grouped into temperature systems by shared evaporating temperature.
The grouping determines:

1. **Which zones share compressor capacity.** All zones in a system are served
   by the same compressor group.
2. **Where diversity is applied.** Diversity factor is applied per temperature
   level in the cooling load calculator, not per individual zone.
3. **How evaporator margin is distributed.** The margin is applied uniformly
   across all evaporators in a system.

**Grouping levels:**

| Level | Typical Range | Example |
|---|---|---|
| `medium_temperature` | 0–5°C | Finished product storage |
| `low_temperature` | -18 to -25°C | Frozen storage |
| `precooling` | 0–5°C | Post-harvest precooling rooms |
| `special_process` | Variable | Blast freezing, controlled atmosphere |

Each level maintains its own simultaneous load total and diversity-adjusted
value. The final design refrigeration load is the sum across all levels.

### Load component model (envelope, product, infiltration, internal, defrost)

Each zone's total load is the sum of five components:

```
Q_zone = Q_transmission + Q_product + Q_infiltration + Q_internal + Q_defrost
```

**Component details:**

| Component | Formula | Key Dependencies |
|---|---|---|
| Transmission | `U × A × ΔT` per surface (wall, roof, floor) | U-values, areas, temperatures |
| Product | `m × c × ΔT / (t × 3600)` + packaging + respiration | Mass, specific heat, cooling duration |
| Infiltration | `ρ × V̇ × cp × ΔT / 3600` | Air change rate, volume, door factor |
| Internal | `people + lighting + equipment_dissipation + fans` | Worker count, power ratings, motor efficiency |
| Defrost | `P × t × (1-η) / operating_hours / 1000` | Defrost power, duration, recovery fraction |

**Inter-component interactions:**
- Equipment internal load uses motor efficiency: only `(1 - η)` of electrical
  input becomes heat load in the cold room.
- Evaporator fan load is 100% heat load (all motor energy dissipates in room).
- Defrost load is averaged over the full operating day, not instantaneous.

### Simultaneous factors and design margin

Two multiplicative adjustments are applied to the raw zone loads:

1. **Diversity factor** (from coefficient resolver) — applied per temperature level.
   Accounts for non-simultaneous operation across zones within a level.
   A factor < 1.0 reduces the total (zones don't all peak at once).
   Applied in `cooling_load.py` at the temperature level grouping step.
   **Required** — raises `CoefficientMissingError` if absent.

2. **Design margin ratio** (from coefficient resolver) — applied to the total
   diversified load. Provides reserve capacity for:
   - Load estimation uncertainties
   - Future capacity expansion
   - Degraded equipment performance
   Applied in `cooling_load.py` as the final step.

**Calculation flow:**
```
Q_level = Σ Q_zone (per level)
Q_level_diversified = Q_level × diversity_factor
Q_total_diversified = Σ Q_level_diversified
Q_design = Q_total_diversified × design_margin_ratio
```

### Equipment capability vs model selection boundary

The equipment capability calculator (`equipment.py`) determines **how much
capacity** is needed. It does **not** determine **which specific equipment**
provides that capacity.

| Capability Calculator (Task 5) | Model Selection (Task 6+) |
|---|---|
| Outputs kW(r) requirements per system | Selects specific evaporator models |
| Outputs kW(e) compressor input power | Selects specific compressor models |
| Outputs condenser heat rejection kW | Selects specific condenser units |
| Uses redundancy ratios (N+1) | Determines actual unit counts |
| Pure deterministic functions | May involve catalog lookups |

This separation ensures that capability calculations remain deterministic and
auditable, while equipment selection can incorporate manufacturer catalogs,
availability, and cost optimization in a later task.

### COP operating conditions

COP (Coefficient of Performance) is the ratio of refrigeration output to
electrical input: `COP = Q_refrigeration(kW(r)) / W_compressor(kW(e))`.

**COP is temperature-dependent.** The COP at -20°C evaporating temperature is
significantly lower than at 0°C. The calculator accepts a single COP value,
which should represent the weighted-average or design-point COP for the system.

**Usage in the pipeline:**
1. Equipment calculator uses COP to derive compressor input power: `W = Q / COP`
2. Compressor input power feeds into the condenser heat rejection formula
3. Compressor input power feeds into the installed power calculator

**If COP is not provided:** Compressor input power defaults to 0 kW(e).
Condenser heat rejection will still include the refrigeration component but
not the compressor work component. This is a degraded calculation mode that
should trigger review.

### Condenser heat rejection relationship

The condenser must reject all energy that enters the refrigeration cycle:

```
Q_condenser = Q_refrigeration + W_compressor_input
```

This follows the first law of thermodynamics (energy conservation) for a
vapor-compression refrigeration cycle:
- Q_refrigeration: heat absorbed at the evaporator (from the cold room)
- W_compressor_input: electrical work input to the compressor
- Q_condenser: total heat rejected at the condenser (to the ambient)

**Condenser heat rejection formula:**
```
Q_condenser_design = (Q_operating + W_compressor_input) × condenser_capacity_margin
```
- Uses `compressor_operating`, NOT `compressor_installed` — standby units do not
  contribute to normal heat rejection.
- `condenser_heat_rejection_factor` has been **removed** — it duplicated the
  W_compressor term.
- `condenser_capacity_margin` (from coefficient resolver): reserve for high
  ambient temperature conditions. **Required** — raises `CoefficientMissingError`
  if absent.

### Installed capacity composition

The installed power calculator aggregates kW(e) from all facility subsystems:

```
P_refrigeration = compressor + evaporator_fans + condenser_fans + pumps + defrost
P_processing = production line equipment
P_lighting = facility lighting
P_auxiliary = controls, IT, office HVAC, miscellaneous

P_total = P_refrigeration + P_processing + P_lighting + P_auxiliary
```

**Peak demand estimation** applies demand factors:
```
peak_demand = P_refrigeration × df_ref + P_processing × df_proc + P_lighting + P_auxiliary
```

The peak demand value guides transformer sizing. It is lower than installed
power because not all equipment operates at full load simultaneously.

### ProjectVersion snapshot structure for Task 5

When Task 5 calculations are persisted to a ProjectVersion, the snapshot
structure includes:

```json
{
  "cooling_load": {
    "calculator_name": "cooling_load",
    "calculator_version": "1.0.0",
    "result": {
      "zones": [...],
      "temperature_levels": [...],
      "design_refrigeration_load_kw_r": 150.0
    },
    "steps": [...],
    "coefficient_references": [...],
    "warnings": [...],
    "requires_review": true
  },
  "equipment": {
    "calculator_name": "equipment",
    "calculator_version": "1.0.0",
    "result": {
      "systems": [...],
      "total_compressor_capacity_kw_r": 165.0,
      "total_compressor_input_power_kw_e": 47.143,
      "total_condenser_rejection_kw": 260.0
    },
    "steps": [...],
    "warnings": [...]
  },
  "installed_power": {
    "calculator_name": "installed_power",
    "calculator_version": "1.0.0",
    "result": {
      "total_installed_power_kw_e": 320.0,
      "estimated_peak_demand_kw_e": 290.0
    },
    "steps": [...],
    "warnings": [...]
  }
}
```

Each calculator's result is independently stored and retrievable. The
`requires_review` flag propagates from coefficient metadata through all
calculators.

### Boundary with Task 4 (core calculations) and Task 6 (scheme generation)

**Task 4 → Task 5 dependency:**
- Task 4 provides the core calculation infrastructure: `CalculationResult`,
  `CalculationStep`, `CoefficientReference`, error types, and the
  coefficient domain service.
- Task 5 builds three calculators on top of this infrastructure.
- Task 5 does not modify Task 4 modules.

**Task 5 → Task 6 dependency:**
- Task 5 outputs capability requirements (kW(r), kW(e)) per temperature
  system.
- Task 6 uses these requirements to select specific equipment models from
  manufacturer catalogs.
- Task 5 results are the input specifications for Task 6 scheme generation.
- Task 6 may override Task 5 values if catalog constraints differ from
  calculated requirements.

**Data flow:**
```
Task 4 (infrastructure) → Task 5 (calculators) → Task 6 (equipment selection)
     ↓                          ↓                         ↓
CalculationResult          kW(r) requirements         Specific models
CoefficientSet            kW(e) installed power      Quantities & costs
Error types               Condenser rejection        Scheme document
```

## PostgreSQL Test Execution

### CI Pipeline Structure

The PostgreSQL CI job (`backend-postgresql`) runs the full test suite with
`DATABASE_BACKEND=postgresql` and excludes architecture tests:

```
pytest -k "not architecture"
```

### Test Counts

| Category | Count | Notes |
|---|---|---|
| Total tests collected | 353 | All test files under `backend/tests/` |
| Architecture tests | 16 | Excluded via `-k "not architecture"` |
| Non-architecture tests | 337 | Run in PostgreSQL CI job |
| Skipped under PostgreSQL | 10 | `test_core_calculation_api.py` — see below |
| Actually executed | 327 | Net tests that run against PostgreSQL |

### Skipped Tests

The entire `test_core_calculation_api.py` module (10 tests) is skipped when
`DATABASE_BACKEND=postgresql` via a module-level `pytestmark`:

```python
pytestmark = pytest.mark.skipif(
    os.environ.get("DATABASE_BACKEND") == "postgresql",
    reason="Integration tests use SQLite; skip on PostgreSQL CI",
)
```

**Reason:** These integration tests create an in-memory SQLite database via
`create_engine("sqlite://", ...)` and wire it into the FastAPI app. They
cannot use a PostgreSQL backend because:
- The test fixtures explicitly use SQLite connection args (`check_same_thread`)
- The `StaticPool` is SQLite-specific
- The app lifespan would attempt async PostgreSQL connection which requires
  asyncpg (not always available in CI)

### Integration Tests That Truly Test PostgreSQL vs Use SQLite Fixtures

| Test File | DB Backend | Truly Tests PostgreSQL? |
|---|---|---|
| `test_core_calculation_api.py` | SQLite (in-memory) | **No** — skipped on PostgreSQL CI |
| `test_project_api_persistence.py` | SQLite (file-based) | **No** — uses `sqlite:///{tmp_path}` |
| `test_coefficient_api.py` | SQLite (in-memory) | **No** — uses `create_engine("sqlite://")` |
| `test_coefficient_database.py` | SQLite (in-memory) | **No** — uses `create_engine("sqlite://")` |

**None of the integration tests use a real PostgreSQL database.** All four
integration test modules create SQLite fixtures regardless of the
`DATABASE_BACKEND` environment variable.

**What PostgreSQL CI actually validates:**
1. All **unit tests** run against PostgreSQL configuration (settings, models,
   domain logic that doesn't touch the database directly)
2. Alembic migrations run successfully against PostgreSQL (before tests)
3. The application can start with PostgreSQL backend configured
4. SQLAlchemy ORM models are compatible with PostgreSQL column types

**What PostgreSQL CI does NOT validate:**
1. Integration test API endpoints against a real PostgreSQL database
2. Concurrent database operations under PostgreSQL
3. PostgreSQL-specific SQL behaviors (e.g., JSONB, array types)
4. Connection pooling under PostgreSQL load
