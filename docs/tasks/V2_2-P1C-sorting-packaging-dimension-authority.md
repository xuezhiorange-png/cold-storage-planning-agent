# V2.2 P1C — Sorting packaging dimension authority

## Separate authorization and current state

```ini
TASK_ID=V2_2_P1C_SORTING_PACKAGING_DIMENSION_AUTHORITY_R1
BASE_MAIN_SHA=7785e877461a2c82980ed4e318bd04eabc0287df
PREVIOUS_PR=273
P1C0_STATUS=MERGED
P1C_AUTHORIZED=true
P1C_STATUS=IMPLEMENTED_DRAFT_REVIEW
CALCULATOR_IDENTITY=zone_dimensioning_foundation@1.3.0
RESULT_SCHEMA_VERSION=1.1.0
SORTING_PROFILE=upstream-sorting-long-edge-envelope@1.0.0
DIMENSIONED_ZONE_COUNT=7
BLOCKED_ZONE_COUNT=5
NO_EPSILON=true
NO_GEOMETRY_INFLATION=true
ZONE_PLANNER_CHANGED=false
MCP_RUNTIME_CHANGED=false
SITE_PLACEMENT_IMPLEMENTED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
P2_AUTHORIZED=false
TAG_AUTHORIZED=false
GITHUB_RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

This is a profile-set revision, not a new zone planner. The existing P1C0 schema
already carries area requirements and provenance, so its shape remains 1.1.0;
the production calculator advances from 1.2.0 to 1.3.0. Historical approvals and
six-zone evidence are not rewritten.

## Upstream authority and approved envelope

Only a successful `cold_room_zone_plan@1.0.0` snapshot with exact 12-zone identity
and `POST-V2.1.1-charles-engineering-rule-adjustments` formula authority reaches
the internal binder. No new user/MCP/frontend input is introduced.

The selected sorting grid is consumed, not searched or recalculated. Upstream
`_pack_sorting_rectangle` uses long pitch 5.6 m, short pitch 3.0 m, long clearance
8.0 m and short clearance 7.6 m. Its existing rectangle has edges
`(n_long-1)*5.6+8.0` and `(n_short-1)*3.0+7.6`.
Charles's dimension authority applies the existing 1.1 factor to the **long edge
only**. This is not an additional area factor: the envelope equals the already
scaled exact requirement. No aspect-ratio optimization, table/worker count
recalculation, capacity repacking or free rectangle search is allowed.

The binder cross-checks positive integer counts, duplicate grid metadata,
`n_actual=n_long*n_short=position_count`, `table_count=n_need`, unused cells,
`four_side_architectural`, raw rectangle area and the existing factor. A mismatch
blocks sorting; it never repairs upstream engineering data.

## Exact/reporting precision chain

`ExactAreaAuthorityV1` binds source JSON and a freshly computed source hash,
approved profile identity/authority, and the exact ordered source paths
`/raw_required_area_m2` and `/sorting_packaging_area_factor`.
The exact product uses Decimal; reported `required_area_m2` remains unchanged.
`cold-room-zone-plan-binary64-product-2dp@1.0.0` must reproduce the reported value.
The profile identity, authority and capacity reference must match that evidence.
Hashes bind content; they do not authenticate a caller or confer Owner approval.
The binder is internal, and exposes no exact/profile/hash override API.

Both the generic precheck and final model use the same
`AreaRequirementV1.geometric_lower_bound_m2`. Missing exact authority retains the
strict reported lower bound. Invalid exact authority never falls back. No epsilon,
rounding alias or geometry inflation is introduced.

## Representative 20t replay

Input: 20000 kg/day, finished 7 days, frozen 10 days, main packaging 4 days,
auxiliary packaging 12 days. Upstream n_long=7, n_short=3, n_actual=21.

| Quantity | Value |
| --- | --- |
| Raw upstream area | 565.76 m² |
| Factor | 1.1 |
| Width / depth | 45.76 / 13.60 m |
| Exact requirement / actual geometry | 622.336 / 622.336 m² |
| Reported requirement | 622.34 m² |

All six existing storage/precool dimension records, including capacity references,
remain identical to the PR #273 merge snapshot. Only sorting changes BLOCKED to
DIMENSIONED. Remaining blocked zones: office, changing_room, coating_room,
packaging_material_storage, shipping_channel. No new authority for these five.
Access remains ACCESS_PROFILE_REQUIRED; no placement, x/y, building footprint,
SVG/PDF/DXF, Tool 7, API, database or deployment work is included.
Concept planning only, requires_review=true; not construction drawings.

## Verification and immutable history

P1C tests replay the real production application, hostile source mutations,
strict lower-bound paths, six-zone record equality, deterministic JSON/hash,
and nine throughput grids. Historical P1A/P1B/P1C0 six-zone integration oracles
read the immutable application profile set at PR #273 merge
`7785e877461a2c82980ed4e318bd04eabc0287df`; generic domain tests remain live.
The historical no-binder architecture assertion also reads that snapshot.
The P1C scope guard records its introducing commit, with precommit candidate
checking; future HEAD is only an ancestry check, never a moving historical endpoint.
Local targeted, architecture, full SQLite, Ruff/format and mypy results and the
exact-head BACKEND CI are recorded in the Draft PR evidence.
