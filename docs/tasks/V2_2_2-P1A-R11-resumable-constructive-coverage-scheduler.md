# V2.2.2 P1A R11 — Resumable constructive coverage scheduler

```ini
TASK_ID=V2_2_2_P1A_R11_RESUMABLE_CONSTRUCTIVE_COVERAGE_SCHEDULER_R1
BASE_HEAD_SHA=d0559847a174e8a86bcf091adccc57898f887a4c
INITIAL_PUSHED_HEAD_SHA=e57c6a45cc149d98867670ed1b78f260d2ebbccb
INITIAL_PUSHED_HEAD_RESULT=FAIL_REGRESSION
RESULT=PASS
PRODUCTION_PLACEMENT_NODE_BUDGET=120
PRODUCTION_BUDGET_CHANGED=false
RESUMABLE_CONSTRUCTIVE_SEARCH_IMPLEMENTED=true
GLOBAL_MULTI_ROUND_SCHEDULER_IMPLEMENTED=true
PER_ROOT_CAP_IS_QUANTUM=true
PER_FACE_CAP_IS_QUANTUM=true
CONSTRUCTION_SHARE_IS_TERMINAL_CAP=false
REPLAYED_PREFIX_NODE_COUNT=0
CONSTRUCTIVE_WORK_ROUND_COUNT=3
GLOBAL_NODE_VISITS=120
GLOBAL_NODE_BUDGET_REMAINING=0
UNUSED_GLOBAL_NODES_WITH_ACTIVE_TRUNCATED_WORK=0
EARLY_STOP_REASON=GLOBAL_PLACEMENT_NODE_BUDGET_EXHAUSTED
DISCOVERED_DISTINCT_MAIN_PROCESS_SKELETON_COUNT=11
PREFLIGHT_REJECTED_DISTINCT_SKELETON_COUNT=8
TAIL_ADMISSIBLE_DISTINCT_MAIN_PROCESS_SKELETON_COUNT=3
P2D_EVALUATED_DISTINCT_MAIN_PROCESS_SKELETON_COUNT=3
P2D_FULL_PASS_DISTINCT_MAIN_PROCESS_SKELETON_COUNT=1
P2C_COMPLETE_CANDIDATE_COUNT=6
P2D_FULL_PASS_CANDIDATE_COUNT=2
956E_PREFLIGHT_REJECTED=true
956E_TAIL_SEARCH_STARTED=false
R10_868C_REACHED_BY_PRODUCTION=false
R10_E73B_REACHED_BY_PRODUCTION=false
SELECTED_TOPOLOGY=STRAIGHT_LINEAR_BAND
SELECTED_MAIN_PROCESS_SKELETON_HASH=sha256:55589c20f3c3336c1c92a8c1ffc8b14a813ac558bac78871d4e6b1fa8ee9b953
SELECTED_MAIN_PROCESS_GEOMETRY_CHANGED=false
CANONICAL_RESULT_HASH=sha256:ed11e746cd65142b26cfb20e371dda3a91b39501175681d2538d4359ee017c0d
SVG_SHA256=sha256:342775cb44d7165a9a64ad7e7f31cd287c04d5a1655bcc8f31ec1c1224f85981
PROJECT_LAYOUT_VALIDATED=true
P2_COMPLETE=true
ZONE_COUNT=12
ACCESS_REQUIREMENT_COUNT=12
ACCESS_PASS_COUNT=12
TRUCK_ROUTE_VALIDATED=true
BUILDING_FOOTPRINT_PRESENT=true
OWNER_XINZHAO_P1A_VISUAL_REVIEW=PENDING
OWNER_XINZHAO_P1A_VISUAL_BLOCKER_RESOLVED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
```

## Outcome

The first pushed R11 head failed a real full-chain regression. It collected
multiple main-process seeds before starting tail search, consuming bounded
search nodes while an admissible seed had not yet received its tail search.
The forward-only correction now tails each exact-preflight-passing seed as
soon as the constructor yields it, then resumes the same constructor cursor.
This restores full-chain feasibility without replaying the consumed prefix,
raising the 120-node global budget, or weakening P2D/access/truck rules.

On the canonical Xinzhao Tool 7 replay, 11 distinct geometries were
constructed: eight were correctly rejected by the unchanged exact packaging
slot preflight, and three were tail-admissible. All three reached P2D. The two
Offset-discovered geometries `062f…` and `a148…` each produced complete P2C
candidates but failed the unchanged access requirement validation. The
`55589…` skeleton remained hard-valid and supplied two full-pass P2C
candidates. It won because it was the only distinct full-pass main-process
skeleton; there is no distinct-skeleton runner-up.

The selected geometry is unchanged from R10, so the SVG hash is unchanged and
no duplicate visual pack was generated. R10 diagnostic frontiers `868c…` and
`e73b…` were not reached by production. The 956e geometry remains rejected
before tail search. R11 therefore passes its bounded-search coverage and
hard-regression gates, but does not resolve the Owner visual blocker or finish
P1A.

## Verification

- Focused R11/R7/R9 unit, architecture, and real Tool 7 checks: 19 passed.
- R10 eight-variant diagnostic, P1F representative fixtures, and real P4
  full-chain regression: 3 passed.
- Existing six-tool and Tool 7 contract/integration checks: 54 passed, one
  long full-chain case deselected from that group and run separately above.
- Full architecture suite: 765 passed, 16 skipped.
- Ruff, format, mypy, diff check, and final exact-head CI are recorded in the
  final task receipt and PR checks.

Machine-readable scheduler, work-queue, budget, candidate, frontier, and
cross-fixture evidence is in `evidence/v2_2_2_p1a/xinzhao_p1a_r11_*`.
