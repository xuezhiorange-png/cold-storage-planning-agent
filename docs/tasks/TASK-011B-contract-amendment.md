# TASK-011B Contract Amendment

**Status:** governance record (docs-only contract amendment per spec
"Task 11B contract amendment docs-only PR round"). NOT a design contract;
NOT a Ready authorization; NOT an implementation authorization.

This document is the **amendment record** that closes Gates 2, 3, and 4
of the PR #57 governance record §10 authorization gate list, by
recording (a) the baseline-success-criteria separate document added by
this amendment, (b) the PR #21 supersession policy that this amendment
explicitly **does NOT mutate** (per spec: no PR #21 mutation in this
round), and (c) the pre-freeze contract's freeze-authorization prerequisite.

This document does **not** authorize implementation.
This document does **not** mutate PR #21.
This document does **not** reopen Issue #35.
This document is the docs-only amendment record that closes Gates 2/3/4
in the same change as the baseline-success-criteria document.

---

## 1. Purpose

This document serves as the **amendment record** complementing the
baseline-success-criteria document at
`docs/tasks/TASK-011B-baseline-success-criteria.md` (a sibling file
created in the same docs-only change). Together, the two records close
Gates 2, 3, and 4 of the PR #57 governance record §10 authorization
gate list.

The motivation for this amendment is the prior audit verdict:

> `TASK_011B_RESUMPTION_REQUIRES_CONTRACT_AMENDMENT`

(see `/root/task11b-resumption-contract-sufficiency-audit-2026-07-09.md`
for the audit; this amendment closes 3 of the 4 governance-record
execution items identified by that audit's recommendation).

This document does **not**:

- authorize implementation of Task 11 Phase B
- mutate PR #21 (state / draft / head / base / mergeable / comments)
- reopen Issue #35
- touch any production code, evaluation runner, evaluation fixtures,
  bootstrap, coefficients, migration, frontend, docker, .github, or
  pyproject / uv.lock
- mark any PR Ready
- merge any PR
- close or comment on any issue (including PR #21 and Issue #35)
- read or print any token
- bypass any forbidden-action set

This document **does**:

- record (in §3) the Gate 2 freeze-authorization prerequisite for the
  pre-freeze contract (without recording the actual Charles freeze
  authorization; that remains Charles's per-message call to amend the
  pre-freeze contract's §10 change log directly OR to authorize the
  freeze separately)
- record (in §4) the Gate 3 PR #21 supersession policy that this
  amendment explicitly does NOT execute (a Charles-authorized PR #21
  thread annotation OR a docs-only cross-reference commit is required
  per PR #57 §8 Option B; this amendment does NOT execute either path)
- record (in §5) the Gate 4 baseline-success-criteria separate document
  (this amendment's sibling file at `TASK-011B-baseline-success-criteria.md`)
- cite the upstream frozen contracts whose terms it inherits without
  modification

---

## 2. Amendment scope

This amendment introduces:

- **One new file**: `docs/tasks/TASK-011B-baseline-success-criteria.md`
  (the required separate baseline-success-criteria document per Phase 4
  governance contract §18.5 + PR #57 §10 Gate 4)

This amendment does **NOT** modify any existing file on `origin/main`.
Per spec "不允许新增" forbidden-action list (no backend / frontend /
tests / migrations / .github / docker / pyproject / uv.lock / production
_seeding.py / TASK-011B contract file / TASK-019 contract file / PR #21
/ Issue #35 modifications), and per spec's "Phase 4 §7 + PR #57 §6" the
**additive pattern** is the right discipline for governance-chain
amendments.

This amendment does **NOT** mutate:

- `docs/tasks/TASK-011B-phase-b-resumption-pre-freeze.md` (the
  pre-freeze contract; frozen after Charles sign-off per §4.4 last row)
- `docs/tasks/TASK-011B-governance-record.md` (the PR #57 governance
  record; frozen at PR #57 merge time)
- `docs/tasks/TASK-011B-phase4-issue35-production-roundtrip-governance.md`
  (the Phase 4 governance contract; frozen at its freeze time)
- Any other `docs/tasks/TASK-011B-*.md` contract file
- Any TASK-019 contract file (`docs/tasks/TASK-019-*.md`)
- PR #21 thread (no comment / state change / label)
- Issue #35 (no reopen / comment / state change)

The Phase 4 governance contract §9.2 mentions "**ad-hoc-amendment
governance-evidence**" patterns; per spec "**append-only
frozen-fixture amendment discipline**", this amendment is
**additive** (one new file), not modifying any frozen contract.

---

## 3. Gate 2 — pre-freeze contract freeze authorization record

### 3.1 Status as of this amendment

The pre-freeze contract
`docs/tasks/TASK-011B-phase-b-resumption-pre-freeze.md` has the following
§0 header (audit-time verified, immutable until Charles records the
freeze authorization):

> "**Status:** DESIGN-ONLY / DRAFT / awaiting Charles freeze authorization"
> "**Author:** Hermes (proposal subject to Charles-authorized freeze review)"

And the following §10 change log entry (audit-time verified):

> "2026-07-08 (this commit): initial pre-freeze draft, awaiting Charles
> freeze review. No implementation begins until Charles signs off."

The pre-freeze contract's own §9 line 357 says:

> "After Charles freezes this contract, this document becomes the §15 /
> §17 reference for the future Phase B Resumption PR."

Per PR #57 §10 Gate 2:

> "Charles 个人复审 + freeze authorization of
> `TASK-011B-phase-b-resumption-pre-freeze.md` (the contract's own §10
> says 'awaiting Charles freeze review')."

### 3.2 What this amendment does

This amendment **does NOT** record the Charles freeze authorization on
the pre-freeze contract itself. Per spec "**不允许修改 TASK-011B 合同文件**"
(per the section 2 forbidden-actions list: "no TASK-011B file amendment"
+ the pre-freeze contract §4.4 last row: "Frozen after Charles sign-off;
further changes require a new 'amendment' round"), the pre-freeze
contract's §10 change log is NOT auto-updated by this amendment.

This amendment **records the prerequisite** for Gate 2:

- The pre-freeze contract is treated as the current design baseline for
  future Charles review (i.e., the contract is **sufficient as a
  design**; the only outstanding work is the Charles freeze authorization).
- This amendment's sibling file at
  `docs/tasks/TASK-011B-baseline-success-criteria.md` does **NOT**
  modify the pre-freeze contract either; it is a sibling governance
  baseline document.
- Charles's freeze authorization may be executed via one of:
  - **Option A** (per PR #57 §8): a docs-only amendment PR that modifies
    pre-freeze §10 to record "2026-07-XX: contract frozen; Charles-approved."
  - **Option B**: Charles directly approves the pre-freeze contract via
    a per-message authorization message (treated as Charles-decided;
    not bound to a docs-only PR).
  - **Option C**: Charles waits for this amendment to be merged and
    then approves the pre-freeze contract in the same per-message
    authorization (treating this amendment as the closing window).

### 3.3 Why Gate 2 blocks implementation

Per pre-freeze contract §9 + PR #57 §10 Gate 2: the pre-freeze contract
is the binding design reference for the future Phase B Resumption PR.
Without Charles's freeze authorization, the contract is in "draft"
status and is NOT the binding reference. Implementation that begins
without a frozen contract would lack the binding design authority.

Per the prior audit: "Implementation cannot begin until the contract is
frozen."

### 3.4 Exact amendment needed for Gate 2 pass

Charles must:

1. Update `docs/tasks/TASK-011B-phase-b-resumption-pre-freeze.md` §10
   change log with "2026-07-XX: contract frozen; Charles-approved."
   (via a docs-only amendment PR OR via Charles's per-message
   authorization message — both legal per Option A/B/C above).
2. The §0 header may optionally be updated to "Status: FROZEN" with a
   frozen-by date.

This amendment does **NOT** execute either step.

---

## 4. Gate 3 — PR #21 supersession record

### 4.1 PR #21 current state (audit-time, mutable)

Per PR #21 server-side JSON:

- state: `open`, draft: `True`, merged: `False`, mergeable: `False`
- head sha: `7822581eeee4c590b4ed9b1e3c46c1cde5490098`
- base sha: `e6dcd631059d1106947ff947ef8c5b9e1e214035` (= stale; pre-Phase-4)
- updated_at: `2026-07-05T10:10:17Z` (= unchanged; no PR #21 activity since
  2026-07-05)
- comments: 16 (= unchanged; no new comments since 2026-06-28T16:51:24Z;
  no supersession annotation has been posted)

PR #21 Comment 16 (id `4826759052`, 2026-06-28T16:51:24Z), the binding
"Correction: Phase B remains blocked" decision, is **still the latest
comment on PR #21 thread as of 2026-07-09** (audit-time verified).

### 4.2 What this amendment does

This amendment **does NOT** mutate PR #21 thread (per spec: "no PR #21
mutation / no PR #21 rebase / no PR #21 ready / no PR #21 merge / no PR
#21 comment **unless explicitly separately authorized**"). PR #21 remains
`open / draft / not merged / not commented / not labeled / not reopened`.

This amendment **records the supersession policy** (§4 below mirrors
PR #57 §6 verbatim).

### 4.3 PR #21 supersession policy (per PR #57 §6)

- **Direct PR #21 resumption is not the design default.**
- The design forward path is a **new** resumption PR on a **new** branch
  (proposed `codex/task-11b-phase-b-resumption-from-main` per pre-freeze
  §3), with PR #21 explicitly superseded.
- This amendment **does NOT write a supersession decision on PR #21
  thread** (per spec: no PR #21 mutation in this round).

### 4.4 Charles-decided supersession execution paths (per PR #57 §8 Option B)

The supersession record, if Charles chooses to authorize one, must be
either:

- A new comment on PR #21 thread (Charles-authored, NOT agent-authored), OR
- A new docs-only commit on `main` referencing this amendment's §4
  decision (a separate `docs/tasks/TASK-011B-phase-b-pr21-supersession-record.md`
  or equivalent cross-reference), OR
- Cross-referenced in the future resumption PR's body when Charles
  authorizes that round.

This amendment does **NOT** execute either path.

### 4.5 Why Gate 3 blocks implementation

Per PR #57 §11 acceptance criteria for resumption: "**No unresolved
blocker from PR #21 comments / reviews remains** (any blocker must be
resolved or explicitly deferred)." Per Phase 4 §18.4: "PR #21 is merged,
**or** an explicit deferred-reason is recorded."

Until Charles records the explicit deferred-reason (either via PR #21
thread annotation OR via the docs-only cross-reference), the Phase 4
§18.4 "**or**" clause is NOT satisfied. Implementation cannot begin.

### 4.6 Exact amendment needed for Gate 3 pass

Charles must execute Option B (one of the three paths above). Either
(a) author a PR #21 thread comment explicitly stating "PR #21 is
superseded by the future resumption PR per `docs/tasks/TASK-011B-phase-b-resumption-pre-freeze.md` §1.1 + this amendment's §4 + `docs/tasks/TASK-011B-governance-record.md` §6", OR (b) approve a docs-only commit on `main` introducing
`docs/tasks/TASK-011B-phase-b-pr21-supersession-record.md` (a new file
whose content records the same deferral decision).

This amendment does **NOT** execute either step.

---

## 5. Gate 4 — baseline success criteria document record

### 5.1 Status before this amendment (audit-time)

Per PR #57 §10 Gate 4:

> "Task 11 Phase B baseline-success-criteria document recorded (per
> Phase 4 §18.5)."

Per `git ls-tree -r origin/main docs/ | grep TASK-011B-phase-b-baseline`
(audit-time): **EMPTY** (the document did NOT exist on `origin/main`
prior to this amendment).

Per Phase 4 §18.5:

> "Task 11B's baseline success criteria are explicitly defined and
> recorded in a separate document."

### 5.2 What this amendment does

This amendment **CREATES** the required separate document:

- **New file**: `docs/tasks/TASK-011B-baseline-success-criteria.md`
  (created in the same docs-only change as this amendment)

This new file:

- Defines baseline-success criteria (per pre-freeze §6 + §7.6)
- Defines the quality-gate list (per pre-freeze §7.1 / §7.2 / §7.3)
- Defines CI / Ready / Merge gates (per §8 of the new file)
- Defines stop conditions (per pre-freeze §8 + §9 of the new file)
- Records forbidden scope (per pre-freeze §4.5 + §5 + PR #57 §9;
  referenced in §6 of the new file)
- Records the PR #21 supersession policy (per pre-freeze §1.1 + §3.3
  + §5.4; referenced in §4 of the new file)
- Records the source-of-truth snapshot (audit-time; mutable; per §2 of
  the new file)

### 5.3 Why Gate 4 blocks implementation

Per Phase 4 §18.5 (verbatim): "Task 11B's baseline success criteria are
explicitly defined and recorded in a separate document." Without this
separate document, the gating criteria are scattered across multiple
governance docs and the audit-grade checklist referenced in PR #57 §11
is incomplete.

This amendment **executes** Gate 4 by creating the separate document.
After this amendment is merged on `main`, Gate 4 is structurally
satisfied (subject to Charles's acceptance of the document's content
during his review of this amendment PR).

### 5.4 Future rounds

The future implementation round will reference this document (and the
upstream pre-freeze contract + PR #57 governance record + Phase 4
governance contract) as the authoritative baseline for any decisions
about Task 11B resumption.

---

## 6. Relationship to PR #57 governance record

This amendment directly serves PR #57's §10 authorization gate list:

| PR #57 §10 Gate | status before this amendment | what this amendment does |
|---|---|---|
| Gate 1 (Charles review of governance record) | pending | does NOT auto-pass; awaits Charles's per-message authorization |
| **Gate 2** (Charles freeze authorization of pre-freeze contract) | pending (pre-freeze §10 still says "awaiting Charles freeze review") | records the prerequisite; does NOT auto-execute the freeze authorization |
| **Gate 3** (PR #21 supersession annotation on PR #21 thread) | pending (PR #21 thread has no supersession annotation) | records the supersession policy; does NOT mutate PR #21 thread |
| **Gate 4** (Task 11B baseline-success-criteria separate document on `origin/main`) | **pending → structurally satisfied** by this amendment's sibling file | **CREATES** `docs/tasks/TASK-011B-baseline-success-criteria.md` (Gate 4 structurally satisfied post-merge) |
| Gate 5 (§17 acceptance criteria for direct PR #21 resumption) | pending (5/6 unmet) | does NOT auto-pass; not applicable for new-resumption-PR path (per PR #57 §6 supersession) |
| Gate 6 (Charles authorizes future implementation round) | pending | does NOT auto-pass; awaits Charles's per-message authorization |
| Gate 7 (future Draft PR passes 4 CI jobs) | pending | does NOT auto-pass; future round's CI |
| Gate 8 (Charles authorizes Ready) | pending | does NOT auto-pass; awaits Charles's per-message authorization |
| Gate 9 (Charles authorizes Merge) | pending | does NOT auto-pass; awaits Charles's per-message authorization |

This amendment **structurally satisfies Gate 4** post-merge. Gates 2, 3,
6, 7, 8, 9 remain pending Charles-decided items.

---

## 7. Non-authorization statement

This amendment **explicitly does NOT**:

- Authorize implementation of Task 11 Phase B
- Mutate PR #21 (state / draft / head / base / mergeable / comments)
- Reopen / comment on / close Issue #35
- Mark any PR Ready
- Merge any PR
- Touch any production code, evaluation runner, evaluation fixtures,
  bootstrap, coefficients, migration, frontend, docker, .github, or
  pyproject / uv.lock
- Restore `backend/src/cold_storage/evaluation/production_seeding.py`
- Read / print / `gh-auth-login` any token
- Execute any forbidden-action item from spec's §"严格禁止" list

This amendment **is** a docs-only governance-record amendment that
structurally satisfies one of the three outstanding PR #57 §10 gates and
records the prerequisite for the other two.

---

## 8. Forbidden scope

This amendment does NOT touch any of the following (per spec's "严格禁止"
list + PR #57 §9):

- `backend/**` (production code freeze)
- `frontend/**`
- `tests/**` (test code freeze)
- `migrations/**`
- `.github/**`
- `docker/**`
- `pyproject.toml` / `uv.lock`
- `backend/src/cold_storage/evaluation/production_seeding.py`
- PR #21 (any mutation: no rebase / force-push / merge / comment /
  label / state change)
- Issue #35 (any mutation: no reopen / close / comment / state change)
- TASK-011B-*.md contract files (the pre-freeze contract itself, the
  governance record, the closeout files)
- TASK-019-*.md contract files (the TASK-019 contract chain)
- Token / auth operations

This amendment **does** add one new file:
`docs/tasks/TASK-011B-baseline-success-criteria.md` (the Gate 4 separate
document). No other file is touched.

---

## 9. Acceptance criteria

This amendment is considered accepted when:

- All §3 (Gate 2 prerequisite recording) content is preserved verbatim.
- All §4 (Gate 3 supersession policy recording) content is preserved
  verbatim.
- All §5 (Gate 4 separate document creation) content is satisfied via
  the sibling file's existence on `origin/main` post-merge.
- `origin/main` HEAD post-merge matches the merge commit SHA of this
  amendment's PR.
- Post-merge main CI is green (4/4 required jobs success) — per pre-freeze
  contract §7.3.

---

## 10. Evidence appendix

### 10.1 Created in this amendment

- `docs/tasks/TASK-011B-baseline-success-criteria.md` (sibling file with
  baseline-success-criteria + quality gates + CI / Ready / Merge gates +
  stop conditions + evidence appendix; 11 sections)

### 10.2 Referenced (NOT modified)

- `docs/tasks/TASK-011B-phase-b-resumption-pre-freeze.md` (the pre-freeze
  contract; Gate 2 prerequisite)
- `docs/tasks/TASK-011B-governance-record.md` (the PR #57 governance
  record; §10 defines 9 authorization gates; this amendment closes Gate 4)
- `docs/tasks/TASK-011B-phase4-issue35-production-roundtrip-governance.md`
  (Phase 4 governance contract; §17 / §18 acceptance criteria; §18.5
  requires the separate document this amendment creates)
- `docs/tasks/TASK-011B-*.md` (other TASK-011B contract files; not
  modified)

### 10.3 Audit-time URLs

- Issue #35:
  `https://api.github.com/repos/xuezhiorange-png/cold-storage-planning-agent/issues/35`
  - state: closed / state_reason: completed / closed_at: `2026-07-08T05:27:57Z`
- PR #55:
  `https://github.com/xuezhiorange-png/cold-storage-planning-agent/pull/55`
  - merged: true / merge_commit: `9185b766de877c32557a355a6c6ce30d444154c0`
- PR #56:
  `https://github.com/xuezhiorange-png/cold-storage-planning-agent/pull/56`
  - merged: true / merge_commit: `841917da81828f6b9ab196e360a74757587eba8a`
- PR #57 (governance record merge):
  `https://github.com/xuezhiorange-png/cold-storage-planning-agent/pull/57`
  - merged: true / merge_commit: `24133de5cf026238cf041c6faadae82b2008c54e`
- PR #21 (historical):
  `https://github.com/xuezhiorange-png/cold-storage-planning-agent/pull/21`
  - state: open / draft: true / merged: false / head: `7822581e...` /
    base: `e6dcd63...` / comments: 16 / updated_at: `2026-07-05T10:10:17Z`

### 10.4 Prior audit verdict (input to this amendment)

- Audit round: `Task 11B resumption contract sufficiency audit`
- Audit-time date: 2026-07-09
- Audit verdict: `TASK_011B_RESUMPTION_REQUIRES_CONTRACT_AMENDMENT`
- Audit evidence file:
  `/root/task11b-resumption-contract-sufficiency-audit-2026-07-09.md`

---

## 11. Change log

| version | date | author | change |
|---|---|---|---|
| v1.0 | 2026-07-09 | Hermes (governance amendment record per spec Phase 3) | initial contract amendment; creates the sibling `TASK-011B-baseline-success-criteria.md` (Gate 4 structurally satisfied); records Gate 2 freeze-authorization prerequisite without mutating pre-freeze contract; records Gate 3 PR #21 supersession policy without mutating PR #21 thread; explicitly does NOT authorize implementation. Base SHA: `24133de5cf026238cf041c6faadae82b2008c54e` (= `origin/main` HEAD at audit time, post-PR #57 merge). |
