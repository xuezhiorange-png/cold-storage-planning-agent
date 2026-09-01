# V1.9 P0 — Per-zone cooling formula audit surface (definition freeze)

**Status:** Definition freeze — wait for Charles to authorize implementation  
**Authority:** Charles-selected theme in `docs/tasks/V1_9-version-plan.md`  
**Previous release:** `v1.8.0`  
**Base `main` SHA:** `ae3814f`  
**Companion:** `docs/tasks/V1_9-version-plan.md`,
`docs/architecture/ADR-041-per-zone-cooling-formula-audit.md`

```text
TASK=V19_P0_ZONE_FORMULA_AUDIT_R1
GOVERNANCE_OWNER=V1.9
PREVIOUS_RELEASE=v1.8.0
BASE_MAIN_SHA=ae3814f
TARGET_FILE=docs/tasks/V1_9-P0-zone-cooling-formula-audit-contract.md
V19_P0_IMPLEMENTATION_AUTHORIZED=NO
V19_IMPLEMENTATION_AUTHORIZED=NO
COOLING_ZONE_FORMULA_AUDIT_SURFACE=YES
KEEP_COOLING_LOAD_VERSION=YES
DO_NOT_BUMP_COOLING_LOAD_VERSION=YES
FORMULA_RECUT_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT=NO
ZONE_PRODUCT_MASS_CATALOG_RECUT=NO
ZONE_THERMAL_CATALOG_RECUT=NO
KEEP_OPERATOR_SCHEMA=OperatorProcessInputV1@1.1.0
KEEP_CALCULATOR_IDENTITY=cold_room_zone_plan@1.0.0,cooling_load@1.0.0,equipment@1.0.0,installed_power@1.0.0,investment_estimate@1.0.0
KEEP_ZONE_PLAN_VERSION=YES
KEEP_EQUIPMENT_VERSION=YES
KEEP_INSTALLED_POWER_VERSION=YES
KEEP_INVESTMENT_VERSION=YES
AILY_OUTBOUND_LIVE_SESSION=NO
KEEP_AILY_V18_SKILL_FROZEN=YES
KEEP_AILY_V19_SKILL=YES
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

On unmodified `create_app`, after Charles authorizes implementation,
workbench persist and Aily in-memory cooling preview (`persisted: false`)
copy each refrigerated zone's **already-computed** `CalculationStep`
rows (formula + inputs + output) onto the cooling snapshot so operators
can 核算 the formulas beside the V1.7 five components and V1.8 °C / m.

Copy kernel steps. Do **not** recompute `Q = U × A × ΔT`. Do **not**
bump `cooling_load@1.0.0`. Do **not** rewrite formula strings in Vue,
reports, prompts, or Aily. Aily does not import
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
No new KEY. Tonne = per day.

## 3. Snapshot fields (frozen addition after authorization)

Keep V1.7 / V1.8 zone leaves. Add an optional formula-audit collection
on new writes (name frozen here; implementation copies kernel steps):

```text
zone_code
zone_name
step_id
output_name
formula
inputs
output_value
```

Historical snapshots without the collection must still parse
(`extra` fields optional on read; `extra="forbid"` stays). Equipment
lineage still binds on `zone_code` + `subtotal_load_kw_r`.

`formula` and `inputs` are copies of kernel `CalculationStep`. They are
not Vue-derived and not prompt-derived.

Plant-level diversity / design-margin steps may be persisted in the same
collection without `zone_code`, labeled as plant-level.

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

Do not extend `/api/v1/agent/**`. Do not expose `mark_reviewed` /
`approve` as MCP tools.

## 5. Display rules

Workbench and 豆包 `preview_cooling_load` extra tables show the **same**
formula-audit columns. Vue / Aily **render persisted strings**; they
must not contain formula literals such as `U × A × ΔT` or
`m × c × ΔT` in source. Caption must keep V1.5 / V1.7 honesty needles
already required by frozen tests, plus: 分区公式来自内核步骤，未改公式.

## 6. Catalog / formula gates

```text
FORMULA_RECUT_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT=NO
KEEP_COOLING_LOAD_VERSION=YES
ZONE_PRODUCT_MASS_CATALOG_RECUT=NO
ZONE_THERMAL_CATALOG_RECUT=NO
```

Do not retune U values, product mass, air change, diversity, or margin
in this package. V1.8 T/H catalog stays.

## 7. Non-goals

```text
AILY_OUTBOUND_LIVE_SESSION=NO
KEEP_COOLING_LOAD_VERSION=YES
COOLING_ZONE_FORMULA_AUDIT_SURFACE=YES
ZONE_PRODUCT_MASS_CATALOG_RECUT=NO
ZONE_THERMAL_CATALOG_RECUT=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
PRODUCTION_RBAC_CLAIM=NO
AGENT_TO_ENGINEERING_VALUE=NO
DELETE_PATH_A_SAVE_INPUTS=NO
FORMULA_RECUT_AUTHORIZED=NO
```

Do not bump calculator `VERSION`. Do not reopen #11 / #13 / #17 / #176 / #20.
Do not move `v0.9.0` … `v1.8.0`.

## 8. Allowlist

```text
V19_P0_FILE_ALLOWLIST
docs/tasks/V1_9-P0-zone-cooling-formula-audit-contract.md
docs/tasks/V1_9-version-plan.md
docs/architecture/ADR-041-per-zone-cooling-formula-audit.md
docs/TECH_DEBT.md
docs/roadmap/DEVELOPMENT_PLAN.md
docs/audit/current-state.md
docs/audit/gap-analysis.md
docs/tasks/V1_8-version-plan.md
backend/tests/architecture/test_v19_p0_zone_cooling_formula_audit_contract.py
```

After authorization this package copies cooling `CalculationStep` rows
onto the snapshot, aligns workbench and Aily formula-audit tables /
captions, and adds `docs/contracts/aily/v1.9/**` plus
`docs/runbooks/v19-doubao-aily-connector.md`.
Do not edit frozen `docs/contracts/aily/v1.8/**` or `cooling_load.py`
formulas.
