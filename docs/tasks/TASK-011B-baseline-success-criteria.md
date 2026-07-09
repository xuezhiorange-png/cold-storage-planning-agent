# TASK-011B Baseline Success Criteria

**Status:** governance record (docs-only baseline document per Phase 4 governance
contract §18.5 + PR #57 governance record §10 Gate 4). NOT a design contract;
NOT a Ready authorization; NOT an implementation authorization.

This document is the **required separate baseline-success-criteria document**
per the Phase 4 governance contract §18.5 ("Task 11B's baseline success
criteria are explicitly defined and recorded in a separate document"). It
records (a) the baseline-success criteria that any future Task 11B
implementation round must satisfy and (b) the quality gates that any future
Draft PR must pass before Charles issues a per-message authorization for
Ready / Merge.

This document does **not** authorize implementation.
This document does **not** mutate PR #21.
This document does **not** reopen Issue #35.
This document defines the baseline success criteria and quality gates
required for the **future Task 11B resumption implementation round**.

---

## 1. Purpose

This document serves as the **baseline-success-criteria** and **quality-
gate** reference for any future Task 11B / Phase B resumption implementation
round. It complements the existing governance chain:

- `docs/tasks/TASK-011B-phase-b-resumption-pre-freeze.md` (the frozen
  pre-freeze design contract; §10 awaiting Charles freeze authorization)
- `docs/tasks/TASK-011B-governance-record.md` (PR #57 governance record;
  §10 defines 9 authorization gates)
- `docs/tasks/TASK-011B-contract-amendment.md` (the sibling amendment
  record that closes Gates 2/3/4 per PR #57 §10)

The motivation for this document is the prior audit verdict:

> `TASK_011B_RESUMPTION_REQUIRES_CONTRACT_AMENDMENT`

(see `/root/task11b-resumption-contract-sufficiency-audit-2026-07-09.md`
for the audit; this document closes Gate 4 of that audit's recommendation).

This document does **not**:

- authorize implementation of Task 11 Phase B
- mutate PR #21 (state / draft / head / base / mergeable / comments)
- reopen Issue #35
- touch any production code, evaluation runner, evaluation fixtures,
  bootstrap, coefficients, migration, frontend, docker, .github, or
  pyproject / uv.lock
- mark any PR Ready
- merge any PR
- close or comment on any issue
- read or print any token
- bypass any forbidden-action set

This document **does**:

- record the baseline-success criteria that any future Task 11B
  resumption implementation round must satisfy (per the upstream
  upstream pre-freeze contract §6 success semantics and §7 validation
  matrix)
- record the quality-gate list (per pre-freeze contract §7.1 +
  §7.3) that any future Draft PR must pass
- record the CI / Ready / Merge gates (per pre-freeze contract §7.3 +
  §7.4)
- record the forbidden scope for the future implementation round (per
  pre-freeze contract §4.5 + §5 + PR #57 §9)
- record the stop conditions that the future implementation round must
  monitor (per pre-freeze contract §8)
- cite the upstream frozen contracts whose terms it inherits without
  modification

---

## 2. Source-of-truth snapshot

Server-side audit-time state, captured at 2026-07-09 via unauth REST per
memory **0-token fact-audit 协议**:

| artifact | state | sha / id |
|---|---|---|
| `origin/main` HEAD | current | `24133de5cf026238cf041c6faadae82b2008c54e` (audit-time; mutable) |
| Issue #35 | closed / completed | closed_at `2026-07-08T05:27:57Z` (stable) |
| PR #55 (TASK-019 Slice 3B contract) | merged / frozen | merge_commit_sha `9185b766de877c32557a355a6c6ce30d444154c0` (stable) |
| PR #56 (TASK-019 Slice 3B implementation) | merged / frozen on main | merge_commit_sha `841917da81828f6b9ab196e360a74757587eba8a` (stable) |
| PR #57 (Task 11B governance record) | merged / frozen on main | merge_commit_sha `24133de5cf026238cf041c6faadae82b2008c54e` (stable) |
| PR #21 (Task 11 Phase B historical Draft) | OPEN / Draft / NOT merged | head `7822581eeee4c590b4ed9b1e3c46c1cde5490098`; base `e6dcd631059d1106947ff947ef8c5b9e1e214035`; updated_at `2026-07-05T10:10:17Z` (audit-time; mutable) |

Mutable facts are recorded here as **audit-time snapshots** only and are
not frozen. Any drift between this snapshot and a future PR's mutable
facts must be detected via external-verification at that future round's
preflight (consistent with the `mutable-facts discipline` principle
from the TASK-019 governance chain — mutable facts are intentionally not
baked into governance docs; they are verified externally per round).

---

## 3. Preconditions before any resumption implementation

Any future Task 11B resumption implementation round MUST have all of the
following preconditions met before any implementation commit:

1. **Current `origin/main` is verified** at the time of the future
   round's preflight (per PR #57 §11).
2. **The future branch is created from current `origin/main`** (not from
   a stale base; per PR #57 §11).
3. **PR #21 is untouched** unless Charles explicitly authorizes a
   different route in the per-message authorization for the future
   implementation round (per pre-freeze contract §5.4 + PR #57 §6 + §9.3).
4. **Issue #35 remains closed**; not reopened by the future implementation
   round unless Charles explicitly authorizes a Phase 4 contract amendment
   round (per pre-freeze contract §0 + PR #57 §9.3).
5. **TASK-019 behavior must not regress**: PR #55 + PR #56 chain (TASK-019
   Slice 3B contract + implementation) is frozen on main and must remain
   preserved; the future implementation round must not touch
   `backend/src/cold_storage/modules/reports/application/validation_adapter.py`
   or `validation_report.py` or the TASK-019 test files unless Charles
   explicitly authorizes a TASK-019 amendment.
6. **`production_seeding.py` is not restored** (per pre-freeze contract
   §4.5 + §5.1 + §8.1; this is a §8 hard stop condition).
7. **Forbidden-file set is explicitly checked** (per PR #57 §9 +
   pre-freeze §4.5 + §5); the future implementation contract's §4 allowed-
   files list and §5 forbidden-patterns list must both be present.
8. **Implementation allowed files are named by the future implementation
   authorization** (per pre-freeze contract §3 / §4); the future
   per-message authorization must explicitly identify which §4 sub-rows
   are being authorized.
9. **Required tests are named by the future implementation authorization**
   (per pre-freeze contract §3 / §7.1); the future per-message authorization
   must explicitly identify which §7.1 sub-rows are being run.
10. **Charles's per-message authorization message is explicit**: it must
    name the branch name, the commit message, the PR title, and any
    contract-specific deltas (per PR #57 §11).

---

## 4. PR #21 supersession policy

Per pre-freeze contract §1.1 + §3.3 + §5.4 + §7.4:

- **Direct PR #21 resumption is not the design default.** The design
  forward path is a new resumption PR on a new branch (proposed
  `codex/task-11b-phase-b-resumption-from-main` per pre-freeze contract
  §3).
- **PR #21 remains historical / superseded draft** until Charles
  separately authorizes a different route via per-message authorization
  (per pre-freeze contract §5.4 + PR #57 §6).
- **PR #21 is not the direct implementation target** unless Charles
  explicitly overrides in per-message authorization.
- **PR #21 must remain untouched in the future implementation round**:
  - No rebase / force-push / merge on PR #21
  - No comment on PR #21 (unless Charles explicitly authors one, which is
    out-of-band)
  - No state transition (Ready / Closed / Reopened)
  - No label changes
  - No new commits on `codex/task-11-evaluation` from the future
    implementation branch
- The supersession annotation (Phase 4 §18.4 + PR #57 §10 Gate 3) may be
  recorded either (a) as a Charles-authored comment on PR #21 thread OR
  (b) as a docs-only commit on `main` cross-referencing
  `docs/tasks/TASK-011B-phase-b-resumption-pre-freeze.md` §1.1 +
  `docs/tasks/TASK-011B-governance-record.md` §6.

---

## 5. Allowed implementation baseline

The future Task 11B implementation round's allowed files are **exactly**
those enumerated in pre-freeze contract §4 (verbatim, NOT modified by
this document) and must be re-confirmed in the future implementation
authorization. The future per-message authorization must explicitly:

1. Confirm that pre-freeze contract §4 is the binding allowed-files list.
2. Identify which §4 sub-rows the future round will modify (with the
   specific modification scope per row).
3. Confirm that no file outside §4 is to be touched in this round.

**Verbatim inheritance of pre-freeze §4**:

- §4.1 Evaluation subsystem:
  - `evaluation/manifest.json`
  - `evaluation/expected/baseline-feasible.v1.json`
  - `evaluation/expected/high-throughput-review.v1.json`
  - `evaluation/expected/invalid-blocked.v1.json`
  - `backend/src/cold_storage/evaluation/execute.py`
  - `backend/src/cold_storage/evaluation/cli.py`
  - `backend/src/cold_storage/evaluation/run_directory.py`
  - `backend/src/cold_storage/evaluation/errors.py`
  - Optional: a new module under `backend/src/cold_storage/evaluation/`
    (the adapter) — per pre-freeze §4.1 last row
- §4.2 Test code:
  - `backend/tests/evaluation/test_sqlite_acceptance.py`
  - `backend/tests/evaluation/test_cli.py`
  - `backend/tests/evaluation/test_fixture_consistency.py`
  - `backend/tests/evaluation/test_postgresql_acceptance.py`
  - `backend/tests/architecture/test_architecture_boundaries.py`
  - `backend/tests/integration/test_production_archive_wiring_e2e_postgresql.py`
    + zero-delta tests
- §4.3 Fixtures:
  - `evaluation/fixtures/projects/baseline-feasible.v1.json`
  - `evaluation/fixtures/projects/high-throughput-review.v1.json`
  - `evaluation/fixtures/projects/invalid-blocked.v1.json`
- §4.4 Documentation:
  - `docs/pilot/TASK-011-PILOT-RUNBOOK.md`
  - `docs/tasks/TASK-011B-phase-b-resumption-pre-freeze.md` (this
    contract's freeze-amendment if Charles explicitly authorizes)

---

## 6. Forbidden scope

Forbidden scope is **exactly** as enumerated in pre-freeze contract §5
+ §4.5 + PR #57 §9 (verbatim, NOT modified by this document). The future
implementation authorization must explicitly confirm adherence.

**Verbatim inheritance summary**:

### 6.1 Production / infrastructure / freeze-protected paths (pre-freeze §4.5 + §5)

- `backend/src/cold_storage/evaluation/production_seeding.py` — file
  remains absent (per pre-freeze §4.5); restoration is a §8 stop condition
- All `backend/src/cold_storage/modules/*/infrastructure/*.py`
  production code (Phase 4 freeze; per pre-freeze §4.5)
- All `backend/src/cold_storage/modules/*/application/*.py` ports
  (Phase 2 + Phase 4 freeze; per pre-freeze §4.5)
- All Alembic migrations under
  `backend/src/cold_storage/modules/*/infrastructure/migrations/versions/*.py`
  (Phase 1/2/3/4 freeze; per pre-freeze §4.5)

### 6.2 Round 11 reversal — DO NOT restore (pre-freeze §5.1)

- **DO NOT** re-introduce `backend/src/cold_storage/evaluation/production_seeding.py`.

### 6.3 Evaluation-owned production row fabrication — DO NOT (pre-freeze §5.2)

- **DO NOT** create or use any module that writes `CalculationRunRecord`
  from `cold_storage.evaluation.*` code.
- **DO NOT** create or use any module that writes `SourceBindingRecord`
  from evaluation code.
- **DO NOT** create or use any module that writes orchestration identity /
  attempt / execution-snapshot / coefficient-context rows from evaluation
  code.
- **DO NOT** create or use any module that writes approved weight-set
  revision rows from evaluation code.
- **DO NOT** engineer evaluation-owned calculation input bridges.

### 6.4 Production invariants — DO NOT weaken (pre-freeze §5.3)

- **DO NOT** introduce demo / unverified coefficients into the production
  path.
- **DO NOT** introduce "latest-row" selection on approved coefficient
  queries.
- **DO NOT** introduce partial `SourceBinding` writes.
- **DO NOT** suppress, rename, downgrade, or reclassify `requires_review`
  warnings or `UntrustedCoefficientError` raise paths.
- **DO NOT** alter production formulas, coefficient values, scoring
  rules, review rules, thresholds, weights.
- **DO NOT** bypass `SourceBindingVerifier` or `SchemeService`.
- **DO NOT** bypass approved non-demo coefficient governance.

### 6.5 PR #21 — DO NOT touch (pre-freeze §5.4)

- **DO NOT** rebase, force-push, merge, comment on, label, or otherwise
  mutate PR #21 in any resumption round.
- **DO NOT** modify PR #21's local branch `codex/task-11-evaluation`
  from the resumption branch.

### 6.6 Demonstration / fixture boundary — DO NOT blur (pre-freeze §5.5)

- **DO NOT** import evaluation code into production modules.
- **DO NOT** import production modules into evaluation code EXCEPT
  through their public ports
  (`application/ports.py` / `compose_production_scheme_service(session_factory)`).
- **DO NOT** bypass `application/ports.py` to reach
  `infrastructure/orm.py` from evaluation code.

### 6.7 Cross-track / governance-record paths (PR #57 §9.3)

- PR #21 thread mutation (no comment / state / Ready / merge in this
  round or in any future round unless Charles explicitly authorizes)
- Issue #35 reopen (no close / reopen / comment in this round or in any
  future round unless Charles explicitly authorizes)
- TASK-011B contract files at `docs/tasks/TASK-011B-*.md` (frozen at
  their respective freeze times; any amendment requires a separate
  design-amendment round)

### 6.8 Non-production paths (PR #57 §9.2)

- `frontend/**`
- `migrations/**` and `backend/alembic/versions/**`
- `.github/**`
- `docker/**` and `docker-compose*.yml` and `Dockerfile*`
- `pyproject.toml` and `uv.lock`
- `package.json` and `package-lock.json`
- `scripts/**`
- `backend/tests/conftest.py` and any other test infrastructure outside
  pre-freeze §4.2 allowed test files

---

## 7. Required tests and quality gates

The future Task 11B implementation round MUST pass all of the following
quality gates (per pre-freeze contract §7 + PR #57 §10 Gate 7). The
future per-message authorization must explicitly confirm that the future
round runs each of these.

### 7.1 Backend validation (per pre-freeze §7.1)

- **`ruff check src tests`** clean (no new warnings).
- **`ruff format --check src tests`** clean.
- **`mypy src`** clean (no new errors; pre-existing errors are out-of-
  scope unless annotated as such).
- **`backend/tests/evaluation/test_sqlite_acceptance.py`** all tests green
  on a fresh SQLite database with `alembic upgrade head` applied
  (including flipped "success" assertions).
- **`backend/tests/evaluation/test_postgresql_acceptance.py`** mirror of
  SQLite suite on a fresh PostgreSQL 14 instance with `alembic upgrade
  head` applied — assert no demo / latest-row / partial-binding paths
  exist.
- **Phase-4 regression suite** — all green on both backends:
  - `backend/tests/integration/test_production_archive_wiring_e2e_postgresql.py`
  - `backend/tests/integration/test_zero_delta_invariant_postgresql.py`
  - `backend/tests/integration/test_zero_delta_invariant_sqlite.py`
  - `backend/tests/integration/test_phase4_slice2a_resolution_gateway_postgresql.py`
  - `backend/tests/integration/test_phase4_slice2c_power_authority_postgresql.py`
- **Architecture tests** — all green:
  - `backend/tests/architecture/test_architecture_boundaries.py` (no
    application file imports from `infrastructure/orm.py`; `phase3_exceptions`
    exception set remains retired).

### 7.2 Production flow failure-closed tests (per pre-freeze §7.1 + Phase 4 §11-§14)

- 9 fail-closed test cases from
  `docs/tasks/TASK-011B-phase4-issue35-production-roundtrip-governance.md`
  §11 — all green on both backends.
- §12 power-authority test — green on both backends.
- §13 archive verification test — green on both backends.
- §14 phase3 retirement verification — green (no application file
  imports from `infrastructure/orm.py`; `phase3_exceptions` exception
  set absent).

### 7.3 Expected-output validation (per pre-freeze §7.2)

- `evaluation/expected/baseline-feasible.v1.json` regenerated under
  reviewer sign-off, with the regenerated file matching the canonicalized
  output of the production path on a fresh SQLite database. The sign-off
  record lives in the future resumption PR's commit message / merge
  commit body / or a designated
  `docs/tasks/TASK-011B-phase-b-resumption-expected-outputs-review.md`
  (separate-document pattern allowed).
- `evaluation/expected/high-throughput-review.v1.json` regenerated with
  the same discipline.
- `evaluation/expected/invalid-blocked.v1.json` unchanged (or changed only
  if the schema evolved, with reviewer sign-off).

### 7.4 CI validation (per pre-freeze §7.3 + PR #57 §10 Gate 7)

- 4 jobs on PR-side run green: `compose-config` / `frontend` /
  `backend-sqlite` / `backend-postgresql`.
- Post-merge run on main, head_sha == resumption PR's merge commit SHA,
  completed / success / 4 jobs all success.
- backend-postgresql job's steps include success of:
  - `PostgreSQL integration tests`
  - `PostgreSQL attempt race stability (10x)`
  - `Backend tests (PostgreSQL)`.
- backend-sqlite job's steps include success of:
  - `Backend tests (SQLite)`
  - `Backend architecture tests`
  - `Backend lint`
  - `Backend typecheck`
- frontend job's `Frontend quality` step success.
- compose-config job's `Docker Compose config` step success.
- **No `workflow_dispatch` or rerun after the merge** that masks real
  failures (per pre-freeze §8.11).

### 7.5 Post-conditions (per pre-freeze §7.4)

- `main` HEAD == resumption PR's merge commit SHA.
- `codex/task-11b-phase-b-resumption-from-main` ref deleted (or
  retained per Charles's choice).
- PR #21 retains its `Draft / Open / Not merged` state, with a
  `superseded by #N` cross-reference comment posted on PR #21 by Charles
  (or in PR #21's body under "Superseded by" trailer) — this is an
  out-of-band Charles action, NOT bound to the resumption PR.

### 7.6 Baseline success criteria (per pre-freeze contract §6)

For the `baseline-feasible.v1` scenario (and analogously for
`high-throughput-review.v1`):

1. `compose_production_scheme_service(session_factory)` is invoked
   exactly once per scenario through `backend/src/cold_storage/evaluation/execute.py`.
   It is the **only** path that writes production rows for that scenario.
2. `SchemeRun.scheme_status == "SUCCEEDED"` at the end of the scenario.
3. The `evaluation/raw/<scenario_id>.json` artifact's top-level
   `outcome == "success"` (not `"blocked"`, not `"failed"`).
4. No `EVAL_PRODUCTION_PIPELINE_PREREQUISITE_MISSING` error is raised on
   the happy path. (The error class MAY exist as a deprecated diagnostic;
   it MUST NOT be raised.)
5. The `SchemeRun` row carries a verifiable `calculation_run_id`
   lineage back to all 5 production `CalculationRunRecord` rows (zone,
   investment, cooling_load, equipment, plus the planning row counted
   by Phase-4 design §4.3). PK-set symmetric-difference test passes (one
   row per table before, one row per table after, delta = ∅ across all
   four production tables).
6. The `combined_source_hash` on the scheme's `SourceBindingRecord` is
   reproducible from `build_source_snapshot_content_v1(...)` and
   round-trips through the scheme-callable path.
7. The expected output comparison (`evaluation/expected/baseline-feasible.v1.json`)
   passes with all exact-paths + decimal-paths matching and all
   ignored-paths justified.
8. The same invariants hold on PostgreSQL backend as on SQLite, with
   migration `alembic upgrade head` applied first.

---

## 8. CI / Ready / Merge gates

### 8.1 CI gate (per pre-freeze §7.3 + §7.4 + PR #57 §10 Gate 7)

The future Draft PR's CI run must:

- Be triggered on `pull_request` event (auto-triggered by GitHub on PR
  creation).
- Pass all 4 required jobs: `compose-config` / `frontend` /
  `backend-sqlite` / `backend-postgresql` (all `completed / success`).
- Step-level success for the steps enumerated in §7.4.
- Post-merge main push run (auto-triggered by squash merge on main)
  must also pass with head_sha == merge commit SHA.

### 8.2 Ready gate (per pre-freeze §3 + §10 + PR #57 §10 Gate 8)

Marking the future Draft PR as Ready for review requires:

- All §7.1 / §7.2 / §7.3 / §7.4 quality gates passing on the PR-head
  branch.
- **Charles's explicit per-message authorization message** naming
  "Mark PR #N Ready for review" or equivalent phrase.
- No forbidden-pattern triggered per §6.
- No §9 stop condition triggered.

The agent does **not** auto-mark Ready. This gate is **blocked** until
Charles's per-message authorization is issued.

### 8.3 Merge gate (per pre-freeze §10 + PR #57 §10 Gate 9)

Squash-merging the future Draft PR requires:

- PR is currently `Open` / `isDraft=false` / `mergeable=true`.
- All §7.1 / §7.2 / §7.3 / §7.4 quality gates still passing.
- **Charles's explicit per-message authorization message** naming
  "Merge PR #N (squash)" or equivalent phrase.
- No forbidden-pattern triggered per §6.
- No §9 stop condition triggered.

The agent does **not** auto-merge. This gate is **blocked** until
Charles's per-message authorization is issued.

---

## 9. Stop conditions

The future Task 11B resumption implementation round MUST halt and
surface a blocker to Charles if any of the following occurs (per pre-freeze
contract §8 + PR #57 §12, verbatim):

1. `production_seeding.py` (or any equivalent) is found reintroduced in
   evaluation code.
2. Any raw `Session.add` / `session.flush` of `CalculationRunRecord` /
   `SourceBindingRecord` / orchestration identity / attempt /
   execution-snapshot / coefficient-context / approved weight-set
   revision rows is found in evaluation code paths.
3. Any demo / latest-row / partial-binding fallback enters the production
   path.
4. Any `requires_review` warning is suppressed, renamed, or downgraded.
5. Production formulas, coefficient values, scoring rules, review rules,
   thresholds, or weights are altered.
6. `compose_production_scheme_service(session_factory)` is bypassed or
   short-circuited.
7. `SourceBindingVerifier` or `SchemeService` is bypassed.
8. Approved non-demo coefficient governance is bypassed.
9. PR #21 is rebased, force-pushed, merged, or otherwise mutated.
10. The expected-output regeneration is committed without Charles's
    reviewer sign-off recorded.
11. CI reruns are performed that mask real failures.
12. `evaluation/manifest.json` `expected_outcome` is downgraded from
    `"success"` to `"blocked"` (or any value other than `"success"`).
13. Any new migration is added under
    `backend/src/cold_storage/modules/*/infrastructure/migrations/versions/*.py`
    without following the Phase-4 design contract's migration discipline.

Each stop is reported with: condition number, evidence (file path, test
name, log snippet, or commit SHA), and a recommendation for next steps.

### 9.1 Cross-cutting stop conditions (inherited from PR #57 §12)

- Main HEAD drift between this baseline document's snapshot and the future
  round's preflight — re-verify and acknowledge before continuing.
- Unclear allowed files — STOP and request a design-amendment round.
- Unclear relationship to PR #21 — STOP and surface blocker to Charles.
- Unresolved blocker in PR #21 comments — STOP; supersession must be
  recorded first.
- Missing required tests in the future implementation contract —
  STOP; tests must be explicitly listed.
- Temptation to mutate PR #21 directly — STOP; per §5.4 + §9.3.
- Temptation to close / reopen Issue #35 — STOP; per §6.7 + PR #57 §9.3.
- Token / auth operations — STOP per memory GITHUB_WRITE_AUTH_UNAVAILABLE.

---

## 10. Evidence appendix

### 10.1 Frozen upstream governance chain (verbatim references)

- `docs/tasks/TASK-011B-path-a-design-ratification.md` (Path A design
  contract; frozen)
- `docs/tasks/TASK-011B-path-a-a1-a2-closeout.md` (Phase 1 A1/A2 closeout)
- `docs/tasks/TASK-011B-phase2-closeout.md` (Phase 2 ports/adapters closeout)
- `docs/tasks/TASK-011B-phase3-sourcebinding-schemeservice-e2e.md`
  (Phase 3 closeout)
- `docs/tasks/TASK-011B-phase4-issue35-production-roundtrip-governance.md`
  (Phase 4 governance contract — defines §17 + §18 acceptance criteria;
  §18.5 explicitly requires "Task 11B's baseline success criteria are
  explicitly defined and recorded in a separate document")
- `docs/tasks/TASK-011B-phase-b-resumption-pre-freeze.md` (the frozen
  pre-freeze design contract — defines §3 / §4 / §5 / §6 / §7 / §8;
  §10 says "awaiting Charles freeze authorization" as of this writing)
- `docs/tasks/TASK-011B-governance-record.md` (PR #57 governance record
  — defines §10's 9 authorization gates)
- `docs/tasks/TASK-011B-contract-amendment.md` (the sibling amendment
  record that closes Gates 2/3/4 in the same docs-only change)

### 10.2 TASK-019 cross-track (parallel, not gating)

- `docs/tasks/TASK-019-slice-3-validation-adapter-contract.md` (TASK-019
  Slice 3 design contract; merged via PR #52)
- `docs/tasks/TASK-019-slice-3a-placeholder-fixture-contract.md` (TASK-019
  Slice 3A fixture contract; merged via PR #53)
- `docs/tasks/TASK-019-slice-3b-adapter-implementation-contract.md`
  (TASK-019 Slice 3B implementation contract; merged via PR #55)
- `docs/tasks/TASK-019-slice-3b-implementation-closeout.md` (TASK-019
  Slice 3B implementation closeout; merged via PR #56)

### 10.3 Audit-time source-of-truth URLs

- Issue #35:
  `https://api.github.com/repos/xuezhiorange-png/cold-storage-planning-agent/issues/35`
- PR #55: `https://github.com/xuezhiorange-png/cold-storage-planning-agent/pull/55`
- PR #56: `https://github.com/xuezhiorange-png/cold-storage-planning-agent/pull/56`
- PR #57 (governance record merge):
  `https://github.com/xuezhiorange-png/cold-storage-planning-agent/pull/57`
- PR #21 (historical Task 11 Phase B Draft):
  `https://github.com/xuezhiorange-png/cold-storage-planning-agent/pull/21`
- PR #57 post-merge CI: run `29027313931` (head_sha `24133de...`)

### 10.4 Prior audit verdict (input to this baseline document)

- Audit round: `Task 11B resumption contract sufficiency audit`
- Audit-time date: 2026-07-09
- Audit verdict: **`TASK_011B_RESUMPTION_REQUIRES_CONTRACT_AMENDMENT`**
- Audit evidence file:
  `/root/task11b-resumption-contract-sufficiency-audit-2026-07-09.md`

---

## 11. Change log

| version | date | author | change |
|---|---|---|---|
| v1.0 | 2026-07-09 | Hermes (governance baseline record per spec Phase 3) | initial baseline-success-criteria document; records §3-§10 baseline success criteria and quality gates; explicitly does NOT authorize implementation; closes Gate 4 of the prior audit verdict. Base SHA: `24133de5cf026238cf041c6faadae82b2008c54e` (= `origin/main` HEAD at audit time, post-PR #57 merge). |
