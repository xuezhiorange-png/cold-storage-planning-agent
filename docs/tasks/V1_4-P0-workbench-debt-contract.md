# V1.4 P0 — Operator workbench debt TD-023 + TD-008 (definition freeze)

**Status:** Implementation authorized — workbench step recut + operator demo five-KEY authority  
**Authority:** Charles-selected theme in `docs/tasks/V1_4-version-plan.md`  
**Previous release:** `v1.3.0`  
**Base `main` SHA:** `0496010`  
**Companion:** `docs/tasks/V1_4-version-plan.md`,
`docs/architecture/ADR-036-workbench-operator-input-and-demo-defaults.md`

```text
TASK=V14_P0_WORKBENCH_DEBT_R1
GOVERNANCE_OWNER=V1.4
PREVIOUS_RELEASE=v1.3.0
BASE_MAIN_SHA=0496010
TARGET_FILE=docs/tasks/V1_4-P0-workbench-debt-contract.md
V14_P0_IMPLEMENTATION_AUTHORIZED=YES
V14_IMPLEMENTATION_AUTHORIZED=YES
TD023_OPERATOR_PROCESS_INPUT_STEP=YES
TD008_OPERATOR_DEMO_FIVE_KEY_AUTHORITY=YES
TD008_POWER_EQUIPMENT_CATALOG_UNIFIED=NO
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
ENVELOPE_WALL_ROOF_FROM_PLAN=NO
AILY_OUTBOUND_LIVE_SESSION=NO
KEEP_AILY_V13_SKILL=YES
AGENT_TO_ENGINEERING_VALUE=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
MARK_REVIEWED_AS_MODEL_TOOL=NO
EXTEND_API_V1_AGENT_FOR_AILY=NO
DELETE_PATH_A_SAVE_INPUTS=NO
POWER_CONFIGURATION_REPLACES_INSTALLED_POWER=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 1. Objective

On unmodified `create_app`:

1. Guided workflow first step identity is `OPERATOR_PROCESS_INPUT` (operator copy: 工程输入).
2. That step completes only when persisted `OperatorProcessInputV1@1.1.0` five KEY
   are present, or when canonical five-stage runs are complete
   (`five_stage_complete`). V0.4 `save_inputs` alone does **not** complete it.
3. Operator demo five KEY and storage-day defaults have one authority:
   `samples/v09-process-input/manifest.json` (`20000 / 7 / 10 / 4 / 12`).
   Vue must not embed a second numeric set for those leaves.

No formula recut. No outbound session. Aily does not import
`cold_storage.modules.calculations`. Path A `save_inputs` remains mounted.

## 2. Operator KEY (unchanged)

```text
zone_planning_inputs.daily_inbound_mass_kg
zone_planning_inputs.finished_storage_days
zone_planning_inputs.frozen_storage_days
zone_planning_inputs.main_packaging_storage_days
zone_planning_inputs.auxiliary_packaging_storage_days
```

Empty-version missing-input lists stay this five-KEY set. Deleted V0.4 KEY
must not appear as missing.

## 3. Workflow contract (after implementation)

```text
contract_version: WorkflowAggregateV2
first mainline step: OPERATOR_PROCESS_INPUT
next-action label for that step: 完成工程输入
```

Completion of `OPERATOR_PROCESS_INPUT`:

```text
five_stage_complete
  OR persisted OperatorProcessInputV1@1.1.0 five KEY
  OR persisted EngineeringInputBundleV1 zone_planning five KEY
  OR persisted cold_room_zone_plan input_snapshot containing the five KEY
```

Not sufficient: non-empty V0.4 `input_snapshot` from `save_inputs` that is
not one of the shapes above.

`INPUT_COMPLETENESS` uses the same V0.9 five-KEY authority, not
`ProjectService.validate_inputs` (V0.4 required field list).

## 4. Demo defaults (after implementation)

Authority file:

```text
samples/v09-process-input/manifest.json
operator_process_input.zone_planning_inputs
  daily_inbound_mass_kg = 20000 kg/day
  finished_storage_days = 7 day
  frozen_storage_days = 10 day
  main_packaging_storage_days = 4 day
  auxiliary_packaging_storage_days = 12 day
```

Read-only HTTP (no formulas):

```text
GET /api/v1/demo/operator-process-input
source_type=demo
validity_status=unverified
requires_review=true
source=samples/v09-process-input/manifest.json
```

Frontend leftover V0.4 design-input defaults for those leaves must load the
same file (shared typed fixture). The V0.9 工程输入 form stays empty by
default (do not silently fill KEY).

`GET /api/v1/demo/overview` remains a **legacy overview**, not operator
defaults. Do not retune its calculator inputs in this version.

Power / equipment / envelope catalog duplication is **out of this slice**
(`TD008_POWER_EQUIPMENT_CATALOG_UNIFIED=NO`).

## 5. HTTP / MCP (unchanged addresses)

Keep Aily:

```text
POST /api/v1/aily/v1/zone-plan
POST /api/v1/aily/v1/concept-preview
Streamable HTTP  {ORIGIN}/api/v1/aily/v1/mcp/sse
```

Keep tools. Keep V1.3 skill / runbook frozen (`KEEP_AILY_V13_SKILL=YES`).
Do not extend `/api/v1/agent/**`. Keep Path A:

```text
PUT /api/v1/projects/{id}/versions/{n}/inputs
```

## 6. Non-goals

```text
AILY_OUTBOUND_LIVE_SESSION=NO
FORMULA_RECUT_AUTHORIZED=NO
ENVELOPE_WALL_ROOF_FROM_PLAN=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
PRODUCTION_RBAC_CLAIM=NO
AGENT_TO_ENGINEERING_VALUE=NO
DELETE_PATH_A_SAVE_INPUTS=NO
POWER_CONFIGURATION_REPLACES_INSTALLED_POWER=NO
TD008_POWER_EQUIPMENT_CATALOG_UNIFIED=NO
```

Do not bump calculator `VERSION`. Do not reopen #11 / #13 / #17 / #176 / #20.
Do not move `v0.9.0` / `v1.0.0` / `v1.1.0` / `v1.2.0` / `v1.3.0`.

## 7. Allowlist (definition freeze now; code after dispatch)

```text
V14_P0_FILE_ALLOWLIST
docs/tasks/V1_4-P0-workbench-debt-contract.md
docs/tasks/V1_4-version-plan.md
docs/architecture/ADR-036-workbench-operator-input-and-demo-defaults.md
docs/TECH_DEBT.md
docs/roadmap/DEVELOPMENT_PLAN.md
docs/audit/current-state.md
docs/audit/gap-analysis.md
backend/tests/architecture/test_v14_p0_workbench_debt_contract.py
```

After `V14_IMPLEMENTATION_AUTHORIZED=YES`, later packages may add workflow
step vocabulary, workflow evaluation, Vue guidance, operator demo defaults
module / GET route, leftover design-input defaults, and their tests.
Do not edit frozen `docs/contracts/aily/v1.3/**` or ADR-035 body.
