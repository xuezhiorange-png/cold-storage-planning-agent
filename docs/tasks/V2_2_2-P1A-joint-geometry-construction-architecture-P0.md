# V2.2.2 P1A — Joint Geometry Construction Architecture P0

TASK_ID=V2_2_2_JOINT_GEOMETRY_CONSTRUCTION_ARCHITECTURE_CONTRACT_P0
P0_CONTRACT_STATUS=OWNER_APPROVED_ARCHITECTURE_SCOPE_FROZEN
CONTRACT_AUTHORITY=OWNER_APPROVED_ARCHITECTURE_DESIGN_SCOPE
AUDIT_HEAD=35206a37e6ee9416d1f2ca30f010cb85e4d63f98

```ini
CURRENT_WHOLE_BUILDING_ARCHITECTURE=WHOLE_BUILDING_GROUP_BAND_COMPOSITION_WITH_RESERVED_PERIPHERAL_DOMAINS
SELECTED_DIRECTION=B_C_HYBRID_WITH_ENGINEERING_INTERFACE_DRIVEN_JOINT_GEOMETRY
P0_ARCHITECTURE_CONTRACT_FROZEN=true
OWNER_ARCHITECTURE_DESIGN_APPROVED=true
WHOLE_BUILDING_ARCHITECTURE_RETAINED=true
WHOLE_BUILDING_ARCHITECTURE_RESET=false
MAJOR_CONSTRUCTION_SUBARCHITECTURE_REFACTOR=true
FROZEN_CONSTRUCTION_STRATEGY_ID=engineering-interface-driven-joint-geometry@1.0.0
CONSTRUCTION_STRATEGY_IDENTITY_APPROVED=true
CONSTRUCTION_STRATEGY_IMPLEMENTED=false
ENGINEERING_AUTHORITY_CHANGE_AUTHORIZED=false
ARCHITECTURE_DESIGN_FROZEN=true
IMPLEMENTATION_READINESS=NOT_AUTHORIZED
STRATEGY_IMPLEMENTED=false
PRODUCTION_IMPLEMENTATION_AUTHORIZED=false
P1_IMPLEMENTATION_AUTHORIZED=false
P3_COMPLETE=false
VERSION_PLAN_FROZEN=false
MAX_RECOVERY_ROUNDS_PER_ARCHITECTURE=2
D04_RECOVERY_LEDGER_RESOLVED=false
HISTORICAL_RECOVERY_ROUNDS=REQUIRES_OWNER_CLASSIFICATION
HISTORICAL_RECOVERY_ROUNDS_REMAINING=UNKNOWN
RESOURCE_MAPPING_OWNER_APPROVAL_PENDING=true
RESOURCE_CONTRACT_CHANGE_REQUIRED=CONDITIONAL_PENDING_RESOURCE_MAPPING
NEW_INDEPENDENT_SEARCH_BUDGET_AUTHORIZED=false
D01_FORMAL_AMENDMENT_COMPLETE=false
D03_FORMAL_AMENDMENT_COMPLETE=false
```

`engineering-interface-driven-joint-geometry@1.0.0` is the Owner-approved, frozen versioned identity for the future exact-construction strategy. It is distinct from the whole-building B/C architecture and is not an engineering-authority identity, a claim that production code exists, or a new recovery-round allowance. Its implementation readiness remains separate from architecture-design approval: production implementation, resource mapping, D04 classification and the named implementation task remain pending. It must not overwrite or impersonate the existing legacy strategy identity.

## PURPOSE

Record the Owner-approved architecture design contract for generating complete factory layouts by jointly constructing shared room geometry and engineering-interface alternatives, while retaining the current B/C whole-building structural architecture and all existing engineering authorities. This freezes the architecture-design scope only; it does not grant implementation readiness or amend engineering-authority contracts.

The intended result is a candidate producer for the whole 12-zone factory—not a Packaging-only solver and not a replacement engineering validator. Structural composition continues to express functional groups, principal bands, peripheral domains, family topology and mandatory structural relationships. A versioned joint-geometry construction strategy then assigns the original rooms and their interfaces in a mutually consistent way. The existing Access, Truck, interaction, footprint and P2D authorities remain responsible for final validation.

Frozen architecture flow (design-level; implementation remains unauthorized):

```text
STRUCTURAL_COMPOSITION
    → ENGINEERING_INTERFACE_BINDING
    → JOINT_GEOMETRY_DOMAIN
    → BOUNDED_JOINT_CONSTRUCTION
    → COMPLETE_12_ZONE_CANDIDATES
    → EXISTING_ACCESS_TRUCK_P2D_VALIDATION
```

This architecture freeze resolves neither the D01 P3 acceptance contract nor the D03 numeric/group conflicts. It preserves them; any changed acceptance semantics still require separate formal Owner-approved amendments.

## ENGINEERING_AUTHORITY

### Authority ledger

| Authority | Source of truth / identity | Construction may do | Construction must not do | Final decision remains with |
|---|---|---|---|---|
| Functional roles and process MUST | Existing process graph and existing 12 role registry; existing `must_adjacencies` | Bind and project the existing roles/edges into shared variables | Add, remove, weaken or reinterpret a MUST or role | Existing hard-adjacency validator |
| Room dimensions and shape/orientation domain | Server-bound `LayoutAuthorityBindingV1.dimension_authorities` and current shape derivation | Enumerate only authorized shape/rotation variants | Hard-code sizes, copy historical dimensions, invent shapes or use caller-supplied authority | Existing dimension/shape validators |
| Site | `ValidatedSiteGeometryV1.site.effective_buildable_boundary` | Use the validated boundary to derive/validate construction domains | Substitute raw project polygons, bbox or unvalidated outline | Existing site predicate / final validator |
| Hard obstacles | `ValidatedSiteGeometryV1.obstacles.hard_obstacles` | Include the full authoritative hard-obstacle geometry in room/corridor construction | Use no-build-only shortcut, omit retained buildings, or upgrade conditional-removal footprints | Existing validated-site obstacle source and geometry predicates |
| Access relationship/profile | Existing server-owned access requirements and `EdgeOrientedConnectionV1` / bound access profile | Derive authorized face classes, portal/corridor requirements and route alternatives | Invent portal width, corridor width, turn permission or a new adjacency | Existing Access router, including `route_site_placement()` / `route_access_requirement()` |
| Truck | Existing project-bound Truck requirement, template set, loading-face and maneuver validator | Transmit relevant shipping/loading-face/interface constraints as necessary construction inputs, when those are present and validated | Treat `SHIPPING_TRUCK_INTERFACE_DOMAIN` or a template endpoint as a Truck PASS; weaken or replace templates or maneuver rules | Existing Truck maneuver chain and project binding |
| Personnel/Truck interaction and footprint | Existing downstream validation authorities | Preserve their inputs and avoid consuming known reserved space where an approved necessary condition exists | Claim interaction clearance or derive a building footprint as passed from a local witness | Existing interaction/footprint validator |
| P2D and quality | Existing P2D validator; P0/ADR-047 quality contract and calibrated inputs only | Attach provenance and report results; keep hard feasibility separate from quality | Claim `P2_COMPLETE`, alter quality gates, or invent numeric calibration thresholds | Existing P2D and approved quality contract |

### Invariants

1. All 12 current functional room roles remain unchanged.
2. The existing seven HARD MUST edges and all other access requirements remain authority-derived; this proposal creates no new MUST adjacency.
3. Authoritative dimensions, shape domains, effective site boundary, complete hard obstacles, non-overlap semantics, Access, Truck, personnel/Truck interaction, footprint and P2D rules do not change.
4. A construction witness is not an engineering acceptance. Only the corresponding existing validator may emit final PASS.
5. Missing or conflicting authority is BLOCKED or UNKNOWN; it is never filled with guessed values.
6. This document freezes only the approved architecture-design scope; it does not amend ADR-047/049/050 or the existing P0/P1A engineering-authority contracts.

## SCOPE

The future strategy covers the complete whole-building assignment: every original room role participates in the same site/obstacle/non-overlap capacity competition, whether or not it belongs to the first interface unit. It considers:

- the existing raw → primary precooling → Sorting/Packaging → secondary precooling → coating → finished goods → shipping process path;
- packaging materials, secondary fruit and frozen fruit functions and their existing structural/access relations;
- personnel entry → Changing → Sorting access requirements, without converting them into new MUST edges;
- Office's existing personnel group/ownership and only its separately authorized existing relationships;
- Shipping's existing loading-face/domain context and actual bound Truck inputs, without equating a structural domain with vehicle manoeuvre feasibility;
- family/group/band/peripheral structure, site outline, full hard obstacles, room orientations, portal/corridor occupancy and layout alternatives.

The Packaging ↔ Sorting interface is the first proposed mechanism test slice, not the only production scope. It may not be optimized as a rigid two-room block that bypasses the remaining ten roles.

### Layered handoff contract

| Layer | Inputs and source identity | Output/data type | Allowed responsibility | Forbidden authority / failure behavior |
|---|---|---|---|---|
| `STRUCTURAL_COMPOSITION` | Canonical zone plan, server-bound structural authorities, family definition, process-graph identity | Existing coordinate-free `StructuralCompositionPlanV2` / placement handoff, plus topology references | Select family, group membership, principal bands, peripheral domains, structural relationships and authority-derived interface references | No x/y, bounds, rectangle, portal interval, corridor geometry, final layout or engineering PASS. Unsupported family/topology → typed UNKNOWN/BLOCKED; never fabricate geometry |
| `ENGINEERING_INTERFACE_BINDING` | Canonical plan + replayed P1 structural handoff; server-loaded access profile/relationship and authority hashes | Bound immutable interface definitions referencing source edges, endpoint roles, legal relations/modes and authority identities | Resolve provenance, role endpoints, authoritative edge/door/corridor semantics and validation owner | Reject caller-injected interface/profile/authority objects; missing/mismatched source identity → BLOCKED |
| `JOINT_GEOMETRY_DOMAIN` | Bound interfaces + all 12 authoritative shape domains + validated site/effective boundary + full hard obstacles + current composition | Runtime-only deterministic domains/relations for room variables and interface alternatives; proof scope and domain revision | Derive conservative necessary domains and deterministic constructive alternatives; represent actual corridor occupancy | No stable P0/P1 coordinates; no final PASS; finite-event miss, unsupported geometry or cap → UNKNOWN; no sound negative without declared complete coverage |
| `BOUNDED_JOINT_CONSTRUCTION` | Server-owned runtime domains and existing composition | Partial shared assignments and eventually complete 12-zone geometry candidates with source provenance | Coordinate one geometry per role; resolve interface modes/portals/corridors jointly; branch/backtrack under approved budget | Not a final authority; no candidate geometry injection; no bypass of current exact site/obstacle/overlap/MUST checks; exhaustion → bounded-search failure/UNKNOWN, not global infeasibility |
| `COMPLETE_12_ZONE_CANDIDATES` | Exact construction assignment for every role | Candidate identity, full geometry digest, construction provenance and status | Deliver reproducible candidates to existing validation entry | A partial joint unit is not a candidate; geometry hash or topology label alone is not a distinct/full-pass result |
| `EXISTING_ACCESS_TRUCK_P2D_VALIDATION` | Existing hash-only/server-owned candidate replay, existing project-bound authority inputs | Per-requirement Access, Truck, interaction, footprint and P2D results | Decide final engineering/product acceptance | Construction certificates cannot override, skip or relabel validator results |

Composition remains coordinate-free. Metric/runtime geometry does not flow back into the P0/P1 serialized contract. Any future serialized geometry/API boundary change requires its own schema audit and approval.

## JOINT GEOMETRY VARIABLES

`AUTHORITY_INPUT` means the value/policy comes from an existing authoritative source. `CONSTRUCTION_DERIVED` means the future strategy may choose or derive it but cannot change the authority. Every variable is search/backtrack state unless stated otherwise. Every complete candidate must be revalidated by existing validators. Candidate deduplication uses full geometry and approved material-structure rules—not a single local variable.

| Variable | Source and classification | Backtrack / identity / final validation |
|---|---|---|
| `ROOM_ROLE` | `AUTHORITY_INPUT`: existing 12-role registry and process graph | Not mutable; part of every candidate identity; validate exact 12-role set |
| `AUTHORITATIVE_ROOM_SHAPE` | `AUTHORITY_INPUT`: bound dimensions and existing shape derivation | Select an allowed variant; backtrack among authorized variants; include authority identity in source hashes; exact dimensions/shape check |
| `ROOM_ROTATION` | Allowed rotations from current shape authority | `CONSTRUCTION_DERIVED`, backtrackable; include in geometry fingerprint; validate dimensions/orientation and interface predicates |
| `ROOM_RECTANGLE` | Exact bounds from authoritative shape plus integer-mm origin | `CONSTRUCTION_DERIVED`, backtrackable; full candidate geometry input; validate site, hard obstacles, overlap, dimensions and MUST |
| `LEGAL_EDGE_CLASS` | `AUTHORITY_INPUT`: bound edge-oriented access relationship/profile | Not invented by solver; role-relative face class and provenance identity; final Access authority checks |
| `PORTAL_FACE` | Legal face(s) derived from access profile and endpoint geometry | `CONSTRUCTION_DERIVED` choice from authorized faces; backtrackable; validation uses existing portal/route predicates |
| `PORTAL_INTERVAL` | Integer-mm segment on an authorized face, with clear width from existing authority | `CONSTRUCTION_DERIVED`; backtrackable; never use an invented minimum; validate clear opening and route |
| `RELATIVE_ROOM_ORIENTATION` | Relationship among role rectangles and legal faces | Derived relation, not a new engineering rule; backtrackable; validate shared-edge/face orientation and route |
| `CORRIDOR_CENTERLINE` | Derived only for a corridor-mediated alternative under existing route-shape authority | Construction variable, backtrackable; no use as an independent engineering PASS; final router checks route |
| `CORRIDOR_CLEAR_ENVELOPE` | Derived from authoritative clear width/route shape and centerline/portal endpoints | Occupied construction-space reservation, not a room; backtrackable; check effective boundary, all hard obstacles and unrelated room blockers; final Access validation |
| `SITE_BOUNDARY` | `AUTHORITY_INPUT`: validated effective buildable boundary | Immutable source geometry/hash; not a candidate variable; exact site predicate |
| `HARD_OBSTACLE_SET` | `AUTHORITY_INPUT`: complete validated `hard_obstacles` | Immutable source identity; no-build and retained buildings included; conditional-removal footprints not upgraded; exact obstacle predicate |
| `PLACED_ROOM_BLOCKERS` | Current partial geometry plus the other roles' exact assignments/domains | Derived and revision-bound; branch-local/backtrackable; exact non-overlap and corridor-clear checks |
| `COMPOSITION_GROUP` | `AUTHORITY_INPUT`: current approved composition contract | Not changed by this strategy; identity part of structural candidate; validate composition intent |
| `PRINCIPAL_BAND` | Existing structural family/handoff | Not changed by joint solver; may constrain domains; structural identity/dedup input, not engineering PASS |
| `PERIPHERAL_DOMAIN` | Existing structural handoff | Not changed by joint solver; may constrain domains; structural identity/dedup input, not proof of metric space |
| `JOINT_PARTIAL_ASSIGNMENT` | Runtime mapping from role variables to current geometry plus selected interface alternatives | `CONSTRUCTION_DERIVED`, immutable snapshots or exact undo; branch-local; proof scope explicitly labelled; not a complete candidate unless all roles assigned |
| `SOURCE_AUTHORITY_VERSION` | Hash/identity of graph, dimension/shape, site, obstacle, profile, composition and validator policy | `AUTHORITY_INPUT` provenance; immutable in a query; part of cache/certificate key; final result records identities and versions |

No corridor is added to the 12-role registry. A corridor envelope may be included in occupancy and branch conflict checks; it is not reported as a thirteenth room.

## PACKAGING JOINT CONSTRUCTION

This first proposed interface uses the already authorized, source-bound semantics:

```text
packaging_material_storage → sorting_packaging_room
PACKAGING_EDGE=LONG_EDGE
SORTING_EDGE=SHORT_EDGE_EXIT_SIDE
ROUTE_SHAPE=STRAIGHT_ONLY
ALTERNATIVES=DIRECT_SHARED_EDGE | CORRIDOR_MEDIATED
```

The endpoint direction is role-relative. `SHORT_EDGE_EXIT_SIDE` must not be guessed as a fixed world-coordinate direction. Portal and corridor clear widths must be read from the bound authority. No new minimum, door width, portal, route bend or adjacency is created.

### Direct alternative

1. Select authorized shapes/rotations for the two separate room variables.
2. Select legal role-relative edge faces and a portal interval on each authorized face.
3. Construct actual shared-edge room bounds with compatible orientation and required clear portal width.
4. Validate site, full hard obstacles, both room dimensions, non-overlap and all already fixed MUST neighbors.
5. Include both rooms in the whole-building partial assignment and retain feasible domains/space for every other role.

Failure of this direct alternative rejects only the direct branch. It cannot prove the corridor alternative unavailable.

### Corridor-mediated alternative

1. Select legal portal faces/intervals from the same source-bound profile.
2. Jointly choose the separate room geometries and straight centerline joining the portals.
3. Derive the clear corridor envelope using the authoritative clear width and route-shape constraints; the envelope is occupied space for construction.
4. Check the full envelope against validated effective boundary, the complete hard-obstacle set and all unrelated placed room rectangles and required remaining domains.
5. Reuse exact geometric predicates for the proposed witness and pass the resulting candidate through the original Access router. Only that router may report Access PASS.

An incomplete portal/centerline/event generator is not a complete domain. If it finds no witness without coverage proof, output UNKNOWN and keep other legal branches. No localized event list can be called exhaustive solely because iteration ended.

### Whole-factory capacity competition

The Packaging/Sorting assignment participates in one global 12-role search state. The same Sorting rectangle must satisfy its other process-MUST interfaces, its group/band intent, non-overlap with the other ten roles, site/obstacle constraints, and its access relations. The chosen corridor envelope must not be allocated as free room space. The search can backtrack over both endpoint geometry, interface mode, portal interval, corridor and other role assignments under the authorized strategy. A successful local pair or independent pair certificates do not imply that the remaining ten roles fit.

## WHOLE-BUILDING JOINT CONSTRUCTION

The strategy must derive interface variables from the source graph/access authority, not maintain a second hard-coded edge list. It must coordinate the declared process path, auxiliary branches, personnel access and shipping/loading constraints while retaining the current Composition family/group/band structure.

For a role with two or more incident relationships, one exact `ROOM_RECTANGLE`/shape assignment is shared by every incident constraint. For example, a Sorting assignment used by Packaging→Sorting is the same assignment used for its process MUST neighbors. For Shipping, the same room geometry is used by all its authorized interface and loading-face constraints. A collection of separately successful pairs with different geometries for the shared role is not a joint assignment.

All 12 roles compete for the same buildable site and hard-obstacle-free space. Roles not yet assigned retain explicit domains/necessary space; joint construction may not seal their area as unconstrained. Auxiliary fruit/frozen branches and personnel circulation are represented through existing role/relationship authorities; no new MUST adjacency is introduced. Main entrance→Changing→Sorting remains an Access relation, not a new structural MUST. Office remains under its existing personnel ownership; Office↔Shipping MUST is not a personnel portal grant.

Truck construction inputs may express an existing shipping loading face and project-bound vehicle/template authority when supplied. They do not establish vehicle swept-envelope representativeness, maneuver feasibility, a route PASS or global physical access. The current fixture/template readiness must be reported as a separate input limitation; no template is replaced or fabricated by this contract.

## NON_GOALS

- No change to the top-level B/C whole-building architecture or family vocabulary.
- No new implementation, solver, production type, exact-placement algorithm or task-specific runtime branch in this P0.
- No coordinate data in CompositionPlan/Handoff or new caller-injected authority/artifact API.
- No new role, MUST, engineering threshold, route permission, door/corridor width or obstacle reinterpretation.
- No replacement of Access, Truck, interaction, footprint or P2D validators.
- No claim that joint support is a complete 12-zone layout or that a complete layout is a project-validated design.
- No modification of zone order, scheduler, candidate selector/output contract or placement budget in this P0.
- No Access/Truck/P2D run, canonical replay, benchmark, CR2, R6A, commit, push, Ready, Merge, release or deployment.

## PROOF, STATUS AND SAFETY INVARIANTS

### Required distinctions

| Result scope | Minimum claim | What it does not prove |
|---|---|---|
| `NECESSARY_DOMAIN_NONEMPTY` | At least one point survives sound necessary constraints in the declared domain | No feasible geometry by itself |
| `PAIRWISE_SUPPORTED` | One exact-authority-valid geometry pair satisfies that interface's checked local predicates | Shared-role consistency, other interfaces, remaining rooms or whole factory |
| `SHARED_ROLE_JOINT_SUPPORTED` | One geometry per shared role simultaneously satisfies the named connected relationships in the certificate | Other unmodeled components or all 12 roles |
| `CONNECTED_COMPONENT_JOINT_SUPPORTED` | One shared assignment satisfies the full declared interface component and all listed constraints | Whole-building feasibility if any roles/constraints are outside the component |
| `COMPLETE_12_ZONE_CONSTRUCTION` | One actual geometry assigned to every original role passes the stated construction checks | Final Access/Truck/P2D until those validators run |
| `FULL_ENGINEERING_VALIDATION` | Existing complete validation chain returns the documented result for a replayed full candidate | Quality/Owner acceptance not included by those validation gates |

### Status semantics

- `SUPPORTED`: a concrete witness records one geometry per involved role and is rechecked against the exact predicates and declared proof scope. It is a construction witness, never an Access/Truck/P2D PASS.
- `PROVED_NO_SUPPORT`: allowed only if a complete, soundly covered necessary/admissible domain for the current authority and partial assignment has been exhausted or a sound contradiction certificate is produced. The proof is bound to role/shape/site/obstacle/authority/composition identities, placed geometry and domain revision.
- `UNKNOWN`: event coverage incomplete, unsupported geometry, unresolved composition rule, resource guard reached, no witness found without complete coverage, or joint assignment unproven. UNKNOWN is never relabelled as SUPPORTED or PROVED_NO and never becomes a negative prune.
- `BOUNDED_SEARCH_EXHAUSTED`: no complete construction within the declared node/resource limits. It is not global infeasibility.
- `BLOCKED`: required authority/version/provenance is absent or conflicting, or a frozen contract prevents the attempted operation.

Partial-state domain changes invalidate stale cursor, support and negative certificates. Backtracking must restore exact parent state and cannot leak child certificates into a sibling. Cache identity includes the construction-strategy version, source hard graph, shapes/dimensions, validated site, full hard obstacles, access profile, composition/handoff, placed geometry and domain revision.

D01's current accepted-partial zero-UNKNOWN strong acceptance gate remains unchanged. This P0 neither makes P3 pass nor reduces the historical denominator. UNKNOWN may remain search-admissible according to existing semantics, but it cannot be counted as proved capacity and any existing zero-UNKNOWN acceptance gate remains in force until a separate formal Owner-approved contract amendment.

## DATA HANDOFF AND VERSION COMPATIBILITY

1. Application boundary reconstructs structural composition, replays/verifies the P1 handoff and binds validated site, dimensions/shapes, access profile and truck project inputs server-side.
2. Internal interface/domain structures reference exact authority identities and source edge identity. Caller-created plan, handoff, metric reservation or joint witness is not authority.
3. Existing P0/P1 plan and handoff remain coordinate-free and semantically stable. Runtime joint geometry is nonserialized/internal unless a later schema audit approves an additive, versioned public artifact.
4. Every complete candidate records construction strategy identity/version, composition identity, family, structural/band identity, full geometry hash, authority source hashes, construction status, per-requirement Access status, Truck status, P2D status and quality-evaluation availability.
5. Historical P1/CR1 evidence and source manifests are immutable. A migration may reference them but cannot rewrite/overwrite them.
6. A new construction strategy identity does not automatically make an old serialized consumer compatible or exempt a task from D04 recovery accounting.

## RESOURCE GOVERNANCE

Frozen values remain:

```ini
PLACEMENT_NODE_BUDGET=60000
ACCESS_ROUTE_NODE_BUDGET=20000
TRUCK_NODE_BUDGET=20000
JOINT_EVALUATION_CAP=256
JOINT_ORIGIN_EVENT_CAP=1024
EXISTING_JOINT_WORK_PROTECTION=8192
```

No value is increased, repurposed, reset per retry, or bypassed by caching, a second generator, a helper process or another API. The 256/1,024/8,192 limits retain their existing scope unless a formal resource amendment explicitly changes that scope.

### Proposed accounting rules

| Work | Required accounting proposal | Approval dependency |
|---|---|---|
| Evaluating a candidate rectangle for one role | Charge one placement node before candidate/site/obstacle/overlap/interface checks, including when cache/predicate shortcuts are used | Must match the current placement node definition in an approved implementation contract |
| Expanding a joint tuple with `k` distinct role rectangles | Charge at least `k` placement nodes before exact evaluation; rejected tuples still consume nodes; repeated assignments are charged whenever actually re-evaluated unless a formally approved unique-state rule is specified | Exact formula and compatibility with current counters require Owner approval |
| Branch/backtrack | Do not refund placement nodes. Record branch/depth/backtrack and all attempted geometry | Future implementation evidence contract |
| Propagation / portal / corridor event generation | Count generated/evaluated events and propagation checks separately; do not hide them as free. Existing proof caps cannot be reused for a new purpose implicitly | Whether unchanged limits can bound this work is unresolved. If an auditable mapping cannot fit without semantic change, `RESOURCE_CONTRACT_CHANGE_REQUIRED=true` and coding is blocked pending a numeric Owner decision |
| Access/Truck validation | Count only under the existing validator's own node budgets; no construction PASS substitutes | Existing caps unchanged |

Before the first kernel or adapter implementation, a task must state the exact counter definitions, cumulative scope, cache-hit charging, cap behavior and evidence fields. This draft does not conclude that a resource amendment is definitely necessary: that depends on the implementation's measured and auditable mapping. Until that mapping is approved, no new independent search budget or implicit reuse of an existing proof cap is authorized. If bounded work cannot fit the unchanged contract, implementation must stop for a separate Owner-approved resource amendment. Resource exhaustion yields UNKNOWN/bounded-search failure, never a false negative or fabricated pass. No performance claim is made by this architecture draft.

## MULTI-CANDIDATE OUTPUT CONTRACT

The existing `candidate_by_family` first-result behavior emits at most one candidate per family and at most three per call. It cannot by itself satisfy the version goal of at least five genuinely distinct structured P2D full-pass candidates across at least three materially different principal structures. This is a separate output/enumeration contract gap; this P0 does not change the selector or enumeration algorithm.

Future candidate records must carry at least:

```text
CONSTRUCTION_STRATEGY_ID
COMPOSITION_IDENTITY
FAMILY
MAJOR_BAND_CONFIGURATION
JOINT_GEOMETRY_IDENTITY
COMPLETE_ZONE_GEOMETRY_HASH
SOURCE_AUTHORITY_HASHES
CONSTRUCTION_HARD_STATUS
ACCESS_STATUS
TRUCK_STATUS
P2D_STATUS
STRUCTURAL_DISTINCTNESS_CLASS
QUALITY_EVALUATION_STATUS
```

Counting and de-duplication rules:

1. A local joint unit, partial assignment or candidate lacking all 12 roles is not a complete layout candidate.
2. A candidate counts toward the five only after actual P2D full PASS with traceable inputs and existing validator outputs.
3. Family labels alone do not establish three material structures.
4. Mirroring, rotation, tiny translation, hash/provenance-only change, repeated invocation and tail swap do not automatically establish distinctness.
5. Full geometry comparison and an Owner-approved structural-difference rule must support every count.
6. Candidate enumeration and any selector/scheduler contract change require separate task authorization. Its allocation under the original 60,000 placement nodes must be specified; no silent budget increase.

The original product targets remain unchanged: `STRUCTURED_P2D_FULL_PASS_CANDIDATE_COUNT_TARGET=5` and `MAJOR_LAYOUT_FAMILY_TARGET=3`.

## PRODUCT QUALITY AND UNRESOLVED CONTRACTS

This factory planner must still produce a clear, correctly directed main process flow; Sorting/Packaging as a coherent process core; connected raw, processing, finished-goods and shipping structure; organized auxiliary branches; personnel/production-logistics separation; coherent axes, depth and building outline; and adaptation to irregular site geometry. Hard engineering acceptance, construction intent, quality evaluation and Owner visual approval remain distinct gates.

### D01 — P3 acceptance

The current `ACCEPTED_PARTIAL_WITH_UNKNOWN_COUNT=0` strong gate and P3 incomplete status remain unchanged. This draft does not split or lower the formal acceptance responsibilities. Any change to separate safe pruning, joint-positive coverage and full engineering validation requires a separately authorized formal amendment to the governing contract/ADR/tests, with historical R3/R4 results retained.

### D03 — grid and group conflicts

- Preserve the original major-zone grid target `0.90`. ADR-047's numeric gate remains uncalibrated; target and gate status must be reported separately. Do not assert a numeric PASS or invent a threshold.
- Preserve the documented historical discrepancy: the original P0 labels `secondary_precooling_room` as `FINISHED_SIDE_GROUP`; the P1A reset/current contract labels it `PROCESSING_CORE_GROUP`. This draft does not rewrite history or change runtime membership. A versioned applicability/compatibility/migration decision is pending formal Owner approval.

### D04 — recovery governance

`MAX_RECOVERY_ROUNDS_PER_ARCHITECTURE=2` remains. The S3 CR1 explicitly recorded round and unresolved #306/#307/Packaging classifications are not reset by a new strategy name. `D04_RECOVERY_LEDGER_RESOLVED=false`; `HISTORICAL_RECOVERY_ROUNDS=REQUIRES_OWNER_CLASSIFICATION`; remaining rounds are `UNKNOWN`. No implementation, correction, or one-time exception is authorized by this P0.

## OLD P1/CR1 CODE MIGRATION PLAN

The table refers to the eight unchanged files in the older evidence-bearing clone at `/Users/charles/codex-r3-isolated.m45h1H/repo`. This new clean clone does not contain those uncommitted files. Hashes were compared with the previous decision manifest; this P0 does not copy, modify, stage or remove them.

| FILE_PATH | CURRENT_PURPOSE | SOURCE_SHA256 | DISPOSITION | REASON | TARGET_ARCHITECTURE_LAYER | REGRESSION_RISK | IMPLEMENTATION_PERMISSION_REQUIRED |
|---|---|---|---|---|---|---|---|
| `backend/src/cold_storage/modules/layout/application/composition_placement.py` | Server-owned authority binding/projection integration | `b7ee727d22c28712b86d4edfc08ab1fc97444616dba68ee3fff7e1c52895724b` | `REUSE` | Preserve server-side provenance and reject caller authority injection; re-audit before adapter use | Application binding | Incorrect provenance or stale caller-created input | Yes |
| `backend/src/cold_storage/modules/layout/domain/composition_placement.py` | Existing sequential exact search plus finite engineering proposals | `e381b7c6350b8f488466119b55875c0d018a1ebdd5e56ea9a5eb372788b483bc` | `REFACTOR` | Existing exact predicates/role accounting may inform the adapter; do not use finite proposal lifecycle as joint coverage | Exact construction adapter | Search order, budget, historical freeze and false-negative regressions | Yes |
| `backend/src/cold_storage/modules/layout/domain/engineering_interface_construction.py` | Bound profile/provenance and finite origin proposals/assessment | `8955f24ec117699cd5efac754768bb3d9eb79067023c2bd86fb4006a26354487` | `REFACTOR` | Re-audit binding; replace incomplete origin/corridor proposal mechanism as core; no wholesale migration | Interface binding / joint-domain adapter | Finite event omission and unsupported negative proof | Yes |
| `backend/tests/architecture/test_v222_p1a_conditional_metric_support_boundary.py` | Conditional support contract/source boundary and compatibility updates | `f4a3882a7810d1d3494732cf66457e607fac044c5ac55e011d718bf5104ef2c7` | `HOLD_FOR_EVIDENCE` | Retain current/historical invariants; adjust only after explicit contract/test allowlist | Architecture regression | Silently weakening pairwise or UNKNOWN semantics | Yes |
| `backend/tests/architecture/test_v222_p1a_joint_metric_capacity_r3_boundary.py` | R3 joint proof boundary | `3c2935a08ef0aa934f1ff23dec9b578d0c3b7c4393f992891e686548d2679e8c` | `HOLD_FOR_EVIDENCE` | Separate stable contract checks from implementation hash pins; keep evidence | Architecture regression | False migration parity or deletion of R3 requirements | Yes |
| `backend/tests/architecture/test_v222_p1a_joint_unknown_proof_r4_boundary.py` | R4 UNKNOWN/zero-UNKNOWN historical boundary | `5b48d7accee93e463a993adc48ec26a308bf4c3bfa3ef64bda5cd9fd29e59f72` | `HOLD_FOR_EVIDENCE` | Preserve denominator and current strong acceptance until formal contract amendment | Architecture regression | Incorrectly converting UNKNOWN to support or erasing history | Yes |
| `backend/tests/architecture/test_v222_p1a_engineering_interface_construction_boundary.py` | P1 engineering-interface architecture tests | `a6041f3ac32301146fcb7b120a507e4a3f6507f02d42ec066a5a38edd2baa8d8` | `REFACTOR` | Reuse server ownership, coordinate-free, and no-role-specific ideas; rewrite to target contract | Architecture regression | Tests encode finite proposal API rather than new contract | Yes |
| `backend/tests/unit/test_v222_p1a_engineering_interface_construction.py` | P1 interface construction unit/orientation/width tests | `3153c53f750fd13ad0763b25b3a3d5265aae42553e142c05686326f31f7c308d` | `REFACTOR` | Retain validated predicates only after review; add independent integer-mm oracle and shared-role/corridor exhaustive cases | Kernel tests | Reusing the same generator as its own oracle | Yes |

No old file is classified for deletion. “REUSE” does not imply acceptance of a complete file; “REFACTOR” does not authorize an edit; “HOLD_FOR_EVIDENCE” preserves the historical artifact as a test/compatibility constraint pending Owner review.

## IMPLEMENTATION STAGES — PROPOSAL ONLY

P1–P5 below are planning-stage labels, not formal task IDs and not implementation authorization.

| Stage | Inputs | Dependencies | Outputs | Proposed allowlist category | Tests / evidence | Business gate | Resources | Stop / rollback | Owner authorization |
|---|---|---|---|---|---|---|---|---|---|
| P1 — Joint Geometry Kernel + Independent Oracle | This approved contract; existing authority projections; small integer-mm fixtures | P0 contract approval; authority projections identified; resource-accounting gate approved | Generic variable/domain/alternative kernel and exact positive/negative/UNKNOWN scope | New focused domain kernel and isolated tests only; no canonical adapter | Independent exhaustive oracle; direct/corridor; shared-role consistency; full obstacle/site; backtrack/revision; generic graph; exact positive revalidation | Mechanism correctness only; no factory feasibility claim | No canonical placement; no new numeric cap until resource gate defined | Any oracle-feasible point removed or cap treated as NO → stop; preserve fixture/evidence; rollback only by separately authorized normal revert | Separate named P1 authorization and D04 classification |
| P2 — Composition/Metric/Exact Adapter | P1 kernel passes; server-bound plan/handoff/site/dimensions/access profile | P1 mechanism/oracle gates pass; adapter files and tests separately allowlisted | Runtime joint domains linked to all 12 existing roles and counted exact branches | Explicit application adapter, exact construction paths and minimal tests, each path individually approved | Caller injection; authority hash; corridor occupancy; all MUST neighbors; 12-zone competition; determinism; historic control/evidence; resource accounting | Adapter is not a complete candidate or validator PASS | 60,000 placement and all other existing budgets unchanged; exact tuple/propagation charging must already be approved | Any need for zone order/scheduler/family/authority/budget change or unbounded propagation → BLOCKED; disable new strategy only by approved revert | Separate explicit production permission |
| P3 — Canonical Candidate + Existing Engineering Validation | P2 exact HEAD; approved input/authority and run limits | P2 adapter gates pass; separate bounded canonical and engineering-validation authorization | Reproducible complete candidate geometry + existing Access/Truck/P2D raw result | Evidence runner/task evidence paths specified in separate task | Deterministic replay, 12 role geometry, 12 Access statuses, Truck, interaction, footprint, P2D | New complete 12-zone candidate; Packaging→Sorting actual Access PASS; full outcome reported, no local PASS substituted for P2D | 60k placement, 20k Access, 20k Truck and current joint guards unless separately amended | No candidate at authorized limit → FAIL; unresolved domain stays UNKNOWN; stop, no automatic correction | Separate bounded run/validation authorization |
| P4 — Multi-Candidate Enumeration Contract | Validated full candidates and version requirements | P3 validated candidate evidence; separate output/selector contract and implementation authorization | Candidate record/identity/dedup/schedule/output contract | Candidate enumeration/selector paths and tests identified by separate authorization | Genuine geometry/structure distinctions; repeated-run dedup; full P2D provenance | 5 actual P2D full-pass candidates across 3 materially different structures | Budget allocation across families/variants must be explicit; no silent increase | Hash-only/translation/mirror/tail-swap inflation → reject; no target under approved budget → report gap | Separate output/selector permission |
| P5 — Quality Ranking + Owner Visual Review | Full engineering-valid candidate pool; calibrated quality metric inputs | P4 portfolio gate; numeric calibration and visual-review protocol approved | Quality evidence, same-scale visual comparison and Owner review record | Quality/ranking/rendering paths identified separately | Calibration, quality sidecar, stable comparison, visual completeness | Original quality goals plus Owner visual approval; hard failures never offset by weighted score | Existing approved engineering resources; no invented numeric threshold | No calibrated threshold or missing Owner signoff → do not claim quality acceptance | Separate quality/visual/release permissions |

Stages are dependent where stated; they do not authorize parallel code or a new formal phase. P0 itself is documentation only.

## ACCEPTANCE_GATES

### This P0 document gate

1. Exactly one new repository document in a fresh clean clone; all prior source documents and evidence unchanged.
2. Whole-building B/C identity and the Owner-approved frozen strategy identity are separate; strategy implementation remains explicitly false.
3. All requested joint geometry variables and source/derived ownership are defined.
4. Direct and corridor-mediated Packaging alternatives are both retained; no false “direct failure ⇒ interface impossible” rule.
5. All twelve roles participate in global space competition; no thirteenth corridor role.
6. All existing engineering authorities and final validators remain unchanged.
7. Proof scopes, UNKNOWN and sound-negative boundaries are explicit; current zero-UNKNOWN P3 gate remains unchanged.
8. Frozen resource values, the 8,192 guard and resource-change approval blocker are explicit.
9. Candidate fields, full-pass counting and anti-inflation rules preserve the five/three product target.
10. Original process/regularity goals and D01/D03/D04 open conflicts are preserved.
11. All eight old P1/CR1 files are individually dispositioned with source SHA; no source path is modified in the old clone.
12. P1–P5 stage plans contain inputs, dependencies, outputs, proposed allowlist, tests/evidence, business gates, resources, stop/rollback and separate Owner authorization.
13. This freeze amendment authorizes only the specified P0-document amendment, its single commit and normal push. No production/test/ADR/fixture/evidence change, canonical or engineering run, future task commit/push, or phase start is implied.

### Later implementation and business gates (not granted by this P0)

- P1 independent oracle proves the kernel preserves known feasible integer-mm witnesses; resource and negative-proof semantics are accepted.
- P2 adapter binds all data server-side, coordinates shared roles and corridor occupancy with all 12 rooms, preserves exact authority and reports counted deterministic work.
- P3 actually produces a new complete 12-zone geometry distinct by full geometry comparison, and the existing Access router returns Packaging→Sorting PASS; all other Access/Truck/P2D outcomes are reported honestly.
- P4/P5 alone address five P2D full-pass candidates, three material structures, calibrated quality and Owner visual review.
- A local joint certificate, construction candidate, seven MUST proofs, successful test or green CI never satisfies a later business gate by implication.

## BUSINESS_OUTCOME

Long-term outcome remains an engineering-validated, coherent blueberry-processing factory layout portfolio—not merely a set of rectangles or local interface witnesses. The new strategy is intended to make process interfaces, direct/corridor alternatives and spatial capacity part of the geometry-generation lifecycle early enough to improve full-layout candidate generation. This intent is unproven until authorized canonical generation and existing engineering validation produce a genuinely new acceptable result.

The v2.2.2 deliverables remain: clear main process direction, Sorting/Packaging process core, connected raw/processing/finished/dispatch flow, organized auxiliary branches, personnel separation, coherent grid/depth/outline adapted to irregular site, at least three material principal structures, at least five distinct structured P2D full-pass candidates, calibrated quality assessment and Owner visual review. This contract lowers none of those targets.

## REGRESSION_REQUIREMENTS

Every future implementation task must separately authorize and test, at minimum:

1. All 12 role identities, process graph MUST bytes/identity and existing composition group/band contracts.
2. P0/P1 coordinate-free plan/handoff, schema consumer and authority-provenance boundary.
3. Authoritative fixed and flexible shape/rotation domain parity and original dimension checks.
4. Validated effective site boundary and complete hard-obstacle parsing including retained buildings; conditional removals not promoted.
5. Exact non-overlap and positive shared-edge predicates; no substitute predicates.
6. Direct shared edge with legal endpoint face/orientation and authoritative portal clearance.
7. Corridor-mediated straight route with authoritative portal/corridor clear width; all corridor envelopes checked against boundary, all hard obstacles and all other rooms.
8. A direct branch failure cannot reject a still-valid corridor branch; incomplete coverage/cap gives UNKNOWN.
9. One shared geometry for every role of degree ≥2; all incident interfaces/neighbors checked jointly; pairwise certificates not called component/full-layout support.
10. Partial assignment/backtracking/domain revision/cache invalidation and sibling isolation.
11. Independent exhaustive integer-mm oracle: no valid point removed by necessary propagation; every positive witness exact-revalidated; negative proof only with complete coverage.
12. Determinism and exact resource accounting; no budget/scheduler/order/family/candidate output changes unless separately authorized.
13. Existing Access/Truck/P2D full-chain validator parity and hash-only/server-owned candidate replay; construction state cannot inject final validator outcomes.
14. Full candidate geometry de-dup and material-structure distinction tests before counting portfolio targets.
15. P0 original quality contract remains separate from engineering hard gates; grid target/calibration and group-ownership disputes are not silently resolved.

## OWNER_DECISIONS_REQUIRED

1. `APPROVED_BY_OWNER_IN_THIS_FREEZE`: retain the top-level B/C architecture and classify the engineering-interface-driven joint-geometry core as a major construction subarchitecture refactor.
2. `APPROVED_BY_OWNER_IN_THIS_FREEZE`: freeze `engineering-interface-driven-joint-geometry@1.0.0` as the construction-strategy identity, distinct from the whole-building architecture; implementation remains false.
3. `PENDING_OWNER`: classify the historical #302/#306/#307/Packaging behavior under D04, determine any remaining recovery allowance from evidence, and decide whether to grant a named implementation permission. No round is reset or exempted by this architecture freeze.
4. `PENDING_OWNER`: approve the exact tuple/propagation resource accounting, cap scope and behavior before implementation. `RESOURCE_CONTRACT_CHANGE_REQUIRED=CONDITIONAL_PENDING_RESOURCE_MAPPING`: no independent budget or numeric increase is authorized; if a bounded mapping to current limits cannot be proven, a separate resource-contract amendment is required.
5. `PENDING_OWNER`: approve a formal P1 task ID, exact module/test/evidence allowlists and the separately scoped implementation permission; the P1–P5 labels here are not frozen task IDs.
6. `PENDING_OWNER`: approve P1 independent integer-mm oracle fixtures, comparison method, acceptance thresholds and evidence requirements.
7. `PENDING_OWNER`: authorize or reject the P2 Adapter implementation and decide any serialized-contract/schema amendment; the coordinate-free/runtime-only design remains the default proposal.
8. `PENDING_OWNER`: authorize P3 canonical replay and full engineering-validation run counts, limits and evidence capture separately.
9. `PENDING_OWNER`: authorize the P4 multi-candidate output mechanism and approve the material structural-distinctness rule; the five/three version goals remain required.
10. `PENDING_OWNER`: complete P5 numeric regularity calibration and approve the Owner visual-review protocol; no uncalibrated numeric threshold is implied.
11. `PENDING_OWNER`: preserve the current D01 zero-UNKNOWN P3 gate until a separate formal amendment is approved; this P0 is not that amendment.
12. `PENDING_OWNER`: preserve both D03 conflicts and decide their formal numeric/group applicability, compatibility and migration changes in a separate authorized task.
13. `PENDING_OWNER`: any other future production, test, ADR, fixture, evidence, canonical replay, Access/Truck/P2D, task commit/push, PR update, Ready, Merge, release or deployment authorization remains separate. This amendment's document-only commit/push permission is not reusable.

## Source register and scope statement

The source manifest and external review report identify the exact SHA-256 of the previous decision package, each of its eight reports, the governing repository documents, and the eight pre-existing P1/CR1 files. Source fact, historical evidence, engineering inference, approved architecture design, resource mapping, D04 classification and Owner-pending decisions are not interchangeable. This Owner decision freezes only the architecture-design scope and strategy identity stated above; it does not freeze resource mapping, resolve D04/D01/D03, amend engineering authorities or authorize implementation.

```ini
P0_DOCUMENT_STATUS=OWNER_APPROVED_ARCHITECTURE_SCOPE_FROZEN
P0_ARCHITECTURE_CONTRACT_FROZEN=true
OWNER_ARCHITECTURE_DESIGN_APPROVED=true
WHOLE_BUILDING_ARCHITECTURE_RETAINED=true
WHOLE_BUILDING_ARCHITECTURE_RESET=false
MAJOR_CONSTRUCTION_SUBARCHITECTURE_REFACTOR=true
FROZEN_CONSTRUCTION_STRATEGY_ID=engineering-interface-driven-joint-geometry@1.0.0
CONSTRUCTION_STRATEGY_IDENTITY_APPROVED=true
CONSTRUCTION_STRATEGY_IMPLEMENTED=false
ENGINEERING_AUTHORITY_CHANGE_AUTHORIZED=false
ARCHITECTURE_DESIGN_FROZEN=true
IMPLEMENTATION_READINESS=NOT_AUTHORIZED
RESOURCE_MAPPING_OWNER_APPROVAL_PENDING=true
RESOURCE_CONTRACT_CHANGE_REQUIRED=CONDITIONAL_PENDING_RESOURCE_MAPPING
NEW_INDEPENDENT_SEARCH_BUDGET_AUTHORIZED=false
D04_RECOVERY_LEDGER_RESOLVED=false
HISTORICAL_RECOVERY_ROUNDS=REQUIRES_OWNER_CLASSIFICATION
HISTORICAL_RECOVERY_ROUNDS_REMAINING=UNKNOWN
MAX_RECOVERY_ROUNDS_PER_ARCHITECTURE=2
D01_FORMAL_AMENDMENT_COMPLETE=false
D03_FORMAL_AMENDMENT_COMPLETE=false
PRODUCTION_IMPLEMENTATION_AUTHORIZED=false
ARCHITECTURE_RESET_AUTHORIZED=false
NEW_RECOVERY_ROUND_AUTHORIZED=false
TEST_MODIFICATION_AUTHORIZED=false
CANONICAL_REPLAY_AUTHORIZED=false
FORMAL_CONTRACT_FREEZE_AUTHORIZED=true
FORMAL_CONTRACT_FREEZE_SCOPE=ARCHITECTURE_DESIGN_ONLY
FORMAL_CONTRACT_AMENDMENT_AUTHORIZED=false
DOCUMENT_AMENDMENT_COMMIT_AUTHORIZED=true
DOCUMENT_AMENDMENT_NORMAL_PUSH_AUTHORIZED=true
COMMIT_AUTHORIZED=true
COMMIT_AUTHORIZATION_SCOPE=THIS_DOCUMENT_AMENDMENT_ONLY
PUSH_AUTHORIZED=true
PUSH_AUTHORIZATION_SCOPE=THIS_DOCUMENT_AMENDMENT_ONLY
FUTURE_CODE_OR_DOCUMENT_COMMIT_AUTHORIZED=false
FUTURE_CODE_OR_DOCUMENT_PUSH_AUTHORIZED=false
P1_IMPLEMENTATION_AUTHORIZED=false
CR2_AUTHORIZED=false
R6A_AUTHORIZED=false
P3_COMPLETE=false
VERSION_PLAN_FROZEN=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
```
