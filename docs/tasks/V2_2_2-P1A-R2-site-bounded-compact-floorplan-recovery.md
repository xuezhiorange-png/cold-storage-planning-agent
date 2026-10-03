# V2.2.2 P1A R2 Site-Bounded Compact Floorplan Recovery

**Task:** `V2_2_2_P1A_ENVELOPE_GRID_BAND_ZONE_GENERATOR_R2`

**Mode:** `R2_SITE_BOUNDED_COMPACT_FLOORPLAN_RECOVERY`

**Baseline:** `ed2b13a53dcc763c60da5f10daeb8109067275e1`

**Result:** `FAIL`

## Outcome

The local constructor now uses the authoritative site outer extents as a
necessary bounding-box prune, without reading site event coordinates during
local synthesis. It retains compact, deterministic 2D MUST-adjacency
embeddings and packs support/personnel zones into complete 12-zone local
compositions. This is local geometry evidence only; the local frame is not an
occupied building footprint.

Two unmocked Xinzhao Tool 7 replays produced the same selected fallback layout,
canonical result hash, SVG bytes, and work-queue trace. The fallback remains
hard-valid (`12/12` access, truck route valid, P2 complete, 12 zones). However,
no structured composition passed rigid placement against the actual site and
no-build geometry, so no structured candidate reached truck validation or
P2D. The task therefore fails its site-placement and delivery gates.

## Local construction and placement evidence

Xinzhao site outer extent is `75.460 m × 55.000 m`. The latest replay recorded:

| Family | Distinct 7-zone local states | Best 7-zone bbox | Complete 12-zone local states | Best 12-zone bbox | Extent-feasible 12-zone states |
| --- | ---: | --- | ---: | --- | ---: |
| `LINEAR_3_BAND` | 36 | `48.179 × 42.250 m` | 233 | `52.971 × 55.600 m` | 233 |
| `CENTRAL_PROCESS_WITH_SIDE_BANKS` | 16 | `50.614 × 55.600 m` | 120 | `52.971 × 55.600 m` | 120 |
| `LONGITUDINAL_PROCESS_SPINE` | 16 | `55.560 × 50.614 m` | 128 | `55.560 × 50.614 m` | 128 |

In total, `68` retained 7-zone local states and `481` complete 12-zone states
passed the necessary outer-extent test, including whole-building rotation.
The actual rigid site-placement stage returned `0` placements across the
recorded structured construction attempts, with first failure
`SITE_PLACEMENT / NO_EXACT_RIGID_TRANSLATION_FITS_SITE_AND_OBSTACLES`. This is
not a proof that every possible local embedding is globally infeasible; it
states that the deterministic retained compositions and exact placement
enumeration did not produce a witness.

The production placement budget remains `120`. The replay used `120/120`
global placement nodes (`12` structured-phase nodes, `108` compatibility
fallback nodes, `7` tail nodes; preflight compute nodes `0`). The existing
fallback phase was not modified.

## Acceptance status

- Local compact 2D synthesis: implemented and deterministic.
- Site-extent-feasible complete local compositions: `481`.
- Structured rigid site placements: `0`.
- Structured truck passes / structured P2D full passes: `0 / 0`.
- Final Tool 7 fallback: hard-valid and deterministic.
- Distinct structured full-pass skeletons: `0`; the historical R15 distinct
  full-pass assertion remains unmet and was not weakened.
- Final result: `FAIL`.

## Evidence and checks

Machine-generated replay evidence is in
`docs/tasks/evidence/v2_2_2_p1a/xinzhao_p1a_r2_site_bounded_compact_floorplan.json`.
The family-local SVG/PNG files show actual zone rectangles and a dashed
site-size reference; blank space is not labeled as a zone or corridor. The
site candidate gallery records that no structured P2D full-pass candidate was
observed.

The focused local-composition, band-packing, P1F context/loading-face, and P4
Tool 7 regression selection passed (`54 passed` in `612.82s`). The generator
architecture tests passed (`7 passed`); Ruff, format, mypy, and
`git diff --check` passed. Exact-head PR/push CI is a separate post-push gate
and is not inferred from these local checks. `site_geometry.py`,
`building_footprint.py`, fallback behavior, truck/P2D authority, selection
authority, and the 120-node budget are unchanged.

PR #302 remains Draft. Owner visual review is pending; no readiness, merge,
release, or deployment action is authorized.
