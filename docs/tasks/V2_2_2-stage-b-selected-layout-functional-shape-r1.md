# Stage B: selected-layout functional shape guidance R1

Task: `V2_2_2_STAGE_B_SELECTED_LAYOUT_FUNCTIONAL_SHAPE_GUIDANCE_R1`.
Baseline: `7c1fc2e262120677f2d865ea037ddb0d10f25388`, PR #307 Draft.
Owner preliminary selections: historical-02 and latest-04; backup historical-01.
This is not final Owner visual acceptance. No historical coordinates are used
as search seeds, dimensions, hints or fixed room positions.

## Frozen evidence, not new candidates

The existing quality analyzer was run read-only on its source-bound projections;
all metrics reproduce the frozen quality baseline exactly. Original bytes of all
eight candidate JSONs and eight public SVGs were SHA256-checked before analysis.

| Physical fact | historical-02 | latest-04 |
| --- | --- | --- |
| Office physical W × D (m) | 2.456 × 24.430 | 1.656 × 36.232 |
| Changing physical W × D (m) | 12.038 × 3.323 | 4.082 × 9.801 |
| Box-film-sealing physical W × D (m) | 6.143 × 13.027 | 7.303 × 10.955 |
| Actual personnel entrance route (m) | 11.214 | 47.352 |
| Recorded route heading changes | 3 | 3 |
| Exterior footprint turns | 50 | 48 |

Raw candidate SHA256:

- historical-02: `6272e8ab1c31e6dd90cf12ceebb1b3fa8f8621a4912c5c926c48aee25496253b`.
- latest-04: `6efc6aa78c7f85d3a4a8aefb27b02ab2cd4d70d5c2fcd7e2140254186486a434`.

Sources: [quality facts](../previews/v2.2.2/stage-b/layout-quality-baseline-01/facts.json),
[historical execution](../previews/v2.2.2/stage-b/multi-solution-validation-01/README.md),
[guided execution](../previews/v2.2.2/stage-b/guided-fair-validation-02/README.md),
[existing functional-fit review](../previews/v2.2.2/stage-b-flexible-room-functional-fit-r2/README.md).

The short historical-02 personnel route is a comparison advantage, not a
constraint to discard. latest-04's changing/sealing proportions are a structural
direction worth reviewing, not a frozen geometry template. Neither receives a
new functional PASS. Geometric short side is not finished clear room width.

## What the existing search actually does

1. `GlobalModel` consumes server-bound P1 dimension authorities. These three
   roles are FLEXIBLE_RECTANGLE: nominal sides have integer-mm site-induced
   domains starting at 1; area has an authoritative lower bound. Rotation,
   containment, obstacles, nonoverlap, MUST, composition and Access further
   constrain the actual geometry. No approved functional min width/aspect bound
   exists here; supplied unmodeled flexible-dimension rules still fail closed.
2. `apply_construction_guidance` already has a flexible-room semiperimeter proxy
   in `ALL_ROOM_GEOMETRY_HINT`. Its opt-in invocation applies separate objectives
   on cloned phase models. Later phases use process-progress, band, corridor
   length and finally enclosing-span proxies. Only physical room hints propagate:
   a warmup's objective or optimum is not a final hard condition or objective.
3. historical-02 was produced by the ordinary multi-solution path: its frozen
   proposal has no `construction_guidance` receipt. It did not use this earlier
   phase-guided solver merely because the function existed in the repository.
4. latest-04's frozen receipt is
   `stage-b-wall-coordinate-coherence-and-span@1.0.0`, with 50 terms. Fair search
   uses the ordinary native warmups and attaches this objective once to the final
   Access model. It has no explicit per-auxiliary-room semiperimeter term.
   Nearest wall offsets and global room spans do not guarantee a usable office.
5. Every native call retains `stop_after_first_solution=True`. Even a model with
   an objective can return its first feasible incumbent, not a proved minimum.
   No weighted-score conflict is silently resolved: the wall policy refuses an
   existing objective; phase models are separate rather than additive scores.

These are proven coverage/search limitations, not a unique causal proof that
adjacency or structure forced either exact office aspect ratio. Their dimensions
are permitted by the current authority and were accepted by historical hard
validation. Whether a more balanced office is attainable in each same complete
handoff without worsening personnel routes/other geometry is NOT_PROVEN. No
counterfactual real solve, shape-bound change or claim that weights alone caused
the result is made.

## Independent, explicit experimental strategy

`stage-b-final-flexible-functional-semiperimeter@1.0.0` reuses the existing
semiperimeter implementation, selecting only server-bound FLEXIBLE_RECTANGLE
roles among office, changing_room and coating_room. Coating here means
PACKAGING_BOX_FILM_SEALING, not fruit waxing/coating.

`StageBFunctionalShapeFairSearchSolver` attaches that one objective directly to
the prepared final Access model, including its continuation solves. It replaces
the wall/span objective in this independent experiment; it does not sum arbitrary
weights, optimize a formal quality score, add a ratio objective, or alter first
solution termination. An existing objective is rejected, never overwritten.
Fixed-dimension roles are excluded. No dimensions are accepted as strategy input.

**Feasible-domain proof:** the new final callback adds no variables or constraints,
only a linear minimization over existing post-rotation physical w/d. Removing
that objective produces a byte-identical original model proto. Every old feasible
physical assignment remains feasible, including slender rooms, all route/Portal
choices and all six handoffs. Independent room/Access/Packaging/Footprint/Site
acceptance, exact holes and existing physical cuts remain unchanged.

This cannot promise better personnel-route length, fewer holes or compactness
simultaneously. Minimizing summed semiperimeters can trade among targeted roles
and still select an unfavorable first solution. No other room's authority/area,
actual route or hard constraint is reduced to manufacture improvement.

The existing fair solver, Stage A, old entry points and default bootstrap selection
remain unchanged. The new class requires its exact `functional_shape_policy_hash`
in the trusted execution decision in addition to inherited source, handoff,
ledger and fair-share checks. Old decisions do not satisfy it. There is no new
bootstrap, grant issuance, public MCP/Tool7 parameter or production activation.
Future execution wiring must separately bind this policy, frozen source and
dependencies in a newly authorized trusted decision; no consumed grant is reused.

## Offline verification and next boundary

Synthetic comparison uses identical 1s/512MiB/single-worker/seed3/partial-fixed
search and first-solution settings on two equal-area office alternatives. Four
repeats select 2×8 without the final preference and 4×4 with it. These are tiny
synthetic units, not project dimensions, a new min-width standard or real rooms.
This demonstrates SYNTHETIC_PREFERENCE_EFFECT only, never real-layout quality.

Tests also retain unfavorable fixed assignments, fixed-authority exclusion,
objective conflict rejection, missing authority/context rejection, deterministic
model/receipt identity, resource-charge failure, old-grant rejection, default
wall behavior, and all six actual complete model builders with native Solve
explicitly prohibited. Existing functional-fit diagnostics remain INPUT_REQUIRED
without project data; this strategy neither duplicates nor replaces them.

Detailed actual test logs and receipts live in the task's local evidence folder.
A future authorized paired real experiment must evaluate auxiliary proportions,
the historical-02 route advantage, latest-04 route burden, all independent hard
checks, hole rejection, structure coverage, resources and replay. No new grant,
real factory/Truck solve or future execution is authorized by this document.

REAL_LAYOUT_QUALITY_IMPROVED=NOT_EVALUATED; P2D_FULL_PASS_COUNT=0;
STAGE_B_COMPLETE=false; P3_COMPLETE=false; VERSION_COMPLETE=false.
D01/D03/D04, historical recovery rounds and 262 UNKNOWN remain unchanged.
