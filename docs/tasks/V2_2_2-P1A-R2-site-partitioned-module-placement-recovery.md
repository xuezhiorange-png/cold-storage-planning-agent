# V2.2.2 P1A R2: Site-Partitioned Module Placement Recovery

## Outcome

`RESULT=FAIL` for the R2 site-partitioned module-placement recovery. The implementation now distinguishes local, rigid module geometry from site-aware module placement and produces exact orthogonal site-bay evidence. On the canonical Xinzhao input it found two site-valid seven-zone main-process assemblies, but both failed the existing packaging-material-storage slot preflight. No structured 12-zone candidate reached truck validation or P2D, so the result does not meet the requested delivery gate.

This is a result failure, not a hard-validity regression: the independent legacy compatibility phase remained available and the real Tool 7 replay returned its prior hard-valid control layout.

## Implemented boundary

- `ROOM → MODULE → SITE BAY → BUILDING` is represented in the structured path.
- Module-internal zone rectangles remain frozen during site assembly; no individual room is moved after module synthesis.
- Site events are used only for module origins/orientations and exact site/obstacle predicates.
- Orthogonal site geometry is decomposed deterministically into exact maximal free rectangles and connectivity partition regions, with their shared interfaces and site/entrance contacts recorded.
- No `heapq` dependency was added to placement-domain code.
- Existing zone dimensions, MUST graph, packaging-slot preflight, truck authority, P2D authority, footprint authority, and the 120-node placement budget were not changed.

## Canonical Xinzhao evidence

Evidence was generated from two unmocked Tool 7 executions using `backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json`; process-local observer instrumentation did not alter the public payload or production behavior.

| Measure | Result |
|---|---:|
| Exact orthogonal bay records | 13 (6 maximal-placement regions and 7 connectivity partition regions) |
| Bay adjacency relationships | 15 |
| RAW module variants | 16 |
| PROCESS_CORE module variants | 2 |
| FINISHED module variants | 24 |
| SUPPORT module variants | 24 |
| PERSONNEL module variants | 4 |
| Site-valid main-process assemblies | 2, both `LINEAR_3_BAND` |
| Site-valid main assemblies by family | LINEAR 2; CENTRAL 0; SPINE 0 |
| Packaging slot preflight passes | 0 |
| Site-valid structured 12-zone assemblies | 0 |
| Structured truck passes | 0 |
| Structured P2D full passes | 0 |
| Structured full-pass distinct skeletons | 0 |
| Family geometry collapse count | 0 |
| Micro-jitter or family-label-only candidates | 0 |

The two main-process geometry hashes were:

- `sha256:cb97b471df0b24e708dce1f853449b526e40a671bf3c9918b7f1befdf0bfa72d`
- `sha256:8905d1a45ff135828c641b1191868e1156e712befbd4fe0770af8571e8ce398f`

Both were rejected at `PACKAGING_SLOT_PREFLIGHT_REJECTED`; neither was admitted to tail completion. This recovery therefore establishes a nonzero S1 site-assembly result, but not S2, truck, or P2D success. The requested three-family coverage and five visually distinct P2D full-pass layouts were not reached.

## Compatibility, budget, and determinism

The observed Tool 7 control remained hard-valid: 12 zones, 12/12 access requirements, truck route validated, P2 complete. Its canonical result hash was `sha256:c8f4011cd0d565e6ecd0ce636ee50586d0d1d075e51eff0d845c156f31ca9d19`; its SVG hash was `sha256:007f8066b55a3bdcf2583e0e4d9c2f325e1c2c6cee4bc9aa8fb9fd4a57c109d2`.

The production placement budget remained 120 and was fully accounted: 120 visits, zero remaining; 28 structured-phase nodes and 92 general-fallback nodes. Truck node budget remained 5000. Repeated Tool 7 execution produced identical selected layout, canonical result hash, SVG bytes, and module/work-queue trace.

The protected `site_geometry.py` scope was not modified. The placement-domain source contains no `heapq` import.

## Evidence and validation

Machine-readable runtime evidence and rendered site-assembly views are stored at:

- `docs/tasks/evidence/v2_2_2_p1a/xinzhao_p1a_r2_site_partitioned_module_placement.json`
- `docs/tasks/evidence/v2_2_2_p1a/xinzhao_module_site_main_candidates.png` and `.svg`
- `docs/tasks/evidence/v2_2_2_p1a/xinzhao_module_site_12zone_candidates.png` and `.svg`
- `docs/tasks/evidence/v2_2_2_p1a/xinzhao_module_p2d_fullpass_gallery.png` and `.svg`

The 12-zone and P2D views explicitly show that no structured candidate was produced; they are not presented as candidate layouts.

Evaluation helper: `backend/tests/evaluation/r2_site_partitioned_module_placement.py` (test-process-only instrumentation).

Local validation on this revision:

- R2 module/bay unit tests: 42 passed.
- R9/R11/R13/R15, P1F, P2C, and P2D targeted unit regressions: 99 passed.
- Full architecture suite: 777 passed, 16 skipped.
- Full backend Ruff and format checks: passed (905 files already formatted).
- Full backend source Mypy: passed (396 source files).
- `git diff --check`: passed; protected `site_geometry.py` comparison: unchanged.
- Two real, unmocked Tool 7 replays: same selected control, result hash, SVG bytes, and structured trace.

Exact-head PR/push CI is recorded in the PR and final task receipt. Historical R2/R9/R13/R14/R15 evidence was not rewritten. PR #302 remains Draft; no readiness, merge, tag, release, or deployment action is authorized.
