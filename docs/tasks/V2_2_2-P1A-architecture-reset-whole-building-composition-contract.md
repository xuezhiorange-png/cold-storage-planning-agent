# V2.2.2 P1A Architecture Reset P0 — Whole-Building Composition Contract

## Contract status

```ini
TASK_ID=V2_2_2_P1A_ARCHITECTURE_RESET_P0_WHOLE_BUILDING_COMPOSITION_CONTRACT_R1
MODE=ARCHITECTURE_RESET_CONTRACT_FREEZE_ONLY
TARGET_VERSION=V2.2.2
BASE_BRANCH=main
BASE_MAIN_SHA=955e5e532236fb6c33a80709e90362b12124fb72
PR_302_STATE=CLOSED_UNMERGED
CURRENT_R2_ARCHITECTURE_CLOSURE=TERMINAL_FAIL
GLOBAL_INFEASIBILITY_PROVEN=false
RUNTIME_IMPLEMENTATION_STARTED=false
NEXT_RUNTIME_IMPLEMENTATION_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
GITHUB_RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
```

This is a documentation-only architecture reset contract. It freezes the
problem framing and proposed next-generation composition lifecycle; it does
not authorize runtime implementation. Any later implementation requires a
separate, explicit Owner task and a fresh baseline/acceptance plan.

## V2.2.2 version goal

```ini
V2_2_2_VERSION_GOAL=GENERATE_A_VISUALLY_RECOGNIZABLE_COHERENT_WHOLE_FACTORY_NOT_MERELY_TWELVE_HARD_VALID_RECTANGLES
```

The candidate must read as a complete produce-processing factory, not as a set
of individually valid tiles. Its organization must make the following visible
at a glance:

1. A directional principal production flow.
2. Sorting/Packaging as a recognizable process core.
3. A continuous main structure linking raw receipt, primary precooling,
   processing, secondary precooling/coating, finished goods, and shipping.
4. Cold rooms, finished storage, and related functions grouped coherently.
5. Packaging, secondary-fruit, and frozen functions organized as subordinate
   branches of the principal process.
6. Changing and Office on a personnel side/domain, outside the product chain.
7. Shipping and truck interface considered at the structural-composition stage.
8. A limited, repeated orthogonal axis family across principal spaces.
9. Support and peripheral functions visually subordinate to the process core.
10. A coherent principal building composition rather than tile-like or
    accidental stair-step assembly.

Owner-provided Golden references are qualitative organization references only.
They may inform vocabulary such as aligned bands, coherent groups, readable
flow, and subordinate branches. They are not coordinates, templates, hidden
runtime geometry, room-dimension authority, or engineering constraints.

`PROJECT_LAYOUT_VALIDATED` continues to mean the existing hard-engineering
validity result. Structural quality is a separate assessment. A visually
coherent composition never compensates for failure of an existing hard rule.

## PR #302 terminal record

PR #302 is closed without merge. Its branch history and evidence remain
available for audit; the PR is not a source branch for the reset.

```ini
PR_302_FINAL_HEAD=0de6161ff46a100c05441e1910889c7b1854dcff
PR_302_COMMIT_COUNT=44
PR_302_CHANGED_FILE_COUNT=323
PR_302_MERGED=false
PR_302_CLOSED_UNMERGED=true
EXACT_HEAD_PR_CI_RUN_ID=37220083027
EXACT_HEAD_PR_CI_RESULT=FAIL
EXACT_HEAD_PUSH_CI_RUN_ID=37220079201
EXACT_HEAD_PUSH_CI_RESULT=FAIL
EXACT_HEAD_CI_HEAD_SHA=0de6161ff46a100c05441e1910889c7b1854dcff
SQLITE=6474_PASSED_470_SKIPPED_1_FAILED
POSTGRESQL=4916_PASSED_52_SKIPPED_1720_DESELECTED_1_FAILED
R15_FAILURE=distinct_full_pass_skeletons_observed_1_required_at_least_2
CI_GATE_RESULT=FAIL
FINAL_STRUCTURED_12_ZONE_COUNT=0
FINAL_STRUCTURED_P2D_ATTEMPT_COUNT=0
CURRENT_R2_RUNTIME_LIFECYCLE_FAILED_TO_REACH_STRUCTURED_TAIL_PATH=true
LAST_FROZEN_TARGET_PORTAL_IMPLEMENTATION=NOT_REACHED_IN_FINAL_REAL_TOOL7_REPLAY
GLOBAL_INFEASIBILITY_PROVEN=false
```

The R15 assertion was not changed. In the final real Tool 7 replay,
`tail_access_capacity_preflight_rows` was empty, the structured global node
count was null, and no per-main Frozen target-state diagnostics were produced.
Accordingly, the terminal finding is that the current R2 runtime lifecycle
failed to reach the structured tail path. It is not evidence that the last
Frozen target-portal implementation was exercised and failed, and it is not a
proof of global layout infeasibility. The 44-commit, 323-file recovery path
accumulated local tail/access/Frozen routing work without delivering a
structured 12-zone candidate or a structured P2D attempt. Continuing to patch
that lifecycle is no longer cost-effective; the reset begins from clean
`main`.

## Architecture decision

```ini
MAIN_FIRST_TAIL_ATTACHMENT_PRIMARY_PATH=false
REJECTED_PRIMARY_ARCHITECTURE=MAIN_PROCESS_FIRST_PLUS_TAIL_ATTACHMENT
SELECTED_ARCHITECTURE=WHOLE_BUILDING_GROUP_BAND_COMPOSITION_WITH_RESERVED_PERIPHERAL_DOMAINS
DECISION_FORM=B_C_HYBRID
```

The primary generator first chooses a whole-building structural composition
that assigns all functional groups and all twelve zone roles. It then reserves
peripheral construction domains, derives exact zone placements inside that
composition, and subjects the result to unchanged engineering validators. The
composition is a structural plan, not a guessed building footprint.

The rejected primary lifecycle was:

```text
main process first -> freeze main -> attach personnel/support/frozen later
```

It makes access-critical peripheral functions compete for leftover space and
encourages route-specific emergency placement after principal geometry is
already fixed. Legacy/fallback compatibility may remain separately available,
but it is not the new structured primary generator.

### Options considered

| Route | Decision | Owner-reference alignment | Route-after-placement risk | Search complexity | Hard-validation compatibility | Migration cost | Diversity potential |
|---|---|---|---|---|---|---|---|
| A. Main-process-first plus tail attachment | Reject as primary | Weak: peripheral branches and personnel domain appear incidental | High: access-critical rooms compete for residual space and prompt repeated repairs | Small initially, but recovery branches and retries make lifecycle cost unbounded | Existing validators can remain, but are reached after a fragile sequence | Lowest immediate change; highest accumulated recovery and maintenance cost | Low/moderate; variants tend to be tail permutations of one main geometry |
| B. Whole-building group-band generation | Viable | Strong: groups, bands, flow, and building mass are chosen together | Lower: all roles participate before exact placement | Composition enumeration is explicit and can be bounded by family/variant | Exact placements remain independently checked by every authority | Medium/high: new composition model and adapter into placement | High when distinct topology, not coordinate jitter, is counted |
| C. Process core plus reserved peripheral domains | Viable | Strong: process core remains legible while personnel, support, and logistics are reserved | Lower than A: peripheral capacity is protected before exact placement | Lower per composition than unrestricted B; reservation semantics need care | Reservations are construction aid only; validators retain full authority | Medium: can stage a new composition layer | Moderate/high through distinct core-face and peripheral-domain topology |
| B/C hybrid | Select | Best fit: whole-building role coverage plus explicit peripheral capacity | Lowers route-after-placement risk without claiming routes before validation | Finite family coverage first, then composition variants, then local placement variants | Strong: hard predicates remain the sole feasibility authority | Deliberate migration; reuse predicates/validators, replace lifecycle | High while preserving meaningful major-family diversity |

The hybrid is selected because B prevents any of the twelve roles from being
deferred as “leftover” work, while C makes personnel, support, access, and
shipping/truck capacity explicit before coordinates are synthesized. It is
more consistent with qualitative Owner references than tile-first construction
and avoids treating route repair as the principal candidate generator.

## `StructuralCompositionPlanV2` contract

The following is a versioned conceptual value object for a future
implementation task. It describes intended organization, not metric geometry.

```text
StructuralCompositionPlanV2
  identity
  schema_version
  family
  process_axis
  process_direction
  functional_groups
  principal_bands
  zone_role_assignment
  peripheral_domains
  personnel_ingress_relationship
  packaging_branch_relationship
  secondary_branch_relationship
  frozen_branch_relationship
  shipping_truck_interface_relationship
  dominant_axis_family
  composition_adjacency_intent
  site_orientation_intent
  construction_provenance
```

The plan must not contain Golden coordinates, guessed room dimensions, fake
portal paths, fake Truck paths, a final building footprint, or a P2D/pass
claim. Relationship fields are composition intent only; they do not create or
upgrade MUST adjacency, access, truck, or footprint authority.

### Complete role coverage

Before exact placement starts, every role below must have exactly one explicit
structural assignment. No role may be marked
`PLACE_LATER_IF_SPACE_REMAINS`.

| Functional group | Required zone roles |
|---|---|
| `RAW_SIDE_GROUP` | `raw_fruit_buffer`, `primary_precooling_room` |
| `PROCESSING_CORE_GROUP` | `sorting_packaging_room`, `secondary_precooling_room`, `coating_room` |
| `FINISHED_SIDE_GROUP` | `finished_goods_room`, `shipping_channel` |
| `SUPPORT_GROUP` | `packaging_material_storage`, `secondary_fruit_buffer`, `frozen_fruit_room` |
| `PERSONNEL_GROUP` | `changing_room`, `office` |

The composition records relationship intent among groups/bands and preserves
the current frozen MUST graph as the only source of MUST adjacency. Side-branch
grouping does not manufacture shared-edge requirements.

### Reserved peripheral domains

Every composition describes all five domains before exact room placement:

| Domain | Structural purpose | Explicit non-authority boundary |
|---|---|---|
| `PERSONNEL_INGRESS_DOMAIN` | Personnel-side organization conceptually connected to entrance access and separate from product flow | Not a room, access route, portal, or proof of route feasibility |
| `PACKAGING_SUPPORT_DOMAIN` | Subordinate packaging-material domain in relation to the process core | Not a zone, area allocation, or packaging access proof |
| `SECONDARY_BRANCH_DOMAIN` | Capacity reservation for secondary-fruit function | Not a new adjacency or direct-access rule |
| `FROZEN_BRANCH_DOMAIN` | Capacity reservation for frozen function | Not a new adjacency or Truck-clear corridor claim |
| `SHIPPING_TRUCK_INTERFACE_DOMAIN` | Structural relationship for shipping/loading and truck interface | Not loading-face geometry, maneuver path, Truck pass, or footprint |

These domains prevent the main process from consuming all composition
capacity before peripheral roles are considered. They are not fake zones,
engineering dimensions, access evidence, or building-footprint authority.
Site, no-build, route, Truck, and final P2D validation remain independent.

## Finite family vocabulary

P0 freezes three distinct topology concepts; it does not implement them.

| Family | Topological distinction |
|---|---|
| `LINEAR_BANDED` | Directional raw-side, process-core, and finished-side bands with explicit subordinate branch and personnel domains |
| `CENTRAL_PROCESS_CORE` | Sorting/process core is the organizing center; raw and finished groups attach to distinct structural sides, with peripheral domains assigned around other core faces |
| `PROCESS_SPINE_WITH_PERIPHERAL_BANKS` | A dominant process spine organizes production; raw/finished and support/personnel functions occupy assigned side banks or terminals |

Each family jointly decides process orientation and direction, Sorting/core
role, raw-side band, finished-side band, cold/storage grouping, support branch
class, personnel ingress domain, Secondary/Frozen branch classes, Packaging
relationship, and Shipping/Truck interface side. Family identity describes
topology. Rotation, mirror, one-millimetre shifts, serialization changes, or
tail-only permutations do not create a new family.

## Exact placement and hard-authority preservation

After a complete composition is chosen, future exact placement continues to
use existing authoritative zone-dimension semantics. The composition layer
may assign groups, bands, axes, and reserved structural domains; it may not
rewrite zone area, width/depth, fixed/flexible dimension semantics, or
dimensional provenance.

Every candidate continues independently through all current hard rules:

- effective site boundary and no-build obstacles;
- zone dimensions and non-overlap;
- frozen MUST adjacency;
- existing portal and access requirements;
- Truck maneuver and loading-face validation;
- P2D routing, interaction, and building-footprint derivation;
- single-building constraints and `P2_COMPLETE`.

No structural quality result changes `PROJECT_LAYOUT_VALIDATED`. Hard
feasibility precedes structural-quality comparison. P2D and Truck results must
be recomputed by their existing authorities; composition intent or construction
preflight is never a synthetic pass.

`ROUTE_REPAIR_IS_PRIMARY_GENERATION_STRATEGY=false`. Access and Truck are
considered at composition-level feasibility/preflight, then exact placement
and final P2D validation. A composition with no basic peripheral access
capacity can be rejected early. Route-specific emergency seeds and
post-placement tail repair must not become the primary structured strategy.

## Bounded composition coverage

P0 does not set or increase a numeric placement budget. A future
implementation task must separately confirm budget values and work
accounting. The scheduling principle is:

1. Cover each distinct structural family before spending most work on one.
2. Cover meaningful composition variants within those families.
3. Spend remaining work on exact-placement/local variants.

Tail-room, Office, portal, route, or micro-adjustment variants may not exhaust
the bounded allowance before family coverage. A bounded search reports only
what it examined; it is never a proof of global infeasibility.

## Future delivery and structural-distinctness gates

Existing hard-validity, P2D, R15, and candidate-count acceptance contracts are
not weakened. Future P1 delivery continues to target at least:

```ini
STRUCTURED_P2D_FULL_PASS_CANDIDATE_COUNT_TARGET=5
MAJOR_LAYOUT_FAMILY_TARGET=3
```

The reported set additionally exposes:

```text
DISTINCT_STRUCTURAL_COMPOSITION_COUNT
DISTINCT_MAJOR_BAND_CONFIGURATION_COUNT
DISTINCT_MAIN_PROCESS_GEOMETRY_COUNT
```

One-millimetre shifts, room serialization differences, and tail-only
permutations cannot count as structural diversity. Full-pass counts require
distinct, hard-valid candidates from the complete existing validation chain.

### Owner visual gate

Automatic hard validity is necessary and not sufficient for V2.2.2. A future
implementation produces a unified-scale gallery with common canvas, scale,
and orientation. It shows site boundary, no-build areas, building composition,
groups, bands, all twelve zones, main-flow direction, personnel ingress,
Secondary and Frozen branches, and Shipping/Truck interface. Owner visual
review must be able to answer whether the result reads as a regular, clear
processing factory. This evaluates organization and does not replace
engineering validation.

## Recovery stop rule

```ini
MAX_RECOVERY_ROUNDS_PER_ARCHITECTURE=2
```

The cap is two bounded correction rounds after the main implementation attempt
for a given architecture. If no structured 12-zone candidate exists by the
end of the frozen rounds, status becomes `ARCHITECTURE_REVIEW_REQUIRED`. No
unbounded R9/R10/... recovery chain follows. Any further implementation
requires renewed Owner authorization and architecture review; this contract
does not authorize it.

## Migration boundary from PR #302

### Reusable under the new lifecycle

- exact site and obstacle predicates;
- zone dimension and adjacency authorities;
- access, portal, Truck, and P2D authorities;
- portal generation and route-validation primitives;
- structural-quality facts and deterministic work accounting;
- P1F/P4 compatibility tests and evidence-rendering utilities.

These are reusable only through explicit adapters owned by the future
composition lifecycle. Their reuse does not import current generator
sequencing.

### Not inherited as the new primary architecture

- main-first lifecycle and tail-attachment admission;
- tail-capacity recovery scheduler assumptions;
- Frozen-specific recovery chain;
- Changing-specific emergency construction path;
- accumulated R2 special-case sequencing.

If a primitive from those paths is useful, the future implementation task
states how it is re-owned by whole-building composition rather than inheriting
its lifecycle by default.

## Governance outcome

This P0 freezes a version goal, candidate-generation architecture, authority
boundaries, diversity contract, visual gate, and stop rule. It changes no
runtime, Tool 7, P2D, Truck, Access, database, frontend, MCP, SVG, selection,
or candidate-generation behavior. `NEXT_RUNTIME_IMPLEMENTATION_AUTHORIZED`
remains false.

## References

- [V2.2.2 P0 process-flow and layout-regularity contract](V2_2_2-P0-process-flow-layout-regularity-contract.md)
- [V2.2.2 P0B Owner positive-reference set](V2_2_2-P0B-owner-positive-layout-reference-set.md)
- [V2.2.2 P0C Golden abstraction and calibration](V2_2_2-P0C-golden-layout-abstraction-and-calibration.md)
- [ADR-047 Process Flow and Layout Regularity Authority](../architecture/ADR-047-process-flow-layout-regularity-authority.md)
- [ADR-049 Whole-Building Group-Band Composition](../architecture/ADR-049-whole-building-group-band-composition.md)
