# V0.8 P0 Operator-Minimal Process Input Contract

**Status:** Definition freeze R1 — V0.8 identity, operator five-KEY surface, assembler/lineage rules
**Authority:** Contract document is the freeze authority until a GitHub umbrella issue is created
**Contract definition source SHA:** `0330d9be36db94a62190d5775612b361fff6da8d`
**Contract definition source tree:** `7bfcb0dcd88390ec196f67290a5e1cf363703c16`
**Previous release:** `v0.7.0`
**Target branch:** `cursor/v08-p0-operator-minimal-input-6c68`

This document freezes the V0.8 P0 **operator-minimal process-input contract**
only. It does not authorize P1–P4 implementation, formula recut, coefficient
promotion, live Aily enablement, tag publication, or Release.

Companion ADR: `docs/architecture/ADR-028-operator-minimal-process-input.md`.

## 0. Contract identity and governance

```text
TASK=V08_P0_OPERATOR_MINIMAL_INPUT_CONTRACT_DEFINITION_R1
PARENT_ISSUE=PENDING
P0_TRACKING_ISSUE=PENDING
DISPATCH_ISSUE=PENDING
GOVERNANCE_OWNER=V0.8
BASE_MAIN_SHA=0330d9be36db94a62190d5775612b361fff6da8d
BASE_TREE=7bfcb0dcd88390ec196f67290a5e1cf363703c16
PREVIOUS_RELEASE=v0.7.0
TARGET_BRANCH=cursor/v08-p0-operator-minimal-input-6c68
TARGET_FILE=docs/tasks/V0_8-P0-operator-minimal-input-contract.md
TARGET_PR_STATE=DRAFT

CONTRACT_STATUS=DEFINITION_R1_DRAFT_FOR_INDEPENDENT_REVIEW
V08_P0_IMPLEMENTATION_AUTHORIZED=YES
V08_P1_IMPLEMENTATION_AUTHORIZED=NO
V08_P2_IMPLEMENTATION_AUTHORIZED=NO
V08_P3_IMPLEMENTATION_AUTHORIZED=NO
V08_P4_IMPLEMENTATION_AUTHORIZED=NO
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

P0 freezes version identity, the operator-visible five KEY leaves, leaf-source
split (user / persisted lineage / explicit catalog), package DAG, and
allowlists. P0 does **not** change application behavior.

## 1. Objective and non-goals

### 1.1 Objective

V0.8 is an **operator input-surface recut**, not a calculator rewrite and not
a trust-loop replay of V0.7.

On unmodified `create_app`, an operator supplies only plant-level process
quantities. Application code expands that into `EngineeringInputBundleV1`.
The canonical five-stage chain still runs, persists, and remains reviewable:

```text
OperatorProcessInputV1 (five KEY leaves)
 → application assembler (catalog leaves + identity)
 → five-stage-execution
 → lineage bind of typed upstream results
 → production scheme-run / report / review / formal export (already delivered at v0.7.0)
```

Judgement for V0.8 is **not** “more engineering fields”. It is:

- operator types only the five KEY process leaves;
- Vue does not duplicate downstream KEY forms or formulas;
- every non-user KEY leaf is either persisted upstream lineage or an explicit
  demo/coefficient catalog leaf with provenance;
- missing operator KEY still fail-closes;
- catalog holes and lineage mismatches still fail-close;
- demo catalog leaves stay unverified and `requires_review=true`;
- V0.5/V0.6/V0.7 full-bundle tests keep their assertion bodies.

### 1.2 Non-goals (hard boundaries)

```text
V08_P1_IMPLEMENTATION_AUTHORIZED=NO
V08_P2_IMPLEMENTATION_AUTHORIZED=NO
V08_P3_IMPLEMENTATION_AUTHORIZED=NO
V08_P4_IMPLEMENTATION_AUTHORIZED=NO
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
V05_V06_V07_TEST_ASSERTION_MUTATION=NO
V07_SAMPLE_LOADER_MUTATION=NO
```

P0 must not:

- implement the assembler, change `five_stage_execution.py`, or shrink Vue;
- add migrations or change calculator formulas;
- promote or choose between conflicting demo coefficient values (E1–E8);
- copy zone plan area into cooling envelope leaves without catalog/lineage
  rules in §3;
- delete the V0.4 `planning-run` page (label leftover; do not make it
  V0.8 authority);
- reopen V0.7 trust-loop delivery as unfinished;
- claim production RBAC or live Aily.

## 2. Frozen inherited contracts

V0.8 inherits and must not recut except the operator-visible surface in §3:

| Frozen item | Authority |
| --- | --- |
| Stage order `zone → cooling_load → equipment → power → investment` | `ORCHESTRATION_STAGE_ORDER` |
| Canonical identities `cold_room_zone_plan`, `cooling_load`, `equipment`, `installed_power`, `investment_estimate` | `CALCULATOR_BINDINGS` |
| `power_configuration` supplemental only | `SUPPLEMENTAL_ONLY_CALCULATOR_NAMES` |
| Five-row report source mapping | V0.6 P0 + delivered V0.6 P1 / V0.7 |
| Reports MUST NOT recalculate formulas | V0.6 P0 §3.4 |
| `FORMAL_EXPORT_STATUSES`, trusted `mark_reviewed` TestClient seam | V0.6 / V0.7 |
| SQLite / PostgreSQL parity of contract meaning | inherited |
| Aily live implementation | `AILY_LIVE_IMPLEMENTATION=NO` (V0.7 P6) |
| Full `EngineeringInputBundleV1` as execution authority | V0.5 P0; V0.8 assembler writes it |

Inherited report source mapping (do not recut):

| Persisted calculator | `OrchestratedCalculationResult` attr | Report JSON section key |
| --- | --- | --- |
| `cold_room_zone_plan` | `throughput_result` | `throughput_inventory_area` |
| `cooling_load` | `cooling_load_result` | `cooling_load` |
| `equipment` | `equipment_result` | `equipment_selection` |
| `installed_power` | `power_result` | `electrical_and_energy` |
| `investment_estimate` | `investment_result` | `investment_estimate` |

## 3. Operator-minimal input surface

### 3.1 `OperatorProcessInputV1`

Operator-visible KEY leaves (exactly these five):

```text
zone_planning_inputs.daily_inbound_mass_kg     unit=kg/day
zone_planning_inputs.working_time_h_per_day    unit=h/day
zone_planning_inputs.finished_storage_days     unit=day
zone_planning_inputs.packaging_storage_days    unit=day
zone_planning_inputs.precooling_required_ratio unit=ratio
```

Workbench supplies `project_version_identity` from the bound project version.
That identity is not an engineering value the operator types.

Schema identity (frozen name only; P1 publishes JSON):

```text
schema_id: OperatorProcessInputV1
schema_version: 1.0.0
```

### 3.2 Leaf-source split

| Class | Leaves | `source_type` | When bound |
| --- | --- | --- | --- |
| Operator KEY | The five process quantities | `user` | Submit |
| Zone remainder of `ColdRoomZonePlanInput` | Existing demo/dataclass fields already used when the five KEY are present | `demo` / `coefficient` | Assembler copies into bundle/snapshot provenance; does not recut the zone calculator |
| Cooling identity + plan area | `zone_code`, `zone_name`, `temperature_level`, `zone_area`, `floor_area` from persisted zone-plan zones | `persisted` | After zone stage |
| Cooling envelope / thermal KEY not produced by zone plan | height, wall/roof area, U-values, design temperatures, product thermal KEY | `demo` / `coefficient` | Assembler writes explicit catalog leaves before cooling stage |
| Equipment grouping | systems/zones from zone-plan temperature grouping | `persisted` identity; catalog for counts/defrost/temperatures | After zone (identity) / catalog (counts) |
| Equipment `design_cooling_load_kw_r` | cooling-load result | `persisted` | After cooling_load stage |
| Installed-power compressor KEY | equipment result electrical compressor input | `persisted` | After equipment stage |
| Installed-power remaining KEY | catalog if equipment result lacks the typed leaf | `demo` / `coefficient` | Before power stage if not lineage-bound |
| Investment KEY | zone + power typed results (existing lineage) | `persisted` | After zone and power stages |

### 3.3 V0.5 auto-feed amendment (operator-minimal path only)

```text
OPERATOR_PROCESS_INPUT_FIVE_KEY_LEAVES_ONLY=YES
ZONE_RESULT_TO_COOLING_LOAD_IDENTITY_AND_PLAN_AREA_LINEAGE=YES
ZONE_RESULT_TO_COOLING_LOAD_ENVELOPE_AUTO_FEED=NO
PERSISTED_UPSTREAM_RESULT_TO_DOWNSTREAM_TYPED_INPUT=YES
DEMO_CATALOG_TO_EXPLICIT_BUNDLE_LEAF=YES
DEMO_DEFAULT_TO_AUTHORITATIVE_INPUT_WITHOUT_BUNDLE_LEAF=NO
POWER_CONFIGURATION_TO_INSTALLED_POWER_AUTO_FEED=NO
AGENT_TO_ENGINEERING_VALUE=NO
```

Full-bundle compatibility path (existing tests posting complete
`EngineeringInputBundleV1`) keeps V0.5 fail-closed KEY rules.

### 3.4 Fail-closed

```text
MISSING_OPERATOR_PROCESS_KEY_LEAF → MISSING_ENGINEERING_PARAMETER
MISSING_CATALOG_LEAF_FOR_REQUIRED_DOWNSTREAM_KEY → MISSING_ENGINEERING_PARAMETER
LINEAGE_TYPE_OR_ZONE_CODE_MISMATCH → UPSTREAM_LINEAGE_BIND_FAILED
CALCULATOR_SILENT_DEFAULT_AS_NEW_AUTHORITY → FORBIDDEN
```

### 3.5 Frontend rule

V0.8 operator **工程输入** page MUST present only the five KEY leaves plus
submit. It MUST NOT present cooling-zone geometry, equipment systems,
installed-power components, investment quantities, or coefficient IDs as
operator KEY. Coefficient/catalog provenance is displayed as review metadata,
not as a second engineering keypad.

The V0.4 基本信息 / `planning-run` page remains leftover and MUST stay labeled
as non-authority.

## 4. Known remaining gaps at `v0.7.0`

Record only; P0 does not fix.

| ID | Gap | Evidence at `BASE_MAIN_SHA` |
| --- | --- | --- |
| V08-GAP-001 | Operator 工程输入 form requires the full bundle KEY surface | `EngineeringInputBundleForm.vue`; `engineeringInputForm.ts` |
| V08-GAP-002 | Bundle KEY validation runs before lineage bind, so downstream KEY must be typed at submit | `engineering_input_bundle.py`; `five_stage_execution.py` `LineageAwareCalculatorPort` |
| V08-GAP-003 | Cooling envelope/thermal KEY have no operator-minimal source except an unwired demo catalog | V0.5 `ZONE_RESULT_TO_COOLING_LOAD_GEOMETRY_AUTO_FEED=NO`; `ZoneCoolingLoadInput` |
| V08-GAP-004 | Installed-power KEY are operator-typed; equipment result already exposes compressor electrical input | `installed_power_inputs`; equipment `total_compressor_input_power_kw_e` |
| V08-GAP-005 | 基本信息 page still looks like the primary operator form | `ProjectPage.vue` V0.4 `planning-run` badge |
| V07-GAP-004 | Coefficient metadata can diverge from effective calculator inputs | carried forward; E1–E8 stay `KNOWN_CONFLICT` |
| V07-GAP-006 | Complete bundle is not the default immutable snapshot on every path | carried forward; assembler must persist the expanded bundle |
| V07-GAP-007 | Registry seed vs embedded calculator coefficients remain dual-track | carried forward; assembler must not merge tracks |
| V07-GAP-010 | Demo coefficient conflicts stay `requires_review=true` | carried forward |

Delivered at `v0.7.0` and must not be reopened as V0.8 umbrellas:
operator `project_summary`, `POST .../production-scheme-runs`, consumer
`result_hash` alignment (V07-GAP-005 production path), Aily **boundary**
(not live), P7 trust-loop controlled acceptance.

## 5. Package DAG

```text
P0 → P1 → (P2 || P3) → P4
```

| Edge | Reason |
| --- | --- |
| P0 → all | Frozen operator-minimal contract required |
| P1 → P2 | Frontend may only submit the compact operator payload after assembler exists |
| P1 → P3 | Sample/runbook must call the assembler path, not a hand-built full bundle |
| P2 + P3 → P4 | Controlled acceptance needs UI + sample on unmodified `create_app` |

P4 MUST NOT mutate P1–P3 production code. P4 does not authorize tag or Release.

## 6. Package ownership and exclusive allowlists

**Global forbidden for every V0.8 package unless a later authorized
contract amendment names it:**

```text
V08_GLOBAL_FORBIDDEN
backend/src/cold_storage/modules/calculations/domain/**
docs/tasks/V0_7-*
docs/tasks/V0_6-*
docs/tasks/V0_5-*
docs/tasks/V0_4-*
docs/tasks/V0_3-*
backend/src/cold_storage/bootstrap/v07_sample_loader.py
backend/src/cold_storage/bootstrap/v06_sample_loader.py
```

Calculator formula files are forbidden. Any calculator behavior change
requires a separate FX package with `FORMULA_RECUT_AUTHORIZED=YES`.

Do not edit `test_v05_*`, `test_v06_*`, or `test_v07_*` assertion bodies.

### 6.1 P0 exclusive allowlist (this package)

```text
V08_P0_FILE_ALLOWLIST
docs/tasks/V0_8-P0-operator-minimal-input-contract.md
docs/architecture/ADR-028-operator-minimal-process-input.md
docs/audit/current-state.md
docs/audit/gap-analysis.md
docs/audit/validation-baseline.md
docs/TECH_DEBT.md
docs/roadmap/DEVELOPMENT_PLAN.md
backend/tests/architecture/test_v08_p0_contract.py
```

### 6.2 P1 exclusive allowlist (assembler + lineage timing)

Objective: expand `OperatorProcessInputV1` into `EngineeringInputBundleV1` in
the application layer; validate KEY after assembly; bind typed upstream
results at execution time. Copy existing catalog/demo authority into explicit
leaves. Do not invent numbers. Do not edit Vue.

```text
V08_P1_FILE_ALLOWLIST
docs/tasks/V0_8-P1-process-input-assembler-contract.md
backend/src/cold_storage/modules/projects/application/operator_process_input.py
backend/src/cold_storage/modules/projects/application/engineering_input_bundle.py
backend/src/cold_storage/modules/projects/application/five_stage_execution.py
backend/src/cold_storage/bootstrap/app.py
backend/tests/architecture/test_v08_p1_operator_process_input_contract.py
backend/tests/unit/test_v08_p1_operator_process_input_assembler.py
backend/tests/integration/test_v08_p1_five_field_execution_sqlite.py
backend/tests/integration/test_v08_p1_five_field_execution_postgresql.py
```

`bootstrap/app.py` may only accept the compact operator payload and pass it to
the application assembler. It MUST NOT contain engineering formulas or catalog
numeric literals.

### 6.3 P2 exclusive allowlist (operator workbench)

Objective: 工程输入 shows only the five KEY leaves and submits
`OperatorProcessInputV1`. Keep the V0.4 基本信息 page labeled leftover.

```text
V08_P2_FILE_ALLOWLIST
docs/tasks/V0_8-P2-operator-workbench-contract.md
frontend/src/features/five-stage/components/EngineeringInputBundleForm.vue
frontend/src/features/five-stage/components/EngineeringInputsPage.vue
frontend/src/features/five-stage/model/engineeringInputForm.ts
frontend/src/stores/fiveStageExecution.ts
frontend/src/features/five-stage/api/fiveStageApi.ts
frontend/src/api/contracts/fiveStage.ts
frontend/src/features/project/components/ProjectPage.vue
frontend/src/features/five-stage/architecture/test_v08_p2_five_key_operator_form.test.ts
```

Vue MUST NOT compute engineering values or copy catalog numbers into KEY
leaves.

### 6.4 P3 exclusive allowlist (sample and runbook)

```text
V08_P3_FILE_ALLOWLIST
docs/tasks/V0_8-P3-operator-sample-runbook-contract.md
samples/v08-process-input/**
backend/src/cold_storage/bootstrap/v08_sample_loader.py
docs/runbooks/v08-process-input-runbook.md
Makefile
backend/tests/integration/v08_p3_operator_fixtures.py
backend/tests/integration/test_v08_p3_operator_sample_sqlite.py
backend/tests/integration/test_v08_p3_operator_sample_postgresql.py
```

Do not mutate `v07_sample_loader.py` or `samples/v07-trust-loop/**`.

### 6.5 P4 exclusive allowlist (controlled acceptance)

```text
V08_P4_FILE_ALLOWLIST
docs/tasks/V0_8-P4-controlled-acceptance-contract.md
backend/tests/integration/test_v08_p4_controlled_acceptance_sqlite.py
backend/tests/integration/test_v08_p4_controlled_acceptance_postgresql.py
```

P4 proves the five-KEY operator path on unmodified `create_app` for SQLite and
PostgreSQL. P4 does not own `Makefile` (P3 does). P4 does not authorize tag,
Release, or issue closure via `gh`.

## 7. Expert decisions developers must not guess

V0.8 inherits V0.7 P0 E1–E8 as `KNOWN_CONFLICT` / `non_consumer`. The
assembler may **copy existing demo/dataclass authority into explicit leaves**
with `requires_review=true`. It MUST NOT pick a winning value for:

| ID | Decision |
| --- | --- |
| E1 | `frozen_fruit_ratio` Input vs `DemoZoneCoefficient` |
| E2 | `frozen_storage_days` Input vs `DemoZoneCoefficient` |
| E3 | `storage_position_capacity_kg` Input vs `DemoZoneCoefficient` |
| E4 | `packaging_storage_days` legacy fallback vs KEY path |
| E5 | `precooling_required_ratio` legacy fallback vs KEY path |
| E6 | Investment registry ratio semantic vs embedded power-distribution unit |
| E7 | Which coefficient seed is runtime authority |
| E8 | `raw_holding_hours` provided but unused by zone formula |

E9–E11 (formal-export blocker, Feishu identity, Aily live fields) remain
out of V0.8.

## 8. Issue mapping

| Issue | Status at P0 freeze | V0.8 note |
| --- | --- | --- |
| #11 / #13 / #17 / #176 | CLOSED (human, 2026-08-26, after `v0.7.0`) | Do not reopen as V0.8 umbrellas |
| #20 | CLOSED (2026-07-22) | Do not reopen |

GitHub umbrella/tracking issues for V0.8 are `PARENT_ISSUE=PENDING` until
created.

## 9. Authorization boundaries

```text
V08_P0_IMPLEMENTATION_DISPATCH_AUTHORIZED=YES
V08_P1_IMPLEMENTATION_AUTHORIZED=NO
V08_P2_IMPLEMENTATION_AUTHORIZED=NO
V08_P3_IMPLEMENTATION_AUTHORIZED=NO
V08_P4_IMPLEMENTATION_AUTHORIZED=NO
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
docs/tasks/V0_7-*
docs/tasks/V0_6-*
docs/tasks/V0_5-*
docs/tasks/V0_4-*
docs/tasks/V0_3-*
```

ADR-028 is listed on the P0 allowlist as the architecture record of this
recut.

## 10. Global V0.8 acceptance gate (release later, not P0)

P4 completion may **propose** `v0.8.0`; P0/P4 do not authorize tag.

```text
V08_P0_CONTRACT_FROZEN=PASS
V08_PACKAGE_DAG_FROZEN=PASS
V08_ALLOWLISTS_DISJOINT=PASS
OPERATOR_FIVE_KEY_LEAVES_ONLY=PASS
ASSEMBLER_NOT_VUE=PASS
LINEAGE_OR_CATALOG_FOR_DOWNSTREAM_KEY=PASS
MISSING_OPERATOR_KEY_FAIL_CLOSED=PASS
DEMO_CATALOG_LEAVES_REQUIRE_REVIEW=PASS
FULL_BUNDLE_COMPAT_PRESERVED=PASS
FORMULA_RECUT=NO
COEFFICIENT_PROMOTION=NO
AILY_LIVE_IMPL=NO
TAG_PUBLICATION_AUTHORIZED=NO
```

## 11. P0 acceptance criteria

V0.8 P0 R1 is complete when:

```text
P0_CONTRACT_EXISTS=PASS
ADR_028_EXISTS=PASS
ORCHESTRATION_STAGE_ORDER_FROZEN=PASS
CALCULATOR_BINDINGS_FROZEN=PASS
POWER_CONFIGURATION_NOT_CANONICAL=PASS
V08_GAPS_RECORDED=PASS
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
backend/tests/architecture/test_v08_p0_contract.py
```

## 12. Contract closure state

```text
TASK=V08_P0_OPERATOR_MINIMAL_INPUT_CONTRACT_DEFINITION_R1
AUTHORIZED_CONTRACT_PATH=docs/tasks/V0_8-P0-operator-minimal-input-contract.md
V08_P0_CONTRACT_FROZEN=YES
V08_P0_IMPLEMENTATION_AUTHORIZED=YES
V08_P0_CONTRACT_EXECUTED=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
DRAFT=YES
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 13. Revision history

| Rev | Date | Change |
| --- | --- | --- |
| R1 | 2026-08-26 | Initial V0.8 P0 freeze at `0330d9b` / `v0.7.0` |
