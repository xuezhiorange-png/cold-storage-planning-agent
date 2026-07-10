# TASK-011B Gate 2 / Gate 3 Governance Closure

**Status:** docs-only governance closure record (Gate 2 / Gate 3 only).
**NOT a design contract. NOT a Ready authorization. NOT an implementation authorization.**

This document records the governance closure basis for Gate 2 (pre-freeze
contract freeze authorization basis) and Gate 3 (PR #21 supersession
basis) of the Task 11 Phase B resumption authorization model defined in
`docs/tasks/TASK-011B-governance-record.md` §10 / PR #57. It is a
sibling closure record, not a replacement for any upstream frozen
document, and it does **not** itself authorize implementation.

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

- record the source-of-truth snapshot (server-side, audit-time) the
  closure is grounded on
- record the Gate 2 closure basis (pre-freeze contract freeze
  authorization) without re-writing the contract
- record the Gate 3 closure basis (PR #21 supersession) without mutating
  PR #21
- list the future-gate sequence (Gates 4–9) and the explicit
  per-message authorizations each requires
- list the forbidden scope inherited from upstream frozen contracts
- cite the upstream frozen contracts whose terms it inherits without
  modification

---

## 1. Purpose

This document is a sibling closure record to the existing Task 11B
governance chain. The chain on `origin/main` already contains:

- `docs/tasks/TASK-011B-governance-record.md` (PR #57; defines 9 gates
  in §10; Gate 4 cross-references PR #57 §10)
- `docs/tasks/TASK-011B-contract-amendment.md` (the PR #58 sibling
  amendment record; structurally closes Gate 4 by creating
  `docs/tasks/TASK-011B-baseline-success-criteria.md`)
- `docs/tasks/TASK-011B-baseline-success-criteria.md` (Gate 4
  structurally satisfied document)
- `docs/tasks/TASK-011B-phase-b-resumption-pre-freeze.md` (the
  pre-freeze contract; §10 says "awaiting Charles freeze review")
- `docs/tasks/TASK-011B-phase4-issue35-production-roundtrip-governance.md`
  (Phase 4 governance; §17 + §18 acceptance criteria for PR #21 /
  Task 11 Phase B resumption)

This record **structurally** closes Gate 2 (records Charles's freeze
authorization basis of the pre-freeze contract as a resumption design
baseline) and Gate 3 (records PR #21 supersession as historical /
superseded candidate) by recording the closure in a new docs file on
a new branch off current `origin/main`, **without mutating any
existing frozen file or PR #21 thread**.

The closure basis is recorded here, not in the upstream frozen files,
because:

1. The frozen pre-freeze contract §10 explicitly says it is awaiting
   Charles freeze review; writing a freeze-authorization line directly
   into §10 would constitute a mutation of a frozen file outside the
   contract's own amendment discipline.
2. PR #21 thread mutation is forbidden by pre-freeze §5.4 + PR #57 §9.3
   and the Phase 4 governance contract §51; an explicit supersession
   record on PR #21 is therefore out-of-band Charles action, not agent
   action.
3. The sibling closure pattern (one new file, zero modifications to
   existing frozen files) mirrors the documented additive-only pattern
   of the PR #58 contract amendment round.

---

## 2. Source-of-truth snapshot

Server-side, audit-time snapshot captured via unauth REST per memory
**0-token fact-audit 协议**:

| artifact | state | sha / id |
|---|---|---|
| `origin/main` HEAD | current | `392f67b4ad14e6b7091159a1403f68fb422dad0d` (mutable; current at branch creation time) |
| Issue #35 | closed / completed | closed_at `2026-07-08T05:27:57Z` (stable) |
| PR #55 (TASK-019 Slice 3B contract) | merged / frozen | merge_commit_sha `9185b766de877c32557a355a6c6ce30d444154c0` (stable) |
| PR #56 (TASK-019 Slice 3B implementation) | merged / frozen on main | merge_commit_sha `841917da81828f6b9ab196e360a74757587eba8a` (stable) |
| PR #57 (Task 11B governance record) | merged / frozen on main | merge_commit_sha `24133de5cf026238cf041c6faadae82b2008c54e` (stable) |
| PR #58 (Task 11B contract amendment) | merged / frozen on main | merge_commit_sha `392f67b4ad14e6b7091159a1403f68fb422dad0d` (stable; equals current `origin/main`) |
| PR #21 (Task 11 Phase B historical Draft) | OPEN / Draft / NOT merged | head `7822581eeee4c590b4ed9b1e3c46c1cde5490098`; base `e6dcd631059d1106947ff947ef8c5b9e1e214035`; updated_at `2026-07-05T10:10:17Z` (mutable) |
| Post-merge main CI run (PR #58) | completed / success | run `29033833916`, head_sha `392f67b4ad14e6b7091159a1403f68fb422dad0d`, 4/4 jobs green (`compose-config`, `frontend`, `backend-sqlite`, `backend-postgresql`) |

Mutable facts are recorded here as **audit-time snapshots only** and
are **not** frozen. Any drift between this snapshot and a future round's
mutable facts must be detected via external verification at that round's
preflight, per the `mutable-facts discipline` (mutable facts are
intentionally not baked into governance docs).

---

## 3. Gate 2 closure — pre-freeze contract freeze authorization basis

**Pre-freeze contract** (the design baseline for any future Task 11
Phase B resumption):
`docs/tasks/TASK-011B-phase-b-resumption-pre-freeze.md` (HEAD 1, status
line: `DESIGN-ONLY / DRAFT / awaiting Charles freeze authorization`).

**This document records** the authorized governance closure basis for
Gate 2 by capturing the following points:

1. The pre-freeze contract **is the binding future-design baseline** for
   any Task 11 Phase B resumption round that Charles may authorize. Its
   §1.1 (PR #21 supersession), §1.2 (Phase B Resumption branch from
   current main), §1.3 (evaluation contract refresh), §1.4 (expected
   outputs regeneration), §1.5 (forbidden paths), §3 (new resumption
   branch strategy), §4 (allowed future implementation files), §5
   (forbidden future implementation paths), §6 (required success
   semantics), §7 (minimal validation matrix), §8 (stop conditions),
   §9 (governance) and §10 (change log) are inherited as **frozen text
   in this contract**, and any modification requires a separate
   design-amendment round per the contract's own §10.
2. **This Gate 2 closure does not authorize implementation.** The
   pre-freeze contract is the design baseline; implementation remains
   a separate Charles per-message authorization event under the 9-gate
   model (Gate 6 below).
3. **The future implementation branch must be created from the then-
   current `origin/main`** (NOT from PR #21 and NOT from a stale base),
   per pre-freeze §3 and PR #57 §11.
4. **The pre-freeze contract §10 ("awaiting Charles freeze review")
   line is not edited by this Gate 2 closure.** The closure record
   lives here in this sibling document, leaving the upstream frozen
   contract byte-for-byte unchanged (per the additive-only pattern
   established by the PR #58 contract amendment round).
5. **Any modification of the pre-freeze contract must follow its own §10
   change-log discipline** (future "amendment" round; not in scope for
   this docs-only closure).

**Authoritative references**:

- `docs/tasks/TASK-011B-phase-b-resumption-pre-freeze.md` §1 / §3 / §4 /
  §5 / §6 / §7 / §8 / §9 / §10
- `docs/tasks/TASK-011B-governance-record.md` §10 Gate 2 row
- `docs/tasks/TASK-011B-phase4-issue35-production-roundtrip-governance.md`
  §16 / §17 / §18

---

## 4. Gate 3 closure — PR #21 supersession basis

**PR #21** (Task 11 Phase B historical Draft):
`codex/task-11-evaluation` head `7822581eeee4c590b4ed9b1e3c46c1cde5490098`,
state `open`, draft `true`, merged `false`, mergeable `false`, base
`e6dcd631059d1106947ff947ef8c5b9e1e214035`, updated_at
`2026-07-05T10:10:17Z` (snapshot; mutable).

**This document records** the authorized governance closure basis for
Gate 3 by capturing the following points:

1. **PR #21 remains OPEN / Draft / Not merged.** This record does not
   mutate PR #21 in any way (no state change, no comment, no body edit,
   no label change, no Ready, no merge, no close).
2. **PR #21 is designated a "historical / superseded candidate"**
   under the pre-freeze contract §1.1 ("PR #21 should be marked
   Superseded and remain Draft / Open / Not merged. PR #21's branch
   ref `codex/task-11-evaluation` is not rebased, force-pushed,
   merged, or touched in this round.") and §5.4 ("DO NOT rebase,
   force-push, merge, comment on, label, or otherwise mutate PR #21 in
   any resumption round").
3. **PR #21 is not the direct implementation target** for any future
   Task 11 Phase B resumption round. The design forward path is a new
   branch off the then-current `origin/main` (proposed branch name in
   pre-freeze §3: `codex/task-11b-phase-b-resumption-from-main`),
   **not** a direct PR #21 rebase / Ready / merge.
4. **PR #21 is retained as historical context / superseded candidate**
   until Charles separately authorizes a different route via
   per-message authorization. The §1.1 designation of PR #21 as
   "Superseded" is recorded in this sibling document rather than as a
   comment on PR #21 thread, per the per-round prohibition against PR
   #21 thread mutation (PR #57 §9.3 + pre-freeze §5.4).
5. **Unless Charles explicitly overrides this route via a future
   per-message authorization**, PR #21 remains untouched and is **not**
   the implementation branch. PR #21's head SHA
   `7822581eeee4c590b4ed9b1e3c46c1cde5490098` is preserved as the
   branch ref for any future PR #21 round if Charles decides to revive
   it.

**Authoritative references**:

- `docs/tasks/TASK-011B-phase-b-resumption-pre-freeze.md` §1.1 + §3.3 +
  §5.4 + §7.4 + §9
- `docs/tasks/TASK-011B-governance-record.md` §5 + §6 + §10 Gate 3 row
- `docs/tasks/TASK-011B-phase4-issue35-production-roundtrip-governance.md`
  §17 + §18.4

---

## 5. Relationship to PR #57 and PR #58

This record is downstream of the PR #57 governance record and the PR
#58 contract amendment round:

- **PR #57** (merged) — `docs/tasks/TASK-011B-governance-record.md`
  defines the 9-gate authorization model (Gate 1 review / Gate 2 freeze
  / Gate 3 PR #21 supersession / Gate 4 baseline-success-criteria /
  Gate 5 §17 met / Gate 6 implementation authorization / Gate 7 Draft
  PR CI green / Gate 8 Ready authorization / Gate 9 Merge
  authorization). Gate 4 was structurally satisfied by PR #58; Gates 2
  and 3 were documented as pending governance actions at PR #57 freeze
  time.
- **PR #58** (merged) — `docs/tasks/TASK-011B-contract-amendment.md` is
  the sibling contract-amendment round; it created
  `docs/tasks/TASK-011B-baseline-success-criteria.md` to structurally
  close Gate 4. PR #58 is the immediate ancestor commit on current
  `origin/main` (`392f67b4ad14e6b7091159a1403f68fb422dad0d`).
- **This record** — sibling closure record for Gates 2 and 3.
  Adopts the additive-only / sibling-file pattern of PR #58 (one new
  file + zero modifications to frozen upstream contracts + zero PR #21
  thread mutation + zero Issue #35 mutation). After this record is
  merged to `main` and the post-merge main CI run is green, **Gates 2
  and 3 are structurally closed** in the 9-gate model.

This record does **not** modify PR #57 / PR #58 / their merge commits
or their bodies. The 9-gate model remains owned by PR #57 §10; this
record is downstream of it.

---

## 6. Non-authorization statement

This document is a docs-only governance closure record. It does **not**
authorize any of the following:

- Task 11 Phase B implementation
- Task 11B implementation
- TASK-011B implementation
- backend changes (production code, ports, infrastructure, evaluation
  runner, evaluation fixtures, bootstrap, coefficients)
- frontend changes
- tests changes
- migrations (Alembic, under any path)
- `.github` changes
- docker changes
- `pyproject.toml` / `uv.lock` changes
- `production_seeding.py` restoration (Round 11 reversal; per pre-freeze
  §4.5 + §5.1 + §8.1)
- PR #21 mutation (no state / draft / head / base / mergeable /
  comments / labels / Ready / merge / rebase / force-push)
- Issue #35 mutation (no reopen / close / comment / label)
- Marking any PR Ready
- Merging any PR
- Reading or printing any token
- Bypassing any forbidden-action set

This document is the **gate-closure record**, not the gate-action
authorization. Implementation authorization is a separate Charles
per-message event under Gate 6 (see §7 below).

---

## 7. Future implementation authorization requirements

After this record is merged to `main` and the post-merge main CI run
is green, the 9-gate model status is:

| gate | status after this round's merge | next authorization required |
|---|---|---|
| **Gate 1** — Charles review governance record | ✅ closed (PR #57) | n/a |
| **Gate 2** — pre-freeze contract freeze authorization basis | ✅ **structurally closed** by this record (merged + post-merge main CI green) | n/a |
| **Gate 3** — PR #21 supersession record | ✅ **structurally closed** by this record (merged + post-merge main CI green) | n/a |
| **Gate 4** — baseline-success-criteria separate document on `origin/main` | ✅ already closed by PR #58 (creates `TASK-011B-baseline-success-criteria.md`) | n/a |
| **Gate 5** — §17 acceptance criteria met (PR #21 unblock review) | ❌ still 5/6 unmet (per PR #57 §7.1; superseded by Gate 3 path) | n/a (Gate 5 is the direct-PR-#21-unblock path; superseded by Gate 3 supersession path) |
| **Gate 6** — Charles explicitly authorizes Task 11 Phase B implementation round | ❌ pending | requires **separate Charles per-message authorization** for: branch name, base SHA (= then-current `origin/main`), commit message(s), allowed-files subset of pre-freeze §4, required-tests subset of pre-freeze §7.1, frozen-contract deltas, post-conditions, sign-off mechanism |
| **Gate 7** — future Draft PR CI green (4 jobs) | ❌ pending | requires implementation round + Draft PR + post-PR-side CI run with all 4 jobs green (per pre-freeze §7.3 + §7.4) |
| **Gate 8** — Ready authorization | ❌ pending | requires **separate Charles per-message authorization** marking the future implementation Draft PR Ready |
| **Gate 9** — Merge authorization | ❌ pending | requires **separate Charles per-message authorization** merging the future implementation PR |

**Implementation round authorization gate (Gate 6) prerequisites** —
Charles's per-message authorization must explicitly include:

1. Branch name and base SHA (then-current `origin/main`).
2. Pre-freeze §4 allowed-files subset the round will modify.
3. Pre-freeze §7.1 required-tests subset the round will run.
4. Any contract-specific deltas (none expected by default; any amendment
   requires its own round).
5. Sign-off mechanism for the §1.4 expected-output regeneration.
6. Stop conditions acknowledged per pre-freeze §8.
7. Confirmation that PR #21 remains untouched in the implementation
   round.
8. Confirmation that Issue #35 remains closed in the implementation
   round.

The future implementation round is **not** auto-authorized by this
record's merge. It requires Charles's per-message authorization.

---

## 8. Forbidden scope

The forbidden scope for any future Task 11B / TASK-011B / Task 11 Phase
B round is inherited verbatim from the upstream frozen contracts:

### 8.1 Production / infrastructure / freeze-protected paths
(pre-freeze §4.5 + §5; PR #57 §9.1)

- `backend/src/cold_storage/evaluation/production_seeding.py` — file
  remains absent; restoration is a pre-freeze §8 stop condition.
- All `backend/src/cold_storage/modules/*/infrastructure/*.py`
  production code (Phase 4 freeze).
- All `backend/src/cold_storage/modules/*/application/*.py` ports
  (Phase 2 + Phase 4 freeze).
- All Alembic migrations under
  `backend/src/cold_storage/modules/*/infrastructure/migrations/versions/*.py`
  (Phase 1/2/3/4 freeze).
- `backend/src/cold_storage/bootstrap/**` (production bootstrap).
- `backend/src/cold_storage/modules/coefficients/application/**`
  (Phase 4 freeze).

### 8.2 Non-production paths
(PR #57 §9.2; pre-freeze §5.5)

- `frontend/**`
- `migrations/**` and `backend/alembic/versions/**`
- `.github/**`
- `docker/**` and `docker-compose*.yml` and `Dockerfile*`
- `pyproject.toml` and `uv.lock`
- `package.json` and `package-lock.json`
- `scripts/**`
- `backend/tests/conftest.py` and any other test infrastructure outside
  pre-freeze §4.2 allowed test files.

### 8.3 PR #21 / Issue #35 / Task 11B governance-doc paths
(PR #57 §9.3; pre-freeze §5.4)

- PR #21 thread mutation (no comment / state / Ready / merge / rebase /
  force-push / label in this round or any future round unless Charles
  explicitly authorizes).
- Issue #35 reopen (no close / reopen / comment / label in this round
  or any future round unless Charles explicitly authorizes).
- TASK-011B contract files at `docs/tasks/TASK-011B-*.md` (frozen at
  their respective freeze times; any amendment requires a separate
  design-amendment round per pre-freeze §10).

### 8.4 Production invariants (pre-freeze §5.3)

- No demo / latest-row / partial-binding fallbacks in production path.
- No suppression / rename / downgrade of `requires_review` warnings or
  `UntrustedCoefficientError` raise paths.
- No alteration of production formulas, coefficient values, scoring
  rules, review rules, thresholds, or weights.
- No bypass of `SourceBindingVerifier` or `SchemeService`.
- No bypass of approved non-demo coefficient governance.

### 8.5 Evaluation-owned production row fabrication (pre-freeze §5.2)

- No module under `backend/src/cold_storage/evaluation/` writes
  `CalculationRunRecord`, `SourceBindingRecord`, orchestration identity /
  attempt / execution-snapshot / coefficient-context rows, or
  approved weight-set revision rows from evaluation code.
- No evaluation-owned calculation input bridges (e.g., `cooling_load` /
  `equipment` inputs derived from upstream stage outputs in evaluation
  code).

---

## 9. Acceptance criteria

This record is acceptable (verdict:
`TASK_011B_GATE_2_3_GOVERNANCE_CLOSURE_REIMPLEMENTED_*`) iff all of the
following hold:

1. ✅ This file is the only file modified by the implementation commit
   on the rebuild branch.
2. ✅ Working tree is clean at branch creation time; commit is added
   with this single file only.
3. ✅ No file under `backend/`, `frontend/`, `tests/`, `migrations/`,
   `.github/`, `docker/`, `pyproject.toml`, `uv.lock`,
   `production_seeding.py` is touched.
4. ✅ PR #21 remains untouched at branch creation, commit, push, and
   Draft PR creation (no comment / state / head / base / Ready /
   merge).
5. ✅ Issue #35 remains untouched (no reopen / comment / label).
6. ✅ TASK-011B implementation is not started.
7. ✅ No Ready / Merge performed.
8. ✅ No token is read or printed.
9. ✅ `git diff --check` clean.
10. ✅ Pre-freeze contract files (`docs/tasks/TASK-011B-*.md`) other
    than this new sibling record are not modified.
11. ✅ Branch is created from current `origin/main` (snapshot
    `392f67b4ad14e6b7091159a1403f68fb422dad0d` at branch creation).
12. ✅ Push verifies `git ls-remote origin <branch>` returns the commit
    SHA from `git rev-parse HEAD`.
13. ✅ If Draft PR creation is authorized, it is created with
    `isDraft: true` and `main` as base; if `gh auth` is blocked, the
    body file is prepared at `/root/PR59-body.md` and the verdict is
    `READY_FOR_DRAFT_PR`.
14. ✅ The `fcc24cea26b441e2c0e0b94fed271ef0223ef0de` SHA from prior
    round's fabrication is **not** referenced, refreshed, or reused.

---

## 10. Evidence appendix

### 10.1 Authoritative source-of-truth documents (on `origin/main` HEAD
`392f67b4ad14e6b7091159a1403f68fb422dad0d`)

- `docs/tasks/TASK-011B-phase-b-resumption-pre-freeze.md` (Gate 2
  pre-freeze contract; §1 / §3 / §4 / §5 / §6 / §7 / §8 / §9 / §10
  inherited verbatim)
- `docs/tasks/TASK-011B-governance-record.md` (PR #57; §10 9-gate
  model)
- `docs/tasks/TASK-011B-contract-amendment.md` (PR #58 sibling
  amendment record)
- `docs/tasks/TASK-011B-baseline-success-criteria.md` (PR #58 sibling;
  Gate 4 structurally closed)
- `docs/tasks/TASK-011B-phase4-issue35-production-roundtrip-governance.md`
  (Phase 4 governance; §16 / §17 / §18)

### 10.2 Server-side audit-time references (snapshot, mutable)

- PR #55 server-side JSON:
  `https://api.github.com/repos/xuezhiorange-png/cold-storage-planning-agent/pulls/55`
- PR #56 server-side JSON:
  `https://api.github.com/repos/xuezhiorange-png/cold-storage-planning-agent/pulls/56`
- PR #57 server-side JSON:
  `https://api.github.com/repos/xuezhiorange-png/cold-storage-planning-agent/pulls/57`
- PR #58 server-side JSON:
  `https://api.github.com/repos/xuezhiorange-png/cold-storage-planning-agent/pulls/58`
- Issue #35 server-side JSON:
  `https://api.github.com/repos/xuezhiorange-png/cold-storage-planning-agent/issues/35`
- PR #21 server-side JSON:
  `https://api.github.com/repos/xuezhiorange-png/cold-storage-planning-agent/pulls/21`
- PR #58 post-merge main CI run `29033833916`:
  `https://api.github.com/repos/xuezhiorange-png/cold-storage-planning-agent/actions/runs/29033833916`

### 10.3 Non-authorization explicit enumeration

This record does NOT perform any of the following:

- ❌ Ready PR #59 (Draft only, or READY_FOR_DRAFT_PR if `gh auth`
  blocked)
- ❌ Merge PR #59
- ❌ Create / mutate / comment / label / close / reopen PR #21
- ❌ Create / mutate / comment / label / close / reopen Issue #35
- ❌ Modify any frozen TASK-011B contract file
- ❌ Start Task 11B / TASK-011B implementation
- ❌ Restore `production_seeding.py`
- ❌ Modify backend / frontend / tests / migrations / `.github` /
  docker / `pyproject.toml` / `uv.lock`
- ❌ Reuse or reference the fabricated prior-round SHA
  `fcc24cea26b441e2c0e0b94fed271ef0223ef0de`
- ❌ Read or print any token

### 10.4 Forward discipline

This record ends with `STOP — awaiting Charles personal review and
Charles-authorized next-step authorization`. Per-round authorization
remains the binding model; no implicit authorization flows from this
record's merge.

---

## 11. Change log

| version | date | author | change |
|---|---|---|---|
| v1.0 | 2026-07-10 | Hermes (docs-only closure record) | initial Gate 2 + Gate 3 closure record; records the pre-freeze contract freeze authorization basis (Gate 2) and the PR #21 supersession basis (Gate 3) without mutating the upstream frozen contracts or PR #21 thread; sibling closure pattern mirroring PR #58's additive-only discipline; explicitly does NOT authorize implementation; Gate 4 already closed by PR #58; Gates 6 / 7 / 8 / 9 still pending Charles per-message authorization. Base SHA: `392f67b4ad14e6b7091159a1403f68fb422dad0d` (= `origin/main` HEAD at branch creation, post-PR #58 merge). |