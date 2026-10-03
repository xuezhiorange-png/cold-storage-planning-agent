# V2.2.2 P1A R2 Direct Synthesis Recovery

**Task:** `V2_2_2_P1A_ENVELOPE_GRID_BAND_ZONE_GENERATOR_R2`
**Mode:** `R2_DIRECT_SYNTHESIS_RECOVERY`
**Base:** `58ed905f80edd5342b594bf39ab85d555cb685cc`
**Result:** `FAIL`

## Outcome

The recovery replaces the structured phase's room-level event-axis DFS with
finite, deterministic envelope/grid/band construction attempts. The direct
phase now enumerates the three layout families independently, synthesizes
main-process and support/personnel zones from band edges, runs the existing
truck preflight and envelope-closure predicates, and yields only complete
12-zone geometries. It does not use local event axes as its structured search
space.

The Xinzhao direct-synthesis probe did **not** produce a complete candidate:

| Measure | Result |
| --- | ---: |
| Layout families attempted | 3 |
| Direct structural construction nodes visited | 3 / 120 (one first-round attempt per family) |
| Complete 12-zone direct candidates | 0 |
| Direct truck-pass candidates | 0 |
| Direct P2D full-pass candidates | 0 |
| Remaining global nodes made available to legacy fallback | 117 |

The pre-recovery R2 trace supplied for this recovery recorded these rejection
counts (historical baseline, not rewritten as recovery measurements):

| Rejection | Count |
| --- | ---: |
| `PROGRAM_BUILDING_ENVELOPE_NO_EXACT_SITE_SLOT` | 7 |
| `SITE_OUTSIDE` | 469 |
| `NO_BUILD_COLLISION` | 686 |
| `ENVELOPE_OR_BAND_REJECT` | 56 |
| `OFFSET_TRANSITION_UNAVAILABLE` | 27 |
| `SKELETON_TOPOLOGY_INVALID` | 16 |
| `ZONE_OVERLAP` | 15 |

Additional direct synthesis failures were `SIMPLE_L_ENVELOPE_UNAVAILABLE`,
`FULL_PROGRAM_BUILDING_ENVELOPE_UNAVAILABLE`, and exact finished/coating band
slot failures. These counts are search diagnostics, not relaxed or newly
introduced engineering rules. The direct construction phase gives each of the
three layout families one initial construction attempt; these three attempts
still produce no complete building.

The existing 120-node placement budget and all truck/P2D/zone authorities are
unchanged. After the three direct family attempts, the selector schedules the
legacy compatibility fallback with the remaining 117 nodes. In the real P1F
selector replay, the shared fallback used all 117 nodes across the three
topology lanes, produced 30 P2D candidates and zero full-pass candidates; the
selector ended with `VALIDATED_LAYOUT_SEARCH_EXHAUSTED` and an 11/12 access
result. A process-local control experiment that suppressed structured work
and gave fallback the full 120 nodes also failed: 33 candidates, zero
full-pass, 120/120 nodes, and three active truncated work items. This shows
that the three-node direct phase alone does not explain or repair the P1F
regression. Historical R1/R2 candidate evidence and images were not rewritten.

## Verification

The focused structured-building, family-quantum, selector-scheduling, and
architecture tests passed (31 tests). Backend Mypy passed for 395 source files;
Ruff, format check, and `git diff --check` passed. The P1F regression remains
unresolved: its four selector fixtures fail with
`VALIDATED_LAYOUT_SEARCH_EXHAUSTED`. The process-local full-fallback control
experiment also failed as recorded above. Local checks therefore do not
constitute recovery acceptance. Any exact-head CI result must be reported
separately and cannot override the failed layout and P1F acceptance criteria.

No new recovery candidate image is claimed: direct synthesis produced zero
complete Xinzhao candidates. The checked-in R1 gallery remains historical
evidence and is retained unchanged; it is not presented as an R2 recovery
gallery.

## Acceptance

`RESULT=FAIL`: zero complete 12-zone direct-synthesis candidates were produced,
so the minimum of five visually distinct hard-valid full-pass candidates
across at least three layout families was not produced; the required P1F
hard-valid scenarios also remain regressed. No recovery gallery is claimed.
The checked-in R1 gallery remains historical and unchanged. The original R2
failure remains historical fact; this document records only the forward
recovery attempt.
