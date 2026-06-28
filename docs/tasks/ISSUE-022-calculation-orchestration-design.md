# ISSUE-022: Formal Calculation Orchestration and Persistence Design

**Issue:** [#22](https://github.com/xuezhiorange-png/cold-storage-planning-agent/issues/22)
**Date:** 2026-06-28
**Review:** 4587035384 — first-round engineering review addressed
**Status:** Design phase — awaiting re-review
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

**Changes in this revision (vs 3a72d8d):**

1. SourceBinding frozen as explicit SchemeService input (`source_binding_id`).
2. Transaction-aware repository layer split from `DatabaseProjectService`; durable failure audit via two-phase commit/outbox.
3. Independent `power` stage restored in DAG — not merged into equipment.
4. Versioned `SourceSnapshotV1` adapters with complete field mapping tables.
5. Materialized `CoefficientContextRecord` with immutable identity hash.
6. Unified orchestration fingerprint replacing `(project_version_id, coefficient_set_id)`.
7. `ProjectVersionExecutionSnapshot` lifecycle and immutability contract.
8. Review propagation limited to calculator-originated `requires_review` — no "any warning" rules.
9. Legacy migration strategy: unversioned/unbound rows rejected by new paths.
10. All five open questions closed with frozen decisions.

---

## 2. Problem Statement

**Current blocked state (Task 11 Phase B, PR #21):**

The evaluation runner (Phase B) must exercise all 8 required production stages;
the final stage, `schemes`, invokes `SchemeService.generate_scheme_run()`.
SchemeService is a DB-bound service that reads four categories of
`CalculationRunRecord` directly from the database:

```
_REQUIRED_CALC_TYPES = frozenset({"zone", "investment", "cooling_load", "equipment"})
```

When any of these records is missing, SchemeService raises
`SourceCalculationMissingError`.  Today these records **do not exist**
outside the demo seeding path (`_ensure_demo_data()`), which uses
hard-coded demo values with `requires_review=False` (bypassing the review
contract).

Furthermore, SchemeService currently selects "latest by `calculator_name`
DESC" — it cannot verify that all four records come from the same
orchestration run, share the same coefficient context, or have matching
hashes.  This is a trust-boundary gap that must be closed by a formal
`SourceBindingRecord`.

The evaluation runner is therefore blocked by an explicit prerequisite gate
(`EvaluationPrerequisiteMissingError`, prerequisite_issue=22), waiting for
a formal production orchestration service that:

1. Accepts an immutable `ProjectVersionExecutionSnapshot`.
2. Resolves an approved `CoefficientContext` (materialized, hash-identified).
3. Executes zone → cooling_load → equipment → power → investment as a production pipeline.
4. Persists results as `CalculationRunRecord` rows with full provenance and hashes.
5. Materializes a `SourceBindingRecord` that SchemeService consumes explicitly.
6. Ensures SchemeService can verify all records via the binding, not via ad-hoc queries.

Without this service, SchemeService **cannot be called** from evaluation
and Task 11 Phase B cannot achieve `baseline expected_outcome=success`.

---

## 3. Existing-System Inventory

### 3.1 Production services and calculators

| Class / Function | File | Input | Output | Persistence | Notes |
|---|---|---|---|---|---|
| `DatabaseProjectService.create_project()` | `modules/projects/infrastructure/database.py` | name, location, product_category | ProjectRecord | Own session + commit | |
| `DatabaseProjectService.create_version()` | same | project_id, change_summary, created_by | ProjectVersionRecord | Own session + commit | |
| `DatabaseProjectService.save_inputs()` | same | project_id, version_number, inputs, actor | SaveInputsResult | Own session + commit | Version locked if status=approved/archived |
| `DatabaseProjectService.validate_inputs()` | `modules/projects/application/service.py` | inputs dict | {valid, missing_fields, tentative_fields} | None | |
| `DatabaseProjectService.record_calculation()` | `modules/projects/infrastructure/database.py` | project_id, version_number, CalculationResult, actor | dict | Own session + commit — **cannot be used for multi-record transaction** | |
| `DatabaseProjectService.list_calculations()` | same | project_id, version_number | list[dict] | Read-only | |
| `CoreCalculationService.orchestrate_core_calculation()` | `modules/calculations/application/service.py` | 5 sub-inputs | OrchestrationResult | None — in-memory | |
| `ColdRoomZonePlanner.plan()` | `modules/calculations/domain/zone_planning.py` | ColdRoomZonePlanInput | ZonePlanResult | None — pure domain | Demo coefficients |
| `calculate_installed_power()` | `modules/calculations/domain/power.py` | InstalledPowerCalcInput | CalculationResult | None — pure domain | |
| `InvestmentEstimator.estimate()` | `modules/calculations/domain/investment.py` | InvestmentEstimateInput | InvestmentEstimateResult | None — pure domain | Demo coefficients |
| `calculate_cooling_load()` | `modules/calculations/domain/cooling_load.py` | CoolingLoadCalcInput | CalculationResult | None — pure domain | |
| Equipment calculator | `modules/calculations/domain/equipment.py` | equipment input | CalculationResult | None — pure domain | |
| `SchemeService.generate_scheme_run()` | `modules/schemes/application/service.py` | project_id, version, profile_codes, weight_set_id, profile_parameters | dict | Uses SchemeRepository | **Needs source_binding_id** |

### 3.2 Key data contracts

**CalculationRunRecord** (`modules/projects/infrastructure/orm.py`, table `calculation_runs`):

| Column | Type | Current | Needed |
|---|---|---|---|
| id | VARCHAR(36) PK | ✓ | ✓ |
| project_id | VARCHAR(36) FK | ✓ | ✓ |
| project_version_id | VARCHAR(36) FK | ✓ | ✓ |
| calculator_name | VARCHAR(120) | ✓ | ✓ |
| calculator_version | VARCHAR(50) | ✓ | ✓ |
| input_snapshot | JSON | ✓ | ✓ |
| result_snapshot | JSON | ✓ | ✓ |
| formulas/coefficients/assumptions/warnings | JSON | ✓ | ✓ |
| requires_review | BOOLEAN | ✓ | ✓ |
| created_at | TIMESTAMPTZ | ✓ | ✓ |
| **input_hash** | VARCHAR(64) | **MISSING** | Required |
| **result_hash** | VARCHAR(64) | **MISSING** | Required |
| **orchestration_run_id** | VARCHAR(36) FK | **MISSING** | Required |
| **coefficient_context_id** | VARCHAR(36) FK | **MISSING** | Required |
| **source_binding_id** | VARCHAR(36) FK | **MISSING** | Required |
| **provenance** | JSON | **MISSING** | Required |
| **schema_version** | VARCHAR(20) | **MISSING** | Required (not default "1.0") |

**Existing `record_calculation()` creates its own session and commits immediately** — it CANNOT participate in a multi-record transaction. A transaction-aware repository layer is required (see §10).

**CalculationResult** (`modules/calculations/domain/models.py`):

```python
@dataclass(frozen=True)
class CalculationResult:
    success: bool
    calculator_name: str
    calculator_version: str
    input_snapshot: dict[str, Any]
    result: dict[str, Any]            # raw calculator output
    steps: list[CalculationStep]
    coefficient_references: list[CoefficientReference]
    assumptions: list[str]
    warnings: list[CalculationWarning]
    requires_review: bool             # from calculator only
    calculated_at: datetime
    correlation_id: str
```

**⚠️ `CalculationResult.result` is NOT the same as the `result_snapshot` that SchemeService consumes.** A typed `SourceSnapshotV1` adapter must bridge the two (see §9).

**Coefficient registry** (`modules/coefficients/domain/models.py`):

- `CoefficientDefinition`: code, name, category, value_type, scope_type
- `CoefficientRevision`: status (draft→unverified→reviewed→approved→withdrawn), value, source metadata
- `CoefficientValue`: immutable resolved value
- `CoefficientSet`: in-memory only — **no persistence, no immutable identity hash**
- Resolution priority: project_version → project → product+zone+process → product → global
- `requires_review` = True for any non-approved revision

### 3.3 Existing audit

`AuditEventRecord` — `actor`, `action`, `entity_type`, `entity_id`, `before_snapshot`, `after_snapshot`, `event_metadata`, `created_at`.

Existing actions: `run_project_calculations`, `save_core_calculation`, `save_design_inputs`.

**No orchestration-level audit events** currently exist.

---

## 4. Confirmed Capability Gaps

| # | Gap | Impact |
|---|---|---|
| G1 | No orchestration service | Blocked Task 11 Phase B |
| G2 | CalculationRunRecord lacks identity fields | No cross-record binding; SchemeService cannot verify source integrity |
| G3 | No approved coefficient catalog covering all required codes; no materialized coefficient-context identity | Baseline always triggers requires_review=true |
| G4 | Cooling-load/equipment/power calculators not wired to production pipeline | No CalculationRunRecord for these types |
| G5 | `record_calculation()` creates own session+commit — no shared transaction | Multi-record all-or-nothing impossible |
| G6 | SchemeService uses "latest by calculator_name DESC" — no source-binding verification | Tampered/stale/mixed-orchestration records silently accepted |
| G7 | No zone/power CalculationRunRecord creation path | SchemeService cannot find required calculation types |
| G8 | No materialized coefficient context identity | Cannot verify which coefficients were used; cannot detect coefficient changes |
| G9 | No orchestration-level audit; no durable failure audit | Cannot track pipeline lifecycle; failure evidence lost on rollback |
| G10 | No concurrent execution guard | Multiple workers could create conflicting records |
| G11 | No immutable ProjectVersion execution snapshot | Version could change between calculation stages |

---

## 5. Scope and Non-Goals

### In scope (this design)

- OrchestrationService with typed contracts
- Six-stage execution DAG: zone → cooling_load → equipment → power → investment
- SourceBindingRecord — explicit input to SchemeService
- Transaction-aware repositories (CalculationRunRepository, OrchestrationRunRepository, AuditRepository)
- ProjectVersionExecutionSnapshot (immutable capture)
- CoefficientContextRecord (materialized, hash-identified)
- Durable failure audit (two-phase persistence)
- Versioned SourceSnapshotV1 adapters with field mapping
- Hash/provenance contract
- Idempotency fingerprint and concurrency strategy
- Review propagation rules
- Error taxonomy
- Legacy migration strategy
- Test matrix
- Task 11 resumption criteria

### Out of scope

- Implementation (separate task/PR)
- Scheme generation formulas or scoring logic (unchanged)
- Evaluation/CLI changes
- API endpoint design
- Equipment model selection
- Energy consumption (kWh)
- Frontend changes

---

## 6. Architecture Decision

### 6.1 Module layout

```
backend/src/cold_storage/modules/orchestration/
├── application/
│   ├── __init__.py
│   └── service.py              # OrchestrationService
├── domain/
│   ├── __init__.py
│   ├── contracts.py             # OrchestrationInput, OrchestrationResult, StageResult
│   ├── dag.py                   # Execution DAG
│   ├── errors.py                # OrchestrationError hierarchy
│   ├── fingerprint.py           # OrchestrationFingerprint
│   ├── snapshots.py             # SourceSnapshotV1 typed adapters
│   └── hash_chain.py            # Hash and provenance builder
└── infrastructure/
    ├── __init__.py
    ├── repositories.py          # CalculationRunRepository, OrchestrationRunRepository
    ├── audit_repository.py      # AuditRepository (durable, independent session)
    └── orm.py                   # OrchestrationRunRecord, SourceBindingRecord, CoefficientContextRecord
```

### 6.2 Ownership

**OrchestrationService** is the sole transaction owner for calculation persistence.
It receives an externally-managed `Session` and:

1. Creates `ProjectVersionExecutionSnapshot` (immutable capture).
2. Resolves `CoefficientContext` (materialized, hash-identified).
3. Executes the DAG inside a single transaction.
4. Materializes `SourceBindingRecord`.
5. Commits — all-or-nothing for calculations, binding, and success audit.

**Repositories** (`CalculationRunRepository`, `OrchestrationRunRepository`) are
transaction-aware but do NOT create sessions or commit.  The orchestration
service calls `session.commit()` exactly once after all records are persisted.

**AuditRepository** uses an **independent session** for durable failure audit
(see §10.3).  Success audit events are committed in the same transaction as
calculations.

### 6.3 Explicitly NOT allowed

- ❌ Orchestration inside SchemeService, evaluation, API routes, or CLI.
- ❌ `DatabaseProjectService.record_calculation()` — it owns its own transaction.
- ❌ SchemeService querying "latest by calculator_name DESC" for production path.
- ❌ Implicit coefficient defaults or zero-value fallbacks.

---

## 7. Public Application Contract

### 7.1 OrchestrationInput

```python
@dataclass(frozen=True, slots=True)
class OrchestrationInput:
    execution_snapshot_id: str       # ProjectVersionExecutionSnapshot.id
    coefficient_context_id: str      # CoefficientContextRecord.id
    actor: str
    correlation_id: str
```

### 7.2 OrchestrationResult

```python
@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    orchestration_run_id: str
    execution_snapshot_id: str
    coefficient_context_id: str
    source_binding_id: str           # for SchemeService consumption
    status: str                      # COMPLETED | BLOCKED | FAILED
    requires_review: bool
    stages: dict[str, StageResult]   # keyed by calculator_name
    fingerprint: str                 # OrchestrationFingerprint hex
    started_at: datetime
    completed_at: datetime
```

### 7.3 StageResult

```python
@dataclass(frozen=True, slots=True)
class StageResult:
    calculator_name: str             # zone | cooling_load | equipment | power | investment
    calculation_run_id: str
    status: str                      # passed | failed | blocked | skipped
    requires_review: bool            # from calculator only
    input_hash: str
    result_hash: str
    calculator_version: str
    snapshot_schema_version: str     # "1.0"
```

### 7.4 SourceBindingRecord

The core trust-boundary artifact.  Materialized by OrchestrationService and
consumed explicitly by SchemeService via `source_binding_id`.

```python
@dataclass(frozen=True, slots=True)
class SourceBindingRecord:
    id: str                          # UUID
    project_id: str
    project_version_id: str
    execution_snapshot_id: str
    orchestration_run_id: str
    coefficient_context_id: str
    orchestration_fingerprint: str   # SHA-256 hex

    # Per-type calculation record IDs
    zone_calculation_id: str
    cooling_load_calculation_id: str
    equipment_calculation_id: str
    power_calculation_id: str
    investment_calculation_id: str

    # Per-type result_snapshot hashes
    per_calculation_result_hashes: dict[str, str]

    combined_source_hash: str        # SHA-256 over all five snapshots (sorted)
    schema_version: str              # "1.0"
    created_at: datetime
```

### 7.5 SchemeService contract — FROZEN CHANGE

**SchemeService source-binding trust-boundary changes ARE PART OF Issue #22 implementation.**
Scheme generation formulas and scoring remain out of scope.

New signature:

```python
def generate_scheme_run(
    self,
    *,
    project_id: str,
    version: int,
    source_binding_id: str,          # NEW — explicit binding
    profile_codes: list[str],
    weight_set_id: str,
    profile_parameters: dict[str, dict[str, Any]],
) -> dict[str, Any]:
```

**Flow:**

1. Load `SourceBindingRecord` by `source_binding_id`.
2. Verify `project_id` and `version` match.
3. Load exactly the five calculation records by their IDs from the binding
   (NOT "latest by calculator_name DESC").
4. Verify every record's `orchestration_run_id` matches the binding.
5. Verify every record's `project_version_id` matches.
6. Verify every record's `result_hash` recomputes to the stored value.
7. Verify `combined_source_hash` recomputes to the stored value.
8. Verify all records have `schema_version` supported.
9. Verify `coefficient_context_id` matches.
10. Reject any legacy/unbound/unversioned/hash-missing records.
11. Proceed with scheme generation (unchanged logic).

**SchemeService MUST NOT:**
- Query by `calculator_name` ORDER BY `created_at DESC` for the production path.
- Accept records from different orchestration runs.
- Accept records without `source_binding_id`.
- Accept unversioned or hash-missing records.

---

## 8. Execution DAG

### 8.1 Fixed dependency order (SIX stages)

```
ProjectVersionExecutionSnapshot
      │
      ▼
  ┌─────────┐
  │  zone   │  ColdRoomZonePlanner.plan()
  └────┬────┘
       │
       ▼
  ┌──────────────┐
  │ cooling_load  │  calculate_cooling_load()
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐
  │  equipment    │  Equipment capability
  └──────┬───────┘  → compressor_operating_kw_r, compressor_installed_kw_r,
         │           condenser_heat_rejection_kw
         │           → compressor_input_power_kw_e (via COP — feeds power stage)
         ▼
  ┌──────────────┐
  │    power     │  Installed power (INDEPENDENT stage)
  └──────┬───────┘  → total_installed_power_kw_e
         │           Aggregates ALL facility electrical loads:
         │           - refrigeration compressors
         │           - evaporator fans
         │           - condenser fans
         │           - defrost
         │           - lighting
         │           - processing/conveying equipment
         │           - auxiliary systems
         │           + ProjectVersion-declared loads
         ├──────────────────┐
         ▼                  │
  ┌──────────────┐          │
  │  investment   │ ←───────┘
  └──────────────┘  total_power_kw = power.total_installed_power_kw_e
         │           + zone areas + position_count + coefficient context
         ▼
  ┌──────────────────────┐
  │ SourceBindingRecord   │
  └──────────┬───────────┘
             ▼
  ┌──────────────┐
  │ SchemeService │  (explicit source_binding_id)
  └──────────────┘
```

### 8.2 Per-node definition

| Stage | Upstream | Calculator | Key output |
|---|---|---|---|
| zone | ExecutionSnapshot only | ColdRoomZonePlanner.plan() | zones, areas, positions |
| cooling_load | zone result + coefficient context | calculate_cooling_load() | design_cooling_load_kw_r per zone |
| equipment | cooling_load result + coefficient context | equipment calculator | compressor capacities kW(r), compressor_input_power_kw_e |
| power | equipment.compressor_input_power_kw_e + ProjectVersion loads | InstalledPowerCalculator | **total_installed_power_kw_e** |
| investment | zone areas + power.total_installed_power_kw_e + coefficient context | InvestmentEstimator.estimate() | total_investment_cny |

### 8.3 Key constraints

- **equipment** computes refrigeration capability (kW(r)) and derives `compressor_input_power_kw_e` via COP. This is ONE input to power — not the whole installed power.
- **power** aggregates ALL facility electrical loads. `compressor_input_power_kw_e` ≠ `total_installed_power_kw_e`.
- **investment** MUST use `power.total_installed_power_kw_e`, not `equipment.compressor_input_power_kw_e`.
- **investment** BLOCKED if power stage is missing or failed.
- Task 11 requires **8 stages** (including independent `power`), not 7.

---

## 9. Versioned SourceSnapshot Adapters

SchemeService MUST NOT directly parse raw `CalculationResult.result` from
different calculators.  A typed adapter layer translates calculator-specific
output into versioned `SourceSnapshotV1` structures.

### 9.1 ZoneSourceSnapshotV1

| Snapshot field | Source (calculator → field) | Type |
|---|---|---|
| `schema_version` | Fixed `"1.0"` | str |
| `calculation_type` | Fixed `"zone"` | str |
| `calculator_name` | `result.calculator_name` | str |
| `calculator_version` | `result.calculator_version` | str |
| `source_input_hash` | SHA-256 of canonicalized input | str |
| `result_hash` | SHA-256 of canonicalized snapshot (this struct) | str |
| `requires_review` | `result.requires_review` | bool |
| `warning_codes` | `result.warnings[*].code` | list[str] |
| `payload.total_daily_throughput_kg_day` | `result.zones` sum of throughput | Decimal |
| `payload.zones[]` | `result.zones[*]` | list |
| `payload.zones[].zone_code` | `zone.zone_code` | str |
| `payload.zones[].zone_name` | `zone.zone_name` | str |
| `payload.zones[].temperature_level` | `zone.temperature_level` | str |
| `payload.zones[].area_m2` | `zone.area_m2` | Decimal |
| `payload.zones[].position_count` | `zone.position_count` | int |
| `payload.zones[].storage_capacity_kg` | `zone.storage_capacity_kg` | Decimal |
| `payload.zones[].process_compatibility` | `zone.process_compatibility` | str |
| `payload.zones[].hygiene_zone` | `zone.hygiene_zone` | str |

### 9.2 CoolingLoadSourceSnapshotV1

| Snapshot field | Source | Type |
|---|---|---|
| `schema_version` | Fixed `"1.0"` | str |
| `calculation_type` | Fixed `"cooling_load"` | str |
| `calculator_name` | Fixed `"cooling_load"` | str |
| `calculator_version` | `result.calculator_version` | str |
| `source_input_hash` | SHA-256 of canonicalized input | str |
| `result_hash` | SHA-256 of this snapshot | str |
| `requires_review` | `result.requires_review` | bool |
| `warning_codes` | `result.warnings[*].code` | list[str] |
| `payload.design_cooling_load_kw_r` | Sum of per-zone totals after diversity + margin | Decimal |
| `payload.sensible_load_kw_r` | Sum of per-zone sensible components | Decimal |
| `payload.latent_load_kw_r` | Sum of per-zone latent components | Decimal |
| `payload.infiltration_load_kw_r` | Sum of per-zone infiltration components | Decimal |

Aggregation: sum per-zone loads from `result` per-zone output, apply diversity factor per temperature level, then design margin.

### 9.3 EquipmentSourceSnapshotV1

| Snapshot field | Source | Type |
|---|---|---|
| `schema_version` | Fixed `"1.0"` | str |
| `calculation_type` | Fixed `"equipment"` | str |
| `calculator_name` | Fixed `"equipment"` | str |
| `calculator_version` | `result.calculator_version` | str |
| `source_input_hash` | SHA-256 of canonicalized input | str |
| `result_hash` | SHA-256 of this snapshot | str |
| `requires_review` | `result.requires_review` | bool |
| `warning_codes` | `result.warnings[*].code` | list[str] |
| `payload.compressor_operating_capacity_kw_r` | total across all temperature systems | Decimal |
| `payload.compressor_installed_capacity_kw_r` | operating × redundancy | Decimal |
| `payload.condenser_heat_rejection_kw` | total across all systems | Decimal |
| `payload.installed_power_kw_e` | compressor input power (from COP derivation) | Decimal |

Note: `payload.installed_power_kw_e` in EquipmentSourceSnapshot is the
**compressor input power only** — NOT the full facility installed power.
Investment MUST NOT use this value as `total_power_kw`.

### 9.4 PowerSourceSnapshotV1

| Snapshot field | Source | Type |
|---|---|---|
| `schema_version` | Fixed `"1.0"` | str |
| `calculation_type` | Fixed `"power"` | str |
| `calculator_name` | Fixed `"installed_power"` | str |
| `calculator_version` | `result.calculator_version` | str |
| `source_input_hash` | SHA-256 of canonicalized input | str |
| `result_hash` | SHA-256 of this snapshot | str |
| `requires_review` | `result.requires_review` | bool |
| `warning_codes` | `result.warnings[*].code` | list[str] |
| `payload.total_installed_power_kw_e` | Sum of all load categories | Decimal |
| `payload.estimated_peak_demand_kw_e` | After demand factors | Decimal |
| `payload.load_breakdown.refrigeration_compressors_kw_e` | from equipment stage | Decimal |
| `payload.load_breakdown.evaporator_fans_kw_e` | from equipment stage | Decimal |
| `payload.load_breakdown.condenser_fans_kw_e` | from equipment stage | Decimal |
| `payload.load_breakdown.defrost_kw_e` | from equipment stage | Decimal |
| `payload.load_breakdown.lighting_kw_e` | from ProjectVersion inputs | Decimal |
| `payload.load_breakdown.processing_equipment_kw_e` | from ProjectVersion inputs | Decimal |
| `payload.load_breakdown.auxiliary_kw_e` | from ProjectVersion inputs | Decimal |
| `payload.source_equipment_calculation_id` | equipment CalculationRunRecord.id | str |

### 9.5 InvestmentSourceSnapshotV1

| Snapshot field | Source | Type |
|---|---|---|
| `schema_version` | Fixed `"1.0"` | str |
| `calculation_type` | Fixed `"investment"` | str |
| `calculator_name` | `result.calculator_name` | str |
| `calculator_version` | `result.calculator_version` | str |
| `source_input_hash` | SHA-256 of canonicalized input | str |
| `result_hash` | SHA-256 of this snapshot | str |
| `requires_review` | `result.requires_review` | bool |
| `warning_codes` | `result.warnings[*].code` | list[str] |
| `payload.total_investment_cny` | from estimator | Decimal |
| `payload.zone_investments` | from estimator | dict[str, Decimal] |
| `payload.source_power_calculation_id` | power CalculationRunRecord.id | str |
| `payload.source_zone_calculation_id` | zone CalculationRunRecord.id | str |

### 9.6 Adapter rules

- All conversions are **typed**, **deterministic**, **unit-explicit**, and **fail-closed**.
- No zero-value fallback for missing fields.
- No message-text parsing to extract values.
- Adapter rejects unknown calculator versions.
- `requires_review` is carried forward from the calculator ONLY — no additional rules.

---

## 10. Persistence and Transactions

### 10.1 Transaction-aware repositories

`DatabaseProjectService.record_calculation()` creates its own session and
commits immediately — it CANNOT participate in a multi-record orchestration
transaction.  New repositories are required:

```python
class CalculationRunRepository:
    """Adds CalculationRunRecord within an externally-managed session.

    Does NOT create sessions.  Does NOT commit.
    """

    def add(self, session: Session, record: CalculationRunRecord) -> None: ...


class OrchestrationRunRepository:
    """Manages OrchestrationRunRecord lifecycle.

    Does NOT create sessions.  Does NOT commit.
    """

    def add(self, session: Session, record: OrchestrationRunRecord) -> None: ...
    def mark_completed(self, session: Session, run_id: str, ...) -> None: ...
    def mark_failed(self, session: Session, run_id: str, ...) -> None: ...
    def find_by_fingerprint(self, session: Session, fingerprint: str) -> OrchestrationRunRecord | None: ...


class SourceBindingRepository:
    def add(self, session: Session, record: SourceBindingRecord) -> None: ...
    def get(self, session: Session, binding_id: str) -> SourceBindingRecord: ...


class AuditRepository:
    """Durable audit — uses INDEPENDENT sessions for failure audit (see §10.3)."""

    def add(self, session: Session, event: AuditEventRecord) -> None: ...
```

### 10.2 Single-transaction calculation persistence

```
OrchestrationService.run(input, session_from_caller):

  Transaction A — execution lease:
    1. fingerprint = compute_fingerprint(input)
    2. existing = OrchestrationRunRepository.find_by_fingerprint(session, fingerprint)
    3. If existing and COMPLETED → return existing result (idempotent)
    4. If existing and RUNNING → return IN_PROGRESS or conflict
    5. Create OrchestrationRunRecord(status=RUNNING, fingerprint=fingerprint)
    6. Create AuditEvent(action=orchestration_started)
    7. session.commit()  ← execution lease committed

  Transaction B — calculations and binding:
    8. Capture ExecutionSnapshot and CoefficientContext (read-only)
    9. For each stage in DAG order:
       a. Build input from upstream results
       b. Call calculator
       c. Build SourceSnapshotV1 via typed adapter
       d. Compute input_hash, result_hash
       e. Create CalculationRunRecord (hash, orchestration_run_id, coefficient_context_id, source_binding_id, provenance)
       f. CalculationRunRepository.add(session, record)
       g. Create AuditEvent(action=calculation_completed)
       h. If failed/blocked → mark stage, continue to determine overall status
   10. Build SourceBindingRecord with all five calculation IDs and hashes
   11. SourceBindingRepository.add(session, binding)
   12. Compute combined_source_hash
   13. Update OrchestrationRunRecord status → COMPLETED | BLOCKED
   14. Create AuditEvent(action=orchestration_completed)
   15. session.commit()  ← all-or-nothing
   16. Return OrchestrationResult

  On unhandled exception in Transaction B:
    session.rollback()
    → fall through to Transaction C
```

### 10.3 Durable failure audit

If the calculation transaction (B) rolls back, the failure audit must survive.
Use an **independent session** for terminal-status writes:

```
  Transaction C — durable failure terminal (independent session):
    failure_session = session_factory()
    try:
      1. Load OrchestrationRunRecord by run_id (needs fresh session after rollback)
      2. Mark status = FAILED (or BLOCKED)
      3. Create AuditEvent(action=orchestration_failed, error_class=..., ...)
      4. failure_session.commit()
    finally:
      failure_session.close()
```

**Rationale:** If calculation_tx commits but the audit write fails (unlikely),
the orchestration is still COMPLETED — the audit event is best-effort.
If calculation_tx rolls back, the failure audit is written in an independent
transaction and survives.

### 10.4 Crash recovery

- **RUNNING lease stale:** If `OrchestrationRunRecord.status=RUNNING` and
  `started_at` is older than a configurable timeout (e.g., 30 min), a new
  orchestration can mark it as ABANDONED and proceed.
- **Terminal reconciliation:** `OrchestrationRunRepository` provides
  `reconcile_stale_runs()` for operations tooling.

### 10.5 New ORM tables

**OrchestrationRunRecord:**

| Column | Type | Notes |
|---|---|---|
| id | VARCHAR(36) PK | |
| project_id | VARCHAR(36) FK | |
| project_version_id | VARCHAR(36) FK | |
| execution_snapshot_id | VARCHAR(36) FK | |
| coefficient_context_id | VARCHAR(36) FK | |
| fingerprint | VARCHAR(64) UNIQUE | SHA-256 hex |
| status | VARCHAR(20) | RUNNING | COMPLETED | BLOCKED | FAILED | ABANDONED |
| requires_review | BOOLEAN | |
| source_binding_id | VARCHAR(36) FK NULLABLE | Set when binding materialized |
| started_at | TIMESTAMPTZ | |
| completed_at | TIMESTAMPTZ NULLABLE | |
| actor | VARCHAR(100) | |
| correlation_id | VARCHAR(36) | |

**SourceBindingRecord:**

| Column | Type |
|---|---|
| id | VARCHAR(36) PK |
| project_id | VARCHAR(36) FK |
| project_version_id | VARCHAR(36) FK |
| execution_snapshot_id | VARCHAR(36) FK |
| orchestration_run_id | VARCHAR(36) FK |
| coefficient_context_id | VARCHAR(36) FK |
| orchestration_fingerprint | VARCHAR(64) |
| zone_calculation_id | VARCHAR(36) FK |
| cooling_load_calculation_id | VARCHAR(36) FK |
| equipment_calculation_id | VARCHAR(36) FK |
| power_calculation_id | VARCHAR(36) FK |
| investment_calculation_id | VARCHAR(36) FK |
| per_calculation_result_hashes | JSON |
| combined_source_hash | VARCHAR(64) |
| schema_version | VARCHAR(20) DEFAULT '1.0' |
| created_at | TIMESTAMPTZ |

```sql
CREATE UNIQUE INDEX uq_source_binding_fingerprint
    ON source_bindings (orchestration_fingerprint);
```

---

## 11. Idempotency Fingerprint and Concurrency

### 11.1 Orchestration fingerprint

```
fingerprint = SHA-256(
    project_version_execution_snapshot_hash   # 64 hex
    + coefficient_context_hash                # 64 hex
    + orchestration_definition_version        # e.g. "1.0.0"
    + calculator_version_vector               # sorted canonical: "cooling_load=1.0.0,equipment=1.0.0,..."
    + input_mapping_schema_version            # e.g. "1.0"
    + source_snapshot_schema_version          # e.g. "1.0"
)
```

### 11.2 Idempotency rules

| Existing run status | Same fingerprint | Action |
|---|---|---|
| COMPLETED | ✓ | Return existing `OrchestrationResult` (idempotent) |
| RUNNING | ✓ | Return IN_PROGRESS or conflict (do not start second) |
| FAILED | ✓ | Create new attempt (fingerprint unchanged; new `orchestration_run_id`) unless terminal policy forbids retry |
| BLOCKED | ✓ | Create new attempt if retry policy allows |
| (any) | ✗ (different) | Create new orchestration run |

Calculator version change → fingerprint changes → always new run.
Coefficient revision change → coefficient_context_hash changes → fingerprint changes → always new run.
Input change → execution_snapshot_hash changes → fingerprint changes → always new run.

### 11.3 Concurrency strategy

**PostgreSQL:**
- `INSERT INTO orchestration_runs ... ON CONFLICT (fingerprint) DO NOTHING`
- Unique constraint on `fingerprint` is the correctness mechanism.
- Optional: `pg_advisory_xact_lock(hashtext(fingerprint))` as optimization.
- The constraint is sufficient — advisory lock is NOT required for correctness.

**SQLite:**
- `INSERT OR IGNORE` or catch `IntegrityError` on UNIQUE constraint violation.
- SQLite serializes writes by default (database-level lock).
- Multi-connection scenarios: use `busy_timeout` + retry on `SQLITE_BUSY`.
- Unique constraint on `fingerprint` still applies — the first writer to
  commit wins.
- Stale RUNNING detection uses `started_at` timeout (not lock-based).

**Winner determination:** The first transaction to COMMIT with a unique
fingerprint wins.  Losers read the committed run and return its status.
No application-level lease negotiation needed — the database constraint
is the single source of truth.

---

## 12. ProjectVersion Execution Snapshot

### 12.1 Design

```python
@dataclass(frozen=True)
class ProjectVersionExecutionSnapshot:
    """Immutable capture of a ProjectVersion at execution time.

    Once created, never updated.  Orchestration reads ONLY from this snapshot,
    never from the mutable ProjectVersion record.
    """

    id: str
    project_id: str
    project_version_id: str
    version_number: int
    version_status: str       # copied from ProjectVersionRecord.status at capture time
    input_snapshot: dict      # copied from ProjectVersionRecord.input_snapshot
    input_snapshot_hash: str  # SHA-256 of canonicalized input_snapshot
    schema_version: str       # "1.0"
    captured_at: datetime
```

### 12.2 Lifecycle

1. Created by `OrchestrationService` at the start of each run.
2. Reads `ProjectVersionRecord` fields once — never re-reads.
3. Input hash is computed and frozen in the snapshot.
4. If `version_status` is `archived`: orchestration BLOCKED (cannot execute against archived versions).
5. Allowed execution states: `generated`, `under_review`, `reviewed`, `approved`.
6. For Task 11 fixture: fixture must provide an `approved` ProjectVersion (or the
   orchestration must accept `generated` with caller-provided override — TBD in implementation).

### 12.3 Validation before execution

- `input_snapshot_hash` matches SHA-256 of captured `input_snapshot`.
- `schema_version` is supported.
- `project_version_id` matches the requested version.
- Version is not archived.
- `execution_snapshot_id` has not changed since capture.

---

## 13. Coefficient Context

### 13.1 Problem

The current `CoefficientSet` is an in-memory object with no persistence,
no immutable identity hash, and no versioned binding to specific revisions.

### 13.2 Design: CoefficientContextRecord

```python
@dataclass(frozen=True)
class CoefficientContextRecord:
    """Materialized, immutable snapshot of resolved coefficients.

    Created once before orchestration execution.  Identified by content_hash.
    Same inputs always produce the same content_hash → idempotent resolution.
    """

    id: str                          # UUID
    schema_version: str              # "1.0"
    project_id: str
    project_version_id: str
    product_type: str                # from ProjectVersion
    location_region: str | None      # from ProjectVersion
    scope_context: dict              # zone/process scope metadata
    content_hash: str                # SHA-256(canonical bindings + resolution context + policy version)

    # Per-coefficient revision bindings
    revision_bindings: dict[str, CoefficientRevisionBinding]
    # {
    #   "cooling.wall_u_value": {
    #     "definition_id": "...",
    #     "revision_id": "...",
    #     "revision_number": 2,
    #     "status": "approved",
    #     "value": "0.35",
    #     "unit": "W/(m²·K)"
    #   },
    #   ...
    # }

    resolution_policy_version: str   # "1.0"
    captured_at: datetime
    created_by: str                  # actor
```

### 13.3 Identity rules

- `content_hash` = SHA-256(canonical JSON of revision_bindings + scope_context + resolution_policy_version).
- `captured_at` does NOT enter the hash (two contexts with identical bindings but
  different capture times have the same content_hash — they ARE the same context).
- **Immutable after creation.**
- Withdrawn revisions do not retroactively change existing contexts.
- New orchestration runs MUST re-resolve coefficients — never reuse stale contexts
  unless the caller explicitly requests a specific `coefficient_context_id`.

### 13.4 Approved coefficient catalog

- **Owner:** `modules/coefficients` — delivered as a sub-task of Issue #22 implementation.
- **Approval:** Uses the existing `CoefficientRevision` state machine:
  draft → reviewed → approved.
- **Seed migration:** Provides approved revisions for all required coefficients.
  The seed migration must NOT bypass approval semantics — each revision must
  transition through the state machine.
- **Missing required code:** If the resolver cannot find an approved revision
  for a required coefficient code, the orchestration is BLOCKED
  (`CoefficientNotApprovedError(field=<code>)`).
- **Demo/unverified fallback:** NOT allowed for orchestration path.  Demo coefficients
  may still be used for manual/demo scenarios, but those always produce
  `requires_review=true`.

The exact list of required coefficient codes is determined by auditing each
calculator's actual `CoefficientSet` field access — not by manual estimation.
The coefficient inventory in `docs/audit/coefficient-inventory.md` provides
the baseline for this audit.

---

## 14. Hash and Provenance

### 14.1 Hash algorithm

```
SHA-256 of canonical_json(obj)
```
Where `canonical_json()` = sorted keys, `separators=(",", ":")`, `ensure_ascii=False`.

### 14.2 Hash chain

| Hash | Content | Excludes |
|---|---|---|
| `input_snapshot_hash` | canonical JSON of calculator input dict | correlation_id, calculated_at |
| `result_hash` | canonical JSON of `SourceSnapshotV1` struct | None — all fields included |
| `per_calculation_result_hashes[name]` | canonical JSON of `SourceSnapshotV1.payload` only | schema envelope |
| `combined_source_hash` | canonical JSON of `{calc_type: SourceSnapshotV1.payload}` sorted by calc_type | |
| `coefficient_context_hash` | canonical JSON of `revision_bindings` + `scope_context` + `resolution_policy_version` | `captured_at`, `id` |
| `orchestration_fingerprint` | concatenation: `snapshot_hash + coefficient_context_hash + definition_version + calculator_version_vector + input_mapping_schema_version + source_snapshot_schema_version` | |

### 14.3 Provenance

Each `CalculationRunRecord.provenance` stores:
```json
{
  "orchestration_run_id": "...",
  "source_binding_id": "...",
  "coefficient_context_id": "...",
  "execution_snapshot_id": "...",
  "upstream_calculation_ids": {
    "zone": "...",
    "cooling_load": "..."
  },
  "orchestration_fingerprint": "..."
}
```

---

## 15. Review and Blocker Propagation

### 15.1 Stage-level

`stage.requires_review = calculator_result.requires_review`

**Only** the calculator's own `requires_review` flag is propagated.
Warnings are recorded but do NOT automatically promote to `requires_review`
unless the calculator itself has a structured `warning_code` that the
calculator contract declares as review-promoting.

The orchestration service does NOT parse warning messages or apply its own
business rules to determine review status.

### 15.2 Orchestration-level aggregation

```
1. Any stage status = failed?
   → orchestration.status = FAILED
2. Else any stage status = blocked?
   → orchestration.status = BLOCKED
3. Else any stage.requires_review = true?
   → orchestration.status = COMPLETED, requires_review = true
4. Else:
   → orchestration.status = COMPLETED, requires_review = false
```

---

## 16. Error Taxonomy

All errors inherit from `OrchestrationError(code, message, field)`.

| Exception | code | field | retryable |
|---|---|---|---|
| `ExecutionSnapshotNotFoundError` | EXEC_SNAPSHOT_NOT_FOUND | execution_snapshot_id | No |
| `ProjectVersionArchivedError` | PROJ_VERSION_ARCHIVED | project_version_id | No |
| `CoefficientContextNotFoundError` | COEFF_CTX_NOT_FOUND | coefficient_context_id | No |
| `CoefficientNotApprovedError` | COEFF_NOT_APPROVED | coefficient_code | No |
| `AmbiguousCoefficientError` | COEFF_AMBIGUOUS | coefficient_code | No |
| `CalculationInputMappingError` | CALC_INPUT_MAPPING_FAILED | calculator_name | No |
| `CalculationExecutionError` | CALC_EXECUTION_FAILED | calculator_name | Maybe |
| `SnapshotAdapterError` | SNAP_ADAPTER_FAILED | calculator_name | No |
| `SourceBindingNotFoundError` | SOURCE_BINDING_NOT_FOUND | source_binding_id | No |
| `SourceBindingVerificationError` | SOURCE_BINDING_VERIFY_FAILED | field (e.g., result_hash) | No |
| `LegacyRecordRejectedError` | LEGACY_RECORD_REJECTED | calculator_name | No |
| `DuplicateOrchestrationError` | ORCH_DUPLICATE_RUNNING | fingerprint | Yes |
| `OrchestrationExecutionError` | ORCH_EXECUTION_FAILED | — | No |
| `AuditPersistenceError` | AUDIT_PERSIST_FAILED | — | Yes |

---

## 17. API/CLI Boundary

### 17.1 Deferred — no API/CLI in Issue #22 scope

The orchestration service is callable from:
1. Test fixtures (immediate need).
2. Evaluation runner (Task 11 Phase B resumption).
3. Future API routes (separate task).

API/CLI design is out of scope for Issue #22.

---

## 18. Migration Assessment

### 18.1 Required schema changes

| Change | Table | Risk |
|---|---|---|
| CREATE `project_version_execution_snapshots` | New | Low |
| CREATE `coefficient_contexts` | New | Low |
| CREATE `orchestration_runs` + UNIQUE(fingerprint) | New | Low |
| CREATE `source_bindings` + UNIQUE(orchestration_fingerprint) | New | Low |
| ALTER `calculation_runs` ADD `input_hash` VARCHAR(64) NULLABLE | Existing | Low — nullable |
| ALTER `calculation_runs` ADD `result_hash` VARCHAR(64) NULLABLE | Existing | Low — nullable |
| ALTER `calculation_runs` ADD `orchestration_run_id` VARCHAR(36) NULLABLE FK | Existing | Low — nullable |
| ALTER `calculation_runs` ADD `coefficient_context_id` VARCHAR(36) NULLABLE FK | Existing | Low — nullable |
| ALTER `calculation_runs` ADD `source_binding_id` VARCHAR(36) NULLABLE FK | Existing | Low — nullable |
| ALTER `calculation_runs` ADD `provenance` JSON NULLABLE | Existing | Low — nullable |
| ALTER `calculation_runs` ADD `schema_version` VARCHAR(20) NULLABLE | Existing | Low — nullable |
| ADD CHECK constraint: new rows require non-null identity fields | `calculation_runs` | Medium |

### 18.2 Legacy vs new records

**Legacy rows** (existing before migration):
- `schema_version` = NULL (interpreted as "legacy-unversioned" by application code, NOT a magic string)
- `orchestration_run_id` = NULL
- `source_binding_id` = NULL
- `input_hash` = NULL
- `result_hash` = NULL
- `coefficient_context_id` = NULL
- `provenance` = NULL

**New orchestrated rows:**
- All identity fields required NON-NULL (enforced by application, optionally
  by CHECK constraint for new rows).
- `schema_version` set to actual version string.

### 18.3 Compatibility rules

| Consumer | Legacy rows | New orchestrated rows |
|---|---|---|
| `DatabaseProjectService.list_calculations()` | ✓ (unchanged) | ✓ |
| `SchemeService` (legacy path — demo only) | ✓ | May coexist |
| `SchemeService` (production path — `source_binding_id`) | **REJECTED** | ✓ |
| `SourceBindingRepository.get()` | N/A — binding only references new rows | ✓ |

### 18.4 Downgrade risk

- New columns are nullable — downgrade removes columns without data loss
  in legacy rows.
- `source_bindings` and `orchestration_runs` tables are new — downgrade
  drops them. Existing `SchemeRun` records that reference them via
  `source_binding_id` will have dangling references — acceptable for
  migration rollback.
- No existing data is modified by the migration.

### 18.5 PostgreSQL/SQLite differences

| Feature | SQLite | PostgreSQL |
|---|---|---|
| UNIQUE constraint | ✓ | ✓ |
| FK enforcement | ✓ (PRAGMA foreign_keys=ON) | ✓ |
| Partial unique index | ✓ | ✓ |
| CHECK constraint | ✓ (limited) | ✓ (full) |
| `INSERT ... ON CONFLICT DO NOTHING` | ✓ | ✓ |

---

## 19. Approved Scheme Weight-Set Path

**Decision:** Task 11 baseline must NOT use `demo-weight-set-001`.

Design an approved weight-set path:
- `status = "approved"`
- Immutable revision
- Content hash
- Approval metadata
- Generator compatibility version
- `requires_review = false`

This belongs to the `schemes` module (weight set management) but is a
prerequisite for Task 11 resumption.  Delivery: sub-task of Issue #22
implementation or separate coefficient/weight-set curation task.

---

## 20. Room Geometry and Design Inputs

**Decision:** These belong to the **project design input schema**, not the
coefficient registry.

Frozen fields:

| Field | Unit | Source |
|---|---|---|
| `room_height_m` | m | ProjectVersion.input_snapshot |
| `wall_area_m2` | m² | ProjectVersion.input_snapshot (or derived from geometry) |
| `roof_area_m2` | m² | ProjectVersion.input_snapshot |
| `floor_area_m2` | m² | ProjectVersion.input_snapshot |
| `outdoor_design_temperature_c` | °C | ProjectVersion.input_snapshot (location-dependent) |
| `room_design_temperature_c` | °C | ProjectVersion.input_snapshot (per zone) |
| `product_entry_temperature_c` | °C | ProjectVersion.input_snapshot |
| `product_target_temperature_c` | °C | ProjectVersion.input_snapshot |
| `cooling_duration_h` | h | ProjectVersion.input_snapshot |

The coefficient registry provides engineering coefficients (U-values,
diversity factors, design margins) — NOT site-specific geometry or
operating conditions.

---

## 21. Test Matrix

### 21.1 Unit tests

| Test | Verifies |
|---|---|
| DAG topological sort | Stages execute in correct dependency order |
| SourceSnapshotV1 adapters | Calculator output → typed snapshot with exact field mapping |
| Snapshot adapter rejects unknown version | Fail-closed for unsupported schema_version |
| Fingerprint computation | Same inputs → same fingerprint; different calculator version → different fingerprint |
| Fingerprint collision | Different inputs produce different fingerprints |
| Review propagation | requires_review from calculator only; no warning-based promotion |
| SourceBinding serialization | Round-trip JSON encode/decode preserves all fields |

### 21.2 Application orchestration tests

| Test | Verifies |
|---|---|
| Happy path — 5 stages | All records persisted; SourceBinding materialized; scheme_service reads via source_binding_id |
| Approved coefficient baseline | requires_review=false for all stages |
| Demo/unverified coefficient → review_required | Calculator.requires_review propagated |
| Approved coefficient catalog incomplete → blocked | Missing required code raises CoefficientNotApprovedError |
| Power stage missing → investment blocked | investment skipped; total_power_kw not defaulted to 0 |
| Compressor input power ≠ total installed power | Investment uses power.total_installed_power_kw_e, not equipment value |
| Missing input fields → blocked | No zero-fallback |
| Partial failure rollback | No partial CalculationRunRecord or SourceBinding persisted |
| Idempotent retry — same fingerprint | Second run returns existing OrchestrationResult |
| Changed calculator version → new run | Different fingerprint → new orchestration |

### 21.3 SchemeService source-binding tests

| Test | Verifies |
|---|---|
| Valid source_binding_id → success | SchemeService reads all 5 records via binding |
| Missing source_binding_id → error | SourceBindingNotFoundError |
| binding.project_id mismatch → rejected | Verification error |
| binding.orchestration_run_id mismatch across records → rejected | Mixed orchestration records rejected |
| Legacy row (null source_binding_id) → rejected | LegacyRecordRejectedError |
| Tampered result_hash → rejected | SourceBindingVerificationError(field=result_hash) |
| Tampered coefficient_context_id → rejected | Verification error |
| Unsupported schema_version → rejected | Verification error |
| Approved weight set + approved coefficients → requires_review=false | Full baseline success |

### 21.4 Concurrency tests

| Test | Backend | Verifies |
|---|---|---|
| Same fingerprint, concurrent workers | SQLite | Only one completes; other returns existing/idempotent |
| Same fingerprint, concurrent workers | PostgreSQL | UNIQUE constraint ensures single winner |
| Stale RUNNING lease | Both | Timeout-based detection; new run allowed |
| Changed coefficient revision | Both | New fingerprint → concurrent run allowed |

### 21.5 Durable failure audit tests

| Test | Verifies |
|---|---|
| Calculation exception → rollback + failure audit persisted | Audit survives in independent session |
| All stages succeed → success audit in same transaction | Audit committed with calculations |
| Failure audit write fails → orchestration still marked FAILED | Audit is best-effort on success path |

---

## 22. Implementation Work Breakdown

All sub-tasks are design-level only — no implementation in this PR.

### A. Immutable execution snapshot and orchestration contracts
- Scope: `ProjectVersionExecutionSnapshot`, `OrchestrationInput`, `OrchestrationResult`, `StageResult`, `OrchestrationFingerprint`
- Dependencies: None (pure domain)
- Files: `modules/orchestration/domain/contracts.py`, `fingerprint.py`
- Schema: `project_version_execution_snapshots` table
- Acceptance: All types immutable, fully documented

### B. Materialized approved coefficient context
- Scope: `CoefficientContextRecord`, resolution, seed approved revisions
- Dependencies: A, coefficient registry (Task 3)
- Files: `modules/orchestration/domain/coefficient_context.py`, `modules/coefficients/` (seed data)
- Schema: `coefficient_contexts` table
- Acceptance: All required codes resolvable as approved; content_hash deterministic

### C. Approved scheme weight-set path
- Scope: Approved weight set with immutable revision, content hash
- Dependencies: scheme module
- Files: `modules/schemes/` (weight set management)
- Acceptance: `demo-weight-set-001` not used in production baseline

### D. Typed production input adapters
- Scope: Map `ExecutionSnapshot` + `CoefficientContext` → calculator inputs
- Dependencies: A, B
- Files: `modules/orchestration/application/adapters.py`
- Acceptance: Unit-tested mapping; missing fields fail-closed

### E. Six-stage execution DAG
- Scope: `OrchestrationService` DAG executor
- Dependencies: A, B, D
- Files: `modules/orchestration/application/service.py`, `domain/dag.py`
- Acceptance: Integration test with all 5 stages passing

### F. Transaction-aware repositories and orchestration lifecycle
- Scope: `CalculationRunRepository`, `OrchestrationRunRepository`,
  `SourceBindingRepository`, `AuditRepository`
- Dependencies: E
- Files: `modules/orchestration/infrastructure/repositories.py`, `audit_repository.py`, `orm.py`
- Schema: `orchestration_runs`, `source_bindings` tables
- Acceptance: Multi-record transaction all-or-nothing; idempotent fingerprint

### G. Versioned source snapshot adapters
- Scope: Five `SourceSnapshotV1` types with field mapping tables
- Dependencies: E
- Files: `modules/orchestration/domain/snapshots.py`
- Acceptance: All fields mapped; adapter rejects unknown versions

### H. SourceBinding persistence and strict verification
- Scope: `SourceBindingRecord` creation, `SchemeService` source_binding_id integration
- Dependencies: F, G
- Files: `modules/orchestration/infrastructure/repositories.py`, `modules/schemes/application/service.py` (signature change only)
- Acceptance: SchemeService reads via binding; legacy/unbound/hash-missing rows rejected

### I. Hash/provenance/audit and durable failure recording
- Scope: Hash chain, provenance JSON, audit events, two-phase failure audit
- Dependencies: F, H
- Files: `modules/orchestration/domain/hash_chain.py`, `modules/orchestration/infrastructure/audit_repository.py`
- Acceptance: input_hash, result_hash, provenance, combined_source_hash correct; failure audit survives rollback

### J. SQLite/PostgreSQL idempotency and concurrency tests
- Scope: Full integration tests on both backends
- Dependencies: H, I
- Files: `tests/integration/test_orchestration.py`
- Acceptance: CI green for both; fingerprint uniqueness enforced

### K. Task 11 Phase B resumption
- Scope: Rebase PR #21, remove `EvaluationPrerequisiteMissingError` gate,
  wire `OrchestrationService` into evaluation runner
- Dependencies: A–J complete
- Files: PR #21 (rebase)
- Acceptance: baseline-feasible: outcome=success, all 8 stages passed

---

## 23. Task 11 Phase B Resumption Criteria

Issue #22 is complete when ALL of the following are true:

1. **Independent production PR merged** — separate from PR #21, with Engineering Review.
2. **Five CalculationRunRecord types** (zone, cooling_load, equipment, power, investment)
   produced by OrchestrationService via transaction-aware repositories.
3. **SourceBindingRecord materialized** — all five calculation IDs, hashes,
   combined_source_hash, orchestration_fingerprint.
4. **SchemeService consumes via `source_binding_id`** — explicit trust-boundary
   verification of all records.
5. **Approved coefficient context** — `CoefficientContextRecord` with all required
   codes resolved as approved → `requires_review=false`.
6. **Approved weight set** — not `demo-weight-set-001`.
7. **Hashes, provenance, and audit complete** — `input_hash`, `result_hash`,
   `provenance`, audit events for every stage + durable failure audit.
8. **Legacy/unbound/hash-missing records rejected** by production path.
9. **SQLite and PostgreSQL tests pass** — CI confirms both backends.
10. **Task 11 baseline achievable** — after rebasing PR #21, evaluation runner's
    baseline-feasible scenario passes all 8 required stages with `outcome=success`.

---

## Appendix A: File Reference Index

| File | Content |
|---|---|
| `backend/src/cold_storage/modules/projects/infrastructure/database.py` | DatabaseProjectService (own-session record_calculation — to be supplemented, not replaced) |
| `backend/src/cold_storage/modules/projects/infrastructure/orm.py` | CalculationRunRecord, AuditEventRecord |
| `backend/src/cold_storage/modules/calculations/domain/zone_planning.py` | ColdRoomZonePlanner |
| `backend/src/cold_storage/modules/calculations/domain/cooling_load.py` | CoolingLoadCalcInput, calculate_cooling_load |
| `backend/src/cold_storage/modules/calculations/domain/equipment.py` | Equipment calculator |
| `backend/src/cold_storage/modules/calculations/domain/power.py` | InstalledPowerCalcInput, calculate_installed_power |
| `backend/src/cold_storage/modules/calculations/domain/investment.py` | InvestmentEstimator |
| `backend/src/cold_storage/modules/schemes/application/service.py` | SchemeService (source_binding_id integration point) |
| `backend/src/cold_storage/modules/coefficients/domain/models.py` | CoefficientDefinition, CoefficientRevision |
| `docs/architecture/ADR-011-engineering-coefficient-registry.md` | Coefficient registry architecture |
| `docs/architecture/ADR-013-cooling-load-equipment.md` | Cooling load and equipment calculator design |
| `docs/audit/coefficient-inventory.md` | Complete hardcoded coefficient inventory |
| `docs/audit/gap-analysis.md` | Known capability gaps |
