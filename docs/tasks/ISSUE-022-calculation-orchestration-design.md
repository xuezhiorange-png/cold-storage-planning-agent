# ISSUE-022: Formal Calculation Orchestration and Persistence Design

**Issue:** #22
**Draft PR:** #23
**Date:** 2026-06-28
**Review addressed:** 4587180512
**Previous Head:** `5d737fc91042979e75f80049c1cd76595749f737`
**Current Head:** `efd2d0db31a6ea51de40951399ed04c5ee8803cb`
**Status:** Design phase — awaiting re-review
**Type:** Design only — no production implementation
**Unblocks after implementation and independent review:** Task 11 Phase B (PR #21)

---

## 1. Decision status and hard constraints

This document freezes the implementable architecture for Issue #22. This revision changes design documentation only. It does not add or modify production code, tests, migrations, runtime behavior, evaluation logic, frontend code, or CI workflows.

The following repository state remains mandatory throughout this design review:

- PR #23 remains Draft, Open, and unmerged.
- Issue #22 remains Open.
- PR #21 is not modified.
- Issue #20 remains Open.
- Task 11 Phase B remains BLOCKED.
- Task 11 Phase C and Phase D are not started.
- Task 12 is not started.

The following previously accepted contracts remain frozen and are not reopened:

1. `SourceSnapshotContentV1` is hashable content; `SourceSnapshotEnvelopeV1` carries `result_hash` outside that content.
2. `result_hash` never enters its own hash input.
3. `CalculationRunRecord` does not hold a reverse `source_binding_id` foreign key.
4. `SourceBindingRecord` is created only for a fully committed COMPLETED attempt.
5. BLOCKED and FAILED attempts never invoke `SchemeService`.
6. `OrchestrationIdentityRecord` and `OrchestrationRunAttemptRecord` are separate persistence concepts.
7. `OrchestrationService` owns every UnitOfWork lifecycle; repositories never commit.
8. Equipment compressor input power and Power installed power are separate semantics.
9. `PowerSourceSnapshotV1.total_installed_power_kw_e` is the only authoritative installed-power source for Scheme generation.
10. Audit intent is written through a transactional outbox.
11. The production calculation DAG has exactly five stages: zone, cooling_load, equipment, power, investment.
12. Task 11 baseline execution uses an approved immutable `ProjectVersion`.
13. Approved Scheme weight-set governance is a fixed Issue #22 implementation subtask.
14. Legacy `CalculationRunRecord` rows obey an all-null/all-non-null integrity rule for orchestration fields.
15. A supported downgrade must not create dangling `SourceBindingRecord` references.

---

## 2. Problem statement and boundaries

Task 11 currently cannot produce a successful baseline because `SchemeService` lacks a formal production source chain. Issue #22 must provide one authoritative path that:

1. accepts an approved `ProjectVersion` by immutable ID;
2. captures an immutable execution snapshot;
3. resolves an approved coefficient context;
4. executes the five formal calculators in dependency order;
5. persists all five results atomically;
6. binds the five records into one strict `SourceBindingRecord`;
7. lets `SchemeService` consume only that verified binding;
8. binds an approved immutable Scheme weight-set revision to the resulting `SchemeRun`;
9. records request-, attempt-, calculation-, and binding-level audit evidence.

Task 11’s evaluation stages and Issue #22’s calculation stages are different abstractions. Task 11 may expose `project`, `version`, `validation`, `planning`, `zone_plan`, `power`, `investment`, and `schemes`, while Issue #22 internally executes exactly:

```text
zone -> cooling_load -> equipment -> power -> investment
```

Preparation artifacts and source binding are not calculator stages.

---

## 3. Scope and non-goals

### 3.1 In scope for the implementation that follows this design

- request and preflight persistence;
- immutable execution snapshot capture;
- materialized approved coefficient context;
- project/version-isolated orchestration fingerprint;
- idempotent artifact get-or-create;
- orchestration identity and attempt lease management;
- five-stage calculation execution;
- transaction-aware calculation persistence;
- typed source snapshot adapters;
- strict SourceBinding persistence and verification;
- SchemeService production trust boundary;
- approved Scheme weight-set revision governance;
- SchemeRun source integrity and provenance;
- transactional audit outbox and idempotent dispatcher;
- SQLite and PostgreSQL concurrency/integrity behavior;
- downgrade archive artifact and historical read contract.

### 3.2 Out of scope for this PR

- `OrchestrationService` implementation;
- ORM models or repositories;
- Alembic migrations;
- approved coefficient or weight-set seed data;
- Scheme generation/scoring logic changes;
- Task 11 runner changes;
- API endpoint design;
- frontend changes;
- production deployment or external message-broker rollout.

---

## 4. Proposed module ownership

```text
backend/src/cold_storage/modules/orchestration/
├── application/
│   ├── service.py                 # OrchestrationService
│   ├── adapters.py                # Project/snapshot/calculator input adapters
│   ├── unit_of_work.py            # OrchestrationUnitOfWorkFactory
│   └── outbox_dispatcher.py       # AuditOutboxDispatcher
├── domain/
│   ├── contracts.py               # immutable command/result DTOs
│   ├── errors.py                  # typed structured errors
│   ├── fingerprint.py             # canonical hashes/fingerprint
│   ├── snapshots.py               # SourceSnapshot content/envelope DTOs
│   └── dag.py                     # five-stage dependency definition
└── infrastructure/
    ├── orm.py                     # mutable persisted lifecycle entities
    └── repositories.py            # session-bound, transaction-aware repositories
```

Scheme trust-boundary changes belong to:

```text
backend/src/cold_storage/modules/schemes/application/service.py
backend/src/cold_storage/modules/schemes/infrastructure/
```

No orchestration implementation belongs in `evaluation/`.

---

## 5. Canonical JSON and hash rules

All hashes in this design use the existing frozen canonical JSON rules. No hash may be produced by directly concatenating strings.

Canonicalization requirements:

- UTF-8 JSON;
- object keys sorted lexicographically;
- no insignificant whitespace;
- arrays preserve declared semantic order;
- `Decimal` serialized as normalized base-10 strings, never binary floats;
- datetimes serialized as RFC 3339 UTC with `Z` suffix;
- dates serialized as ISO `YYYY-MM-DD`;
- enums serialized by their exact string value;
- UUIDs/identifiers serialized as lowercase canonical strings;
- mappings reject duplicate logical keys after normalization;
- non-finite numeric values are rejected;
- schema-defined exact key sets reject missing or extra keys where stated.

`SHA-256(x)` means SHA-256 over the UTF-8 bytes returned by `canonical_json(x)`.

All `result_hash` values in this design are **execution-bound**: they hash the complete `SourceSnapshotContentV1` including execution provenance (see §13.3, §13.5.7), not just the business payload.  There is no separate "output-only hash" or "payload hash".

---

## 6. Authoritative ProjectVersion lookup and execution snapshot

### 6.1 Sole authoritative lookup

`project_version_id` is the only authoritative ProjectVersion lookup key.

Formal flow:

1. load `ProjectVersionRecord` by `project_version_id`;
2. fail closed when no record exists;
3. verify `record.project_id == input.project_id`;
4. require `record.status == "approved"`;
5. capture `record.version_number` as snapshot metadata;
6. never re-query by `(project_id, version_number)` later in the workflow.

`version_number` is not a parallel identity. It is captured metadata and may be used only for human-readable output and the legacy-facing `SchemeService` version cross-check. Any mismatch between a caller-facing version parameter and the loaded record fails closed.

### 6.2 ExecutionSnapshotCandidate and record

`OrchestrationService` builds an immutable `ExecutionSnapshotCandidate` in memory from the approved ProjectVersion and validates its schema before persistence.

The persisted `ProjectVersionExecutionSnapshot` contains at least:

- `id`;
- `project_id`;
- `project_version_id`;
- `version_number`;
- `input_snapshot` canonical JSON;
- `input_snapshot_hash`;
- `schema_version`;
- `captured_at`;
- captured ProjectVersion status and source revision metadata.

Unique identity:

```sql
UNIQUE (project_version_id, input_snapshot_hash, schema_version)
```

The record is immutable after insert.

### 6.3 Execution identity hash

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

Required guarantees:

- different `project_id`, identical inputs -> different hash;
- same project, different `project_version_id`, identical inputs -> different hash;
- same ProjectVersion and identical snapshot -> identical hash;
- `version_number` inconsistent with the loaded `project_version_id` -> fail closed before identity creation.

---

## 7. Materialized coefficient context

`CoefficientContextCandidate` is resolved in memory from the approved coefficient catalog. It includes exact approved revision IDs, values, units, source metadata, resolution scope, schema version, and the captured resolution context.

`coefficient_context_hash` is SHA-256 over the complete canonical candidate content, excluding database-generated ID and timestamps.

The persisted `CoefficientContextRecord` contains at least:

- `id`;
- `project_id`;
- `project_version_id`;
- canonical content;
- `content_hash`;
- `schema_version`;
- `captured_at`.

Cross-project reuse is intentionally disabled because the record preserves project/version resolution scope and audit meaning. Unique identity is therefore:

```sql
UNIQUE (project_version_id, content_hash)
```

Callers cannot supply `coefficient_context_id`. The service always resolves and verifies the candidate from the formal context.

---

## 8. Orchestration fingerprint and idempotency

### 8.1 Fingerprint

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

`calculator_version_vector` is a canonical mapping with exactly the five calculation types as keys and exact calculator versions as values.

### 8.2 Orphan-free materialization order

The service must follow this order:

1. load and validate ProjectVersion by `project_version_id`;
2. build `ExecutionSnapshotCandidate` in memory;
3. compute `execution_identity_hash`;
4. resolve `CoefficientContextCandidate` in memory;
5. compute `coefficient_context_hash`;
6. compute `orchestration_fingerprint`;
7. query `OrchestrationIdentityRecord` by fingerprint;
8. when an authoritative COMPLETED attempt exists, return it without creating a snapshot or context;
9. otherwise get-or-create the execution snapshot;
10. get-or-create the coefficient context;
11. get-or-create the identity and acquire an attempt lease.

### 8.3 Backend-specific get-or-create

PostgreSQL:

```sql
INSERT ... ON CONFLICT (...) DO NOTHING
RETURNING id;
```

When no row is returned, reload by the exact unique key in the same transaction.

SQLite:

- use `INSERT OR IGNORE` followed by reload by exact unique key; or
- attempt a normal insert, catch `IntegrityError`, roll back to a savepoint, then reload.

The implementation must not roll back unrelated UnitOfWork state. Concurrent callers must receive the same authoritative snapshot/context record. A completed idempotency hit must produce no orphan preparation artifacts.

---

## 9. Request/preflight contract

### 9.1 Immutable command DTO

```python
@dataclass(frozen=True, slots=True)
class OrchestrationInput:
    project_id: str
    project_version_id: str
    coefficient_resolution_context: CoefficientResolutionContext
    actor: str
    correlation_id: str
```

### 9.2 Mutable persisted request entity

`OrchestrationRequestRecord` is a mutable persisted lifecycle entity, not a frozen dataclass.

Required fields:

```python
class OrchestrationRequestRecord:
    id: str
    project_id: str
    project_version_id: str
    request_fingerprint: str
    actor: str
    correlation_id: str
    status: str                 # PENDING | PREFLIGHT_REJECTED | ACCEPTED
    resolved_identity_id: str | None
    resolved_attempt_id: str | None
    failure_code: str | None
    failure_field: str | None
    failure_details: Mapping[str, object] | None
    created_at: datetime
    completed_at: datetime | None
```

`request_fingerprint` is an audit correlation hash, not the orchestration idempotency key:

```python
request_fingerprint = SHA-256(
    canonical_json({
        "project_id": input.project_id,
        "project_version_id": input.project_version_id,
        "coefficient_resolution_context": input.coefficient_resolution_context,
        "actor": input.actor,
        "correlation_id": input.correlation_id,
    })
)
```

It is indexed but not globally unique; every invocation receives a distinct request ID. `resolved_identity_id` and `resolved_attempt_id` are null for PENDING/PREFLIGHT_REJECTED requests and are populated for ACCEPTED requests — including an idempotent hit that returns an existing authoritative identity/attempt (no new identity is necessarily created). A database CHECK enforces those status-dependent nullability rules.

### 9.3 Typed preflight result

```python
@dataclass(frozen=True, slots=True)
class PreflightFailure:
    request_id: str
    project_id: str
    project_version_id: str
    error_class: str
    code: str
    field: str
    details: Mapping[str, object]
    occurred_at: datetime
```

### 9.4 Preflight rejection classification

The following occur before an orchestration identity or attempt exists and therefore produce a typed preflight rejection:

- request identity validation failure;
- ProjectVersion not found;
- ProjectVersion/project mismatch;
- ProjectVersion status is draft;
- ProjectVersion status is archived;
- ProjectVersion status is unknown or otherwise illegal;
- execution snapshot schema is invalid or unsupported;
- coefficient resolution context is invalid;
- an approved required coefficient is missing;
- coefficient resolution is ambiguous;
- resolved coefficient content fails integrity validation.

A preflight rejection:

- updates the request to `PREFLIGHT_REJECTED`;
- writes `failure_code`, `failure_field`, and structured details;
- writes a request-level `AuditOutboxEvent` bound by `request_id`;
- creates no `OrchestrationIdentityRecord`;
- creates no `OrchestrationRunAttemptRecord`;
- creates no `CalculationRunRecord`;
- creates no `SourceBindingRecord`.

### 9.5 Execution BLOCKED classification

Only a failure after identity and RUNNING attempt creation may be represented as `attempt.status = BLOCKED`.

Execution blockers include:

- a calculator’s structured blocker;
- an upstream formal result that cannot satisfy the next stage’s typed input contract;
- an entered-DAG input mapping blocker;
- a production-capacity blocker raised after DAG execution begins.

BLOCKED and FAILED are different from preflight rejection. Both skip SchemeService and create no SourceBinding.

---

## 10. Persistence graph, foreign keys, nullability, and lifecycle

```text
OrchestrationRequestRecord
    ├── status=PREFLIGHT_REJECTED
    └── status=ACCEPTED
          │
          ├── project_version_id ───────────────> ProjectVersionRecord.id
          │
          ▼
ProjectVersionExecutionSnapshot
          │ project_version_id FK NOT NULL
          ▼
CoefficientContextRecord
          │ project_version_id FK NOT NULL
          ▼
OrchestrationIdentityRecord
          │ execution_snapshot_id FK NOT NULL
          │ coefficient_context_id FK NOT NULL
          │ 1:N
          ▼
OrchestrationRunAttemptRecord
          │ identity_id FK NOT NULL
          │ 1:N
          ▼
CalculationRunRecord x 5
          │ identity_id / attempt_id / snapshot_id / context_id FK NOT NULL
          ▼ COMPLETED only
SourceBindingRecord
          │ identity_id / attempt_id / five calculation IDs FK NOT NULL
          ▼
SchemeRun
          │ production: source_binding_id + source contract + weight revision NOT NULL
          ▼
SchemeSourceArchiveV1
```

Audit chain:

```text
Request / Identity / Attempt / Calculation / Binding
          │ same state transaction
          ▼
AuditOutboxEvent
          │ at-least-once delivery
          ▼
AuditOutboxDispatcher
          │ idempotent materialization
          ▼
AuditEventRecord(outbox_event_id UNIQUE NOT NULL)
```

### 10.1 Immutable persisted fields

- identity fingerprint;
- identity execution snapshot ID;
- identity coefficient context ID;
- identity definition/version fields;
- attempt identity ID;
- attempt number;
- calculation ownership IDs and hashes;
- SourceBinding five slot IDs and hashes.

### 10.2 Mutable persisted lifecycle fields

- request status/failure/completed time;
- identity authoritative completed attempt ID;
- attempt status;
- attempt heartbeat;
- attempt completed time;
- attempt source binding ID;
- attempt failure code/details;
- outbox claim/retry/publication fields.

Domain commands, results, snapshots, diagnostics, and archive DTOs are frozen dataclasses. Persisted lifecycle entities/ORM records are mutable only in the fields explicitly listed above.

---

## 11. Identity, attempt, and concurrency contracts

### 11.1 Identity

`OrchestrationIdentityRecord` has `UNIQUE(fingerprint)` and immutable references to the authoritative execution snapshot and coefficient context.

### 11.2 Attempts

`OrchestrationRunAttemptRecord` has:

```sql
UNIQUE (identity_id, attempt_number)
```

and exactly one RUNNING attempt is enforced on both PostgreSQL and SQLite:

```sql
CREATE UNIQUE INDEX uq_orchestration_attempt_one_running
ON orchestration_run_attempts(identity_id)
WHERE status = 'RUNNING';
```

### 11.3 Attempt states

```text
RUNNING -> COMPLETED
RUNNING -> BLOCKED
RUNNING -> FAILED
RUNNING -> ABANDONED
```

A completed attempt is authoritative only after all five calculation rows, SourceBinding, terminal attempt state, identity authoritative pointer, and their audit outbox rows commit atomically.

### 11.4 Atomic stale takeover

The takeover worker first reads the RUNNING attempt’s `id`, `status`, and `heartbeat_at`. After confirming the lease is expired, it performs:

```sql
UPDATE orchestration_run_attempts
SET status = 'ABANDONED', completed_at = :now
WHERE id = :id
  AND status = 'RUNNING'
  AND heartbeat_at = :observed_heartbeat;
```

Rules:

1. `affected_rows == 1` is required before creating the next attempt.
2. The next attempt uses `attempt_number + 1`.
3. `affected_rows == 0` means the state or heartbeat changed; reload current state and do not create an attempt.
4. Attempt-number insertion races are resolved by the unique constraint and bounded retry.
5. The one-RUNNING partial index is the final database guard.

### 11.5 Same-fingerprint behavior

- authoritative COMPLETED -> return existing result, no new artifacts or attempt;
- RUNNING with valid lease -> return typed in-progress/conflict result;
- RUNNING with expired lease -> CAS takeover;
- FAILED -> a new attempt may be created under explicit retry policy;
- BLOCKED -> retry only when the caller explicitly requests re-evaluation and preconditions may have changed; otherwise return the prior blocked result;
- changed calculator, mapping, snapshot, or coefficient version -> changed fingerprint and new identity.

---

## 12. Transaction model and rollback semantics

`OrchestrationService` receives a UnitOfWork factory, not an externally managed SQLAlchemy session. Repositories accept a session and never commit, roll back, close, or create sessions.

### 12.1 Transaction A — request, preparation, identity, and lease

Transaction A:

1. creates `OrchestrationRequestRecord(PENDING)`;
2. performs authoritative ProjectVersion lookup and all preflight validation;
3. on rejection, writes request failure + request-level outbox and commits;
4. on acceptance, computes candidates and hashes in memory;
5. checks completed idempotency before materializing artifacts;
6. get-or-creates snapshot, context, and identity when needed;
7. acquires or creates one RUNNING attempt;
8. marks the request ACCEPTED and writes request/attempt audit outbox rows;
9. commits.

### 12.2 Transaction B — all-or-nothing five-stage execution

Transaction B executes the five calculators, adapts results, and stages persistence. It commits only when all of the following are valid:

- all five stages passed;
- five `CalculationRunRecord` rows are valid;
- all five result hashes verify;
- SourceBinding strict validation passes;
- SourceBinding is inserted;
- attempt becomes COMPLETED and points to the binding;
- identity authoritative completed attempt is set;
- all state-linked outbox rows are inserted.

Any blocker, structured failure, persistence error, or integrity failure rolls back all Transaction B changes.

### 12.3 Transaction C — terminal status after Transaction B rollback

After a Transaction B rollback, a fresh UnitOfWork updates the existing attempt to BLOCKED or FAILED and writes the corresponding attempt-level outbox event. No calculation row or SourceBinding from the failed execution remains.

---

## 13. Five-stage DAG and source snapshot hash contract

### 13.1 Exact DAG

```text
zone -> cooling_load -> equipment -> power -> investment
```

No stage may silently synthesize missing upstream data or use zero/default fallback where the formal mapping requires a value.

### 13.2 Supported calculator registry for schema V1

| Binding type | `calculation_type` | supported `calculator_name` |
|---|---|---|
| zone | `zone` | `cold_room_zone_plan` |
| cooling load | `cooling_load` | `cooling_load` |
| equipment | `equipment` | `equipment` |
| power | `power` | `installed_power` |
| investment | `investment` | `investment_estimate` |

`calculation_type = "investment"` is the orchestration/source-binding business type identifier.  `calculator_name = "investment_estimate"` is the specific calculator implementation.  The two names differ intentionally: `calculation_type` is the stable semantic category; `calculator_name` allows multiple implementations to register for the same type in future schema versions.

A future calculator name requires a reviewed registry/schema-version change; it is not accepted through loose string matching.

### 13.3 Content/envelope split

```python
@dataclass(frozen=True, slots=True)
class SourceSnapshotContentV1:
    schema_version: str
    calculation_type: str
    calculator_name: str
    calculator_version: str
    project_id: str
    project_version_id: str
    execution_snapshot_id: str
    coefficient_context_id: str
    orchestration_identity_id: str
    orchestration_run_attempt_id: str
    input_hash: str
    requires_review: bool
    payload: Mapping[str, object]
    provenance: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class SourceSnapshotEnvelopeV1:
    content: SourceSnapshotContentV1
    result_hash: str
```

```python
result_hash = SHA-256(canonical_json(SourceSnapshotContentV1))
```

The same exact `result_hash` value is stored in `CalculationRunRecord`, copied into the binding's per-calculation hash map, and recomputed by SchemeService. No alternate payload-only or envelope hash is permitted.

`result_hash` is **execution-bound**: `SourceSnapshotContentV1` contains `provenance` (execution identity, upstream calculation IDs, coefficient context identity — see §13.5.7), `requires_review`, and `payload`.  Identical business payloads from different runs produce different `result_hash` values.  This is the sole frozen hash identity model — there is no separate "business-output-only hash" or "payload hash".

### 13.4 Semantic boundaries

- Equipment may expose `compressor_input_power_kw_e`; it must never label that value as total installed power.
- Power owns `total_installed_power_kw_e`, including the formal auxiliary/processing/lighting inputs defined by the Power adapter.
- SchemeService installed-power mapping reads only the Power snapshot.
- Investment consumes the formal Power output and other declared upstream values.
- `requires_review` is propagated from calculator results and only explicitly approved warning classes may promote review; not every warning automatically promotes review.

### 13.5 Adapter field-bridge contracts and per-type payload schemas

Every adapter maps a real calculator's `CalculationResult.result` dict to
`SourceSnapshotContentV1.payload`.  All adapters use an explicit **allowlist**:
unknown calculator output fields are ignored and do not enter the hashed payload.

#### 13.5.0 Universal adapter rules

| Rule | Detail |
|---|---|
| Field policy | Explicit allowlist — only listed fields enter payload |
| Unknown top-level fields | Ignored; do NOT enter payload; no schema version change needed |
| Unknown nested keys | Ignored within allowed objects — adapter constructs a new canonical object from allowlisted source paths; it never hashes the original dict directly |
| Missing required allowed key | Fail closed — adapter MUST NOT fabricate zero, null, or empty defaults |
| Duplicate semantic key | After normalization (e.g., duplicate `zone_code`), fail closed |
| Excluded fields | Must be documented per adapter with exclusion rationale |
| Schema evolution | Adding/removing/renaming a payload field, or changing its unit → new `snapshot_schema_version` |
| Canonical JSON | Sorted by key from table top-to-bottom; arrays sorted by declared sort key |
| Numeric | Decimal string; no binary floats; NaN/Infinity rejected |
| Nullability | NOT NULL unless marked nullable; nullable field absent from calculator output → written as `null` |
| Source path | Written as `CalculationResult.result["key"]` or `result["key"][].subkey` |
| Derived fields | Tagged `derived` with exact formula; verifier recomputes from source fields |
| Database IDs | Prohibited in business payload — belong in `SourceBindingRecord` or `provenance` |
| Nested object projection | Adapter constructs new canonical object from allowlisted paths — never passes through raw calculator dict directly |

#### 13.5.1 ZoneSourceSnapshot payload

Source: `CalculationResult.result` from `ColdRoomZonePlanner.plan()`
(`calculation_type = "zone"`, `calculator_name = "cold_room_zone_plan"`)

| # | Payload key | Source path | Classification | Type | Unit | Nullable | Sort key |
|---|---|---|---|---|---|---|---|
| 1 | `daily_inbound_mass_kg` | `result["daily_inbound_mass_kg"]` | direct | Decimal | kg/day | No | — |
| 2 | `design_daily_mass_kg` | `result["design_daily_mass_kg"]` | direct | Decimal | kg/day | No | — |
| 3 | `total_required_area_m2` | `result["total_required_area_m2"]` | direct | Decimal | m² | No | — |
| 4 | `total_area_m2` | `result["total_area_m2"]` | direct | Decimal | m² | No | — |
| 5 | `planning_parameters` | `result["planning_parameters"]` | direct | object | — | No | — |
| 5.01 | `planning_parameters.raw_storage_ratio` | `result["planning_parameters"]["raw_storage_ratio"]` | direct | Decimal | — | No | — |
| 5.02 | `planning_parameters.finished_storage_days` | `result["planning_parameters"]["finished_storage_days"]` | direct | Decimal | days | No | — |
| 5.03 | `planning_parameters.main_packaging_storage_days` | `result["planning_parameters"]["main_packaging_storage_days"]` | direct | Decimal | days | No | — |
| 5.04 | `planning_parameters.auxiliary_packaging_storage_days` | `result["planning_parameters"]["auxiliary_packaging_storage_days"]` | direct | Decimal | days | No | — |
| 5.05 | `planning_parameters.primary_precooling_pallet_weight_kg` | `result["planning_parameters"]["primary_precooling_pallet_weight_kg"]` | direct | Decimal | kg | No | — |
| 5.06 | `planning_parameters.primary_precooling_hours_per_pallet` | `result["planning_parameters"]["primary_precooling_hours_per_pallet"]` | direct | Decimal | h | No | — |
| 5.07 | `planning_parameters.primary_precooling_working_hours_per_day` | `result["planning_parameters"]["primary_precooling_working_hours_per_day"]` | direct | Decimal | h/day | No | — |
| 5.08 | `planning_parameters.secondary_precooling_pallet_weight_kg` | `result["planning_parameters"]["secondary_precooling_pallet_weight_kg"]` | direct | Decimal | kg | No | — |
| 5.09 | `planning_parameters.secondary_precooling_hours_per_pallet` | `result["planning_parameters"]["secondary_precooling_hours_per_pallet"]` | direct | Decimal | h | No | — |
| 5.10 | `planning_parameters.secondary_precooling_working_hours_per_day` | `result["planning_parameters"]["secondary_precooling_working_hours_per_day"]` | direct | Decimal | h/day | No | — |
| 5.11 | `planning_parameters.pallet_base_area_m2` | `result["planning_parameters"]["pallet_base_area_m2"]` | direct | Decimal | m² | No | — |
| 5.12 | `planning_parameters.storage_area_factor` | `result["planning_parameters"]["storage_area_factor"]` | direct | Decimal | — | No | — |
| 5.13 | `planning_parameters.precooling_position_area_m2` | `result["planning_parameters"]["precooling_position_area_m2"]` | direct | Decimal | m² | No | — |
| 5.14 | `planning_parameters.packing_area_factor` | `result["planning_parameters"]["packing_area_factor"]` | direct | Decimal | — | No | — |
| 5.15 | `planning_parameters.packaging_area_factor` | `result["planning_parameters"]["packaging_area_factor"]` | direct | Decimal | — | No | — |
| 5.16 | `planning_parameters.frozen_fruit_ratio` | `result["planning_parameters"]["frozen_fruit_ratio"]` | direct | Decimal | — | No | — |
| 5.17 | `planning_parameters.frozen_storage_days` | `result["planning_parameters"]["frozen_storage_days"]` | direct | Decimal | days | No | — |
| 6 | `zones` | `result["zones"]` | direct | list[dict] | — | No | `zone_code` ASC |
| 6.1 | `zones[].zone_code` | `zone["zone_code"]` | direct | str | — | No | — |
| 6.2 | `zones[].zone_name` | `zone["zone_name"]` | direct | str | — | No | — |
| 6.3 | `zones[].temperature_band` | `zone["temperature_band"]` | direct | str | — | No | — |
| 6.4 | `zones[].function` | `zone["function"]` | direct | str | — | No | — |
| 6.5 | `zones[].daily_throughput_kg_day` | `zone["daily_throughput_kg_day"]` | direct | Decimal | kg/day | No | — |
| 6.6 | `zones[].design_storage_mass_kg` | `zone["design_storage_mass_kg"]` | direct | Decimal | kg | No | — |
| 6.7 | `zones[].position_count` | `zone["position_count"]` | direct | int | — | No | — |
| 6.8 | `zones[].required_area_m2` | `zone["required_area_m2"]` | direct | Decimal | m² | No | — |
| 6.9 | `zones[].requires_review` | `zone["requires_review"]` | direct | bool | — | No | — |
| 6.a | `zones[].pallet_weight_kg` | `zone["pallet_weight_kg"]` | direct | Decimal | kg | **Yes** | — |
| 6.b | `zones[].hours_per_pallet` | `zone["hours_per_pallet"]` | direct | Decimal | h | **Yes** | — |
| 6.c | `zones[].working_hours_per_day` | `zone["working_hours_per_day"]` | direct | Decimal | h/day | **Yes** | — |
| 6.d | `zones[].position_hourly_capacity_kg_h` | `zone["position_hourly_capacity_kg_h"]` | direct | Decimal | kg/h | **Yes** | — |
| 6.e | `zones[].position_daily_capacity_kg_day` | `zone["position_daily_capacity_kg_day"]` | direct | Decimal | kg/day | **Yes** | — |
| 6.f | `zones[].raw_position_count` | `zone["raw_position_count"]` | direct | int | — | **Yes** | — |
| 6.g | `zones[].area_basis` | `zone["area_basis"]` | direct | object | — | Yes (nullable if no coefficient) | — |
| 6.g1 | `zones[].area_basis.code` | `zone["area_basis"]["code"]` | direct | str | — | No | — |
| 6.g2 | `zones[].area_basis.name` | `zone["area_basis"]["name"]` | direct | str | — | No | — |
| 6.g3 | `zones[].area_basis.value` | `zone["area_basis"]["value"]` | direct | Decimal | varies | No | — |
| 6.g4 | `zones[].area_basis.unit` | `zone["area_basis"]["unit"]` | direct | str | — | No | — |
| 6.g5 | `zones[].area_basis.category` | `zone["area_basis"]["category"]` | direct | str | — | No | — |
| 6.g6 | `zones[].area_basis.source_type` | `zone["area_basis"]["source_type"]` | direct | str | — | No | — |
| 6.g7 | `zones[].area_basis.source_reference` | `zone["area_basis"]["source_reference"]` | direct | str | — | No | — |
| 6.g8 | `zones[].area_basis.version` | `zone["area_basis"]["version"]` | direct | str | — | No | — |
| 6.g9 | `zones[].area_basis.validity_status` | `zone["area_basis"]["validity_status"]` | direct | str | — | No | — |
| 6.g10 | `zones[].area_basis.approval_status` | `zone["area_basis"]["approval_status"]` | direct | str | — | No | — |
| 6.g11 | `zones[].area_basis.requires_review` | `zone["area_basis"]["requires_review"]` | direct | bool | — | No | — |
| 6.g12 | `zones[].area_basis.notes` | `zone["area_basis"]["notes"]` | direct | str | — | No | — |
| 6.h | `zones[].worker_count` | `zone["worker_count"]` | direct | int | — | **Yes** | — |
| 6.i | `zones[].table_count` | `zone["table_count"]` | direct | int | — | **Yes** | — |
| 6.j | `zones[].person_daily_capacity_kg_day` | `zone["person_daily_capacity_kg_day"]` | direct | Decimal | kg/day | **Yes** | — |
| 6.k | `zones[].packing_table_area_m2` | `zone["packing_table_area_m2"]` | direct | Decimal | m² | **Yes** | — |

Zone zones use a **unified field set** with nullable optional fields.
Zones are sorted by `zone_code` ASC before canonical JSON serialization.
Duplicate `zone_code` within the same zone list → adapter fails closed.

#### 13.5.2 CoolingLoadSourceSnapshot payload

Source: `CalculationResult.result` from `calculate_cooling_load()`
(`calculation_type = "cooling_load"`, `calculator_name = "cooling_load"`)

| # | Payload key | Source path | Classification | Type | Unit | Nullable | Sort key |
|---|---|---|---|---|---|---|---|
| 1 | `zones` | `result["zones"]` | direct | list[dict] | — | No | `zone_code` ASC |
| 1.1 | `zones[].zone_code` | `zone["zone_code"]` | direct | str | — | No | — |
| 1.2 | `zones[].zone_name` | `zone["zone_name"]` | direct | str | — | No | — |
| 1.3 | `zones[].temperature_level` | `zone["temperature_level"]` | direct | str | — | No | — |
| 1.4 | `zones[].transmission_load_kw_r` | `zone["transmission_load_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 1.5 | `zones[].wall_transmission_load_kw_r` | `zone["wall_transmission_load_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 1.6 | `zones[].roof_transmission_load_kw_r` | `zone["roof_transmission_load_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 1.7 | `zones[].floor_transmission_load_kw_r` | `zone["floor_transmission_load_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 1.8 | `zones[].product_load_kw_r` | `zone["product_load_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 1.9 | `zones[].infiltration_load_kw_r` | `zone["infiltration_load_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 1.10 | `zones[].sensible_infiltration_load_kw_r` | `zone["sensible_infiltration_load_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 1.11 | `zones[].latent_infiltration_load_kw_r` | `zone["latent_infiltration_load_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 1.12 | `zones[].internal_load_kw_r` | `zone["internal_load_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 1.13 | `zones[].people_load_kw_r` | `zone["people_load_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 1.14 | `zones[].lighting_load_kw_r` | `zone["lighting_load_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 1.15 | `zones[].internal_equipment_load_kw_r` | `zone["internal_equipment_load_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 1.16 | `zones[].evaporator_fan_load_kw_r` | `zone["evaporator_fan_load_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 1.17 | `zones[].defrost_load_kw_r` | `zone["defrost_load_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 1.18 | `zones[].subtotal_load_kw_r` | `zone["subtotal_load_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 2 | `temperature_levels` | `result["temperature_levels"]` | direct | list[dict] | — | No | `temperature_level_code` ASC |
| 2.1 | `temperature_levels[].temperature_level_code` | `result["temperature_levels"][]["temperature_level_code"]` | direct | str | — | No | — |
| 2.2 | `temperature_levels[].room_count` | `result["temperature_levels"][]["room_count"]` | direct | int | — | No | — |
| 2.3 | `temperature_levels[].subtotal_load_kw_r` | `result["temperature_levels"][]["subtotal_load_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 2.4 | `temperature_levels[].diversified_load_kw_r` | `result["temperature_levels"][]["diversified_load_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 2.5 | `temperature_levels[].zones` | `result["temperature_levels"][]["zones"]` | direct | list[str] | — | No | sorted by `zone_code` ASC |
| 3 | `total_subtotal_load_kw_r` | `result["total_subtotal_load_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 4 | `diversity_factor` | `result["diversity_factor"]` | direct | str | — | No | — |
| 5 | `total_diversified_load_kw_r` | `result["total_diversified_load_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 6 | `design_margin_ratio` | `result["design_margin_ratio"]` | direct | str | — | No | — |
| 7 | `design_margin_kw_r` | `result["design_margin_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 8 | `design_refrigeration_load_kw_r` | `result["design_refrigeration_load_kw_r"]` | direct | Decimal | kW(r) | No | — |

`requires_review` is a top-level field of `SourceSnapshotContentV1` (outside the business `payload` but inside the hashed content — see §13.3).  `warnings` are NOT automatically copied into `payload`; only explicitly frozen warning fields that the adapter elects to include enter the hashed content.

Duplicate `zone_code` within cooling-load `zones` → adapter fails closed.
Duplicate `temperature_level_code` within `temperature_levels` → adapter fails closed.

#### 13.5.3 EquipmentSourceSnapshot payload

Source: `CalculationResult.result` from equipment calculator
(`calculation_type = "equipment"`, `calculator_name = "equipment"`)

**EXCLUDED:** No fields excluded from payload — however the field `total_compressor_input_power_kw_e` in the calculator result is **compressor input power only**, NOT whole-facility installed power. SchemeService MUST NOT use this slot for `installed_power_kw_e`.

| # | Payload key | Source path | Classification | Type | Unit | Nullable | Sort key |
|---|---|---|---|---|---|---|---|
| 1 | `systems` | `result["systems"]` | direct | list[dict] | — | No | `system_code` ASC |
| 1.1 | `systems[].system_code` | `system["system_code"]` | direct | str | — | No | — |
| 1.2 | `systems[].system_name` | `system["system_name"]` | direct | str | — | No | — |
| 1.3 | `systems[].design_evaporating_temperature_c` | `system["design_evaporating_temperature_c"]` | direct | str | °C | No | — |
| 1.4 | `systems[].zones` | `system["zones"]` | direct | list[dict] | — | No | `zone_code` ASC |
| 1.4a | `systems[].zones[].zone_code` | `system["zones"][]["zone_code"]` | direct | str | — | No | — |
| 1.4b | `systems[].zones[].zone_name` | `system["zones"][]["zone_name"]` | direct | str | — | No | — |
| 1.4c | `systems[].zones[].design_cooling_load_kw_r` | `system["zones"][]["design_cooling_load_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 1.4d | `systems[].zones[].evaporator_count` | `system["zones"][]["evaporator_count"]` | direct | int | — | No | — |
| 1.4e | `systems[].zones[].defrost_method` | `system["zones"][]["defrost_method"]` | direct | str | — | No | — |
| 1.5 | `systems[].system_simultaneous_load_kw_r` | `system["system_simultaneous_load_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 1.6 | `systems[].evaporator_total_capacity_kw_r` | `system["evaporator_total_capacity_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 1.7 | `systems[].evaporator_count` | `system["evaporator_count"]` | direct | int | — | No | — |
| 1.8 | `systems[].single_evaporator_capacity_kw_r` | `system["single_evaporator_capacity_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 1.9 | `systems[].compressor_operating_capacity_kw_r` | `system["compressor_operating_capacity_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 1.10 | `systems[].compressor_installed_capacity_kw_r` | `system["compressor_installed_capacity_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 1.11 | `systems[].compressor_standby_capacity_kw_r` | `system["compressor_standby_capacity_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 1.12 | `systems[].compressor_input_power_kw_e` | `system["compressor_input_power_kw_e"]` | direct | Decimal | kW(e) | No | — |
| 1.13 | `systems[].condenser_heat_rejection_kw` | `system["condenser_heat_rejection_kw"]` | direct | Decimal | kW | No | — |
| 1.14 | `systems[].defrost_methods` | `system["defrost_methods"]` | direct | list[str] | — | No | lexicographic ASC |
| 2 | `total_design_load_kw_r` | `result["total_design_load_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 3 | `total_compressor_capacity_kw_r` | `result["total_compressor_capacity_kw_r"]` | direct | Decimal | kW(r) | No | — |
| 4 | `total_compressor_input_power_kw_e` | `result["total_compressor_input_power_kw_e"]` | direct | Decimal | kW(e) | No | — |
| 5 | `total_condenser_rejection_kw` | `result["total_condenser_rejection_kw"]` | direct | Decimal | kW | No | — |

⚠️ `total_compressor_input_power_kw_e` is compressor input power — NOT facility installed power.

Duplicate `system_code` within `systems` → adapter fails closed.
Duplicate `zone_code` within a system's `zones` → adapter fails closed.
Duplicate `defrost_method` value within `defrost_methods` list → canonical deduplicate (set semantics, sorted lexicographic ASC); conflicting duplicates from malformed input fail closed.

#### 13.5.4 PowerSourceSnapshot payload

Source: `CalculationResult.result` from `calculate_installed_power()`
(`calculation_type = "power"`, `calculator_name = "installed_power"`)

| # | Payload key | Source path | Classification | Type | Unit | Nullable | Sort key |
|---|---|---|---|---|---|---|---|
| 1 | `refrigeration_system_installed_power_kw_e` | `result["refrigeration_system_installed_power_kw_e"]` | direct | Decimal | kW(e) | No | — |
| 2 | `process_equipment_installed_power_kw_e` | `result["process_equipment_installed_power_kw_e"]` | direct | Decimal | kW(e) | No | — |
| 3 | `lighting_installed_power_kw_e` | `result["lighting_installed_power_kw_e"]` | direct | Decimal | kW(e) | No | — |
| 4 | `auxiliary_installed_power_kw_e` | `result["auxiliary_installed_power_kw_e"]` | direct | Decimal | kW(e) | No | — |
| 5 | `total_installed_power_kw_e` | `result["total_installed_power_kw_e"]` | direct | Decimal | kW(e) | No | — |
| 6 | `estimated_peak_demand_kw_e` | `result["estimated_peak_demand_kw_e"]` | direct | Decimal | kW(e) | No | — |
| 7 | `equipment_items` | `result["equipment_items"]` | direct | list[dict] | — | Yes | `(category, name, quantity, unit_power_kw_e, demand_factor)` ASC |
| 7.1 | `equipment_items[].name` | `result["equipment_items"][]["name"]` | direct | str | — | No | — |
| 7.2 | `equipment_items[].category` | `result["equipment_items"][]["category"]` | direct | str | — | No | — |
| 7.3 | `equipment_items[].quantity` | `result["equipment_items"][]["quantity"]` | direct | int | — | No | — |
| 7.4 | `equipment_items[].unit_power_kw_e` | `result["equipment_items"][]["unit_power_kw_e"]` | direct | Decimal | kW(e) | No | — |
| 7.5 | `equipment_items[].total_power_kw_e` | `result["equipment_items"][]["total_power_kw_e"]` | direct | Decimal | kW(e) | No | — |
| 7.6 | `equipment_items[].demand_factor` | `result["equipment_items"][]["demand_factor"]` | direct | Decimal | — | No | — |
| 7.7 | `equipment_items[].demand_power_kw_e` | `result["equipment_items"][]["demand_power_kw_e"]` | direct | Decimal | kW(e) | No | — |

Power adapter MUST INCLUDE `total_installed_power_kw_e`.  SchemeService installed-power reads ONLY the Power slot.  Power slot missing → fail closed.  Equipment slot MUST NOT serve as fallback.

Duplicate `(category, name, quantity, unit_power_kw_e, demand_factor)` composite key within `equipment_items` → adapter fails closed.

#### 13.5.5 InvestmentSourceSnapshot payload

Source: `CalculationResult.result` from `InvestmentEstimator.estimate()`
(`calculation_type = "investment"`, `calculator_name = "investment_estimate"`)

| # | Payload key | Source path | Classification | Type | Unit | Nullable | Sort key |
|---|---|---|---|---|---|---|---|
| 1 | `total_investment_cny` | `result["total_investment_cny"]` | direct | Decimal | CNY | No | — |
| 2 | `items` | `result["items"]` | direct | list[dict] | — | No | `item_name` ASC |
| 2.1 | `items[].item_name` | `result["items"][]["item_name"]` | direct | str | — | No | — |
| 2.2 | `items[].amount_cny` | `result["items"][]["amount_cny"]` | direct | Decimal | CNY | No | — |

Duplicate `item_name` within the same items list → adapter fails closed.
Unknown nested key in an item → ignored (per universal policy §13.5.0).

Upstream calculation IDs (power, zone) are provenance metadata — NOT in business payload.
They belong in `SourceBindingRecord` or `SourceSnapshotContentV1.provenance`, not `payload`.

#### 13.5.6 Golden mapping examples

For each adapter, given a fixed `CalculationResult.result` input, the adapter
MUST produce a deterministic `payload`.  Two independent implementations given
identical input MUST produce identical `SourceSnapshotContentV1` and `result_hash`.

**Required golden scenarios:**

1. Zone zones in original order `[B, A, C]` → payload zones sorted `[A, B, C]` → same hash as `[A, C, B]`.
2. CoolingLoad temperature_levels in different order → sorted by `temperature_level_code` → same hash.
3. Equipment systems in different order → sorted by `system_code` → same hash.
4. Power equipment_items in different order → sorted by composite key → same hash.
5. Investment items in different order → sorted by `item_name` → same hash.
6. Adding a new unknown field to calculator `result` → payload unchanged → same hash.
7. CalculationRunRecord database ID changes → business payload unchanged → provenance changes (upstream calculation IDs differ) → complete SourceSnapshotContentV1 changes → result_hash changes.
8. Calculator output dictionary key order changes, but normalized payload and provenance remain identical → complete SourceSnapshotContentV1 identical → result_hash identical.
9. Same business payload + same provenance (same upstream calculation IDs, same execution identity) → same SourceSnapshotContentV1 → same result_hash.

Canonical hash inputs (complete SourceSnapshotContentV1 objects) are frozen as part of implementation tests.
Implementation tests MUST lock specific expected SHA-256 values.

#### 13.5.7 Provenance contract

The following are **NOT** business payload fields — they belong in `SourceSnapshotContentV1.provenance`:

```python
@dataclass(frozen=True, slots=True)
class SourceSnapshotProvenanceV1:
    execution_snapshot_id: str
    coefficient_context_id: str
    orchestration_identity_id: str
    orchestration_run_attempt_id: str
    upstream_calculation_ids: dict[str, str | None]
```

`upstream_calculation_ids` is an explicit fixed-key mapping.  Each stage may only include
its real upstream dependencies:

| Stage       | Expected `upstream_calculation_ids` keys                  |
|-------------|-----------------------------------------------------------|
| zone        | `{}` (no upstream calculation ID)                         |
| cooling_load| `{"zone": str}` (one upstream calculation ID)             |
| equipment   | `{"cooling_load": str}` (one upstream calculation ID)     |
| power       | `{"equipment": str}` (one upstream calculation ID)        |
| investment  | `{"zone": str, "power": str}` (two upstream calculation IDs) |

Rules:

- The exact key set is frozen per stage.  Unknown provenance keys MUST be rejected.
- A `None` value means the upstream is not applicable for that stage (used for
  stages like `zone` that have no upstream `CalculationRunRecord`).
- Canonical JSON serialization MUST include the fixed key set.
- Adding, removing, or renaming a provenance key requires a schema version increment.

`provenance` enters `SourceSnapshotContentV1` and therefore participates in `result_hash`.
This means `result_hash` is **execution-bound**: it depends on the complete
`SourceSnapshotContentV1`, including execution identity, upstream calculation IDs,
and coefficient context identity.  Two orchestration runs that produce identical
business payloads will have different `result_hash` values whenever:

- upstream calculation IDs differ;
- the execution snapshot or coefficient context is different;
- the orchestration identity or attempt ID differs.

This is intentional: a) tamper detection requires binding to specific upstream
records; b) the hash represents a complete execution provenance, not merely a
business-output fingerprint.

### 13.6 Semantic boundaries (reaffirmed)

- Equipment may expose `compressor_input_power_kw_e`; it must never label that value as total installed power.
- Power owns `total_installed_power_kw_e`, including the formal auxiliary/processing/lighting inputs defined by the Power adapter.
- SchemeService installed-power mapping reads only the Power snapshot.
- Investment consumes the formal Power output and other declared upstream values.
- `requires_review` is propagated from calculator results and only explicitly approved warning classes may promote review; not every warning automatically promotes review.

---

## 14. Rollback-safe result contracts

### 14.1 Execution diagnostics

```python
@dataclass(frozen=True, slots=True)
class StageExecutionDiagnostic:
    calculator_name: str
    execution_status: str       # passed | blocked | failed | skipped
    requires_review: bool
    input_hash: str | None
    result_hash: str | None
    blocker: StructuredBlocker | None
    error: StructuredError | None
```

Diagnostics describe in-memory execution. They contain no `calculation_run_id` and make no persistence claim.

### 14.2 Persisted stage results

```python
@dataclass(frozen=True, slots=True)
class StagePersistedResult:
    calculator_name: str
    calculation_run_id: str
    input_hash: str
    result_hash: str
    calculator_version: str
    snapshot_schema_version: str
```

A `StagePersistedResult` is constructed only after the COMPLETED Transaction B commit succeeds.

### 14.3 OrchestrationResult

```python
@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    request_id: str
    identity_id: str | None
    attempt_id: str | None
    attempt_number: int | None
    status: str                 # PREFLIGHT_REJECTED | COMPLETED | BLOCKED | FAILED | IN_PROGRESS
    requires_review: bool
    persisted_stages: tuple[StagePersistedResult, ...]
    diagnostics: tuple[StageExecutionDiagnostic, ...]
    source_binding_id: str | None
    fingerprint: str | None
    started_at: datetime
    completed_at: datetime | None
```

Rules:

- COMPLETED: exactly five persisted stages and non-null SourceBinding ID;
- BLOCKED/FAILED: persisted stages empty, SourceBinding ID null, diagnostics allowed;
- PREFLIGHT_REJECTED: identity/attempt/fingerprint null and persisted stages empty;
- IN_PROGRESS: existing identity/attempt returned without creating a second RUNNING attempt.

Example rollback requirement:

```text
zone passed
cooling_load passed
equipment blocked
-> Transaction B rolls back
-> no CalculationRunRecord from this attempt exists
-> persisted_stages == ()
-> diagnostics contain zone/cooling_load passed and equipment blocked
-> no SourceBinding exists
```

---

## 15. CalculationRunRecord integrity

New orchestration columns must obey an all-null legacy versus all-required orchestrated CHECK:

```sql
CHECK (
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

Legacy rows remain explicitly unbound/unversioned and are rejected by the production SourceBinding/SchemeService path. `CalculationRunRecord` has no `source_binding_id` column.

---

## 16. SourceBinding persistence and strict verification

### 16.1 SourceBindingRecord

Required fields include:

- ID;
- project ID and project version ID;
- execution snapshot ID;
- orchestration identity ID and attempt ID;
- orchestration fingerprint;
- five calculation IDs;
- exact five-key per-calculation result-hash mapping;
- combined source hash;
- binding schema version;
- created timestamp.

Unique/index rules:

```sql
UNIQUE (orchestration_identity_id, orchestration_run_attempt_id)
INDEX (zone_calculation_id)
INDEX (cooling_load_calculation_id)
INDEX (equipment_calculation_id)
INDEX (power_calculation_id)
INDEX (investment_calculation_id)
```

Each calculation ID is a foreign key to `CalculationRunRecord.id`. The identity and attempt IDs are non-null foreign keys. SourceBinding is inserted only inside the COMPLETED transaction.

### 16.2 Exact slot mapping

| SourceBinding slot | required `calculation_type` | supported calculator |
|---|---|---|
| `zone_calculation_id` | `zone` | `cold_room_zone_plan` |
| `cooling_load_calculation_id` | `cooling_load` | `cooling_load` |
| `equipment_calculation_id` | `equipment` | `equipment` |
| `power_calculation_id` | `power` | `installed_power` |
| `investment_calculation_id` | `investment` | `investment_estimate` |

### 16.3 SchemeService verification

For every slot, SchemeService must verify all of the following before reading business payload fields:

1. record exists;
2. `record.id` equals the binding slot ID;
3. `record.project_id == binding.project_id`;
4. `record.project_version_id == binding.project_version_id`;
5. `record.execution_snapshot_id == binding.execution_snapshot_id`;
6. `record.orchestration_identity_id == binding.orchestration_identity_id`;
7. `record.orchestration_run_attempt_id == binding.orchestration_run_attempt_id`;
8. identity exists and `record.coefficient_context_id == identity.coefficient_context_id`;
9. `record.calculation_type` equals the slot’s required type;
10. `record.calculator_name` belongs to the supported registry for that type/schema;
11. `record.schema_version` is supported;
12. `record.result_hash` equals the binding’s hash for that exact type;
13. recomputed content hash equals `record.result_hash`;
14. `record.requires_review` equals the snapshot content value;
15. the binding hash map has exactly the five allowed keys and no extras;
16. the binding belongs to the identity’s authoritative COMPLETED attempt.

Any mismatch fails closed. No “latest row”, timestamp-based fallback, type coercion, or lenient calculator-name matching is allowed.

### 16.4 Sole combined source hash formula

```python
combined_source_hash = SHA-256(
    canonical_json({
        "zone": zone_result_hash,
        "cooling_load": cooling_load_result_hash,
        "equipment": equipment_result_hash,
        "power": power_result_hash,
        "investment": investment_result_hash,
    })
)
```

Each value is the corresponding `CalculationRunRecord.result_hash`, which is the hash of complete `SourceSnapshotContentV1` (including provenance — see §13.3 and §13.5.7).  Because each `result_hash` is execution-bound, the `combined_source_hash` is also execution-bound: two runs producing identical business payloads will have different combined hashes when their provenance differs.

The exact key set is mandatory. Payloads, envelopes, raw `CalculationResult` objects, file bytes, and database JSON strings are forbidden combined-hash inputs.

---

## 17. SchemeService — production/demo type separation and approved weight-set revision

### 17.0 Production and demo path separation

The current source file `schemes/application/service.py` line 67 defines:

```python
_REQUIRED_CALC_TYPES = frozenset({"zone", "investment", "cooling_load", "equipment"})
```

This four-type set is used by both `generate_scheme_run()` (production) and
`generate_demo_scheme_comparison()` (demo).  Issue #22 must separate them.

**Decision: Demo path uses five types with deterministic demo power seed.**

```python
DEMO_REQUIRED_CALC_TYPES = frozenset(
    {"zone", "investment", "cooling_load", "equipment", "power"}
)
```

The demo path requires exactly five calculation types.  When
`generate_demo_scheme_comparison()` is called, the demo seed data MUST include
a deterministic demo power record.  Missing power in demo → fail closed
(same as production).

**Invariants:**

| Path | Authoritative type set | Power required | SourceBinding required |
|---|---|---|---|
| Production (`source_binding_id`) | `PRODUCTION_SOURCE_SLOTS` (5) | Yes — fail closed | Yes |
| Demo (`generate_demo_scheme_comparison`) | `DEMO_REQUIRED_CALC_TYPES` (5) | Yes — demo power seed | No |

The same `_REQUIRED_CALC_TYPES` constant must not serve both paths.
Production must never silently fall back to demo data.
There is no "4 or 5", no "TBD", no "may retain four types".

Production path uses five SourceBinding slots as the authoritative set:

```python
PRODUCTION_SOURCE_SLOTS = (
    "zone",
    "cooling_load",
    "equipment",
    "power",
    "investment",
)
```

Production `generate_scheme_run()` with `source_binding_id`:
- does NOT consult `_REQUIRED_CALC_TYPES`;
- loads only records identified by the binding’s five calculation IDs;
- power slot missing → `SourceBindingSlotTypeError(cause="power slot record missing")`.

Legacy/demo path retains an independent constant:

```python
DEMO_REQUIRED_CALC_TYPES = frozenset({"zone", "investment", "cooling_load", "equipment", "power"})
```

When `generate_demo_scheme_comparison()` is called, the demo seed data MUST include
a deterministic demo Power record.  Missing power record → fail closed, same as production.
The demo path MUST NOT accept production SourceBinding records, and the production path
MUST NOT fall back to demo data.

### 17.1 Formal production contract

```python
def generate_scheme_run(
    self,
    *,
    project_id: str,
    version: int,
    source_binding_id: str,
    weight_set_revision_id: str,
    profile_codes: list[str],
    profile_parameters: Mapping[str, Mapping[str, object]],
) -> Mapping[str, object]:
    ...
```

The `version` argument is legacy-facing metadata only. SchemeService loads the SourceBinding and its ProjectVersion by ID and cross-checks `version`; it does not use `(project_id, version)` as the source identity.

### 17.2 Weight-set verification

1. load `SchemeWeightSetRevisionRecord` by `weight_set_revision_id`;
2. verify `status == "approved"`;
3. verify the revision’s generator compatibility version;
4. recompute and verify immutable content hash;
5. generate the SchemeRun only after SourceBinding and weight-set verification pass.

SchemeRun persists:

- `weight_set_revision_id`;
- `weight_set_content_hash`;
- `weight_set_generator_compatibility_version`.

The SchemeRun result hash and provenance include all three fields plus SourceBinding ID, source contract version, and combined source hash.

### 17.3 Task 11 baseline fixture

The fixture uses `weight_set_code="baseline-balanced"` to resolve the current approved compatible revision, then passes the exact resolved `revision_id` to SchemeService. The registry must expose exactly one active approved revision per `(weight_set_code, generator_compatibility_version)`; multiple active matches are an ambiguity error. The fixture neither passes only the code nor hard-codes an arbitrary UUID.

---

## 18. SchemeRun database integrity and source mode

Add `source_mode = legacy | production` and enforce:

```sql
CHECK (
    (
        source_mode = 'legacy'
        AND source_binding_id IS NULL
        AND source_contract_version IS NULL
        AND weight_set_revision_id IS NULL
        AND weight_set_content_hash IS NULL
        AND weight_set_generator_compatibility_version IS NULL
    )
    OR
    (
        source_mode = 'production'
        AND source_binding_id IS NOT NULL
        AND source_contract_version IS NOT NULL
        AND weight_set_revision_id IS NOT NULL
        AND weight_set_content_hash IS NOT NULL
        AND weight_set_generator_compatibility_version IS NOT NULL
    )
)
```

This includes the required all-null/all-non-null rule for `source_binding_id` and `source_contract_version`. Production SchemeRuns reject legacy or partially populated source identity.

---

## 19. SchemeSourceArchiveV1 and downgrade contract

```python
@dataclass(frozen=True, slots=True)
class SchemeSourceArchiveV1:
    scheme_run_id: str
    source_binding_id: str
    source_contract_version: str
    project_id: str
    project_version_id: str
    execution_snapshot_hash: str
    coefficient_context_hash: str
    zone_calculation_id: str
    cooling_load_calculation_id: str
    equipment_calculation_id: str
    power_calculation_id: str
    investment_calculation_id: str
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
    archive_hash: str
```

`archive_hash` is SHA-256 over canonical JSON of every field above except `archive_hash` itself.

Downgrade rules:

1. default downgrade is blocked while any production SchemeRun depends on online SourceBinding rows;
2. explicit archive/export never automatically deletes online source rows;
3. archive content and hash must verify before any detachment is considered;
4. only a separate independently reviewed migration may detach/remove online foreign-key targets;
5. historical SchemeRun reads must resolve either the online SourceBinding or a verified `SchemeSourceArchiveV1` artifact;
6. missing online binding and missing/invalid archive is a hard integrity error.

---

## 20. Transactional audit outbox and dispatcher

### 20.1 AuditOutboxEvent

Required fields:

- `id`;
- nullable `request_id`, `identity_id`, `attempt_id`, `calculation_run_id`, `source_binding_id` foreign keys according to event level;
- action;
- canonical payload;
- `status = PENDING | PROCESSING | PUBLISHED`;
- `claimed_at`;
- `claimed_by`;
- `attempt_count`;
- `next_retry_at`;
- `last_error_code`;
- `published_at`;
- `created_at`.

Request-level preflight events bind to `request_id` and must not invent identity/attempt IDs. Execution events bind to identity/attempt, and calculation/binding events add their specific foreign key.

### 20.2 AuditEventRecord idempotency key

```sql
outbox_event_id NOT NULL UNIQUE
```

One outbox event can materialize at most one database `AuditEventRecord`. The migration must backfill every pre-existing audit row with a stable unique legacy materialization identifier before enforcing NOT NULL; new dispatcher-created rows always use the real outbox event ID.

### 20.3 Atomic claim

PostgreSQL uses `SELECT ... FOR UPDATE SKIP LOCKED` or an equivalent atomic `UPDATE ... RETURNING`. Eligibility is:

```text
status=PENDING and next_retry_at is due
or
status=PROCESSING and claim lease expired
```

SQLite uses one write transaction, preferably `BEGIN IMMEDIATE`, to:

1. select eligible IDs;
2. update only rows still eligible to PROCESSING with `claimed_at`, `claimed_by`, and incremented `attempt_count`;
3. return/reload only rows claimed by that worker in that transaction.

A worker may process only rows it atomically claimed.

### 20.4 Delivery, retry, and crash recovery

- On success, insert `AuditEventRecord(outbox_event_id=...)`, then mark the outbox PUBLISHED with `published_at`.
- On a handled delivery failure, return the outbox to PENDING, clear claim fields, set `last_error_code`, and set deterministic/backoff `next_retry_at`.
- On worker crash, the row remains PROCESSING and is reclaimable after lease expiry.
- If `AuditEventRecord` was inserted but PUBLISHED was not recorded, retry insertion hits the unique constraint; that conflict is treated as successful prior materialization, and the outbox is marked PUBLISHED.
- PUBLISHED rows are never eligible for claim.

The accurate guarantee is **at-least-once delivery plus idempotent materialization**, not distributed exactly-once delivery.

---

## 21. Error taxonomy

Minimum structured errors:

| Error class | code | field | phase |
|---|---|---|---|
| `OrchestrationRequestIdentityError` | `ORCH_REQUEST_IDENTITY_INVALID` | request identity field | preflight |
| `ProjectVersionNotFoundError` | `PROJ_VERSION_NOT_FOUND` | `project_version_id` | preflight |
| `ProjectVersionProjectMismatchError` | `PROJ_VERSION_PROJECT_MISMATCH` | `project_id` | preflight |
| `ProjectVersionNotReadyError` | `PROJ_VERSION_NOT_READY` | `version_status` | preflight |
| `ProjectVersionArchivedError` | `PROJ_VERSION_ARCHIVED` | `project_version_id` | preflight |
| `ProjectVersionStatusInvalidError` | `PROJ_VERSION_STATUS_INVALID` | `version_status` | preflight |
| `ExecutionSnapshotSchemaError` | `EXEC_SNAPSHOT_SCHEMA_INVALID` | `schema_version` | preflight |
| `CoefficientResolutionError` | `COEFF_RESOLUTION_FAILED` | `coefficient_code` | preflight |
| `CoefficientNotApprovedError` | `COEFF_NOT_APPROVED` | `coefficient_code` | preflight |
| `AmbiguousCoefficientError` | `COEFF_AMBIGUOUS` | `coefficient_code` | preflight |
| `AttemptAlreadyRunningError` | `ORCH_ATTEMPT_ALREADY_RUNNING` | `identity_id` | lease |
| `AttemptTakeoverConflictError` | `ORCH_ATTEMPT_TAKEOVER_CONFLICT` | `heartbeat_at` | lease |
| `SourceBindingSlotTypeError` | `SOURCE_BINDING_SLOT_TYPE` | `slot_name` | verification |
| `SourceBindingIdentityMismatchError` | `SOURCE_BINDING_IDENTITY_MISMATCH` | mismatched field | verification |
| `SourceBindingHashMismatchError` | `SOURCE_BINDING_HASH_MISMATCH` | hash field | verification |
| `WeightSetNotApprovedError` | `WEIGHT_SET_NOT_APPROVED` | `weight_set_revision_id` | SchemeService |
| `WeightSetIncompatibleError` | `WEIGHT_SET_INCOMPATIBLE` | `generator_compatibility_version` | SchemeService |
| `SchemeSourceArchiveIntegrityError` | `SCHEME_SOURCE_ARCHIVE_INVALID` | `archive_hash` | historical read |

Errors preserve machine-readable `code`, `field`, and structured `details`.

---

## 22. Implementation work breakdown

Every subtask below requires a separate implementation review. This PR does not implement any item.

### A. Request/preflight contracts and audit

- **Scope:** immutable input/result DTOs, mutable request entity, typed preflight errors, request-level outbox.
- **Dependencies:** none.
- **Files/modules:** orchestration `contracts.py`, `errors.py`, request repository/ORM.
- **Schema changes:** `orchestration_requests`; request FK on outbox.
- **Acceptance criteria:** all preflight classes persist request rejection and no identity/attempt/calculation/binding.
- **Non-goals:** no calculator execution.

### B. Execution snapshot identity and get-or-create

- **Scope:** snapshot candidate, canonical snapshot hash, execution identity hash, immutable snapshot record.
- **Dependencies:** A.
- **Files/modules:** `fingerprint.py`, snapshot adapter, repository.
- **Schema changes:** execution snapshot table and unique constraint.
- **Acceptance criteria:** cross-project/version isolation and concurrent get-or-create on both databases.
- **Non-goals:** no coefficient resolution.

### C. Materialized coefficient context and approved catalog

- **Scope:** approved revision resolution, candidate materialization, content hash, project-version-scoped reuse.
- **Dependencies:** A, B, coefficient registry.
- **Files/modules:** orchestration coefficient adapter; coefficient catalog/repository.
- **Schema changes:** coefficient context table and unique constraint; approved catalog records as separately reviewed migration/seed.
- **Acceptance criteria:** missing/ambiguous/unapproved revisions fail preflight; identical concurrent contexts converge.
- **Non-goals:** no demo fallback.

### D. Approved Scheme weight-set governance

- **Scope:** immutable weight-set revisions, approval metadata, content hash, compatibility version, baseline-balanced revision.
- **Dependencies:** Scheme module ownership approval.
- **Files/modules:** Scheme domain/infrastructure/service.
- **Schema changes:** weight-set revision tables and SchemeRun binding columns.
- **Acceptance criteria:** only approved compatible revision IDs generate production SchemeRuns.
- **Non-goals:** no scoring-formula redesign.

### E. Production input adapters

- **Scope:** deterministic mapping from execution snapshot/context and prior formal stage results into typed calculator inputs.
- **Dependencies:** B, C.
- **Files/modules:** orchestration `adapters.py`.
- **Schema changes:** none.
- **Acceptance criteria:** missing required source fields fail closed; no zero/default fabrication.
- **Non-goals:** no calculator formula changes.

### F. Five-stage calculation DAG

- **Scope:** exact sequential DAG and structured stage blocker propagation.
- **Dependencies:** B, C, E.
- **Files/modules:** orchestration `service.py`, `dag.py`.
- **Schema changes:** none beyond dependent persistence tasks.
- **Acceptance criteria:** exact order, exact five stages, no SchemeService call on BLOCKED/FAILED.
- **Non-goals:** no parallel execution.

### G. Orchestration identity and attempt lease

- **Scope:** identity, attempts, retry policy, heartbeat, one-RUNNING index, CAS takeover.
- **Dependencies:** B, C.
- **Files/modules:** orchestration ORM/repositories.
- **Schema changes:** identity/attempt tables, unique and partial unique indexes.
- **Acceptance criteria:** at most one RUNNING attempt; CAS failure never creates a new attempt.
- **Non-goals:** no external distributed-lock service.

### H. UnitOfWork and transaction-aware repositories

- **Scope:** service-owned Transaction A/B/C lifecycles and session-bound repositories.
- **Dependencies:** F, G.
- **Files/modules:** `unit_of_work.py`, repositories, project calculation persistence adapter.
- **Schema changes:** none beyond dependent entities.
- **Acceptance criteria:** repositories never commit; Transaction B rollback removes all staged calculations/binding.
- **Non-goals:** no reuse of the existing independently committing method unchanged.

### I. SourceSnapshot hash/content adapters

- **Scope:** five typed content adapters, envelope, canonical result hash, review propagation.
- **Dependencies:** F.
- **Files/modules:** `snapshots.py` and adapter tests.
- **Schema changes:** CalculationRun orchestration/hash/provenance columns and CHECK.
- **Acceptance criteria:** one non-self-referential result hash verifies in record, binding, and SchemeService.
- **Non-goals:** no raw envelope persistence as Scheme business payload.

### J. SourceBinding persistence and strict verification

- **Scope:** one-way binding, exact slot registry, full identity/type/hash verification, authoritative attempt check.
- **Dependencies:** G, H, I.
- **Files/modules:** orchestration repository and SchemeService.
- **Schema changes:** SourceBinding table, FKs, unique constraints.
- **Acceptance criteria:** any wrong slot/type/project/version/snapshot/context/hash fails closed.
- **Non-goals:** no latest-row fallback or reverse calculation FK.

### K. Power-to-Scheme mapping

- **Scope:** map only Power total installed power into Scheme candidate inputs.
- **Dependencies:** I, J.
- **Files/modules:** SchemeService adapters/tests.
- **Schema changes:** none beyond SchemeRun changes.
- **Acceptance criteria:** equipment compressor power cannot satisfy installed-power input.
- **Non-goals:** no Power formula changes.

### L. Transactional audit outbox and idempotent dispatcher

- **Scope:** outbox lifecycle, atomic claim, retry, crash recovery, AuditEvent idempotency.
- **Dependencies:** H.
- **Files/modules:** outbox dispatcher, ORM, repositories.
- **Schema changes:** outbox table; `AuditEventRecord.outbox_event_id UNIQUE NOT NULL` for outbox-materialized events with migration strategy for legacy rows.
- **Acceptance criteria:** multi-worker claims do not duplicate materialization; crash windows recover.
- **Non-goals:** no external broker and no exactly-once claim.

### M. SQLite/PostgreSQL constraints and concurrency tests

- **Scope:** parity tests for unique indexes, get-or-create, CAS, transaction rollback, outbox claim.
- **Dependencies:** J, K, L.
- **Files/modules:** backend integration/concurrency tests.
- **Schema changes:** validates all migration behavior.
- **Acceptance criteria:** both database suites prove equivalent business invariants.
- **Non-goals:** no load/performance certification.

### N. Issue #22 acceptance-criteria synchronization

- **Scope:** after design approval, update Issue #22 from four to five calculation types and add all frozen contracts.
- **Dependencies:** this design review accepted.
- **Files/modules:** Issue #22 body only.
- **Schema changes:** none.
- **Acceptance criteria:** Issue #22 accurately requires Power, SourceBinding, identity/attempt, approved weight revision, and outbox before implementation begins.
- **Non-goals:** no code and no issue closure.

### O. Task 11 Phase B resumption

- **Scope:** only after A-N are implemented, merged, and independently reviewed, wire Task 11 to the production path.
- **Dependencies:** A-N complete and Issue #22 acceptance criteria satisfied.
- **Files/modules:** PR #21/evaluation runner in a later reviewed change.
- **Schema changes:** none beyond Issue #22 implementation.
- **Acceptance criteria:** baseline uses approved ProjectVersion and exact approved compatible weight-set revision; all eight evaluation stages pass with `outcome=success`.
- **Non-goals:** no Phase C, Phase D, or Task 12.

---

## 23. Test matrix

### 23.1 Identity and preflight

- different project IDs with identical inputs produce different fingerprints;
- different ProjectVersion IDs with identical inputs produce different fingerprints;
- identical ProjectVersion/context/version vector produces identical fingerprint;
- version number inconsistent with ProjectVersion ID fails closed;
- `project_version_id` is the only authoritative lookup;
- project ID cross-check failure is a preflight rejection;
- draft, archived, unknown, and illegal version states are preflight rejections;
- invalid request identity is a preflight rejection;
- invalid snapshot schema is a preflight rejection;
- missing/ambiguous/unapproved coefficient is a preflight rejection;
- preflight rejection creates request-level outbox evidence;
- preflight rejection creates no identity, attempt, calculation, or binding.

### 23.2 Idempotency and concurrency

- completed idempotency hit creates no snapshot/context;
- concurrent execution snapshot get-or-create returns one authoritative row;
- concurrent coefficient context get-or-create returns one authoritative row;
- concurrent identity get-or-create returns one identity;
- one identity permits at most one RUNNING attempt;
- valid RUNNING lease returns in-progress/conflict and creates no attempt;
- stale takeover with unchanged heartbeat transitions exactly one row and creates the next attempt;
- stale takeover with changed heartbeat affects zero rows and creates no attempt;
- attempt-number race is resolved without duplicate RUNNING attempts;
- PostgreSQL and SQLite prove the same invariants.

### 23.3 Rollback and result semantics

- zone and cooling_load pass, equipment blocks, Transaction B rolls back;
- no calculation row from that attempt remains after rollback;
- `persisted_stages` is empty after rollback;
- diagnostics show actual execution states and no calculation ID;
- BLOCKED/FAILED has null SourceBinding ID;
- SchemeService is never called for BLOCKED/FAILED;
- COMPLETED returns exactly five persisted stages and one SourceBinding.

### 23.4 SourceBinding and hashes

- each correct slot/type/calculator combination verifies;
- a slot pointing to another calculation type is rejected;
- unsupported calculator name is rejected;
- project mismatch is rejected;
- ProjectVersion mismatch is rejected;
- execution snapshot mismatch is rejected;
- identity/attempt mismatch is rejected;
- coefficient context mismatch is rejected;
- unsupported schema is rejected;
- tampered content/result hash is rejected;
- `requires_review` mismatch is rejected;
- extra or missing per-calculation hash keys are rejected;
- combined source hash is exact and stable;
- Power installed power is used and equipment compressor power fallback is rejected;
- five adapters given identical complete SourceSnapshotContentV1 produce identical result_hash;
- same business payload + same provenance (same upstream calculation IDs, same execution identity) → same result_hash;
- same business payload + different upstream calculation IDs → different provenance → different result_hash;
- same business payload + different coefficient context → different result_hash;
- calculator output field order changes do not alter normalized payload or result_hash;
- zone detail order changes → canonical sort → hash unchanged;
- CalculationRunRecord database ID changes → provenance differs → result_hash changes;
- equipment `installed_power_kw_e` absent from EquipmentSourceSnapshot payload;
- Power payload includes `total_installed_power_kw_e`;
- Power slot missing → SchemeService fail closed;
- Equipment power must not serve as Power fallback;
- production path uses five PRODUCTION_SOURCE_SLOTS;
- demo path uses exactly five DEMO_REQUIRED_CALC_TYPES with demo power seed;
- demo power missing → fail closed;
- demo duplicated power → fail closed;
- demo power wrong calculation_type → fail closed;
- demo power wrong calculator_name → fail closed;
- production never consumes demo records;
- demo never consumes production SourceBinding;
- unknown calculator output field excluded from payload;
- adding a payload field requires schema version increment;
- `calculation_type="investment"` correctly bound to `calculator_name="investment_estimate"`.

### 23.5 Outbox

- multiple dispatchers atomically claim disjoint rows;
- claim followed by worker crash is recoverable after lease expiry;
- handled delivery failure schedules retry and preserves error code;
- duplicate AuditEvent insertion is treated as idempotent success;
- `AuditEventRecord.outbox_event_id` uniqueness is enforced;
- PUBLISHED events are never reclaimed;
- request-level preflight events do not require identity/attempt IDs.

### 23.6 Scheme and downgrade integrity

- approved compatible weight-set revision is accepted;
- unapproved revision is rejected;
- generator-incompatible revision is rejected;
- recomputed weight-set content hash mismatch is rejected;
- SchemeRun result hash/provenance changes when revision/hash/compatibility changes;
- legacy SchemeRun all-null CHECK passes;
- production SchemeRun all-non-null CHECK passes;
- partially populated SchemeRun fails CHECK;
- `SchemeSourceArchiveV1.archive_hash` verifies;
- tampered archive fails historical read;
- downgrade is blocked while production SchemeRuns reference online binding;
- historical read resolves online binding or verified archive, never neither.

---

## 24. Post-approval Issue #22 synchronization gate

Issue #22 currently requires four CalculationRunRecord types. The accepted design requires five. This design review must not directly change Issue #22; however, after approval and before any implementation starts, subtask N must update its acceptance criteria to:

1. replace four types with five: zone, cooling_load, equipment, power, investment;
2. require a separate Power CalculationRunRecord;
3. require SourceBinding persistence and strict verification;
4. require orchestration request, identity, and attempt contracts;
5. require approved coefficient context and approved Scheme weight-set revision;
6. require transactional audit outbox and idempotent dispatcher;
7. require SQLite/PostgreSQL integrity and concurrency tests;
8. require the legacy/orchestrated CalculationRun CHECK and SchemeRun source-mode CHECK.

Implementation is forbidden until this synchronization gate is complete.

---

## 25. Task 11 Phase B resumption gate

Task 11 Phase B remains BLOCKED until all of the following are true:

- this design is accepted;
- Issue #22 acceptance criteria are synchronized;
- a separate production implementation PR is merged after independent engineering review;
- five CalculationRunRecord types are produced atomically;
- SourceBinding is materialized only for COMPLETED attempts;
- SchemeService strictly verifies SourceBinding and approved weight-set revision;
- approved coefficient and weight-set paths can produce the required baseline without demo fallback;
- fingerprint, concurrency, rollback, hash, outbox, and downgrade contracts pass on SQLite and PostgreSQL;
- Task 11 baseline uses an approved ProjectVersion and exact approved compatible weight-set revision;
- all eight Task 11 stages pass with `outcome=success`.

No Phase C, Phase D, or Task 12 work is authorized by this design.

---

## 26. Review 4587180512 closure map

1. Execution-bound hash identity unified (§5, §13.3, §13.5.6, §13.5.7, §16.4) — `result_hash` hashes complete `SourceSnapshotContentV1` including provenance; golden scenarios 7-9 added; provenance key set frozen with exact upstream dependency contract.
2. Demo path frozen to single five-type strategy (§17.0) — all four-type branch residue deleted.
3. Nested payload schemas completed (§13.5.1–§13.5.5) — `planning_parameters`, `area_basis`, `systems[].zones`, `equipment_items` expanded from opaque dict/list to field-level tables; all missing source paths added; duplicate handling frozen per list type.
4. Universal adapter rules hardened (§13.5.0) — explicit nested unknown-key policy, missing required key → fail closed, duplicate semantic key → fail closed, nested object projection from allowlisted paths.
5. `requires_review`/envelope confusion resolved (§13.5.2) — `requires_review` is top-level content field, not envelope; `warnings` not auto-copied to payload.
6. Document metadata updated to current review head.

This document is ready for engineering re-review. It does not authorize implementation.
