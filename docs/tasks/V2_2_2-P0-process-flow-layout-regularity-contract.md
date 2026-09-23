# V2.2.2 P0 — Process Flow and Layout Regularity Contract

```ini
TASK_ID=V2_2_2_P0_PROCESS_FLOW_AND_LAYOUT_REGULARITY_CONTRACT_R1
TARGET_VERSION=v2.2.2
ACTIVE_GOVERNANCE_LANE=V2.2.2_P0
BASE_MAIN_SHA=64f335bbfbbaf061b9ba08c18f2068db411f8922
CURRENT_RELEASE=v2.2.1
P0_CONTRACT_ONLY=true
RUNTIME_IMPLEMENTATION_AUTHORIZED=false
P1_IMPLEMENTATION_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
GITHUB_RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NEXT_PHASE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

## 1. Purpose and boundary

V2.2.1 established a technically validated 12-zone layout and deterministic
drawing projections. Owner acceptance found that technical validity did not
guarantee a legible factory organization: the layout could look like unrelated
rectangles, make the main product path double back, and lack coherent bands,
axes, depth alignment, or an orderly exterior. This is a layout-generation,
candidate-quality, and process-flow gap—not an SVG styling or sheet-composition
gap.

This P0 freezes the audit result and the next-version domain contract only. It
does not implement any metric, score, candidate generator, selector, route,
placement, or projection behavior. Structured layout JSON remains the sole
engineering geometry authority. Golden drawings and screenshots may inform
organization patterns, never project dimensions or runtime engineering rules.

## 2. Baseline and source evidence

The canonical `origin/main` and `v2.2.1` tag both resolve to
`64f335bbfbbaf061b9ba08c18f2068db411f8922`. This contract treats that release
as historical evidence, not an output that future geometry changes must hash
match.

The inspected implementation has these responsibilities and limits:

| Layer | Current behavior evidenced in source | What it does not establish |
| --- | --- | --- |
| P2C `domain/placement.py` | Deterministic bounded anchor/edge DFS; constrained-first fixed zone order; exact geometry predicates; candidate options locally sorted by SHOULD count then stable geometry keys; a finite node budget and per-zone option cap. | It does not construct semantic process bands, score backtracking or main-flow turns, align major rooms to a shared axis/depth, or rank building outline regularity. |
| P2B2 objective profile and P2C comparator | Lexicographic ranking: five SHOULD adjacencies satisfied, then loading-side preference (binary cardinal match or exact nearest segment distance), then canonical normalized layout JSON tie-break. | Compactness, shape regularity, unused-site efficiency, process-flow distance, circulation length, and people/truck separation are disabled or deferred. |
| P1 adjacency/process graph | Directed MATERIAL flow plus separate packaging, secondary-product, frozen-product, and people flows. MUST/SHOULD zone adjacency is currently a boolean positive shared-edge predicate; flow existence is not the same predicate. | No semantic process ranks, process-order gate, overall main-flow backtrack count, or shared-edge quality ratio. |
| P2D access/truck validation | Validates authoritative portal/corridor routes, truck maneuver templates, people/truck interactions, and derived building footprint. Per-route length and turn facts exist; packaging straight-only is enforced. | It does not aggregate routes into a process-chain objective or compute a layout-wide regularity assessment. A route passing validation is not evidence that the route is short or the overall factory is orderly. |
| P2 validated-candidate selector | Enumerates the deterministic P2C candidate family, validates candidates with P2D, and selects the highest P2C-ranked full-pass candidate among those explored; it records bounded-search provenance. | It is not a first-P2D-pass selector, but its ranking has no process-flow or regularity criteria. Exhausting a bounded family is not an infeasibility proof. |
| P4 Tool 7 | Calls the P2 validated-candidate selector and projects its selected validated result through P3. | Tool 7 does not own candidate enumeration, candidate ranking, route scoring, or layout regularity. |

The current `process_graph()` has seven directed nodes/six main MATERIAL edges,
seven MUST shared-edge pairs (the six main-chain interfaces plus
`office <-> shipping_channel`), and five SHOULD pairs. Its separate directed
side flows are packaging storage to sorting, sorting to secondary-product and
frozen-product storage, and the two PEOPLE transitions from main entrance via
changing room. `shipping_channel -> truck_entrance` is a separate access
proximity, not one of the five SHOULD objectives. Current zone adjacency is a
positive shared-edge boolean; actual portal/corridor access is separately
validated by P2D.

### Root cause

`PROJECT_LAYOUT_VALIDATED=true` currently means that engineering hard
constraints passed. It does not mean that the process order is forward, the
layout has few turns, the principal rooms share axes/depths, the building
outline is compact, or people are separated from logistics. Current P2B2
ranking values adjacency count and loading-side preference only. As a result,
a candidate can pass all access, truck, MUST-adjacency, and site predicates
and still be geometrically irregular. This is an objective/quality coverage
gap, not evidence that P2D should be weakened.

The selector does **not** return the first candidate merely because P2D passes:
it continues the deterministic P2C stream within its finite family/budget and
compares full-pass candidates using the existing P2C comparator. The correction
is to add an explicit, separately authorized quality-assessment/ranking layer
and ensure the candidate family represents orderly alternatives—not to
misstate or remove bounded-search semantics.

## 3. Frozen semantic process-flow authority

The V2.2.2 process graph is role-based. A project binds present semantic roles
to its canonical zones/interfaces; roles may be omitted only when the project
authority explicitly says that stage is absent. Omission never permits the
remaining active roles to reverse order.

| Process rank | Semantic role | Existing/current mapping | Presence |
| ---: | --- | --- | --- |
| 10 | `RAW_RECEIVING` | Explicit receiving interface/zone mapping; no automatic zone is created. | Project-bound; required when raw receiving is in scope. |
| 20 | `RAW_TEMP_STORAGE` | `raw_fruit_buffer` | Optional only when the project explicitly has no raw temporary-storage stage. |
| 30 | `PRIMARY_PRECOOL` | `primary_precooling_room` | Project process authority. |
| 40 | `SORTING_PACKAGING` | `sorting_packaging_room` | Project process authority. |
| 50 | `SECONDARY_PRECOOL` | `secondary_precooling_room` | Optional only when explicitly absent. |
| 55 | `COATING` | `coating_room` | Optional; preserves the existing V2.2 coating stage and its ordering. |
| 60 | `FINISHED_STORAGE` | `finished_goods_room` | Project process authority. |
| 70 | `SHIPPING` | `shipping_channel` plus its existing loading-face authority | Project process authority. |

Canonical ordering when roles are present:

```text
RAW_RECEIVING
  -> RAW_TEMP_STORAGE
  -> PRIMARY_PRECOOL
  -> SORTING_PACKAGING
  -> SECONDARY_PRECOOL
  -> COATING (optional)
  -> FINISHED_STORAGE
  -> SHIPPING
```

The existing frozen V2.2 zone flow
`raw_fruit_buffer -> primary_precooling_room -> sorting_packaging_room ->
secondary_precooling_room -> coating_room -> finished_goods_room ->
shipping_channel` is preserved. The new `RAW_RECEIVING` role is not silently
bound to `truck_entrance`: current truck entrance semantics concern access to
the shipping loading face. A project must supply the receiving interface and
role mapping needed to evaluate the added stage.

`PROCESS_FLOW_ORDER_PASS` is a hard quality gate over the active role sequence:
all observed process transitions must have strictly increasing rank. A missing
required role mapping, route, or direction fact is `UNAVAILABLE`, never an
implicit pass. Process flow is directed semantic authority and is not inferred
from undirected shared-edge adjacency.

## 4. Flow quality and branches

### Main-flow backtracking

`MAIN_FLOW_BACKTRACK_COUNT` counts verified reverse crossings of earlier
process-band progress along the main-flow path. It must be derived from the
ordered authoritative portal/corridor route geometry and the configured
receiving-to-shipping direction, not from zone centroids alone. A local lateral
offset or a small coordinate decrease that does not cross back into an earlier
process band is a soft geometric deviation, not a backtrack. Re-entry across a
previously passed rank boundary is a backtrack.

`MAIN_FLOW_BACKTRACK_COUNT=0` is a hard requirement for
`PROCESS_FLOW_VALIDATED=true`. Missing direction, process-band, or route facts
make the metric unavailable and fail closed. No centroid, Manhattan, or
straight-line proxy can replace an authoritative route.

### Main-flow turns

`MAIN_FLOW_TURN_COUNT` is measured on the concatenated, ordered main-flow
rectilinear route evidence. Collapse duplicate points and collinear segments;
count each orthogonal heading change once, including transitions at process
portals. Do not count zone-centroid offsets as turns. For ordinary rectangular
or near-rectangular site domains, target `<= 1`; `>= 2` receives a high
lexicographic penalty and does not satisfy the ordinary-site regularity gate.
An irregular-site exception requires
`IRREGULAR_SITE_EXCEPTION=true` plus a stable machine-readable reason tied to
the actual authoritative boundary/obstacle constraints. Search exhaustion by
itself is not an exception. The exception and its reason remain visible in the
quality result; it cannot convert a hard process-flow failure into a pass.

### Branch flows and packaging

`packaging_material_storage -> sorting_packaging_room` remains the existing
P1D3/P1E edge-oriented relationship: package-store `LONG_EDGE` to sorting
`SHORT_EDGE_EXIT_SIDE`, with its existing `STRAIGHT_ONLY` route and access
authority. It must not be weakened or turned into a requirement that the two
zones always share an edge; a valid corridor-mediated straight connection is
allowed under the existing authority.

`sorting_packaging_room -> secondary_fruit_buffer` and
`sorting_packaging_room -> frozen_fruit_room` remain side branches, not new
MUST adjacencies. Side branches must not cut across the main product flow,
force finished-goods detours, or create main-flow backtracking:
`SIDE_BRANCH_CROSSES_MAIN_FLOW=false` is required for an unqualified pass.
The branch crossing predicate must use authoritative route/corridor geometry.

## 5. Functional grouping and people/logistics separation

Future layout generation is organized `group -> band -> zone`, not as twelve
same-priority free rectangles. Functional groups are:

| Group | Semantic members/purpose |
| --- | --- |
| `RAW_SIDE_GROUP` | `RAW_RECEIVING`, `raw_fruit_buffer`, `primary_precooling_room`, and explicitly mapped raw-intake support. |
| `PROCESSING_CORE_GROUP` | `sorting_packaging_room`, `coating_room` when present, and explicitly mapped core processing. |
| `FINISHED_SIDE_GROUP` | `secondary_precooling_room`, `finished_goods_room`, and `shipping_channel`. |
| `SUPPORT_GROUP` | `packaging_material_storage`, `secondary_fruit_buffer`, `frozen_fruit_room`, and explicitly mapped auxiliary storage. |
| `PERSONNEL_GROUP` | `office`, `changing_room`, and the explicitly mapped personnel entrance/route. |

`FUNCTIONAL_GROUPING_PASS` evaluates whether these role-bound groups occupy
coherent functional bands and whether support branches remain subordinate to
the core/finished flow. Missing role mappings are unavailable. A role may not
be invented to fill a group.

People and logistics remain different access classes. Office/changing zones
must not be inserted as ordinary rectangles into the main product chain.
Personnel ingress should be on the building exterior and connected to the
personnel route, with separation from raw unloading/truck loading where the
project geometry allows. `PERSONNEL_LOGISTICS_SEPARATION` is one of
`PASS`, `CONSTRAINED_PASS`, or `FAIL`; it is never defaulted to PASS.
`PASS` requires distinct actual routes with no shared corridor. A constrained
crossing remains explicit and reviewable; it is not a regularity pass unless
future Owner criteria explicitly say otherwise. Existing P2D rules remain
unchanged in this P0.

## 6. Grid and depth alignment

Major zones for the first alignment contract are exactly:

```text
primary_precooling_room
secondary_precooling_room
sorting_packaging_room
finished_goods_room
packaging_material_storage
```

All comparisons use the existing exact 0.001 m geometry grid; no epsilon is
introduced. For one candidate, `PRIMARY_X_AXES` are x coordinates at which a
vertical boundary is shared by at least two distinct major zones;
`PRIMARY_Y_AXES` are the analogous y coordinates for horizontal boundaries.
The sets are candidate-derived evidence, not project engineering axes.
`MAJOR_ZONE_GRID_ALIGNMENT_RATE` is the count of major-zone boundary
incidences lying exactly on a primary axis divided by all x/y boundary
incidences of the five major zones. Count each zone-boundary incidence once;
do not round coordinates before comparison. Target:
`MAJOR_ZONE_GRID_ALIGNMENT_RATE >= 0.90`.

`MAJOR_ZONE_DEPTH_ALIGNMENT_RATE` evaluates compatible major-zone pairs in
the same functional band and the same local band orientation. A pair aligns
when the two corresponding near/far depth limits are exactly equal on the
existing grid. Rate is aligned eligible pairs divided by eligible pairs; zero
eligible pairs is `NOT_APPLICABLE`, not a synthetic 1.0. Same-depth/coaxial
placement is preferred for the primary precool group when that group contains
multiple explicitly modeled rooms, and for the secondary-precool/finished
storage pair when they share a finished-side band.

The `0.80` depth-rate value previously suggested is **not calibrated or frozen
as a gate in this P0**. Current P1F evidence has three full-chain fixtures but
does not contain this metric distribution; the required Xinzhao canonical
fixture is absent. Freeze the metric now; freeze a pass threshold only after
the canonical regression fixtures and declared eligible-pair policy are
evaluated and Owner accepts the threshold. Do not weaken the threshold or
pretend a sample distribution exists to obtain a pass.

## 7. Building outline and adjacency quality

`BUILDING_COMPACTNESS` is an atomic metric family, never a substitute for
individual gates:

- `BOUNDING_RECTANGLE_OCCUPANCY = orthogonal building-footprint area /
  axis-aligned footprint bounding-rectangle area`;
- `EXTERIOR_REFLEX_CORNER_COUNT` counts reflex vertices on the canonical
  orthogonal exterior boundary;
- `EXTERIOR_NOTCH_COUNT` counts classified exterior indentations using a
  versioned, deterministic polygon-topology classifier;
- `ISOLATED_APPENDAGE_COUNT` counts classified narrow/isolated appendages
  using a versioned classifier; its thresholds require Owner/fixture
  calibration and cannot be guessed from a drawing;
- `MAIN_BUILDING_COMPONENT_COUNT` is the number of connected components in
  the authoritative derived building footprint; target exactly `1`.

Ordinary regular sites prefer a rectangle or simple L shape. Stair-step edges,
unnecessary notches, one-room projections, thin connecting necks, and
disconnected components rank worse. No numeric compactness floor or notch /
appendage tolerance is frozen until the metric algorithms are versioned and
evaluated against canonical full-chain fixtures. True non-rectangular site and
no-build authority is never altered to improve appearance.

Existing MUST adjacency remains a hard boolean shared-positive-edge
constraint where the current contract requires it. Add a separate
`REQUIRED_ADJACENCY_SHARED_EDGE_RATIO` quality fact for the critical direct
interfaces:

- `primary_precooling_room <-> sorting_packaging_room`;
- `sorting_packaging_room <-> secondary_precooling_room`;
- `secondary_precooling_room <-> finished_goods_room` when both roles are
  present in the selected process configuration.

For a direct-portal interface, per-pair ratio is
`shared_positive_edge_length / applicable_authoritative_portal_clear_width`.
The existing portal authority supplies the denominator; no extra clearance or
arbitrary metre threshold is added. Report every pair separately and do not
let an aggregate hide a deficient pair. A corridor-mediated relationship is
evaluated under its existing access contract rather than represented as a
fake shared edge.

## 8. Route length and efficiency

`MAIN_PROCESS_ROUTE_LENGTH_M` is the sum of the actual authoritative route
lengths for the active, rank-ordered main-flow transitions. Include explicit
within-zone process connectors only if a versioned project process-route
authority supplies them; never infer internal travel from room centroids.
`NORMALIZED_PROCESS_ROUTE_LENGTH = actual route length / shortest feasible
route length` and
`PROCESS_ROUTE_EFFICIENCY_RATIO = shortest feasible route length / actual
route length`. The shortest route must use the same endpoints, portal choices
allowed by authority, buildable domain, obstacles, and corridor/access
constraints. Missing actual or comparable shortest-route evidence makes the
ratio unavailable. These facts may be computed by future implementation; no
route objective is activated by this P0.

## 9. Hard feasibility, quality ranking, and result semantics

Future candidate evaluation has two non-interchangeable levels:

1. **HARD_FEASIBILITY** — existing site containment, no-build/obstacles,
   area/dimension authority, MUST adjacency, required portals/access, actual
   route validation, selected loading face, truck maneuver validation,
   people/truck policy, and building-footprint validity. Any hard failure
   rejects a candidate before quality is compared.
2. **QUALITY_RANKING** — deterministic lexicographic comparison of the
   separately reported process/regularity facts, in this order:
   `PROCESS_FLOW_ORDER`, `MAIN_FLOW_BACKTRACK_COUNT`,
   `MAIN_FLOW_TURN_COUNT`, `REQUIRED_ADJACENCY_QUALITY`, `GRID_ALIGNMENT`,
   `DEPTH_ALIGNMENT`, `BUILDING_COMPACTNESS`,
   `PROCESS_ROUTE_EFFICIENCY`, `SIDE_BRANCH_QUALITY`,
   `PERSONNEL_LOGISTICS_SEPARATION`.

After all newly frozen quality components tie, preserve the existing P2B2
lexicographic placement tie-break (`SHOULD_ADJACENT` satisfied count, then
`LOADING_SIDE_PREFERENCE`, then canonical normalized layout JSON) unless a
separate Owner-approved contract explicitly replaces it. Do not introduce a
weighted score. A summary `LAYOUT_REGULARITY_SCORE` may be diagnostic only;
it cannot hide a failed atom, override an unavailable required metric, or
change the lexicographic winner.

The selector must explain `WHY_THIS_CANDIDATE_WON`: state the first decisive
quality component, each hard gate, the relevant atomic values (flow/backtrack/
turns, key shared-edge facts, axes/depth, footprint, route efficiency,
branches, people/logistics), and how the winner compares with the next-ranked
full-pass candidate. Opaque objective scores alone are insufficient.

Preserve current public hard-validity semantics:

```ini
PROJECT_LAYOUT_VALIDATED=ENGINEERING_HARD_CONSTRAINTS_ONLY
P2_COMPLETE=EXISTING_ENGINEERING_HARD_VALIDATION_COMPLETION
PROCESS_FLOW_VALIDATED=SEPARATE_VERSIONED_QUALITY_ASSESSMENT
LAYOUT_REGULARITY_VALIDATED=SEPARATE_VERSIONED_QUALITY_ASSESSMENT
```

Do not upgrade/reinterpret `PROJECT_LAYOUT_VALIDATED`, change Tool 7 schema,
or claim process/regularity validity from the existing boolean. A future
versioned quality sidecar can expose the two new assessments without breaking
the current MCP contract; its public exposure requires separate contract
review. `LAYOUT_REGULARITY_VALIDATED=true` requires all frozen hard quality
gates to pass and no required metric to be unavailable. Uncalibrated thresholds
remain an explicit implementation blocker, not a pass.

## 10. Frozen machine-readable metric inventory

Future quality output must expose these atomic values/statuses (or a
version-compatible schema that preserves every fact):

```text
PROCESS_FLOW_VALIDATED
PROCESS_FLOW_ORDER_PASS
MAIN_FLOW_BACKTRACK_COUNT
MAIN_FLOW_TURN_COUNT
MAIN_PROCESS_ROUTE_LENGTH_M
NORMALIZED_PROCESS_ROUTE_LENGTH
PROCESS_ROUTE_EFFICIENCY_RATIO
FUNCTIONAL_GROUPING_PASS
SIDE_BRANCH_CROSSES_MAIN_FLOW
PERSONNEL_LOGISTICS_SEPARATION
MAJOR_ZONE_GRID_ALIGNMENT_RATE
MAJOR_ZONE_DEPTH_ALIGNMENT_RATE
MAIN_BUILDING_COMPONENT_COUNT
BOUNDING_RECTANGLE_OCCUPANCY
EXTERIOR_NOTCH_COUNT
EXTERIOR_REFLEX_CORNER_COUNT
ISOLATED_APPENDAGE_COUNT
REQUIRED_ADJACENCY_QUALITY_PASS
REQUIRED_ADJACENCY_SHARED_EDGE_RATIO
LAYOUT_REGULARITY_SCORE
LAYOUT_REGULARITY_VALIDATED
ACCESS_REQUIREMENT_COUNT
ACCESS_PASS_COUNT
TRUCK_ROUTE_VALIDATED
PROJECT_LAYOUT_VALIDATED
```

Required facts must distinguish measured/derived/not-applicable/unavailable;
missing evidence is never zero/false. Each metric definition, source,
classifier version, and gate status must be returned so a reviewer can explain
the result. The existing P2D route/access outcomes remain hard facts, not
quality proxies.

## 11. Golden drawing and historical fixture authority

`PRIMARY_GOLDEN_REFERENCE=GD-005_PANLONG` remains a visual/layout-organization
reference only. Its permitted use expands from drawing style to abstract
patterns: directional main processing flow, grouped cold rooms, sorting as a
hub, packaging as a side branch, finished/shipping organization, repeated
axes/depths, simple rectangle/L-shaped building tendency, and personnel/logistics
separation. `GOLDEN_ENGINEERING_AUTHORITY=false`.

The repository records `ORIGINAL_GOLDEN_PDF_SUBMITTED=FALSE`; no original
GD-005 drawing bytes are present. Therefore
`ORIGINAL_GOLDEN_SOURCE_AVAILABLE=false`; this P0 does not claim to have
inspected unavailable source bytes. Do not OCR or copy dimensions, coordinates,
areas, or other project-specific engineering values; do not train runtime
rules from the reference image.

The 20 t/day Xinzhao Tool 7 layout criticized by Owner must become a future
regression fixture using its canonical structured input. The repository does
not contain `site_layout_input_v3.json` or an equivalent canonical Xinzhao
input. Record:

```ini
XINZHAO_SITE_LAYOUT_INPUT_V3_PRESENT=false
MISSING_CANONICAL_FIXTURE=true
```

Do not reconstruct this input from conversation text, the SVG, screenshot, or
layout hash. The historical v2.2.1 result
`sha256:eaa791651fa3fdb20d707d18fa31620992ab17b1ade8dc89554b8b2331742b30`
is preserved as baseline evidence only. Future algorithm work is expected to
change geometry and may change this hash:
`FUTURE_CANONICAL_HASH_CHANGE_ALLOWED=true`.

## 12. Future implementation boundary and entry criteria

The next implementation should target, after separate authorization:

- `layout/domain/objective_profile.py` — versioned quality vector and required
  fact/gate metadata;
- `layout/domain/placement.py` and its application boundary — orderly
  group/band candidate families, grid/depth/compactness facts, deterministic
  candidate stream and bounded-search provenance;
- `layout/application/validated_candidate_selection.py` — rank only candidates
  that pass existing hard validation, preserve bounded search, and expose
  winner-vs-next explanation;
- focused domain, integration, canonical-fixture evaluation, and architecture
  tests.

P2D may need a separately versioned route-fact extension only if its current
authoritative route evidence cannot support a metric; it must not have its
frozen access/truck rules weakened. P3 SVG, P1A–P1F renderer, P4 Tool 7, and
the drawing/page-composition path are not the next implementation target.

Before implementation begins, Owner/project authority must provide the
canonical Xinzhao fixture and approve/calibrate depth-alignment and
building-outline classifier thresholds that require empirical evidence.
Implementation requires separate authorization; this P0 does not grant it.

## 13. Scope guard

This P0 changes this contract, ADR-047, the V2.2 version plan, its architecture
lock, and one historical P1G scope-test assertion. That assertion was comparing
all future descendants against P1G's original allowlist; it is now pinned to
P1G's accepted task head `83d43e6432165a2ef8d7b20683e10ac1103f50ee`, preserving
the historical scope check without blocking later independent work. This P0
changes no backend runtime, frontend, database/migration, MCP contract,
renderer, engineering formula, P2/P2D behavior, release, or deployment. It does
not implement a score, quality gate, automatic repair, new fixture, placement,
route, or drawing change.
