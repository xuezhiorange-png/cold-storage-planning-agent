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
