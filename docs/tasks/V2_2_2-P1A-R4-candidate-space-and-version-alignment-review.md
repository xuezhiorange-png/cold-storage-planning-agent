# V2.2.2 P1A R4 — Candidate-Space and Version-Alignment Review

```ini
TASK_ID=V2_2_2_P1A_R4_CANDIDATE_SPACE_AND_VERSION_ALIGNMENT_REVIEW_R1
REVIEWED_PR_HEAD=82f3260c17609ec45d0e81318a34c9a1c4568927
TARGET_VERSION=v2.2.2
ACTIVE_GOVERNANCE_LANE=V2.2.2_P1A
TASK_TYPE=DESIGN_GATE_AND_EVIDENCE_REVIEW
P1A_R3_RESULT=PARTIAL
OWNER_XINZHAO_P1A_R3_VISUAL_REVIEW=PENDING
RUNTIME_IMPLEMENTATION_AUTHORIZED=false
P1B_THRESHOLD_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
GITHUB_RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
```

## Scope and evidence basis

This review changes no production runtime. It reconciles the version plan and
records a same-head, unmocked Tool 7 replay plus process-local search
instrumentation. The replay matched the saved R3 canonical result hash
`sha256:b3dd2de4fb24f74b5ce96601a74edab5f58a9a781eb5af41b29afd0a66ac98da`
and SVG hash
`sha256:342775cb44d7165a9a64ad7e7f31cd287c04d5a1655bcc8f31ec1c1224f85981`.
The input is the frozen Xinzhao fixture with SHA-256
`d03ecae9e1e2808cba346eb83a39f853c8a4b366acc103669af1cf868363901e`.

The replay instrumentation temporarily wrapped private placement functions in
the test process to attribute existing rejection events and per-seed tail-node
boundaries. It restored all hooks after the replay. No instrumentation is
added to Tool 7 output or runtime source. Machine-readable detail is in
[`xinzhao_r4_family_search_audit.json`](evidence/v2_2_2_p1a/xinzhao_r4_family_search_audit.json),
[`xinzhao_r4_linear_rejection_matrix.json`](evidence/v2_2_2_p1a/xinzhao_r4_linear_rejection_matrix.json),
[`xinzhao_r4_hub_skeleton_survival_trace.json`](evidence/v2_2_2_p1a/xinzhao_r4_hub_skeleton_survival_trace.json), and
[`xinzhao_r4_candidate_space_design_matrix.json`](evidence/v2_2_2_p1a/xinzhao_r4_candidate_space_design_matrix.json).

## Version-plan correction

The prior P1A plan text still described 15 nodes as the current P4 budget.
That was R1 history, not the R3 runtime. The corrected history is:

| Stage | Production placement cutoff | Evidence/status |
|---|---:|---|
| P1A R1 | 15 | Initial budget; not current |
| P1A R2 | 120 | Raised after deterministic sensitivity evidence |
| P1A R3 | 120 | Retained; still a bounded cutoff |
| Current reviewed head | 120 | Not a global-optimum claim; no Linear infeasibility proof |

At 60 and 120 total nodes, the sensitivity runs each produced two P2D
full-pass candidates but only one distinct full-pass main-process skeleton.
The R3 final selected seven-zone main-process geometry is unchanged from
v2.2.1/R1/R2. The plan now records these as R3 PARTIAL facts and marks R4
runtime implementation unauthorized.

## Candidate lifecycle audit (A–G)

The source path is `composition_family_candidates` → preferred-family ordering
→ lane budgets → constructive sorting roots → attachment faces → seven-zone
skeleton construction → tail placement → P2D → structural comparison → P2B2
tie-break. At the reviewed head:

| State | Finding |
|---|---|
| A. Family not explored | None. All three declared lanes received a nonzero allocation and were visited. |
| B. Family search truncated | All three. Hub visited 80/80; Linear Positive and Negative each visited 15 nodes under a 20-node lane allocation; none reports an exhausted search tree. |
| C. Skeleton construction failed | Both Linear lanes emitted zero skeletons in the explored prefix. This is a prefix outcome only; both lanes were truncated. |
| D. Skeleton constructed, tail failed | Hub skeleton `956e85adebc6f55ded51a481fb07dee437d364d241159beecd5714fbac24dfcc` was constructed, but its tail search exhausted its per-seed node share at node 80 without a complete P2C candidate. It never reached P2D. |
| E. Complete candidate rejected by P2D | None. Both complete P2C candidates passed P2D, including 12/12 access and truck validation. |
| F. P2D full-pass lost structural comparison | None across distinct skeletons. Both P2D full-pass candidates carry skeleton `55589c20f3c3336c1c92a8c1ffc8b14a813ac558bac78871d4e6b1fa8ee9b953`. |
| G. Structural tie, then P2B2 loss | One candidate lost. The recorded first decisive component is `P2B2_FINAL_TIE_BREAK`; candidate `7245f59f…` lost to `80e31a1f…`. This is a tie between tail variants on the same main skeleton, not a structural-topology contest. |

The second Hub seed's trace is exact: tail started at visited node 44, had a
share limit of 80, ended at node 80 with `tail_share_exhausted=true`, emitted
zero complete candidates, and therefore has access/truck/footprint/P2D
statuses `NOT_REACHED`. This is a tail-search budget outcome, not an access,
truck, footprint, or P2D rejection.

## Linear-family diagnosis

The linear lanes each receive 20 nodes but the construction allowance is
`max(15, lane_budget // 2)`, so each gets a 15-node skeleton-construction
prefix. The replay rejection matrix groups every captured event by family,
sorting root, raw/finished face pair, zone code, reason, and stage. Its 513
events aggregate to 366 root-specific rows. Across each direction, 171 events
occur while filtering sorting-room root candidates. The remaining observed
construction rejections concentrate on `primary_precooling_room`,
`raw_fruit_buffer`, and, for Positive only, `secondary_precooling_room`.
Reasons include `SITE_OUTSIDE`, `NO_BUILD_COLLISION`, and
`SKELETON_TOPOLOGY_INVALID`; the evidence does not show a completed seven-zone
Linear candidate reaching the stage where the entire group envelope can be
tested.

### Q1 — genuine site impossibility or early search loss?

Not proven to be genuine site impossibility. Both Linear lanes were truncated
at 15 construction nodes and the final attempted roots are marked `TRUNCATED`.
The observed failures identify constraints encountered in the explored
prefix, not an exhausted search space. Therefore
`LINEAR_INFEASIBILITY_PROVEN=false`.

### Q2 — is the allowed Linear topology too narrow?

Yes, structurally. For the X-dominant fixture the lanes fix raw/finished faces
to WEST/EAST or EAST/WEST. The constructor then grows one exact-edge chain
from sorting: primary/raw on the raw face and secondary/coating/finished/
shipping on the finished chain. It has no separately enumerated Straight,
Offset, Folded, parallel-row, or terminal-bend Linear topology. This means the
current rejection evidence cannot tell whether a folded/offset viable layout
exists; it only describes this specific chain policy.

### Q3 — do roots account for full-chain extents?

Sorting roots are sampled from deterministic site-boundary events, obstacle
events, and family root anchors. Each candidate sorting rectangle is checked
for site containment and obstacle collision, then roots are ordered by
preferred anchor and max-min spacing. The root builder does not first project
the seven-zone group extents or reject roots by whole-chain viable intervals.
Thus it can spend construction nodes on a sorting rectangle that fits alone
but leaves insufficient room for its upstream/downstream groups. This is a
root-planning coverage limitation, not evidence that dimensions should change.

### Q4 — where did observed Linear rejections occur?

The zone-level totals, with every row retaining its root and face-pair key,
are in the rejection matrix. Positive: sorting roots 135 `SITE_OUTSIDE` + 36
`NO_BUILD_COLLISION`; primary precooling 2 + 11 respectively, plus one
topology invalid; raw buffer 40 + 18, plus eight topology invalid; secondary
precooling six site-outside plus one topology invalid. Negative: sorting roots
135 + 36; primary precooling 15 site-outside, four no-build, two topology
invalid; raw buffer 54 site-outside and nine topology invalid. These totals
match the saved R3 family rejection counts. There is no `SHIPPING_INTERFACE`
failure in either Linear lane because neither emitted a full skeleton that
reached shipping construction.

## Search budget, diversity caps, and family preference

The following values bound computation, not engineering/layout authority:

`CONSTRUCTIVE_SKELETON_COMPLETION_LIMIT=2`,
`STRUCTURED_COMPLETIONS_PER_MAIN_SKELETON=2`,
`STRUCTURED_COMPLETIONS_PER_CORE_ROOT=4`,
`CONSTRUCTIVE_FACE_PAIR_NODE_BUDGET=20`, and
`CONSTRUCTIVE_SORTING_ROOT_NODE_BUDGET=16`. The global per-lane completion
limit of two is a plausible diversity ceiling: Hub constructed two seeds and
the lane's construction report still says search was truncated. It should not
be interpreted as a design rule or as proof that only two layouts exist.

The current preferred-family rule uses the sorting room being the largest
main-process zone as a reason to order Central Hub first; the preferred lane
then receives approximately two thirds of the node allocation (80/120 vs
20/120 per Linear direction). “Largest room” is a search-order prior, not
evidence that Hub is the only or best organization. The four policy options
and trade-offs are in the candidate-space design matrix:

| Policy | Benefit | Risk |
|---|---|---|
| A. Preferred-family biased | Preserves a cheap role-based prior | Can starve alternative topologies based on a weak proxy |
| B. Equal family exploration | Gives comparable initial coverage | May spend equal work on unproductive lanes |
| C. Skeleton-count-targeted | Allocates against realized geometric diversity | Needs explicit fairness and stopping semantics |
| D. Staged coverage, then preference | Seeks a seed from each viable topology before spending the remainder on preference | A non-viable topology can consume its initial exploration reserve |

R4 does not change any budget, cap, lane policy, or runtime behavior.

## Proposed R4 candidate space (design only)

The next candidate generator should enumerate geometrically distinct
topologies, not just more points in the current chain:

1. `STRAIGHT_LINEAR_BAND` — monotonic raw/core/finished intervals in a single
   principal band.
2. `OFFSET_LINEAR_BAND` — same process order across parallel offset rows.
3. `FOLDED_LINEAR_BAND` — process spine with one explicit orthogonal bend.
4. `CENTRAL_PROCESS_HUB` — sorting as the core with independently selected
   permitted raw and finished attachment faces.
5. `HUB_WITH_STORAGE_BANK` — hub plus a co-constructed raw or finished cold
   bank; support remains a subordinate branch.

Each construction must consume existing authoritative dimensions and pass
site/buildable containment, no-build, MUST adjacency, access, truck, and P2D
predicates. Topology preferences are not hard overrides. Golden drawings
remain qualitative references for continuous process bands, recognizable
cores, grouped storage, subordinate support, and limited orthogonal axes; no
coordinates, dimensions, room counts, or templates are adopted.

The candidate-space design gate is complete for planning purposes:

```ini
CANDIDATE_SPACE_DESIGN_REVIEW_COMPLETE=true
AT_LEAST_TWO_STRUCTURALLY_DISTINCT_MAIN_PROCESS_TOPOLOGIES_DEFINED=true
LINEAR_FAMILY_FAILURE_CLASSIFIED=true
SECOND_HUB_SKELETON_FAILURE_CLASSIFIED=true
SEARCH_BUDGET_SEPARATED_FROM_LAYOUT_AUTHORITY=true
GOLDEN_COORDINATE_TEMPLATE_USED=false
P1B_NUMERIC_THRESHOLD_USED=false
NEXT_IMPLEMENTATION_ENTRY_READY=true
NEXT_IMPLEMENTATION_AUTHORIZED=false
```

For a separately authorized implementation, recommend the temporary Xinzhao
development acceptance target: at least two different main-process skeletons
must each satisfy the existing hard engineering predicates and both reach
complete P2D evaluation. This is not a permanent production threshold and
does not replace Owner visual review. No weighted total score or uncalibrated
P1B metric threshold is proposed.

## Verification and scope

The R4 evidence test validates the R3 PARTIAL/PENDING state, lane/exhaustion
facts, rejection-matrix totals, Hub survival trace, topology/policy proposal,
and the corrected version-plan budget history. The unmocked replay above
matched the saved R3 result and SVG hashes. No file under `backend/src/`,
`frontend/`, database, or MCP contract was changed by this review. No SVG was
edited. This report does not claim Owner acceptance and does not authorize
runtime implementation.
