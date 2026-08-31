# V1.7 P0 — Per-zone cooling load component surface (definition freeze)

**Status:** Implementation authorized — persist and display kernel zone components  
**Authority:** Charles-selected theme in `docs/tasks/V1_7-version-plan.md`  
**Previous release:** `v1.6.0`  
**Base `main` SHA:** `cd702b0`  
**Companion:** `docs/tasks/V1_7-version-plan.md`,
`docs/architecture/ADR-039-per-zone-cooling-component-surface.md`

```text
TASK=V17_P0_ZONE_COOLING_SURFACE_R1
GOVERNANCE_OWNER=V1.7
PREVIOUS_RELEASE=v1.6.0
BASE_MAIN_SHA=cd702b0
TARGET_FILE=docs/tasks/V1_7-P0-zone-cooling-surface-contract.md
V17_P0_IMPLEMENTATION_AUTHORIZED=YES
V17_IMPLEMENTATION_AUTHORIZED=YES
COOLING_ZONE_COMPONENT_SURFACE=YES
KEEP_COOLING_LOAD_VERSION=YES
DO_NOT_BUMP_COOLING_LOAD_VERSION=YES
FORMULA_RECUT_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT=NO
ZONE_THERMAL_CATALOG_RECUT=NO
KEEP_OPERATOR_SCHEMA=OperatorProcessInputV1@1.1.0
KEEP_CALCULATOR_IDENTITY=cold_room_zone_plan@1.0.0,cooling_load@1.0.0,equipment@1.0.0,installed_power@1.0.0,investment_estimate@1.0.0
KEEP_ZONE_PLAN_VERSION=YES
KEEP_EQUIPMENT_VERSION=YES
KEEP_INSTALLED_POWER_VERSION=YES
KEEP_INVESTMENT_VERSION=YES
AILY_OUTBOUND_LIVE_SESSION=NO
KEEP_AILY_V16_SKILL_FROZEN=YES
KEEP_AILY_V17_SKILL=YES
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

On unmodified `create_app`, workbench persist and Aily in-memory cooling
preview (`persisted: false`) keep the kernel's **per-zone five components**
instead of collapsing `zones` to `zone_code` + `subtotal_load_kw_r`.

Copy fields from `cooling_load.py` zone dict. Do **not** recompute
`Q = U × A × ΔT`. Do **not** bump `cooling_load@1.0.0`. Aily does not import
`cold_storage.modules.calculations`. Vue / reports / prompts do not embed
cooling formulas.

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

## 3. Zone snapshot fields (frozen)

Each refrigerated zone in the cooling adapter payload / persisted snapshot:

```text
zone_code
zone_name
temperature_level
transmission_load_kw_r
product_load_kw_r
infiltration_load_kw_r
internal_load_kw_r
defrost_load_kw_r
subtotal_load_kw_r
```

Historical snapshots that only have `zone_code` + `subtotal_load_kw_r` must
still parse (`extra` fields optional on read). New writes populate all listed
leaves. Equipment lineage still binds on `zone_code` + `subtotal_load_kw_r`.

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

Do not extend `/api/v1/agent/**`.

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

And add: 分区冷量按内核五项加总；货品热工各区目前共用 v05 演示目录，需复核.

This slice `FORMULA_RECUT_AUTHORIZED=NO`. `ZONE_THERMAL_CATALOG_RECUT=NO`.

## 6. Non-goals

```text
AILY_OUTBOUND_LIVE_SESSION=NO
KEEP_COOLING_LOAD_VERSION=YES
ZONE_THERMAL_CATALOG_RECUT=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
PRODUCTION_RBAC_CLAIM=NO
AGENT_TO_ENGINEERING_VALUE=NO
DELETE_PATH_A_SAVE_INPUTS=NO
FORMULA_RECUT_AUTHORIZED=NO
```

Do not bump calculator `VERSION`. Do not reopen #11 / #13 / #17 / #176 / #20.
Do not move `v0.9.0` … `v1.6.0`.

## 7. Allowlist

```text
V17_P0_FILE_ALLOWLIST
docs/tasks/V1_7-P0-zone-cooling-surface-contract.md
docs/tasks/V1_7-version-plan.md
docs/architecture/ADR-039-per-zone-cooling-component-surface.md
docs/TECH_DEBT.md
docs/roadmap/DEVELOPMENT_PLAN.md
docs/audit/current-state.md
docs/audit/gap-analysis.md
docs/tasks/V1_6-version-plan.md
backend/tests/architecture/test_v17_p0_zone_cooling_surface_contract.py
```

After authorization, later packages may change cooling adapter zone
projection, `CoolingLoadZoneResultV1` optional component leaves,
Aily cooling extra table / captions, `docs/contracts/aily/v1.7/**`, and
`docs/runbooks/v17-doubao-aily-connector.md`.
Do not edit frozen `docs/contracts/aily/v1.6/**` or `cooling_load.py` formulas.
