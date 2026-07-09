# TASK-019 Slice 3A — Placeholder Fixture Contract

**Status:** FIXTURE CONTRACT ONLY / IMPLEMENTATION NOT AUTHORIZED / ADAPTER IMPLEMENTATION NOT AUTHORIZED / EXPECTED OUTPUT AUTHORING NOT AUTHORIZED
**Created:** 2026-07-09 (server UTC)
**Author:** Hermes (placeholder fixture contract authoring, awaiting Charles freeze + amendment authorization)
**Base SHA:** `e237a9a14288a554b0043be4117bd818794d4b63` (= `origin/main` HEAD post-PR-#52-merge)
**Source contract (frozen):** `docs/tasks/TASK-019-slice-3-validation-adapter-contract.md` (merged via PR #52; merge commit `e237a9a14288a554b0043be4117bd818794d4b63`)
**Branch base:** `main @ e237a9a14288a554b0043be4117bd818794d4b63` (= `origin/main` HEAD post-PR-#52)
**Branch name:** `docs/task-019-slice-3a-placeholder-fixtures`
**Target Phase:** TASK-019 Slice 3A (placeholder fixture contract; precedes Slice 3B adapter-only implementation)
**Authoritative references:**
- `docs/tasks/TASK-019-slice-3-validation-adapter-contract.md` (frozen design contract, PR #52)
- PR #52 (`Task 019 Slice 3 validation adapter design contract`) — `closed / merged` / merge commit `e237a9a14288a554b0043be4117bd818794d4b63` / merged at `2026-07-08T23:58:56Z`
- Post-merge main CI run `28984086570` (run_number 1071) — `completed / success / 4/4 jobs green`

> **Mutable-facts discipline:** Stable identifiers (PR #, Issue #, base SHA, branch, contract path) are recorded in this file. Mutable facts (current PR head SHA, current CI run id, current branch tip, current PR/Issue state) are **intentionally not frozen in this mutable branch row**; they are re-verified externally during any future review / freeze / amendment authorization round. The same discipline was adopted in the source design contract (PR #52, `docs/tasks/TASK-019-slice-3-validation-adapter-contract.md`) under the heading "Mutable PR-identity trap".

---

## 1. Status

This document is a **placeholder fixture contract** for TASK-019 Slice 3A.
It is **not** an implementation authorization. Specifically:

- **FIXTURE CONTRACT ONLY.** No validation-adapter implementation, no
  `ValidationReport` production model, no production-path call, no
  fixture-authoring that invents a real expected output, no fixture that
  pretends a placeholder is success, is authorized by this document.
- **IMPLEMENTATION NOT AUTHORIZED.** This document defines the **shape**
  of placeholder fixtures and the **fixture-contract test** that
  validates the shape. It does **not** authorize any future
  implementation round.
- **ADAPTER IMPLEMENTATION NOT AUTHORIZED.** The thin validation
  adapter (per the source contract §7) and the `ValidationReport`
  production model (per the source contract §8) are not authorized by
  this document. Their implementation requires a separate, explicit
  Charles authorization (see §11 Next authorization required).
- **EXPECTED OUTPUT AUTHORING NOT AUTHORIZED.** No real expected output
  is invented or hard-coded in this document or in the placeholder
  fixtures. A future expected-output-authoring round, if and when
  authorized, must produce real expected values via a frozen production
  path (not via hand-writing).

---

## 2. Problem statement

The frozen design contract (`docs/tasks/TASK-019-slice-3-validation-adapter-contract.md`,
PR #52 merge commit `e237a9a14288a554b0043be4117bd818794d4b63`) defines
the **shape** of fixtures (§6) and the **status enum** that the future
adapter must use (§5), but it does not yet define **any actual
placeholder case data**. Without on-disk placeholder cases, a future
adapter-only implementation round would have to:

- invent fixture data inline (violating the design contract §4 "no
  fixture expected-output invention"), or
- depend on verbal / memory handoff (violating the governance
  discipline adopted in the source design contract §0).

This document establishes the on-disk placeholder fixture contract so
that a future Slice 3B adapter-only implementation round has stable,
shape-only placeholder inputs to work with, and the future adapter's
classification of each case can be tested against an
externally-defined expected status **without** any real expected
output being invented.

---

## 3. Allowed files for this Slice 3A contract (suggested, this round)

This round creates / modifies **only** the following files:

| path | role |
|---|---|
| `docs/tasks/TASK-019-slice-3a-placeholder-fixture-contract.md` | this file (docs contract) |
| `backend/tests/validation/__init__.py` | new (empty, parallel to existing `tests/__init__.py`) |
| `backend/tests/validation/_task_019_slice_3_placeholder_fixtures.py` | placeholder fixture case data (3 cases) |
| `backend/tests/validation/test_task_019_slice_3_placeholder_fixtures.py` | fixture-contract test (shape only) |

**Discipline**: actual implementation requires Charles's explicit
authorization in a follow-up round. The candidate paths above are the
**only** files this round is allowed to touch. The implementation
round (Slice 3B) will be allowed to touch a separate, larger set of
candidate paths (per the source contract §9), and that round is
**not** this round.

---

## 4. Forbidden scope (this round)

The following are **explicitly forbidden** in this Slice 3A
placeholder fixture contract:

- **No validation-adapter implementation.** No
  `backend/src/cold_storage/validation/adapter.py`, no
  `backend/src/cold_storage/validation/report.py`. The adapter and
  report code is a Slice 3B concern, not Slice 3A.
- **No production-path call.** No call to any
  `cold_storage.modules.*` / `cold_storage.evaluation.*` module from
  the placeholder fixtures or the fixture-contract test.
- **No SQLAlchemy session.** No `session_factory`, no
  `Session(...)`, no `session.execute(...)`, no raw SQL.
- **No real expected output invention.** No numeric value, no
  engineering unit (kW, m^2, CNY, etc.), no formula in any
  `expected_output` field. The only allowed content of
  `expected_output` is the `placeholder: True` flag and a
  human-readable `reason`.
- **No pressure-drop implementation.** Pressure-drop does not exist
  in this repository as of the base SHA. No reference to it; no
  forbidden-import test for it; nothing.
- **No production formula / coefficient / threshold / weight /
  scoring rule mutation.** The placeholder fixtures and the
  fixture-contract test must not import any production formula, must
  not call any production calculator, must not read any coefficient
  resolver. They are shape-only.
- **No `production_seeding.py` restoration.** The forbidden file
  remains absent.
- **No migration.** No Alembic migration under this contract.
- **No frontend mutation.** Slice 3A is backend-docs-and-tests only.
- **No API expansion.** No new REST endpoint, no new GraphQL query,
  no new CLI command.
- **No Task 11B / PR #21 / Issue #35 mutation.** Untouched.
- **No comment / Ready / merge / close-issue mutation** in this round.
- **No push unless Charles explicitly authorizes** a follow-up round.
- **No fixture-authoring that pretends a placeholder is success.**
  Every placeholder case must carry an `expected_status` of
  `placeholder` or `requires_upstream_slice` or `blocked`, never
  `implemented`.
- **No fixture-authoring that hard-codes a real expected value.**
  Every `expected_output` is a placeholder; the fixture-contract test
  explicitly forbids forbidden real-value keys (`value`, `kW`, `m2`,
  `m^2`, `CNY`, `formula`, etc.).

---

## 5. Fixture case list (3 placeholder cases)

Three placeholder cases are defined in
`backend/tests/validation/_task_019_slice_3_placeholder_fixtures.py`:

### 5.1 `case_01_smoke_placeholder`

| field | value |
|---|---|
| `task_id` | `TASK-019` |
| `slice_id` | `slice-3` |
| `case_id` | `case_01_smoke_placeholder` |
| `inputs` | `{ "placeholder": True, "reason": "TBD-by-Slice-3A fixture contract only; smoke-test the placeholder shape." }` |
| `expected_output` | `{ "placeholder": True, "reason": "No real expected output authorized for this case." }` |
| `requires_slice` | `None` |
| `expected_status` | `placeholder` |
| `placeholder_fields` | `["inputs", "expected_output"]` |
| `reason` | Smoke case used to verify the placeholder shape is well-formed. Both inputs and expected_output are explicitly placeholder; no real expected value is asserted. |
| `source_references` | `[<source contract path>, <this contract path>]` |

### 5.2 `case_02_requires_upstream_slice`

| field | value |
|---|---|
| `task_id` | `TASK-019` |
| `slice_id` | `slice-3` |
| `case_id` | `case_02_requires_upstream_slice` |
| `inputs` | `{ "placeholder": True, "reason": "TBD-by-Slice-3A; this case requires an upstream TASK-019 slice (e.g., Slice 1 or Slice 2) that has not yet been authored." }` |
| `expected_output` | `{ "placeholder": True, "reason": "Cannot be produced until the upstream slice completes; not a real expected value, and not a failure." }` |
| `requires_slice` | `"slice-1"` (upstream slice identifier, per source contract §6) |
| `expected_status` | `requires_upstream_slice` |
| `placeholder_fields` | `["inputs", "expected_output"]` |
| `reason` | Case requires an upstream TASK-019 slice that has not been authored. The future adapter must classify it as `requires_upstream_slice`, not as `implemented` and not as `failure`. |
| `source_references` | `[<source contract path>, <this contract path>]` |

### 5.3 `case_03_malformed_or_blocked_placeholder`

| field | value |
|---|---|
| `task_id` | `TASK-019` |
| `slice_id` | `slice-3` |
| `case_id` | `case_03_malformed_or_blocked_placeholder` |
| `inputs` | `{ "placeholder": False, "missing_required_field": "intentionally_absent", "reason": "..." }` (intentionally structurally invalid to exercise the `blocked` path) |
| `expected_output` | `{ "placeholder": True, "reason": "Cannot be produced; inputs are structurally invalid. The future adapter must classify this case as `blocked`, not as `placeholder` and not as `implemented`." }` |
| `requires_slice` | `None` |
| `expected_status` | `blocked` |
| `placeholder_fields` | `["expected_output"]` |
| `reason` | Intentionally malformed to exercise the `blocked` status path per the source contract §5. The `blocked` status is reserved for cases where the contract or the inputs are not executable; it is neither success nor ordinary skip. This is the only kind of case the future adapter is allowed to classify as `blocked`. |
| `source_references` | `[<source contract path>, <this contract path>]` |

---

## 6. Placeholder semantics (per source contract §5 + §6)

- **`placeholder` is not success.** A placeholder case must be
  reported by the future adapter as `placeholder` (or
  `requires_upstream_slice`, depending on the case). The fixture-contract
  test enforces: if `expected_output.placeholder is True`, then
  `expected_status != "implemented"`.
- **`requires_upstream_slice` is not failure.** A case with
  `requires_slice` non-null must be reported as
  `requires_upstream_slice`. The fixture-contract test enforces: if
  `requires_slice` is set, then `expected_status == "requires_upstream_slice"`.
- **`blocked` is reserved for malformed / contract-invalid cases.**
  The future adapter is allowed to classify a case as `blocked` only
  if the case is structurally invalid (per the source contract §5
  "the contract or the inputs are not executable"). The
  `case_03_malformed_or_blocked_placeholder` case is the only case
  in the fixture set that exercises this status.
- **`implemented` is reserved for cases with real expected output.**
  No case in this fixture set has a real expected output, so no case
  has `expected_status == "implemented"`. The fixture-contract test
  enforces this: every case with `expected_output.placeholder is True`
  has `expected_status != "implemented"`.

---

## 7. Fixture-contract test scope

The fixture-contract test in
`backend/tests/validation/test_task_019_slice_3_placeholder_fixtures.py`
covers **shape only**. It does **not**:

- call the validation adapter (the adapter is not authorized in this
  round);
- call any production calculation;
- open a database session;
- snapshot or assert against any real expected output;
- generate any report artifact.

The fixture-contract test enforces:

- `case_id` uniqueness across the case list.
- Minimum case count (≥ 3).
- `task_id == "TASK-019"` and `slice_id == "slice-3"` for every case.
- All required fields per the source contract §6/§8 are present
  (`case_id`, `task_id`, `slice_id`, `inputs`, `expected_output`,
  `expected_status`, `placeholder_fields`, `reason`, `source_references`).
- `expected_status` is in the closed set defined by the source
  contract §5.
- A placeholder case lists at least one field in `placeholder_fields`.
- A case with `expected_output.placeholder is True` does not have
  `expected_status == "implemented"`.
- A case with `requires_slice` non-null has
  `expected_status == "requires_upstream_slice"`.
- `source_references` includes the source design contract path.
- `expected_output` does not contain any real-value key
  (`value`, `kW`, `m2`, `m^2`, `CNY`, `formula`, etc.).
- `get_case_by_id` round-trips for every known `case_id`.
- `iter_cases` is an immutable view (returns the same tuple every call).

The fixture-contract test is **not** a substitute for a future
adapter-only implementation round. It only validates the **shape** of
the placeholder fixtures; it does not validate the future adapter's
**behavior**.

---

## 8. Stop conditions (this Slice 3A round)

A future follow-up round, if and when authorized, must **STOP** and
surface the blocker to Charles in any of the following cases:

- **STOP** if the implementation requires mutation of any production
  formula, coefficient, threshold, weight, or scoring rule.
- **STOP** if the implementation requires inventing a real expected
  output for any of the three placeholder cases.
- **STOP** if the implementation requires a pressure-drop
  implementation.
- **STOP** if the implementation requires `production_seeding.py`
  restoration or any production-row seeding.
- **STOP** if the implementation requires a migration.
- **STOP** if the implementation requires a frontend mutation.
- **STOP** if the implementation requires an API expansion.
- **STOP** if the implementation requires touching PR #21 or
  Issue #35.
- **STOP** if the implementation requires touching any file outside
  the candidate paths listed in §3 of the source design contract
  (without an amendment to that contract first).
- **STOP** if the implementation requires a case to be classified as
  `implemented` while its `expected_output.placeholder` is `True` (or
  while any field in `placeholder_fields` is set).
- **STOP** if the implementation requires a case with
  `requires_slice` non-null to be classified as anything other than
  `requires_upstream_slice`.

A STOP is a **hard boundary**. The implementation round does not
auto-expand; it surfaces the blocker and waits for Charles's
amendment authorization.

---

## 9. Compliance audit (this Slice 3A round)

- 0 validation-adapter implementation ✅
- 0 `ValidationReport` production model ✅
- 0 production-path call ✅
- 0 SQLAlchemy session ✅
- 0 real expected output invention ✅
- 0 pressure-drop implementation / mutation ✅
- 0 production formula / coefficient / threshold / weight / scoring rule mutation ✅
- 0 `production_seeding.py` restoration ✅
- 0 migration mutation ✅
- 0 frontend mutation ✅
- 0 API expansion ✅
- 0 Task 11B mutation ✅
- 0 PR #21 mutation ✅
- 0 Issue #35 mutation ✅
- 0 comment / Ready / merge / close-issue mutation ✅
- 0 push (awaiting Charles authorization for follow-up round) ✅
- 4 new files under the §3 allowed-files boundary:
  - `docs/tasks/TASK-019-slice-3a-placeholder-fixture-contract.md`
  - `backend/tests/validation/__init__.py`
  - `backend/tests/validation/_task_019_slice_3_placeholder_fixtures.py`
  - `backend/tests/validation/test_task_019_slice_3_placeholder_fixtures.py`

---

## 10. Change log

| version | date | author | change |
|---|---|---|---|
| 1.0 | 2026-07-09 | Hermes | Initial TASK-019 Slice 3A placeholder fixture contract. 3 placeholder cases (smoke / requires_upstream_slice / malformed-blocked). No implementation authorized. No expected output authorized. Base SHA: `e237a9a14288a554b0043be4117bd818794d4b63` (= `origin/main` HEAD post-PR-#52). Source contract: PR #52 (frozen). |

---

## 11. Next authorization required

This document does **not** authorize implementation. The next round
requires Charles's explicit authorization for one of the following:

- **A) Slice 3B adapter-only implementation round.** Charles authorizes
  the implementation of the thin validation adapter and the
  `ValidationReport` production model per the source design contract
  §7 / §8, in the candidate paths per the source design contract §9,
  with the placeholder fixtures from this Slice 3A contract as the
  input. The implementation must obey the source design contract §4
  (no production formula / coefficient / pressure-drop / cost-model
  mutation) and §6 (no expected-output invention). The implementation
  must classify the three Slice 3A placeholder cases as
  `placeholder` / `requires_upstream_slice` / `blocked` per §5 of this
  document.
- **B) Fixture contract amendment round.** Charles authorizes
  amendments to this fixture contract (e.g., to add a 4th placeholder
  case, to refine the shape of an existing case, to answer an open
  question, or to clarify the §6 placeholder semantics). The
  implementation round (option A) is **not** automatically authorized
  by an amendment to this contract.
- **C) Expected-output authoring round, if explicitly authorized
  later.** Charles authorizes a separate round that produces real
  expected outputs for one or more of the three placeholder cases, via
  a frozen production path (not via hand-writing). This option is
  **explicitly conditional** on a separate, future Charles
  authorization; it is not in the default scope of this contract.

In all three cases, the implementation / amendment round must be a
**separate, explicitly authorized round** with its own preflight, its
own commit, and its own compliance audit. This placeholder fixture
contract does not implicitly authorize any of them.
