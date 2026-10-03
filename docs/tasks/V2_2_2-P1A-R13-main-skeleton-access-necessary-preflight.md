# V2.2.2 P1A R13 — main-skeleton truck necessary preflight

```ini
TASK_ID=V2_2_2_P1A_R13_MAIN_SKELETON_ACCESS_NECESSARY_PREFLIGHT_R1
BASE_HEAD_SHA=ec9ea3aa20589f587be352f70cba0cd4b541fbd7
PR_NUMBER=302
PR_STATE=OPEN_DRAFT
RESULT=PASS
```

## Result

The structured Tool 7 candidate generator now applies the existing
`validate_truck_maneuver_chain(...)` to the frozen seven-zone main-process
skeleton after construction and before any tail search. It reuses the same
truck binding, boundary, obstacles, node budget, and `_loading_face(...)`
helper used to form the final P2C shipping loading face.

Only an authoritative `TRUCK_MANEUVER_SEARCH_EXHAUSTED` result with
`search_tree_exhausted=true` and `node_budget_exhausted=false` rejects a
skeleton. A passing result only admits the skeleton to tail search; an
unresolved/missing-authority or budget-exhausted result also continues to the
existing path. Every complete candidate still undergoes the unchanged P2D,
including all access requirements, truck, and footprint validation. The
preflight trace is internal evaluation evidence and is not serialized in Tool
7's public response.

| Main-process skeleton | Preflight | Truck search | Tail/P2D result |
| --- | --- | --- | --- |
| `55589c20…` control | PASS | 3 nodes; tree exhausted; budget 5000 not exhausted | Tail entered; 2 complete P2C candidates and 2 P2D full-pass candidates |
| `062f563b…` Target A | REJECT | `TRUCK_MANEUVER_SEARCH_EXHAUSTED`; 39 nodes; tree exhausted; budget 5000 not exhausted | Tail not entered; P2D not reached |
| `a148aab8…` Target B | REJECT | `TRUCK_MANEUVER_SEARCH_EXHAUSTED`; 39 nodes; tree exhausted; budget 5000 not exhausted | Tail not entered; P2D not reached |

For the selected control, the preflight and final P2C loading face are identical.
The final selected layout remains hard-valid: 12 zones, 12/12 access,
truck route validated, building footprint present, `PROJECT_LAYOUT_VALIDATED=true`,
and `P2_COMPLETE=true`.

## Accounting and determinism

The real Tool 7 replay examined six distinct main skeletons: one passed and
five were rejected by the same exact exhausted-search condition. R12 had six
complete P2C candidates (two per control/A/B skeleton); R13 has two complete
P2C candidates, both under the surviving control. Tail search was entered for
one skeleton and avoided for five. Placement search used its existing 120/120
nodes. Truck preflight used the unchanged 5000-node authority;
across these six skeletons it visited 198 truck-search nodes. Truck preflight
computation is separate from placement-node accounting.

Two unmocked Xinzhao replays produced identical preflight results and rejection
order, selected layout, canonical result hash, work-queue trace, SVG bytes, and
SVG hash. The selected main skeleton, canonical result hash
(`sha256:ed11e746cd65142b26cfb20e371dda3a91b39501175681d2538d4359ee017c0d`),
and SVG hash
(`sha256:342775cb44d7165a9a64ad7e7f31cd287c04d5a1655bcc8f31ec1c1224f85981`)
are unchanged from R12. No serialization change was needed.

The existing P1F real-selector fixture with no-build zones also remained
hard-valid. Across the Xinzhao and P1F replays, no preflight rejection had a
failure reason other than the exact authoritative exhausted truck search, and
there were zero hard-valid-to-invalid fixture regressions.

## Scope and governance

```ini
MAIN_SKELETON_TRUCK_PREFLIGHT=NECESSARY_CONDITION_ONLY
SECOND_TRUCK_GEOMETRY_VALIDATOR_CREATED=false
P2D_FINAL_VALIDATION_RETAINED=true
PRODUCTION_PLACEMENT_NODE_BUDGET=120
TRUCK_NODE_BUDGET=5000
PRODUCTION_PLACEMENT_NODE_BUDGET_CHANGED=false
TRUCK_NODE_BUDGET_CHANGED=false
TOOL7_PUBLIC_CONTRACT_CHANGED=false
P1B_THRESHOLD_ACTIVATED=false
WEIGHTED_SCORE_USED=false
OWNER_XINZHAO_P1A_VISUAL_BLOCKER_RESOLVED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
```

The R13 outcome only removes known truck-infeasible main skeletons before tail
search. It does not claim to resolve the independent Owner visual blocker or
authorize any later governance step.

Machine-generated replay evidence is recorded in the six
`xinzhao_p1a_r13_*.json` files under `docs/tasks/evidence/v2_2_2_p1a/`.
