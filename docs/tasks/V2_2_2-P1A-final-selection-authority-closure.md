# V2.2.2 P1A final selection authority closure

Task: `V2_2_2_P1A_FINAL_SELECTION_AUTHORITY_CLOSURE_R1`
PR: #302 (kept Draft)
Baseline: `edb6038a5f887573337b4885966b85e39a60e4d5`

## Decision

All three distinct main-process skeletons observed in the canonical, unmocked
Tool 7 replay produced full P2D passes. The selector continues to choose the
control skeleton, but its comparison against the best distinct runner-up is now
explained by the geometry-derived fact
`FINISHED_SHIPPING_INTERFACE_ALIGNMENT` (`1` versus `0`). It is no longer
explained by canonical JSON ordering.

The three panels are sorted by skeleton hash solely to assign stable labels;
the labels do not encode a recommendation:

| Panel | Main-process skeleton | P2D | Main group order | Core contiguous | Finished/shipping interface alignment |
|---|---|---|---:|---:|---:|
| Candidate A | `1c537958…` | Full pass | false | false | 1 |
| Candidate B | `55589c20…` (control) | Full pass | true | true | 1 |
| Candidate C | `e05ce4ee…` (1 mm shipping offset) | Full pass | true | true | 0 |

Candidate B also beats Candidate A earlier in the authorized lexicographic
vector at `MAIN_GROUP_ORDER_MONOTONIC` (true versus false). Candidate B beats
Candidate C at `FINISHED_SHIPPING_INTERFACE_ALIGNMENT` (one aligned interface
endpoint versus none). No topology bonus, weighted score, candidate hash, or
fixture-specific branch was added.

## Authority order

For full-pass candidates, selection now explicitly compares:

1. P2D hard-pass eligibility;
2. `StructuralQualityFactsV1` atomic lexicographic facts;
3. P2B2 business objectives (SHOULD adjacency, then the authorized loading-side
   preference);
4. canonical JSON only when structural facts and P2B2 business objectives are
   exactly tied.

The P2B2 objective comparison is separated from the serialization fallback.
The replay reports a canonical fallback among same-skeleton tail variants;
the distinct-skeleton comparison reports
`distinct_skeleton_canonical_json_tiebreak_used=false` and
`distinct_skeleton_first_decisive_component=FINISHED_SHIPPING_INTERFACE_ALIGNMENT`.

The new fact is an exact geometry relation. For the positive shared edge between
`finished_goods_room` and `shipping_channel`, it counts how many endpoints of
the shared segment coincide exactly with endpoints of the corresponding
finished-goods face. It is derived from the existing axis-aligned rectangle
geometry, including the existing rotation interpretation. It is not a hard
gate or a numeric threshold.

## Hard validation and compatibility

The selected control remains unchanged and passes: project layout validated,
P2 complete, access 12/12, truck route validated, 12 zones, and building
footprint present. Truck, access, P2D, site, zone dimension, placement-budget,
and Tool 7 public contract authorities were not changed. The canonical result
hash and SVG hash remain the control hashes because the lawful winner remains
the control. Owner visual acceptance remains a separate pending decision.

## Evidence and drawings

The generated candidate matrix contains, for each of the three skeletons, the
full twelve-zone candidate geometry, full P2D result, structural facts,
comparison vector, and its projection SVG hash. Individual SVG/PNG files and a
same-canvas, same-scale, uncropped A/B/C comparison are in
[`evidence/v2_2_2_p1a/`](evidence/v2_2_2_p1a/).

- [Candidate comparison](evidence/v2_2_2_p1a/xinzhao_p1a_final_selection_candidates.png)
- [Before/control](evidence/v2_2_2_p1a/xinzhao_p1a_final_before.png)
- [After/selected](evidence/v2_2_2_p1a/xinzhao_p1a_final_after.png)
- [Before/after](evidence/v2_2_2_p1a/xinzhao_p1a_final_side_by_side.png)

Two unmocked Tool 7 replays produced the same selected layout, canonical result
hash, SVG bytes, and SVG hash. The final candidate matrix and selection result
are `xinzhao_p1a_final_selection_candidates.json` and
`xinzhao_p1a_final_selection_result.json`.
