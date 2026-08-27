# POST-V0.9 P2 — Five-Stage Persisted Result Display

**Status:** Implementation authorized — calculations workbench shows each stage  
**Authority:** Charles `可以派发` 2026-08-27: after five KEY submit, every stage
must show calculation results  
**Parent on `main`:** `c6f806575a3d100bd00ef22aa7600f3c7109c7ee`  
**Target branch:** `cursor/post-v09-p2-stage-result-display-6c68`

This package implements **P2 only**: the **计算结果** page reads persisted
five-stage snapshots and shows numbers for **all five** canonical stages.
It does not hide 基本信息 (P1). It does not recut report JSON (P3).
It does not recalculate formulas in Vue.

Sibling packages (do not implement here):

- P1: `docs/tasks/POST_V09-P1-hide-planning-run-nav-contract.md`
- P3: `docs/tasks/POST_V09-P3-report-calculation-logic-contract.md`

## 0. Contract identity and governance

```text
TASK=POST_V09_P2_STAGE_RESULT_DISPLAY_R1
GOVERNANCE_OWNER=POST-V0.9
BASE_MAIN_SHA=c6f806575a3d100bd00ef22aa7600f3c7109c7ee
BASE_SUBJECT=Align workbench workflow guidance with V0.9 five KEY. (#223)
PREVIOUS_RELEASE=v0.9.0
TARGET_BRANCH=cursor/post-v09-p2-stage-result-display-6c68
TARGET_FILE=docs/tasks/POST_V09-P2-stage-result-display-contract.md
TARGET_PR_STATE=DRAFT

POST_V09_P2_IMPLEMENTATION_AUTHORIZED=YES
POST_V09_P1_IMPLEMENTATION_AUTHORIZED=NO
POST_V09_P3_IMPLEMENTATION_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT=NO
VUE_ENGINEERING_FORMULAS=NO
AILY_LIVE_IMPLEMENTATION=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
CHARLES_POST_V09_P2_LIVING_TEST_UPDATE_AUTHORIZED=YES
```

## 1. Objective

Today 计算结果 shows the zone table plus four summary cards, while the
five-stage progress panel only prints `calculation_id` / `result_hash`.
Cold-load, equipment, power, and investment numbers are already persisted.

After five-stage execution, an operator on **计算结果** must see **results**
for:

| Stage | Calculator | Already shown? |
| --- | --- | --- |
| 区域规划 | `cold_room_zone_plan` | Yes (P3 zone table). Keep it. |
| 冷负荷 | `cooling_load` | No — add a result table |
| 设备选型 | `equipment` | No — add a result table |
| 装机功率 | `installed_power` | Only a total on 用电配置. Also show here. |
| 投资估算 | `investment_estimate` | Only on 投资估算. Also show here. |

Vue **reads** persisted fields. Missing fields render as omitted / em dash.
Do not invent `0` as a substitute for absence (same rule as V0.9 P3).

## 2. Snapshot shapes (pass-through only)

GET `.../calculations` rows already include `result_snapshot` and `formulas`.
`result_snapshot` may be either the inner payload **or** wrap it under
`.result` (V0.9 P6 fixtures accept both). Reuse that dual-read.

Read payload from `result_snapshot.result` when that is a dict, else from
`result_snapshot` itself.

### 2.1 `cooling_load`

Show whenever the cooling slot record exists. Pass through when present:

```text
total_cooling_load_kw
safety_margin_load_kw
envelope_heat_transfer_load_kw
product_sensible_heat_load_kw
packaging_load_kw
infiltration_load_kw
personnel_load_kw
lighting_load_kw
evaporator_fan_load_kw
defrost_additional_load_kw
other_configuration_load_kw
```

If `zones` / `zone_loads` / `level_summaries` is a persisted array, list
rows as persisted objects (label + numeric fields present on each row).
Do not compute totals from zone rows in Vue.

Unit copy: kW(r) for these loads. Formatting `toFixed` is allowed.

### 2.2 `equipment`

```text
evaporator_total_cooling_capacity_kw
evaporator_quantity
single_evaporator_capacity_kw
compressor_operating_capacity_kw
standby_capacity_kw
condenser_heat_rejection_capacity_kw
evaporation_temperature_c
condensing_temperature_c
defrost_method
```

If `systems` is a persisted array, list it. Do not derive capacities.

### 2.3 `installed_power`

```text
total_installed_power_kw_e
total_estimated_demand_kw
equipment_rows[]  (name, quantity, running_power_kw, total_power_kw, … as persisted)
summary_rows[]
items[]
```

Do not use V0.4 `power_configuration` as the canonical table on 计算结果.
If only `power_configuration` exists, keep the existing progress-panel
supplemental note; do not treat it as `installed_power`.

### 2.4 `investment_estimate`

```text
total_investment_cny
items[].item_name
items[].amount_cny
```

Display 万元 with the same formatting as `InvestmentPage` (`value / 10000`).
That division is display formatting, not an engineering formula.

### 2.5 Zone

Do not regress V0.9 P3 `ZoneResultsTable` (schemes, n_need, docks,
8-position caption). P2 must not strip those fields.

## 3. Progress panel versus result tables

Keep `FiveStageProgressPanel` status tags (缺失 / 已持久化 / …).

Add **result tables** on `CalculationsPage` for cooling / equipment / power /
investment. Either:

- new presentational components next to `ZoneResultsTable`, or
- a single `StageResultPanel` that switches on `slot.stage`

Do not replace the zone table with hashes.

When a canonical slot is missing: that stage's table shows empty copy
「本阶段尚无持久化结果」, not fabricated zeros.

When present: also pass through `record.formulas` when it is a non-empty
array of `{formula_id, formula_version, expression, description}` (or the
same keys under `result_snapshot`). Render as a read-only list. If formulas
are absent, omit the list — do not write expressions in Vue.

`record.assumptions` / `record.warnings` may be listed when present.

## 4. Mapper / types

`CalculationResultSnapshot` currently omits `formulas` / `steps`. The run
record already has `formulas?: unknown[]`. Tighten that to an optional
typed array. Do not require `steps` on the run record in this package
(P3 owns report projection of steps).

Do not edit backend snapshot models (`extra="forbid"`). Do not bump
calculator `VERSION` strings. Do not edit `zone_planning.py` or cooling /
equipment / power / investment formula modules.

## 5. Exclusive allowlist

```text
POST_V09_P2_FILE_ALLOWLIST
docs/tasks/POST_V09-P2-stage-result-display-contract.md
backend/tests/architecture/test_post_v09_p2_stage_result_display_contract.py
frontend/src/features/calculations/components/CalculationsPage.vue
frontend/src/features/calculations/components/CalculationSummary.vue
frontend/src/features/five-stage/components/FiveStageProgressPanel.vue
frontend/src/api/contracts/calculations.ts
frontend/src/features/calculations/model/mapPersistedCalculations.ts
frontend/src/features/calculations/model/mapPersistedCalculations.test.ts
frontend/src/features/five-stage/model/mapFiveStageCalculations.ts
frontend/src/features/five-stage/model/fiveStageModel.test.ts
frontend/src/features/calculations/components/CoolingLoadResultsTable.vue
frontend/src/features/calculations/components/CoolingLoadResultsTable.test.ts
frontend/src/features/calculations/components/EquipmentResultsTable.vue
frontend/src/features/calculations/components/EquipmentResultsTable.test.ts
frontend/src/features/calculations/components/InstalledPowerResultsTable.vue
frontend/src/features/calculations/components/InstalledPowerResultsTable.test.ts
frontend/src/features/calculations/components/InvestmentResultsTable.vue
frontend/src/features/calculations/components/InvestmentResultsTable.test.ts
frontend/src/features/calculations/architecture/test_post_v09_p2_stage_result_display.test.ts
```

New `*ResultsTable.vue` names are the expected split. If the implementer
uses one shared panel component instead, replace those four pairs in
**both** this fence and the architecture test tuple in the same commit.
Do not add files outside this list.

Forbidden: `WorkbenchLayout.vue`, `router.ts`, `workbench.test.ts` (P1),
report assembler/schema/templates (P3), `ZoneResultsTable.vue` unless a
compile error requires a type-only import, formula Python, Alembic, live Aily.

`CHARLES_POST_V09_P2_LIVING_TEST_UPDATE_AUTHORIZED=YES` applies only to
tests on this allowlist (including existing `mapPersistedCalculations.test.ts`
and `fiveStageModel.test.ts`).

## 6. Vue formula file-scan

P2 Vue/TS files MUST NOT contain engineering arithmetic that produces
loads, capacities, areas, or money. Allowed: `toFixed`, kg vs t display,
万元 `/ 10000` for investment copy, em dash, reading persisted numbers.

Forbidden patterns (file-scan on P2 Vue/TS allowlist files): `Math.ceil`,
`Math.floor` used on engineering values, `n ×` room formulas, hardcoded
`1.56` class coefficients.

## 7. Acceptance criteria

```text
P2-AC-01 After five-stage records exist, CalculationsPage shows zone + cooling + equipment + power + investment result blocks
P2-AC-02 Missing stage: empty copy, no fabricated zeros
P2-AC-03 Zone P3 fields still render (schemes / n_need / docks)
P2-AC-04 power_configuration is not the canonical power table
P2-AC-05 formulas[] rendered only when persisted; no Vue-authored expressions
P2-AC-06 File-scan: no Vue engineering formulas
P2-AC-07 Architecture allowlist vs origin/main on this branch
```

## 8. Not in P2

- Hiding 基本信息 (P1)
- Report JSON / Word/PDF calculation_logic (P3)
- Auto production-scheme-run
- Recutting calculator formulas
- InvestmentPage / PowerPage recut (they already read persisted rows;
  empty-copy 基本信息 is P1)
- Merge, tag, Release

## 9. Rollback

Revert this PR. 计算结果 returns to zone table + hash progress panel.

## Revision history

| Rev | Date | Notes |
| --- | --- | --- |
| R1 | 2026-08-27 | Charles 可以派发: each stage shows persisted results |
