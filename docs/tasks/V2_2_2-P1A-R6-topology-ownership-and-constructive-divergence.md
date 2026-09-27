# V2.2.2 P1A R6 — topology ownership and constructive divergence

```ini
TASK_ID=V2_2_2_P1A_R6_TOPOLOGY_OWNERSHIP_AND_CONSTRUCTIVE_DIVERGENCE_R1
RESULT=PARTIAL
BASE_HEAD_SHA=d99ebfadd90a477e9f801dae49ef03bbe524f384
PRODUCTION_PLACEMENT_NODE_BUDGET=120
PRODUCTION_BUDGET_CHANGED=false
SEARCH_POLICY=STAGED_COVERAGE_THEN_PREFERENCE
OWNER_XINZHAO_P1A_R6_VISUAL_REVIEW=PENDING
```

R6 adds a deterministic exact-geometry topology classifier with canonical
ownership precedence `STRAIGHT_LINEAR_BAND`, then `OFFSET_LINEAR_BAND`, then
`CENTRAL_PROCESS_HUB`. The classifier identifies search topology only; it is
not an engineering-validity gate and does not contribute a quality score.
R5's shared seven-zone geometry (`sha256:55589c20…ee9b953`) classifies as
Straight even though it also matches Hub face-contact facts.

The Straight lane records an explicit construction policy. Offset now actively
enumerates the `CORE_TO_FINISHED` cross-axis transition in both directions;
the representative fixture produced exact nonzero-shift transition options,
but did not close any into a complete seven-zone Offset skeleton. Hub
construction continued after finding a geometry canonically owned by Straight
and did not send that non-owner geometry through tail search or P2D. New
construction provenance is isolated in the internal evaluation sidecar;
Tool 7 serialization fields remain unchanged.

On the canonical Xinzhao input, all three topology-specific divergence paths
were attempted within the unchanged 120-node global cutoff. Actual placement
visits were 98/120. Only one canonical-owner skeleton reached P2D: the same
Straight geometry selected in R5. Two tail variants passed P2D, but they are
one distinct main-process skeleton, not two. The distinct runner-up is absent;
therefore structural comparison still cannot choose between different
full-pass skeletons. The result remains `PARTIAL`, and no new visual pack is
created because selected geometry and SVG are unchanged from R5.

The hard-valid result still has 12 zones, 12/12 access passes, validated truck
route, and a building footprint. No P1B threshold, weighted score, fixture
special case, Golden coordinate template, or P2D relaxation was introduced.
Owner visual acceptance remains an independent pending gate.

Machine-readable evidence:

- `evidence/v2_2_2_p1a/xinzhao_p1a_r6_metrics.json`
- `evidence/v2_2_2_p1a/xinzhao_p1a_r6_topology_ownership.json`
- `evidence/v2_2_2_p1a/xinzhao_p1a_r6_constructive_divergence.json`
- `evidence/v2_2_2_p1a/xinzhao_p1a_r6_offset_transition.json`
- `evidence/v2_2_2_p1a/xinzhao_p1a_r6_cross_topology_duplicates.json`
- `evidence/v2_2_2_p1a/xinzhao_p1a_r6_skeleton_survival.json`

Next diagnostic focus: determine why the exact Offset transition options cannot
complete the remaining authoritative process chain within the existing
bounded search, without increasing the global budget or weakening any hard
predicate. This note does not authorize a subsequent implementation phase.
