# V2.2.2 P1A R2 Terminal Closure and Architecture Reset Proposal

```ini
TASK_ID=V2_2_2_P1A_R2_TERMINAL_CLOSURE_AND_ARCHITECTURE_RESET_PROPOSAL
SOURCE_PR=302
SOURCE_MODE=R2_FINAL_BOUNDED_FROZEN_TARGET_PORTAL_STATE_CLOSURE
R2_RUNTIME_PATH=CLOSED_TERMINAL_FAIL
GLOBAL_INFEASIBILITY_PROVEN=false
NEXT_ARCHITECTURE_IMPLEMENTATION_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
GITHUB_RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
```

## Decision summary

This is a design review and proposal, not a runtime architecture change. The
bounded Frozen target-portal closure did not produce an evidenced structured
12-zone candidate or a structured P2D attempt. The real Tool 7 double replay
was deterministic and returned a hard-valid 12-zone fallback result with
12/12 access and `P2_COMPLETE=true`; its full-pass registry contained only the
existing control skeleton. The replay exposed no tail-capacity preflight rows
or per-main Frozen target-state metrics. Therefore it does not demonstrate
that the new structured path reached Frozen target-state admission, and it
does not establish global geometric infeasibility.

The current R2 construction path is closed as `TERMINAL_FAIL` under its
bounded recovery rule. Any future work requires a separately reviewed and
authorized architecture proposal/implementation task. No further R2 or R3
runtime recovery is implied by this document.

## Version goal versus stage gates

`VERSION_GOAL` is to generate visibly more orderly, legible factory plans:
grouped functions organized as bands and zones; a recognizable directional
main process and process core; subordinate support branches; personnel outside
the product chain; a limited dominant orthogonal axis family; and one coherent
principal building composition. P0 identifies this as a layout-generation,
candidate-quality, and process-flow gap, not a drawing-style issue
(`docs/tasks/V2_2_2-P0-process-flow-layout-regularity-contract.md`, Purpose and
boundary; Functional grouping; Grid and depth alignment).

P0B records recurring positive-reference patterns: a legible primary
production organization, grouped cold/storage blocks, repeated major axes
where feasible, and subordinate support. P0C likewise abstracts continuous
production bands or a central process core, grouped storage, peripheral
support, limited orthogonal axes, and a coherent principal composition. Those
references are qualitative only: they provide neither project dimensions nor
runtime templates (`docs/tasks/V2_2_2-P0B-owner-positive-layout-reference-set.md`,
Reference-by-reference findings; `docs/tasks/V2_2_2-P0C-golden-layout-abstraction-and-calibration.md`,
What the references support).

P1A translates that intent into a deterministic group/band/zone placement
policy and a lexicographic structural comparison among candidates that have
already passed P2D; it preserves P2D as the hard-validation gate and does not
change Tool 7's input or validity semantics
(`docs/tasks/V2_2_2-P1A-structural-layout-generation.md`, Governance and
Implemented structural policy).

Candidate-count, family-diversity, R15, and full-chain checks are
`STAGE_ACCEPTANCE_GATES`. They are evidence that the version goal has been
delivered only when the candidates themselves exhibit the intended
organization. Passing engineering validation alone is not visual/structural
acceptance; failing a bounded search is not a proof that no valid geometry
exists.

## Why the current R2 path diverged

The recovery chain successively concentrated on envelope semantics, direct
family synthesis, band packing, local composition, site bays, packaging
anchors, shipping/truck dock alignment, tail capacity, Changing access,
flexible dimensions, Frozen construction routes, and finally Frozen portal
arrival states. Those were real integration issues, but the sequence spent
most of its design effort on recovering hard-validity for residual tail zones
after the main geometry had already been selected.

The latest double replay is deterministic, returns the existing hard-valid
fallback, and records only the control full-pass skeleton. Structured P2D
attempts and tail-capacity rows are absent in that replay. The bounded R2 path
therefore has not delivered an Owner-reviewable structured 12-zone result on
which to assess the original visual goal. This is a bounded construction
failure, not a global infeasibility result.

## Architecture assessment

### A. Main-process-first plus tail attachment

This is the current recovery direction: produce a main chain, freeze it, then
attach office, changing, secondary support, and frozen support. It preserves
the current process chain and makes Truck preflight easy to isolate. However,
it leaves access-critical branches competing for whatever site area remains;
the successive tail-capacity and route-recovery layers demonstrate that this
is a poor fit for this site's coupled constraints. It is only partially
aligned with the Owner's group/band references and has accumulated high
search/integration cost.

### B. Whole-building group-band candidate generation

Generate a small deterministic family of complete semantic compositions:
functional groups, their principal bands, all zone banks, personnel ingress,
support branches, and external interfaces are described together before
exact site placement. Dimensions and zone geometry remain authoritative;
site/no-build, access, Truck, and P2D predicates remain unchanged. This best
matches the original `group -> band -> zone` contract and the Owner's
positive-reference abstractions. It reduces route-after-placement repair,
but requires a deliberate composition model and careful bounded enumeration
to control variant growth. Migration cost is high because it replaces the
current main-first lifecycle rather than adding another tail heuristic.

### C. Process core plus reserved peripheral bands

Construct a directional process core and reserve explicit peripheral
construction domains for personnel ingress, Frozen/secondary branches,
support, and Truck/shipping interfaces. All reserves are generation aids,
not fake zones or building-footprint authority; exact room placement and P2D
corridors still determine validity and footprint. This is more incremental
than B and directly prevents late tail starvation. It is moderately complex,
but can over-constrain a site if theoretical band estimates become hard
containment gates. It aligns well when the reserved domains are flexible
construction spaces derived from authoritative dimensions rather than
precomputed boxes that reject a composition prematurely.

## Proposal for a separately authorized next architecture

Review a B/C hybrid before implementation:

1. Define a versioned structural-composition value containing family,
   process direction, group membership, principal bands, and explicit
   peripheral-domain relationships. It must not contain guessed room
   coordinates or claim building-footprint authority.
2. Generate a bounded, deterministic set of complete group/band skeletons.
   Include the access-critical personnel and branch roles and the packaging
   and shipping/Truck interfaces in the composition decision, rather than
   treating them as leftover-space attachments.
3. Derive exact zone placements from authoritative dimensions and finite
   shared-axis/interface events within each composition. Use module rigidity
   only where the current graph/authority supports it; do not introduce new
   MUST adjacency, portal, dimension, access, or Truck rules.
4. Apply site, obstacle, overlap, existing adjacency, and exact route
   predicates as hard validation. Run Truck and full P2D independently; keep
   the existing footprint derivation from exact zones plus actual P2D
   corridors.
5. Only after engineering hard validation, compare structural facts under
   the already authorized P1A selection contract. Do not use Golden geometry
   as coordinates, templates, or hidden runtime input.
6. Preserve deterministic work accounting and a General Fallback phase, but
   schedule by composition coverage rather than letting room-level tail
   repair dominate the candidate budget.

Before implementation, the proposal owner should resolve the finite
composition vocabulary, family coverage contract, authority ownership, and
what evidence constitutes a visibly coherent group/band result. The resulting
implementation must be a separate authorized task with its own bounded
acceptance plan; this document itself grants no runtime-change authority.

## Closure facts and limits

The current replay's observable facts are preserved in
`docs/tasks/evidence/v2_2_2_p1a/xinzhao_frozen_truck_clear_corridor_candidates.json`:

```ini
TOOL7_REPLAY_DETERMINISTIC=true
TOOL7_RESULT_HARD_VALID=true
TOOL7_ACCESS=12/12
TOOL7_P2_COMPLETE=true
DISTINCT_P2D_FULL_PASS_SKELETON_COUNT=1
STRUCTURED_P2D_ATTEMPT_EVIDENCE=0
TAIL_ACCESS_CAPACITY_PREFLIGHT_ROWS=0
GLOBAL_INFEASIBILITY_PROVEN=false
```

The one full-pass hash is the existing control skeleton. Empty structured
diagnostic maps are reported as absent/unobserved work, not as zero legal
Frozen placements or as an exhausted geometric domain. The Frozen targeted
unit tests exercise physical-event placement, target arrival direction,
shared-graph keepouts, direct Truck-overlap rejection, exact final authority,
and deterministic replay; they do not replace real Tool 7/P2D acceptance.
