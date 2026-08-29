# V1.2 Overall Version Plan

**Status:** Conversation five-stage preview for 豆包工作伙伴 (Feishu Aily)  
**Previous release:** `v1.1.0`  
**Base `main` SHA:** `93f1a4b`  
**Authority:** Charles — 对话补齐五阶段预览；吨=每天；豆包理解语义；五个 KEY 不变

```text
TASK=V12_OVERALL_VERSION_PLAN_R1
GOVERNANCE_OWNER=V1.2
PREVIOUS_RELEASE=v1.1.0
TARGET_FILE=docs/tasks/V1_2-version-plan.md
AILY_INBOUND_FIVE_STAGE_PREVIEW=YES
AILY_OUTBOUND_LIVE_SESSION=NO
FORMULA_RECUT_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT=NO
EQUIPMENT_FORMULA_RECUT=NO
INSTALLED_POWER_FORMULA_RECUT=NO
INVESTMENT_FORMULA_RECUT=NO
KEEP_ZONE_PLAN_VERSION=YES
KEEP_COOLING_LOAD_VERSION=YES
KEEP_EQUIPMENT_VERSION=YES
KEEP_INSTALLED_POWER_VERSION=YES
KEEP_INVESTMENT_VERSION=YES
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 1. Version identity

V1.2 extends the V1.1 inbound connector with **five-stage conversation preview**.

A customer talks to 豆包工作伙伴. 豆包 collects the five operator KEY, calls
this system's kernels, and answers with tables for zone planning, cooling load,
equipment, installed power, and investment — as separate tools or one
`concept-preview` REST response.

This system does **not** parse chat. It does **not** let 豆包 invent
engineering numbers. Cooling load still uses the **demo envelope catalog**;
`FORMULA_RECUT_AUTHORIZED=NO` — zone surface area is **not** auto-fed into
cooling load.

## 2. Operator KEY (unchanged)

```text
zone_planning_inputs.daily_inbound_mass_kg          kg/day
zone_planning_inputs.finished_storage_days          day
zone_planning_inputs.frozen_storage_days            day
zone_planning_inputs.main_packaging_storage_days    day
zone_planning_inputs.auxiliary_packaging_storage_days  day
```

`OperatorProcessInputV1` schema_version stays `1.1.0`.

Calculator identities stay frozen:

```text
cold_room_zone_plan@1.0.0
cooling_load@1.0.0
equipment@1.0.0
installed_power@1.0.0
investment_estimate@1.0.0
```

## 3. Conversation flow (locked)

1. User speaks naturally; 豆包 treats 吨 as tonnes **per day**.
2. Missing KEY → `ask_operator`; never silently fill.
3. Five KEY present → **first** still `preview_zone_plan` / zone-plan REST.
4. User asks 冷量/设备/功率/投资 → matching new MCP tools or REST
   `concept-preview`; 豆包 shows `markdown_table` verbatim.
5. Every success reply states 概念设计、需复核、演示系数、`requires_review=true`.

## 4. Packages

| Pkg | Name | Status |
|---|---|---|
| **P0** | Freeze contract + ADR-034 | This release |
| **P1** | Application + REST `concept-preview` | This release |
| **P2** | MCP tools (four new + zone) | This release |
| **P3** | v1.2 skill + runbook | This release |
| Later | Outbound live 豆包 session | `AILY_OUTBOUND_LIVE_SESSION=NO` |
| Later | Formula recut / Transaction B chat persistence | Not this version |

V1.1 files under `docs/contracts/aily/v1.1/**` remain frozen.
