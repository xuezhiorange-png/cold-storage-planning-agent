# V2.2 P2C — Deterministic site-constrained placement engine

## Current status

```ini
TASK_ID=V2_2_P2C_DETERMINISTIC_PLACEMENT_ENGINE_R1
TARGET_VERSION=v2.2.0
BASE_MAIN_SHA=776d6836975d5f27a0261820548425e798919f03
ACTIVE_GOVERNANCE_LANE=V2.2_P2
P2C_AUTHORIZED=true
P2C_STATUS=IMPLEMENTED_DRAFT_REVIEW
PLACEMENT_SEARCH_IMPLEMENTED=true
PLACEMENT_SEARCH_PROFILE_IDENTITY=deterministic-placement-search@1.0.0
PLACEMENT_RESULT_IDENTITY=site_constrained_factory_layout@1.0.0
PLACEMENT_RESULT_SCHEMA_VERSION=1.0.0
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

P2C is the first placement implementation in V2.2. It consumes the verified
`cold_room_zone_plan@1.0.0`, the P1 project handoff, the P2A validated site
geometry and the approved P2B2 objective profile. It produces a deterministic
candidate with all twelve zone rectangles, coordinates, rotation, selected
flexible dimensions, the shipping loading face, hard placement evaluation and
the placement-stage objective vector.

This is a placement result, not a final project-layout approval. A successful
finite search is reported as `PLACEMENT_FOUND`; an exhausted finite candidate
family is reported as `LAYOUT_SEARCH_EXHAUSTED`, never as a proof of
infeasibility. `LAYOUT_INFEASIBLE_PROOF_IMPLEMENTED=false` remains explicit.

## Authority and hard placement boundary

The twelve zone codes remain the canonical `cold_room_zone_plan` authority.
P2C copies the nine fixed/deterministic rectangle dimensions from the P1
handoff and may translate or rotate them only through the approved 0/90 degree
discrete representation. It cannot resize those rectangles, repack their
capacity geometry, recalculate required area or change their profile identity.

`coating_room`, `changing_room` and `office` retain their
`FLEXIBLE_RECTANGLE` authority. P2C selects only positive dimensions on the
existing 0.001m grid, with `width_m * depth_m >= required_area_m2`. This is a
finite technical candidate family, not a new engineering aspect-ratio rule:

```ini
ZONE_AREA_AUTHORITY=COLD_ROOM_ZONE_PLAN
FIXED_RECTANGLE_RESIZE_ALLOWED=false
DETERMINISTIC_GRID_RECTANGLE_RESIZE_ALLOWED=false
FLEXIBLE_DIMENSION_SELECTION_ALLOWED=true
NO_ASPECT_RATIO_AUTHORITY_CREATED=true
GRID_M=0.001
ROTATION_ALLOWED=0,90
```

Every complete candidate is checked using the P2A exact geometry predicates:
all zones are inside the effective buildable boundary, hard obstacles are
clear, rectangles do not overlap in their interiors, and every hard
`MUST_ADJACENT` pair shares a positive-length edge. Corner contact is not an
adjacency. No floating epsilon or full-site millimetre scan is used.

The deterministic search uses stable constrained-first zone ordering and a
finite edge/vertex anchor family. Flexible dimensions are drawn from
adjacent-edge, relevant-span and deterministic near-square candidates. The
search budget is a versioned node/candidate budget and is recorded in result
provenance; it is not a wall-clock timeout and is not engineering authority.

## Process graph and objective evaluation

The current P1 process authority is preserved exactly:

```text
raw_fruit_buffer
  → primary_precooling_room
  → sorting_packaging_room
  → secondary_precooling_room
  → coating_room
  → finished_goods_room
  → shipping_channel
```

The seven hard adjacency pairs are the six process edges plus
`office ↔ shipping_channel`. The five SHOULD pairs remain the P1/P2B2 graph
authority and are evaluated as an equal-priority satisfied count. The
shipping/truck entrance relation is not included in that count.

Candidate comparison is the approved P2B2 lexicographic placement order:

```ini
OBJECTIVE_AGGREGATION=LEXICOGRAPHIC
MUST_ADJACENT_COUNT=7
SHOULD_ADJACENT_COUNT=5
PLACEMENT_OBJECTIVE_ORDER=SHOULD_ADJACENT,LOADING_SIDE_PREFERENCE
WEIGHTED_SCORE=false
NEAREST_TRUCK_ENTRANCE_COMPARATOR=EXACT_MIN_SEGMENT_TO_SEGMENT_SQUARED_EUCLIDEAN_DISTANCE
FLOAT_EPSILON_ALLOWED=false
SQRT_REQUIRED_FOR_RANKING=false
COMPACTNESS_ACTIVE=false
SHAPE_REGULARITY_ACTIVE=false
UNUSED_SITE_EFFICIENCY_ACTIVE=false
```

`UNSPECIFIED` loading side is not scored. Cardinal preferences use an actual
loading-face binary match. `NEAREST_TRUCK_ENTRANCE` compares the actual
shipping long-edge segment with the actual truck-entrance segment using exact
minimum squared segment distance in integer `MM2`; no square root, epsilon,
centroid or Manhattan proxy is introduced. If the approved business vector is
equal, the normalized candidate JSON is the deterministic technical tie-break,
not a hash or iteration order.

## Canonical output

`SitePlacementResultV1` binds:

```text
source_zone_plan_hash
source_p1_handoff_hash
source_site_geometry_hash
source_objective_profile_hash
zones[12]
shipping_loading_face_side
shipping_loading_face_segment
must_adjacency_evaluation
should_adjacency_evaluation
placement_access_observations
placement_objective_vector
search_provenance
canonical_candidate_hash
canonical_result_hash
```

Each zone record contains the canonical zone code, required area, selected
coordinates, local width/depth, actual area, 0/90 rotation and the dimension
authority identity. Fixed/deterministic records retain their handoff geometry;
flexible records carry only dimensions selected by this placement candidate.

The result is `PLACEMENT_AVAILABLE=true` and
`PLACEMENT_HARD_CONSTRAINTS_PASSED=true` only for a complete candidate. It
always remains subject to review and carries the following explicit status:

```ini
ROUTING_IMPLEMENTED=false
ACCESS_ROUTE_VALIDATED=false
TRUCK_ROUTE_VALIDATED=false
PROJECT_LAYOUT_VALIDATED=false
P2_COMPLETE=false
```

Placement-level observations may record a direct shared edge or the selected
loading face, but every access observation that requires a portal, corridor or
route remains `PENDING_ROUTE_VALIDATION`.

## Explicit non-goals and gate

P2C does not generate a building footprint, portal coordinates, corridor
geometry, personnel/material/truck routes, turning paths or kinematic
solutions. It does not implement SVG, PDF, DXF, CAD, MCP Tool 7, frontend
behavior, database changes, deployment or release activity.

```ini
PORTAL_PLACEMENT=false
CORRIDOR_GENERATION=false
TRUCK_PATH_SEARCH=false
NO_MCP_TOOL_7=true
NO_SVG_PDF_DXF=true
P2C_REVIEW_GATE=DRAFT
```

P2C does not authorize P3, P4 or P5. Later stages must consume the canonical
placement JSON and may not treat a drawing projection or an unvalidated route
as a replacement authority.
