# ADR-041: Freeze the per-zone minimum cooling-estimation basis

- **Status:** V1.9 P0 contract frozen; separately authorized P1 implementation
  merged through PR #254; release closure pending
- **Date:** 2026-09-07
- **Direction:** `PER_ZONE_COOLING_ESTIMATION_BASIS`
- **Authority:** `CHARLES_CONFIRMED_ENGINEERING_REFERENCE`
- **Companion:** `docs/tasks/V1_9-version-plan.md` and
  `docs/tasks/V1_9-P0-per-zone-cooling-estimation-basis-contract.md`

## Context

The existing zone planner is the authoritative source for the zone identity,
final pre-cooling position count, and planned area. Its zone rows expose
`position_count` and `required_area_m2`; pre-cooling rows also expose the
intermediate `raw_position_count`. The repository therefore needs an explicit
contract before any future consumer can express a per-zone cooling reference.

This ADR freezes a **minimum estimated cooling load** basis only. It does not
claim an exact cooling load, a final design cooling load, a formal thermal load,
or a precise heat load calculation. The computed
`minimum_estimated_cooling_load_kw_r` equals the frozen reference basis. A
future selected or design capacity must be **not less than** that minimum.

## Decision

### 1. Reuse the existing zone-plan lineage

The contract reads `zone_plan.result.zones[]` and keeps the current runtime
schema unchanged:

- `zone_code` selects one of the nine frozen rules.
- Pre-cooling rules use the final `position_count`.
- Area rules use `required_area_m2` with semantic `PLANNED_ZONE_AREA`.
- `raw_position_count` is never a permitted basis.

No processing-plant building area, replacement field, geometry derivation, or
new runtime input is introduced by this ADR.

### 2. Freeze the nine reference-factor rules

| Zone code | Basis | Reference factor |
| --- | --- | --- |
| `primary_precooling_room` | `position_count` | 20 kW(r)/final position |
| `secondary_precooling_room` | `position_count` | 15 kW(r)/final position |
| `raw_fruit_buffer` | `required_area_m2` | 400 W/m² |
| `sorting_packaging_room` | `required_area_m2` | 300 W/m² |
| `coating_room` | `required_area_m2` | 300 W/m² |
| `finished_goods_room` | `required_area_m2` | 300 W/m² |
| `secondary_fruit_buffer` | `required_area_m2` | 400 W/m² |
| `frozen_fruit_room` | `required_area_m2` | 550 W/m² |
| `shipping_channel` | `required_area_m2` | 300 W/m² |

The canonical reference expressions are `position_count * 20`,
`position_count * 15`, and `required_area_m2 * 0.40`, `* 0.30`, `* 0.30`,
`* 0.30`, `* 0.40`, `* 0.55`, `* 0.30`, respectively. The machine-readable
schema names their two fields `reference_factor` and `reference_factor_unit`.
Each rule carries `requires_review=true` to preserve manual engineering review;
this does not mean the contract is unfrozen or the result is invalid. The
expressions are reference bases, not an authorization to recut `cooling_load`.

The semantic layers are deliberately separate:

```text
ENGINEERING_REFERENCE:
required cooling capacity >= frozen reference basis

COMPUTED_MINIMUM_VALUE:
minimum_estimated_cooling_load_kw_r = frozen reference basis
```

In a future separately authorized design or selection flow,
`future_selected_or_design_cooling_capacity >= minimum_estimated_cooling_load_kw_r`
may be required. This is not a new runtime field or an equipment-selection
algorithm in this P0.

### 3. Fail closed instead of guessing

Any missing `position_count`, missing `required_area_m2`, unmapped
`zone_code`, or missing reference factor fails closed. Future implementation
must not fall back to `raw_position_count`, a demo thermal catalog,
`U × A × ΔT`, product sensible heat, an infiltration model, legacy cooling
output, AI-guessed values, or arbitrary defaults.

### 4. Keep the authorization boundary explicit

The following are true for this P0:

```text
EXISTING_ZONE_PLAN_REUSE=YES
USER_CONFIRMED_ESTIMATION_REFERENCE=YES
MINIMUM_ESTIMATE_SEMANTICS=YES
RUNTIME_IMPLEMENTATION_AUTHORIZED=NO
DETAILED_THERMAL_LOAD_ALGORITHM_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT_AUTHORIZED=NO
EQUIPMENT_SELECTION_RECUT_AUTHORIZED=NO
INSTALLED_POWER_RECUT_AUTHORIZED=NO
INVESTMENT_RECUT_AUTHORIZED=NO
FRONTEND_IMPLEMENTATION_AUTHORIZED=NO
```

Only documentation and an architecture contract test are in scope. A passing
test, a pushed branch, or a Draft PR cannot be interpreted as authorization for
P1 or runtime work.

### 5. Record the relationship to PR #252

PR #252 remains a Draft and is not merged, closed, marked Ready, pushed to, or
rewritten by this decision. Its formula-audit direction is superseded by this
per-zone minimum-estimation-basis direction, while the PR itself remains
unchanged:

```text
PR_252_FORMULA_AUDIT_DIRECTION=SUPERSEDED_BY_PER_ZONE_COOLING_ESTIMATION_BASIS
PR_252_MERGE_AUTHORIZED=NO
PR_252_CLOSE_AUTHORIZED=NO
PR_252_RUNTIME_IMPLEMENTATION_AUTHORIZED=NO
```

## Consequences

- Reviewers have one auditable matrix for the nine zones and one output semantic.
- Existing zone-plan lineage remains the source of `position_count` and
  `required_area_m2`.
- Missing or unmapped engineering inputs fail closed in any future authorized
  implementation.
- No current calculator output, equipment decision, installed power, investment,
  frontend surface, database schema, or migration changes as a consequence of
  this P0.

## Rejected interpretations

1. Treating `raw_position_count` as the pre-cooling basis.
2. Treating 300 W/m² as the raw-fruit-buffer reference; that historical value is
   obsolete under this contract.
3. Calling the reference an exact/final/formal heat load.
4. Replacing the existing zone-plan area field with a new runtime schema field.
5. Inferring a completed implementation or V1.9 P1 authorization from this
   documentation freeze.

## 6. Separately authorized P1 implementation

The P0 decision above remains historical and frozen. Charles separately
authorized a minimal P1 runtime implementation after P0 was merged. P1 uses a
typed/static runtime registry in
`backend/src/cold_storage/modules/calculations/domain/per_zone_cooling_estimation.py`
and applies it after the existing zone planner has built its rows.

```text
P0_CONTRACT_FROZEN=YES
P1_IMPLEMENTATION_SEPARATELY_AUTHORIZED=YES
V19_P1_IMPLEMENTATION_AUTHORIZED=YES
V19_P1_IMPLEMENTATION_EXECUTED=YES
RUNTIME_RULE_COUNT=9
PRECOOL_SOURCE_FIELD=position_count
AREA_SOURCE_FIELD=required_area_m2
MINIMUM_OUTPUT_FIELD=minimum_estimated_cooling_load_kw_r
PROVENANCE_SURFACE_IMPLEMENTED=YES
REQUIRES_REVIEW_ALL_RULES=YES
AMBIENT_ZONES_ENRICHED=NO
ZONE_PLAN_EXISTING_VALUES_CHANGED=NO
ZONE_PLANNING_ADAPTER_PRESERVES_V19_FIELDS=YES
SOURCE_SNAPSHOT_SCHEMA_PRESERVES_V19_FIELDS=YES
CALCULATION_TYPE_CHANGED=NO
ZONE_PLAN_VERSION_CHANGED=NO
COOLING_LOAD_FORMULA_RECUT=NO
EQUIPMENT_INPUT_CHANGED=NO
POWER_INPUT_CHANGED=NO
INVESTMENT_INPUT_CHANGED=NO
FRONTEND_CHANGED=NO
MIGRATION_CREATED=NO
PR252_STATE_CHANGED=NO
```

The P1 output is an additive minimum-reference surface with provenance. It is
not a detailed thermal algorithm, does not recut `cooling_load`, does not feed
equipment/power/investment sizing, and does not change the five-stage
`CalculationType` graph. PR #254 merged the implementation into
`main@675fa8adfc58e2362101079d83393e90706505b2`; its exact-head CI run
`34113336197` concluded SUCCESS. The report projection regression is closed and
the V0.7 golden controlled evolution is complete. V1.9 release closure remains
separate from downstream selection/display authorization.
