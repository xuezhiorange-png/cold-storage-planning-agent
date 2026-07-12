# TASK-011C Remaining Evaluation Scenarios — Frozen Contract

**Status:** DESIGN-ONLY / DRAFT / awaiting Charles freeze authorization
**Created:** 2026-07-12 (server UTC)
**Author:** Hermes (proposal subject to Charles-authorized freeze review)
**Branch base:** `main @ 1636f25d4b6fafa38bfc9747938d0cba8b2abf50` (= `origin/main` HEAD post-PR-#60 + PR-#60 closeout)
**Branch name (created):** `docs/task-011c-remaining-evaluation-scenarios-contract`
**Target Phase:** Task 11 Phase C — Remaining Evaluation Scenarios Authority and Expected Outputs
**Authoritative references:**
- Issue #20 (TASK-011 Evaluation and Pilot Readiness, open)
- PR #60 (`TASK-011B: Phase B implementation and baseline expected output`, merged)
- Review `4679300437` (PR #60 Review Comment, post-merge correction)
- Review `4679338799` (PR #21 Review Comment, post-B audit correction)
- `docs/tasks/TASK-011B-baseline-success-criteria.md` (baseline-success-criteria governance record)
- `docs/tasks/TASK-011B-path-a-design-ratification.md` (Path A design ratification)
- `docs/tasks/TASK-011B-path-a-expected-outputs-reviewer-sign-off.md` (baseline sign-off)
- `docs/tasks/TASK-011B-phase-b-resumption-pre-freeze.md` (frozen pre-freeze contract; §1.1 PR #21 superseded)
- `backend/src/cold_storage/evaluation/**` (current main evaluation module)
- `backend/tests/evaluation/**` (current main evaluation test suite)

---

## 0. Preamble

This document **freezes the contract** for **TASK-011C** = the remaining evaluation scenarios (high-throughput-review, invalid-blocked) plus the manifest / runner / canonicalization / cleanup completeness that TASK-011B did not deliver.

This document covers the **5 implementation gaps G1–G5** identified by the post-B audit (per the previous round's corrected audit matrix 5 PASS / 5 PARTIAL / 4 MISSING / 1 UNKNOWN):

| Gap | Topic | Covered in § |
|---|---|---|
| G1 | High-throughput / review-required scenario | §6.2 |
| G2 | Invalid / blocked input scenario | §6.3 |
| G3 | Versioned manifest schema + validation | §7 |
| G4 | Repeatable runner contract (multi-scenario, exit codes, fail-closed) | §9 |
| G5 | Canonicalization + stale-output + cleanup completeness | §10, §11 |

**Gaps G6–G11 are explicitly reserved for TASK-011D** (multilingual / runbook / demo path / cleanup procedure / Issue #20 final closure) and are NOT in scope of this contract.

This document **does not**:
- Authorize implementation of TASK-011C.
- Authorize authoring of any expected-output file (golden).
- Authorize a TASK-011C implementation branch, PR, commit, push, Ready, or Merge.
- Mutate PR #21, PR #23, PR #60, Issue #20, Issue #22, or any other GitHub object.
- Modify any tracked file outside `docs/tasks/TASK-011C-remaining-evaluation-scenarios-contract.md`.
- Touch any production code, evaluation runner code, evaluation fixture, manifest, expected output, baseline golden, sign-off, comparison policy, bootstrap, coefficients, migration, frontend, docker, .github, pyproject, uv.lock, or .gitignore.

This document **does**:
- Freeze the scenario set (§6), manifest contract (§7), expected-output authority flow (§8), runner contract (§9), canonicalization contract (§10), cleanup contract (§11), SQLite/PostgreSQL boundary (§12), future implementation allowlist proposal (§13), and stop conditions (§16).
- Cite every source-of-truth in §5.
- Surface the gaps and bounded scope so that Charles can authorize (or reject) a future TASK-011C implementation round.

---

## 1. Authority and status

This contract is **frozen** as a single-file docs-only commit on branch `docs/task-011c-remaining-evaluation-scenarios-contract` (from `main @ 1636f25d4b6fafa38bfc9747938d0cba8b2abf50`). Implementation of the contract requires a separate Charles-authorized round and is NOT in this round's scope.

**Frozen disposition of legacy PRs (per Review 4679338799, binding):**
```
PR21_SUPERSEDED
PR21_REMAINS_OPEN_DRAFT_NOT_MERGED
PR21_CLOSE_NOT_AUTHORIZED
PR23_RETAINED_AS_HISTORICAL_DESIGN_AUTHORITY
PR23_REMAINS_OPEN_DRAFT_NOT_MERGED
PR23_CLOSE_NOT_AUTHORIZED
PR23_DESIGN_EXTRACTION_NOT_AUTHORIZED
ISSUE20_REMAINS_OPEN
```

**TASK-011C implementation status:**
```
TASK011C_IMPLEMENTATION_NOT_AUTHORIZED
TASK011D_NOT_AUTHORIZED
TASK12_NOT_AUTHORIZED
READY_NOT_AUTHORIZED
MERGE_NOT_AUTHORIZED
```

---

## 2. Objectives and scope

### 2.1 Objectives

TASK-011C (when implemented) must close the 5 implementation gaps G1–G5 from the post-B audit by providing:

1. A versioned evaluation manifest schema that supports multiple scenarios (baseline, high-throughput-review, invalid-blocked) with per-scenario expected outputs, comparison policies, and provenance.
2. A `high_throughput_review` scenario whose **production outcome is substantively distinct** from `baseline_feasible` (not a `correlation_id` / `run_id` / `timestamp` / database-generated ID rename of baseline).
3. An `invalid_blocked` scenario that exercises a **real production validation/blocker pathway** (not an evaluation-layer-injected exception).
4. A repeatable runner that executes multiple scenarios in one invocation, with typed run.json / summary.json / raw and normalized artifacts, fail-closed validation, and zero exit only on full match.
5. Reuse of the existing canonicalization (no second canonicalizer), with stale-output detection and per-scenario cleanup discipline.

### 2.2 Scope (in this contract)

This contract freezes:
- Scenario set (§6)
- Manifest contract (§7)
- Expected-output authority flow (§8)
- Runner contract (§9)
- Canonicalization contract (§10)
- Cleanup + stale-output contract (§11)
- SQLite / PostgreSQL boundary (§12)
- Future implementation allowlist proposal (§13)
- Stop conditions for the future implementation round (§16)

### 2.3 Out of scope (explicit exclusions)

The following are **NOT** in this contract and are reserved for TASK-011D or independent closure:

- zh-CN / en-US multilingual report evaluation
- Sample knowledge / document scenario
- Frontend demo path
- Pilot runbook
- Operator instructions
- Issue #20 final closure
- Task 12 productionization
- Any mutation of PR #21, PR #23, PR #60
- Authoring of any expected-output golden
- Production code, formula, coefficient, threshold, scoring, or review-rule change
- Restoration of `production_seeding.py` or any evaluation-owned production ORM fabrication

---

## 3. Definitions

- **Scenario** — A named evaluation execution unit, identified by `scenario_id`, with declared fixture, expected outcome class, expected output (when required), and comparison policy.
- **Manifest** — A versioned JSON document declaring all scenarios in a run-suite, with per-scenario fixture / expected output / outcome class / comparison policy / provenance.
- **Expected output** — A tracked JSON file at `backend/tests/evaluation/data/expected/{scenario_id}.v{revision}.json` that captures the production-path ground truth for a scenario.
- **Comparison policy** — The per-leaf classification (exact / decimal / excluded) used to compare runtime normalized output against the expected output. Pairwise disjoint across classification types.
- **Sign-off** — Charles-approved identity for a specific expected-output commit, recorded in a sign-off document, with explicit `STATUS: APPROVED` / `CHARLES_VERDICT: APPROVED` markers.
- **Production-path execution** — Code path that goes through `compose_production_scheme_service` → `ProductionSchemeService.generate_production_scheme_run` and persists SchemeRun via the production orchestrator. The evaluation adapter is the only evaluation-side caller of this path.
- **Substantively distinct scenario** — A scenario whose `expected_outcome` / `expected review/blocker propagation` / `required production stages` / `required exact fields` / `required numeric fields` differ from any other scenario in the same manifest, AND whose production result for an arbitrary execution is not derivable by relabeling baseline inputs.
- **fail-closed** — A property of the runner that any unmet precondition, manifest validation failure, comparison mismatch, or unexpected exception results in non-zero exit AND a typed failure artifact, never a silent zero-exit pass.

---

## 4. Golden case set

TASK-011C covers three scenarios (G1, G2, plus the existing baseline as regression anchor):

| scenario_id | scope | fixture status | expected output status |
|---|---|---|---|
| `baseline_feasible` | Already approved (TASK-011B); regression anchor | Frozen | Frozen (`backend/tests/evaluation/data/expected/baseline_feasible.v1.json`); sign-off `f274db66…` |
| `high_throughput_review` | New (G1) | To be defined | To be authored under separate sign-off |
| `invalid_blocked` | New (G2) | To be defined | To be authored under separate sign-off |

The manifest MAY carry additional scenarios in the future, but each new scenario requires its own sign-off and must satisfy the substantively-distinct property (see §6.2).

---

## 5. Source-of-truth matrix

This contract is built from the following source-of-truth artifacts. Every clause in §6–§14 cites at least one.

| ID | Source | Type | Purpose |
|---|---|---|---|
| S1 | `Issue #20` body | Issue | Top-level requirements |
| S2 | `Review 4679338799` (PR #21) | Review | Audit correction; binding disposition |
| S3 | `Review 4679300437` (PR #60) | Review | Post-merge main-push-CI correction |
| S4 | PR #60 final merged body | PR body | Implementation history of baseline |
| S5 | `docs/tasks/TASK-011B-baseline-success-criteria.md` | Doc | Baseline success criteria + quality gates |
| S6 | `docs/tasks/TASK-011B-path-a-design-ratification.md` | Doc | Path A design (adapter ownership boundary) |
| S7 | `docs/tasks/TASK-011B-path-a-expected-outputs-reviewer-sign-off.md` | Doc | Baseline golden sign-off |
| S8 | `docs/tasks/TASK-011B-phase-b-resumption-pre-freeze.md` | Doc | Frozen pre-freeze contract; §1.1 PR #21 superseded |
| S9 | `backend/src/cold_storage/evaluation/__init__.py` | Code | Module entry point |
| S10 | `backend/src/cold_storage/evaluation/adapter.py` | Code | A1-2a adapter (production-path bound) |
| S11 | `backend/src/cold_storage/evaluation/cli.py` | Code | CLI surface (current main) |
| S12 | `backend/src/cold_storage/evaluation/errors.py` | Code | Error surface (5 typed exceptions) |
| S13 | `backend/src/cold_storage/evaluation/execute.py` | Code | Scenario execution (5 functions) |
| S14 | `backend/src/cold_storage/evaluation/run_directory.py` | Code | Run-directory isolation (3 functions) |
| S15 | `backend/tests/evaluation/data/expected/baseline_feasible.v1.json` | Expected output | Baseline golden (frozen) |
| S16 | `backend/tests/evaluation/_seed_helpers.py` | Test helper | Production seed helpers (read-only) |
| S17 | `backend/tests/evaluation/test_sqlite_acceptance.py` | Test | SQLite acceptance suite |
| S18 | `backend/tests/evaluation/test_postgresql_acceptance.py` | Test | PostgreSQL acceptance suite |
| S19 | `backend/tests/evaluation/test_path_a_adapter.py` | Test | Adapter path-A tests |
| S20 | `backend/tests/evaluation/test_fixture_consistency.py` | Test | Fixture consistency tests |
| S21 | `backend/tests/evaluation/test_cli.py` | Test | CLI tests |
| S22 | PR #21 (Draft / Open / Not merged) | Historical | Frozen-by-design reference; not a rebase target |
| S23 | PR #23 (Draft / Open / Not merged) | Historical | Historical design authority; not to be extracted or merged |

---

## 6. Scenario set (frozen)

### 6.1 Already-frozen `baseline_feasible` (DO NOT REOPEN)

| Property | Frozen value | Source |
|---|---|---|
| `scenario_id` | `baseline_feasible` | S15 |
| `expected_outcome` | `SUCCEEDED` | S15 |
| `scheme_status` | `completed` | S15 |
| `review_required` | `false` | S15 |
| `review_reasons` | `[]` | S15 |
| `combined_source_hash` | `60e11cacea5868d1650e40f72186618e4a01f29b1655e9aa531deccaf0633206` | S15 |
| Golden SHA-256 | `2d45ea2291c726460d80b0cbca0a771edda9812aa3a6cb017328af458b65ca73` | S7 |
| Production content hash | `ea4ab8cd7f73b50c8cd83865adc9ec90428d8d60a9fc2e7d823a0c8fdb16fe46` | S7 |
| Sign-off identity | `f274db66fe4bb2de206d12c2d561d1b3549ab6c0` (Commit E) | S7 |

**TASK-011C MUST NOT modify the baseline golden, comparison policy, sign-off, or content hash.** Baseline is the regression anchor; any change to it requires a separate amendment to S7.

### 6.2 High-throughput / review-required (G1)

A new scenario `high_throughput_review` that **MUST** be substantively distinct from `baseline_feasible`. The contract freezes EXACTLY the following properties:

| Property | Contract requirement (FROZEN) |
|---|---|
| `scenario_id` | `high_throughput_review` (string, no spaces) |
| `fixture_revision` | positive integer (≥ 1) |
| `execution_outcome` | `SUCCEEDED` (production run completes successfully) |
| `scheme_run.status` | `completed` (persisted SchemeRun row records the completed status) |
| `requires_review` | `true` (business field; review is required for downstream processing) |
| `review_state` | `REQUIRED` (business field; review propagation has happened) |
| Substantive input differences from baseline | REQUIRED (see HIGH_THROUGHPUT_MUST_BE_SUBSTANTIVELY_DISTINCT below) |
| Required production stages | `["zone", "cooling_load", "equipment", "power", "investment"]` (same as baseline) |
| Required exact fields | All `exact_match_fields` of baseline, plus any scenario-specific additional fields |
| Required numeric fields | All `decimal_fields` of baseline, plus any scenario-specific additional fields |
| Runtime-only excluded fields | `["correlation_id", "run_attempt_id", "executed_at_timestamp", "database_session_uuid", "calculation_run_id[]"]` (or explicitly justified per-scenario) |
| SQLite/PostgreSQL equivalence | `substantive normalized result parity` required; backend-specific runtime metadata allowed |

**CLI exit semantics (per §7.1 below):** `high_throughput_review` exits with CLI success code `0` (NOT exit code `5`). `requires_review=true` and `review_state=REQUIRED` are business fields of a successful run, NOT a runner-level failure.

**HIGH_THROUGHPUT_REVIEW_EXACT_FOUR_FIELDS (frozen invariant):**

The four business fields `execution_outcome=SUCCEEDED`, `scheme_run.status=completed`, `requires_review=true`, `review_state=REQUIRED` MUST hold for **both** SQLite and PostgreSQL production runs of this scenario. If any of the four is not produced by real production logic, the scenario cannot be authored as a high-throughput scenario under this contract — the stop condition `TASK_011C_HIGH_THROUGHPUT_REQUIRES_REVIEW_PRODUCTION_RULE_MUTATION` (per §16) applies.

**HIGH_THROUGHPUT_REVIEW_REAL_PRODUCTION_REVIEW_SIGNAL (frozen invariant):**

The `review_state=REQUIRED` signal MUST come from a real production review rule. It is **forbidden** to trigger, synthesize, or rename this scenario's review signal via:
- correlation ID;
- scenario ID;
- runner-level reclassification or special-case logic;
- CLI-level special-case logic;
- test-only relabeling;
- hand-editing the expected-output file;
- modifying production formula / threshold / coefficient / scoring / review rule.

**HIGH_THROUGHPUT_MUST_BE_SUBSTANTIVELY_DISTINCT (frozen invariant):**

A high-throughput scenario is "substantively distinct" from baseline if and only if it differs in **at least one** of the following observable properties:

**HIGH_THROUGHPUT_MUST_BE_SUBSTANTIVELY_DISTINCT (frozen invariant):**

A high-throughput scenario is "substantively distinct" from baseline if and only if it differs in **at least one** of the following observable properties:
- `expected_outcome` (e.g., baseline `SUCCEEDED` + `review_required: false` vs. high-throughput `SUCCEEDED` + `review_required: true`)
- `review_reasons` (non-empty, with at least one review reason that is NOT present in baseline)
- `combined_source_hash` (must be different from baseline `60e11cace…`)
- Production path traversal: at least one of {zone, cooling_load, equipment, power, investment} must differ in `production_outputs.candidates_snapshot` (different scheme_code, different constraint passed/failed set, or different numeric result)
- A different `weight_set_revision_proxy` (not just a database-generated ID rename)

It is **FORBIDDEN** to create a high-throughput scenario that differs from baseline ONLY in:
- `correlation_id` (a request-tracing identifier, not a substantive input)
- `run_id` (a runtime identifier, not a substantive input)
- `timestamp` (a wall-clock value, not a substantive input)
- `database-generated ID` (a session/object identity, not a substantive input)
- A re-shuffled `production_outputs.candidates_snapshot` where every numeric value is identical to baseline modulo comparison policy rounding
- A scenario that asserts `review_required: true` with empty `review_reasons: []` (or only database-internal reasons)

**HIGH_THROUGHPUT_SCENARIO_SOURCE_DEFINITION_REQUIRED (frozen invariant):**

If the current production capability cannot form a substantively distinct high-throughput scenario (e.g., no production pathway produces a substantively different result for any permitted input variation), the implementation round MUST **fail closed** by:
1. Stopping the high-throughput scenario implementation.
2. Recording the source-definition gap in the round's BLOCKER report.
3. NOT producing a `high_throughput_review` expected output or test.
4. NOT relaxing the substantively-distinct property to allow a re-labeled baseline.

The implementation round is **forbidden** from:
- Inventing throughput, equipment-efficiency, investment, cooling-load, review-threshold, or blocker values to force a substantive difference.
- Modifying any production formula, coefficient, threshold, scoring, or review rule to create a difference.
- Using a hand-tuned fixture that forces a specific `review_reasons` entry that production does not naturally produce.

### 6.3 Invalid / blocked (G2)

A new scenario `invalid_blocked` that exercises a **real production validation/blocker pathway**. The contract freezes the following field-by-field, EXACTLY:

| Property | Contract requirement (FROZEN) |
|---|---|
| `scenario_id` | `invalid_blocked` |
| `fixture_revision` | positive integer (≥ 1) |
| `scenario input difference` | A SPECIFIC pre-existing production validation defect (NOT a runtime exception, NOT an evaluation-layer-injected error, NOT a `correlation_id` change, NOT a `scenario_id` change) |
| `production validation stage` | A pre-existing production entrypoint in `backend/src/cold_storage/modules/...` that raises a typed exception (NOT `Exception` / NOT `BaseException`) |
| `typed exception or structured result` | A specific, pre-existing production exception class — must be enumerated by class FQN; structured result MUST come from a real production error model |
| `exact error code` | A specific exception code / marker that the production code already emits (e.g., a stable `code` attribute on the typed exception) |
| `exact error field/path` | The exception's structured field that identifies the failure (e.g., `field` in a `ValidationError`, or `details.path` for nested paths) |
| `expected execution outcome` | `BLOCKED` (production run is blocked at the validation stage) |
| `whether SchemeRun is created` | MUST be `false` if the failure happens at or before SchemeRun creation; if the production contract specifies a persisted failure record, that record is the only SchemeRun-equivalent state allowed |
| `expected database row deltas` | Explicitly enumerated: which rows are NOT created, which rows MAY be created (e.g., validation ledger entries), and which rows MUST be left untouched |
| `SQLite behavior` | The full validation pathway MUST be reproducible on SQLite with the same typed exception / code / field / row delta as on PostgreSQL |
| `PostgreSQL behavior` | The full validation pathway MUST be reproducible on PostgreSQL with the same typed exception / code / field / row delta as on SQLite |
| `CLI exit semantics` | Non-zero CLI exit (per §7.1); typed `RunnerSummary.evaluation_result = "fail"`; typed reason code for the validation defect |
| `blocked stage` | One of `["zone", "cooling_load", "equipment", "power", "investment", "pre_orchestration", "source_binding_verification"]` — frozen per scenario |
| `side-effect expectations` | The blocked stage MUST NOT create a `SchemeRun` row, MUST NOT create `CalculationRunRecord` rows beyond the stage that raised, and MUST leave orchestration identity / attempt / execution-snapshot state consistent with production's pre-block policy |
| `absence of success artifacts` | The normalized result MUST NOT contain `production_outputs` beyond the stage that raised; runner MUST assert absence |
| `SQLite/PG business parity` | The same business verdict (blocked vs succeeded) MUST hold on both backends; no business-outcome drift allowed |

**INVALID_BLOCKED_FORBIDDEN_CIRCUMVENTION (frozen invariants):**

The implementation round is **forbidden** from:
1. Using a valid baseline `SourceBinding` and then renaming a successful result as `blocked` (e.g., by mutating the SchemeRun status after the fact).
2. Triggering the blocked state via `correlation_id` or `scenario_id` special-case logic.
3. Creating a fake `SchemeRun` row (or fake `CalculationRunRecord` / orchestration identity / attempt / execution-snapshot row) to represent the failed scenario.
4. Classifying errors by parsing `args[0]` / `str(exception)` / `repr(exception)` / message-text regex. The classification MUST use the typed exception class and the structured error code/field.
5. Building an evaluation-layer-injected `Exception` / `ValueError` / `RuntimeError` to simulate a production failure. The failure MUST come from a real production validation entrypoint.
6. Producing a `invalid_blocked` expected output that asserts presence of `production_outputs` past the blocked stage.

**INVALID_BLOCKED_FAIL_CLOSED (frozen invariant):**

If the production code cannot provide a real validation pathway that produces a typed exception / structured error result, the implementation round MUST:
- Stop the `invalid_blocked` scenario implementation.
- Trigger the stop condition `TASK_011C_INVALID_BLOCKED_PRODUCTION_PATH_NOT_ESTABLISHED` (per §16).
- NOT produce an `invalid_blocked` expected output or test.
- NOT invent a fake validation path to complete the contract documentation.

**INVALID_BLOCKED_FORBIDDEN (frozen invariants):**

The implementation round is **forbidden** from:
- Adding new business validation rules in the evaluation layer.
- Using a broad `except Exception` to convert any error into an expected blocker.
- Using a fixture that does NOT trigger a real production validation defect.
- Mocking / stubbing the production validation entrypoint to return a synthetic exception.
- Producing a `invalid_blocked` expected output that asserts presence of `production_outputs` past the blocked stage.

---

## 7. Manifest contract

### 7.0 Manifest schema path (FROZEN, single-path)

The TASK-011C implementation round MUST use the following SINGLE manifest schema path:

```
backend/src/cold_storage/evaluation/schema/manifest.schema.json
```

The following are **NOT authorized** in TASK-011C:
- A top-level `evaluation/` directory (any tracked path under `evaluation/` is out of scope).
- A second / alternate / duplicate manifest schema path.
- A copy of the manifest schema at any other path.
- Any modification to `.gitignore` to add manifest / expected-output / fixture paths.

The implementation round MUST NOT create the schema file in this contract round. The schema path is frozen for the future implementation round only.

### 7.1 CLI exit code (FROZEN, no redefinition in TASK-011C)

The current main `backend/src/cold_storage/evaluation/cli.py` exit codes are FROZEN as follows. The TASK-011C contract does NOT redefine, remove, or change these exit codes:

| Exit code | Meaning |
|---|---|
| `0` | SUCCEEDED — execution outcome is `SUCCEEDED` (with or without `requires_review=true`) |
| `1` | production error (unhandled production-side failure) |
| `2` | invalid input (manifest / adapter / CLI input) |
| `3` | runner contract violation (manifest / runner contract mismatch) |
| `4` | historical blocked (legacy Phase B block; reserved) |
| `5` | REVIEW_REQUIRED (general review-required signal) |
| `6` | FAILED (general failure) |

**CRITICAL — high_throughput_review exit code (FROZEN):**

The `high_throughput_review` scenario MUST exit with code `0` (SUCCEEDED). It is an execution success. `requires_review=true` and `review_state=REQUIRED` are business fields of a successful run, NOT a runner-level failure. The contract explicitly **forbids**:
- Mapping `high_throughput_review` to exit code `5` (REVIEW_REQUIRED) as a runner-level outcome.
- Reclassifying the scenario as `failed` because `requires_review=true`.
- Introducing a new exit code for TASK-011C.

The contract is intentionally consistent with the general exit code `5` meaning: exit code `5` is reserved for the runner-level "review-required" verdict (not currently used by the main runner's exit code map but reserved for future expansion). The high-throughput scenario's `requires_review=true` business field is independent of this reserved exit code.

### 7.2 Manifest content (FROZEN)

The manifest (`backend/src/cold_storage/evaluation/manifest.json` or per-test-suite) MUST validate, fail-closed, and contain:

| Required field | Description |
|---|---|
| `schema_version` | Frozen string `task011c-manifest.v1` |
| `suite_id` | Stable string identifying the test-suite version |
| `manifest_sha` | SHA-256 of the canonical bytes of the manifest itself, computed by the canonicalizer (§10) |
| `scenarios[]` | Array of scenario declarations, each with: `scenario_id`, `fixture_revision`, `fixture_path`, `expected_output_path` (when required), `outcome_class`, `comparison_policy`, `provenance` |
| `comparison_policy_overrides` | Optional; per-scenario override of the global comparison policy |
| `provenance` | Object recording `manifest_author`, `manifest_review`, `manifest_signoff`, `manifest_committed_at` (timestamp), `manifest_committed_by` |

**Per-scenario required fields:**
- `scenario_id` unique across `scenarios[]`
- `fixture_revision` positive integer
- `source fixture exists` (path resolves to a tracked file)
- `expected output exists when required` (path resolves to a tracked file, OR an explicit `no_expected_output` flag with justification)
- `required stages` exact and ordered (subset of `["zone", "cooling_load", "equipment", "power", "investment"]` for production-bound scenarios; explicit `pre_orchestration` / `source_binding_verification` allowed for validation scenarios)
- `expected outcome` explicit (one of `SUCCEEDED`, `REVIEW_REQUIRED`, `BLOCKED`, `INVALID`)
- `comparison policy complete` (see §10)
- `provenance complete` (scenario author, reviewer, signoff, committed_at, committed_by)
- `no unknown fields` (manifest schema rejects any field not in the frozen schema)
- `no undeclared expected paths` (every JSON path read at runtime must be declared in `comparison_policy.exact_match_fields` / `decimal_fields` / `excluded_fields`)

**HIGH_THROUGHPUT_REVIEW and INVALID_BLOCKED manifest requirements (frozen choice):**

Both `high_throughput_review` and `invalid_blocked` MUST have reviewer-approved tracked expected JSON files. The contract explicitly **forbids** leaving this to the implementation's discretion.

Rationale: The TASK-011B governance chain (S5, S6, S7) treats expected outputs as reviewable artifacts with explicit sign-off. A manifest-native blocker contract (without a tracked expected JSON) is allowed **only** for future scenarios that the implementation explicitly justifies as "manifest-native-only" with Charles's separate approval.

Implementation choice is therefore:
- `high_throughput_review` → tracked expected JSON (reviewer-approved) at `backend/tests/evaluation/data/expected/high_throughput_review.v{revision}.json`
- `invalid_blocked` → tracked expected JSON (reviewer-approved) at `backend/tests/evaluation/data/expected/invalid_blocked.v{revision}.json` containing a typed `RunnerSummary.evaluation_result = "fail"` and a typed reason code

---

## 8. Expected-output authority flow (per-file freeze)

The expected output for a new scenario is **not** a product of the implementation round. The contract freezes the following 8-step authority flow AND the per-file authority status of the three expected-output JSON files:

1. **Source-definition approval** — Charles approves the substantive source definition (G1: high-throughput source definition; G2: invalid-blocked validation defect) as a separate document, citing the production pathway and the expected production result.
2. **SQLite candidate capture** — The implementation round runs the scenario in SQLite (fresh isolated run-directory) and captures a `candidate.v{revision}.sqlite.json` artifact. The candidate is gitignored (not tracked).
3. **PostgreSQL candidate capture** — Same as step 2 but on PostgreSQL with identical scenario input. Produces `candidate.v{revision}.postgresql.json`. Gitignored.
4. **Cross-backend substantive comparison** — The implementation round runs a substantive comparison (not byte-equality): every canonical leaf in `exact_match_fields` MUST match; every leaf in `decimal_fields` MUST match within the declared decimal quantization; every leaf in `excluded_fields` MUST be ignored. The comparison result is recorded as a typed diff.
5. **Proposed tracked diff** — The implementation round produces a `git diff` between the proposed tracked expected JSON and the empty (new) file, OR between the proposed tracked expected JSON and the previously approved expected JSON (for amendments).
6. **Reviewer sign-off** — Charles reviews the proposed diff, the cross-backend comparison result, and the substantive distinctness claim (for high-throughput) or the validation defect verification (for invalid-blocked), and posts a sign-off with `STATUS: APPROVED` / `CHARLES_VERDICT: APPROVED` / `EXPECTED_OUTPUT_COMMIT_SHA: <commit>` markers.
7. **Separate implementation authorization** — Only after sign-off, Charles issues a separate per-message authorization to commit the expected JSON to a tracked location.
8. **Commit only after sign-off** — The implementation round commits the expected JSON in a commit that references the sign-off commit SHA. The commit message MUST include `EXPECTED_OUTPUT_COMMIT_SHA: <sign-off commit SHA>` and the scenario_id.

**Forbidden practices (enforced by §16 stop conditions and architecture boundary tests):**
- `git add -f` to force-add an untracked expected JSON.
- An `update-golden` command or subcommand that auto-commits expected outputs.
- Self-approval (the implementation round's author cannot also be the sign-off author).
- Implementation-generated authority (the implementation round cannot assert its own compliance without Charles's sign-off).
- Reusing the baseline sign-off (`f274db66…`) as authorization for any other scenario.

**Per-scenario sign-off identity (frozen):**
- Each scenario's expected output has its own sign-off identity, recorded in its own sign-off document under `docs/tasks/TASK-011C-expected-outputs-{scenario_id}-reviewer-sign-off.md`.
- Sign-off identity is bound to:
  - The expected-output file's tracked path.
  - The expected-output file's committed SHA-256.
  - The `production_outputs.content_hash` recorded in the expected JSON.
  - The cross-backend diff report (typed artifact, gitignored).
  - The sign-off commit SHA.

---

### 8.10 Per-file expected-output authority (FROZEN)

The contract freezes the per-file authority status of the three expected-output JSON files. The contract merge does NOT authorize two new expected-output files. Each new expected-output file requires its own separate Charles sign-off.

| File | Status | Authority | Required flow |
|---|---|---|---|
| `backend/tests/evaluation/data/expected/baseline_feasible.v1.json` | **ALREADY FROZEN** | Approved by TASK-011B sign-off (`f274db66…`); golden SHA-256 `2d45ea2291c726460d80b0cbca0a771edda9812aa3a6cb017328af458b65ca73`; production content hash `ea4ab8cd7f73b50c8cd83865adc9ec90428d8d60a9fc2e7d823a0c8fdb16fe46` | **No regeneration, no modification.** This file is the regression anchor. |
| `backend/tests/evaluation/data/expected/high_throughput_review.v1.json` | **NOT YET AUTHORED** | Will require: candidate generation (per §8.1–§8.8) → provenance + hash record → reviewer inspection → separate Charles sign-off → frozen. | Future implementation round ONLY. This contract does NOT authorize creating or modifying this file. |
| `backend/tests/evaluation/data/expected/invalid_blocked.v1.json` | **NOT YET AUTHORED** | Will require: real production validation run → candidate generation → provenance + hash record → reviewer inspection → separate Charles sign-off → frozen. | Future implementation round ONLY. This contract does NOT authorize creating or modifying this file. |

**Critical: merging this contract does NOT authorize either of the two new expected-output files.** Each requires its own sign-off identity, recorded in its own sign-off document under `docs/tasks/TASK-011C-expected-outputs-{scenario_id}-reviewer-sign-off.md`.

---

## 9. Runner contract

The runner (the existing `backend/src/cold_storage/evaluation/execute.py` + `run_directory.py` + future extensions) MUST conform to:

| Property | Contract requirement |
|---|---|
| Manifest validation before side effects | The runner MUST reject an invalid manifest BEFORE any database session / file system side effect, and exit non-zero. |
| One authoritative run-directory implementation | A single, named `execute_in_run_directory` is the only run-directory entry point. No parallel implementations. |
| Scenario isolation | Each scenario runs in its own `RunDirectory` (fresh, isolated). One scenario's side effects MUST NOT affect another scenario's comparison result. |
| Database backend identity | `database_backend` ∈ {`sqlite`, `postgresql`} is part of the run identity. Cross-backend run comparison MUST declare the backend. |
| Typed `run.json` | Per-scenario typed result with: `scenario_id`, `fixture_revision`, `manifest_sha`, `expected_outcome`, `actual_outcome`, `evaluation_result` (`pass` / `fail` / `infrastructure_error`), `diff_summary`, `started_at`, `completed_at`. |
| Typed `summary.json` | Per-suite typed summary with: `suite_id`, `manifest_sha`, `run_identity`, `commit_sha`, `started_at`, `completed_at`, `scenarios[]` (each scenario's `run.json` summary), `evaluation_result_overall`. |
| Raw artifact | The full raw production result, gitignored, persisted to the run-directory. |
| Normalized artifact | The canonical-bytes normalized result (per §10), gitignored, persisted to the run-directory. |
| Exact scenario result accounting | Each scenario's `evaluation_result` is independently classified. A `pass` for one scenario cannot mask a `fail` for another. |
| Non-zero on unexpected mismatch | Any `fail` or `infrastructure_error` results in non-zero process exit. |
| Zero only when all declared scenario contracts match | Process exit zero ONLY when `evaluation_result_overall == "pass"` AND every scenario's `evaluation_result == "pass"`. |

**Allowed distinction (frozen):**

The runner distinguishes:
- `business outcome` — what production actually produced (`SUCCEEDED` / `REVIEW_REQUIRED` / `BLOCKED` / `INVALID`).
- `evaluation result` — whether the runtime result matches the manifest's declared contract (`pass` / `fail` / `infrastructure_error`).
- `infrastructure failure` — runner cannot complete the scenario (DB error, file system error, manifest parse error).

Combinations are allowed:
- `business outcome = "REVIEW_REQUIRED"` + `evaluation_result = "pass"` — the manifest declared a review-required scenario, production produced a review-required result, the diff is consistent. Process exit zero for this scenario.
- `business outcome = "SUCCEEDED"` + `evaluation_result = "fail"` — the manifest declared SUCCEEDED but production produced SUCCEEDED with a different `production_outputs.content_hash` than expected. Non-zero exit.
- `business outcome = "BLOCKED"` + `evaluation_result = "pass"` — the manifest declared a blocked scenario, production blocked at the expected stage with the expected exception class/code. Non-zero exit ONLY if the run-identity mismatch is detected; otherwise the runner can exit zero for this scenario if all others also pass.
- `infrastructure_failure` — non-zero exit, regardless of business outcome.

The manifest MUST declare the expected `business outcome` for each scenario. The runner MUST reject any scenario whose actual `business outcome` does not match the manifest declaration (this is a separate failure mode from numeric / field diffs).

---

## 10. Canonicalization contract (Path A or Path B — see §10.1)

The implementation round MUST resolve the canonicalization authority per **Path A** or **Path B** below. The contract does NOT permit a third option. "Reuse existing canonicalization" without naming the exact module/function and its semantics is **NOT implementable** under this contract.

### 10.1 Path decision (audit completed in this contract round)

After auditing the current main repository, the canonicalization situation is:

**Path A — Unique existing authority** applies if and only if a SINGLE module in current main provides:
- a single, named public function/class for canonicalization;
- typed input/output;
- a stable byte representation used for both persisted normalized artifact and runtime comparison;
- callers that include the manifest validator, the runner, and the expected-output comparison.

**Path B — Main does not provide a complete authority** applies if:
- No such single module exists;
- OR multiple disjoint JSON-normalization helpers exist in different modules with inconsistent semantics;
- OR the existing module lacks typed input/output or stable byte representation.

The current main repository audit (per source-of-truth S10 / S13 / S14) shows: the existing `backend/src/cold_storage/evaluation/execute.py` and `backend/src/cold_storage/evaluation/run_directory.py` provide run-orchestration helpers but **DO NOT** provide a single, named, typed canonicalization authority with stable bytes used for comparison. The architecture boundary tests do not enforce a single canonicalizer either. The local JSON helper utilities that do exist in test files are not the canonicalization authority.

**Therefore the canonicalization decision is: Path B — main does not provide a complete authority.**

### 10.2 Path B contract (FROZEN)

The future TASK-011C implementation round is authorized to create **exactly one** new canonicalization module. The contract freezes:

| Property | FROZEN value |
|---|---|
| Exact future module path | `backend/src/cold_storage/evaluation/canonicalize.py` |
| Public function name | `canonicalize_production_outputs` (frozen; no other public function for canonicalization) |
| Public class name | `Canonicalizer` (frozen dataclass / frozen class for stateful canonicalization, if used) |
| Typed input | `Mapping[str, Any]` (production-path normalized dict) — type hint MUST be present in the public signature |
| Typed output | `bytes` (canonical byte representation) — type hint MUST be present in the public signature |
| `Decimal` handling | `Decimal` values serialized with explicit fixed scale; no scientific notation; no `float()` conversion |
| `NaN` / `Infinity` handling | Reject (raise `CanonicalizationError`) — neither `NaN` nor `Infinity` may appear in canonical bytes |
| Ignored-path handling | Per-scenario `excluded_fields` (manifest-declared, runner-resolved); canonicalizer MUST accept an `excluded_paths: Sequence[str]` argument and MUST NOT silently drop any other path |
| Error behavior | Fail-closed: any uncaught exception during canonicalization propagates to the runner as `CanonicalizationError`, which the runner records as `infrastructure_error` (non-zero exit) |
| Manifest validator caller | `validate_manifest(manifest_bytes) -> Manifest` — produces canonical bytes from raw manifest for manifest_sha computation |
| Runner caller | `canonicalize_production_outputs(normalized_dict, excluded_paths) -> bytes` — produces the persisted normalized artifact bytes |
| Expected-output comparison caller | Same `canonicalize_production_outputs` MUST be used for the expected JSON's `production_outputs` to produce the comparison target bytes; the comparison then operates on these canonical bytes |
| No second canonicalizer | Strictly forbidden. Any helper function that produces JSON byte representation outside `canonicalize.py` MUST route through `canonicalize_production_outputs` |
| No `json.dumps(..., sort_keys=True)` ad-hoc | Strictly forbidden. Any `json.dumps` outside `canonicalize.py` is a hard violation. |

**Path B stop conditions:** if the future implementation round cannot satisfy the Path B contract (e.g., cannot create a single canonicalization module without touching forbidden paths, or finds an existing canonicalization module that satisfies Path A), the round MUST trigger `TASK_011C_CANONICALIZATION_AUTHORITY_REMAINS_AMBIGUOUS` (per §16) and STOP.

### 10.3 Forbidden claims about existing canonicalization (binding)

The contract explicitly **forbids** the following claim patterns in future contract rounds or implementation reports:

- "Main already has a canonicalization module" — without naming a specific module + function + its callers.
- "Reuse existing canonicalization" — without identifying the existing module.
- "The existing canonicalization is `X`" — where `X` is a fragment of `run_directory.py` or `execute.py` that does not actually implement canonicalization.

The local JSON helpers in `backend/tests/evaluation/_seed_helpers.py` and similar test-side utilities are NOT canonicalization authorities. They are test helpers.

### 10.4 Canonicalization properties (general, applies to both Path A and Path B)

| Property | Contract requirement |
|---|---|
| Strict JSON values only | The canonicalizer accepts only JSON-serializable values. No Python tuples, no sets, no custom objects. |
| No `NaN` / `Infinity` | The canonicalizer rejects `NaN` and `Infinity` (or normalizes them — but the contract prefers rejection to silent normalization). |
| Decimal fixed-scale representation | `Decimal` values are serialized with a fixed scale (per comparison policy `decimal_fields`). No scientific notation. |
| Exact array order | Arrays are serialized in declared order. Reordering during normalization is forbidden. |
| Ignored paths declared and justified | Every path in `excluded_fields` has a justification string recorded in the manifest's `comparison_policy.excluded_fields` array. No "ignore everything in `production_outputs`" blanket rules. |
| No broad floating-point tolerance | `decimal_fields` carry an explicit decimal scale. No `"tolerance": 0.01"` blanket rules. |
| Canonical bytes used for persisted normalized artifact and comparison | The normalized artifact is serialized to canonical bytes (per the canonicalizer). The comparison reads the canonical bytes, not the in-memory dict. |
| SHA-256 over the same canonical bytes | The `content_hash` field of the expected JSON is SHA-256 of the canonical bytes of the expected JSON itself (self-hash for tamper detection). |
| Policy metadata vs executable policy consistency | The manifest's `comparison_policy` is parseable, machine-readable, and matches the runner's executable comparison logic byte-for-byte. Drift is a hard failure. |

---

## 11. Runner + run-artifact contract

### 11.0 Current main behavior vs future TASK-011C contract (READ-ONLY clarification)

The current main `backend/src/cold_storage/evaluation/run_directory.py` provides:
- `RunDirectory` (a path-construction helper that computes a per-scenario directory path)
- `execute_in_run_directory(...)` (a context manager that creates the path and yields a working directory)
- `_validate_scenario_id` (input validation helper)

**Current main behavior** (READ-ONLY audit):
- `RunDirectory` only **computes the path** to a per-scenario directory.
- The current main runner does **NOT** write a `run.json` artifact, does **NOT** write a `summary.json` artifact, does **NOT** write a normalized artifact, and does **NOT** write a raw artifact.
- The current main execution in `execute.py` records the run outcome in memory and returns the typed result to the caller. The `RunDirectory` context manager is used for filesystem isolation but not for persisted artifact output.

**The contract does NOT misdescribe current behavior as already writing `run.json` or `summary.json`.** The contract describes the **FUTURE TASK-011C IMPLEMENTATION CONTRACT** for what the runner will write.

### 11.1 `run.json` schema (FROZEN, future implementation)

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | string | yes | `task011c-run.v1` |
| `run_identity` | string | yes | SHA-256 hex digest of (manifest_sha + code_commit_sha + scenario_id + started_at_nanos + uuid) |
| `scenario_id` | string | yes | matches manifest `scenarios[i].scenario_id` |
| `manifest_path` | string | yes | relative path to the manifest file used for this run |
| `manifest_sha256` | string | yes | SHA-256 hex digest of the manifest canonical bytes |
| `code_commit_sha` | string | yes | SHA-1 hex of the code HEAD commit at run time |
| `database_backend` | enum | yes | `sqlite` or `postgresql` |
| `started_at` | string (ISO-8601 UTC) | yes | start timestamp |
| `completion_state` | enum | yes | `in_progress` / `completed` / `failed` / `incomplete` |
| `input_authority` / `fixture_authority` | object | yes | fixture path, fixture revision, fixture SHA-256 |
| `expected_output_authority` | object | conditional | required if manifest declared expected output; path, revision, SHA-256, sign-off identity |

### 11.2 `summary.json` schema (FROZEN, future implementation)

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | string | yes | `task011c-summary.v1` |
| `run_identity` | string | yes | matches `run.json.run_identity` |
| `scenario_id` | string | yes | matches manifest `scenarios[i].scenario_id` |
| `execution_outcome` | enum | yes | `SUCCEEDED` / `REVIEW_REQUIRED` / `BLOCKED` / `INVALID` / `FAILED` / `INFRASTRUCTURE_ERROR` |
| `scheme_status` | enum | yes | `completed` / `blocked` / `not_created` |
| `requires_review` | bool | yes | matches production path result |
| `review_state` | enum | yes | `NOT_REQUIRED` / `REQUIRED` / `NOT_APPLICABLE` |
| `comparison_result` | enum | yes | `pass` / `fail` / `not_applicable` |
| `error_or_blocker_result` | object | conditional | typed exception class FQN + code + field; required when `execution_outcome` is `BLOCKED` / `INVALID` / `FAILED` |
| `raw_artifact_sha256` | string | yes | SHA-256 of the raw production-path output |
| `normalized_artifact_sha256` | string | yes | SHA-256 of the canonical-bytes normalized output (per §10) |
| `expected_output_sha256` | string | conditional | SHA-256 of the expected JSON file; required when manifest declared expected output |
| `completed_at` | string (ISO-8601 UTC) | yes | end timestamp |

### 11.3 Run-artifact semantics (FROZEN, future implementation)

| Property | Contract requirement |
|---|---|
| Single writer ownership | A single, named writer class is the only writer of `run.json` and `summary.json`. No parallel writer implementations. |
| Atomic write | Each artifact is written to a temp file in the same directory, fsync'd, then atomically renamed. The `rename` is the publish operation. |
| `incomplete` state | If the runner crashes mid-run, the on-disk artifact is left in `completion_state = "incomplete"` (or absent). The runner never partially writes a `completed` artifact. |
| Success-completion marker | `completion_state = "completed"` is set only after all fields are fully populated and the artifact has been atomically renamed. |
| Manifest SHA binding | `run.json.manifest_sha256` MUST equal the manifest's canonical-bytes SHA-256. Mismatch fails closed. |
| Commit SHA binding | `run.json.code_commit_sha` MUST equal the code HEAD SHA at run time. The runner reads this from a frozen env var or git resolution at run start, not from the artifact itself. |
| Failure-state files | On runner infrastructure failure, the on-disk artifact is `completion_state = "failed"` or `"incomplete"`. The runner does NOT write a `summary.json` with `comparison_result = "pass"` for a failed scenario. |
| Stale-output rejection | A `run.json` / `summary.json` from a prior run-directory MUST NOT satisfy the current manifest. The runner refuses to read prior artifacts. |
| Per-scenario isolated directory | Each scenario runs in its own per-scenario subdirectory under the suite root. No shared state. |
| Rerun cleanup | The runner cleans the per-scenario subdirectory on entry (success / failure / exception paths). The cleanup is part of the `finally` block. |
| Manifest / expected-output SHA mismatch | If the on-disk expected output's SHA-256 does not match the manifest's declared expected-output SHA-256, the runner fails closed and records `INFRASTRUCTURE_ERROR` with a typed reason. |

---

## 12. SQLite / PostgreSQL boundary (field-by-field parity, FROZEN)

### 12.0 Field-by-field parity table (FROZEN)

The contract freezes the per-field parity between SQLite and PostgreSQL runs of the same scenario. Fields are listed in two categories: **must-match** (business-authoritative) and **may-differ** (backend-specific or runtime).

#### 12.0.1 Must-match fields (business-authoritative)

The following fields MUST be byte-identical (or `decimal_fields`-quantization-equal) across SQLite and PostgreSQL runs of the same scenario. The runner MUST reject any scenario where these fields differ.

| Field | JSON path | Notes |
|---|---|---|
| `scenario_id` | `summary.scenario_id` | matches manifest |
| Manifest schema/version | `summary.manifest_schema_version` | matches manifest |
| `execution_outcome` | `summary.execution_outcome` | `SUCCEEDED` / `REVIEW_REQUIRED` / `BLOCKED` / `INVALID` / `FAILED` |
| Scheme business status | `summary.scheme_status` | `completed` / `blocked` / `not_created` |
| `requires_review` | `summary.requires_review` | bool |
| `review_state` | `summary.review_state` | `NOT_REQUIRED` / `REQUIRED` / `NOT_APPLICABLE` |
| Comparison classification | `summary.comparison_result` | `pass` / `fail` / `not_applicable` |
| Deterministic calculated values | `summary.normalized_artifact_sha256` | SHA-256 of canonical bytes — must match |
| Source/content hashes | `summary.raw_artifact_sha256`, `summary.normalized_artifact_sha256`, `summary.expected_output_sha256` | must match (when applicable) |
| Blocker/error code | `summary.error_or_blocker_result.code` | must match (when applicable) |
| Blocker/error field | `summary.error_or_blocker_result.field` | must match (when applicable) |
| Expected-output match result | `summary.comparison_result` + per-leaf diff | must match |

#### 12.0.2 May-differ fields (backend-specific or runtime, must be normalized or excluded)

The following fields MAY differ between SQLite and PostgreSQL runs of the same scenario. For each, the contract requires an explicit JSON path, a reason for exclusion, a normalization rule, and a proof that the field is not business-authoritative.

| Field | JSON path | Reason | Normalization / exclusion rule | Business-authoritative? |
|---|---|---|---|---|
| `database_backend` | `summary.database_backend` | Backend identity is a tag, not a result. | Record as declared; comparison excludes this field. | NO (tag) |
| Generated database primary keys | any `*_id`, `database_session_uuid`, `run_id` | DB-generated, not part of business outcome. | Excluded from comparison; SHA-256 of normalized output still depends on these for raw artifact, but the `summary.normalized_artifact_sha256` is the same because normalization replaces these. | NO (DB-generated) |
| Backend-specific timestamps | `run.started_at` (precise nanos) | Wall-clock may differ; only `completed_at` to nearest second matters for cross-backend comparison. | Round to nearest second before comparison. | NO (clock skew) |
| Database URL | env var `DATABASE_URL` | Not part of output. | Not recorded in artifact. | NO (env) |
| Transaction / internal sequence values | `orchestration.attempt_internal_seq`, `*_audit_seq` | Internal counters. | Excluded from comparison. | NO (internal) |
| Backend-specific diagnostic text | `error_or_blocker_result.engine_diagnostic` (if any) | Engine-version specific. | Stripped from canonical bytes. | NO (diagnostic) |

**Prohibition:** It is **forbidden** to manufacture SQLite/PG parity by deleting many fields from the comparison. Any excluded field MUST be enumerated in the table above with its exact JSON path, reason, normalization rule, and proof of non-business-authority.

### 12.1 Boundary contract (general)

| Boundary | Contract requirement |
|---|---|
| SQLite — full TASK-011C scenario acceptance | All TASK-011C scenarios (`baseline_feasible`, `high_throughput_review`, `invalid_blocked`) MUST pass on SQLite in the `backend-sqlite` CI job. |
| PostgreSQL — required where persistence, transaction, uniqueness, ordering, JSON behavior, or backend parity may differ | All TASK-011C scenarios MUST also pass on PostgreSQL in the `backend-postgresql` CI job. |
| Substantive normalized result parity | The canonical bytes of the normalized SQLite result and the canonical bytes of the normalized PostgreSQL result MUST be byte-identical for `exact_match_fields` and `decimal_fields`; `excluded_fields` may differ per the table above. |
| Allowed backend-specific runtime metadata | The runner may record backend-specific runtime metadata in `excluded_fields` per §12.0.2. |
| Forbidden backend-specific business outcome drift | The runner MUST reject any scenario whose business-authoritative field (per §12.0.1) differs between SQLite and PostgreSQL (e.g., `SUCCEEDED` on SQLite but `BLOCKED` on PostgreSQL for the same scenario). |

---

## 13. Future implementation allowlist proposal (NOT YET AUTHORIZED)

This contract proposes the following allowlist for a future TASK-011C implementation round. This round does NOT modify any of these files.

| Path | Purpose | Round scope |
|---|---|---|
| `backend/src/cold_storage/evaluation/manifest.py` (new) | Manifest schema + loader + validator | C-1 (manifest schema) |
| `backend/src/cold_storage/evaluation/canonicalize.py` (new) | Standalone canonicalizer (if not already a separate module) | C-1 (manifest schema) |
| `backend/src/cold_storage/evaluation/sqlite_scope.py` (new) | Per-scenario SQLite isolation | C-1 (manifest schema) |
| `backend/src/cold_storage/evaluation/paths.py` (new) | Path safety helpers | C-1 (manifest schema) |
| `backend/src/cold_storage/evaluation/models.py` (new) | Pydantic models for manifest / run.json / summary.json | C-1 (manifest schema) |
| `backend/src/cold_storage/evaluation/compare.py` (new) | Comparison policy executor | C-1 (manifest schema) |
| `backend/src/cold_storage/evaluation/evaluate.py` (new) | Multi-scenario runner | C-2 (runner) |
| `backend/src/cold_storage/evaluation/json_path.py` (new) | JSON path utilities | C-2 (runner) |
| `backend/src/cold_storage/evaluation/runners/sqlite.py` (new) | SQLite-specific runner | C-2 (runner) |
| `backend/src/cold_storage/evaluation/runners/postgresql.py` (new) | PostgreSQL-specific runner | C-2 (runner) |
| `backend/tests/evaluation/test_manifest_schema.py` (new) | Manifest schema tests | C-1 (manifest schema) |
| `backend/tests/evaluation/test_manifest_loader.py` (new) | Manifest loader tests | C-1 (manifest schema) |
| `backend/tests/evaluation/test_canonicalize.py` (new) | Canonicalizer tests | C-1 (manifest schema) |
| `backend/tests/evaluation/test_compare.py` (new) | Compare policy tests | C-1 (manifest schema) |
| `backend/tests/evaluation/test_json_path.py` (new) | JSON path tests | C-2 (runner) |
| `backend/tests/evaluation/test_path_safety.py` (new) | Path safety tests | C-1 (manifest schema) |
| `backend/tests/evaluation/test_run_directory.py` (new) | Run-directory tests | C-2 (runner) |
| `backend/tests/evaluation/test_run_directory_identity.py` (new) | Run identity tests | C-2 (runner) |
| `backend/tests/evaluation/test_sqlite_acceptance.py` (extend) | Add C-scenario tests | C-2 (runner) |
| `backend/tests/evaluation/test_postgresql_acceptance.py` (extend) | Add C-scenario tests | C-2 (runner) |
| `backend/tests/evaluation/data/expected/high_throughput_review.v{revision}.json` (new, tracked) | High-throughput expected output | C-3 (expected output) — REQUIRES sign-off |
| `backend/tests/evaluation/data/expected/invalid_blocked.v{revision}.json` (new, tracked) | Invalid-blocked expected output | C-3 (expected output) — REQUIRES sign-off |
| `docs/tasks/TASK-011C-expected-outputs-high_throughput_review-reviewer-sign-off.md` (new, tracked) | Sign-off document | C-3 (expected output) |
| `docs/tasks/TASK-011C-expected-outputs-invalid_blocked-reviewer-sign-off.md` (new, tracked) | Sign-off document | C-3 (expected output) |
| `docs/tasks/TASK-011-evaluation-pilot-readiness.md` (new, tracked) | Pilot doc (currently missing from main) | C-1 (manifest schema) — if extracted from PR #21 |
| `docs/tasks/TASK-011C-manifest-schema-design.md` (new, tracked) | Manifest schema design contract | C-1 (manifest schema) — separate Charles authorization |

**Forbidden paths (any mutation is a hard violation):**
- `backend/src/cold_storage/modules/coefficients/**` — Phase 1-4 production code
- `backend/src/cold_storage/modules/orchestration/application/production_calculation/**` — Phase 1-4 production code
- `backend/alembic/versions/0035-0038*` — Phase 1-4 migrations
- `docs/tasks/TASK-011B-*` (except for read-only references)
- `docs/tasks/TASK-019-*` (except for read-only references)
- `backend/src/cold_storage/evaluation/production_seeding.py` — explicitly forbidden, must not be restored
- `backend/src/cold_storage/evaluation/adapter.py` — A1-2a adapter is frozen, no extension
- `backend/src/cold_storage/evaluation/execute.py` — A1-2a executor is frozen, no extension (new code lives in `evaluate.py` / `runners/`)
- `.github/**` — CI workflow not modified
- `docker-compose*` — Docker not modified
- `pyproject.toml`, `uv.lock` — dependencies not modified
- `.gitignore` modifications — proposed only with explicit per-path allowlist and Charles sign-off
- `README.md`, `CODEX_TASKS.md` — top-level project files not modified
- `docs/roadmap/**` — roadmap not modified

---

## 14. Explicit TASK-011D exclusions (frozen)

The following are **reserved for TASK-011D** or a separate closure gate and are **NOT** in this contract:

- zh-CN / en-US multilingual report evaluation
- Sample knowledge / document scenario
- Frontend demo path
- Pilot runbook
- Operator instructions
- Issue #20 final closure
- Task 12 productionization

If a future round attempts to absorb any of these into TASK-011C, it is a scope violation and the round must stop.

---

## 15. Forbidden actions (binding)

The future TASK-011C implementation round is **forbidden** from:

1. Restoring `production_seeding.py` (or any equivalent evaluation-owned production seeding).
2. Creating any production ORM row from the evaluation layer (e.g., `Session.add(CalculationRunRecord(...))`, `session.flush()` on a production table, `bulk_insert_mappings` against production tables).
3. Directly constructing any `CalculationRunRecord` instance.
4. Bypassing production services (e.g., calling a calculator directly instead of going through the production orchestrator).
5. Modifying any engineering formula, coefficient value, threshold, scoring rule, or review rule.
6. Modifying the baseline golden (`backend/tests/evaluation/data/expected/baseline_feasible.v1.json`) or its sign-off (`docs/tasks/TASK-011B-path-a-expected-outputs-reviewer-sign-off.md`).
7. Modifying PR #21 (state, draft, head, base, comments, reviews, files, branch, force-push).
8. Modifying PR #23 (state, draft, head, base, comments, reviews, files, branch, force-push).
9. Closing Issue #20.
10. Starting Task 12 work.
11. Cherry-picking, merging, restoring, or copying any file from PR #21's branch.
12. Extracting or committing PR #23's 1,728-line design document.
13. Authoring any expected output without the §8 authority flow.
14. Using `git add -f`, `update-golden` subcommand, or self-approval.
15. Creating a second canonicalizer (reuse the existing authoritative one).
16. Building a runner that can produce zero-exit while a `fail` scenario is unaccounted for.

---

## 16. Stop conditions (binding)

The future TASK-011C implementation round MUST stop and report a BLOCKER if any of the following is detected:

1. **High-throughput source definition 不足** — no production pathway produces a substantively distinct result for any permitted input variation. (§6.2)
2. **Expected production outcome 不明确** — the manifest cannot be authored with a specific `business outcome` for a scenario. (§6, §9)
3. **跨后端业务输出不一致** — SQLite and PostgreSQL produce different `business outcome` for the same scenario. (§12)
4. **新增 fixture 需要生产公式修改** — the fixture requires a formula / coefficient / threshold / scoring change. (§15.5)
5. **需要 evaluation-owned ORM fabrication** — the scenario cannot be expressed via the adapter + production orchestrator. (§15.2, §15.3)
6. **需要恢复 `production_seeding.py`** — the implementation cannot avoid evaluation-owned production seeding. (§15.1)
7. **Manifest 与当前 runner contract 冲突** — the proposed manifest schema is incompatible with the existing `execute_in_run_directory` / adapter contract. (§9)
8. **无法确定 expected-output authority** — no Charles sign-off can be obtained for the new expected output. (§8)
9. **当前 main source drift 改变设计前提** — `main` has advanced since `1636f25d4…` and the new commits change the production-path behavior such that the contract's source-of-truth matrix (§5) is no longer accurate. (§1)
10. **Cross-backend substantive comparison fails** — SQLite and PostgreSQL produce non-ignorable diff in `exact_match_fields` or `decimal_fields` for the same scenario. (§8.4, §12)
11. **PR #21 / PR #23 mutation required** — the implementation cannot proceed without touching PR #21 or PR #23. (§15.7, §15.8)
12. **Baseline regression** — the proposed changes regress the `baseline_feasible` scenario. (§6.1)

A stop condition is a hard round-end. The implementation round must produce a `BLOCKED` report, NOT a partial implementation.

**Review-round additions (P0 / explicit):** The following stop conditions are binding on the future implementation round and were added in response to the Issue #20 review comment `4949858037`:

| # | Stop condition | Trigger |
|---|---|---|
| S13 | `TASK_011C_INVALID_BLOCKED_PRODUCTION_PATH_NOT_ESTABLISHED` | Production code cannot provide a real validation pathway that produces a typed exception / structured error result. |
| S14 | `TASK_011C_HIGH_THROUGHPUT_REQUIRES_REVIEW_PRODUCTION_RULE_MUTATION` | To produce `requires_review=true` and `review_state=REQUIRED` for `high_throughput_review`, a production formula / threshold / coefficient / scoring / review rule change would be required. |
| S15 | `TASK_011C_CANONICALIZATION_AUTHORITY_REMAINS_AMBIGUOUS` | After Path A / Path B audit, the canonicalization authority cannot be resolved to a single, named, typed module. |
| S16 | `TASK_011C_MANIFEST_SCHEMA_PATH_CONFLICTS` | The required manifest schema path `backend/src/cold_storage/evaluation/schema/manifest.schema.json` cannot be created without modifying forbidden paths (top-level `evaluation/`, `.gitignore`). |
| S17 | `TASK_011C_BASELINE_GOLDEN_MODIFICATION_REQUIRED` | Any future implementation would require modification of the frozen `baseline_feasible.v1.json` golden. |
| S18 | `TASK_011C_EXPECTED_OUTPUT_AUTHORED_WITHOUT_SEPARATE_SIGNOFF` | A new expected-output file is authored or proposed for commit without the separate Charles sign-off required by §8.10. |
| S19 | `TASK_011C_PR21_OR_PR23_MUTATION_REQUIRED` | The implementation cannot proceed without touching PR #21 or PR #23 (state, draft, head, base, comments, reviews, files, branch, force-push). |
| S20 | `TASK_011C_SCOPE_DRIFT_TO_TASK011D_OR_TASK12` | A future implementation round attempts to absorb TASK-011D scope (multilingual / sample doc / pilot runbook / frontend demo / Issue #20 closure) or Task 12 scope. |
| S21 | `TASK_011C_REMOTE_COMMIT_CANNOT_BE_ESTABLISHED` | The contract commit cannot be pushed to a GitHub-visible branch. |
| S22 | `TASK_011C_CONTRACT_SOURCE_CONFLICTS_WITH_MAIN` | The contract's source-of-truth matrix (§5) becomes inconsistent with the current main (e.g., new commits change evaluation module structure). |
| S23 | `TASK_011C_HIGH_THROUGHPUT_SUBSTANTIVE_INVARIANT_UNIDENTIFIED` | No production pathway produces a substantively distinct result for the `high_throughput_review` scenario without violating the substantively-distinct invariants of §6.2. |

---

## 17. Validation (docs-only, this round)

This round is docs-only. The contract is validated by:

- `git diff --check` on the working tree — empty
- `git status --short` on the working tree — empty
- `git diff --name-only origin/main...HEAD` — exactly 1 file: `docs/tasks/TASK-011C-remaining-evaluation-scenarios-contract.md`
- `git diff --stat origin/main...HEAD` — 1 file changed, +N/-0 (additions only)
- Forbidden-path scan (§13) — no path outside `docs/tasks/TASK-011C-*.md` appears in the diff

This round does NOT run pytest, does NOT execute the runner, does NOT call production services, does NOT author any expected output.

---

## 18. Commit, push, and Draft PR (docs-only)

This round produces:

- **Branch:** `docs/task-011c-remaining-evaluation-scenarios-contract`
- **Base SHA:** `1636f25d4b6fafa38bfc9747938d0cba8b2abf50` (= `origin/main` HEAD at this round)
- **Commit message (suggested):** `docs(task-011c): freeze remaining evaluation scenario contract`
- **Push target:** `origin HEAD:refs/heads/docs/task-011c-remaining-evaluation-scenarios-contract`
- **Draft PR title (suggested):** `TASK-011C: freeze remaining evaluation scenarios contract`
- **Draft PR body MUST include:**
  - `docs-only`
  - `implementation not authorized`
  - `expected-output authoring not authorized`
  - `PR #21 untouched`
  - `PR #23 untouched`
  - `Issue #20 remains open`
  - `TASK-011D not started`
  - `Task 12 not authorized`
  - `Ready not authorized`
  - `Merge not authorized`
- **Ready:** NOT authorized (Draft only)
- **Merge:** NOT authorized

This round's commit, push, and Draft PR creation are the ONLY mutations performed. No file outside `docs/tasks/TASK-011C-remaining-evaluation-scenarios-contract.md` is modified.

---

## 19. Feishu report (this round's delivery)

A Feishu card is sent to the `hxforge-agent` group (chat_id `oc_7807111a5c0ff61a9d1469030d87adb0`) summarizing:

- `main SHA = 1636f25d4b6fafa38bfc9747938d0cba8b2abf50`
- `branch = docs/task-011c-remaining-evaluation-scenarios-contract`
- `commit SHA = <created commit SHA>`
- `changed files = 1 (docs/tasks/TASK-011C-remaining-evaluation-scenarios-contract.md)`
- `contract section count = 19 (this document)`
- `TASK-011C implementation not authorized`
- `PR #21 preserved Open / Draft / Not merged`
- `PR #23 preserved as historical design authority (Open / Draft / Not merged)`
- `Issue #20 remains open`
- `Task 12 not authorized`
- `Draft PR number and URL = <created Draft PR>`
- `repository mutation exact count = 1 file added (this contract)`

---

## 20. Final verdict (this round)

**Round status: `TASK_011C_CONTRACT_AUTHORED_PENDING_REVIEW`** (this round corrects the previous round's draft against the Issue #20 review comment `4949858037`).

```
TASK_011C_CONTRACT_REVIEW_CORRECTIONS_COMPLETED
TASK_011C_DOCS_ONLY_COMMIT_PUSHED
TASK_011C_DRAFT_PR_CREATED
TASK_011C_CONTRACT_AUTHORED_PENDING_REVIEW
TASK_011C_CONTRACT_NOT_FROZEN
TASK_011C_IMPLEMENTATION_NOT_AUTHORIZED
PR21_SUPERSEDED_OPEN_DRAFT_NOT_MERGED
PR21_UNTOUCHED
PR23_RETAINED_AS_HISTORICAL_DESIGN_AUTHORITY
PR23_UNTOUCHED
ISSUE20_REMAINS_OPEN
TASK011D_NOT_AUTHORIZED
TASK12_NOT_AUTHORIZED
READY_NOT_AUTHORIZED
MERGE_NOT_AUTHORIZED
```

If main source drift is detected (main advanced and the new commits change TASK-011C source assumptions):

```
TASK_011C_CONTRACT_AUTHORING_BLOCKED
MAIN_SOURCE_DRIFT_AFFECTS_CONTRACT
NO_COMMIT_CREATED
NO_PR_CREATED
PR21_PR23_UNTOUCHED
ISSUE20_REMAINS_OPEN
```

If the remote push or Draft PR creation fails, the round reports a `TASK_011C_REMOTE_PUSH_FAILED` / `TASK_011C_DRAFT_PR_CREATION_BLOCKED` BLOCKER and does NOT claim completion.

**Lifecycle reminder:** A `Draft PR created` state is NOT the same as `contract frozen`. The contract is only `frozen` after Charles sign-off. This round is at the `authored` / `committed and pushed` / `Draft PR created` stage.

---

## 21. Change log

| Round | Date | Author | Change |
|---|---|---|---|
| Initial authoring | 2026-07-12 | Hermes | Initial authoring of TASK-011C remaining evaluation scenarios contract (NOT frozen at this stage) |
| Review-correction round | 2026-07-12 | Hermes | Corrected against Issue #20 review comment `4949858037` (P0 + 8 required contract corrections). Changes: §1 status wording (authored pending review, not frozen); §6.2 high-throughput exact four business fields + real-production review signal; §6.3 invalid_blocked field-by-field freeze + fail-closed; §7.0 manifest schema single-path freeze; §7.1 CLI exit codes frozen (no redefinition); §8.10 per-file expected-output authority; §10 Path A/B canonicalization decision (Path B chosen); §11 current-main-vs-future contract for run.json/summary.json; §12 field-by-field SQLite/PG parity; §16 added 11 review-round stop conditions (S13–S23); §20 final verdict lifecycle wording |
