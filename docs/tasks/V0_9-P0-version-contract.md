# V0.9 P0 Version Contract

**Status:** Definition freeze R1 — V0.9 identity, operator KEY, DAG, allowlists  
**Authority:** This contract plus `docs/tasks/V0_9-version-plan.md`  
**Contract definition source SHA:** `0dc8de5b3c711aaa662b0bbda3988def037fda3b`  
**Contract definition source tree:** `db5c9298c1be7a922b0cacaf84a8c9f176c87838`  
**Previous release:** `v0.8.0`  
**Target branch:** `cursor/v09-version-plan-6c68`

This document freezes the V0.9 P0 **version contract** only. It does not
authorize P1–P7 implementation, formula code, coefficient promotion, live
Aily, tag publication, or Release.

Companion documents:

- Overall plan (formula lock §4): `docs/tasks/V0_9-version-plan.md`
- ADR: `docs/architecture/ADR-029-v09-operator-key-and-workbench-recut.md`

## 0. Contract identity and governance

```text
TASK=V09_P0_VERSION_CONTRACT_DEFINITION_R1
PARENT_ISSUE=PENDING
P0_TRACKING_ISSUE=PENDING
DISPATCH_ISSUE=PENDING
GOVERNANCE_OWNER=V0.9
BASE_MAIN_SHA=0dc8de5b3c711aaa662b0bbda3988def037fda3b
BASE_TREE=db5c9298c1be7a922b0cacaf84a8c9f176c87838
PREVIOUS_RELEASE=v0.8.0
TARGET_BRANCH=cursor/v09-version-plan-6c68
TARGET_FILE=docs/tasks/V0_9-P0-version-contract.md
TARGET_PR_STATE=DRAFT

CONTRACT_STATUS=DEFINITION_R1_DRAFT_FOR_INDEPENDENT_REVIEW
V09_P0_IMPLEMENTATION_AUTHORIZED=YES
V09_P1_IMPLEMENTATION_AUTHORIZED=NO
V09_P2_IMPLEMENTATION_AUTHORIZED=NO
V09_P3_IMPLEMENTATION_AUTHORIZED=NO
V09_P4_IMPLEMENTATION_AUTHORIZED=NO
V09_P5_IMPLEMENTATION_AUTHORIZED=NO
V09_P6_IMPLEMENTATION_AUTHORIZED=NO
V09_P7_IMPLEMENTATION_AUTHORIZED=NO
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
PRODUCTION_RBAC_CLAIM=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P0 freezes version identity, operator KEY, package DAG, allowlists, and
review-versus-export policy. P0 does **not** change application behavior.
Zone formula numbers live in the version plan, not in this file.

## 1. Objective and non-goals

### 1.1 Objective

V0.9 is an **operator workbench recut + zone-planning formula recut**.
The formula package is necessary and not sufficient.

On unmodified `create_app` after later packages:

```text
OperatorProcessInputV1 (V0.9 five KEY)
 → application assembler (catalog + identity, including shipping_channel)
 → five-stage-execution (zone planner implements version-plan §4)
 → production scheme-run / report
 → draft export without waiting for review
 → trusted TestClient review / formal export (already delivered at v0.7.0)
```

Judgement for V0.9:

- operator types only the five KEY in §3;
- Vue does not duplicate formulas;
- zone results display persisted layout fields;
- draft export is not blocked by pending review;
- workbench layout uses the screen; demo `requires_review` is not a core stop;
- missing operator KEY fail-closes;
- demo catalog leaves stay `requires_review=true`;
- V0.5/V0.6/V0.7/V0.8 tests keep their assertion bodies.

### 1.2 Non-goals (hard boundaries)

```text
V09_P1_IMPLEMENTATION_AUTHORIZED=NO
V09_P2_IMPLEMENTATION_AUTHORIZED=NO
V09_P3_IMPLEMENTATION_AUTHORIZED=NO
V09_P4_IMPLEMENTATION_AUTHORIZED=NO
V09_P5_IMPLEMENTATION_AUTHORIZED=NO
V09_P6_IMPLEMENTATION_AUTHORIZED=NO
V09_P7_IMPLEMENTATION_AUTHORIZED=NO
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
VUE_ENGINEERING_FORMULAS=NO
NEW_CANONICAL_STAGE=NO
MICROSERVICES=NO
PRODUCTION_RBAC_CLAIM=NO
COOLING_LOAD_FORMULA_RECUT=NO
EQUIPMENT_FORMULA_RECUT=NO
INSTALLED_POWER_FORMULA_RECUT=NO
INVESTMENT_FORMULA_RECUT=NO
V05_V06_V07_V08_TEST_ASSERTION_MUTATION=NO
V07_SAMPLE_LOADER_MUTATION=NO
V08_SAMPLE_LOADER_MUTATION=NO
```

P0 must not:

- implement the assembler, planner, Vue, or export status machine;
- add migrations;
- promote E1–E8 demo conflicts;
- auto-feed zone area into cooling envelope;
- reopen V0.7/V0.8 delivery as unfinished;
- claim production RBAC or live Aily;
- implement Feishu review.

## 2. Frozen inherited contracts

| Frozen item | Authority |
| --- | --- |
| Stage order `zone → cooling_load → equipment → power → investment` | `ORCHESTRATION_STAGE_ORDER` |
| Canonical identities `cold_room_zone_plan`, `cooling_load`, `equipment`, `installed_power`, `investment_estimate` | `CALCULATOR_BINDINGS` |
| `power_configuration` supplemental only | `SUPPLEMENTAL_ONLY_CALCULATOR_NAMES` |
| Five-row report source mapping | V0.6 P0 + delivered V0.6 P1 / V0.7 |
| Reports MUST NOT recalculate formulas | V0.6 P0 §3.4 |
| `FORMAL_EXPORT_STATUSES` | V0.6 / V0.7 (formal only) |
| `DRAFT_EXPORT_STATUSES` | V0.6 (draft path must remain usable) |
| Trusted `mark_reviewed` TestClient seam | V0.7 |
| SQLite / PostgreSQL parity of contract meaning | inherited |
| Aily live implementation | `AILY_LIVE_IMPLEMENTATION=NO` (V0.7 P6) |
| Full `EngineeringInputBundleV1` as execution authority | V0.5 P0; assembler writes it |
| Three leaf sources user / persisted / catalog | ADR-028 |
| Cooling envelope auto-feed | `ZONE_RESULT_TO_COOLING_LOAD_ENVELOPE_AUTO_FEED=NO` |

Inherited report source mapping (do not recut):

| Persisted calculator | `OrchestratedCalculationResult` attr | Report JSON section key |
| --- | --- | --- |
| `cold_room_zone_plan` | `throughput_result` | `throughput_inventory_area` |
| `cooling_load` | `cooling_load_result` | `cooling_load` |
| `equipment` | `equipment_result` | `equipment_selection` |
| `installed_power` | `power_result` | `electrical_and_energy` |
| `investment_estimate` | `investment_result` | `investment_estimate` |

## 3. Operator-minimal input surface

### 3.1 `OperatorProcessInputV1` (V0.9 five KEY)

```text
zone_planning_inputs.daily_inbound_mass_kg                 unit=kg/day
zone_planning_inputs.finished_storage_days                 unit=day
zone_planning_inputs.frozen_storage_days                   unit=day
zone_planning_inputs.main_packaging_storage_days           unit=day
zone_planning_inputs.auxiliary_packaging_storage_days      unit=day
```

Removed versus V0.8:

```text
zone_planning_inputs.working_time_h_per_day
zone_planning_inputs.packaging_storage_days
zone_planning_inputs.precooling_required_ratio
```

`precooling_required_ratio` is deleted because **100% of inbound is
precooled**. Primary and secondary precooling use full-plant daily inbound.

Workbench supplies `project_version_identity`. That identity is not an
engineering value the operator types.

```text
schema_id: OperatorProcessInputV1
schema_version: 1.1.0
```

(`1.1.0` is the V0.9 KEY set. P1 publishes JSON. P0 does not ship schema.)

### 3.2 Leaf-source split

Unchanged from ADR-028: operator KEY / persisted lineage / explicit catalog.
Zone remainder of `ColdRoomZonePlanInput` that is not a V0.9 KEY remains
catalog/demo until P2 writes the locked planner rules. P1 must still expand
a complete bundle so five-stage execution can run; P1 must not invent
planner geometry numbers.

### 3.3 Fail-closed

Missing operator KEY must fail-closed (`MISSING_ENGINEERING_PARAMETER`).
Catalog holes and lineage mismatches fail-closed. Calculators must not
introduce a new silent default as authority.

```text
MISSING_OPERATOR_PROCESS_KEY_LEAF → MISSING_ENGINEERING_PARAMETER
MISSING_CATALOG_LEAF_FOR_REQUIRED_DOWNSTREAM_KEY → MISSING_ENGINEERING_PARAMETER
LINEAGE_TYPE_OR_ZONE_CODE_MISMATCH → UPSTREAM_LINEAGE_BIND_FAILED
CALCULATOR_SILENT_DEFAULT_AS_NEW_AUTHORITY → FORBIDDEN
OPERATOR_PRECOOLING_RATIO_KEY → FORBIDDEN
```

### 3.4 Frontend rule

V0.9 operator **工程输入** MUST present only the five KEY in §3.1 plus
submit. It MUST NOT present `precooling_required_ratio` or
`working_time_h_per_day` as operator KEY.

The V0.4 基本信息 / `planning-run` page remains leftover and MUST stay
labeled as non-authority.

### 3.5 Review versus export

```text
DRAFT_EXPORT_INDEPENDENT_OF_REVIEW=YES
FORMAL_EXPORT_REQUIRES_APPROVED_OR_ARCHIVED=YES
BROWSER_MARK_REVIEWED_IS_NOT_PRODUCTION_RBAC=YES
FEISHU_REVIEW_IMPLEMENTATION=NO
```

UI must separate draft download from formal download. Formal blockers must
not disable draft export. Demo `requires_review=true` must not be rendered
as a core workbench stop.

## 4. Zone formula authority

Authoritative formula lock: `docs/tasks/V0_9-version-plan.md` §4.

P0 records ownership only:

| Zone | Notes |
| --- | --- |
| 办公室 / 更衣室 / 覆膜间 | Fixed areas this version |
| 一级预冷间 / 二级预冷间 | Full-plant inbound; dual room schemes persisted |
| 原果 / 成品 / 次果 / 冻果 | Packed rectangle; need vs actual positions |
| 分选包装间 | Table matrix; four-sided perimeter |
| 包材库 | Two user days; existing material coefficients |
| 出货通道 (`shipping_channel`, 1~3℃) | New zone; no extra operator KEY |

P2 implements that section in `zone_planning.py` only after
`FORMULA_RECUT_AUTHORIZED=YES` and P2 dispatch. P3 displays persisted
fields only.

## 5. Known remaining gaps at `v0.8.0`

Record only; P0 does not fix.

| ID | Gap | Evidence at `BASE_MAIN_SHA` |
| --- | --- | --- |
| V09-GAP-001 | Zone planner still uses unused KEY, fixed aisle factor, no shipping_channel | `calculations/domain/zone_planning.py` |
| V09-GAP-002 | Operator KEY still V0.8 five including precooling ratio and working time | `OperatorProcessInputV1`; Engineering input form |
| V09-GAP-003 | Zone results table shows area number without layout/schemes | `ZoneResultsTable.vue` |
| V09-GAP-004 | Formal-export blockers and stacked 核心阻断/溯源阻断 dominate every page | `WorkflowGuidancePanel.vue`; `KnowledgeProvenancePanel.vue` |
| V09-GAP-005 | Draft export exists but is easy to confuse with formal/review | `ReportExportPanel.vue`; `FORMAL_EXPORT_STATUSES` |
| V09-GAP-006 | Workbench is a single column with page max-width crowding empty screen | `WorkbenchLayout.vue` |
| V09-GAP-007 | Calculations empty-state still tells operators to fill EngineeringInputBundleV1 | `CalculationsPage.vue` |
| V08-GAP-003 | Cooling envelope/thermal KEY remain demo catalog | carried forward |
| V07-GAP-004 | Coefficient metadata can diverge from effective inputs | carried forward |
| V07-GAP-006 | Complete bundle snapshot gap | carried forward |
| V07-GAP-007 | Registry seed vs embedded coefficients dual-track | carried forward |
| V07-GAP-010 | Demo conflicts stay `requires_review=true` | carried forward |

Delivered at `v0.8.0` and must not be reopened as V0.9 umbrellas: five-KEY
assembler path, V0.7 trust loop, Aily **boundary** (not live).

## 6. Package DAG

```text
P0 → (P1 || P4 || P5)
P1 → P2 → P3
(P2 || P3 || P4 || P5) → P6 → P7
```

| Edge | Reason |
| --- | --- |
| P0 → all | Frozen V0.9 contract required |
| P1 → P2 | Planner consumes V0.9 KEY / assembler zone identity |
| P2 → P3 | Display reads persisted layout fields |
| P4 ∥ P5 | Export policy and layout have no formula dependency |
| P6 after P2–P5 | Sample must exercise KEY, planner, UI, draft export |
| P7 last | Controlled acceptance; must not mutate P1–P6 production code |

P7 does not authorize tag or Release.

Wave 1 after P0 merge: **P1 ∥ P4 ∥ P5**.  
Wave 2: **P2**.  
Wave 3: **P3**.  
Wave 4: **P6**.  
Wave 5: **P7**.

## 7. Package ownership and exclusive allowlists

**Global forbidden for every V0.9 package unless that package allowlist
names the path:**

```text
V09_GLOBAL_FORBIDDEN
docs/tasks/V0_8-*
docs/tasks/V0_7-*
docs/tasks/V0_6-*
docs/tasks/V0_5-*
docs/tasks/V0_4-*
docs/tasks/V0_3-*
backend/src/cold_storage/bootstrap/v07_sample_loader.py
backend/src/cold_storage/bootstrap/v08_sample_loader.py
backend/src/cold_storage/modules/calculations/domain/cooling_load.py
backend/src/cold_storage/modules/calculations/domain/equipment.py
backend/src/cold_storage/modules/calculations/domain/installed_power.py
backend/src/cold_storage/modules/calculations/domain/investment.py
```

`zone_planning.py` is forbidden except on **P2**. Cooling/equipment/power/
investment formula files stay forbidden for the whole version.

Do not edit `test_v05_*`, `test_v06_*`, `test_v07_*`, or `test_v08_*`
assertion bodies.

### 7.1 P0 exclusive allowlist (this package)

```text
V09_P0_FILE_ALLOWLIST
docs/tasks/V0_9-P0-version-contract.md
docs/tasks/V0_9-version-plan.md
docs/architecture/ADR-029-v09-operator-key-and-workbench-recut.md
docs/audit/current-state.md
docs/audit/gap-analysis.md
docs/audit/validation-baseline.md
docs/TECH_DEBT.md
docs/roadmap/DEVELOPMENT_PLAN.md
backend/tests/architecture/test_v09_p0_contract.py
```

### 7.2 P1 exclusive allowlist (KEY + assembler + 工程输入)

Objective: V0.9 five KEY in §3.1; assembler expands catalog + zone identity
including `shipping_channel`; Vue 工程输入 shows only those five KEY.

```text
V09_P1_FILE_ALLOWLIST
docs/tasks/V0_9-P1-operator-key-assembler-contract.md
backend/src/cold_storage/modules/projects/application/operator_process_input.py
backend/src/cold_storage/modules/projects/application/engineering_input_bundle.py
backend/src/cold_storage/modules/projects/application/five_stage_execution.py
backend/src/cold_storage/bootstrap/app.py
frontend/src/features/five-stage/components/EngineeringInputBundleForm.vue
frontend/src/features/five-stage/components/EngineeringInputsPage.vue
frontend/src/features/five-stage/model/engineeringInputForm.ts
frontend/src/stores/fiveStageExecution.ts
frontend/src/features/five-stage/api/fiveStageApi.ts
frontend/src/api/contracts/fiveStage.ts
backend/tests/architecture/test_v09_p1_operator_key_contract.py
backend/tests/unit/test_v09_p1_operator_process_input_assembler.py
backend/tests/integration/test_v09_p1_five_field_execution_sqlite.py
backend/tests/integration/test_v09_p1_five_field_execution_postgresql.py
frontend/src/features/five-stage/architecture/test_v09_p1_five_key_operator_form.test.ts
```

`bootstrap/app.py` may only accept the compact operator payload. It MUST NOT
contain engineering formulas. P1 MUST NOT edit `zone_planning.py`.

### 7.3 P2 exclusive allowlist (zone formula recut)

Requires later `FORMULA_RECUT_AUTHORIZED=YES` and P2 dispatch. Implements
version-plan §4.

```text
V09_P2_FILE_ALLOWLIST
docs/tasks/V0_9-P2-zone-formula-recut-contract.md
backend/src/cold_storage/modules/calculations/domain/zone_planning.py
backend/tests/unit/test_zone_planner.py
backend/tests/unit/test_v09_p2_zone_planning.py
backend/tests/architecture/test_v09_p2_zone_formula_contract.py
```

### 7.4 P3 exclusive allowlist (zone result display)

```text
V09_P3_FILE_ALLOWLIST
docs/tasks/V0_9-P3-zone-result-display-contract.md
frontend/src/features/calculations/components/CalculationsPage.vue
frontend/src/features/calculations/components/ZoneResultsTable.vue
frontend/tests/features/calculations/ZoneResultsTable.test.ts
```

Vue MUST NOT compute area, positions, or dock counts.

### 7.5 P4 exclusive allowlist (draft vs formal export)

```text
V09_P4_FILE_ALLOWLIST
docs/tasks/V0_9-P4-draft-formal-export-contract.md
frontend/src/features/reports/components/ReportsPage.vue
frontend/src/features/reports/components/ReportExportPanel.vue
frontend/src/features/reports/composables/useReportExport.ts
frontend/tests/features/reports/useReportWorkflow.test.ts
frontend/tests/features/reports/errorMessages.test.ts
```

Must not implement Feishu. Must not claim production RBAC. Must not weaken
`FORMAL_EXPORT_STATUSES`. Must keep draft export reachable without review.

### 7.6 P5 exclusive allowlist (layout + banners)

```text
V09_P5_FILE_ALLOWLIST
docs/tasks/V0_9-P5-workbench-layout-contract.md
frontend/src/features/workbench/WorkbenchLayout.vue
frontend/src/features/workflow/components/WorkflowGuidancePanel.vue
frontend/src/features/workflow/components/KnowledgeProvenancePanel.vue
frontend/src/features/project/components/ProjectPage.vue
frontend/src/features/schemes/components/SchemesPage.vue
frontend/src/features/power/components/PowerPage.vue
frontend/src/features/investment/components/InvestmentPage.vue
frontend/tests/workbench.test.ts
```

P5 must not change report export status rules (P4) or zone result math (P2/P3).

### 7.7 P6 exclusive allowlist (sample and runbook)

```text
V09_P6_FILE_ALLOWLIST
docs/tasks/V0_9-P6-operator-sample-runbook-contract.md
samples/v09-process-input/**
backend/src/cold_storage/bootstrap/v09_sample_loader.py
docs/runbooks/v09-process-input-runbook.md
Makefile
backend/tests/integration/v09_p6_operator_fixtures.py
backend/tests/integration/test_v09_p6_operator_sample_sqlite.py
backend/tests/integration/test_v09_p6_operator_sample_postgresql.py
```

Do not mutate `v07_sample_loader.py` or `v08_sample_loader.py`.

### 7.8 P7 exclusive allowlist (controlled acceptance)

```text
V09_P7_FILE_ALLOWLIST
docs/tasks/V0_9-P7-controlled-acceptance-contract.md
backend/tests/integration/test_v09_p7_controlled_acceptance_sqlite.py
backend/tests/integration/test_v09_p7_controlled_acceptance_postgresql.py
```

P7 MUST NOT mutate P1–P6 production code. P7 does not authorize tag or
Release.

## 8. Expert decisions developers must not guess

| ID | Decision |
| --- | --- |
| V09-E1 | 100% precool; no operator precooling ratio KEY |
| V09-E2 | Operator working time is not an area KEY; planner hours stay written-dead |
| V09-E3 | Frozen days are operator KEY; frozen ratio stays catalog/hardcoded as in the version plan |
| V09-E4 | Packaging store uses two operator day KEY (main and auxiliary) |
| V09-E5 | 次果 days are not operator KEY this version |
| V09-E6 | Dual precooling schemes always persist; UI must not collapse to one area |
| V09-E7 | Draft export independent of review; formal export stays approved/archived |
| V09-E8 | No Feishu live review; no production RBAC claim |
| E1 / E3 / E6–E8 | Inherited V0.7 `KNOWN_CONFLICT` rows that §4 does not supersede stay unresolved |
| E2 | Zone **area** uses operator `frozen_storage_days`; demo catalog days remain non-authority for that area |
| E4 / E5 | Legacy single `packaging_storage_days` and `precooling_required_ratio` KEY paths are removed on the V0.9 operator path |

Numeric geometry (aisle widths, room modules, pallet mass, packing rates)
is frozen in the version plan. P2 must not invent replacements.

## 9. Issue mapping

| Issue | Status at P0 freeze | V0.9 note |
| --- | --- | --- |
| #11 / #13 / #17 / #176 | CLOSED (human, after `v0.7.0`) | Do not reopen |
| #20 | CLOSED (2026-07-22) | Do not reopen |

GitHub umbrella/tracking issues for V0.9 are `PARENT_ISSUE=PENDING` until
created.

## 10. Authorization boundaries

```text
V09_P0_IMPLEMENTATION_DISPATCH_AUTHORIZED=YES
V09_P1_IMPLEMENTATION_AUTHORIZED=NO
V09_P2_IMPLEMENTATION_AUTHORIZED=NO
V09_P3_IMPLEMENTATION_AUTHORIZED=NO
V09_P4_IMPLEMENTATION_AUTHORIZED=NO
V09_P5_IMPLEMENTATION_AUTHORIZED=NO
V09_P6_IMPLEMENTATION_AUTHORIZED=NO
V09_P7_IMPLEMENTATION_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
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
docs/tasks/V0_8-*
docs/tasks/V0_7-*
docs/tasks/V0_6-*
docs/tasks/V0_5-*
docs/tasks/V0_4-*
docs/tasks/V0_3-*
```

## 11. Global V0.9 acceptance gate (release later, not P0)

P7 completion may **propose** `v0.9.0`; P0/P7 do not authorize tag.

```text
V09_P0_CONTRACT_FROZEN=PASS
V09_PACKAGE_DAG_FROZEN=PASS
V09_ALLOWLISTS_DISJOINT=PASS
OPERATOR_FIVE_KEY_LEAVES_ONLY=PASS
PRECOOLING_RATIO_NOT_OPERATOR_KEY=PASS
ASSEMBLER_NOT_VUE=PASS
ZONE_FORMULA_IN_PLANNER_NOT_VUE=PASS
DRAFT_EXPORT_INDEPENDENT_OF_REVIEW=PASS
FORMAL_EXPORT_STILL_GATED=PASS
MISSING_OPERATOR_KEY_FAIL_CLOSED=PASS
DEMO_CATALOG_LEAVES_REQUIRE_REVIEW=PASS
FULL_BUNDLE_COMPAT_PRESERVED=PASS
FORMULA_RECUT_ONLY_P2=PASS
COEFFICIENT_PROMOTION=NO
AILY_LIVE_IMPL=NO
TAG_PUBLICATION_AUTHORIZED=NO
```

## 12. P0 acceptance criteria

V0.9 P0 R1 is complete when:

```text
P0_CONTRACT_EXISTS=PASS
VERSION_PLAN_EXISTS=PASS
ADR_029_EXISTS=PASS
ORCHESTRATION_STAGE_ORDER_FROZEN=PASS
CALCULATOR_BINDINGS_FROZEN=PASS
POWER_CONFIGURATION_NOT_CANONICAL=PASS
V09_GAPS_RECORDED=PASS
PACKAGE_ALLOWLISTS_DISJOINT=PASS
OPERATOR_FIVE_KEY_SURFACE_DOCUMENTED=PASS
EXPERT_DECISIONS_RECORDED=PASS
ISSUE_20_CLOSED_RECORDED=PASS
LIVING_DOCS_TRUTH_UP=PASS
ARCHITECTURE_TESTS_PASS=PASS
RUFF_PASS=PASS
MERGE_AUTHORIZED=NO
DRAFT=YES
```

Authoritative architecture test surface:

```text
backend/tests/architecture/test_v09_p0_contract.py
```

## 13. Contract closure state

```text
TASK=V09_P0_VERSION_CONTRACT_DEFINITION_R1
AUTHORIZED_CONTRACT_PATH=docs/tasks/V0_9-P0-version-contract.md
V09_P0_CONTRACT_FROZEN=YES
V09_P0_IMPLEMENTATION_AUTHORIZED=YES
V09_P0_CONTRACT_EXECUTED=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
DRAFT=YES
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 14. Revision history

| Rev | Date | Change |
| --- | --- | --- |
| R1 | 2026-08-27 | Initial V0.9 P0 freeze at `0dc8de5` / `v0.8.0` |
