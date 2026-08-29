# V1.2 P0 Aily Five-Stage Conversation Preview Contract

**Status:** Implementation — inbound 豆包工作伙伴 five-stage preview  
**Authority:** Charles 2026-08-29: 对话补齐五阶段预览；吨一律按每天；五个 KEY 不变  
**Previous release:** `v1.1.0`  
**Base `main` SHA:** `93f1a4b`  
**Target branch:** `cursor/v12-five-stage-preview-742e`

Companion: `docs/tasks/V1_2-version-plan.md`,
`docs/architecture/ADR-034-aily-five-stage-conversation-preview.md`.

## 0. Governance

```text
TASK=V12_P0_AILY_FIVE_STAGE_PREVIEW_R1
GOVERNANCE_OWNER=V1.2
PREVIOUS_RELEASE=v1.1.0
BASE_MAIN_SHA=93f1a4b
TARGET_BRANCH=cursor/v12-five-stage-preview-742e
TARGET_FILE=docs/tasks/V1_2-P0-aily-five-stage-preview-contract.md

V12_P0_IMPLEMENTATION_AUTHORIZED=YES
AILY_INBOUND_FIVE_STAGE_PREVIEW=YES
AILY_OUTBOUND_LIVE_SESSION=NO
KEEP_OPERATOR_SCHEMA=OperatorProcessInputV1@1.1.0
KEEP_ZONE_PLAN_VERSION=YES
KEEP_COOLING_LOAD_VERSION=YES
KEEP_EQUIPMENT_VERSION=YES
KEEP_INSTALLED_POWER_VERSION=YES
KEEP_INVESTMENT_VERSION=YES
DO_NOT_BUMP_ZONE_PLAN_VERSION=YES
KEEP_CALCULATOR_IDENTITY=cold_room_zone_plan@1.0.0,cooling_load@1.0.0,equipment@1.0.0,installed_power@1.0.0,investment_estimate@1.0.0
FORMULA_RECUT_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT=NO
EQUIPMENT_FORMULA_RECUT=NO
INSTALLED_POWER_FORMULA_RECUT=NO
INVESTMENT_FORMULA_RECUT=NO
ENVELOPE_FROM_ZONE_AREA=NO
AGENT_TO_ENGINEERING_VALUE=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
MARK_REVIEWED_AS_MODEL_TOOL=NO
EXTEND_API_V1_AGENT_FOR_AILY=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 1. Objective

On unmodified `create_app`:

```text
豆包工作伙伴 (semantic understanding)
 → five OperatorProcessInputV1 KEY
 → preview_zone_plan (first) OR stage tools / concept-preview
 → assemble (existing operator assembler)
 → five preview kernels (existing adapters, in memory)
 → JSON tables + markdown_table per stage
```

This is a **second inbound transport**, not a second kernel. No persist. No
Transaction B. No formula recut.

## 2. Operator KEY

```text
zone_planning_inputs.daily_inbound_mass_kg
zone_planning_inputs.finished_storage_days
zone_planning_inputs.frozen_storage_days
zone_planning_inputs.main_packaging_storage_days
zone_planning_inputs.auxiliary_packaging_storage_days
```

Missing KEY → `MISSING_ENGINEERING_PARAMETER` plus `ask_operator`.

## 3. HTTP

Keep `POST /api/v1/aily/v1/zone-plan`.

Add `POST /api/v1/aily/v1/concept-preview` (one shot, five tables).

Same `X-Aily-Connector-Key` gate as zone-plan. Not `/api/v1/agent/**`.

MCP Streamable HTTP unchanged at `{ORIGIN}/api/v1/aily/v1/mcp/sse`.

## 4. MCP tools

Keep `preview_zone_plan` (first in tools/list).

Add:

```text
preview_cooling_load
preview_equipment
preview_installed_power
preview_investment
```

Same five-KEY inputSchema, `validate_input=False`, same auth.

## 5. Cooling honesty

```text
FORMULA_RECUT_AUTHORIZED=NO
ENVELOPE_FROM_ZONE_AREA=NO
```

Cooling preview uses the existing **demo envelope catalog** (same as workbench).
It does **not** feed zone-planner surface area into cooling load.
API/MCP/skill must state: 冷量仍用演示围护，不是分区面积自动带入.

## 6. Response flags

Every success preview:

```text
persisted: false
requires_review: true
concept-preview additionally:
  envelope_from_zone_area: false
  formula_recut_authorized: false
```

## 7. Non-goals

```text
AILY_OUTBOUND_LIVE_SESSION=NO
COOLING_LOAD_FORMULA_RECUT=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
PRODUCTION_RBAC_CLAIM=NO
AGENT_TO_ENGINEERING_VALUE=NO
```

Do not bump calculator `VERSION` identities. Do not reopen #11 / #13 / #17 /
#176 / #20. Do not move `v0.9.0` / `v1.0.0` / `v1.1.0`.

## 8. Allowlist (this package)

```text
V12_P0_FILE_ALLOWLIST
docs/tasks/V1_2-P0-aily-five-stage-preview-contract.md
docs/tasks/V1_2-version-plan.md
docs/architecture/ADR-034-aily-five-stage-conversation-preview.md
docs/contracts/aily/v1.2/**
docs/runbooks/v12-doubao-aily-connector.md
docs/TECH_DEBT.md
docs/roadmap/DEVELOPMENT_PLAN.md
docs/audit/current-state.md
docs/audit/gap-analysis.md
docs/audit/validation-baseline.md
backend/src/cold_storage/modules/aily/**
backend/tests/architecture/test_v12_p0_aily_five_stage_preview_contract.py
backend/tests/unit/test_v12_aily_*
backend/tests/integration/test_v12_aily_*
```

`app.py` may only include the Aily router. Do not add a metrics route.

## 9. Expert decisions

| ID | Decision |
|---|---|
| V12-E1 | Five-stage preview is inbound transport only; kernels unchanged |
| V12-E2 | 吨 always means per day; 豆包 owns semantics |
| V12-E3 | Cooling demo envelope; `envelope_from_zone_area=false` |
| V12-E4 | `preview_zone_plan` remains first tool and first conversation step |
| V12-E5 | ADR-034 supersedes ADR-033 scope for V1.2 only; ADR-033 file frozen |
