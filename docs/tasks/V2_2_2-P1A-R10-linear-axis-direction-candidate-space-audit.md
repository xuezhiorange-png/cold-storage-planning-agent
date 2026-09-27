# V2.2.2 P1A-R10: Linear axis/direction candidate-space audit

TASK_ID=V2_2_2_P1A_R10_LINEAR_AXIS_DIRECTION_CANDIDATE_SPACE_AUDIT_R1
RESULT=PASS
PR_NUMBER=302
BASE_HEAD_SHA=5d1bb00c3dad831525e1c3162fd55bd15db0d2c3
ACTIVE_GOVERNANCE_LANE=V2.2.2_P1A
RUNTIME_IMPLEMENTATION_AUTHORIZED=false
BACKEND_SRC_CHANGED=false

## Finding

The current runtime admits only the site-selected Linear axis with
`POSITIVE` direction. For the canonical Xinzhao fixture this is
`Y/POSITIVE`; neither the alternate axis nor negative process direction is
enumerated by the Straight/Offset production lanes. `_process_band_axis()` is
described as an ordering prior, but because its selected axis is the only
Linear axis admitted to those lanes, that description is inaccurate at the
candidate-space boundary. The axis choice is not a quality conclusion.

The diagnostic matrix exercised eight Linear variants and one live Hub
reference through the same Tool 7 authority path. Each diagnostic lane had an
independent deterministic 120-node cap; this is not a shared or production
budget. Existing constructor caps and exact site, obstacle, dimension,
MUST-adjacency, topology-classifier, packaging-slot preflight, and P2D rules
were retained. P2D was not mocked.

## Axis/direction matrix

`roots / visited roots` are root-candidate counts; `nodes` is the placement
node count. All rows below were truncated rather than exhausted, so an empty
row is not evidence of geometric infeasibility.

| Variant | Roots / visited roots | Nodes | Face pairs / attempts | Distinct skeletons | Packaging slot pass / fail | Tail-admissible | P2D reached / full-pass distinct |
|---|---:|---:|---:|---:|---:|---:|---:|
| Straight X+ | 9 / 4 | 60 | 1 / 4 | 0 | 0 / 0 | 0 | 0 / 0 |
| Straight X− | 9 / 6 | 60 | 1 / 6 | 0 | 0 / 0 | 0 | 0 / 0 |
| Straight Y+ | 8 / 8 | 47 | 1 / 8 | 1 | 1 / 0 | 1 | 1 / 1 |
| Straight Y− | 7 / 6 | 60 | 1 / 6 | 0 | 0 / 0 | 0 | 0 / 0 |
| Offset X+ | 9 / 8 | 90 | 1 / 11 | 11 | 0 / 11 | 0 | 0 / 0 |
| Offset X− | 9 / 6 | 90 | 1 / 11 | 0 | 0 / 0 | 0 | 0 / 0 |
| Offset Y+ | 8 / 8 | 91 | 1 / 9 | 2 | 2 / 0 | 2 | 1 / 0 |
| Offset Y− | 7 / 4 | 90 | 1 / 8 | 0 | 0 / 0 | 0 | 0 / 0 |
| Hub reference | 8 / 3 | 90 | 5 / 12 | 1 | 0 / 1 | 0 | 0 / 0 |

The Hub reference constructs the known `956e85ad…24dfcc` geometry. It was
discovered by the Hub lane and canonically classified Straight; its packaging
preflight found no legal slot, so it did not enter tail/P2D. The Straight
Y-positive variant reproduces `55589c20…ee9b953`; it completed two P2C tail
variants, both hard-valid through P2D, but these are one distinct main
skeleton. Offset Y-positive found two further package-slot-admissible
geometries: one reached P2D and failed the access-completeness validation;
the other did not complete tail placement within its bounded search.

Across all matrix variants, exact geometry deduplication yields 15 distinct
main-process skeletons, 3 packaging-slot-admissible skeletons, 2 distinct
skeletons that reached P2D, and 1 distinct P2D full-pass skeleton. The only
full-pass skeleton is also reachable by the current runtime. No runtime-
excluded admissible or full-pass skeleton was found in the explored portion
of the matrix. All nine variants were truncated; no axis/direction family was
proved infeasible.

## Current production search and unused nodes

An unmodified default Tool 7 replay confirms the R9 accounting: 98 of 120
placement nodes were visited, leaving 22. The staged lane allocations/visits
were Offset 40/30, Hub 45/33, and final Straight 57/35. Earlier unused lane
capacity was included in the later lane allocations. The final Straight lane
reported `search_tree_exhausted=false` and `node_budget_exhausted=false`; its
constructive search was truncated by internal search bounds. The scheduler
does not revisit earlier lanes after the final lane, so those remaining 22
nodes were not spent. This is a bounded search/cap and scheduling observation,
not a proof that additional skeletons do not exist.

The reproduced selected Tool 7 layout remains hard-valid: 12 zones, P2
complete, 12/12 access, truck route valid, and building footprint present.
No hard authority or production node budget changed.

## Decision and next boundary

The matrix shows that the axis/direction omission is real, but the explored
alternate variants do not establish a second full-pass skeleton. Since all
nine diagnostic searches remain truncated, the evidence cannot establish
that the full axis/direction space lacks a second admissible layout. One
Offset Y-positive admissible skeleton also exposes a distinct P2D access
failure that should be examined if that candidate is pursued.

Recommended next design/implementation path:
`CONSTRUCTIVE_SEARCH_COVERAGE_REDESIGN`. A future authorization may consider
enumerating axis/direction symmetry, but should first make the construction
coverage and bounded-search lifecycle measurable and fair across variants.
This audit does not implement that change, does not authorize another
topology, and does not activate P1B thresholds.

`NEXT_IMPLEMENTATION_PATH=CONSTRUCTIVE_SEARCH_COVERAGE_REDESIGN`

Machine-readable detail is split across the R10 axis/direction, skeleton,
preflight, P2D, and runtime-gap evidence JSON files in
[`evidence/v2_2_2_p1a`](evidence/v2_2_2_p1a/).

## Governance

`PROCESS_AXIS_SELECTION_ORDERING_ONLY_CLAIM_ACCURATE=false`
`LINEAR_INFEASIBILITY_PROVEN=false`
`P1B_THRESHOLD_ACTIVATED=false`
`WEIGHTED_SCORE_USED=false`
`GOLDEN_COORDINATE_TEMPLATE_USED=false`
`BACKEND_SRC_CHANGED=false`
`TOOL7_RUNTIME_CHANGED=false`
`READY_AUTHORIZED=false`
`MERGE_AUTHORIZED=false`
`TAG_AUTHORIZED=false`
`GITHUB_RELEASE_AUTHORIZED=false`
`DEPLOYMENT_AUTHORIZED=false`
