# V2.2 P2D — Access routing and truck validation

## Current status

```ini
TASK_ID=V2_2_P2D_ACCESS_ROUTING_AND_TRUCK_VALIDATION_R1
TARGET_VERSION=v2.2.0
BASE_MAIN_SHA=99116fb8f5999461f718ad6a4d5747f1ec865716
ACTIVE_GOVERNANCE_LANE=V2.2_P2
P2D_AUTHORIZED=true
P2D_STATUS=IMPLEMENTED_DRAFT_REVIEW
ROUTING_IMPLEMENTED=true
ACCESS_ROUTE_VALIDATED=true|false
TRUCK_ROUTE_VALIDATED=true|false
PROJECT_LAYOUT_VALIDATED=true|false
P2_COMPLETE=true|false
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

P2D consumes one verified P2C placement, the verified P1 project handoff, the
P2A `ValidatedSiteGeometryV1`, the P2C-selected shipping loading face and the
project-bound P2B1 maneuver input. The implementation is result-conditional:
the four validation flags become `true` only when every required predicate for
that supplied project input passes. A valid representative fixture is covered
end to end; an incomplete or infeasible input remains explicitly blocked.

## Access authority and route results

The twelve access requirements are copied from
`p1e_historical_handoff.access_requirements` after the existing P1 authority
binding has revalidated the handoff. P2D does not regenerate the process graph,
profiles, widths or access relationships. Each requirement produces exactly
one access result and one placement access observation. The result preserves
the P1 identity, from/to references, flow/access class, profile, topology flags,
edge-orientation requirement and route-shape requirement, then adds the
observed portal, centerline, corridor envelope, evaluation status and codes.

Direct shared-edge access is attempted first. A generated portal is centered on
the shared edge before deterministic endpoint alternatives are considered; it
must remain wholly on the positive-length shared edge and satisfy the
server-owned portal width. When direct access is unavailable and the P1
requirement permits a corridor, P2D searches a finite orthogonal anchor graph
with the profile-specific clear width. The search uses integer millimetres on
the existing `0.001m` grid, has a deterministic node budget, and has no
wall-clock timeout or floating-point epsilon. Budget exhaustion is reported as
`ROUTE_SEARCH_EXHAUSTED`, not as an infeasibility proof.

The packaging-material connection keeps its separate P1 edge authority:

```ini
FROM=packaging_material_storage
FROM_EDGE=LONG_EDGE
TO=sorting_packaging_room
TO_EDGE=SHORT_EDGE_EXIT_SIDE
ROUTE_SHAPE=STRAIGHT_ONLY
```

It may be direct or corridor-mediated, but a corridor route must have zero
turns and must satisfy the orientation relationship. It is not converted into
an ordinary shared-edge adjacency.

The P2D route layer reuses the P1 predicate semantics for profile, portal,
corridor, edge alignment and the packaging straight-route check. It does not
recalculate any engineering value. Route lengths are exposed as factual
metrics only; route-objective optimization remains inactive because the route
objective order is not frozen.

Corridors are portal-only at incident zone boundaries. An incident zone's
interior is never a transit surface: the open interval immediately after the
origin portal and immediately before the destination portal must leave/enter
through the selected portal, and positive-area corridor-envelope overlap with
an incident zone is rejected. Exact boundary contact at the selected portal
is permitted; this check does not rely on a segment midpoint.

## Truck validation and personnel policy

Truck validation requires a complete, project-bound
`BoundTruckManeuverProjectInputV1`. There is no default vehicle, turning radius,
template or envelope. P2D revalidates the P1F vehicle binding, project
provenance, template hashes and required maneuver classes before using the
existing `OPTION_C_APPROVED_MANEUVER_TEMPLATES` representation.

The finite chain search uses the supplied `STRAIGHT_APPROACH`, `TURN_90` and
`DOCK_REVERSE` templates, exact 0/90/180/270 degree transforms and exact pose
continuity. The first entry must be on the supplied truck entrance segment and
the final dock pose must be on the P2C-selected shipping loading-face segment.
Every transformed envelope must be inside the effective buildable boundary,
clear of hard obstacles and clear of indoor zone interiors. Search exhaustion
is reported as `TRUCK_MANEUVER_SEARCH_EXHAUSTED`; it is not renamed to an
infeasibility proof.

Personnel/truck interaction preserves the P1 policy: shared routes are
prohibited. Geometry may detect a crossing/contact, but it does not establish
that the crossing is necessary. Without a separate engineering authority the
result is `REQUIRES_ENGINEERING_REVIEW` with
`crossing_necessary=UNDETERMINED`; that status cannot make a final project
layout valid. A route with neither shared overlap nor crossing passes.

## Building footprint and final validation

For a placement whose eleven non-truck access requirements pass, P2D derives a
non-optimized orthogonal building footprint from the twelve zone rectangles and
the generated personnel/material corridor envelopes. It must contain all
indoor rectangles and corridors, remain inside the effective buildable boundary
and clear hard obstacles. P2D does not optimize compactness, shape regularity
or unused-site efficiency.

The canonical `site_validated_layout@1.0.0` result binds:

```text
source_zone_plan_hash
source_p1_handoff_hash
source_site_geometry_hash
source_objective_profile_hash
source_placement_result_hash
source_truck_maneuver_binding_hash
```

It contains the twelve zone records, selected shipping loading face, portals,
corridors, twelve access results and observations, truck maneuver chain and
envelopes, personnel/truck evaluation, building footprint, factual route
metrics, warnings and a canonical result hash. `p2_complete` is true only when
placement hard constraints, all twelve access results, the truck chain,
personnel/truck policy and footprint validation all pass without unresolved
review.

## Explicit boundaries

P2D does not change zone areas, dimension authority, the P2B2 objective profile,
the factory-power calculator, MCP tools, frontend behavior, database schema or
the P2C placement search. It does not implement Ackermann or steering
kinematics, route optimization, SVG, PDF, DXF, CAD, deployment or release
activity. P3, P4 and P5 remain separately authorized stages.

## R2 review correction (2026-09-15)

The two review corrections are deliberately limited to validation trust
boundaries:

```ini
INCIDENT_ZONE_INTERIOR_TRANSIT_ALLOWED=false
PORTAL_ONLY_ZONE_BOUNDARY_TRANSIT=true
CROSSING_NECESSITY_INFERRED_FROM_GEOMETRY=false
CROSSING_WITHOUT_AUTHORITY_REQUIRES_REVIEW=true
```

The representative full-pass fixture remains a no-crossing case, so it still
validates the complete P2D gate. No placement search, truck maneuver template,
route objective, MCP, frontend, database or P3 behavior changed.
