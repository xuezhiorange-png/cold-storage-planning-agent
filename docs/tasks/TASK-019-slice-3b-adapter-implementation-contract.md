# TASK-019 Slice 3B — Adapter Implementation Contract

**Status:** DESIGN CONTRACT — IMPLEMENTATION NOT AUTHORIZED BY THIS DOCUMENT
**Branch base:** `main @ b51a0a6f842d4ecf7e74e7358ebc252094778a53` (post-PR-#54, post-PR-#53, post-PR-#52, post-PR-#51)
**Branch name:** `docs/task-019-slice-3b-contract`
**Target Phase:** TASK-019 Slice 3B (placeholder-aware thin validation adapter / harness)
**Authoritative upstream contracts:**
- `docs/tasks/TASK-019-slice-3-validation-adapter-contract.md` (PR #52 — **FROZEN**, Slice 3 design contract)
- `docs/tasks/TASK-019-slice-3a-placeholder-fixture-contract.md` (PR #53 — **FROZEN**, Slice 3A placeholder fixture contract)
- `backend/tests/validation/_task_019_slice_3_placeholder_fixtures.py` (Slice 3A fixture helper — **FROZEN**)
- `backend/tests/validation/test_task_019_slice_3_placeholder_fixtures.py` (Slice 3A fixture tests — **FROZEN**)

> **Mutable-facts discipline:** Stable identifiers (PR #, Issue #, base SHA, branch, contract path) are recorded in this file. Mutable facts (current PR head SHA, current CI run id, current branch tip, current PR/Issue state) are **intentionally not frozen in this mutable branch row**; they are re-verified externally during any future review / freeze / amendment / Ready / merge authorization round.

---

## 1. Status / governance

This document is a **design contract** for TASK-019 Slice 3B. It is **not** an implementation authorization.

- **CONTRACT ONLY.** No production code, no tests, no fixtures, no expected outputs, no migration, no frontend, no API expansion, no production row seeding, no `production_seeding.py` restoration is authorized by this document.
- **IMPLEMENTATION NOT AUTHORIZED BY THIS DOCUMENT.** Slice 3B implementation requires a **separate, explicit authorization from Charles** in a follow-up round after this contract is merged and frozen.
- **READY / MERGE NOT AUTHORIZED.** This document does not authorize the agent to mark the contract PR as Ready or to merge it. Both require Charles's explicit per-message authorization in the next message.
- **EXPECTED-OUTPUT AUTHORING NOT AUTHORIZED.** This document forbids the invention of "real" expected outputs in any future implementation round. Any future expected output must be produced by an upstream production path that already exists at freeze time, or by an explicitly authorized expected-output-authoring round.
- **FIXTURE EXPANSION NOT AUTHORIZED.** This document does not authorize adding new fixture cases or new fixture fields in any implementation round. The three Slice 3A fixture cases (`case_01_smoke_placeholder`, `case_02_requires_upstream_slice`, `case_03_malformed_or_blocked_placeholder`) are the only inputs to the future adapter. New fixtures require an amendment round.

**Replaces prior-blocked-round verdict**:
- The previous TASK-019 Slice 3B preflight round reported `TASK_019_SLICE_3B_BLOCKED_BY_MISSING_OR_AMBIGUOUS_CONTRACT` because no on-disk Slice 3B contract file existed.
- This document is that contract. It converts the forward references in Slice 3 §13 (option B "Slice 3 adapter-only implementation round") and Slice 3A §11 (option A "Slice 3B adapter-only implementation round") into explicit, on-disk, implementation boundaries.

---

## 2. Upstream frozen contracts

This contract inherits **all** boundaries from the two upstream frozen contracts and adds Slice-3B-specific allowed-file / forbidden-file boundaries. Specifically:

### 2.1 TASK-019 Slice 3 design contract (PR #52, merged) — FROZEN

- `docs/tasks/TASK-019-slice-3-validation-adapter-contract.md` (578 lines)
- **Status:** FROZEN (post-merge, `e237a9a14288a554b0043be4117bd818794d4b63`)
- **Inherited scope:** §3 (Slice 3 scope — adapter-only, validation-report boundary), §4 (forbidden scope — no production formula / coefficient / pressure-drop / cost-model mutation; no fixture expected-output invention; no migration; no Task 11B / PR #21 / Issue #35 mutation), §5 (status enum — implemented / not_implemented / placeholder / skipped / requires_upstream_slice / blocked), §6 (fixture contract shape), §7 (adapter contract — inputs / outputs / forbidden behaviors), §8 (validation report schema — required fields: task_id / slice_id / case_id / status / reason / implemented_fields / placeholder_fields / missing_fields / blocked_fields / source_references / warnings; optional: metadata), §11 (stop conditions), §12 (open questions — these remain open at Slice 3B freeze time; implementation must stop and surface any required amendment if a §12 question blocks it).
- **Inheritance note:** Slice 3 §13 (option B "Slice 3 adapter-only implementation round") is the upstream authorization surface; this Slice 3B contract **operationalizes** Slice 3 §13 by adding the explicit allowed-file boundary that §13 lists only as "candidate paths (suggestions, not authorizations)".

### 2.2 TASK-019 Slice 3A placeholder fixture contract (PR #53, merged) — FROZEN

- `docs/tasks/TASK-019-slice-3a-placeholder-fixture-contract.md` (354 lines)
- `backend/tests/validation/_task_019_slice_3_placeholder_fixtures.py` (Slice 3A fixture helper)
- `backend/tests/validation/test_task_019_slice_3_placeholder_fixtures.py` (Slice 3A fixture tests, 32 tests)
- **Status:** FROZEN (post-merge, `b5805d21d9492922f7b8c3d276c02ed938435ae9`)
- **Inherited scope:** the three Slice 3A placeholder cases are the **only** inputs to the future adapter; each case's `expected_status` field is the contract-enforced classification target; no real expected output exists.
- **Inheritance note:** Slice 3A §11 (option A "Slice 3B adapter-only implementation round") is the upstream authorization surface for Slice 3B; this Slice 3B contract implements that option.

### 2.3 PR #54 — Independent main-green fixup (NOT a TASK-019 artifact)

- `b51a0a6 Fix pre-existing FastAPI waiter SQLite race (#54)`
- PR #54 is the fix for a pre-existing race condition in `tests/test_reports/test_waiter_concurrent.py::TestDefaultWaiterFastAPIConvergence::test_default_waiter_two_fastapi_requests_converge` (race was already latent; PR #54 makes main green).
- PR #54 is **NOT** part of TASK-019 semantics. It is referenced here only to document that main is GREEN at Slice 3B freeze time.
- Future Slice 3B implementation MUST NOT touch PR #54's files (already merged; the merged files are out of scope for implementation; see §7 forbidden files).

---

## 3. Problem statement

The TASK-019 Slice 3B implementation preflight round (the round immediately preceding this contract authoring) reported `TASK_019_SLICE_3B_BLOCKED_BY_MISSING_OR_AMBIGUOUS_CONTRACT` because the repository contained only forward references to "Slice 3B" without an on-disk Slice 3B contract defining allowed files, behavior, and stop conditions.

**Without this contract**, any "continue TASK-019 Slice 3B" round would amount to:
1. **Implementation from memory / verbal handoff**, which is explicitly forbidden by the project's governance discipline and the source Slice 3 / Slice 3A contracts.
2. **Scope ambiguity at the allowed-files level** — the source Slice 3 §9 lists candidate paths as "**suggestions, not authorizations**", so without an explicit Slice 3B contract, no implementation can be sure whether a new path under `backend/src/cold_storage/validation/` is allowed.
3. **Expected-output drift** — without a hard rule that the three Slice 3A placeholder cases are the *only* inputs, an implementation might invent a new fixture or a real expected value, violating Slice 3 §4.
4. **Stop-condition ambiguity** — without an explicit Slice 3B stop-condition list, an implementation could silently expand into production-code mutation, pressure-drop invention, or production-row fabrication.

This document establishes the on-disk Slice 3B contract so that a future implementation round (after Charles's per-message authorization) has:
- A stable file layout under `backend/src/cold_storage/modules/` for the adapter / harness code.
- A hard rule that the three Slice 3A fixture cases are the only inputs and no real expected output is invented.
- A clear boundary between "the adapter" (a thin transformation / classification layer) and "the production path" (the upstream source of truth, read-only).
- A list of stop conditions specific to Slice 3B that extend the Slice 3 §11 stop conditions.

---

## 4. Slice 3B objective

Slice 3B implementation, **if and when authorized by Charles in a follow-up round**, is limited to:

1. **A thin validation adapter module** that:
   - Takes a Slice 3A fixture case (input) and a reference to one of the three permitted inputs (`case_01_smoke_placeholder`, `case_02_requires_upstream_slice`, `case_03_malformed_or_blocked_placeholder`).
   - Classifies the case to exactly one of the Slice 3A `expected_status` values (`placeholder`, `requires_upstream_slice`, `blocked`) using only the placeholder semantics from the Slice 3A fixture helper and the Slice 3A contract.
   - **Does not compute** business results.
   - **Does not infer** missing fields.
   - **Does not swallow** exceptions.
   - **Does not mutate** the production database.
   - **Does not call** any pressure-drop implementation (which does not exist in this repo as of the design base SHA).

2. **A `ValidationReport` typed object** (Python dataclass or Pydantic model — to be decided at implementation-freeze time) that:
   - Exposes the Slice 3 §8 required fields (`task_id`, `slice_id`, `case_id`, `status`, `reason`, `implemented_fields`, `placeholder_fields`, `missing_fields`, `blocked_fields`, `source_references`, `warnings`).
   - Supports JSON round-trip serialization.
   - Does **not** invent expected values; the `expected_output` field in the report (if present) is the fixture's `expected_output` verbatim, **including** the `placeholder` marker.

3. **Fixture provenance preservation** so that every report carries the fixture's `case_id`, the fixture contract path, and the source contract path in `source_references`.

4. **A test module** (per §15) that verifies the three Slice 3A fixture cases are classified correctly, the `ValidationReport` schema is stable, and the adapter does not violate the §7 forbidden behaviors.

5. **Optional, only-if-necessary** new module path: if an implementation round determines that placing the adapter under an existing module is structurally incompatible with the `Dependency direction is API -> Application -> Domain` rule (from `AGENTS.md` Architecture Rules), the implementation may create `backend/src/cold_storage/modules/validation/__init__.py` and place adapter code under it. This path creation is the **only** new module path authorized by this contract; it is **not** a default — prefer placing the adapter under `backend/src/cold_storage/modules/reports/application/validation_adapter.py` first (see §6).

Slice 3B implementation, **if and when authorized**, is **not** allowed to expand into the items in §5 / §7 / §20.

---

## 5. Non-goals

The following are **explicitly forbidden** in any future implementation under this contract. This list inherits the Slice 3 §4 forbidden patterns and the Slice 3A forbidden patterns, and adds TASK-019-Slice-3B-specific items.

### 5.1 Inherited from Slice 3 §4 (verbatim application)

- **No pressure-drop implementation.** Pressure-drop is a production calculation that does not exist in this repository as of the design base SHA (`b51a0a6f`). No code path, no stub, no TODO marker for pressure-drop may be added by a Slice 3B implementation round.
- **No pressure-drop calculation logic mutation.** Even if a pressure-drop implementation is added by a separate (post-Slice-3B) authorization, the Slice 3B adapter must not import, call, or depend on it.
- **No production formula mutation.** Existing production formulas (storage capacity, precooling capacity, room area, cooling load, investment, equipment capability, etc., per `AGENTS.md` "Engineering Calculation Rules") are **immutable** from the perspective of a Slice 3B implementation round.
- **No coefficient mutation.** Coefficient resolution is owned by the production-side coefficient resolver. The adapter does not introduce, modify, or short-circuit coefficient resolution.
- **No discount / salvage / cost-model invention.** These are production-side economic models. The adapter does not invent, approximate, or assume any values for them.
- **No fixture expected-output invention.** (See §12 for the Slice 3B-specific elaboration.)
- **No migration.** No Alembic migration under this contract. The adapter does not introduce new schema; it operates on already-persisted production rows (read-only) and on in-memory fixture objects.
- **No frontend mutation.** Slice 3B is backend-only.
- **No API expansion unless later slice explicitly authorizes.** The adapter is an internal contract; it does not introduce new REST endpoints, new GraphQL queries, or new CLI commands.
- **No production row seeding.** No `production_seeding.py`-style file may be created or restored. The adapter does not write to the production database; it only reads from it (and only when needed for the validation-report assembly, on a read-only basis).
- **No Task 11B mutation.**
- **No PR #21 mutation.**
- **No Issue #35 mutation.**

### 5.2 Slice 3B-specific additions

- **No expansion of the three Slice 3A fixture cases.** The three cases (`case_01_smoke_placeholder`, `case_02_requires_upstream_slice`, `case_03_malformed_or_blocked_placeholder`) are the ONLY inputs to the adapter. Adding a 4th case requires an explicit amendment round.
- **No mutation of the Slice 3A fixture helper file** (`backend/tests/validation/_task_019_slice_3_placeholder_fixtures.py`). The helper is **frozen**; the adapter imports from it, never modifies it.
- **No mutation of the Slice 3A fixture tests file** (`backend/tests/validation/test_task_019_slice_3_placeholder_fixtures.py`). The 32 fixture-contract tests are **frozen** and must remain passing after the Slice 3B implementation.
- **No closure of any slice contract as a side effect of this contract.** This contract is docs-only; it does not close, amend, or supersede Slice 3 or Slice 3A. Slice 3 / Slice 3A remain FROZEN.
- **No deletion of the `codex/task-019-slice-3b-implementation` branch** (the prior round's local-only branch). That branch may be cleaned up in a future, separately authorized round.
- **No reference to PR #54's fix-up files** in the Slice 3B implementation diff. PR #54 is an independent main-green fixup; its files are out of scope for Slice 3B.

---

## 6. Allowed files

A future Slice 3B implementation round, **if and when authorized by Charles**, may create or modify **only** the following files. Any file outside this list is forbidden unless a future, separately authorized amendment round expands this §6.

### 6.1 Allowed for modification (existing files)

The implementation round may **modify** the following existing files:

| path | role | scope of allowed modification |
|---|---|---|
| `docs/tasks/TASK-019-slice-3b-adapter-implementation-contract.md` | this file (the contract) | An implementation round may **never** modify this file. If a §6 / §7 boundary needs adjustment, it must go through a separate design-amendment round. (This row is a hard guard against self-modification.) |
| `backend/tests/validation/__init__.py` | existing empty file | May be left empty; may add an `__all__` export only if needed to expose a new module-level helper. No business logic. |

### 6.2 Allowed for creation (new files)

The implementation round may **create** the following new files. Each path is **conditional** on the implementation round's actual need; default is to NOT create any new module path until forced by the adapter's structural requirements.

| path | role | condition for creation |
|---|---|---|
| `backend/src/cold_storage/modules/reports/application/validation_adapter.py` | the thin validation adapter (preferred location; parallels the existing `backend/src/cold_storage/modules/reports/application/render_service.py` precedent) | **Default path.** Try this first. |
| `backend/src/cold_storage/modules/reports/application/validation_report.py` | the `ValidationReport` typed dataclass / Pydantic model + JSON serialization (per Slice 3 §8) | **Default path.** Try this first. |
| `backend/src/cold_storage/modules/validation/__init__.py` | new module, parallel to `evaluation/` (per Slice 3 §9 candidate path 1) | Only if `reports/application/validation_adapter.py` is structurally incompatible with the dependency direction rule (`API -> Application -> Domain`) from `AGENTS.md`. **Discouraged default; require explicit justification in the PR body.** |
| `backend/src/cold_storage/modules/validation/adapter.py` | alternate thin adapter location (per Slice 3 §9 candidate path 2) | Same condition as above; mutual-exclusion with the `reports/application/validation_adapter.py` path. |
| `backend/src/cold_storage/modules/validation/report.py` | alternate `ValidationReport` location (per Slice 3 §9 candidate path 3) | Same condition as above. |
| `backend/tests/validation/test_task_019_slice_3b_validation_adapter.py` | new test file (per §15) | **Required** for any implementation round. |
| `backend/tests/validation/test_task_019_slice_3b_validation_report.py` | new test file for `ValidationReport` JSON schema round-trip (per §15) | **Required** for any implementation round. |
| `docs/tasks/TASK-019-slice-3b-implementation-closeout.md` | closeout evidence doc (per §18-§19) | **Required** at the end of any implementation round, before the implementation PR is marked Ready. |

### 6.3 Discipline

- The implementation MUST prefer `backend/src/cold_storage/modules/reports/application/validation_adapter.py` first. The `backend/src/cold_storage/modules/validation/` path is a fallback, not a default.
- If an implementation round creates a file under `backend/src/cold_storage/modules/validation/`, the PR body MUST document why `reports/application/validation_adapter.py` was structurally incompatible.
- The `__init__.py` files for any new module MUST be empty except for an `__all__` export; no business logic in `__init__.py`.
- No file under `backend/src/cold_storage/modules/validation/` may import from any production formula / coefficient / discount / salvage / pressure-drop module.
- The `ValidationReport` dataclass (or Pydantic model) MUST live in `reports/application/validation_report.py` (or `backend/src/cold_storage/modules/validation/report.py` if the fallback path is used). It MUST NOT live in any other location.

---

## 7. Forbidden files (in addition to §6 allowed files)

The following files / paths are **forbidden** in any future implementation under this contract. Any required file outside §6 / §7 must go through a separate design-amendment round.

### 7.1 Forbidden production code paths

- `production_seeding.py` (anywhere in the repo; restoration is explicitly forbidden by Slice 3 §4)
- `backend/src/cold_storage/modules/**/coefficients/**` (coefficient resolution is owned by the production-side resolver)
- `backend/src/cold_storage/modules/**/formulas/**` (production formulas)
- `backend/src/cold_storage/modules/**/pressure*` and `backend/src/cold_storage/modules/**/*pressure*` (pressure-drop is forbidden by Slice 3 §4)
- `backend/src/cold_storage/modules/**/discount*` and `backend/src/cold_storage/modules/**/*discount*` (discount / salvage / cost-model invention is forbidden by Slice 3 §4)
- `backend/src/cold_storage/modules/**/salvage*` and `backend/src/cold_storage/modules/**/*salvage*` (same)
- `backend/src/**/migrations/**` and `backend/migrations/**` and `migrations/**` (no Alembic migration under this contract)

### 7.2 Forbidden non-production paths

- `frontend/**` (Slice 3B is backend-only)
- `.github/**` (workflow changes require a separate authorization)
- `docker/**` and `docker-compose*.yml` and `Dockerfile*` (infrastructure changes require a separate authorization)
- `pyproject.toml` and `uv.lock` (dependency changes require a separate authorization)
- `package.json` and `package-lock.json` (frontend / Node changes; none expected)
- `scripts/**` (build / utility scripts)

### 7.3 Forbidden TASK-011B / PR #21 / Issue #35 paths

- `docs/tasks/TASK-011B-*.md` (any TASK-011B design / closeout / ratification document)
- `docs/tasks/TASK-011.md` and `docs/tasks/task-011*.md` (Task 11)
- `docs/tasks/TASK-011-INFRA*.md` (Task 11 INFRA)
- `backend/src/cold_storage/modules/**` files that belong to TASK-011B (calculators, coefficient resolver, weight revisions, scheme source archive, production scheme service, production seeding)
- `backend/src/cold_storage/modules/production_calculation/**` (Slice 2 closeout territory)
- `backend/src/cold_storage/modules/orchestration/**` (Slice 2 / Slice 2D closeout territory)
- PR #21's files (the draft PR body, the validation tests that PR #21 added before being closed as Draft) — **out of scope for Slice 3B**
- Issue #35's files (Issue #35 is `closed / state_reason=completed` per Slice 3 §4; no reopening)
- `backend/src/cold_storage/modules/schemes/domain/validation.py` (unrelated domain validation module; **NOT** the TASK-019 validation module; **FORBIDDEN** to import or modify under this contract)

### 7.4 Forbidden Slice 3 / Slice 3A / Slice 3B contract files

- `docs/tasks/TASK-019-slice-3-validation-adapter-contract.md` (Slice 3 design contract — FROZEN; no amendment in this round or in any implementation round)
- `docs/tasks/TASK-019-slice-3a-placeholder-fixture-contract.md` (Slice 3A fixture contract — FROZEN; no amendment in this round or in any implementation round)
- `backend/tests/validation/_task_019_slice_3_placeholder_fixtures.py` (Slice 3A fixture helper — FROZEN)
- `backend/tests/validation/test_task_019_slice_3_placeholder_fixtures.py` (Slice 3A fixture tests — FROZEN)
- `docs/tasks/TASK-019-slice-3b-adapter-implementation-contract.md` (this file — FROZEN at merge time of this contract PR)

### 7.5 Forbidden PR-#54-vintage files (independent main-green fixup)

- `tests/test_reports/test_waiter_concurrent.py` (modified by PR #54; out of Slice 3B scope)

---

## 8. Adapter-only behavior contract

The thin validation adapter has the following contract (inherits Slice 3 §7 verbatim and adds Slice 3B-specific clarifications):

### 8.1 Inputs

- `case`: a Slice 3A fixture case dict (one of `case_01_smoke_placeholder`, `case_02_requires_upstream_slice`, `case_03_malformed_or_blocked_placeholder`).
- `production_output`: a reference to the result of calling the production path on the case's inputs, **if** the production path exists and was successfully invoked. May be `None` if the production path does not exist or was not invoked. For all three Slice 3A cases, **the production path does not exist** (or the inputs are placeholder / malformed / blocked), so `production_output` will typically be `None`.
- `metadata`: an optional dict carrying additional context (e.g., the current `origin/main` SHA, the upstream-slice identifier). The adapter does **not** interpret `metadata`; it only attaches it to the report.

### 8.2 Output

- A `ValidationReport` object whose shape is defined in §8 of the Slice 3 design contract (the upstream contract) and elaborated in §9 of this contract. The adapter returns exactly one report per case. It does not return `None`; failure to construct a report is itself a `blocked` case.

### 8.3 Forbidden behaviors (the adapter must not do these)

These inherit Slice 3 §7 forbidden behaviors verbatim and add:

- **Must not compute** business results. The adapter does not re-implement or approximate any production formula. Even for `case_01_smoke_placeholder` (which has placeholder inputs), the adapter must not "compute what the production would output"; it must report `placeholder` status and stop.
- **Must not infer** missing fields. If a field is absent, the adapter records the absence in `missing_fields` and routes the case to `placeholder` (for `case_01`), `requires_upstream_slice` (for `case_02`), or `blocked` (for `case_03`), per the Slice 3A fixture's `expected_status`.
- **Must not swallow** exceptions. Any exception raised by the production path (or by the adapter itself) is captured into the report's `warnings` (or `status: blocked` if the exception is unrecoverable) and surfaced to the caller.
- **Must not mutate the database.** The adapter is read-only with respect to production data.
- **Must not modify production data.** No `INSERT`, `UPDATE`, `DELETE`, no `session.flush()`, no `session.commit()`, no `bulk_insert_mappings`, no raw SQL.
- **Must not invent expected values.** The adapter's `expected_output` field in the report is the fixture's `expected_output` verbatim, **including** the `placeholder: True` flag. The adapter does not fill in placeholders with the production result.
- **Must not rewrite unknown / placeholder / blocked as `implemented`.** If the production path raises an exception, returns an unexpected shape, or is missing, the adapter reports `placeholder`, `requires_upstream_slice`, or `blocked` — never `implemented`.
- **Must not import any production-formula / coefficient / pressure-drop / discount / salvage / cost-model module.** The §7.1 forbidden paths are also forbidden as import targets.

### 8.4 Adapter may do

- Parse the Slice 3A fixture's `case_id`, `inputs`, `expected_output`, `requires_slice`, `expected_status`, `placeholder_fields`, `reason`, `source_references`.
- Construct a `ValidationReport` with the Slice 3 §8 required fields populated from the fixture and the adapter's classification.
- Surface the fixture's `placeholder_fields` verbatim into the report's `placeholder_fields`.
- Surface the fixture's `source_references` verbatim into the report's `source_references`.

---

## 9. Placeholder semantics contract

Placeholder values are **first-class contract states**. The adapter must treat them as such:

- **Placeholder detection**: an input or expected-output field with `placeholder: True` is a placeholder. The adapter must NOT coerce placeholder strings into real numeric / material / design inputs.
- **Placeholder routing**: a case with any placeholder input or placeholder expected-output is reported as `placeholder` (per Slice 3A `case_01`) or `requires_upstream_slice` (per Slice 3A `case_02`). It is NEVER reported as `implemented`.
- **Placeholder preservation**: the report's `placeholder_fields` lists every input / output field that is a placeholder. The report does NOT contain any computed value where the fixture had a placeholder.
- **Provenance preservation**: every report carries the fixture's `case_id`, the fixture contract path, and the source contract path in `source_references`.
- **Fail-closed for ambiguous mixed placeholders**: if a case mixes real-looking fields (e.g., numeric values) and placeholder fields ambiguously (e.g., a "placeholder" flag is absent but the value is a TBD marker string), the adapter must report `blocked` (per Slice 3A `case_03`'s shape) and surface a warning that explains the ambiguity. The adapter must NOT guess which fields are placeholder.
- **`placeholder` ≠ success**: a placeholder case is reported with `status: placeholder` (or `requires_upstream_slice` if the placeholder is specifically an "I need an upstream slice" marker). It is NEVER reported with `status: implemented`.
- **`requires_upstream_slice` ≠ failure**: a `requires_upstream_slice` case is reported as `requires_upstream_slice`. It is not a test failure; it is a forward-pointer to a not-yet-completed slice.
- **`blocked` ≠ failure**: a `blocked` case is reported with `status: blocked`. `blocked` is reserved for cases where the contract or the inputs are not executable (e.g., fixture is malformed). It is not a test failure; it is a structural stop.

---

## 10. Fixture / case contract

The future adapter MUST consume only the three Slice 3A placeholder cases:

| case_id | inputs | expected_output | requires_slice | expected_status (from Slice 3A) |
|---|---|---|---|---|
| `case_01_smoke_placeholder` | `placeholder: True` (TBD-by-Slice-3A; smoke-test the placeholder shape) | `placeholder: True` (no real expected output authorized) | `None` | `placeholder` |
| `case_02_requires_upstream_slice` | `placeholder: True` (TBD-by-Slice-3A; requires an upstream TASK-019 slice like Slice 1 or Slice 2) | `placeholder: True` (cannot be produced until the upstream slice completes) | `"slice-1"` | `requires_upstream_slice` |
| `case_03_malformed_or_blocked_placeholder` | structurally invalid (missing required fields; `placeholder: False` but fields are absent) | `placeholder: True` | `None` | `blocked` |

**Constraints**:
- The adapter must NOT add new fixture cases.
- The adapter must NOT modify the Slice 3A fixture helper file.
- The adapter must NOT modify the Slice 3A fixture tests file.
- The adapter must preserve each case's identity (the `case_id`) and provenance (the `source_references` list).
- The adapter must report each case with the Slice 3A `expected_status` (verbatim) — i.e., `placeholder` for `case_01`, `requires_upstream_slice` for `case_02`, `blocked` for `case_03`.

---

## 11. Production API boundary

The future implementation must follow these production-API rules:

- The adapter MAY call existing public application/service APIs (e.g., `backend/src/cold_storage/modules/reports/application/render_service.py::ReportRenderService.render` or its public helpers). The adapter MUST treat public application/service APIs as the source of truth for the production path.
- Raw ORM access (e.g., `Base.metadata.create_all`, raw SQL via `session.execute(text("..."))`, direct `session.add(...)`, `session.flush()`, `session.commit()`) is **FORBIDDEN** in the adapter. The adapter is a **read-only consumer** of production data.
- The adapter MAY use the same `session_factory` pattern as the production read paths, but only for `SELECT`-style operations. No write operations.
- Production API changes (modifying the signature of `ReportRenderService.render`, adding new methods to the service, changing the public Python API) are a **STOP condition** unless separately authorized.
- If the production API is unreachable (e.g., the session factory raises an exception), the adapter must report the case as `blocked` and surface the exception in `warnings`. The adapter must NOT retry the call on its own.

---

## 12. Expected-output boundary

Expected-output authoring is **explicitly outside Slice 3B**. The adapter MUST NOT invent any expected output value.

- For `case_01_smoke_placeholder`: the report's `expected_output` field is the fixture's `expected_output` verbatim (`{"placeholder": True, "reason": "No real expected output authorized for this case."}`). The adapter does not fill this in with a production result.
- For `case_02_requires_upstream_slice`: the report's `expected_output` field is the fixture's `expected_output` verbatim. The adapter does not "guess" what the expected output would be once Slice 1 / Slice 2 completes.
- For `case_03_malformed_or_blocked_placeholder`: the report's `expected_output` field is the fixture's `expected_output` verbatim. The adapter does not "fix" the malformed inputs to make them look complete.

**If a future Slice 3B implementation needs a real expected output to pass a test, it must STOP and surface the blocker.** A real expected output requires:
1. An upstream production path that already exists at freeze time and is known to be stable; AND
2. An explicitly authorized expected-output-authoring round that snapshots the production result for the specific case.

Neither condition is met for any of the three Slice 3A cases. **All three cases are placeholder; all three cases are tested for placeholder behavior, not for value-comparison.**

---

## 13. Prohibited inference rules

The adapter MUST NOT perform any of the following inference behaviors:

- **No invented pressure-drop value** (forbidden by Slice 3 §4)
- **No invented discount rate** (forbidden by Slice 3 §4)
- **No invented salvage value** (forbidden by Slice 3 §4)
- **No invented efficiency** (any efficiency assumption — e.g., "assume 95% efficiency for the report rendering pipeline" — is invented)
- **No invented cost model assumption** (e.g., "assume $X/m² for construction" is invented)
- **No inferred coefficient** (the adapter does not resolve coefficients via any production-side path; if a value is needed, the case is reported as `placeholder`)
- **No inferred material property** (e.g., "assume density = 50 kg/m³" is forbidden; material properties belong to the production calculation pipeline)
- **No latest-row fallback** (the adapter does not read "the latest row in the production DB" to fabricate a result)
- **No demo fallback** (the adapter does not read demo / placeholder data from any source to fabricate a result)
- **No partial / reasonable-default completion** (e.g., "if a field is missing, use 0" or "if a field is missing, use None" is forbidden; the field is reported in `missing_fields` and the case is routed to `placeholder` / `blocked`)

---

## 14. Error / reporting semantics

The adapter surfaces structured statuses in the `ValidationReport`. The status closed set is inherited from Slice 3 §5:

| status (closed set) | when | example case |
|---|---|---|
| `implemented` | the case has all required inputs and all required expected outputs, and the production path produced a result that the adapter successfully normalized | (none of the Slice 3A cases; `implemented` is reserved for cases where real expected outputs exist and the production path ran end-to-end) |
| `not_implemented` | the production path required by the case does not exist yet | (none of the Slice 3A cases; reserved for future non-placeholder cases) |
| `placeholder` | the fixture itself is a placeholder; no real expected output | `case_01_smoke_placeholder` |
| `skipped` | the case is intentionally skipped for the current slice | (none of the Slice 3A cases) |
| `requires_upstream_slice` | the case requires a feature in a different slice that has not been completed | `case_02_requires_upstream_slice` |
| `blocked` | the contract or the inputs are not executable (e.g., fixture is malformed) | `case_03_malformed_or_blocked_placeholder` |

**In addition to the Slice 3 §5 statuses**, the adapter MAY surface **advisory warning strings** in the `warnings` field of the report (a `list[str]`). The advisory warnings are not statuses and do not change the case's classification. They are informational, not actionable by the adapter. Examples (non-exhaustive):

- `"production_api_unavailable"` — surfacing a transient production API failure that did not change the case classification but may be relevant for debugging
- `"contract_ambiguous"` — surfacing an ambiguity in the fixture shape that the adapter treated as `blocked` but that may indicate a fixture contract improvement opportunity
- `"unsupported_case_shape"` — surfacing a case shape that the adapter does not recognize (used only if a future Slice expands the case shape beyond the three Slice 3A cases)
- `"adapter_internal_warning"` — surfacing a non-recoverable internal adapter state (distinct from `blocked` in that the case classification may still be `placeholder`, but the adapter had to make a fallback decision)

**The `warnings` field is informational; the `status` field is the source of truth.** A future consumer of the report MUST NOT treat a warning as a status.

---

## 15. Required tests

A future implementation round, **if and when authorized**, MUST include the following tests. Each test is described by its **behavior**, not by its implementation; the test author chooses the actual test framework and assertion style.

### 15.1 New test file: `backend/tests/validation/test_task_019_slice_3b_validation_adapter.py`

This file MUST contain at least the following tests:

| test name | behavior |
|---|---|
| `test_case_01_placeholder_blocked_status` | run adapter on `case_01_smoke_placeholder`; assert `status == "placeholder"` (per Slice 3A `expected_status`); assert `placeholder_fields` includes `"inputs"` and `"expected_output"` |
| `test_case_02_requires_upstream_slice_status` | run adapter on `case_02_requires_upstream_slice`; assert `status == "requires_upstream_slice"`; assert `placeholder_fields` includes `"inputs"` and `"expected_output"`; assert `requires_slice == "slice-1"` surfaces in `metadata` or `source_references` |
| `test_case_03_blocked_status` | run adapter on `case_03_malformed_or_blocked_placeholder`; assert `status == "blocked"`; assert `placeholder_fields` includes `"expected_output"`; assert `missing_fields` is non-empty (the structurally invalid inputs surface as missing fields) |
| `test_fixture_provenance_preserved` | run adapter on each of the three cases; assert `source_references` includes both `docs/tasks/TASK-019-slice-3-validation-adapter-contract.md` AND `docs/tasks/TASK-019-slice-3a-placeholder-fixture-contract.md` |
| `test_no_expected_output_comparison` | run adapter on each of the three cases; assert the report's `expected_output` field is the fixture's `expected_output` verbatim (including `placeholder: True`), and that the adapter does NOT contain any value-comparison logic that compares the report's `expected_output` against the production result |
| `test_fail_closed_on_ambiguous_mixed_placeholder` | construct a synthetic case that mixes real-looking and placeholder fields ambiguously; assert the adapter reports `blocked` (not `placeholder` and not `implemented`) |
| `test_no_production_row_writes` | run adapter against a real or in-memory session and assert that no `INSERT` / `UPDATE` / `DELETE` was issued and that `session.flush()` / `session.commit()` were not called by the adapter (this can be implemented as a transaction isolation check: open an outer transaction, run the adapter, assert no inner commit) |
| `test_no_demo_or_latest_row_fallback` | construct a synthetic case that requires fallback to demo / latest-row data; assert the adapter does NOT silently fill in defaults from any fallback source and reports `blocked` instead |

### 15.2 New test file: `backend/tests/validation/test_task_019_slice_3b_validation_report.py`

This file MUST contain at least the following tests:

| test name | behavior |
|---|---|
| `test_validation_report_required_fields` | construct a `ValidationReport` and verify that all Slice 3 §8 required fields (`task_id`, `slice_id`, `case_id`, `status`, `reason`, `implemented_fields`, `placeholder_fields`, `missing_fields`, `blocked_fields`, `source_references`, `warnings`) are present and typed correctly |
| `test_validation_report_json_round_trip` | serialize a `ValidationReport` to JSON; deserialize back; assert all field values are preserved verbatim (including the `placeholder: True` flag in `expected_output`, if present) |
| `test_validation_report_status_closed_set` | assert that the `status` field, when set, is one of the Slice 3 §5 values (`implemented`, `not_implemented`, `placeholder`, `skipped`, `requires_upstream_slice`, `blocked`) |

### 15.3 Forbidden-import / no-pressure-drop guard

The implementation round MUST include a static check that the adapter module does not import any of the §7.1 forbidden paths (pressure-drop / discount / salvage / cost-model / coefficient). This can be a `pytest`-level static check (e.g., read the adapter module's `__import__` / `import` statements and assert no forbidden symbols) or a `ruff`/`mypy` rule. The static check is forward-looking: as of the design base SHA, no pressure-drop module exists, so the guard is currently trivial (no symbol to find); it is included to prevent future accidental introduction.

### 15.4 Inherited Slice 3A tests (NOT modified, NOT removed)

The 32 Slice 3A fixture-contract tests in `backend/tests/validation/test_task_019_slice_3_placeholder_fixtures.py` MUST remain passing after any future implementation round. The implementation round MUST NOT modify, delete, or skip any of these tests.

---

## 16. Verification commands

A future implementation round, **if and when authorized**, MUST run (at minimum) the following commands. All commands must exit with code 0 before the implementation PR is marked Ready.

```bash
# 1. Slice 3A fixture tests (must remain 32/32 passing; inherited)
cd backend
PYTHONPATH=src DATABASE_BACKEND=sqlite \
  uv run pytest tests/validation/test_task_019_slice_3_placeholder_fixtures.py -q -vv

# 2. Slice 3B adapter tests (the new tests per §15)
PYTHONPATH=src DATABASE_BACKEND=sqlite \
  uv run pytest tests/validation/test_task_019_slice_3b_validation_adapter.py -q -vv

# 3. Slice 3B report tests (the new tests per §15)
PYTHONPATH=src DATABASE_BACKEND=sqlite \
  uv run pytest tests/validation/test_task_019_slice_3b_validation_report.py -q -vv

# 4. All validation tests together (the combined scope)
PYTHONPATH=src DATABASE_BACKEND=sqlite \
  uv run pytest tests/validation -q -vv

# 5. The pre-existing waiter race test (must remain passing — PR #54 fix must not regress)
PYTHONPATH=src DATABASE_BACKEND=sqlite \
  uv run pytest tests/test_reports/test_waiter_concurrent.py::TestDefaultWaiterFastAPIConvergence::test_default_waiter_two_fastapi_requests_converge -q -vv

# 6. Lint and format (must remain clean)
uv run ruff check .
uv run ruff format --check .

# 7. Type check (must remain clean)
uv run mypy src
```

### 16.1 Optional / contract-dependent verifications

If the implementation round determines that a PostgreSQL-specific test is in scope (e.g., the adapter is parametrized over both SQLite and PostgreSQL), the following MAY be run:

```bash
DATABASE_BACKEND=postgresql PYTHONPATH=src \
  uv run pytest tests/validation -q -vv
```

The implementation PR body MUST document which of these optional verifications were run.

### 16.2 Forbidden verification commands

The implementation round MUST NOT run the full backend test suite (`uv run pytest -q`) as a verification command unless the implementation round has determined that the full suite is the **only** way to confirm the Slice 3B behavior. The full suite takes ~20 minutes; running it without justification is wasteful.

---

## 17. Stop conditions

A future Slice 3B implementation round, **if and when authorized**, MUST **STOP** and surface the blocker to Charles in any of the following cases. The stop is a **hard boundary**; the implementation round does not auto-expand.

- **STOP** if the implementation requires mutation of any production formula (storage capacity, precooling capacity, room area, cooling load, investment, equipment capability, or any production calculator's coefficient / threshold / weight / scoring rule).
- **STOP** if the implementation requires inventing a real expected output for a fixture that has only a placeholder (i.e., a fixture like the Slice 3A cases).
- **STOP** if the implementation requires adding a new fixture case (the three Slice 3A cases are the only inputs).
- **STOP** if the fixture contract defined in Slice 3A §6 conflicts with existing production behavior (e.g., if a production path requires a field that Slice 3A §6 declares optional, or vice versa).
- **STOP** if a pressure-drop implementation is needed to make any case runnable.
- **STOP** if the §6 allowed-files boundary is insufficient to express the implementation (e.g., a new file under `backend/src/cold_storage/modules/<other-module>/` is required). The boundary must be amended via a separate design-amendment round, NOT silently expanded.
- **STOP** if any production-row seeding is required (no `production_seeding.py` restoration; no `session.add(...)` of production rows; no raw SQL `INSERT`).
- **STOP** if PR #21 or Issue #35 or Task 11B needs to be touched.
- **STOP** if any forbidden file under §7 needs to be created or restored.
- **STOP** if the implementation requires any non-§6 file to be created (e.g., a `conftest.py` change in `backend/tests/validation/`, a new module under `backend/src/cold_storage/modules/orchestration/`).
- **STOP** if the implementation requires a new dependency in `pyproject.toml` or `uv.lock`.
- **STOP** if any of the 32 Slice 3A fixture-contract tests start failing after the implementation.

A STOP is a **hard boundary**. The implementation round does not auto-expand; it surfaces the blocker and waits for Charles's amendment authorization.

---

## 18. PR / CI / merge boundaries

### 18.1 Contract PR (this document's PR)

- This contract PR MUST be **Draft** initially.
- Marking the contract PR as **Ready** requires Charles's explicit per-message authorization.
- Merging the contract PR requires Charles's explicit per-message authorization.
- The PR body MUST list the upstream-frozen-contract references (Slice 3 / Slice 3A), confirm docs-only diff, confirm no implementation, confirm no production-code mutation, confirm PR #21 / Issue #35 / Task 11B untouched, and confirm ready/merge not authorized.

### 18.2 Implementation PR (future round, after contract merge)

- The implementation PR is a **separate future round**.
- The implementation PR requires a **separate, explicit authorization** from Charles in the message after this contract is merged.
- The implementation PR's PR body MUST list this Slice 3B contract as the upstream frozen contract and confirm §6 allowed-files compliance, §7 forbidden-files compliance, §15 test compliance, and §16 verification commands passing.

### 18.3 CI behavior

- The contract PR MUST be docs-only. The CI pipeline MUST show the documentation checks passing and the backend tests passing (since no backend changes occurred, the backend tests should pass trivially).
- The implementation PR's CI MUST pass all 4 jobs (`frontend`, `backend-sqlite`, `backend-postgresql`, `compose-config`) before Ready can be authorized.
- The CI run id, PR head SHA, and merge SHA are mutable; they are intentionally not recorded in this contract.

### 18.4 Merge authorization flow

Per the project's multi-round governance discipline (inherited from TASK-011B / TASK-019 prior rounds):
1. Contract authoring round produces the contract on a branch + Draft PR.
2. Charles reviews the contract; **either** requests amendments (in which case the round ends with `TASK_019_SLICE_3B_CONTRACT_AUTHORING_BLOCKED_BY_AMENDMENT_REQUEST`) **or** authorizes the Draft → Ready transition.
3. Charles authorizes Ready via per-message authorization; the PR is marked Ready (this step may also be performed by Charles manually via the Web UI).
4. Charles authorizes merge via per-message authorization; the PR is merged (this step may also be performed by Charles manually via the Web UI).
5. A future implementation round is authorized by Charles in a separate message.

The implementation round does not auto-start. The agent waits for Charles's authorization in each step.

---

## 19. Acceptance criteria

The contract PR (this document's PR) is considered **accepted** when:

- The contract file `docs/tasks/TASK-019-slice-3b-adapter-implementation-contract.md` exists on disk and is complete (all 20 sections filled in, no `[TODO]` / `[FILL IN]` / `[PLACEHOLDER]` markers).
- The PR is **docs-only**: `git diff --name-only origin/main...HEAD` returns ONLY files under `docs/tasks/`. No `backend/**`, `frontend/**`, `scripts/**`, `.github/**`, `docker/**`, `migrations/**`, `pyproject.toml`, `uv.lock`, `package.json`, `package-lock.json`, `production_seeding.py`, or other non-docs file.
- No commits modify any file outside `docs/tasks/TASK-019-slice-3b-adapter-implementation-contract.md`.
- The CI pipeline shows green for the docs / backend tests / lint / typecheck jobs.
- The PR body lists the upstream frozen contracts and confirms compliance with all PR / CI / merge boundaries.

The future implementation round (separate, post-merge-of-this-contract) is considered **accepted** when (in addition to the above):

- All §15 required tests are added and pass.
- All §16 verification commands exit with code 0.
- The implementation round produces a `docs/tasks/TASK-019-slice-3b-implementation-closeout.md` closeout evidence document.
- The implementation round's PR body documents §6 allowed-files compliance, §7 forbidden-files compliance, and why (if applicable) the `backend/src/cold_storage/modules/validation/` fallback path was used.

---

## 20. Future rounds explicitly outside Slice 3B

The following are **explicitly outside Slice 3B** and require their own Charles authorization round:

### 20.1 Expected-output authoring round

A round that produces a **real expected output** for one or more of the three Slice 3A cases, via a frozen production path (not via hand-writing). This requires:
1. A production path that already exists at freeze time and is known to be stable for the specific case.
2. An explicit per-message Charles authorization for the expected-output authoring.

This is the only way to add an `implemented` case (i.e., a case with a real expected output and a passing production path). Until this round happens, the three Slice 3A cases remain placeholder.

### 20.2 Slice 1 / Slice 2 / Slice 4 / Slice N rounds

Any TASK-019 slice that produces a real production path component (e.g., a calculation, a report template, a coefficient resolution path) is outside Slice 3B and requires its own design contract + implementation + review round.

### 20.3 Production model / formula changes

Any change to a production formula, coefficient, threshold, weight, or scoring rule. These are forbidden by Slice 3 §4 and inherited by §5.1.

### 20.4 Pressure-drop implementation

Adding a pressure-drop calculation to the repository. This is forbidden by Slice 3 §4 and inherited by §5.1. Any future round that adds pressure-drop must include an explicit design contract amendment to remove the §7.1 pressure-drop prohibition (currently forbidden); the amendment is non-trivial and is not part of Slice 3B.

### 20.5 Discount / salvage / economic logic

Adding any discount rate, salvage value, or economic-model calculation. These are forbidden by Slice 3 §4 and inherited by §5.1. Any future round that introduces these requires an explicit design contract amendment.

### 20.6 UI / frontend implementation

Adding any frontend (Vue, CLI, dashboard) component. Slice 3B is backend-only. Any future round that requires a UI requires an explicit design contract amendment.

### 20.7 Migration / schema work

Adding any Alembic migration, schema change, or new table/column. Slice 3B does not introduce new schema. Any future round that requires a migration requires an explicit design contract amendment.

### 20.8 PR #21 / Issue #35 / Task 11B reactivation

Any reactivation, reopening, or amendment of PR #21, Issue #35, or Task 11B / TASK-011B. These remain frozen per their respective closeout / design-contract rounds.

### 20.9 Task 11B post-Phase B production path

Any continuation of Task 11B Phase B (the production path) outside the closed-set Slice 1 / Slice 2 / Slice 2A / Slice 2C / Slice 2D closeout territory. Slice 3B does not reopen Task 11B.

---

## 21. Compliance audit (this contract authoring round)

- 0 production code mutation ✅
- 0 tests mutation ✅
- 0 fixture / expected-output mutation ✅
- 0 manifest / migration / frontend / API-contract mutation ✅
- 0 `production_seeding.py` restoration ✅
- 0 Task 11B mutation ✅
- 0 PR #21 mutation ✅
- 0 Issue #35 mutation ✅
- 0 Slice 3 / Slice 3A contract mutation ✅
- 0 ready / 0 merge / 0 close-issue / 0 label mutation ✅
- 0 push during the initial design-contract authoring commit (push is Phase 8; not yet executed at this audit point) ✅
- 1 new docs file: `docs/tasks/TASK-019-slice-3b-adapter-implementation-contract.md` ✅
- Push and Draft PR creation performed later (Phase 8) per the spec; subject to §18 PR / CI / merge boundaries (Draft initially; Ready and Merge require Charles's per-message authorization)

---

## 22. Change log

| version | date | author | change |
|---|---|---|---|
| 1.0 | 2026-07-09 | Hermes | Initial TASK-019 Slice 3B adapter implementation contract. Inherits Slice 3 §1-§13 (PR #52, FROZEN) and Slice 3A §1-§11 (PR #53, FROZEN). Adds §6 allowed-files boundary, §7 forbidden-files boundary, §8 adapter-only behavior, §9 placeholder semantics, §10 three Slice 3A fixture cases as input, §11 production API boundary, §12 expected-output boundary, §13 prohibited inference rules, §14 error / reporting semantics, §15 required tests, §16 verification commands, §17 stop conditions, §18 PR / CI / merge boundaries, §19 acceptance criteria, §20 future rounds outside Slice 3B. Base SHA: `b51a0a6f842d4ecf7e74e7358ebc252094778a53` (= `origin/main` HEAD post-PR-#54 / PR-#53 / PR-#52). |
