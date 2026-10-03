# V2.2.2 P1A-R3 — constructive main-process skeleton search

```ini
TASK_ID=V2_2_2_P1A_R3_CONSTRUCTIVE_MAIN_PROCESS_SKELETON_R1
PR_NUMBER=302
BASE_MAIN_SHA=955e5e532236fb6c33a80709e90362b12124fb72
OWNER_P1A_R2_VISUAL_REVIEW=FAIL
RESULT=PARTIAL
OWNER_XINZHAO_P1A_R3_VISUAL_REVIEW=PENDING
P1B_THRESHOLD_ACTIVATED=false
WEIGHTED_SCORE_USED=false
TOOL7_CONTRACT_CHANGED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
```

## Scope and result

R3 adds a versioned `MainProcessSkeletonCandidateV1` and a constructive
seven-zone seed path before the support/personnel tail search. The seed
identity is derived only from the seven main-process rectangles. Candidate
families remain separate, search order is deterministic, rejection reasons
are recorded, and the existing P2D hard-validation gate remains ahead of
structural quality and the P2B2 tie-break. The public Tool 7 input contract,
P2D rules, and total P4 placement budget remain unchanged.

This is not an accepted layout improvement. The unmocked Xinzhao Tool 7 run is
still hard-valid, but the selected seven main-process rectangles are identical
to v2.2.1, P1A-R1, and P1A-R2. Two P2D full-pass candidates collapse to one
distinct main-process skeleton, so the decisive selection component is still
the existing P2B2 tie-break. R3 therefore remains `PARTIAL`; it does not close
the Owner's spatial-regularity blocker.

## Canonical Xinzhao run

The unchanged fixture is
`backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json`, SHA-256
`d03ecae9e1e2808cba346eb83a39f853c8a4b366acc103669af1cf868363901e`.
The actual Tool 7 chain reports:

```ini
PROJECT_LAYOUT_VALIDATED=true
P2_COMPLETE=true
ZONE_COUNT=12
ACCESS_REQUIREMENT_COUNT=12
ACCESS_PASS_COUNT=12
TRUCK_ROUTE_VALIDATED=true
BUILDING_FOOTPRINT_PRESENT=true
P2C_CANDIDATE_COUNT=2
P2D_FULL_PASS_CANDIDATE_COUNT=2
DISTINCT_FULL_PASS_MAIN_PROCESS_SKELETON_COUNT=1
R3_MAIN_PROCESS_GEOMETRY_CHANGED=false
R3_MAIN_PROCESS_CHANGED_ZONE_COUNT=0
R3_CANONICAL_RESULT_HASH=sha256:b3dd2de4fb24f74b5ce96601a74edab5f58a9a781eb5af41b29afd0a66ac98da
R3_SVG_SHA256=sha256:342775cb44d7165a9a64ad7e7f31cd287c04d5a1655bcc8f31ec1c1224f85981
R3_SVG_HASH_EQUALS_R2=true
FIRST_DECISIVE_COMPONENT=P2B2_FINAL_TIE_BREAK
GLOBAL_OPTIMUM_CLAIMED=false
```

The changed canonical layout hash reflects changed internal selection
provenance; it is not evidence of changed drawing geometry. R3's SVG is
byte-identical to R2's SVG. The structural facts still show three support
attachment sides (`EAST,SOUTH,WEST`) and outline class `STAIR_STEP`; no
universal grid/depth/occupancy/notch threshold was enabled.

## Bounded sensitivity and lane evidence

| Total node budget | Elapsed seconds | P2C candidates | P2D full-pass | Distinct full-pass main skeletons |
| ---: | ---: | ---: | ---: | ---: |
| 15 | 0.323 | 0 | 0 | 0 |
| 30 | 2.160 | 0 | 0 | 0 |
| 60 | 3.865 | 2 | 2 | 1 |
| 120 | 11.504 | 2 | 2 | 1 |

At the unchanged 120-node total, the deterministic lane allocations are
Central Hub 80, Linear Positive 20, and Linear Negative 20. The Central Hub
lane constructs two seeds, but its P2D full-pass results do not provide two
distinct main-process skeletons. Both Linear lanes yield zero completed P2C
candidates in their bounded exploration. Their search trees are not marked
exhausted; this evidence does **not** prove those families infeasible. Stable
observed rejection categories include `SITE_OUTSIDE`, `NO_BUILD_COLLISION`,
`ZONE_OVERLAP`, and `SKELETON_TOPOLOGY_INVALID`; absence of another category in
this run is not proof that the corresponding constraint can never reject a
candidate.

Increasing the budget is not the correction: 60 and 120 produce the same two
full-pass results and the same single unique full-pass main skeleton. R3 does
not increase the production budget and does not claim global optimality.

## Visual evidence

The [four-way comparison](evidence/v2_2_2_p1a/xinzhao_p1a_r3_comparison.md)
contains the v2.2.1 baseline, R1, R2, and R3 at the same canvas size, with the
layout JSON, SVG, and direct SVG raster PNGs. It also includes the evaluation-
only structural-group overlay. The four production drawings show the same
main-process geometry for R2 and R3. Owner review remains pending; this report
does not substitute for that review.

## Authority boundaries

- Structured layout JSON remains engineering authority; skeleton envelopes
  are candidate-search structure only.
- Zone area/dimension authority, site/no-build geometry, access, portal,
  shipping, truck, loading-face, and P2D hard validation are not relaxed.
- Golden drawings are not runtime templates or coordinate authorities.
- Search-budget exhaustion is a bounded-search result, not mathematical
  infeasibility.
- P1B numeric thresholds remain unauthorized and inactive.
- Tool 7 and the existing six MCP tools retain their contracts.
