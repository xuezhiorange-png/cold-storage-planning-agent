# V2.2.2 P1A R7 — Canonical Geometry Admission and Tail Evaluation

## Result

`RESULT=PARTIAL`. R7 separates discovery lane, canonical geometry ownership,
and evaluation admission. A new exact skeleton is admitted to tail search once
regardless of whether its discovery lane matches its canonical owner. Repeated
discovery of a hash whose tail search has already started is skipped.

The Xinzhao Tool 7 full-chain result remains engineering-hard-valid and
deterministic. The previously excluded `956e...` geometry now enters tail
search, but exhausts its 12-node tail share without completing a P2C candidate;
it does not reach P2D. Therefore only one distinct main-process skeleton is
evaluated and full-pass, and no distinct runner-up exists. This is valid
lifecycle progress, not proof that the second geometry is infeasible.

## R7 gates

| Gate | Result |
| --- | --- |
| Discovery lane decoupled from canonical owner | PASS |
| Canonical owner decoupled from evaluation admission | PASS |
| New non-owner geometry admitted to tail | PASS |
| Same exact geometry tail evaluated at most once | PASS |
| Evaluation family rebound to canonical topology | PASS |
| Constructed distinct main-process skeletons | 2 |
| Distinct skeletons reaching P2D | 1 |
| Distinct full-pass skeletons | 1 |
| Distinct runner-up | NONE |
| Selected layout hard-valid | PASS |
| Selected main-process geometry changed from R6 | NO |
| SVG hash changed from R6 | NO |

## 956e lifecycle

`sha256:956e85adebc6f55ded51a481fb07dee437d364d241159beecd5714fbac24dfcc`
was discovered by `CENTRAL_PROCESS_HUB` and classified as
`STRAIGHT_LINEAR_BAND`. Its evaluation identity was rebound to
`LINEAR_PROCESS_BAND`, dominant axis `Y`, direction `POSITIVE`, without
changing any zone rectangle. Tail search started once under its Hub discovery
provenance. It used 12/12 tail nodes, produced zero complete P2C candidates,
and did not reach P2D. The first failure is
`TAIL_SEARCH / TAIL_NODE_SHARE_EXHAUSTED_WITHOUT_COMPLETE_P2C_CANDIDATE`; the
recorded zero-option tail zone is `packaging_material_storage`.

## Selected geometry and quality gates

The selected distinct geometry remains
`sha256:55589c20f3c3336c1c92a8c1ffc8b14a813ac558bac78871d4e6b1fa8ee9b953`
(`STRAIGHT_LINEAR_BAND`). It yielded two complete P2C candidates and two P2D
full passes, both for the same exact main-process geometry. Since 956e did not
reach P2D, structural comparison between distinct full-pass skeletons was not
available; `distinct_skeleton_first_decisive_component=ONLY_ONE_P2D_FULL_PASS_MAIN_SKELETON`.

The canonical result hash is
`sha256:30daa8da4bb3d181f4dc0004c027f86152b995c68535c8baef0678e53947702a`.
The SVG hash remains equal to R6:
`sha256:342775cb44d7165a9a64ad7e7f31cd287c04d5a1655bcc8f31ec1c1224f85981`.
Because selected engineering geometry did not change, no duplicate visual
pack was generated; Owner visual review remains pending.

Detailed run evidence: [R7 metrics](evidence/v2_2_2_p1a/xinzhao_p1a_r7_metrics.json)
and [geometry evaluation lifecycle](evidence/v2_2_2_p1a/xinzhao_p1a_r7_geometry_evaluation.json).

P1B numeric thresholds, P2D rules, public Tool 7 contract, the existing six
tool contracts, and the 120-node production budget remain unchanged. The
bounded search result is not a global-optimum claim or an infeasibility proof.
