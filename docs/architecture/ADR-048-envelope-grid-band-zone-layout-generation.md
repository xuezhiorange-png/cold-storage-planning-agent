# ADR-048 — Envelope, Grid, Band, Zone Layout Generation

## Status

Implemented for the authorized V2.2.2 P1A generator refactor. The required
five-candidate / three-band-configuration acceptance gate failed on the
canonical Xinzhao run. This ADR records the architecture and its verified
limitations; it does not claim visual acceptance.

## Context

The bounded P2C generator already binds authoritative room dimensions and
preserves exact site, no-build, adjacency, truck, and P2D checks. Its structured
main-process path nevertheless starts at individual room rectangles and grows
the footprint by adjacency. That can yield hard-valid but visually fragmented
plans. Selection changes cannot repair a candidate family whose construction
does not encode building-scale organization.

## Decision

1. Construct a versioned `StructuredBuildingSkeletonV1` plan before placement.
   It owns an envelope candidate, finite primary/event grid axes, five
   functional bands, and the later zone-to-band assignment records.
2. The envelope is a search region, not a new building-size authority. Its
   rectangle or simple-L cells are derived from the effective site boundary
   and obstacle events. Existing exact boundary and closed-obstacle predicates
   remain authoritative for every room.
3. The primary grid uses exact integer-millimetre site, obstacle, and derived
   band events. Additional finite dimension-event coordinates seed roots; they
   are not independent room-specific grids and do not introduce epsilon.
4. Raw-side, process-core, finished-side, support, and personnel bands are
   derived before placement. The canonical Xinzhao plan currently assigns the
   support and personnel bands the full envelope bounds. They are therefore
   permissive regions, not yet effective spatial guarantees of subordinate or
   peripheral placement; the R1 visual acceptance failure keeps this gap
   explicit rather than describing it as solved.
5. Structured candidate generation admits a room only when its exact
   rectangle is within both the envelope and its assigned band, in addition
   to all existing exact geometry and MUST-edge predicates. Primary-grid edge
   alignment orders otherwise legal candidates; it does not override a hard
   predicate.
6. Existing topology lanes map to distinct construction plans:
   `STRAIGHT_LINEAR_BAND` to `LINEAR_3_BAND`, `CENTRAL_PROCESS_HUB` to
   `CENTRAL_PROCESS_WITH_SIDE_BANKS`, and `OFFSET_LINEAR_BAND` to
   `LONGITUDINAL_PROCESS_SPINE`. A simple-L envelope constructor exists for
   exact orthogonal geometry, but the current selector initializes all three
   Xinzhao lanes with a rectangle envelope; simple-L was not exercised in this
   canonical run and is not counted as an attempted candidate family.
7. Truck preflight remains a necessary-condition prune after the complete
   seven-zone geometry; final P2D still validates every complete candidate.
   P2D rules, truck authority, dimensions, site boundary, obstacles, budgets,
   ranking, Tool 7 contracts, and database/frontend behavior are unchanged.
8. Golden drawings provide no coordinates, dimensions, proportions, or runtime
   templates. No visual score or P1B threshold is introduced.

## Consequences

- Envelope, grid, and band construction are explicit domain objects rather
  than facts inferred after room placement.
- The exact P2C predicates remain the engineering gate. If a planned band has
  no feasible root, that family contributes no seed and search continues in
  the bounded family scheduler.
- Grid-alignment ordering and band regions can change the candidate set; exact
  hard-valid regression and deterministic Tool 7 replay are required.
- Candidate-generation architecture acceptance is separate from the required
  five visually distinct P2D-full-pass candidates and the Owner visual gate.
  Neither a domain-model test nor a green CI run proves visual acceptance.
- On the canonical Xinzhao replay, 11 distinct main skeletons reached truck
  preflight (9 rejected, 2 passed). Only two distinct skeletons reached a
  P2D full pass; both were classified as `LINEAR_3_BAND`, had the same
  main-group relation signature, and were rendered with a `STAIR_STEP`
  building outline. Consequently this implementation did not demonstrate
  different major band configurations or Owner-acceptable regularity.

## Validation boundary

The implementation is successful only if the canonical Xinzhao replay yields
at least five geometrically distinct full-pass layouts, with at least three
distinct major band configurations, while all existing hard-valid fixtures
remain hard-valid. Otherwise the task is reported as FAIL and the generated
candidate images are retained as evidence.
