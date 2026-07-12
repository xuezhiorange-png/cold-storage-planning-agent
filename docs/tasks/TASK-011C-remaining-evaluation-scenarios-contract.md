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

A new scenario `high_throughput_review` that **MUST** be substantively distinct from `baseline_feasible`. The contract freezes the following properties:

| Property | Contract requirement |
|---|---|
| `scenario_id` | `high_throughput_review` (string, no spaces) |
| `fixture_revision` | positive integer (≥ 1) |
| Substantive input differences from baseline | REQUIRED (see below) |
| Expected production outcome | `SUCCEEDED` (production run completes) **OR** explicitly frozen alternative |
| Expected review/blocker propagation | REQUIRED — must declare whether `review_required: true` and what `review_reasons` are expected |
| Required production stages | `["zone", "cooling_load", "equipment", "power", "investment"]` (same as baseline) |
| Required exact fields | All `exact_match_fields` of baseline, plus any scenario-specific additional fields |
| Required numeric fields | All `decimal_fields` of baseline, plus any scenario-specific additional fields |
| Runtime-only excluded fields | `["correlation_id", "run_attempt_id", "executed_at_timestamp", "database_session_uuid", "calculation_run_id[]"]` (or explicitly justified per-scenario) |
| SQLite/PostgreSQL equivalence | `substantive normalized result parity` required; backend-specific runtime metadata allowed |

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

A new scenario `invalid_blocked` that exercises a **real production validation/blocker pathway**. The contract freezes:

| Property | Contract requirement |
|---|---|
| `scenario_id` | `invalid_blocked` |
| `fixture_revision` | positive integer (≥ 1) |
| Fixture input defect | A SPECIFIC pre-existing production validation defect (NOT a runtime exception, NOT an evaluation-layer-injected error) |
| Production validation entrypoint | A pre-existing production entrypoint in `backend/src/cold_storage/modules/...` that raises a typed exception (NOT `Exception` / NOT `BaseException`) |
| Expected exception class | A specific, pre-existing production exception class — must be enumerated by class FQN |
| Stable code | A specific exception code / marker that the production code already emits |
| Field | The exception's structured field that identifies the failure (e.g., `field` in a `ValidationError`) |
| Details shape | A pre-existing structured `details` dict on the exception; no new shape is allowed |
| Blocked stage | One of `["zone", "cooling_load", "equipment", "power", "investment", "pre_orchestration", "source_binding_verification"]` |
| Side-effect expectations | The blocked stage MUST NOT create a `SchemeRun` row, MUST NOT create `CalculationRunRecord` rows beyond the stage that raised, and MUST leave orchestration identity / attempt / execution-snapshot state consistent with production's pre-block policy |
| Absence of success artifacts | The normalized result MUST NOT contain `production_outputs` beyond the stage that raised; runner MUST assert absence |
| CLI exit semantics | Non-zero exit; typed `RunnerSummary.evaluation_result = "fail"`; typed reason code for the validation defect |

**INVALID_BLOCKED_FORBIDDEN (frozen invariants):**

The implementation round is **forbidden** from:
- Adding new business validation rules in the evaluation layer.
- Using a broad `except Exception` to convert any error into an expected blocker.
- Using a fixture that does NOT trigger a real production validation defect.
- Mocking / stubbing the production validation entrypoint to return a synthetic exception.
- Producing a `invalid_blocked` expected output that asserts presence of `production_outputs` past the blocked stage.

---

## 7. Manifest contract

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

## 8. Expected-output authority flow

The expected output for a new scenario is **not** a product of the implementation round. The contract freezes the following 8-step authority flow:

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

## 10. Canonicalization contract

The implementation round MUST reuse the existing authoritative canonicalization, not build a second canonicalizer. The contract freezes:

| Property | Contract requirement |
|---|---|
| Strict JSON values only | The canonicalizer accepts only JSON-serializable values. No Python tuples, no sets, no custom objects. |
| No `NaN` / `Infinity` | The canonicalizer rejects (or normalizes) `NaN` and `Infinity` to `null` / `0` / explicit error. The current main canonicalizer does NOT emit `NaN` / `Infinity`. |
| Decimal fixed-scale representation | `Decimal` values are serialized with a fixed scale (per comparison policy `decimal_fields`). No scientific notation. |
| Exact array order | Arrays are serialized in declared order. Reordering during normalization is forbidden. |
| Ignored paths declared and justified | Every path in `excluded_fields` has a justification string recorded in the manifest's `comparison_policy.excluded_fields` array. No "ignore everything in `production_outputs`" blanket rules. |
| No broad floating-point tolerance | `decimal_fields` carry an explicit decimal scale. No `"tolerance": 0.01"` blanket rules. |
| Canonical bytes used for persisted normalized artifact and comparison | The normalized artifact is serialized to canonical bytes (per the canonicalizer). The comparison reads the canonical bytes, not the in-memory dict. |
| SHA-256 over the same canonical bytes | The `content_hash` field of the expected JSON is SHA-256 of the canonical bytes of the expected JSON itself (self-hash for tamper detection). |
| Policy metadata vs executable policy consistency | The manifest's `comparison_policy` is parseable, machine-readable, and matches the runner's executable comparison logic byte-for-byte. Drift is a hard failure. |

The existing `canonicalize` module in main (per S10 / S13) is the authoritative implementation. The contract explicitly **forbids** building a second canonicalizer (e.g., "for high-throughput only" or "for invalid-blocked only"). All three scenarios use the same canonicalizer.

---

## 11. Cleanup + stale-output contract

| Property | Contract requirement |
|---|---|
| Per-scenario isolated SQLite state | Each scenario's SQLite run uses a fresh, isolated database (file or `:memory:` scoped to the run-directory). No shared SQLite state across scenarios. |
| PostgreSQL isolation strategy | Each scenario's PostgreSQL run uses either a fresh schema (`CREATE SCHEMA … SET search_path = …`) or a transaction-scope (`SET TRANSACTION ISOLATION LEVEL SERIALIZABLE` + `ROLLBACK` after scenario). The strategy is declared in the manifest's per-scenario `isolation_strategy` field. |
| Temporary DB ownership | The runner OWNS the temporary database (SQLite file or PG schema) and is responsible for cleanup in all paths (success / failure / exception). No caller is expected to clean up. |
| Cleanup in success / failure / exception paths | The runner's `finally` block (or equivalent) deletes the SQLite file, drops the PG schema, and removes the run-directory. Cleanup failures are recorded as `infrastructure_error` with a typed reason. |
| Stale prior run cannot satisfy current manifest | The runner MUST refuse to read a `run.json` / `summary.json` / normalized artifact from a prior run-directory. The run-directory is created fresh per scenario, identified by a fresh `run_identity` (UUIDv4 + scenario_id + manifest_sha + commit_sha). |
| Run identity binds manifest SHA | The run identity is `sha256(manifest_sha + commit_sha + scenario_id + started_at_nanos + uuid)`. The runner rejects a scenario whose `run_identity` does not match the current `manifest_sha`. |
| Summary identity binds run / manifest / suite / scenarios / backend / commit | The summary.json's identity is the hash of the sorted concatenation of all `run.json` identities + the `manifest_sha` + `commit_sha`. |
| Generated artifacts never treated as repository-owned golden | All `run.json`, `summary.json`, `candidate.*.json`, normalized artifacts, raw artifacts, and run-directories are gitignored. They MUST NOT be committed. |
| Cleanup proof by deterministic resource / file existence test | The contract explicitly **forbids** requiring long-running repeated full pytest to prove cleanup. Cleanup is proven by deterministic resource tests (e.g., "after runner exits, the SQLite file is gone", "after runner exits, the PG schema does not exist", "the run-directory is empty"). |

---

## 12. SQLite / PostgreSQL boundary

| Boundary | Contract requirement |
|---|---|
| SQLite — full TASK-011C scenario acceptance | All TASK-011C scenarios (`baseline_feasible`, `high_throughput_review`, `invalid_blocked`) MUST pass on SQLite in the `backend-sqlite` CI job. |
| PostgreSQL — required where persistence, transaction, uniqueness, ordering, JSON behavior, or backend parity may differ | All TASK-011C scenarios MUST also pass on PostgreSQL in the `backend-postgresql` CI job. |
| Substantive normalized result parity | The canonical bytes of the normalized SQLite result and the canonical bytes of the normalized PostgreSQL result MUST be byte-identical for `exact_match_fields` and `decimal_fields`; `excluded_fields` may differ (e.g., `database_session_uuid`). |
| Allowed backend-specific runtime metadata | The runner may record backend-specific runtime metadata (e.g., `database_backend`, `engine_version`) in `excluded_fields`. |
| Forbidden backend-specific business outcome drift | The runner MUST reject any scenario whose `business outcome` differs between SQLite and PostgreSQL (e.g., `SUCCEEDED` on SQLite but `BLOCKED` on PostgreSQL for the same scenario). |

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

```
TASK_011C_REMAINING_EVALUATION_SCENARIOS_CONTRACT_AUTHORED
DOCS_ONLY_COMMIT_CREATED
DRAFT_PR_CREATED
PR21_SUPERSEDED_OPEN_DRAFT_NOT_MERGED
PR23_RETAINED_AS_HISTORICAL_DESIGN_AUTHORITY
ISSUE20_REMAINS_OPEN
TASK011C_IMPLEMENTATION_NOT_AUTHORIZED
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

This round ends after the commit + push + Draft PR creation + Feishu report. The future TASK-011C implementation round requires separate Charles authorization and is NOT in this round.

---

## 21. Change log

| Round | Date | Author | Change |
|---|---|---|---|
| Initial freeze | 2026-07-12 | Hermes | First freeze of TASK-011C remaining evaluation scenarios contract |
