# V1.9 P1 — 逐区域最低冷量估算运行时实现

**状态：** P1 runtime implementation is complete and merged through PR #254
into `main@675fa8adfc58e2362101079d83393e90706505b2`; the report projection
regression is closed and V1.9 is in release-closure state.
**Task:** `V19_P1_PER_ZONE_COOLING_ESTIMATION_IMPLEMENTATION_R1`
**Mode:** `MINIMAL_RUNTIME_IMPLEMENTATION`
**Authority:** `CHARLES_CONFIRMED_ENGINEERING_REFERENCE`
**Merged main:** `main@675fa8adfc58e2362101079d83393e90706505b2`，tree
`71e726710d7df97fb6c2ea1b8e8cfbe080c232f9`

P0 的九条规则继续是唯一工程参考依据。P0 文档保持历史事实，其中
`RUNTIME_IMPLEMENTATION_AUTHORIZED=NO` 仍然不变；本文件记录 Charles 对 P1
运行时实现的单独授权与实际边界。

```text
P0_CONTRACT_FROZEN=YES
P1_IMPLEMENTATION_SEPARATELY_AUTHORIZED=YES
V19_P1_IMPLEMENTATION_AUTHORIZED=YES
V19_P1_IMPLEMENTATION_EXECUTED=YES
RUNTIME_RULE_COUNT=9
MINIMUM_OUTPUT_FIELD=minimum_estimated_cooling_load_kw_r
PRECOOL_SOURCE_FIELD=position_count
AREA_SOURCE_FIELD=required_area_m2
RAW_POSITION_COUNT_USED=NO
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
P1_IMPLEMENTATION_MERGED=YES
PR254_MERGED=YES
PR254_EXACT_HEAD_CI_RUN=34113336197
PR254_EXACT_HEAD_CI=SUCCESS
REPORT_PROJECTION_REGRESSION=CLOSED
V07_GOLDEN_EVOLUTION=COMPLETE
V19_STATUS=IMPLEMENTATION_COMPLETE
V1_9_0_RELEASE_READY=YES
NEXT_FEATURE_LANE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 1. Runtime boundary

The implementation lives in the pure domain module
`backend/src/cold_storage/modules/calculations/domain/per_zone_cooling_estimation.py`.
It owns a typed/static registry named
`PER_ZONE_COOLING_ESTIMATION_RULES`. Runtime code does not parse the P0 Markdown
or JSON; the architecture test compares the registry with the P0 machine-readable
contract.

`ColdRoomZonePlanner` first completes the existing zone rows and then applies
the estimator as an additive enrichment. The estimator reads only the existing
canonical `position_count` or `required_area_m2`; it does not recalculate either
field, change zone order, alter schemes, or create a sixth calculation stage.
`CalculationType` remains the existing five-stage enum:

```text
ZONE → COOLING_LOAD → EQUIPMENT → POWER → INVESTMENT
```

The zone-plan calculator identity remains `cold_room_zone_plan@1.0.0`.

## 2. Frozen nine-zone registry

| `zone_code` | Basis | Source | Reference factor | Minimum expression |
| --- | --- | --- | --- | --- |
| `primary_precooling_room` | `FINAL_POSITION_COUNT` | `position_count` | 20 kW(r)/final position | `position_count * 20` |
| `secondary_precooling_room` | `FINAL_POSITION_COUNT` | `position_count` | 15 kW(r)/final position | `position_count * 15` |
| `raw_fruit_buffer` | `ZONE_AREA` | `required_area_m2` | 400 W/m² | `required_area_m2 * 0.40` |
| `sorting_packaging_room` | `ZONE_AREA` | `required_area_m2` | 300 W/m² | `required_area_m2 * 0.30` |
| `coating_room` | `ZONE_AREA` | `required_area_m2` | 300 W/m² | `required_area_m2 * 0.30` |
| `finished_goods_room` | `ZONE_AREA` | `required_area_m2` | 300 W/m² | `required_area_m2 * 0.30` |
| `secondary_fruit_buffer` | `ZONE_AREA` | `required_area_m2` | 400 W/m² | `required_area_m2 * 0.40` |
| `frozen_fruit_room` | `ZONE_AREA` | `required_area_m2` | 550 W/m² | `required_area_m2 * 0.55` |
| `shipping_channel` | `ZONE_AREA` | `required_area_m2` | 300 W/m² | `required_area_m2 * 0.30` |

All nine rules carry:

```text
authority_source=CHARLES_CONFIRMED_ENGINEERING_REFERENCE
requires_review=true
```

Area factors are stored as static Decimal kW(r)/m² values (`0.40`, `0.30`,
`0.55`) alongside the original P0 `reference_factor` and unit. Source values
are converted with `Decimal(str(value))`; no new rounding policy is applied.
For the legacy numeric zone payload boundary, the exact Decimal result is
converted to a JSON number without quantization.

## 3. Output and provenance

Only the nine refrigerated rows receive:

```text
minimum_estimated_cooling_load_kw_r
cooling_estimation_basis
```

The provenance object records `basis_type`, `source_field`, `source_value`,
`source_unit`, `reference_factor`, `reference_factor_unit`,
`authority_source`, and `requires_review`.

Ambient rows such as `office`, `changing_room`, and
`packaging_material_storage` pass through unchanged. The production
`ZonePlanningAdapter`, strict `ZoneSourceSnapshotV1` schema, and its
payload/draft lineage preserve both V1.9 fields. The schema version remains
`1.0.0`; this additive field allowlist requires no migration.

The computed relation is equality:

```text
minimum_estimated_cooling_load_kw_r = frozen_reference_basis
```

This P1 does not calculate or expose selected/design/equipment capacity, does
not take a `max` with existing `cooling_load`, and does not alter any downstream
equipment, power, or investment input.

## 4. Fail-closed behavior

The enrichment boundary fails closed for a missing `zone_code`, an unmapped
refrigerated zone, a missing or duplicate frozen refrigerated zone, a missing
canonical source, a missing reference factor, a non-numeric/non-finite source,
or a negative source. It returns a structured `CalculationError` through the
existing zone-planner `CalculationResult`; no `raw_position_count`, scheme
position, alternate area, legacy cooling output, thermal formula, zero default,
or AI guess is used as a fallback.

## 5. Explicit exclusions and stop gate

This P1 does not modify `cooling_load.py`, equipment, power, or investment
calculators; does not change `CalculationType`; does not bump
`cold_room_zone_plan@1.0.0`; and does not add migrations, frontend, Aily,
Doubao, release, tag, or database behavior. PR #252 remains untouched.

PR #254 is the completed P1 implementation handoff and is merged into main.
The report projection regression is closed and the V0.7 golden controlled
evolution is complete. The next required stage is V1.9 release closure;
creation or movement of `v1.9.0` remains gated on the closure PR merge and
green main HEAD CI. The next display/equipment-selection stage remains
unauthorized.
