# V2.2.2 P1A R8 — 956e tail feasibility and ordering audit

TASK_ID=V2_2_2_P1A_R8_956E_TAIL_FEASIBILITY_AND_ORDERING_AUDIT_R1
TASK_TYPE=DIAGNOSTIC_DESIGN_GATE
RESULT=PASS
PR_NUMBER=302
BASE_HEAD_SHA=f4768c19bea4611d46d34dd83474bd8ca05b8c00
TARGET_SKELETON_HASH=sha256:956e85adebc6f55ded51a481fb07dee437d364d241159beecd5714fbac24dfcc

## Finding

The 956e main-process skeleton is incompatible with the Xinzhao site and the
authoritative packaging-material rectangle: `17.3 m × 14.5 m`,
`DETERMINISTIC_GRID_RECTANGLE`, with both allowed orientations checked. On the
frozen seven-zone geometry, there is no legal packaging rectangle origin on
the integer-millimetre coordinate lattice after applying the exact site,
no-build and main-zone predicates together.

This is a fixed-skeleton finding, not a claim that the project or every possible
main-process skeleton is geometrically infeasible. `infeasibility_proven=false`
remains the global conclusion. The exhaustive proof scope is only all legal
integer-mm origins for the two authoritative orientations against this exact
site, obstacle set and frozen 956e main skeleton.

The packaging relation is not MUST adjacency. Its authority is
`packaging_material_storage → sorting_packaging_room`, PACKAGING flow, with
direct or corridor-mediated access allowed. The empty option set is not treated
as an adjacency failure: no packaging rectangle can first occupy the site
without colliding with a no-build polygon or one of the seven fixed main zones.

## Reproduction and option census

The offline evaluation helper captures 956e from the real, unmodified R7 Tool 7
chain and then holds its seven rectangles fixed. The replay matched the R7
canonical result hash and SVG hash. No coordinates were manually transcribed.

At state A (main skeleton only), the structured candidate pipeline evaluated
338 rectangle attempts across 286 unique origins:

| Rejection stage | Count |
| --- | ---: |
| Site outside | 157 |
| No-build collision | 98 |
| Overlap with a main-process zone | 83 |
| MUST adjacency / skeleton-region / other | 0 |
| Final options | 0 |

The machine evidence records each rejected package rectangle and its exact
blocker identity or site-boundary failure. In addition, the existing general
fallback free-anchor counterfactual evaluated 3,164 attempts (2,746 unique
origins) and also found zero options. That fallback result alone would not prove
anchor completeness; the separate exhaustive origin-space check does.

For each orientation, a position exists if the no-build set is removed while
the seven zones remain, and a position exists if the seven zones are removed
while no-build remains. No position exists with both sets present. This
identifies a combined site/no-build/main-skeleton conflict rather than a single
zone adjacency rule.

## Ordering and tail search

The first-ranked changing room and office do not cause the package option loss:
the package option count is already zero at state A, remains zero after either
one is placed, remains zero after both, and is zero for all 36 explored
compatible changing/office pairs.

Evaluation-only tail ordering runs used a 5,000-node diagnostic limit, separate
from production:

| Strategy | Search phase | Nodes | Exhausted current candidate family | P2D reached |
| --- | --- | ---: | --- | --- |
| Personnel first | Structured | 43 | Yes | No |
| Support first | Structured | 1 | Yes | No |
| Most constrained first | Structured | 1 | Yes | No |
| Support first | General fallback | 1 | Yes | No |

The support-first and MRV searches stop at the package zone with zero options.
The personnel-first search exhausts the currently generated option branches;
it does not find a complete P2C placement. Since no complete P2C witness exists,
P2D is not reached and no P2D result is inferred or mocked.

## Production budget accounting

The production placement budget remains 120. The fresh R7 replay assigns 956e a
12-node tail share and consumes all 12. Other lane nodes are not recycled by
the current scheduler into that already bounded share. This is a mechanical
tail-share limit, but it is not the cause of the zero package options: the
package has no legal slot before personnel or support placement, and the
diagnostic searches independently hit the same fixed-skeleton geometric
conflict.

The archived R7 evidence reports 92 global node visits / 28 remaining. A fresh
replay with matching canonical-result and SVG hashes sums lane visits to 104 /
16 remaining. This accounting discrepancy is preserved, not silently
rewritten. It does not change the 956e 12-node share or the package-slot proof;
the source of the aggregate accounting difference remains an evidence
reconciliation item.

## Classification and next path

| Cause class | Finding |
| --- | --- |
| `TAIL_ORDERING_STARVATION` | Not causal |
| `PERSONNEL_BRANCH_STARVES_SUPPORT` | Not causal |
| `PACKAGING_ANCHOR_COVERAGE_GAP` | Not indicated for fixed authoritative dimensions; all integer-mm origins were exhausted |
| `TAIL_SHARE_ALLOCATION_STARVATION` | Mechanically present, not causal for the package's zero options |
| `TRUE_ENUMERATED_GEOMETRY_CONFLICT` | Proven for this fixed 956e skeleton and package dimension authority |
| `P2D_HARD_FAILURE_AFTER_COMPLETE_P2C` | No; complete P2C was never formed |
| `UNRESOLVED_BOUNDED_SEARCH` | No for the fixed-skeleton package-slot question; global project infeasibility remains unproven |

Next implementation investigation should return to main-process skeleton
generation and produce alternative seven-zone geometry that leaves a legal
place for the unchanged authoritative package rectangle. Do not change the
package area/dimensions, access authority, no-build geometry, P2D rules, or
production tail order to make 956e pass. The archived/live aggregate node
accounting difference should be reconciled separately.

## Scope and artifacts

The evaluation-only helper and tests are under `backend/tests/evaluation/`.
They use process-local instrumentation around the real Tool 7 replay; nothing
is persisted to runtime, and the Tool 7 payload is unchanged. No file under
`backend/src/` is modified. Production budget remains 120; P2D, access, truck,
MUST adjacency, topology construction and runtime tail ordering are unchanged.

Machine-readable detail:

- `xinzhao_p1a_r8_tail_zone_option_census.json`
- `xinzhao_p1a_r8_packaging_option_lifecycle.json`
- `xinzhao_p1a_r8_tail_order_comparison.json`
- `xinzhao_p1a_r8_tail_feasibility_search.json`
- `xinzhao_p1a_r8_tail_budget_accounting.json`

Owner visual review is not asserted or changed by this diagnostic task.
