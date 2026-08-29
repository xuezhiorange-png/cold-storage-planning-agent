# V1.3 P0 — Aily 对话预览对齐工作台血缘（定义冻结）

**Status:** Definition freeze R1 — plan reviewable; implementation not dispatched  
**Authority:** recommended theme in `docs/tasks/V1_3-version-plan.md`  
**Previous release:** `v1.2.0`  
**Base `main` SHA:** `cb8a00b`  
**Companion:** `docs/tasks/V1_3-version-plan.md`,
`docs/architecture/ADR-035-aily-preview-workbench-lineage.md`

```text
TASK=V13_P0_AILY_PREVIEW_LINEAGE_R1
GOVERNANCE_OWNER=V1.3
PREVIOUS_RELEASE=v1.2.0
BASE_MAIN_SHA=cb8a00b
TARGET_FILE=docs/tasks/V1_3-P0-aily-preview-lineage-contract.md
V13_P0_IMPLEMENTATION_AUTHORIZED=NO
V13_IMPLEMENTATION_AUTHORIZED=NO
AILY_INBOUND_PREVIEW_LINEAGE=YES
AILY_OUTBOUND_LIVE_SESSION=NO
KEEP_OPERATOR_SCHEMA=OperatorProcessInputV1@1.1.0
KEEP_ZONE_PLAN_VERSION=YES
KEEP_COOLING_LOAD_VERSION=YES
KEEP_EQUIPMENT_VERSION=YES
KEEP_INSTALLED_POWER_VERSION=YES
KEEP_INVESTMENT_VERSION=YES
KEEP_CALCULATOR_IDENTITY=cold_room_zone_plan@1.0.0,cooling_load@1.0.0,equipment@1.0.0,installed_power@1.0.0,investment_estimate@1.0.0
DO_NOT_BUMP_ZONE_PLAN_VERSION=YES
FORMULA_RECUT_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT=NO
EQUIPMENT_FORMULA_RECUT=NO
INSTALLED_POWER_FORMULA_RECUT=NO
INVESTMENT_FORMULA_RECUT=NO
ENVELOPE_FROM_ZONE_AREA=floor_and_zone_area_only
ENVELOPE_WALL_ROOF_FROM_PLAN=NO
AGENT_TO_ENGINEERING_VALUE=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
MARK_REVIEWED_AS_MODEL_TOOL=NO
EXTEND_API_V1_AGENT_FOR_AILY=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 1. Objective (when dispatched)

On unmodified `create_app`, conversation preview reuses the **same lineage
binds** the operator workbench already runs after persist, but **in memory**:

```text
five KEY
 → assemble (existing operator assembler)
 → zone kernel
 → bind required_area_m2 → cooling floor_area / zone_area
 → cooling kernel (wall / roof / U-values still demo catalog)
 → bind cooling kW(r) → equipment (already in V1.2)
 → equipment kernel with electrical kW(e) retained
 → bind kW(e) → installed power
 → bind zone totals + power → investment
 → tables + markdown_table
```

No persist. Not Transaction B. No formula recut. Aily does not import
`cold_storage.modules.calculations`. Aily does not compute kW(e) from kW(r)/COP.

## 2. Operator KEY (unchanged)

```text
zone_planning_inputs.daily_inbound_mass_kg
zone_planning_inputs.finished_storage_days
zone_planning_inputs.frozen_storage_days
zone_planning_inputs.main_packaging_storage_days
zone_planning_inputs.auxiliary_packaging_storage_days
```

Missing KEY → `MISSING_ENGINEERING_PARAMETER` plus `ask_operator`.

## 3. HTTP / MCP (unchanged addresses)

Keep:

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

Same five-KEY inputSchema, `validate_input=False`, same `X-Aily-Connector-Key`.
Do not extend `/api/v1/agent/**`.

## 4. Honesty flags (after implementation)

Success cooling / concept-preview:

```text
persisted: false
requires_review: true
floor_area_from_zone_plan: true
envelope_wall_roof_from_plan: false
formula_recut_authorized: false
power_from_demo_catalog: false   (success path)
investment_from_demo_catalog: false   (success path)
```

Skill / table caption: 地板与规划面积来自分区结果；墙、屋面、U 值仍为演示目录，需复核.

V1.2 flags `envelope_from_zone_area: false` and `power_from_demo_catalog: true`
are **superseded on the V1.3 success path** after dispatch. V1.2 skill and
runbook stay frozen as historical.

## 5. Non-goals

```text
AILY_OUTBOUND_LIVE_SESSION=NO
COOLING_LOAD_FORMULA_RECUT=NO
ENVELOPE_WALL_ROOF_FROM_PLAN=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
PRODUCTION_RBAC_CLAIM=NO
AGENT_TO_ENGINEERING_VALUE=NO
```

Do not bump calculator `VERSION`. Do not reopen #11 / #13 / #17 / #176 / #20.
Do not move `v0.9.0` / `v1.0.0` / `v1.1.0` / `v1.2.0`.

## 6. Allowlist (definition freeze now; code after dispatch)

```text
V13_P0_FILE_ALLOWLIST
docs/tasks/V1_3-P0-aily-preview-lineage-contract.md
docs/tasks/V1_3-version-plan.md
docs/architecture/ADR-035-aily-preview-workbench-lineage.md
docs/TECH_DEBT.md
docs/roadmap/DEVELOPMENT_PLAN.md
docs/audit/current-state.md
docs/audit/gap-analysis.md
backend/tests/architecture/test_v13_p0_aily_preview_lineage_contract.py
```

After `V13_IMPLEMENTATION_AUTHORIZED=YES`, later packages may add
`backend/src/cold_storage/modules/aily/**`, orchestration snapshot capture,
`docs/contracts/aily/v1.3/**`, and `docs/runbooks/v13-doubao-aily-connector.md`.
Do not edit frozen `docs/contracts/aily/v1.2/**` or ADR-034 body.
