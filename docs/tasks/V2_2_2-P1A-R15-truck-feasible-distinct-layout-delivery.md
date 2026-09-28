# V2.2.2 P1A R15 — truck-feasible distinct layout delivery

**Overall result: FAIL (delivery geometry is not materially visible).**

The real Tool 7 chain constructed and selected a new distinct, hard-valid main-process skeleton under the unchanged 120-node placement budget and existing truck authority. However, the selected geometry changes only `shipping_channel.y` from `33.700 m` to `33.701 m` (1 mm); the before/after drawing is effectively indistinguishable at the shared canvas scale. This does not satisfy the requested visible structural change, so this is not reported as a successful P1A layout delivery.

## Exact replay result

| Fact | Result |
|---|---|
| Control skeleton | `sha256:55589c20f3c3336c1c92a8c1ffc8b14a813ac558bac78871d4e6b1fa8ee9b953` |
| Selected skeleton | `sha256:e05ce4ee27571b7e7fb7fdb72517353584455740217651f2f083927ba7ada834` |
| Main skeletons examined | 28 |
| Truck preflight PASS / REJECT | 5 / 23 |
| Distinct truck-feasible skeletons | 5 |
| Distinct P2D full-pass skeletons | 1 (the selected new skeleton) |
| Placement nodes | 120 / 120 |
| Final hard validity | PASS; 12 zones, 12/12 access, truck route, P2 complete, footprint present |
| Changed main-process zones | `shipping_channel` only; y delta `+1 mm` |
| Canonical result hash | `sha256:037b722f4b16c90c41d1651a70ec4af6b14e83bb9e8a8804682f59e335eb160b` |
| SVG SHA-256 | `sha256:6c4e43594161de0a8b31b5fed47292b35da726cf9725c08bddac2fab01749cd1` |
| Deterministic replay | PASS for selected skeleton, layout, result hash, SVG, preflight, selector trace, and work queue |
| P1F/P4 representative regression | PASS; zero hard-valid-to-invalid regressions |

The run exercised finite shipping candidates derived from authoritative dock-template/entrance and site-boundary events. Every retained layout still used the existing loading-face authority, truck validator, MUST adjacency, tail completion, and P2D. No truck/site/zone authority or search budget was changed. The additional interior dock-event branch was rejected after it failed to produce a complete candidate within the existing bounded search; it is not part of the final constructor.

## Visual evidence

The PNGs are rendered from the corresponding before/after SVGs and share a canvas and scale. They are evidence of the result, not a claim that the result is visually sufficient.

- Before SVG: `docs/tasks/evidence/v2_2_2_p1a/xinzhao_p1a_r15_before.svg`
- After SVG: `docs/tasks/evidence/v2_2_2_p1a/xinzhao_p1a_r15_after.svg`
- Before PNG: `docs/tasks/evidence/v2_2_2_p1a/xinzhao_p1a_r15_before.png`
- After PNG: `docs/tasks/evidence/v2_2_2_p1a/xinzhao_p1a_r15_after.png`
- Side-by-side PNG: `docs/tasks/evidence/v2_2_2_p1a/xinzhao_p1a_r15_side_by_side.png`

## Governance

R15 remains a failed delivery attempt; it does not resolve the Owner visual blocker. PR #302 remains Draft. Ready, merge, tag, release, and deployment remain unauthorized.

## R15 closure recovery (forward-only addendum)

The original R15 result above remains `FAIL`; this addendum records the authorized
closure attempt without rewriting that result. The recovery fixes the unbound
`seed` control-flow path and restores the control skeleton's complete lifecycle.
The final real Tool 7 replay again selects the control geometry, so the closure
acceptance remains `FAIL`.

The current closure replay discovers a distinct meaningful full-pass geometry
(`sha256:1c5379589c1da63835062ea8943a14d9af8f24611081395a176e4d5ef60709dc`),
whose changed main-process zones are coating, finished goods, secondary
precooling, and shipping. The existing selection authority still selects
`55589...`; the distinct comparison's first decisive component is
`P2B2_FINAL_TIE_BREAK` (runner-up `e05ce4ee...`). Ranking was not changed.
Therefore the selected geometry and SVG remain identical to the control, and
this does not satisfy R15's delivery goal.

The closure replay examined 17 unique main skeletons: 4 truck-preflight PASS,
13 REJECT, and 3 distinct P2D full-pass skeletons, of which one is a meaningful
new geometry. The selected layout remains hard-valid (12 zones, 12/12 access,
truck route, P2 complete, footprint). Its canonical result hash is
`sha256:2cd24ea6c47d3e389e8aee4b9385b61f1cf4c4ecec3a592cddccf05a653358f9`, and
its SVG hash remains the control's
`sha256:342775cb44d7165a9a64ad7e7f31cd287c04d5a1655bcc8f31ec1c1224f85981`.
Two real Tool 7 replays were deterministic. The P1F/P4 regression remained
hard-valid with zero hard-valid-to-invalid cases.

The `xinzhao_p1a_r15_before/after/side_by_side` visual files were regenerated
from the closure replay. They show the control on both sides, at the same scale;
they are not evidence of a new selected layout. The original R15 result JSON
and the committed history retain the first-attempt `e05...` 1 mm-jitter failure.

R15 closure evidence is recorded in the `xinzhao_p1a_r15_closure_*` files. Frozen
R9/R10/R13/R14 live candidate snapshots are checked as immutable historical
evidence, while current hard-validity and determinism checks are exercised by
the R15 live Tool 7 test. Their checked-in historical evidence files are not
modified.

The updated historical snapshot assertions are: R9's exact 956e/55589
preflight replay; R10's exact nine-variant diagnostic counts; R13's exact
three-skeleton live matrix; R14's exact six-skeleton search-boundary replay;
and the pre-R6 through R5 Xinzhao layout/hash snapshots in
`test_v222_p1a_xinzhao_structural_layout.py`. These assert the checked-in
versioned evidence, not permanent current-runtime candidate counts. Current
hard validation, truck preflight admission, determinism, cross-fixture
validity, and Tool 7 response behavior remain live R15 invariants. The original
R9/R13/R14 evidence files and numbers remain unchanged.
