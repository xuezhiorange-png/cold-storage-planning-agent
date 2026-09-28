# V2.2.2 P1A R14 — main-skeleton truck-feasibility boundary audit

```ini
TASK_ID=V2_2_2_P1A_R14_MAIN_SKELETON_TRUCK_FEASIBILITY_BOUNDARY_AUDIT_R1
TASK_TYPE=DIAGNOSTIC_DESIGN_GATE
RUNTIME_IMPLEMENTATION_AUTHORIZED=false
UNIQUE_MAIN_SKELETON_COUNT=6
COMMON_ROOT_CAUSE=true
MULTI_CAUSAL_EXHAUSTION=true
ROOT_CAUSE_CLASS=SHIPPING_CHANNEL_LOADING_FACE_AND_BOUNDARY_REACHABILITY
NEXT_IMPLEMENTATION_ENTRY=TRUCK_PREFLIGHT_AWARE_MAIN_SKELETON_CONSTRUCTION
NEXT_IMPLEMENTATION_AUTHORIZED=false
```

## Real R13 preflight skeletons

All rows below are captured from the unmocked Tool 7 production replay. The process-local observer wrapped the existing validator's transform call and did not alter its result or persist runtime instrumentation.

| Skeleton | Discovery → canonical owner | Truck result | Nodes | Loading face |
| --- | --- | --- | ---: | --- |
| `sha256:55589c20…` | STRAIGHT_LINEAR_BAND → STRAIGHT_LINEAR_BAND | PASS | 3 | BOTTOM_LONG_EDGE [1624, 33700]→[9317, 33700] |
| `sha256:062f563b…` | OFFSET_LINEAR_BAND → STRAIGHT_LINEAR_BAND | TRUCK_MANEUVER_SEARCH_EXHAUSTED | 39 | LEFT_LONG_EDGE [800, 33700]→[800, 41393] |
| `sha256:36bb2818…` | OFFSET_LINEAR_BAND → STRAIGHT_LINEAR_BAND | TRUCK_MANEUVER_SEARCH_EXHAUSTED | 39 | BOTTOM_LONG_EDGE [6100, 27200]→[13793, 27200] |
| `sha256:6613e0ea…` | OFFSET_LINEAR_BAND → STRAIGHT_LINEAR_BAND | TRUCK_MANEUVER_SEARCH_EXHAUSTED | 39 | LEFT_LONG_EDGE [800, 39153]→[800, 46846] |
| `sha256:a148aab8…` | OFFSET_LINEAR_BAND → STRAIGHT_LINEAR_BAND | TRUCK_MANEUVER_SEARCH_EXHAUSTED | 39 | LEFT_LONG_EDGE [6100, 26007]→[6100, 33700] |
| `sha256:b667428b…` | OFFSET_LINEAR_BAND → STRAIGHT_LINEAR_BAND | TRUCK_MANEUVER_SEARCH_EXHAUSTED | 39 | LEFT_LONG_EDGE [800, 44607]→[800, 52300] |

## Causal geometry boundary

The control's selected final dock pose lies on its authoritative loading face. For each rejected skeleton, every observed terminal dock pose misses the current loading face; other explored branches fail the exact effective-boundary predicate. No observed branch envelope was rejected by a hard obstacle or another main-zone interior.

| Skeleton | Main zones changed vs control | Final dock on current face | Direct failure counts | Blocking zones / obstacles |
| --- | --- | --- | --- | --- |
| `sha256:55589c20…` | — | PASS | `{}` | zones `none`; obstacles `none` |
| `sha256:062f563b…` | secondary_precooling_room, coating_room, finished_goods_room, shipping_channel | MISS | `{'BOUNDARY_CONFLICT': 18, 'FINAL_DOCK_NOT_ON_LOADING_FACE': 6}` | zones `none`; obstacles `none` |
| `sha256:36bb2818…` | secondary_precooling_room, coating_room, finished_goods_room, shipping_channel | MISS | `{'BOUNDARY_CONFLICT': 18, 'FINAL_DOCK_NOT_ON_LOADING_FACE': 6}` | zones `none`; obstacles `none` |
| `sha256:6613e0ea…` | secondary_precooling_room, coating_room, finished_goods_room, shipping_channel | MISS | `{'BOUNDARY_CONFLICT': 18, 'FINAL_DOCK_NOT_ON_LOADING_FACE': 6}` | zones `none`; obstacles `none` |
| `sha256:a148aab8…` | secondary_precooling_room, coating_room, finished_goods_room, shipping_channel | MISS | `{'BOUNDARY_CONFLICT': 18, 'FINAL_DOCK_NOT_ON_LOADING_FACE': 6}` | zones `none`; obstacles `none` |
| `sha256:b667428b…` | secondary_precooling_room, coating_room, finished_goods_room, shipping_channel | MISS | `{'BOUNDARY_CONFLICT': 18, 'FINAL_DOCK_NOT_ON_LOADING_FACE': 6}` | zones `none`; obstacles `none` |

- The five rejects share the same direct-failure signature: `{'BOUNDARY_CONFLICT': 90, 'FINAL_DOCK_NOT_ON_LOADING_FACE': 30}`. This is a common failure pattern with multiple exhausted branch causes: boundary-envelope rejection and final dock-pose/loading-face mismatch.
- Across the six real searches, `198` nodes were observed: `120` directly failed an existing predicate and `75` locally viable nodes had no complete descendant chain; `3` nodes form the control pass chain.
- Main-zone-envelope conflicts: `0`; hard-obstacle conflicts: `0`.

## Branch-level findings

Each attempted template transform includes its required-class sequence, entry lattice point, rotation, transformed poses, envelope, the first rejecting existing predicate, and exact blocking zone/obstacle identities. The machine-readable tree preserves every node; aggregate labels are descriptive taxonomy, not new engineering rules.

- Direct rejection counts: `{'BOUNDARY_CONFLICT': 90, 'HARD_OBSTACLE_CONFLICT': 0, 'MAIN_ZONE_ENVELOPE_CONFLICT': 0, 'ENTRY_POSE_INVALID': 0, 'CHAIN_CONTINUITY_INVALID': 0, 'FINAL_DOCK_POSE_MISSING': 0, 'FINAL_DOCK_NOT_ON_LOADING_FACE': 30, 'NO_TEMPLATE_FOR_REQUIRED_CLASS': 0, 'OTHER_EXACT_TRUCK_CONFLICT': 0}`.
- Alternate loading-face passes: `0`.
- Owner authority decision required: `false`.
- Local truck-feasible translation witness: `false`.
- Zone-removal counterfactual pass witnesses: `0`.
- All loading-face, zone-removal, and translation changes are evaluation-only; none is a production candidate or authority change.

## Search coverage and selected result

- Placement budget `120`, visited `120`, remaining `0`; active truncated work items `3`.
- Unexplored constructive work remains: `true`. Therefore the observed absence of another truck-feasible skeleton is not an infeasibility proof.
- Tool 7 remains hard-valid: project layout `true`, P2 complete `true`, access `12/12`, truck `true`, zones `12`, footprint `true`.
- Selected layout/hash/SVG remain unchanged from R13; this audit does not resolve the Owner visual blocker.

## Governance

No production code, P2D authority, loading-face policy, truck templates/budgets, placement budget, public contracts, ranking, Golden inputs, or P1B thresholds were changed. R14 is diagnostic only; a subsequent implementation requires separate authorization.
