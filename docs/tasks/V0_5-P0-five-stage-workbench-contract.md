# V0.5 P0 Five-Stage Workbench Contract

**Status:** Definition freeze R2 — field-level EngineeringInputBundleV1 + architecture tests
**Authority:** Issue #163 (umbrella), tracked by Issue #167
**Contract definition source SHA:** `eec12b9d1ee956ce9f02e8c92bec32dfcf31308f`
**Target branch:** `cursor/v05-p0-five-stage-contract-6c68`

This document freezes the V0.5 P0 five-stage workbench **contract boundary** only.
It does not authorize P1 backend execution, frontend wiring, scheme/report
integration, migrations, formula recut, tag publication, or Release.

## 0. Contract identity and governance

```text
TASK=V05_P0_FIVE_STAGE_WORKBENCH_CONTRACT_DEFINITION_R2
PARENT_ISSUE=163
P0_TRACKING_ISSUE=167
GOVERNANCE_OWNER=V0.5
BASE_MAIN_SHA=eec12b9d1ee956ce9f02e8c92bec32dfcf31308f
TARGET_BRANCH=cursor/v05-p0-five-stage-contract-6c68
TARGET_FILE=docs/tasks/V0_5-P0-five-stage-workbench-contract.md
TARGET_PR_STATE=DRAFT

CONTRACT_STATUS=DEFINITION_R2_DRAFT_FOR_INDEPENDENT_REVIEW
P0_IMPLEMENTATION_AUTHORIZED=YES
P1_IMPLEMENTATION_AUTHORIZED=NO
P2_IMPLEMENTATION_AUTHORIZED=NO
P3_IMPLEMENTATION_AUTHORIZED=NO
P4_IMPLEMENTATION_AUTHORIZED=NO
P5_IMPLEMENTATION_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P0 freezes identifiers, input-bundle shape, consumer mapping, failure semantics,
and governance truth-up. P0 does **not** change application behavior.

## 1. Objective and non-goals

### 1.1 Objective

Freeze the canonical five-stage engineering chain that V0.5 workbench delivery
must converge on:

```text
zone → cooling_load → equipment → power → investment
```

and the explicit engineering input bundle required to execute that chain without
silent guessing, auto-feed, or supplemental-table masquerading.

### 1.2 Non-goals (hard boundaries)

```text
V05_P1_IMPLEMENTATION_AUTHORIZED=NO
V05_P2_IMPLEMENTATION_AUTHORIZED=NO
V05_P3_IMPLEMENTATION_AUTHORIZED=NO
V05_P4_IMPLEMENTATION_AUTHORIZED=NO
V05_P5_IMPLEMENTATION_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
ZONE_AREA_TO_COOLING_LOAD_AUTO_FEED=NO
LATENT_HUMIDITY_MODEL=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
DEMO_COEFFICIENT_CONFLICT_RESOLUTION=NO
HEAT_EXCHANGER=NO
PRESSURE_DROP=NO
DETAILED_MANUFACTURER_SELECTION=NO
LIVE_MIMO=NO
PRODUCTION_DEPLOYMENT=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
FIELD_EQUIPMENT_CONTROL=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
```

P0 must not:

- implement Transaction B execution on the local workbench path;
- wire workflow/scheme/report consumers to new persistence;
- add migrations or change calculator formulas;
- promote or choose between conflicting demo coefficient values;
- treat `power_configuration` as canonical installed power;
- inject engineering numbers into contract or tests.

## 2. Frozen stage order and canonical calculator identities

### 2.1 Stage order (immutable)

The orchestration DAG stage order is exactly:

| Order | Stage name | Canonical calculator identity |
| --- | --- | --- |
| 1 | `zone` | `cold_room_zone_plan` |
| 2 | `cooling_load` | `cooling_load` |
| 3 | `equipment` | `equipment` |
| 4 | `power` | `installed_power` |
| 5 | `investment` | `investment_estimate` |

Authoritative code registry:

- `backend/src/cold_storage/modules/orchestration/domain/dag.py`
  - `ORCHESTRATION_STAGE_ORDER`
  - `CALCULATOR_BINDINGS`
  - `STAGE_DEPENDENCIES`
  - `STAGE_UPSTREAM_PROVENANCE_KEYS`

No sixth canonical stage, no reordering, and no alternate calculator alias may
satisfy a canonical slot without a later authorized contract amendment.

### 2.2 Stage dependencies (immutable)

```text
zone:           ()
cooling_load:   (zone)
equipment:      (cooling_load)
power:          (equipment)
investment:     (zone, power)
```

Upstream provenance keys per stage must match dependency stages exactly.

### 2.3 Supplemental `power_configuration` boundary

`power_configuration` is a **backward-compatible supplemental/demo table**
produced by the V0.4 local workbench planning helper
(`build_power_configuration`).

Rules:

1. `power_configuration` MUST NOT satisfy the canonical `power` stage slot.
2. `power_configuration` MUST NOT masquerade as `installed_power` in
   orchestration, scheme source binding, workflow authority, or report assembly.
3. Consumers that need canonical installed power MUST read persisted
   `installed_power` calculation runs only.
4. Legacy V0.4 read paths MAY continue to display `power_configuration` for
   backward compatibility, but MUST label it supplemental and MUST NOT treat it
   as the five-stage canonical power result.
5. P0 does not remove `power_configuration`; it freezes the identity separation.

## 3. Versioned engineering input bundle contract

### 3.1 Bundle identity

```text
schema_id: EngineeringInputBundleV1
schema_version: 1.0.0
```

The bundle is the explicit, versioned input authority for a single project
version five-stage execution attempt. It is assembled from persisted project
inputs, coefficient context references, and stage-local payloads. It does not
embed calculator formulas and does not assign engineering values.

### 3.2 Required top-level sections

Every bundle MUST include these sections. Missing **key** parameters MUST fail
closed with structured `MISSING_ENGINEERING_PARAMETER` errors — never silent
defaults or guessed values.

| Section | Purpose | Tentative/missing handling |
| --- | --- | --- |
| `project_version_identity` | `project_id`, `project_version_id`, `version_number`, `version_status`, archive flags, execution actor/correlation | missing identity → fail closed |
| `zone_planning_inputs` | throughput, inventory, storage, precooling, and area planning inputs for `cold_room_zone_plan` | per-field `state`: `provided` \| `tentative` \| `missing` |
| `cooling_load_inputs` | per-zone geometry and thermal inputs for `cooling_load` | MUST NOT auto-feed from zone area; missing geometry/thermal keys → `MISSING_ENGINEERING_PARAMETER` |
| `product_load_inputs` | product temperatures, cooling duration, and product load inputs | missing product temperature or duration → fail closed |
| `equipment_inputs` | temperature-system grouping, counts, and equipment capability inputs | missing grouping/count keys → fail closed |
| `installed_power_inputs` | compressor/fan/ancillary installed-power component inputs for `installed_power` | missing component keys → fail closed |
| `coefficient_context` | coefficient revision/context references, `source_type`, `validity_status`, `requires_review` | demo coefficients remain `source_type=demo`, `validity_status=unverified`, `requires_review=true`; conflicts stay unresolved |
| `units_metadata` | explicit unit for every numeric field | missing unit on required numeric field → fail closed |
| `source_metadata` | provenance source per input group | required for audit display |
| `review_metadata` | review status per input group and overall bundle | tentative inputs MUST surface review warnings |

### 3.3 Per-field metadata (required on bundle leaves)

Each engineering input leaf MUST carry:

```json
{
  "value": "<typed or null>",
  "unit": "<canonical unit string or null when non-numeric>",
  "state": "provided | tentative | missing",
  "source_type": "user | persisted | coefficient | demo",
  "validity_status": "verified | unverified | conflict",
  "requires_review": true
}
```

Rules:

- `state=missing` on a **key** parameter MUST produce
  `MISSING_ENGINEERING_PARAMETER` at execution time.
- `state=tentative` is allowed only for non-blocking display; it MUST NOT be
  promoted to authoritative calculation input without explicit user confirmation
  in a later authorized implementation round.
- Demo/conflicting coefficient values MUST remain marked
  `validity_status=unverified` or `validity_status=conflict` and
  `requires_review=true`. P0 does not resolve demo coefficient conflicts
  documented in `docs/audit/coefficient-inventory.md`.

### 3.4 No auto-feed and no silent derivation

Frozen prohibitions:

```text
ZONE_AREA_TO_COOLING_LOAD_AUTO_FEED=NO
ZONE_AREA_TO_COOLING_LOAD_GEOMETRY_AUTO_FEED=NO
ZONE_RESULT_TO_COOLING_LOAD_GEOMETRY_AUTO_FEED=NO
POWER_CONFIGURATION_TO_INSTALLED_POWER_AUTO_FEED=NO
PERSISTED_UPSTREAM_RESULT_TO_DOWNSTREAM_TYPED_INPUT=YES
DEMO_DEFAULT_TO_AUTHORITATIVE_INPUT=NO
AGENT_TO_ENGINEERING_VALUE=NO
```

**DAG lineage vs auto-feed:** Binding typed downstream inputs from **persisted
upstream calculation results** at execution time (for example
`equipment_inputs.systems[].zones[].design_cooling_load_kw_r` from
`cooling_load` result, or `investment_inputs.total_area_m2` from `zone`
result) is **allowed** when the bundle records explicit lineage confirmation
and upstream `calculation_id` / `result_hash`. Copying zone **area** into
cooling-load **geometry** fields without explicit bundle leaves is **forbidden**.

Cooling-load geometry and thermal inputs MUST be explicitly provided in
`cooling_load_inputs`. Zone-planning outputs MAY be displayed for guidance but
MUST NOT silently populate cooling-load required fields.

### 3.5 Bundle versioning and compatibility

- `schema_version` bump requires a new contract amendment and architecture tests.
- Readers MUST reject unknown `schema_version` values fail-closed.
- SQLite and PostgreSQL consumers MUST accept the same bundle JSON shape; only
  persistence mechanics differ.

### 3.6 A. Per-field inventory — `EngineeringInputBundleV1FieldInventory`

Authoritative calculator input shapes:

| Stage | Domain type | Projection required keys (`production_calculation/projection.py`) |
| --- | --- | --- |
| `zone` | `ColdRoomZonePlanInput` | `daily_inbound_mass_kg`, `working_time_h_per_day`, `finished_storage_days`, `packaging_storage_days`, `precooling_required_ratio` |
| `cooling_load` | `CoolingLoadCalcInput` / `ZoneCoolingLoadInput` | `zones`, `coefficients` |
| `equipment` | `EquipmentCapabilityCalcInput` | `systems`, `coefficients` |
| `power` | `InstalledPowerCalcInput` | `compressor_input_power_kw_e`, `evaporator_fan_power_kw_e`, `condenser_fan_power_kw_e` |
| `investment` | `InvestmentEstimateInput` | `total_area_m2`, `refrigerated_area_m2`, `frozen_area_m2`, `position_count`, `total_power_kw` |

Leaf metadata shape (§3.3) applies to every row below. `required=key` means the
bundle layer MUST NOT proceed when `state=missing`. Calculator Python defaults
(for example power fields defaulting to `0`) are **not** authorized silent
guesses at the workbench/bundle layer.

```yaml
# EngineeringInputBundleV1FieldInventory
schema_version: "1.0.0"
bundle_root:
  - path: schema_id
    json_type: string
    unit: null
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: verified
    requires_review: false
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: schema_version
    json_type: string
    unit: null
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: verified
    requires_review: false
    fail_closed_code: MISSING_ENGINEERING_PARAMETER

project_version_identity:
  - path: project_version_identity.project_id
    json_type: string
    unit: null
    required: key
    state_if_absent: missing
    source_type: persisted
    validity_status: verified
    requires_review: false
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: project_version_identity.project_version_id
    json_type: string
    unit: null
    required: key
    state_if_absent: missing
    source_type: persisted
    validity_status: verified
    requires_review: false
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: project_version_identity.version_number
    json_type: integer
    unit: null
    required: key
    state_if_absent: missing
    source_type: persisted
    validity_status: verified
    requires_review: false
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: project_version_identity.version_status
    json_type: string
    unit: null
    required: key
    state_if_absent: missing
    source_type: persisted
    validity_status: verified
    requires_review: false
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: project_version_identity.is_archived
    json_type: boolean
    unit: null
    required: key
    state_if_absent: missing
    source_type: persisted
    validity_status: verified
    requires_review: false
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: project_version_identity.actor_principal
    json_type: string
    unit: null
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: verified
    requires_review: false
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: project_version_identity.correlation_id
    json_type: string
    unit: null
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: verified
    requires_review: false
    fail_closed_code: MISSING_ENGINEERING_PARAMETER

zone_planning_inputs:
  - path: zone_planning_inputs.daily_inbound_mass_kg
    json_type: number
    unit: kg/day
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: zone_planning_inputs.working_time_h_per_day
    json_type: number
    unit: h/day
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: zone_planning_inputs.finished_storage_days
    json_type: number
    unit: day
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: zone_planning_inputs.packaging_storage_days
    json_type: number
    unit: day
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: zone_planning_inputs.precooling_required_ratio
    json_type: number
    unit: ratio
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: zone_planning_inputs.raw_holding_hours
    json_type: number
    unit: h
    required: optional
    state_if_absent: tentative
    source_type: demo
    validity_status: unverified
    requires_review: true
    fail_closed_code: null
  - path: zone_planning_inputs.storage_position_capacity_kg
    json_type: number
    unit: kg
    required: optional
    state_if_absent: tentative
    source_type: demo
    validity_status: conflict
    requires_review: true
    fail_closed_code: null

cooling_load_inputs:
  - path: cooling_load_inputs.zones
    json_type: array
    unit: null
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: cooling_load_inputs.coefficients
    json_type: object
    unit: null
    required: key
    state_if_absent: missing
    source_type: coefficient
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: cooling_load_inputs.zones[].zone_code
    json_type: string
    unit: null
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: cooling_load_inputs.zones[].zone_name
    json_type: string
    unit: null
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: cooling_load_inputs.zones[].temperature_level
    json_type: string
    unit: null
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: cooling_load_inputs.zones[].zone_area
    json_type: number
    unit: m2
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: cooling_load_inputs.zones[].room_height
    json_type: number
    unit: m
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: cooling_load_inputs.zones[].wall_area
    json_type: number
    unit: m2
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: cooling_load_inputs.zones[].roof_area
    json_type: number
    unit: m2
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: cooling_load_inputs.zones[].floor_area
    json_type: number
    unit: m2
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: cooling_load_inputs.zones[].outdoor_design_temperature
    json_type: number
    unit: C
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: cooling_load_inputs.zones[].room_design_temperature
    json_type: number
    unit: C
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: cooling_load_inputs.zones[].operating_hours_per_day
    json_type: number
    unit: h/day
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: cooling_load_inputs.zones[].u_value_wall
    json_type: number
    unit: W/(m2·K)
    required: optional
    state_if_absent: missing
    source_type: coefficient
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: cooling_load_inputs.zones[].u_value_roof
    json_type: number
    unit: W/(m2·K)
    required: optional
    state_if_absent: missing
    source_type: coefficient
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: cooling_load_inputs.zones[].u_value_floor
    json_type: number
    unit: W/(m2·K)
    required: optional
    state_if_absent: missing
    source_type: coefficient
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: cooling_load_inputs.zones[].product_mass_per_day
    json_type: number
    unit: kg/day
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: cooling_load_inputs.zones[].product_entry_temperature
    json_type: number
    unit: C
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: cooling_load_inputs.zones[].product_target_temperature
    json_type: number
    unit: C
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: cooling_load_inputs.zones[].cooling_duration
    json_type: number
    unit: h
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: cooling_load_inputs.zones[].product_specific_heat
    json_type: number
    unit: kJ/(kg·K)
    required: optional
    state_if_absent: missing
    source_type: coefficient
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER

equipment_inputs:
  - path: equipment_inputs.systems
    json_type: array
    unit: null
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: equipment_inputs.coefficients
    json_type: object
    unit: null
    required: key
    state_if_absent: missing
    source_type: coefficient
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: equipment_inputs.systems[].system_code
    json_type: string
    unit: null
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: equipment_inputs.systems[].system_name
    json_type: string
    unit: null
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: equipment_inputs.systems[].design_evaporating_temperature
    json_type: number
    unit: C
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: equipment_inputs.systems[].zones[].zone_code
    json_type: string
    unit: null
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: equipment_inputs.systems[].zones[].zone_name
    json_type: string
    unit: null
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: equipment_inputs.systems[].zones[].evaporator_count
    json_type: integer
    unit: count
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: equipment_inputs.systems[].zones[].defrost_method
    json_type: string
    unit: null
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: equipment_inputs.systems[].zones[].design_cooling_load_kw_r
    json_type: number
    unit: kW(r)
    required: key
    state_if_absent: missing
    source_type: persisted
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER

installed_power_inputs:
  - path: installed_power_inputs.compressor_input_power_kw_e
    json_type: number
    unit: kW(e)
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: installed_power_inputs.evaporator_fan_power_kw_e
    json_type: number
    unit: kW(e)
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: installed_power_inputs.condenser_fan_power_kw_e
    json_type: number
    unit: kW(e)
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: installed_power_inputs.pump_power_kw_e
    json_type: number
    unit: kW(e)
    required: optional
    state_if_absent: tentative
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: null
  - path: installed_power_inputs.defrost_power_kw_e
    json_type: number
    unit: kW(e)
    required: optional
    state_if_absent: tentative
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: null
  - path: installed_power_inputs.processing_equipment_power_kw_e
    json_type: number
    unit: kW(e)
    required: optional
    state_if_absent: tentative
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: null
  - path: installed_power_inputs.lighting_power_kw_e
    json_type: number
    unit: kW(e)
    required: optional
    state_if_absent: tentative
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: null
  - path: installed_power_inputs.other_auxiliary_power_kw_e
    json_type: number
    unit: kW(e)
    required: optional
    state_if_absent: tentative
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: null

investment_inputs:
  - path: investment_inputs.total_area_m2
    json_type: number
    unit: m2
    required: key
    state_if_absent: missing
    source_type: persisted
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: investment_inputs.refrigerated_area_m2
    json_type: number
    unit: m2
    required: key
    state_if_absent: missing
    source_type: persisted
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: investment_inputs.frozen_area_m2
    json_type: number
    unit: m2
    required: key
    state_if_absent: missing
    source_type: persisted
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: investment_inputs.position_count
    json_type: integer
    unit: count
    required: key
    state_if_absent: missing
    source_type: persisted
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: investment_inputs.total_power_kw
    json_type: number
    unit: kW(e)
    required: key
    state_if_absent: missing
    source_type: persisted
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER

coefficient_context:
  - path: coefficient_context.coefficient_context_id
    json_type: string
    unit: null
    required: key
    state_if_absent: missing
    source_type: coefficient
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: coefficient_context.approved_revision_ids
    json_type: array
    unit: null
    required: key
    state_if_absent: missing
    source_type: coefficient
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: coefficient_context.demo_coefficient_leaves[]
    json_type: object
    unit: null
    required: optional
    state_if_absent: missing
    source_type: demo
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER

units_metadata:
  - path: units_metadata.leaf_unit_by_path
    json_type: object
    unit: null
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: verified
    requires_review: false
    fail_closed_code: MISSING_ENGINEERING_PARAMETER

source_metadata:
  - path: source_metadata.input_group_provenance
    json_type: object
    unit: null
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: verified
    requires_review: false
    fail_closed_code: MISSING_ENGINEERING_PARAMETER

review_metadata:
  - path: review_metadata.overall_requires_review
    json_type: boolean
    unit: null
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
  - path: review_metadata.per_group_requires_review
    json_type: object
    unit: null
    required: key
    state_if_absent: missing
    source_type: user
    validity_status: unverified
    requires_review: true
    fail_closed_code: MISSING_ENGINEERING_PARAMETER
```

**U-value / specific-heat rule:** For each optional envelope or product
coefficient leaf (`u_value_*`, `product_specific_heat`), the bundle MUST provide
either an explicit leaf with `state=provided` **or** a resolvable
`coefficient_context` entry. Missing **both** MUST fail closed with
`MISSING_ENGINEERING_PARAMETER`. Demo coefficient conflicts documented in
`docs/audit/coefficient-inventory.md` MUST NOT be silently resolved.

### 3.7 B. Complete positive example — `EngineeringInputBundleV1PositiveExample`

```json
{
  "schema_id": "EngineeringInputBundleV1",
  "schema_version": "1.0.0",
  "project_version_identity": {
    "project_id": { "value": "<PROVIDED>", "unit": null, "state": "provided", "source_type": "persisted", "validity_status": "verified", "requires_review": false },
    "project_version_id": { "value": "<PROVIDED>", "unit": null, "state": "provided", "source_type": "persisted", "validity_status": "verified", "requires_review": false },
    "version_number": { "value": "<PROVIDED>", "unit": null, "state": "provided", "source_type": "persisted", "validity_status": "verified", "requires_review": false },
    "version_status": { "value": "<PROVIDED>", "unit": null, "state": "provided", "source_type": "persisted", "validity_status": "verified", "requires_review": false },
    "is_archived": { "value": false, "unit": null, "state": "provided", "source_type": "persisted", "validity_status": "verified", "requires_review": false },
    "actor_principal": { "value": "<PROVIDED>", "unit": null, "state": "provided", "source_type": "user", "validity_status": "verified", "requires_review": false },
    "correlation_id": { "value": "<PROVIDED>", "unit": null, "state": "provided", "source_type": "user", "validity_status": "verified", "requires_review": false }
  },
  "zone_planning_inputs": {
    "daily_inbound_mass_kg": { "value": "<PROVIDED>", "unit": "kg/day", "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
    "working_time_h_per_day": { "value": "<PROVIDED>", "unit": "h/day", "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
    "finished_storage_days": { "value": "<PROVIDED>", "unit": "day", "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
    "packaging_storage_days": { "value": "<PROVIDED>", "unit": "day", "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
    "precooling_required_ratio": { "value": "<PROVIDED>", "unit": "ratio", "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true }
  },
  "cooling_load_inputs": {
    "zones": [
      {
        "zone_code": { "value": "<PROVIDED>", "unit": null, "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
        "zone_name": { "value": "<PROVIDED>", "unit": null, "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
        "temperature_level": { "value": "<PROVIDED>", "unit": null, "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
        "zone_area": { "value": "<PROVIDED>", "unit": "m2", "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
        "room_height": { "value": "<PROVIDED>", "unit": "m", "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
        "wall_area": { "value": "<PROVIDED>", "unit": "m2", "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
        "roof_area": { "value": "<PROVIDED>", "unit": "m2", "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
        "floor_area": { "value": "<PROVIDED>", "unit": "m2", "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
        "outdoor_design_temperature": { "value": "<PROVIDED>", "unit": "C", "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
        "room_design_temperature": { "value": "<PROVIDED>", "unit": "C", "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
        "operating_hours_per_day": { "value": "<PROVIDED>", "unit": "h/day", "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
        "product_mass_per_day": { "value": "<PROVIDED>", "unit": "kg/day", "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
        "product_entry_temperature": { "value": "<PROVIDED>", "unit": "C", "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
        "product_target_temperature": { "value": "<PROVIDED>", "unit": "C", "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
        "cooling_duration": { "value": "<PROVIDED>", "unit": "h", "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true }
      }
    ],
    "coefficients": { "value": "<PROVIDED>", "unit": null, "state": "provided", "source_type": "coefficient", "validity_status": "unverified", "requires_review": true }
  },
  "equipment_inputs": {
    "systems": [
      {
        "system_code": { "value": "<PROVIDED>", "unit": null, "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
        "system_name": { "value": "<PROVIDED>", "unit": null, "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
        "design_evaporating_temperature": { "value": "<PROVIDED>", "unit": "C", "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
        "zones": [
          {
            "zone_code": { "value": "<PROVIDED>", "unit": null, "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
            "zone_name": { "value": "<PROVIDED>", "unit": null, "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
            "evaporator_count": { "value": "<PROVIDED>", "unit": "count", "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
            "defrost_method": { "value": "<PROVIDED>", "unit": null, "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
            "design_cooling_load_kw_r": { "value": "<PROVIDED>", "unit": "kW(r)", "state": "provided", "source_type": "persisted", "validity_status": "unverified", "requires_review": true }
          }
        ]
      }
    ],
    "coefficients": { "value": "<PROVIDED>", "unit": null, "state": "provided", "source_type": "coefficient", "validity_status": "unverified", "requires_review": true }
  },
  "installed_power_inputs": {
    "compressor_input_power_kw_e": { "value": "<PROVIDED>", "unit": "kW(e)", "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
    "evaporator_fan_power_kw_e": { "value": "<PROVIDED>", "unit": "kW(e)", "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
    "condenser_fan_power_kw_e": { "value": "<PROVIDED>", "unit": "kW(e)", "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true }
  },
  "investment_inputs": {
    "total_area_m2": { "value": "<PROVIDED>", "unit": "m2", "state": "provided", "source_type": "persisted", "validity_status": "unverified", "requires_review": true },
    "refrigerated_area_m2": { "value": "<PROVIDED>", "unit": "m2", "state": "provided", "source_type": "persisted", "validity_status": "unverified", "requires_review": true },
    "frozen_area_m2": { "value": "<PROVIDED>", "unit": "m2", "state": "provided", "source_type": "persisted", "validity_status": "unverified", "requires_review": true },
    "position_count": { "value": "<PROVIDED>", "unit": "count", "state": "provided", "source_type": "persisted", "validity_status": "unverified", "requires_review": true },
    "total_power_kw": { "value": "<PROVIDED>", "unit": "kW(e)", "state": "provided", "source_type": "persisted", "validity_status": "unverified", "requires_review": true }
  },
  "coefficient_context": {
    "coefficient_context_id": { "value": "<PROVIDED>", "unit": null, "state": "provided", "source_type": "coefficient", "validity_status": "unverified", "requires_review": true },
    "approved_revision_ids": { "value": "<PROVIDED>", "unit": null, "state": "provided", "source_type": "coefficient", "validity_status": "unverified", "requires_review": true },
    "demo_coefficient_leaves": [
      { "code": "storage_position_capacity_kg", "value": "<PROVIDED>", "unit": "kg", "state": "provided", "source_type": "demo", "validity_status": "conflict", "requires_review": true }
    ]
  },
  "units_metadata": {
    "leaf_unit_by_path": {
      "zone_planning_inputs.daily_inbound_mass_kg": "kg/day",
      "cooling_load_inputs.zones[0].zone_area": "m2",
      "installed_power_inputs.compressor_input_power_kw_e": "kW(e)"
    }
  },
  "source_metadata": {
    "input_group_provenance": {
      "zone_planning_inputs": "user_entry",
      "cooling_load_inputs": "user_entry",
      "equipment_inputs": "user_entry",
      "installed_power_inputs": "user_entry",
      "investment_inputs": "persisted_upstream_confirmed"
    }
  },
  "review_metadata": {
    "overall_requires_review": { "value": true, "unit": null, "state": "provided", "source_type": "user", "validity_status": "unverified", "requires_review": true },
    "per_group_requires_review": {
      "zone_planning_inputs": true,
      "cooling_load_inputs": true,
      "equipment_inputs": true,
      "installed_power_inputs": true,
      "investment_inputs": true
    }
  }
}
```

### 3.8 C. Negative missing-field examples — `EngineeringInputBundleV1NegativeExamples`

```json
[
  {
    "case_id": "neg_01_missing_zone_daily_inbound",
    "field_path": "zone_planning_inputs.daily_inbound_mass_kg",
    "error_code": "MISSING_ENGINEERING_PARAMETER",
    "description": "Key zone planning throughput field absent or state=missing."
  },
  {
    "case_id": "neg_02_missing_cooling_zone_area",
    "field_path": "cooling_load_inputs.zones[0].zone_area",
    "error_code": "MISSING_ENGINEERING_PARAMETER",
    "description": "Per-zone geometry must be explicit; zone-area auto-feed forbidden."
  },
  {
    "case_id": "neg_03_missing_outdoor_design_temperature",
    "field_path": "cooling_load_inputs.zones[0].outdoor_design_temperature",
    "error_code": "MISSING_ENGINEERING_PARAMETER",
    "description": "Outdoor design temperature is a required thermal input."
  },
  {
    "case_id": "neg_04_missing_product_entry_temperature",
    "field_path": "cooling_load_inputs.zones[0].product_entry_temperature",
    "error_code": "MISSING_ENGINEERING_PARAMETER",
    "description": "Product load in-scope requires explicit product_entry_temperature."
  },
  {
    "case_id": "neg_05_missing_evaporator_count",
    "field_path": "equipment_inputs.systems[0].zones[0].evaporator_count",
    "error_code": "MISSING_ENGINEERING_PARAMETER",
    "description": "Evaporator count must be explicit; inferring from zone area forbidden."
  },
  {
    "case_id": "neg_06_missing_compressor_input_power",
    "field_path": "installed_power_inputs.compressor_input_power_kw_e",
    "error_code": "MISSING_ENGINEERING_PARAMETER",
    "description": "Workbench/bundle layer must not treat calculator default 0 as authorized guess."
  },
  {
    "case_id": "neg_07_missing_investment_total_area",
    "field_path": "investment_inputs.total_area_m2",
    "error_code": "MISSING_ENGINEERING_PARAMETER",
    "description": "Investment key area field absent even if zone result exists without bundle confirmation."
  },
  {
    "case_id": "neg_08_missing_unit_on_required_numeric_leaf",
    "field_path": "cooling_load_inputs.zones[0].zone_area.unit",
    "error_code": "MISSING_ENGINEERING_PARAMETER",
    "description": "Required numeric leaf missing canonical unit string."
  },
  {
    "case_id": "neg_09_unknown_schema_version",
    "field_path": "schema_version",
    "error_code": "MISSING_ENGINEERING_PARAMETER",
    "description": "Unknown schema_version rejected fail-closed."
  },
  {
    "case_id": "neg_10_power_configuration_as_canonical_power",
    "field_path": "canonical_power_slot.calculator_name",
    "error_code": "INVALID_CANONICAL_POWER_SLOT",
    "description": "power_configuration offered as canonical power slot; must be rejected. Only installed_power may satisfy the power stage."
  }
]
```

### 3.9 D. Consumer alias table (freeze target — not implemented in P0)

Documents current `eec12b9d` drift and required canonical mapping after V0.5.
No silent UI-only aliasing. V0.4 persisted rows remain readable additively.

| Consumer | Current identity (`eec12b9d`) | Canonical after V0.5 | Notes |
| --- | --- | --- | --- |
| Workflow `REQUIRED_SCHEME_CALCULATOR_NAMES` (`workflow/domain/steps.py`) | `zone`, `investment`, `cooling_load`, `equipment` | `cold_room_zone_plan`, `cooling_load`, `equipment`, `installed_power`, `investment_estimate` | Missing `installed_power`; uses stage aliases not calculator identities |
| Schemes `_REQUIRED_CALC_TYPES` (`schemes/application/service.py`) | `zone`, `investment`, `cooling_load`, `equipment` | `cold_room_zone_plan`, `cooling_load`, `equipment`, `installed_power`, `investment_estimate` | Same drift as workflow |
| Schemes `_SLOT_CALCULATOR_NAMES` (`source_binding_verifier.py`) | Already canonical five identities | unchanged | Verifier mapping is correct; service gate is not |
| V0.4 workbench persist (`v04_local_sample.py`) | `cold_room_zone_plan`, `investment_estimate`, `power_configuration` | five canonical rows; `power_configuration` supplemental only | Three-row persist is legacy read-compatible only |
| Orchestration DAG (`orchestration/domain/dag.py`) | canonical five stages | unchanged authority | P1+ workbench must converge here |

```text
SILENT_UI_ALIASING=NO
V04_READ_ADDITIVE_ONLY=YES
POWER_CONFIGURATION_SUPPLEMENTAL_ONLY=YES
```

## 4. Execution semantics (contract only — not implemented in P0)

### 4.1 Atomicity

When the five-stage canonical chain executes (future P1+ scope):

1. All five canonical stages MUST succeed, OR
2. No partial five-stage chain is committed.

On any canonical stage failure:

- no partial `SourceBinding` with fewer than five canonical slots;
- no committed attempt in `COMPLETED` disposition with incomplete canonical
  slots;
- caller/session rollback remains the persistence authority (Transaction B
  contract).

`power_configuration` persistence MUST NOT substitute for a failed or skipped
`installed_power` stage.

### 4.2 Idempotency and payload-conflict behavior

Orchestration attempts are idempotent on
`(database_backend, idempotency_key)`:

| Case | Required behavior |
| --- | --- |
| Same key, same payload | return existing attempt outcome; no duplicate commit |
| Same key, different payload | fail closed with explicit conflict; no overwrite |
| Missing `idempotency_key` on new attempt write | invariant violation; fail closed |

Payload sameness is determined by canonical input hash / source snapshot hash,
not by incidental response ordering.

### 4.3 Approved and archived version lock

Five-stage execution and input mutation MUST respect project version lifecycle:

- `APPROVED` versions are immutable for engineering inputs and calculation
  reruns that would change persisted canonical results.
- `ARCHIVED` versions are read-only.
- Violations MUST surface `PROJECT_VERSION_LOCKED` (or equivalent typed error),
  not silent no-ops.

### 4.4 Upstream calculation IDs, result hashes, and stale lineage

Each canonical stage result MUST persist:

- `calculation_id` (stage run identity)
- `result_hash` (canonical hash of typed result snapshot)
- `upstream_calculation_ids` matching `STAGE_UPSTREAM_PROVENANCE_KEYS`

Stale rules:

| Consumer | Stale when |
| --- | --- |
| `cooling_load` | upstream `zone` `calculation_id` or `result_hash` differs from binding |
| `equipment` | upstream `cooling_load` lineage differs |
| `power` | upstream `equipment` lineage differs |
| `investment` | upstream `zone` or `power` lineage differs |
| scheme source binding | any slot hash/identity mismatch vs verifier |
| workflow aggregate | persisted calculation lineage newer than workflow projection inputs |
| report assembly | referenced calculation/report revision lineage no longer current |

Consumers MUST mark results stale and MUST NOT recalculate formulas to refresh
display. Refresh requires a new authorized execution attempt.

## 5. Consumer canonical mapping

Workflow, scheme, and report modules MUST use the **same** canonical stage →
calculator mapping and the **same** `project_id` / `project_version_id`
context.

| Stage | Canonical calculator | MUST NOT accept as canonical substitute |
| --- | --- | --- |
| `zone` | `cold_room_zone_plan` | demo zone helpers |
| `cooling_load` | `cooling_load` | transient demo planning numbers |
| `equipment` | `equipment` | static reference tables |
| `power` | `installed_power` | `power_configuration` |
| `investment` | `investment_estimate` | ad hoc bootstrap investment helpers |

### 5.1 Reports

Reports MUST read persisted calculation results and persisted report revision
metadata. Report templates and assemblers MUST NOT re-derive engineering
formulas or re-run calculators.

### 5.2 Known V0.5 baseline gap (truth-up)

At contract base `eec12b9d`, the **local workbench planning path** persists only:

- `cold_room_zone_plan`
- `investment_estimate`
- `power_configuration`

It does **not** persist the full five-stage canonical chain
(`cooling_load`, `equipment`, `installed_power`). Production orchestration
(Transaction B) can execute all five stages, but workbench/workflow/scheme/report
consumers still use inconsistent identities and snapshot shapes. V0.5 P1+ must
close this gap without breaking V0.4 read compatibility.

## 6. Legacy V0.4 read compatibility

V0.4 local sample and planning-run paths remain readable:

- `GET .../calculations` MAY return the three V0.4 helper calculators.
- Workflow MUST remain fail-closed where canonical five-stage slots are absent.
- New five-stage results MUST be additive; P0/P1 MUST NOT delete V0.4 rows in
  place on approved versions.
- `power_configuration` remains displayable as supplemental/demo power detail.

## 7. Database portability

The contract applies equally to SQLite (local) and PostgreSQL (CI/production
parity paths):

- identical JSON bundle shapes and canonical calculator names;
- identical idempotency and hash semantics;
- dialect-specific persistence is infrastructure-only and MUST NOT change
  contract meaning.

## 8. Authorization boundaries

```text
V05_P0_IMPLEMENTATION_DISPATCH_AUTHORIZED=YES
V05_P1_IMPLEMENTATION_AUTHORIZED=NO
V05_P2_IMPLEMENTATION_AUTHORIZED=NO
V05_P3_IMPLEMENTATION_AUTHORIZED=NO
V05_P4_IMPLEMENTATION_AUTHORIZED=NO
V05_P5_IMPLEMENTATION_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
```

P0 allowlist:

```text
docs/tasks/V0_5-P0-five-stage-workbench-contract.md
docs/audit/current-state.md
docs/audit/gap-analysis.md
docs/audit/validation-baseline.md
docs/TECH_DEBT.md
docs/roadmap/DEVELOPMENT_PLAN.md
backend/tests/architecture/test_v05_p0_contract.py
```

P0 forbidden without separate authorization:

```text
backend/src/cold_storage/modules/calculations/**
backend/src/cold_storage/modules/orchestration/application/transaction_b.py  # behavior change
backend/src/cold_storage/modules/planning/**
backend/src/cold_storage/modules/workflow/**
backend/src/cold_storage/modules/schemes/**
backend/src/cold_storage/modules/reports/**
frontend/**
backend/alembic/**
```

## 9. Acceptance criteria

V0.5 P0 R2 is complete when:

```text
P0_CONTRACT_EXISTS=PASS
ORCHESTRATION_STAGE_ORDER_FROZEN=PASS
CALCULATOR_BINDINGS_FROZEN=PASS
POWER_CONFIGURATION_NOT_CANONICAL=PASS
ENGINEERING_INPUT_BUNDLE_V1_FIELD_INVENTORY=PASS
ENGINEERING_INPUT_BUNDLE_V1_POSITIVE_EXAMPLE=PASS
ENGINEERING_INPUT_BUNDLE_V1_NEGATIVE_EXAMPLES=PASS
CONSUMER_ALIAS_TABLE_FROZEN=PASS
FAIL_CLOSED_AND_NO_AUTO_FEED_DOCUMENTED=PASS
MISSING_ENGINEERING_PARAMETER_DOCUMENTED=PASS
ATOMICITY_IDEMPOTENCY_LINEAGE_DOCUMENTED=PASS
V04_READ_COMPATIBILITY_DOCUMENTED=PASS
SQLITE_POSTGRESQL_PARITY_DOCUMENTED=PASS
WORKBENCH_GAP_TRUTHED=PASS
ARCHITECTURE_TESTS_PASS=PASS
RUFF_PASS=PASS
MYPY_PASS=PASS
CI_GREEN=PASS
MERGE_AUTHORIZED=NO
DRAFT=YES
```

Authoritative architecture test surface:

```text
backend/tests/architecture/test_v05_p0_contract.py
```

## 10. Contract closure state

```text
TASK=V05_P0_FIVE_STAGE_WORKBENCH_CONTRACT_R2
PARENT_ISSUE=163
P0_TRACKING_ISSUE=167
CONTRACT_DEFINITION_SOURCE_SHA=eec12b9d1ee956ce9f02e8c92bec32dfcf31308f
AUTHORIZED_CONTRACT_PATH=docs/tasks/V0_5-P0-five-stage-workbench-contract.md

V05_P0_CONTRACT_FROZEN=YES
V05_P0_IMPLEMENTATION_AUTHORIZED=YES
V05_P0_CONTRACT_EXECUTED=NO
V05_P1_IMPLEMENTATION_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
DRAFT=YES

NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 11. Revision history

| Rev | Date | Change |
| --- | --- | --- |
| R1 | 2026-08-24 | Initial P0 contract freeze at `eec12b9d` |
| R2 | 2026-08-25 | Field-level `EngineeringInputBundleV1` inventory, positive/negative examples, consumer alias table |
