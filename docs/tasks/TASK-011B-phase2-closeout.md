# Task 11B Phase 2 — Technical Closeout & Governance Record

Status: **closeout / governance record — implementation NOT authorized**

> **This document is documentation-only.**
> It records the technical closeout of Task 11B Phase 2
> (PR #38) and a governance deviation that occurred between
> the last pre-merge closeout report and the merge. It
> does NOT authorize any code, schema, migration, test,
> workflow, frontend, evaluation, coefficient, formula,
> threshold, weight, or review-rule change.

This document is the canonical project-side record of:

- the technical artifacts delivered by PR #38;
- the CI evidence that supports the merge;
- a governance deviation that must be tracked for future
  task sequencing;
- the residual acceptance criteria still required to
  close Issue #35;
- the explicit list of phases that remain NOT AUTHORIZED.

It is intentionally separate from:

- PR #21 (`codex/task-11-evaluation`, Task 11 evaluation
  pilot readiness, Draft / Open / Not merged, BLOCKED);
- Issue #22 (transport-B E2E persistence, CLOSED via PR #33);
- Issue #31 (transactional audit outbox dispatcher, CLOSED
  via PR #32);
- the Phase 1 / Phase 2 design contract in
  `docs/tasks/TASK-011B-production-calculation-orchestration-prerequisite.md`.

---

## 1. Technical closeout

### 1.1 Merge record

- Task: **Task 11B Phase 2 — production calculation
  ports and adapters**
- PR: **#38**
- Branch: `codex/task-011b-phase2-ports-adapters`
- base SHA: `2266131c30aa4aea795d275be3e1b3bef3fccedf`
  (PR #39 merge commit, frontend test-isolation fix)
- pre-merge head SHA: `3298f44418aeb84239dec9c70def200a7016fced`
- merge commit: **`fbd715603b7673fd8bea9b4076477cdaa7f4a37c`**
- merged_at: `2026-07-06T10:01:16Z`
- merged_by: `xuezhiorange-png` (Charles Cheng)
- changedFiles: 16
- additions / deletions: +3412 / -0
- origin/main HEAD after merge: `fbd715603b7673fd8bea9b4076477cdaa7f4a37c`
  (== PR #38 merge commit; origin/main did not advance
  further at the time this closeout record was authored)

### 1.2 Post-merge main CI

- run id: **`28783522794`**
- event: `push`
- head SHA: `fbd715603b7673fd8bea9b4076477cdaa7f4a37c`
  (PR #38 merge commit, headBranch `main`)
- created_at: `2026-07-06T10:01:19Z`
- updated_at: `2026-07-06T10:21:03Z`
- final status: `completed`
- final conclusion: **`success`**

4 jobs conclusion:

| Job | dbId | conclusion |
| --- | --- | --- |
| compose-config | 85344574649 | success |
| frontend       | 85344574700 | success |
| backend-sqlite | 85344574684 | success |
| backend-postgresql | 85344574671 | success |

backend-postgresql step conclusions (dbId 85344574671):

- Set up job / Initialize containers /
  Run actions/checkout@v4 / Run astral-sh/setup-uv@v4 /
  Backend install: success
- Alembic upgrade (PostgreSQL): success
- Alembic downgrade/re-upgrade roundtrip (PostgreSQL): success
- Install CJK font: success
- PostgreSQL integration tests: success
- PostgreSQL attempt race stability (10x): success
- Backend tests (PostgreSQL): success
- Post Run / Stop containers / Complete job: success

backend-sqlite step conclusions (dbId 85344574684):

- Set up job / checkout / setup-uv / Backend install:
  success
- Alembic upgrade (SQLite): success
- Alembic downgrade/re-upgrade roundtrip (SQLite): success
- Install CJK font: success
- Backend tests (SQLite): success
- Backend architecture tests: success
- Backend lint: success
- Backend typecheck: success
- Post Run: success

frontend step conclusions (dbId 85344574700):

- Set up job / checkout / setup-node / install: success
- Frontend quality: success
- Post Run / Complete job: success

URL:
<https://github.com/xuezhiorange-png/cold-storage-planning-agent/actions/runs/28783522794>

### 1.3 Pre-merge CI (kept on file for the merge evidence)

These are the CI runs that gated the merge of PR #38 and
that are referenced in the PR body and in the pre-merge
closeout report. They are recorded here for completeness.

PR event run **`28780519638`** (event=pull_request,
head=`3298f44`, run_attempt=1): final conclusion `success`,
4/4 jobs green on first attempt.

Push run **`28780516552`** (event=push, head=`3298f44`,
run_attempt=2): final conclusion `success`. The
backend-sqlite job on attempt 1 (dbId `85334759869`) failed
on a pre-existing flake in
`tests/test_reports/test_waiter_concurrent.py::TestDefaultWaiterFastAPIConvergence::test_default_waiter_two_fastapi_requests_converge`
(a 2-thread `threading.Barrier(2)` concurrent POST stress
test against
`/api/v1/reports/{id}/revisions/{n}/render` that
intermittently returns 404 due to a known render-waiter
race). The test file is not modified by PR #38, PR #39, or
the main-rebase merge. A targeted rerun of
`gh run rerun 28780516552 --job 85334759869` produced
attempt-2 dbId `85339738055` with conclusion `success`
(2414 / 2414 passed). No code, test, workflow, or schema
change was made during the rerun. The PR event run
backend-sqlite (dbId `85334769753`) passed 2414 / 2414 on
first attempt, confirming the pre-existing flake
character of the failure.

### 1.4 Delivered scope (PR #38)

PR #38 ships the Task 11B Phase 2 ports & adapters
subpackage only. It delivers:

- New application port contracts:
  - `ApprovedProjectVersionReadPort`
  - `ZonePlanningCalculationPort`
  - `CoolingLoadCalculationPort`
  - `EquipmentCapabilityCalculationPort`
  - `InstalledPowerCalculationPort`
  - `InvestmentCalculationPort`
  - `CalculationRunPersistencePort` (interface only)
- Adapter wrappers (5):
  - `ZonePlanningAdapter` (wraps `ColdRoomZonePlanner`)
  - `CoolingLoadAdapter` (wraps `calculate_cooling_load`
    via the existing `build_cooling_load_input` boundary)
  - `EquipmentCapabilityAdapter` (wraps
    `calculate_equipment_capability`)
  - `InstalledPowerAdapter` (wraps
    `calculate_installed_power`)
  - `InvestmentAdapter` (wraps `InvestmentEstimator`)
- DTOs / contracts:
  - `ApprovedProjectVersionSnapshot`
  - `CalculatorInputProjection`
  - `AdapterResult` (with `payload`, `content_hash`,
    `requires_review`, `warnings`, `blockers`,
    `provenance`, `calculator_name`,
    `calculator_version`)
  - `AdapterWarning` / `AdapterBlocker` / `AdapterProvenance`
  - `CalculationRunDraft` (pure value object representing
    a future `CalculationRunRecord`)
  - `ProductionCalculationErrorCode`
    (`PROJ_VERSION_NOT_APPROVED`,
    `PROJ_INPUT_INVALID`, `CALCULATOR_REJECTED_INPUT`,
    `CALC_OUTPUT_REVIEW_REQUIRED`,
    `ADAPTER_CONTRACT_VIOLATION`)
- A pure `CalculationRunDraft` mapper.
- An in-memory `InMemoryCalculationRunPersistencePort`
  test double only.
- 78 unit tests, 20 integration tests, 9 architecture
  tests (149 total), covering:
  - adapter wrapping against the frozen calculator
    surface
  - `CalculatorInputProjection` ↔ DTO mapping
  - threading helper invariants
  - error code model
  - contract validator behavior
  - end-to-end pipeline (adapter → mapper → in-memory
    port)
  - architecture boundaries (no evaluation imports, no
    `SchemeService` invocation, no `SourceBinding`
    generation, no outbox materialization, no formula
    mutation, no full orchestrator, no ORM, calculator
    source files unchanged)

### 1.5 Not delivered (PR #38)

PR #38 explicitly does **not** deliver:

- No full orchestrator implementation.
- No `SourceBinding` generation.
- No `SourceArchive` write.
- No `SchemeService` end-to-end E2E invocation.
- No approved non-demo coefficient governance /
  resolver.
- No `CalculationRunRecord` ORM row written.
- No outbox materialization event.
- No evaluation backdoor or evaluation-owned seam.
- No latest-row fallback.
- No raw ORM fabrication of production state.
- No production calculator formula / threshold / weight /
  review rule mutation.
- No migration.
- No PR #21 / Issue #35 / Issue #22 / Issue #31 changes.
- No frontend test / source / build change (the only
  frontend delta in the PR #38 branch came from the main
  rebase that included PR #39's `workbench.test.ts`
  state-isolation fix; PR #38 itself does not own it).
- No Task 11 Phase B resumption.
- No workflow change.

The above non-delivery list is itself part of the closeout
record so that no later reading of the merge can mistake
Phase 2 ports & adapters for a green-light to Phase 3.

---

## 2. Governance deviation record

> **PR #38 was merged before independent review
> acceptance. This is a governance/process deviation.**

**中文口径**：

> **PR #38 在独立工程复审正式通过前已被合并，属于
> 治理流程偏差。当前技术收口完成，但不追认该合并流程
> 为合规。**

### 2.1 What happened

In the pre-merge closeout report circulated just before
this record was authored, PR #38 was reported as
Draft / Open / Not merged with 4/4 jobs green on both the
PR event run (`28780519638`) and the push run
(`28780516552`, attempt 2). The review verdict at that
time was "整改停止，等待 PR #38 独立工程复审". After that
closeout was delivered, and **before** an independent
review acceptance was issued, PR #38 was merged at
`2026-07-06T10:01:16Z` (merge commit
`fbd715603b7673fd8bea9b4076477cdaa7f4a37c`,
merged_by `xuezhiorange-png`).

### 2.2 What this record does

- Records the deviation as a fact, in both English and
  Chinese, with the exact wording above.
- Distinguishes technical state from governance state:
  - **Technical state** — pre-merge CI was green;
    post-merge main CI run `28783522794` is also 4/4
    green; the merge commit physically exists and
    contains the Phase 2 ports & adapters subpackage
    exactly as scoped in PR #38.
  - **Governance state** — the merge action occurred
    prior to the formal independent review acceptance
    conclusion; the merge flow is therefore not ratified
    as compliant. The deviation is logged here so that
    future task sequencing can reference it.
- Does **not** retroactively approve the merge flow. The
  technical closeout is recorded; the governance flow is
  recorded as a deviation. These two records are not
  conflated.

### 2.3 What this record does not do

- Does not change PR #38's `isDraft=false` /
  `state=MERGED` GitHub state. That state is what it is;
  the closeout flow does not reopen, revert, reset,
  force-push, or otherwise rewrite history.
- Does not modify the PR #38 body or title.
- Does not re-evaluate PR #38's own technical content.
- Does not authorise any follow-on implementation.

### 2.4 Forward implication

Future task sequencing MUST treat the deviation as a
standing rule, not a one-off: the project requires an
explicit independent review acceptance verdict on any
Phase 2 / Phase 3 implementation PR **before** the merge
button is pressed. Any closeout of a future implementation
PR that arrives with `isDraft=false` / `state=MERGED` /
no prior independent review verdict MUST be recorded the
same way this one is.

---

## 3. Issue #35 status

**Issue #35 remains OPEN.**

Phase 2 merge does **NOT** close Issue #35.

Issue: **#35** — "Production prerequisite: formal
calculation orchestration path for Task 11 Phase B
baseline success"

Issue #35 acceptance criteria still require (i.e. the
remaining open work, none of which is in scope for this
closeout record):

- End-to-end orchestration that produces a `SchemeRun`
  via `SchemeService.run(...)` from an approved project
  version, with the produced `SchemeRun` consumed by the
  PR #21 evaluation harness as a real production producer
  (path A, as designated in
  `docs/tasks/TASK-011B-production-calculation-orchestration-prerequisite.md`).
- `SourceBinding` generation for the orchestration run.
- `SourceArchive` write.
- `SchemeService` end-to-end E2E coverage.
- Approved non-demo coefficient governance / resolver.
- Task 11 Phase B resumption test — the
  `EVAL_PRODUCTION_PIPELINE_PREREQUISITE_MISSING` harness
  blocker must clear, the
  `baseline-feasible` attempt must pass on the SQLite
  evaluation baseline AND on the PostgreSQL evaluation
  baseline, and the result must be reproducible in CI.
- SQLite **and** PostgreSQL end-to-end acceptance.

None of the above is delivered by PR #38. PR #38 is the
ports & adapters subpackage only.

---

## 4. Subsequent phase status (NOT AUTHORIZED)

The following remain NOT AUTHORIZED at the time this
closeout was authored. None of these is enabled by the
PR #38 merge, by the post-merge CI green, or by this
closeout record. Each of these requires its own separate
design, contract freeze, and authorization round, in the
same governance pattern that produced TASK-011B Phase 1
and Phase 2.

- **Phase 3** — NOT AUTHORIZED
- **SourceBinding + archive + SchemeService E2E** — NOT
  AUTHORIZED
- **approved non-demo coefficient governance** — NOT
  AUTHORIZED
- **Task 11 Phase B / C / D** — NOT AUTHORIZED
- **Task 12** — NOT AUTHORIZED

The PR #21 evaluation branch
(`codex/task-11-evaluation`, head `7822581eeee4c590b4ed9b1e3c46c1cde5490098`)
remains **Draft / Open / Not merged / BLOCKED**. The
`EVAL_PRODUCTION_PIPELINE_PREREQUISITE_MISSING` harness
blocker is not yet cleared. No PR #21 change is
authorised by this closeout.

---

## 5. PR / Issue governance ledger at the time of this record

| Item | Identifier | State |
| --- | --- | --- |
| PR #38 | Task 11B Phase 2 ports & adapters | MERGED (with deviation, see §2) |
| PR #21 | Task 11 Phase B evaluation | OPEN / Draft / Not merged / BLOCKED |
| PR #32 | Issue-31 audit outbox dispatcher | MERGED (untouched) |
| PR #33 | Issue-22E downgrade archive | MERGED (untouched) |
| Issue #35 | Production prerequisite / Task 11 Phase B | OPEN |
| Issue #20 | Task 11 evaluation baseline / pilot fixtures | OPEN |
| Issue #22 | Transport-B E2E persistence | CLOSED (untouched) |
| Issue #31 | Audit outbox dispatcher & idempotent materialization | CLOSED (untouched) |

PR #21 governance anchors (unchanged):

- headRefName: `codex/task-11-evaluation`
- headRefOid: `7822581eeee4c590b4ed9b1e3c46c1cde5490098`
- isDraft: `true`
- mergedAt: `null`
- state: `OPEN`

---

## 6. References

- PR #38: <https://github.com/xuezhiorange-png/cold-storage-planning-agent/pull/38>
- PR #38 merge commit: `fbd715603b7673fd8bea9b4076477cdaa7f4a37c`
- PR #38 post-merge main CI run: <https://github.com/xuezhiorange-png/cold-storage-planning-agent/actions/runs/28783522794>
- PR #21: <https://github.com/xuezhiorange-png/cold-storage-planning-agent/pull/21>
- Issue #35: <https://github.com/xuezhiorange-png/cold-storage-planning-agent/issues/35>
- Issue #20: <https://github.com/xuezhiorange-png/cold-storage-planning-agent/issues/20>
- PR #32: <https://github.com/xuezhiorange-png/cold-storage-planning-agent/pull/32>
- PR #33: <https://github.com/xuezhiorange-png/cold-storage-planning-agent/pull/33>
- Frozen design contract:
  `docs/tasks/TASK-011B-production-calculation-orchestration-prerequisite.md`
  (Phase 1 + Phase 2 design only; not modified by
  this closeout record beyond the closeout-link
  appendix it owns in §13.1)

---

## 7. Explicit non-authorization statement

**This document does NOT authorize any code, schema,
migration, test, workflow, frontend, evaluation,
coefficient, formula, threshold, weight, or review-rule
change.** It is a closeout / governance record only. The
following are all explicitly NOT authorized by this
document:

- No commits to `backend/src/cold_storage/**` source code.
- No commits to `backend/tests/**`.
- No commits to `frontend/**`.
- No commits to `alembic/**` migrations.
- No commits to `evaluation/**` (manifest, expected
  outputs, fixtures, runner).
- No commits to `.github/workflows/**`.
- No commits to PR #21 (`codex/task-11-evaluation`).
- No `Ready` review, `merge`, or `close Issue` actions on
  this docs PR or on any other PR.
- No edits to production formulas / thresholds / weights
  / review rules.
- No latest-row fallback, no raw ORM fabrication.
- No Phase 3 implementation.
- No Task 11 Phase B / C / D implementation.
- No Task 12 implementation.
- No revert / reset / force-push on PR #38, on main, or
  on this branch.
- No reopen of PR #38.
- No close of Issue #35.
- No edit of PR #38 body / title.

This document records the technical closeout of PR #38
and the governance deviation. It does not move the
project forward into Phase 3 or any other
not-yet-authorised phase.
