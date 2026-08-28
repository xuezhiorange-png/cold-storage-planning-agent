# POST-V0.9 P5 — Operator Result Tables

**Status:** Implementation authorized — Charles `可以派发` 2026-08-28  
**Authority:** 结果展示改用表格，直观一点  
**Parent on `main`:** `d6c3af953d0d8486fd5762e5797ecd336f44fbf2`  
**Target branch:** `cursor/post-v09-p5-result-tables-6c68`

计算结果 must show **Chinese tables**, not English JSON keys, definition
lists of English field names, or `calculation_id` / `result_hash` as the
primary view. Vue **reads** persisted fields. No engineering arithmetic.

Sibling packages (do not implement here):

- P4 zone area recut
- P6 report Word/PDF composition
- P7 scheme-button enablement / sidebar copy
- P8 workbench visual polish (shell, nav, form chrome)

## 0. Governance

```text
TASK=POST_V09_P5_RESULT_TABLES_R1
GOVERNANCE_OWNER=POST-V0.9
BASE_MAIN_SHA=d6c3af953d0d8486fd5762e5797ecd336f44fbf2
PREVIOUS_RELEASE=v0.9.0
TARGET_BRANCH=cursor/post-v09-p5-result-tables-6c68
TARGET_FILE=docs/tasks/POST_V09-P5-result-tables-contract.md
TARGET_PR_STATE=DRAFT

POST_V09_P5_IMPLEMENTATION_AUTHORIZED=YES
FORMULA_RECUT_AUTHORIZED=NO
VUE_ENGINEERING_FORMULAS=NO
AILY_LIVE_IMPLEMENTATION=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
CHARLES_POST_V09_P5_LIVING_TEST_UPDATE_AUTHORIZED=YES
```

## 1. Objective

On **计算结果**:

1. Scalar results (冷负荷分项、设备标量、功率合计) render as a table
   with columns **项目 / 数值 / 单位**, Chinese labels.
2. Array results (zones / zone_loads / systems / equipment_rows /
   summary_rows / items) render as tables with a **whitelist of Chinese
   column headers**. Do not use `Object.keys` as `<th>`.
3. Unknown nested objects, hashes, and English codes are omitted from
   the main table (not shown as `[object Object]`).
4. 公式 / 假设 / 警告 go under a collapsed **计算依据** `<details>`,
   not the first screen.
5. `FiveStageProgressPanel` operator view: stage Chinese name + 已持久化/
   缺失 / 待复核. Do **not** show `calculation_id`, `result_hash`,
   `requires_review: true` as the primary body. Hash/id may live inside
   `<details>`.
6. Calculations page titles: **装机功率结果** — drop `(installed_power)`
   and `(equipment_rows)` style English.

Zone table: keep Chinese zone names; translate aisle/scheme labels
(`three_side_3m` → 三面通道, `6_position` → 6位间). Keep the substring
`6位汇报` in the zone table source (existing P3 arch test).

Missing persisted fields: em dash / omit. Do not invent `0`.

## 2. Exclusive allowlist

```text
POST_V09_P5_FILE_ALLOWLIST
docs/tasks/POST_V09-P5-result-tables-contract.md
backend/tests/architecture/test_post_v09_p5_result_tables_contract.py
frontend/src/features/calculations/components/persistedResultLabels.ts
frontend/src/features/calculations/components/PersistedScalarResultsTable.vue
frontend/src/features/calculations/components/PersistedArrayResultsTable.vue
frontend/src/features/calculations/components/CalculationBasisDetails.vue
frontend/src/features/calculations/components/CalculationsPage.vue
frontend/src/features/calculations/components/ZoneResultsTable.vue
frontend/src/features/calculations/components/ZoneResultsTable.test.ts
frontend/src/features/calculations/components/CoolingLoadResultsTable.vue
frontend/src/features/calculations/components/CoolingLoadResultsTable.test.ts
frontend/src/features/calculations/components/EquipmentResultsTable.vue
frontend/src/features/calculations/components/EquipmentResultsTable.test.ts
frontend/src/features/calculations/components/InstalledPowerResultsTable.vue
frontend/src/features/calculations/components/InstalledPowerResultsTable.test.ts
frontend/src/features/calculations/components/InvestmentResultsTable.vue
frontend/src/features/calculations/components/InvestmentResultsTable.test.ts
frontend/src/features/five-stage/components/FiveStageProgressPanel.vue
frontend/src/features/calculations/architecture/test_post_v09_p2_stage_result_display.test.ts
frontend/src/features/calculations/architecture/test_v09_p3_zone_result_display.test.ts
frontend/src/features/calculations/architecture/test_post_v09_p5_result_tables.test.ts
```

New small presentational Vue files under
`frontend/src/features/calculations/components/` (shared table chrome
used only by these result tables) may be added and must be appended to
this allowlist in the same PR. Do not put labels in `utils.py` /
`helpers.ts` dumping-ground files.

## 3. Out of scope

- AppShell / WorkbenchLayout / engineering-input chrome (P8)
- ProductionSchemeRunPanel enablement (P7)
- Report assembler / Word (P6)
- zone_planning.py (P4)
