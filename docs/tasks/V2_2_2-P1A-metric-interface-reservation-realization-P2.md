# V2.2.2 P1A — metric interface reservation realization P2

## Scope and authorization

Start: `4576614282a362e86b9cd1f7bf48eb296eac1674`, existing branch
`codex/v2.2.2-p1a-structural-hard-interface-reservation-p0`, Draft PR #307.
PR #306 remains frozen diagnostic evidence; no implementation or coordinates
were copied. The previous Git quarantine is outside this task and untouched.

P0 makes every authority MUST interface visible. P1 reserves a topological
attachment slot. P2 realizes **pairwise site/dimension hard-interface capacity**.
P2 does not prove simultaneous compatibility with the other ten rooms, actual
structural host footprints, whole-building feasibility, Access, Truck or P2D.

## Implementation

- Independent application accepts only canonical zone plan, existing P1
  dimension handoff and `ValidatedSiteGeometryV1`. It binds authority and
  server-rebuilds/replays structural plans/handoffs; caller compositions and
  metric artifacts are not authority inputs.
- Separate immutable metric artifact contains provenance-bound pair slots,
  source reservation identities, counts, digests and gate. P0/P1 serialized
  contracts, coordinate-free semantics and reservation classification stay intact.
- Site source is `site.effective_buildable_boundary`; obstacles are the complete
  `obstacles.hard_obstacles`, including retained existing buildings. Conditional
  removal footprints are not promoted. No raw polygon or bbox replaces authority.
- Pure shape derivation was mechanically extracted into `authority_shapes.py`.
  Exact placement retains the old aliases and identical helper AST. All fixed
  rotations and flexible canonical footprints remain available; flexible shape
  approval still uses `validate_flexible_candidate`.
- Each pair is checked with existing inside-polygon, closed-obstacle,
  positive-shared-edge and non-overlap predicates. No minimum shared edge or
  portal width is invented; corner touch is insufficient.

## Declared finite domain

Policy: `symmetric-boundary-obstacle-corner-and-shared-face-events@1.0.0`.
For each canonical authority footprint, anchor all four corners at every
effective-boundary vertex and at every hard-obstacle vertex with the four
diagonal ±1 mm offsets. Place the other endpoint at each of four faces, with
tangential start, end and integer-center alignment. Union A-first and B-first,
canonically ordered by role and footprint, and remove exact duplicate bounds.

This explicitly declared event domain is **not** the continuous feasible set.
An exhaustive empty result means only no capacity in this finite domain.
The deterministic safety cap is 10,000,000 unique pair evaluations per edge;
it is independent of the unchanged 60,000-node placement budget. Cap exhaustion
or an empty authority shape domain produces UNKNOWN, never negative proof.
Valid slots are counted and digested in deterministic canonical traversal order;
only up to four orientation representatives are retained. Representatives are
not the full domain and must not be treated as exclusive alternatives.

All families use the same site and dimensions, and P1 hosts have no metric
footprints. Accordingly the pair domain is evaluated once per edge within each
invocation and rebound to each family reservation. No cross-run evidence seed
or persisted slot cache is loaded. Two complete application invocations establish
determinism, not reuse of a previously captured result.

Pair events are streamed as integer bounds before materializing rectangles.
Within each edge evaluation a bounded cache keys physical results by world
bounds (orientation does not change that physical footprint). A necessary bbox
check rejects only provable site violations; it never establishes positive
site validity. Every positive footprint still uses the exact polygon and hard
obstacle predicates. Witnesses retain original authoritative dimensions and
rotation. Independent small-domain enumeration checks counts and no exclusions.

## Site-authority parity audit

Existing exact placement currently reads `obstacles.no_build_zones`, rather than
the complete `hard_obstacles` set. Canonical Xinzhao has no retained buildings,
but the semantic gap exists for other validated inputs. P2 retains the stronger
existing site authority and does not remediate search behavior in this phase.
Future P3 consumption is blocked until this parity gap is separately resolved.

## Validation and evidence

Evidence:
`evidence/v2_2_2_p1a_metric_interface_reservation_p2/xinzhao_metric_interface_reservation_realization.json`.
The evidence blob is bound to its containing Git commit and exact-head CI;
its own containing commit SHA cannot be embedded self-referentially.

Runner: `backend/tests/evaluation/v222_p1a_metric_reservation_evidence.py`.
It runs the production application twice, captures all 42 realization summaries,
and compares P0/P1 plan/handoff hashes with immutable P1 evidence. No full
production layout replay, Access, Truck or P2D is executed for P2 evidence.
Existing placement tests run only to verify behavior parity after extraction.

Focused tests cover fixed/flexible shapes, real validated retained/conditional
building inputs, boundary and obstacle parity, exact shared edges, overlap,
symmetric/exhaustive finite domains, incomplete UNKNOWN, authority edge coverage,
provenance replay rejection and coordinate-free P0/P1 regressions. The initial
local test run had two missing-import failures; imports were corrected before
the final regression run. A fresh mypy cache stalled locally; the established
external cache completed successfully without source/dependency workarounds.
An initial evidence attempt was deliberately interrupted after observing costly
duplicate rectangle construction/physical checks. The integer-bounds/cache
optimization preserves the declared domain, ordering, safety cap and predicates;
the formal evidence uses two fresh invocations on the final implementation.

Local validation: final combined related/architecture regression run passed
907 tests, with 16 skipped; the focused/boundary selection separately passed
18 cases. Ruff/format and mypy (400 source files) passed. Required exact-head SQLite and
PostgreSQL CI results will be published against the containing commit in PR #307.

## Canonical result

Both final-code application invocations completed with 6 complete composition
domains, 42 nonempty reservations, 6 READY gates, zero negative gates and zero
UNKNOWN gates. Full serialized results are identical:
`sha256:412a5ec8f51a84ceebddd4b663e89fe50a76d7cc8997c239b02dcb4c5dfc6677`.
All P1 plan/handoff hashes remain identical to the immutable P1 evidence.
The optimized evaluation counts and valid-slot counts exactly match the earlier
unoptimized full-domain diagnostic; no domain or budget was narrowed.

| Existing HARD edge | Unique evaluated pairs | Valid pairwise slots |
| --- | ---: | ---: |
| Raw ↔ Primary Precooling | 18,300 | 1,407 |
| Primary Precooling ↔ Sorting | 18,304 | 148 |
| Sorting ↔ Secondary Precooling | 18,304 | 180 |
| Secondary Precooling ↔ Coating | 4,726,212 | 244,436 |
| Coating ↔ Finished Goods | 4,743,006 | 67,240 |
| Finished Goods ↔ Shipping | 18,304 | 698 |
| Office ↔ Shipping | 5,251,868 | 328,373 |

Each invocation evaluated 14,794,298 unique pairs across the seven independent
edge domains. Every individual edge stayed below its unchanged 10,000,000 cap.
All four attachment orientations occur for every edge. Counts are the same for
all six compositions because they bind the same pairwise site/dimension domains
to different topological provenance, not metric host polygons.

Office has 1,188 authority shape variants, deduplicated to 594 equivalent world
footprints; Shipping has two. Office/Shipping slot digest:
`sha256:490019d5738b18d43d676c62dc030c82ee21cf81270822e82a09c0882df92cdc`.
The logical sum over six compositions is 1,970,238 slots, not that many unique
cross-family geometries. Canonical site has three NO_BUILD hard obstacles and
zero retained buildings; actual retained/conditional validated-site fixtures
separately prove retained obstacles are included and conditional removals are not.

## Stop

P3 is not authorized. No DFS consumes these slots in P2. No search scheduler,
budget, family, engineering authority, candidate selector or Tool 7 behavior
changes. Metric gate success is not project-layout validation or P2D completion.
