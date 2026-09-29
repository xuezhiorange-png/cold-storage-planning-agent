# V2.2.2 P1A — Envelope/Grid/Band/Zone Generator R1

## Outcome

`RESULT=FAIL` against the explicit R1 acceptance gate. The generator now
constructs a versioned building-envelope/grid/band plan before structured zone
placement, and the production candidate path applies envelope and band
admission predicates. However, the canonical, unmocked Xinzhao Tool 7 replay
produced only two visually distinct full-pass main-process skeletons, both in
the same band configuration. The requirement is at least five candidates and
at least three major band configurations. No Owner acceptance is claimed.

The two real candidates and the same-scale gallery are retained under
[`evidence/v2_2_2_p1a`](evidence/v2_2_2_p1a/).

## Canonical Tool 7 evidence

Fixture: `backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json`

| Candidate | Skeleton | Layout family | Changed main zones vs control | P2D | Access | Truck | Outline |
| --- | --- | --- | --- | --- | ---: | --- | --- |
| 01 | `55589c20f3c3…` | `LINEAR_3_BAND` | none (control) | full pass | 12/12 | pass | `STAIR_STEP` |
| 02 | `f5f71519639f…` | `LINEAR_3_BAND` | `coating_room`, `finished_goods_room`, `shipping_channel` | full pass | 12/12 | pass | `STAIR_STEP` |

Both candidates have the same geometry-derived main-group relation signature.
The two-run replay was deterministic for selected layout, canonical result
hash, SVG bytes, and SVG hash. The selected result remains hard-valid with 12
zones and a building footprint.

Search accounting: 120/120 placement nodes visited; 11 distinct main skeletons
examined; 9 truck-preflight rejects; 2 truck-preflight passes; 2 distinct P2D
full-pass skeletons. The three attempted band plans were
`LINEAR_3_BAND`, `CENTRAL_PROCESS_WITH_SIDE_BANKS`, and
`LONGITUDINAL_PROCESS_SPINE`. Among full-pass candidates, only
`LINEAR_3_BAND` appeared. Their major band configuration count is 1 and their
major-band configuration changes count is 0. No 1–10 mm-only variant was
counted.

The constructed primary grid reports 8 X axes and 13 Y axes. The search-node
accounting attributed 104 nodes to rectangle-envelope work and 16 nodes whose
work item did not carry an envelope-family label. The canonical selector
initialized rectangle envelopes; the simple-L constructor was not exercised
for this input.

The generated side-by-side gallery has a common canvas and scale, is uncropped,
and shows the site boundary. It also confirms the remaining visual issue:
both layouts still read as stair-stepped room compositions rather than a
regular, coherent building mass with visibly distinct band organizations.

## Scope and local validation

The change adds `BuildingEnvelopeV1`, `PrimaryGridV1`, `FunctionalBandV1`,
`BandZonePlacementV1`, and `StructuredBuildingSkeletonV1`. The plan is created
before main-process search; exact site, obstacle, room-dimension, adjacency,
truck, access, and P2D authorities remain the hard validators. The 120-node
placement budget is unchanged. No Golden coordinates, numeric visual gates,
weighted score, Tool 7 schema change, database change, or frontend change was
introduced.

The support/personnel bands currently span the full envelope and therefore do
not yet enforce subordinate/peripheral placement. That limitation and the
unexercised simple-L path are recorded in ADR-048; they must not be represented
as successful fulfillment of the visual requirements.

Local results:

- New envelope/grid/band, R9/R11/R13/R15, P2C/P2D, and evidence tests:
  `57 passed`.
- P2 validated-selection and Tool 7 contract tests: `32 passed`.
- Full architecture suite: `773 passed, 16 skipped`.
- Existing P1F cross-fixture full-chain evaluation: `3 passed`.
- SQLite integration suite: `49 passed`.
- Ruff and format checks: passed; `mypy src`: 395 source files passed;
  `git diff --check`: passed.
- Two real, unmocked Xinzhao Tool 7 runs were deterministic. No local
  PostgreSQL service/client was available; exact-head PostgreSQL CI remains the
  remote verification gate.

The exact-head PR/push CI is recorded in the PR body after the forward-only
commit. `OWNER_VISUAL_REVIEW=PENDING`,
`OWNER_XINZHAO_P1A_VISUAL_BLOCKER_RESOLVED=false`, and the PR remains Draft.
