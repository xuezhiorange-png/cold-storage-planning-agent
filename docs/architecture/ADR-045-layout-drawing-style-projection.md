# ADR-045 — CAD-style layout drawing projection contract

## Status

Proposed contract freeze for V2.2.1 P0. It is not an implementation or
release authorization.

## Context

V2.2.0 has a deterministic engineering chain through P2 placement, P2D
access/truck validation, P3 static SVG projection, MCP Tool 7, and the
validated Doubao path. The structured layout result is useful engineering
evidence, but the current SVG expression is not yet a business-ready CAD or
factory-plan drawing. The missing work is presentation semantics: hierarchy,
labels, dimensions, page composition, mobile readability, and controlled
debug visibility.

Five owner drawings are style references. They are not calculation sources,
runtime training data, or geometry authority.

## Decision

Adopt `LAYOUT_DRAWING_STYLE_V1` / `CAD_FACTORY_LAYOUT` as the V2.2.1 drawing
style contract. The structured validated layout JSON remains the canonical
engineering authority, and SVG remains a presentation projection. The
contract defines two views (`PRESENTATION` and `ENGINEERING_REVIEW`) and two
page profiles (`MOBILE_PREVIEW` and `ENGINEERING_SHEET`) over the same source
geometry.

The default visual language is primarily monochrome with relative stroke
weights W5 through W0. Business labels use stable Chinese display names with
deterministic fallback to a schedule/number. Room labels must not cross walls,
cover doors or primary dimensions, and formal dimensions, schedules, legends
and title blocks live in page layout space rather than shrinking engineering
geometry bounds. The default drawing does not invent racks, equipment,
columns, grid, doors, vehicles or other absent structured objects.

The complete contract, including layer order, occupancy, collision, label,
truck/loading, schedule, title-block, no-build and determinism rules, is
recorded in
[`V2_2_1-P0-layout-drawing-style-contract.md`](../tasks/V2_2_1-P0-layout-drawing-style-contract.md).

## Consequences

- Future P3 presentation work can improve drawing quality without changing
  zone area, dimensions, placement, access, truck validation, MCP, or
  calculation authority.
- Mobile and engineering-sheet consumers have explicit, testable profiles.
- Missing structured authority stays visibly absent instead of being replaced
  with plausible but unauthorised engineering symbols.
- A future renderer must keep engineering geometry bounds separate from page
  furniture bounds and must report deterministic presentation checks.

## Non-goals

This ADR does not implement or authorize renderer changes, route or placement
search, engineering formula changes, PDF/DXF/CAD/BIM export, frontend work,
MCP changes, database migration, release, deployment, or the next feature
lane.
