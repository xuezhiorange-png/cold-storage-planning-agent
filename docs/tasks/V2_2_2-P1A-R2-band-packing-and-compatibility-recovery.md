# V2.2.2 P1A R2 Band-Packing and Compatibility Recovery

**Task:** `V2_2_2_P1A_ENVELOPE_GRID_BAND_ZONE_GENERATOR_R2`
**Mode:** `R2_BAND_PACKING_AND_COMPATIBILITY_RECOVERY`
**Base:** `f2296f0c6b9b706351dd645eaa48e06f13de5d2d`
**Result:** `FAIL` (the earlier R2 failure remains historical and unchanged)

## Outcome

This forward-only recovery separates the structured construction phase from a
real `GENERAL_FALLBACK_PHASE`, removes non-authoritative shared-edge gates,
restores the protected `site_geometry.py` baseline, and adds finite joint band
packing for the three authorized layout families. The structured phase no
longer delegates its zone placement to the legacy event-axis DFS or a
room-by-room greedy chain.

The real, unmocked Xinzhao Tool 7 replay selected a valid compatibility
fallback layout. It passed project validation, P2 completeness, all 12 access
requirements, truck validation, and building-footprint presence. This confirms
compatibility recovery, not structured-generator acceptance.

## Xinzhao structured construction findings

The exact replay evidence is recorded in
[`xinzhao_p1a_r2_recovery_runtime.json`](evidence/v2_2_2_p1a/xinzhao_p1a_r2_recovery_runtime.json).
Across its finite family attempts, no complete 12-zone structured geometry
was emitted:

| Layout family | Attempts | Complete structured layouts | First observed failure |
| --- | ---: | ---: | --- |
| `LINEAR_3_BAND` | 2 | 0 | `MAIN_BAND_PACKING`: `BAND_PACKING_UNAVAILABLE:FINISHED_SIDE_BAND` |
| `CENTRAL_PROCESS_WITH_SIDE_BANKS` | 2 | 0 | `PLAN`: `SIMPLE_L_ENVELOPE_UNAVAILABLE` |
| `LONGITUDINAL_PROCESS_SPINE` | 2 | 0 | `PLAN`: `SIMPLE_L_ENVELOPE_UNAVAILABLE` |

Therefore Stage A, Stage B, Stage C, and Stage D are all **not met**. In
particular, there are zero structured full-pass candidates; compatibility
fallback results are not counted as structured or visually regular
candidates.

## Compatibility and budget evidence

The placement budget remained 120. The replay consumed 2 nodes in the
structured phase and 118 in general fallback, for 120 total. The search
accounting reconciles exactly and leaves no stranded global nodes. The
selected compatibility result has canonical hash
`sha256:9be8014423738b89d3a5c47a4b076ef2b35d51363dec62b90a7437a79ad11c72`
and SVG hash
`sha256:007f8066b55a3bdcf2583e0e4d9c2f325e1c2c6cee4bc9aa8fb9fd4a57c109d2`.

The replay records two fallback P2D full-pass tail variants, both over the
same control skeleton `sha256:55589c20f3c3336c1c92a8c1ffc8b14a813ac558bac78871d4e6b1fa8ee9b953`;
they are fallback evidence, not two distinct or structured family candidates.
The generated
[`general-fallback gallery`](evidence/v2_2_2_p1a/xinzhao_general_fallback_r2_recovery_gallery.png)
labels both as fallback, never as structured candidate acceptance.

The R1-compatible P1F cross-fixture replay passed. The targeted P1F inset and
P4 Tool 7/MCP regressions passed 22 tests. R9/R11/R13/R15, P2C/P2D and the
related admission/preflight regressions passed 64 tests. The focused R2
structured/architecture set passed 47 tests. Mypy, Ruff, formatting, and diff
checks passed locally. PostgreSQL and the new exact-head GitHub CI remain
separate gates and are not claimed here.

The R2 addition was removed from `site_geometry.py` and moved to the
layout-specific `building_footprint.py` module. The protected-file comparison
against `fa884b8ddf2b93f34beb2335d646fe6b157a8f5f` is required to pass at the
committed head.

## Acceptance

`RESULT=FAIL`. Compatibility is restored for the exercised P1F/P4 paths and
the canonical Xinzhao fallback is hard-valid, but the direct structured
generator emitted zero complete 12-zone candidates. It consequently does
not meet the required five full-pass candidates across at least three layout
families. No R3 task is started by this recovery.
