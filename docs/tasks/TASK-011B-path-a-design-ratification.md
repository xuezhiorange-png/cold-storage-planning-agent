# Task 11 Phase B Resumption — Path A Design Ratification

**Status:** DESIGN-ONLY / DRAFT / awaiting Charles freeze authorization
**Created:** 2026-07-08 (server UTC)
**Author:** Hermes (proposal subject to Charles-authorized freeze review)
**Branch base:** `main @ 184463138e54d23b57ef961130edf78b61e8f36c` (= `origin/main` HEAD post-PR-#48)
**Branch name (proposed):** `codex/task-11b-path-a-design-ratification`
**Target Phase:** Task 11 Phase B Resumption (Path A)
**Authoritative references:**
- `docs/tasks/TASK-011B-phase-b-resumption-pre-freeze.md` (PR #48 design contract, original §1-§10 + Amendment 1 §11)
- `docs/tasks/TASK-011B-phase4-issue35-production-roundtrip-governance.md` (Phase 4 governance, §15/§16/§17/§18/§19/§20)
- Amendment 1 commit `06c12840f6485a8176b025710835f492c5c36047` (starting-line fidelity correction)
- Issue #35 (closed 2026-07-08, state_reason=completed)
- PR #21 (Draft / Open / Not merged / head `7822581eeee4c590b4ed9b1e3c46c1cde5490098`)
- `main` post-merge main CI run `28922438426` (completed / success / 4 jobs)

---

## 0. Preamble

This document ratifies **Path A** as defined in the Amendment 1 §11.5.1 of the pre-freeze design contract. Path A implements Task 11 Phase B Resumption by introducing a **new, narrowly-scoped evaluation-to-orchestration adapter** on a fresh branch from `main`, without porting PR #21's evaluation subsystem onto `main`. The adapter is the **only** evaluation-side artifact introduced; it is the **only** path by which the evaluation layer can interact with production.

This document does **not** authorize implementation. It ratifies the design. Implementation begins only after Charles freezes this design and authorizes a follow-up `Implementation Slice A1` round.

---

## 1. Adapter responsibility

### 1.1 What the adapter is

The evaluation adapter is a **thin, stateless, in-process Python client** that the evaluation harness instantiates per evaluation run. It exposes a single, narrowly-scoped API surface to the evaluation layer. It has the following properties:

- It is the **only** evaluation-side code that holds a reference to `compose_production_scheme_service(session_factory)` or any other production orchestrator entrypoint.
- It is the **only** evaluation-side code that knows about the production orchestrator's public ports (`backend/src/cold_storage/modules/orchestration/application/ports.py` and the equivalent scheme-service ports).
- It is **read-only** with respect to production row schema: it never `Session.add(...)` a `CalculationRunRecord`, `SourceBindingRecord`, `SchemeRun`, `OrchestrationIdentityRecord`, `OrchestrationAttemptRecord`, `ExecutionSnapshotRecord`, `CoefficientContextRecord`, or `ApprovedWeightSetRevision` row. It does not call `session.flush()`, `session.commit()`, `bulk_insert_mappings`, or any raw SQL `INSERT` / `UPDATE` / `DELETE` against the production tables.
- It does **not** know about evaluation's `expected_outcome`, `manifest.json`, `compare.py`, `canonicalize.py`, `run_directory.py`, `cli.py`, or any evaluation-side artifact. It returns a typed result that the evaluation harness then formats into the evaluation artifact.
- It has **no** startup-time configuration beyond a `session_factory` (the same `session_factory` that production code uses) and an evaluation-side `scenario_id` + project input. It does not read environment variables, configuration files, or feature flags to decide whether to short-circuit. The only "configuration" surface is the explicit constructor parameters.

### 1.2 What the adapter is **not**

- It is **not** a wrapper around `SchemeService` that bypasses the production orchestrator. The production orchestrator is the **only** path that writes production rows; the adapter MUST go through it.
- It is **not** a re-implementation of any production calculator, coefficient resolver, source-binding verifier, scheme selector, or weight-set reconciler. The adapter MUST call into production public ports for every decision.
- It is **not** a place to put evaluation-only production row fabrication. Such fabrication is forbidden (see §1.3 below).
- It is **not** a place to introduce demo / latest-row / partial-binding fallback. Such fallbacks are forbidden (see §1.3 below).
- It is **not** a place to suppress, rename, or reclassify `requires_review` warnings. Suppression is forbidden (see §1.3 below).
- It is **not** a place to modify production formulas, coefficient values, scoring rules, review rules, thresholds, or weights. The adapter MUST treat these as immutable production-side contracts.

### 1.3 Forbidden paths (re-stated from §5 of the pre-freeze contract, with adapter-specific elaborations)

The following are **explicitly forbidden** in any implementation under this contract. The amendment 1 §11.6 §8 stop conditions are inherited and remain binding.

- **F1. `backend/src/cold_storage/evaluation/production_seeding.py` MUST NOT be created.** The file remains absent. Restoration is a §8 #1 stop condition.
- **F2. The adapter MUST NOT call `Session.add(...)`, `session.flush()`, `session.commit()`, `bulk_insert_mappings`, or raw SQL `INSERT` / `UPDATE` / `DELETE` against any production table.** All production row writes are owned by `compose_production_scheme_service(session_factory)`.
- **F3. The adapter MUST NOT hand-write `CalculationRunRecord`, `SourceBindingRecord`, `SchemeRun`, orchestration identity / attempt / execution-snapshot / coefficient-context / approved weight-set revision rows.** All such rows are produced by the production orchestrator.
- **F4. The adapter MUST NOT hand-write `SourceSnapshotContentV1` or `combined_source_hash`.** These are produced by the production `build_source_snapshot_content_v1` / `_compute_combined_source_hash` helpers.
- **F5. The adapter MUST NOT introduce demo / unverified coefficients into the production path.** Demo coefficients, if needed for harness-only purposes, are produced via the existing production-side approved-coefficient gate (which already supports a `requires_review=true` baseline for catalog inputs; the adapter reuses that path).
- **F6. The adapter MUST NOT introduce "latest-row" selection on approved coefficient queries.** The production-side `SourceBindingVerifier` is the single selector.
- **F7. The adapter MUST NOT introduce partial `SourceBinding` writes that succeed despite missing required slots.** Partial bindings are detected and rejected by `SourceBindingVerifier`.
- **F8. The adapter MUST NOT suppress, rename, downgrade, or reclassify `requires_review` warnings or `UntrustedCoefficientError` raise paths.** These warnings are forwarded as-is to the evaluation harness.
- **F9. The adapter MUST NOT alter production formulas, coefficient values, scoring rules, review rules, thresholds, weights, or migrations.** The adapter treats these as immutable production-side contracts.
- **F10. The adapter MUST NOT bypass `SourceBindingVerifier`.** All source binding goes through it.
- **F11. The adapter MUST NOT bypass `SchemeService`.** All scheme runs go through `compose_production_scheme_service(session_factory)`.
- **F12. The adapter MUST NOT bypass the production orchestrator.** No `session_factory`-less execution path. No `session` parameter is accepted by the adapter; only a `session_factory`.
- **F13. The adapter MUST NOT bypass approved non-demo coefficient governance.** The adapter asks the production-side `IdentityReadPort` / coefficient resolver for an approved coefficient revision; it does not construct one.
- **F14. The adapter MUST NOT modify `backend/src/cold_storage/modules/*/infrastructure/migrations/versions/*.py`.** No new Alembic migration under this contract. The adapter uses the existing schema (post-Phase 1/2/3/4 migrations).
- **F15. The adapter MUST NOT import evaluation code into production modules.** All cross-boundary access goes through public ports.

### 1.4 Single production write path

There is **exactly one** production write path: `compose_production_scheme_service(session_factory)`. This is the entrypoint of the production orchestrator. The adapter calls it (see §2.3 for the call shape). No other code path may write production rows.

```
Evaluation Runner
       |
       v
Evaluation Adapter (this contract)
       |
       v
compose_production_scheme_service(session_factory)
       |
       v
SchemeService (and SourceBindingVerifier, identity layer, coefficient resolver)
       |
       v
Production Persistence (SQLite / PostgreSQL)
```

The adapter's call to `compose_production_scheme_service(session_factory)` produces, in order, all production rows:

- `OrchestrationIdentityRecord` row (if a new identity is needed for the project input)
- `OrchestrationAttemptRecord` row
- 5 `CalculationRunRecord` rows (zone, throughput, investment, cooling_load, equipment — exact count, per Phase-4 §4.3)
- `CoefficientContextRecord` rows (one per calculation run, per the production coefficient resolution path)
- `SourceBindingRecord` row (with `combined_source_hash` and snapshot content)
- `ExecutionSnapshotRecord` rows (one per stage)
- `ApprovedWeightSetRevision` row (if a new weight-set revision is needed)
- `SchemeRun` row (with `scheme_status` ∈ {`PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `REVIEW_REQUIRED`})

The adapter **receives** the resulting `SchemeRun` (and its `calculation_run_id` lineage, `SourceBindingRecord`, weight-set revision) but does **not** persist anything of its own.

---

## 2. Input / output contract

### 2.1 Inputs to the adapter

The adapter's public surface (one method) takes:

- `session_factory: Callable[[], Session]` — the same `session_factory` that production code uses (typically `lambda: SessionLocal()` for SQLite, or a `scoped_session` factory for PostgreSQL). The adapter does **not** accept a raw `Session`; the production entrypoint accepts a factory, and the adapter does the same.
- `scenario_id: str` — the evaluation scenario's stable identifier (e.g., `"baseline-feasible"`, `"high-throughput-review"`). This is passed through to production for log correlation only; it does not change any production behavior.
- `project_input: ProjectInput` — the same `ProjectInput` shape that production services accept. The adapter does **not** validate, normalize, or default-fill the project input; the production orchestrator does that.

### 2.2 Outputs from the adapter

The adapter returns a typed dataclass `AdapterResult` with the following fields:

- `scheme_run: SchemeRun` — the resulting `SchemeRun` row from `compose_production_scheme_service(session_factory)`. The `scheme_status` is one of the production-defined `SchemeStatus` values.
- `calculation_run_ids: list[int]` — the 5 `CalculationRunRecord` IDs that the orchestrator persisted, in the canonical order: `[zone, throughput, investment, cooling_load, equipment]`. The evaluation harness uses these to construct the stage ledger and to assert the §4.3 strict row counts.
- `source_binding_id: int | None` — the `SourceBindingRecord` ID, or `None` if the orchestrator did not persist one (this is only possible on the `REVIEW_REQUIRED` or `FAILED` paths; on `SUCCEEDED`, it is non-null).
- `weight_set_revision_id: int | None` — the `ApprovedWeightSetRevision` ID, or `None` if a new revision was not needed.
- `combined_source_hash: str | None` — the `combined_source_hash` from the resulting `SourceBindingRecord`, or `None` if no `SourceBindingRecord` was persisted.
- `review_required: bool` — whether the resulting `SchemeRun` carries a `requires_review` flag. The adapter does **not** suppress this flag; it forwards it as-is to the evaluation harness.
- `review_reasons: list[str]` — the list of `requires_review` reasons reported by the orchestrator. The adapter does **not** filter or rename these.

The adapter does **not** return a `success: bool` flag in the literal sense; the `scheme_run.scheme_status` field encodes success. The evaluation harness translates the status to its own `outcome` vocabulary in §3 below.

### 2.3 Adapter call shape (pseudocode)

```python
def execute_scenario(
    session_factory: Callable[[], Session],
    scenario_id: str,
    project_input: ProjectInput,
) -> AdapterResult:
    """
    Submit `project_input` to the production orchestrator and return
    the resulting SchemeRun + lineage. This is the ONLY call the
    evaluation layer makes to production.
    """
    orchestrator = compose_production_scheme_service(session_factory)
    scheme_run = orchestrator.generate_production_scheme_run(
        project_version_id=...,  # resolved from project_input via production path
        scenario_id=scenario_id,
    )
    # lineage extraction is read-only
    return AdapterResult(
        scheme_run=scheme_run,
        calculation_run_ids=[...],   # 5 IDs, in canonical order
        source_binding_id=scheme_run.source_binding_id,
        weight_set_revision_id=scheme_run.weight_set_revision_id,
        combined_source_hash=scheme_run.source_binding.combined_source_hash,
        review_required=scheme_run.requires_review,
        review_reasons=[...],
    )
```

The exact call shape (function name, parameter names, return type) MUST be frozen by the implementation round against the production orchestrator's actual public surface. This contract does **not** pin the function name; it pins the **invariant** that the adapter goes through `compose_production_scheme_service(session_factory)` and that the adapter does no production row writes.

### 2.4 Why this shape

- **Single-call**: the evaluation harness submits the project input and gets a `SchemeRun` back. The harness does not need to know about calculation runs, source bindings, weight sets, or coefficients.
- **Read-only lineage**: the adapter pulls the 5 calculation_run_ids, source_binding_id, weight_set_revision_id, and combined_source_hash from the resulting `SchemeRun` row. It does not query the database for these; the production orchestrator already attaches them to the `SchemeRun` (this is the Phase-4 main wiring; the implementation round must verify this wiring exists before pinning the adapter's return shape).
- **`review_required` is a first-class field**: the adapter does not collapse `SUCCEEDED` and `REVIEW_REQUIRED` into a single "success" outcome. The evaluation harness translates `scheme_status` to its own `outcome` per §3.

---

## 3. Failure semantics

The adapter's behavior on production-side failure is:

### 3.1 Production raises

- If `compose_production_scheme_service(session_factory).generate_production_scheme_run(...)` raises any exception, the adapter **forwards** that exception to the evaluation harness. The adapter does **not** catch, suppress, log-and-continue, or transform the exception. The evaluation harness decides what to do with it (typically: record a `failed` stage in the stage ledger, mark the run as `failed`, exit non-zero).
- The adapter does **not** introduce a new error class. All errors come from production.

### 3.2 Production returns `FAILED` or `REVIEW_REQUIRED`

- The adapter returns the `SchemeRun` as-is, with `scheme_status` set to `FAILED` or `REVIEW_REQUIRED`, and `review_required=True` if `REVIEW_REQUIRED`. The evaluation harness translates this to its own `outcome` vocabulary.
- The adapter does **not** retry. The adapter does **not** "try a different path" or "fall back to demo coefficients" or "suppress the review flag".

### 3.3 Production returns `SUCCEEDED`

- The adapter returns the `SchemeRun` as-is, with `scheme_status=SUCCEEDED`. The evaluation harness records `outcome=success`.

### 3.4 No harness-level blocker

- The adapter does **not** raise any `EVAL_PRODUCTION_PIPELINE_PREREQUISITE_MISSING` error class. That error class is forbidden (F-3 re-stated). If the production orchestrator cannot execute (e.g., schema migration is missing, session_factory is broken), production raises its own error (e.g., `OperationalError`, `ProgrammingError`); the adapter forwards it.
- The adapter's `AdapterResult` always reflects what production actually did, not a synthetic "blocked" outcome.

### 3.5 Why no harness-level blocker

The pre-freeze contract §6 #4 says: "No `EVAL_PRODUCTION_PIPELINE_PREREQUISITE_MISSING` error is raised on the happy path." The happy path is `scheme_status=SUCCEEDED`. The adapter implements this by simply not raising that error. If the production orchestrator succeeds, the adapter returns success. If the production orchestrator fails or needs review, the adapter returns the corresponding `SchemeRun` status. There is no "blocked" outcome in the production contract; the only outcomes are `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `REVIEW_REQUIRED`.

The evaluation harness translates these as:

| production `scheme_status` | evaluation `outcome` |
|---|---|
| `SUCCEEDED` | `success` |
| `REVIEW_REQUIRED` | `review_required` (new outcome; not in the pre-freeze contract, but a faithful translation of production's `REVIEW_REQUIRED`) |
| `FAILED` | `failed` |
| `PENDING` / `RUNNING` (if returned synchronously, which they shouldn't be) | `failed` (treat as a contract violation; surface) |
| production raises | `failed` (with the exception in the stage ledger) |

`review_required` is a new outcome that the pre-freeze contract did not enumerate. This is a Path A-specific addition. It is **not** a downgrade of `expected_outcome=success` (the §8 #12 stop condition). It is a separate, production-faithful outcome that the evaluation harness exposes.

### 3.6 What "blocked" means now

The pre-freeze contract's `outcome=blocked` (from PR #21's frozen-by-design contract) **does not exist in Path A**. Path A's evaluation harness does not have a `blocked` outcome. The only outcomes are `success`, `review_required`, `failed`, and `failed (with exception)`.

If a future round needs a `blocked` outcome, that is a contract-level change requiring a new freeze.

---

## 4. Persistence ownership

### 4.1 Production persistence — owned by production

All production row writes are owned by `compose_production_scheme_service(session_factory)`. The adapter does not write any production row (F2 / F3 / F4).

### 4.2 Evaluation persistence — owned by evaluation

The evaluation harness persists evaluation-side artifacts (raw run JSON, normalized run JSON, summary JSON, run directory state) under a path of its choosing. These artifacts are **not** production rows; they live outside the production database and are owned by the evaluation harness.

Path A does **not** re-use PR #21's evaluation directory structure (`evaluation/runs/<run_id>/...`) verbatim. Instead, it specifies a clean Path A structure:

```
backend/storage/evaluation_runs/<run_id>/      # or evaluation/runs/ — frozen by implementation round
    raw/<scenario_id>.json
    normalized/<scenario_id>.json
    summary.json
```

The `backend/storage/evaluation_runs/` directory is **not** in scope of this design contract; it is up to the implementation round to freeze the path. What matters is:

- The path is **not** `evaluation/runs/` if that path conflicts with the `.gitignore` rule `"evaluation/"` (which excludes the entire `evaluation/` directory tree). See Amendment 1 §11.5.1 for the manifest / fixture path discussion.
- The path is **not** inside `backend/src/cold_storage/evaluation/` (that is the source module path, not an artifact path).
- The path is **not** inside any production module.

### 4.3 What the adapter does **not** persist

- The adapter does not write to any file. The adapter returns `AdapterResult` in memory; the evaluation harness writes the artifact.
- The adapter does not mutate the `session_factory`'s session. The session is the production orchestrator's; the adapter reads from it (via the returned `SchemeRun`) but does not add, delete, or commit.

### 4.4 What the evaluation harness persists

The evaluation harness writes:

- `raw/<scenario_id>.json` — the uncanonicalized JSON form of the run (including all `AdapterResult` fields plus harness-side stage ledger).
- `normalized/<scenario_id>.json` — the canonicalized form (canonical JSON serialization, deterministic field ordering, etc.).
- `summary.json` — the run-level summary (which scenarios ran, which passed / failed / needed review, manifest hash, run timestamps).

The canonicalization and comparison policy are evaluation-side and are **not** in scope of this design contract; they will be frozen by the implementation round.

---

## 5. Acceptance test strategy

Path A's acceptance test strategy is intentionally narrow. It consists of **four** test files, each with a clear purpose:

### 5.1 `backend/tests/evaluation/test_adapter_contract.py` (new file)

**Purpose**: assert that the adapter itself satisfies the contract in this document. This is the **only** test that directly exercises the adapter.

**Test cases** (minimum set, to be expanded by implementation round):

- `test_adapter_does_not_import_production_modules_except_through_public_ports`: assert that the adapter's import graph includes only `cold_storage.modules.orchestration.application.ports`, `cold_storage.modules.schemes.application.service`, `cold_storage.bootstrap.production_composition`, and standard library / type-hint modules. Assert that it does **not** import from `cold_storage.modules.orchestration.infrastructure.*` (the F15 / §8 family of stops).
- `test_adapter_does_not_call_session_add_or_commit`: assert that the adapter's source code does not contain `Session.add`, `session.flush`, `session.commit`, `bulk_insert_mappings`, or `INSERT` / `UPDATE` / `DELETE` SQL keywords. (A simple textual grep is sufficient; this is a structural invariant.)
- `test_adapter_does_not_import_evaluation_artifacts_into_production`: assert that the production modules do not import anything from `cold_storage.evaluation.*` after the adapter is added. (This guards against accidental reverse-coupling.)
- `test_adapter_call_shape_matches_production_orchestrator`: assert that the adapter calls `compose_production_scheme_service(session_factory)` exactly once per `execute_scenario` invocation. Use a mock or a recording `session_factory` to count calls.
- `test_adapter_forwards_exceptions_unchanged`: assert that when the production orchestrator raises, the adapter raises the same exception type with the same message. No suppression, no transformation.
- `test_adapter_returns_review_required_as_outcome`: assert that when the production `SchemeRun` has `scheme_status=REVIEW_REQUIRED`, the adapter returns that status in `AdapterResult` and the harness maps it to `outcome=review_required`. The adapter does **not** collapse this to `success` or `failed`.

### 5.2 `backend/tests/evaluation/test_path_a_baseline_sqlite.py` (new file)

**Purpose**: assert the **end-to-end** happy path on SQLite. This is the smallest acceptance test that proves the adapter is functional against the real production path.

**Test cases** (minimum set):

- `test_baseline_feasible_succeeds_on_sqlite`: instantiate the adapter with a fresh in-memory SQLite session_factory, call `execute_scenario` with `scenario_id="baseline-feasible"` and a `ProjectInput` that corresponds to a feasible production input. Assert that the resulting `SchemeRun.scheme_status == "SUCCEEDED"`. Assert that the 5 `CalculationRunRecord` rows are present (PK-set symmetric-difference test). Assert that the `SourceBindingRecord.combined_source_hash` is reproducible from the production `build_source_snapshot_content_v1` helper. Assert that no `requires_review` warnings are raised (or, if they are, the test asserts the corresponding `outcome=review_required`, not `success`).
- `test_baseline_feasible_creates_no_evaluation_owned_production_rows`: assert that the `CalculationRunRecord`, `SourceBindingRecord`, `SchemeRun` rows persisted during the test are owned by the production orchestrator (i.e., they have the production-defined default values, the production-defined `created_at` timestamps, etc.). This guards against F2 / F3 / F4 (no fabrication).
- `test_baseline_feasible_does_not_create_production_seeding_file`: assert that the file `backend/src/cold_storage/evaluation/production_seeding.py` does **not** exist on disk after the test runs. (This is a §8 #1 stop condition check.)

### 5.3 `backend/tests/evaluation/test_path_a_baseline_postgresql.py` (new file)

**Purpose**: assert the **end-to-end** happy path on PostgreSQL.

**Test cases**: same shape as the SQLite test, with a PostgreSQL session_factory. Use the existing test infrastructure for PostgreSQL integration tests (see `backend/tests/integration/test_production_archive_wiring_e2e_postgresql.py` and `backend/tests/integration/test_zero_delta_invariant_postgresql.py` for the Phase-4 baseline; the implementation round can mirror their setup).

This is the **only** test that runs against PostgreSQL. The implementation round is responsible for ensuring that the CI `backend-postgresql` job runs it (see §6.3 for CI).

### 5.4 `backend/tests/evaluation/test_path_a_no_pr21_pollution.py` (new file)

**Purpose**: assert that no PR #21-era forbidden patterns are present in the new code.

**Test cases** (minimum set):

- `test_no_production_seeding_module_imports`: assert that no source file in `backend/src/cold_storage/evaluation/` imports from `backend/src/cold_storage/evaluation/production_seeding` (the forbidden file).
- `test_no_evaluation_layer_raw_orm_on_production_tables`: assert that the evaluation layer's source code does not contain `CalculationRunRecord`, `SourceBindingRecord`, `SchemeRun` literals except in `AdapterResult` type annotations (where they are read-only references).
- `test_no_evaluation_module_writes_to_main_or_main_modules`: assert that evaluation modules do not import from `cold_storage.modules.*.infrastructure.*` (the F15 / §8 family).

### 5.5 Tests explicitly **not** in this contract

- Tests that re-implement the PR #21 frozen blocked contract (e.g., `test_baseline_outcome_blocked_by_prerequisite`).
- Tests that carry over the PR #21 design doc's expected outputs (`evaluation/expected/baseline-feasible.v1.json` etc.).
- Tests that depend on `evaluation/manifest.json` (the implementation round will freeze a new manifest as a separate step).
- Tests that mock or stub the production orchestrator. The adapter's value is in calling the real production path; mocking it would defeat the purpose of the contract.

If a future round needs any of the above, that is a contract-level change requiring a new freeze.

---

## 6. Expected output strategy

Path A does **not** re-use PR #21's expected output files (`evaluation/expected/baseline-feasible.v1.json`, `evaluation/expected/high-throughput-review.v1.json`, `evaluation/expected/invalid-blocked.v1.json`). Those files do not exist on `main`, and Path A does not port them.

Instead, Path A defines expected outputs as a **separate freeze step** that happens after the adapter's end-to-end happy path is proven (via §5.2 / §5.3). The freeze step has the following properties:

### 6.1 Expected output format

The expected output for a scenario is the **canonicalized form of `AdapterResult` plus the harness-side stage ledger**, serialized as a single JSON file:

```
backend/storage/evaluation_runs/<run_id>/expected/<scenario_id>.v1.json
```

or, equivalently (the implementation round chooses):

```
backend/tests/evaluation/data/expected/<scenario_id>.v1.json
```

The exact directory is up to the implementation round. What matters:

- The expected output is **not** in `evaluation/expected/` (which is gitignored via the `.gitignore` rule `"evaluation/"`). See §6.5.
- The expected output is **not** in `backend/src/cold_storage/evaluation/` (which is the source module path).
- The expected output is committed to git (unlike the actual `runs/<id>/` directory, which is gitignored).

### 6.2 Expected output content

The expected output file contains:

- The 5 `CalculationRunRecord` IDs (or, if IDs are non-deterministic, the PK-set symmetric-difference from a fresh SQLite or PostgreSQL test).
- The `SourceBindingRecord.combined_source_hash`.
- The `ApprovedWeightSetRevision` ID (or a stable proxy if IDs are non-deterministic).
- The `SchemeRun.scheme_status` (must be `SUCCEEDED`).
- The `scheme_run.id` (or, again, a stable proxy).
- The stage ledger (which stages ran, in which order, with what inputs and outputs).
- The `requires_review` reasons list (must be empty for `baseline-feasible`).
- The canonicalized JSON form (canonical field ordering, deterministic representation).

The expected output does **not** contain:

- Field values that depend on database-generated UUIDs, timestamps, or other non-deterministic artifacts (these are excluded from the comparison policy).
- Field values that depend on demo coefficients or unverified coefficients.
- Field values that depend on `requires_review=true` baselines (the expected output for `baseline-feasible` is `requires_review=false` only).

### 6.3 Reviewer sign-off

The expected output regeneration is gated on **explicit Charles reviewer sign-off**, per §8 #10 of the pre-freeze contract (inherited via Amendment 1 §11.6). The sign-off is recorded in a separate document:

```
docs/tasks/TASK-011B-path-a-expected-outputs-reviewer-sign-off.md
```

This document is created by the implementation round and signed off by Charles **before** the expected output files are committed. The sign-off record must include:

- The commit SHA of the adapter + acceptance test PR.
- The commit SHA of the regenerated expected output files.
- Charles's review verdict (approve / amend / reject).
- The comparison policy (which fields are exact-matched, which are decimal-matched, which are ignored).

Without this sign-off document, the implementation PR cannot be marked Ready.

### 6.4 When expected outputs are generated

The expected outputs are generated **after** the adapter's end-to-end happy path is proven on both SQLite and PostgreSQL. The generation process is:

1. Implementation round commits the adapter + acceptance tests on `codex/task-11b-path-a-design-ratification` (or a successor branch).
2. Implementation round runs the acceptance test on a fresh SQLite and a fresh PostgreSQL.
3. The actual canonicalized outputs are captured (from the test run, not from a manual run).
4. The expected output files are committed as a separate commit (or as part of the same PR).
5. The reviewer sign-off document is created.
6. Charles signs off.
7. The PR is marked Ready.

### 6.5 Why Path A does not use `evaluation/expected/`

The pre-freeze contract and Amendment 1 assume a `evaluation/` directory at the repository root, with subpaths like `expected/`, `fixtures/`, `manifest.json`, etc. This is PR #21's layout. The `.gitignore` rule `"evaluation/"` excludes the **entire** `evaluation/` tree from version control. This means:

- If Path A uses `evaluation/expected/baseline-feasible.v1.json`, the file is **not** committed to git (it is gitignored). The expected output would not be reproducible from a fresh clone.
- If Path A uses `backend/storage/evaluation_runs/...`, the file **is** committed (the `.gitignore` does not exclude `backend/storage/`, only the top-level `evaluation/`).

Path A's expected output path is therefore either `backend/storage/...` or `backend/tests/evaluation/data/...`, both of which are tracked by git. The exact path is up to the implementation round, subject to Charles's review.

---

## 7. Relationship to PR #21

Path A's relationship to PR #21 is **strictly adversarial-by-design**: Path A does not import, cherry-pick, rebase, merge, or otherwise consume any commit or artifact from PR #21. Path A produces an entirely new evaluation harness from scratch.

### 7.1 What Path A does **not** carry over from PR #21

- **Code**: not a single `.py` file from PR #21 is copied, even if the code is structurally similar.
- **Tests**: not a single `test_*.py` from `backend/tests/evaluation/` is copied.
- **Expected outputs**: not a single `evaluation/expected/*.json` is copied.
- **Fixtures**: not a single `evaluation/fixtures/*.json` is copied.
- **Manifest**: not a single `evaluation/manifest.json` is copied. Path A freezes a new manifest in the implementation round.
- **Design doc**: PR #21's `docs/tasks/TASK-011-evaluation-pilot-readiness.md` is **not** carried over. It is not in this repository's `main` (it never reached main), and it is not in scope of this contract. It remains as a historical record on PR #21 branch and on the PR #21 GitHub PR.
- **The `EvaluationPrerequisiteMissingError` error class**: not carried over. It is forbidden (F-3). If a future Path A round needs an evaluation-side error class, that is a separate freeze step.

### 7.2 What Path A **may** reference from PR #21

Path A may reference PR #21 in **comments** and **design doc** for historical context only. For example:

- The adapter's module docstring may include a single line: `# Historical context: this module is the consumer half of the Task 11 Phase B Resumption. See PR #21 for the rejected Round 11 / Round 12 history.`
- The design doc (this contract) references PR #21 by number and branch head SHA.

PR #21 is **not** an implementation base. PR #21 is **not** read as source code in any Path A implementation. PR #21's `codex/task-11-evaluation` branch is **not** fetched, checked out, or imported by Path A.

### 7.3 What happens to PR #21

PR #21 remains **Draft / Open / Not merged / untouched** per the pre-freeze contract §1.1, §2, §3, §4, §5.4, §9, and Amendment 1 §11.4. Specifically:

- PR #21's branch ref `codex/task-11-evaluation` head `7822581eeee4c590b4ed9b1e3c46c1cde5490098` is preserved.
- PR #21 is **not** rebased, force-pushed, cherry-picked, merged, or otherwise mutated by Path A.
- PR #21's body, comments, labels, and review state are **not** modified.
- PR #21's commit history (the Round 11 → Round 12 reversal arc) remains as a historical record.

The §8 #9 stop condition ("PR #21 is rebased, force-pushed, merged, or otherwise mutated") remains binding and is inherited from Amendment 1 §11.6.

### 7.4 The "supersedes" relationship

Per pre-freeze contract §1.1, the pre-freeze design contract itself supersedes PR #21. Path A is the implementation of that supersession. Once Path A is merged to `main`, PR #21 remains as a historical Draft; it does not need to be closed or otherwise modified by this contract. (Closing PR #21 is a separate Charles decision; it is not in scope of Path A.)

---

## 8. Stop conditions (inherited + adapter-specific)

All 13 §8 stop conditions of the pre-freeze contract are inherited via Amendment 1 §11.6. The following are the **adapter-specific** elaborations of those conditions for Path A:

- **S-1 (inherited from §8 #1)**: `backend/src/cold_storage/evaluation/production_seeding.py` MUST NOT be created.
- **S-2 (inherited from §8 #2)**: the adapter and any evaluation-side code MUST NOT use `Session.add(...)`, `session.flush()`, `session.commit()`, `bulk_insert_mappings`, or raw SQL `INSERT` / `UPDATE` / `DELETE` against production tables.
- **S-3 (inherited from §8 #3)**: the evaluation layer MUST NOT introduce demo / latest-row / partial-binding fallback into the production path.
- **S-4 (inherited from §8 #4)**: the evaluation layer MUST NOT suppress, rename, or reclassify `requires_review` warnings.
- **S-5 (inherited from §8 #5)**: the evaluation layer MUST NOT alter production formulas, coefficient values, scoring rules, review rules, thresholds, or weights.
- **S-6 (inherited from §8 #6)**: the evaluation layer MUST NOT bypass the production orchestrator. The adapter's only path is `compose_production_scheme_service(session_factory)`.
- **S-7 (inherited from §8 #7)**: the evaluation layer MUST NOT bypass `SourceBindingVerifier` or `SchemeService`.
- **S-8 (inherited from §8 #8)**: the evaluation layer MUST NOT bypass approved non-demo coefficient governance.
- **S-9 (inherited from §8 #9)**: PR #21 is **not** rebased, force-pushed, merged, or otherwise mutated.
- **S-10 (inherited from §8 #10)**: expected output regeneration is **not** committed without Charles's reviewer sign-off recorded in `docs/tasks/TASK-011B-path-a-expected-outputs-reviewer-sign-off.md`.
- **S-11 (inherited from §8 #11)**: CI reruns are **not** performed that mask real failures.
- **S-12 (inherited from §8 #12)**: `expected_outcome` is **not** downgraded from `"success"` to `"blocked"` (or any other value). Path A does not have a `blocked` outcome; the new `review_required` outcome is a separate status, not a downgrade.
- **S-13 (inherited from §8 #13)**: the evaluation layer MUST NOT add a new Alembic migration.
- **S-14 (Path A-specific)**: the evaluation harness MUST NOT introduce a `blocked` outcome (a Path A-specific prohibition; the pre-freeze contract's `blocked` outcome is forbidden in Path A).
- **S-15 (Path A-specific)**: the evaluation harness MUST NOT carry over PR #21's design doc, expected outputs, fixtures, manifest, or any source file (a Path A-specific elaboration of §11.7).
- **S-16 (Amendment 1 §11.6 implicit)**: the implementation target's `main` base MUST be re-verified via `git ls-tree -r <base> --name-only | grep -E '(^evaluation/|backend/src/cold_storage/evaluation/|backend/tests/evaluation/)'` at the start of every implementation round; if the result contains more paths than expected, the implementation round MUST stop and surface this.

A violation of any of S-1 through S-16 is a STOP. The implementation round reports the violation (condition number, evidence, recommended next step) and exits without completing the round.

---

## 9. Scope of the design freeze

This design contract freezes the following:

- The adapter's responsibility (§1).
- The adapter's input / output contract (§2).
- The adapter's failure semantics (§3).
- The evaluation / production persistence ownership boundary (§4).
- The acceptance test strategy (§5).
- The expected output strategy (§6).
- The relationship to PR #21 (§7).
- The stop conditions (§8).

This design contract does **not** freeze:

- The exact name of the adapter module (candidates: `backend/src/cold_storage/evaluation/adapter.py`, `backend/src/cold_storage/evaluation/orchestration_client.py`, etc.). The implementation round chooses, subject to Charles's review.
- The exact `AdapterResult` field names. The fields are fixed; the names can be adjusted.
- The exact call shape of `compose_production_scheme_service(session_factory).generate_production_scheme_run(...)` (the function name and parameter list depend on the production orchestrator's actual public surface, which the implementation round must verify).
- The exact expected output directory (candidates: `backend/storage/evaluation_runs/...` or `backend/tests/evaluation/data/...`).
- The exact comparison policy for expected outputs (exact-matched paths, decimal-matched paths, ignored paths).
- The exact manifest schema (the implementation round freezes a new manifest as a separate step).

---

## 10. Implementation round authorization gates

This design contract is a design contract. Implementation does **not** begin until Charles freezes this contract and authorizes a follow-up `Implementation Slice A1` round.

The implementation round's authorization must explicitly include:

- The contract freeze acceptance (this document).
- The expected output path (`backend/storage/...` or `backend/tests/evaluation/data/...`).
- The expected output comparison policy (or a freeze that the implementation round will pick).
- The expected output reviewer sign-off process (sign-off document path, sign-off record structure).
- The implementation PR's branch name (candidate: `codex/task-11b-path-a-implementation-slice-a1`).
- The implementation PR's target (must be `main`).
- The implementation PR's expected diff size (≤ 1000 LOC across all new files, per Amendment 1 §11.5.1; if the implementation round needs more, that is a contract change requiring a new freeze).
- The 4-job CI green requirement (compose-config / frontend / backend-sqlite / backend-postgresql all success, with backend-postgresql including the §5.3 PostgreSQL acceptance test).

Without these explicit gates in the implementation round's authorization, the implementation round does **not** begin.

---

## 11. Change log

- 2026-07-08 (this commit): initial Path A design ratification, awaiting Charles freeze review. No implementation begins until Charles signs off.
- 2026-07-08 (Amendment 2): adapter input contract corrected. The original §2 input contract (`session_factory, scenario_id, project_input → AdapterResult`) is **superseded by §13 Amendment 2**, which replaces the surface with `session_factory, *, source_binding_id, weight_set_revision_id, correlation_id, database_backend → AdapterResult`. The Slice A1 preflight round (2026-07-08, branch `codex/task-11b-path-a-impl-slice-a1`) verified via ground-truth reading of the production source that the original §2 surface is incompatible with the actual production API. See §13 for the corrected contract (option A1-2a), the explicit ownership boundary (adapter does not do upstream production state), and the deleted false assumption.

---

## 12. Author signature

This document is a proposal authored by Hermes in response to Amendment 1 §11.5.1 and Charles's Path A ratification authorization. It is **not** the design contract until Charles signs off. If Charles proposes amendments (e.g., a different `outcome` vocabulary, a different expected output path, a different adapter module name), those amendments are recorded in a successor commit on this branch or on a successor branch.


---

## 13. Amendment 2 — Adapter input contract correction (A1-2a)

### 13.1 Discovery (from Slice A1 preflight round)

On 2026-07-08, an Implementation Slice A1 preflight round on `codex/task-11b-path-a-impl-slice-a1` from `main @ 184463138e54d23b57ef961130edf78b61e8f36c` (post-PR-#48) attempted to implement the §2 design as written. The preflight read-only audit of the production source revealed that the §2 surface is **incompatible with the actual production API**.

The contract said:

```python
def execute_scenario(
    session_factory: Callable[[], Session],
    scenario_id: str,
    project_input: ProjectInput,
) -> AdapterResult:
    """
    Submit `project_input` to the production orchestrator and return
    the resulting SchemeRun + lineage. This is the ONLY call the
    evaluation layer makes to production.
    """
    orchestrator = compose_production_scheme_service(session_factory)
    scheme_run = orchestrator.generate_production_scheme_run(
        project_version_id=...,  # resolved from project_input via production path
        scenario_id=scenario_id,
    )
    ...
```

The actual production surface on `main` is:

- `compose_production_scheme_service(session_factory) -> ProductionSchemeService` is the **second-stage** factory (returns a service whose entrypoint `generate_production_scheme_run(cmd)` requires a pre-built `GenerateProductionSchemeCommand`).
- `GenerateProductionSchemeCommand` is `@dataclass(frozen=True, slots=True, kw_only=True)` with **mandatory** fields `source_binding_id: str`, `weight_set_revision_id: str`, `correlation_id: str`, `database_backend: str`. None of these are derived from a `project_input`; they are FK references and required NOT-NULL columns.
- The `source_binding_id` is produced only by the upstream `ProductionSourceBindingUseCase.run(session, command, snapshot_payload, ctx_payload, snapshot_id, ctx_id)` (in `backend/src/cold_storage/modules/orchestration/application/production_source_binding.py:154-260`), which itself requires a multi-step upstream: an `OrchestrationRequestCommand`, a verbatim `execution_snapshot_payload`, a verbatim `coefficient_context_payload`, and pre-existing `execution_snapshot_id` + `coefficient_context_id` durable row IDs.
- The `weight_set_revision_id` references a pre-existing `ApprovedWeightSetRevision` row with `status='approved'`. There is no production-side helper that creates and approves a weight-set revision from a `project_input`.
- The production side exposes **two** separate composition roots (`compose_production_source_binding_use_case(...)` and `compose_production_scheme_service(...)`), not a single "project_version → SchemeRun" pipeline helper. There is no `def run_full_pipeline(...)` or equivalent on the production side; the existing test pattern (`backend/tests/integration/test_production_archive_wiring_e2e_postgresql.py`) pre-seeds all upstream state via `_seed_all_prereqs(session)` (raw ORM `session.add` / `session.flush` / `session.commit`) and then calls `service.generate_production_scheme_run(cmd)` with a pre-built command.

**Conclusion**: the §2 single-call `execute_scenario(session_factory, scenario_id, project_input) -> AdapterResult` cannot be implemented without one of:

1. Hand-writing the upstream production state inside the adapter (raw ORM `session.add` of `OrchestrationIdentityRecord`, `OrchestrationAttemptRecord`, `CalculationRunRecord` × 5, `SourceBindingRecord`, `ApprovedWeightSetRevision`, etc.) — **violates Path A F-2 / F-3 / F-4 and pre-freeze §8 #2**.
2. Calling `_seed_all_prereqs` from inside the adapter — couples the adapter to a test helper (which lives in `backend/tests/integration/`, not in production source). Importing test helpers from production code is an architecture violation.
3. Mocking the production orchestrator — defeats the contract purpose.
4. Silently re-framing §2 to accept a pre-seeded `(source_binding_id, weight_set_revision_id, correlation_id, database_backend)` instead of `project_input` — honest, but **not** what §2 says; requires amendment.

(1), (2), (3) violate Path A design contract and pre-freeze §8 stop conditions. (4) is the only honest path.

### 13.2 The corrected surface (A1-2a)

This amendment ratifies the **A1-2a** option from the Slice A1 preflight report's §5. The adapter's input surface is changed as follows:

**Before** (original §2, now superseded):

```python
def execute_scenario(
    session_factory: Callable[[], Session],
    scenario_id: str,
    project_input: ProjectInput,
) -> AdapterResult:
    ...
```

**After** (corrected, A1-2a):

```python
def execute_scenario(
    session_factory: Callable[[], Session],
    *,
    source_binding_id: str,
    weight_set_revision_id: str,
    correlation_id: str,
    database_backend: str,
) -> AdapterResult:
    """
    Submit a pre-built GenerateProductionSchemeCommand to the
    production SchemeService and return the resulting SchemeRun
    + lineage. The adapter does NOT build the upstream
    OrchestrationIdentity / OrchestrationAttempt /
    CalculationRunRecord x 5 / ExecutionSnapshot /
    CoefficientContext / SourceBindingRecord /
    ApprovedWeightSetRevision state — that work is done by the
    upstream production orchestration (via
    compose_production_source_binding_use_case + the
    weight-set approval path) before this adapter is called.

    `source_binding_id` and `weight_set_revision_id` MUST
    reference pre-existing production rows that the caller
    has produced via the upstream production pipeline.
    `correlation_id` and `database_backend` are mandatory
    fields on GenerateProductionSchemeCommand (NOT-NULL
    columns, no Python default).
    """
    cmd = GenerateProductionSchemeCommand(
        source_binding_id=source_binding_id,
        weight_set_revision_id=weight_set_revision_id,
        profile_codes=("balanced",),  # or however the caller specifies
        correlation_id=correlation_id,
        database_backend=database_backend,
    )
    service = compose_production_scheme_service(session_factory)
    scheme_run = service.generate_production_scheme_run(cmd)
    # lineage extraction is read-only
    return AdapterResult(
        scheme_run=scheme_run,
        source_binding_id=scheme_run.source_binding_id,
        weight_set_revision_id=scheme_run.weight_set_revision_id,
        combined_source_hash=scheme_run.source_binding.combined_source_hash,
        review_required=scheme_run.requires_review,
        review_reasons=[...],
    )
```

**Field-level changes**:

| field | before (original §2) | after (Amendment 2, A1-2a) |
|---|---|---|
| `session_factory` | required | required (unchanged) |
| `scenario_id` | required (log correlation only) | **REMOVED** (was redundant; caller can include scenario_id in `correlation_id` if needed) |
| `project_input` | required | **REMOVED** (was incompatible with the actual production API) |
| `source_binding_id` | not in surface | **REQUIRED** (FK to pre-existing `SourceBindingRecord`) |
| `weight_set_revision_id` | not in surface | **REQUIRED** (FK to pre-existing `ApprovedWeightSetRevision`) |
| `correlation_id` | not in surface | **REQUIRED** (mandatory NOT-NULL on `GenerateProductionSchemeCommand`) |
| `database_backend` | not in surface | **REQUIRED** (mandatory NOT-NULL on `GenerateProductionSchemeCommand`; one of `"sqlite"` or `"postgresql"`) |

The output `AdapterResult` (re-shaped in §13.4 below) drops the `calculation_run_ids` field because the adapter no longer observes the 5 `CalculationRunRecord` rows directly — those are upstream of the `SchemeService` call. The adapter observes the `SchemeRun` row only.

### 13.3 Ownership boundary (explicit)

The adapter is responsible for:

- **Calling** `compose_production_scheme_service(session_factory)` to obtain a wired `ProductionSchemeService`.
- **Building** a `GenerateProductionSchemeCommand` from the inputs (`source_binding_id`, `weight_set_revision_id`, `correlation_id`, `database_backend`).
- **Invoking** `service.generate_production_scheme_run(cmd)`.
- **Reading** the resulting `SchemeRun` and extracting its `source_binding_id`, `weight_set_revision_id`, `combined_source_hash`, `requires_review`, and `review_reasons` (read-only).
- **Constructing** an `AdapterResult` typed dataclass with the read-only lineage.
- **Forwarding** any production exception unchanged to the caller.

The adapter is **not** responsible for:

- Creating a `ProjectVersion` row.
- Creating a `OrchestrationIdentityRecord` row.
- Creating a `OrchestrationAttemptRecord` row.
- Creating any `CalculationRunRecord` rows (the 5 stage calculations).
- Creating an `OrchestrationExecutionSnapshotRecord` row.
- Creating an `OrchestrationCoefficientContextRecord` row.
- Creating a `SourceBindingRecord` row.
- Creating an `ApprovedWeightSetRevision` row.
- Approving a weight-set revision.
- Resolving approved non-demo coefficients.
- Verifying the `SourceBinding` (the production orchestrator's `SourceBindingVerifier` does this).
- Selecting a `SchemeService` policy (the production orchestrator does this).
- Persisting any production row of any kind.

These responsibilities are **owned by the upstream production orchestration** (the existing production factories `compose_production_source_binding_use_case(...)` and the weight-set approval path) and are **out of scope** of this adapter.

This ownership boundary is **enforced by the adapter's API surface**: the adapter does not accept any input that would let it create production state. The only inputs are FK references to pre-existing production rows (plus the `correlation_id` and `database_backend` metadata). The adapter has no constructor parameters other than the `session_factory` and the typed command fields.

### 13.4 Corrected `AdapterResult`

The corrected `AdapterResult` typed dataclass (replacing the §2.2 version):

```python
@dataclass(frozen=True, slots=True)
class AdapterResult:
    """Read-only result of a single evaluation scenario execution.

    The adapter populates this from the production SchemeRun row;
    the evaluation harness writes it to the evaluation artifact
    (raw/normalized JSON). The adapter does NOT mutate the
    SchemeRun row in any way.
    """
    scheme_run: SchemeRun                # the production SchemeRun row
    source_binding_id: str               # FK to SourceBindingRecord
    weight_set_revision_id: str          # FK to ApprovedWeightSetRevision
    combined_source_hash: str | None     # from SourceBindingRecord.combined_source_hash
    review_required: bool                # from SchemeRun.requires_review
    review_reasons: tuple[str, ...]      # from SchemeRun.review_reasons
```

The `calculation_run_ids` field is **dropped** because the adapter no longer observes the 5 `CalculationRunRecord` rows directly. The evaluation harness can read these rows separately via the production read ports (e.g., `SqlAlchemySourceBindingReadPort`) if it needs to assert the §4.3 strict row counts; this is a separate concern from the adapter.

### 13.5 Corrected failure semantics (replacing §3 references to `project_input`)

- **Production raises**: the adapter forwards the exception unchanged. The evaluation harness records `outcome=failed` and the exception in the stage ledger.
- **Production returns `FAILED`**: the adapter returns the `SchemeRun` as-is. The evaluation harness records `outcome=failed`.
- **Production returns `REVIEW_REQUIRED`**: the adapter returns the `SchemeRun` as-is. The evaluation harness records `outcome=review_required`.
- **Production returns `SUCCEEDED`**: the adapter returns the `SchemeRun` as-is. The evaluation harness records `outcome=success`.
- **Adapter has no `EVAL_PRODUCTION_PIPELINE_PREREQUISITE_MISSING`**: that error class is forbidden (F-3). If the production orchestrator cannot execute, production raises its own error; the adapter forwards it.

The corrected semantics **do not change** the failure semantics from §3; this amendment only clarifies that the `project_input` failure modes (e.g., "project_input validation failed") are now **caller responsibilities**, not adapter responsibilities. The caller must validate the project input and pre-build the production state before calling the adapter.

### 13.6 Corrected acceptance test strategy (replacing §5)

The acceptance test strategy is updated as follows:

1. **`test_adapter_contract.py`** — same as before. The adapter's structural invariants (no `Session.add` / `session.flush` / `session.commit` / `bulk_insert_mappings`; no production-row writes; exception forwarding; `review_required` outcome translation) are unchanged.

2. **`test_path_a_baseline_sqlite.py`** — the test now **pre-seeds** the upstream production state via `_seed_all_prereqs`-style helpers (which the implementation round will factor out of `backend/tests/integration/test_production_scheme_postgresql.py` into a reusable test helper, e.g., `backend/tests/evaluation/_seed_helpers.py`) and then calls the adapter with the pre-seeded `source_binding_id` + `weight_set_revision_id`. The test asserts that the adapter:
   - calls `compose_production_scheme_service` exactly once
   - returns a `SchemeRun` with `scheme_status="SUCCEEDED"`
   - returns an `AdapterResult` whose `combined_source_hash` matches the production `build_source_snapshot_content_v1` helper's output
   - does NOT introduce any new production row beyond what the upstream `_seed_all_prereqs` already created (PK-set symmetric-difference test)
   - does NOT create `backend/src/cold_storage/evaluation/production_seeding.py` (assert the file does not exist on disk after the test runs)

3. **`test_path_a_baseline_postgresql.py`** — same shape as the SQLite test, against PostgreSQL.

4. **`test_path_a_no_pr21_pollution.py`** — same as before. Asserts no PR #21 forbidden patterns.

**Important**: the test helper that does the upstream pre-seeding (`_seed_all_prereqs`-style) lives in `backend/tests/evaluation/_seed_helpers.py` (or similar), **not** in `backend/src/cold_storage/evaluation/`. The adapter does not import this helper. The helper is test-only infrastructure that produces the production state needed to drive the adapter; the helper is not part of the adapter's API surface.

The adapter's API surface is **only** the `execute_scenario(...)` method. The helper is a test-side convenience.

### 13.7 Corrected implementation round authorization gates (replacing §10)

The implementation round's authorization must explicitly include:

- The contract freeze acceptance (this amendment, §13).
- The **expected source_binding_id + weight_set_revision_id** that the test will use (or the strategy for the test to produce them via the upstream pre-seeding helper).
- The expected output path (`backend/storage/...` or `backend/tests/evaluation/data/...`).
- The expected output comparison policy (or a freeze that the implementation round will pick).
- The expected output reviewer sign-off process.
- The implementation PR's branch name (candidate: `codex/task-11b-path-a-impl-slice-a1` re-resumed, or a new branch).
- The implementation PR's target (must be `main`).
- The implementation PR's expected diff size (<= 1000 LOC across all new files per Amendment 1 §11.5.1; if more is needed, that is a contract change requiring a new freeze).
- The 4-job CI green requirement (compose-config / frontend / backend-sqlite / backend-postgresql, with backend-postgresql including the §5 PostgreSQL acceptance test).
- **NEW for A1-2a**: the test-side `_seed_all_prereqs`-style helper's location (e.g., `backend/tests/evaluation/_seed_helpers.py`) and a freeze that the helper is test-only and is **not** imported from production code (the adapter does not depend on it).

### 13.8 What is **unchanged** by this amendment

- **All forbidden paths** (Path A F-1 through F-15, pre-freeze §8 stop conditions, Amendment 1 §11.6 implicit condition, the 16 Path A stop conditions S-1 through S-16) are unchanged. The amendment does not weaken any stop condition.
- **PR #21 relationship** (per §7) is unchanged: PR #21 is **not** an implementation base, **not** a code/test/expected-output/fixture/manifest/design-doc carryover, and the branch ref `7822581eeee4c590b4ed9b1e3c46c1cde5490098` is preserved untouched.
- **Expected output strategy** (per §6) is unchanged: regenerated under Charles reviewer sign-off, recorded in `docs/tasks/TASK-011B-path-a-expected-outputs-reviewer-sign-off.md`. The §8 #10 stop condition is binding.
- **The four acceptance test files** (per §5 / §13.6) are still required; only the SQLite and PostgreSQL tests are updated to pre-seed the upstream state.
- **Path A scope** (<= 1000 LOC, per Amendment 1 §11.5.1) is unchanged. The adapter itself is small (a thin wrapper around `compose_production_scheme_service` + `service.generate_production_scheme_run(cmd)`); the test-side pre-seeding helper is separate and is **not** counted against the adapter's LOC budget because the helper is not part of the adapter.

### 13.9 What is **deleted** by this amendment

The following false assumptions in the original §2 are **explicitly deleted**:

- "**`project_input` can directly drive full production execution**" — **DELETED**. The actual production API does not accept a `project_input`; it accepts a pre-built `GenerateProductionSchemeCommand` with FK references.
- "**The adapter internally completes Phase 2/3/4**" — **DELETED**. The adapter does not create any of the Phase 2/3/4 production state; that is upstream orchestration's responsibility.
- "**The adapter is a single-call entry point for a full pipeline**" — **DELETED**. The adapter is a single-call entry point for **only** the scheme-generation step of the production pipeline. The full pipeline is multi-step and the adapter is one of those steps.
- "**The adapter reads the 5 `CalculationRunRecord` IDs and forwards them in the `AdapterResult`**" — **DELETED**. The adapter no longer observes the 5 `CalculationRunRecord` rows directly; the `calculation_run_ids` field is removed from `AdapterResult`.
- "**The §2 single-call `execute_scenario(session_factory, scenario_id, project_input) -> AdapterResult` is the canonical adapter surface**" — **DELETED**. The canonical adapter surface is now `execute_scenario(session_factory, *, source_binding_id, weight_set_revision_id, correlation_id, database_backend) -> AdapterResult` (A1-2a).

### 13.10 Why A1-2a was chosen over A1-2b / A1-2c

The Slice A1 preflight round enumerated three options:

- **A1-2a**: adapter takes `(source_binding_id, weight_set_revision_id, correlation_id, database_backend)`. Caller runs the Phase 2/3/4 pipeline upstream.
- **A1-2b**: adapter takes `(project_input)` and runs the full pipeline internally. Thousands of LOC, exceeds Path A's <= 1000 LOC budget.
- **A1-2c**: adapter takes `ProjectVersionRecord` and runs the rest internally. Same as A1-2b but smaller (the project_version creation is the only thing skipped). Still exceeds 1000 LOC.

A1-2a was chosen because:

1. **It fits the <= 1000 LOC Path A budget.** The adapter is a thin wrapper (~30-50 LOC) around `compose_production_scheme_service` + `service.generate_production_scheme_run(cmd)`. The upstream pipeline is reused from existing production factories; the adapter does not re-implement it.
2. **It reuses existing production code.** The Phase 2/3/4 pipeline is already in production (`compose_production_source_binding_use_case`, the weight-set approval path, `ProductionSchemeService`). Path A does not invent a new pipeline; it consumes the existing one.
3. **It does not violate any forbidden path.** The adapter does not create production state. The adapter does not bypass `SourceBindingVerifier`, `SchemeService`, or the production orchestrator. The adapter does not import evaluation code into production modules.
4. **It matches the production-side composition pattern.** The existing tests already pre-seed the upstream state and call `service.generate_production_scheme_run(cmd)` directly. A1-2a makes the adapter an explicit, named, tested wrapper around this established pattern.
5. **It allows the adapter to be implemented in <= 1000 LOC across source + tests + helper.** The adapter module is small; the test-side pre-seeding helper is separate and is not part of the adapter's LOC budget (per §13.8).

A1-2b and A1-2c were rejected because they would re-implement the Phase 2/3/4 pipeline inside the adapter, exceeding the Path A budget and increasing the risk of forbidden-path violations.

### 13.11 Status after Amendment 2

- The Path A design contract is amended. The original §2 (and the false assumptions in §2.4 "Why this shape") are **superseded** by §13. The remaining sections (§1, §3, §4, §5, §6, §7, §8, §9) are unchanged except where they cross-reference §2; those cross-references now point to §13.
- Task 11 Phase B implementation **remains NOT resumed**. No code has been authored against `main` in this round. No implementation begins until Charles freezes this amendment and authorizes a follow-up `Implementation Slice A1` round.
- PR #21 is **not** touched. Its head SHA `7822581eeee4c590b4ed9b1e3c46c1cde5490098` is preserved.
- Issue #35 is **not** touched. Its closed / completed state is preserved.
- The implementation branch `codex/task-11b-path-a-impl-slice-a1` from `main @ 184463138e54d23b57ef961130edf78b61e8f36c` (created in the Slice A1 preflight round, with **0 commits**) is preserved as a reference branch; this amendment does not modify it.
- The amendment branch `codex/task-11b-path-a-amendment-2` is created at `main @ 184463138e54d23b57ef961130edf78b61e8f36c` with one docs-only commit (this amendment) and is **not** pushed and **not** opened as a PR.
- Charles's next step is to ratify this amendment and authorize a follow-up `Implementation Slice A1` round (the same round that previously STOP'd at preflight, now with the corrected contract surface).

---

## 14. Amendment 3 — Phase-B orchestration boundary narrow carve-out

### 14.1 Discovery (from PR #60 remote-grounded reconstruction round, 2026-07-10)

PR #60 head `2b9e04566dc65ac66a7ccfa2eccd236b0b6b8314` (commit
message: "fix(task-011b): restore frozen scope and correct runner
boundaries") introduced a `call_via_markers(...)` indirection
wrapper inside `adapter.py` to keep the runner from carrying the
Phase-1 ORM column tokens (`correlation_id` / `database_backend`)
as literal kwarg names. The PR body self-reported this helper as
"architecture-test evasion" — the runner was being kept
artificially separate from the A1-2a contract surface via
marker-name indirection.

Charles authorized the remote-grounded reconstruction round
(`AUTHORIZE_TASK011B_AMENDMENT3_REMOTE_GROUNDED_RECONSTRUCTION`)
to:
1. Remove the `call_via_markers` workaround.
2. Restore the runner to call `adapter.execute_scenario(...)`
   directly under the canonical A1-2a kwarg names.
3. Allow `execute.py` (the Phase-B orchestration boundary) to
   carry the A1-2a contract token names on its public surface
   as a 1-file narrow carve-out (not a 6-file broad carve-out).
4. Preserve the adapter's frozen base surface (the diff between
   the amended `adapter.py` and the frozen base SHA `9459e6532`
   must be empty).

### 14.2 The 1-file narrow architecture-boundary carve-out (only `execute.py`)

This amendment ratifies a **1-file narrow carve-out** for the
A1-2a contract token names. The carve-out is:

- **Path-precise**: only `backend/src/cold_storage/evaluation/execute.py` is exempted. All other evaluation files (`errors.py` / `run_directory.py` / `cli.py` / `__init__.py` / test files / seed helpers) remain subject to the original Phase-1 field ban.
- **Token-precise**: only `correlation_id` and `database_backend` are exempted. All other Phase-1 tokens (`idempotency_key`, `actor_principal_type`, `scheme_run_id`, `frozen_envelope`) remain banned in **all** evaluation files.
- **Does NOT allow** `project_input`, `scenario_id`, or `calculation_run_ids` in any evaluation file.
- **Does NOT weaken** the `production_seeding` / `OrchestrationRunAttemptRecord` / `SchemeRunRecord` / raw ORM / production-row fabrication defences.

The amendment does **NOT** restore the prior 6-file broad carve-out. Per Charles's "no carve-out re-expansion" rule, the carve-out is the strict 1-file narrow form.

### 14.3 The corrected runner public surface (canonical A1-2a kwargs)

The Phase-B runner (`execute.py::run_scenario`) is restored to the canonical A1-2a input contract:

```python
def run_scenario(
    session_factory: Callable[[], Session],
    *,
    source_binding_id: str,
    weight_set_revision_id: str,
    correlation_id: str,
    database_backend: str,
) -> ScenarioOutcome:
    """Run a single evaluation scenario against the production
    scheme pipeline. Validates the A1-2a input contract at the
    entry boundary and forwards the canonical A1-2a kwarg names
    to ``adapter.execute_scenario(...)``.

    The runner does NOT import any production ORM / repository /
    production persistence internals; it only validates inputs
    and maps the production-side ``SchemeRun.status`` to a typed
    ``Outcome`` literal.
    """
    ...
```

The runner delegates to `adapter.execute_scenario(...)` directly, **not** via any indirection wrapper. The `call_via_markers` helper is removed from `adapter.py` and from `adapter.__all__`. The `adapter.py` final state restores the frozen base surface (diff vs frozen base SHA `9459e6532fcd5cfe728bf326b92557b0e082faf8` is empty).

### 14.4 The run-directory marker-name boundary

The run-directory helper (`run_directory.py::execute_in_run_directory`) is forbidden by §14.2 to hold the A1-2a contract token names on its public surface. To accommodate this, `execute.py` (the Phase-B orchestration boundary) exposes a marker-named thin wrapper `run_scenario_via_markers` that:

- Accepts `correlation_marker` / `backend_marker` (the run-directory helper's marker names) on its public surface.
- Maps the marker names to the canonical A1-2a contract kwarg names (`correlation_id` / `database_backend`) at the runner boundary.
- Forwards to `run_scenario` (the canonical A1-2a surface) under the canonical A1-2a contract kwarg names.

The run-directory helper therefore calls `run_scenario_via_markers(correlation_marker=..., backend_marker=...)` and does **not** retain the A1-2a token names on its public surface. The mapping from marker names to A1-2a contract kwarg names happens **only** inside `execute.py`. The CLI similarly uses marker-named argparse flags (`--correlation-marker` / `--backend-marker`) and does **not** retain the A1-2a token names on its public surface.

This marker-name boundary is the implementation mechanism that allows `run_directory.py` and `cli.py` to remain compliant with the 1-file narrow carve-out (they pass marker names through to the runner boundary, where the mapping to the A1-2a contract kwarg names occurs).

### 14.5 Ownership boundary (explicit, restated)

The Phase-B runner (`execute.py`) is responsible for:

- **Validating** the A1-2a input contract at the entry boundary (typed errors: `InvalidEvaluationScenarioError` on boundary violations).
- **Calling** `adapter.execute_scenario(session_factory, *, source_binding_id, weight_set_revision_id, correlation_id, database_backend)` — direct call, not via any indirection wrapper.
- **Mapping** the production-side `SchemeRun.status` (canonical: `"completed"` / `"review_required"` / `"failed"` / `"running"` / `"pending"`) to a typed `Outcome` literal (`SUCCEEDED` / `REVIEW_REQUIRED` / `FAILED` / `BLOCKED_HISTORICAL`).
- **Mapping** documented historical-blocked upstream errors (`MISSING_APPROVED_COEFFICIENT`, `SCHEMA_MIGRATION_MISSING`, `WEIGHT_REVISION_NOT_APPROVED`, `IDENTITY_FINGERPRINT_STALE`) to `PhaseBBlockedError`.

The runner does **not**:

- Bypass production pathways (`adapter.execute_scenario` is always called).
- Write any production row (raw ORM inserts of `OrchestrationIdentityRecord` / `OrchestrationRunAttemptRecord` / `SchemeRunRecord` etc. are forbidden).
- Raise `PhaseBBlockedError` on the happy path.
- Expose any field beyond the A1-2a input contract (no `profile_codes`, no `scenario_id`, no `project_input`).
- Call the adapter via any indirection wrapper (`call_via_markers` / marker-named kwargs / etc.).
- Call any production ORM / repository / production persistence internals directly (e.g., `compose_production_scheme_service`, `GenerateProductionSchemeCommand`). The runner is a thin wrapper around `adapter.execute_scenario`; the production service composition and command construction is delegated to the adapter.

### 14.6 `profile_codes` exposure cleanup

The `profile_codes` parameter is **removed** from the runner's public surface:

- `execute.py::run_scenario(...)` — `profile_codes: tuple[str, ...] = ("balanced",)` **removed** from the function signature. The runner passes `profile_codes=("balanced",)` as an internal literal to `adapter.execute_scenario(...)` (which constructs the production `GenerateProductionSchemeCommand` internally).
- `cli.py` — no `--profile-codes` CLI flag is exposed.
- `tests/evaluation/test_*.py` — all `profile_codes=...` kwarg invocations to `run_scenario` are **removed**; tests assert the runner rejects arbitrary `profile_codes` (defense-in-depth: the runner does not even accept the kwarg, so attempting to pass one raises `TypeError` at the function-call boundary).

The `profile_codes=("balanced",)` decision remains an internal literal in `adapter.py::execute_scenario` and is **not** exposed to the runner, CLI, or callers. The runner's public surface is exactly the A1-2a contract.

### 14.7 What is **unchanged** by this amendment

- The A1-2a adapter surface (`execute_scenario(session_factory, *, source_binding_id, weight_set_revision_id, correlation_id, database_backend) -> AdapterResult`) is unchanged.
- The A1-2a `AdapterResult` typed dataclass is unchanged.
- The typed error surface (`EvaluationRunnerError`, `PhaseBBlockedError`, `InvalidEvaluationScenarioError`, `EvaluationRunnerContractViolationError`) is unchanged.
- The acceptance tests (`test_sqlite_acceptance.py`, `test_postgresql_acceptance.py`, `test_cli.py`, `test_fixture_consistency.py`) are unchanged in scope (only `correlation_marker` / `backend_marker` → `correlation_id` / `database_backend` kwarg migrations, plus the new defense-in-depth `test_runner_does_not_accept_profile_codes_kwarg` test).
- The forbidden-path defences (`production_seeding`, `OrchestrationRunAttemptRecord`, `SchemeRunRecord`, raw ORM, production-row fabrication, `project_input`, `scenario_id`, `calculation_run_ids`) are unchanged.
- The pre-freeze stop conditions (§8), Path A stop conditions (S-1 through S-16), and Amendment 1 §11.6 implicit condition are unchanged.
- The adapter's frozen base surface: the diff between the amended `adapter.py` and the frozen base SHA `9459e6532fcd5cfe728bf326b92557b0e082faf8` is **empty**. The `call_via_markers` workaround is removed; the adapter's public API is restored to the single entry point `execute_scenario`.

### 14.8 What is **deleted** by this amendment

- **`call_via_markers` indirection wrapper** (the prior PR head's "architecture-test evasion" helper) — removed from `adapter.py` and from `adapter.__all__`.
- **`profile_codes` parameter** from `run_scenario` public surface.
- Any other marker-name indirection wrapper in the evaluation layer.

### 14.9 Status after Amendment 3

- The Path A design contract is amended. The 1-file narrow architecture-boundary carve-out is now formally documented in §14.2. The runner public surface is restored to the canonical A1-2a contract (§14.3). The run-directory marker-name boundary is the implementation mechanism for the 1-file narrow carve-out (§14.4).
- The Phase B implementation slice (`codex/task-11b-phase-b-resumption-from-main`) is amended in-place on a new branch `codex/task-11b-amendment3-reconcile` (remote-grounded worktree from PR #60 head `2b9e04566`). The amendment is built up file-by-file (NOT cherry-picked from the prior isolated local commit `4ed6707`):
  - `backend/src/cold_storage/evaluation/adapter.py` — `call_via_markers` removed; `__all__` restored to `{AdapterInputError, AdapterResult, execute_scenario}`; final state matches frozen base.
  - `backend/src/cold_storage/evaluation/execute.py` — restored to direct call of `adapter.execute_scenario(...)`; profile_codes removed; `run_scenario_via_markers` added as the marker-name boundary for the run-directory helper.
  - `backend/src/cold_storage/evaluation/run_directory.py` — uses `run_scenario_via_markers` (marker-named entry point) instead of holding the A1-2a token names on its own public surface.
  - `backend/src/cold_storage/evaluation/cli.py` — uses marker-named argparse flags; does not hold the A1-2a token names on its public surface.
  - `backend/tests/architecture/test_phase1_identity_foundation_boundary.py` — 1-file narrow carve-out for `execute.py` added (path-precise + token-precise); original 1-file adapter carve-out (A1-2a) preserved.
  - `backend/tests/evaluation/test_*.py` — `correlation_marker` / `backend_marker` migrated to `correlation_id` / `database_backend`; defense-in-depth `test_runner_does_not_accept_profile_codes_kwarg` added.
- PR #60 remains **Draft**. Ready and Merge are **NOT** authorized in this round.
- The amendment is **NOT** expected-output authoring. Expected outputs remain separately unauthorized.
- The amendment is a regular fast-forward commit on top of the PR head `2b9e04566`; it is **NOT** a force-push.

---

## 15. Amendment 4 — Expected-output contract freeze

**Round authorization**: `AUTHORIZE_TASK011B_EXPECTED_OUTPUT_CONTRACT_FREEZE_AMENDMENT_4` (2026-07-10).
**Base SHA**: PR #60 head `6cecdc1e214abd4742ec55a8cb23b69eebcbe50a` (Amendment 3 reconciliation head).
**Scope**: design-contract freeze only. This amendment does NOT author, commit, or push expected-output JSON. Expected outputs remain separately unauthorized.

### 15.1 Tracked expected-output path

The tracked expected-output path is **frozen at**:

```
backend/tests/evaluation/data/expected/
```

The following paths are **forbidden** for the expected-output fixture location:

- `evaluation/expected/` (matches the top-level `.gitignore` rule that excludes the **entire** `evaluation/` tree from version control, per pre-freeze contract §5.4 and §6.5 above).
- `backend/src/cold_storage/evaluation/expected/` (lives inside a tracked source-code package; would conflate evaluation-source with evaluation-test-data).
- `backend/storage/evaluation_runs/<runtime-id>/expected/` (lives in a runtime artifact directory; not stable across re-runs).

Rationale for `backend/tests/evaluation/data/expected/`:

- **Tracked by git** (not in `.gitignore`).
- **Lives outside the source-code package** (`backend/src/cold_storage/`).
- **Lives outside any runtime artifact directory** (not under `backend/storage/`).
- **Does not collide with the existing `evaluation/` ignore rule** (the new path is under `backend/tests/evaluation/data/expected/`, not under the top-level `evaluation/`).
- **Is co-located with the consuming tests** (`backend/tests/evaluation/test_*acceptance*.py`), making the path convention self-documenting.

This resolves the §6.5 ambiguity ("The exact path is up to the implementation round, subject to Charles's review.") by explicitly ratifying the implementation path.

### 15.2 Scenario set

The expected-output scenario set is **frozen at exactly two scenarios**:

| File | Scenario ID | Correlation ID |
|---|---|---|
| `baseline_feasible.v1.json` | `baseline_feasible` | `test-a15-baseline-001` |
| `high_throughput_review.v1.json` | `high_throughput_review` | `test-a15-high-throughput-001` |

The following are **forbidden** in this round:

- Carrying over any PR #21 fixture.
- Using `transaction_b_cross_backend_v1.json` (Task 11A cross-backend integration test golden, which is a **different scenario at a different scale** — 2 zones / 350 kW / 12.5 M CNY / 6 equipment rows — NOT interchangeable with the A1 acceptance-test scenario of 1 zone / 25 kW / 6 M CNY / 0 equipment rows).
- Adding a third scenario not defined in this amendment.
- Treating a repeat run as an independent golden. Repeat runs are **only** for determinism verification (§15.8); they are NOT expected outputs.

### 15.3 Canonical expected-output schema

Each expected JSON file MUST contain (at minimum) the following top-level keys:

| Key | Type | Purpose |
|---|---|---|
| `schema_version` | string (semver) | Format version (frozen at `task11b-expected-output.v1` for this round). |
| `scenario_id` | string (frozen set) | One of `baseline_feasible` / `high_throughput_review`. |
| `expected_outcome` | string enum | `SUCCEEDED` / `FAILED` / `REVIEW_REQUIRED`. |
| `scheme_status` | string enum | `pending` / `completed` / `failed` / `review_required`. |
| `combined_source_hash` | 64-hex sha256 | The frozen production path's `combined_source_hash` (already cross-backend normalized). |
| `review_required` | bool | Whether production flagged the result for review. |
| `review_reasons` | string[] | Ordered list of review reason codes. |
| `source_binding_proxy` | string (semantic ID) | The semantic `SourceBindingRecord.id` (e.g. `a1-test-binding-001`). |
| `weight_set_revision_proxy` | string (semantic ID) | The semantic `SchemeWeightSetRevisionRecord.id` (e.g. `a1-test-wrev-001`). |
| `stage_ledger` | string[] (ordered) | The ordered list of canonical stage names. Frozen at `["zone", "cooling_load", "equipment", "power", "investment"]`. |
| `production_outputs` | object | The full `input_snapshot` from `SchemeRun_entity` (zone_results, cooling_load_result, equipment_result, power_result, investment_result, source_calculation_ids, source_snapshot_hashes). |
| `constraint_check_summary` | object | `{expected_passed_count, expected_failed_count, expected_failed_code}`. |
| `content_hash` | 64-hex sha256 | The `SchemeRun_entity.content_hash` (cross-backend normalized). |
| `_comparison_policy` | object | Self-documenting comparison policy (see §15.4, §15.5, §15.6). |

**Forbidden keys** in the expected JSON (per §15.6 stable-proxies rule):

- `scheme_run.id` (UUID4 random per `default_factory=_uuid`).
- Any UUID4.
- `created_at` / `updated_at` / `completed_at` (wall-clock variance).
- Any database-generated integer primary key (SQLite rowid, PostgreSQL `bigserial`).
- Runtime run-directory names.
- Temporary labels.
- Absolute filesystem paths.

### 15.4 Exact-match fields

The following fields MUST be **exact-string-equal** between the captured run and the expected JSON:

- `schema_version`
- `scenario_id`
- `expected_outcome`
- `scheme_status`
- `combined_source_hash`
- `review_required`
- `review_reasons` (compared as a list; order-sensitive)
- `stage_ledger` (compared as an ordered list; order-sensitive)
- `stage_ledger` stage names (each string is exact-equal)
- `content_hash`
- `source_snapshot_hash`
- All decimal / monetary values (compared as canonical decimal strings, NOT floats)
- All deterministic categorical output fields (scheme_code, profile_code, room_code, temperature_level, etc.)
- All canonical object keys
- All canonical list orders

Comparison implementation MUST NOT use:

- Fuzzy global tolerance
- String truncation to hide differences
- "Skip if can't compare" (any un-typed field is a STOP condition per §15.10)
- Manual rewriting of production output to match golden (forbidden by §15.5)

### 15.5 Numeric comparison

Decimal and monetary values are normalized as **canonical decimal strings** (per the domain `canonical_json_bytes` rule that rejects binary `float`). Comparison is exact-string-equal after canonicalization.

Float-derived engineering values are compared after the **production-defined quantization**:

- `partition_length_proxy_m = 28.28427124746190097603377448` is treated as exact-string-equal because production's serialization normalizes the Decimal.
- If production has no quantization contract, the comparison MUST freeze an explicit absolute tolerance AND relative tolerance per field family.

**Forbidden comparison methods**:

- Fuzzy global tolerance (e.g. "all floats within 1e-6").
- String truncation to hide differences (e.g. slicing to 6 decimal places).
- Ignoring all numerical values (i.e. a contract with zero numerical assertions).
- Hand-rewriting production output to match golden.

The complete per-field numerical comparison policy is enumerated in each expected JSON's `_comparison_policy.exact_match_fields` array.

### 15.6 Stable proxies

Database-generated IDs MUST be replaced by **re-derivable stable proxies**:

| Production field | Stable proxy |
|---|---|
| `scheme_run.id` (UUID4) | (omitted from expected JSON; replaced by `content_hash`) |
| `SchemeRunRecord.id` (DB PK) | (omitted; replaced by `combined_source_hash`) |
| `SourceBindingRecord.id` (semantic) | `source_binding_proxy` (kept verbatim — semantic IDs ARE stable) |
| `SchemeWeightSetRevisionRecord.id` (semantic) | `weight_set_revision_proxy` (kept verbatim) |
| `Project.id` (semantic) | `project_id` (kept verbatim) |
| `ProjectVersion.id` (semantic) | `project_version_id` (kept verbatim) |
| `CalculationRunRecord.id` (semantic) | `production_outputs.source_calculation_ids.{stage}` (kept verbatim per stage) |
| Timestamps | (omitted; replaced by `source_snapshot_hash` for input + `content_hash` for output) |

Forbidden proxy sources:

- SQLite integer primary key (rowid)
- PostgreSQL `bigserial` PK
- UUID4 (anywhere)
- Wall-clock timestamps
- Process IDs
- OS random values

### 15.7 Cross-backend capture (independent execution per backend)

SQLite and PostgreSQL captures MUST be executed independently:

```
/tmp/task011b-expected-output-amendment4/sqlite/
├── baseline_feasible.run1.json
├── baseline_feasible.run2.json
├── high_throughput_review.run1.json
└── high_throughput_review.run2.json

/tmp/task011b-expected-output-amendment4/postgresql/
├── baseline_feasible.run1.json
├── baseline_feasible.run2.json
├── high_throughput_review.run1.json
└── high_throughput_review.run2.json
```

Each backend MUST capture from the **acceptance-test execution path** (i.e. via the `a1_engine` / `a1_session_factory` fixtures for SQLite, and via the `a2_pg_engine` / `a2_pg_session_factory` fixtures for PostgreSQL).

**Forbidden capture methods**:

- Manual invocation of the production service (e.g. calling `compose_production_scheme_service` directly).
- Mocks, stubs, fakes, in-memory stand-ins for the production path.
- Copying a capture from one backend to the other.
- Using a stale run artifact from a prior round.
- Skipping the PostgreSQL capture and claiming "cross-backend verified" (the PostgreSQL capture MUST run against a real PostgreSQL service).

**Verified in this round**: PostgreSQL 14.23 is up at `127.0.0.1:5432` with a `cold_storage` superuser. Both backends captured 8 / 8 PASS via the real acceptance-test execution path.

### 15.8 Determinism verification (per scenario, per backend, ≥2 runs)

For each scenario × backend combination, **at least 2 runs MUST be executed** and compared field-by-field.

The diff classification MUST be one of three classes:

| Class | Meaning | Action |
|---|---|---|
| `EXACT_STABLE` | Zero diffs between run N and run N+1. | Production path is fully deterministic. |
| `NORMALIZED_STABLE` | Diffs exist only in `_meta` (id, run_idx, created_at, completed_at) or in `database_backend` (cross-backend echo). | Production path is content-deterministic; `_meta` and `database_backend` are excluded from comparison per §15.6. |
| `NONDETERMINISTIC_EXCLUDED` | Substantive content diffs (snapshots, hashes, candidates, constraint_results, etc.). | **STOP condition per §15.10**; the production path has a real non-determinism bug. |

The report MUST enumerate each diff **per JSON path** (e.g. `root._meta.scheme_run_id`, `root.SchemeRun_entity.completed_at`), not just summary statistics like "4 expected diffs, 0 substantive diffs". The §15.8 field-by-field enumeration is the **primary evidence**; summary statistics are a derived view.

**Verified in this round**:

| (backend, scenario) | Diff class | Total diffs | Substantive diffs |
|---|---|---|---|
| (sqlite, baseline_feasible) | `NORMALIZED_STABLE` | 4 | 0 |
| (sqlite, high_throughput_review) | `NORMALIZED_STABLE` | 4 | 0 |
| (postgresql, baseline_feasible) | `NORMALIZED_STABLE` | 4 | 0 |
| (postgresql, high_throughput_review) | `NORMALIZED_STABLE` | 4 | 0 |

Per-path enumeration (all 4 captures, 4 paths each = 16 paths total, all of them in `_meta` or `database_backend`):

| Path | Variance type |
|---|---|
| `root._meta.scheme_run_id` | UUID4 random per `_uuid` factory |
| `root._meta.run_idx` | Test-side label (1 vs 2) |
| `root._meta.created_at` | Wall-clock |
| `root._meta.completed_at` | Wall-clock |
| `root.SchemeRun_entity.database_backend` | Cross-backend echo (intentional, excluded per §15.6) |

**Cross-backend identity (substantive content)**:

| Scenario | sqlite canonical SHA-256 | postgresql canonical SHA-256 | Match? |
|---|---|---|---|
| `baseline_feasible` | `d6775a7954d4699f51a678ccc84412ef...` | `d6775a7954d4699f51a678ccc84412ef...` | **YES** |
| `high_throughput_review` | `a326a54bdb8283f4f667195bb30a2a70...` | `a326a54bdb8283f4f667195bb30a2a70...` | **YES** |

Both backends produce **byte-identical canonical content** (after stripping `_meta` and `database_backend` echo). The production path's hashing is already cross-backend normalized — `combined_source_hash`, `source_snapshot_hash`, and `content_hash` are identical across SQLite and PostgreSQL for the same scenario inputs.

### 15.9 Reviewer sign-off sequencing

The following order is **frozen** for the future expected-output commit round:

1. Generate un-committed candidate expected files (in `/tmp/task011b-expected-output-amendment4/proposed_expected/`, NOT in the tracked path).
2. Record the SHA-256 of each candidate file.
3. Charles reviews the candidate content and the comparison policy.
4. Charles explicitly issues the authorization string: `AUTHORIZE_TASK011B_EXPECTED_OUTPUT_CANDIDATE_COMMIT`.
5. The expected-output candidate files become a **separate local commit** (NOT a force-push; the docs-only commit from this Amendment 4 round is the previous head on the branch).
6. Record the candidate commit SHA.
7. Create `docs/tasks/TASK-011B-path-a-expected-outputs-reviewer-sign-off.md`.
8. The sign-off document MUST reference:
   - The implementation head SHA at the time of sign-off (NOT the current docs-only head — see #5).
   - The candidate commit SHA.
   - Each expected file's SHA-256.
   - The scenario set.
   - The comparison policy.
   - Charles's verdict.
9. The sign-off commit and the candidate commit are pushed together via regular fast-forward to `origin/codex/task-11b-phase-b-resumption-from-main`.
10. After CI 4 / 4 green, Ready can be considered (in a separate, explicitly authorized round).

This sequencing resolves the chicken-and-egg problem where:

- The sign-off document must reference the expected-output commit SHA.
- The expected-output commit cannot be pushed without Charles's sign-off.

The resolution is: the sign-off document is created AFTER the expected-output commit exists locally but BEFORE the push. The push bundles both commits. The sign-off document references the expected-output commit SHA **at the time of authoring**, which is stable from the moment of authoring through the push.

### 15.10 Stop conditions

If **any** of the following is observed, this amendment is **incomplete** and the round is **stopped**:

1. **SQLite / PostgreSQL substantive output divergence**: any diff beyond `_meta` / `database_backend` between two captures of the same (backend, scenario, run-equivalent). This would indicate a real production-path non-determinism bug.
2. **PostgreSQL capture skipped**: any test or capture claiming to be "cross-backend verified" without running against a real PostgreSQL service.
3. **Production numerical result non-deterministic**: a Decimal / monetary / float-derived engineering value differing between two runs of the same (backend, scenario).
4. **Comparison policy cannot explain a field**: any production output field that is not covered by `_comparison_policy.exact_match_fields` or a documented tolerance band.
5. **Need to modify the production formula** to make a capture match an expected value.
6. **Need to modify the adapter contract** (`adapter.execute_scenario` surface, `AdapterResult` schema, etc.) to make a capture match.
7. **Need `production_seeding.py`** (resurrecting the deleted file is forbidden by §5.1 and the pre-freeze contract).
8. **Need to copy a PR #21 fixture** (forbidden by §7.1).
9. **Need to ignore all numerical values** (forbidden by §15.5; expected outputs MUST have meaningful numerical assertions).
10. **Candidate expected output contains UUID / timestamp / generated PK** (forbidden by §15.6).

**None of these conditions were triggered in this round.** All 8 captures completed without STOP.

---

## 16. Amendment 5 — Expected-output tracking and scenario semantics correction

### 16.1 Correct the Amendment 4 path assertion (§15.1 contradiction)

Amendment 4 §15.1 / §6.5 (line 388-393) stated that the expected-output path
`backend/tests/evaluation/data/expected/`
was tracked by git. **This was incorrect.** The actual existing
`.gitignore` rule reads:

```
backend/tests/evaluation/*
!backend/tests/evaluation/__init__.py
!backend/tests/evaluation/test_path_a_adapter.py
!backend/tests/evaluation/_seed_helpers.py
```

The rule excludes the entire `backend/tests/evaluation/*` subtree
(including `data/expected/`), allowing only the four files explicitly
re-included by `!` lines. The path that Amendment 4 asserted as
"tracked by git" is **NOT** tracked; `git add -A` silently skips both
candidate JSON files. The current feasible ways to land the candidate
files in the repo are:

- `git add -f` (forced addition; bypasses `.gitignore` at the
  per-path level), or
- Re-anchor the candidate path to a tracked location via a
  `.gitignore` whitelist amendment.

Amendment 5 ratifies the **gitignore whitelist approach** as the
future-correct fix, because it preserves the production-side
invariant that "expected outputs are reproducible from a fresh
clone" without requiring `-f` on every commit. `git add -f` is
**FORBIDDEN** for any future expected-output commit (it is a
workaround that masks the underlying rule mismatch and renders
`.gitignore` non-authoritative).

The exact future `.gitignore` whitelist (frozen by this amendment,
to be added in the future implementation round) is:

```
!backend/tests/evaluation/data/
backend/tests/evaluation/data/*
!backend/tests/evaluation/data/expected/
backend/tests/evaluation/data/expected/*
!backend/tests/evaluation/data/expected/baseline_feasible.v1.json
# Superseded by §16.9.2 corrective addendum. The future implementation
# round MUST un-ignore ONLY `baseline_feasible.v1.json`. The
# `high_throughput_review.v1.json` line is intentionally absent
# because `high_throughput_review` is not part of the current
# expected-output set (see §16.9.1).
```

This is **path-precise** — only the two freeze-listed files are
un-ignored; other paths under `backend/tests/evaluation/data/` remain
ignored. The whitelist is the minimum-set necessary to make the §15
contract assertion true.

`git add -f` IS FORBIDDEN for future expected-output commits. Expected
output files MUST be trackable through normal Git behavior after the
whitelist is implemented.

### 16.2 Correct the scenario semantics assumption (§15.2)

Amendment 4 §15.2 (table at lines 964-967) froze two scenarios
(`baseline_feasible` and `high_throughput_review`) as independent
expected-output scenarios, **without independently verifying that the
two scenarios produce independent substantive production state**.
The current repository facts are:

- Both scenarios call the same `seed_a1_all_prereqs(session)`.
- Both scenarios use the same `SOURCE_BINDING_ID
  = "a1-test-binding-001"`.
- Both scenarios use the same `WEIGHT_REVISION_ID
  = "a1-test-wrev-001"`.
- Both scenarios use the same five `CalculationRunRecord` rows
  (`ZONE_RUN_ID`, `COOL_RUN_ID`, `EQUIP_RUN_ID`, `POWER_RUN_ID`,
  `INVEST_RUN_ID`).
- Only the `correlation_id` differs between the two scenarios.
- The current 8-run capture (4 SQLite + 4 PostgreSQL, run1/run2)
  yields byte-identical canonical content (post-strip
  `_meta` + `database_backend`) for both scenarios. The only
  cross-scenario byte difference is the `content_hash` (which
  incorporates `correlation_id` into the hash domain).

**State that correlation ID alone does not create an independent
expected-output scenario.** A scenario is independent iff it differs
from other scenarios in all of: semantic input identity, at least one
substantive input value, at least one production output or
constraint result, and canonical content hash (per §16.5). Two
expected-output files that share their semantic inputs and
substantive outputs but differ only in correlation ID are the **same
scenario**, not two scenarios.

The §15.2 design-intent ("two scenarios") was correct in intent
(`baseline_feasible` is the canonical feasible baseline;
`high_throughput_review` was meant to be a genuinely distinct
production scenario exercising different inputs) but the §15.2
implementation (`seed_a1_all_prereqs(session) + execute_scenario
with correlation_id differing only`) does not achieve the intent
under the current frozen `_seed_helpers.py`.

### 16.3 Freeze `baseline_feasible` semantics

`baseline_feasible` continues to use the existing A1 baseline state:

- Canonical feasible baseline (1 zone / 25 kW cooling / 6 M CNY /
  0 equipment_rows / 30 pallet positions / 10000 kg / day /
  15000 kg storage).
- Real production execution via the A1-2a adapter surface
  (`adapter.execute_scenario`) against the pre-existing production
  context seeded by `seed_a1_all_prereqs`.
- Stable cross-backend output (byte-identical canonical content
  for SQLite and PostgreSQL after stripping `_meta` and
  `database_backend`).
- No fabricated review state — `requires_review = False` is
  capture-derived (all five `CalculationRunRecord.requires_review`
  flags are `False`).

Its existing corrected v2 candidate may be retained as a local
reference (under `/tmp/` or `/root/`), but remains uncommitted and
unsigned pending a future implementation round that contains the
expected-output commit + sign-off.

### 16.4 High-throughput feasibility audit (read-only)

**Methodology**: A read-only feasibility probe was performed in
`/tmp/task011b-amendment5/probe2_variant.py`. The probe
**imported** `backend/tests/evaluation/_seed_helpers.py` as an
imported module and **monkey-patched** the module-level attributes
`_SLOT_RESULTS`, `ZONE_RESULT_SNAPSHOT`, `COOLING_RESULT_SNAPSHOT`,
`EQUIPMENT_RESULT_SNAPSHOT`, `POWER_RESULT_SNAPSHOT`, and
`INVESTMENT_RESULT_SNAPSHOT` in-process **only** (the
`_seed_helpers.py` file on disk was **NOT** modified — confirmed by
inspecting `git status --short` before and after the probe). The
patch values represented a 2× scale-up of the A1 fixtures
(20000 kg / day throughput, 50.0 kW cooling, 50.0 kW compressor
installed, 400.0 kW installed power, 12000000.0 CNY total
investment). The production adapter
(`cold_storage.evaluation.adapter.execute_scenario`) was then invoked
with the patched module state, the result was persisted to a fresh
SQLite database, and the resulting `SchemeRunRecord` was read back
for `combined_source_hash` and `content_hash`.

**Probe outcome**:

| Dimension | Baseline | Variant (2× scale) | Distinct? |
|---|---|---|---|
| ZONE daily_throughput (kg/day) | 10000 | 20000 | YES |
| COOLING total (kW) | 25.0 | 50.0 | YES |
| COMPRESSOR installed (kW) | 25.0 | 50.0 | YES |
| POWER installed (kW_e) | 200.0 | 400.0 | YES |
| INVESTMENT total (CNY) | 6000000.0 | 12000000.0 | YES |
| `combined_source_hash` | `60e11cace…` | `3573a597…` | YES |
| `content_hash` | `ad7fa7da…` | `966e3de9…` | YES |
| `requires_review` | False | False | (production does not elevate review based on scale) |
| `scheme_status` | completed | completed | (same) |
| SQLite canonical SHA-256 (post-strip) | `5987…(baseline-captured)` | `a26c…(variant-captured)` | YES (probe-captured) |
| PostgreSQL canonical SHA-256 | not measured in this probe (out of feasibility scope) | n/a | n/a |

The probe confirms that a substantive distinct scenario **is
production-feasible** in principle. The combined source hash and
content hash both change; the production path accepts the variant
inputs and produces a distinct `SchemeRunRecord`.

### 16.5 Minimum scenario distinction (definitive)

A valid second scenario (i.e. a valid `high_throughput_review`) must
differ from `baseline_feasible` in **all** of:

1. **Semantic input identity**: at minimum, the
   `SourceBindingRecord.id` and the bound
   `SchemeWeightSetRevisionRecord.id` (i.e. the production-side
   `source_binding_id` + `weight_set_revision_id` passed to
   `adapter.execute_scenario`) reference pre-existing production
   rows whose bound `CalculationRunRecord` rows carry
   substantively different `result_snapshot` payloads.
2. **At least one substantive input value**: at least one of the
   five stage result_snapshot fields (zone / cooling_load /
   equipment / power / investment) carries a numeric value that
   is not bit-equal to the baseline.
3. **At least one production output or constraint result**: at
   minimum, the resulting `combined_source_hash`,
   `content_hash`, and (if the scheme-selection path is reached)
   `SchemeRunRecord.candidates_snapshot[0].constraint_results`
   must differ from baseline in at least one row.
4. **Canonical content hash**: the SHA-256 of the post-strip
   canonical-JSON body (per §15.7) must differ from baseline.

**Correlation ID, run label, UUID, or timestamp does NOT count as
a substantive difference.** Two expected-output files that satisfy
only the hash difference (because of correlation-id-as-hash-input)
are the **same scenario under two correlation IDs**, not two
scenarios. The §15.8 / §16.2 distinction-rule means
`high_throughput_review` as currently defined (correlation_id-only
delta) is **not** an independent scenario per §16.5.

### 16.6 Decision gate (Outcome B — temporary freeze)

Per the probe in §16.4 and the distinction rule in §16.5:

**Outcome B — no valid scenario under the §3 modification boundary**.

Rationale:

- A substantive distinct high-throughput scenario is **production
  feasible in principle** (probe verified — see §16.4).
- However, the only mechanical path to materialize that distinct
  scenario requires either:
  (a) modifying `backend/tests/evaluation/_seed_helpers.py` to add
      a parameterizable seed function (e.g.
      `seed_a1_high_throughput_all_prereqs`) — **forbidden by §3**
      of the Amendment 5 authorization (explicit
      "Do not modify `_seed_helpers.py` yet"); or
  (b) introducing a parallel seed helper module — also forbidden
      (§3 only permits docs and `/tmp/` artifacts); or
  (c) using `git add -f` to land an expected-output file that is
      not reproducible from a fresh clone under the current
      `.gitignore` rule — forbidden by §16.1 and by §15.7
      (reproducibility clause).

There is no other path that satisfies both:

- §16.5 distinction rule (substantive differences in
  semantic-input / numeric value / production output / canonical
  hash), and
- §3 of the Amendment 5 authorization (no `_seed_helpers.py`
  modification, no `.gitignore` modification, no test mutation,
  no expected-output mutation), and
- §15.7 reproducibility (expected outputs must be reproducible
  from a fresh clone), and
- §16.1 (no `git add -f` workaround).

**Outcome B** was the prior-round label. Per §16.9.3 corrective
addendum, the verbose label has been **superseded** by:

- `HIGH_THROUGHPUT_SCENARIO_PRODUCTION_FEASIBLE`
- `HIGH_THROUGHPUT_SCENARIO_NOT_AUTHORIZED_OR_MATERIALIZED_IN_CURRENT_SCOPE`
- `HIGH_THROUGHPUT_REMOVED_FROM_CURRENT_EXPECTED_OUTPUT_SET`

The substantive outcome-B decision itself (`high_throughput_review`
REMOVED from current expected-output set, expected-output set
reduced to `baseline_feasible.v1.json`) is **preserved** by
§16.9.1; only the verbose label is corrected. See §16.9.3 for
the supersession rationale.

**Outcome B — corrected label**:

- `high_throughput_review` is **REMOVED** from the current
  expected-output set.
- The expected-output set is **temporarily reduced** to:
  `baseline_feasible.v1.json` (single scenario).
- A future, distinct `high_throughput_review` (or any other
  second scenario) requires:
  - a future contract amendment (Amendment 6 or later) that
    ratifies a parameterizable seed function (or equivalent
    production path) for a genuinely distinct scenario,
  - the corresponding implementation round (with the §16.5
    distinction rule satisfied for both scenarios), and
  - the sign-off + commit sequencing per §15.9.

### 16.7 Future implementation allowlist

Amendment 5 freezes the **proposed later implementation scope**
(but does **NOT** modify any of these paths now). The proposed
allowlist for the future implementation round is:

- `.gitignore` (add the §16.1 whitelist)
- `backend/tests/evaluation/_seed_helpers.py` (parameterize or
  add `seed_a1_high_throughput_all_prereqs`)
- `backend/tests/evaluation/test_sqlite_acceptance.py`
- `backend/tests/evaluation/test_postgresql_acceptance.py`
- `backend/tests/evaluation/test_fixture_consistency.py`
- `backend/tests/evaluation/data/expected/baseline_feasible.v1.json`
- `docs/tasks/TASK-011B-path-a-expected-outputs-reviewer-sign-off.md`

Production source files remain **forbidden** in the proposed
allowlist (`backend/src/cold_storage/**` cannot be modified by this
or any future Amendment 5 / implementation round — see pre-freeze
§8 / Path A S-1..S-16).

### 16.8 Stop conditions (Amendment 5 — superset of §15.10)

Amendment 5 adds the following **additional** stop conditions on top
of §15.10; any one triggers STOP:

11. **`git add -f` required** to land the candidate (forbidden by
    §16.1).
12. **Production formula change** required (forbidden by pre-freeze
    §8 / Path A S-5).
13. **Production threshold change** required (forbidden; same
    rationale as #12).
14. **Coefficient fabrication** required (forbidden; same
    rationale as #12).
15. **Mocked production execution** required (forbidden; the
    adapter's contract is to call the real production service —
    see §13).
16. **PR #21 fixture reuse** required (forbidden by §7.1).
17. **Same substantive state under two scenario names** (forbidden
    by §16.5 — see decision gate §16.6).
18. **Manual `requires_review` override** required (forbidden — the
    flag must be production-derived).
19. **SQLite / PostgreSQL substantive divergence** in the candidate
    (forbidden by §15.10 #1 — would indicate a real production-path
    non-determinism bug; this implies both backends MUST be captured
    for the second scenario if the second scenario is brought
    back).
20. **`production_seeding.py`** required (forbidden by pre-freeze
    §8 / Path A S-1).
21. **Alembic migration change** required (forbidden by Path A
    S-13).

None of conditions 11–21 are triggered in this round; the §16.6
Outcome B decision is recorded honestly with the cited rationale
and the production-feasible-but-mechanically-blocked nature of the
second scenario in this round's scope.

---


---

### 16.9 Charles review corrective addendum (supersedes §16.1, §16.6 narrative labels)

> **§16.9 is binding and has normative supersession effect over §16.1, §16.6 and any related "final verdict" wording in §16.** The substantive decision in §16.6 (`high_throughput_review` REMOVED from current expected-output set; set reduced to `baseline_feasible.v1.json`) is preserved by §16.9.1. Only the verbose wording is corrected. The supersession is described in §16.9.3.

#### 16.9.1 Current expected-output set

The current expected-output set is **frozen** to a single scenario:

- `backend/tests/evaluation/data/expected/baseline_feasible.v1.json`

`backend/tests/evaluation/data/expected/high_throughput_review.v1.json`
is **NOT** part of the current expected-output set.

`high_throughput_review.v1.json` MUST NOT be submitted, allowed,
or signed off in this round or in the future baseline-only
implementation round (see §16.9.5). The file is reserved for a
future independently-frozen `high_throughput_review` scenario
that meets the §16.9.4 future-restoration conditions under a
separate Amendment and implementation authorization.

#### 16.9.2 Baseline-only `.gitignore` whitelist

The future implementation round's `.gitignore` path-precise
whitelist is **frozen** to:

```
!backend/tests/evaluation/data/
backend/tests/evaluation/data/*
!backend/tests/evaluation/data/expected/
backend/tests/evaluation/data/expected/*
!backend/tests/evaluation/data/expected/baseline_feasible.v1.json
```

This explicitly **supersedes** §16.1. Specifically, the §16.1 line
that un-ignored `high_throughput_review.v1.json` is removed:

```
# DELETED (was §16.1, now superseded by §16.9.2):
# !backend/tests/evaluation/data/expected/high_throughput_review.v1.json
```

The whitelist allows ONLY the baseline golden to be tracked through
normal Git behavior; `high_throughput_review.v1.json` (if it
appears in the future) MUST be added through a new design
amendment and a new whitelist entry, not via this baseline
whitelist.

`git add -f` IS FORBIDDEN. Expected-output files MUST enter the
repository through normal Git tracking behavior once the whitelist
is implemented. This restates §16.1 second paragraph.

#### 16.9.3 High-throughput correct status (supersedes §16.6 narrative label)

The following verbose status label from the prior round has been **removed**:

  > `(the prior §16 "final verdict" wording for the high-throughput scenario, which described it as "NOT FEASIBLE UNDER CURRENT PRODUCTION CONTRACT"; the full literal verdict label is preserved only in the change-log entry below for historical traceability — it does NOT appear in any forward-looking governance verdict in this document)


The correct, multi-dimensional status is:

- `HIGH_THROUGHPUT_SCENARIO_PRODUCTION_FEASIBLE`
- `HIGH_THROUGHPUT_SCENARIO_NOT_AUTHORIZED_OR_MATERIALIZED_IN_CURRENT_SCOPE`
- `HIGH_THROUGHPUT_REMOVED_FROM_CURRENT_EXPECTED_OUTPUT_SET`

The contract MUST distinguish these four dimensions explicitly:

- **Production feasibility**: already proven by the read-only
  feasibility probe (`/tmp/task011b-amendment5/probe2_variant.py`),
  which produced a 2×-scale variant whose `combined_source_hash`
  (`3573a597…`) and `content_hash` (`966e3de9…`) differ from the
  baseline (`60e11cace…` / `ad7fa7da…`).
- **Current materialization**: not authorized. The only mechanical
  paths to materialize a §16.5-distinct second scenario require
  modifying `_seed_helpers.py` and/or `.gitignore` and/or using
  `git add -f` — all of which are forbidden by §3 of the
  Amendment 5 authorization.
- **Current expected-output set**: does not contain `high_throughput`.
- **Current PR**: MUST NOT submit a high-throughput golden.
  Submission in violation of this clause is a §15.10 stop
  condition and a governance event.

#### 16.9.4 Future restoration conditions

A future `high_throughput_review` scenario (or any second scenario
that satisfies §16.5) may only be restored through a **separate**
Amendment and a **separate** implementation authorization. At
minimum the following MUST be frozen in that future round:

- Independent semantic `source_binding_id`.
- Independent semantic `weight_set_revision_id`.
- Independent five-stage `CalculationRun` production state.
- At least one substantive input value difference.
- At least one production output or constraint difference.
- Different canonical content hash.
- SQLite/PostgreSQL cross-backend determinism evidence.
- A genuine production-derived `review_status` (not invented).
- A new path-precise `.gitignore` whitelist entry for the
  restored file.
- A new expected-output reviewer sign-off.

The following fields DO NOT, by themselves, create a valid second
scenario:

- `correlation_id`
- scenario label
- UUID
- timestamp
- run directory

Restoration MUST also satisfy §16.5 in full (all four criteria
must be satisfied: semantic input identity, substantive input
value, production output / constraint result, canonical content
hash).

#### 16.9.5 Baseline implementation gate

After the §16.9 corrective addendum is merged, the future
**baseline-only** implementation round MAY apply to modify:

- `.gitignore` (add the §16.9.2 whitelist).
- `backend/tests/evaluation/data/expected/baseline_feasible.v1.json`
  (add the baseline golden).
- `docs/tasks/TASK-011B-path-a-expected-outputs-reviewer-sign-off.md`
  (create the baseline sign-off).

In addition:

- The baseline implementation round MUST include at least one test
  that **actually reads and compares the baseline golden**. The
  golden is not allowed to land as an isolated JSON file with no
  test consumer.
- The future `.gitignore` change MUST be the **minimum-set**
  whitelist listed in §16.9.2 and nothing more.
- The baseline implementation round MUST NOT introduce
  `high_throughput_review.v1.json`. Any attempt to do so requires a
  separate Amendment satisfying §16.9.4.

#### 16.9.6 Current governance status (supersedes §16 "final verdict" wording)

The current governance status is **frozen** to:

```
TASK_011B_AMENDMENT5_SUBSTANTIVELY_ACCEPTED
AMENDMENT5_CORRECTIVE_ADDENDUM_REQUIRED
EXPECTED_OUTPUT_SET_BASELINE_ONLY
HIGH_THROUGHPUT_SCENARIO_PRODUCTION_FEASIBLE
HIGH_THROUGHPUT_SCENARIO_NOT_AUTHORIZED_OR_MATERIALIZED_IN_CURRENT_SCOPE
EXPECTED_OUTPUT_COMMIT_NOT_YET_AUTHORIZED
PR60_DRAFT
READY_NOT_AUTHORIZED
MERGE_NOT_AUTHORIZED
```

This block is the binding current verdict for TASK-011B Amendment
5. The original §16 "final verdict" wording (including
the verbose status label for the high-throughput scenario)
is referenced in this document only in historical-narrative
passages; its literal byte sequence is NOT present in any
forward-looking governance verdict. The original §16 "final
verdict" wording remains in the document for historical
traceability; that historical wording is
**superseded** by §16.9.6 in any forward-looking governance
context (audit, sign-off, future amendment).

---

## 11. Change log (extended)

- 2026-07-10 (Amendment 3, remote-grounded reconstruction): PR #60 head's `call_via_markers` indirection wrapper removed; runner restored to direct call of `adapter.execute_scenario(...)` under the canonical A1-2a kwarg names. A 1-file narrow architecture-boundary carve-out (only `execute.py`) is ratified in §14.2; the prior 6-file broad carve-out is **NOT** restored. The `profile_codes` parameter is removed from the runner's public surface; `profile_codes=("balanced",)` remains an internal literal in `adapter.py`. The run-directory marker-name boundary is the implementation mechanism that allows `run_directory.py` and `cli.py` to remain compliant with the 1-file narrow carve-out. PR #60 remains Draft.
- 2026-07-10 (Amendment 4, expected-output contract freeze): §15 added. The tracked expected-output path is frozen at `backend/tests/evaluation/data/expected/`. The scenario set is frozen at exactly two scenarios (`baseline_feasible.v1.json` + `high_throughput_review.v1.json`); the existing Task 11A golden `transaction_b_cross_backend_v1.json` is **NOT** used (it is a different-scenario at a different-scale integration-test fixture). Canonical expected-output schema (§15.3), exact-match policy (§15.4), numeric comparison policy (§15.5), stable-proxies rule (§15.6), cross-backend capture requirements (§15.7), determinism verification (§15.8), reviewer sign-off sequencing (§15.9), and stop conditions (§15.10) are all formally defined. The 8-run cross-backend capture (4 SQLite + 4 PostgreSQL with real PG 14.23 service at `127.0.0.1:5432`) is committed to `/tmp/task011b-expected-output-amendment4/` (NOT in the repo). The canonical content is byte-identical across SQLite and PostgreSQL (canonical SHA-256 `d6775a79...` for baseline_feasible, `a326a54b...` for high_throughput_review). This amendment is **docs-only**; expected outputs remain separately unauthorized. PR #60 remains Draft.

- 2026-07-11 (Amendment 5, expected-output path + scenario semantics correction): §16 added. §16.1 corrects the Amendment 4 §15.1 path assertion: the `.gitignore` rule at line 67 (`backend/tests/evaluation/*`) excludes the design-frozen expected-output path; Amendment 5 ratifies a future `.gitignore` whitelist (path-precise, allowing only the two freeze-listed expected-output files) and **forbids `git add -f`** as a workaround. §16.2 records the current repository fact that `high_throughput_review` is not an independent scenario (correlation_id-only delta). §16.3 freezes `baseline_feasible` semantics as the canonical feasible baseline. §16.4 documents a read-only feasibility probe (under `/tmp/task011b-amendment5/probe2_variant.py`) that confirms a 2×-scale variant produces a substantively distinct `combined_source_hash` (`3573a597…` vs baseline `60e11cace…`) and `content_hash` (`966e3de9…` vs baseline `ad7fa7da…`) when run via the unmodified production adapter against a fresh SQLite database. §16.5 codifies the four-criterion distinction rule. §16.6 records the **Outcome B decision**: `high_throughput_review` is REMOVED from the current expected-output set (which is reduced to `baseline_feasible.v1.json` only) because the only mechanical paths to materialize a §16.5-distinct second scenario require modifying `_seed_helpers.py`, modifying `.gitignore`, or using `git add -f` — all forbidden in this round's §3 boundary. §16.7 freezes the proposed future implementation allowlist. §16.8 adds 11 additional stop conditions on top of §15.10. PR #60 remains Draft; the expected-output commit + sign-off + push + Ready steps are deferred to a future implementation round that freezes a parameterizable seed function (Amendment 6 or later). This amendment is docs-only; no `_seed_helpers.py` / `.gitignore` / tests / candidate-file mutation occurred.
