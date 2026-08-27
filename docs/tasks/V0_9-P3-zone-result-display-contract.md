# V0.9 P3 — Zone Result Display Contract

**Status:** Implementation R1 — calculations UI reads persisted P2 zone fields  
**Authority:** `docs/tasks/V0_9-P0-version-contract.md` §4, §7.4, V09-E6; ADR-029 §5; version-plan §3 item 5  
**Parent:** P0 #213 + P1 #216 + P2 #217 on `main`  
**Previous release:** `v0.8.0`  
**Target branch:** `cursor/v09-p3-zone-result-display-6c68`

This package implements **P3 only**: the calculations workbench displays
persisted `cold_room_zone_plan` layout/scheme/dock fields. It does not
recalculate area, positions, or docks. It does not authorize merge, tag,
Release, P6, or P7.

Companion documents:

- Overall plan: `docs/tasks/V0_9-version-plan.md`
- P0 contract (allowlist reference): `docs/tasks/V0_9-P0-version-contract.md`
- P2 formula recut (already on `main`): `docs/tasks/V0_9-P2-zone-formula-recut-contract.md`

## 0. Contract identity and governance

```text
TASK=V09_P3_ZONE_RESULT_DISPLAY_R1
PARENT_ISSUE=213
PARENT_CONTRACT=docs/tasks/V0_9-P0-version-contract.md
GOVERNANCE_OWNER=V0.9
BASE_MAIN_SHA=808cbfd755ae85d5f7795baaa2987fb497698ab2
BASE_TREE=b4273cdcc1dc1e807082a94611c0a4aab317da1f
BASE_SUBJECT=V0.9 P2: recut zone planner to version-plan §4 (#217)
PREVIOUS_RELEASE=v0.8.0
TARGET_BRANCH=cursor/v09-p3-zone-result-display-6c68
TARGET_FILE=docs/tasks/V0_9-P3-zone-result-display-contract.md
TARGET_PR_STATE=DRAFT

V09_P3_IMPLEMENTATION_AUTHORIZED=YES
V09_P1_IMPLEMENTATION_AUTHORIZED=NO
V09_P2_IMPLEMENTATION_AUTHORIZED=NO
V09_P4_IMPLEMENTATION_AUTHORIZED=NO
V09_P5_IMPLEMENTATION_AUTHORIZED=NO
V09_P6_IMPLEMENTATION_AUTHORIZED=NO
V09_P7_IMPLEMENTATION_AUTHORIZED=NO
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
```

P0 may still record `V09_P3_IMPLEMENTATION_AUTHORIZED=NO`. This file
overrides that for the zone-result-display package only. Do not edit P0.

## 1. Objective

Close **V09-GAP-003** (zone table is little more than an area number) and
**V09-GAP-007** (calculations empty-state still tells operators to fill
`EngineeringInputBundleV1`).

On the calculations workbench, after five-stage execution, Vue **reads**
persisted zone snapshot fields:

- dual precooling schemes (6-position and 8-position);
- packed need vs actual positions (`n_need` / `n_actual` / unused cells);
- shipping-channel dock counts (`pallet_count` / `truck_count` /
  `platform_count`).

Vue MUST NOT compute those values. Missing persisted fields render as
omitted / em dash. Do not invent substitutes.

V09-E6: dual precooling schemes always persist; UI must not collapse to
one area.

## 2. Required operator-visible behavior

Keep existing columns (name, temperature band, throughput, storage mass,
reporting `position_count`, reporting `required_area_m2`). Add persisted
layout detail **without** replacing those reporting scalars.

Detection is presence of persisted fields, not a Vue formula:

| When persisted | Show (read-only) |
| --- | --- |
| `schemes` is a non-empty array | **Both** scheme rows: `scheme_id`, `room_count`, `position_count`, `required_area_m2`. Label `reporting_scheme_id` as the scalar reporting scheme (6-position). Never `min()` / never hide the other scheme. |
| `n_need` is present | `n_need`, `n_actual`, `unused_cells`, packed `n_long` × `n_short` (from those fields or `layout`), persisted `aisle_layout` token |
| `pallet_count` / `truck_count` / `platform_count` present (出货通道) | those three counts; area stays the persisted `required_area_m2` |
| `zone_code` present | may be shown as a secondary identity; do not derive names from it |
| `total_area_m2_8_position_scheme` on the zone **result** snapshot | optional caption on CalculationsPage: 8-position plant total. Pass through. Do not sum scheme areas in Vue. |

Reporting `required_area_m2` / `position_count` remain the P2 6-position
projection. Copy MUST say the scalar area is the **6 位汇报方案**, not
“the only” precooling area.

Empty state (CalculationsPage):

- Keep the sentence `暂无完整五阶段计算结果。` (P5 `workbench.test.ts`
  asserts it; do not edit that P5 file).
- Replace `填写 EngineeringInputBundleV1` with operator-path copy:
  请在「工程输入」填写五个过程 KEY 并提交 `OperatorProcessInputV1`.
- Do not tell operators to assemble a full bundle in Vue.

Page measure: raise `calculations-page` `max-width` from 960px to
**1400px** so scheme/layout columns fit (P5 left this page untouched).

Formatting (`toFixed`, kg vs t, em dash) is allowed. Arithmetic that
produces area, positions, rooms, trucks, or docks is forbidden.

## 3. Pass-through plumbing (P0 §7.4 did not name these files)

At `BASE_MAIN_SHA`, `mapPersistedCalculationsToPlanningResponse` **strips**
zone objects to six fields, so `ZoneResultsTable` cannot see P2 schemes
even if the table is updated. `ZoneResultContract` likewise omits them.

P3 must pass persisted P2 fields through. This is display plumbing, not
a formula recut, and not a Charles leftover round.

Optional fields to admit on `ZoneResultContract` (all optional so V0.4
fixtures keep compiling):

```text
zone_code
n_need
n_long
n_short
n_actual
unused_cells
layout
aisle_layout
reporting_scheme_id
schemes
pallet_count
truck_count
platform_count
```

Optional on `PlanningRunResponse.summary`:

```text
total_area_m2_8_position_scheme
```

Mapper rules:

- Copy those fields when present; do not default them to `0` when absent
  (`asNumber(...)` → 0 would fabricate docks/need).
- Prefer persisted `result.total_area_m2` for summary when present.
- Copy `result.total_area_m2_8_position_scheme` when present; **do not**
  add scheme areas in the frontend.
- Existing summary `total_position_count` summing of persisted
  `position_count` may remain (display aggregation of persisted scalars,
  not a zone formula).

Do not recut `PlanningRunRequest` (V0.4 leftover). Do not edit backend
snapshot models (`extra="forbid"` stays P2's job).

## 4. Exclusive allowlist

P3 allowlist = P0 §7.4 (with the co-located test path) ∪ mapper/types ∪
architecture tests.

P0 listed `frontend/tests/features/calculations/ZoneResultsTable.test.ts`.
The file already lives at
`frontend/src/features/calculations/components/ZoneResultsTable.test.ts`.
Do **not** create a second copy. Do **not** edit P0.

```text
V09_P3_FILE_ALLOWLIST
docs/tasks/V0_9-P3-zone-result-display-contract.md
frontend/src/features/calculations/components/CalculationsPage.vue
frontend/src/features/calculations/components/ZoneResultsTable.vue
frontend/src/features/calculations/components/ZoneResultsTable.test.ts
frontend/src/features/calculations/model/mapPersistedCalculations.ts
frontend/src/features/calculations/model/mapPersistedCalculations.test.ts
frontend/src/api/contracts/planning.ts
frontend/src/features/calculations/architecture/test_v09_p3_zone_result_display.test.ts
backend/tests/architecture/test_v09_p3_zone_result_display_contract.py
backend/tests/architecture/test_v09_p2_zone_formula_contract.py
```

Architecture tests:

- P0 §7.4 paths (after aliasing the P0 test path to the co-located file)
  are a subset of this allowlist.
- `git diff --name-only origin/main` plus untracked stays on this
  allowlist. Enforce only when the branch name contains
  `v09-p3-zone-result` (`GITHUB_HEAD_REF` in CI). Wrap long `skipif`
  reasons so ruff E501 cannot fail.
- Vue/TS P3 files file-scan: no `Math.ceil`, no area/dock arithmetic
  (`* 1.56`, `* 2.5`, `* 55`, `/ 400`, `/ 16`), no
  `utilization_factor` / `reserve_factor` assignments.
- No `backend/src/**` changes. No `zone_planning.py`.

## 5. Hard non-goals

```text
FORMULA_RECUT_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT=NO
ZONE_PLANNING_PY_EDIT=NO
BACKEND_SRC_EDIT=NO
VUE_ENGINEERING_FORMULAS=NO
AILY_LIVE_IMPLEMENTATION=NO
PRODUCTION_RBAC_CLAIM=NO
FEISHU_REVIEW_IMPLEMENTATION=NO
WORKBENCH_TEST_TS_EDIT=NO
CALCULATION_SUMMARY_VUE_EDIT=NO
V05_V06_V07_V08_TEST_ASSERTION_MUTATION=NO
```

P3 must not:

- edit `zone_planning.py`, cooling/equipment/power/investment, Alembic,
  sample loaders, or P0/P1/P2/P4/P5 contracts
- edit `frontend/tests/workbench.test.ts` (P5 allowlist)
- edit `CalculationSummary.vue` (keep four cards; 8-position plant total
  is an optional CalculationsPage caption, not a fifth summary card)
- invent scheme/need/dock numbers when the snapshot omitted them
- collapse dual precooling schemes to one area
- claim construction drawings or field-equipment control

If `PersistedResultsPages.test.ts` fails because mapper fixtures must
carry optional fields, retarget that file on this PR (standing CI-red
repair). Do not pre-edit it unless the test fails. If it must change,
add it to the allowlist in the same commit and keep this contract in
sync — then ruff-format / skipif-wrap without a new 授权 round.

### 5.1 Charles-authorized CI-red repair (2026-08-27)

Charles standing: 红了就修. sqlite failed because merged P2 architecture
tests `test_zone_planning_is_only_production_formula_file_changed` and
`test_no_vue_changes_in_p2_diff` still asserted against `origin/main`
on the P3 branch. Gate those two to `v09-p2-zone-formula`. Do not weaken
P2 formula identity checks that read `zone_planning.py` on disk.

```text
CHARLES_V09_P3_CI_RED_REPAIR_AUTHORIZED=YES
DATE=2026-08-27
AUTHORIZED_FILES
backend/tests/architecture/test_v09_p2_zone_formula_contract.py
IDENTITY_DECISION=P2 formula recut stays merged; Vue display is P3
```

## 6. Tests required

| Surface | Must prove |
| --- | --- |
| ZoneResultsTable | Dual schemes both visible; need vs actual; shipping docks; missing optional fields do not fabricate zeros; empty state unchanged for zero zones |
| Mapper | P2 fields pass through; absent optional fields stay absent (not `0`); 8-position plant total copied not summed |
| Architecture (frontend) | File-scan no Vue formulas on P3 Vue/TS |
| Architecture (backend) | Allowlist vs origin/main on the P3 branch; no `backend/src` diff |

Do not assert expert geometry numbers (52 / 68 / 55 / 1.56) in Vue tests.
Use fixture literals and check they **render as given**.

## 7. Acceptance criteria

```text
ZONE_TABLE_SHOWS_DUAL_PRECOOL_SCHEMES=PASS
ZONE_TABLE_SHOWS_NEED_VS_ACTUAL=PASS
ZONE_TABLE_SHOWS_SHIPPING_DOCKS=PASS
MAPPER_PASSES_THROUGH_P2_FIELDS=PASS
MISSING_FIELDS_NOT_INVENTED=PASS
NO_VUE_AREA_OR_DOCK_ARITHMETIC=PASS
EMPTY_STATE_OPERATOR_PROCESS_INPUT=PASS
EMPTY_STATE_KEEPS_NO_FULL_CHAIN_SENTENCE=PASS
CALCULATIONS_PAGE_MAX_WIDTH_1400=PASS
BACKEND_SRC_UNCHANGED=PASS
ZONE_PLANNING_PY_UNCHANGED=PASS
WORKBENCH_TEST_TS_UNCHANGED=PASS
FORMULA_RECUT_AUTHORIZED=NO
AILY_LIVE_IMPLEMENTATION=NO
DRAFT=YES
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
```

Authoritative test surface:

```text
frontend/src/features/calculations/components/ZoneResultsTable.test.ts
frontend/src/features/calculations/model/mapPersistedCalculations.test.ts
frontend/src/features/calculations/architecture/test_v09_p3_zone_result_display.test.ts
backend/tests/architecture/test_v09_p3_zone_result_display_contract.py
```

## 8. Verification

```text
cd frontend && npm test -- --run \
  src/features/calculations/components/ZoneResultsTable.test.ts \
  src/features/calculations/model/mapPersistedCalculations.test.ts \
  src/features/calculations/architecture/test_v09_p3_zone_result_display.test.ts
cd backend && uv run ruff format --check ../docs/tasks/V0_9-P3-zone-result-display-contract.md \
  tests/architecture/test_v09_p3_zone_result_display_contract.py
cd backend && PYTHONPATH=src uv run pytest -q \
  tests/architecture/test_v09_p3_zone_result_display_contract.py
```

(Contract markdown is not ruff-formatted; ruff the Python architecture
test. Frontend also run existing `PersistedResultsPages.test.ts` and
`CalculationSummary.test.ts` without editing them unless they fail.)

## 9. Not in P3

- Zone formula recut (P2, already merged)
- Draft vs formal export (P4, already merged)
- Workbench layout / `workbench.test.ts` (P5, already merged)
- V0.9 sample loader (P6)
- Controlled acceptance (P7)
- Tag / Release / merge authorization

## 10. Revision history

| Rev | Date | Change |
| --- | --- | --- |
| R1 | 2026-08-27 | P3 zone result display at `808cbfd` / P2 #217 / `v0.8.0` |
| R2 | 2026-08-27 | Gate P2 origin/main Vue/formula-diff tests to the P2 branch |
