# V1.6 P0 — v05 evaporator/condenser fan demo catalog (definition freeze)

**Status:** Implementation authorized — catalog authority only, not a calculator bump  
**Authority:** Charles-selected theme in `docs/tasks/V1_6-version-plan.md`  
**Previous release:** `v1.5.0`  
**Base `main` SHA:** `536603d`  
**Companion:** `docs/tasks/V1_6-version-plan.md`,
`docs/architecture/ADR-038-v05-power-fan-demo-catalog.md`

```text
TASK=V16_P0_POWER_FAN_CATALOG_R1
GOVERNANCE_OWNER=V1.6
PREVIOUS_RELEASE=v1.5.0
BASE_MAIN_SHA=536603d
TARGET_FILE=docs/tasks/V1_6-P0-power-fan-catalog-contract.md
V16_P0_IMPLEMENTATION_AUTHORIZED=YES
V16_IMPLEMENTATION_AUTHORIZED=YES
TD008_POWER_FAN_DEMO_AUTHORITY=YES
TD008_EQUIPMENT_CATALOG_UNIFIED=NO
FAN_KW_FROM_EQUIPMENT=NO
KEEP_INSTALLED_POWER_VERSION=YES
KEEP_OPERATOR_SCHEMA=OperatorProcessInputV1@1.1.0
AILY_OUTBOUND_LIVE_SESSION=NO
FORMULA_RECUT_AUTHORIZED=NO
KEEP_AILY_V15_SKILL_FROZEN=YES
KEEP_AILY_V16_SKILL=YES
KEEP_CALCULATOR_IDENTITY=cold_room_zone_plan@1.0.0,cooling_load@1.0.0,equipment@1.0.0,installed_power@1.0.0,investment_estimate@1.0.0
KEEP_ZONE_PLAN_VERSION=YES
KEEP_COOLING_LOAD_VERSION=YES
KEEP_EQUIPMENT_VERSION=YES
KEEP_INVESTMENT_VERSION=YES
DO_NOT_BUMP_INSTALLED_POWER_VERSION=YES
NO_STEP_IMPLIES_THE_NEXT=TRUE
AGENT_TO_ENGINEERING_VALUE=NO
DELETE_PATH_A_SAVE_INPUTS=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
MARK_REVIEWED_AS_MODEL_TOOL=NO
EXTEND_API_V1_AGENT_FOR_AILY=NO
POWER_CONFIGURATION_REPLACES_INSTALLED_POWER=NO
COOLING_LOAD_FORMULA_RECUT=NO
EQUIPMENT_FORMULA_RECUT=NO
INSTALLED_POWER_FORMULA_RECUT=NO
INVESTMENT_FORMULA_RECUT=NO
V05_COMPRESSOR_120_NOT_AUTHORITY=YES
```

## 1. Objective

On unmodified `create_app`, operator-minimal assembly and Aily in-memory
preview (`persisted: false`) use **one** demo authority for fan electrical
leaves:

```text
installed_power_inputs.evaporator_fan_power_kw_e = 10.0
installed_power_inputs.condenser_fan_power_kw_e  = 8.0
source_type=demo
validity_status=unverified
requires_review=true
source_path=samples/v05-local-workbench/manifest.json
```

Shared reader:
`projects.application.demo_power_fan_catalog`.
Assembler `_installed_power_defaults` / fan demo leaves must not copy
`InstalledPowerCalcInput()` zeros. Aily must delete `_PREVIEW_POWER_FAN_DEMO`
and must not keep a second `"10.0"` / `"8.0"` assignment set.

`InstalledPowerCalcInput` kernel defaults stay `_D("0")` / `_D("0")`.
Do **not** bump `installed_power@1.0.0`. Aily does not import
`cold_storage.modules.calculations`.

## 2. Operator KEY (unchanged)

```text
zone_planning_inputs.daily_inbound_mass_kg
zone_planning_inputs.finished_storage_days
zone_planning_inputs.frozen_storage_days
zone_planning_inputs.main_packaging_storage_days
zone_planning_inputs.auxiliary_packaging_storage_days
```

Missing KEY → `MISSING_ENGINEERING_PARAMETER` plus `ask_operator`.
No new KEY for fan kW(e). Tonne = per day.

## 3. HTTP / MCP (unchanged addresses)

Keep:

```text
POST /api/v1/aily/v1/zone-plan
POST /api/v1/aily/v1/concept-preview
Streamable HTTP  {ORIGIN}/api/v1/aily/v1/mcp/sse
GET  /api/v1/demo/operator-process-input
```

Optional honesty GET (same class as V1.4 operator demo):

```text
GET /api/v1/demo/power-fan-catalog
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

Compressor path stays:

```text
persisted: false
requires_review: true
power_from_demo_catalog: false
```

Fan caption / skill: 蒸发/冷凝风机电气来自 v05 演示目录（10 / 8 kW(e)），不是设备结果，需复核.

V1.5 cooling flags on the success path stay:

```text
floor_area_from_zone_plan: true
envelope_wall_roof_from_plan: true
formula_recut_authorized: true
```

This slice does **not** authorize a new formula recut
(`FORMULA_RECUT_AUTHORIZED=NO` on the V1.6 gate block).

## 5. Catalog (frozen)

| Leaf | Source |
|---|---|
| `evaporator_fan_power_kw_e` | v05 manifest `10.0` kW(e), stamped demo |
| `condenser_fan_power_kw_e` | v05 manifest `8.0` kW(e), stamped demo |
| `compressor_input_power_kw_e` | equipment electrical bind (not v05 `120.0`) |
| Kernel fan defaults | stay `0` / `0` (fail-closed) |

Missing v05 file or fan leaves fail-closed. Do not guess 10/8 in Python
when the sample is absent. Do not treat v05 `source_type=user` on those
sample leaves as operator-entered authority; assembler honesty is demo.

## 6. Non-goals

```text
AILY_OUTBOUND_LIVE_SESSION=NO
KEEP_INSTALLED_POWER_VERSION=YES
FAN_KW_FROM_EQUIPMENT=NO
TD008_EQUIPMENT_CATALOG_UNIFIED=NO
V05_COMPRESSOR_120_NOT_AUTHORITY=YES
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
PRODUCTION_RBAC_CLAIM=NO
AGENT_TO_ENGINEERING_VALUE=NO
DELETE_PATH_A_SAVE_INPUTS=NO
FORMULA_RECUT_AUTHORIZED=NO
```

Do not bump calculator `VERSION`. Do not reopen #11 / #13 / #17 / #176 / #20.
Do not move `v0.9.0` / `v1.0.0` / `v1.1.0` / `v1.2.0` / `v1.3.0` / `v1.4.0` /
`v1.5.0`.

## 7. Allowlist (definition freeze now; code in P1–P3)

```text
V16_P0_FILE_ALLOWLIST
docs/tasks/V1_6-P0-power-fan-catalog-contract.md
docs/tasks/V1_6-version-plan.md
docs/architecture/ADR-038-v05-power-fan-demo-catalog.md
docs/TECH_DEBT.md
docs/roadmap/DEVELOPMENT_PLAN.md
docs/audit/current-state.md
docs/audit/gap-analysis.md
docs/tasks/V1_5-version-plan.md
backend/tests/architecture/test_v16_p0_power_fan_catalog_contract.py
```

After `V16_IMPLEMENTATION_AUTHORIZED=YES`, later packages may change
`demo_power_fan_catalog.py`, assembler fan demo leaves,
Aily `prepare_power_fan_catalog_inputs` / captions / MCP copy,
`docs/contracts/aily/v1.6/**`, and
`docs/runbooks/v16-doubao-aily-connector.md`.
Do not edit frozen `docs/contracts/aily/v1.5/**`, `docs/contracts/aily/v1.3/**`,
ADR-028 body, ADR-035 body, or ADR-037 body.
Do not change `power.py` fan defaults or `CALCULATOR_VERSION`.
