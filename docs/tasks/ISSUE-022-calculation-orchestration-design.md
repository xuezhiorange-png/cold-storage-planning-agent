# ISSUE-022: Formal Calculation Orchestration and Persistence Design

**Issue:** #22  
**Draft PR:** #23  
**Date:** 2026-06-28  
**Review addressed:** 4587054607  
**Reviewed Head:** `7df4ded32a28a1dbd012362b494640da8cd4f0b9`  
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
execution_identity_hash = SHA_256(
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
orchestration_fingerprint = SHA_256(
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
    accepted_identity_id: str | None
    accepted_attempt_id: str | None
    failure_code: str | None
    failure_field: str | None
    failure_details: Mapping[str, object] | None
    created_at: datetime
    completed_at: datetime | None
```

`request_fingerprint` is an audit correlation hash, not the orchestration idempotency key:

```python
request_fingerprint = SHA_256(
    canonical_json({
        "project_id": input.project_id,
        "project_version_id": input.project_version_id,
        "coefficient_resolution_context": input.coefficient_resolution_context,
        "actor": input.actor,
        "correlation_id": input.correlation_id,
    })
)
```

It is indexed but not globally unique; every invocation receives a distinct request ID. `accepted_identity_id` and `accepted_attempt_id` are null for PENDING/PREFLIGHT_REJECTED requests and are populated for ACCEPTED requests, including an idempotent hit that returns an existing authoritative attempt. A database CHECK enforces those status-dependent nullability rules.

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
result_hash = SHA_256(canonical_json(SourceSnapshotContentV1))
```

The same exact `result_hash` value is stored in `CalculationRunRecord`, copied into the binding’s per-calculation hash map, and recomputed by SchemeService. No alternate payload-only or envelope hash is permitted.

### 13.4 Semantic boundaries

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
combined_source_hash = SHA_256(
    canonical_json({
        "zone": zone_result_hash,
        "cooling_load": cooling_load_result_hash,
        "equipment": equipment_result_hash,
        "power": power_result_hash,
        "investment": investment_result_hash,
    })
)
```

Each value is the corresponding `CalculationRunRecord.result_hash`, which is the hash of `SourceSnapshotContentV1`. The exact key set is mandatory. Payloads, envelopes, raw `CalculationResult` objects, file bytes, and database JSON strings are forbidden combined-hash inputs.

---

## 17. SchemeService and approved weight-set revision

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
- Power installed power is used and equipment compressor power fallback is rejected.

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

## 26. Review 4587054607 closure map

1. Project/version fingerprint isolation -> Sections 6 and 8.
2. Preflight rejection versus execution BLOCKED -> Section 9.
3. Orphan-free snapshot/context materialization -> Section 8.
4. One RUNNING attempt and heartbeat CAS takeover -> Section 11.
5. Rollback-safe persisted stages and diagnostics -> Sections 12 and 14.
6. Strict SourceBinding type/identity verification -> Section 16.
7. Sole combined source hash -> Section 16.4.
8. Idempotent outbox dispatcher -> Section 20.
9. Authoritative ProjectVersion lookup -> Section 6.1.
10. Approved weight-set revision binding -> Section 17.
11. SchemeRun CHECK and archive artifact -> Sections 18 and 19.
12. Post-approval Issue #22 synchronization -> Section 24 and work item N.

This document is ready for engineering re-review. It does not authorize implementation.
