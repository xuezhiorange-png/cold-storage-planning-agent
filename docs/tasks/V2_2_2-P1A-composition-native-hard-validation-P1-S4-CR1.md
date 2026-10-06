# V2.2.2 P1A S4 Correction Round 1 — access-aware composition placement

`TASK_ID=V2_2_2_P1A_COMPOSITION_NATIVE_HARD_VALIDATION_P1_S4_CR1`

## Scope

This bounded correction adds construction intents for the five existing
access-critical interfaces and an access-aware composition-native placement
search. It does not change composition families, dimension authority, MUST
adjacency, Access/Truck/P2D authority, candidate selection, or Tool 7. Interface
intents and construction preflights are search guidance only; they never claim
Access or Truck validity. Complete candidates, when produced, are checked by
the existing Access authority, then existing Truck/P2D validation is rerun
without geometry repair.

The exact budget remains 60,000 composition-placement nodes, 20,000 route nodes,
and 20,000 Truck nodes. No unbounded route/geometry repair is performed.

## Implementation

- `domain/access_critical_construction.py` defines immutable, non-authoritative
  interface-intent values for personnel ingress, Packaging-to-Sorting straight
  access, Secondary/Frozen branches, and Shipping/Truck maneuver interface.
- `application/access_critical_construction.py` binds these intents to the
  server-owned zone plan, P1 handoff, validated site, frozen Access profiles,
  and validated Truck input. Dock events are transformed from the existing
  `DOCK_REVERSE` authority; no Truck result is inferred.
- `domain/composition_placement.py` uses finite entrance, Sorting-face,
  peripheral-domain, and authoritative dock-point events in its access-aware
  branch. It performs a necessary Shipping/Office capacity check and an
  authoritative dock-point-on-loading-face preflight. The existing S3 path is
  unchanged when no access intent is supplied.
- `application/access_aware_composition_placement.py` replays the composition
  and authority chain, supplies the existing exact Access validator as the
  complete-candidate checkpoint, selects only among composition-native
  candidates, and invokes full Truck/P2D validation only after 11/11 non-Truck
  Access and the necessary Truck preflight. It never repairs geometry.

## Results

The preserved S4 control was replayed through the unchanged validation bridge:

```ini
CONTROL_ACCESS_REQUIREMENT_COUNT=12
CONTROL_ACCESS_PASS_COUNT=7
CONTROL_ACCESS_FAIL_COUNT=5
CONTROL_TRUCK_VISITED_NODES=27
CONTROL_TRUCK_NODE_BUDGET_EXHAUSTED=false
CONTROL_TRUCK_SEARCH_TREE_EXHAUSTED=true
CONTROL_PROJECT_LAYOUT_VALIDATED=false
CONTROL_P2_COMPLETE=false
```

The bounded access-aware construction replay used 56,334 of at most 60,000
placement nodes across all three families. It completed the family first round
and tried three deterministic family/composition/bank tracks, but produced no
complete 12-zone candidate. Therefore the exact Access checkpoint was not
reached for a new candidate; new-candidate Access, Truck, and P2D attempt counts
are all zero. This is a construction-stage failure, not evidence of global
infeasibility. The control's 7/12 result is not counted as improvement.

The search covered three attempts per family (9 total); family node use was
`LINEAR_BANDED=16,334`, `CENTRAL_PROCESS_CORE=20,000`, and
`PROCESS_SPINE_WITH_PERIPHERAL_BANKS=20,000`. The deepest successful partial
placement reached 8/12 roles for Linear and Central and 10/12 for Spine. The
deepest attempted roles were `shipping_channel` for Linear/Central and
`coating_room` for Spine. No complete candidate exists to score against the
11 non-Truck Access requirements. Bounded candidate-level Truck preflight
results are retained separately from formal Truck validation in the evidence;
formal Truck and P2D validation attempts remain zero.

Family-level search, preflight, and best-partial diagnostics are retained in
[`xinzhao_access_aware_candidate_search.json`](evidence/v2_2_2_p1a_s4_cr1/xinzhao_access_aware_candidate_search.json).

## Non-goals and boundaries

No Access route rule, portal/corridor width, Truck template, Truck search
budget, room dimension, MUST adjacency, composition contract, P2D behavior,
selector behavior, or Tool 7 behavior is changed. Construction corridor seeds
and Truck preflights are not validation results. The new search does not call
legacy `place_zones()` as a fallback. No candidate overlay is generated because
there is no improved candidate with real validated paths to display.

## Acceptance outcome

`IMPLEMENTATION_RESULT=PASS` only describes the bounded construction/intention
implementation and its tests. The required validation-progress gate is not
met: the best new candidate is absent, so `BEST_NON_TRUCK_ACCESS_PASS_COUNT=0`
and the control remains at 7/11 non-Truck requirements. Consequently the
overall task result is `FAIL`, with
`FAIL_STAGE=COMPOSITION_EXACT_CANDIDATE_CONSTRUCTION_NO_COMPLETE_12_ZONE` and
`GLOBAL_INFEASIBILITY_PROVEN=false`. No further correction round is authorized
by this record.

## Validation boundary

Local final regression: 187 passed across S1/S2/S3/S4, Access/Truck/P2D,
P2C, validated selection, and P1F-related tests. The full architecture suite
passed with 751 passed and 16 skipped. Ruff, format, and mypy also passed;
SQLite/PostgreSQL full-backend outcomes are reserved for exact-head GitHub CI.
The exact-head PR and push CI outcomes are appended only after both GitHub runs
reach terminal states; no pending run is represented as a pass. Even if
automated checks pass, the PR remains Draft and P1 is incomplete; Owner review,
candidate diversity, gallery, and later integration are not implied.
