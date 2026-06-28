# ISSUE-022: Formal Calculation Orchestration and Persistence Design

**Issue:** [#22](https://github.com/xuezhiorange-png/cold-storage-planning-agent/issues/22)
**Date:** 2026-06-28
**Status:** Design phase — awaiting review
**Type:** Architecture design only — no production implementation
**Unblocks:** Task 11 Phase B (PR #21)

---

## 1. Status and Decision Record

This document is a **design artefact only**.  It freezes the architecture
contract for a formal production calculation orchestration service that
SchemeService requires before it can be called from the evaluation runner.
No production code, migrations, API routes, or runtime behaviour is changed
by this document — implementation requires a separate reviewed task and PR.

**Decision authority:** This design is submitted for Engineering Review.
All "decisions" below are recommendations pending reviewer acceptance.

---

## 2. Problem Statement

**Current blocked state (Task 11 Phase B, PR #21):**

The evaluation runner (Phase B) must exercise all 8 required production stages;
the final stage, `schemes`, invokes `SchemeService.generate_scheme_run()`.
SchemeService is a DB-bound service that reads four category of
`CalculationRunRecord` directly from the database:

```
_REQUIRED_CALC_TYPES = frozenset({"zone", "investment", "cooling_load", "equipment"})
```

When any of these records is missing, SchemeService raises
`SourceCalculationMissingError`.  Today these records **do not exist**
outside the demo seeding path (`_ensure_demo_data()`), which uses
hard-coded demo values with `requires_review=False` (bypassing the review
contract).

The evaluation runner is therefore blocked by an explicit prerequisite gate
(`EvaluationPrerequisiteMissingError`, prerequisite_issue=22), waiting for
a formal production orchestration service that:

1. Accepts an immutable ProjectVersion snapshot.
2. Executes zone planning, cooling load, equipment capability calculation,
   and investment estimation as a production pipeline.
3. Persists results as `CalculationRunRecord` rows with full provenance.
4. Ensures SchemeService can trust those records as authoritative.

Without this service, SchemeService **cannot be called** from evaluation
and Task 11 Phase B cannot achieve `baseline expected_outcome=success`.

---

## 3. Existing-System Inventory

### 3.1 Production services and calculators

| Class / Function | File | Input | Output | Persistence | Notes |
|---|---|---|---|---|---|
| `DatabaseProjectService.create_project()` | `modules/projects/infrastructure/database.py` | name, location, product_category | ProjectRecord | SQLAlchemy session.commit() | |
| `DatabaseProjectService.create_version()` | same | project_id, change_summary, created_by | ProjectVersionRecord | session.commit() | |
| `DatabaseProjectService.save_inputs()` | same | project_id, version_number, inputs, actor | SaveInputsResult | session.commit() — writes version.input_snapshot | Version locked if status=approved/archived |
| `DatabaseProjectService.validate_inputs()` | `modules/projects/application/service.py` | inputs dict | {valid, missing_fields, tentative_fields} | None | Validates required fields presence only |
| `DatabaseProjectService.record_calculation()` | `modules/projects/infrastructure/database.py` | project_id, version_number, CalculationResult, actor | dict (record as dict) | session.add(CalculationRunRecord) + session.commit() | One session per call; no dedup |
| `DatabaseProjectService.list_calculations()` | same | project_id, version_number | list[dict] | Read-only query by project_version_id | |
| `DatabaseProjectService.save_core_calculation_result()` | same | project_id, version_number, result_snapshot, actor | {success} | Writes version.calculation_snapshot | Overall version-level snapshot |
| `CoreCalculationService.orchestrate_core_calculation()` | `modules/calculations/application/service.py` | ThroughputCalcInput, InventoryCalcInput, PalletCalcInput, PrecoolingCalcInput, InstalledPowerCalcInput | OrchestrationResult | None — returns in-memory result | Runs 5 sub-calculations |
| `ColdRoomZonePlanner.plan()` | `modules/calculations/domain/zone_planning.py` | ColdRoomZonePlanInput | ZonePlanResult (.success, .requires_review, .result.zones) | None — pure domain | Uses DemoZoneCoefficient → triggers review |
| `calculate_installed_power()` | `modules/calculations/domain/power.py` | InstalledPowerCalcInput | CalculationResult | None — pure domain | |
| `InvestmentEstimator.estimate()` | `modules/calculations/domain/investment.py` | InvestmentEstimateInput | InvestmentEstimateResult | None — pure domain | Uses DemoInvestmentCoefficient → triggers review |
| `calculate_cooling_load()` | `modules/calculations/domain/cooling_load.py` | CoolingLoadCalcInput | CalculationResult | None — pure domain | Envelope, product, infiltration, internal, defrost |
| Equipment calculator | `modules/calculations/domain/cooling_load.py` + `equipment.py` | equipment input (from cooling load + coefficient set) | CalculationResult | None — pure domain | Compressor, evaporator, condenser capability |
| `SchemeService.generate_scheme_run()` | `modules/schemes/application/service.py` | project_id, version, profile_codes, weight_set_id, profile_parameters | dict (schemes, recommended_code) | Uses SchemeRepository.save_run() | Reads 4 calc types from DB |

### 3.2 Data contracts

**CalculationRunRecord** (`modules/projects/infrastructure/orm.py`, table `calculation_runs`):

| Column | Type | Notes |
|---|---|---|
| id | VARCHAR(36) PK | UUID v4 |
| project_id | VARCHAR(36) FK→projects.id | |
| project_version_id | VARCHAR(36) FK→project_versions.id | |
| calculator_name | VARCHAR(120) | e.g. "zone", "cooling_load", "equipment", "investment" |
| calculator_version | VARCHAR(50) | Semantic version |
| input_snapshot | JSON | Raw input dict |
| result_snapshot | JSON | Raw result dict |
| formulas | JSON | list[dict] |
| coefficients | JSON | list[dict] |
| assumptions | JSON | list[str] |
| warnings | JSON | list[dict] |
| source_references | JSON | list[dict] |
| requires_review | BOOLEAN | |
| created_at | TIMESTAMPTZ | Auto-set |

**⚠️ Missing fields (confirmed gaps):**
- No `input_hash` (SHA-256 of canonicalized input_snapshot)
- No `result_hash` (SHA-256 of canonicalized result_snapshot)
- No `orchestration_run_id` (cross-record binding)
- No `coefficient_set_id` (which coefficient set was used)
- No `provenance` (source calculation IDs, upstream record references)
- No `schema_version` (snapshot schema version for evolution)
- No `status` (calculation lifecycle — always assumed "completed")
- No unique constraint preventing duplicate (calculator_name, project_version_id) runs

**CalculationResult** (`modules/calculations/domain/models.py`):

```python
@dataclass(frozen=True)
class CalculationResult:
    success: bool
    calculator_name: str
    calculator_version: str
    input_snapshot: dict[str, Any]
    result: dict[str, Any]
    steps: list[CalculationStep]
    coefficient_references: list[CoefficientReference]
    assumptions: list[str]
    warnings: list[CalculationWarning]
    requires_review: bool
    calculated_at: datetime
    correlation_id: str
```

Has `to_dict()` but `CalculationRunRecord` already stores fields individually.

**Coefficient registry** (`modules/coefficients/domain/models.py`):

- `CoefficientDefinition`: code, name, category, value_type, scope_type
- `CoefficientRevision`: status (draft→unverified→reviewed→approved→withdrawn), value, source metadata
- `CoefficientValue`: immutable resolved value
- `CoefficientSet`: schema_version, captured_at, items dict
- Resolution priority: project_version → project → product+zone+process → product → global
- `requires_review` = True for any non-approved revision

**SchemeService snapshot consumption** (from source code):

SchemeService parses these exact fields from `CalculationRunRecord.result_snapshot`:

| Calc Type | Consumed Fields |
|---|---|
| zone | zone_results[].zone_code, zone_name, temperature_level, area_m2, position_count, storage_capacity_kg, process_compatibility, hygiene_zone; total_daily_throughput_kg_day |
| investment | total_investment_cny; zone_investments |
| cooling_load | design_cooling_load_kw_r, sensible_load_kw_r, latent_load_kw_r, infiltration_load_kw_r |
| equipment | compressor_operating_capacity_kw_r, compressor_installed_capacity_kw_r, condenser_heat_rejection_kw, installed_power_kw_e |

SchemeService computes:
- `source_hash` = SHA-256(canonical_json(per_calc result_snapshots sorted by name))
- `per_calc_hash` = SHA-256(canonical_json(result_snapshot))
- `source_calc_ids` = dict mapping calc_name → record.id
- These are bound into SchemeGenerationInput and persisted in SchemeRun.

### 3.3 Existing coefficient registries

**Zone planning — `DemoZoneCoefficient`** (zone_planning.py):
- Hard-coded dataclass with demo values
- All values have `source_type="demo"`, `revision_status="unverified"`
- Triggers `requires_review=true` for all calculations

**Investment — `DemoInvestmentCoefficient`** (investment.py):
- Same pattern — demo, unverified
- Triggers review

**Equipment — `EquipmentCoefficientSet`** (equipment.py):
- redundancy_ratio, evaporator_capacity_margin, condenser_capacity_margin, compressor_cop
- `get_coefficient_metadata()` returns `requires_review` based on revision_status
- Default: revision_status = "demo" → requires_review = True

**Cooling load — coefficient set** (cooling_load.py):
- U-values, outdoor/indoor design temps, diversity factors, design margin
- Uses coefficient resolver pattern from `CoefficientMissingError` / `CoefficientReference`
- Missing coefficients raise `CoefficientMissingError`

**There is NO approved coefficient path today.** Every existing coefficient
set is demo/unverified. A baseline path to `requires_review=false` requires
a seeded approved coefficient catalog.

### 3.4 Audit

**AuditEventRecord** (`modules/projects/infrastructure/orm.py`, table `audit_events`):

| Column | Type |
|---|---|
| id | VARCHAR(36) PK |
| actor | VARCHAR(100) |
| action | VARCHAR(120) |
| entity_type | VARCHAR(120) |
| entity_id | VARCHAR(120) |
| before_snapshot | JSON |
| after_snapshot | JSON |
| event_metadata | JSON |
| created_at | TIMESTAMPTZ |

Existing actions: `run_project_calculations`, `save_core_calculation`, `save_design_inputs`, `reject_modify_approved_version`.

**No orchestration-level audit events** currently exist (orchestration_started, calculation_completed, orchestration_failed, etc.).

---

## 4. Confirmed Capability Gaps

| # | Gap | Evidence | Impact |
|---|---|---|---|
| G1 | No orchestration service | No module/service exists for running zone→cooling_load→equipment→investment as a pipeline | Blocked Task 11 Phase B |
| G2 | CalculationRunRecord lacks identity fields | Fields like input_hash, result_hash, orchestration_run_id, provenance not present in ORM | No cross-record binding; SchemeService can't verify source integrity |
| G3 | No approved coefficient path | All existing coefficient sets are demo/unverified | Baseline always triggers requires_review=true |
| G4 | Cooling-load/equipment calculators not wired to production | Calculators exist as domain functions but no application service invokes and persists them | No CalculationRunRecord for cooling_load/equipment |
| G5 | No idempotency | `record_calculation()` always creates new record with new UUID | Duplicate runs create duplicate records |
| G6 | No cross-record provenance | SchemeService loads "latest by calculator_name DESC" — no guarantee all came from same orchestration run | Tampered/stale records silently accepted |
| G7 | No zone record persistence | ColdRoomZonePlanner returns in-memory result; no CalculationRunRecord created | SchemeService can't find "zone" calculation |
| G8 | Investment uses placeholder upstream | Evaluation runner patches total_power_kw from power result but production has no pipeline | Investment lacks authoritative power input |
| G9 | No orchestration-level audit | Only per-record audit events exist | Can't track pipeline lifecycle |
| G10 | No concurrent execution guard | Multiple workers could create conflicting CalculationRunRecords | Non-deterministic authoritative record selection |

---

## 5. Scope and Non-Goals

### In scope (this design)

- Formal orchestration service contract
- Four-calculation DAG (zone → cooling_load → equipment → investment)
- Typed input/output models for each stage
- Persistence and transaction design
- Idempotency and authoritative record selection
- Hash and provenance chain
- Audit event contract
- Coefficient registry approved path
- Review/blocker propagation
- Error taxonomy
- Migration assessment
- Test matrix
- Task 11 resumption criteria

### Out of scope

- Implementation (separate task/PR)
- SchemeService changes (it already consumes CalculationRunRecord correctly)
- Evaluation/CLI changes (evaluation is a consumer)
- API endpoint design (orchestration may be API-exposed later — TBD)
- Equipment model selection (not part of capability calculator)
- Energy consumption (kWh) calculation
- Frontend changes
- Agent runtime integration
- New Alembic migrations (design assessment only)
- Changing existing calculation formulas or coefficients

---

## 6. Architecture Decision

### 6.1 Recommended module

```
backend/src/cold_storage/modules/orchestration/
├── application/
│   ├── __init__.py
│   └── service.py          # OrchestrationService (public entry point)
├── domain/
│   ├── __init__.py
│   ├── contracts.py         # Typed input/output dataclasses
│   ├── dag.py               # Execution DAG definition
│   ├── errors.py            # Orchestration-specific errors
│   └── hash_chain.py        # Hash and provenance builder
└── infrastructure/
    ├── __init__.py
    └── repository.py        # OrchestrationRunRepository
```

### 6.2 Orchestration ownership

**Recommendation:** `OrchestrationService` in `modules/orchestration/application/service.py`.

- Transactions owned by the orchestration service (it manages the session).
- No new module coupling: orchestration depends on existing production services
  (DatabaseProjectService, ColdRoomZonePlanner, calculators) but NOT vice versa.
- SchemeService remains a downstream consumer — it reads CalculationRunRecord
  directly from the database via its existing infrastructure.

**Explicitly NOT allowed:**
- ❌ Orchestration inside `SchemeService` — SchemeService generates schemes, doesn't run calculations.
- ❌ Orchestration inside `cold_storage.evaluation` — evaluation is a consumer, not a producer.
- ❌ Orchestration inside API routes or CLI commands.
- ❌ Orchestration inside `CalculationRunRecord` ORM model.

### 6.3 Service name

```
class OrchestrationService:
    """Formal production calculation orchestration.

    Accepts an immutable ProjectVersion snapshot, executes the calculation
    DAG (zone → cooling_load → equipment → investment), persists results
    as CalculationRunRecord rows with full provenance, and returns a typed
    orchestration result that SchemeService can trust.
    """

    def run(
        self,
        input: OrchestrationInput,
        session: Session,
    ) -> OrchestrationResult:
        ...
```

### 6.4 Transaction boundary

One orchestration `run()` executes inside a single SQLAlchemy session.
The session is provided by the caller (API route, CLI, or test fixture).

**Commit strategy:** All-or-nothing per orchestration run.
- If any stage fails: rollback entire session.
- If all stages succeed: commit once at end.
- No partial commits (no intermediate records visible to other sessions).

**Rationale:** Partial commits would produce inconsistent state where
SchemeService sees some but not all calculation types.

---

## 7. Public Application Contract

### 7.1 OrchestrationInput

```python
@dataclass(frozen=True, slots=True)
class OrchestrationInput:
    """Immutable input for a calculation orchestration run.

    All engineering values come from the ProjectVersion snapshot or
    an approved coefficient set identity.  No implicit defaults.
    """

    project_id: str
    project_version_id: str

    # From ProjectVersion.input_snapshot (read by orchestration service):
    #   daily_inbound_mass_kg, working_time_h_per_day, utilization_factor,
    #   finished_storage_days, packaging_storage_days, reserve_factor,
    #   shift_count, storage_position_capacity_kg, precooling_required_ratio,
    #   raw_holding_hours, secondary_fruit_ratio, frozen_fruit_ratio,
    #   frozen_storage_days, safety_stock_days, storage_ratio, etc.
    # These are loaded by the orchestration service, not passed by caller.

    # Coefficient set identity — REQUIRED, no default
    coefficient_set_id: str

    # Actor for audit trail
    actor: str

    # Execution correlation ID (provided by caller or auto-generated)
    correlation_id: str
```

### 7.2 OrchestrationResult

```python
@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    orchestration_run_id: str
    project_id: str
    project_version_id: str
    coefficient_set_id: str
    status: OrchestrationStatus  # COMPLETED | BLOCKED | FAILED
    stages: dict[str, StageResult]
    source_binding: SourceBinding  # for SchemeService consumption
    requires_review: bool
    started_at: datetime
    completed_at: datetime
    correlation_id: str
```

### 7.3 StageResult

```python
@dataclass(frozen=True, slots=True)
class StageResult:
    calculation_type: str  # zone | cooling_load | equipment | investment
    calculation_run_id: str  # persisted CalculationRunRecord.id
    status: str  # passed | failed | blocked
    requires_review: bool
    input_hash: str  # SHA-256 of canonicalized input
    result_hash: str  # SHA-256 of canonicalized result
    calculator_name: str
    calculator_version: str
```

### 7.4 SourceBinding

```python
@dataclass(frozen=True, slots=True)
class SourceBinding:
    """Immutable snapshot of calculation source records for SchemeService.

    Maps calculation_type → CalculationRunRecord identifying information.
    SchemeService can verify that all four records belong to the same
    orchestration run and that hashes match.
    """
    orchestration_run_id: str
    calculation_ids: dict[str, str]  # calc_type → record.id
    snapshot_hashes: dict[str, str]  # calc_type → SHA-256(result_snapshot)
    combined_source_hash: str  # SHA-256 over all four snapshots
    coefficient_set_id: str
    project_version_id: str
```

---

## 8. Execution DAG

### 8.1 Fixed dependency order

```
ProjectVersion.input_snapshot
      │
      ▼
  ┌─────────┐
  │  zone   │  ColdRoomZonePlanner.plan(ColdRoomZonePlanInput)
  └────┬────┘  Output: ZonePlanResult (zones, areas, positions, capacities)
       │
       ▼
  ┌──────────────┐
  │ cooling_load  │  calculate_cooling_load(CoolingLoadCalcInput)
  └──────┬───────┘  Output: CalculationResult (kW(r) per zone, totals)
         │
         ▼
  ┌──────────────┐
  │  equipment    │  Equipment capability calculator
  └──────┬───────┘  Output: CalculationResult (compressor/evaporator/condenser kW(r), kW(e))
         │
         ├──────────────────┐
         ▼                  ▼
  ┌──────────────┐  ┌──────────────┐
  │  investment   │  │   power      │  (if needed separately)
  └──────────────┘  └──────────────┘
         │                  │
         └────────┬─────────┘
                  ▼
          ┌──────────────┐
          │ SchemeService │  (downstream consumer — not part of orchestration)
          └──────────────┘
```

**Dependencies:**

| Stage | Upstream dependencies | Input source |
|---|---|---|
| zone | ProjectVersion.input_snapshot ONLY | throughput, storage days, temp bands, etc. |
| cooling_load | zone result | zone areas, temperature levels, envelope geometry, U-values from coefficient set |
| equipment | cooling_load result | design_cooling_load_kw_r per zone, coefficient set |
| investment | zone result + equipment result + power result | areas, position_count, total_power_kw_e, coefficient set |

**Key constraint:** `investment` requires `total_power_kw` from the **real power result**, not a placeholder zero. The power calculation runs as part of the equipment stage (compressor input power via COP). Investment consumes `equipment.installed_power_kw_e`.

### 8.2 Per-node definition

#### zone

| Aspect | Detail |
|---|---|
| Input | ColdRoomZonePlanInput (from ProjectVersion.input_snapshot + coefficient set) |
| Calculator | ColdRoomZonePlanner.plan() |
| Output | ZonePlanResult (.success, .requires_review, .result.zones) |
| Record | CalculationRunRecord(calculator_name="zone", ...) |
| Failure | Missing project inputs → blocked; zone planner raises exception → failed |

#### cooling_load

| Aspect | Detail |
|---|---|
| Input | CoolingLoadCalcInput (zones from zone result, geometry, U-values, design temps from coefficient set) |
| Calculator | calculate_cooling_load() |
| Output | CalculationResult (design_cooling_load_kw_r, sensible/latent/infiltration per zone) |
| Record | CalculationRunRecord(calculator_name="cooling_load", ...) |
| Failure | Missing coefficient → blocked; calculator exception → failed |

#### equipment

| Aspect | Detail |
|---|---|
| Input | ZoneEquipmentInput[] (from cooling_load per-zone results) + coefficient set |
| Calculator | equipment calculator |
| Output | CalculationResult (compressor_operating/installed_capacity_kw_r, condenser_heat_rejection_kw, installed_power_kw_e) |
| Record | CalculationRunRecord(calculator_name="equipment", ...) |
| Failure | Same as above |

#### investment

| Aspect | Detail |
|---|---|
| Input | InvestmentEstimateInput (total_area_m2 from zone, refrigerated/frozen area from zone, position_count from zone, total_power_kw from equipment.installed_power_kw_e, coefficient set) |
| Calculator | InvestmentEstimator.estimate() |
| Output | InvestmentEstimateResult |
| Record | CalculationRunRecord(calculator_name="investment", ...) |
| Failure | Missing upstream → handler blocks BEFORE calling estimator |

---

## 9. Typed Inputs and Outputs

### 9.1 Zone input mapping contract

`OrchestrationService` maps `ProjectVersion.input_snapshot` → `ColdRoomZonePlanInput`:

```python
def _build_zone_input(
    version_inputs: dict[str, Any],
    coefficients: CoefficientSet,
) -> ColdRoomZonePlanInput:
    """Map ProjectVersion.input_snapshot to deterministic zone planning input.

    Every value comes from either the version snapshot (project-specific)
    or the approved coefficient set (engineering parameter).  No hard-coded
    defaults at orchestration level — missing fields fail closed.
    """
    return ColdRoomZonePlanInput(
        daily_inbound_mass_kg=float(_require_field(version_inputs, "daily_inbound_mass_kg")),
        working_time_h_per_day=float(_require_field(version_inputs, "working_time_h_per_day")),
        finished_storage_days=float(_require_field(version_inputs, "finished_storage_days")),
        packaging_storage_days=float(_require_field(version_inputs, "packaging_storage_days")),
        precooling_required_ratio=float(_get_coefficient(coefficients, "precooling.required_ratio")),
        raw_holding_hours=float(_get_coefficient(coefficients, "zone.raw_holding_hours")),
        storage_position_capacity_kg=float(_get_coefficient(coefficients, "zone.position_capacity_kg")),
        secondary_fruit_ratio=float(_get_coefficient(coefficients, "zone.secondary_fruit_ratio")),
        frozen_fruit_ratio=float(_get_coefficient(coefficients, "zone.frozen_fruit_ratio")),
        frozen_storage_days=float(_get_coefficient(coefficients, "zone.frozen_storage_days")),
        # ... all other fields from project inputs or coefficient set
    )
```

**Owner:** `OrchestrationService` — no evaluation, no SchemeService.

### 9.2 Cooling-load input contract

Zone result → cooling load input mapping:

| CoolingLoadCalcInput field | Source |
|---|---|
| zones[].zone_code | zone result |
| zones[].temperature_level | zone result |
| zones[].area_m2 | zone result |
| zones[].envelope_geometry | ProjectVersion.input_snapshot building geometry |
| zones[].u_values | CoefficientSet (U_wall, U_roof, U_floor) |
| zones[].design_indoor_temp_c | CoefficientSet (per temperature level) |
| zones[].design_outdoor_temp_c | CoefficientSet (location-dependent) |
| zones[].air_change_rate | CoefficientSet |
| zones[].product_load_params | ProjectVersion.input_snapshot (product type, mass, specific heat) |
| zones[].internal_loads | CoefficientSet (lighting W/m², personnel count, equipment power) |
| zones[].diversity_factor | CoefficientSet (per temperature level) |
| design_margin_ratio | CoefficientSet |

**Fields without a formal source → BLOCKED (no 0/default fallback).**

### 9.3 Equipment input contract

Cooling load result → equipment input mapping:

| Equipment input field | Source |
|---|---|
| zones[].design_cooling_load_kw_r | cooling_load result (per zone) |
| zones[].temperature_level | zone result |
| zones[].evaporator_count | Derived: 1 per zone (configurable via coefficient) |
| redundancy_ratio | CoefficientSet |
| condenser_capacity_margin | CoefficientSet |
| compressor_cop | CoefficientSet |

**Equipment result and installed-power result are one calculation.**
The equipment calculator outputs `installed_power_kw_e` as part of its result.
No separate power-only calculation needed.

### 9.4 Investment input contract

| InvestmentEstimateInput field | Source |
|---|---|
| total_area_m2 | sum(zone result zones[].area_m2) |
| refrigerated_area_m2 | sum(zone result zones where temp ≠ 常温 .area_m2) |
| frozen_area_m2 | sum(zone result zones where temp = -18℃ .area_m2) |
| position_count | sum(zone result zones[].position_count) |
| total_power_kw | equipment result.installed_power_kw_e |

**`total_power_kw=0` is forbidden.** If equipment stage failed, investment
is skipped (blocked), not run with zero.

### 9.5 SchemeService snapshot schema

SchemeService already parses `CalculationRunRecord.result_snapshot`.
The orchestration must ensure each record's `result_snapshot` contains
exactly the fields SchemeService expects:

**zone result_snapshot:**
```json
{
  "schema_version": "1.0",
  "calculator_name": "zone",
  "calculator_version": "1.0.0",
  "zone_results": [
    {
      "zone_code": "precooling-primary",
      "zone_name": "双级预冷间",
      "temperature_level": "precooling",
      "area_m2": 112.0,
      "position_count": 20,
      "storage_capacity_kg": 8800.0,
      "process_compatibility": "raw",
      "hygiene_zone": "standard"
    }
  ],
  "total_daily_throughput_kg_day": 25000.0
}
```

**cooling_load result_snapshot:**
```json
{
  "schema_version": "1.0",
  "design_cooling_load_kw_r": 180.0,
  "sensible_load_kw_r": 150.0,
  "latent_load_kw_r": 20.0,
  "infiltration_load_kw_r": 10.0
}
```

**equipment result_snapshot:**
```json
{
  "schema_version": "1.0",
  "compressor_operating_capacity_kw_r": 180.0,
  "compressor_installed_capacity_kw_r": 216.0,
  "condenser_heat_rejection_kw": 240.0,
  "installed_power_kw_e": 65.0
}
```

**investment result_snapshot:**
```json
{
  "schema_version": "1.0",
  "total_investment_cny": 6150420.50,
  "zone_investments": {}
}
```

Each snapshot includes a `schema_version` field for forward compatibility.

---

## 10. Persistence and Transactions

### 10.1 Decision: Reuse `DatabaseProjectService.record_calculation()`

The existing `record_calculation(project_id, version_number, CalculationResult, actor)`
already creates `CalculationRunRecord` rows with correct foreign keys and audit.
We extend it rather than building a parallel persistence path.

**Required extensions to `CalculationRunRecord`:**

| New field | Type | Purpose |
|---|---|---|
| input_hash | VARCHAR(64) NULLABLE | SHA-256 of canonicalized input_snapshot |
| result_hash | VARCHAR(64) NULLABLE | SHA-256 of canonicalized result_snapshot |
| orchestration_run_id | VARCHAR(36) NULLABLE FK→orchestration_runs.id | Cross-record binding |
| coefficient_set_id | VARCHAR(36) NULLABLE | Which coefficient set was used |
| schema_version | VARCHAR(20) DEFAULT "1.0" | Snapshot schema version |
| provenance | JSON NULLABLE | Upstream calculation IDs |

### 10.2 New table: `orchestration_runs`

```sql
CREATE TABLE orchestration_runs (
    id VARCHAR(36) PRIMARY KEY,
    project_id VARCHAR(36) NOT NULL REFERENCES projects(id),
    project_version_id VARCHAR(36) NOT NULL REFERENCES project_versions(id),
    coefficient_set_id VARCHAR(36) NOT NULL,
    status VARCHAR(20) NOT NULL,  -- RUNNING | COMPLETED | BLOCKED | FAILED
    requires_review BOOLEAN NOT NULL DEFAULT FALSE,
    source_binding JSON,  -- SourceBinding serialised
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    actor VARCHAR(100) NOT NULL,
    correlation_id VARCHAR(36) NOT NULL
);

CREATE UNIQUE INDEX uq_orch_run_version
    ON orchestration_runs (project_version_id, coefficient_set_id)
    WHERE status = 'COMPLETED';
```

The partial unique index ensures only one COMPLETED orchestration run
exists per (project_version, coefficient_set). This provides idempotency:
re-running with the same inputs returns the existing run.

### 10.3 Transaction strategy

```
1. BEGIN transaction
2. Validate project_version exists and is mutable (not approved/archived)
3. Create orchestration_run record (status=RUNNING)
4. Create audit event: orchestration_started
5. For each stage in DAG order:
   a. Build input from upstream results + ProjectVersion + coefficient set
   b. Compute input_hash before calling calculator
   c. Call calculator
   d. Compute result_hash from canonicalized result
   e. Create CalculationRunRecord with hash, orchestration_run_id, provenance
   f. Create audit event: calculation_completed
   g. If failed/blocked: mark stage blocked, continue to determine overall status
6. Compute SourceBinding
7. Update orchestration_run status → COMPLETED | BLOCKED
8. Create audit event: orchestration_completed | orchestration_failed
9. COMMIT

On any unhandled exception:
   ROLLBACK entire transaction
```

### 10.4 Idempotency

**Identity key:** `(project_version_id, coefficient_set_id, calculation_type, input_hash)`

- Same inputs + same project_version → return existing CalculationRunRecord.id.
  Do NOT create duplicate.
- Changed inputs → new run (different input_hash).
- Changed coefficient set → new run (different coefficient_set_id).

**Authoritative record selection:**
- SchemeService calls `_load_all_calculations(project_version_id)` → returns
  latest per calculator_name (ordered by created_at DESC, id DESC).
- If multiple runs exist for same calculator_name, latest wins.
- With the partial unique index on `(project_version_id, coefficient_set_id)`,
  only one COMPLETED orchestration can produce records per set.
- SchemeService can verify `orchestration_run_id` matches across all four records.

### 10.5 Concurrency

- **SQLite:** Serialized by default. No concurrent writes.
- **PostgreSQL:** Use `SELECT ... FOR UPDATE` on the `orchestration_runs` row
  or an advisory lock on `(project_version_id)`.
- The partial unique index prevents two concurrent orchestrations from both
  completing for the same (project_version, coefficient_set).

---

## 11. Hash and Provenance

### 11.1 Hash algorithm

```
SHA-256 of canonical_json(obj)
```

Where `canonical_json()`:
- Sorts keys alphabetically.
- Uses `separators=(",", ":")` (no whitespace).
- `ensure_ascii=False`.
- Decimal → string representation.
- datetime → ISO-8601 with timezone.
- UUID → string.

This matches the existing `_canonical_json()` in SchemeService.

### 11.2 What goes into hashes

| Hash | Content |
|---|---|
| input_hash | canonical_json(calculator_input_dict) excluding timestamps, correlation_id |
| result_hash | canonical_json(result_snapshot_dict) including schema_version, calculator_name, calculator_version |
| per_calc_hash | canonical_json(CalculationRunRecord.result_snapshot) — same as result_hash |
| combined_source_hash | canonical_json({calc_type: result_snapshot for calc_type in sorted order}) |

### 11.3 Provenance chain

Each `CalculationRunRecord` stores in `provenance`:
```json
{
  "orchestration_run_id": "...",
  "upstream_calculation_ids": {
    "zone": "<zone calc run id>",
    "cooling_load": "<cooling load calc run id>"
  },
  "coefficient_set_id": "...",
  "project_version_id": "..."
}
```

Investment's provenance includes zone, cooling_load, and equipment IDs.
SchemeService verifies all four records share the same `orchestration_run_id`.

### 11.4 Cross-record integrity

`SourceBinding` provides SchemeService with:
- `orchestration_run_id` — all four records must match.
- `calculation_ids` — exact record.id for each calc_type.
- `snapshot_hashes` — pre-computed SHA-256 of each result_snapshot.
- `combined_source_hash` — overall hash for tamper detection.

SchemeService can verify:
1. Each record exists and its `result_snapshot` hash matches `snapshot_hashes`.
2. All four records share the same `orchestration_run_id`.
3. `combined_source_hash` recomputes to the same value.

---

## 12. Audit Events

### 12.1 New audit actions

| Action | Phase | entity_type | entity_id |
|---|---|---|---|
| orchestration_started | Start | OrchestrationRun | orchestration_run_id |
| calculation_completed | Per stage | CalculationRun | calc_run_id |
| calculation_blocked | Per stage (prerequisite missing) | CalculationRun | calc_run_id |
| calculation_failed | Per stage (exception) | — | — |
| orchestration_completed | End (success/blocked) | OrchestrationRun | orchestration_run_id |
| orchestration_failed | End (exception) | OrchestrationRun | orchestration_run_id |
| source_binding_materialized | After completion | OrchestrationRun | orchestration_run_id |

### 12.2 Audit event schema (per event)

```json
{
  "actor": "orchestration-service",
  "action": "calculation_completed",
  "entity_type": "CalculationRun",
  "entity_id": "<calc_run_id>",
  "before_snapshot": {},
  "after_snapshot": {
    "calculator_name": "cooling_load",
    "input_hash": "abc123...",
    "result_hash": "def456...",
    "requires_review": false
  },
  "event_metadata": {
    "project_id": "...",
    "project_version_id": "...",
    "orchestration_run_id": "...",
    "calculation_type": "cooling_load",
    "correlation_id": "..."
  }
}
```

Audit events are created by `DatabaseProjectService._add_audit()` within
the same transaction. They are NOT created by the evaluation runner.

---

## 13. Coefficient Registry — Approved Path

### 13.1 Required approved coefficient definitions

To achieve `requires_review=false` for a baseline scenario, the following
coefficient definitions must have at least one **approved** revision:

| Category | Definitions |
|---|---|
| Zone planning | storage_position_capacity_kg, secondary_fruit_ratio, frozen_fruit_ratio, frozen_storage_days, precooling_position_daily_capacity_kg, primary_precooling_pallet_weight_kg, primary_precooling_hours_per_pallet, secondary_precooling_pallet_weight_kg, secondary_precooling_hours_per_pallet, raw_storage_ratio, precooling_required_ratio, raw_holding_hours, pallet dimensions, gaps |
| Cooling load | U_wall, U_roof, U_floor, design_indoor_temp_c (per level), design_outdoor_temp_c, air_change_rate, lighting_w_per_m2, personnel_heat_w_per_person, equipment_motor_efficiency, diversity_factor (per level), design_margin_ratio |
| Equipment | redundancy_ratio, evaporator_capacity_margin, condenser_capacity_margin, compressor_cop |
| Investment | unit_cost_per_m2, unit_cost_per_kw, regional_factor, circulation_allowance_ratio, equipment_cost_ratio, installation_cost_ratio |

### 13.2 CoefficientSet identity

A `coefficient_set_id` identifies a specific, immutable CoefficientSet.
The orchestration service resolves coefficients at the start of each run
and captures their values in an immutable snapshot. The same `coefficient_set_id`
can be reused for idempotency — same inputs + same set = same results.

### 13.3 Demo vs approved

- **Demo**: `source_type="demo"`, `revision_status="unverified"`, `requires_review=True`
- **Approved**: `source_type="standard"|"book"|"enterprise_standard"`, `revision_status="approved"`, `requires_review=False`

The orchestration service MUST use the coefficient resolver to get the
highest-priority approved revision. If no approved revision exists, the
orchestration is **blocked** (fail-closed), not demo-fallback.

---

## 14. Review/Blocker Propagation

### 14.1 Stage-level

| Condition | Stage status | requires_review |
|---|---|---|
| Calculator returns success, no warnings, all coefficients approved | passed | false |
| Calculator returns success, any coefficient non-approved or any warning | passed | true |
| Missing required input or coefficient | blocked | — |
| Calculator raises exception | failed | — |

### 14.2 Orchestration-level (aggregated)

```
1. Any stage blocked/failed?
   → orchestration.status = BLOCKED | FAILED
2. Any stage requires_review = true?
   → orchestration.requires_review = true
3. Otherwise:
   → orchestration.status = COMPLETED, requires_review = false
```

### 14.3 SchemeService consumption

SchemeService does NOT re-evaluate review status. It trusts the
`CalculationRunRecord.requires_review` field as set by the orchestration.
SchemeService's own review flag derives from scheme generation constraints
and weight set metadata — independent of upstream review status.

---

## 15. Error Taxonomy

### 15.1 Typed exception hierarchy

All exceptions inherit from `OrchestrationError(code, message, field)`.

| Exception class | code | field | retryable | HTTP (if exposed) |
|---|---|---|---|---|
| ProjectVersionNotFoundError | PROJ_VERSION_NOT_FOUND | project_version_id | No | 404 |
| ProjectVersionLockedError | PROJ_VERSION_LOCKED | project_version_id | No | 409 |
| CoefficientSetNotFoundError | COEFF_SET_NOT_FOUND | coefficient_set_id | No | 404 |
| CoefficientNotApprovedError | COEFF_NOT_APPROVED | coefficient_code | No | 422 |
| AmbiguousCoefficientSetError | COEFF_AMBIGUOUS | coefficient_set_id | No | 409 |
| CalculationInputMappingError | CALC_INPUT_MAPPING_FAILED | calc_type | No | 422 |
| CalculationExecutionError | CALC_EXECUTION_FAILED | calc_type | Maybe (timeout) | 500 |
| CalculationPersistenceError | CALC_PERSIST_FAILED | calc_type | Yes | 500 |
| DuplicateOrchestrationError | ORCH_DUPLICATE | project_version_id | No | 409 |
| SourceCalculationMissingError | SOURCE_CALC_MISSING | calc_type | No | 422 |
| SourceCalculationTamperedError | SOURCE_CALC_TAMPERED | calc_type | No | 422 |
| ProvenanceMismatchError | PROVENANCE_MISMATCH | calc_type | No | 422 |
| HashMismatchError | HASH_MISMATCH | calc_type | No | 422 |
| AuditWriteError | AUDIT_WRITE_FAILED | — | Yes | 500 |

### 15.2 Fail-closed default

Missing fields, missing coefficients, and missing upstream results must
**always fail closed**. No zero-fallback, no demo fallback, no silent skip.

---

## 16. API/CLI Boundary

### 16.1 Decision: No API/CLI in Issue #22 scope

The orchestration service is a Python application service callable by:
1. Backend API routes (future — separate task).
2. CLI evaluation runner (existing — Task 11 Phase B).
3. Test fixtures (immediate need).

API endpoint design is deferred to a later task. The orchestration service
accepts a SQLAlchemy `Session` parameter, making it callable from any context.

### 16.2 Service dependency injection

```python
# From API route (future):
with session_factory() as session:
    orch = OrchestrationService()
    result = orch.run(input, session)

# From evaluation runner:
with SqliteScope() as scope:
    result = orch.run(input, scope.session)

# From tests:
with session_factory() as session:
    result = orch.run(input, session)
```

---

## 17. Migration Assessment

### 17.1 Required schema changes

| Change | Table | Type |
|---|---|---|
| Add `orchestration_runs` table | New | CREATE TABLE |
| Add `input_hash` VARCHAR(64) | calculation_runs | ALTER TABLE ADD COLUMN (nullable) |
| Add `result_hash` VARCHAR(64) | calculation_runs | ALTER TABLE ADD COLUMN (nullable) |
| Add `orchestration_run_id` VARCHAR(36) FK | calculation_runs | ALTER TABLE ADD COLUMN + FK |
| Add `coefficient_set_id` VARCHAR(36) | calculation_runs | ALTER TABLE ADD COLUMN (nullable) |
| Add `schema_version` VARCHAR(20) DEFAULT '1.0' | calculation_runs | ALTER TABLE ADD COLUMN |
| Add `provenance` JSON | calculation_runs | ALTER TABLE ADD COLUMN (nullable) |
| Add partial unique index | orchestration_runs | CREATE UNIQUE INDEX |

### 17.2 Migration order

1. Create `orchestration_runs` table (no FKs to it yet).
2. Add columns to `calculation_runs` (all nullable — backward compatible).
3. Add FK from `calculation_runs.orchestration_run_id` → `orchestration_runs.id`.
4. Add partial unique index on `orchestration_runs`.

### 17.3 Rollback risk

- **Low**: All new columns are nullable. Existing records have NULL for new fields.
- Existing queries (SchemeService._load_all_calculations, list_calculations) are unaffected.
- Alembic downgrade removes columns and table cleanly.

---

## 18. Security and Integrity

### 18.1 Tamper detection

- `input_hash` and `result_hash` are stored alongside the data.
- SchemeService can recompute hash and compare.
- Hash mismatch → `SourceCalculationTamperedError`.
- `combined_source_hash` covers all four snapshots — any single record tampered is detected.

### 18.2 Stale record detection

- Orchestration run has `completed_at`.
- SchemeService can verify `orchestration_run.completed_at` is within acceptable window.
- Records from different orchestration runs have different `orchestration_run_id`.

### 18.3 SQLite vs PostgreSQL

| Concern | SQLite | PostgreSQL |
|---|---|---|
| Concurrent writes | Serialized (database lock) | MVCC + row-level locks |
| Advisory lock | Not available | `pg_advisory_xact_lock()` |
| Partial unique index | Supported | Supported |
| Transaction isolation | Serializable | Read Committed (default) |
| FK enforcement | Enabled (PRAGMA foreign_keys=ON) | Enabled |

Design uses portable SQL — no PostgreSQL-specific features required.

---

## 19. Test Matrix

### 19.1 Unit tests

| Test | What it verifies |
|---|---|
| DAG topological order | Stages execute in: zone → cooling_load → equipment → investment |
| Input mapping — zone | ProjectVersion.input_snapshot → ColdRoomZonePlanInput |
| Input mapping — cooling_load | Zone result → CoolingLoadCalcInput |
| Input mapping — equipment | Cooling load result → equipment input |
| Input mapping — investment | Zone + equipment result → InvestmentEstimateInput |
| Missing project input → fail closed | Missing daily_inbound_mass_kg → CalculationInputMappingError |
| Missing coefficient → fail closed | Missing U-value → CoefficientNotApprovedError |
| Hash computation | input_hash matches SHA-256(canonical_json(input)) |
| Hash computation | result_hash matches SHA-256(canonical_json(result)) |
| SourceBinding construction | All four calc IDs and hashes captured |
| Requires_review propagation | Any stage requires_review → orchestration requires_review=true |
| All stages passed + approved coefficients | orchestration.requires_review=false |
| Blocked stage stops downstream | cooling_load blocked → equipment, investment skipped |

### 19.2 Application orchestration tests

| Test | What it verifies |
|---|---|
| Happy path — all four stages succeed | OrchestrationResult(status=COMPLETED), 4 CalculationRunRecords |
| Approved coefficient baseline | requires_review=false for all stages and orchestration |
| Demo coefficient path | requires_review=true for affected stages |
| Partial failure — equipment fails | Zone and cooling_load records committed? No — all-or-nothing rollback |
| Missing prerequisite — no zone input | Orchestration blocked before any calculation |
| Concurrent orchestration — same inputs | DuplicateOrchestrationError or idempotent return |
| Project version locked | ProjectVersionLockedError raised |

### 19.3 Repository tests

| Test | What it verifies |
|---|---|
| Create orchestration run | OrchestrationRunRecord persisted with correct fields |
| Create calculation record with new fields | input_hash, result_hash, orchestration_run_id stored |
| List calculations by orchestration_run_id | All four records returned |
| Partial unique index | Two COMPLETED runs for same (project_version, coefficient_set) rejected |
| Nullable new columns | Existing records (no hash/provenance) still readable |

### 19.4 Integration tests

| Test | Backend | What it verifies |
|---|---|---|
| Full orchestration SQLite | SQLite | All four records persisted, SchemeService reads them |
| Full orchestration PostgreSQL | PostgreSQL | Same, with PostgreSQL-specific constraints |
| Idempotent retry SQLite | SQLite | Second run returns existing orchestration_run_id |
| Idempotent retry PostgreSQL | PostgreSQL | Same |
| Concurrent runs PostgreSQL | PostgreSQL | Advisory lock prevents double execution |

### 19.5 Tamper tests

| Test | What it verifies |
|---|---|
| Tampered result_snapshot hash | Hash mismatch detected by SchemeService |
| Cross-orchestration records | Records from two different runs have different orchestration_run_id |
| Missing source calculation | SourceCalculationMissingError |
| Stale record | orchestration_run completed_at > threshold |

### 19.6 Audit tests

| Test | What it verifies |
|---|---|
| orchestration_started event | Audit event with correct metadata |
| calculation_completed per stage | One event per successful stage |
| orchestration_completed event | Final audit event |
| orchestration_failed event | On exception/rollback |

---

## 20. Task 11 Phase B Resumption Criteria

Issue #22 is complete when **all** of the following are true:

1. **Independent production PR merged** — separate from PR #21, with its own
   Engineering Review pass.
2. **Four CalculationRunRecord types produced by OrchestrationService** —
   zone, cooling_load, equipment, investment — all persisted via
   `DatabaseProjectService.record_calculation()`.
3. **All four records bound to same `ProjectVersion` and `orchestration_run_id`** —
   SourceBinding contract satisfied.
4. **Hashes, provenance, and audit events complete** — `input_hash`,
   `result_hash`, `provenance`, and audit trail for every stage.
5. **SchemeService consumption verified** — `generate_scheme_run()` reads
   the four records successfully and produces a valid SchemeRun.
6. **Approved coefficient baseline** — a coefficient set with all-approved
   revisions produces `requires_review=false` for all stages.
7. **Missing/tampered records fail closed** — SchemeService raises
   appropriate error on missing or tampered source data.
8. **SQLite and PostgreSQL tests pass** — CI confirms both backends.
9. **Task 11 baseline achievable** — after rebasing PR #21 onto the Issue #22
   branch, the evaluation runner's baseline-feasible scenario passes all 8
   required stages with `outcome=success`.
10. **PR #21 rebased onto main** — only after Issue #22 merges.

---

## 21. Open Questions

1. **Coefficient catalog seeding:** Who creates the approved coefficient
   revisions? Should Task 3 (coefficient registry) or a separate coefficient
   curation task deliver the approved values?
   → Recommendation: Separate "approved coefficient catalog" subtask
   (Issue #22-B) that seeds approved revisions for baseline path.

2. **API exposure:** Should `POST /api/v1/projects/{id}/versions/{v}/orchestrate`
   be part of Issue #22 or deferred?
   → Recommendation: Defer. Orchestration service is callable from evaluation
   runner directly. API endpoint can be a follow-up.

3. **Weight set dependency:** SchemeService also needs a weight set. Is
   `demo-weight-set-001` acceptable for Phase B or does it need its own
   approved path?
   → Recommendation: Address in Issue #22 or a follow-up. The weight set is
   a SchemeService concern, not an orchestration concern.

4. **Room height and envelope geometry:** These are needed for cooling load
   but not in current `ProjectVersion.input_snapshot`.
   → Recommendation: Add to input_snapshot schema as part of Issue #22.

5. **Installed power calculator:** Should it be a separate calculation stage
   or part of equipment?
   → Recommendation: Part of equipment stage. The equipment calculator
   already outputs `installed_power_kw_e`. No separate power stage needed.

---

## 22. Implementation Work Breakdown

### A. Typed orchestration contracts
- Scope: `OrchestrationInput`, `OrchestrationResult`, `StageResult`, `SourceBinding` dataclasses
- Dependencies: None (pure domain models)
- Files: `modules/orchestration/domain/contracts.py`
- Acceptance: All typed models immutable, JSON-serializable, documented

### B. Coefficient registry approved path
- Scope: Seed approved coefficient revisions for baseline scenario
- Dependencies: Coefficient registry (Task 3)
- Files: `modules/coefficients/` (seed data), Alembic migration for seed
- Acceptance: Baseline scenario produces `requires_review=false`

### C. Production calculation adapters
- Scope: Input mapping functions (ProjectVersion → calculator inputs)
- Dependencies: A (contracts), B (coefficients)
- Files: `modules/orchestration/application/adapters.py`
- Acceptance: Unit-tested mapping with fail-closed missing fields

### D. Orchestration transaction and persistence
- Scope: `OrchestrationService.run()`, DAG executor, transaction management
- Dependencies: A, B, C
- Files: `modules/orchestration/application/service.py`, `infrastructure/repository.py`
- Acceptance: Full happy-path integration test, rollback on failure

### E. Snapshot schema and versioning
- Scope: `schema_version` in CalculationRunRecord.result_snapshot
- Dependencies: D
- Files: `modules/orchestration/domain/snapshot_schema.py`
- Acceptance: All four snapshots parseable by SchemeService with schema_version

### F. Provenance and audit
- Scope: Hash computation, provenance chain, audit events
- Dependencies: D
- Files: `modules/orchestration/domain/hash_chain.py`
- Acceptance: input_hash, result_hash, provenance stored; audit events created

### G. SchemeService source binding
- Scope: Verify SchemeService reads orchestrated records correctly
- Dependencies: D, E, F
- Files: Existing `SchemeService` (no changes), test file
- Acceptance: `generate_scheme_run()` succeeds with orchestrated records

### H. SQLite/PostgreSQL integration tests
- Scope: Full pipeline integration tests on both backends
- Dependencies: D, E, F, G
- Files: `tests/integration/test_orchestration.py`
- Acceptance: CI green for both backends

### I. Task 11 Phase B resumption
- Scope: Rebase PR #21, remove prerequisite gate, verify baseline success
- Dependencies: A–H complete
- Files: PR #21 (rebase), `execute.py` (remove gate)
- Acceptance: baseline-feasible: outcome=success, all 8 stages passed

---

## Appendix A: File Reference Index

| File | Content |
|---|---|
| `backend/src/cold_storage/modules/projects/infrastructure/database.py` | DatabaseProjectService with create/version/inputs/record_calculation |
| `backend/src/cold_storage/modules/projects/infrastructure/orm.py` | CalculationRunRecord, AuditEventRecord ORM models |
| `backend/src/cold_storage/modules/projects/application/service.py` | validate_inputs, record_calculation (in-memory) |
| `backend/src/cold_storage/modules/calculations/application/service.py` | CoreCalculationService.orchestrate_core_calculation |
| `backend/src/cold_storage/modules/calculations/domain/zone_planning.py` | ColdRoomZonePlanner, ColdRoomZonePlanInput, DemoZoneCoefficient |
| `backend/src/cold_storage/modules/calculations/domain/cooling_load.py` | CoolingLoadCalcInput, calculate_cooling_load |
| `backend/src/cold_storage/modules/calculations/domain/equipment.py` | EquipmentCoefficientSet, equipment calculator |
| `backend/src/cold_storage/modules/calculations/domain/power.py` | InstalledPowerCalcInput, calculate_installed_power |
| `backend/src/cold_storage/modules/calculations/domain/investment.py` | InvestmentEstimator, InvestmentEstimateInput |
| `backend/src/cold_storage/modules/calculations/domain/models.py` | CalculationResult, CalculationStep, CoefficientReference |
| `backend/src/cold_storage/modules/schemes/application/service.py` | SchemeService.generate_scheme_run, _REQUIRED_CALC_TYPES, snapshot parsing |
| `backend/src/cold_storage/modules/coefficients/domain/models.py` | CoefficientDefinition, CoefficientRevision, state machine |
| `backend/src/cold_storage/modules/audit/domain/__init__.py` | AuditEvent |
| `docs/architecture/ADR-011-engineering-coefficient-registry.md` | Coefficient registry architecture |
| `docs/architecture/ADR-013-cooling-load-equipment.md` | Cooling load and equipment calculator design |
| `docs/schemes/scheme-generation-specification.md` | Scheme generation profiles and input sources |
| `docs/audit/coefficient-inventory.md` | Complete inventory of hardcoded coefficients |
| `docs/audit/gap-analysis.md` | Known capability gaps |
