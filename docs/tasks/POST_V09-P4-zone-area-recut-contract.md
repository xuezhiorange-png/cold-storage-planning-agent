# POST-V0.9 P4 — Zone Area Formula Recut

**Status:** Implementation authorized — Charles `可以派发` 2026-08-28  
**Authority:** Room-by-room expert lock 2026-08-28 (supersedes V0.9 version-plan §4
for **zone area only**)  
**Parent on `main`:** `d6c3af953d0d8486fd5762e5797ecd336f44fbf2`  
**Target branch:** `cursor/post-v09-p4-zone-area-recut-6c68`

This package recuts **only** `cold_room_zone_plan` area formulas in
deterministic Python. It does not recut cooling / equipment / power /
investment **formulas**. Vue must not duplicate formulas. Reports must
not recalculate; they read persisted `required_area_m2`.

Sibling packages (do not implement here):

- P5 result tables
- P6 report readability
- P7 scheme button / sidebar
- P8 frontend visual polish

## 0. Contract identity and governance

```text
TASK=POST_V09_P4_ZONE_AREA_RECUT_R1
GOVERNANCE_OWNER=POST-V0.9
BASE_MAIN_SHA=d6c3af953d0d8486fd5762e5797ecd336f44fbf2
PREVIOUS_RELEASE=v0.9.0
TARGET_BRANCH=cursor/post-v09-p4-zone-area-recut-6c68
TARGET_FILE=docs/tasks/POST_V09-P4-zone-area-recut-contract.md
TARGET_PR_STATE=DRAFT

POST_V09_P4_IMPLEMENTATION_AUTHORIZED=YES
FORMULA_RECUT_AUTHORIZED=YES
ZONE_AREA_FORMULA_ONLY=YES
COOLING_LOAD_FORMULA_RECUT=NO
EQUIPMENT_FORMULA_RECUT=NO
INSTALLED_POWER_FORMULA_RECUT=NO
INVESTMENT_FORMULA_RECUT=NO
VUE_ENGINEERING_FORMULAS=NO
KEEP_CALCULATOR_IDENTITY=cold_room_zone_plan@1.0.0
AILY_LIVE_IMPLEMENTATION=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
CHARLES_POST_V09_P4_LIVING_TEST_UPDATE_AUTHORIZED=YES
```

Do not rewrite `docs/tasks/V0_9-version-plan.md` in place. This contract
is the new area-formula authority. Persist
`planning_parameters.formula_authority = "POST-V0.9-P4-charles-zone-area-recut"`.

## 1. Shared locks

`M_kg` = operator `daily_inbound_mass_kg`.  
`M_t` = `M_kg / 1000` (t/day).

Throughput bands (25 inclusive mid, 50 inclusive high):

- `M_t < 25`
- `25 ≤ M_t < 50`
- `M_t ≥ 50`

Pallet pitch for storage rooms (unchanged): along-wall 1.2 m, depth 1.3 m.
Rectangle packing (unchanged): `n_long ≥ n_short`, aspect 1.67–2.40,
fewest unused cells, then closest to ratio 2, then smaller area.

Do not deduct 次果 from 成品间. Do not deduct 冻果 from 出货通道.

## 2. Room formulas

### 2.1 办公室 `office`

- `M_t < 25` → 60 m²
- `25 ≤ M_t < 50` → 80 m²
- `M_t ≥ 50` → 100 m²

### 2.2 更衣室 `changing_room`

- `M_t < 25` → 40 m²
- `25 ≤ M_t < 50` → 80 m²
- `M_t ≥ 50` → 120 m²

### 2.3 一级预冷 `primary_precooling_room`

Capacity unchanged: 100% `M_kg`, 220 kg × 6 h → `q_d = 1320`,
`n_need = ceil(M_kg / 1320)`. Dual schemes. Report 6-position, not `min()`.

- 6-position room **42 m²** (was 52)
- 8-position room **56 m²** (was 68)

### 2.4 二级预冷 `secondary_precooling_room`

Capacity unchanged: full `M_kg`, `q_d = 3200`,
`n_need = ceil(M_kg / 3200)`. Same modules **42 / 56**. Report 6-position.

### 2.5 原果暂存 `raw_fruit_buffer`

`M_raw = M_kg × 0.40`, 220 kg/pallet, `n_need = ceil(M_raw / 220)`.
Long side against wall; **three-side aisle 2.2 m** (was 3.0):

```text
A = (n_long × 1.2 + 2.2 + 2.2) × (n_short × 1.3 + 2.2)
```

### 2.6 分选包装 `sorting_packaging_room`

Throughput full `M_kg`. Person capacity 384 kg/day. 3 persons/table.
Table pitch **5.6 × 3.0**. n tables → **(n−1)** pitches (Charles lock A).
Four-side clearances, architectural 短边/长边 of packed rectangle:

- n_long axis (5.6): 3 m + 5 m
- n_short axis (3.0): 3 m + 4.6 m

```text
A = ((n_long − 1) × 5.6 + 3 + 5) × ((n_short − 1) × 3.0 + 3 + 4.6)
```

If `n_long = 1` or `n_short = 1`, that axis is clearances only (Charles chose A).

### 2.7 覆膜间 `coating_room`

- `M_t < 25` → 80 m²
- `25 ≤ M_t < 50` → 120 m²
- `M_t ≥ 50` → 200 m²

### 2.8 成品间 `finished_goods_room`

Deduct frozen ratio 10% only (hardcoded `FROZEN_FRUIT_RATIO`):

```text
M_fin = M_kg × (1 − 0.10) × D_f
n_need = ceil(M_fin / 400)
A = (n_long × 1.2) × (n_short × 1.3 + 3)
```

`D_f` = operator `finished_storage_days`. One long-side 3 m aisle.
Do not deduct 次果. Do not use 原果 2.2 m three-side.

### 2.9 次果暂存 `secondary_fruit_buffer`

```text
M_sec = M_kg × 0.10 × 2
```

Days **hardcoded 2** (was 3). 220 kg/pallet. One long-side 3 m aisle
(same A as finished).

### 2.10 冻果间 `frozen_fruit_room`

**Maintain** V0.9 §4.8: `M_fr = M_kg × 0.10 × D_fr`, 600 kg/pallet,
one long-side 3 m aisle. `D_fr` = operator `frozen_storage_days`.

### 2.11 包材库 `packaging_material_storage`

Position count formula unchanged (`c_main` / `c_aux`).  
`A = n × 1.56 × k(M_t)` where

- `M_t < 25` → k = 2.4
- `25 ≤ M_t < 50` → k = 2.3
- `M_t ≥ 50` → k = 2.2

### 2.12 出货通道 `shipping_channel`

Truck/platform count unchanged. **50 m² per platform** (was 55).
Full `M_kg`, no 冻果 deduct.

## 3. Sample KEY oracle (must have an independent test)

Operator sample: 20000 kg/day, finished 7 d, frozen 10 d, main pack 4 d,
aux pack 12 d.

| zone_code | required_area_m2 |
|---|---|
| office | 60.00 |
| changing_room | 40.00 |
| primary_precooling_room | 126.00 |
| secondary_precooling_room | 84.00 |
| raw_fruit_buffer | 132.24 |
| sorting_packaging_room | 489.60 |
| coating_room | 80.00 |
| finished_goods_room | 602.64 |
| secondary_fruit_buffer | 57.96 |
| frozen_fruit_room | 88.56 |
| packaging_material_storage | 250.85 |
| shipping_channel | 50.00 |
| **total 6-position** | **2061.85** |

Primary 6-pos: n_need=16 → 3×42=126. Sorting 6×3 → 36×13.6=489.6.
Finished n_need=315, packed 27×12.

Also keep independent oracles for other masses (including **exactly 25 t**
and **exactly 50 t** band edges).

## 4. Exclusive allowlist

```text
POST_V09_P4_FILE_ALLOWLIST
docs/tasks/POST_V09-P4-zone-area-recut-contract.md
backend/tests/architecture/test_post_v09_p4_zone_area_recut_contract.py
backend/src/cold_storage/modules/calculations/domain/zone_planning.py
backend/tests/unit/test_zone_planner.py
backend/tests/unit/test_v09_p2_zone_planning.py
backend/tests/unit/test_post_v09_p4_zone_area_recut.py
```

Living-test retarget of `test_zone_planner.py` and
`test_v09_p2_zone_planning.py` is authorized. If another unit test
calls the live planner and fails only on superseded §4 areas, add that
file to the allowlist in a follow-up commit on this branch and record
it in the PR body. Do not expand into Vue or reports.

## 5. Out of scope

- Vue, workflow, scheme-runs, report assembler
- Cooling/equipment/power/investment calculators
- Calculator VERSION bump
- Tag / Release / merge
