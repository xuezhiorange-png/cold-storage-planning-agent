# V0.7 P0 Data And Logic Trust-Loop Contract

**Status:** Definition freeze R1 — V0.7 identity, package DAG, allowlists, Aily boundary
**Authority:** Contract document is the freeze authority until a GitHub umbrella issue is created
**Contract definition source SHA:** `f8a4b80a8a8fab26113b57d9f4ea666b8bc699ba`
**Contract definition source tree:** `23af6e60e4247394b2b12c50440d5fc03a819074`
**Previous release:** `v0.6.0`
**Target branch:** `cursor/v07-p0-trust-loop-contract-6c68`

This document freezes the V0.7 P0 **trust-loop contract boundary** only.
It does not authorize P1–P7 implementation, formula recut, coefficient
promotion, live Aily enablement, tag publication, or Release.

## 0. Contract identity and governance

```text
TASK=V07_P0_TRUST_LOOP_CONTRACT_DEFINITION_R1
PARENT_ISSUE=PENDING
P0_TRACKING_ISSUE=PENDING
DISPATCH_ISSUE=PENDING
GOVERNANCE_OWNER=V0.7
BASE_MAIN_SHA=f8a4b80a8a8fab26113b57d9f4ea666b8bc699ba
BASE_TREE=23af6e60e4247394b2b12c50440d5fc03a819074
PREVIOUS_RELEASE=v0.6.0
TARGET_BRANCH=cursor/v07-p0-trust-loop-contract-6c68
TARGET_FILE=docs/tasks/V0_7-P0-trust-loop-contract.md
TARGET_PR_STATE=DRAFT

CONTRACT_STATUS=DEFINITION_R1_DRAFT_FOR_INDEPENDENT_REVIEW
V07_P0_IMPLEMENTATION_AUTHORIZED=YES
V07_P1_IMPLEMENTATION_AUTHORIZED=NO
V07_P2_IMPLEMENTATION_AUTHORIZED=NO
V07_P3A_IMPLEMENTATION_AUTHORIZED=NO
V07_P3B_IMPLEMENTATION_AUTHORIZED=NO
V07_P4_IMPLEMENTATION_AUTHORIZED=NO
V07_P5_IMPLEMENTATION_AUTHORIZED=NO
V07_P6_IMPLEMENTATION_AUTHORIZED=NO
V07_P7_IMPLEMENTATION_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
CONTROLLED_ACCEPTANCE_EXECUTION_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
DEMO_COEFFICIENT_CONFLICT_RESOLUTION=NO
LIVE_MODEL_PRODUCTION_ENABLEMENT_AUTHORIZED=NO
AILY_LIVE_IMPLEMENTATION=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P0 freezes version identity, known remaining gaps after `v0.6.0`, package
ownership, fail-closed rules, expert-decision items, and the Feishu Aily
integration **boundary**. P0 does **not** change application behavior.

## 1. Objective and non-goals

### 1.1 Objective

V0.7 is a **data and logic trust loop**, not a feature-expansion release.

Prove and close already-landed capabilities so the following chain is
traceable, repeatable, and complete on the unmodified operator
`create_app` path:

```text
EngineeringInputBundleV1
 → five-stage-execution
 → production scheme-run
 → workflow / scheme / report / workbench
 → reviewable report JSON
 → trusted review
 → formal zh-CN / en-US DOCX / PDF
```

Judgement for V0.7 is **not** “more features”. It is:

- same input + coefficient version + calculator version ⇒ same hashes;
- SQLite and PostgreSQL agree;
- API, persistence, scheme, workflow, and report read the same canonical
  results;
- reports never recalculate formulas;
- missing key parameters fail closed;
- demo coefficients remain unverified;
- the operator public-API path can complete the review/formal loop that
  V0.6 P3 proved only under evaluation DI.

### 1.2 Non-goals (hard boundaries)

```text
V07_P1_IMPLEMENTATION_AUTHORIZED=NO
V07_P2_IMPLEMENTATION_AUTHORIZED=NO
V07_P3A_IMPLEMENTATION_AUTHORIZED=NO
V07_P3B_IMPLEMENTATION_AUTHORIZED=NO
V07_P4_IMPLEMENTATION_AUTHORIZED=NO
V07_P5_IMPLEMENTATION_AUTHORIZED=NO
V07_P6_IMPLEMENTATION_AUTHORIZED=NO
V07_P7_IMPLEMENTATION_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
DEMO_COEFFICIENT_CONFLICT_RESOLUTION=NO
LIVE_MODEL_PRODUCTION_ENABLEMENT_AUTHORIZED=NO
AILY_LIVE_IMPLEMENTATION=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
FIELD_EQUIPMENT_CONTROL=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
AGENT_TO_ENGINEERING_VALUE=NO
REPORT_FORMULA_RECALCULATION=NO
NEW_CANONICAL_STAGE=NO
MICROSERVICES=NO
PRODUCTION_RBAC_CLAIM=NO
```

P0 must not:

- implement data-integrity repairs, consumer hash alignment, report DI,
  or production-scheme routes;
- add migrations or change calculator formulas;
- promote or choose between conflicting demo coefficient values;
- treat V0.6 operator `submit-review` HTTP 409 as a defect to hide;
- claim production RBAC for `mark_reviewed`;
- implement live Feishu Aily MCP/connectors/skills;
- reopen V0.5 five-stage persistence or V0.6 report source mapping as
  unfinished umbrellas.

## 2. Frozen inherited contracts

V0.7 inherits and must not recut:

| Frozen item | Authority |
| --- | --- |
| Stage order `zone → cooling_load → equipment → power → investment` | `ORCHESTRATION_STAGE_ORDER` |
| Canonical identities `cold_room_zone_plan`, `cooling_load`, `equipment`, `installed_power`, `investment_estimate` | `CALCULATOR_BINDINGS` / `STAGE_TO_CALCULATOR_NAME` |
| `power_configuration` supplemental only | `SUPPLEMENTAL_ONLY_CALCULATOR_NAMES` |
| Five-row report source mapping | table below; V0.6 P0 + delivered V0.6 P1 |
| `input_conditions` from `EngineeringInputBundleV1` / immutable snapshot | V0.6 P0 §3.1 |
| `assumptions` from persisted snapshots and review-required flags | V0.6 P0 §3.2 |
| `measured_value` lineage: `source_result_id`, `source_tool`, `source_tool_version` | V0.6 P0 §3.3 |
| Reports MUST NOT recalculate formulas; templates MUST NOT embed formulas | V0.6 P0 §3.4 |
| `FORMAL_EXPORT_STATUSES`, `requires_review=true`, trusted `mark_reviewed` | V0.6 P0 §4 |
| SQLite / PostgreSQL parity of contract meaning | V0.6 P0 §5 |

Inherited report source mapping (do not recut):

| Persisted calculator | `OrchestratedCalculationResult` attr | Report JSON section key |
| --- | --- | --- |
| `cold_room_zone_plan` | `throughput_result` | `throughput_inventory_area` |
| `cooling_load` | `cooling_load_result` | `cooling_load` |
| `equipment` | `equipment_result` | `equipment_selection` |
| `installed_power` | `power_result` | `electrical_and_energy` |
| `investment_estimate` | `investment_result` | `investment_estimate` |

`high_throughput_review` remains a scenario label only.

Trusted operator remains an injected application-service seam.
V0.7 does not claim production RBAC.

## 3. Known remaining gaps at `v0.6.0`

Record only; P0 does not fix. Do **not** reopen delivered V0.6 assembly
gaps V06-P0-001/002/003 as active unfinished work.

| ID | Gap | Evidence at `BASE_MAIN_SHA` |
| --- | --- | --- |
| V07-GAP-001 | Operator `create_app` report DI omits `project_service`, so `project_summary` is absent and generate stays `draft` | `bootstrap/app.py` `_get_report_service`; `RealReportDataProvider.get_project()` |
| V07-GAP-002 | No public API persists `source_mode=production` scheme runs bound to the five-stage version, so `scheme_comparison` is absent on the operator sample | `schemes/api/routes.py` legacy `scheme-runs`; `v06_sample_loader.py` avoids that path |
| V07-GAP-003 | Evaluation happy path (V0.6 P3 test DI + direct production seed) ≠ operator path (V0.6 P5 Surface A fail-closed PASS) | `V0_6-P5-controlled-acceptance-contract.md` Surface A/B |
| V07-GAP-004 | Coefficient metadata can diverge from effective calculator inputs; optional bundle leaves may not enter the execution snapshot | `docs/audit/coefficient-inventory.md`; `engineering_input_bundle.py` KEY-only zone projection |
| V07-GAP-005 | Workflow/scheme consumer hash helpers may not equal persisted `fingerprint.result_hash` | `workflow/application/service.py`; `schemes/application/canonical_source_reads.py` |
| V07-GAP-006 | Complete `EngineeringInputBundleV1` is not the default immutable project-version snapshot on the operator sample path | `five_stage_execution.py`; `persisted_calculation_query.py` bundle schema guard |
| V07-GAP-007 | Registry seed and embedded calculator coefficients remain dual-track | `coefficients` seed vs `DemoZoneCoefficient` |
| V07-GAP-008 | No Feishu Aily integration boundary contract exists | repository has no Aily contract/ADR |
| V07-GAP-009 | Issues #11 / #13 / #17 / #176 remain OPEN because operator formal closure is still fail-closed | GitHub issue list at freeze |
| V07-GAP-010 | Demo coefficient conflicts remain unresolved and must stay `requires_review=true` | V05-P0-004 / V06-P0-006 / TD-003 note |

V0.6 P5 **correctly** recorded operator fail-closed as PASS at `v0.6.0`.
V0.7 must close the seam by binding, not by weakening fail-closed tests.

## 4. Package DAG and parallel waves

```text
P0 → (P1 || P2 || P3A || P3B || P6) → (P4 || P5) → P7
```

Hard edges:

| Edge | Reason |
| --- | --- |
| P0 → all | Frozen contract required |
| P3A → P5 | Operator report generate needs `project_summary` |
| P3B → P5 | Operator report generate needs production `scheme_comparison` |
| P1 + P2 → P4 | P4 repairs only proven findings |
| P5 + P6 → P7 | Controlled acceptance consumes operator + Aily-boundary evidence |
| P3 ∥ P4 from V0.6 numbering is **not** used | V0.7 uses P3A/P3B for the operator report/scheme seam |

Wave 1 after P0 merge: **P1 ∥ P2 ∥ P3A ∥ P3B ∥ P6**.
Wave 2: **P4** (after P1/P2 evidence) and **P5** (after P3A+P3B).
Wave 3: **P7**.

P7 MUST NOT mutate P1–P6 production code. P7 does not authorize tag or
Release.

## 5. Package ownership and exclusive allowlists

**Global forbidden for every V0.7 package unless a later authorized
contract amendment names it:**

```text
V07_GLOBAL_FORBIDDEN
backend/src/cold_storage/modules/calculations/domain/**
docs/tasks/V0_6-*
docs/tasks/V0_5-*
docs/tasks/V0_4-*
docs/tasks/V0_3-*
.github/workflows/v0-3-p5-*
```

Calculator formula files are forbidden even for metadata-only edits in
Wave 1. Any calculator behavior change requires a separate FX package
with `FORMULA_RECUT_AUTHORIZED=YES`.

### 5.1 P0 exclusive allowlist (this package)

```text
V07_P0_FILE_ALLOWLIST
docs/tasks/V0_7-P0-trust-loop-contract.md
docs/audit/current-state.md
docs/audit/gap-analysis.md
docs/audit/validation-baseline.md
docs/TECH_DEBT.md
docs/roadmap/DEVELOPMENT_PLAN.md
backend/tests/architecture/test_v07_p0_contract.py
```

### 5.2 P1 exclusive allowlist (data integrity proof)

Objective: prove input, unit, default, coefficient version, source,
assumption, warning, review-status, and snapshot traceability. Do **not**
choose conflicting demo values.

```text
V07_P1_FILE_ALLOWLIST
docs/tasks/V0_7-P1-data-integrity-contract.md
docs/audit/coefficient-inventory.md
docs/audit/data-integrity-matrix.md
backend/tests/architecture/test_v07_p1_data_integrity_contract.py
backend/tests/architecture/test_v07_p1_default_alignment_matrix.py
backend/tests/architecture/test_v07_p1_coefficient_metadata_alignment.py
backend/tests/integration/test_v07_p1_bundle_execution_traceability.py
backend/tests/integration/test_v07_p1_version_snapshot_authority.py
backend/tests/integration/test_v07_p1_seed_authority.py
```

P1 Wave 1 is **proof and matrix**. It MAY record `KNOWN_CONFLICT` rows.
It MUST NOT edit calculator formulas, report assembler mapping, scheme
routes, or `bootstrap/app.py`.

### 5.3 P2 exclusive allowlist (logic / cross-consumer consistency)

Objective: CI-prove API persistence, SourceBinding, scheme, workflow, and
report identity **and numeric** consistency, plus idempotency / replay /
SQLite-PostgreSQL hash parity.

```text
V07_P2_FILE_ALLOWLIST
docs/tasks/V0_7-P2-cross-consumer-consistency-contract.md
backend/tests/integration/v07_p2_consistency_evidence.py
backend/tests/integration/v07_p2_numeric_projection_map.py
backend/tests/integration/test_v07_p2_cross_consumer_consistency_sqlite.py
backend/tests/integration/test_v07_p2_cross_consumer_consistency_postgresql.py
backend/tests/architecture/test_v07_p2_consumer_hash_alignment.py
samples/v07-consistency/**
backend/tests/golden/v07_cross_consumer_v1.json
```

P2 MUST NOT edit `modules/calculations/**`. Consumer hash **production**
repairs are a separate P2b package, not this Wave 1 allowlist.

Numeric projection mapping lives in tests, not Vue or report templates.
Reports MUST NOT recalculate formulas.

### 5.4 P3A exclusive allowlist (report production composition)

Objective: inject `project_service` into `RealReportDataProvider` on the
unmodified `create_app` path so `project_summary` can be assembled.

```text
V07_P3A_FILE_ALLOWLIST
docs/tasks/V0_7-P3A-report-production-composition-contract.md
backend/src/cold_storage/bootstrap/app.py
backend/tests/integration/test_v07_p3a_report_project_summary_sqlite.py
backend/tests/integration/test_v07_p3a_report_project_summary_postgresql.py
```

P3A may change **only** `_get_report_service` composition in
`bootstrap/app.py`. It MUST NOT add routes, change assembler
`REQUIRED_SECTIONS`, weaken fail-closed, or touch scheme services.

Until P3B lands, operator `scheme_comparison` may still block
`submit-review`. P3A tests assert `project_summary` presence, not full
formal-export success.

### 5.5 P3B exclusive allowlist (public production scheme path)

Objective: add a distinct public production-scheme API that persists
`source_mode=production` runs bound to five-stage `SourceBinding`.
Legacy `POST .../scheme-runs` remains unsupported as report authority.

```text
V07_P3B_FILE_ALLOWLIST
docs/tasks/V0_7-P3B-production-scheme-public-api-contract.md
backend/src/cold_storage/modules/schemes/api/routes.py
backend/tests/integration/test_v07_p3b_production_scheme_public_api_sqlite.py
backend/tests/integration/test_v07_p3b_production_scheme_public_api_postgresql.py
backend/tests/unit/test_v07_p3b_production_scheme_routes.py
```

P3B MUST NOT edit `bootstrap/app.py`. Wire the new route through existing
`register_scheme_routes` and existing `get_production_scheme_service`.
Do not weaken `read_verified_production_scheme_run`. Do not bind demo
`GET /demo/scheme-comparison` onto the sample version.

Recommended route identity (frozen intent):

```text
POST /api/v1/projects/{project_id}/versions/{version}/production-scheme-runs
```

### 5.6 P4 exclusive allowlist (targeted proven repairs)

P4 is **not** Wave 1. It exists only after P1/P2 evidence. Each repair is
one bounded PR. Formula changes require a named FX amendment.

```text
V07_P4_FILE_ALLOWLIST
docs/tasks/V0_7-P4-targeted-repair-contract.md
docs/audit/coefficient-inventory.md
```

P4 production paths are added by contract amendment after evidence, not
guessed in P0.

### 5.7 P5 exclusive allowlist (operator sample and runbook)

Requires P3A + P3B. Do **not** mutate the V0.6 fail-closed sample loader.

```text
V07_P5_FILE_ALLOWLIST
docs/tasks/V0_7-P5-operator-sample-runbook-contract.md
samples/v07-trust-loop/**
backend/src/cold_storage/bootstrap/v07_sample_loader.py
docs/runbooks/v07-trust-loop-runbook.md
Makefile
backend/tests/integration/v07_p5_operator_fixtures.py
backend/tests/integration/test_v07_p5_operator_sample_sqlite.py
backend/tests/integration/test_v07_p5_operator_sample_postgresql.py
frontend/src/features/reports/**
frontend/src/features/five-stage/components/**
frontend/tests/features/reports/**
```

Loader rules: public API only; no `planning-run`; no Alembic inside the
loader; trusted actor remains a TestClient seam, not production RBAC.

### 5.8 P6 exclusive allowlist (Aily boundary freeze)

Docs + static contract tests only. No live Aily implementation.

```text
V07_P6_FILE_ALLOWLIST
docs/tasks/V0_7-P6-aily-integration-boundary-contract.md
docs/architecture/ADR-027-aily-integration-boundary.md
docs/contracts/aily/v0.7/**
backend/tests/architecture/test_v07_p6_aily_contract.py
```

### 5.9 P7 exclusive allowlist (controlled acceptance)

```text
V07_P7_FILE_ALLOWLIST
docs/tasks/V0_7-P7-controlled-acceptance-contract.md
backend/tests/integration/test_v07_p7_controlled_acceptance.py
Makefile
```

P7 MUST NOT import V0.6 P3 evaluation helpers into operator tests.
P7 MUST NOT mutate V0.6 P5 tests that still document fail-closed
evidence.

### 5.10 Allowlist disjointness

Wave 1 exclusive allowlists `V07_P1_FILE_ALLOWLIST`,
`V07_P2_FILE_ALLOWLIST`, `V07_P3A_FILE_ALLOWLIST`,
`V07_P3B_FILE_ALLOWLIST`, and `V07_P6_FILE_ALLOWLIST` MUST be pairwise
disjoint.

`bootstrap/app.py` is P3A-only.
`schemes/api/routes.py` is P3B-only.

Shared-test rule: each package owns `test_v07_pN_*` files. Packages MUST
NOT edit `test_v06_*` or `test_v05_*` assertion bodies.

## 6. Expert decisions developers must not guess

| ID | Decision | Why not developer-default | Owner |
| --- | --- | --- | --- |
| E1 | `frozen_fruit_ratio` Input vs `DemoZoneCoefficient` | Changes frozen-zone mass | process engineer |
| E2 | `frozen_storage_days` Input vs `DemoZoneCoefficient` | Changes frozen storage | process engineer |
| E3 | `storage_position_capacity_kg` Input vs `DemoZoneCoefficient` | Currently unused by zone formula; still metadata authority | process engineer |
| E4 | `packaging_storage_days` legacy fallback vs demo/orchestration | Legacy path drift | process engineer |
| E5 | `precooling_required_ratio` legacy fallback vs demo | Legacy path drift | process engineer |
| E6 | Investment registry ratio semantic vs embedded power-distribution unit | Same-looking code, different unit meaning | process + electrical |
| E7 | Which coefficient seed is runtime authority | Dual seed tracks | coefficient governance |
| E8 | `raw_holding_hours` provided in samples but unused by formula | False authority | process engineer |
| E9 | Whether `scheme_comparison` is a hard formal-export blocker | Closure standard for #11/#13 | report owner |
| E10 | Production trusted-operator / Feishu identity mapping | Security | security + product |
| E11 | Aily out-bound fields, write-path tools, confirmation channel | Compliance | product + security + Feishu owner |

P1/P2 must **detect and register** E1–E8. P4 may repair only after the
named owner records a value, unit, `source_type`, and `requires_review`
decision. Silent promotion remains forbidden.

## 7. Feishu Aily boundary (frozen intent, not implementation)

Aily is an external conversation and orchestration surface.
This system remains the only engineering and persistence authority.

| Aily may | This system must |
| --- | --- |
| Collect intent and missing parameters | Validate `EngineeringInputBundleV1` |
| Call allowlisted tools | Run deterministic five-stage execution |
| Display persisted `{name, value, unit}` | Persist calculation IDs, hashes, sources |
| Guide a human to confirm | Issue and consume confirmation tokens |
| Phrase warnings in natural language | Enforce review/formal-export state machine |

Hard rules:

- `AILY_LIVE_IMPLEMENTATION=NO` in V0.7 except P6 contract artifacts.
- Aily MUST NOT compute engineering values or access ORM/sessions.
- Model-visible tools MUST NOT include `mark_reviewed`, `approve`, or
  confirmation tokens.
- Write tools require proposal → trusted human confirmation →
  re-authorization → execution.
- Actor identity MUST come from trusted transport, not model JSON.
- Current `/api/v1/agent/**` is an internal V0.6 compatibility surface,
  not the Aily production boundary.
- Two call directions MUST NOT be confused:
  - Aily → this system (custom MCP or connector);
  - this system → Aily (skill/session/run OpenAPI).

P6 freezes four model-visible tools plus a non-model confirmation
callback:

1. `planning_context.get`
2. `engineering_inputs.validate`
3. `five_stage_execution.propose`
4. `report_delivery.propose`

Confirmation callback is not a model tool.

## 8. Issue mapping

| Issue | Status at P0 freeze | V0.7 closure timing |
| --- | --- | --- |
| #176 | OPEN (V0.6 umbrella) | Remains open until operator + evaluation surfaces align; do not auto-close |
| #11 | OPEN | Close later after operator `submit-review` 200 with complete JSON |
| #13 | OPEN | Close later after operator formal artifacts 200 |
| #17 | OPEN | Rendering follow-ups; not a V0.7 formula recut |
| #20 | **CLOSED** (2026-07-22) | Already closed; do not reopen |

P0 MUST NOT claim closure of #11, #13, #17, or #176.

GitHub umbrella/tracking issues for V0.7 are `PARENT_ISSUE=PENDING` until
created. Missing GitHub numbers do not block this contract freeze.

## 9. Authorization boundaries

```text
V07_P0_IMPLEMENTATION_DISPATCH_AUTHORIZED=YES
V07_P1_IMPLEMENTATION_AUTHORIZED=NO
V07_P2_IMPLEMENTATION_AUTHORIZED=NO
V07_P3A_IMPLEMENTATION_AUTHORIZED=NO
V07_P3B_IMPLEMENTATION_AUTHORIZED=NO
V07_P4_IMPLEMENTATION_AUTHORIZED=NO
V07_P5_IMPLEMENTATION_AUTHORIZED=NO
V07_P6_IMPLEMENTATION_AUTHORIZED=NO
V07_P7_IMPLEMENTATION_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
READY_AUTHORIZED=NO
AILY_LIVE_IMPLEMENTATION=NO
```

P0 forbidden without separate authorization:

```text
backend/src/**
frontend/**
backend/alembic/**
samples/**
Makefile
docs/tasks/V0_6-*
docs/tasks/V0_5-*
docs/tasks/V0_4-*
docs/tasks/V0_3-*
```

## 10. Global V0.7 acceptance gate (release later, not P0)

P7 completion may **propose** `v0.7.0`; P0/P7 do not authorize tag.

```text
V07_P0_CONTRACT_FROZEN=PASS
V07_PACKAGE_DAG_FROZEN=PASS
V07_AILY_BOUNDARY_FROZEN=PASS
V07_ALLOWLISTS_DISJOINT=PASS
CANONICAL_FIVE_PERSISTED=PASS
POWER_CONFIGURATION_SUPPLEMENTAL_ONLY=PASS
MISSING_KEY_LEAF_FAIL_CLOSED=PASS
PRODUCTION_SCHEME_RUN_ON_VERSION=PASS
REPORT_PROJECT_SUMMARY_BOUND=PASS
REPORT_SCHEME_COMPARISON_BOUND=PASS
INPUT_CONDITIONS_ASSUMPTIONS_FROM_PERSISTED=PASS
WORKFLOW_SCHEME_REPORT_PARITY=PASS
NO_FORMULA_RECALC_IN_REPORT=PASS
OPERATOR_SUBMIT_REVIEW_OR_DOCUMENTED_FAIL_CLOSED=PASS
UNTRUSTED_ACTOR_MARK_REVIEWED_FAIL_CLOSED=PASS
DEMO_COEFFICIENTS_REMAIN_UNVERIFIED=PASS
FORMULA_RECUT=NO
COEFFICIENT_PROMOTION=NO
AILY_LIVE_IMPL=NO
TAG_PUBLICATION_AUTHORIZED=NO
```

## 11. P0 acceptance criteria

V0.7 P0 R1 is complete when:

```text
P0_CONTRACT_EXISTS=PASS
ORCHESTRATION_STAGE_ORDER_FROZEN=PASS
CALCULATOR_BINDINGS_FROZEN=PASS
POWER_CONFIGURATION_NOT_CANONICAL=PASS
V07_GAPS_RECORDED=PASS
WAVE1_ALLOWLISTS_DISJOINT=PASS
AILY_BOUNDARY_DOCUMENTED=PASS
EXPERT_DECISIONS_RECORDED=PASS
ISSUE_20_CLOSED_RECORDED=PASS
LIVING_DOCS_TRUTH_UP=PASS
ARCHITECTURE_TESTS_PASS=PASS
RUFF_PASS=PASS
MYPY_PASS=PASS
MERGE_AUTHORIZED=NO
DRAFT=YES
```

Authoritative architecture test surface:

```text
backend/tests/architecture/test_v07_p0_contract.py
```

## 12. Contract closure state

```text
TASK=V07_P0_TRUST_LOOP_CONTRACT_DEFINITION_R1
PARENT_ISSUE=PENDING
P0_TRACKING_ISSUE=PENDING
CONTRACT_DEFINITION_SOURCE_SHA=f8a4b80a8a8fab26113b57d9f4ea666b8bc699ba
AUTHORIZED_CONTRACT_PATH=docs/tasks/V0_7-P0-trust-loop-contract.md

V07_P0_CONTRACT_FROZEN=YES
V07_P0_IMPLEMENTATION_AUTHORIZED=YES
V07_P0_CONTRACT_EXECUTED=NO
V07_P1_IMPLEMENTATION_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
DRAFT=YES

NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 13. Revision history

| Rev | Date | Change |
| --- | --- | --- |
| R1 | 2026-08-26 | Initial P0 trust-loop freeze at `v0.6.0` / `f8a4b80a8a8fab26113b57d9f4ea666b8bc699ba` |
