# V0.6 P0 Five-Stage Report Delivery Contract

**Status:** Definition freeze R2 — report source mapping + package test allowlist correction
**Authority:** Issue #176 (umbrella), tracked by Issue #180, dispatched by Issue #184
**Contract definition source SHA:** `06a446501b83f75ba42b3920d912d980c51d7fe5`
**Contract definition source tree:** `633c9712a5a558bc6d6df183303733d90540dc24`
**Previous release:** `v0.5.0`
**Target branch:** `cursor/v06-p0-report-delivery-contract-6c68`

This document freezes the V0.6 P0 **report delivery contract boundary** only.
It does not authorize P1 report assembly, P2 rendering, frontend workflow,
samples, evaluation goldens, migrations, formula recut, tag publication, or
Release.

## 0. Contract identity and governance

```text
TASK=V06_P0_REPORT_DELIVERY_CONTRACT_DEFINITION_R1
PARENT_ISSUE=176
P0_TRACKING_ISSUE=180
DISPATCH_ISSUE=184
GOVERNANCE_OWNER=V0.6
BASE_MAIN_SHA=06a446501b83f75ba42b3920d912d980c51d7fe5
BASE_TREE=633c9712a5a558bc6d6df183303733d90540dc24
PREVIOUS_RELEASE=v0.5.0
TARGET_BRANCH=cursor/v06-p0-report-delivery-contract-6c68
TARGET_FILE=docs/tasks/V0_6-P0-five-stage-report-delivery-contract.md
TARGET_PR_STATE=DRAFT

CONTRACT_STATUS=DEFINITION_R2_DRAFT_FOR_INDEPENDENT_REVIEW
V06_P0_IMPLEMENTATION_AUTHORIZED=YES
V06_P1_IMPLEMENTATION_AUTHORIZED=NO
V06_P2_IMPLEMENTATION_AUTHORIZED=NO
V06_P3_IMPLEMENTATION_AUTHORIZED=NO
V06_P4A_IMPLEMENTATION_AUTHORIZED=NO
V06_P4B_IMPLEMENTATION_AUTHORIZED=NO
V06_P5_IMPLEMENTATION_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
CONTROLLED_ACCEPTANCE_EXECUTION_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
LIVE_MODEL_PRODUCTION_ENABLEMENT_AUTHORIZED=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P0 freezes report source mapping, input/assumption authority, fail-closed
lifecycle, package ownership, and governance truth-up. P0 does **not** change
application behavior or close known baseline gaps.

## 1. Objective and non-goals

### 1.1 Objective

Freeze the canonical **five-stage review and formal delivery closure** contract
that V0.6 report delivery must converge on:

```text
zone → cooling_load → equipment → power → investment
```

and the explicit persisted-source mapping from canonical calculator runs to
reviewable report JSON sections, through review/formal-export lifecycle, to
formal DOCX/PDF artifacts — without recalculating engineering formulas.

V0.5 delivered the five-stage workbench persistence and consumer identity
alignment at `v0.5.0` (`BASE_MAIN_SHA`). V0.6 closes the remaining gap:
**five-stage persisted results → reviewable report JSON → formal DOCX/PDF
closure**.

### 1.2 Non-goals (hard boundaries)

```text
V06_P1_IMPLEMENTATION_AUTHORIZED=NO
V06_P2_IMPLEMENTATION_AUTHORIZED=NO
V06_P3_IMPLEMENTATION_AUTHORIZED=NO
V06_P4A_IMPLEMENTATION_AUTHORIZED=NO
V06_P4B_IMPLEMENTATION_AUTHORIZED=NO
V06_P5_IMPLEMENTATION_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
DEMO_COEFFICIENT_CONFLICT_RESOLUTION=NO
LIVE_MODEL_PRODUCTION_ENABLEMENT_AUTHORIZED=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
FIELD_EQUIPMENT_CONTROL=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
AGENT_TO_ENGINEERING_VALUE=NO
REPORT_FORMULA_RECALCULATION=NO
```

P0 must not:

- implement report assembly, rendering, or frontend workflow changes;
- add migrations or change calculator formulas;
- promote or choose between conflicting demo coefficient values;
- treat `power_configuration` as canonical installed power or report electrical
  authority;
- inject engineering numbers into contract or tests;
- claim Task 12 or live Agent production enablement are in V0.6 scope.

## 2. Frozen stage order and canonical calculator identities

Copied from V0.5 (`docs/tasks/V0_5-P0-five-stage-workbench-contract.md`); no
sixth canonical stage.

### 2.1 Stage order (immutable)

| Order | Stage name | Canonical calculator identity |
| --- | --- | --- |
| 1 | `zone` | `cold_room_zone_plan` |
| 2 | `cooling_load` | `cooling_load` |
| 3 | `equipment` | `equipment` |
| 4 | `power` | `installed_power` |
| 5 | `investment` | `investment_estimate` |

Authoritative code registry:

- `backend/src/cold_storage/modules/orchestration/domain/dag.py`
  - `ORCHESTRATION_STAGE_ORDER`
  - `CALCULATOR_BINDINGS`
- `backend/src/cold_storage/modules/orchestration/domain/consumer_bindings.py`
  - `CANONICAL_STAGE_ORDER`
  - `STAGE_TO_CALCULATOR_NAME`
  - `SUPPLEMENTAL_ONLY_CALCULATOR_NAMES`

### 2.2 Supplemental `power_configuration` boundary

`power_configuration` is supplemental only and **MUST NOT** satisfy the
canonical `power` stage slot or report electrical authority.

Rules:

1. `power_configuration` MUST NOT satisfy the canonical `power` stage slot.
2. `power_configuration` MUST NOT masquerade as `installed_power` in report
   assembly, render models, or formal export provenance.
3. Report electrical authority MUST read persisted `installed_power` only.
4. Legacy V0.4 read paths MAY continue to display `power_configuration` as
   supplemental, but MUST NOT treat it as canonical power.

## 3. Frozen report source mapping

P1 must implement this mapping later; P0 only freezes the contract target.

| Persisted calculator | `OrchestratedCalculationResult` attr | Report JSON section key |
| --- | --- | --- |
| `cold_room_zone_plan` | `throughput_result` | `throughput_inventory_area` |
| `cooling_load` | `cooling_load_result` | `cooling_load` |
| `equipment` | `equipment_result` | `equipment_selection` |
| `installed_power` | `power_result` | `electrical_and_energy` |
| `investment_estimate` | `investment_result` | `investment_estimate` |

Authoritative read surfaces (baseline at `BASE_MAIN_SHA`):

- `backend/src/cold_storage/modules/reports/application/persisted_calculation_reads.py`
- `backend/src/cold_storage/modules/reports/infrastructure/real_data_provider.py`
- `backend/src/cold_storage/modules/reports/application/assembler.py`
- `backend/src/cold_storage/modules/reports/domain/schema.py`

### 3.1 `input_conditions` source rules

`input_conditions` MUST come from immutable persisted project/version
engineering inputs — specifically `EngineeringInputBundleV1` leaves and
persisted version snapshot fields.

Forbidden sources:

- report templates;
- model prompts;
- silent defaults;
- ad hoc assembler inference.

Missing immutable input authority MUST surface explicit blocker findings; draft
report JSON MAY exist, but formal export MUST fail closed.

### 3.2 `assumptions` source rules

`assumptions` MUST come from:

- persisted calculation/version assumption snapshots; and
- explicit review-required coefficient flags (`requires_review=true`,
  `source_type=demo`, `validity_status=unverified` or `conflict`).

P0 does not invent assumption text. Demo coefficient conflicts documented in
`docs/audit/coefficient-inventory.md` remain unresolved.

### 3.3 `measured_value` lineage binding

Every `measured_value` in report JSON MUST carry:

- `source_result_id`
- `source_tool`
- `source_tool_version`

and MUST bind to persisted `calculation_id`, `result_hash`, and
`calculator_version` for the canonical source row.

Missing any canonical source, stale lineage, or missing units MUST produce an
explicit blocker finding (for example `MISSING_CANONICAL_SOURCE` or
`REPORT_QUALITY_BLOCKER`). Draft report revisions MAY exist; formal export MUST
fail closed.

### 3.4 No formula recalculation

Reports MUST NOT recalculate formulas. Report templates MUST NOT embed formulas.
Assemblers and render model builders MUST read persisted calculation
results and version metadata only.

## 4. Review and formal-export lifecycle

Freeze existing authority; do not invent new states.

### 4.1 Report status machine

The existing report status machine and `FORMAL_EXPORT_STATUSES` in
`backend/src/cold_storage/modules/reports/domain/enums.py` remain authoritative.

### 4.2 Review gate

`requires_review=true` on any coefficient or calculation reference MUST block
formal export unless a persisted trusted `mark_reviewed` proof exists.
Frontend is not approval authority.

### 4.3 Scenario labels

`high_throughput_review` is a scenario label only, not a new review rule.
P3 later may add evaluation golden after source-definition evidence.

### 4.4 Trusted operator seam

The trusted operator seam remains injected via application services; P0 does not
claim production RBAC.

### 4.5 Formal artifact binding

Formal artifacts MUST bind:

- report revision `content_hash`;
- template version;
- locale;
- source provenance (calculation IDs, result hashes, calculator versions).

P2 later hardens display; P0 freezes the requirement.

## 5. Database portability and API compatibility

### 5.1 SQLite / PostgreSQL parity

The contract applies equally to SQLite (local) and PostgreSQL (CI/production
parity paths):

- identical report JSON shapes and canonical calculator identities;
- identical lineage and hash semantics;
- dialect-specific persistence is infrastructure-only and MUST NOT change
  contract meaning.

### 5.2 API compatibility

V0.5 `POST .../five-stage-execution` and existing reports APIs remain.
P0 introduces no new required breaking fields.

## 6. Package DAG and parallel ownership

```text
P0 → (P1 || P2) → (P3 || P4A) → P4B → P5
```

P1 and P2 MAY proceed in parallel after P0 merge. P3 and P4A MAY proceed in
parallel after P1 and P2. P4B requires P3 and P4A evidence. P5 is
controlled-acceptance only and MUST NOT mutate P1–P4 production code.

### 6.1 P1 exclusive allowlist (report assembly)

```text
V06_P1_FILE_ALLOWLIST
backend/src/cold_storage/modules/reports/application/persisted_calculation_reads.py
backend/src/cold_storage/modules/reports/infrastructure/persisted_calculation_query.py
backend/src/cold_storage/modules/reports/infrastructure/real_data_provider.py
backend/src/cold_storage/modules/reports/application/assembler.py
backend/src/cold_storage/modules/reports/domain/quality.py
backend/alembic/**
backend/tests/unit/test_real_report_data_provider.py
backend/tests/unit/test_reports_service.py
backend/tests/integration/test_v06_p1_report_assembly.py
```

P1 is sole migration owner if P1 later proves schema is required. P0 MUST NOT
add a migration.

### 6.2 P2 exclusive allowlist (report rendering)

```text
V06_P2_FILE_ALLOWLIST
backend/src/cold_storage/modules/reports/renderers/**
backend/src/cold_storage/modules/reports/localization/**
backend/src/cold_storage/modules/reports/application/render_model_localizer.py
backend/src/cold_storage/modules/reports/application/canonical_render_model_builder.py
backend/src/cold_storage/modules/reports/application/render_service.py
backend/tests/unit/test_reports_rendering.py
backend/tests/pilot/test_multilingual_report_pilot.py
backend/tests/pilot/run_multilingual_report_pilot.py
backend/tests/integration/test_v06_p2_report_rendering.py
```

P2 covers rendering/pilot tests for Issue #17 hardening items.

### 6.3 P3 exclusive scope (evaluation)

```text
V06_P3_FILE_ALLOWLIST
backend/tests/evaluation/**
backend/tests/fixtures/v06/**
docs/tasks/V0_6-P3-evaluation-contract.md
```

P3 MUST NOT edit reports production module paths unless a later authorized
contract amendment explicitly expands scope.

### 6.4 P4A exclusive scope (frontend report workflow)

```text
V06_P4A_FILE_ALLOWLIST
frontend/src/features/reports/**
frontend/tests/features/reports/**
```

### 6.5 P4B exclusive scope (samples and runbook)

```text
V06_P4B_FILE_ALLOWLIST
samples/v06-**
backend/src/cold_storage/bootstrap/v06_sample_loader.py
docs/runbooks/v06-pilot-runbook.md
Makefile
```

### 6.6 P5 exclusive scope (controlled acceptance)

```text
V06_P5_FILE_ALLOWLIST
backend/tests/integration/test_v06_p5_controlled_acceptance.py
docs/tasks/V0_6-P5-controlled-acceptance-contract.md
```

P5 MUST NOT mutate P1–P4 production code.

### 6.7 Allowlist disjointness

`V06_P1_FILE_ALLOWLIST` and `V06_P2_FILE_ALLOWLIST` MUST be disjoint. Overlap
is a contract defect and MUST be resolved in the contract, not by editing
production code in P0.

## 7. Known baseline gaps at `BASE_MAIN_SHA`

Record only; P0 does not fix.

| ID | Gap | Evidence at `BASE_MAIN_SHA` |
| --- | --- | --- |
| V06-GAP-001 | Investment stage skipped in report assembly reads | `persisted_calculation_reads.py` skips `investment`; `CANONICAL_STAGE_TO_REPORT_ATTR` has no `investment`; `OrchestratedCalculationResult` has no `investment_result` |
| V06-GAP-002 | Real data provider omits investment section | `real_data_provider._REPORT_SECTIONS` has only four calculation sections and omits `investment_estimate` |
| V06-GAP-003 | Assembler does not populate `input_conditions` / `assumptions` | `assembler.py` does not read immutable version snapshot for these sections |
| V06-GAP-004 | Living docs describe V0.5 as active unfinished umbrella | `docs/roadmap/DEVELOPMENT_PLAN.md`, `docs/audit/gap-analysis.md`, `docs/audit/current-state.md` |
| V06-GAP-005 | Issue #20 closed but some docs imply open | Issue #20 CLOSED 2026-07-22; TASK-011 docs may still reference open status |

V0.5 delivered gaps V05-P0-001/002/003 at `v0.5.0`. V0.6 P1+ must close
V06-GAP-001 through V06-GAP-003 without breaking V0.4 read compatibility.

## 8. Issue mapping

| Issue | Status at P0 freeze | V0.6 closure timing |
| --- | --- | --- |
| #176 | OPEN (umbrella) | Remains open; P0 refs only |
| #180 | OPEN (P0 tracking) | Closes when P0 evidence merges |
| #184 | OPEN (dispatch) | Refs only |
| #11 | OPEN | Close later after P4B/P5 evidence |
| #13 | OPEN | Close later after evidence |
| #17 | OPEN | Close later after P2/P3 evidence |
| #20 | **CLOSED** (2026-07-22) | Already closed; record in living docs |
| #72 | OPEN | Close later after evidence |

P0 MUST NOT claim closure of #11, #13, #17, #72, or #176.

## 9. Authorization boundaries

```text
V06_P0_IMPLEMENTATION_DISPATCH_AUTHORIZED=YES
V06_P1_IMPLEMENTATION_AUTHORIZED=NO
V06_P2_IMPLEMENTATION_AUTHORIZED=NO
V06_P3_IMPLEMENTATION_AUTHORIZED=NO
V06_P4A_IMPLEMENTATION_AUTHORIZED=NO
V06_P4B_IMPLEMENTATION_AUTHORIZED=NO
V06_P5_IMPLEMENTATION_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
READY_AUTHORIZED=NO
```

P0 allowlist:

```text
docs/tasks/V0_6-P0-five-stage-report-delivery-contract.md
docs/audit/current-state.md
docs/audit/gap-analysis.md
docs/audit/validation-baseline.md
docs/TECH_DEBT.md
docs/roadmap/DEVELOPMENT_PLAN.md
backend/tests/architecture/test_v06_p0_contract.py
```

P0 forbidden without separate authorization:

```text
backend/src/**
frontend/**
backend/alembic/**
samples/**
Makefile
docs/tasks/V0_5-*
docs/tasks/V0_4-*
docs/tasks/V0_3-*
```

## 10. Acceptance criteria

V0.6 P0 R1 is complete when:

```text
P0_CONTRACT_EXISTS=PASS
ORCHESTRATION_STAGE_ORDER_FROZEN=PASS
CALCULATOR_BINDINGS_FROZEN=PASS
POWER_CONFIGURATION_NOT_CANONICAL=PASS
REPORT_SOURCE_MAPPING_FROZEN=PASS
INPUT_CONDITIONS_ASSUMPTIONS_RULES_FROZEN=PASS
FAIL_CLOSED_AND_REVIEW_LIFECYCLE_DOCUMENTED=PASS
P1_P2_ALLOWLISTS_DISJOINT=PASS
KNOWN_BASELINE_GAPS_RECORDED=PASS
ISSUE_20_CLOSED_RECORDED=PASS
ARCHITECTURE_TESTS_PASS=PASS
RUFF_PASS=PASS
MYPY_PASS=PASS
MERGE_AUTHORIZED=NO
DRAFT=YES
```

Authoritative architecture test surface:

```text
backend/tests/architecture/test_v06_p0_contract.py
```

## 11. Contract closure state

```text
TASK=V06_P0_REPORT_DELIVERY_CONTRACT_DEFINITION_R1
PARENT_ISSUE=176
P0_TRACKING_ISSUE=180
CONTRACT_DEFINITION_SOURCE_SHA=06a446501b83f75ba42b3920d912d980c51d7fe5
AUTHORIZED_CONTRACT_PATH=docs/tasks/V0_6-P0-five-stage-report-delivery-contract.md

V06_P0_CONTRACT_FROZEN=YES
V06_P0_IMPLEMENTATION_AUTHORIZED=YES
V06_P0_CONTRACT_EXECUTED=NO
V06_P1_IMPLEMENTATION_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
DRAFT=YES

NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 12. Revision history

| Rev | Date | Change |
| --- | --- | --- |
| R1 | 2026-08-25 | Initial P0 report delivery contract freeze at `06a446501b83f75ba42b3920d912d980c51d7fe5` |
| R2 | 2026-08-25 | Correct P1/P2 package test allowlists to name existing repository test files |
