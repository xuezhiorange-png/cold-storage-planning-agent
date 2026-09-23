# ADR-047 — Process Flow and Layout Regularity Authority

## Status

Proposed contract for V2.2.2 P0; implementation is not authorized by this ADR.

## Context

V2.2.1 can return a hard-valid site layout while its overall process
organization is irregular. The P2C ranking currently uses SHOULD-adjacency
count and loading-side preference; compactness and shape regularity are
inactive. P2D validates actual access, route, truck, and footprint constraints,
but does not rank a complete process chain or certify factory regularity. The
P2 validated-candidate selector correctly compares full-pass candidates within
its deterministic bounded family; it is not the first passing candidate that
causes the gap. The missing authority is a separate process/regularity quality
contract.

## Decision

1. Keep `PROJECT_LAYOUT_VALIDATED` as the existing engineering hard-feasibility
   result and preserve `P2_COMPLETE` semantics. Add distinct, versioned
   `PROCESS_FLOW_VALIDATED` and `LAYOUT_REGULARITY_VALIDATED` assessments in a
   future quality result; do not silently change Tool 7 or layout schema.
2. Define semantic process roles and strict increasing ranks for present
   stages, preserving the current V2.2 chain. Coating remains optional at rank
   55. Receiving is project-mapped and is not inferred from truck entrance.
3. Derive backtrack and turn metrics from authoritative ordered route/portal
   geometry, not centroids or geometric proxies. A nonzero verified backtrack
   fails process-flow validation. Ordinary rectangle/near-rectangle sites
   target no more than one main-flow turn; irregular-site exceptions require
   explicit evidence and reason.
4. Organize future candidates as functional group, then band, then zone.
   Freeze the five groups and the side-branch, personnel/logistics, exact-grid,
   depth-alignment, compactness, and required shared-edge-quality metrics in
   the P0 task contract.
5. Evaluate hard engineering constraints before any quality ranking. Rank
   quality lexicographically using the ordered atomic metrics in the P0
   contract; preserve P2B2 SHOULD-count and loading-side preference as final
   compatibility tie-breaks. Do not use a weighted score to offset a failed
   hard gate or atom.
6. Report metric evidence and explain the first decisive reason a candidate
   won versus the next-ranked full-pass candidate. A bounded search reports
   only results over its explored family; it is not an infeasibility proof.
7. Treat GD-005 Panlong as an abstract composition/organization reference,
   never engineering authority. Preserve v2.2.1 hashes as historical evidence,
   while allowing future candidate geometry and hashes to change.

## Calibration and entry criteria

At the original P0 freeze, the canonical Xinzhao `site_layout_input_v3.json`
was unavailable and was not inferred from its SVG or hash. P0A later acquired
the Owner-provided raw bytes, verified their digest, and reproduced the
v2.2.1 Tool 7 result; the fixture and replay evidence are recorded in the
P0A calibration document. This resolves fixture availability only. The
repository still does not contain the original GD-005 drawing bytes. The
proposed depth-alignment value `0.80` and thresholds for
notches/appendages/compactness are not frozen acceptance gates: they require
Owner-labelled positive samples, versioned definitions, and Owner approval.
P1 implementation cannot treat these as passing defaults.

## Consequences

- Engineering hard validity and factory process/regularity quality are
  independently observable.
- Existing zone areas, dimensions, site geometry, access/portal, truck,
  loading-face, and P2D authority remain unchanged.
- The implementation belongs primarily in the layout objective profile,
  deterministic P2C candidate family, and P2 application candidate selector,
  with domain/integration/evaluation tests. P2D changes are conditional on
  missing authoritative route facts; SVG/P1A–P1F/P4 are not the primary
  implementation layer.
- P0 adds no runtime behavior and authorizes no P1 implementation, release,
  deployment, or subsequent phase.

## References

- [V2.2.2 P0 contract](../tasks/V2_2_2-P0-process-flow-layout-regularity-contract.md)
- [ADR-044 site-constrained layout authority](ADR-044-site-constrained-factory-layout-authority.md)
- [V2.2.1 P1F cross-fixture evidence](../tasks/V2_2_1-P1F-cross-fixture-drawing-robustness.md)
