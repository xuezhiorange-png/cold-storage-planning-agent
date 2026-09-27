# V2.2.2 P1A R11 — Resumable constructive coverage scheduler

```ini
TASK_ID=V2_2_2_P1A_R11_RESUMABLE_CONSTRUCTIVE_COVERAGE_SCHEDULER_R1
BASE_HEAD_SHA=d0559847a174e8a86bcf091adccc57898f887a4c
RESULT=FAIL_REGRESSION
PRODUCTION_PLACEMENT_NODE_BUDGET=120
PRODUCTION_BUDGET_CHANGED=false
RESUMABLE_CONSTRUCTIVE_SEARCH_IMPLEMENTED=true
GLOBAL_MULTI_ROUND_SCHEDULER_IMPLEMENTED=true
PER_ROOT_CAP_IS_QUANTUM=true
PER_FACE_CAP_IS_QUANTUM=true
CONSTRUCTION_SHARE_IS_TERMINAL_CAP=false
REPLAYED_PREFIX_NODE_COUNT=0
GLOBAL_NODE_VISITS=120
GLOBAL_NODE_BUDGET_REMAINING=0
UNUSED_GLOBAL_NODES_WITH_ACTIVE_TRUNCATED_WORK=0
EARLY_STOP_REASON=GLOBAL_PLACEMENT_NODE_BUDGET_EXHAUSTED
956E_PREFLIGHT_REJECTED=true
956E_TAIL_SEARCH_STARTED=false
TAIL_ADMISSIBLE_DISTINCT_MAIN_PROCESS_SKELETON_COUNT=3
P2D_EVALUATED_DISTINCT_MAIN_PROCESS_SKELETON_COUNT=2
P2D_FULL_PASS_DISTINCT_MAIN_PROCESS_SKELETON_COUNT=0
R10_868C_REACHED_BY_PRODUCTION=false
R10_E73B_REACHED_BY_PRODUCTION=false
OWNER_XINZHAO_P1A_VISUAL_BLOCKER_RESOLVED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
```

## Outcome

The scheduler keeps each topology lane's generator alive across deterministic
16-node quanta, rotates active lanes in rounds, and accounts for exactly 120
placement nodes. No prefix nodes were replayed, and no global nodes were left
unused while truncated work remained. The exact R9 packaging preflight remains
active: the 956e skeleton has no legal packaging slot and never starts tail
search. Three distinct skeletons pass packaging preflight; two distinct
skeletons reach P2D.

R11 is nevertheless **FAIL_REGRESSION**. The existing real Tool 7 full-chain
regression test
`test_tool7_real_chain_selects_later_p2d_full_pass_and_projects_svg` now returns
`VALIDATED_LAYOUT_SEARCH_EXHAUSTED`. Its P2D candidates have 11/12 access
requirements passing and report `TRUCK_MANEUVER_SEARCH_EXHAUSTED`; no full-pass
layout, canonical result hash, or SVG is produced. This is a hard-valid-to-no-
layout regression and blocks acceptance. Access, truck, and P2D authorities
were not changed.

The R10 diagnostic frontiers `868c…` and `e73b…` were not reached by the
production scheduler. The observed P2D skeletons were different geometry
(`062f…` and `a148…`), and both failed unchanged P2D validation. The 55589
skeleton passed packaging preflight and began tail search but did not reach
P2D within this run. The 956e skeleton was rejected at preflight.

## Determinism and scope

Two real Tool 7 replays produced the same queue trace and the same search
result. Because no layout was selected, layout/SVG byte and hash identity are
not applicable. Placement budget remains 120; axis/direction coverage,
topology construction geometry, topology classification, Tool 7 payload, and
the six earlier MCP tools were not expanded or redefined. P1B thresholds,
weighted scores, Golden coordinate templates, and fixture-specific runtime
branches remain disabled.

## Verification

- Focused R11/R7/R9 tests: 42 passed.
- Full architecture suite: 763 passed, 16 skipped.
- Six-tool plus Tool 7 non-full-chain contract tests: 46 passed, one long
  real-chain test excluded from this group and reported separately as failed.
- Real Tool 7 full-chain regression: failed with
  `VALIDATED_LAYOUT_SEARCH_EXHAUSTED` (hard-valid-to-no-layout regression).
- Changed-file Ruff, format check, mypy, and diff check: recorded after final
  documentation/evidence updates.
- Owner visual review: pending; no new visual pack was created because no
  selected layout geometry exists.

Machine-readable details are in `evidence/v2_2_2_p1a/xinzhao_p1a_r11_*`.
