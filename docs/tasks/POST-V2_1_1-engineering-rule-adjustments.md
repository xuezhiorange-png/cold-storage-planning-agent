# POST-V2.1.1 Engineering Rule Adjustments

This record describes the current engineering-rule adjustment lane after the
`v2.1.1` patch release. It is additive to the released V2.0/V2.1 contracts and
does not move or rewrite historical release evidence.

```text
TASK_ID=POST_V2_1_1_ENGINEERING_RULE_ADJUSTMENTS_R1
BASE_MAIN_SHA=c9ce6e7399ec2a163ab4c7c7339b828a86abbf08
TARGET_VERSION=post-v2.1.1-current-rule-adjustment
FORMULA_AUTHORITY_BEFORE=POST-V0.9-P4-charles-zone-area-recut
FORMULA_AUTHORITY_AFTER=POST-V2.1.1-charles-engineering-rule-adjustments
CALCULATOR_IDENTITY=cold_room_zone_plan@1.0.0
FACTORY_POWER_CALCULATOR=factory_power_estimation@2.0.0-p1
```

## Current rules

The existing cold-room zone-planner identity remains `1.0.0`; the current
formula authority is now explicitly recorded as
`POST-V2.1.1-charles-engineering-rule-adjustments`.

- 一级预冷 uses seven batches/day. With 220 kg/pallet and one hour/pallet,
  the effective daily capacity is `220 × 7 = 1540 kg/day/position`.
- 二级预冷 remains at 14 h/day and `2800 kg/day/position`.
- 分选包装 keeps the input-driven capacity
  `16 × 1.5 × 14 = 336 kg/person·day`. It keeps the existing worker/table
  and rectangle layout counts, then applies only
  `SORTING_PACKAGING_AREA_FACTOR=1.1` to the rectangle's final area.
- 化霜 installed power, equipment counts, normal-running simultaneity, and
  all other factory-power rules remain unchanged. Only the defrost
  simultaneous-use factor changes from `0.30` to `0.20`.

For the representative 20 t/day input (`finished_storage_days=7`,
`frozen_storage_days=10`, `main_packaging_storage_days=4`, and
`auxiliary_packaging_storage_days=12`), the current canonical zone result is:

| Field | Current result |
| --- | ---: |
| Primary precooling batches/day | 7 |
| Primary precooling position daily capacity | 1540 kg/day/position |
| Primary precooling area | 126.00 m² |
| Secondary precooling hours/day | 14 |
| Secondary precooling position daily capacity | 2800 kg/day/position |
| Secondary precooling area | 84.00 m² |
| Sorting/packing raw rectangle area | 565.76 m² |
| Sorting/packing area factor | 1.1 |
| Sorting/packing final area | 622.34 m² |
| Total area before this lane | 2138.01 m² |
| Total area after this lane | 2194.59 m² |

The raw rectangle geometry and all layout counts are exposed separately from
the scaled final area so the area adjustment cannot alter staffing or table
counts.

## Historical compatibility

V0.7 golden replay and POST-V0.9 contract tests use explicit historical rule
profiles in test fixtures. They retain the historical 16 h/day dedicated
working-time semantics, the historical primary 6 h/day input, the historical
unscaled sorting rectangle, and the historical formula authority. The
historical golden and numeric oracles are not rewritten.

The current audit still records the known packing-pieces metadata drift
(inventory value 15 versus the runtime value 16); this task does not silently
resolve that unrelated discrepancy.

## Boundary and release safety

```text
HISTORICAL_GOLDEN_CHANGED=NO
V09_HISTORICAL_ORACLE_REWRITTEN=NO
MCP_TOOL_COUNT=6
MCP_CONTRACT_CHANGED=NO
DOUBAO_SKILL_CHANGED=NO
DATABASE_MIGRATION_CHANGED=NO
DEPLOYMENT_CHANGED=NO
V2_1_1_TAG_MOVED=NO
V2_1_1_RELEASE_CHANGED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_AUTHORIZED=NO
GITHUB_RELEASE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

The implementation PR remains a Draft review gate. No MCP/Skill contract,
database, release, deployment, or unrelated calculation formula is included.

## R2 calculator identity correction (current Draft)

The R1 rule adjustment changed the production defrost simultaneous-use factor
to `0.20`, but retained the released P1 calculator identity in current
consumer metadata. R2 closes that identity conflict by publishing a new
calculator revision. The result schema is unchanged because the serialized
payload shape is unchanged.

```text
TASK_ID=POST_V2_1_1_ENGINEERING_RULE_ADJUSTMENTS_R2
BASE_HEAD_SHA=dcb6e87877255e8a3619abc2fcde1330bd702012
OLD_FACTORY_POWER_CALCULATOR_VERSION=2.0.0-p1
OLD_FACTORY_POWER_CALCULATOR_IDENTITY=factory_power_estimation@2.0.0-p1
OLD_DEFROST_SIMULTANEOUS_FACTOR=0.30
NEW_FACTORY_POWER_CALCULATOR_VERSION=2.0.0-p2
NEW_FACTORY_POWER_CALCULATOR_IDENTITY=factory_power_estimation@2.0.0-p2
NEW_DEFROST_SIMULTANEOUS_FACTOR=0.20
RESULT_SCHEMA_VERSION=2.0.0-p1
HISTORICAL_P1_IDENTITY_PRESERVED=YES
HISTORICAL_P1_FACTOR_PRESERVED=YES
CURRENT_CONSUMERS_USE_NEW_IDENTITY=YES
MCP_TOOL_COUNT=6
MCP_CONTRACT_CHANGED=NO
DATABASE_MIGRATION_CHANGED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_AUTHORIZED=NO
GITHUB_RELEASE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

The immutable V2.0/V2.1/v2.1.1 release evidence remains a P1 historical
snapshot with `POOL_A=0.30`. Current untagged production results and their
read-only consumers use `factory_power_estimation@2.0.0-p2` with `POOL_A=0.20`.
The V2.1 Skill, runbook, release-closure records, and golden artifacts remain
unchanged historical evidence; this R2 correction does not rewrite a released
artifact or move a tag.
