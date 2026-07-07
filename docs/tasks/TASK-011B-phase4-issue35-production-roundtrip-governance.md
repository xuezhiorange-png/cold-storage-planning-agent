# TASK-011B Phase 4 — Issue #35 Production Roundtrip Governance Contract

> **Status:** Design contract, frozen content, awaiting review.
> **Scope:** Design-only. Phase 4 implementation is NOT authorized by this document.
> **Branch:** `codex/issue-35-phase4-design-contract`
> **Baseline:** `origin/main` @ `f5c46a7b503cb6e50d6c245d168c24b98235e906` (PR #41 merge).

---

## 0. Governance reminders (mandatory)

The following statements are explicit and binding. They must be honored until separately amended.

- **Phase 4 implementation is not authorized by this contract.** This document freezes design intent only. Any implementation PR must follow the standard handoff: separate design freeze → review → separate implementation PR → separate review → separate merge.
- **Task 11 Phase B remains blocked** unless separately authorized. PR #21 remains Draft / Blocked / Not merged.
- **Task 12 is not started.**
- **Issue #35 remains OPEN** at the time of this contract. This document does not close Issue #35; it defines what closure would require.
- **PR #21 remains blocked** until the acceptance criteria in §16 and §17 are met.
- **Production boundary is enforced by tests, not documentation alone.** Every acceptance criterion in §16 must be backed by an automated test that fails when the criterion is violated.
- **No demo fallback, no latest-row fallback, no partial SourceBinding.** These are non-negotiable invariants of the production path.
- **`phase3_exceptions` must be retired** before Phase 4 implementation is merged. The temporary architecture exception must be replaced with a formal architecture boundary.

---

## 1. Scope

### 1.1 In-scope (Phase 4)

The following 14 items are explicitly in-scope for Phase 4:

1. Approved non-demo coefficient governance.
2. Full 5-stage database roundtrip on production coefficients.
3. Production coefficient source approval path.
4. SourceBinding + SchemeService full-link usage of approved non-demo coefficients.
5. SQLite / PostgreSQL parity.
6. No demo fallback.
7. No latest-row fallback.
8. No partial SourceBinding.
9. Audit / archive / historical resolver continuity.
10. Rollback and atomicity.
11. Fail-closed tests.
12. Power authority test.
13. Archive verification test.
14. `phase3_exceptions` retirement.

### 1.2 Non-goals (NOT in Phase 4)

- Calculator redefinition (formulas, coefficients, weights, thresholds, review rules).
- Migration redefinition.
- Evaluation manifest / expected outputs / fixtures / runner redefinition.
- PR #21 mutation.
- Task 11 Phase B / Phase C / Phase D resumption.
- Task 12 start.
- Issue #35 close.
- Replacement of the `transaction_b.py` execution path with a new engine.

### 1.3 Boundaries

- **Production boundary:** The boundary between "code is real" and "code is in a sandbox / demo / unverified" is enforced by `source_type` (demo / under_review / approved / retired) on every coefficient row.
- **Architecture boundary:** Application code must not import from `infrastructure.orm` or `infrastructure.repositories`. All cross-layer access goes through `application/ports.py` protocols.
- **Evaluation boundary:** The evaluation harness reads persisted results only. It must not call calculators or trigger recomputation.

---

## 2. Current mainline state

- `origin/main` HEAD = `f5c46a7b503cb6e50d6c245d168c24b98235e906` (PR #41 merge).
- PR #41 (Task 11B Phase 3: SourceBinding archive and SchemeService E2E) is merged.
- PR #42 (Issue #22E P2 test parity) is merged.
- Issue #22 (calculation orchestration prerequisite) is closed.
- Issue #35 (production roundtrip governance) is open.
- PR #21 (Task 11 evaluation) is open / draft / blocked.

### 2.1 What PR #41 closed

PR #41 completed the Phase 3 in-scope work: Phase 2 adapter calculator port, ProductionSourceBindingUseCase, actor / correlation_id threading, composition-root wiring, SourceBinding archive, SchemeService E2E in the zone stage, SQLite / PostgreSQL mirror tests, and architecture tests for the composition root.

### 2.2 What PR #41 did NOT close

- Full 5-stage database roundtrip on production coefficients.
- Approved non-demo coefficient governance.
- Power authority test, archive verification test, and the 9 fail-closed test cases.
- `phase3_exceptions` retirement.
- PR #21 rebase / re-evaluation on the new coefficient path.

### 2.3 What PR #42 closed

PR #42 closed the P2 follow-up for Issue #22E: PG parity tests for archive resolver and tamper coverage, and the 4 make-test-pg harness commands.

### 2.4 What PR #42 did NOT close

- Issue #35 (production roundtrip governance).
- Any acceptance criteria listed in §16 of this document.

---

## 3. Approved non-demo coefficient governance

### 3.1 Coefficient lifecycle

Every coefficient row carries a `source_type` and `validity_status` with the following states:

| `source_type` | Meaning | Production eligible? |
|---|---|---|
| `demo` | Shipped as placeholder; unverified | NO |
| `under_review` | Awaiting review | NO |
| `approved` | Reviewed and signed off | YES |
| `retired` | Superseded | NO (but historical lookups still work) |

| `validity_status` | Meaning |
|---|---|
| `unverified` | No review recorded |
| `verified` | Review recorded; sign-off present |
| `expired` | Review was valid until a cutoff date and is now past |

### 3.2 Approval workflow

Approval is a deliberate action recorded in a dedicated audit log:

1. Submit-for-review creates a row with `source_type=under_review`, `validity_status=unverified`, `requires_review=true`.
2. A reviewer with the `coefficient.reviewer` role signs off, transitioning to `source_type=approved`, `validity_status=verified`, `requires_review=false`.
3. The approval is recorded in `coefficient_approval_log` with reviewer, timestamp, source citation, and a payload hash.
4. Approval is non-retroactive: a coefficient is eligible for production only from the approval timestamp forward.

### 3.3 Audit trail

Every transition writes a row to `coefficient_audit_log` with: actor, correlation_id, old state, new state, timestamp, reason. The log is append-only and tamper-evident (no DELETE, only INSERT).

### 3.4 Approval coverage requirement

Every required coefficient (zone, cooling_load, equipment, power, investment) must have an `approved` row in the production coefficient pool. The application fails closed at startup if any required stage is missing its approved coefficient.

### 3.5 Source citation

Every approved coefficient must carry a `source_citation` field (DOI, standard number, or named internal reference). Citations without an actual reference are invalid and the approval is rejected.

### 3.6 Approval state machine diagram

```
demo ──submit──▶ under_review ──approve──▶ approved ──retire──▶ retired
                                          │
                                          └──revert──▶ under_review
```

---

## 4. Full 5-stage database roundtrip on production coefficients

### 4.1 Required persistence

For every successful SourceBinding, the system must persist:

| Table | Count | Notes |
|---|---|---|
| `calculation_run` | 5 | One per stage (zone, cooling_load, equipment, power, investment) |
| `source_binding` | 1 | Verified; binds all 5 stages |
| `scheme_run` | 1 | Consumes the verified SourceBinding |
| `source_archive` | 1 | Archive of the source payload with `payload_hash` |

All 5 stages must run on approved non-demo coefficients. If any stage runs on a demo coefficient, the entire roundtrip fails closed.

### 4.2 Roundtrip invariants

- A `source_binding` row is committed only if all 5 `calculation_run` rows are committed and verified.
- A `scheme_run` row is committed only if its `source_binding_id` references a verified `source_binding`.
- A `source_archive` row is committed with the same transaction as the `source_binding`; the archive's `payload_hash` must match the recomputed hash of the archived payload.
- If any stage fails, the entire transaction rolls back. No `source_binding`, `scheme_run`, or `source_archive` row is left behind.

### 4.3 Atomicity tests

Two test contracts are required:

- **Happy path:** a complete roundtrip produces exactly 5 `calculation_run` + 1 `source_binding` + 1 `scheme_run` + 1 `source_archive` row.
- **Failure path:** injecting a failure at stage 3 (or any other stage) leaves zero `source_binding`, zero `scheme_run`, and zero `source_archive` rows. The `calculation_run` rows that completed before the failure are also rolled back (PK-set zero-delta invariant).

### 4.4 Idempotency

Re-running the roundtrip with the same input and the same coefficient versions must produce the same `source_binding` and `scheme_run` rows (same identity, same `combined_source_hash`). Idempotency tests cover both SQLite and PostgreSQL.

---

## 5. Production coefficient source approval path

### 5.1 Coefficient pool separation

The production coefficient pool is physically separate from the demo coefficient pool. The pool key is `(stage_name, calculation_type, source_type)`. The application selects from `source_type=approved` exclusively when running in production mode.

### 5.2 `CoefficientApprovalService`

A new service owns the approval state machine:

- `submit_for_review(coefficient_id, actor, correlation_id)` — transitions demo → under_review.
- `approve(coefficient_id, reviewer, source_citation, correlation_id)` — transitions under_review → approved.
- `retire(coefficient_id, actor, reason, correlation_id)` — transitions approved → retired.
- `revert(coefficient_id, actor, reason, correlation_id)` — transitions approved → under_review.
- `list_approved(stage_name, calculation_type)` — returns current approved coefficients for a stage.

### 5.3 Fail-closed startup

On application startup, the production composition root must verify:

- For each of the 5 required stages, there is at least one `source_type=approved` coefficient with `validity_status=verified`.
- If any required stage is missing, startup aborts with a typed `MissingApprovedCoefficientError`.

### 5.4 Stale approval

An approval carries a `valid_until` timestamp. If the current time is past `valid_until`, the approval is treated as `expired` even if `validity_status=verified`. The application fails closed when the only approved coefficient for a stage is expired.

### 5.5 Source citation validation

The `source_citation` field is non-nullable on approved rows. Citations must match a known pattern: `DOI:10.NNNN/...`, `STANDARD:ISO-NNNN`, or `INTERNAL:REF-...`. Other formats are rejected at approval time.

### 5.6 Approval rejection paths

- Reject if coefficient already retired.
- Reject if the same `coefficient_id` has a pending approval request from the same reviewer.
- Reject if `source_citation` does not match a known pattern.
- Reject if the actor lacks the `coefficient.reviewer` role.

---

## 6. SourceBinding and SchemeService trust boundary

### 6.1 Production-path strictness

The production SourceBinding path is strict in the following ways:

- Every stage slot must be filled by an approved coefficient's calculation result.
- The `combined_source_hash` must match the recomputed hash of the bound slots.
- The `project_id` on the binding must match the `project_id` on all 5 `calculation_run` rows.
- The `calculation_type` on each slot must match the expected `calculation_type` for that stage.
- The `attempt_status` on each `calculation_run` must be `COMPLETED`; `PENDING` or `RUNNING` rows are rejected.
- `requires_review=true` rows are not used in the production path; they fail closed.

### 6.2 SchemeService E2E

The production SchemeService consumes a verified SourceBinding. The full E2E test:

- Starts from an approved-coefficient pool.
- Runs the 5-stage roundtrip.
- Produces a `scheme_run` that references the verified `source_binding`.
- Verifies the scheme's `installed_power` comes from the power slot, not from any field on the equipment slot.

### 6.3 Power authority test

The `installed_power` field on the `scheme_run` must come from the power slot's calculation result, not from a compressor power field on the equipment slot. A test feeds an equipment slot with an inflated compressor power and asserts the resulting `scheme_run.installed_power` matches the power slot, not the equipment slot.

### 6.4 Archive verification

After the `source_archive` row is committed, a subsequent read recomputes the `payload_hash` from the stored payload. If the recomputed hash does not match, the read returns a typed `TamperedArchiveError` and the binding is treated as untrusted.

---

## 7. No-fallback requirements

The following fallbacks are forbidden in the production path. Each is enforced by a test.

- **No demo fallback.** The application must not select a `source_type=demo` coefficient in production mode. A test that injects only demo coefficients asserts that startup aborts with `MissingApprovedCoefficientError`.
- **No latest-row fallback.** The application must not select a coefficient by "latest" or "most recent" timestamp when an explicit identity is required. A test that injects an unverified row as the latest asserts that the application fails closed rather than selecting it.
- **No partial SourceBinding.** A SourceBinding is only valid if all 5 stages are verified. A test that injects a binding with one missing stage asserts that the binding is rejected.
- **No skipping the verifier.** The SourceBindingVerifier must be invoked on every binding before it is committed. A test that bypasses the verifier asserts that the commit fails.
- **No suppressing `requires_review`.** A test that sets `requires_review=false` on a coefficient that is otherwise unapproved asserts that the production path rejects the row.
- **No raw ORM fabrication.** `calculation_run` rows must be created through the application service, not via direct ORM writes. A test that fabricates a `calculation_run` outside the Transaction B boundary asserts that the binding rejects the row.
- **No implicit coefficient resolution.** A test that requests a coefficient without an explicit `coefficient_id` and without a default asserts that the request fails closed.

---

## 8. Audit / archive / historical resolver continuity

### 8.1 SourceBindingVerifier fail-closed

The SourceBindingVerifier must:

- Reject bindings with missing slots.
- Reject bindings with a tampered `combined_source_hash`.
- Reject bindings with a wrong `project_id`.
- Reject bindings with a wrong `calculation_type` on any slot.
- Reject bindings where any underlying `calculation_run.attempt_status != COMPLETED`.
- Reject bindings where any underlying `calculation_run.requires_review == true`.

Each rejection is a typed exception, not a generic `Exception`. The 9 fail-closed test cases in §11 cover all of these.

### 8.2 Historical source resolver

The historical source resolver returns the source binding that was active for a given project version at a given timestamp. Strictness:

- The resolver must not return a binding whose `created_at` is after the requested timestamp.
- The resolver must not return a binding that was superseded by a later binding.
- The resolver must not return a binding whose underlying `calculation_run` rows have been deleted.

### 8.3 Archive payload_hash recompute

After read, the archive's `payload_hash` is recomputed from the stored payload. A mismatch raises `TamperedArchiveError`. The binding is treated as untrusted for the remainder of the session.

### 8.4 Audit log continuity

The audit log is append-only. The schema rejects `UPDATE` and `DELETE` on `coefficient_audit_log`. A migration-level test asserts that any attempt to update or delete raises a `DatabaseError` from the engine.

---

## 9. Rollback and atomicity

### 9.1 PK-set zero-delta invariant

If a 5-stage roundtrip fails at any stage, the set of `calculation_run`, `source_binding`, `scheme_run`, and `source_archive` row PKs added or removed by the failed transaction is empty. The `calculation_run` rows completed before the failure are rolled back.

### 9.2 Outer transaction rollback

The roundtrip is wrapped in a single outer transaction. Any uncaught exception inside the roundtrip triggers a rollback. The post-failure state is byte-identical to the pre-roundtrip state, except for `coefficient_audit_log` rows (which are append-only and always persist).

### 9.3 Concurrent roundtrip isolation

Two concurrent roundtrips on the same project version must not interleave writes that violate the PK-set zero-delta invariant. The implementation uses `SELECT ... FOR UPDATE` or equivalent to lock the project's source-binding slot for the duration of the roundtrip.

### 9.4 Idempotent re-run

Re-running a failed roundtrip with the same input must produce the same final state as a successful first run. Idempotency tests cover both the happy path and the failure path.

---

## 10. SQLite / PostgreSQL parity test matrix

The following table is the contract for the test matrix. Every row must pass on both backends. CI runs the matrix on push and on pull_request.

| Test group | SQLite | PostgreSQL |
|---|---|---|
| Roundtrip happy path | required | required |
| Roundtrip failure path (stage 3) | required | required |
| Roundtrip failure path (stage 5) | required | required |
| Idempotent re-run | required | required |
| Concurrent roundtrip isolation | required | required |
| SourceBindingVerifier fail-closed (9 cases) | required | required |
| Power authority test | required | required |
| Archive verification (tampered) | required | required |
| Audit log append-only | required | required |
| PK-set zero-delta | required | required |
| CoefficientApprovalService state machine | required | required |
| Missing approved coefficient (startup) | required | required |
| Stale approval (expired) | required | required |
| Source citation validation | required | required |

A test that passes on only one backend fails CI.

---

## 11. Fail-closed tests

The following 9 fail-closed test cases are required. Each is a single test that injects a specific violation and asserts the roundtrip fails with a typed exception.

1. **Missing slot.** Bind 4 stages; attempt to commit. Assert `SourceBindingVerificationError`.
2. **Tampered `combined_source_hash`.** Commit a binding; rewrite the `combined_source_hash` to a different value; attempt to re-verify. Assert `SourceBindingVerificationError`.
3. **Wrong `project_id` on binding.** Bind 5 stages for project A; commit a binding with `project_id=B`. Assert `SourceBindingVerificationError`.
4. **Wrong `calculation_type` on a slot.** Bind a slot with a calculation_type that does not match the expected type for that stage. Assert `SourceBindingVerificationError`.
5. **`attempt_status=PENDING`.** Create a `calculation_run` with `attempt_status=PENDING`; attempt to bind. Assert `SourceBindingVerificationError`.
6. **`requires_review` suppression.** Set `requires_review=false` on a coefficient that is not approved. Assert the production path rejects the row with `UntrustedCoefficientError`.
7. **Raw ORM fabrication.** Bypass the application service and write a `calculation_run` directly via the ORM. Assert the binding rejects the row.
8. **Demo seed records.** Inject a `source_type=demo` row as the only candidate for a stage in production mode. Assert the roundtrip fails with `MissingApprovedCoefficientError` (or refuses to start).
9. **Latest-row fallback.** Inject an unverified row with the latest `created_at`. Assert the application fails closed rather than selecting it (no implicit "latest" selection).

---

## 12. Power authority test

The `installed_power` field on `scheme_run` must come from the power slot, not from any compressor power field on the equipment slot. The test:

- Sets up an equipment slot with an inflated compressor power (e.g., 999 kW).
- Sets up a power slot with a correct calculation result (e.g., 50 kW).
- Runs the roundtrip.
- Asserts `scheme_run.installed_power == 50`, not 999.

The test runs on both SQLite and PostgreSQL.

---

## 13. Archive verification test

After a successful roundtrip, the test:

- Reads the `source_archive` row.
- Tampers with one byte of the archived payload.
- Recomputes the `payload_hash`.
- Asserts the recomputed hash does not match the stored hash.
- Asserts the binding is treated as untrusted (subsequent reads raise `TamperedArchiveError`).

The test runs on both SQLite and PostgreSQL.

---

## 14. `phase3_exceptions` retirement

### 14.1 Current state

PR #41 introduced a temporary architecture exception (`phase3_exceptions`) to allow `production_source_binding.py` to import `OrchestrationIdentityRecord` directly. The exception is documented and time-bounded.

### 14.2 Retirement plan

The retirement is a 4-step process:

1. **Introduce `IdentityReadPort` in `application/ports.py`.** Define a protocol that exposes the operations `production_source_binding.py` needs from the orchestration identity layer.
2. **Implement the port in `infrastructure.repositories`.** Add a SQLAlchemy adapter that fulfills the protocol using the `OrchestrationIdentityRecord` table.
3. **Inject the port into `ProductionSourceBindingUseCase.__init__`.** Update the use case to accept the port and call it instead of the direct ORM import.
4. **Remove the import and the `phase3_exceptions` set from the architecture test.** With the import removed, the architecture test's exception set is no longer needed and is deleted.

### 14.3 Test for retirement

A test asserts that after the retirement, the file `production_source_binding.py` does not import from `cold_storage.modules.orchestration.infrastructure.*`. The architecture test is updated to require this constraint without the `phase3_exceptions` exception.

### 14.4 Sequencing

The retirement is a prerequisite for closing Issue #35. It is implemented as part of Phase 4, not as a separate issue.

---

## 15. Architecture boundary requirements

### 15.1 Application layer

- Application code (`service.py`, `transaction_b.py`, `production_source_binding.py`, `source_binding_assembly.py`, `production_calculation/`) must not import from `infrastructure.orm` or `infrastructure.repositories`.
- All cross-layer access goes through `application/ports.py` protocols.
- After Phase 4 retirement of `phase3_exceptions`, no application file imports from infrastructure.

### 15.2 Ports

- `application/ports.py` defines the protocols: `IdentityReadPort`, `SourceBindingReadPort`, `SourceBindingWritePort`, `CalculationRunReadPort`, `SchemeRunWritePort`, `ArchiveReadPort`, `ArchiveWritePort`, `VerificationReadPort`, `CoefficientReadPort`, `CoefficientApprovalService` (or equivalent).
- Each port is implemented in `infrastructure.repositories` or `infrastructure.services`.

### 15.3 Domain layer

- Domain code must not depend on FastAPI, SQLAlchemy, Redis, or model SDKs.
- Domain code must not perform network IO.

### 15.4 Repository

- Repositories do not self-commit. They expose `add` / `get` / `list` / `update` operations; the application service owns the transaction boundary.

---

## 16. Acceptance criteria for Issue #35 close

The following 15 criteria are required for Issue #35 to be closed. Each is backed by a test that fails when the criterion is violated.

1. Approved non-demo coefficient governance is implemented and frozen (commit SHA recorded).
2. Full 5-stage database roundtrip on production coefficients is implemented and tested.
3. SQLite / PostgreSQL parity tests pass on both backends (CI green on both).
4. No demo fallback is enforced in production (fail-closed test passes on both backends).
5. No latest-row fallback is enforced in production (fail-closed test passes on both backends).
6. No partial SourceBinding is enforced in production (fail-closed test passes on both backends).
7. Audit / archive / historical resolver continuity is end-to-end verified (tampered archive fails closed on both backends).
8. `phase3_exceptions` is retired; the architecture test passes without the exception set; the file no longer imports from infrastructure.
9. All 9 fail-closed test cases from §11 are implemented and pass on both backends.
10. Rollback / atomicity is fully proven (PK-set zero-delta test passes on both backends; mid-pipeline failure leaves 0 `source_binding` / 0 `scheme_run` / 0 `source_archive`).
11. Power authority test is implemented and passes on both backends.
12. Archive verification test is implemented and passes on both backends.
13. The Phase 4 implementation PR is merged to `main`.
14. The Phase 4 post-merge CI run is green on all 4 jobs (frontend, compose-config, backend-sqlite, backend-postgresql).
15. The preconditions for unblocking PR #21 / Task 11 Phase B are explicitly stated in the implementation PR's body, with a decision recorded (merge PR #21 or defer with reason).

Closing Issue #35 requires all 15 criteria to pass. A single missing criterion blocks the close.

---

## 17. Acceptance criteria for unblocking PR #21

PR #21 (Task 11 evaluation) can be marked ready and merged only when the following 6 criteria are met:

1. Issue #35 Phase 4 implementation is merged to `main` and post-merge CI is green.
2. PR #21 is rebased onto the post-Phase-4 `main` and the rebase is clean.
3. PR #21's evaluation manifest / expected outputs / fixtures / runner are consistent with the production path defined by this contract (no demo coefficients, no latest-row fallback, no partial binding).
4. PR #21's evaluation is baseline-feasible: the evaluation no longer depends on demo coefficients.
5. PR #21's CI is green on all 4 jobs.
6. Charles explicitly authorizes marking PR #21 ready and merging it.

Until all 6 are met, PR #21 remains Draft / Blocked / Not merged.

---

## 18. Acceptance criteria for Task 11 Phase B resumption

Task 11 Phase B can be resumed only when the following 7 criteria are met:

1. Issue #35 Phase 4 implementation is merged to `main`.
2. Issue #35 close review is approved (all 15 criteria in §16 are met).
3. PR #21 unblock review is approved (all 6 criteria in §17 are met).
4. PR #21 is merged, or an explicit deferred-reason is recorded.
5. Task 11 Phase B's baseline success criteria are explicitly defined and recorded in a separate document.
6. Task 11 Phase C / D and Task 12 are not automatically authorized by the Phase B resumption; they each require their own design freeze and explicit authorization.
7. Charles explicitly authorizes starting Task 11 Phase B.

Until all 7 are met, Task 11 Phase B remains blocked.

---

## 19. Explicit deferred items

The following 12 items are explicitly deferred out of Phase 4 and into a future task or issue. They are listed here to prevent scope creep.

1. Calculator formula redefinition (e.g., changing the cooling-load formula).
2. Coefficient value updates (Phase 4 uses the same demo coefficient values as Phase 2; the approval workflow is what changes, not the values).
3. Threshold redefinition.
4. Weight rule redefinition.
5. Review rule redefinition.
6. Migration redefinition beyond what's required for the architecture test retirement.
7. Evaluation manifest redefinition.
8. Expected outputs redefinition.
9. Fixtures redefinition.
10. Runner redefinition.
11. Task 12 start.
12. Task 11 Phase C / D start.

Each of these requires its own design freeze and explicit authorization.

---

## 20. Stop conditions

The following 10 conditions halt Phase 4 immediately. Reporting one of these is a stop, not a continue.

1. A production code change appears in the Phase 4 implementation PR (this contract is design-only).
2. A test or migration change appears in the Phase 4 implementation PR beyond what the design contract authorizes.
3. Issue #35 is closed or moved to a non-OPEN state before all 15 criteria in §16 are met.
4. PR #21 is marked ready or merged before all 6 criteria in §17 are met.
5. CI on the Phase 4 branch or `main` is not green.
6. The design scope expands into Task 12 territory.
7. The approved non-demo coefficient governance cannot be demonstrated (no approved row exists for any required stage in a test).
8. This design contract and the Issue #35 acceptance criteria conflict.
9. A latest-row or demo fallback is permitted in any production path.
10. A partial SourceBinding is permitted in any production path.

A stop is reported with: condition number, evidence (file path, test name, log snippet, or commit SHA), and a recommendation for next steps.

---

## 21. References

- PR #41 (Task 11B Phase 3): merged at `f5c46a7b503cb6e50d6c245d168c24b98235e906`.
- PR #42 (Issue #22E P2 test parity): merged at `49389d566d78e23d3698f6ac9950a6ade56d2774`.
- Phase 3 design contract: `docs/tasks/TASK-011B-phase3-sourcebinding-schemeservice-e2e.md`.
- Issue #35: open at the time of this contract.
- Issue #22: closed.
- AGENTS.md: project-wide rules.

---

## 22. Sign-off

This contract is design-only. It does not authorize implementation. Implementation requires:

1. A separate implementation PR.
2. A separate review cycle.
3. A separate merge.
4. A post-merge CI green.
5. All 15 criteria in §16 verified.

Until those happen, this contract remains a design intent document, and Issue #35 remains OPEN.
