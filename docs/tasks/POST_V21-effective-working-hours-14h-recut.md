# POST-V2.1 — Effective Working Hours 14h Recut

## 1. Authority

Charles instruction on 2026-09-10:

- 二级预冷有效工作时间：14 h/day
- 分选包装间有效工作时间：14 h/day

This change supersedes the prior 16 h/day defaults only for these two area-planning assumptions.
It does not change primary precooling, storage-day KEYs, packaging-material storage, shipping,
cooling/equipment/power/investment calculator identities, or the six-tool Doubao MCP contract.

```text
TASK_ID=POST_V21_EFFECTIVE_WORKING_HOURS_14H_R1
BASE_MAIN_SHA=2221077d4ebe0ee90e218b8869ccb3bb000b1d60
TARGET_BRANCH=fix/v2-1-effective-working-hours-14h-r1
CALCULATOR_FORMULA_AUTHORITY=POST-V0.9-P4-charles-zone-area-recut
CHANGE_AUTHORITY=Charles instruction 2026-09-10
CHANGE_SCOPE=SECONDARY_PRECOOL_AND_PACKING_EFFECTIVE_HOURS_ONLY
SECONDARY_PRECOOL_EFFECTIVE_HOURS_PER_DAY=14
PACKING_EFFECTIVE_HOURS_PER_DAY=14
MERGE_AUTHORIZED=NO
TAG_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 2. Secondary precooling

Default pallet weight remains 400 kg/pallet and processing time remains 2 h/pallet.

```text
hourly_capacity = 400 / 2 = 200 kg/h
daily_capacity = 200 * 14 = 2800 kg/day/position
n_need = ceil(daily_inbound_mass_kg / 2800)
```

The existing 6-position / 42 m² and 8-position / 56 m² room modules remain unchanged.
The reporting scheme remains the 6-position scheme.

## 3. Sorting / packing room

Default person rate remains 16 pcs/(person·h), package weight remains 1.5 kg/pc,
and effective packing time becomes 14 h/day.

```text
person_daily_capacity = 16 * 1.5 * 14 = 336 kg/(person·day)
worker_count = ceil(daily_inbound_mass_kg / 336)
table_count = ceil(worker_count / 3)
```

The existing packed-rectangle and clearance geometry remains unchanged:

```text
A = ((n_long - 1) * 5.6 + 8.0) * ((n_short - 1) * 3.0 + 7.6)
```

The implementation now derives person daily capacity from
`packing_pieces_per_person_hour * packing_weight_per_piece_kg * packing_working_hours_per_day`
instead of using a disconnected fixed 384 kg/day constant.

## 4. 20 t/day sample impact

Existing sample KEY:

- daily inbound: 20,000 kg/day
- finished storage: 7 days
- frozen storage: 10 days
- main packaging storage: 4 days
- auxiliary packaging storage: 12 days

Expected impact:

| Item | Before | After |
| --- | ---: | ---: |
| Secondary precooling daily capacity | 3200 kg/day/position | 2800 kg/day/position |
| Secondary precooling area | 84.00 m² | 84.00 m² |
| Packing person daily capacity | 384 kg/person·day | 336 kg/person·day |
| Packing room area | 489.60 m² | 565.76 m² |
| Total 6-position area | 2061.85 m² | 2138.01 m² |

The secondary precooling area remains 84 m² for this sample because both capacities still resolve
to two 6-position rooms. The packing room increases because 20 t/day requires 60 people and
20 packing tables at 336 kg/person·day.

## 5. Scope

Included:

- deterministic zone-planning defaults and packing capacity calculation
- planning-service secondary-precooling default
- workbench secondary-precooling default
- current audit inventories
- backend and frontend regression expectations

Not included:

- rewriting historical POST-V0.9 P4 contract in place
- changing the general `working_time_h_per_day` field
- changing packaging-material storage days or area factors
- merge, release, tag, or deployment

## 6. R2 correction record

The zone planner remains `VERSION=1.0.0` under the historical
`POST-V0.9-P4-charles-zone-area-recut` formula authority. The 14 h/day values
are parameter corrections within that authority; they do not create a new
calculator identity.

```text
TASK_ID=POST_V21_EFFECTIVE_WORKING_HOURS_14H_CORRECTION_R2
CALCULATOR_FORMULA_AUTHORITY=POST-V0.9-P4-charles-zone-area-recut
CHANGE_AUTHORITY=Charles instruction 2026-09-10
CHANGE_SCOPE=SECONDARY_PRECOOL_AND_PACKING_EFFECTIVE_HOURS_ONLY
HISTORICAL_POST_V09_ORACLE_REWRITTEN=NO
HISTORICAL_POST_V09_TESTS_USE_EXPLICIT_16H_INPUTS=YES
EXISTING_AUDIT_DRIFT=packing_pieces_per_person_hour inventory=15 versus main runtime default=16
```
