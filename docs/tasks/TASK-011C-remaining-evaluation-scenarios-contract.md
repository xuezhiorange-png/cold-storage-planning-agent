# TASK-011C Remaining Evaluation Scenarios — Frozen V1 Contract

> **Status:** Frozen V1 contract. The V1 contract is bound by `TASK_011C_V1_CONTRACT_FROZEN` per PR #61 review `4679730144`. The contract is frozen. Implementation, fixture authoring, expected-output authoring, production-path execution, and production-integration prerequisite implementation are NOT authorized by this freeze decision. The PR remains Draft / Not merged / No Ready / No Merge.
> **This document is the canonical TASK-011C contract.** It supersedes all prior TASK-011C contract drafts in this branch's history; prior `D3_DECISION_PENDING` / `D9_DECISION_PENDING` / `TASK_011C_CONTRACT_FREEZE_BLOCKED_BY_D3_AND_D9` / `TASK_011C_CONTRACT_FREEZE_BLOCKED_BY_D9_ONLY` / `D9_ARCHITECTURE_DISPOSITION_PENDING` / `HIGH_THROUGHPUT_SOURCE_DEFINITION_PENDING` / `D3_EMPTY_LIST_NOT_APPROVED` / `D3_CANDIDATE_EXCLUDED_JSON_PATHS=NOT_PROPOSED` wording in prior round change-log rows is preserved only as labeled historical audit trace, never as current operative status.
> **V1 scope (this round):** the **only** scenarios in V1 are `baseline_feasible` (already frozen by TASK-011B) and `invalid_blocked` (D10 source-defined). **`high_throughput_review` is REMOVED from V1 scope** and is **deferred** to a future production-integration prerequisite round (see §21).
> **All D3-D10 decisions (this round):** D1, D2, D3, D4, D5, D6, D7, D8, D10 **APPROVED**. D9 **DEFERRED_FROM_TASK_011C_V1** (high-throughput production-integration prerequisite; no V1 obligation; no task number assigned).

---

## 0. Preamble

This document is the **frozen V1 contract** for TASK-011C = the remaining evaluation scenarios plus the manifest / runner / canonicalization / cleanup completeness that TASK-011B did not deliver. The contract targets the **4 implementation gaps for V1** (manifest, runner, canonicalization, cleanup), scoped strictly to `baseline_feasible` (TASK-011B-frozen) and `invalid_blocked` (D10 source-defined). The V1 contract is bound by `TASK_011C_V1_CONTRACT_FROZEN` per PR #61 review `4679730144`.

In this round, the binding maintainer decisions for TASK-011C are recorded as follows:

```
D1_APPROVED
D2_APPROVED
D3_APPROVED
D4_APPROVED
D5_APPROVED
D6_APPROVED
D7_APPROVED
D8_APPROVED
D10_APPROVED
D9_DEFERRED_FROM_TASK_011C_V1
D9_DISPOSITION=DEFERRED_TO_PRODUCTION_INTEGRATION_PREREQUISITE
D9_DECISION_CLOSED_FOR_TASK_011C_V1
D9_HIGH_THROUGHPUT_REVIEW_DEFERRED
D9_EXACT_INPUT_SEARCH_CLOSED_WITHOUT_SOURCE_DEFINITION
```

**D3 evidence base (binding, this round):**
- `D3_V1_EXCLUDED_JSON_PATHS=[]` (empty exclusion set, evidence-established by D3 evidence-validation round)
- `D3_SQLITE_REPEATABILITY=PASS`
- `D3_POSTGRESQL_REPEATABILITY=PASS`
- `D3_CROSS_BACKEND_PARITY=PASS`
- `D3_PROJECTED_DIFFERENCE_COUNT=0`
- `COMBINED_SOURCE_HASH_PARITY=PASS`
- `CONTENT_HASH_PARITY=PASS`
- `CANDIDATES_SNAPSHOT_PARITY=PASS`
- `DECIMAL_SERIALIZATION_PARITY=PASS`
- `D3_AUDIT_RESULT=NOT_ESTABLISHED` for the V1 legacy wording is **superseded** by `D3_APPROVED` with empty exclusion set
- `D3_EVIDENCE_RESULT=EMPTY_EXCLUSION_SET_SUPPORTED`
- `D3_DECISION_CLOSED`
- `D3_EMPTY_EXCLUSION_SET_APPROVED`
- `D3_EMPTY_LIST_NOT_APPROVED` and `D3_CANDIDATE_EXCLUDED_JSON_PATHS=NOT_PROPOSED` are removed from current operative status; they appear only in historical audit trace.
- **No wildcard exclusions are permitted** under this contract.
- **No additional exact paths are approved** beyond the empty set (the 4 runtime-only fields `scheme_run.id`, `scheme_run.created_at`, `scheme_run.completed_at`, `scheme_run.database_backend` are already structurally absent from the projected output and do not require an explicit exclusion set; they are documented in §10.5 evidence ledger for audit traceability).

**Maintainer authority (binding, this round):**
- D3 approval + D9 deferral: PR #61 review `4679707878` (D3 approval)
- D9 Path A deferral: PR #61 review `4679711007` (D9 disposition)

**D9 disposition (binding, this round):**
- `D9_READ_ONLY_EVIDENCE_VALIDATION_COMPLETED`
- `D9_EVIDENCE_RESULT=CURRENT_MAIN_UNREACHABLE`
- `D9_BLOCKER_TYPE=PRODUCTION_INTEGRATION_ARCHITECTURE_GAP`
- `D9_DISPOSITION=DEFERRED_FROM_TASK_011C_V1`
- `D9_HIGH_THROUGHPUT_REVIEW_DEFERRED`
- `D9_EXACT_INPUT_SEARCH_CLOSED_WITHOUT_SOURCE_DEFINITION`
- `D9_DECISION_CLOSED_FOR_TASK_011C_V1`

The future production-integration prerequisite scope is described in §21; it is **NOT** authorized for implementation by this contract-freeze proposal. The deferred scope requires a separate, future Charles authorization; the future round is NOT pre-assigned any task number (TASK-011D is NOT authorized; no task number is unilaterally assigned in this round).

```
TASK_011C_V1_CONTRACT_FROZEN
TASK_011C_CONTRACT_FREEZE_AUTHORITY=PR61_REVIEW_4679730144
TASK_011C_V1_SCOPE_CLOSED
TASK_011C_MAINTAINER_AUTHORITY_ESTABLISHED
TASK_011C_REPOSITORY_FREEZE_STAMP_COMPLETE
D1_APPROVED
D2_APPROVED
D3_APPROVED
D3_V1_EXCLUDED_JSON_PATHS=[]
D4_APPROVED
D5_APPROVED
D6_APPROVED
D7_APPROVED
D8_APPROVED
D9_DEFERRED_FROM_TASK_011C_V1
D9_HIGH_THROUGHPUT_REVIEW_DEFERRED
D9_DECISION_CLOSED_FOR_TASK_011C_V1
D10_APPROVED
TASK_011C_IMPLEMENTATION_NOT_AUTHORIZED
EXPECTED_OUTPUT_AUTHORING_NOT_AUTHORIZED
FIXTURE_AUTHORING_NOT_AUTHORIZED
PRODUCTION_PREREQUISITE_IMPLEMENTATION_NOT_AUTHORIZED
PR61_OPEN_DRAFT_NOT_MERGED
READY_NOT_AUTHORIZED
MERGE_NOT_AUTHORIZED
```

**Historical reference (NOT current operative status, preserved for audit traceability):** the prior-round V1 final decision integration operative markers `TASK_011C_FINAL_DECISIONS_INTEGRATED` / `TASK_011C_CONTRACT_FREEZE_PROPOSAL_READY` / `TASK_011C_CONTRACT_NOT_YET_FROZEN` / `TASK_011C_CONTRACT_FREEZE_NOT_AUTHORIZED` / `TASK_011C_CONTRACT_AUTHORED_PENDING_CHARLES_FREEZE` / `proposal ready for Charles review` / `Charles retains the contract-freeze decision authority` are preserved in the §20 change log as historical audit trace; they are NOT current operative status. The current operative V1 status is `TASK_011C_V1_CONTRACT_FROZEN` per PR #61 review `4679730144`.

This document **does not**:
- Authorize TASK-011C implementation in this round or in any future round without separate Charles authorization.
- Authorize authoring of any expected-output file (golden) for the V1 scenarios beyond what TASK-011B already froze for `baseline_feasible`.
- Create a TASK-011C implementation branch, PR, commit, push, Ready, or Merge.
- Mutate PR #21, PR #23, PR #60, Issue #20, Issue #22, or any other GitHub object.
- Modify any tracked file outside `docs/tasks/TASK-011C-remaining-evaluation-scenarios-contract.md`.
- Touch any production code, evaluation runner code, evaluation fixture, manifest, expected output, baseline golden, sign-off, comparison policy, bootstrap, coefficients, migration, frontend, docker, .github, pyproject, uv.lock, or .gitignore.
- Implement or authorize the deferred `high_throughput_review` scenario or any production-integration prerequisite (TASK-011D / §21).

This round **only modifies** `docs/tasks/TASK-011C-remaining-evaluation-scenarios-contract.md`. This document records the V1 freeze decision per PR #61 review `4679730144`; the freeze is binding but does NOT authorize implementation, fixture authoring, expected-output authoring, Ready, or Merge. Implementation requires separate, future Charles authorization.

---

## 1. Authority and status

**Document status: `TASK_011C_V1_CONTRACT_FROZEN`**

**Binding freeze authority:** **PR #61 Review `4679730144`** (V1 contract freeze decision; binding; recorded in this contract as `TASK_011C_CONTRACT_FREEZE_AUTHORITY=PR61_REVIEW_4679730144`).

The V1 contract is **frozen** by the binding freeze authority. D1 / D2 / D3 / D4–D8 / D10 are APPROVED. D9 is DEFERRED_FROM_TASK_011C_V1 (high-throughput production-integration prerequisite; no V1 obligation; no task number assigned). The V1 scope is `baseline_feasible` (TASK-011B-frozen) + `invalid_blocked` (D10 source-defined); `high_throughput_review` is REMOVED from V1.

**The contract is frozen. Implementation is not authorized by the freeze decision.** Implementation of the V1 contract requires a separate, future Charles authorization and is NOT in this round's scope and NOT in this freeze decision's scope.

**Binding maintainer authority (PR #61 top-level comment `4950035046` + review `4679707878` for D3 + review `4679711007` for D9):**

```
D1_CANONICALIZATION_AUTHORITY=backend/src/cold_storage/evaluation/canonicalization.py
    ::canonicalize_production_outputs(value, *, excluded_paths)

D2_JSON_VALUE_DOMAIN=
    STRICT_JSON_VALUES_ONLY
    TWO_LAYER_FAIL_CLOSED_VALIDATION
    NO_IMPLICIT_COERCION

D3_NORMALIZED_OUTPUT_VOLATILITY_AUDIT=COMPLETED
D3_EVIDENCE_RESULT=EMPTY_EXCLUSION_SET_SUPPORTED
D3_V1_EXCLUDED_JSON_PATHS=[]
D3_SQLITE_REPEATABILITY=PASS
D3_POSTGRESQL_REPEATABILITY=PASS
D3_CROSS_BACKEND_PARITY=PASS
D3_PROJECTED_DIFFERENCE_COUNT=0
D3_APPROVED
NO_WILDCARD_EXCLUSIONS
NO_ADDITIONAL_EXACT_PATHS_APPROVED

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

**Pending decisions / dispositions (per comment `4950035046` + reviews `4679707878` / `4679711007`):**

```
D9_DISPOSITION=DEFERRED_FROM_TASK_011C_V1
D9_DEFERRED_TO_PRODUCTION_INTEGRATION_PREREQUISITE
D9_HIGH_THROUGHPUT_REVIEW_DEFERRED
D9_EXACT_INPUT_SEARCH_CLOSED_WITHOUT_SOURCE_DEFINITION
D9_DECISION_CLOSED_FOR_TASK_011C_V1
D9_EVIDENCE_RESULT=CURRENT_MAIN_UNREACHABLE
D9_BLOCKER_TYPE=PRODUCTION_INTEGRATION_ARCHITECTURE_GAP
```

D3 is approved as `D3_V1_EXCLUDED_JSON_PATHS=[]` (no wildcard; no additional exact paths). Wildcard exclusions remain forbidden. The 4 runtime-volatile fields identified in the D3 evidence round (`scheme_run.id`, `scheme_run.created_at`, `scheme_run.completed_at`, `scheme_run.database_backend`) are structurally absent from the projected output schema, so they do not need to appear in the exclusion set; they are documented in §10.5 evidence ledger for audit traceability.

D9 is closed for TASK-011C V1 with disposition `DEFERRED_FROM_TASK_011C_V1`; the deferred production-integration prerequisite scope is described in §21; it requires a separate future Charles authorization and is NOT pre-assigned any task number (`TASK011D_NOT_AUTHORIZED`).

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

**TASK-011C implementation status (this round):**

```
TASK_011C_V1_CONTRACT_FROZEN
TASK_011C_REPOSITORY_FREEZE_STAMP_COMPLETE
TASK_011C_IMPLEMENTATION_NOT_AUTHORIZED
TASK_011C_V1_SCOPE_CLOSED
TASK011D_NOT_AUTHORIZED
TASK12_NOT_AUTHORIZED
PRODUCTION_PREREQUISITE_IMPLEMENTATION_NOT_AUTHORIZED
READY_NOT_AUTHORIZED
MERGE_NOT_AUTHORIZED
EXPECTED_OUTPUT_AUTHORING_NOT_AUTHORIZED
FIXTURE_AUTHORING_NOT_AUTHORIZED
```

**Contract-freeze status (this round):**

```
TASK_011C_V1_CONTRACT_FROZEN
TASK_011C_REPOSITORY_FREEZE_STAMP_COMPLETE
TASK_011C_V1_SCOPE_CLOSED
D1_APPROVED
D2_APPROVED
D3_APPROVED
D3_V1_EXCLUDED_JSON_PATHS=[]
D4_APPROVED
D5_APPROVED
D6_APPROVED
D7_APPROVED
D8_APPROVED
D9_DEFERRED_FROM_TASK_011C_V1
D9_HIGH_THROUGHPUT_REVIEW_DEFERRED
D9_DECISION_CLOSED_FOR_TASK_011C_V1
D10_APPROVED
INVALID_BLOCKED_SOURCE_DEFINITION_CLOSED_BY_D10
HIGH_THROUGHPUT_REVIEW_NOT_IN_V1_SCOPE
```

While TASK-011C V1 contract is **frozen** (per PR #61 review `4679730144`):
- Charles MUST NOT sign off the contract as frozen again (the freeze is already binding per the recorded freeze authority).
- PR #61 MUST NOT be marked Ready.
- PR #61 MUST NOT be merged.
- TASK-011C implementation MUST NOT be authorized.
- Fixture authoring (other than what TASK-011B already froze for `baseline_feasible`) MUST NOT be authorized.
- Expected-output authoring (other than what TASK-011B already froze for `baseline_feasible`) MUST NOT be authorized.
- Deferred production-integration prerequisite (§21) MUST NOT be implemented without separate future Charles authorization.

The D3 decision is closed (V1 exclusion set is `[]`; the 4 runtime-volatile fields are structurally absent from the projected output). The D9 decision is closed for V1 with deferral to §21. The V1 contract is frozen; the V1 scope is `baseline_feasible` (TASK-011B-frozen) + `invalid_blocked` (D10 source-defined); `high_throughput_review` is NOT in V1.

---

## 2. Objectives and scope

### 2.1 Objectives

TASK-011C V1 (when implemented) must close the 4 remaining implementation gaps from the post-B audit by providing:

1. A versioned evaluation manifest schema that supports multiple scenarios (baseline, invalid-blocked) with per-scenario expected outputs, comparison policies, and provenance.
2. An `invalid_blocked` scenario that exercises a **real production validation/blocker pathway** (not an evaluation-layer-injected exception).
3. A repeatable runner that executes multiple scenarios in one invocation, with typed run.json / summary.json / raw and normalized artifacts, fail-closed validation, and zero exit only on full match.
4. Use of the single canonicalization authority `canonicalize_production_outputs` (per §3.1 / §10 / D1), with stale-output detection and per-scenario cleanup discipline.

> **Historical reference (NOT current operative status):** A prior round of this contract proposed a 5th gap (G1: `high_throughput_review` scenario with substantively distinct production outcome). This 5th gap is REMOVED from V1 in this round. The `high_throughput_review` scenario is **deferred** to the production-integration prerequisite (§21). It is **not** in V1 scope; it is **not** a V1 obligation. The 4-item objective list above is the current V1 scope.

### 2.2 Scope (this contract)

This contract-freeze proposal proposes the following clauses; the Charles-approved clauses are binding, the rest remain `PROPOSED / PENDING CONTRACT FREEZE`:
- Scenario set (§6) — `baseline_feasible` (TASK-011B-frozen) + `invalid_blocked` (D10 source-defined)
- Manifest contract (§7) — D5/D6/D7/D8 binding per comment `4950035046`
- Expected-output authority flow (§8) — proposed, pending contract freeze
- Runner contract (§9) — proposed, pending contract freeze
- Canonicalization contract (§10) — **D1 signed: §10 binding; D2 signed: §10.4 strict JSON; D4 signed: §10.4 numeric defaults; D3 approved: §10.5 evidence ledger + empty exclusion set; all canonicalization rules per §10.2/§10.3/§10.4 are binding**
- Cleanup + stale-output contract (§11) — proposed, pending contract freeze
- SQLite / PostgreSQL boundary (§12) — **D3 approved: §12 boundary clauses apply; D3 evidence ledger at §10.5 confirms cross-backend parity; D3 final exclusion set is empty (`D3_V1_EXCLUDED_JSON_PATHS=[]`)**
- Future implementation allowlist proposal (§13) — D1, D6, D7, D8 signed: §13 updated to reflect final canonicalization/loader/distribution module names; D3 test name corrected; `high_throughput_review`-dedicated entries REMOVED; all other allowlist items remain proposed, pending contract freeze
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
- `high_throughput_review` scenario (DEFERRED to §21; not in V1 scope)
- Production code, formula, coefficient, threshold, scoring, or review-rule change
- Restoration of `production_seeding.py` or any evaluation-owned production ORM fabrication

---

## 3. Definitions

- **Scenario** — A named evaluation execution unit, identified by `scenario_id`, with declared fixture, expected outcome class, expected output (when required), and comparison policy. V1 scenarios: `baseline_feasible` (TASK-011B-frozen) and `invalid_blocked` (D10 source-defined).
- **Manifest** — A versioned JSON document declaring all scenarios in a run-suite, with per-scenario fixture / expected output / outcome class / comparison policy / provenance.
- **Schema version** — The literal `schema_version` string the manifest validator reads first. Frozen at `"1.0"` per Charles **D5**. Unknown / missing / non-`"1.0"` values are rejected fail-closed.
- **Manifest loader** — Single entry point `load_and_validate_manifest` at `backend/src/cold_storage/evaluation/manifest.py` per Charles **D6**. Loads schema from `importlib.resources`, deserializes, validates the v1 schema, and returns a typed `Manifest`.
- **Manifest schema path** — `backend/src/cold_storage/evaluation/schema/manifest.schema.json`. Package-owned, single path; no copy at any other location.
- **Canonicalization** — The single function `canonicalize_production_outputs(value, *, excluded_paths)` at `backend/src/cold_storage/evaluation/canonicalization.py` per Charles **D1**. No second canonicalizer is permitted.
- **Expected output** — A tracked JSON file at `backend/tests/evaluation/data/expected/{scenario_id}.v{revision}.json` that captures the production-path ground truth for a scenario.
- **Comparison policy** — Per-leaf classification (exact / decimal canonical / excluded) used to compare runtime normalized output against the expected output. Per **D4**, default is exact equality; no global float tolerance; no per-field tolerance unless separately Charles-approved.
- **Sign-off** — Charles-approved identity for a specific expected-output commit, recorded in a sign-off document with explicit `STATUS: APPROVED` markers.
- **Review field vocabulary** — Single mapping table per §6.4.4: production `requires_review` → normalized `requires_review` → expected-output `review_required` (baseline-compatible) + derived `review_state`.

> **Historical reference (NOT current operative status):** a prior round of this contract included a definition for `High-throughput review signal source`. This definition is REMOVED from V1; it is preserved in the change log as historical audit trace. The V1 contract does NOT define any `high_throughput_review` scenario, signal source, or production rule.

---

## 4. Golden case set (V1)

TASK-011C V1 covers the following scenarios (G2 plus the existing TASK-011B-frozen baseline as regression anchor):

| scenario_id            | scope                                       | fixture status           | expected output status                                                                                  |
|---|---|---|---|
| `baseline_feasible`    | Already approved (TASK-011B); regression anchor | Frozen                  | Frozen (`backend/tests/evaluation/data/expected/baseline_feasible.v1.json`); sign-off `f274db66…`        |
| `invalid_blocked`      | New (G2); **D10 chosen — source definition closed** | Authoring requires sign-off | Authoring requires sign-off; per Charles D10 contract below in §6.3 |

> **V1 scope is exactly the 2 scenarios above.** `high_throughput_review` is **NOT** in V1 scope; it is REMOVED from V1 and DEFERRED to §21 (production-integration prerequisite). No alternative high-throughput scenario is invented in this round.

The manifest MAY carry additional scenarios in the future (including a future `high_throughput_review` after §21 is implemented under separate Charles authorization); each requires its own sign-off and must satisfy the substantively-distinct property.

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
| **S26** | D3 evidence-validation round `4679707878` (PR #61 review) | Review | D3 approval; `D3_V1_EXCLUDED_JSON_PATHS=[]`; cross-backend parity evidence; projected difference count = 0 |
| **S27** | D9 disposition round `4679711007` (PR #61 review) | Review | D9 Path A deferral; `D9_DEFERRED_FROM_TASK_011C_V1`; `D9_HIGH_THROUGHPUT_REVIEW_DEFERRED` |

---

## 6. Scenario set (V1)

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

### 6.2 High-throughput / review-required — REMOVED FROM V1 (deferred to §21)

> **Current operative status (this round):** `high_throughput_review` is **REMOVED from V1 scenario set** and **DEFERRED** to the production-integration prerequisite described in §21. The V1 contract does NOT define a `high_throughput_review` scenario; the V1 contract does NOT bind any production rule to a high-throughput threshold; the V1 contract does NOT assert any `requires_review=true` + non-empty `review_reasons` invariant for any V1 scenario.

> **Historical reference (NOT current operative status, preserved for audit traceability):** Prior rounds of this contract proposed a `high_throughput_review` scenario under G1 with `execution_outcome=SUCCEEDED` + `persisted_scheme_status=completed` + `requires_review=true` + `review_state=REQUIRED` + `cli_exit_5_used=false` + `expected_output_kind=STRUCTURED_ASSERTIONS_ONLY` + `full_golden=NOT_AUTHORIZED`. The proposed invariants were: `HIGH_THROUGHPUT_REVIEW_EXACT_FOUR_FIELDS` (the four business invariants MUST hold for both SQLite and PostgreSQL) and `HIGH_THROUGHPUT_REVIEW_REAL_PRODUCTION_REVIEW_SIGNAL` (the review signal MUST come from a real production review rule, forbidden via correlation ID / scenario ID / runner-level reclassification / CLI-level special-case / test-only relabeling / hand-editing the expected-output / modifying production formula). The proposed `current-main observed fact` blocks cited `_coefficient_review` in `backend/src/cold_storage/modules/calculations/domain/service.py:89, 189, 274, 309` and `DEMO_INVESTMENT_REQUIRES_REVIEW` / `DEMO_ASSUMPTIONS_REQUIRE_REVIEW` warnings as production-rule candidates. The prior-round D9 verdict was `D9_AUDIT_RESULT = NOT_ESTABLISHED` / `D9_EXACT_INPUT_EVIDENCE_NOT_ESTABLISHED` / `D9_CANDIDATE_INPUT_PATH = NOT_PROPOSED` / `D9_BASELINE_VALUE = NOT_PROPOSED` / `D9_CANDIDATE_VALUE = NOT_PROPOSED` / `D9_EXPECTED_REVIEW_REASON = NOT_ESTABLISHED`. **All of this prior-round content is REMOVED from V1 in this round**; it is preserved in the change log as historical audit trace only.

The `high_throughput_review` scenario is NOT in V1 scope; it is NOT a V1 obligation; it is NOT a V1 acceptance criterion. The deferred scope is described in §21.

### 6.3 Invalid / blocked (G2) — D10 approved per binding maintainer authority

D10 status (per binding maintainer authority comment `4950035046`):

```
D10_INVALID_BLOCKED_PATH = PRODUCTION_CALCULATION_PROJECTION_MISSING_TOTAL_AREA_M2
D10_APPROVED
INVALID_BLOCKED_SOURCE_DEFINITION_CLOSED_BY_D10
```

D10 is approved. The `invalid_blocked` source definition is **closed by D10**; the contract-freeze blocker is **REMOVED** (D3 approved + D9 deferred). The V1 freeze blocker is no longer `D3 AND D9`; it is the contract-freeze decision itself, awaiting Charles.

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

> **Historical reference (NOT current operative status):** the prior round of this contract described the review-field vocabulary as the mechanism by which `high_throughput_review` would carry `requires_review=true` + `review_state=REQUIRED` + non-empty `review_reasons`. The mapping table above is preserved as a single-source-of-truth for the V1 scenarios; the V1 scenarios do not require a non-empty `review_reasons` because `high_throughput_review` is NOT in V1. The mapping remains in the contract for forward-compatibility with the deferred scope (§21).

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

### 7.2 CLI exit code (D10-only, frozen)

The V1 contract does NOT define a CLI exit code for a successful high-throughput run (because `high_throughput_review` is not in V1). The CLI exit code is governed by D10 for `invalid_blocked`:

```
invalid_blocked CLI exit: non-zero (typed reason code PROJ_INPUT_INVALID)
baseline_feasible CLI exit: zero on full match
```

```
CLI_EXIT_5_RESERVED_NOT_USED_BY_TASK011C
```

> **Historical reference (NOT current operative status):** a prior round of this contract documented `high_throughput_review` MUST exit with code `0` (SUCCEEDED) and asserted `cli_exit_5_used=false`. The prior-round `cli_exit_5_used=false` is REMOVED from V1 because the high-throughput scenario is no longer in V1 scope. The `EXIT_REVIEW_REQUIRED = 5` reservation remains in code for backward compatibility but is not used by TASK-011C.

---

## 8. Expected-output authority flow (per-file authority, not per-file freeze)

This section restates the 8-step authority flow from §8 of the contract. "Per-file freeze" has been replaced by "per-file authority status" — each expected-output file has a current authority status (frozen / not yet authored), NOT a freeze time or governance relation.

1. **Source-definition approval** — Charles approves the substantive source definition (G2: invalid-blocked validation defect in §6.3) as a separate document.
2. **SQLite candidate capture** — Implementation round runs the scenario in SQLite and captures a `candidate.v{revision}.sqlite.json` artifact (gitignored).
3. **PostgreSQL candidate capture** — Implementation round does the same on PostgreSQL, producing `candidate.v{revision}.postgresql.json` (gitignored).
4. **Cross-backend substantive comparison** — Every canonical leaf in `exact_match_fields` MUST match; every leaf in `decimal_fields` MUST match within the declared decimal quantization; every leaf in `excluded_fields` (none in TASK-011C V1 per **D3 approved**, `D3_V1_EXCLUDED_JSON_PATHS=[]`) MUST be ignored.
5. **Proposed tracked diff** — Implementation produces a `git diff` between the proposed tracked expected JSON and the empty file (or the previously approved expected JSON, for amendments).
6. **Reviewer sign-off** — Charles reviews the diff + cross-backend comparison + substantive distinctness / validation defect verification, and posts a sign-off with `STATUS: APPROVED` / `CHARLES_VERDICT: APPROVED` / `EXPECTED_OUTPUT_COMMIT_SHA: <commit>`.
7. **Separate implementation authorization** — Only after sign-off, Charles issues a per-message authorization to commit the expected JSON to a tracked location.
8. **Commit only after sign-off** — Implementation commits the expected JSON with `EXPECTED_OUTPUT_COMMIT_SHA: <sign-off commit SHA>` and the `scenario_id`.

**Per-file authority status (this round):**

| File                                                              | Status                                | Authority                                                                                       |
|---|---|---|
| `backend/tests/evaluation/data/expected/baseline_feasible.v1.json`   | ALREADY FROZEN                        | TASK-011B sign-off `f274db66…`                                                                  |
| `backend/tests/evaluation/data/expected/invalid_blocked.v1.json`       | NOT YET AUTHORIZED                   | Requires §8 authority flow (D10 source definition is CLOSED)                                  |

> **V1 contract scope**: V1 has exactly 2 scenarios, hence 2 rows in the per-file authority table. The `high_throughput_review.v1.json` row that appeared in prior rounds is REMOVED from V1; the high-throughput expected-output file is NOT a V1 obligation. If/when a future round (§21) implements the deferred `high_throughput_review` scenario, the table will be amended under separate Charles authorization.

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

**Allowed distinction (frozen, V1):**
- `business outcome` — production result (`SUCCEEDED` / `BLOCKED` / `INVALID_INPUT` per D10).
- `evaluation result` — manifest declared vs runtime (`pass` / `fail` / `infrastructure_error`).
- `infrastructure failure` — runner cannot complete the scenario.

Combinations:
- `business outcome = "SUCCEEDED"` + `evaluation_result = "pass"` (e.g., `baseline_feasible` run) — exit zero.
- `business outcome = "INVALID_INPUT"` + `evaluation_result = "pass"` (`invalid_blocked` run with expected exception) — exit zero for that scenario.
- `business outcome = "SUCCEEDED"` + `evaluation_result = "fail"` — non-zero exit (cross-backend parity fail or hash mismatch).
- `infrastructure_failure` — non-zero exit regardless of business outcome.

> **Historical reference (NOT current operative status):** a prior round of this contract documented `business outcome = "SUCCEEDED" + evaluation_result = "pass"` for a high-throughput run with `requires_review=true`. That example is REMOVED from V1 because `high_throughput_review` is not in V1. The remaining combinations are unchanged.

---

## 10. Canonicalization contract
(D1, D2, D3, D4 approved)

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

### 10.3 Canonicalization properties
(D3 approved, empty exclusion set; D3-bound clauses now binding)

| Property | Contract requirement |
|---|---|
| Strict JSON values only | Only JSON-serializable values. No Python tuples, no sets, no custom objects. |
| No `NaN` / `Infinity` | Reject (raise `CanonicalizationError`). |
| Decimal fixed-scale representation | `Decimal` values serialized with explicit fixed scale, e.g. `quantize=Decimal("0.01")`. No scientific notation. No `float()` conversion. |
| Exact array order | Arrays serialized in declared order. Reordering forbidden. |
| **Ignored paths declared and justified** | Per **D3 approved**, `D3_V1_EXCLUDED_JSON_PATHS=[]` (empty set). The 4 runtime-volatile fields identified in the D3 evidence round (`scheme_run.id`, `scheme_run.created_at`, `scheme_run.completed_at`, `scheme_run.database_backend`) are **structurally absent** from the projected output schema; they do NOT require explicit exclusion. The empty V1 exclusion set is binding. **No path may be ignored in V1.** Any future exclusion requires triple `(governed_artifact_name, jsonpath, source_evidence)` and Charles authorization. |
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

### 10.5 D3 normalized-output volatility audit — APPROVED (D3 evidence-validation round)

**Audit objective:** determine whether the normalized output is free of all runtime-volatile values such that an empty V1 exclusion list is supportable.

**Audit method:** evidence-validation round executed 4 fully independent baseline runs (SQLite×2 + PostgreSQL×2) through the production path on real SQLite temp files and isolated temporary PostgreSQL databases. Each run was compared against the same scenario with a fresh in-memory DB and identical seed-helper, source-binding semantics, and weight revision. The 4 captures produced byte-identical projected output (SHA-256 `118a10cc7235069cf44ae60617c3ca3128b410363c63a9989250d213a7f9c158` × 4) and identical production `content_hash` (`ea4ab8cd7f73b50c8cd83865adc9ec90428d8d60a9fc2e7d823a0c8fdb16fe46` × 4) and identical `combined_source_hash` (`60e11cacea5868d1650e40f72186618e4a01f29b1655e9aa531deccaf0633206` × 4).

**D3 evidence (binding, this round):**

```
D3_APPROVED
D3_EVIDENCE_RESULT=EMPTY_EXCLUSION_SET_SUPPORTED
D3_V1_EXCLUDED_JSON_PATHS=[]
D3_EMPTY_EXCLUSION_SET_APPROVED
D3_DECISION_CLOSED
D3_SQLITE_REPEATABILITY=PASS
D3_POSTGRESQL_REPEATABILITY=PASS
D3_CROSS_BACKEND_PARITY=PASS
D3_PROJECTED_DIFFERENCE_COUNT=0
COMBINED_SOURCE_HASH_PARITY=PASS
CONTENT_HASH_PARITY=PASS
CANDIDATES_SNAPSHOT_PARITY=PASS
DECIMAL_SERIALIZATION_PARITY=PASS
```

**D3 raw-layer differences (audited, structurally absent from projected output):**

| Path | Category | Status |
|---|---|---|
| `$.scheme_run.id` | RUNTIME_ID (UUID4) | Structurally absent from projected output |
| `$.scheme_run.created_at` | TIMESTAMP | Structurally absent from projected output |
| `$.scheme_run.completed_at` | TIMESTAMP | Structurally absent from projected output |
| `$.scheme_run.database_backend` | DATABASE_BACKEND_MARKER | Structurally absent from projected output |

**D3 audit rules (binding, per review `4679463188` + this round's evidence):**

```
NO_WILDCARD_EXCLUSIONS
NO_ADDITIONAL_EXACT_PATHS_APPROVED
EMPTY_LIST_ALLOWED_AND_APPROVED_BASED_ON_SCHEMA_AUDIT
D3_V1_EXCLUDED_JSON_PATHS=[]
```

The D3 evidence is sufficient to close D3. The V1 exclusion set is the empty set. No future exclusion may be added to V1 without separate Charles authorization. The 4 runtime-volatile fields above are **structurally absent** from the projected output schema and do not require explicit exclusion set membership; they are documented here for audit traceability.

> **Historical reference (NOT current operative status, preserved for audit):** the prior-round D3 evidence-ledger content (read-only audit, docs-only verdict `D3_AUDIT_RESULT = NOT_ESTABLISHED`, candidate exclusion set `NOT_PROPOSED`, `D3_DECISION_PENDING`, `D3_EMPTY_LIST_NOT_APPROVED`) is superseded by this round's D3 approval. The prior-round wording is preserved in the change log as historical audit trace.

### 10.6 D9 disposition — DEFERRED FROM TASK-011C V1

> **Current operative status (this round):** D9 is **DEFERRED_FROM_TASK_011C_V1** per PR #61 review `4679711007`. The `high_throughput_review` scenario is REMOVED from V1. The deferred production-integration prerequisite scope is described in §21. The V1 contract does NOT bind any production rule to a high-throughput threshold; the V1 contract does NOT require any input that would trigger `requires_review=true` + non-empty `review_reasons` for V1 scenarios. D9 is **closed for TASK-011C V1**; it is NOT closed in the abstract; it is a deferred item requiring a separate future Charles authorization under a separately designated round.

**D9 disposition (binding, this round):**

```
D9_READ_ONLY_EVIDENCE_VALIDATION_COMPLETED
D9_EVIDENCE_RESULT=CURRENT_MAIN_UNREACHABLE
D9_BLOCKER_TYPE=PRODUCTION_INTEGRATION_ARCHITECTURE_GAP
D9_DISPOSITION=DEFERRED_FROM_TASK_011C_V1
D9_DEFERRED_TO_PRODUCTION_INTEGRATION_PREREQUISITE
D9_HIGH_THROUGHPUT_REVIEW_DEFERRED
D9_EXACT_INPUT_SEARCH_CLOSED_WITHOUT_SOURCE_DEFINITION
D9_DECISION_CLOSED_FOR_TASK_011C_V1
D9_HIGH_THROUGHPUT_REVIEW_NOT_IN_V1_SCOPE
```

> **Historical reference (NOT current operative status, preserved for audit):** the prior-round D9 evidence-ledger content (read-only audit, production rule identified as `_coefficient_review` in `backend/src/cold_storage/modules/calculations/domain/service.py:89, 189, 274, 309`, candidate warning code `COEFFICIENT_REQUIRES_REVIEW`, candidate message `计算使用了未批准或需复核的系数`, `D9_AUDIT_RESULT = NOT_ESTABLISHED`, `D9_CANDIDATE_INPUT_PATH = NOT_PROPOSED`, `D9_BASELINE_VALUE = NOT_PROPOSED`, `D9_CANDIDATE_VALUE = NOT_PROPOSED`, `D9_EXPECTED_REVIEW_REASON = NOT_ESTABLISHED`, `D9_DECISION_PENDING`, `D9_NOT_APPROVED_DURING_THIS_ROUND`) is **superseded** by the D9 deferral. The prior-round production-rule identification is preserved in the change log as historical audit trace; the future production-integration prerequisite round (§21) may re-open the search with separate Charles authorization and a separately scoped evidence-validation round; it does NOT inherit the prior-round's verbatim candidate values.

The deferred scope is described in §21; it is NOT authorized for implementation by this contract-freeze proposal.

---

## 11. Runner + run-artifact contract

### 11.0 Current main behavior vs TASK-011C contract (read-only)

Read-only description; current `run_directory.py` computes paths only, does not write `run.json` / `summary.json` / normalized artifacts. TASK-011C contract describes what a future separately authorized evidence-validation round, NOT an implementation round, may write.

### 11.1 `run.json` schema

Proposed, pending contract freeze. The semantic-versioning literal is bound to D5 (`schema_version` literal in nested run.json follows `"task011c-run.v1"` as a string label, not a numeric version). The other field shapes and semantics remain proposed and require Charles sign-off before freeze.

### 11.2 `summary.json` schema

Proposed, pending contract freeze. The requirement that `summary.normalized_artifact_sha256` MUST be equal across SQLite and PostgreSQL is **binding** per D3 approved (`D3_V1_EXCLUDED_JSON_PATHS=[]` + `D3_CROSS_BACKEND_PARITY=PASS` + `COMBINED_SOURCE_HASH_PARITY=PASS` + `CONTENT_HASH_PARITY=PASS`). No `conditional on the D3 final exclusion set decision` wording remains; the D3 decision is closed.

### 11.3 Run-artifact semantics

Proposed, pending contract freeze. Canonical byte generation, when separately authorized for implementation, must use the single D1 canonicalization authority `canonicalize_production_outputs(...)`. Artifact naming, retention, raw/normalized payload shape, write timing, and cleanup semantics remain proposed and are not authorized for implementation in this round. The current round is a docs-only contract-freeze proposal; an evidence-validation round is not authorized and may not write artifacts.

---

## 12. SQLite / PostgreSQL boundary (D3 approved)

### 12.0 Field-by-field parity

Proposed, pending contract freeze. The business-authoritative field set below requires Charles sign-off before freeze.

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
| Deterministic calculated values             | `summary.normalized_artifact_sha256`     | SHA-256 of canonical bytes — **MUST match across SQLite and PostgreSQL** (binding per D3 approved) |
| Blocker / error code (D10)                   | `summary.error_or_blocker_result.code`   | `PROJ_INPUT_INVALID` (D10); must match across backends |
| Blocker / error field                        | `summary.error_or_blocker_result.field`  | `total_area_m2` (D10); must match across backends |
| Expected-output match result                | `summary.comparison_result` + per-leaf diff | must match |

### 12.0.1 Hash-category requirements

The three-tier hash policy is proposed, pending contract freeze. The cross-backend parity rule on `normalized_artifact_sha256` is **binding** per D3 approved (no longer conditional on a pending decision).

| Hash category                       | Cross-backend rule                                                                | Used for |
|---|---|---|
| `raw_artifact_sha256`               | Per-backend stable; NOT required equal across SQLite / PostgreSQL. Each backend records its own. | Integrity verification only. |
| `normalized_artifact_sha256`        | **MUST be equal across SQLite and PostgreSQL** (binding per D3 approved, `D3_CROSS_BACKEND_PARITY=PASS`, `COMBINED_SOURCE_HASH_PARITY=PASS`, `CONTENT_HASH_PARITY=PASS`). SHA-256 of canonical bytes from D1. | Cross-backend business parity. |
| `expected_output_sha256`            | Per scenario + revision (file-level hash). NOT cross-backend. | Repository-owned golden integrity. |

The contract explicitly **forbids** asserting `raw_artifact_sha256` is equal across SQLite and PostgreSQL while permitting backend-specific fields to differ. Such a combination is removed by the three-tier hash policy above.

### 12.0.2 Excluded paths — D3 APPROVED, empty V1 exclusion set

Per the binding maintainer authority comment `4950035046`, reviews `4679463188` and `4679707878` (D3 approval), and the D3 evidence-validation round:

```
D3_APPROVED
D3_EVIDENCE_RESULT=EMPTY_EXCLUSION_SET_SUPPORTED
D3_V1_EXCLUDED_JSON_PATHS=[]
D3_EMPTY_EXCLUSION_SET_APPROVED
D3_DECISION_CLOSED
D3_SQLITE_REPEATABILITY=PASS
D3_POSTGRESQL_REPEATABILITY=PASS
D3_CROSS_BACKEND_PARITY=PASS
D3_PROJECTED_DIFFERENCE_COUNT=0
NO_WILDCARD_EXCLUSIONS
NO_ADDITIONAL_EXACT_PATHS_APPROVED
```

The 4 runtime-volatile fields identified in the D3 evidence round (`scheme_run.id`, `scheme_run.created_at`, `scheme_run.completed_at`, `scheme_run.database_backend`) are **structurally absent** from the projected output schema and do NOT require explicit exclusion set membership. They are documented here for audit traceability.

A future excluded path (in a future amendment, NOT in this V1 contract-freeze proposal) requires:
- exact JSON path,
- source evidence that the field exists,
- proof of nondeterminism,
- proof that it is irrelevant to business-contract equivalence,
- explanation why deterministic generation cannot replace exclusion,
- separate Charles authorization.

Wildcard exclusions (e.g., `any *_id`) are **forbidden** in V1 and in all future amendments.

> **Historical reference (NOT current operative status, preserved for audit):** the prior-round §12.0.2 may-differ table that named `summary.run_identity`, `raw.database_session_uuid`, `raw.orchestration.attempt_id`, `raw.calculation_run_ids.*` as candidate paths pending audit and Charles approval is **superseded** by the D3 approval with empty V1 exclusion set. The prior-round wording is preserved in the change log as historical audit trace.

### 12.1 Boundary contract (general)

Proposed, pending contract freeze. The general cross-backend rules below require Charles sign-off.

| Boundary | Contract requirement |
|---|---|
| SQLite — full TASK-011C scenario acceptance | All V1 scenarios MUST pass on SQLite in `backend-sqlite` CI. |
| PostgreSQL — required where persistence / JSON behavior may differ | All V1 scenarios MUST also pass on PostgreSQL in `backend-postgresql` CI. |
| Substantive normalized result parity | Canonical bytes (per D1) of the normalized SQLite and PostgreSQL results MUST be byte-identical for `exact_match_fields` and `decimal_fields`. **No excluded fields in V1** (D3 approved, `D3_V1_EXCLUDED_JSON_PATHS=[]`). |
| Allowed backend-specific runtime metadata | Recorded separately per backend in `raw_artifact_sha256`. |
| Forbidden backend-specific business outcome drift | Runner MUST reject any scenario whose business-authoritative field differs between backends. |

---

## 13. Future implementation allowlist proposal (D1, D6, D7, D8, D3 updated)

This round's allowlist incorporates Charles-signed module names from D1 / D6 / D7 / D8, and the D3-approved exclusion status. **This round does NOT modify any of these files.** `high_throughput_review`-dedicated entries that appeared in prior rounds are **REMOVED** from this allowlist because the scenario is not in V1 scope; only allowlist entries that serve V1 scenarios OR have independent §6.3 / §10.1 / §10.4 contract authority remain.

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
| `backend/tests/evaluation/test_d3_excluded_paths_policy.py` (new) | D3 exact-path policy and approved-decision enforcement tests (D3 approved; V1 exclusion set is empty per `D3_V1_EXCLUDED_JSON_PATHS=[]`) | C-1 |
| `backend/tests/evaluation/test_d4_numeric_exact.py` (new) | D4 exact-only numeric tests | C-1 |
| `backend/tests/evaluation/test_d5_schema_version.py` (new) | D5 schema-version literal tests | C-1 |
| `backend/tests/evaluation/test_d6_manifest_loader.py` (new) | D6 loader tests | C-1 |
| `backend/tests/evaluation/test_d7_distribution.py` (new) | D7 setuptools package-data tests | C-1 |
| `backend/tests/evaluation/test_d8_resource_loading.py` (new) | D8 importlib.resources tests | C-1 |
| `backend/tests/evaluation/test_d10_invalid_blocked.py` (new) | D10 invalid-blocked scenario tests | C-2 |
| `backend/tests/evaluation/test_sqlite_acceptance.py` (extend) | Add C-scenario tests | C-2 |
| `backend/tests/evaluation/test_postgresql_acceptance.py` (extend) | Add C-scenario tests | C-2 |
| `backend/tests/evaluation/data/expected/invalid_blocked.v{revision}.json` (new, tracked) | Invalid-blocked expected output | C-3 — REQUIRES sign-off |
| `docs/tasks/TASK-011C-expected-outputs-invalid_blocked-reviewer-sign-off.md` (new, tracked) | Sign-off document | C-3 |
| `docs/tasks/TASK-011C-manifest-schema-design.md` (new, tracked) | Manifest schema design contract | C-1 — separate Charles authorization |

**Removed from V1 allowlist (were dedicated to `high_throughput_review`; scenario is not in V1 scope):**
- ~~`backend/tests/evaluation/data/expected/high_throughput_review.v{revision}.json`~~
- ~~`docs/tasks/TASK-011C-expected-outputs-high_throughput_review-reviewer-sign-off.md`~~

These are NOT V1 obligations. They may be re-added in a future amendment under §21 (production-integration prerequisite) with separate Charles authorization.

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

> **V1 contract this round:** `TASK011D_NOT_AUTHORIZED`. The future production-integration prerequisite (§21) is **NOT** pre-assigned any task number; it is NOT `TASK-011D`; it is NOT `TASK-011D+`; it is NOT any specific task number. A future round that addresses the deferred scope will receive a separate, future Charles authorization with a task number assigned by Charles at that time.

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
18. **Inventing or restoring a `high_throughput_review` scenario in V1** — the scenario is REMOVED from V1 and is deferred to §21. Any implementation-round attempt to define a high-throughput-style scenario under a different name is forbidden.
19. **Creating any D9-production-prerequisite fixture / expected-output / production-rule file in V1** — the D9-deferred scope is not in V1; production-integration prerequisite work is §21 and requires separate future Charles authorization.

---

## 16. Stop conditions (binding, post-D3-approved + D9-deferred)

This list supersedes the prior §16 by removing the D9 / high-throughput-related stop conditions that are now resolved by deferral and by removing the empty-D3 stop conditions, and adding a small set of V1 stop conditions for the D3 approved state:

1. **Cross-backend business outcome inconsistent** — SQLite and PostgreSQL produce different business outcome for the same scenario.
2. **New fixture requires production-formula modification** — forbidden.
3. **Requires evaluation-owned ORM fabrication** — forbidden.
4. **Requires restoring `production_seeding.py`** — forbidden.
5. **Manifest incompatible with current runner contract.**
6. **Cannot obtain Charles sign-off for new expected output.**
7. **Current main source drift changes design premise.**
8. **Cross-backend substantive comparison fails.**
9. **PR #21 / PR #23 mutation required** — forbidden.
10. **Baseline regression** — forbidden.
11. (Removed — `INVALID_BLOCKED_PRODUCTION_PATH_NOT_ESTABLISHED` is closed by D10.)
12. (Removed — `TASK_011C_HIGH_THROUGHPUT_REQUIRES_REVIEW_PRODUCTION_RULE_MUTATION` is no longer applicable because the `high_throughput_review` scenario is not in V1 scope.)
13. `TASK_011C_CANONICALIZATION_AUTHORITY_REMAINS_AMBIGUOUS` — D1 future module not creatable without contradiction.
14. `TASK_011C_MANIFEST_SCHEMA_PATH_CONFLICTS` — schema path requires top-level `evaluation/` or `.gitignore` modification.
15. `TASK_011C_BASELINE_GOLDEN_MODIFICATION_REQUIRED` — frozen baseline modification.
16. `TASK_011C_EXPECTED_OUTPUT_AUTHORED_WITHOUT_SEPARATE_SIGNOFF` — §8 authority flow not followed.
17. `TASK_011C_PR21_OR_PR23_MUTATION_REQUIRED` — forbidden.
18. `TASK_011C_SCOPE_DRIFT_TO_TASK011D_OR_TASK12` — forbidden.
19. `TASK_011C_REMOTE_COMMIT_CANNOT_BE_ESTABLISHED` — push failure.
20. `TASK_011C_CONTRACT_SOURCE_CONFLICTS_WITH_MAIN` — main drift.
21. `TASK_011C_GITIGNORE_CHANGE_REQUIRES_SEPARATE_AMENDMENT`.
22. `TASK_011C_D2_VALUE_DOMAIN_VIOLATED` — manifest contains a rejected type (NaN, Infinity, Decimal object, datetime, etc.).
23. `TASK_011C_D3_WILDCARD_EXCLUSION_INTRODUCED` — `any *_id`-style wildcards or non-JSONPath exclusion. (D3 approved with empty exclusion set; this is a V1 invariant.)
24. `TASK_011C_D3_ADDITIONAL_EXACT_PATH_ADDED_WITHOUT_AMENDMENT` — any future amendment to `D3_V1_EXCLUDED_JSON_PATHS=[]` requires a separate Charles authorization.
25. `TASK_011C_D4_GLOBAL_TOLERANCE_INTRODUCED` — broad `1e-*` or per-leaf tolerance without Charles approval.
26. `TASK_011C_D5_VERSION_NOT_LITERAL_1_0` — implementation rejects version `"1.0"` literal or accepts e.g. `1.0` numeric.
27. `TASK_011C_D6_SECOND_LOADER_INTRODUCED` — a parallel `load_and_validate_manifest` outside the canonical file.
28. `TASK_011C_D8_REPOSITORY_RELATIVE_FALLBACK_USED` — loader falls back to `Path(__file__).parent / ...` instead of `importlib.resources.files(...)`.
29. `TASK_011C_D9_DEFERRED_SCOPE_IMPLEMENTED_IN_V1` — implementation round attempts to address the D9-deferred production-integration prerequisite scope (§21) under a V1 implementation round. The deferred scope requires a separate future round with separate Charles authorization.

---

## 17. Validation (docs-only, this round)

This round is docs-only:
- `git diff --check` on working tree — empty
- `git status --short` on working tree — empty
- `git diff --name-only <auth-required-starting-head>...HEAD` — exactly 1 file: `docs/tasks/TASK-011C-remaining-evaluation-scenarios-contract.md`
- `git diff --stat <auth-required-starting-head>...HEAD` — 1 file changed
- Forbidden-path scan (§13) — no path outside `docs/tasks/TASK-011C-*.md` appears in the diff

---

## 18. Commit, push, and Draft PR (docs-only)

- **Branch:** `docs/task-011c-remaining-evaluation-scenarios-contract`
- **Base SHA:** `ba08b6b3ee92ebdb8122b3660ff2d08a16e25b03` (Repository Freeze Stamp Round, this round)
- **Single commit (this round):** `docs(task-011c): stamp frozen V1 contract`
- **Push target:** `origin HEAD:refs/heads/docs/task-011c-remaining-evaluation-scenarios-contract`
- **Draft PR:** #61 — title remains unchanged: `TASK-011C: remaining evaluation scenarios contract`. No PR title or body mutation was authorized to the coding software in this round. **Draft / Not merged / No Ready**.
- **PR #61 body update in this software round:** **NOT AUTHORIZED IN THIS SOFTWARE ROUND** — the body update must wait for Charles/ChatGPT to perform a manual paste after this commit is independently verified at the new Head.
- **`PR_BODY_UPDATE_NOT_AUTHORIZED_IN_SOFTWARE_ROUND`**: confirmed binding for this round.
- **Required current markers (for the future PR body update by Charles/ChatGPT):**
  - `TASK_011C_V1_CONTRACT_FROZEN`
  - `TASK_011C_REPOSITORY_FREEZE_STAMP_COMPLETE`
  - `TASK_011C_CONTRACT_FREEZE_AUTHORITY=PR61_REVIEW_4679730144`
  - `TASK_011C_V1_SCOPE_CLOSED`
  - `TASK_011C_MAINTAINER_AUTHORITY_ESTABLISHED`
  - `D1_D2_D3_D4_D5_D6_D7_D8_D10_APPROVED`
  - `D3_V1_EXCLUDED_JSON_PATHS=[]`
  - `D9_DEFERRED_FROM_TASK_011C_V1`
  - `D9_HIGH_THROUGHPUT_REVIEW_DEFERRED`
  - `D9_DECISION_CLOSED_FOR_TASK_011C_V1`
  - `HIGH_THROUGHPUT_REVIEW_NOT_IN_V1_SCOPE`
  - `TASK_011C_IMPLEMENTATION_NOT_AUTHORIZED`
  - `EXPECTED_OUTPUT_AUTHORING_NOT_AUTHORIZED`
  - `FIXTURE_AUTHORING_NOT_AUTHORIZED`
  - `PRODUCTION_PREREQUISITE_IMPLEMENTATION_NOT_AUTHORIZED`
  - `READY_NOT_AUTHORIZED`
  - `MERGE_NOT_AUTHORIZED`
  - `PR21_UNTOUCHED`
  - `PR23_UNTOUCHED`
  - `ISSUE20_REMAINS_OPEN`

---

## 19. Final verdict (this round)

**Round status: `TASK_011C_V1_CONTRACT_FROZEN` / `TASK_011C_REPOSITORY_FREEZE_STAMP_COMPLETE`**

```
TASK_011C_V1_CONTRACT_FROZEN
TASK_011C_REPOSITORY_FREEZE_STAMP_COMPLETE
TASK_011C_V1_SCOPE_CLOSED
TASK_011C_MAINTAINER_AUTHORITY_ESTABLISHED
D1_APPROVED
D2_APPROVED
D3_APPROVED
D3_V1_EXCLUDED_JSON_PATHS=[]
D4_APPROVED
D5_APPROVED
D6_APPROVED
D7_APPROVED
D8_APPROVED
D9_DEFERRED_FROM_TASK_011C_V1
D10_APPROVED
HIGH_THROUGHPUT_REVIEW_NOT_IN_V1_SCOPE
D9_HIGH_THROUGHPUT_REVIEW_DEFERRED
D9_DECISION_CLOSED_FOR_TASK_011C_V1
TASK_011C_IMPLEMENTATION_NOT_AUTHORIZED
EXPECTED_OUTPUT_AUTHORING_NOT_AUTHORIZED
FIXTURE_AUTHORING_NOT_AUTHORIZED
PRODUCTION_PREREQUISITE_IMPLEMENTATION_NOT_AUTHORIZED
PR61_OPEN_DRAFT_NOT_MERGED
READY_NOT_AUTHORIZED
MERGE_NOT_AUTHORIZED
INVALID_BLOCKED_SOURCE_DEFINITION_CLOSED_BY_D10
TASK011D_NOT_AUTHORIZED
TASK12_NOT_AUTHORIZED
PR21_UNTOUCHED
PR23_UNTOUCHED
ISSUE20_REMAINS_OPEN
CLI_EXIT_5_RESERVED_NOT_USED_BY_TASK011C
```

This round records the binding V1 contract freeze per PR #61 review `4679730144`. The V1 contract is frozen. The freeze is binding for the V1 contract clauses; it does NOT authorize implementation, fixture authoring, expected-output authoring, production-path execution, Ready, or Merge. PR #61 stays Draft / Not merged. The next allowed work, if Charles separately authorizes it, is a `future implementation round` for the V1 contract (`baseline_feasible` + `invalid_blocked` only), which does NOT automatically authorize fixture / expected-output / canonicalizer / runner / manifest / production-code authoring — each of those requires its own sign-off per the §8 authority flow. The deferred production-integration prerequisite scope (§21) requires a separate future Charles authorization and is NOT pre-assigned any task number.

**Historical reference (NOT current operative status, preserved for audit):** the prior-round V1 final decision integration operative markers `TASK_011C_FINAL_DECISIONS_INTEGRATED` / `TASK_011C_CONTRACT_FREEZE_PROPOSAL_READY` / `TASK_011C_CONTRACT_NOT_YET_FROZEN` / `TASK_011C_CONTRACT_FREEZE_NOT_AUTHORIZED` / `TASK_011C_CONTRACT_AUTHORED_PENDING_CHARLES_FREEZE` / `proposal ready for Charles review` / `Charles retains the contract-freeze decision authority` are preserved in the §20 change log as historical audit trace; they are NOT current operative status. The current operative V1 status is `TASK_011C_V1_CONTRACT_FROZEN` per PR #61 review `4679730144`.

---

## 20. Change log

| Round | Date | Author | Change |
|---|---|---|---|
| Initial authoring | 2026-07-12 | Hermes | Initial TASK-011C remaining evaluation scenarios contract (NOT frozen) |
| Review-correction round | 2026-07-12 | Hermes | Corrected against Issue #20 review comment `4949858037` (P0 + 8 contract corrections; §1 status wording; §6.2 high-throughput four-field invariants + real-production review signal; §6.3 invalid_blocked field-by-field; §7.0 manifest single-path; §7.1 CLI exit codes; §8.10 per-file expected-output authority; §10 Path B canonicalization; §11 current-main-vs-future contract; §12 field-by-field SQLite/PG parity; §16 stop conditions S13–S23; §20 verdict lifecycle) |
| **Prior-round decision-closure round** | 2026-07-12 | Hermes | Integrated prior-round Charles authority: D1 (canonicalization `canonicalization.py::canonicalize_production_outputs`); D2 (strict JSON two-layer); D3 (prior-round authority's candidate was later audited and the audit verdict is `NOT_ESTABLISHED` per the maintainer authority round; no empty-list claim survives); D4 (exact numeric default, no global tolerance); D5 (`schema_version="1.0"` Charles policy); D6 (loader `manifest.py::load_and_validate_manifest`); D7 (setuptools package-data); D8 (importlib.resources); D10 (`PRODUCTION_CALCULATION_PROJECTION_MISSING_TOTAL_AREA_M2` source-defines `invalid_blocked`). D9 was carried as `PENDING_EXACT_INPUT_VALUES` during the prior round; the prior round also temporarily treated it as the single remaining deficit, which was subsequently corrected to `TASK_011C_CONTRACT_FREEZE_BLOCKED_BY_D3_AND_D9` in the maintainer-authority round. Rewrote §6.3 invalid_blocked source inventory to remove prior staged PENDING counters and close the source definition; removed §12.0.2 wildcard exclusions table (the prior-round empty-list claim was later superseded); updated §10 manifest decisions to reflect D1; updated §13 implementation allowlist with new test names; updated §16 stop conditions S25–S30 for D1–D8/D10; replaced the prior pending-state marker for invalid_blocked with `INVALID_BLOCKED_SOURCE_DEFINITION_CLOSED`. PR #21 / PR #23 / PR #60 / Issue #20 untouched. |
| **Maintainer Authority Provenance Correction + D3/D9 Audit Round (prior round)** | 2026-07-12 | Hermes | **Read the binding maintainer authority from PR #61 top-level comment `4950035046` and review `4679463188` (NOT the local `/root/TASK-011C-Charles-Decision-Closure-Packet.md`)**. Downgraded the local packet to "historical work material only", not a repository authority source. **Updated status** to `TASK_011C_MAINTAINER_AUTHORITY_ESTABLISHED` / `TASK_011C_CONTRACT_NOT_FROZEN`. **Marked D3** as `PENDING_NORMALIZED_SCHEMA_AUDIT` (replaced the prior-round empty-list claim with `PENDING` + D3 audit evidence ledger in new §10.5, verdict `D3_AUDIT_RESULT = NOT_ESTABLISHED`). **Marked D9** as `PENDING_EXACT_INPUT_VALUES` (replaced the prior-round single-deficit framing with the new D3+D9 dual-blocker framing and §10.6 D9 audit evidence ledger, verdict `D9_AUDIT_RESULT = NOT_ESTABLISHED`; production rule identified = `_coefficient_review` in `backend/src/cold_storage/modules/calculations/domain/service.py:89, 189, 274, 309`, but exact input values NOT established at docs-only audit level). **Updated contract-freeze blocker** from the prior-round D9-only formulation to `TASK_011C_CONTRACT_FREEZE_BLOCKED_BY_D3_AND_D9` (§1, §6.2, §19). **Preserved** D1, D2, D4–D8, D10 as approved. **Preserved** `INVALID_BLOCKED_SOURCE_DEFINITION_CLOSED_BY_D10` (D10 closure unchanged). **Updated** §6.2 D9 disposition, §6.3 D10 disposition, §10.1 D1 path, §12.0.2 D3 pending state, §19 final verdict to reflect the new maintainer-authority framework. PR #21 / PR #23 / PR #60 / Issue #20 untouched; no fixture / no expected-output / no implementation authorized. |
| **D3/D9 Audit Residual Correction Round (prior round)** | 2026-07-12 | Hermes | **Read the correction directive from PR #61 review `4679476507` (D3/D9 Residual Correction Review, CHANGES_REQUESTED)**. **Cleaned residual D3 empty/signed/frozen wording** in §2.2, §12 title, §12.0, §12.0.1, §12.0.2, §12.1, §13, §19 — all D3 lifecycle references updated to the triplet (read-only audit completed, decision evidence not established, decision pending). **Cleaned residual D9 invented review reason** in §10.6 — replaced the prior-round invented string with the explicit NOT_ESTABLISHED marker; preserved the candidate production rule `_coefficient_review` at `backend/src/cold_storage/modules/calculations/domain/service.py:89, 189, 274, 309` and the candidate warning code from the production code review (NOT a fabricated value), explicitly marked as candidates, not source definition. **Unified D3/D9 lifecycle** — removed mixed `audit pending` / `audit completed` language; consistent `D*_READ_ONLY_AUDIT_COMPLETED` + `D*_DECISION_EVIDENCE_NOT_ESTABLISHED` + `D*_DECISION_PENDING` triplet throughout. **Renamed proposed test** from the prior-round D3-empty-asserting name to `test_d3_excluded_paths_policy.py` to drop the empty-list assertion. **Cleaned §18 old-round metadata** — replaced the old suggested commit subject and the old PR body markers with the current D3/D9 lifecycle markers; replaced "old commit was X" with "current commit is Y". **Removed "(frozen)" labels from §11.1 / §11.2 / §11.3 / §12.0 / §12.0.1 / §12.0.2 / §12.1** and replaced with `proposed, pending contract freeze`. **Removed prior-round subtitle from document title** (rewritten as a neutral title). PR #21 / PR #23 / PR #60 / Issue #20 untouched; no fixture / no expected-output / no implementation authorized. |
| **Commit-Chain Reconciliation + Final D3/D9 Status Cleanup Round (prior round)** | 2026-07-12 | Hermes | **Read the correction directive from PR #61 review `4679487987` (D3/D9 Residual Correction Re-review, CHANGES_REQUESTED)**. **Phase A — commit-chain reconciliation**: discovered the actual commit chain between auth-required starting head `5495e948...` and current head `b203c33...` contains **2 commits, not 1**: intermediate commit `0711cfdaed83990e909366b9c1df77c318f0e820` (`docs(task-011c): align D3 and D9 pending authority`, author `root`, 2026-07-12 05:24:49 UTC, 1 file changed 39 insertions / 34 deletions, parent `5495e948`, tree `b9d4455c8088b0e6bba7baf8b51ee374c71a1bbd`) was created earlier but was not disclosed in the prior round's report. Both commits modify only the target contract. No scope violation; no history rewrite. **Phase B — single-file docs residual correction**: §6.2 split the four pre-D9-pending parenthetical clause labels — the two proposed TASK-011C invariants became `(proposed, pending D9 decision and contract freeze)` and the two current-main observed facts became `(current-main observed fact; not a complete D9 source definition)` with explicit marker blocks `CURRENT_MAIN_OBSERVED_FACT` / `NOT_D9_DECISION` / `NOT_COMPLETE_SOURCE_DEFINITION`. Replaced the legacy audit-pending variant in §6.2 status block with the canonical D9 lifecycle triplet. Restored empty §11.3 to a non-empty proposed-status statement. Fixed §18 PR title claim to `PR #61 title remains unchanged: TASK-011C: remaining evaluation scenarios contract` (per actual GitHub API). Added `PR_BODY_UPDATE_NOT_AUTHORIZED_IN_SOFTWARE_ROUND` marker to §18. Added review `4679487987` to Authoritative references with explicit `NOT a D3 or D9 approval decision` disclaimer. **Preserved** D1, D2, D4–D8, D10 as approved; D3 / D9 decisions and evidence remain pending. PR #21 / PR #23 / PR #60 / Issue #20 untouched; no fixture / no expected-output / no production-path execution / no PR metadata mutation / no implementation authorized. |
| **Second Commit-Chain Reconciliation + D3 Operative-Lifecycle Correction Round (prior round)** | 2026-07-12 | Hermes | **Read the correction directive from PR #61 review `4679499719` (Second Commit-Chain Reconciliation + D3 Operative-Lifecycle Correction, CHANGES_REQUESTED)**. **Phase A — second commit-chain reconciliation**: discovered the actual commit chain between auth-required starting head `b203c33c1303b4ac94f3852991769104ff7ce4fd` and prior-reported current head `ec25e53375b317751872be72623060141fc452ae` contains **2 commits, not 1**: intermediate commit `f9c33f4a19f029e0f7392603a2300160b5689cce` (`docs(task-011c): remove final D3 D9 freeze residuals`, author `root`, 2026-07-12 05:35:51 UTC, 1 file changed 45 insertions / 17 deletions, parent `b203c33`, child of `b203c33` and parent of `ec25e533`) was created earlier but was not disclosed in the prior round's report. The substantive §6.2 / §11.3 / §18 corrections are in this unreported intermediate commit. No scope violation; no history rewrite. **Phase B — D3 operative-lifecycle correction**: the operative preamble (former line 32) and §1 (former line 69) both still stated the legacy pre-audit D3 wording. Replaced the operative D3 status in the §0 Preamble with the canonical D3 lifecycle triplet (`D3_READ_ONLY_AUDIT_COMPLETED` / `D3_DECISION_EVIDENCE_NOT_ESTABLISHED` / `D3_DECISION_PENDING`). Replaced the §1 narrative phrasing `D3 (normalized-output volatility audit pending)` with `D3 (audit completed, decision evidence not established, decision pending)`. Preserved the pre-audit framing only as an explicitly labeled historical reference of the binding maintainer comment `4950035046`, not as current operative status. **Preserved** D1, D2, D4–D8, D10 as approved; D3 / D9 decisions and evidence remain pending. PR #21 / PR #23 / PR #60 / Issue #20 untouched; no fixture / no expected-output / no production-path execution / no PR metadata mutation / no implementation authorized. |
| **Final Verdict Metadata Correction Round (prior round)** | 2026-07-12 | Hermes | **Read the correction directive from PR #61 review `4679518692` (Final Verdict Metadata Correction, CHANGES_REQUESTED)**. **Review 4679518692 required only the final-verdict and change-log metadata correction. It did not approve D3. It did not approve D9. It did not authorize contract freeze or implementation.** Updated §19 Final Verdict operative markers: removed the prior-round operative markers `TASK_011C_COMMIT_CHAIN_RECONCILED` and `TASK_011C_D3_D9_FINAL_STATUS_CLEANUP_COMPLETED`; added the current-round operative markers `TASK_011C_SECOND_COMMIT_CHAIN_RECONCILED` / `TASK_011C_D3_OPERATIVE_LIFECYCLE_CORRECTED` / `TASK_011C_FINAL_VERDICT_METADATA_CORRECTED`; added `HIGH_THROUGHPUT_SOURCE_DEFINITION_PENDING` for completeness. Updated §20 Change Log: relabeled the prior-round `Commit-Chain Reconciliation + Final D3/D9 Status Cleanup Round` row from `(this round)` to `(prior round)`; relabeled the prior-round `Second Commit-Chain Reconciliation + D3 Operative-Lifecycle Correction Round` row from `(this round)` to `(prior round)`. No new business decisions authored in this round. D3 / D9 decisions and evidence remain pending. PR #21 / PR #23 / PR #60 / Issue #20 untouched; no fixture / no expected-output / no production-path execution / no PR metadata mutation / no implementation authorized. |
| **Final Maintainer Decision Integration Round (prior round)** | 2026-07-12 | Hermes | **Read the binding maintainer decisions from PR #61 review `4679707878` (D3 approval) and PR #61 review `4679711007` (D9 Path A deferral)**. **Phase A — D3 approval integration**: replaced the operative D3 status with `D3_APPROVED` + `D3_V1_EXCLUDED_JSON_PATHS=[]` + `D3_EVIDENCE_RESULT=EMPTY_EXCLUSION_SET_SUPPORTED` + `D3_EMPTY_EXCLUSION_SET_APPROVED` + `D3_DECISION_CLOSED`. Captured D3 evidence base: `D3_SQLITE_REPEATABILITY=PASS` + `D3_POSTGRESQL_REPEATABILITY=PASS` + `D3_CROSS_BACKEND_PARITY=PASS` + `D3_PROJECTED_DIFFERENCE_COUNT=0` + `COMBINED_SOURCE_HASH_PARITY=PASS` + `CONTENT_HASH_PARITY=PASS` + `CANDIDATES_SNAPSHOT_PARITY=PASS` + `DECIMAL_SERIALIZATION_PARITY=PASS`. Made the D3 cross-backend parity rule binding in §11.2 / §12.0.1 / §12.1 (no longer conditional on a pending decision). Made the D3-approved empty V1 exclusion set binding in §10.3 / §12.0.2 (no future amendment without separate Charles authorization). **Phase B — D9 deferral integration**: removed `high_throughput_review` from V1 scenario set (§2.1 / §4 / §6.2 / §7.2 / §8 / §9 / §13 allowlist / §15 / §16); moved the production-integration prerequisite to a new §21 (deferred scope); recorded D9 disposition `D9_DEFERRED_FROM_TASK_011C_V1` + `D9_DEFERRED_TO_PRODUCTION_INTEGRATION_PREREQUISITE` + `D9_HIGH_THROUGHPUT_REVIEW_DEFERRED` + `D9_EXACT_INPUT_SEARCH_CLOSED_WITHOUT_SOURCE_DEFINITION` + `D9_DECISION_CLOSED_FOR_TASK_011C_V1`. Preserved prior-round D9 audit evidence as historical audit trace in §10.6 + §6.2 (NO_CURRENT_PRODUCTION_HIGH_THROUGHPUT_THRESHOLD_REVIEW_TRIGGER block, `_coefficient_review` production-rule candidate, `COEFFICIENT_REQUIRES_REVIEW` warning code candidate, `计算使用了未批准或需复核的系数` message candidate) for forward traceability to the future §21 round. **Phase C — V1 scope closure**: §2.1 / §4 / §6 / §7.2 / §8 / §9 / §10.5 / §10.6 / §11.2 / §12 / §13 / §14 / §15 / §16 / §19 all reflect the V1 scope: `baseline_feasible` (TASK-011B-frozen) + `invalid_blocked` (D10 source-defined). The future `high_throughput_review` scenario is NOT in V1; the future production-integration prerequisite scope is described in §21; the future scope requires a separate future Charles authorization and is NOT pre-assigned any task number (`TASK011D_NOT_AUTHORIZED`). **Phase D — V1 final verdict**: replaced the prior-round operative markers with the V1 final decision integration markers: `TASK_011C_FINAL_DECISIONS_INTEGRATED` / `TASK_011C_V1_SCOPE_CLOSED` / `TASK_011C_CONTRACT_FREEZE_PROPOSAL_READY` / `TASK_011C_CONTRACT_NOT_YET_FROZEN` / `PRODUCTION_PREREQUISITE_IMPLEMENTATION_NOT_AUTHORIZED` / `HIGH_THROUGHPUT_REVIEW_NOT_IN_V1_SCOPE` / `HIGH_THROUGHPUT_REVIEW_DEFERRED_TO_PRODUCTION_INTEGRATION_PREREQUISITE`. **This round integrates decisions only; it does not freeze the contract by itself; it does not authorize implementation.** PR #21 / PR #23 / PR #60 / Issue #20 / Issue #22 untouched; no fixture / no expected-output / no production-path execution / no PR metadata mutation / no implementation authorized. |
| **Repository Freeze Stamp Round (this round)** | 2026-07-12 | Hermes | **Read the binding V1 contract freeze decision from PR #61 review `4679730144`**. **Phase A — title + status block freeze**: changed the document title to `Frozen V1 Contract`; rewrote the top-level status block (§0) to begin with `TASK_011C_V1_CONTRACT_FROZEN` + `TASK_011C_CONTRACT_FREEZE_AUTHORITY=PR61_R...4`; updated the §1 Authority and status to `Document status: TASK_011C_V1_CONTRACT_FROZEN` and added `Binding freeze authority: PR #61 Review 4679730144`. **Phase B — operative-wording scrub**: removed `TASK_011C_CONTRACT_FREEZE_PROPOSAL_READY` / `TASK_011C_CONTRACT_NOT_YET_FROZEN` / `TASK_011C_CONTRACT_FREEZE_NOT_AUTHORIZED` / `TASK_011C_CONTRACT_AUTHORED_PENDING_CHARLES_FREEZE` / `Charles retains the contract-freeze decision authority` / `proposal ready for Charles review` from the operative status blocks (§0, §1, §19); preserved them in the change log and in explicitly labeled `Historical reference (NOT current operative status, preserved for audit traceability)` paragraphs. **Phase C — §19 Final Verdict rewrite**: rewrote §19 with `Round status: TASK_011C_V1_CONTRACT_FROZEN / TASK_011C_REPOSITORY_FREEZE_STAMP_COMPLETE`; removed D3 evidence ledger / D9 disposition details from the operative verdict (they remain in §10.5 / §10.6 as binding records); kept the V1 scope markers (`baseline_feasible` + `invalid_blocked`) and the deferred-scope markers (`HIGH_THROUGHPUT_REVIEW_NOT_IN_V1_SCOPE` / `D9_HIGH_THROUGHPUT_REVIEW_DEFERRED` / `D9_DECISION_CLOSED_FOR_TASK_011C_V1`) in the operative verdict. **Phase D — §18 Commit metadata + PR body markers**: updated §18 `Base SHA` to `ba08b6b3...`; updated `Single commit (this round)` to `docs(task-011c): stamp frozen V1 contract`; updated the `Required current markers` list to reflect the freeze (added `TASK_011C_V1_CONTRACT_FROZEN` / `TASK_011C_REPOSITORY_FREEZE_STAMP_COMPLETE` / `TASK_011C_CONTRACT_FREEZE_AUTHORITY=PR61_REVIEW_4679730144` / `HIGH_THROUGHPUT_REVIEW_NOT_IN_V1_SCOPE` / `PRODUCTION_PREREQUISITE_IMPLEMENTATION_NOT_AUTHORIZED`; removed `TASK_011C_FINAL_DECISIONS_INTEGRATED` / `TASK_011C_CONTRACT_FREEZE_PROPOSAL_READY` / `TASK_011C_CONTRACT_NOT_YET_FROZEN` / `D3_EVIDENCE_RESULT=EMPTY_EXCLUSION_SET_SUPPORTED`). **Phase E — §20 Change Log relabel**: relabeled the `Final Maintainer Decision Integration Round` row from `(this round)` to `(prior round)`. **This round records the binding V1 contract freeze. It does not authorize implementation, fixture authoring, expected-output authoring, Ready, or merge.** PR #21 / PR #23 / PR #60 / Issue #20 / Issue #22 untouched; no fixture / no expected-output / no production-path execution / no PR metadata mutation / no implementation authorized. |

---

## 21. Deferred production-integration prerequisite (NOT in V1 scope)

> **This section describes scope only. It is NOT authorized for implementation. The future production-integration prerequisite round requires a separate, future Charles authorization. The future round is NOT pre-assigned any task number; `TASK-011D` is NOT authorized; no task number is unilaterally assigned in this round.**

**Disposition:**

```
D9_READ_ONLY_EVIDENCE_VALIDATION_COMPLETED
D9_EVIDENCE_RESULT=CURRENT_MAIN_UNREACHABLE
D9_BLOCKER_TYPE=PRODUCTION_INTEGRATION_ARCHITECTURE_GAP
D9_DISPOSITION=DEFERRED_FROM_TASK_011C_V1
D9_DEFERRED_TO_PRODUCTION_INTEGRATION_PREREQUISITE
D9_HIGH_THROUGHPUT_REVIEW_DEFERRED
D9_EXACT_INPUT_SEARCH_CLOSED_WITHOUT_SOURCE_DEFINITION
D9_DECISION_CLOSED_FOR_TASK_011C_V1
D9_HIGH_THROUGHPUT_REVIEW_NOT_IN_V1_SCOPE
```

**Status carry-forward:**

```
TASK011D_NOT_AUTHORIZED
PRODUCTION_PREREQUISITE_IMPLEMENTATION_NOT_AUTHORIZED
NO_TASK_NUMBER_ASSIGNED_IN_THIS_ROUND
NO_TASK_NUMBER_PRE_ASSIGNED_FOR_FUTURE_ROUND
```

**Forward scope (description only — not implementation):**

The deferred production-integration prerequisite is a future round that may (subject to separate Charles authorization) address the following scope:

1. **Valid review-required source chain** — establish a real production review rule (e.g., a throughput-threshold-based reviewer or a coefficient-source-based reviewer) that produces `requires_review=true` + non-empty `review_reasons` on the production path with `execution_outcome=SUCCEEDED` + `scheme_run.status=completed`. The prior-round D9 audit identified candidate production rules (e.g., `_coefficient_review` at `backend/src/cold_storage/modules/calculations/domain/service.py:89, 189, 274, 309`; `DEMO_INVESTMENT_REQUIRES_REVIEW` / `DEMO_ASSUMPTIONS_REQUIRE_REVIEW` warnings) but the exact input values were not established; the future round may re-open the search with separate evidence-validation and source definition.
2. **`requires_review` hash/provenance propagation** — confirm the production-side propagation of `requires_review` from calculation run → `SchemeRunRecord.requires_review` → expected-output `review_required`. Verify the cross-backend byte-identity of the propagation path.
3. **Structured warning / review-reason persistence** — verify that `SchemeRunRecord.warning_messages` carries the same content as the source `CalculationRunRecord.warning_messages` in deterministic order; verify the `field_normalization_mapping` from raw warning messages to canonical `review_reasons`.
4. **`SchemeRun.warning_messages` propagation** — verify that the runner-side canonicalization (`canonicalize_production_outputs`) preserves `warning_messages` order; verify cross-backend byte-identity of the propagation path.
5. **Adapter `review_reasons` propagation** — verify that `adapter.execute_scenario` propagates `SchemeRunRecord.warning_messages` into `AdapterResult.review_reasons` (per the existing `AdapterResult` shape); verify cross-backend byte-identity of the propagation path.
6. **SQLite / PostgreSQL parity** — re-run the D3 evidence-validation methodology (4 fully independent baseline runs) with the deferred high-throughput scenario; require `D3_SQLITE_REPEATABILITY=PASS` + `D3_POSTGRESQL_REPEATABILITY=PASS` + `D3_CROSS_BACKEND_PARITY=PASS` for the high-throughput scenario before approving any expected-output for the high-throughput scenario.

**Forward future-round forbidden practices (binding when the future round is authorized):**
- The future round may NOT pick up the prior-round D9 candidate values verbatim without re-establishing them in a separately authorized evidence-validation round.
- The future round may NOT introduce a `high_throughput_review` scenario in V1; it must establish V1 freeze first, then authorize a separate future round for the high-throughput scenario.
- The future round may NOT widen the V1 exclusion set; any future amendment to `D3_V1_EXCLUDED_JSON_PATHS=[]` requires a separate Charles authorization.
- The future round may NOT pre-assign any task number; the task number is assigned by Charles at the time of the future authorization.

**Forward future-round evidence ledger (placeholders, NOT content):**
- `D9_EVIDENCE_RESULT` (new): TBD by future round
- `D9_EXACT_INPUT_VALUES`: TBD by future round
- `D9_EXPECTED_REVIEW_REASON`: TBD by future round
- `D9_PRODUCTION_RULE_FINAL`: TBD by future round
- `D9_PRODUCTION_WARNING_CODE_FINAL`: TBD by future round

These placeholders are NOT current operative values; they are forward-scope descriptors.
