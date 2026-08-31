# V1.8 P0 — Per-zone cooling temperature and height (definition freeze)

**Status:** Definition frozen — implementation **not** authorized  
**Authority:** Charles-selected theme in `docs/tasks/V1_8-version-plan.md`  
**Previous release:** `v1.7.0`  
**Base `main` SHA:** `60f741c`  
**Companion:** `docs/tasks/V1_8-version-plan.md`,
`docs/architecture/ADR-040-per-zone-temperature-height-surface.md`

```text
TASK=V18_P0_ZONE_TEMP_HEIGHT_R1
GOVERNANCE_OWNER=V1.8
PREVIOUS_RELEASE=v1.7.0
BASE_MAIN_SHA=60f741c
TARGET_FILE=docs/tasks/V1_8-P0-zone-temperature-height-contract.md
V18_P0_IMPLEMENTATION_AUTHORIZED=NO
V18_IMPLEMENTATION_AUTHORIZED=NO
ZONE_THERMAL_INPUT_SURFACE=YES
ZONE_TEMPERATURE_FROM_ZONE_PLAN_BAND=YES
ZONE_TEMPERATURE_BAND_POINT=COLD_END
ZONE_TEMPERATURE_CATALOG_RECUT=YES
ZONE_HEIGHT_CATALOG_RECUT=YES
ZONE_PRODUCT_MASS_CATALOG_RECUT=NO
ZONE_THERMAL_CATALOG_RECUT=NO
KEEP_COOLING_LOAD_VERSION=YES
DO_NOT_BUMP_COOLING_LOAD_VERSION=YES
FORMULA_RECUT_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT=NO
KEEP_OPERATOR_SCHEMA=OperatorProcessInputV1@1.1.0
KEEP_CALCULATOR_IDENTITY=cold_room_zone_plan@1.0.0,cooling_load@1.0.0,equipment@1.0.0,installed_power@1.0.0,investment_estimate@1.0.0
KEEP_ZONE_PLAN_VERSION=YES
KEEP_EQUIPMENT_VERSION=YES
KEEP_INSTALLED_POWER_VERSION=YES
KEEP_INVESTMENT_VERSION=YES
AILY_OUTBOUND_LIVE_SESSION=NO
KEEP_AILY_V17_SKILL_FROZEN=YES
KEEP_AILY_V18_SKILL=YES
AGENT_TO_ENGINEERING_VALUE=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
DELETE_PATH_A_SAVE_INPUTS=NO
TD008_EQUIPMENT_CATALOG_UNIFIED=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
MARK_REVIEWED_AS_MODEL_TOOL=NO
EXTEND_API_V1_AGENT_FOR_AILY=NO
```

## 1. Objective

On unmodified `create_app`, after Charles authorizes implementation, workbench
persist and Aily in-memory cooling preview (`persisted: false`) copy each
refrigerated zone's **already-bound** `room_design_temperature` and
`room_height` onto the cooling snapshot so operators can audit °C and m
beside the V1.7 five components.

Copy the values cooling actually used. Do **not** recompute
`Q = U × A × ΔT`. Do **not** bump `cooling_load@1.0.0`. Do **not** invent
per-zone °C or m. Aily does not import `cold_storage.modules.calculations`.
Vue / reports / prompts do not embed cooling or geometry formulas.

Temperature catalog gate is **YES**: indoor °C comes from existing
zone-plan bands, **cold end** of each range (V18-T1: 8.0 / 1.0 / −18.0).
`product_target_temperature` uses the same table. Height catalog gate is
**YES**: **4.0 m** for every refrigerated zone (V18-H1).
Do not invent per-zone °C or m. Do not keep v05 −18 °C / 5.0 m on the
operator-minimal path after implementation is authorized.

## 2. Operator KEY (unchanged)

```text
zone_planning_inputs.daily_inbound_mass_kg
zone_planning_inputs.finished_storage_days
zone_planning_inputs.frozen_storage_days
zone_planning_inputs.main_packaging_storage_days
zone_planning_inputs.auxiliary_packaging_storage_days
```

Missing KEY → `MISSING_ENGINEERING_PARAMETER` plus `ask_operator`.
No new KEY. Tonne = per day.

## 3. Zone snapshot fields (frozen addition)

Keep V1.7 leaves. Add optional input-echo leaves on new writes:

```text
zone_code
zone_name
temperature_level
room_design_temperature
room_height
transmission_load_kw_r
product_load_kw_r
infiltration_load_kw_r
internal_load_kw_r
defrost_load_kw_r
subtotal_load_kw_r
```

Historical snapshots without the two new leaves must still parse
(`extra` fields optional on read). Equipment lineage still binds on
`zone_code` + `subtotal_load_kw_r`.

`room_design_temperature` and `room_height` are copies of cooling inputs
(or kernel input echo). They are not Vue-derived and not prompt-derived.

## 4. HTTP / MCP (unchanged addresses)

```text
POST /api/v1/aily/v1/zone-plan
POST /api/v1/aily/v1/concept-preview
Streamable HTTP  {ORIGIN}/api/v1/aily/v1/mcp/sse
```

Keep tools (zone first):

```text
preview_zone_plan
preview_cooling_load
preview_equipment
preview_installed_power
preview_investment
```

Do not extend `/api/v1/agent/**`. Freeze `docs/contracts/aily/v1.7/**`.
A V1.8 skill pack is a later package after authorization.

## 5. Honesty (success path)

Keep V1.5 flags:

```text
persisted: false
requires_review: true
floor_area_from_zone_plan: true
envelope_wall_roof_from_plan: true
formula_recut_authorized: true
```

Caption / skill must still contain:

```text
地板、墙、屋面来自分区几何（正方形平面 + 演示层高）
U 值与设计温度仍为演示目录
```

After catalog recut, honesty must say refrigerated-zone height is the
Charles demo catalog **4.0 m**, and indoor °C is the zone-plan band
**cold end** (8 / 1 / −18), not v05 −18 for every zone.

This slice `FORMULA_RECUT_AUTHORIZED=NO`.
`ZONE_TEMPERATURE_FROM_ZONE_PLAN_BAND=YES`.
`ZONE_TEMPERATURE_BAND_POINT=COLD_END`.
`ZONE_TEMPERATURE_CATALOG_RECUT=YES`.
`ZONE_HEIGHT_CATALOG_RECUT=YES`.
`ZONE_PRODUCT_MASS_CATALOG_RECUT=NO`.
`ZONE_THERMAL_CATALOG_RECUT=NO`.

## 6. Catalog recut (explicit Charles gates only)

Do not stamp band midpoints. Do not guess missing height.

`ZONE_TEMPERATURE_CATALOG_RECUT=YES`: stamp `room_design_temperature`
and `product_target_temperature` from V18-T1 (zone-plan band cold end:
8.0 / 1.0 / −18.0). Unmapped band → fail-closed.

`ZONE_HEIGHT_CATALOG_RECUT=YES`: stamp `room_height = 4.0` m on every
refrigerated zone from V18-H1 (`source_type=demo`,
`validity_status=unverified`, `requires_review=true`). Do not rewrite
`samples/v05-local-workbench/manifest.json`. Missing / non-positive
height stays fail-closed. V1.5 square-plan wall bind consumes the new
height; do not re-derive wall area in Vue or Aily. The `4` in
`wall = height × 4 × √A` is four square sides, not the 4.0 m catalog.

Product mass per zone stays 20000 kg/day unless
`ZONE_PRODUCT_MASS_CATALOG_RECUT=YES` (not requested for V1.8).

## 7. Non-goals

```text
AILY_OUTBOUND_LIVE_SESSION=NO
KEEP_COOLING_LOAD_VERSION=YES
ZONE_THERMAL_INPUT_SURFACE=YES
ZONE_TEMPERATURE_FROM_ZONE_PLAN_BAND=YES
ZONE_TEMPERATURE_BAND_POINT=COLD_END
ZONE_TEMPERATURE_CATALOG_RECUT=YES
ZONE_HEIGHT_CATALOG_RECUT=YES
ZONE_PRODUCT_MASS_CATALOG_RECUT=NO
ZONE_THERMAL_CATALOG_RECUT=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
PRODUCTION_RBAC_CLAIM=NO
AGENT_TO_ENGINEERING_VALUE=NO
DELETE_PATH_A_SAVE_INPUTS=NO
FORMULA_RECUT_AUTHORIZED=NO
```

Do not bump calculator `VERSION`. Do not reopen #11 / #13 / #17 / #176 / #20.
Do not move `v0.9.0` … `v1.7.0`.

## 8. Allowlist

```text
V18_P0_FILE_ALLOWLIST
docs/tasks/V1_8-P0-zone-temperature-height-contract.md
docs/tasks/V1_8-version-plan.md
docs/architecture/ADR-040-per-zone-temperature-height-surface.md
docs/TECH_DEBT.md
docs/roadmap/DEVELOPMENT_PLAN.md
docs/audit/current-state.md
docs/audit/gap-analysis.md
docs/tasks/V1_7-version-plan.md
backend/tests/architecture/test_v18_p0_zone_temperature_height_contract.py
```

After authorization, later packages may change cooling snapshot optional
leaves, adapter/kernel input echo, assembler demo catalog (only if a recut
gate is YES), workbench `COOLING_ZONE_COLUMNS`, Aily cooling extra table /
captions, `docs/contracts/aily/v1.8/**`, and
`docs/runbooks/v18-doubao-aily-connector.md`.
Do not edit frozen `docs/contracts/aily/v1.7/**` or `cooling_load.py` formulas.
