# Stage B balanced layout quality R1 — opt-in, not activated

Task: `V2_2_2_STAGE_B_BALANCED_LAYOUT_QUALITY_R1`, starting HEAD
`2c5b8d6a6c033267e306da494c25fe45748a3a75`, existing Draft PR #307.
Only scoped development, synthetic tests and read-only historical comparison
are authorized. No real factory solve, replay, grant, default change or project
engineering approval is provided by this change. D01/D03/D04 and historical
262 P3 UNKNOWN are unchanged.

## Two distinct strategies

The existing semiperimeter continuation remains
`stage-b-feasibility-first-bounded-functional-continuation@1.0.0`, hash
`sha256:2a2db1361e71b6872eea1a536a890ababcaf835070dcd67833c598a651bcc092`.
Its objective, comparison behavior, default consumers and consumed MAIN slot
remain unchanged. The only shared-code extension is a guidance/policy hook
whose defaults are exactly the previous functions and hashes.

New internal port: `StageBBalancedQualityFairSearchSolver`.

* Strategy: `BALANCED_FUNCTIONAL_SHAPE`.
* Shape policy: `stage-b-balanced-functional-shape-minimax@1.0.0`.
* Shape hash: `sha256:4f03968760711b1ab090fbcabc2d45ea367428065ec23a47d6986671b7c3ddb0`.
* Two-stage policy: `stage-b-feasibility-first-balanced-quality@1.0.0`.
* Two-stage hash: `sha256:7eade090fb1f173473dd050f8a5cbfba9ab66c0c3a8180bdf8a1becf6d8ac3ed`.

The port requires a trusted decision binding `balanced_quality_policy_hash`.
An old feasibility/semiperimeter decision is insufficient. There is no new
bootstrap, approval store, task slot or execution script here. Any future real
run requires independent Owner authorization and source/dependency/policy
binding; it cannot reuse the consumed feasibility-first MAIN slot.

## Mathematical safety and precision

For each of office, changing_room and coating_room, use existing post-rotation
integer-mm physical variables w,d from the server-bound FLEXIBLE_RECTANGLE model.
No width, area, ratio, site, obstacle or access authority is supplied by a caller.
The opt-in policy fails closed on missing/nonpositive/unmodeled dimensions.

Define s=min(w,d), l=max(w,d), n=1000*l+s-1 and q=n//s.
Thus q=ceil(1000*l/s); minimize max(q) across the three rooms. There is no weighted
sum, historical coordinate hint, new width threshold or hard maximum ratio.
The factor 1000 is representation precision, **not an engineering numeric gate**.
Final comparisons use exact Fraction values from actual physical sides, never q.
Quantization error in q/1000 is nonnegative and strictly less than 1/1000; close
ratios can tie and do not become equal exact engineering facts.

Bounds derive solely from existing domains: s has bounds min(w_lo,d_lo) to
min(w_hi,d_hi); l has max(w_lo,d_lo) to max(w_hi,d_hi). The numerator bounds are
1000*l_lo+s_lo-1 to 1000*l_hi+s_hi-1; q is bounded below by 1000 and above by
ceil(1000*l_hi/s_lo). The maximum uses the maximum q upper bound. All these
definitions are total and unique for every positive original physical assignment.
Clearing the objective therefore projects onto the original physical feasible
set. No physical assignment is excluded because it is slender or unpreferred.

Domain sums, linear activities and the division q*s range receive conservative
int64 checks before adding definitions. Unsupported huge arithmetic domains
raise an explicit error, never acquire clamped physical bounds. Python integer
bound arithmetic does not overflow. Domain values are materialized before
negative indexing because the locked OR-Tools repeated-field wrapper is not a
Python list. Division by zero is excluded by the original positive physical
domains, not by silently adding a new engineering minimum.

## Continuation and baseline safety

First-stage wall alignment and independent engineering acceptance are unchanged.
Only after the baseline has been recorded/yielded does the existing transition
reuse that exact final model, current native assignment hint, same Handoff
quantum and same cumulative ledger. Original hard constraints and topology cuts
remain. New definitions/indexing and all native calls are charged. No warmup,
model preparation, composition admission or budget is restarted for stage two.
UNKNOWN, exhausted resources or failed objective preparation cannot replace the
saved baseline or manufacture an accepted continuation candidate.

Minimax alone does not guarantee that each individual aspect, route or footprint
metric never worsens. Such a guarantee is not claimed and is not implemented by
deleting legal assignments. The exact comparator instead prevents a tradeoff
from being described as Pareto improvement; all construction evidence remains
available without changing Pool admission, V1/V2 diversity or family counts.

## Exact quality facts, not another engineering validator

The new snapshot reuses existing construction diagnostics and branch diversity.
It compares nine exact metrics: the three physical aspect ratios, their exact
maximum, validated personnel centerline length/heading changes, and the actual
application footprint perimeter/outline turns/reflex corners. Building area is
preserved separately and is not treated as a smaller-is-better criterion.
Neither a room bbox nor its perimeter substitutes for the building polygon.
Missing footprint/route facts stay unknown; no zero is invented. A route with
non-PASS status, missing centerline or inconsistent reported length is unusable.

Only same-Handoff, same-V2-meaningful-organization, same Plan/P1/Site snapshots
with all nine exact metrics comparable qualify for a paired Pareto relation.
All nonworse and at least one strictly better gives
`GEOMETRIC_PARETO_IMPROVEMENT`; mixed improvements/worsening give
`QUALITY_TRADEOFF`; other cases are `NO_MEASURABLE_IMPROVEMENT`,
`INCOMPLETE_EVIDENCE` or `NOT_COMPARABLE_STRUCTURE`. Float/rounded input cannot
stand in for exact metrics. No result automatically selects production output
or approves functional room fit; equipment and clear-space evidence is still
required. Full main-process routing remains unvalidated.

## Evidence and limits

Synthetic native tests distinguish Minimax from the semiperimeter sum, exhaust
all 729 original physical assignments of a small model, verify unique auxiliary
extensions, check rotation/narrow/large domains, quantization ties, overflow,
remaining-share refusal, real UNKNOWN and failed switching. The existing tiny
native stream harness verifies first-stage policy/model/share reuse. Comparison
tests calculate actual synthetic polygon/path facts, including a concave polygon
whose perimeter differs from its bbox, and retain unknown/malformed evidence.
Quality conclusions are not mocked into PASS.

Read-only comparison of the sealed MAIN's four valid geometries remains two
tradeoffs. The linear pair's worst aspect stays 20513/975 while reflex corners
rise 22→24. The spine pair's worst aspect stays 40942/977 while reflex corners
rise 20→21. Both actual personnel routes are unchanged. These facts explain why
the previous sum objective did not address the worst room; they do **not** prove
that the new strategy improves real layouts within the existing finite budget.
The new policy has not performed a real factory solve.

All private candidate coordinates, original Owner instructions, grants and full
native logs remain local. No new analysis framework or public MCP/Tool7 interface
is introduced. REAL_LAYOUT_QUALITY_IMPROVED=NOT_EVALUATED,
P2D_FULL_PASS_COUNT=0, STAGE_B_COMPLETE=false, VERSION_COMPLETE=false.
