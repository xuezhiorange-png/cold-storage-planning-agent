# TASK-011B Governance Record

**Status:** governance record (docs-only) — NOT a design contract, NOT a Ready
authorization, NOT an implementation authorization.

This document is the **governance baseline** for any future Task 11B / Phase B
resumption round. It records (a) the current frozen state of the
prerequisite artifacts (Issue #35, TASK-019, PR #21) and (b) the explicit
gates that must be passed before any resumption round can be authorized.

This document does **not** authorize implementation.
This document does **not** mutate PR #21.
This document does **not** reopen Issue #35.
This document defines the governance baseline required before any Task 11B
resumption round.

---

## 1. Purpose

This document serves as the **audit-trail-grade snapshot** of the
governance state required before any future Task 11B / Phase B resumption
round can be authorized. It does not itself authorize implementation; it
captures the preconditions and gates that any future resumption round must
verify, record, and pass before Charles issues a per-message authorization
for the implementation round.

The motivation for this document is the prior audit verdict:

> `PR21_TASK11B_RESUMPTION_REQUIRES_GOVERNANCE_RECORD`

(see the prior audit summary below; full evidence at
`/root/pr21-task11b-resumption-audit-2026-07-09.md`).

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

- record the current state of the prerequisite artifacts (Issue #35,
  TASK-019, PR #21) verbatim from server-side JSON
- define the resumption baseline success criteria (the §17 + §18 acceptance
  criteria of the Phase 4 governance contract)
- record the explicit authorization gates that must be passed before
  any future resumption round
- record the forbidden scope for the future resumption round
- cite the upstream frozen contracts whose terms it inherits without
  modification

---

## 2. Source-of-truth snapshot

Server-side audit-time state, captured at 2026-07-09 via unauth REST per
memory **0-token fact-audit 协议**:

| artifact | state | sha / id |
|---|---|---|
| `origin/main` HEAD | current | `841917da81828f6b9ab196e360a74757587eba8a` |
| Issue #35 | closed / completed | closed_at `2026-07-08T05:27:57Z` |
| PR #55 (TASK-019 Slice 3B contract) | merged / frozen | merge_commit_sha `9185b766de877c32557a355a6c6ce30d444154c0`; 1 file / 597 insertions / 0 deletions |
| PR #56 (TASK-019 Slice 3B implementation) | merged / frozen on main | merge_commit_sha `841917da81828f6b9ab196e360a74757587eba8a`; 5 files / 1554 insertions / 0 deletions |
| PR #21 (Task 11 Phase B) | OPEN / Draft / NOT merged | head `7822581eeee4c590b4ed9b1e3c46c1cde5490098`; base `e6dcd631059d1106947ff947ef8c5b9e1e214035`; updated_at `2026-07-05T10:10:17Z`; 40 files / 15,450 insertions / 3 deletions; `mergeable: false` |
| Post-merge main CI run (PR #56) | completed / success | run `29016039790`, head_sha `841917d...`, all 4 required jobs green |

Mutable facts are recorded here as **audit-time snapshots** only and are
not frozen. Any drift between this snapshot and a future PR's mutable
facts must be detected via external-verification at that future round's
preflight (consistent with the `mutable-facts discipline` principle
from the TASK-019 governance chain — mutable facts are intentionally
not baked into governance docs; they are verified externally per round).

---

## 3. Issue #35 closure status

Per Issue #35 server-side JSON:

- **state**: `closed`
- **state_reason**: `completed`
- **closed_at**: `2026-07-08T05:27:57Z`
- **comments**: 2 (Comment 1: "PR #45 post-merge closeout" 2026-07-07; Comment 2: "Decision Record — Issue #35 §16 #15 / §18 #4 — defer PR #21 / Task 11 Phase B resumption" 2026-07-08T05:22:00Z)

The closure follows the §16 acceptance criteria of the Phase 4 governance
contract (`docs/tasks/TASK-011B-phase4-issue35-production-roundtrip-governance.md`):

- All 15 §16 criteria closed (including §16.13 "The Phase 4 implementation
  PR is merged to `main`" and §16.14 "The Phase 4 post-merge CI run is
  green on all 4 jobs")

This governance record confirms:

- **Issue #35 is closed / completed.** ✅
- **Issue #35 is not to be reopened by this governance record.** ✅
- **TASK-019 no longer acts as the Issue #35 production prerequisite blocker
  for Task 11B, subject to Charles review.** Per the cross-track analysis:
  TASK-019 PR #55 (contract) and PR #56 (implementation) are frozen on
  main, post-merge main CI green. TASK-019 work is a separate governance
  track from Issue #35's acceptance criteria, and its completion is
  consistent with — but not a direct lifting of — the §18 Task 11 Phase B
  resumption gate.

The TASK-019 / Issue #35 cross-track analysis is informational only. The
binding gate for Task 11 Phase B resumption remains the Phase 4 governance
contract §18 (see §11 below).

---

## 4. TASK-019 frozen dependency status

Per PR #55 and PR #56 server-side JSON:

- **PR #55 (TASK-019 Slice 3B adapter implementation contract)**:
  - state: closed (merged)
  - merged: true
  - merge_commit_sha: `9185b766de877c32557a355a6c6ce30d444154c0`
  - head sha: `1036cce9f8840cd27dcd16f62bde60db980c6336`
  - 1 file (the contract doc) / 597 insertions / 0 deletions

- **PR #56 (TASK-019 Slice 3B adapter-only implementation)**:
  - state: closed (merged)
  - merged: true
  - merge_commit_sha: `841917da81828f6b9ab196e360a74757587eba8a`
  - head sha: `66f7620a7644615b852564045d99487a7c8ebbea`
  - 5 files (the §6.2 allowed-files list of the Slice 3B contract) /
    1,554 insertions / 0 deletions

- **Post-merge main CI run `29016039790`**:
  - event: push
  - head_branch: main
  - head_sha: `841917d...`
  - status: completed
  - conclusion: success
  - 4/4 required jobs green (`compose-config`, `frontend`, `backend-sqlite`,
    `backend-postgresql`)

TASK-019 Slice 3B adapter implementation is **frozen on main**. The TASK-019
governance track's authorized scope (per Slice 3 design contract §13) had
three next-authorization options:
- A) Fixture-contract authoring round — executed via PR #53 ✅
- B) Slice 3 adapter-only implementation round — executed via PR #56 ✅
- C) Design amendment round — not triggered (no amendment needed)

The TASK-019 governance track is **complete** in the sense that all
explicit §13 next-authorization options have been exercised; future
TASK-019 slices (if any) require their own design freezes and explicit
authorizations per the Slice 3B contract §20.2 informational list
("Slice 1 / Slice 2 / Slice 4 / Slice N rounds ... outside Slice 3B ... each
requires its own design contract + implementation + review round").

Per the Phase 4 governance contract §7.3 forbidden-file list and the
TASK-019 Slice 3B contract §7.3 / §7.4: **TASK-019 does not authorize any
change to Task 11B / TASK-011B / PR #21 / Issue #35 / Task 12 / Phase C /
Phase D**. The TASK-019 governance track is **parallel**, not
**gating**, for the Task 11 Phase B resumption decision.

---

## 5. PR #21 current status

Per PR #21 server-side JSON:

- **state**: `open`
- **draft**: `True`
- **merged**: `False`
- **mergeable**: `False`
- **head sha**: `7822581eeee4c590b4ed9b1e3c46c1cde5490098`
- **head branch**: `codex/task-11-evaluation`
- **base sha**: `e6dcd631059d1106947ff947ef8c5b9e1e214035` (= PR #33
  merge commit, 2026-07-05)
- **base branch**: `main` (declarative; actual base SHA is stale since
  2026-07-05)
- **changedFiles**: 40
- **additions**: 15,450
- **deletions**: 3
- **commits**: 88
- **comments**: 16
- **review_comments**: 0
- **updated_at**: `2026-07-05T10:10:17Z` (= no PR #21 activity since the
  base was set 2026-07-05)
- **created_at**: `2026-06-27T05:51:40Z`

PR #21's most recent commit (`7822581`):
> "revert(task-11): roll back round 11 evaluation-owned production seeding
> direction"
> authored `2026-07-05T09:43:40Z`

This commit reverted all Round 11 evaluation-owned seeding changes,
including **DELETE `backend/src/cold_storage/evaluation/production_seeding.py`**
(a key forbidden file). The Round 11 attempt to drive the production
SchemeService via an evaluation-owned `production_seeding` module
(1.2k LoC) was rejected by engineering review because it fabricates
production records in evaluation code (raw ORM inserts of
CalculationRunRecord, SourceBindingRecord, orchestration
identity/attempt/execution-snapshot/coefficient-context rows, and
approved weight-set revisions).

PR #21's last known state explicitly says: "Round 12 reverses that
direction in full and **re-blocks Phase B on the standalone production
capability gap that no closed prerequisite has yet delivered**."

This governance record confirms:

- **PR #21 remains OPEN / Draft / NOT merged.** ✅ (unchanged from prior
  audits: `7822581eeee4c590b4ed9b1e3c46c1cde5490098`,
  `updated_at: 2026-07-05T10:10:17Z`)
- **PR #21 is intentionally untouched.** ✅ (no comment, no state
  transition, no merge, no Ready)
- **PR #21 is not to be directly rebased in this round.** ✅ (a direct
  rebase+merge is not the design; see §6 below)
- **PR #21 is not to be marked Ready in this round.** ✅ (the §17.6
  criterion "Charles explicitly authorizes marking PR #21 ready and merging
  it" is not yet met)

---

## 6. PR #21 superseded-path decision

Per the frozen pre-freeze contract for Phase B resumption:

- `docs/tasks/TASK-011B-phase-b-resumption-pre-freeze.md`
- Contract §1.1 (verbatim): "**PR #21 superseded by this PR — see `docs/tasks/TASK-011B-phase-b-resumption-pre-freeze.md` §1.1. This contract (§1.1 and the full document) is the contract that supersedes PR #21; the resumption PR is the vehicle that closes out Phase B once Charles authorizes it.**"
- Contract §3.3 requires the resumption PR body to explicitly state "PR
  #21 superseded by this PR — see `docs/tasks/TASK-011B-phase-b-resumption-pre-freeze.md` §1.1".

Per the prior audit verdict:
- Direct PR #21 resumption is not the design default
- The design forward path is a **new** resumption PR on a **new** branch,
  with PR #21 explicitly superseded

This governance record **does not** write a supersession decision on PR #21
thread (per spec: no PR #21 mutation in this round). The supersession
record, if Charles chooses, must be:

- A new comment on PR #21 thread (Charles authored, NOT agent-authored), OR
- A new docs-only commit on `main` referencing this governance record's §6
  decision and updating the pre-freeze contract's §10 change log with
  the Charles freeze authorization, OR
- Cross-referenced in the new resumption PR's body when Charles
  authorizes that round

This governance record **does** confirm:

- **Direct PR #21 resumption is not the default path.** ✅
- **The resumption path should be a new branch / new Draft PR unless
  Charles explicitly authorizes another route.** ✅ (per pre-freeze
  contract §3 proposed branch `codex/task-11b-phase-b-resumption-from-main`)
- **PR #21 remains historical context / superseded draft until Charles
  decides otherwise.** ✅ (no in-round supersession action; awaits
  Charles's per-message authorization)

### 6.1 Future branch name (NOT auto-created)

Per the pre-freeze contract §3 proposed branch name:
- `<future-Charles-authorized-Task-11B-resumption-branch>` — placeholder
  label only; the contract's proposed name is `codex/task-11b-phase-b-resumption-from-main`,
  but the actual branch name and creation are Charles's per-message
  authorization call.

This governance record does **not** create or push any new branch.

---

## 7. Task 11B baseline success criteria

Per the Phase 4 governance contract §17 and §18 (verbatim), and per the
pre-freeze contract §3 / §4 (verbatim), the Task 11 Phase B resumption
requires the following baseline success criteria (audit-grade checklist):

### 7.1 §17 Acceptance criteria for unblocking PR #21 (6 criteria; ALL required)

- [ ] **§17.1** Issue #35 Phase 4 implementation is merged to `main` and
  post-merge CI is green. ✅ **MET** (PR #54 merged, main CI run
  `29016039790` success)
- [ ] **§17.2** PR #21 is rebased onto the post-Phase-4 `main` and the
  rebase is clean. ❌ **NOT MET** (PR #21 base `e6dcd63` ≠ post-Phase-4
  `841917d`; 42 commits behind)
- [ ] **§17.3** PR #21's evaluation manifest / expected outputs / fixtures /
  runner are consistent with the production path defined by this
  contract (no demo coefficients, no latest-row fallback, no partial
  binding). ❌ **NOT MET** (would require a successful rebase first; PR
  #21 itself is superseded per §6)
- [ ] **§17.4** PR #21's evaluation is baseline-feasible: the evaluation
  no longer depends on demo coefficients. ❌ **NOT MET** (would require
  a successful rebase first)
- [ ] **§17.5** PR #21's CI is green on all 4 jobs. ❌ **NOT MET**
  (mergeable=false)
- [ ] **§17.6** Charles explicitly authorizes marking PR #21 ready and
  merging it. ❌ **NOT MET** (no per-message authorization recorded)

§17 verdict: **1/6 met; 5/6 unmet**.

### 7.2 §18 Acceptance criteria for Task 11 Phase B resumption (7 criteria; ALL required)

- [x] **§18.1** Issue #35 Phase 4 implementation is merged to `main`. ✅ **MET**
- [x] **§18.2** Issue #35 close review is approved (all 15 criteria in
  §16 are met). ✅ **MET**
- [ ] **§18.3** PR #21 unblock review is approved (all 6 criteria in §17
  are met). ❌ **NOT MET**
- [ ] **§18.4** PR #21 is merged, **or** an explicit deferred-reason is
  recorded. ❌ **NOT MET** (neither merged nor deferred-reason recorded
  in this round)
- [ ] **§18.5** Task 11 Phase B's baseline success criteria are explicitly
  defined and recorded in a separate document. ⚠ **PARTIAL** (this
  governance record defines the gating criteria but is not the
  phase-specific baseline-success-criteria document)
- [x] **§18.6** Task 11 Phase C / D and Task 12 are not automatically
  authorized by the Phase B resumption; each requires its own design
  freeze and explicit authorization. ✅ **MET** (criterion is non-action;
  vacuously met)
- [ ] **§18.7** Charles explicitly authorizes starting Task 11 Phase B. ❌
  **NOT MET**

§18 verdict: **2/7 fully met; 1/7 partial; 4/7 unmet**.

### 7.3 Pre-freeze contract §4 allowed-future-implementation files (verbatim)

The pre-freeze contract `docs/tasks/TASK-011B-phase-b-resumption-pre-freeze.md`
§4 enumerates the candidate modification files for any future resumption
implementation round. The future implementation contract must explicitly
list the §4.1 evaluation-subsystem files, §4.2 test code, §4.3 fixtures,
and §4.4 documentation; and MUST NOT touch the §4.5 forbidden files
(including `production_seeding.py`, infrastructure production code,
application ports, and Alembic migrations).

### 7.4 Forbidden scope for any future resumption round (inherited)

- `backend/src/cold_storage/evaluation/production_seeding.py` — file
  remains absent; restoration is a stop condition (pre-freeze §8).
- All `backend/src/cold_storage/modules/*/infrastructure/*.py` production
  code — Phase 4 has its own freeze.
- All `backend/src/cold_storage/modules/*/application/*.py` ports —
  Phase 2 + Phase 4 freeze.
- All Alembic migrations under `backend/src/cold_storage/modules/*/infrastructure/migrations/versions/*.py` — Phase 1/2/3/4 freeze.

---

## 8. Allowed next-step strategy

Per the pre-freeze contract §3 + this audit's recommendation matrix, the
allowed next-step strategy is one of the following, all gated by Charles's
per-message authorization:

### Option A: Frozen pre-freeze contract amendment + Charles freeze

- Future round: docs-only amendment PR on `main` that updates the
  pre-freeze contract's §10 change log with "2026-07-XX: contract frozen;
  Charles-approved".
- Required to satisfy pre-freeze §10 "awaiting Charles freeze review".
- This is a prerequisite for any Option B or Option C below.

### Option B: Explicit PR #21 supersession record

- Future round: a Charles-authored comment on PR #21 thread (NOT
  agent-authored) that records an explicit deferral decision per Phase 4
  §18.4 ("PR #21 is superseded by the new resumption PR per `docs/tasks/TASK-011B-phase-b-resumption-pre-freeze.md` §1.1").
- Or: a docs-only commit on `main` cross-referencing this governance
  record's §6 decision.
- Required to satisfy Phase 4 §18.4.

### Option C: Task 11 Phase B baseline-success-criteria document

- Future round: a new docs file (proposed
  `docs/tasks/TASK-011B-phase-b-baseline-success-criteria.md`) that
  records the baseline-success criteria for the
  `baseline-feasible.v1.json` evaluation scenario (and the
  `high-throughput-review.v1.json` scenario).
- Required to satisfy Phase 4 §18.5.

### Option D: Implementation round authorization (per pre-freeze §3)

- Future round: Charles's per-message authorization to cut a new branch
  (proposed `codex/task-11b-phase-b-resumption-from-main`), commit the
  implementation per the pre-freeze contract §4 allowed files, push the
  branch, and create a Draft PR.
- This is the actual Task 11B / Phase B resumption round. Requires
  Options A + B + C to be complete (or Charles explicitly accepts partial
  completion in his per-message authorization).
- NOT IN SCOPE for this governance record.

### Option E: Keep PR #21 frozen and archive/supersede later

- Future round: no action; PR #21 remains historical Draft/Open/Blocked
  indefinitely.
- Per Phase 4 §18.4, this requires an explicit deferred-reason record.

This governance record does **not** auto-select any option. The selection
is Charles's per-message authorization call.

---

## 9. Forbidden scope

For any future Task 11B resumption round, the following are forbidden
unless a future, separately authorized amendment expands the relevant
contract section:

### 9.1 Production / infrastructure / freeze-protected paths

- `backend/src/cold_storage/evaluation/production_seeding.py` — file
  remains absent; restoration is a stop condition (pre-freeze §8)
- All `backend/src/cold_storage/modules/*/infrastructure/*.py` production
  code (Phase 4 freeze)
- All `backend/src/cold_storage/modules/*/application/*.py` ports (Phase 2
  + Phase 4 freeze)
- All Alembic migrations under
  `backend/src/cold_storage/modules/*/infrastructure/migrations/versions/*.py`
  (Phase 1/2/3/4 freeze)
- `backend/src/cold_storage/bootstrap/**` (production bootstrap, freeze-
  protected by Phase 2 + Phase 4)
- `backend/src/cold_storage/modules/coefficients/application/**` (Phase 4
  freeze)

### 9.2 Non-production paths

- `frontend/**` (Task 11B is backend-only)
- `migrations/**` and `backend/alembic/versions/**` (no Alembic
  migration under resumption rounds unless a future contract explicitly
  authorizes)
- `.github/**` (workflow changes require separate authorization)
- `docker/**` and `docker-compose*.yml` and `Dockerfile*` (infrastructure
  changes require separate authorization)
- `pyproject.toml` and `uv.lock` (dependency changes require separate
  authorization)
- `package.json` and `package-lock.json` (frontend / Node changes; none
  expected)
- `scripts/**` (build / utility scripts)
- `backend/tests/conftest.py` and any other test infrastructure outside
  the pre-freeze §4.2 allowed test files (unless future contract
  explicitly authorizes)

### 9.3 Cross-track / governance-record paths

- PR #21 thread mutation (no comment / state / Ready / merge in this
  round or in any future round unless Charles explicitly authorizes)
- Issue #35 reopen (no close / reopen / comment in this round or in any
  future round unless Charles explicitly authorizes)
- TASK-011B contract files at `docs/tasks/TASK-011B-*.md` (frozen at
  their respective freeze times; any amendment requires a separate
  design-amendment round)

### 9.4 Token / auth operations

- No token read
- No token print
- No `gh auth login`
- No Authorization header echo
- No secret scanning bypass

---

## 10. Required authorization gates

The following gates must be passed in order before any future Task 11B
resumption implementation round can be authorized:

| gate | description | source | status at audit time |
|---|---|---|---|
| **Gate 1** | Charles 个人复审 of this governance record PR (or per-message authorization of a future amendment PR that supersedes this record). | this document §10 | ❌ (pending) |
| **Gate 2** | Charles 个人复审 + freeze authorization of `TASK-011B-phase-b-resumption-pre-freeze.md` (the contract's own §10 says "awaiting Charles freeze review"). | pre-freeze contract §10 | ❌ (pending) |
| **Gate 3** | Explicit PR #21 supersession / deferral decision recorded on PR #21 thread (per Phase 4 §18.4). | Phase 4 §18.4; pre-freeze §1.1 | ❌ (pending; this record does NOT auto-record) |
| **Gate 4** | Task 11 Phase B baseline-success-criteria document recorded (per Phase 4 §18.5). | Phase 4 §18.5 | ❌ (pending) |
| **Gate 5** | All Phase 4 §17 acceptance criteria met for any direct PR #21 resumption (per Phase 4 §17.6, requires Charles explicit authorization). | Phase 4 §17 | ❌ (5/6 unmet) |
| **Gate 6** | Charles 个人授权 of the future implementation round itself (per pre-freeze §3 + Phase 4 §18.7). | pre-freeze §3 + Phase 4 §18.7 | ❌ (pending) |
| **Gate 7** | Future Draft PR passes all 4 CI jobs (compose-config / frontend / backend-sqlite / backend-postgresql) before Ready. | Phase 4 §17.5 | ❌ (pending; future round's CI) |
| **Gate 8** | Charles 个人授权 of Ready transition for the future Draft PR. | this document §10 | ❌ (pending) |
| **Gate 9** | Charles 个人授权 of merge for the future Draft PR. | this document §10 | ❌ (pending) |

**Until all 9 gates pass**, no Task 11B implementation round may begin.
This is a hard boundary; no auto-skip is permitted.

---

## 11. Acceptance criteria for resumption

The future Task 11B resumption round is considered authorized for
implementation **only** when all of the following are met before any
implementation commit:

- [ ] This governance record is merged / frozen on `main`.
- [ ] Current `origin/main` is verified at the time of the future
  round's preflight.
- [ ] The future branch is created from current `origin/main` (not
  from a stale base).
- [ ] The future scope is explicitly bounded by an implementation
  contract that inherits the pre-freeze §4 allowed-files list and
  forbids the §9 list above.
- [ ] Required tests are explicitly listed in the future
  implementation contract (consistent with pre-freeze §3's §16 verification
  command pattern).
- [ ] No unresolved blocker from PR #21 comments / reviews remains (any
  blocker must be resolved or explicitly deferred).
- [ ] Charles's per-message authorization message explicitly names the
  implementation round, the branch name, the commit message, the PR
  title, and any other contract-specific deltas.

---

## 12. Stop conditions

Any of the following halts the future Task 11B resumption round
immediately:

- **Main HEAD drift** between this governance record's snapshot
  (`841917da...`) and the future round's preflight (must be re-verified
  and acknowledged).
- **Unclear allowed files** — the future round must inherit the
  pre-freeze §4 allowed-files list verbatim; if a new file is needed
  outside this list, the future round must STOP and request a
  design-amendment round, NOT silently expand.
- **Unclear relationship to PR #21** — direct PR #21 mutation (rebase,
  Ready, merge, comment) is forbidden unless Charles explicitly
  authorizes per Phase 4 §17.6 / §18.4 in the per-message authorization
  for the future round.
- **Unresolved blocker in PR #21 comments** — the binding decision in PR
  #21 Comment 16 ("Phase B remains blocked") must be explicitly
  superseded or replaced before the future resumption round may merge.
- **Missing required tests** in the future implementation contract
  (must list explicit test IDs / pytest nodes for each §16 verification
  command category).
- **Temptation to mutate PR #21 directly** — the design forward path is
  the pre-freeze §3 new-branch new-PR path; direct PR #21 rebase+merge
  is NOT the design (and requires re-passing the §17 acceptance criteria).
- **Temptation to close / reopen Issue #35** — Issue #35 closure is
  binding; the future round must NOT reopen Issue #35 unless Charles's
  per-message authorization explicitly authorizes an amendment to the
  Phase 4 governance contract.
- **Token / auth operations** — any unauthorized read / print / reuse of
  a credential, or any `gh auth login` attempt, halts the round.

A stop is reported with: stop condition name, evidence (file path,
server-side field value, audit-time snapshot, or commit SHA), and a
recommendation for next steps.

---

## 13. Evidence appendix

### 13.1 Audit-time evidence sources (server-side JSON)

- Issue #35 server-side JSON: `https://api.github.com/repos/xuezhiorange-png/cold-storage-planning-agent/issues/35`
  - state: `closed`
  - state_reason: `completed`
  - closed_at: `2026-07-08T05:27:57Z`
- Issue #35 comments: `https://api.github.com/repos/xuezhiorange-png/cold-storage-planning-agent/issues/35/comments?per_page=100`
  - 2 comments (Comment 1: PR #45 post-merge closeout, 2026-07-07; Comment 2: Decision Record — Issue #35 §16 #15 / §18 #4, 2026-07-08T05:22:00Z)
- PR #55 server-side JSON: `https://api.github.com/repos/xuezhiorange-png/cold-storage-planning-agent/pulls/55`
  - state: closed (merged)
  - merge_commit_sha: `9185b766de877c32557a355a6c6ce30d444154c0`
  - head_sha: `1036cce9f8840cd27dcd16f62bde60db980c6336`
  - 1 file / 597 insertions / 0 deletions
- PR #56 server-side JSON: `https://api.github.com/repos/xuezhiorange-png/cold-storage-planning-agent/pulls/56`
  - state: closed (merged)
  - merge_commit_sha: `841917da81828f6b9ab196e360a74757587eba8a`
  - head_sha: `66f7620a7644615b852564045d99487a7c8ebbea`
  - 5 files / 1,554 insertions / 0 deletions
- PR #21 server-side JSON: `https://api.github.com/repos/xuezhiorange-png/cold-storage-planning-agent/pulls/21`
  - state: open
  - draft: True
  - merged: False
  - mergeable: False
  - head_sha: `7822581eeee4c590b4ed9b1e3c46c1cde5490098`
  - base_sha: `e6dcd631059d1106947ff947ef8c5b9e1e214035`
  - updated_at: `2026-07-05T10:10:17Z`
  - 40 files / 15,450 insertions / 3 deletions / 16 comments
- PR #21 comments (server-side JSON):
  `https://api.github.com/repos/xuezhiorange-png/cold-storage-planning-agent/issues/21/comments?per_page=100`
  - 16 comments; the binding "Correction: Phase B remains blocked"
    decision is Comment 16 (id `4826759052`, 2026-06-28T16:51:24Z)
- Post-merge main CI run for PR #56: `29016039790` (server-side JSON),
  head_sha `841917da81828f6b9ab196e360a74757587eba8a`, event `push`,
  branch `main`, status `completed`, conclusion `success`, all 4
  required jobs green

### 13.2 Upstream frozen governance contracts (inherited verbatim)

- `docs/tasks/TASK-019-slice-3-validation-adapter-contract.md` (TASK-019
  Slice 3 design contract; merged via PR #52; merge commit
  `e237a9a14288a554b0043be4117bd818794d4b63`)
- `docs/tasks/TASK-019-slice-3a-placeholder-fixture-contract.md` (TASK-019
  Slice 3A fixture contract; merged via PR #53; merge commit
  `b5805d29e2b38da6fd8650176a6c0fef9e1f70b7`)
- `docs/tasks/TASK-019-slice-3b-adapter-implementation-contract.md`
  (TASK-019 Slice 3B implementation contract; merged via PR #55; merge
  commit `9185b766de877c32557a355a6c6ce30d444154c0`)
- `docs/tasks/TASK-019-slice-3b-implementation-closeout.md` (TASK-019
  Slice 3B implementation closeout; merged via PR #56)
- `docs/tasks/TASK-011B-path-a-design-ratification.md` (Path A design
  contract; frozen)
- `docs/tasks/TASK-011B-path-a-a1-a2-closeout.md` (Path A Phase 1 A1/A2
  closeout)
- `docs/tasks/TASK-011B-phase2-closeout.md` (Phase 2 ports/adapters
  closeout)
- `docs/tasks/TASK-011B-phase3-sourcebinding-schemeservice-e2e.md`
  (Phase 3 SourceBinding + SchemeService E2E closeout)
- `docs/tasks/TASK-011B-phase4-issue35-production-roundtrip-governance.md`
  (Phase 4 governance contract binding Issue #35 close; **defines the
  §17 / §18 acceptance criteria for PR #21 / Task 11 Phase B
  resumption**)
- `docs/tasks/TASK-011B-phase-b-resumption-pre-freeze.md` (the frozen
  pre-freeze design contract for Phase B resumption; **§1.1 supersedes
  PR #21; §3 specifies the future-branch and future-PR strategy; §4
  enumerates allowed future implementation files; §4.5 enumerates
  forbidden future implementation files**)

### 13.3 Prior audit verdict (input to this governance record)

- Audit round: `PR #21 / Task 11B resumption readiness audit`
- Audit-time date: 2026-07-09
- Audit verdict: **`PR21_TASK11B_RESUMPTION_REQUIRES_GOVERNANCE_RECORD`**
- Audit evidence file: `/root/pr21-task11b-resumption-audit-2026-07-09.md`
  (~26 KB; 9 sections; comprehensive cross-reference matrix of PR #21,
  Issue #35, PR #55, PR #56, TASK-011B governance contracts)

### 13.4 Branch / commit audit (this round)

This governance record was authored on a new docs-only branch from
`origin/main @ 841917da81828f6b9ab196e360a74757587eba8a`:

- Branch name: `docs/task-011b-governance-record`
- Base SHA: `origin/main @ 841917da...`
- HEAD (this commit): to be recorded at the time of the future Draft PR
  creation; the mutable-fact convention applies (HEAD SHA at commit
  time is recorded here at audit time; future rounds must
  externally-verify HEAD and CI via `git rev-parse` + `gh pr view` /
  unauth REST).

The branch push is part of the future round's Phase 7 (per the spec's
Phase 7 of the original governance-record authorization — push + Draft
PR creation). This governance record's text is committed locally on the
new branch; the future round will push the branch and create the Draft
PR in a separate operation.

---

## 14. Change log

| version | date | author | change |
|---|---|---|---|
| v1.0 | 2026-07-09 | Hermes (governance baseline record per spec Phase 3) | initial governance record; records server-side audit-time state for Issue #35 / PR #55 / PR #56 / PR #21 + post-merge main CI run; defines the §17 / §18 acceptance baseline for any future Task 11B resumption round; explicitly does NOT authorize implementation. Base SHA: `841917da81828f6b9ab196e360a74757587eba8a` (= `origin/main` HEAD at audit time, post-PR #56 merge). |
