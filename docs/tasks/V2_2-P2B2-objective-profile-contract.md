# V2.2 P2B2 — Deterministic objective profile contract

## Current status

```ini
TASK_ID=V2_2_P2B2_OBJECTIVE_PROFILE_CONTRACT_FREEZE_R1
TARGET_VERSION=v2.2.0
BASE_MAIN_SHA=fa884b8ddf2b93f34beb2335d646fe6b157a8f5f
ACTIVE_GOVERNANCE_LANE=V2.2_P2
P2_AUTHORIZED=true
P2B2_AUTHORIZED=true
OBJECTIVE_PROFILE_AUTHORIZED=true
OBJECTIVE_PROFILE_IMPLEMENTED=true
PLACEMENT_SEARCH_IMPLEMENTED=false
ROUTING_IMPLEMENTED=false
P2C_AUTHORIZED=false
P2_COMPLETE=false
P3_AUTHORIZED=false
P4_AUTHORIZED=false
P5_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P2B2 freezes only the versioned objective metadata and the evaluation boundary.
It does not generate a candidate layout, place a zone, generate a route, or
calculate a score. P2C remains separately gated.

## Owner decisions

The following decisions are the current Owner authority. They are represented
by `site-constrained-objective-profile@1.0.0` in the layout domain.

```ini
OBJECTIVE_AGGREGATION=LEXICOGRAPHIC
WEIGHTED_SCORE=false

SHOULD_ADJACENT_EQUAL_PRIORITY=true
SHOULD_ADJACENT_METRIC=SATISFIED_COUNT
SHOULD_ADJACENT_COUNT=5
SHIPPING_TRUCK_ENTRANCE_PROXIMITY_IN_SHOULD_COUNT=false

ROUTE_OBJECTIVES_REQUIRE_ACTUAL_PORTAL_CORRIDOR_ROUTE=true
CENTROID_PROXY_ALLOWED=false
EDGE_MANHATTAN_PROXY_ALLOWED=false
STRAIGHT_LINE_PROXY_ALLOWED=false

CARDINAL_LOADING_SIDE_METRIC=BINARY_MATCH
UNSPECIFIED_LOADING_SIDE_SCORING=DISABLED
NEAREST_TRUCK_ENTRANCE_METRIC=MIN_LOADING_FACE_TO_TRUCK_ENTRANCE_SEGMENT_DISTANCE

COMPACTNESS_ACTIVE=false
SHAPE_REGULARITY_ACTIVE=false
UNUSED_SITE_EFFICIENCY_ACTIVE=false
DEFER_UNTIL_BUILDING_ROUTE_AUTHORITY_COMPLETE=true
```

The lexicographic priority sequence preserves the declaration order already
used by the P0 soft-objective list. This is an ordering contract, not a set of
weights and not a claim that one unit is exchangeable for another:

```text
SHOULD_ADJACENT
MATERIAL_FLOW_DISTANCE
LOADING_SIDE_PREFERENCE
COMPACTNESS
CIRCULATION_LENGTH
PEOPLE_TRUCK_SEPARATION
SHAPE_REGULARITY
UNUSED_SITE_EFFICIENCY
```

Hard constraints are evaluated first. A hard violation cannot be compensated
by any soft objective.

## Objective rules and staging

The profile keeps all eight P0 objectives visible, while preventing an
unverified proxy from becoming an objective silently.

| Objective | Stage | Current rule | Unit / direction | Dependency |
| --- | --- | --- | --- | --- |
| `SHOULD_ADJACENT` | placement | maximize the count of the five equal-priority SHOULD zone adjacencies | count / maximize | complete zone rectangles and `AdjacencyGraphV1`; truck proximity is separate |
| `MATERIAL_FLOW_DISTANCE` | route | actual portal/corridor route length only | m / minimize | actual material route; no centroid, Manhattan, or straight-line proxy |
| `LOADING_SIDE_PREFERENCE` | placement | cardinal side is binary match; nearest-truck mode uses minimum loading-face-to-entrance-segment distance | match / maximize, or m / minimize | placed shipping loading face, site orientation, and truck entrance |
| `COMPACTNESS` | placement | disabled | — | building footprint authority is not active |
| `CIRCULATION_LENGTH` | route | actual portal/corridor circulation route length only | m / minimize | actual circulation routes |
| `PEOPLE_TRUCK_SEPARATION` | route | deferred; existing shared-route prohibition and crossing-review policy remain separate access authority | owner metric not invented | personnel and truck routes plus an Owner-approved metric |
| `SHAPE_REGULARITY` | placement | disabled | — | no layout shape metric is frozen |
| `UNUSED_SITE_EFFICIENCY` | placement | disabled | — | final building footprint and residual-site semantics are not active |

`UNSPECIFIED` loading side contributes no score. `NORTH`, `EAST`, `SOUTH`,
and `WEST` use only a binary match against the actual placed loading face.
`NEAREST_TRUCK_ENTRANCE` uses the minimum distance between the two supplied
geometry segments; it is not a centroid or room-center distance.

The intended future evaluation sequence is:

```text
hard constraints
  -> placement-stage objective vector
  -> route-stage objective vector, only when actual routes exist
  -> exact equality check of the complete approved objective vector
  -> deterministic technical tie-break
```

An objective marked deferred or disabled is not replaced with zero, a guessed
value, or a geometric proxy.

## Deterministic tie-break

Only after the approved business objective vector is exactly equal, the future
engine may use:

```ini
FINAL_TIE_BREAK=CANONICAL_NORMALIZED_FULL_LAYOUT_JSON_LEXICAL
FINAL_TIE_BREAK_AFTER_EXACT_OBJECTIVE_VECTOR=true
RAW_MAPPING_ORDER_ALLOWED=false
HASH_AS_TIE_BREAK=false
```

The candidate must first be normalized: geometry numbers use the existing
0.001m grid, zones and other records use stable identifiers, and lists use
their contract-defined stable order. The comparison is then lexical over the
canonical full candidate JSON. Python mapping insertion order, hash seed,
runtime discovery order, and the canonical hash itself are not tie-break
authority.

## Boundary and non-goals

P2B2 does not implement `placement_search`, `route_search`, a building
footprint solver, portal placement, corridor generation, truck routing, SVG,
PDF, DXF, MCP Tool 7, frontend behavior, database changes, or deployment.

The existing P0/P1/P2A/P2B1 hard constraints, zone authority, access policy,
truck maneuver template contract, six-tool MCP contract, and all calculator
identities remain unchanged. This profile is metadata for a later deterministic
engine, not a release or P2 completion decision.
