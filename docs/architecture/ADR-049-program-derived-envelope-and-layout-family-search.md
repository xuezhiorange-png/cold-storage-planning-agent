# ADR-049 — Program-Derived Envelopes and Layout-Family Search

## Status

Implemented within the authorized R2 scope; the required Xinzhao acceptance
gate failed. The refactor now distinguishes planned building geometry from
site bounds, binds peripheral bands to actual envelope components, and
enumerates layout families independently of the legacy topology label. The
canonical real Tool 7 replay still produced no complete main-process skeleton,
so this ADR does not claim a usable building layout or Owner visual acceptance.

## Context

ADR-048 introduced envelope/grid/band domain objects but left important
semantics incomplete. In particular, its simple-L envelope was selected from
site/obstacle events using only a total-area test, and zone containment
required a rectangle to lie in one component rather than in the exact union of
touching components. Peripheral bands could also be computed from the
envelope's bounding rectangle, causing a band to cross a non-buildable notch.
The initial family traversal was still too closely associated with legacy
topology search.

## Decision

1. Keep effective site geometry and planned building geometry as distinct
   authorities. Rectangle envelope dimensions are derived from the authoritative
   twelve-zone program and family-specific band projections. Simple-L candidates
   must meet those derived dimensions, the complete program area, and the
   necessary edge capacity for support/personnel bands; their components are
   checked against the existing exact site and no-build predicates.
2. Define `BuildingEnvelopeV1.contains` as exact axis-aligned rectangle coverage
   by the union of its orthogonal components. A room may span a shared seam
   between adjacent components, but a room entering the L notch is rejected.
   No tolerance or geometric clearance is added.
3. Place support and personnel bands within envelope components that touch
   their selected exterior edge and have the authoritative band dimensions.
   The personnel band is anchored near the authoritative main entrance and
   clamped to the selected component. A missing component slot makes that plan
   unavailable; it does not enlarge the site or relax a zone dimension.
4. Treat `LINEAR_3_BAND`, `CENTRAL_PROCESS_WITH_SIDE_BANKS`, and
   `LONGITUDINAL_PROCESS_SPINE` as first-class construction-plan inputs. Each
   compatible family is attempted on the preferred and orthogonal process axis
   in deterministic order. The exact resulting seven-zone geometry is still
   classified by the existing topology authority; layout-family names do not
   grant ranking bonuses.
5. Keep primary grid axes separate from local site, obstacle, and dimension
   events. Primary axes arise from envelope and major-band edges. Exact local
   events remain available to placement without being called primary axes.
6. Keep the twelve-zone closure gate before truck/P2D candidate admission.
   Truck, P2D, access, zone dimensions, MUST adjacency, site/no-build geometry,
   placement budget, selection authority, Tool 7 contracts, and public schemas
   remain unchanged.
7. Golden drawings remain qualitative references only; no coordinates,
   dimensions, proportions, templates, scores, or numeric visual thresholds
   enter runtime behavior.

## Consequences and verified limitation

- The canonical Xinzhao fixture has a buildable L-shaped region. Its exact
  envelope components can jointly cover a room that crosses their shared seam;
  containment no longer rejects such a room merely because it spans two
  component records.
- Support/personnel bands are now bounded subregions and are not the whole
  envelope. The observed canonical primary grid has four X axes and five Y
  axes; the many exact local event axes remain separate.
- The two unmocked Xinzhao Tool 7 replays both terminated with
  `VALIDATED_LAYOUT_SEARCH_EXHAUSTED` at the unchanged 120-node budget. They
  examined zero complete main-process skeletons, reached zero truck preflights,
  and produced zero P2D full-pass candidates. Therefore no candidate gallery
  can be truthfully generated from this run.
- Family-plan attempts were recorded for all three requested families. The
  bounded live search did not produce a complete twelve-zone building
  skeleton in any family. This is an implementation failure against the R2
  acceptance gate, not evidence that the families or site are infeasible.
- A green exact-head CI, if obtained, will validate code and tests only; it
  cannot substitute for the missing candidate gallery or visual review.

## Validation boundary

R2 is accepted only if at least five visually distinct, regular-outline
P2D-full-pass candidates are produced across at least three layout families,
with no presented stair-step candidate, under the existing hard authorities.
The current canonical run did not meet that gate and must be reported as
`RESULT=FAIL`.
