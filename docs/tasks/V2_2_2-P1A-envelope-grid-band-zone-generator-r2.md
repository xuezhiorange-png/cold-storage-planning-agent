# V2.2.2 P1A — Envelope/Grid/Band/Zone Generator R2

## Outcome

`RESULT=FAIL`. This is the direct R1 generator repair, not an audit-only task.
The implementation now derives planned envelopes from the full authoritative
program, constrains support/personnel bands to actual exterior envelope
components, tests exact union coverage for L-shaped envelopes, and attempts
the three layout families on both orthogonal process axes. However, two real,
unmocked Tool 7 replays exhausted the unchanged 120-node placement budget
without constructing a complete main-process skeleton. The mandatory five
regular full-pass candidate gate was not met.

No candidate image or gallery is claimed. The evaluation helper writes panel
images only for actual P2D full-pass layouts, and this replay returned none.

## Canonical Xinzhao replay

Input: `backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json`

| Measure | R2 result |
| --- | ---: |
| Placement node budget / visits | 120 / 120 |
| Main-process skeletons examined | 0 |
| Truck-feasible skeletons | 0 |
| P2D full-pass skeletons | 0 |
| Visually distinct regular full-pass candidates | 0 |
| Layout families attempted | 3 |
| Family construction-policy attempts | 6 attempts per family across topology/axis variants |
| Complete building skeletons | 0 |
| Primary X / Y axes in planned candidates | 4 / 5 |
| Gallery | not generated; no qualifying real candidates |

Both replay results were `VALIDATED_LAYOUT_SEARCH_EXHAUSTED`. The selector and
work-queue traces were deterministic; selected-layout, canonical-result, and
SVG determinism are not applicable because no layout was selected. All three
families were attempted, but the family-specific search did not reach complete
seven-zone skeletons, so no truck or P2D comparison occurred. This is not a
proof of geometric infeasibility.

The machine-readable two-run trace is
[`xinzhao_structured_r2_candidate_gallery.json`](evidence/v2_2_2_p1a/xinzhao_structured_r2_candidate_gallery.json).

## Cross-fixture regression

The targeted layout/P2C/P2D/Tool 7 regression run completed with 189 passed
tests and 4 setup errors. All four errors are the P1F selector-backed
`P4_REAL_SELECTOR_SITE_WITH_NO_BUILD_ZONES` scenario: `preview_site_layout`
returns `VALIDATED_LAYOUT_SEARCH_EXHAUSTED`, so the historical presentation,
mobile, and engineering-sheet evidence cannot be regenerated from a selected
layout. This is a real cross-fixture regression and is not treated as a
passing compatibility result. The checked-in P1F evidence itself was not
modified.

## Implemented

- `BuildingEnvelopeV1` is kept distinct from site bounds. Rectangle candidates
  use complete-program, family-derived dimensions. Simple-L candidates also
  require sufficient program area and exact exterior-edge capacity for the
  peripheral bands.
- `BuildingEnvelopeV1.contains` checks whether a room rectangle is covered by
  the union of orthogonal envelope components. It permits a room to span
  contiguous components and rejects room geometry inside the L notch.
- Support and personnel bands are placed in a component attached to their
  selected exterior side; personnel placement is anchored to the main entrance
  and clamped within that component. Neither band is the full envelope.
- Primary grid axes remain distinct from local event axes. Family construction
  plans are attempted independently of the legacy topology label and include
  both orthogonal process axes when a plan is site-feasible.
- The envelope closure gate remains before truck/P2D admission. Existing hard
  validation, dimensions, adjacency, budgets, Tool 7 schema, and selection
  authority are unchanged.

The critical union-containment behavior has a regression test covering both a
valid room across an L seam and an invalid room in the notch. Envelope,
peripheral-band, family, axis, and closure behavior are also covered by unit and
architecture tests.

## Local validation

Initial focused R2 suite after the final geometry fix:

- Structured-building, face-root ordering, family-quantum, and architecture
  tests: `16 passed`.
- Full architecture suite: `776 passed, 16 skipped` after fetching the missing
  `origin/main` tracking ref required by unrelated historical scope tests.
- Broader layout/P2C/P2D/Tool 7 regression: `189 passed, 4 errors`; the four
  errors are the P1F selector-backed cross-fixture scenario described above.
- SQLite-marked suite: `153 passed, 26 skipped`; it required `PYTHONPATH=src`
  so Alembic subprocesses could import the backend package. PostgreSQL was not
  available locally (`psql`, `pg_isready`, and Docker are absent); exact-head
  CI is the PostgreSQL authority.
- Real Tool 7: two unmocked runs; both exhausted search with zero complete
  skeletons.

Changed-file Ruff, format, and mypy checks pass. PR and exact-head CI results
are reported in the task handoff.

`OWNER_VISUAL_REVIEW=PENDING`,
`OWNER_XINZHAO_P1A_VISUAL_BLOCKER_RESOLVED=false`, and PR #302 remains Draft.
