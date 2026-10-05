# V2.2.2 P1A P1-S4 — composition-native hard-validation bridge

## Scope

P1-S4 takes one exact 12-zone candidate emitted by the S3 composition-constrained
placement engine and sends that unchanged geometry through the existing P2D
application authority. It is a validation bridge, not a selector, repair loop,
or new engineering validator.

The public application API accepts the canonical zone plan, P1 handoff,
validated site geometry, a truck-maneuver binding, and a candidate hash
reference. It does not accept a candidate object or geometry payload. The
server replays composition enumeration and exact placement, resolves exactly
one candidate by its canonical hash, verifies its composition identity/signature
and source hashes, then adapts only its representation to the existing P2D
placement-result contract.

## Implementation

`application/composition_candidate_validation.py` is the new application
boundary. It reuses the current shared layout-authority binding,
`enumerate_composition_placements`, and `route_site_placement`. The adapter
checks the existing seven MUST edges, retains every role and source hash, and
uses existing placement serialization/loading-face rules. Exact x, y, width,
depth, and rotation are compared through adaptation and again against the
returned P2D body. Any mismatch fails closed; no rectangle is moved, resized,
rotated, dropped, or added.

`route_site_placement()` remains the sole downstream authority for access and
portal routing, truck maneuver validation, personnel/truck interaction,
building-footprint derivation, `project_layout_validated`, and `p2_complete`.
The result embeds the unmodified existing P2D response and its canonical hash,
including warnings, route failures, truck codes, interaction status, and
footprint output. An objective-profile hash is populated only because the
existing P2D placement wire contract requires it; this task does not score or
rank candidates.

There is one geometry input and one P2D result per bridge invocation. The
bridge does not call legacy placement, `select_validated_placement`, Tool 7,
SVG projection, or a geometry-repair path. It does not modify S3 search
behavior, the selector, P2D rules, Access rules, Truck rules, or dimensions.

## Xinzhao replay and result

The real fixture is
`backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json`. The
machine-readable run, including candidate provenance, exact rectangles, all
access results, truck result, personnel/truck interaction, P2D result, and
failure classification, is recorded in
[`xinzhao_composition_candidate_hard_validation.json`](evidence/v2_2_2_p1a_reset_s4/xinzhao_composition_candidate_hard_validation.json).

## Measured Xinzhao result

The S3 server replay emitted the candidate below after 50,621 of the fixed
60,000 composition-placement nodes. The S4 endpoint selected it by canonical
hash, replayed it again, preserved all 12 rectangles and the seven existing
MUST adjacencies, then called `route_site_placement()` once with the existing
20,000-node route and truck budgets.

```ini
IMPLEMENTATION_RESULT=PASS
CANDIDATE_VALIDATION_RESULT=FAIL_ACCESS
CANDIDATE_HASH=sha256:4a4b8f6695526ea0bd1cf30238ae4c7c45b35e6d9677b0c4bd8f98228e8f3c47
FAMILY=LINEAR_BANDED
PROCESS_AXIS=Y
PROCESS_DIRECTION=POSITIVE
ZONE_COUNT=12
MUST_ADJACENCY_SATISFIED_COUNT=7
ACCESS_REQUIREMENT_COUNT=12
ACCESS_PASS_COUNT=7
ACCESS_FAIL_COUNT=5
ACCESS_FAILURE_CODES=ROUTE_SEARCH_EXHAUSTED,PACKAGING_SORTING_STRAIGHT_ROUTE_REQUIRED,TRUCK_MANEUVER_SEARCH_EXHAUSTED
TRUCK_VALIDATION_PERFORMED=true
TRUCK_ROUTE_VALIDATED=false
TRUCK_ROUTE_CODES=TRUCK_MANEUVER_SEARCH_EXHAUSTED
PERSONNEL_TRUCK_STATUS=BLOCKED
BUILDING_FOOTPRINT_DERIVED=false
PROJECT_LAYOUT_VALIDATED=false
P2_COMPLETE=false
FAIL_STAGE=ACCESS
P2D_RESULT_HASH=sha256:632817a23ee61d47225441730ce7e63bb22029ca34694bfdf83febbd28237718
GEOMETRY_REPAIR_PERFORMED=false
GLOBAL_INFEASIBILITY_PROVEN=false
```

This is a real hard-validation rejection of the selected candidate, not a
bridge execution failure and not a global infeasibility proof. Access reported
7/12 PASS; the five non-PASS rows include entrance-to-changing routing,
packaging straight access, the secondary/frozen branches, and the truck
entrance-to-shipping requirement. Truck maneuver search was executed and
returned `TRUCK_MANEUVER_SEARCH_EXHAUSTED`. The unchanged P2D result is retained
in full in the evidence JSON. No alternate candidate, repair, or S3 search
change was used to turn this result into PASS.

## Tests and compatibility

The focused S4 tests cover hash-only input, stale-hash rejection, exact geometry
and provenance preservation, a real Xinzhao P2D call, and deterministic result
serialization. The architecture guard limits this bridge to server-side
composition replay and existing validation authorities. S1/S2/S3,
P2C, Access, Truck, P2D, validated-selection, P1F, and repository CI are run
separately and reported independently.

## Non-goals and next-stage boundary

No candidate ranking, visual score, geometry repair, multi-family selection,
gallery acceptance, Tool 7 integration, or P1 completion is included. If the
candidate fails the existing authority chain, that is recorded as a candidate
hard-validation failure—not global infeasibility—and no geometry correction is
started by this task. P1 remains incomplete; any follow-on layout correction or
selector/Tool 7 integration needs separate authorization.

```ini
TASK_ID=V2_2_2_P1A_COMPOSITION_NATIVE_HARD_VALIDATION_P1_S4
MODE=COMPOSITION_NATIVE_ACCESS_TRUCK_P2D_VALIDATION_BRIDGE
BASE_MAIN_SHA=073ac48cd69d7122cb56d22f7330e9647bc3aa7c
IMPLEMENTATION_RESULT=PASS
CANDIDATE_VALIDATION_RESULT=FAIL_ACCESS
COMPOSITION_PLACEMENT_NODE_BUDGET=60000
ACCESS_REQUIREMENT_COUNT=12
ACCESS_PASS_COUNT=7
TRUCK_ROUTE_STATUS=TRUCK_MANEUVER_SEARCH_EXHAUSTED
P2D_COMPLETE=false
GEOMETRY_REPAIR_DURING_VALIDATION=false
S3_PLACEMENT_SEARCH_BEHAVIOR_CHANGED=false
VALIDATED_CANDIDATE_SELECTOR_CHANGED=false
TOOL7_BEHAVIOR_CHANGED=false
P1_COMPLETE=false
GLOBAL_INFEASIBILITY_PROVEN=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```
