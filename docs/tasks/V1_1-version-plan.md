# V1.1 Overall Version Plan

**Status:** Conversation connector for 豆包工作伙伴 (Feishu Aily)  
**Previous release:** `v1.0.0`  
**Base `main` SHA:** `938002546090ac0ca0932c65c48e83cd107a6702` (`#237`)  
**Base tree:** `49ee3dde429fd00c4ae05a11da96d32227b50400`  
**Authority:** Charles — 先做飞书/豆包接口；吨=每天；豆包理解语义；五个参数调用现有内核，表格回复分区规划

```text
TASK=V11_OVERALL_VERSION_PLAN_R1
GOVERNANCE_OWNER=V1.1
PREVIOUS_RELEASE=v1.0.0
TARGET_FILE=docs/tasks/V1_1-version-plan.md
AILY_INBOUND_ZONE_PLAN_PREVIEW=YES
AILY_OUTBOUND_LIVE_SESSION=NO
FORMULA_RECUT_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT=NO
EQUIPMENT_FORMULA_RECUT=NO
INSTALLED_POWER_FORMULA_RECUT=NO
INVESTMENT_FORMULA_RECUT=NO
DO_NOT_BUMP_ZONE_PLAN_VERSION=YES
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 1. Version identity

V1.1 is a **conversation planning connector**.

A customer talks to 豆包工作伙伴 in ordinary language. 「要建一个多少吨的加工厂」
is only an example utterance — 豆包 owns semantics. Charles 2026-08-28: **吨
always means per day**. 豆包 asks until the five operator KEY are present,
calls this system's kernel, and answers with a table: total area, room
areas, positions / tables / docks.

This system does **not** parse chat. It does **not** let 豆包 invent
square metres.

## 2. Operator KEY (unchanged)

```text
zone_planning_inputs.daily_inbound_mass_kg          kg/day
zone_planning_inputs.finished_storage_days          day
zone_planning_inputs.frozen_storage_days            day
zone_planning_inputs.main_packaging_storage_days    day
zone_planning_inputs.auxiliary_packaging_storage_days  day
```

`OperatorProcessInputV1` schema_version stays `1.1.0`.  
Calculator identity stays `cold_room_zone_plan@1.0.0`.

豆包 converts 吨/天 → kg/day before calling. The connector also accepts an
explicit `t/day` unit and multiplies by 1000 (unit conversion only).

## 3. Conversation flow (locked)

1. User speaks naturally (example only: plant size in 吨).
2. 豆包 treats 吨 as tonnes **per day**, converts to kg/day, and asks until
   the five KEY are present.
3. 豆包 `POST /api/v1/aily/v1/zone-plan` with those KEY — not the chat text.
4. This system runs `cold_room_zone_plan` (same kernel as 工程输入).
5. Response includes `table` + `markdown_table` for 豆包 to show the user.

Missing KEY fail closed with `ask_operator` Chinese prompts. No silent defaults.
This connector does not parse `message` / 口语.

## 4. Packages

| Pkg | Name | Status |
|---|---|---|
| **P0/P1** | Inbound zone-plan connector | Delivered on `main` (`#237`) |
| **P2** | Static 豆包工作伙伴 skill pack (paste-ready) | Delivered on `main` (`#238`) |
| **P3** | Aily connector auth | Delivered on `main` (`#240`) |
| **P4** | Runbook + OpenAPI examples | Delivered on `main` (`#239`) |
| **P5** | MCP Streamable HTTP for 豆包工作伙伴 custom tools | Delivered on `main` (`#243`); tagged `v1.1.0` |
| Later | Outbound live 豆包 session, Feishu tenant skill wiring | `AILY_OUTBOUND_LIVE_SESSION=NO` |
| Later | Cooling/equipment/power/investment formula recut | Not this version |

P0–P5 inbound HTTP, skill, auth, runbook, and Streamable HTTP MCP shipped on
`main` and tagged `v1.1.0`. Feishu 传输方式 must be **Streamable HTTP**
(`POST` JSON-RPC, complete JSON). GET SSE is not the Feishu path and is
unavailable on trycloudflare / 飞书云. Not live Feishu session control.

## 5. Non-goals

```text
AILY_OUTBOUND_LIVE_SESSION=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
COOLING_LOAD_FORMULA_RECUT=NO
EQUIPMENT_FORMULA_RECUT=NO
INSTALLED_POWER_FORMULA_RECUT=NO
INVESTMENT_FORMULA_RECUT=NO
AGENT_TO_ENGINEERING_VALUE=NO
REPORT_FORMULA_RECALCULATION=NO
VUE_ENGINEERING_FORMULAS=NO
MARK_REVIEWED_AS_MODEL_TOOL=NO
EXTEND_API_V1_AGENT_FOR_AILY=NO
```

Issues **#11 / #13 / #17 / #176 / #20 stay CLOSED**. Do not move tags
`v0.9.0` or `v1.0.0`.
