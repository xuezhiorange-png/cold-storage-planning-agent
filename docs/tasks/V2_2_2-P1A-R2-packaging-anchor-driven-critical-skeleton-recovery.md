# V2.2.2 P1A R2: Packaging-Anchor-Driven Critical-Skeleton Recovery

**Task:** `V2_2_2_P1A_ENVELOPE_GRID_BAND_ZONE_GENERATOR_R2`
**Mode:** `R2_PACKAGING_ANCHOR_DRIVEN_CRITICAL_SKELETON_RECOVERY`
**Baseline:** `2c2463a2819f338698ce14bad3f73865da1d945f`
**Result:** `FAIL`

## Outcome

Structured site construction now begins with exact packaging anchors. For each
construction-representative anchor it derives sorting roots from the package's
long-edge / sorting short-edge alignment events, then attaches rigid raw and
finished modules. The package-to-sorting relationship remains a construction
ordering witness, not a MUST shared-edge rule or a P2D access result. The
unchanged formal packaging-slot preflight remains in the candidate admission
path.

The required core pair and packaging-reserved main stages were reached, and
two distinct structured 12-zone site assemblies were built. Neither passed the
authoritative truck maneuver preflight, so structured tail/P2D completion and
the required structured P2D full-pass were not reached. The task therefore
remains `FAIL`; this change does not claim a new complete layout.

## Canonical Xinzhao evidence

Two unmocked Tool 7 replays used
`backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json`.

| Measure | Result |
| --- | ---: |
| Exact legal packaging anchors | 433 |
| Anchors by bay | BAY-0001: 216; BAY-0002: 201; BAY-0003: 16 |
| Packaging construction representatives / anchor groups | 27 / 27 |
| Anchor groups covering sorting rotation 0° | 27 (attempt or exact impossibility proof) |
| Anchor groups covering sorting rotation 90° | 27 (attempt or exact impossibility proof) |
| Packaging + sorting core-pair geometries | 34 |
| Distinct RAW module signatures / representatives | 16 / 16 |
| Distinct FINISHED module signatures / representatives | 24 / 24 |
| Source-pair attempt rows: Linear / Central / Spine | 412 / 792 / 540 |
| Distinct source input geometries per family | 33 / 33 / 33 |
| Site-valid critical geometries: Linear / Central / Spine | 2 / 0 / 2 |
| Packaging-reserved main assemblies | 3 |
| Complete structured 8-zone critical assemblies | 3 |
| Site-valid structured 12-zone assemblies | 2 |
| Structured truck passes / structured P2D full passes | 0 / 0 |
| Early/formal packaging-preflight mismatches | 0 |
| Placement budget / visits | 120 / 120 |
| Truck node budget | 5000 (unchanged) |

The structured truck rejects were exact `TRUCK_MANEUVER_SEARCH_EXHAUSTED`
results with the truck node budget not exhausted. The existing selected
control remains valid: skeleton `55589c20…`, 12 zones, access 12/12, truck
route validated, and P2 complete. The structured P2D full-pass count is zero;
no structured layout is presented as a full-pass candidate.

The 120-node global placement budget and 5000-node truck budget are unchanged.
The 27 construction anchors retain both sorting orientations in their
per-anchor evidence; orientations without compatible facing edges have an
explicit geometric impossibility proof rather than being silently omitted.

## Determinism and compatibility

Both Tool 7 replays selected the same layout and produced the same canonical
result hash, SVG bytes, and work/module trace. The general fallback and legacy
access requirement objects remain unchanged; construction-only profile widths
are passed only to the structured construction-ordering phase. P1F/P4/R15
targeted regression tests passed, including the frozen P1F SVG hash test.

## Validation

- R2/R9 helper and architecture tests: 66 passed.
- Full architecture suite: 778 passed, 16 skipped.
- R15 truck construction, P1F, and P4/Tool 7 targeted regressions: 26 passed.
- P2C/P2D unit tests: 25 passed.
- Ruff, format, mypy, and `git diff --check`: passed.
- Protected `site_geometry.py` diff: empty.

## Evidence and images

Machine-readable results and generated drawings are under
`docs/tasks/evidence/v2_2_2_p1a/`:

- `xinzhao_p1a_r2_packaging_anchor_driven_critical_skeleton.json`
- `xinzhao_packaging_anchor_candidates.png`
- `xinzhao_packaging_sorting_core_pairs.png`
- `xinzhao_critical_8zone_candidates.png`
- `xinzhao_structured_12zone_candidates.png`
- `xinzhao_structured_p2d_fullpass_gallery.png` (no structured full-pass
  candidate)

PR #302 remains Draft. This recovery does not authorize Ready, merge, tag,
release, or deployment.
