# V2.2.2 P1A R12 — distinct-candidate access failure audit

```ini
TASK_ID=V2_2_2_P1A_R12_DISTINCT_CANDIDATE_ACCESS_FAILURE_AUDIT_R1
BASE_HEAD_SHA=f2fda10c30d9299be3fb55e281a739a57fbe7ccf
TASK_TYPE=DIAGNOSTIC_DESIGN_GATE
RUNTIME_IMPLEMENTATION_AUTHORIZED=false
RESULT=PASS
```

## Finding

The real Tool 7 replay captured all six complete P2C candidates: two variants for
each of the 55589 control, 062f Target A, and a148 Target B skeletons. Each P2D
result contains all 12 authority-bound requirements. The Tool 7 replay itself
selected the existing 55589 control layout and remained hard-valid:

```ini
PROJECT_LAYOUT_VALIDATED=true
P2_COMPLETE=true
SELECTED_CANONICAL_RESULT_HASH=sha256:ed11e746cd65142b26cfb20e371dda3a91b39501175681d2538d4359ee017c0d
SELECTED_SVG_SHA256=sha256:342775cb44d7165a9a64ad7e7f31cd287c04d5a1655bcc8f31ec1c1224f85981
```

| Main-process skeleton | P2C variants | Access result per variant | Exact non-PASS requirement |
| --- | ---: | --- | --- |
| 55589 control | 2 | 12 PASS, 0 FAIL, 0 BLOCKED | None |
| 062f Target A | 2 | 11 PASS, 0 FAIL, 1 BLOCKED | `access:truck_entrance->shipping_channel@1.0.0` |
| a148 Target B | 2 | 11 PASS, 0 FAIL, 1 BLOCKED | `access:truck_entrance->shipping_channel@1.0.0` |

The four target variants carry `TRUCK_MANEUVER_SEARCH_EXHAUSTED`. Their other
11 planar personnel, packaging, and material-flow requirements all pass. Thus
the aggregate `ACCESS_REQUIREMENT_VALIDATION_INCOMPLETE` warning is the count
summary; it does not identify a failed planar portal or corridor requirement.

For both target skeletons, the failed requirement is invariant across their two
tail variants. In both pairs, only `secondary_fruit_buffer` changes among the
five compared tail zones; the truck result does not change. The real
`validate_truck_maneuver_chain` predicate was then run with the exact seven
captured main-process rectangles and all five tail zones omitted. All four
counterfactuals still had no maneuver chain; each reported
`search_tree_exhausted=true`, `node_budget_exhausted=false`, and 39 visited nodes
against the unchanged 5000-node limit. This supports a main-skeleton truck
access conflict under the currently bound maneuver authority, not tail
occlusion or route-budget starvation. It is not a claim of universal geometric
infeasibility beyond that finite authority/search family.

No failed direct/corridor planar access was found, so portal-width and edge
orientation conflict are absent. The personnel route from `main_entrance` to
`changing_room` is corridor-mediated and passes. Its first attempted portal pair
has a rejected route (`ROUTE_SEARCH_EXHAUSTED`, with corridor crossing, obstacle,
boundary, and unrelated-zone rejection observations); its second pair succeeds
with a 2-turn, 32.01 m route. A rejected alternative portal pair is not a failed
access requirement. The failed truck requirement does not use the planar direct
or corridor portal search.

No route-budget sensitivity run was made: none of the failed access-result rows
contains planar `ROUTE_SEARCH_EXHAUSTED`; the only blocked code is
`TRUCK_MANEUVER_SEARCH_EXHAUSTED`, and the truck search reports its finite tree
exhausted without its node budget being hit. Production route/truck budgets and
all hard rules remain unchanged.

## Classification and next path

```ini
TARGET_A_ROOT_CAUSE=MAIN_SKELETON_ACCESS_GEOMETRY_CONFLICT+OTHER_EXACT_ACCESS_CONFLICT
TARGET_B_ROOT_CAUSE=MAIN_SKELETON_ACCESS_GEOMETRY_CONFLICT+OTHER_EXACT_ACCESS_CONFLICT
MAIN_SKELETON_ACCESS_INFEASIBILITY_PROVEN=true
TAIL_ACCESS_WITNESS_EXISTENCE_UNRESOLVED=false
PACKAGING_ACCESS_FAILURE_PRESENT=false
PERSONNEL_ACCESS_FAILURE_PRESENT=false
MAIN_FLOW_ACCESS_FAILURE_PRESENT=false
PORTAL_WIDTH_FAILURE_PRESENT=false
EDGE_ORIENTATION_FAILURE_PRESENT=false
CORRIDOR_GEOMETRY_FAILURE_PRESENT=false
ROUTE_BUDGET_CAUSAL=false
NEXT_IMPLEMENTATION_PATH=MAIN_SKELETON_ACCESS_NECESSARY_PREFLIGHT
```

The next design proposal is an evaluation of the already-authoritative truck
maneuver feasibility against a frozen main-process skeleton before tail search.
This audit does not implement that preflight or authorize any runtime change.
Owner visual acceptance remains unresolved.

## Evidence and scope

The six machine-readable evidence files in
`docs/tasks/evidence/v2_2_2_p1a/` contain the captured candidate geometry,
requirement metadata/results, portal-pair attempts, tail-variant comparison,
seven-zone counterfactuals, and root-cause classification. The capture wrapper
is evaluation-only and delegates to the original Tool 7, P2C, P2D, access, and
truck functions; no instrumentation enters production serialization.

```ini
BACKEND_SRC_CHANGED=false
TOOL7_RUNTIME_CHANGED=false
MCP_CONTRACT_CHANGED=false
REPORT_RUNTIME_CHANGED=false
DATABASE_CHANGED=false
FRONTEND_CHANGED=false
PRODUCTION_CHANGED=false
P1B_THRESHOLD_ACTIVATED=false
WEIGHTED_SCORE_USED=false
```
