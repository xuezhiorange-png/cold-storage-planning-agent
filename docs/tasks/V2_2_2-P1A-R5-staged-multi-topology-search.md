# V2.2.2 P1A-R5 — staged multi-topology search

```ini
TASK_ID=V2_2_2_P1A_R5_STAGED_MULTI_TOPOLOGY_SEARCH_IMPLEMENTATION_R1
ACTIVE_GOVERNANCE_LANE=V2.2.2_P1A
BASE_MAIN_SHA=955e5e532236fb6c33a80709e90362b12124fb72
PREVIOUS_PR_HEAD_SHA=2b00f3d8de7f13991137bf484930c69d1f203ad6
RESULT=PARTIAL
OWNER_XINZHAO_P1A_R5_VISUAL_REVIEW=PENDING
PRODUCTION_PLACEMENT_NODE_BUDGET=120
PRODUCTION_BUDGET_CHANGED=false
SEARCH_POLICY=STAGED_COVERAGE_THEN_PREFERENCE
TOPOLOGIES_AUTHORIZED=STRAIGHT_LINEAR_BAND,OFFSET_LINEAR_BAND,CENTRAL_PROCESS_HUB
FOLDED_LINEAR_BAND_IMPLEMENTED=false
HUB_WITH_STORAGE_BANK_IMPLEMENTED=false
P1B_THRESHOLD_ACTIVATED=false
WEIGHTED_SCORE_USED=false
TOOL7_CONTRACT_CHANGED=false
EXISTING_SIX_TOOL_CONTRACT_CHANGED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
GITHUB_RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
```

## Outcome

R5 replaces preferred-family-biased allocation with deterministic staged
topology coverage. The unchanged 120-node global cutoff is divided 40/40/40
among Straight Linear, Offset Linear, and Central Hub. The first 15 nodes of
each lane are reserved for coverage; remaining lane capacity is available for
diversity work. Sorting roots are ordered by an estimated full-topology
envelope penalty, but this is ordering only. There is no heuristic root
pruning. Face-pair and sorting-root construction allowances are apportioned
within the bounded lane instead of allowing the first root/face pair to take
the whole allowance.

The representative Xinzhao Tool 7 replay remains hard-valid and deterministic:
12 zones, 12/12 access passes, validated truck route, and building footprint
present. All three topology lanes were entered. Straight Linear and Central
Hub each constructed and submitted a skeleton to P2D, but both produced the
same seven-zone main-process geometry identity
`sha256:55589c20f3c3336c1c92a8c1ffc8b14a813ac558bac78871d4e6b1fa8ee9b953`.
Offset Linear constructed no skeleton in its bounded search. Its rejection
counts and attempted roots are retained in the topology-search evidence;
search was not exhausted, so this does not prove infeasibility.

Four complete P2D full-pass candidates were observed across the successful
lanes, but they represent only one distinct main-process skeleton. The
selected seven main-process zones therefore remain unchanged from R3, and the
selected production SVG is byte-identical to R3. There is no distinct-skeleton
runner-up artifact. Within the candidates sharing that geometry, the final
compatibility tie-break remains P2B2; R5 has not demonstrated a structural
choice between different full-pass skeletons. These facts fail the requested
R5 diversity and layout-effect acceptance criteria, so the result is
intentionally `PARTIAL`.

This is not a global optimum or infeasibility claim. The search used 74 of the
120 node cutoff in this representative run, and the per-lane reports retain
construction truncation facts. No P2D hard rule, MUST adjacency, access,
truck, footprint, site, or no-build constraint was relaxed. No fixture-specific
runtime condition or Golden coordinate/template was added. No P1B numeric
threshold or weighted score was activated. Tool 7 and the six earlier MCP
tools keep their public contracts.

## Evidence

- [R5 metrics](evidence/v2_2_2_p1a/xinzhao_p1a_r5_metrics.json)
- [Topology-lane search](evidence/v2_2_2_p1a/xinzhao_p1a_r5_topology_search.json)
- [Per-skeleton survival trace](evidence/v2_2_2_p1a/xinzhao_p1a_r5_skeleton_survival.json)
- [Budget accounting](evidence/v2_2_2_p1a/xinzhao_p1a_r5_budget_accounting.json)
- [Cross-fixture regression](evidence/v2_2_2_p1a/xinzhao_p1a_r5_cross_fixture_regression.json)
- [Before / R3 / R5 comparison](evidence/v2_2_2_p1a/xinzhao_p1a_r5_comparison.md)
- [Selected layout JSON](evidence/v2_2_2_p1a/xinzhao_p1a_r5_selected_layout.json)
- [Selected production SVG](evidence/v2_2_2_p1a/xinzhao_p1a_r5_selected.svg)
- [Selected production PNG](evidence/v2_2_2_p1a/xinzhao_p1a_r5_selected.png)
- [Evaluation-only structural debug SVG](evidence/v2_2_2_p1a/xinzhao_p1a_r5_structural_debug.svg)
- [Evaluation-only structural debug PNG](evidence/v2_2_2_p1a/xinzhao_p1a_r5_structural_debug.png)

The debug overlay draws current functional-group bounding envelopes and the
selected topology's dominant-axis indicator. Envelopes are diagnostic bounds,
not engineering geometry; overlap between group bounds is possible. No image
was manually edited. The PNGs are direct macOS Quick Look rasterizations of the
corresponding SVGs.

Cross-fixture validation reuses three authoritative full-chain P1F fixtures
and two composition-only scenarios. It checks hard-pass status and deterministic
replay without claiming that the composition-only scenarios are validated
layouts. Owner review of the Xinzhao image remains a separate pending gate.
