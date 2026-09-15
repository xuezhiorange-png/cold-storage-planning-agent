# V2.2 P2A — Deterministic site-geometry foundation

## P2B1 当前决策覆盖（2026-09-15）

P2A 的历史 Option C 推荐已由 Charles 正式裁决为当前
`OPTION_C_APPROVED_MANEUVER_TEMPLATES`。本覆盖只说明 P2B1 的独立合同实现，
不改写下方 P2A 历史授权快照，也不启动 placement。

```ini
TRUCK_REPRESENTATION=OPTION_C_APPROVED_MANEUVER_TEMPLATES
TRUCK_REPRESENTATION_OWNER_APPROVED=true
OPTION_A_REJECTED_FOR_V2_2=true
OPTION_B_REJECTED_FOR_V2_2=true
DEFAULT_TRUCK_ALLOWED=false
DEFAULT_MANEUVER_GEOMETRY_ALLOWED=false
KINEMATIC_TRUCK_SOLVER_REQUIRED=false
P2B1_TEMPLATE_CONTRACT=IMPLEMENTED_DRAFT_REVIEW
PLACEMENT_SEARCH_IMPLEMENTED=false
OBJECTIVE_PROFILE_FROZEN=false
P2_COMPLETE=false
P3_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P2B1 使用 P2A 的 `normalize_polygon` 作为项目机动包络的唯一二维几何边界，
增加 `TruckManeuverTemplateV1`、模板集合、需求绑定、项目组合输入和离散
0/90/180/270 度变换。它不生成模板、不寻找路线、不验证场地放置，也不改变
P2A 的 site geometry、旧 P1F 输入或任何 zone authority。

## Current status

```ini
TASK_ID=V2_2_P2A_SITE_GEOMETRY_FOUNDATION_R1
TARGET_VERSION=v2.2.0
BASE_MAIN_SHA=50210aa7cc876ed8a93a099c82ef4a4f287da82a
ACTIVE_GOVERNANCE_LANE=V2.2_P2
P1_COMPLETE=true
P1_CLOSURE_BLOCKERS=NONE
P2_AUTHORIZED=true
P2A_STATUS=IMPLEMENTED_DRAFT_REVIEW
P2_PLACEMENT_ENGINE_COMPLETE=false
P2_OBJECTIVE_PROFILE_FROZEN=false
P2_TRUCK_TURNING_REPRESENTATION_FROZEN=false
NO_MCP_TOOL_7=true
P3_AUTHORIZED=false
P4_AUTHORIZED=false
P5_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
GITHUB_RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P2A is the first executable geometry layer after the merged P1 handoff. It
validates a project site and supplies exact predicates for later placement; it
does not place any zone, choose flexible dimensions, generate a building
footprint, search routes, or produce a drawing.

## Authority boundary

The input boundary is `SiteLayoutProjectInputV1` plus the current
`p1-project-access-handoff@1.0.0`. P2A validates the handoff identity and
status, but does not re-run or replace its zone-plan, dimension, access, or
truck authority. `required_area_m2`, position counts, room counts, packing
geometry, shipping platform counts, the nine concrete dimensions, and the
three flexible authorities remain upstream facts.

```ini
ZONE_AREA_RECALCULATION_ALLOWED=false
FIXED_RECTANGLE_RESIZE_ALLOWED=false
DETERMINISTIC_GRID_RECTANGLE_RESIZE_ALLOWED=false
FLEXIBLE_RECTANGLE_P2_DIMENSION_SELECTION_ALLOWED=true
P1_HANDOFF_MUTATED=false
P1_DIMENSIONS_MUTATED=false
P1_ACCESS_AUTHORITY_MUTATED=false
```

The three flexible zones (`coating_room`, `changing_room`, and `office`) remain
dimension authorities without final width/depth. P2A only validates a future
candidate: positive, finite, 0.001 m-grid width/depth and exact product at
least the approved required area. It adds no ratio, square, or process-side
assumption.

## Geometry model

`site-geometry-foundation@1.0.0` uses local Cartesian metres and converts every
coordinate to integer millimetres (`1 m = 1000` units) at the validation
boundary. No floating epsilon, binary-float accumulation, implicit rounding,
or unordered final collection is used.

`site_boundary` and explicit `buildable_boundary` are simple, implicitly closed
polygons. They require at least three distinct vertices, positive area, finite
non-boolean coordinates on the 0.001 m grid, non-zero edges, and no repeated
vertices, self-intersection, or self-touch. Holes and multipolygons are not
accepted. A buildable polygon must be wholly contained in the site, including
its edges; shared boundary is allowed. If omitted, the effective buildable
boundary is the site boundary and the source is recorded as
`SITE_BOUNDARY_DEFAULT`.

No-build polygons must be valid and inside the site. Existing-building
footprints must be valid simple polygons inside the site; the orthogonal-only
restriction applies only to the future supplied building-footprint primitive,
not to an existing obstacle. Retained buildings are hard obstacles.
Non-retained buildings are recorded as conditional removal
footprints with `removal_authorized=false`; they are not silently removed or
treated as clear land. A successful foundation result warns
`NON_RETAINED_BUILDING_REMOVAL_CONFIRMATION_REQUIRED` when such a footprint is
present.

Entrances are positive-length segments whose entire segment lies on the site
boundary. The validator accepts a segment spanning consecutive collinear
boundary edges, but rejects an endpoint-only chord through the interior. Main
and truck entrances may overlap; positive overlap is recorded as
`shared_entrance=true`.

`PlacedRectangleV1` is an observation/primitive for later placement. Its `x`
and `y` are the lower-left coordinates of the post-rotation axis-aligned
footprint; `width_m` and `depth_m` are the unrotated positive dimensions;
`rotation_deg` is only 0 or 90. At 90 degrees the extents swap. Rectangle
overlap means positive-area interior overlap. Shared positive-length edges are
separate from overlap, and corner-only contact is neither overlap nor
adjacency. A zone may touch the effective buildable boundary, but it may not
touch or overlap a closed no-build/retained obstacle.

The building-footprint predicate accepts a supplied rectangle or orthogonal
polygon only. It never generates a bounding box, convex hull, or envelope.

## Canonical foundation result

`ValidatedSiteGeometryV1` records:

- identity and schema version;
- canonical hashes of the project input and P1 handoff;
- site and effective buildable polygons;
- normalized main/truck entrances and their shared flag;
- no-build, retained, and conditional-removal obstacle records;
- coordinate system and 0.001 m grid;
- project truck-input status, while explicitly marking that no truck geometry
  or turning solver was used;
- validation warnings and `requires_review=true`.

It deliberately has no zone `x/y`, final building footprint, route, portal,
SVG, PDF, or DXF. The result is deterministic under mapping-key reordering and
ambient Decimal-context changes. Collection ordering is canonicalized by
stable identifiers or canonical polygon content.

The P2A non-scope is explicit: `NO_LAYOUT_ALGORITHM_IMPLEMENTATION` and
`NO_SVG_GENERATION` (as well as no PDF/DXF/CAD, route search, portal placement,
or MCP Tool 7). These capabilities remain separately gated after review.

The hard predicates exposed for later P2 work are:

```text
rectangle_inside_polygon
rectangles_overlap
rectangles_share_positive_edge
rectangle_intersects_closed_obstacle
```

These predicates are foundation checks only. They do not claim adjacency,
access, route feasibility, or a complete layout PASS.

## Truck representation decision package

P1F project input supplies vehicle width/length and traceable evidence slots,
but the evidence slots are not solver geometry. P2A intentionally does not
invent a turning radius, Ackermann model, default vehicle, or maneuver
clearance.

| Option | Machine representation | Benefit | Remaining risk / decision |
| --- | --- | --- | --- |
| A | Project-supplied, versioned swept-envelope polygon/template | Directly tests the actual hard envelope and keeps solver deterministic | Each project must provide valid geometry and an approved version; provenance and maneuver applicability must be defined |
| B | Project vehicle kinematic parameters | Can derive multiple maneuvers from a vehicle model | Requires Owner-approved kinematics, steering assumptions, motion discretization, and a deterministic swept-path algorithm |
| C | Approved maneuver templates with versioned envelope geometry | Limits the solver surface and makes reviewable maneuvers explicit | Owner must approve the template catalogue and when each template applies |

The architecture recommendation is **Option C** for the first implementation:
approved maneuver templates keep the geometry authority explicit without
silently turning evidence references into a kinematic solver. This is a
recommendation, not an Owner decision.

```ini
P2A_TRUCK_TURNING_REPRESENTATION_DECISION_REQUIRED=true
RECOMMENDED_TRUCK_REPRESENTATION=OPTION_C_APPROVED_MANEUVER_TEMPLATES
MINIMUM_OWNER_DECISION_REQUIRED=SELECT_A_B_OR_C_AND_APPROVE_ONE_VERSIONED_MACHINE_GEOMETRY_CONTRACT
TRUCK_TURNING_SOLVER_IMPLEMENTED=false
```

The future decision must also state whether a supplied envelope represents a
straight approach, a 90-degree maneuver, reversing to a dock, or another
named maneuver. P2A does not use those values in geometry validation.

## Error and non-goal boundary

Input errors retain `INVALID_INPUT`, `INVALID_SITE_BOUNDARY`, and the specific
boundary/obstacle/entrance errors. `INSUFFICIENT_BUILDABLE_AREA`,
`HARD_CONSTRAINT_UNSATISFIABLE`, `LAYOUT_INFEASIBLE`, and
`LAYOUT_SEARCH_EXHAUSTED` remain distinct. P2A performs no placement search,
so it cannot claim a search-based infeasibility result; resource exhaustion is
not relabeled as infeasibility.

The following remain outside this task:

```ini
PLACEMENT_SEARCH_IMPLEMENTED=false
OBJECTIVE_PROFILE_IMPLEMENTED=false
BUILDING_FOOTPRINT_SOLVER_IMPLEMENTED=false
CORRIDOR_ROUTING_IMPLEMENTED=false
PORTAL_PLACEMENT_IMPLEMENTED=false
TRUCK_TURNING_SOLVER_IMPLEMENTED=false
SVG_IMPLEMENTED=false
PDF_IMPLEMENTED=false
DXF_IMPLEMENTED=false
MCP_CHANGED=false
FRONTEND_CHANGED=false
DATABASE_MIGRATION_CREATED=false
```

P2A is therefore `IMPLEMENTED_DRAFT_REVIEW`, not P2 completion, layout
acceptance, release readiness, or authorization of the next phase.
