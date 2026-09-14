# V2.2 P1D3 — Hybrid dimension authority handoff

TASK_ID=V2_2_P1D3_FLEXIBLE_RECTANGLE_HANDOFF_CONTRACT_R1
BASE_MAIN_SHA=a848c2a3b44c6625db7a2546596f4bb3ceb3d7d3
PREVIOUS_PR=275
PREVIOUS_STATUS=MERGED
ACTIVE_LANE=V2.2_P1
DIMENSION_AUTHORITY_MODEL=HYBRID
P1_REQUIRES_ALL_12_ZONES_FIXED_WIDTH_DEPTH=false
P1_REQUIRES_ALL_ZONES_HAVE_DIMENSION_AUTHORITY=true
P2_IMPLEMENTATION_AUTHORIZED=false
ACCESS_PROFILE=SEPARATE_P1E
NO_STEP_IMPLIES_THE_NEXT=TRUE

## Separate versioned API and historical compatibility

`build_dimension_handoff(canonical_zone_plan)` is the new internal P1→P2 authority
entrypoint: `hybrid_zone_dimension_handoff@1.0.0`, handoff schema `1.0.0`.
This is a new schema family, not reuse of old dimensioning schema 1.2.0.
The old `dimension_zones()` / `zone_dimensioning_foundation@1.4.0` API and all
eight complete geometry records stay unchanged. Its historical four missing
profiles do not define the new handoff's statuses. No MCP/API registration changes.

`authorities[12]` is the complete dimension-authority collection; `dimensions`
contains only concrete results. Success at this boundary means
DIMENSION_AUTHORITY_COMPLETE, not site feasibility, access acceptance or P1 closure.
Blocked candidates stay BLOCKED with their exact reason; never fake dimensions.

Three explicit handoff classes:

| Class | Current bindings | P2 rights |
|---|---|---|
| FIXED_RECTANGLE | Approved precool room-combination envelopes | translate/rotate later; no resizing or capacity repacking |
| DETERMINISTIC_GRID_RECTANGLE | Existing storage, sorting, shipping; new packaging envelope | dimensions already bound; no resizing |
| FLEXIBLE_RECTANGLE | coating, changing, office | choose final positive dimensions under site/adjacency/obstacle/orientation constraints |

These are new handoff classifications, not renamed historical profile modes.
All classes preserve canonical required_area and area_requirement, source hash,
profile/authority identity, 0.001m grid and rotation 0/90. P1C0 verified exact-area
projection rules remain unchanged for existing dimensions; new flexible/packaging
rows use the reported hard lower bound with no epsilon or tolerance.

## Flexible authority schema

Each flexible row has zone_code, dimension_mode, status=FLEXIBLE_AUTHORIZED,
required_area_m2, area_requirement, dimension_authority_identity, source_zone_hash,
authority, grid_m, rotation_allowed, nullable min/max_width_m/min/max_depth_m and
aspect_ratio_bounds, orientation_constraints, required_connection_edges and P2 rights.
It has **no width_m, depth_m, actual_area_m2, geometry, x or y**.
Null/empty constraints do not invent any numeric restriction. The future solver's
finite domain is bounded by the site and existing hard constraints, not guessed ratios.
Final successful layout still has twelve concrete positive rectangular geometries.
SiteLayoutInputV1 remains unchanged. Future result/provenance must bind this handoff
identity/hash and chosen flexible dimensions; no current site result is produced.

- Coating: no fixed dimensions, no ratio or process-side constraint; retain
  secondary→coating→finished MUST chain. P2 chooses dimensions, never area.
- Changing: same area bands and PEOPLE flow; no ratio, gender/clean-dirty partition
  or internal geometry inferred.
- Office: same area bands, MUST shipping, SHOULD primary precooling. No personnel
  portal to shipping is authorized by the adjacency. No unapproved dimension values.

## Packaging candidate profile

`packaging-integer-envelope@1.0.0` binds canonical position_count and required area.
PALLET_MODULE=1.2x1.0m; pallet rotation 0/90; longitudinal aisle minimum=3.0m.
PACKAGING_K_SEMANTICS=UNDECOMPOSED_AREA_FACTOR
PACKAGING_AISLE_IS_GEOMETRY_CONSTRAINT_NOT_ADDITIVE_AREA=true

Candidate family is uniform-orientation integer rows/columns with residual envelope
space; both pallet orientations are enumerated. No mixed-orientation/free-form
packing, aisle-routing, stacking, forklift or per-position access compliance claim.
For each rows=1..N, columns=ceil(N/rows); extra empty columns are dominated by the
same envelope as residual space. Unused final-row cells remain explicitly counted.
Long minimum=columns×oriented module edge; short minimum=rows×other edge+3m.
The aisle uses its minimum3m because no wider geometry is needed to satisfy this
dimension-only contract; a future access requirement cannot be silently assumed.

For every short-edge grid candidate, choose the least long edge satisfying module,
long≥short and area. Enumerate short≤sqrt(incumbent area), an exact integer search
bound, **not** an engineering aspect ratio or guessed square. Search never derives
a square from area as an unapproved dimension authority.

Rank: minimum actual area; minimum perimeter; minimum long/short ratio; numeric
rows/columns/orientation lexical tie-break; final numeric edges. Area+perimeter
already determine the unordered edges, so equal first two imply equal ratio.
Integer millimetre arithmetic and isolated Decimal conversion; no float/epsilon.
For equal edges, the width axis is the designated longitudinal/aisle axis, not a
cardinal direction. No pallet or zone coordinates generated.

Resource caps (10000 positions/2000000 grid candidates) are implementation limits,
not engineering coefficients. Exceeding either returns PACKAGING_SEARCH_RESOURCE_LIMIT
and BLOCKED rather than selecting from a truncated search or recalculating counts.

20t canonical example (20000kg/day, finished7, frozen10, main-pack4, auxiliary12):
67 positions; required250.85m²; chosen4rows×17columns, one unused cell, pallet90°;
width17.3m×depth14.5m=250.85m². Required area is copied, not recomputed from k or
1.2×1.0, and **no aisle area is added to it**.

## Edge-oriented packaging connection

Separate `EdgeOrientedConnectionV1`, identity `packaging-sorting-edge-connection@1.0.0`:

from_zone=packaging_material_storage
from_edge_class=LONG_EDGE
to_zone=sorting_packaging_room
to_edge_class=SHORT_EDGE_EXIT_SIDE
connection_required=true
direction_alignment_required=true
direct_allowed=true
corridor_allowed=true
portal_access_profile_required=true

DIRECT_SHARED_EDGE and CORRIDOR_MEDIATED are accepted **topology alternatives**;
the membership predicate is not a geometry/route validator. No additional MUST or
SHOULD pair or duplicate PACKAGING flow is added. Current graph remains7MUST/5SHOULD.
Connection cannot be satisfied merely by proximity or downgraded to SHOULD.

Sorting authority adds material_exit_edge_class=SHORT_EDGE in the new handoff,
not in its old geometry record. The actual one of two opposite short edges is
chosen later under the P2 connection constraints; no north/east or fixed sign is
invented. Rotation must map the selected relative edge to world geometry in P2.
Packaging long edge must face that exit side, directly or via an aligned connection.

## Access and non-goals

ACCESS_PROFILE_REQUIRED=true. P1E separately freezes corridor/portal/pedestrian/
forklift/cold-door/truck authority. No path or portal size is invented here.
Connection status stays NOT_EVALUATED_ACCESS_PROFILE_REQUIRED. Office/shipping
adjacency is not authorization for a door directly onto the loading face.
No P2 placement/optimization, x/y, footprint, routing, SVG/PDF/DXF, Tool7, frontend,
zone-planner, migration, tag/release or deployment work.

## Verification / stop gate

Current tests replay canonical input, validate9concrete/3flexible, exact old-eight
equality, mutable-copy rejection, deterministic search/rotation/aisle/lower bound,
topology alternatives, unchanged flow/graph and persistent scope. Full test and
exact-head CI results are recorded in the Draft PR metadata.

READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
P2_AUTHORIZED=false
TAG_AUTHORIZED=false
GITHUB_RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
