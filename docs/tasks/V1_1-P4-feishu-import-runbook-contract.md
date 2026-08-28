# V1.1 P4 Feishu Custom-Connector Import Runbook Contract

**Status:** Implementation — operator runbook for 豆包工作伙伴 custom connector import  
**Authority:** Charles 2026-08-28: parallel V1.1 follow-ups; P4 owns human import steps only  
**Previous release:** `v1.0.0`  
**Base `main` SHA:** `938002546090ac0ca0932c65c48e83cd107a6702`  
**Target branch:** `cursor/v11-p4-feishu-import-runbook-742e`

Companion: `docs/tasks/V1_1-P0-aily-zone-plan-connector-contract.md`,
`docs/contracts/aily/v1.1/README.md`.

## 0. Governance

```text
TASK=V11_P4_FEISHU_IMPORT_RUNBOOK_R1
GOVERNANCE_OWNER=V1.1
PREVIOUS_RELEASE=v1.0.0
BASE_MAIN_SHA=938002546090ac0ca0932c65c48e83cd107a6702
TARGET_BRANCH=cursor/v11-p4-feishu-import-runbook-742e
TARGET_FILE=docs/tasks/V1_1-P4-feishu-import-runbook-contract.md

V11_P4_IMPLEMENTATION_AUTHORIZED=YES
AILY_OUTBOUND_LIVE_SESSION=NO
DO_NOT_BUMP_ZONE_PLAN_VERSION=YES
KEEP_CALCULATOR_IDENTITY=cold_room_zone_plan@1.0.0
FORMULA_RECUT_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT=NO
EQUIPMENT_FORMULA_RECUT=NO
INSTALLED_POWER_FORMULA_RECUT=NO
INVESTMENT_FORMULA_RECUT=NO
AGENT_TO_ENGINEERING_VALUE=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
EXTEND_API_V1_AGENT_FOR_AILY=NO
IMPLEMENT_FEISHU_SDK_OUTBOUND=NO
IMPLEMENT_CONNECTOR_KEY_AUTH_IN_REPO=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 1. Objective

Charles (operator) can follow `docs/runbooks/v11-doubao-aily-connector.md` to:

1. Reach `POST /api/v1/aily/v1/zone-plan` (local or deployed origin).
2. Import `docs/contracts/aily/v1.1/aily-to-system-zone-plan.openapi.yaml` as a
   Feishu Aily / 豆包工作伙伴 **custom connector** in the tenant UI.
3. Map the five OperatorProcessInputV1 KEY; 豆包 converts spoken 吨 (per day) to
   `daily_inbound_mass_kg` in kg/day.
4. Configure 豆包 to send structured KEY JSON, not chat text; on HTTP 400 use
   `ask_operator` from the error body.
5. Render `markdown_table` to the user; mention `extra_tables` and
   `requires_review`.

This package does **not** open a live Feishu outbound session from this repo.

## 2. Operator KEY (unchanged)

```text
zone_planning_inputs.daily_inbound_mass_kg
zone_planning_inputs.finished_storage_days
zone_planning_inputs.frozen_storage_days
zone_planning_inputs.main_packaging_storage_days
zone_planning_inputs.auxiliary_packaging_storage_days
```

Example mapping (illustration only): user says「20 吨/天」→
`daily_inbound_mass_kg=20000` (kg/day). Other four day fields in tests use
7 / 10 / 4 / 12.

## 3. HTTP

`POST /api/v1/aily/v1/zone-plan`

Not `/api/v1/agent/**`. OpenAPI:
`docs/contracts/aily/v1.1/aily-to-system-zone-plan.openapi.yaml`.

Optional later header `X-Aily-Connector-Key` may land in sibling P3; if unset,
connector works without it. P4 does not implement auth.

## 4. Skill references (read-only)

- Skill notes: `docs/contracts/aily/v1.1/README.md` (§ 豆包 skill notes).
- Intended skill pack: `docs/contracts/aily/v1.1/doubao-skill.v1.md` (P2
  artifact; reference even if not merged yet).

## 5. Non-goals

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

Do not bump `cold_room_zone_plan` `VERSION`. Do not reopen #11 / #13 / #17 /
#176 / #20. Do not move `v0.9.0` / `v1.0.0`.

## 6. Allowlist (this package)

```text
V11_P4_FILE_ALLOWLIST
docs/runbooks/v11-doubao-aily-connector.md
docs/tasks/V1_1-P4-feishu-import-runbook-contract.md
docs/contracts/aily/v1.1/aily-to-system-zone-plan.openapi.yaml
backend/tests/architecture/test_v11_p4_feishu_import_runbook.py
```

OpenAPI edits: **examples only** (including 400 `ask_operator` example). Do
not change `operationId`, paths, or calculator identity.

## 7. Expert decisions

| ID | Decision |
| --- | --- |
| V11-P4-E1 | P4 is human Feishu UI import steps; no outbound SDK in repo |
| V11-P4-E2 | 吨 always means per day; 豆包 owns semantics |
| V11-P4-E3 | Five KEY unchanged; flat JSON or envelope per P0 OpenAPI |
| V11-P4-E4 | Concept-design disclaimer; not 施工图 |

## 8. Closed issues

#11 / #13 / #17 / #176 / #20 stay CLOSED.
