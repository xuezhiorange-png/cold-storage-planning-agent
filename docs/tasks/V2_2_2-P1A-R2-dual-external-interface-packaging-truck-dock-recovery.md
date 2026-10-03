# R2 dual external-interface packaging / truck dock recovery

Task ID: `V2_2_2_P1A_ENVELOPE_GRID_BAND_ZONE_GENERATOR_R2`\
Mode: `R2_DUAL_EXTERNAL_INTERFACE_PACKAGING_TRUCK_DOCK_RECOVERY`\
PR: #302 (Draft)\
Baseline: `73d7c6c151c6b1f1351a02fd8b615343bc5c107c`

## Outcome

`RESULT=FAIL`. The structured path now constructs shipping geometry from the
existing Truck entrance, dock template, shipping dimensions, and shared
loading-face authority. Dock-capable main skeletons pass the unchanged Truck
preflight, and two corresponding twelve-zone site candidates reach P2D. Neither
is a P2D full pass: each has 8/12 access requirements passing, with four
requirements blocked by `ROUTE_SEARCH_EXHAUSTED`. No Truck, P2D, access,
dimension, or placement-budget authority was changed.

The authoritative Tool 7 result remains valid through the general fallback:
12/12 access, Truck PASS, P2 complete, 12 zones, and a building footprint.
The structured-path objective is therefore not complete, despite reaching the
Truck and twelve-zone gates.

## Construction and evidence

- Packaging-first construction is preserved; 433 legal packaging anchors are
  represented by 27 deterministic construction representatives.
- Dual packaging/shipping interface construction reports 27 anchor pairs, 4
  necessary-condition survivors, 20 distinct shipping rectangles (12 at 0°,
  8 at 90°), and 6 authoritative dock points.
- Three dock-capable main skeletons receive authoritative Truck-preflight PASS
  and construction witnesses. The final Truck revalidation mismatch count is
  computed against actual structured P2D candidate traces.
- Two Truck-qualified twelve-zone candidates enter P2D:
  `sha256:62bc404539c5bcd1a13fb60f79b72935fe9bea64ce11e13cfa3a6aa808ddd095`
  and
  `sha256:d87bc7a5c3a002d0e6ba1d751736efa3ffa1959c2628cc2bc87f9a10b8ece16d`.
- Both candidates are Truck-valid but have the same four blocked access
  requirements: `changing_room -> sorting_packaging_room`,
  `main_entrance -> changing_room`, `sorting_packaging_room -> frozen_fruit_room`,
  and `sorting_packaging_room -> secondary_fruit_buffer`. Each returns
  `ROUTE_SEARCH_EXHAUSTED`; this task does not change route budget or P2D.
- Two unmocked Tool 7 replays are compared for selected layout, canonical hash,
  SVG bytes, work-queue trace, and P2D route trace.

Machine-generated evidence and the rendered anchor / candidate views are in
[`docs/tasks/evidence/v2_2_2_p1a/`](evidence/v2_2_2_p1a/), led by
[`xinzhao_p1a_r2_dual_external_interface_truck_dock.json`](evidence/v2_2_2_p1a/xinzhao_p1a_r2_dual_external_interface_truck_dock.json).

## Verification

- Focused R2, R9, R13, P2D, Truck, P2C, and architecture tests: 37 passed.
- Full architecture suite plus targeted placement/access suites: 933 passed,
  16 skipped.
- R9/R12/R13/R14 historical evidence checks: 13 passed.
- P1F cross-fixture evaluation: 3 passed; previously valid fixtures remain
  valid.
- R15 closure evaluation: failed only at the preserved distinct-full-pass
  assertion (`observed=1`, `required>=2`); the selected control itself remains
  fully valid.
- Ruff, format check, mypy, and `git diff --check`: passed.
- Exact-head CI runs follow the forward-only push; their result is reported
  separately from the local task result.

## Boundaries and governance

`PLACEMENT_NODE_BUDGET=120`; `TRUCK_NODE_BUDGET=5000`. The production Truck
validator, templates, loading-face authority, packaging preflight, fallback,
selection authority, and public Tool 7 contract remain unchanged. PR #302 stays
Draft; Ready, merge, tag, release, and deployment are not authorized.
