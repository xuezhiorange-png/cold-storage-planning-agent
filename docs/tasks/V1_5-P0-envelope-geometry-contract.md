# V1.5 P0 — Cooling envelope wall/roof from zone geometry (definition freeze)

**Status:** Implementation authorized — envelope wall/roof input lineage only  
**Authority:** Charles-selected theme in `docs/tasks/V1_5-version-plan.md`  
**Previous release:** `v1.4.0`  
**Base `main` SHA:** `c58f0ae`  
**Companion:** `docs/tasks/V1_5-version-plan.md`,
`docs/architecture/ADR-037-envelope-wall-roof-from-zone-geometry.md`

```text
TASK=V15_P0_ENVELOPE_GEOMETRY_R1
GOVERNANCE_OWNER=V1.5
PREVIOUS_RELEASE=v1.4.0
BASE_MAIN_SHA=c58f0ae
TARGET_FILE=docs/tasks/V1_5-P0-envelope-geometry-contract.md
V15_P0_IMPLEMENTATION_AUTHORIZED=YES
V15_IMPLEMENTATION_AUTHORIZED=YES
FORMULA_RECUT_AUTHORIZED=YES
COOLING_LOAD_FORMULA_RECUT=envelope_wall_roof_geometry_only
ENVELOPE_WALL_ROOF_FROM_PLAN=YES
ENVELOPE_FROM_ZONE_AREA=floor_wall_roof_from_plan
KEEP_COOLING_LOAD_VERSION=YES
KEEP_OPERATOR_SCHEMA=OperatorProcessInputV1@1.1.0
KEEP_ZONE_PLAN_VERSION=YES
KEEP_EQUIPMENT_VERSION=YES
KEEP_INSTALLED_POWER_VERSION=YES
KEEP_INVESTMENT_VERSION=YES
KEEP_CALCULATOR_IDENTITY=cold_room_zone_plan@1.0.0,cooling_load@1.0.0,equipment@1.0.0,installed_power@1.0.0,investment_estimate@1.0.0
DO_NOT_BUMP_ZONE_PLAN_VERSION=YES
DO_NOT_BUMP_COOLING_LOAD_VERSION=YES
AILY_OUTBOUND_LIVE_SESSION=NO
KEEP_AILY_V13_SKILL_FROZEN=YES
TD008_POWER_EQUIPMENT_CATALOG_UNIFIED=NO
EQUIPMENT_FORMULA_RECUT=NO
INSTALLED_POWER_FORMULA_RECUT=NO
INVESTMENT_FORMULA_RECUT=NO
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

On unmodified `create_app`, after zone-plan `required_area_m2` binds into
cooling `floor_area` / `zone_area`, the **same shared binder** writes:

```text
roof_area  = floor_area
wall_area  = room_height × 4 × √floor_area
```

Workbench five-stage persist and Aily in-memory preview (`persisted: false`)
use that binder. Assembler catalog `wall_area=200` / `roof_area=100` are
**not** authority after bind. `room_height` stays v05 catalog `5.0` m.
Missing `room_height` fail-closed. Ambient `常温` zones stay skipped.

Do **not** change `Q = U × A × ΔT` in `cooling_load.py`. Do **not** bump
`cooling_load@1.0.0`. Aily does not import `cold_storage.modules.calculations`.

## 2. Operator KEY (unchanged)

```text
zone_planning_inputs.daily_inbound_mass_kg
zone_planning_inputs.finished_storage_days
zone_planning_inputs.frozen_storage_days
zone_planning_inputs.main_packaging_storage_days
zone_planning_inputs.auxiliary_packaging_storage_days
```

Missing KEY → `MISSING_ENGINEERING_PARAMETER` plus `ask_operator`.
No new KEY for perimeter. Tonne = per day.

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
envelope_wall_roof_from_plan: true
formula_recut_authorized: true
```

Skill / table caption: 地板、墙、屋面来自分区几何（正方形平面 + 演示层高）；U 值与设计温度仍为演示目录，需复核.

Demo geometry assumption: `source_type=demo`, `validity_status=unverified`,
`requires_review=true`. U-values remain demo catalog.

V1.3 flags `envelope_wall_roof_from_plan: false` and
`formula_recut_authorized: false` are **superseded on the V1.5 success path**.
V1.3 skill and runbook stay frozen as historical.

## 5. Geometry (frozen)

| Leaf | Source |
|---|---|
| `floor_area` / `zone_area` | zone `required_area_m2` |
| `roof_area` | `= floor_area` (single-story) |
| `wall_area` | `= room_height × 4 × √floor_area` (square plan) |
| `room_height` | demo catalog `5.0` m |
| `u_value_*`, design temperatures, product thermal | demo / coefficient catalog |

Rejected: `wall = floor × height` (ADR-035). Missing height must not be guessed.

## 6. Non-goals

```text
AILY_OUTBOUND_LIVE_SESSION=NO
KEEP_COOLING_LOAD_VERSION=YES
TD008_POWER_EQUIPMENT_CATALOG_UNIFIED=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
PRODUCTION_RBAC_CLAIM=NO
AGENT_TO_ENGINEERING_VALUE=NO
DELETE_PATH_A_SAVE_INPUTS=NO
```

Do not bump calculator `VERSION`. Do not reopen #11 / #13 / #17 / #176 / #20.
Do not move `v0.9.0` / `v1.0.0` / `v1.1.0` / `v1.2.0` / `v1.3.0` / `v1.4.0`.

## 7. Allowlist (definition freeze now; code in P1–P3)

```text
V15_P0_FILE_ALLOWLIST
docs/tasks/V1_5-P0-envelope-geometry-contract.md
docs/tasks/V1_5-version-plan.md
docs/architecture/ADR-037-envelope-wall-roof-from-zone-geometry.md
docs/TECH_DEBT.md
docs/roadmap/DEVELOPMENT_PLAN.md
docs/audit/current-state.md
docs/audit/gap-analysis.md
docs/tasks/V1_4-version-plan.md
backend/tests/architecture/test_v15_p0_envelope_geometry_contract.py
```

After `V15_IMPLEMENTATION_AUTHORIZED=YES`, later packages may change
`preview_lineage_bind.py`, assembler wall/roof pending leaves,
Aily flags/captions, `docs/contracts/aily/v1.5/**`, and
`docs/runbooks/v15-doubao-aily-connector.md`.
Do not edit frozen `docs/contracts/aily/v1.3/**`, ADR-028 body, or ADR-035 body.
