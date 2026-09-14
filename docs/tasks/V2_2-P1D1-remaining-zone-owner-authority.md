# V2.2 P1D1 — Remaining-zone Owner authority

```ini
TASK_ID=V2_2_P1D1_REMAINING_ZONE_OWNER_AUTHORITY_R1
BASE_MAIN_SHA=4f8c3a0c3b8e866695a917990588caffdd60defc
P1C_STATUS=MERGED
P1D1_STATUS=IMPLEMENTED_DRAFT_REVIEW
CALCULATOR_IDENTITY=zone_dimensioning_foundation@1.4.0
RESULT_SCHEMA_VERSION=1.2.0
ADJACENCY_IDENTITY=charles-v22-process-flow@1.1.0
SHIPPING_PROFILE=shipping-pit-module-envelope@1.0.0
SHIPPING_CHANNEL_FIXED_WIDTH_M=6.5
SHIPPING_LOADING_FACE=LONG_EDGE
SHIPPING_SINGLE_PIT_WIDTH_M=2.0
SHIPPING_MIN_PIT_TO_PIT_CLEARANCE_M=2.5
SHIPPING_MIN_PIT_TO_SIDE_WALL_CLEARANCE_M=2.5
COATING_FIXED_DIMENSION_AUTHORITY=false
COATING_AREA_AUTHORITY=AVAILABLE
COATING_DIMENSION_AUTHORITY=NOT_FROZEN
COATING_REMAINS_BLOCKED=true
PACKAGING_MODULE_AUTHORITY=PARTIAL
PACKAGING_POSITION_MODULE=1.2x1.0m
PACKAGING_LONG_EDGE_AISLE_MIN_M=3.0
PACKAGING_ROW_COLUMN_RULE_AUTHORIZED=false
PACKAGING_DIMENSION_PROFILE_IMPLEMENTED=false
OFFICE_DIMENSION_STATUS=BLOCKED
OFFICE_ADJACENCY_AUTHORITY=UPDATED
CHANGING_ROOM_DIMENSION_AUTHORITY=NOT_FROZEN
CHANGING_ROOM_REMAINS_BLOCKED=true
DIMENSIONED_ZONE_COUNT=8
BLOCKED_ZONE_COUNT=4
ZONE_PLANNER_CHANGED=false
MCP_RUNTIME_CHANGED=false
SITE_PLACEMENT_IMPLEMENTED=false
NO_EPSILON=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
P2_AUTHORIZED=false
TAG_AUTHORIZED=false
GITHUB_RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## Shipping authority and deterministic binding

Charles independently approved a 6.5m short edge, loading on the long edge,
2.0m per pit, at least 2.5m between pits and at least 2.5m at **each** side wall.
The existing application validates the successful canonical twelve-zone snapshot
and formula identity before binding shipping. Platform count and required area
are read unchanged; position_count must agree with platform_count. No count is
recomputed from pallet/truck metadata. No caller profile override is exposed.

For N=platform_count, minimum loading edge = 2×2.5 + N×2.0 + (N−1)×2.5.
Final loading edge is ceil-to-0.001m(max(minimum, required_area_m2/6.5)), under
an isolated Decimal context. The final dimension model still enforces the strict
reported area lower bound (no exact-area relaxation for shipping).

Coordinate-independent convention: width_m=6.5 (short edge), depth_m=loading
long edge. loading_face=LONG_EDGE and loading_edge_dimension=depth_m explicitly
identify that convention; no x/y, pit positions, entrance position or loading
cardinal direction is generated. These are envelope constraints, not access approval.

## Actual 20t canonical replay

For 20000kg/day, finished7/frozen10/main-packaging4/aux-packaging12 days:
platform_count=1, required_area_m2=50.00. Pit minimum is 7.0m; its area is 45.5m²,
so **AREA** controls. Rounded loading edge=7.693m; width=6.5m;
actual_area=50.0045m². One shorter grid step (7.692m) cannot satisfy 50m².
No epsilon, capacity recalculation or arbitrary aspect-ratio search is used.

Profile metadata exposes the approved pit/clearance values, minimum loading edge
and controlling constraint. It does not assign surplus space to fabricated pit positions.
Current canonical area is still 50m² per platform, so its positive platform cases
are area-controlled. Pit-controlled unit cases deliberately use synthetic area
requirements to exercise the independent geometric bound, not a new area formula.
The existing seven complete dimension records remain identical to PR #274 merge.
The calculator advances 1.3.0→1.4.0; schema advances 1.1.0→1.2.0 for shipping
profile/envelope evidence. Historical snapshots retain their prior identities.

## Adjacency, not a new directed flow

The existing six main-chain MUST pairs and all directed flows are unchanged.
Append office↔shipping_channel as MUST, office↔primary_precooling_room as SHOULD.
Current totals: seven MUST, five SHOULD; graph identity advances to 1.1.0.
No office dimension is inferred. Office/shipping zone adjacency does not imply
office adjacency to the truck loading face, nor establish safety separation.

## Deliberately incomplete authority

Coating has valid area authority but no frozen dimensions. No fixed rectangle,
square root, ratio or future adaptive site dimensioning is introduced.
Packaging's 1.2×1.0m pallet module and long-edge aisle≥3m are **recorded only**.
Rows/columns, single/double/multiple rows and whether k includes aisle geometry
remain unresolved. No production packaging profile is created.
Changing room receives no new authority. Office only receives adjacency changes.
Blocked set: coating_room, packaging_material_storage, changing_room, office.

Access remains ACCESS_PROFILE_REQUIRED. No external truck turning, roads,
site placement, footprint, SVG/PDF/DXF, Tool7, MCP, frontend, database, tag,
release or deployment changes. Concept planning only; requires_review=true.

## Verification / history

Tests cover 20t, 1/2/3/multiple platforms, both controlling bounds, exact grid
ties and just-above-grid cases, malformed counts, unchanged source and seven
dimension records, four blocked zones, office relations and deterministic hashes.
Historical P1C application/graph is read from immutable PR #274 merge; original
count/flow oracles are not rewritten to masquerade as the new revision.
Current P0/P1A contract-to-runtime locks explicitly include the separately approved
office relations while preserving all original main-chain pairs.
Task scope uses its introducing commit, with precommit candidate validation;
future HEAD is only ancestry, not a moving historical diff endpoint.
Local regression/full SQLite/static checks and exact-head CI results are recorded
in the Draft PR evidence. Ready/Merge and P2 require separate authorization.
