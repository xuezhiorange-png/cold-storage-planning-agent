# V1.1 P0/P1 Aily Zone-Plan Connector Contract

**Status:** Implementation — inbound 豆包工作伙伴 connector  
**Authority:** Charles 2026-08-28: 飞书对接；吨一律按每天（口语举例，勿纠结单位）；豆包负责理解语义；五个参数调用现有内核；表格回复总面积/分区面积/货位  
**Previous release:** `v1.0.0`  
**Base `main` SHA:** `79af2a32a282777ce3d1790106751c2481d81800`  
**Target branch:** `cursor/v11-aily-zone-plan-connector-742e`

Companion: `docs/tasks/V1_1-version-plan.md`,
`docs/architecture/ADR-031-aily-conversation-zone-plan.md`.

## 0. Governance

```text
TASK=V11_P0_AILY_ZONE_PLAN_CONNECTOR_R1
GOVERNANCE_OWNER=V1.1
PREVIOUS_RELEASE=v1.0.0
BASE_MAIN_SHA=79af2a32a282777ce3d1790106751c2481d81800
TARGET_BRANCH=cursor/v11-aily-zone-plan-connector-742e
TARGET_FILE=docs/tasks/V1_1-P0-aily-zone-plan-connector-contract.md

V11_P0_IMPLEMENTATION_AUTHORIZED=YES
AILY_INBOUND_ZONE_PLAN_PREVIEW=YES
AILY_OUTBOUND_LIVE_SESSION=NO
DO_NOT_BUMP_ZONE_PLAN_VERSION=YES
KEEP_CALCULATOR_IDENTITY=cold_room_zone_plan@1.0.0
KEEP_OPERATOR_SCHEMA=OperatorProcessInputV1@1.1.0
FORMULA_RECUT_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT=NO
EQUIPMENT_FORMULA_RECUT=NO
INSTALLED_POWER_FORMULA_RECUT=NO
INVESTMENT_FORMULA_RECUT=NO
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
 → POST /api/v1/aily/v1/zone-plan
 → assemble (existing operator assembler)
 → cold_room_zone_plan kernel (existing adapter)
 → JSON table + markdown_table
```

Vue is unchanged. Reports are unchanged. Five-stage persistence is not
required for this preview. `mark_reviewed` is not exposed.

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

`POST /api/v1/aily/v1/zone-plan`

Not `/api/v1/agent/**`. V0.6 agent routes stay internal compatibility.

Actor is transport `aily-connector`, never model JSON `actor`.

OpenAPI: `docs/contracts/aily/v1.1/aily-to-system-zone-plan.openapi.yaml`

## 4. Non-goals

```text
AILY_OUTBOUND_LIVE_SESSION=NO
COOLING_LOAD_FORMULA_RECUT=NO
EQUIPMENT_FORMULA_RECUT=NO
INSTALLED_POWER_FORMULA_RECUT=NO
INVESTMENT_FORMULA_RECUT=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
PRODUCTION_RBAC_CLAIM=NO
AGENT_TO_ENGINEERING_VALUE=NO
```

Do not bump `cold_room_zone_plan` `VERSION`. Do not restore 基本信息.
Do not reopen #11 / #13 / #17 / #176 / #20. Do not move `v0.9.0` / `v1.0.0`.

## 5. Allowlist (this package)

```text
V11_P0_FILE_ALLOWLIST
docs/tasks/V1_1-P0-aily-zone-plan-connector-contract.md
docs/tasks/V1_1-version-plan.md
docs/architecture/ADR-031-aily-conversation-zone-plan.md
docs/contracts/aily/v1.1/**
docs/TECH_DEBT.md
docs/roadmap/DEVELOPMENT_PLAN.md
docs/audit/current-state.md
docs/audit/gap-analysis.md
docs/audit/validation-baseline.md
backend/src/cold_storage/modules/aily/**
backend/src/cold_storage/bootstrap/app.py
backend/tests/architecture/test_v11_p0_aily_connector_contract.py
backend/tests/unit/test_v11_aily_zone_plan_preview.py
backend/tests/integration/test_v11_aily_zone_plan_http.py
```

`app.py` may only include the Aily router. Do not add a metrics route
template (bounded cardinality cap is already full).

## 6. Expert decisions

| ID | Decision |
| --- | --- |
| V11-E1 | 吨 always means per day; 豆包 owns semantics |
| V11-E2 | Five KEY unchanged |
| V11-E3 | First reply is zone plan table, not cooling/equipment/power/investment |
| V11-E4 | Preview does not persist a project version |
| V11-E5 | Confirmation-before-write from V0.7 P6 remains for later write tools; this preview is a table reply after the user supplied KEY |
| V11-E6 | Feishu tenant skill wiring is later (`AILY_OUTBOUND_LIVE_SESSION=NO`) |

## 7. Closed issues

#11 / #13 / #17 / #176 / #20 stay CLOSED.
