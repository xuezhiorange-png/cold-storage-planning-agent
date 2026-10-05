# ADR-049 — Whole-Building Group-Band Composition

## Status

Proposed contract for V2.2.2 P1A Architecture Reset P0; documentation only.
Runtime implementation is not authorized.

## Context

V2.2.2 addresses a quality gap beyond basic hard validity: a layout can have
twelve valid zones, access 12/12, Truck PASS, and P2 complete, yet still look
like independent tiles, obscure production direction, fail to read
Sorting/Packaging as a process core, scatter cold/storage functions, mix
personnel with product flow, or form an incoherent building composition. The
version goal is a visually recognizable whole factory with directional process
structure, coherent groups/bands, subordinate peripheral functions, and a
limited orthogonal axis family.

PR #302 pursued a long main-first/tail-attachment recovery chain. Its terminal
HEAD was `0de6161ff46a100c05441e1910889c7b1854dcff`, with 44 commits and 323
changed files. Exact-head PR run `37220083027` and push run `37220079201` both
failed only the unchanged R15 distinct-full-pass requirement (one observed,
two required); SQLite recorded 6474 passed, 470 skipped, one failed, and
PostgreSQL recorded 4916 passed, 52 skipped, 1720 deselected, one failed.
Final structured 12-zone count and structured P2D attempts were both zero.

The final real Tool 7 replay did not reach the last Frozen target-portal
structured path. This is a bounded implementation-lifecycle failure, not a
global infeasibility proof or proof that the unreached Frozen algorithm is
impossible. PR #302 is closed unmerged; its history remains available for
traceability.

## Decision

Adopt a B/C hybrid primary generator named
`WHOLE_BUILDING_GROUP_BAND_COMPOSITION_WITH_RESERVED_PERIPHERAL_DOMAINS`.
Reject `MAIN_PROCESS_FIRST_PLUS_TAIL_ATTACHMENT` as the primary structured
path. Legacy/fallback compatibility may remain independently, but it is not
the new structured composition authority.

The primary lifecycle is:

```text
whole-building structural composition
  -> functional groups and principal bands
  -> reserved peripheral domains
  -> exact authoritative zone placement
  -> existing site/adjacency/access/Truck hard validation
  -> P2D independent validation
  -> structural-quality comparison among hard-valid candidates
  -> selection
```

The composition covers all twelve zone roles before exact placement and does
not defer any role as “place later if space remains.” It assigns structural
intent to `RAW_SIDE_GROUP`, `PROCESSING_CORE_GROUP`,
`FINISHED_SIDE_GROUP`, `SUPPORT_GROUP`, and `PERSONNEL_GROUP`, and describes
personnel ingress, Packaging, Secondary, Frozen, and Shipping/Truck interface
domains. Such domains are construction reservations only: not zones,
dimensions, a building footprint, an access proof, or hard engineering
authority.

The proposed `StructuralCompositionPlanV2` carries a schema version, identity,
family, process axis/direction, functional groups, principal bands, zone-role
assignments, peripheral domains, relationship intents, dominant axis family,
site-orientation intent, and construction provenance. It contains no Golden
coordinates, guessed room dimensions, fake portal/Truck paths, final footprint,
or pass claim. Relationship intent cannot add or upgrade a MUST adjacency.

The finite family vocabulary is:

1. `LINEAR_BANDED` — directional raw/process/finished bands.
2. `CENTRAL_PROCESS_CORE` — a central Sorting/process core with raw and
   finished groups attached to distinct structural sides.
3. `PROCESS_SPINE_WITH_PERIPHERAL_BANKS` — a dominant process spine with
   explicitly assigned side banks or terminal groups.

Each family simultaneously assigns process orientation, Sorting/core role,
raw and finished bands, cold/storage grouping, support branches, personnel
ingress domain, Secondary/Frozen branch class, Packaging relation, and
Shipping/Truck interface side. A rotation, mirror, tiny shift, or tail-only
permutation is not a distinct family.

## Alternatives considered

### A. Main-process-first plus tail attachment — rejected as primary

This is the least expensive short-term migration but structurally defers
access-critical personnel and support functions until after the main geometry
has consumed space. It creates high route-after-placement risk and encourages
unbounded tail, portal, and route recovery. Its candidate diversity is liable
to collapse to one main skeleton with tail permutations. It may remain only as
legacy/fallback compatibility behavior.

### B. Whole-building group-band generation — viable

This best represents Owner-positive patterns because the full set of groups
and bands is chosen together. It sharply reduces the chance that a functional
role is an afterthought. It requires an explicit composition model and bounded
family enumeration, but composes cleanly with independent hard validation and
offers meaningful topology diversity.

### C. Process-core plus reserved peripheral domains — viable

This gives a clear process core while explicitly protecting personnel,
Packaging, Secondary, Frozen, and Shipping/Truck capacity. It can reduce
route-after-placement risk and bound per-composition complexity. However, it
needs careful finite reservation semantics so domains are not mistaken for
rooms, footprints, routes, or new hard authorities. On its own it may provide
less whole-building group/band coverage than B.

### B/C hybrid — selected

The hybrid gives B responsibility for complete whole-building group/band
coverage and gives C responsibility for explicit peripheral construction
domains. It aligns with qualitative positive references, lowers
route-after-placement risk, and remains compatible with all current hard
validators. Migration is more substantial than a local R2 patch, but reuses
authoritative predicates and validators while replacing the failed lifecycle.
Candidate diversity is measured by structural topology, not incidental
coordinate variants.

## Hard-authority and migration constraints

Future exact placement continues using current authoritative room dimensions,
fixed/flexible semantics, and provenance. This architecture does not modify
site boundaries, obstacles, zone overlap, MUST adjacency, portal/access rules,
Truck maneuver or loading-face authority, P2D, single-building footprint, or
`P2_COMPLETE`. `PROJECT_LAYOUT_VALIDATED` retains its current meaning.
Engineering feasibility runs before structural-quality comparison; no visual
benefit can offset a hard failure.

Golden references remain qualitative organization references. Their geometry
must not become coordinates, templates, hidden runtime geometry, or engineering
authority. Structural relationship intent cannot manufacture a shared-edge
MUST, route, portal, or Truck pass.

Reuse from PR #302 is limited to exact predicates, dimension/adjacency/access/
Truck/P2D authorities, portal and route primitives, structural facts,
deterministic accounting, compatibility tests, and evidence-rendering tools.
These must be explicitly integrated under the new composition lifecycle.
Main-first sequencing, tail-capacity scheduler assumptions, Frozen/Changing
emergency paths, and accumulated R2 special-case ordering are not inherited as
the primary architecture.

## Bounded search and acceptance

This ADR does not set a numeric placement budget. A separately authorized
implementation task must confirm budgets, but scheduling must guarantee
structural-family coverage first, meaningful composition-variant coverage
second, and local exact-placement variants last. No single family's tail,
Office, portal, or micro-adjustment variations may consume the full allowance
before other families receive coverage. A bounded search is not a global
infeasibility proof.

Existing hard-validity, R15, and full-chain acceptance tests remain unchanged.
Future delivery targets at least five structured P2D full-pass candidates and
three major layout families, with explicit counts for distinct structural
compositions, major-band configurations, and main-process geometries. Tiny
coordinate shifts, serialization changes, and tail-only permutations do not
count as structural distinctness.

An Owner visual gate is central to the version goal. A common-scale gallery
must show site and no-build regions, composition/groups/bands, all twelve
zones, flow direction, personnel ingress, support branches, and
Shipping/Truck interface. Hard validity and visual organization remain
separate judgments.

To prevent another unbounded recovery chain, the proposed cap is at most two
bounded correction rounds after the main implementation attempt. If no
structured 12-zone candidate exists at that stop, require
`ARCHITECTURE_REVIEW_REQUIRED`. Further implementation needs renewed Owner
authorization.

## Consequences

- The version-level objective is restored to recognizable whole-factory
  organization; tail routing is not treated as the product goal.
- All twelve roles and peripheral construction domains participate before
  exact room placement.
- Existing engineering authorities remain independent and unchanged.
- Hard feasibility and structural quality remain separately reported.
- Implementation remains unauthorized by this P0 contract.

## References

- [V2.2.2 P0 process-flow and layout-regularity contract](../tasks/V2_2_2-P0-process-flow-layout-regularity-contract.md)
- [V2.2.2 P0B Owner positive-reference set](../tasks/V2_2_2-P0B-owner-positive-layout-reference-set.md)
- [V2.2.2 P0C Golden abstraction and calibration](../tasks/V2_2_2-P0C-golden-layout-abstraction-and-calibration.md)
- [P1A whole-building composition contract](../tasks/V2_2_2-P1A-architecture-reset-whole-building-composition-contract.md)
- [ADR-047 Process Flow and Layout Regularity Authority](ADR-047-process-flow-layout-regularity-authority.md)
