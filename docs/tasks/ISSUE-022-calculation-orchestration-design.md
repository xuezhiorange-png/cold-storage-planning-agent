# ISSUE-022: Formal Calculation Orchestration and Persistence Design

**Issue:** [#22](https://github.com/xuezhiorange-png/cold-storage-planning-agent/issues/22)
**Date:** 2026-06-28
**Review:** 4587054607 — third-round engineering review addressed
**Status:** Design phase — awaiting re-review
**Type:** Architecture design only — no production implementation
**Unblocks:** Task 11 Phase B (PR #21)

---

## 1. Status and Decision Record

This document is a **design artefact only**.  No production code, migrations,
API routes, or runtime behaviour is changed — implementation requires a
separate reviewed task and PR.

**Changes in this revision (vs 7df4ded):**

1. `execution_identity_hash` added to fingerprint — project/version isolation prevents cross-project collision.
2. Preflight rejection separated from execution BLOCKED — `OrchestrationRequestRecord` + `PreflightFailure`.
3. Snapshot/context materialized AFTER fingerprint check — no orphan artifacts on idempotent hit.
4. Partial UNIQUE index enforces at most one RUNNING attempt per identity; CAS stale takeover.
5. `StageExecutionDiagnostic` vs `StagePersistedResult` — rollback-safe semantics.
6. SourceBinding strict slot/type/project/version verification; `combined_source_hash` single formula.
7. Audit outbox with `claimed_at`/`attempt_count`/idempotent materialization.
8. `project_version_id` as sole authoritative lookup key; `version_number` is captured metadata only.
9. SchemeService accepts `weight_set_revision_id` — revision hash/version bound to SchemeRun.
10. `SchemeRun` CHECK constraint; `SchemeSourceArchiveV1` artifact for safe downgrade.
11. Post-approval Issue #22 acceptance-criteria synchronization gate.
12. Lifecycle entities explicitly split: domain DTOs (immutable) vs ORM records (mutable).

---

## 2. Problem Statement and Abstraction Note

Same as previous revision.  Key unchanged facts:

Task 11's 8 required stages (`project`, `version`, `validation`, `planning`,
`zone_plan`, `power`, `investment`, `schemes`) operate at the evaluation
harness level.  Issue #22's 5 calculation stages (`zone`, `cooling_load`,
`equipment`, `power`, `investment`) operate at the production orchestration
level.  They are different abstractions and are not contradictory.

---

## 3. Existing-System Inventory and Confirmed Gaps

Same as previous revisions.  No changes to the inventory or the 11 capability
gaps (G1–G11).

---

## 4. Scope and Non-Goals

### In scope (this design)

- Request/preflight contracts and audit
- Execution identity/fingerprint with project isolation
- Five-stage calculation DAG
- SourceBindingRecord (one-way, COMPLETED only) with strict verification
- Identity/attempt lease with single-RUNNING constraint and CAS takeover
- UnitOfWork ownership model
- SourceSnapshotContentV1/EnvelopeV1 (non-self-referential hash)
- Transactional audit outbox with idempotent dispatcher
- ProjectVersion authoritative lookup by `project_version_id`
- Approved weight-set revision binding
- SchemeRun CHECK constraint and archive artifact
- Legacy migration strategy
- Post-approval Issue #22 sync gate

### Out of scope

- Implementation
- Scheme generation/scoring logic
- Evaluation/CLI changes
- API endpoint design
- Frontend changes

---

## 5. Architecture Decision

### 5.1 Module layout

```
backend/src/cold_storage/modules/orchestration/
├── application/
│   ├── __init__.py
│   ├── service.py              # OrchestrationService
│   ├── unit_of_work.py         # OrchestrationUnitOfWork
│   └── outbox_dispatcher.py    # AuditOutboxDispatcher
├── domain/
│   ├── __init__.py
│   ├── contracts.py             # DTOs (frozen dataclass)
│   ├── dag.py                   # Five-stage DAG
│   ├── errors.py
│   ├── fingerprint.py
│   ├── snapshots.py             # SourceSnapshotContentV1/EnvelopeV1
│   └── hash_chain.py
└── infrastructure/
    ├── __init__.py
    ├── repositories.py          # No sessions, no commits
    └── orm.py                   # Mutable ORM records
```

### 5.2 Execution order (frozen)

```
1. Load ProjectVersion by project_version_id; cross-check project_id.
2. Validate ProjectVersion status (draft/archived → preflight rejection).
3. Build in-memory ExecutionSnapshotCandidate; compute execution_identity_hash.
4. Resolve in-memory CoefficientContextCandidate; compute coefficient_context_hash.
5. Compute orchestration_fingerprint from execution_identity_hash + coefficient_context_hash + versions.
6. Query existing OrchestrationIdentityRecord by fingerprint.
   → If authoritative COMPLETED exists: return idempotent result
     (NO snapshot/context persisted).
7. Get-or-create ExecutionSnapshotRecord (idempotent — UNIQUE constraint).
8. Get-or-create CoefficientContextRecord (idempotent — UNIQUE constraint).
9. Create OrchestrationIdentityRecord (fingerprint UNIQUE).
10. Acquire execution attempt lease:
    - Check no other RUNNING attempt for this identity.
    - If stale RUNNING exists: CAS takeover (mark ABANDONED, create new attempt_number+1).
    - Create OrchestrationRunAttemptRecord(status=RUNNING).
11. Execute five-stage calculation DAG within all-or-nothing UnitOfWork.
12. On COMPLETED: materialize SourceBindingRecord.
13. On FAILED/BLOCKED: write terminal status in independent UnitOfWork.
```

### 5.3 UnitOfWork ownership

`OrchestrationService` owns the full transaction lifecycle via
`OrchestrationUnitOfWork`.  Callers provide a factory — never a
pre-existing session with pending work.  Repositories never create
sessions, commit, rollback, or close.

---

## 6. Data Model Overview

```
OrchestrationRequestRecord
    │ PREFLIGHT_REJECTED
    └── ACCEPTED
        │
        ▼
ProjectVersionExecutionSnapshot
    │ UNIQUE(project_version_id, input_snapshot_hash, schema_version)
    ▼
CoefficientContextRecord
    │ UNIQUE(project_version_id, content_hash)
    ▼
OrchestrationIdentityRecord
    │ UNIQUE(fingerprint)
    │ 1:N
    ▼
OrchestrationRunAttemptRecord
    │ UNIQUE(identity_id, attempt_number)
    │ UNIQUE partial: (identity_id) WHERE status='RUNNING'
    │ 1:N
    ▼
CalculationRunRecord × 5
    │ (NO reverse FK to SourceBinding)
    ▼ (COMPLETED only)
SourceBindingRecord
    │ UNIQUE(orchestration_identity_id, orchestration_run_attempt_id)
    ▼
SchemeRun
    │ CHECK(source_binding_id ↔ source_contract_version)
    ▼
SchemeSourceArchiveV1 (safe downgrade artifact)

Audit chain:
OrchestrationRequest / Identity / Attempt / Calculation / Binding
    │ same transaction
    ▼
AuditOutboxEvent
    │ at-least-once dispatch + idempotent materialization
    ▼
AuditEventRecord (outbox_event_id UNIQUE NOT NULL)
```

### 6.1 Entity lifecycle semantics

**Domain DTOs** (contracts.py, snapshots.py): frozen `@dataclass` — never mutated.
**ORM records** (orm.py): mutable where lifecycle fields change (status, heartbeat, completed_at).

Immutable fields on ORM records:
- `OrchestrationIdentityRecord.fingerprint`
- `OrchestrationIdentityRecord.execution_snapshot_id`
- `OrchestrationIdentityRecord.coefficient_context_id`
- `OrchestrationRunAttemptRecord.identity_id`
- `OrchestrationRunAttemptRecord.attempt_number`

Mutable fields on ORM records:
- `OrchestrationIdentityRecord.authoritative_completed_attempt_id`
- `OrchestrationRunAttemptRecord.status`
- `OrchestrationRunAttemptRecord.heartbeat_at`
- `OrchestrationRunAttemptRecord.completed_at`
- `OrchestrationRunAttemptRecord.source_binding_id`
- `OrchestrationRunAttemptRecord.failure_code`
- `OrchestrationRunAttemptRecord.failure_details`

---

## 7. Public Application Contract

### 7.1 OrchestrationInput

```python
@dataclass(frozen=True, slots=True)
class OrchestrationInput:
    project_id: str
    project_version_id: str              # sole authoritative lookup key
    coefficient_resolution_context: CoefficientResolutionContext
    actor: str
    correlation_id: str
```

Callers do NOT provide pre-created IDs.  `OrchestrationService` internally
captures snapshot and resolves context.

### 7.2 Request/preflight model

```python
@dataclass(frozen=True, slots=True)
class OrchestrationRequestRecord:
    id: str
    project_id: str
    project_version_id: str
    request_fingerprint: str             # SHA-256(project_id + project_version_id + correlation_id + timestamp)
    actor: str
    correlation_id: str
    status: str                          # PENDING | PREFLIGHT_REJECTED | ACCEPTED
    failure_code: str | None
    failure_field: str | None
    failure_details: dict | None
    created_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class PreflightFailure:
    request_id: str
    project_id: str
    project_version_id: str
    error_class: str
    code: str
    field: str
    details: dict
    occurred_at: datetime
```

**Preflight rejection** (before any identity/attempt exists):
- ProjectVersion `draft` → `ProjectVersionNotReadyError`
- ProjectVersion `archived` → `ProjectVersionArchivedError`
- ProjectVersion status unknown → `ProjectVersionStatusInvalidError`
- input snapshot schema unsupported → `SchemaNotSupportedError`
- coefficient resolution context invalid → `CoefficientResolutionError`
- No approved coefficient for required code → `CoefficientNotApprovedError`
- Ambiguous coefficient → `AmbiguousCoefficientError`

Preflight rejection creates:
- `OrchestrationRequestRecord(status=PREFLIGHT_REJECTED)` with failure details
- `AuditOutboxEvent(action=orchestration_request_rejected, request_id=...)`

Preflight rejection does NOT create:
- `OrchestrationIdentityRecord`
- `OrchestrationRunAttemptRecord`
- `CalculationRunRecord`
- `SourceBindingRecord`

**Execution BLOCKED** (after identity + attempt exist):
- Calculator structured blocker (missing upstream result)
- DAG-stage input mapping failure after entering execution

Execution BLOCKED writes:
- `OrchestrationRunAttemptRecord.status=BLOCKED` with failure details
- `AuditOutboxEvent(action=orchestration_blocked, identity_id=..., attempt_id=...)`

### 7.3 OrchestrationResult

```python
@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    request_id: str
    identity_id: str | None              # NULL on preflight rejection
    attempt_id: str | None               # NULL on preflight rejection
    attempt_number: int | None
    status: str                          # PREFLIGHT_REJECTED | COMPLETED | BLOCKED | FAILED
    requires_review: bool

    # COMPLETED: populated with five persisted stage results
    # BLOCKED/FAILED: empty list
    persisted_stages: tuple[StagePersistedResult, ...]

    # BLOCKED/FAILED: carries execution diagnostics (no persisted IDs)
    diagnostics: tuple[StageExecutionDiagnostic, ...]

    source_binding_id: str | None        # NON-NULL only for COMPLETED
    fingerprint: str | None              # NULL on preflight rejection
    started_at: datetime
    completed_at: datetime


@dataclass(frozen=True, slots=True)
class StagePersistedResult:
    """Only exists after COMPLETED transaction commits."""
    calculator_name: str
    calculation_run_id: str
    input_hash: str
    result_hash: str
    calculator_version: str
    snapshot_schema_version: str


@dataclass(frozen=True, slots=True)
class StageExecutionDiagnostic:
    """In-memory diagnostic — does NOT claim persistence."""
    calculator_name: str
    execution_status: str                 # passed | blocked | failed | skipped
    requires_review: bool
    input_hash: str | None
    result_hash: str | None
    blocker: dict | None                  # StructuredBlocker
    error: dict | None                    # StructuredError
```

**Rules:**
- COMPLETED: `persisted_stages` has five entries, `source_binding_id` non-null.
- BLOCKED/FAILED: `persisted_stages` empty, `source_binding_id` = NULL.
- `diagnostics` records what happened in-memory but makes no persistence claims.
- Rollback after some stages passed → no `CalculationRunRecord` exists → `persisted_stages` is empty.

---

## 8. Execution DAG

### 8.1 Five-stage calculation DAG (unchanged)

```
zone → cooling_load → equipment → power → investment
```

### 8.2 Task 11 stage mapping (unchanged)

| Task 11 stage | Issue #22 relationship |
|---|---|
| project, version, validation, planning | Existing evaluation scaffolding |
| zone_plan | Issue #22 stage: zone |
| power | Issue #22 stage: power |
| investment | Issue #22 stage: investment |
| schemes | Post-Issue-22 — calls SchemeService with source_binding_id |

---

## 9. Fingerprint with Project/Version Isolation

### 9.1 Execution identity hash

```python
execution_identity_hash = SHA-256(
    canonical_json({
        "project_id": project_id,
        "project_version_id": project_version_id,
        "version_number": version_number,
        "input_snapshot_hash": input_snapshot_hash,
        "execution_snapshot_schema_version": execution_snapshot_schema_version,
    })
)
```

### 9.2 Orchestration fingerprint

```python
orchestration_fingerprint = SHA-256(
    canonical_json({
        "execution_identity_hash": execution_identity_hash,
        "coefficient_context_hash": coefficient_context_hash,
        "orchestration_definition_version": orchestration_definition_version,
        "calculator_version_vector": calculator_version_vector,
        "input_mapping_schema_version": input_mapping_schema_version,
        "source_snapshot_schema_version": source_snapshot_schema_version,
    })
)
```

All components are computed via `canonical_json()` with the frozen
specification (sorted keys, Decimal strings, RFC 3339 UTC with Z suffix).

**Guarantees:**
- Different project_id + same inputs → different fingerprint.
- Same project, different project_version_id + same inputs → different fingerprint.
- Same ProjectVersion, same identity/context/versions → same fingerprint.
- `version_number` inconsistent with `project_version_id` → fail closed.

### 9.3 Orphan-free materialization

Fingerprint is computed **in memory** before any persistence.  Only when
no existing COMPLETED identity is found are snapshot and context persisted:

1. Compute execution_identity_hash and coefficient_context_hash in memory.
2. Compute orchestration_fingerprint.
3. Query `OrchestrationIdentityRecord WHERE fingerprint = ?`.
4. If authoritative COMPLETED exists → return immediately (NO persistence).
5. If new identity needed:
   - `INSERT … ON CONFLICT DO NOTHING` for ExecutionSnapshot (UNIQUE on project_version_id, input_snapshot_hash, schema_version).
   - `INSERT … ON CONFLICT DO NOTHING` for CoefficientContext (UNIQUE on project_version_id, content_hash).
   - `INSERT … ON CONFLICT DO NOTHING` for OrchestrationIdentity (UNIQUE on fingerprint).

**Unique keys:**

| Record | UNIQUE constraint |
|---|---|
| ProjectVersionExecutionSnapshot | (project_version_id, input_snapshot_hash, schema_version) |
| CoefficientContextRecord | (project_version_id, content_hash) |
| OrchestrationIdentityRecord | (fingerprint) |

Concurrent get-or-create returns the same authoritative artifact.

---

## 10. Identity, Attempt, and Concurrency

### 10.1 OrchestrationIdentityRecord

```python
class OrchestrationIdentityRecord:          # ORM — mutable fields
    id: str
    fingerprint: str                        # UNIQUE — immutable
    execution_snapshot_id: str              # immutable
    coefficient_context_id: str             # immutable
    orchestration_definition_version: str   # immutable
    calculator_version_vector: str          # immutable
    input_mapping_schema_version: str       # immutable
    source_snapshot_schema_version: str     # immutable
    authoritative_completed_attempt_id: str | None  # mutable
    created_at: datetime                    # immutable
```

### 10.2 OrchestrationRunAttemptRecord

```python
class OrchestrationRunAttemptRecord:        # ORM — mutable fields
    id: str
    identity_id: str                        # immutable
    attempt_number: int                     # immutable
    status: str                             # mutable: RUNNING | COMPLETED | BLOCKED | FAILED | ABANDONED
    requires_review: bool
    source_binding_id: str | None           # mutable — set on COMPLETED
    started_at: datetime
    heartbeat_at: datetime                  # mutable — updated periodically for RUNNING
    completed_at: datetime | None           # mutable
    actor: str
    correlation_id: str
    failure_code: str | None                # mutable
    failure_details: dict | None            # mutable
```

**UNIQUE(identity_id, attempt_number)**

### 10.3 Single RUNNING attempt constraint

```sql
CREATE UNIQUE INDEX uq_orchestration_attempt_one_running
    ON orchestration_run_attempts (identity_id)
    WHERE status = 'RUNNING';
```

PostgreSQL: native partial unique index.
SQLite: partial unique index (SQLite ≥ 3.25 supports `WHERE` on indexes).

At most one RUNNING attempt per identity at any time.

### 10.4 Atomic stale takeover (CAS)

```
def takeover_stale_attempt(identity_id: str, stale_attempt_id: str,
                            observed_heartbeat: datetime, now: datetime,
                            lease_timeout: timedelta) -> bool:
    """
    Atomically mark a stale RUNNING attempt as ABANDONED.
    Returns True if takeover succeeded, False if CAS failed.
    """

    # Only proceed if lease is truly expired
    if (now - observed_heartbeat) < lease_timeout:
        return False  # lease still valid — do NOT takeover

    # CAS: only update if status is still RUNNING and heartbeat unchanged
    result = session.execute(
        update(OrchestrationRunAttemptRecord)
        .where(
            OrchestrationRunAttemptRecord.id == stale_attempt_id,
            OrchestrationRunAttemptRecord.status == "RUNNING",
            OrchestrationRunAttemptRecord.heartbeat_at == observed_heartbeat,
        )
        .values(status="ABANDONED", completed_at=now)
    )
    return result.rowcount == 1
```

- CAS succeeds (1 row updated) → old attempt marked ABANDONED → create attempt_number + 1.
- CAS fails (0 rows) → another worker beat us, or heartbeat changed → reload current state → do NOT create new attempt.

### 10.5 State behaviour (updated)

| Existing state | Same fingerprint | Action |
|---|---|---|
| COMPLETED (authoritative) | ✓ | Return existing result (NO new attempt) |
| RUNNING (lease valid) | ✓ | Return IN_PROGRESS/CONFLICT |
| RUNNING (lease expired) | ✓ | CAS takeover → new attempt_number + 1 |
| FAILED | ✓ | New attempt_number + 1 |
| BLOCKED (same prereq) | ✓ | Return existing result |
| BLOCKED (prereq changed → different fingerprint) | ✗ | New identity, attempt_number = 1 |

---

## 11. SourceBinding Strict Verification

### 11.1 SourceBindingRecord (unchanged — one-way)

```python
class SourceBindingRecord:
    id: str
    project_id: str
    project_version_id: str
    execution_snapshot_id: str
    orchestration_identity_id: str
    orchestration_run_attempt_id: str
    orchestration_fingerprint: str

    zone_calculation_id: str
    cooling_load_calculation_id: str
    equipment_calculation_id: str
    power_calculation_id: str
    investment_calculation_id: str

    per_calculation_result_hashes: dict[str, str]
    combined_source_hash: str
    schema_version: str
    created_at: datetime
```

### 11.2 Binding slot → calculation type mapping (frozen)

| Slot | Expected calculation_type | Expected calculator_name |
|---|---|---|
| zone_calculation_id | zone | formal zone calculator name |
| cooling_load_calculation_id | cooling_load | cooling_load |
| equipment_calculation_id | equipment | equipment |
| power_calculation_id | power | installed_power |
| investment_calculation_id | investment | investment |

### 11.3 Per-record verification (SchemeService)

For each slot in the binding, the referenced record must satisfy ALL:

1. `record.id` == binding slot's calculation ID.
2. `record.project_id` == binding.project_id.
3. `record.project_version_id` == binding.project_version_id.
4. `record.execution_snapshot_id` == binding.execution_snapshot_id.
5. `record.orchestration_identity_id` == binding.orchestration_identity_id.
6. `record.orchestration_run_attempt_id` == binding.orchestration_run_attempt_id.
7. `record.calculator_name` matches the slot's expected calculator_name.
8. `record.schema_version` is supported.
9. `record.result_hash` recomputes to `binding.per_calculation_result_hashes[type]`.
10. `record.requires_review` == the `requires_review` in SourceSnapshotContentV1.

Any slot pointing to a record with wrong calculation type or calculator_name
→ fail closed.  No lenient matching.

### 11.4 combined_source_hash — single formula

```
combined_source_hash = SHA-256(
    canonical_json({
        "zone":          zone_result_hash,
        "cooling_load":  cooling_load_result_hash,
        "equipment":     equipment_result_hash,
        "power":         power_result_hash,
        "investment":    investment_result_hash,
    })
)
```

Where each value is `CalculationRunRecord.result_hash` (i.e.,
`SHA-256(canonical_json(SourceSnapshotContentV1))`).

Type key set is exactly these five.  No extra keys.  No missing keys.
Not payload.  Not envelope.  Not raw database JSON.

---

## 12. Transactional Audit Outbox — Idempotent Dispatcher

### 12.1 AuditOutboxEvent

| Field | Notes |
|---|---|
| id | PK |
| request_id | FK → OrchestrationRequestRecord (nullable — preflight events) |
| identity_id | FK → OrchestrationIdentityRecord (nullable) |
| attempt_id | FK → OrchestrationRunAttemptRecord (nullable) |
| calculation_run_id | FK → CalculationRunRecord (nullable) |
| source_binding_id | FK → SourceBindingRecord (nullable) |
| action | orchestration_request_rejected / orchestration_started / calculation_completed / source_binding_materialized / orchestration_completed / orchestration_failed / orchestration_blocked |
| payload | JSON |
| status | PENDING | PROCESSING | PUBLISHED |
| claimed_at | datetime (nullable) |
| claimed_by | str (nullable — worker ID) |
| attempt_count | int DEFAULT 0 |
| next_retry_at | datetime (nullable) |
| last_error_code | str (nullable) |
| published_at | datetime (nullable) |
| created_at | datetime |

### 12.2 AuditEventRecord extension

| Field | Notes |
|---|---|
| outbox_event_id | VARCHAR(36) UNIQUE NOT NULL — exactly one per outbox event |

### 12.3 Dispatcher contract

**Claim (atomic):**

PostgreSQL:
```sql
UPDATE audit_outbox
SET status = 'PROCESSING', claimed_at = NOW(), claimed_by = :worker_id,
    attempt_count = attempt_count + 1
WHERE id IN (
    SELECT id FROM audit_outbox
    WHERE status = 'PENDING'
       OR (status = 'PROCESSING' AND claimed_at < :lease_timeout)
    ORDER BY created_at
    LIMIT :batch_size
    FOR UPDATE SKIP LOCKED
)
RETURNING *
```

SQLite: single-transaction `UPDATE … WHERE status='PENDING' OR (status='PROCESSING' AND claimed_at < :timeout)` + retry.

**Deliver:**
1. Materialize `AuditEventRecord` with `outbox_event_id`.
2. Mark outbox `status='PUBLISHED'`, `published_at=NOW()`.

**Crash recovery:**
- `AuditEventRecord` inserted but outbox not yet PUBLISHED:
  - On retry, INSERT AuditEventRecord fails with UNIQUE violation on `outbox_event_id`.
  - Dispatcher catches unique conflict → outbox was already delivered → mark PUBLISHED.
- Outbox `PROCESSING` lease expired: re-claimed by next dispatcher cycle.

**Guarantee:** At-least-once delivery + idempotent materialization.
At most one `AuditEventRecord` per `outbox_event_id`.

---

## 13. ProjectVersion Authoritative Lookup

`project_version_id` is the **sole authoritative lookup key**.

```
1. Load ProjectVersionRecord by project_version_id.
2. Verify record.project_id == input.project_id.
3. Capture version_number into ExecutionSnapshot as metadata only.
4. All subsequent resolution uses project_version_id — never (project_id + version_number).
```

`version_number` is captured metadata for human readability and SchemeService
legacy-facing parameter cross-check.  It is NOT a parallel identity.

---

## 14. Approved Weight-Set Revision Binding

### 14.1 SchemeService contract — FROZEN CHANGE

```python
def generate_scheme_run(
    self,
    *,
    project_id: str,
    version: int,
    source_binding_id: str,
    weight_set_revision_id: str,        # NOT weight_set_id
    profile_codes: list[str],
    profile_parameters: dict[str, dict[str, Any]],
) -> dict[str, Any]:
```

**Flow:**
1. Load `SchemeWeightSetRevisionRecord` by `weight_set_revision_id`.
2. Verify `status == "approved"`.
3. Verify `generator_compatibility_version` matches current SchemeService.
4. Recompute `content_hash`.
5. Generate SchemeRun.
6. Persist in SchemeRun:
   - `weight_set_revision_id`
   - `weight_set_content_hash`
   - `weight_set_generator_compatibility_version`

### 14.2 Task 11 fixture resolution

```
1. Resolve by weight_set_code="baseline-balanced" + status="approved".
2. Get the latest approved compatible revision.
3. Pass the exact revision_id to SchemeService.
```

Fixture does NOT hard-code UUIDs.  Fixture does NOT pass bare `weight_set_code`.

---

## 15. SchemeRun Database Integrity and Archive

### 15.1 CHECK constraint

```sql
ALTER TABLE scheme_runs ADD CONSTRAINT ck_scheme_run_source_mode
CHECK (
    -- Legacy (no source binding)
    (source_binding_id IS NULL
     AND source_contract_version IS NULL
     AND weight_set_revision_id IS NULL
     AND weight_set_content_hash IS NULL)
    OR
    -- Production
    (source_binding_id IS NOT NULL
     AND source_contract_version IS NOT NULL
     AND weight_set_revision_id IS NOT NULL
     AND weight_set_content_hash IS NOT NULL
     AND weight_set_generator_compatibility_version IS NOT NULL)
);
```

### 15.2 SchemeSourceArchiveV1

For safe downgrade when SchemeRun references SourceBinding:

```python
@dataclass(frozen=True)
class SchemeSourceArchiveV1:
    scheme_run_id: str
    source_binding_id: str
    source_contract_version: str
    project_id: str
    project_version_id: str
    execution_snapshot_hash: str
    coefficient_context_hash: str
    # Five calculation IDs
    zone_calculation_id: str
    cooling_load_calculation_id: str
    equipment_calculation_id: str
    power_calculation_id: str
    investment_calculation_id: str
    # Five result hashes
    zone_result_hash: str
    cooling_load_result_hash: str
    equipment_result_hash: str
    power_result_hash: str
    investment_result_hash: str
    combined_source_hash: str
    weight_set_revision_id: str
    weight_set_content_hash: str
    archive_schema_version: str
    archived_at: datetime
    archive_hash: str                  # SHA-256 of all fields above
```

### 15.3 Safe downgrade rules

| Condition | Action |
|---|---|
| No production SchemeRun references SourceBinding | Downgrade allowed |
| Production SchemeRun exists | Downgrade **BLOCKED** |
| After explicit archive/export | Source rows still NOT auto-deleted |
| Source rows removable | Only via separate reviewed migration, AFTER archive verified |
| `archive_hash` | Must be verifiable |
| Historical query | Must be able to read either online binding or archive artifact |

---

## 16. CalculationRunRecord CHECK

```sql
CHECK (
    -- Legacy: all new fields NULL
    (orchestration_identity_id IS NULL
     AND orchestration_run_attempt_id IS NULL
     AND execution_snapshot_id IS NULL
     AND coefficient_context_id IS NULL
     AND input_hash IS NULL
     AND result_hash IS NULL
     AND provenance IS NULL
     AND schema_version IS NULL)
    OR
    -- Orchestrated: all new fields NON-NULL
    (orchestration_identity_id IS NOT NULL
     AND orchestration_run_attempt_id IS NOT NULL
     AND execution_snapshot_id IS NOT NULL
     AND coefficient_context_id IS NOT NULL
     AND input_hash IS NOT NULL
     AND result_hash IS NOT NULL
     AND provenance IS NOT NULL
     AND schema_version IS NOT NULL)
)
```

No `source_binding_id` column — SourceBinding is one-way owner.

---

## 17. Error Taxonomy (updated)

New preflight-specific errors:

| Exception | code | field |
|---|---|---|
| `ProjectVersionNotReadyError` | PROJ_VERSION_NOT_READY | version_status |
| `ProjectVersionArchivedError` | PROJ_VERSION_ARCHIVED | project_version_id |
| `ProjectVersionStatusInvalidError` | PROJ_VERSION_STATUS_INVALID | version_status |
| `SchemaNotSupportedError` | SCHEMA_NOT_SUPPORTED | schema_version |
| `CoefficientResolutionError` | COEFF_RESOLUTION_FAILED | coefficient_code |
| `CoefficientNotApprovedError` | COEFF_NOT_APPROVED | coefficient_code |
| `AmbiguousCoefficientError` | COEFF_AMBIGUOUS | coefficient_code |
| `WeightSetNotApprovedError` | WEIGHT_SET_NOT_APPROVED | weight_set_revision_id |
| `WeightSetIncompatibleError` | WEIGHT_SET_INCOMPATIBLE | generator_compatibility_version |
| `SourceBindingSlotTypeError` | SOURCE_BINDING_SLOT_TYPE | slot_name |

---

## 18. Post-Approval Issue #22 Synchronization Gate

**Design review acceptance does NOT automatically modify Issue #22.**
After this design is accepted and before implementation begins, the
following must be updated in Issue #22's acceptance criteria:

1. Change "four categories" (zone, cooling_load, equipment, investment)
   → "five categories" (zone, cooling_load, equipment, **power**, investment).
2. Add: `power` CalculationRunRecord required.
3. Add: `SourceBindingRecord` materialization.
4. Add: `OrchestrationIdentityRecord` + `OrchestrationRunAttemptRecord`.
5. Add: Approved weight-set revision.
6. Add: Transactional audit outbox.
7. Add: Legacy row CHECK constraint.

This gate is a **mandatory prerequisite** before any production code
is written.  It is listed as sub-task **N** in the implementation breakdown.

---

## 19. Implementation Work Breakdown

All sub-tasks are design-level only — no implementation in this PR.

### A. Request/preflight contracts and audit
- Scope: `OrchestrationInput`, `OrchestrationRequestRecord`, `PreflightFailure`, preflight error types
- Dependencies: None
- Files: `modules/orchestration/domain/contracts.py`, `errors.py`
- Schema: `orchestration_requests` table
- Non-goals: No execution logic

### B. Execution snapshot identity and get-or-create
- Scope: `ProjectVersionExecutionSnapshot`, `execution_identity_hash`, idempotent get-or-create
- Dependencies: A
- Files: `modules/orchestration/domain/fingerprint.py`, `infrastructure/repositories.py`
- Schema: `project_version_execution_snapshots` + UNIQUE constraint
- Non-goals: No coefficient resolution

### C. Materialized coefficient context and approved catalog
- Scope: `CoefficientContextRecord`, approved revision seed, idempotent get-or-create
- Dependencies: B, coefficient registry
- Files: `modules/orchestration/domain/coefficient_context.py`, `modules/coefficients/`
- Schema: `coefficient_contexts` + UNIQUE(project_version_id, content_hash)
- Non-goals: No demo fallback

### D. Approved scheme weight-set governance
- Scope: `SchemeWeightSetRevisionRecord`, baseline-balanced approved revision
- Dependencies: scheme module
- Files: `modules/schemes/`
- Non-goals: No demo-weight-set-001 in baseline

### E. Production input adapters
- Scope: Map ExecutionSnapshot + CoefficientContext → calculator inputs
- Dependencies: B, C
- Files: `modules/orchestration/application/adapters.py`
- Non-goals: No zero-fallback

### F. Five-stage calculation DAG
- Scope: Sequential DAG executor
- Dependencies: B, C, E
- Files: `modules/orchestration/application/service.py`, `domain/dag.py`
- Non-goals: No parallel execution

### G. Orchestration identity and attempt lease
- Scope: `OrchestrationIdentityRecord`, `OrchestrationRunAttemptRecord`, single-RUNNING constraint, CAS takeover
- Dependencies: B, C
- Files: `modules/orchestration/infrastructure/repositories.py`, `orm.py`
- Schema: `orchestration_identities`, `orchestration_run_attempts` + partial UNIQUE index
- Non-goals: No distributed locking

### H. UnitOfWork and transaction-aware repositories
- Scope: `OrchestrationUnitOfWork`, all repositories (no sessions, no commits)
- Dependencies: F, G
- Files: `modules/orchestration/application/unit_of_work.py`, `infrastructure/repositories.py`
- Non-goals: No callers passing sessions with pending work

### I. SourceSnapshot content/envelope adapters
- Scope: Five `SourceSnapshotContentV1` + `SourceSnapshotEnvelopeV1`
- Dependencies: F
- Files: `modules/orchestration/domain/snapshots.py`
- Non-goals: No self-referential hash

### J. SourceBinding persistence and strict verification
- Scope: `SourceBindingRecord` (one-way), SchemeService integration with slot/type/project/version verification
- Dependencies: G, H, I
- Files: `modules/orchestration/infrastructure/repositories.py`, `modules/schemes/application/service.py`
- Schema: `source_bindings`
- Non-goals: No reverse FK from CalculationRunRecord

### K. Power-to-Scheme mapping
- Scope: SchemeService reads installed_power_kw_e from Power snapshot ONLY
- Dependencies: I, J
- Files: `modules/schemes/application/service.py`, tests
- Non-goals: No Equipment fallback

### L. Transactional audit outbox and idempotent dispatcher
- Scope: `AuditOutboxEvent`, `AuditOutboxDispatcher` with claim/retry/idempotent materialization
- Dependencies: H
- Files: `modules/orchestration/application/outbox_dispatcher.py`, `infrastructure/orm.py`
- Schema: `audit_outbox`, ALTER `audit_events` ADD `outbox_event_id` UNIQUE NOT NULL
- Non-goals: No external message broker

### M. SQLite/PostgreSQL constraints and concurrency tests
- Scope: Full integration tests on both backends
- Dependencies: J, K, L
- Files: `tests/integration/test_orchestration.py`
- Non-goals: No production deployment

### N. Issue #22 acceptance-criteria synchronization
- Scope: Update Issue #22 body from "four categories" → "five categories" + all new contracts
- Dependencies: Design review accepted
- No code changes
- Mandatory gate before implementation

### O. Task 11 Phase B resumption
- Scope: Rebase PR #21, remove prerequisite gate, wire OrchestrationService
- Dependencies: A–N complete
- Files: PR #21 (rebase), evaluation runner
- Non-goals: No Phase C/D

---

## 20. Test Matrix (new items this round)

| # | Test |
|---|---|
| T28 | Different project_id + same inputs → different fingerprint |
| T29 | Same project, different project_version_id + same inputs → different fingerprint |
| T30 | Same ProjectVersion, same identity/context/versions → same fingerprint |
| T31 | version_number inconsistent with project_version_id → fail closed |
| T32 | Preflight rejection (draft/archived/invalid status) → no identity/attempt created |
| T33 | Preflight rejection → request-level audit outbox created |
| T34 | Preflight rejection → typed PreflightFailure returned |
| T35 | Blocker after identity/attempt exists → attempt.status=BLOCKED |
| T36 | Idempotent hit on COMPLETED → no snapshot/context persisted |
| T37 | Concurrent snapshot/context get-or-create → same authoritative artifact returned |
| T38 | Single RUNNING attempt per identity enforced by partial UNIQUE index |
| T39 | CAS stale takeover: matching heartbeat → ABANDONED + new attempt |
| T40 | CAS stale takeover: heartbeat changed → CAS fails → no new attempt |
| T41 | Transaction B rollback → persisted_stages empty, diagnostics populated |
| T42 | Diagnostics never claim persisted calculation_run_id |
| T43 | SourceBinding slot points to wrong calculation type → fail closed |
| T44 | Binding record project/version/snapshot mismatch → fail closed |
| T45 | combined_source_hash exact and stable across runs |
| T46 | Outbox multi-dispatcher atomic claim → no duplicate materialization |
| T47 | Outbox crash recovery: AuditEvent exists but outbox not published → idempotent |
| T48 | AuditEventRecord.outbox_event_id UNIQUE constraint enforced |
| T49 | project_version_id sole lookup; version_number mismatch cross-checked |
| T50 | Approved weight-set revision resolved by code + status; hash bound to SchemeRun |
| T51 | Unapproved weight-set revision → SchemeService rejects |
| T52 | Incompatible generator_version → SchemeService rejects |
| T53 | SchemeRun CHECK: legacy (all NULL) passes |
| T54 | SchemeRun CHECK: production (all NON-NULL) passes |
| T55 | SchemeRun CHECK: mixed (partial NULL) fails |
| T56 | SchemeSourceArchiveV1 archive_hash verifiable |
| T57 | Downgrade blocked when production SchemeRun references SourceBinding |

---

## 21. Task 11 Phase B Resumption Criteria

Issue #22 is complete when:

1. Independent production PR merged (separate from PR #21).
2. Five CalculationRunRecord types produced by OrchestrationService.
3. SourceBindingRecord materialized for COMPLETED runs — one-way owner.
4. SchemeService consumes via `source_binding_id` + `weight_set_revision_id`.
5. Approved coefficient context + approved weight set → `requires_review=false`.
6. Non-self-referential `result_hash` consistent across all three locations.
7. Fingerprint isolates project/version identity — no cross-project collision.
8. Preflight rejection vs execution BLOCKED separated.
9. Orphan-free snapshot/context: idempotent hit creates no artifacts.
10. Single RUNNING attempt constraint; CAS stale takeover.
11. Rollback-safe: persisted_stages empty after rollback.
12. SourceBinding strict slot/type/project/version verification.
13. combined_source_hash single formula, exact five keys.
14. Outbox at-least-once + idempotent materialization.
15. Legacy CHECK constraint enforced.
16. SchemeRun CHECK + SchemeSourceArchiveV1 + safe downgrade.
17. SQLite + PostgreSQL tests pass.
18. Task 11 baseline: all 8 stages passed, `outcome=success`.
19. Issue #22 acceptance criteria synchronized (sub-task N).

---

## Appendix A: File Reference Index

| File | Content |
|---|---|
| `backend/src/cold_storage/modules/projects/infrastructure/orm.py` | CalculationRunRecord, AuditEventRecord |
| `backend/src/cold_storage/modules/calculations/domain/` | All calculators |
| `backend/src/cold_storage/modules/schemes/application/service.py` | SchemeService integration point |
| `docs/architecture/ADR-011-engineering-coefficient-registry.md` | Coefficient registry |
| `docs/architecture/ADR-013-cooling-load-equipment.md` | Cooling load/equipment |
| `docs/audit/coefficient-inventory.md` | Coefficient inventory |
