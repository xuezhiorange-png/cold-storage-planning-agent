# Task 11B — Production Calculation Orchestration Prerequisite (Design)

Status: **design draft — implementation NOT authorized**

> **Designation of path forward: A (end-to-end to SchemeService).**
> This production prerequisite MUST invoke the production
> SchemeService end-to-end. The completed `SchemeRun`
> produced by `SchemeService.run(...)` is part of this task's
> acceptance criteria, not a future Phase C deliverable.
> When this capability ships, Task 11 Phase B
> `baseline-feasible` success is unlocked directly, without
> requiring any additional bridge PR.

This document defines the formal production calculation
orchestration path. It is intentionally separate from PR #21
(Task 11 evaluation pilot readiness, Draft / Open / Not
merged) and from Issue #22 (transport-B E2E persistence,
CLOSED via PR #33). The capability delivered here is the
standalone application orchestration that PR #21's evaluation
harness consumes as a real production producer — not as an
evaluation-owned seam.

> ⚠️ **This document is design-only.** All sections below
> describe a target architecture and a contract surface; **no
> production code, no tests, no migrations, and no PR changes
> against PR #21 are authorized by this document.**

---

## 1. Problem statement

PR #21 / Task 11 Phase B is currently blocked by the
harness-level blocker
`EVAL_PRODUCTION_PIPELINE_PREREQUISITE_MISSING`, which asserts
a missing capability:

```
missing_capability = "formal_production_calculation_orchestration_path"
blocked_by         = "production_capability_gap"
required_calculation_types = ["zone", "investment",
                              "cooling_load", "equipment"]
```

This prerequisite is bound to path **A** (end-to-end
SchemeService invocation). Path **B** (deferred
SchemeService.run to a separate bridge phase) was reviewed
and rejected because it could not, on its own, unlock Task
11 Phase B baseline-feasible success.

This blocker does NOT come from evaluation. It comes from the
real production path not yet exposing a public entry point
that:

1. Accepts an **approved ProjectVersion** as the single source
   of truth for inputs and coefficients.
2. Drives the production **Transaction A → C → B** pipeline to
   generate, persist, and verify five `CalculationRunRecord`s
   (zone, cooling_load, equipment, power, investment).
3. Persists a **SourceBindingRecord** whose combined source
   hash is reproducible against `SourceBindingVerifier`.
4. **End-to-end invokes the production SchemeService** to
   produce a completed `SchemeRun` whose envelope carries the
   same five frozen `ResultSnapshotV1`s and the same verified
   binding.
5. Writes the immutable **source archive row** that
   governance requires for every successful run.
6. Returns the completed `SchemeRun` id and a status that the
   evaluation runner can map to `outcome = "success"` for
   `baseline-feasible` — without re-implementing anything.

Until this path exists:

- The `baseline-feasible` scenario is unreachable from the
  evaluation runner without evaluation-owned workarounds that
  fabricate orchestration identity / attempt / execution
  snapshot / coefficient context rows.
- The `ColdRoomZonePlanner.plan()` and
  `InvestmentEstimator.estimate()` calculators internally
  hard-code demo coefficient warnings and emit
  `requires_review=true`, even when the approved ProjectVersion
  supplies catalog coefficients. There is no current way to
  drive `requires_review=false` from a production caller.
- The `SourceBindingVerifier` cannot be reached from an
  end-to-end SchemeService call without test-only adapters.

This task's implementation MUST close all three at once. There
is no follow-on "SchemeService bridge" PR waiting to consume
this work — closing Issue #35 is the same act as closing the
production prerequisite for Task 11 Phase B.

---

## 2. Non-goals

This design task explicitly does not authorize:

1. **Modifying PR #21** in any way (no commits, no body edits,
   no ready/merge actions, no base retargeting).
2. **Modifying PR #32, PR #33, Issue #22, Issue #31, Issue #20**
   states.
3. **Reopening Issue #22** or re-litigating its closure.
4. **Starting Task 11 Phase C / Phase D** or **Task 12**.
5. **Modifying production formulas, thresholds, weights, or
   review rules** in the calculators
   (`ColdRoomZonePlanner`, `calculate_cooling_load`,
   `calculate_equipment_capability`, `calculate_installed_power`,
   `InvestmentEstimator`).
6. **Adding evaluation-layer seeding** of any kind (including
   but not limited to `compose_*`, hand-written snapshot
   construction, ORM-fabricated records).
7. **Wrapping the demo coefficient path as a "production"
   path** — e.g. capturing `requires_review` warnings and
   dropping them, or substituting demo coefficients with
   in-test mocks and calling that "approved".
8. **Modifying `evaluation/manifest.json` or
   `evaluation/expected/*.v1.json`** to accept
   `review_required` as a baseline success substitute.
9. **Modifying golden expectations** in any way.
10. **Implementing tests, repositories, services, or ORM
    mappings**. This is a design deliverable only.

---

## 3. Architecture boundary

The new capability MUST live in the existing orchestration
module, NOT in a new module, NOT in evaluation, NOT in tests:

```
backend/src/cold_storage/modules/orchestration/
├── application/
│   ├── production_calculation_orchestrator.py   ← new (entry point)
│   ├── service.py                                ← existing (Transaction A + C)
│   ├── transaction_b.py                          ← existing (Transaction B + SourceBindingVerifier)
│   ├── source_snapshots.py                       ← existing (typed snapshot models)
│   ├── source_archive_builder.py                 ← existing (SourceArchiveBuilderPort)
│   ├── historical_source_resolver.py             ← existing
│   ├── ports.py                                  ← existing (extend)
│   ├── unit_of_work.py                           ← existing
│   └── ...
├── domain/
│   ├── contracts.py                              ← existing
│   ├── snapshots.py                              ← existing (SourceSnapshotContentV1)
│   ├── fingerprint.py                            ← existing (result_hash)
│   └── errors.py                                 ← existing
├── infrastructure/
│   ├── repositories.py                           ← existing (extend)
│   ├── outbox_dispatcher.py                      ← existing
│   ├── coefficient_resolver.py                   ← existing
│   ├── source_archive_repository.py              ← existing
│   └── orm.py                                    ← existing
└── ...
```

The new `production_calculation_orchestrator.py` is the SINGLE
public entry point for the production flow. It composes:

- `service.execute(...)` (Transaction A: request → snapshot →
  coefficient context → identity → RUNNING attempt → ACCEPTED)
- `TransactionBExecutor.execute(...)` (Transaction B: invoke
  calculators, persist `CalculationRunRecord`s, build binding,
  verify combined source hash)
- `SourceArchiveBuilderPort` (Transaction C tail: write source
  archive immutable row)
- `MaterializeOutboxEventUseCase` (audit outbox envelope)
- **`SchemeService.run(...)`** (end-to-end SchemeService
  invocation — completes the `SchemeRun` and freezes its
  envelope. There is no "ready output" projection; the
  completed `SchemeRun` IS the terminal record.)
- The existing terminal-transition path that flips RUNNING →
  SUCCEEDED on the orchestration attempt.

It MUST NOT short-circuit any of these calls. It MUST NOT
fabricate records. It MUST NOT bypass the existing repository
ports by calling ORM directly. It MUST NOT produce a
"SchemeService-ready" projection that a separate future PR
will then re-read and feed to SchemeService — that design is
explicitly rejected under path A; this task invokes
SchemeService itself.

The capability MUST be reachable from:

- A FastAPI endpoint OR an application-level CLI subcommand
  exposed via the orchestration module
  (e.g. `cold_storage orchestration execute-approved ...`),
  with `Idempotency-Key` honored as a first-class input.
- The evaluation runner — but only as a real producer, never
  as an evaluation-owned producer. The runner MAY call the
  orchestrator via the same public entry point any other caller
  would, and the orchestrator's terminal record MUST be
  consumable by the runner without re-implementing SchemeRun
  invariant checks.

---

## 4. Domain model / ports / adapters

### 4.1 Identity & snapshot records

The orchestrator MUST materialize, in this order, with the
following governance:

| Record | Owner | Identity source | Authority |
| --- | --- | --- | --- |
| `OrchestrationIdentity` | new | `RequestEnvelope.request_id` (frozen) | one per ProjectVersion execution |
| `OrchestrationRunAttempt` | new | next `attempt_no` for that identity | one RUNNING → one terminal |
| `ProjectVersionExecutionSnapshot` | new | input fingerprint over ProjectVersion + inputs | immutable, hash-stable |
| `CoefficientContext` | new | resolved from approved catalogue via `CoefficientContextPort` | one per attempt |
| `CalculationRunRecord` (5×) | new | deterministic from `(attempt_id, calculation_type, input_hash)` | calculator-port-produced |
| `SourceBindingRecord` | new | combined source hash from the five `result_hash`es | verified by `SourceBindingVerifier` |
| `SourceArchiveRow` | existing | immutable archive of the binding | enforced by archive repository |
| **`SchemeRun`** | existing | terminal output of `SchemeService.run(...)` | envelope-frozen, immutable after completion |
| `AuditOutboxEvent` | existing | `AuditOutboxRepository.materialize_event` | envelope-frozen |

The completed `SchemeRun` is the terminal record of this
orchestrator call. It carries:

- the same `attempt_id` as the orchestration attempt,
- the same `binding_id` as the verified `SourceBindingRecord`,
- the same five `ResultSnapshotV1` payloads as the
  `CalculationRunRecord`s (frozen into its envelope at run
  time),
- a `frozen_envelope` (canonical JSON, hash-stamped, schema
  version `v1`),
- a `completed_at` timestamp,
- a `scheme_status ∈ {SUCCEEDED, BLOCKED, FAILED}` and, when
  applicable, a `blocker.code` consistent with the
  `EVAL_PRODUCTION_PIPELINE_PREREQUISITE_MISSING` /
  `production_capability_gap` contract.

### 4.2 Ports (additions to `application/ports.py`)

The following ports MUST exist before any implementation
begins; their signatures are stated here as a contract, but
the implementation is **NOT** part of this design task:

- `ApprovedProjectVersionReadPort.load(version_id) → ProjectVersionReadResult`
  — returns ProjectVersion plus its inputs, status
  (`APPROVED`), and the originating project.
- `ApprovedProjectVersionReadPort.assert_status_approved(version)`
  — fail-closed if status ≠ APPROVED.
- `OrchestrationIdempotencyPort.lookup_or_register(idempotency_key)`
  — returns `(existing_attempt_id, status)` if seen before;
  registers a new key if not.
- `ProductionCalculatorPort` — adapters must implement
  `execute(calculation_type, attempt_id, inputs, snapshot)`
  for each of `zone | cooling_load | equipment | power |
  investment`. Each adapter wraps the existing calculator
  (`ColdRoomZonePlanner.plan()`,
  `calculate_cooling_load(...)`, etc.) and emits a
  `CalculationRunRecord` with `result_snapshot`, `result_hash`,
  `requires_review`, `review_reasons`, and audit metadata.
- `ApprovedNonDemoCoefficientResolverPort` — selects approved
  coefficients from the catalogue based on the ProjectVersion
  execution snapshot. Returns
  `(CoefficientContext, warnings)`. Demo coefficients
  (`source_type=demo`) are NOT acceptable for any baseline /
  production input set; the port rejects them with
  `CoefficientNotApprovedError`.
- **`SchemeServiceRunPort`** — invokes the production
  `SchemeService.run(attempt_id, binding_id, snapshots)`,
  returning the persisted `SchemeRun`. This is the
  end-to-end invocation; it is NOT a "ready output" writer
  awaiting a later bridge.

### 4.3 Adapters (high-level shape, not implementation)

- `SqlApprovedProjectVersionReadAdapter` — reads from the
  existing project module via its read port (no direct ORM
  dependence in the orchestration module).
- `SqlOrchestrationIdempotencyAdapter` — uses an existing
  schema table or extends `orchestration_attempts` to add
  `idempotency_key` (migration out of scope here; design
  only).
- `ProductionCalculatorAdapters` (one per type) — wraps the
  existing deterministic Python calculators; each adapter is
  a `CalculatorPort` implementation and inherits the
  Transaction B UoW contract.
- `CatalogApprovedCoefficientResolverAdapter` — uses the
  catalog module's read port to resolve coefficients;
  rejects `source_type=demo`, `validity_status=unverified`,
  or `requires_review=true at the coefficient level` for any
  baseline / production path.
- **`SqlSchemeServiceRunAdapter`** — invokes the existing
  production `SchemeService.run(...)` and persists the
  resulting `SchemeRun` row, including its `frozen_envelope`
  JSON. This adapter is the last step of the orchestrator
  flow; the orchestrator awaits its return.

### 4.4 Actor / correlation_id / idempotency key

Every orchestrator call MUST carry:

- `actor: str` (e.g. `"evaluation-runner"` or a real user
  principal).
- `correlation_id: str` (UUID v4, propagated).
- `idempotency_key: str | None` (UUID v4 or
  `RequestEnvelope.idempotency_key`).
- `database_backend: Literal["sqlite", "postgresql"]` —
  recorded on `OrchestrationRunAttempt.database_backend` and
  on the resulting `SchemeRun.database_backend`.
- `actor_principal_type: Literal["user", "service"]`.

These are persisted on `OrchestrationIdentity` /
`OrchestrationRunAttempt` and on the resulting `SchemeRun`,
and propagated to every outbox event envelope. They MUST NOT
be reconstructed or guessed on retry.

### 4.5 Run status lifecycle

```
PENDING → RUNNING → (
  SUCCEEDED                       (SchemeRun SUCCEEDED + archive written + binding verified)
  | BLOCKED                       (preflight or coefficient rejection — no SchemeRun written)
  | FAILED                        (calculator failure or SchemeService failure — no partial SchemeRun)
  | IDEMPOTENT_REPLAY_SUCCEEDED   (replay of an existing SUCCEEDED attempt + SchemeRun)
)
```

When status reaches `SUCCEEDED`, the orchestrator MUST return
`(attempt_id, scheme_run_id)`; the runner resolves
`outcome = "success"` when `SchemeRun.scheme_status ==
SUCCEEDED`.

Transitions are terminal. Replay of a SUCCEEDED attempt by
idempotency key MUST NOT re-execute calculators, re-invoke
SchemeService, or re-persist records — it MUST return the
existing `(attempt_id, scheme_run_id)` tuple, marked
`IDEMPOTENT_REPLAY_SUCCEEDED`.

---

## 5. DB records and schema implications

The following records already exist and require NO schema
change:

- `orchestration_requests`, `orchestration_attempts`,
  `orchestration_identity`, `coefficient_context`,
  `execution_snapshots`, `calculation_runs`,
  `source_bindings`, `source_archive`, `audit_outbox`,
  `weight_set_revisions`, `audit_events`, `scheme_runs`.

The following MAY require new columns or new tables (design
only — migration is NOT authorized by this document):

- `orchestration_attempts.idempotency_key UNIQUE` (per
  database backend).
- `orchestration_attempts.database_backend TEXT NOT NULL`.
- `orchestration_attempts.actor_principal_type TEXT NOT NULL`.
- `orchestration_attempts.correlation_id TEXT NOT NULL`.
- `orchestration_attempts.scheme_run_id` (nullable FK to
  `scheme_runs.id`, set on terminal SUCCEEDED).
- `scheme_runs.frozen_envelope` (canonical JSON, written at
  `SchemeService.run` completion; schema-frozen as
  `schema_version = "v1"`).
- `scheme_runs.database_backend TEXT NOT NULL`.

All schema changes MUST be Alembic-versioned and accompanied
by a downgrade/re-upgrade roundtrip test on PostgreSQL.

---

## 6. SourceBinding contract

`SourceBindingRecord` MUST satisfy:

- Five source slots in fixed order:
  `zone | cooling_load | equipment | power | investment`.
- Each slot binds `(calculation_id, result_hash)` where
  `calculation_id = CalculationRunRecord.id` and `result_hash`
  is the production canonical hash from
  `domain/fingerprint.result_hash(...)`.
- `combined_source_hash` is `_compute_combined_source_hash(...)`
  from `transaction_b.py` — the production canonical hash,
  NOT a test-derived hash.
- The binding is `verified=true, approved=true` only after
  `SourceBindingVerifier.verify(...)` accepts the binding
  unchanged. Fail-closed on tamper, missing slot, hash
  mismatch, or partial binding.
- No `latest-row` fallback. No legacy binding returned.
- The same `binding_id` is propagated into
  `SchemeService.run(...)` and is the `binding_id` persisted
  on the resulting `SchemeRun`. The SchemeService envelope
  binds to the same five slot hashes.
- Schema: `schema_version = "v1"`, frozen_envelope JSON
  contains the canonical 5-slot payload as a stable
  representation.

---

## 7. Coefficient governance

The `ApprovedNonDemoCoefficientResolverPort` MUST:

- Look up coefficients only from the catalogue (`catalog_*`
  modules) with `source_type ∈ {"manufacturer",
  "standard", "measured"}` and
  `validity_status == "verified"`. Demo
  (`source_type == "demo"` or `validity_status == "unverified"`)
  are REJECTED for baseline / production paths with
  `CoefficientNotApprovedError`.
- Build a `CoefficientContext` per attempt with full
  provenance: catalogue id, code, version, source type,
  validity status, approval status, lookup timestamp.
- Emit `Review-Required` only when a real warning comes from
  a calculator adapter (e.g. equipment-margin-warning) —
  NEVER as a default.
- Treat `missing`, `expired`, or `demo` coefficients as
  blockers (`BLOCKED + outbox event`), not as warnings.
- Provide a `CoefficientContext` shape compatible with the
  existing `CoefficientContextRepository` and the
  `FrozenCoefficientResolutionCriteria` contract from
  `coefficient_contracts.py`.

The current internal demo coefficient warnings emitted by
`ColdRoomZonePlanner.plan()` and
`InvestmentEstimator.estimate()` are a known source of
`requires_review=true`. **Resolving them is the responsibility
of the implementation task, not this design task**, but the
contract above makes the resolution path concrete: the
calculator adapters will be threaded with the resolved
`CoefficientContext` rather than hard-coding coefficients.

---

## 8. Snapshot schemas

The five `ResultSnapshotV1` Pydantic models already exist in
`application/source_snapshots.py`:

- `ZoneResultSnapshotV1`
- `CoolingLoadResultSnapshotV1`
- `EquipmentResultSnapshotV1`
- `PowerResultSnapshotV1`
- `InvestmentResultSnapshotV1`

Their contracts MUST be FROZEN as part of this design task:

- `extra = "forbid"` — additional fields are not allowed.
- Decimal canonicalisation: `Decimal` values are serialised
  as `str` (canonical string) and re-parsed losslessly.
  `float` representation is FORBIDDEN.
- Stable ordering: `CoefficientEntry`, `WarningEntry`,
  `SourceReferenceEntry`, `ZoneEntry`, power / investment
  rows are sorted by their `code` / `id` / `name` field at
  build time. Lists MUST be sorted before hash.
- Hash coverage: `result_hash = sha256(canonical_json(
  result_snapshot, sort_keys=True, ensure_ascii=False,
  decimal=str))`.
- `schema_version = "v1"`.
- Forward compatibility: a `v2` snapshot MUST be introduced
  as a new type, with explicit migration; v1 stays frozen.
- Resolver / verifier contract:
  - `build_*_snapshot_v1(calculation_output,
    coefficient_context)` returns the typed model;
  - `assert_snapshot_v1(snapshot)` re-parses via the model
    and recomputes the hash; mismatch is `raise
    SnapshotHashMismatchError`.
- SQLite / PostgreSQL parity: same JSON canonicalisation
  regardless of backend; storage layer treats the JSON
  payload as opaque bytes via `JSONB` on PostgreSQL and
  `JSON` on SQLite (no backend-specific hashing).
- **SchemeRun envelope**: the same five snapshots are
  bundled into the `SchemeRun.frozen_envelope` at run time,
  in the same fixed order, with the same hashes. The
  `SchemeRun.frozen_envelope` hash equals the
  `combined_source_hash` for the binding.

---

## 9. Transaction model

A single end-to-end orchestrator call MUST run inside one
`SqlAlchemyOrchestrationUnitOfWork`, with the following
savepoint discipline:

| Step | Savepoint | Notes |
| --- | --- | --- |
| Transaction A: persist request, snapshot, coefficient context, identity, attempt RUNNING | outer | required |
| Transaction B: persist 5 CalculationRunRecords + SourceBinding | nested savepoint per calculator | failure in one rolls back only that calculator run |
| SourceBindingVerifier | nested | fail-closed if verify rejects |
| SourceArchiveBuilder | nested | commits only if verify passes |
| **SchemeService.run** (persists `SchemeRun` row + `frozen_envelope`) | nested | commits only on SchemeRun SUCCEEDED; rolled back together with binding + archive on failure |
| Audit outbox (SUCCEEDED / BLOCKED / FAILED) | outer | one terminal event per orchestrator call |

The `SchemeService.run` step is committed in the SAME outer
UoW as the binding and archive. A partial state where the
binding and archive are persisted but the SchemeRun is not,
or vice versa, is not a valid orchestrator terminal state.

Idempotent replay: if an attempt with the same idempotency
key has already reached a terminal state, the orchestrator
MUST return that state without re-entering the UoW, with
status = `IDEMPOTENT_REPLAY_SUCCEEDED`, returning the same
`(attempt_id, scheme_run_id)` tuple.

PG unique constraints: existing
`uq_active_approved_weight_rev` and
`scheme_weight_set_active_revisions_pkey` continue to apply;
`outbox_event_id` UNIQUE applies to
`audit_events.outbox_event_id`. New
`orchestration_attempts.idempotency_key UNIQUE` per
database backend.

Outbox envelope: the existing
`AuditOutboxRepository.materialize_event(...)` + envelope
contract is the only writer. No silent fallback events.

---

## 10. Fail-closed matrix

| Condition | Failure mode |
| --- | --- |
| ProjectVersion status ≠ APPROVED | BLOCKED, no rows persisted after attempt RUNNING |
| ProjectVersion not found | BLOCKED, no rows |
| Demo coefficient requested | BLOCKED, no calculator execution |
| Calculator exception | FAILED, attempt row in FAILED, no partial CalculationRunRecord |
| SourceBindingVerifier rejects | FAILED, attempt FAILED, no archive, no SchemeRun, no outbox SUCCEEDED |
| `SchemeService.run` returns `BLOCKED` | attempt → BLOCKED, no archive, no SchemeRun, blocker.code mirrored to outbox |
| `SchemeService.run` raises | FAILED, attempt FAILED, no archive, no SchemeRun |
| Outbox envelope missing | FAILED, attempt FAILED, no SchemeRun |
| PG unique conflict on idempotency_key | IDEMPOTENT_REPLAY returned (no double execution, no extra outbox) |
| Tamper / missing snapshot / hash mismatch | detected by `assert_snapshot_v1` and treat as FAILED |
| Source snapshot shape change | fail-closed (v1 model rejects with Pydantic ValidationError) |
| Schema version mismatch | reject via `SourceSnapshotContentV1.schema_version == "v1"` check |

Fail-closed means: no partial state, no silent archive, no
warn-and-continue, and no SchemeRun persisted when the
binding is unverified. Every fail-closed path is paired with
a test in §11.

---

## 11. Test matrix (acceptance contract — design only)

### 11.1 Unit tests (post-implementation)

- Calculator adapter produces a `CalculationRunRecord` with
  the correct `result_snapshot`, `result_hash`, and
  `requires_review` flag.
- `ApprovedNonDemoCoefficientResolverPort` rejects demo
  coefficients with `CoefficientNotApprovedError`.
- `assert_snapshot_v1` rejects tampered JSON.
- `SourceBindingVerifier` rejects missing slot, hash
  mismatch, partial binding.
- `SchemeServiceRunPort` integration glue preserves all
  invariants (binding id, snapshot hashes, attempt id).

### 11.2 Integration SQLite

- Orchestrator runs an approved ProjectVersion to SUCCEEDED
  end-to-end; writes 5 calculation runs, 1 binding
  (verified), the **source archive row is persisted**, 1
  outbox SUCCEEDED event, AND a **completed `SchemeRun`**
  with the same binding id and the same five frozen
  snapshots in its envelope.
- Replay with same idempotency key returns
  IDEMPOTENT_REPLAY_SUCCEEDED with the same `(attempt_id,
  scheme_run_id)` tuple; no new rows.
- Demo coefficient path raises
  `CoefficientNotApprovedError`, attempt → BLOCKED, no
  calculation runs, no archive, no SchemeRun.

### 11.3 Integration PostgreSQL

- Same as SQLite above, on PostgreSQL.
- Concurrent replay with same idempotency key from two
  sessions: exactly one attempt reaches SUCCEEDED with one
  `SchemeRun`; the other receives
  `IDEMPOTENT_REPLAY_SUCCEEDED`.
- `outbox_event_id UNIQUE` and
  `orchestration_attempts.idempotency_key UNIQUE` both
  observe `IntegrityError` and are converted to
  `IdempotencyConflictError`.

### 11.4 Architecture tests

- The new orchestrator is NOT importable from
  `backend/src/cold_storage/evaluation/**` (architecture
  boundary test).
- The new orchestrator is NOT importable from
  `backend/tests/**` (test-only separation).
- All five calculator adapters implement `CalculatorPort`
  (interface check).
- The orchestrator's terminal record path includes the
  existing production `SchemeService` (no separate
  "ready output" writer remains in the call graph).

### 11.5 Race / idempotency tests

- Two concurrent calls with same idempotency key — one
  SUCCEEDED, one IDEMPOTENT_REPLAY_SUCCEEDED, both pointing
  to the same `SchemeRun`.
- Two concurrent calls to a non-idempotent path (different
  keys) — both reach SUCCEEDED with distinct attempt ids
  but identical binding hash and identical SchemeRun
  `frozen_envelope` hash.

### 11.6 Tamper tests

- Manual edit of one `result_snapshot` JSON column →
  `assert_snapshot_v1` detects mismatch →
  SourceBindingVerifier rejects → attempt FAILED, no
  SchemeRun.
- Manual edit of one slot in the binding → rejected, no
  SchemeRun.
- Manual edit of `combined_source_hash` →
  SourceBindingVerifier rejects, no SchemeRun.
- Manual edit of `SchemeRun.frozen_envelope` JSON after
  completion → `scheme_runs` row checksum mismatch on
  readback, treated as FAILED.

### 11.7 Missing coefficient tests

- ProjectVersion with no catalogue coefficient →
  CoefficientNotApprovedError → BLOCKED.
- ProjectVersion with `validity_status=unverified` →
  rejected → BLOCKED.

### 11.8 Demo coefficient rejection

- ProjectVersion + calculator adapter that internally
  emits demo warnings: the orchestrator rejects at the
  resolver step before calculator execution.

### 11.9 SourceBinding mismatch

- Mismatched `result_hash` between
  `CalculationRunRecord.result_hash` and the value bound
  in `SourceBindingRecord.slots` → rejected.
- Mismatched `combined_source_hash` between
  `SourceBindingRecord.combined_source_hash` and
  `SchemeRun.frozen_envelope_hash` → rejected on re-read.

### 11.10 SchemeService E2E

- Orchestrator invokes the production `SchemeService.run`
  with `(attempt_id, binding_id, five snapshots)`.
- `SchemeRun.scheme_status == SUCCEEDED` and
  `SchemeRun.frozen_envelope` carries the same five
  snapshots (byte-for-byte) and the same
  `combined_source_hash` as the source binding.
- `SchemeRun.database_backend` matches
  `OrchestrationRunAttempt.database_backend`.

### 11.11 Task 11 Phase B resumption test

- The evaluation runner calls the orchestrator (NOT an
  evaluation-owned producer) for `baseline-feasible` and
  reaches outcome = `success` because
  `SchemeRun.scheme_status == SUCCEEDED` with
  `frozen_envelope` carrying the same five snapshots and
  the same `combined_source_hash`. No `requires_review`
  warning reaches the runner.
- `manifest.json` and `expected/baseline-feasible.v1.json`
  remain frozen at Round 8 contracts.
- The runner still classifies `high-throughput-review` and
  `invalid-blocked` to their respective outcomes.

---

## 12. Rollout plan

The implementation MUST be delivered in ONE end-to-end PR
(or staged as a series of sub-PRs that are individually
non-functional until the final assembly PR is merged). No
follow-on "Phase C" bridge PR is contemplated; the
end-to-end SchemeService invocation is part of this task.

1. **Phase 0 — Schema (separate task)**: Alembic migration
   introducing `idempotency_key`, `database_backend`,
   `correlation_id`, `actor_principal_type`, `scheme_run_id`
   on `orchestration_attempts`, plus
   `frozen_envelope` and `database_backend` columns on
   `scheme_runs`.
2. **Phase 1 — Ports & adapters (this task's implementation,
   NOT authorized here)**: extend `application/ports.py`,
   add adapters per §4, freeze snapshot contract per §8,
   wire `SchemeServiceRunPort` adapter to the existing
   production `SchemeService`.
3. **Phase 2 — SourceBinding & archive & SchemeService**:
   introduce `frozen_envelope` of the binding, wire
   `SourceBindingVerifier`, `SourceArchiveBuilder`, AND the
   production `SchemeService.run` call into a single
   orchestrator flow. Idempotency-key replay returns the
   same `(attempt_id, scheme_run_id)` tuple.
4. **Phase 3 — Demo coefficient resolution**: thread
   `CoefficientContext` into the calculator adapters and
   rewrite `requires_review` propagation so demo warnings
   are filtered at the adapter boundary before
   `SchemeService.run`.
5. **Phase 4 — Task 11 Phase B unblock**: re-run the
   evaluation harness on `baseline-feasible`; expect
   outcome = `success` because SchemeRun SUCCEEDED.

Each phase MUST carry its own PR, its own PR-body `Frozen
Contract Authority SHA`, and its own implementation
authorization gate (mirroring the Task 10/11 governance).

---

## 12.1 Phase 2 closeout pointer (documentation only)

The Phase 2 implementation of this design was delivered
by **PR #38** (Task 11B Phase 2 — production calculation
ports and adapters). PR #38 is recorded as MERGED with a
governance deviation: the merge action occurred before an
independent review acceptance verdict was issued. The
canonical record of this closeout — including the exact
merge commit, the post-merge main CI run, the deviation
wording (English + 中文), the residual Issue #35
acceptance criteria, and the explicit NOT-AUTHORIZED list
for subsequent phases — is in:

- `docs/tasks/TASK-011B-phase2-closeout.md`

This section is a pointer only. It does not amend the
design contract in §1–§12, does not weaken the explicit
non-authorization statement in §13, and does not move the
project forward into Phase 3, SourceBinding + archive +
SchemeService E2E, approved non-demo coefficient
governance, Task 11 Phase B / C / D, or Task 12. All of
those remain NOT AUTHORIZED as recorded in §13 below and
in §4 of the closeout record.

Note: this design contract refers to a `TASK_BACKLOG.md`
that is not present in the repository. The closeout
record does not create that file; it records the same
technical / governance facts directly in
`docs/tasks/TASK-011B-phase2-closeout.md`.

---

## 13. Explicit non-authorization statement

**This document does NOT authorize any code, schema,
migration, or test implementation.** It is a design
contract only. The following are all explicitly NOT
authorized by this task:

- No commits to `backend/src/cold_storage/**` source code.
- No commits to `backend/tests/**`.
- No commits to `alembic/**` migrations.
- No commits to PR #21 (`codex/task-11-evaluation`).
- No commits to PR #32, PR #33, Issue #22, Issue #31.
- No `Ready` review, `merge`, or `close Issue` actions.
- No edits to evaluation fixtures, manifest, expected
  outputs, or runner.

Any implementation PR opened against this design MUST
copy the frozen-contract boilerplate from the Task 10/11
governance pattern ("Frozen Contract Authority SHA: ...",
"Implementation authorization: NOT GRANTED",
"Benchmark cases: NOT IMPLEMENTED") and MUST update
TASK_BACKLOG.md atomically alongside its Issue body and
PR body.

---

## 14. References (existing surface in repo)

This design reuses the following existing modules — see
their source for behavior:

- `backend/src/cold_storage/modules/orchestration/application/service.py`
  — Transaction A + C
- `backend/src/cold_storage/modules/orchestration/application/transaction_b.py`
  — Transaction B + `SourceBindingVerifier` +
  `_compute_combined_source_hash`
- `backend/src/cold_storage/modules/orchestration/application/source_snapshots.py`
  — typed snapshot models (ResultSnapshotV1, SourceSnapshotV1)
- `backend/src/cold_storage/modules/orchestration/application/source_archive_builder.py`
  — SourceArchiveBuilderPort
- `backend/src/cold_storage/modules/orchestration/application/outbox_dispatcher.py`
  — audit outbox envelope + dispatcher
- `backend/src/cold_storage/modules/orchestration/application/coefficient_contracts.py`
  — FrozenCoefficientResolutionCriteria + canonical_revision_ids
- `backend/src/cold_storage/modules/orchestration/domain/contracts.py`
  — OrchestrationRequestCommand, AttemptStatus, RequestStatus
- `backend/src/cold_storage/modules/orchestration/domain/fingerprint.py`
  — result_hash
- `backend/src/cold_storage/modules/orchestration/infrastructure/coefficient_resolver.py`
  — coefficient resolution infrastructure
- `backend/src/cold_storage/modules/schemes/application/service.py`
  — production `SchemeService` (the existing service that this
    orchestrator end-to-end invokes; the frozen envelope of the
    resulting SchemeRun is the terminal record)
- `docs/tasks/TASK-011-evaluation-pilot-readiness.md`
  — PR #21 / Task 11 Phase B context
- `docs/tasks/TASK-010-frontend-workbench.md`
  — Task 10 governance and frozen-contract precedent
