# ISSUE-022: Formal Calculation Orchestration and Persistence Design

**Issue:** [#22](https://github.com/xuezhiorange-png/cold-storage-planning-agent/issues/22)
**Date:** 2026-06-28
**Review:** 4587046149 — second-round engineering review addressed
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

**Changes in this revision (vs 70b24c6):**

1. `result_hash` made non-self-referential — split into `SourceSnapshotContentV1` (hashed) + `SourceSnapshotEnvelopeV1` (carries hash).
2. `CalculationRunRecord.source_binding_id` removed — SourceBinding is one-way owner.
3. SourceBinding materialized ONLY for COMPLETED runs — BLOCKED/FAILED produce no binding.
4. Identity/attempt split — `OrchestrationIdentityRecord` (fingerprint UNIQUE) + `OrchestrationRunAttemptRecord` (1:N).
5. Executable preparation order — OrchestrationService internally captures snapshot and resolves context.
6. UnitOfWork ownership — service owns transaction lifecycle; caller provides factory, not session.
7. Equipment snapshot no longer carries `installed_power_kw_e` — power stage is sole authority.
8. Transactional audit outbox replaces best-effort audit — terminal status + outbox intent same transaction.
9. Five-stage DAG terminology unified; Task 11's 8 stages acknowledged as different abstraction.
10. ProjectVersion status contract frozen — no TBD, no caller override.
11. Approved weight-set sub-task fixed in implementation breakdown.
12. Legacy CHECK constraint, SchemeRun FK, and safe downgrade rules frozen.

---

## 2. Problem Statement

**Current blocked state (Task 11 Phase B, PR #21):**

The evaluation runner must exercise all 8 required production stages.
The final stage, `schemes`, invokes `SchemeService.generate_scheme_run()`.
SchemeService currently selects "latest `CalculationRunRecord` by
`calculator_name` DESC" — it cannot verify that all records came from the
same orchestration run, share the same coefficient context, or have
matching hashes.

The evaluation runner is blocked by an explicit prerequisite gate
(`EvaluationPrerequisiteMissingError`), waiting for a formal production
orchestration service that:

1. Captures an immutable `ProjectVersionExecutionSnapshot`.
2. Resolves and materializes a `CoefficientContextRecord`.
3. Executes the five-stage calculation DAG: zone → cooling_load → equipment → power → investment.
4. Persists results with full hashes and provenance.
5. Materializes a `SourceBindingRecord` **only when all five stages pass**.
6. Exposes `source_binding_id` to SchemeService for explicit trust-boundary verification.

**Abstraction note:** Task 11's 8 required stages (`project`, `version`, `validation`,
`planning`, `zone_plan`, `power`, `investment`, `schemes`) operate at the evaluation
harness level.  Issue #22's 5 calculation stages (`zone`, `cooling_load`, `equipment`,
`power`, `investment`) operate at the production orchestration level.  The former wraps
the latter plus scaffolding (project/version lifecycle, validation, planning aggregation,
scheme generation).  They are different abstractions and are not contradictory.

---

## 3. Existing-System Inventory

Same as previous revision.  Key unchanged facts:

- `DatabaseProjectService.record_calculation()` owns its own session — cannot be used for multi-record transactions.
- `SchemeService` reads `CalculationRunRecord` by `calculator_name` ORDER BY `created_at DESC` — no cross-record binding.
- `CoefficientSet` is in-memory only — no persistent identity or content hash.
- All coefficient sets are demo/unverified — no approved catalog covering all required codes.

---

## 4. Confirmed Capability Gaps

Same 11 gaps as previous revision (G1–G11).  No changes.

---

## 5. Scope and Non-Goals

### In scope

- Five-stage calculation DAG contracts
- SourceBindingRecord (one-way owner, COMPLETED-only)
- Transaction-aware UnitOfWork and repositories
- Identity/attempt split with fingerprint idempotency
- ProjectVersionExecutionSnapshot lifecycle
- CoefficientContextRecord with content hash
- SourceSnapshotContentV1/EnvelopeV1 adapters (non-self-referential hashes)
- Transactional audit outbox
- Legacy migration strategy with CHECK constraints
- Safe downgrade rules
- Approved weight-set governance sub-task
- Error taxonomy
- Test matrix
- Task 11 resumption criteria

### Out of scope

- Implementation (separate task/PR)
- Scheme generation/scoring logic
- Evaluation/CLI changes
- API endpoint design
- Equipment model selection
- Frontend changes

---

## 6. Architecture Decision

### 6.1 Module layout

```
backend/src/cold_storage/modules/orchestration/
├── application/
│   ├── __init__.py
│   ├── service.py              # OrchestrationService
│   ├── unit_of_work.py         # OrchestrationUnitOfWork (context manager)
│   └── outbox_dispatcher.py    # AuditOutboxDispatcher
├── domain/
│   ├── __init__.py
│   ├── contracts.py             # OrchestrationInput, OrchestrationResult, StageResult
│   ├── dag.py                   # Five-stage DAG
│   ├── errors.py                # OrchestrationError hierarchy
│   ├── fingerprint.py           # OrchestrationFingerprint
│   ├── snapshots.py             # SourceSnapshotContentV1, SourceSnapshotEnvelopeV1
│   └── hash_chain.py            # Hash helpers
└── infrastructure/
    ├── __init__.py
    ├── repositories.py          # All repositories (no sessions, no commits)
    └── orm.py                   # All ORM records
```

### 6.2 UnitOfWork ownership

```python
class OrchestrationUnitOfWork:
    """Transaction boundary owned by OrchestrationService.

    Provides a SQLAlchemy Session.  The service calls begin/commit/rollback/close.
    Callers provide a factory — never a pre-existing session with pending work.
    """

    def __enter__(self) -> OrchestrationUnitOfWork: ...
    def __exit__(self, ...) -> None: ...
    @property
    def session(self) -> Session: ...


class OrchestrationUnitOfWorkFactory:
    def create(self) -> OrchestrationUnitOfWork: ...


class OrchestrationService:
    def __init__(self, uow_factory: OrchestrationUnitOfWorkFactory, ...) -> None: ...

    def run(self, input: OrchestrationInput) -> OrchestrationResult:
        # Service owns the full lifecycle:
        uow = self._uow_factory.create()
        with uow:
            # ... do work ...
            uow.commit()
        return result
```

**Callers must NOT pass a pre-existing Session with uncommitted work.**
Repositories receive the current UoW's session, never create sessions,
never commit, never rollback, never close.

### 6.3 Explicitly NOT allowed

- ❌ Orchestration inside SchemeService, evaluation, API routes, or CLI.
- ❌ `DatabaseProjectService.record_calculation()` in orchestration path.
- ❌ SchemeService querying "latest by calculator_name DESC" for production.
- ❌ Implicit defaults or zero-value fallbacks.
- ❌ Callers injecting sessions with pending work.

---

## 7. Public Application Contract

### 7.1 Preparation order (orchestration-owned)

`OrchestrationService.run()` internally performs preparation.  Callers do NOT
pre-create snapshots or contexts:

```
1. Read ProjectVersion by project_id + version_number
2. Capture ProjectVersionExecutionSnapshot
3. Resolve and materialize CoefficientContextRecord
4. Determine calculator version vector
5. Compute orchestration fingerprint
6. Get-or-create OrchestrationIdentityRecord (fingerprint UNIQUE)
7. Acquire execution attempt lease (new OrchestrationRunAttemptRecord)
8. Execute five-stage calculation DAG
9. On COMPLETED: materialize SourceBindingRecord
```

### 7.2 OrchestrationInput (caller-provided)

```python
@dataclass(frozen=True, slots=True)
class OrchestrationInput:
    project_id: str
    project_version_id: str
    coefficient_resolution_context: CoefficientResolutionContext
        # product_type, location_region, zone/process scope
        # — NOT a pre-resolved CoefficientContextRecord
    actor: str
    correlation_id: str
```

### 7.3 OrchestrationResult

```python
@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    identity_id: str                     # OrchestrationIdentityRecord.id
    attempt_id: str                      # OrchestrationRunAttemptRecord.id
    attempt_number: int
    status: str                          # COMPLETED | BLOCKED | FAILED
    requires_review: bool
    stages: dict[str, StageResult]       # keyed by calculator_name
    source_binding_id: str | None        # NON-NULL only when status=COMPLETED
    fingerprint: str
    started_at: datetime
    completed_at: datetime
```

### 7.4 StageResult

```python
@dataclass(frozen=True, slots=True)
class StageResult:
    calculator_name: str
    status: str                          # passed | failed | blocked | skipped
    requires_review: bool
    calculation_run_id: str | None       # NULL if blocked before execution
    input_hash: str | None               # NULL if blocked before execution
    result_hash: str | None              # NULL if blocked before execution
    calculator_version: str
    snapshot_schema_version: str
```

**Rules:**
- `passed` → `calculation_run_id`, `input_hash`, `result_hash` all NON-NULL.
- `blocked` (before calculator call) → `calculation_run_id` = NULL, hashes = NULL.
- `failed` (calculator or persistence failure) → `calculation_run_id` = NULL, hashes = NULL.
- `skipped` (upstream blocker) → same as blocked.

### 7.5 SourceBindingRecord — COMPLETED only

```python
@dataclass(frozen=True, slots=True)
class SourceBindingRecord:
    """ONE-WAY owner of five calculation records.  CalculationRunRecord does
    NOT reference back to SourceBinding."""

    id: str
    project_id: str
    project_version_id: str
    execution_snapshot_id: str
    orchestration_identity_id: str          # FK → OrchestrationIdentityRecord
    orchestration_run_attempt_id: str        # FK → OrchestrationRunAttemptRecord
    orchestration_fingerprint: str

    # One-way references to calculation records
    zone_calculation_id: str
    cooling_load_calculation_id: str
    equipment_calculation_id: str
    power_calculation_id: str
    investment_calculation_id: str

    per_calculation_result_hashes: dict[str, str]
    combined_source_hash: str
    schema_version: str                     # "1.0"
    created_at: datetime
```

**Binding rules:**
- Created ONLY when orchestration status = COMPLETED (all five stages passed).
- BLOCKED/FAILED → `source_binding_id` = NULL, no SourceBindingRecord exists.
- SchemeService MUST NOT be called when `source_binding_id` is NULL.
- `CalculationRunRecord` does NOT carry `source_binding_id` — no reverse FK.

### 7.6 SchemeService contract — FROZEN

```python
def generate_scheme_run(
    self,
    *,
    project_id: str,
    version: int,
    source_binding_id: str,          # REQUIRED for production path
    profile_codes: list[str],
    weight_set_id: str,
    profile_parameters: dict[str, dict[str, Any]],
) -> dict[str, Any]:
```

**Flow:**

1. Load `SourceBindingRecord` by `source_binding_id`.
2. Verify `project_id` and `version` match.
3. Load exactly the five calculation records by their IDs from the binding.
4. Verify every record's `orchestration_identity_id` and `orchestration_run_attempt_id` match the binding.
5. Verify `result_hash` recomputes to `per_calculation_result_hashes[type]`.
6. Verify `combined_source_hash` recomputes.
7. Verify `schema_version` supported and `coefficient_context_id` matches.
8. Reject legacy/unbound/hash-missing records.

---

## 8. Execution DAG

### 8.1 Five-stage calculation DAG

```
Preparation (orchestration-owned):
  ProjectVersion → ExecutionSnapshot → CoefficientContext → Identity + Fingerprint

Calculation (five stages):
  zone → cooling_load → equipment → power → investment

Post-calculation (COMPLETED only):
  SourceBindingRecord → SchemeService
```

### 8.2 Per-node definition

| Stage | Upstream | Calculator | Key output |
|---|---|---|---|
| zone | ExecutionSnapshot only | ColdRoomZonePlanner.plan() | zones, areas, positions |
| cooling_load | zone + coefficient context | calculate_cooling_load() | design_cooling_load_kw_r |
| equipment | cooling_load + coefficient context | equipment calculator | compressor capacities kW(r), compressor_input_power_kw_e |
| power | equipment.compressor_input_power_kw_e + ProjectVersion loads | InstalledPowerCalculator | **total_installed_power_kw_e** |
| investment | zone areas + power.total_installed_power_kw_e + coefficient context | InvestmentEstimator.estimate() | total_investment_cny |

### 8.3 Task 11 stage mapping

| Task 11 stage | Issue #22 relationship |
|---|---|
| project | Existing — evaluation wraps DatabaseProjectService.create_project() |
| version | Existing — evaluation wraps DatabaseProjectService.create_version() |
| validation | Existing — evaluation wraps validate_inputs() |
| planning | Existing — evaluation wraps CoreCalculationService |
| zone_plan | **Issue #22 stage: zone** |
| power | **Issue #22 stage: power** |
| investment | **Issue #22 stage: investment** |
| schemes | Post-Issue-22 — calls SchemeService with source_binding_id |

---

## 9. Versioned SourceSnapshot Adapters

### 9.1 Non-self-referential hash design

```python
@dataclass(frozen=True, slots=True)
class SourceSnapshotContentV1:
    """The content that is hashed — does NOT contain result_hash."""
    schema_version: str
    calculation_type: str
    calculator_name: str
    calculator_version: str
    source_input_hash: str           # SHA-256 of canonicalized calculator input
    requires_review: bool
    warning_codes: tuple[str, ...]
    payload: dict[str, object]       # typed per calculation_type


@dataclass(frozen=True, slots=True)
class SourceSnapshotEnvelopeV1:
    """Carries content + its hash.  result_hash is NOT part of content."""
    content: SourceSnapshotContentV1
    result_hash: str                 # SHA-256(canonical_json(content))
```

**Hash computation (sole definition):**
```
result_hash = SHA-256(canonical_json(SourceSnapshotContentV1))
```

This exact same value is stored in all three locations:
1. `CalculationRunRecord.result_hash`
2. `SourceBindingRecord.per_calculation_result_hashes[type]`
3. Re-computed by `SchemeService` during strict verification

No separate payload-only or full-snapshot hash variants.  One definition.

### 9.2 Canonical JSON specification (frozen)

| Rule | Detail |
|---|---|
| Key ordering | Unicode code point order (sorted) |
| Separators | `(",", ":")` — no whitespace |
| Encoding | UTF-8, `ensure_ascii=False` |
| Decimal | Canonical decimal string (e.g. `"3.14"`), never float |
| NaN/Infinity | Forbidden — raises error |
| datetime | UTC RFC 3339 with fixed `Z` suffix |
| list | Preserve order |
| set | Forbidden in contract |
| UUID | Lowercase canonical string |
| Excluded | `created_at`, `correlation_id` and other non-business identity fields unless explicitly listed in field tables |

### 9.3 Field mapping tables

**ZoneSourceSnapshotContentV1.payload:**

| Field | Source | Type |
|---|---|---|
| `total_daily_throughput_kg_day` | calculator result | Decimal |
| `zones[].zone_code` | calculator result | str |
| `zones[].zone_name` | calculator result | str |
| `zones[].temperature_level` | calculator result | str |
| `zones[].area_m2` | calculator result | Decimal |
| `zones[].position_count` | calculator result | int |
| `zones[].storage_capacity_kg` | calculator result | Decimal |
| `zones[].process_compatibility` | calculator result | str |
| `zones[].hygiene_zone` | calculator result | str |

**CoolingLoadSourceSnapshotContentV1.payload:**

| Field | Source | Type |
|---|---|---|
| `design_cooling_load_kw_r` | sum per-zone after diversity + margin | Decimal |
| `sensible_load_kw_r` | sum per-zone sensible | Decimal |
| `latent_load_kw_r` | sum per-zone latent | Decimal |
| `infiltration_load_kw_r` | sum per-zone infiltration | Decimal |

**EquipmentSourceSnapshotContentV1.payload:**

| Field | Source | Type |
|---|---|---|
| `compressor_operating_capacity_kw_r` | total across systems | Decimal |
| `compressor_installed_capacity_kw_r` | operating × redundancy | Decimal |
| `condenser_heat_rejection_kw` | total across systems | Decimal |
| `compressor_input_power_kw_e` | from COP derivation | Decimal |

**⚠️ `installed_power_kw_e` is NOT in Equipment payload.**  Power is the sole
authority for installed power.  `compressor_input_power_kw_e` is one input to
the power stage — it is not the full facility installed power.

**PowerSourceSnapshotContentV1.payload:**

| Field | Source | Type |
|---|---|---|
| `total_installed_power_kw_e` | sum of all load categories | Decimal |
| `estimated_peak_demand_kw_e` | after demand factors | Decimal |
| `load_breakdown.refrigeration_compressors_kw_e` | from equipment stage | Decimal |
| `load_breakdown.evaporator_fans_kw_e` | from equipment stage | Decimal |
| `load_breakdown.condenser_fans_kw_e` | from equipment stage | Decimal |
| `load_breakdown.defrost_kw_e` | from equipment stage | Decimal |
| `load_breakdown.lighting_kw_e` | from ProjectVersion | Decimal |
| `load_breakdown.processing_equipment_kw_e` | from ProjectVersion | Decimal |
| `load_breakdown.auxiliary_kw_e` | from ProjectVersion | Decimal |
| `source_equipment_calculation_id` | equipment CalculationRunRecord.id | str |

**InvestmentSourceSnapshotContentV1.payload:**

| Field | Source | Type |
|---|---|---|
| `total_investment_cny` | from estimator | Decimal |
| `zone_investments` | from estimator | dict[str, Decimal] |
| `source_power_calculation_id` | power CalculationRunRecord.id | str |
| `source_zone_calculation_id` | zone CalculationRunRecord.id | str |

### 9.4 SchemeService power mapping (frozen)

SchemeService schemes use `installed_power_kw_e` from:
- **`PowerSourceSnapshotContentV1.payload.total_installed_power_kw_e`**

SchemeService MUST NOT:
- Read `installed_power_kw_e` from Equipment snapshot.
- Fallback to Equipment when Power is missing.
- Use `compressor_input_power_kw_e` as facility installed power.

---

## 10. Data Model Overview

```
ProjectVersion
    │ capture (once, immutable)
    ▼
ProjectVersionExecutionSnapshot
    │
    ▼
CoefficientContextRecord
    │ content_hash, revision_bindings
    ▼
OrchestrationIdentityRecord         ← fingerprint UNIQUE
    │ 1:N
    ▼
OrchestrationRunAttemptRecord       ← UNIQUE(identity_id, attempt_number)
    │ 1:N (calculation stages)
    ▼
CalculationRunRecord × 5            ← FK → identity + attempt (NOT → source_binding)
    │
    │ one-way reference (COMPLETED only)
    ▼
SourceBindingRecord                 ← FK → identity + attempt
    │
    ▼
SchemeRun                           ← FK → source_binding (NOT NULL for production)
    │
    ▼
AuditOutboxEvent                    ← references identity/attempt/calculation/binding
    │ dispatched asynchronously
    ▼
AuditEventRecord
```

**FK direction rules:**
- `CalculationRunRecord` → `OrchestrationIdentityRecord` + `OrchestrationRunAttemptRecord` (child)
- `SourceBindingRecord` → `OrchestrationIdentityRecord` + `OrchestrationRunAttemptRecord` (child)
- `SourceBindingRecord` → 5 × `CalculationRunRecord` (one-way, parent)
- `CalculationRunRecord` does NOT reference `SourceBindingRecord` (no reverse FK)
- `SchemeRun` → `SourceBindingRecord` (child)

---

## 11. Identity, Attempt, and Retry Lifecycle

### 11.1 OrchestrationIdentityRecord

```python
@dataclass(frozen=True)
class OrchestrationIdentityRecord:
    id: str
    fingerprint: str                         # UNIQUE
    execution_snapshot_id: str
    coefficient_context_id: str
    orchestration_definition_version: str
    calculator_version_vector: str           # canonical sorted
    input_mapping_schema_version: str
    source_snapshot_schema_version: str
    authoritative_completed_attempt_id: str | None
    created_at: datetime
```

### 11.2 OrchestrationRunAttemptRecord

```python
@dataclass(frozen=True)
class OrchestrationRunAttemptRecord:
    id: str
    identity_id: str                         # FK → OrchestrationIdentityRecord
    attempt_number: int                      # 1-based, monotonically increasing
    status: str                              # RUNNING | COMPLETED | BLOCKED | FAILED | ABANDONED
    requires_review: bool
    source_binding_id: str | None            # NON-NULL only when COMPLETED
    started_at: datetime
    heartbeat_at: datetime
    completed_at: datetime | None
    actor: str
    correlation_id: str
    failure_code: str | None
    failure_details: dict | None
```

**UNIQUE(identity_id, attempt_number)**

### 11.3 Fingerprint computation

```
fingerprint = SHA-256(
    execution_snapshot.input_snapshot_hash      # 64 hex
    + coefficient_context.content_hash          # 64 hex
    + orchestration_definition_version           # e.g. "1.0.0"
    + calculator_version_vector                  # sorted: "cooling_load=1.0.0,equipment=1.0.0,..."
    + input_mapping_schema_version               # "1.0"
    + source_snapshot_schema_version             # "1.0"
)
```

Snapshot and context MUST be materialized before fingerprint computation.

### 11.4 State behaviour

| Existing state | Same fingerprint | Action |
|---|---|---|
| COMPLETED (authoritative) | ✓ | Return existing `OrchestrationResult` — no new attempt |
| RUNNING (lease valid) | ✓ | Return IN_PROGRESS/CONFLICT |
| RUNNING (lease expired) | ✓ | Mark old ABANDONED; create attempt_number + 1 |
| FAILED | ✓ | Create attempt_number + 1 |
| BLOCKED | ✓ (same prereq) | Return existing BLOCKED result |
| BLOCKED | ✗ (prereq changed → different fingerprint) | New identity, attempt_number = 1 |

Calculator version change → fingerprint changes → new identity.
Coefficient revision change → coefficient_context_hash changes → new identity.
Input change → execution_snapshot_hash changes → new identity.

### 11.5 Concurrency

**PostgreSQL:** `INSERT … ON CONFLICT (fingerprint) DO NOTHING` on `OrchestrationIdentityRecord`.
For attempt lease: UNIQUE(identity_id, attempt_number) — first writer wins.

**SQLite:** `INSERT OR IGNORE` + `busy_timeout` + retry on `SQLITE_BUSY`.
UNIQUE constraint is the correctness mechanism — database is the single source of truth.

---

## 12. UnitOfWork and Transaction Ownership

### 12.1 Transaction boundaries

| Transaction | Content | UnitOfWork |
|---|---|---|
| Preparation | ExecutionSnapshot + CoefficientContext + Identity + RUNNING attempt + audit outbox(orchestration_started) | Same UoW |
| Calculation | 5 × CalculationRunRecord + SourceBinding (COMPLETED only) + attempt.status=COMPLETED + audit outbox events | Same UoW (all-or-nothing) |
| Terminal failure | attempt.status=FAILED/BLOCKED + audit outbox(orchestration_failed/blocked) | Independent UoW |

### 12.2 Transactional audit outbox

```python
@dataclass
class AuditOutboxEvent:
    id: str
    identity_id: str | None
    attempt_id: str | None
    calculation_run_id: str | None
    source_binding_id: str | None
    action: str                    # orchestration_started | calculation_completed |
                                    # source_binding_materialized | orchestration_completed |
                                    # orchestration_failed | orchestration_blocked
    payload: dict
    published: bool                # default False
    created_at: datetime
```

**Rules:**
- Outbox events are written in the SAME transaction as the business state they describe.
- Terminal status and outbox intent are transactionally consistent — no "lost audit on rollback".
- `AuditOutboxDispatcher` (background or synchronous) reads unpublished events and
  materializes them into `AuditEventRecord`.  Marks `published=True` on success.
- Dispatcher retries on failure.  `AuditEventRecord` is created exactly once per outbox event.
- Terminal status does not depend on outbox delivery success.
- Outbox delivery failure does not roll back terminal status.

---

## 13. ProjectVersion Execution Snapshot

### 13.1 Design

```python
@dataclass(frozen=True)
class ProjectVersionExecutionSnapshot:
    id: str
    project_id: str
    project_version_id: str
    version_number: int
    version_status: str          # copied from ProjectVersionRecord at capture
    input_snapshot: dict
    input_snapshot_hash: str
    schema_version: str          # "1.0"
    captured_at: datetime
```

### 13.2 Status contract (frozen)

| Status | Issue #22 orchestration allowed? |
|---|---|
| `generated` | ✓ |
| `under_review` | ✓ |
| `reviewed` | ✓ |
| `approved` | ✓ |
| `draft` | ✗ → `ProjectVersionNotReadyError` |
| `archived` | ✗ → `ProjectVersionArchivedError` |
| unknown | ✗ → `ProjectVersionStatusInvalidError` |

**Task 11 baseline fixture:** `approved` ProjectVersion required.
**No generic caller override.**  If special execution is needed in future,
an explicit `AuthorizedExecutionOverride` type with actor, reason,
authorization scope, and audit event must be designed separately.

---

## 14. Coefficient Context

Same design as previous revision with the following clarifications:

- `content_hash` = SHA-256(canonical JSON of `revision_bindings` + `scope_context` + `resolution_policy_version`).
- `captured_at` excluded from content hash.
- Immutable after creation.
- New orchestration runs MUST re-resolve — never reuse stale context unless
  the caller explicitly specifies a `coefficient_context_id`.

---

## 15. Approved Scheme Weight-Set Governance

**Fixed sub-task C of Issue #22 implementation:**

```python
@dataclass(frozen=True)
class SchemeWeightSetRevisionRecord:
    id: str
    weight_set_code: str             # e.g. "baseline-balanced"
    revision_number: int
    status: str                      # approved
    weights: dict
    content_hash: str
    generator_compatibility_version: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    approved_by: str | None
    approved_at: datetime | None
    supersedes_revision_id: str | None
    created_at: datetime
```

**Baseline usage:**
- `weight_set_code = "baseline-balanced"`
- `status = "approved"`
- `generator_compatibility_version` matching current SchemeService
- Resolved by code + status filter — fixture does NOT hard-code UUID

**Task 11 resumption requires:** approved weight set exists; content hash
bound to SchemeRun; `demo-weight-set-001` NOT used for baseline.

---

## 16. Review Propagation

```
stage.requires_review = calculator.requires_review   (only — no warning-based promotion)

Orchestration aggregation:
  1. Any stage failed?       → FAILED
  2. Any stage blocked?      → BLOCKED
  3. Any stage review=true?  → COMPLETED + requires_review=true
  4. Else                    → COMPLETED + requires_review=false
```

---

## 17. Error Taxonomy

Same as previous revision, plus:

| Exception | code | field |
|---|---|---|
| `ProjectVersionNotReadyError` | PROJ_VERSION_NOT_READY | version_status |
| `ProjectVersionArchivedError` | PROJ_VERSION_ARCHIVED | project_version_id |
| `ProjectVersionStatusInvalidError` | PROJ_VERSION_STATUS_INVALID | version_status |
| `WeightSetNotApprovedError` | WEIGHT_SET_NOT_APPROVED | weight_set_code |

---

## 18. CalculationRunRecord — Updated Fields

| Field | New | Nullable | Notes |
|---|---|---|---|
| `orchestration_identity_id` | NEW | NULL | FK → OrchestrationIdentityRecord |
| `orchestration_run_attempt_id` | NEW | NULL | FK → OrchestrationRunAttemptRecord |
| `execution_snapshot_id` | NEW | NULL | FK → ProjectVersionExecutionSnapshot |
| `coefficient_context_id` | NEW | NULL | FK → CoefficientContextRecord |
| `input_hash` | NEW | NULL | SHA-256 of canonicalized input |
| `result_hash` | NEW | NULL | SHA-256(SourceSnapshotContentV1) |
| `provenance` | NEW | NULL | JSON |
| `schema_version` | NEW | NULL | e.g. "1.0" |

**DELETED from design:** `source_binding_id` — SourceBinding is one-way owner.

**Provenance JSON:**
```json
{
  "orchestration_identity_id": "...",
  "orchestration_run_attempt_id": "...",
  "coefficient_context_id": "...",
  "execution_snapshot_id": "...",
  "upstream_calculation_ids": {
    "zone": "...",
    "cooling_load": "..."
  },
  "orchestration_fingerprint": "..."
}
```

### 18.1 Legacy CHECK constraint

```sql
CHECK (
    -- Legacy row: all new fields NULL
    (
        orchestration_identity_id IS NULL
        AND orchestration_run_attempt_id IS NULL
        AND execution_snapshot_id IS NULL
        AND coefficient_context_id IS NULL
        AND input_hash IS NULL
        AND result_hash IS NULL
        AND provenance IS NULL
        AND schema_version IS NULL
    )
    OR
    -- Orchestrated row: all new fields NON-NULL
    (
        orchestration_identity_id IS NOT NULL
        AND orchestration_run_attempt_id IS NOT NULL
        AND execution_snapshot_id IS NOT NULL
        AND coefficient_context_id IS NOT NULL
        AND input_hash IS NOT NULL
        AND result_hash IS NOT NULL
        AND provenance IS NOT NULL
        AND schema_version IS NOT NULL
    )
)
```

PostgreSQL: native CHECK constraint.
SQLite: CHECK constraint (supported in SQLite ≥ 3.25) or application-level validation.

---

## 19. SchemeRun SourceBinding FK and Safe Downgrade

### 19.1 SchemeRun

| New field | Nullable | Notes |
|---|---|---|
| `source_binding_id` | NULLABLE (legacy) | FK → SourceBindingRecord |
| `source_contract_version` | NULLABLE | "1.0" for production rows |

**Production path:** `source_binding_id` NOT NULL — enforced by application.
Legacy demo SchemeRun rows: `source_binding_id` = NULL.  Application-level
CHECK distinguishes production from legacy rows.

### 19.2 Safe downgrade

| Condition | Rule |
|---|---|
| Any `SchemeRun.source_binding_id` references a `SourceBindingRecord` | **Downgrade BLOCKED** |
| Downgrade precondition | Caller must first detect references and export/archive |
| Dangling references | **Not acceptable** — downgrade must fail with clear error |
| Historical SchemeRun | Must retain source identity and hash evidence even after export |
| Auto-deletion | **Forbidden** — SourceBinding with active references must not be dropped |

Downgrade command MUST check references before proceeding.  Error message
MUST identify which SchemeRun rows block the downgrade.

---

## 20. Migration Assessment

### 20.1 New tables

| Table | Indexes |
|---|---|
| `project_version_execution_snapshots` | |
| `coefficient_contexts` | |
| `orchestration_identities` | UNIQUE(fingerprint) |
| `orchestration_run_attempts` | UNIQUE(identity_id, attempt_number) |
| `source_bindings` | UNIQUE(orchestration_identity_id, orchestration_run_attempt_id) |
| `audit_outbox` | INDEX(published, created_at) |

### 20.2 Altered tables

| Table | Change |
|---|---|
| `calculation_runs` | ADD 8 nullable columns + CHECK constraint |
| `scheme_runs` | ADD `source_binding_id` (nullable), `source_contract_version` (nullable) |

### 20.3 Order

1. CREATE new tables (no FKs to them yet).
2. ALTER `calculation_runs` ADD columns (all nullable).
3. CREATE FKs from `calculation_runs` to new tables.
4. ALTER `scheme_runs` ADD columns.
5. Add CHECK constraint (PostgreSQL) or application guard (SQLite).
6. Precondition for production usage: all referenced records exist.

---

## 21. Test Matrix (new items)

| # | Test |
|---|---|
| T1 | `result_hash` = SHA-256(SourceSnapshotContentV1) — no self-reference |
| T2 | Same `result_hash` across CalculationRunRecord, SourceBinding, SchemeService |
| T3 | Tampered snapshot content → `result_hash` mismatch detected |
| T4 | Tampered snapshot envelope hash → mismatch detected |
| T5 | `CalculationRunRecord` has no `source_binding_id` column |
| T6 | BLOCKED orchestration → no SourceBindingRecord; `source_binding_id` = NULL |
| T7 | FAILED orchestration → no SourceBindingRecord; `source_binding_id` = NULL |
| T8 | COMPLETED orchestration → SourceBindingRecord materialized |
| T9 | Same fingerprint COMPLETED → idempotent return; no new attempt |
| T10 | Same fingerprint FAILED → new attempt_number |
| T11 | Same fingerprint RUNNING (stale) → new attempt |
| T12 | ExecutionSnapshot + CoefficientContext materialized before fingerprint |
| T13 | UnitOfWork not committing caller's other pending work |
| T14 | Equipment snapshot has no `installed_power_kw_e` |
| T15 | SchemeService `installed_power_kw_e` reads Power snapshot ONLY |
| T16 | Power missing → SchemeService rejects, no Equipment fallback |
| T17 | Transaction B rollback → no calculation/binding residue |
| T18 | Terminal status + audit outbox in same transaction |
| T19 | Outbox dispatcher retries; AuditEventRecord created exactly once |
| T20 | Outbox delivery failure → terminal status unaffected |
| T21 | `draft` ProjectVersion → `ProjectVersionNotReadyError` |
| T22 | `archived` ProjectVersion → `ProjectVersionArchivedError` |
| T23 | Approved weight set resolver returns correct revision |
| T24 | Legacy `calculation_runs` row passes CHECK (all NULL) |
| T25 | Orchestrated row passes CHECK (all NON-NULL) |
| T26 | Partially-filled row fails CHECK |
| T27 | Downgrade blocked when SchemeRun references SourceBinding |

---

## 22. Implementation Work Breakdown

All sub-tasks are design-level only — no implementation in this PR.

### A. Execution snapshot and orchestration contracts
- Scope: `ProjectVersionExecutionSnapshot`, `OrchestrationInput/Result`, `StageResult`, `OrchestrationFingerprint`
- Dependencies: None
- Files: `modules/orchestration/domain/contracts.py`, `fingerprint.py`
- Schema: `project_version_execution_snapshots`
- Non-goals: No API, no CLI

### B. Materialized coefficient context and approved catalog
- Scope: `CoefficientContextRecord`, approved revision seed
- Dependencies: A, coefficient registry (Task 3)
- Files: `modules/orchestration/domain/coefficient_context.py`, `modules/coefficients/`
- Schema: `coefficient_contexts`
- Non-goals: No demo fallback

### C. Approved scheme weight-set governance
- Scope: `SchemeWeightSetRevisionRecord`, approved baseline weight set
- Dependencies: scheme module
- Files: `modules/schemes/`
- Non-goals: No demo-weight-set-001 in baseline

### D. Production input adapters
- Scope: Map ExecutionSnapshot + CoefficientContext → calculator inputs
- Dependencies: A, B
- Files: `modules/orchestration/application/adapters.py`
- Non-goals: No zero-fallback

### E. Five-stage calculation DAG
- Scope: DAG executor calling five calculators in sequence
- Dependencies: A, B, D
- Files: `modules/orchestration/application/service.py`, `domain/dag.py`
- Non-goals: No parallel execution (sequential is correct for dependencies)

### F. Identity, attempt lease and retry lifecycle
- Scope: `OrchestrationIdentityRecord`, `OrchestrationRunAttemptRecord`, retry logic
- Dependencies: A
- Files: `modules/orchestration/infrastructure/repositories.py`, `orm.py`
- Schema: `orchestration_identities`, `orchestration_run_attempts`
- Non-goals: No distributed locking beyond DB constraints

### G. Transaction-aware UnitOfWork and repositories
- Scope: `OrchestrationUnitOfWork`, all repositories
- Dependencies: E, F
- Files: `modules/orchestration/application/unit_of_work.py`, `infrastructure/repositories.py`
- Non-goals: No callers passing sessions with pending work

### H. SourceSnapshot content/envelope adapters
- Scope: Five `SourceSnapshotContentV1` + `SourceSnapshotEnvelopeV1` with field mapping
- Dependencies: E
- Files: `modules/orchestration/domain/snapshots.py`
- Non-goals: No self-referential hash

### I. SourceBinding persistence and SchemeService integration
- Scope: `SourceBindingRecord` (one-way), SchemeService `source_binding_id`
- Dependencies: F, G, H
- Files: `modules/orchestration/infrastructure/repositories.py`, `modules/schemes/application/service.py`
- Schema: `source_bindings`
- Non-goals: No reverse FK from CalculationRunRecord

### J. Power-to-Scheme mapping
- Scope: Ensure SchemeService reads `installed_power_kw_e` from Power snapshot ONLY
- Dependencies: H, I
- Files: `modules/schemes/application/service.py` (mapping), tests
- Non-goals: No Equipment fallback

### K. Transactional audit outbox
- Scope: `AuditOutboxEvent`, `AuditOutboxDispatcher`
- Dependencies: G
- Files: `modules/orchestration/application/outbox_dispatcher.py`, `infrastructure/orm.py`
- Schema: `audit_outbox`
- Non-goals: No external message broker dependency

### L. SQLite/PostgreSQL migration and concurrency tests
- Scope: Full integration on both backends
- Dependencies: I, J, K
- Files: `tests/integration/test_orchestration.py`
- Non-goals: No production deployment

### M. Task 11 Phase B resumption
- Scope: Rebase PR #21, remove prerequisite gate, wire OrchestrationService
- Dependencies: A–L complete
- Files: PR #21 (rebase), evaluation runner
- Non-goals: No Phase C/D content

---

## 23. Task 11 Phase B Resumption Criteria

Issue #22 is complete when:

1. Independent production PR merged (separate from PR #21).
2. Five CalculationRunRecord types produced by OrchestrationService.
3. SourceBindingRecord materialized for COMPLETED runs — one-way owner.
4. SchemeService consumes via `source_binding_id` with strict verification.
5. Approved coefficient context produces `requires_review=false`.
6. Approved weight set exists; `demo-weight-set-001` not used.
7. Non-self-referential `result_hash` consistent across all three locations.
8. Legacy/unbound/hash-missing rows rejected by production path.
9. Terminal status + audit outbox transactionally consistent.
10. Downgrade blocked when SchemeRun references SourceBinding.
11. SQLite + PostgreSQL tests pass.
12. Task 11 baseline: all 8 stages passed, `outcome=success`.

---

## Appendix A: File Reference Index

| File | Content |
|---|---|
| `backend/src/cold_storage/modules/projects/infrastructure/orm.py` | CalculationRunRecord, AuditEventRecord |
| `backend/src/cold_storage/modules/calculations/domain/zone_planning.py` | ColdRoomZonePlanner |
| `backend/src/cold_storage/modules/calculations/domain/cooling_load.py` | calculate_cooling_load |
| `backend/src/cold_storage/modules/calculations/domain/equipment.py` | Equipment calculator |
| `backend/src/cold_storage/modules/calculations/domain/power.py` | InstalledPower calculator |
| `backend/src/cold_storage/modules/calculations/domain/investment.py` | InvestmentEstimator |
| `backend/src/cold_storage/modules/schemes/application/service.py` | SchemeService (integration point) |
| `docs/architecture/ADR-011-engineering-coefficient-registry.md` | Coefficient registry |
| `docs/architecture/ADR-013-cooling-load-equipment.md` | Cooling load/equipment design |
| `docs/audit/coefficient-inventory.md` | Coefficient inventory |
| `docs/audit/gap-analysis.md` | Known gaps |
