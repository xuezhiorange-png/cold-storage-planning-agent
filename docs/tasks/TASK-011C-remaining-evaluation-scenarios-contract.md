# TASK-011C Remaining Evaluation Scenarios — Draft Contract

**Status:** `TASK_011C_MAINTAINER_AUTHORITY_ESTABLISHED` / `TASK_011C_CONTRACT_NOT_FROZEN` / D3 + D9 audits completed, pending Charles decision
**Branch base:** `main @ 1636f25d4b6fafa38bfc9747938d0cba8b2abf50` (= `origin/main` HEAD)
**Branch name (this round):** `docs/task-011c-remaining-evaluation-scenarios-contract`
**Draft PR:** #61 (Open / Draft / Not merged)
**Authoritative references (binding maintainer authority):**
- **PR #61 top-level comment `4950035046`** (binding maintainer decision authority for D1–D10)
- **PR #61 review `4679463188`** (binding correction and audit scope)
- Issue #20 (TASK-011 Evaluation and Pilot Readiness, open)
- PR #60 (TASK-011B baseline implementation, merged; merge_commit_sha `1636f25d4b6fafa38bfc9747938d0cba8b2abf50`)
- **NOT authority (downgraded):**
  - `/root/TASK-011C-Charles-Decision-Closure-Packet.md` (local file, NOT repository authority, retained only as historical work material)
  - commit message self-description
  - contract self-declaration
  - execution-agent (Hermes/Codex) summary
  - any `/root/...` untracked file

---

## 0. Preamble

This document is a **draft contract** (NOT yet frozen) for TASK-011C = the remaining evaluation scenarios (high-throughput-review, invalid-blocked) plus the manifest / runner / canonicalization / cleanup completeness that TASK-011B did not deliver. The contract targets the **5 implementation gaps G1–G5**.

In this round, the maintainer authority for TASK-011C is established by **PR #61 top-level comment `4950035046`** (binding maintainer decision authority for D1–D10). The comment supersedes any authority claim based solely on the local `/root/TASK-011C-Charles-Decision-Closure-Packet.md`, commit message self-description, contract self-declaration, or execution-agent (Hermes/Codex) summary. The binding disposition is:

```
D1_APPROVED
D2_APPROVED
D3_PENDING_NORMALIZED_SCHEMA_AUDIT
D4_APPROVED
D5_APPROVED
D6_APPROVED
D7_APPROVED
D8_APPROVED
D9_PENDING_EXACT_INPUT_VALUES
D10_APPROVED

TASK_011C_CONTRACT_NOT_FROZEN
TASK_011C_CONTRACT_FREEZE_BLOCKED_BY_D3_AND_D9
TASK_011C_IMPLEMENTATION_NOT_AUTHORIZED
EXPECTED_OUTPUT_AUTHORING_NOT_AUTHORIZED
FIXTURE_AUTHORING_NOT_AUTHORIZED
PR61_MUST_REMAIN_DRAFT
READY_NOT_AUTHORIZED
MERGE_NOT_AUTHORIZED
TASK011D_NOT_AUTHORIZED
TASK12_NOT_AUTHORIZED
```

This document **does not**:
- Authorize TASK-011C implementation in this round.
- Authorize authoring of any expected-output file (golden).
- Create a TASK-011C implementation branch, PR, commit, push, Ready, or Merge.
- Mutate PR #21, PR #23, PR #60, Issue #20, Issue #22, or any other GitHub object.
- Modify any tracked file outside `docs/tasks/TASK-011C-remaining-evaluation-scenarios-contract.md`.
- Touch any production code, evaluation runner code, evaluation fixture, manifest, expected output, baseline golden, sign-off, comparison policy, bootstrap, coefficients, migration, frontend, docker, .github, pyproject, uv.lock, or .gitignore.

This round **only modifies** `docs/tasks/TASK-011C-remaining-evaluation-scenarios-contract.md`. This document corrects the maintainer authority provenance, removes the authority dependence on the local packet, marks D3 and D9 as `PENDING` (with read-only audit evidence attached), and preserves D1, D2, D4–D8, and D10 as approved. The remainder of the audit / closure work remains external.

---

## 1. Authority and status

**Document status: `TASK_011C_MAINTAINER_AUTHORITY_ESTABLISHED` / `TASK_011C_CONTRACT_NOT_FROZEN`**

This contract is **authored, partially approved by the binding maintainer authority (D1, D2, D4–D8, D10), and NOT yet frozen**. The remaining freeze blockers are **D3 (normalized-output volatility audit pending) and D9 (exact high-throughput input values pending)**. Implementation of the contract requires separate Charles-authorized rounds and is NOT in this round's scope.

**Binding maintainer authority (PR #61 top-level comment `4950035046`):**

```
D1_CANONICALIZATION_AUTHORITY=backend/src/cold_storage/evaluation/canonicalization.py
    ::canonicalize_production_outputs(value, *, excluded_paths)

D2_JSON_VALUE_DOMAIN=
    STRICT_JSON_VALUES_ONLY
    TWO_LAYER_FAIL_CLOSED_VALIDATION
    NO_IMPLICIT_COERCION

D4_NUMERIC_COMPARISON=
    EXACT_EQUALITY_DEFAULT
    DECIMAL_FIELDS_REQUIRE_EXPLICIT_JSON_CANONICAL_STRING_REPRESENTATION
    NO_GLOBAL_FLOAT_TOLERANCE
    NO_FIELD_TOLERANCE_UNLESS_SEPARATELY_LISTED_AND_MAINTAINER_APPROVED

D5_MANIFEST_SCHEMA_VERSION=1.0

D6_MANIFEST_LOADER=
    backend/src/cold_storage/evaluation/manifest.py
    ::load_and_validate_manifest

D7_PACKAGE_DISTRIBUTION=
    SETUPTOOLS_PACKAGE_DATA
    cold_storage.evaluation.schema=["manifest.schema.json"]

D8_RESOURCE_LOADING=
    IMPORTLIB_RESOURCES
    importlib.resources.files("cold_storage.evaluation.schema")
    .joinpath("manifest.schema.json")

D10_INVALID_BLOCKED_PATH=
    PRODUCTION_CALCULATION_PROJECTION_MISSING_TOTAL_AREA_M2
```

**Pending decisions (per comment `4950035046`):**

```
D3_EXCLUDED_JSON_PATHS=
    PENDING_NORMALIZED_OUTPUT_SCHEMA_VOLATILITY_AUDIT

D9_HIGH_THROUGHPUT_INPUT=
    PENDING_EXACT_INPUT_VALUES
```

D3 is not approved as an unconditional empty list yet. Wildcard exclusions are forbidden. Only explicit JSON paths may be proposed, and an empty V1 exclusion list is acceptable only if the normalized-output schema has already removed every runtime-volatile field relevant to cross-run and SQLite/PostgreSQL comparison.

D9 remains open until exact, repository-backed high-throughput input values and the corresponding real production review trigger are established.

**Disposition of legacy PRs (per Review 4679338799, binding):**

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
TASK_011C_IMPLEMENTATION_NOT_AUTHORIZED
TASK_011C_CONTRACT_FREEZE_NOT_AUTHORIZED
TASK_011C_CONTRACT_AUTHORED_PENDING_REVIEW
TASK_011C_CONTRACT_NOT_FROZEN
TASK011D_NOT_AUTHORIZED
TASK12_NOT_AUTHORIZED
READY_NOT_AUTHORIZED
MERGE_NOT_AUTHORIZED
EXPECTED_OUTPUT_AUTHORING_NOT_AUTHORIZED
```

**Contract-freeze blocker (this round):**

```
TASK_011C_CONTRACT_FREEZE_BLOCKED_BY_D3_AND_D9
D3_NORMALIZED_SCHEMA_AUDIT_PENDING
D9_HIGH_THROUGHPUT_EXACT_INPUT_VALUES_PENDING
INVALID_BLOCKED_SOURCE_DEFINITION_CLOSED_BY_D10
HIGH_THROUGHPUT_SOURCE_DEFINITION_PENDING
```

While D3 and D9 remain pending:
- Charles MUST NOT sign off the contract as frozen.
- PR #61 MUST NOT be marked Ready.
- PR #61 MUST NOT be merged.
- TASK-011C implementation MUST NOT be authorized.
- Fixture authoring MUST NOT be authorized.
- Expected-output authoring MUST NOT be authorized.

The contract-freeze blocker is `TASK_011C_CONTRACT_FREEZE_BLOCKED_BY_D3_AND_D9` (D3 AND D9, NOT D9 alone). Closing either D3 or D9 requires separate Charles authorization.

---

## 2. Objectives and scope

### 2.1 Objectives

TASK-011C (when implemented) must close the 5 implementation gaps G1–G5 from the post-B audit by providing:

1. A versioned evaluation manifest schema that supports multiple scenarios (baseline, high-throughput-review, invalid-blocked) with per-scenario expected outputs, comparison policies, and provenance.
2. A `high_throughput_review` scenario whose **production outcome is substantively distinct** from `baseline_feasible` (not a `correlation_id` / `run_id` / `timestamp` / database-generated ID rename of baseline).
3. An `invalid_blocked` scenario that exercises a **real production validation/blocker pathway** (not an evaluation-layer-injected exception).
4. A repeatable runner that executes multiple scenarios in one invocation, with typed run.json / summary.json / raw and normalized artifacts, fail-closed validation, and zero exit only on full match.
5. Use of the single canonicalization authority `canonicalize_production_outputs` (per §3.1 / §10 / D1), with stale-output detection and per-scenario cleanup discipline.

### 2.2 Scope (this contract)

This contract proposes the following clauses; the Charles-approved clauses are binding, the rest remain `PROPOSED / PENDING CONTRACT FREEZE`:
- Scenario set (§6)
- Manifest contract (§7) — D5/D6/D7/D8 binding per comment `4950035046`
- Expected-output authority flow (§8) — proposed, pending contract freeze
- Runner contract (§9) — proposed, pending contract freeze
- Canonicalization contract (§10) — **D1 signed: §10 binding; D2 signed: §10.4 strict JSON; D4 signed: §10.4 numeric defaults; D3 audit completed read-only; candidate exclusion set and empty-list decision remain pending separate Charles decision**
- Cleanup + stale-output contract (§11) — proposed, pending contract freeze
- SQLite / PostgreSQL boundary (§12) — **D3 audit completed read-only; no excluded fields are currently approved; the final exact exclusion set, including the possibility of an empty set, remains pending D3 decision**
- Future implementation allowlist proposal (§13) — **D6, D7, D8 signed: §13 updated to reflect final canonicalization/loader/distribution module names; D3 test name corrected to non-empty-asserting name; all other allowlist items remain proposed, pending contract freeze**
- Stop conditions for the future implementation round (§16) — proposed, pending contract freeze

### 2.3 Out of scope (explicit exclusions)

- zh-CN / en-US multilingual report evaluation
- Sample knowledge / document scenario
- Frontend demo path
- Pilot runbook
- Operator instructions
- Issue #20 final closure
- Task 12 productionization
- Mutation of PR #21, PR #23, PR #60
- Authoring of any expected-output golden (without §8 authority flow)
- Production code, formula, coefficient, threshold, scoring, or review-rule change
- Restoration of `production_seeding.py` or any evaluation-owned production ORM fabrication

---

## 3. Definitions

- **Scenario** — A named evaluation execution unit, identified by `scenario_id`, with declared fixture, expected outcome class, expected output (when required), and comparison policy.
- **Manifest** — A versioned JSON document declaring all scenarios in a run-suite, with per-scenario fixture / expected output / outcome class / comparison policy / provenance.
- **Schema version** — The literal `schema_version` string the manifest validator reads first. Frozen at `"1.0"` per Charles **D5**. Unknown / missing / non-`"1.0"` values are rejected fail-closed.
- **Manifest loader** — Single entry point `load_and_validate_manifest` at `backend/src/cold_storage/evaluation/manifest.py` per Charles **D6**. Loads schema from `importlib.resources`, deserializes, validates the v1 schema, and returns a typed `Manifest`.
- **Manifest schema path** — `backend/src/cold_storage/evaluation/schema/manifest.schema.json`. Package-owned, single path; no copy at any other location.
- **Canonicalization** — The single function `canonicalize_production_outputs(value, *, excluded_paths)` at `backend/src/cold_storage/evaluation/canonicalization.py` per Charles **D1**. No second canonicalizer is permitted.
- **Expected output** — A tracked JSON file at `backend/tests/evaluation/data/expected/{scenario_id}.v{revision}.json` that captures the production-path ground truth for a scenario.
- **Comparison policy** — Per-leaf classification (exact / decimal canonical / excluded) used to compare runtime normalized output against the expected output. Per **D4**, default is exact equality; no global float tolerance; no per-field tolerance unless separately Charles-approved.
- **Sign-off** — Charles-approved identity for a specific expected-output commit, recorded in a sign-off document with explicit `STATUS: APPROVED` markers.
- **Review field vocabulary** — Single mapping table per §6.4.4: production `requires_review` → normalized `requires_review` → expected-output `review_required` (baseline-compatible) + derived `review_state`.
- **High-throughput review signal source** — Real production review rule (per §6.4.4 + D9 narrowed scope). The `requires_review=true` + `review_state=REQUIRED` MUST come from production, not from scenario ID / correlation ID / runner relabel / test hooks.

---

## 4. Golden case set

TASK-011C covers three scenarios (G1, G2, plus the existing baseline as regression anchor):

| scenario_id            | scope                                       | fixture status           | expected output status                                                                                  |
|---|---|---|---|
| `baseline_feasible`    | Already approved (TASK-011B); regression anchor | Frozen                  | Frozen (`backend/tests/evaluation/data/expected/baseline_feasible.v1.json`); sign-off `f274db66…`        |
| `high_throughput_review` | New (G1); D9 input values still PENDING      | To be defined (sign-off) | To be authored under separate sign-off after D9 closes                                               |
| `invalid_blocked`      | New (G2); **D10 chosen — source definition closed** | Authoring requires sign-off | Authoring requires sign-off; per Charles D10 contract below in §6.3 |

The manifest MAY carry additional scenarios in the future; each requires its own sign-off and must satisfy the substantively-distinct property.

---

## 5. Source-of-truth matrix

This contract is built from the following source-of-truth artifacts:

| ID | Source | Type | Purpose |
|---|---|---|---|
| S1 | `Issue #20` body | Issue | Top-level requirements |
| S2 | `Review 4679338799` (PR #21) | Review | Audit correction; binding PR21/PR23 disposition |
| S3 | `Review 4679300437` (PR #60) | Review | Post-merge main-push-CI correction |
| S4 | PR #60 final merged body | PR body | Implementation history of baseline |
| S5 | `docs/tasks/TASK-011B-baseline-success-criteria.md` | Doc | Baseline success criteria |
| S6 | `docs/tasks/TASK-011B-path-a-design-ratification.md` | Doc | Path A design (adapter ownership) |
| S7 | `docs/tasks/TASK-011B-path-a-expected-outputs-reviewer-sign-off.md` | Doc | Baseline golden sign-off |
| S8 | `docs/tasks/TASK-011B-phase-b-resumption-pre-freeze.md` | Doc | Pre-freeze contract |
| S9 | `backend/src/cold_storage/evaluation/__init__.py` | Code | Evaluation module entry |
| S10 | `backend/src/cold_storage/evaluation/adapter.py` | Code | A1-2a adapter (production-path bound) |
| S11 | `backend/src/cold_storage/evaluation/cli.py` | Code | CLI surface |
| S12 | `backend/src/cold_storage/evaluation/errors.py` | Code | Error surface |
| S13 | `backend/src/cold_storage/evaluation/execute.py` | Code | Scenario execution |
| S14 | `backend/src/cold_storage/evaluation/run_directory.py` | Code | Run-directory isolation |
| S15 | `backend/tests/evaluation/data/expected/baseline_feasible.v1.json` | Expected output | Baseline golden (frozen) |
| S16 | `backend/tests/evaluation/_seed_helpers.py` | Test helper | Production seed helpers (read-only) |
| S17-S21 | SQLite / PostgreSQL / path-A / fixture-consistency / CLI tests | Test | Acceptance suites |
| S22 | PR #21 (Draft / Open / Not merged) | Historical | Reference; no copy / extract / cherry-pick |
| S23 | PR #23 (Draft / Open / Not merged) | Historical | Design authority; no extraction |
| **S24** | `backend/src/cold_storage/modules/orchestration/application/production_calculation/projection.py` blob `af82ecd64ad2e7ef3036e8304e9b7923757cc1af` | Code | **D10 validation source** (`project_calculator_input`) |
| **S25** | `backend/src/cold_storage/modules/orchestration/application/production_calculation/errors.py` blob `7b9af522d2d11d31d9e65be8f8ad5087db282f15` | Code | **D10 typed exception source** (`InvalidProjectInputError`, code `PROJ_INPUT_INVALID`) |

---

## 6. Scenario set

### 6.1 Already-frozen `baseline_feasible` (DO NOT REOPEN)

The `baseline_feasible` scenario is **already frozen** by TASK-011B sign-off. Reproduced for reference; no TASK-011C clause changes `baseline_feasible`.

| Property            | Upstream frozen value (TASK-011B-approved)         | Source |
|---|---|---|
| `scenario_id`       | `baseline_feasible`                                | S15    |
| `expected_outcome`  | `SUCCEEDED`                                        | S15    |
| `scheme_status`     | `completed`                                        | S15    |
| `review_required`   | `false`                                            | S15    |
| `review_reasons`    | `[]`                                               | S15    |
| `combined_source_hash` | `60e11cacea5868d1650e40f72186618e4a01f29b1655e9aa531deccaf0633206` | S15    |
| Golden SHA-256      | `2d45ea2291c726460d80b0cbca0a771edda9812aa3a6cb017328af458b65ca73` | S7 |
| Production content hash | `ea4ab8cd7f73b50c8cd83865adc9ec90428d8d60a9fc2e7d823a0c8fdb16fe46` | S7 |
| Sign-off identity   | `f274db66fe4bb2de206d12c2d561d1b3549ab6c0` (Commit E) | S7 |

TASK-011C MUST NOT modify the baseline golden, sign-off, or content hash. Baseline is the regression anchor.

### 6.2 High-throughput / review-required (G1) — D9 pending exact input values

D9 status (per binding maintainer authority comment `4950035046`):

```
D9_HIGH_THROUGHPUT_INPUT = PENDING_EXACT_INPUT_VALUES
D9_EXACT_INPUT_VALUES_NOT_YET_ESTABLISHED_AT_REPOSITORY_LEVEL
NO_CURRENT_PRODUCTION_HIGH_THROUGHPUT_THRESHOLD_REVIEW_TRIGGER
D9_PRODUCTION_REVIEW_TRIGGER_CANDIDATE_DEMO_COEFFICIENT_PATH
D9_NOT_APPROVED_DURING_THIS_ROUND
D9_PENDING_NORMALIZED_INPUT_VOLATILITY_AUDIT
```

D9 is **NOT** the sole remaining contract-freeze blocker; both D3 and D9 must be closed before contract freeze. The contract-freeze blocker is `TASK_011C_CONTRACT_FREEZE_BLOCKED_BY_D3_AND_D9` (see §1).

Established semantics (proposed this round, not subject to future change without Charles authorization):

| Property                       | Value (Charles-decided or already-frozen upstream)                   |
|---|---|
| `scenario_id`                  | `high_throughput_review`                                             |
| `execution_outcome`            | `SUCCEEDED`                                                          |
| `persisted_scheme_status`      | `completed`                                                          |
| `requires_review`              | `true`                                                               |
| `review_state`                 | `REQUIRED`                                                           |
| `review_source`                | `REAL_PRODUCTION_LOGIC` (no scenario ID / correlation ID / runner relabel / test hook) |
| `cli_exit_5_used`              | `false` (high-throughput is a successful execution, exit code `0`)   |
| `expected_output_kind`         | `STRUCTURED_ASSERTIONS_ONLY` (per DECISION_1; no full golden)        |
| `full_golden`                   | `NOT_AUTHORIZED`                                                     |

**HIGH_THROUGHPUT_REVIEW_EXACT_FOUR_FIELDS (frozen this round):**

The four business invariants `execution_outcome=SUCCEEDED` + `persisted_scheme_status=completed` + `requires_review=true` + `review_state=REQUIRED` MUST hold for both SQLite and PostgreSQL production runs of this scenario. If any is not produced by real production logic, the scenario stops per `TASK_011C_HIGH_THROUGHPUT_REQUIRES_REVIEW_PRODUCTION_RULE_MUTATION` (S14).

**HIGH_THROUGHPUT_REVIEW_REAL_PRODUCTION_REVIEW_SIGNAL (frozen this round):**

The `requires_review=true` + `review_state=REQUIRED` signal MUST come from a real production review rule. It is forbidden to trigger, synthesize, or rename the review signal via:
- correlation ID,
- scenario ID,
- runner-level reclassification or special-case logic,
- CLI-level special-case logic,
- test-only relabeling,
- hand-editing the expected-output file,
- modifying production formula / threshold / coefficient / scoring / review rule.

**VALID_INPUTS_CAN_PRODUCE_REQUIRES_REVIEW_TRUE_VIA_REAL_DEMO_COEFFICIENT_LOGIC (frozen this round):**

Production code at `origin/main@1636f25d4b6fafa38bfc9747938d0cba8b2abf50` does produce `requires_review=true` for valid inputs via demo-coefficient review rules:
- `backend/src/cold_storage/modules/calculations/domain/investment.py:122` raises `CalculationWarning("DEMO_INVESTMENT_REQUIRES_REVIEW", ...)` on every successful `InvestmentEstimateInput.estimate()` call.
- `backend/src/cold_storage/modules/calculations/domain/zone_planning.py:418` raises `CalculationWarning("DEMO_ASSUMPTIONS_REQUIRE_REVIEW", ...)` on every successful `cold_room_zone_plan` call.

These are real production logic sites that emit `requires_review=true` through the legitimate review-propagation chain (`warnings` → `CalculationRunRecord.requires_review=True` → `SchemeRun.requires_review=source.requires_review` via `production_service.py:469 / 493 / 565`).

**NO_CURRENT_PRODUCTION_HIGH_THROUGHPUT_THRESHOLD_REVIEW_TRIGGER (frozen this round):**

origin/main does NOT define an input-throughput-threshold reviewer. The six `requires_review=True` sites in `backend/src/cold_storage/modules/calculations/{domain,zone_planning}.py` are split between invalid-input rejections (4 of 6: `investment.py:73`, `service.py:247`, `service.py:351`, `zone_planning.py:224`) and unconditional demo-coefficient boilerplate (2 of 6: `investment.py:122`, `zone_planning.py:418`). None is keyed on a numeric throughput threshold.

**D9 pending exact input values (binding, this round):**

Until D9 closes:
- High-throughput fixture authoring is NOT authorized.
- High-throughput expected output authoring is NOT authorized.
- The implementation round MUST NOT produce a high-throughput expected-output draft.
- The implementation round MUST NOT modify production formulas, thresholds, coefficients, scoring, or review rules to create a threshold.

D9 closes when Charles names the exact input values (or input-value-determination rule) that drive a real production review signal in the high-throughput scenario. D9 may be closed by separate Charles authorization without re-opening D1–D8 or D10.

### 6.3 Invalid / blocked (G2) — D10 approved per binding maintainer authority

D10 status (per binding maintainer authority comment `4950035046`):

```
D10_INVALID_BLOCKED_PATH = PRODUCTION_CALCULATION_PROJECTION_MISSING_TOTAL_AREA_M2
D10_APPROVED
INVALID_BLOCKED_SOURCE_DEFINITION_CLOSED_BY_D10
```

D10 is approved. The invalid_blocked source definition is **closed by D10**; the contract-freeze blocker is `TASK_011C_CONTRACT_FREEZE_BLOCKED_BY_D3_AND_D9` (D3 and D9), NOT D10.

**Frozen contract (D10):**

| Property                              | Value                                                                  |
|---|---|
| `scenario_id`                         | `invalid_blocked`                                                      |
| `calculation_type`                    | `INVESTMENT`                                                           |
| `validation_module`                   | `backend/src/cold_storage/modules/orchestration/application/production_calculation/projection.py` |
| `validation_module_blob`              | `af82ecd64ad2e7ef3036e8304e9b7923757cc1af`                              |
| `validation_symbol`                   | `project_calculator_input` (line 59)                                   |
| `invalid_condition`                   | omit `total_area_m2` while all other required INVESTMENT fields are present |
| `exception_module`                    | `backend/src/cold_storage/modules/orchestration/application/production_calculation/errors.py` |
| `exception_module_blob`               | `7b9af522d2d11d31d9e65be8f8ad5087db282f15`                              |
| `exception`                           | `InvalidProjectInputError` (errors.py:101)                            |
| `code`                                | `PROJ_INPUT_INVALID` (errors.py:27 / 111)                               |
| `field`                               | `total_area_m2`                                                        |
| `details.field`                       | `total_area_m2`                                                        |
| `stage`                               | `PRE_ADAPTER_PRE_PERSISTENCE_PROJECTION`                                |
| `persistence_side_effects`            | `NONE`                                                                 |
| `sqlite_postgresql_parity`            | `IDENTICAL`                                                            |
| `artifact`                            | `COMPACT_STRUCTURED_BLOCKER_ARTIFACT`                                  |
| `full_golden`                         | `NOT_AUTHORIZED`                                                       |

**Trigger mechanics (binding, D10):**

`project_calculator_input` is invoked at `backend/src/cold_storage/modules/orchestration/application/source_binding_assembly.py:232` **before** any `SchemeRun` / `SourceBinding` / `CalculationRunRecord` write. For `CalculationType.INVESTMENT`, `_REQUIRED_FIELDS` at `projection.py:50` is `("total_area_m2", "refrigerated_area_m2", "frozen_area_m2", "position_count", "total_power_kw")`. If `total_area_m2` is absent while the other four are present and valid, `missing[0] == "total_area_m2"` and `InvalidProjectInputError(field_name="total_area_m2", reason=...)` is raised fail-closed. No row is persisted. SQLite and PostgreSQL produce identical behavior because the validation is backend-agnostic.

**Compact structured blocker artifact (binding, D10):**

```json
{
  "scenario_id": "invalid_blocked",
  "outcome": "INVALID_INPUT",
  "error": {
    "type": "InvalidProjectInputError",
    "code": "PROJ_INPUT_INVALID",
    "field": "total_area_m2",
    "details": {
      "field": "total_area_m2"
    }
  },
  "stage": "PRE_ADAPTER_PRE_PERSISTENCE_PROJECTION",
  "persistence_side_effects": "NONE"
}
```

Rules:
- No message-text parsing.
- No fabricated TASK-011C exception.
- No full golden.
- The blocker is `COMPACT_STRUCTURED_BLOCKER_ARTIFACT` (DECISION_3).

**A. PROPOSED TARGET GUARDS (fixed invariants):**

| # | Guard | Value |
|---|---|---|
| A1 | `scenario_id` | `invalid_blocked` |
| A2 | `expected execution outcome` | `INVALID_INPUT` (BLOCKED at validation stage) |
| A3 | must use real production validation | required (per D10 = `project_calculator_input`) |
| A4 | no evaluation-injected exception | required |
| A5 | no correlation/scenario-ID special case | required |
| A6 | no fake SchemeRun | required |
| A7 | no message-text parsing | required (typed exception + structured field only) |
| A8 | SQLite/PostgreSQL business verdict must agree | required (IDENTICAL per D10) |
| A9 | CLI exit semantics | non-zero CLI exit; typed reason code `PROJ_INPUT_INVALID` |
| A10 | side-effect expectations (target) | blocked stage MUST NOT create a `SchemeRun` row, MUST NOT create `CalculationRunRecord` rows beyond the stage that raised, MUST leave orchestration identity / attempt state consistent with production's pre-block policy |

**INVALID_BLOCKED_SOURCE_DEFINITION_CLOSED_BY_D10:** The 16 source items are RESOLVED. The contract has the path, the symbol, the exception, the code, the field, the stage, the side-effects, and the cross-backend parity all anchored to origin/main@1636f25d4b6fafa38bfc9747938d0cba8b2abf50. The scenario is source-defined.

The implementation round MAY proceed to fixture / expected-output authoring only after separate Charles sign-off per §8 authority flow. Fixture authoring remains `EXPECTED_OUTPUT_AUTHORING_NOT_AUTHORIZED` in this round.

**Forbidden circumventions (binding, G2):**

The implementation round is **forbidden** from:
1. Using a valid baseline `SourceBinding` and then renaming a successful result as `blocked`.
2. Triggering the blocked state via `correlation_id` or `scenario_id` special-case logic.
3. Creating a fake `SchemeRun` row (or fake `CalculationRunRecord` / orchestration identity / attempt / execution-snapshot row) to represent the failed scenario.
4. Classifying errors by parsing `args[0]` / `str(exception)` / `repr(exception)` / message-text regex. The classification MUST use the typed exception class and the structured error code/field.
5. Building an evaluation-layer-injected `Exception` / `ValueError` / `RuntimeError` to simulate a production failure.
6. Producing an `invalid_blocked` expected output that asserts presence of `production_outputs` past the blocked stage.
7. Adding new business validation rules in the evaluation layer.
8. Using a broad `except Exception` to convert any error into an expected blocker.
9. Using a fixture that does NOT trigger a real production validation defect.
10. Mocking / stubbing the production validation entrypoint to return a synthetic exception.

### 6.4 Review-field vocabulary mapping (frozen, single-source)

Per §6.4.4 of the contract source, the single mapping is:

| Concept         | Production (model)                                | Normalized (runner)                   | Expected-output JSON (canonical) |
|---|---|---|---|
| Execution outcome | `execution_outcome` (enum: `SUCCEEDED`, etc.) | `execution_outcome` (runner-emitted, normalized) | `expected_outcome` (baseline-compatible literal) |
| Review boolean  | `requires_review: bool`                           | `requires_review: bool` (1-to-1)      | `review_required: bool` (baseline-compatible legacy) |
| Review state    | (production has NO `review_state` field)          | `review_state: enum ∈ {REQUIRED, NOT_REQUIRED, NOT_APPLICABLE}` | `review_state: enum` (derived; existence below the canonicalizer/loader is irrelevant) |
| Review reasons  | `review_reasons: list[str]`                       | `review_reasons: list[str]` (1-to-1) | `review_reasons: list[str]` |

**One-way mappings:**

- Production `execution_outcome` → Normalized `execution_outcome` (canonicalize exactly the enum string).
- Normalized `execution_outcome` → Expected-output `expected_outcome` (literal match at assertion time).
- Production `requires_review == true` → Normalized `review_state == REQUIRED`; production `requires_review == false` → Normalized `review_state == NOT_REQUIRED`.
- Production `review_reasons` → Normalized `review_reasons` → Expected-output `review_reasons` (carried 1-to-1).

`requires_review` / `review_required` / `review_state` / `review_reasons` are NOT interchangeable. Each has a specific layer and a specific source. Cross-layer mapping MUST go through the table above.

---

## 7. Manifest contract (D5, D6, D7, D8 integrated)

### 7.0 Schema version (D5, frozen)

Charles **D5** freezes:

```
MANIFEST_SCHEMA_VERSION="1.0"
```

Behavior:
- Exactly `schema_version="1.0"` accepted.
- Missing version rejected.
- Numeric `1.0` (non-string) rejected.
- Unknown version rejected.
- Forward compatibility is fail-closed.
- Backward compatibility is not implicit.
- Any schema change requiring different validation semantics requires a version bump (`"1.0"` → `"1.1"` additive; `→` `"2.0"` breaking) and separate Charles approval.

The `coefficients` module's existing `SCHEMA_VERSION = "1.0"` convention (at `origin/main:backend/src/cold_storage/modules/coefficients/domain/models.py:63`, blob `4a395c8ea259d363d8a2390e4e5f0dad8333e2f2`) is **supporting context only**, not cross-module authority.

### 7.0.1 Manifest schema path (frozen)

```
MANIFEST_SCHEMA_PATH = backend/src/cold_storage/evaluation/schema/manifest.schema.json
MANIFEST_SCHEMA_PACKAGE_OWNED
```

The path is the **single** accepted manifest schema path. The file location is package-owned under `cold_storage.evaluation.schema`. Top-level `evaluation/` directory and `.gitignore` mutations remain unauthorized.

### 7.1 Manifest loader (D6, frozen)

Charles **D6** freezes:

```
MANIFEST_LOADER_MODULE = backend/src/cold_storage/evaluation/manifest.py
MANIFEST_LOADER_FUNCTION = load_and_validate_manifest
LOADER_LOADS_FROM = D8 resource-loading mechanism
LOADER_RAISES_ON = ManifestSchemaVersionError | ManifestUnsupportedJSONValueError | ManifestMissingFieldError | ManifestUndeclaredFieldError | ManifestDuplicateFixtureIDError | ManifestMissingFileError | ManifestMalformedJSONError
```

The loader is the single entry point; no parallel loaders, no CLI-side loading, no test-side re-implementation.

### 7.1.1 Package distribution (D7, frozen)

Charles **D7** freezes:

```
PYPROJECT_SECTION = [tool.setuptools.package-data]
PYPROJECT_DECLARATION = cold_storage.evaluation.schema = ["manifest.schema.json"]
```

The schema file is shipped inside the Python package via setuptools package-data.

### 7.1.2 Runtime resource loading (D8, frozen)

Charles **D8** freezes:

```
RESOURCE_LOADING_MECHANISM = importlib.resources.files
LOAD_PATH = importlib.resources.files("cold_storage.evaluation.schema").joinpath("manifest.schema.json")
LOAD_RETURN_TYPE = str  ; UTF-8 text content
LOAD_FALLBACK_ALLOWED = (none)
PYTHON_VERSION_MINIMUM = 3.9   ; project requires 3.12; 3.9 is the floor for importlib.resources.files
```

Behavior:
- Works from installed package.
- Works in source checkout.
- Works in CI (editable install).
- Missing packaged resource fails closed.
- Repository-relative fallback is forbidden.
- Current working directory must not affect loading.
- Top-level `evaluation/` remains unauthorized.
- `.gitignore` mutation remains unauthorized.

### 7.2 CLI exit code (D9 + DECISION_6 frozen)

`high_throughput_review` MUST exit with code `0` (SUCCEEDED). It is an execution success. `requires_review=true` + `review_state=REQUIRED` are business fields of a successful run, NOT a runner-level failure.

```
cli_exit_5_used = false    ; CLI_EXIT_5_RESERVED_NOT_USED_BY_TASK011C
```

The reserved exit code `5` is NOT exercised by `high_throughput_review`. `EXIT_REVIEW_REQUIRED = 5` remains in code for backward compatibility but is not used by TASK-011C.

---

## 8. Expected-output authority flow (per-file authority, not per-file freeze)

This section restates the 8-step authority flow from §8 of the contract. "Per-file freeze" has been replaced by "per-file authority status" — each expected-output file has a current authority status (frozen / not yet authored), NOT a freeze time or governance relation.

1. **Source-definition approval** — Charles approves the substantive source definition (G1: high-throughput source items SD-1..SD-6 in §6.2; G2: invalid-blocked validation defect in §6.3) as a separate document.
2. **SQLite candidate capture** — Implementation round runs the scenario in SQLite and captures a `candidate.v{revision}.sqlite.json` artifact (gitignored).
3. **PostgreSQL candidate capture** — Implementation round does the same on PostgreSQL, producing `candidate.v{revision}.postgresql.json` (gitignored).
4. **Cross-backend substantive comparison** — Every canonical leaf in `exact_match_fields` MUST match; every leaf in `decimal_fields` MUST match within the declared decimal quantization; every leaf in `excluded_fields` (none in TASK-011C V1 per **D3**) MUST be ignored.
5. **Proposed tracked diff** — Implementation produces a `git diff` between the proposed tracked expected JSON and the empty file (or the previously approved expected JSON, for amendments).
6. **Reviewer sign-off** — Charles reviews the diff + cross-backend comparison + substantive distinctness / validation defect verification, and posts a sign-off with `STATUS: APPROVED` / `CHARLES_VERDICT: APPROVED` / `EXPECTED_OUTPUT_COMMIT_SHA: <commit>`.
7. **Separate implementation authorization** — Only after sign-off, Charles issues a per-message authorization to commit the expected JSON to a tracked location.
8. **Commit only after sign-off** — Implementation commits the expected JSON with `EXPECTED_OUTPUT_COMMIT_SHA: <sign-off commit SHA>` and the `scenario_id`.

**Per-file authority status (this round):**

| File                                                              | Status                                | Authority                                                                                       |
|---|---|---|
| `backend/tests/evaluation/data/expected/baseline_feasible.v1.json`   | ALREADY FROZEN                        | TASK-011B sign-off `f274db66…`                                                                  |
| `backend/tests/evaluation/data/expected/high_throughput_review.v1.json` | NOT YET AUTHORIZED                   | Requires D9 exact-input closure + §8 authority flow                                                |
| `backend/tests/evaluation/data/expected/invalid_blocked.v1.json`       | NOT YET AUTHORIZED                   | Requires §8 authority flow (D10 source definition is now CLOSED)                                  |

**Forbidden practices (binding):**
- `git add -f` to force-add an untracked expected JSON.
- An `update-golden` command or subcommand that auto-commits expected outputs.
- Self-approval.
- Implementation-generated authority.
- Reusing the baseline sign-off (`f274db66…`) as authorization for any other scenario.

---

## 9. Runner contract

The runner conforms to:

| Property | Contract requirement |
|---|---|
| Manifest validation before side effects | Reject an invalid manifest BEFORE any DB / FS side effect; non-zero exit. |
| One authoritative run-directory implementation | A single `execute_in_run_directory`. No parallel implementations. |
| Scenario isolation | Each scenario runs in its own `RunDirectory`. |
| Database backend identity | `database_backend ∈ {sqlite, postgresql}` is part of run identity. |
| Typed `run.json` | Scenario fields: `scenario_id`, `fixture_revision`, `manifest_sha`, `expected_outcome`, `actual_outcome`, `evaluation_result`, `diff_summary`, `started_at`, `completed_at`. |
| Typed `summary.json` | Suite fields: `suite_id`, `manifest_sha`, `run_identity`, `commit_sha`, `started_at`, `completed_at`, `scenarios[]`, `evaluation_result_overall`. |
| Raw artifact | Full raw production result (gitignored). |
| Normalized artifact | Canonical-bytes normalized result via `canonicalize_production_outputs` (D1) — gitignored. |
| Exact scenario result accounting | Each scenario's `evaluation_result` is independently classified. |
| Non-zero on unexpected mismatch | Any `fail` or `infrastructure_error` → non-zero exit. |
| Zero only when full match | Exit zero ONLY when `evaluation_result_overall == "pass"` AND every scenario's `evaluation_result == "pass"`. |

**Allowed distinction (frozen, G1 + G2):**
- `business outcome` — production result (`SUCCEEDED` / `BLOCKED` / `INVALID_INPUT` per D10).
- `evaluation result` — manifest declared vs runtime (`pass` / `fail` / `infrastructure_error`).
- `infrastructure failure` — runner cannot complete the scenario.

Combinations:
- `business outcome = "SUCCEEDED"` + `evaluation_result = "pass"` (e.g., high-throughput run) — exit zero.
- `business outcome = "INVALID_INPUT"` + `evaluation_result = "pass"` (invalid-blocked run with expected exception) — exit zero for that scenario.
- `business outcome = "SUCCEEDED"` + `evaluation_result = "fail"` — non-zero exit (cross-backend parity fail or hash mismatch).
- `infrastructure_failure` — non-zero exit regardless of business outcome.

---

## 10. Canonicalization contract (D1, D2, D3, D4 integrated)

### 10.1 D1: single canonicalization authority (frozen)

Per Charles **D1**:

```
CANONICALIZATION_AUTHORITY = backend/src/cold_storage/evaluation/canonicalization.py
SYMBOL = canonicalize_production_outputs
SIGNATURE = (value, *, excluded_paths) -> CanonicalBytes
```

Rules:
- No second TASK-011C canonicalizer.
- No canonicalization by CLI, manifest loader, tests, fixtures, or comparison code independently.
- Input must already be within the strict JSON value domain (D2).
- Unsupported values fail closed.
- Object keys must be strings.
- Object keys are sorted deterministically.
- Arrays preserve order.
- No silent tuple / set / custom-object conversion.
- No `NaN` or `Infinity`.
- Canonical output must itself be valid JSON data.
- Canonical byte serialization uses deterministic UTF-8 JSON with fixed separators and sorted object keys.

There is no Path A. There is no choice between Path A and Path B. The canonicalization authority is `backend/src/cold_storage/evaluation/canonicalization.py::canonicalize_production_outputs`. If the future implementation round finds an existing complete authority in current main, that finding requires a separate contract amendment (and contradicts the present §10 audit at this round's preflight).

### 10.2 Canonicalization properties (frozen, D4 integrated)

Per Charles **D4**:

```
DEFAULT_COMPARISON = EXACT
GLOBAL_FLOAT_TOLERANCE = FORBIDDEN
UNDECLARED_QUANTIZATION = FORBIDDEN
UNDECLARED_TOLERANCE = FORBIDDEN
```

Decimal-valued governed fields MUST be deliberately represented as canonical JSON strings before comparison. Examples: `"123.45"`, `"0"`, `"-12.500"`. The contract for each governed decimal field MUST define its canonical scale. Representation drift is a mismatch. TASK-011C V1 does NOT authorize a named numeric tolerance.

### 10.3 Canonicalization properties (general, frozen)

| Property | Contract requirement |
|---|---|
| Strict JSON values only | Only JSON-serializable values. No Python tuples, no sets, no custom objects. |
| No `NaN` / `Infinity` | Reject (raise `CanonicalizationError`). |
| Decimal fixed-scale representation | `Decimal` values serialized with explicit fixed scale, e.g. `quantize=Decimal("0.01")`. No scientific notation. No `float()` conversion. |
| Exact array order | Arrays serialized in declared order. Reordering forbidden. |
| Ignored paths declared and justified | Per **D3** (V1 excluded = empty), no paths ignored by default. Any future exclusion requires triple `(governed_artifact_name, jsonpath, source_evidence)` and Charles authorization. |
| No broad floating-point tolerance | Per **D4**, no global float tolerance; no per-field tolerance unless separately Charles-approved. |
| Canonical bytes for persistence and comparison | Normalized artifact serialized to canonical bytes via `canonicalize_production_outputs`. |
| SHA-256 over canonical bytes | `content_hash` of expected JSON is SHA-256 of the canonical bytes of the expected JSON itself. |
| Policy metadata vs executable policy consistency | The manifest's `comparison_policy` is parseable, machine-readable, and matches the runner's executable comparison logic byte-for-byte. Drift is a hard failure. |

### 10.4 Two-layer validation per D2 (frozen)

The manifest is validated through two layers, both fail-closed:

1. **Manifest JSON Schema validation** — against `backend/src/cold_storage/evaluation/schema/manifest.schema.json` (loaded per D8).
2. **Application-level recursive strict-value validation** — checks every value against the D2 allow-list; rejects any unsupported value.

**Strict JSON value domain (Charles D2):**

```
ALLOWED_JSON_VALUES = [null, boolean, string, integer, finite JSON number,
                       array of allowed values,
                       object with string keys and allowed values]
REJECTED_JSON_VALUES = [NaN, Infinity, -Infinity, Decimal objects,
                        datetime/date/time objects, UUID objects,
                        bytes/bytearray, set/frozenset,
                        tuple as implicit array, custom classes,
                        non-string mapping keys, unsupported enums,
                        implicit stringification]
```

Both layers fail closed:
- Layer 1 mismatch → `ManifestSchemaVersionError` or `ManifestMalformedJSONError`.
- Layer 2 mismatch → `ManifestUnsupportedJSONValueError`.

### 10.5 D3 normalized-output volatility audit (read-only, this round)

**Audit objective:** determine whether the normalized output is free of all runtime-volatile values such that an empty V1 exclusion list is supportable.

**Audit method:** read-only inspection of production code on `origin/main @ 1636f25d4b6fafa38bfc9747938d0cba8b2abf50` and the contract's defined normalized output structure.

**Volatility categories inspected (per review `4679463188`):**

| Category | Inspection finding | Verdict |
|----------|--------------------|---------|
| Generated IDs (SchemeRun PK) | `SchemeRunRecord.id` is a DB-generated PK (SQLite auto-increment vs PostgreSQL sequence). NOT in `AdapterResult` fields (adapter.py:116-122). | `NOT_IN_NORMALIZED_OUTPUT` |
| Generated IDs (OrchestrationIdentity) | Read via `SourceBindingReadPort` per contract; FK `source_binding_id` is pre-existing, not generated. | `BUSINESS_LINEAGE_FIELD` |
| Generated IDs (OrchestrationRunAttempt) | FK `weight_set_revision_id` is pre-existing. | `BUSINESS_LINEAGE_FIELD` |
| Timestamps / datetimes | No `datetime` field in `AdapterResult` (adapter.py:116-122). Production `SchemeRunRecord` has no datetime column surfaced. | `NOT_IN_NORMALIZED_OUTPUT` |
| Backend/database markers | `database_backend` is a validation literal (adapter.py:124 `frozenset({"sqlite", "postgresql"})`), NOT in the output dataclass. | `NOT_IN_NORMALIZED_OUTPUT` |
| Filesystem / run-directory values | `run_directory.py` only computes paths; does not write `run.json` / `summary.json` (per §11.0). | `NOT_PRESENT_IN_NORMALIZED_OUTPUT` |
| Nondeterministic collection ordering | `_seed_helpers.py` uses fixed string IDs (`a1-test-p-001` etc.) for test runs. Production path uses DB-generated PKs that are NOT in `AdapterResult`. | `PARTIAL_DETERMINISTIC` |
| Backend-specific diagnostics / exception text | Not in `AdapterResult`; the runner maps `HISTORICAL_BLOCKED_UPSTREAM_CODES` to typed `PhaseBBlockedError`, not text-parsed. | `NOT_IN_NORMALIZED_OUTPUT` |
| SQLite/PostgreSQL identity differences | `SchemeRunRecord` has `id` column not exposed; `combined_source_hash` is content-based. | `CONTENT_DETERMINISTIC` |
| Decimal / float representation | `cand.warnings`, `cand.metrics` are passed through; `combined_source_hash` is hex string. `total_score` is string-ified (service.py:638). | `PARTIAL_DETERMINISTIC_REQUIRES_CANONICAL` |
| NaN / Infinity | Not present; production uses `Decimal` per domain. | `NOT_PRESENT` |

**D3 verdict (binding, this round):**

```
D3_READ_ONLY_AUDIT_COMPLETED
D3_AUDIT_RESULT = NOT_ESTABLISHED
D3_NORMALIZED_SCHEMA_AUDIT_PENDING = FALSE (audit itself completed read-only)
D3_DECISION_EVIDENCE_NOT_ESTABLISHED
D3_CANDIDATE_EXCLUDED_JSON_PATHS = NOT_PROPOSED
D3_DECISION_STATUS = PENDING
D3_DECISION_PENDING
D3_EMPTY_LIST_NOT_APPROVED
```

**Rationale:** the docs-only audit cannot definitively prove that the production runtime path produces byte-identical normalized output across SQLite and PostgreSQL for all high-throughput inputs. The `_seed_helpers.py` test path is deterministic (fixed string IDs), but the production path uses DB-generated PKs that are NOT in the `AdapterResult` output by design. A full proof requires executing the production path on both backends with the high-throughput input; this round is docs-only and cannot run the production path. The honest verdict is `NOT_ESTABLISHED`, NOT a fabricated empty-list approval.

**Allowed next step:** a future separately authorized evidence-validation round, NOT an implementation round, may run the production path on both backends with a high-throughput input and produce empirical evidence. That future round does NOT automatically authorize: fixture authoring, expected-output authoring, canonicalizer implementation, runner implementation, manifest implementation, or any production-code mutation. Each of those requires a separate Charles authorization with explicit file / command / database / side-effect boundary.

### 10.6 D9 high-throughput exact-input audit (read-only, this round)

**Audit objective:** identify the smallest, repository-backed, concrete input delta that naturally causes the production path to emit `execution_outcome=SUCCEEDED` + `scheme_run.status=completed` + `requires_review=true` + non-empty `review_reasons` + `CLI exit=0`.

**Production rule candidates inspected:**

| Production rule | Location | Mechanism | Reachable from existing input? |
|-----------------|----------|-----------|-------------------------------|
| `requires_review = any(c.requires_review for c in candidates)` | `backend/src/cold_storage/modules/schemes/application/service.py:611` | If any candidate has `requires_review=true`, the SchemeRun's `requires_review` becomes `true` | Yes (if any candidate emits a warning) |
| `requires_review = True` (NO_FEASIBLE_SCHEME) | `service.py:615` | If no candidate is feasible, `requires_review=True` and `recommended_code = None` | Yes, but this would change `scheme_status` semantics (no recommendation) — does not satisfy "completed" + SUCCEEDED invariants |
| `_coefficient_review` returns `requires_review=True` | `backend/src/cold_storage/modules/calculations/domain/service.py:89, 189, 274, 309` | Demo coefficients trigger review-propagation chain | Yes, per `AGENTS.md` mandatory rule "Demo coefficients must always be marked `source_type=demo`, `validity_status=unverified`, and `requires_review=true`" |
| `warning_messages` populates from `cand.warnings` | `service.py:591` (passed to recommendation snapshot) and `production_service.py:1286/1385` (persisted to SchemeRunRecord) | Calculation warning list propagates to SchemeRun | Yes, if candidate emits warnings |

**D9 verdict (binding, this round):**

```
D9_READ_ONLY_AUDIT_COMPLETED
D9_AUDIT_RESULT = NOT_ESTABLISHED
HIGH_THROUGHPUT_SOURCE_DEFINITION_NOT_ESTABLISHED
D9_CANDIDATE_INPUT_PATH = NOT_PROPOSED
D9_BASELINE_VALUE = NOT_PROPOSED
D9_CANDIDATE_VALUE = NOT_PROPOSED
D9_PRODUCTION_RULE_CANDIDATE = backend/src/cold_storage/modules/calculations/domain/service.py::_coefficient_review
D9_PRODUCTION_WARNING_CODE_CANDIDATE = COEFFICIENT_REQUIRES_REVIEW
D9_PRODUCTION_WARNING_MESSAGE_CANDIDATE = 计算使用了未批准或需复核的系数
D9_EXPECTED_REVIEW_REASON = NOT_ESTABLISHED
D9_EXACT_INPUT_EVIDENCE_NOT_ESTABLISHED
D9_DECISION_STATUS = PENDING
D9_DECISION_PENDING
D9_NOT_APPROVED_DURING_THIS_ROUND
```

**Rationale:** the production rule that naturally produces `requires_review=true` + non-empty `review_reasons` is the `_coefficient_review` mechanism in `backend/src/cold_storage/modules/calculations/domain/service.py`, triggered by demo coefficients (per `AGENTS.md`). The candidate production-rule warning code is `COEFFICIENT_REQUIRES_REVIEW` and the production message is `计算使用了未批准或需复核的系数` (per the production code review). However, the **exact input values** (the `project_input` payload, weight-set IDs, source-binding IDs, and the specific `SourceBinding` configuration) that produce the high-throughput scenario's `requires_review=true` with `execution_outcome=SUCCEEDED` are **NOT** established at the docs-only audit level. Furthermore, the final persisted `review_reasons` array order, exact composition, and warning-message mapping have NOT been executed and confirmed; therefore the exact `review_reasons` value remains `NOT_ESTABLISHED`. Establishing them requires:
- authoring a fixture (FORBIDDEN this round, per §6.2 "no fixture authoring"),
- authoring an expected-output file (FORBIDDEN this round, per §0 "no expected-output authoring"),
- running the production path on both backends (OUT of scope, this round is read-only).

The honest verdict is `NOT_ESTABLISHED`. The production rule is identified as a candidate; the exact input values, the exact persisted `review_reasons` array, and the final source definition are NOT.

**Forbidden methods (binding, per review `4679463188`, this round's auth §6.2, and review `4679476507`):**
- Setting `requires_review` based on `scenario_id` or `correlation_id`.
- Injecting review flag in evaluation adapter.
- Monkey-patching production rules in tests.
- Modifying production thresholds.
- Inventing review reasons.
- Creating fixture or expected-output files.
- Asserting a review reason value that is not produced by the identified production rule.

**Allowed next step:** a future separately authorized evidence-validation round, NOT an implementation round, may propose a repository-backed fixture that exercises the `_coefficient_review` path. That future round does NOT automatically authorize: fixture authoring, expected-output authoring, canonicalizer implementation, runner implementation, manifest implementation, or any production-code mutation. Each of those requires a separate Charles authorization with explicit file / command / database / side-effect boundary.

---

## 11. Runner + run-artifact contract

### 11.0 Current main behavior vs TASK-011C contract (read-only)

Read-only description; current `run_directory.py` computes paths only, does not write `run.json` / `summary.json` / normalized artifacts. TASK-011C contract describes what a future separately authorized evidence-validation round, NOT an implementation round, may write.

### 11.1 `run.json` schema

Proposed, pending contract freeze. The semantic-versioning literal is bound to D5 (`schema_version` literal in nested run.json follows `"task011c-run.v1"` as a string label, not a numeric version). The other field shapes and semantics remain proposed and require Charles sign-off before freeze.

### 11.2 `summary.json` schema

Proposed, pending contract freeze. The requirement that `summary.normalized_artifact_sha256` MUST be equal across SQLite and PostgreSQL is conditional on the D3 final exclusion set decision (§12.0.2, §10.5); the rest of the field set remains proposed.

### 11.3 Run-artifact semantics

Proposed, pending contract freeze. The canonical-bytes concept is anchored in the D1 canonicalization authority (`canonicalize_production_outputs`); the rest of the artifact semantics remain proposed.

### 12.0 Field-by-field parity (frozen)

**Must-match fields (business-authoritative):**

| Field                                       | JSON path                                | Notes |
|---|---|---|
| `scenario_id`                               | `summary.scenario_id`                    | matches manifest |
| Manifest schema/version                     | `summary.manifest_schema_version`         | matches manifest |
| `execution_outcome`                         | `summary.execution_outcome`              | `SUCCEEDED` / `BLOCKED` / `INVALID_INPUT` / `FAILED` |
| Scheme business status                      | `summary.scheme_status`                  | `completed` / `blocked` / `not_created` |
| `requires_review`                           | `summary.requires_review`                | bool |
| `review_state`                              | `summary.review_state`                   | `NOT_REQUIRED` / `REQUIRED` / `NOT_APPLICABLE` |
| Comparison classification                   | `summary.comparison_result`              | `pass` / `fail` / `not_applicable` |
| Deterministic calculated values             | `summary.normalized_artifact_sha256`     | SHA-256 of canonical bytes — must match (cross-backend) |
| Blocker / error code (D10)                   | `summary.error_or_blocker_result.code`   | `PROJ_INPUT_INVALID` (D10); must match across backends |
| Blocker / error field                        | `summary.error_or_blocker_result.field`  | `total_area_m2` (D10); must match across backends |
| Expected-output match result                | `summary.comparison_result` + per-leaf diff | must match |

### 12.0.1 Hash-category requirements (frozen, single canonical)

| Hash category                       | Cross-backend rule                                                                | Used for |
|---|---|---|
| `raw_artifact_sha256`               | Per-backend stable; NOT required equal across SQLite / PostgreSQL. Each backend records its own. | Integrity verification only. |
| `normalized_artifact_sha256`        | MUST be equal across SQLite and PostgreSQL (conditional on D3 = empty excluded paths in V1). SHA-256 of canonical bytes from D1. | Cross-backend business parity. |
| `expected_output_sha256`            | Per scenario + revision (file-level hash). NOT cross-backend. | Repository-owned golden integrity. |

The contract explicitly **forbids** asserting `raw_artifact_sha256` is equal across SQLite and PostgreSQL while permitting backend-specific fields to differ. Such a combination is removed by the three-tier hash policy above.

### 12.0.2 Excluded paths (D3, PENDING_NORMALIZED_SCHEMA_AUDIT)

Per the binding maintainer authority comment `4950035046`, the D3 excluded-JSON-paths set is **NOT** approved as an unconditional empty list. The empty-list claim in the prior round is **superseded**:

```
TASK_011C_V1_EXCLUDED_JSON_PATHS = PENDING
D3_NORMALIZED_SCHEMA_AUDIT_PENDING
D3_AUDIT_RESULT = NOT_ESTABLISHED_AT_THIS_ROUND
D3_DECISION_STATUS = PENDING_NORMALIZED_SCHEMA_AUDIT
D3_EMPTY_LIST_NOT_APPROVED
```

**D3 audit (read-only, this round):** see §10.5 for the full evidence ledger. The audit inspected at least: generated identifiers (SchemeRun auto-PK, OrchestrationIdentity IDs), timestamps and datetimes (none in `AdapterResult` line 116–122 of `backend/src/cold_storage/evaluation/adapter.py`), backend/database markers (none in normalized output per §11.1 `run.json` schema), filesystem/run-directory values (`run_directory.py` only computes paths, does not write per §11.0), nondeterministic collection ordering (`_seed_helpers.py` uses fixed string IDs `a1-test-p-001` etc., but production path uses DB-generated PKs), backend-specific diagnostics or exception text (none in normalized output), values derived from SQLite/PostgreSQL persistence identities (production `SchemeRunRecord` has `id` column not in `AdapterResult` line 116–122). The audit cannot definitively prove the production runtime path is fully deterministic across SQLite/PostgreSQL without executing the production path; therefore `D3_AUDIT_RESULT = NOT_ESTABLISHED` is the only honest verdict for a docs-only audit.

Audit rules (binding, per review `4679463188`):

```
NO_WILDCARD_EXCLUSIONS
ONLY_EXACT_JSON_PATHS_MAY_BE_PROPOSED
BUSINESS_AUTHORITATIVE_FIELDS_MUST_NOT_BE_EXCLUDED
EMPTY_LIST_ALLOWED_ONLY_IF_PROVEN_BY_SCHEMA_AUDIT
```

A future excluded path requires:
- exact JSON path,
- source evidence that the field exists,
- proof of nondeterminism,
- proof that it is irrelevant to business-contract equivalence,
- explanation why deterministic generation cannot replace exclusion,
- separate Charles authorization.

Wildcard exclusions (e.g., `any *_id`) are **forbidden**.

The earlier `§12.0.2` may-differ table that named `summary.run_identity`, `raw.database_session_uuid`, `raw.orchestration.attempt_id`, `raw.calculation_run_ids.*` is **superseded** by the current D3 PENDING state. These fields are NOT in the current empty-list assertion; they are candidate paths pending audit and Charles approval.

### 12.1 Boundary contract (frozen, general)

| Boundary | Contract requirement |
|---|---|
| SQLite — full TASK-011C scenario acceptance | All scenarios MUST pass on SQLite in `backend-sqlite` CI. |
| PostgreSQL — required where persistence / JSON behavior may differ | All scenarios MUST also pass on PostgreSQL in `backend-postgresql` CI. |
| Substantive normalized result parity | Canonical bytes (per D1) of the normalized SQLite and PostgreSQL results MUST be byte-identical for `exact_match_fields` and `decimal_fields`; D3 says no `excluded_fields` in V1. |
| Allowed backend-specific runtime metadata | Recorded separately per backend in `raw_artifact_sha256`. |
| Forbidden backend-specific business outcome drift | Runner MUST reject any scenario whose business-authoritative field differs between backends. |

---

## 13. Future implementation allowlist proposal (D1, D6, D7, D8 updated)

This round's allowlist incorporates Charles-signed module names from D1 / D6 / D7 / D8. **This round does NOT modify any of these files.**

| Path | Purpose | Round scope |
|---|---|---|
| **`backend/src/cold_storage/evaluation/canonicalization.py`** (new) | **D1: single canonicalization authority** `canonicalize_production_outputs` | C-1 (manifest schema) |
| `backend/src/cold_storage/evaluation/manifest.py` (new) | **D6: manifest loader** `load_and_validate_manifest` | C-1 (manifest schema) |
| `backend/src/cold_storage/evaluation/schema/__init__.py` (new) | Package marker (D7 owns schema under `cold_storage.evaluation.schema`) | C-1 (manifest schema) |
| `backend/src/cold_storage/evaluation/schema/manifest.schema.json` (new) | **D7: package-data; D8: importlib.resources load**; JSON Schema source | C-1 (manifest schema) |
| `backend/src/cold_storage/evaluation/sqlite_scope.py` (new) | Per-scenario SQLite isolation | C-1 |
| `backend/src/cold_storage/evaluation/paths.py` (new) | Path safety helpers | C-1 |
| `backend/src/cold_storage/evaluation/models.py` (new) | Pydantic models for manifest / run.json / summary.json | C-1 |
| `backend/src/cold_storage/evaluation/compare.py` (new) | Comparison policy executor | C-2 (runner) |
| `backend/src/cold_storage/evaluation/evaluate.py` (new) | Multi-scenario runner | C-2 |
| `backend/src/cold_storage/evaluation/json_path.py` (new) | JSON path utilities | C-2 |
| `backend/src/cold_storage/evaluation/runners/sqlite.py` (new) | SQLite-specific runner | C-2 |
| `backend/src/cold_storage/evaluation/runners/postgresql.py` (new) | PostgreSQL-specific runner | C-2 |
| `backend/tests/evaluation/test_manifest_schema.py` (new) | Manifest schema tests | C-1 |
| `backend/tests/evaluation/test_manifest_loader.py` (new) | Manifest loader tests (D6) | C-1 |
| `backend/tests/evaluation/test_canonicalization.py` (new) | Canonicalizer tests (D1) | C-1 |
| `backend/tests/evaluation/test_canonicalization_d1.py` (new) | Single-authority tests (frozen behavior, no second canonicalizer) | C-1 |
| `backend/tests/evaluation/test_compare.py` (new) | Compare policy tests | C-2 |
| `backend/tests/evaluation/test_json_path.py` (new) | JSON path tests | C-2 |
| `backend/tests/evaluation/test_path_safety.py` (new) | Path safety tests | C-1 |
| `backend/tests/evaluation/test_run_directory.py` (new) | Run-directory tests | C-2 |
| `backend/tests/evaluation/test_run_directory_identity.py` (new) | Run identity tests | C-2 |
| `backend/tests/evaluation/test_d2_strict_value_domain.py` (new) | D2 strict-value domain tests | C-1 |
| `backend/tests/evaluation/test_d3_excluded_paths_empty.py` (new) | D3 excluded-path-empty assertion | C-1 |
| `backend/tests/evaluation/test_d4_numeric_exact.py` (new) | D4 exact-only numeric tests | C-1 |
| `backend/tests/evaluation/test_d5_schema_version.py` (new) | D5 schema-version literal tests | C-1 |
| `backend/tests/evaluation/test_d6_manifest_loader.py` (new) | D6 loader tests | C-1 |
| `backend/tests/evaluation/test_d7_distribution.py` (new) | D7 setuptools package-data tests | C-1 |
| `backend/tests/evaluation/test_d8_resource_loading.py` (new) | D8 importlib.resources tests | C-1 |
| `backend/tests/evaluation/test_d10_invalid_blocked.py` (new) | D10 invalid-blocked scenario tests | C-2 |
| `backend/tests/evaluation/test_sqlite_acceptance.py` (extend) | Add C-scenario tests | C-2 |
| `backend/tests/evaluation/test_postgresql_acceptance.py` (extend) | Add C-scenario tests | C-2 |
| `backend/tests/evaluation/data/expected/high_throughput_review.v{revision}.json` (new, tracked) | High-throughput expected output | C-3 — REQUIRES D9 + sign-off |
| `backend/tests/evaluation/data/expected/invalid_blocked.v{revision}.json` (new, tracked) | Invalid-blocked expected output | C-3 — REQUIRES sign-off |
| `docs/tasks/TASK-011C-expected-outputs-high_throughput_review-reviewer-sign-off.md` (new, tracked) | Sign-off document | C-3 |
| `docs/tasks/TASK-011C-expected-outputs-invalid_blocked-reviewer-sign-off.md` (new, tracked) | Sign-off document | C-3 |
| `docs/tasks/TASK-011C-manifest-schema-design.md` (new, tracked) | Manifest schema design contract | C-1 — separate Charles authorization |

**Forbidden paths (any mutation is a hard violation):**

- `backend/src/cold_storage/modules/coefficients/**` — Phase 1-4 production code
- `backend/src/cold_storage/modules/orchestration/application/production_calculation/**` — Phase 1-4 production code (READ-ONLY reference for D10)
- `backend/alembic/versions/0035-0038*` — Phase 1-4 migrations
- `docs/tasks/TASK-011B-*` (read-only references only)
- `docs/tasks/TASK-019-*` (read-only references only)
- `backend/src/cold_storage/evaluation/production_seeding.py` — explicitly forbidden, must not be restored
- `backend/src/cold_storage/evaluation/adapter.py` — A1-2a adapter is frozen, no extension
- `backend/src/cold_storage/evaluation/execute.py` — A1-2a executor is frozen, no extension
- `.github/**` — CI workflow not modified
- `docker-compose*`
- `pyproject.toml`, `uv.lock` (except for D7's `[tool.setuptools.package-data]` section add at implementation time)
- **`.gitignore`** — NOT AUTHORIZED. Any required `.gitignore` change triggers `TASK_011C_GITIGNORE_CHANGE_REQUIRES_SEPARATE_AMENDMENT` (S24).
- `README.md`, `CODEX_TASKS.md`
- `docs/roadmap/**`

**No extraction from PR #21 (binding):**

TASK-011C does NOT authorize extracting, copying, cherry-picking, or restoring any file from PR #21 (`codex/task-11-evaluation`). PR #21 is **re-authoring reference only**. The future `TASK-011-evaluation-pilot-readiness.md`, if needed, MUST be independently authored from current main under a separate TASK-011D round or a closure round, NOT extracted from PR #21.

---

## 14. Explicit TASK-011D exclusions (frozen)

Same scope reservation as prior; multilingual, runbook, demo, frontend, Issue #20 closure, Task 12 are all TASK-011D / closure-only.

---

## 15. Forbidden actions (binding)

The future TASK-011C implementation round is **forbidden** from:

1. Restoring `production_seeding.py`.
2. Creating any production ORM row from the evaluation layer.
3. Directly constructing any `CalculationRunRecord` instance.
4. Bypassing production services.
5. Modifying any engineering formula, coefficient value, threshold, scoring rule, or review rule.
6. Modifying the baseline golden or its sign-off.
7. Modifying PR #21 (state, draft, head, base, comments, reviews, files, branch).
8. Modifying PR #23 (state, draft, head, base, comments, reviews, files, branch).
9. Closing Issue #20.
10. Starting Task 12.
11. Cherry-picking, merging, restoring, or copying any file from PR #21.
12. Extracting or committing PR #23's design document.
13. Authoring any expected output without the §8 authority flow.
14. Using `git add -f`, `update-golden` subcommand, or self-approval.
15. **Canonicalization authority is single, future-only, separately authorized.** Per **D1**, the canonicalization authority is `backend/src/cold_storage/evaluation/canonicalization.py::canonicalize_production_outputs(...)`. **It is forbidden to create a second canonicalizer. It is forbidden to claim that any other module (including `run_directory.py`, `execute.py`, `test_*` helpers, manifest loader, CLI, etc.) is the authoritative canonicalizer. ALL canonicalization MUST go through the single D1 symbol.** Until that module exists, no canonicalization is performed and no canonical bytes are produced.
16. Building a runner that can produce zero-exit while a `fail` scenario is unaccounted for.
17. Creating a path-based canonicalizer, a CLI-side canonicalizer, a manifest-loader-side canonicalizer, a compare-side canonicalizer, a test-side canonicalizer, or any other parallel canonicalizer in addition to D1.

---

## 16. Stop conditions (binding, post-D10)

This list supersedes the prior §16 only by removing **S13** (which is closed by D10) and adding **S25–S30** for the new D1–D10 contracts:

1. **High-throughput source-definition insufficient** — no production pathway produces a substantively distinct result for any permitted input variation.
2. **Expected production outcome ambiguous** — manifest cannot be authored with a specific business outcome for a scenario.
3. **Cross-backend business outcome inconsistent** — SQLite and PostgreSQL produce different business outcome for the same scenario.
4. **New fixture requires production-formula modification** — forbidden.
5. **Requires evaluation-owned ORM fabrication** — forbidden.
6. **Requires restoring `production_seeding.py`** — forbidden.
7. **Manifest incompatible with current runner contract.**
8. **Cannot obtain Charles sign-off for new expected output.**
9. **Current main source drift changes design premise.**
10. **Cross-backend substantive comparison fails.**
11. **PR #21 / PR #23 mutation required** — forbidden.
12. **Baseline regression** — forbidden.
13. (Removed — `INVALID_BLOCKED_PRODUCTION_PATH_NOT_ESTABLISHED` is closed by D10.)
14. `TASK_011C_HIGH_THROUGHPUT_REQUIRES_REVIEW_PRODUCTION_RULE_MUTATION` — D9 sign-off requires a production-formula / threshold / coefficient / scoring / review-rule change.
15. `TASK_011C_CANONICALIZATION_AUTHORITY_REMAINS_AMBIGUOUS` — D1 future module not creatable without contradiction.
16. `TASK_011C_MANIFEST_SCHEMA_PATH_CONFLICTS` — schema path requires top-level `evaluation/` or `.gitignore` modification.
17. `TASK_011C_BASELINE_GOLDEN_MODIFICATION_REQUIRED` — frozen baseline modification.
18. `TASK_011C_EXPECTED_OUTPUT_AUTHORED_WITHOUT_SEPARATE_SIGNOFF` — §8 authority flow not followed.
19. `TASK_011C_PR21_OR_PR23_MUTATION_REQUIRED` — forbidden.
20. `TASK_011C_SCOPE_DRIFT_TO_TASK011D_OR_TASK12` — forbidden.
21. `TASK_011C_REMOTE_COMMIT_CANNOT_BE_ESTABLISHED` — push failure.
22. `TASK_011C_CONTRACT_SOURCE_CONFLICTS_WITH_MAIN` — main drift.
23. `TASK_011C_HIGH_THROUGHPUT_SUBSTANTIVE_INVARIANT_UNIDENTIFIED`.
24. `TASK_011C_GITIGNORE_CHANGE_REQUIRES_SEPARATE_AMENDMENT`.
25. `TASK_011C_D2_VALUE_DOMAIN_VIOLATED` — manifest contains a rejected type (NaN, Infinity, Decimal object, datetime, etc.).
26. `TASK_011C_D3_WILDCARD_EXCLUSION_INTRODUCED` — `any *_id`-style wildcards or non-JSONPath exclusion.
27. `TASK_011C_D4_GLOBAL_TOLERANCE_INTRODUCED` — broad `1e-*` or per-leaf tolerance without Charles approval.
28. `TASK_011C_D5_VERSION_NOT_LITERAL_1_0` — implementation rejects version `"1.0"` literal or accepts e.g. `1.0` numeric.
29. `TASK_011C_D6_SECOND_LOADER_INTRODUCED` — a parallel `load_and_validate_manifest` outside the canonical file.
30. `TASK_011C_D8_REPOSITORY_RELATIVE_FALLBACK_USED` — loader falls back to `Path(__file__).parent / ...` instead of `importlib.resources.files(...)`.

---

## 17. Validation (docs-only, this round)

This round is docs-only:
- `git diff --check` on working tree — empty
- `git status --short` on working tree — empty
- `git diff --name-only origin/main...HEAD` — exactly 1 file: `docs/tasks/TASK-011C-remaining-evaluation-scenarios-contract.md`
- `git diff --stat origin/main...HEAD` — 1 file changed
- Forbidden-path scan (§13) — no path outside `docs/tasks/TASK-011C-*.md` appears in the diff

---

## 18. Commit, push, and Draft PR (docs-only)

- **Branch:** `docs/task-011c-remaining-evaluation-scenarios-contract`
- **Base SHA:** `1636f25d4b6fafa38bfc9747938d0cba8b2abf50`
- **Commit message (suggested):** `docs(task-011c): integrate D1-D8 + D10 partial decision closure`
- **Push target:** `origin HEAD:refs/heads/docs/task-011c-remaining-evaluation-scenarios-contract`
- **Draft PR:** #61 — title updated to reflect partial decision closure; status updated; **Draft / Not merged / No Ready**.
- **PR #61 body MUST include:**
  - `D1_D8_D10_DECISIONS_INTEGRATED`
  - `INVALID_BLOCKED_SOURCE_DEFINITION_CLOSED`
  - `D9_HIGH_THROUGHPUT_EXACT_INPUT_PENDING`
  - `CONTRACT_FREEZE_NOT_AUTHORIZED`
  - `IMPLEMENTATION_NOT_AUTHORIZED`
  - `PR #21 untouched`
  - `PR #23 untouched`
  - `Issue #20 remains open`
  - `TASK-011D not started`
  - `Task 12 not authorized`
  - `Ready not authorized`
  - `Merge not authorized`

---

## 19. Final verdict (this round)

**Round status: `TASK_011C_MAINTAINER_AUTHORITY_ESTABLISHED`**

```
TASK_011C_MAINTAINER_AUTHORITY_ESTABLISHED
D1_APPROVED
D2_APPROVED
D3_PENDING_NORMALIZED_SCHEMA_AUDIT
D4_APPROVED
D5_APPROVED
D6_APPROVED
D7_APPROVED
D8_APPROVED
D9_PENDING_EXACT_INPUT_VALUES
D10_APPROVED
TASK_011C_CONTRACT_NOT_FROZEN
TASK_011C_CONTRACT_AUTHORED_PENDING_REVIEW
TASK_011C_CONTRACT_FREEZE_BLOCKED_BY_D3_AND_D9
D3_NORMALIZED_SCHEMA_AUDIT_PENDING
D9_HIGH_THROUGHPUT_EXACT_INPUT_VALUES_PENDING
INVALID_BLOCKED_SOURCE_DEFINITION_CLOSED_BY_D10
TASK_011C_CONTRACT_FREEZE_NOT_AUTHORIZED
TASK_011C_IMPLEMENTATION_NOT_AUTHORIZED
EXPECTED_OUTPUT_AUTHORING_NOT_AUTHORIZED
FIXTURE_AUTHORING_NOT_AUTHORIZED
PR61_OPEN_DRAFT_NOT_MERGED
PR21_UNTOUCHED
PR23_UNTOUCHED
ISSUE20_REMAINS_OPEN
TASK011D_NOT_AUTHORIZED
TASK12_NOT_AUTHORIZED
READY_NOT_AUTHORIZED
MERGE_NOT_AUTHORIZED
CLI_EXIT_5_RESERVED_NOT_USED_BY_TASK011C
```

This round commits and pushes only the contract amendment; PR #61 stays Draft / Not merged; no Ready / no Merge / no implementation. The contract-freeze blocker is `D3 AND D9`; closing either D3 or D9 requires separate Charles authorization.

---

## 20. Change log

| Round | Date | Author | Change |
|---|---|---|---|
| Initial authoring | 2026-07-12 | Hermes | Initial TASK-011C remaining evaluation scenarios contract (NOT frozen) |
| Review-correction round | 2026-07-12 | Hermes | Corrected against Issue #20 review comment `4949858037` (P0 + 8 contract corrections; §1 status wording; §6.2 high-throughput four-field invariants + real-production review signal; §6.3 invalid_blocked field-by-field; §7.0 manifest single-path; §7.1 CLI exit codes; §8.10 per-file expected-output authority; §10 Path B canonicalization; §11 current-main-vs-future contract; §12 field-by-field SQLite/PG parity; §16 stop conditions S13–S23; §20 verdict lifecycle) |
| **Charles Partial Decision Closure Round (prior round)** | 2026-07-12 | Hermes | Integrated prior-round Charles authority: D1 (canonicalization `canonicalization.py::canonicalize_production_outputs`); D2 (strict JSON two-layer); D3 (prior-round authority's candidate proposed an empty excluded-paths claim — later audited and superseded to pending-audit per maintainer authority round; no empty-list claim survives); D4 (exact numeric default, no global tolerance); D5 (`schema_version="1.0"` Charles policy); D6 (loader `manifest.py::load_and_validate_manifest`); D7 (setuptools package-data); D8 (importlib.resources); D10 (`PRODUCTION_CALCULATION_PROJECTION_MISSING_TOTAL_AREA_M2` source-defines `invalid_blocked`). D9 was carried as `PENDING_EXACT_INPUT_VALUES` during the prior round; the prior round also temporarily treated it as the single remaining deficit, which was subsequently corrected to `TASK_011C_CONTRACT_FREEZE_BLOCKED_BY_D3_AND_D9` in the maintainer-authority round. Rewrote §6.3 invalid_blocked source inventory to remove prior staged PENDING counters and close the source definition; removed §12.0.2 wildcard exclusions table (the prior-round empty-list claim was later superseded); updated §10 manifest decisions to reflect D1; updated §13 implementation allowlist with new test names; updated §16 stop conditions S25–S30 for D1–D8/D10; replaced the prior pending-state marker for invalid_blocked with `INVALID_BLOCKED_SOURCE_DEFINITION_CLOSED`. PR #21 / PR #23 / PR #60 / Issue #20 untouched. |
| **Maintainer Authority Provenance Correction + D3/D9 Audit Round (this round)** | 2026-07-12 | Hermes | **Read the binding maintainer authority from PR #61 top-level comment `4950035046` and review `4679463188` (NOT the local `/root/TASK-011C-Charles-Decision-Closure-Packet.md`)**. Downgraded the local packet to "historical work material only", not a repository authority source. **Updated status** to `TASK_011C_MAINTAINER_AUTHORITY_ESTABLISHED` / `TASK_011C_CONTRACT_NOT_FROZEN`. **Marked D3** as `PENDING_NORMALIZED_SCHEMA_AUDIT` (replaced the prior-round empty-list claim with `PENDING` + D3 audit evidence ledger in new §10.5, verdict `D3_AUDIT_RESULT = NOT_ESTABLISHED`). **Marked D9** as `PENDING_EXACT_INPUT_VALUES` (replaced the prior-round single-deficit framing with the new D3+D9 dual-blocker framing and §10.6 D9 audit evidence ledger, verdict `D9_AUDIT_RESULT = NOT_ESTABLISHED`; production rule identified = `_coefficient_review` in `backend/src/cold_storage/modules/calculations/domain/service.py:89, 189, 274, 309`, but exact input values NOT established at docs-only audit level). **Updated contract-freeze blocker** from the prior-round D9-only formulation to `TASK_011C_CONTRACT_FREEZE_BLOCKED_BY_D3_AND_D9` (§1, §6.2, §19). **Preserved** D1, D2, D4–D8, D10 as approved. **Preserved** `INVALID_BLOCKED_SOURCE_DEFINITION_CLOSED_BY_D10` (D10 closure unchanged). **Updated** §6.2 D9 disposition, §6.3 D10 disposition, §10.1 D1 path, §12.0.2 D3 pending state, §19 final verdict to reflect the new maintainer-authority framework. PR #21 / PR #23 / PR #60 / Issue #20 untouched; no fixture / no expected-output / no implementation authorized. |
