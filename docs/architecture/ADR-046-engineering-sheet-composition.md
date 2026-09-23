# ADR-046 — Deterministic Engineering Sheet Composition

## Status

Proposed implementation decision for V2.2.1 P1E; Draft review only.

## Context

The existing SVG projection has distinct user-facing, mobile, engineering
sheet, and engineering review profiles. Before P1E, the engineering sheet
used full site extents to size its main drawing. On a site with distant
context geometry, that made the building plan too small and left the sheet
with low primary-plan occupancy. The same profile also exposed review
provenance/debug text, although that information belongs to the separate
engineering-review view. P1D already provides deterministic drawing lint and
page-furniture/label facts that can act as a composition gate.

## Decision

Add a versioned, finite, deterministic page-space composition policy:
`engineering-sheet-composition@1.0.0`. The `ENGINEERING_SHEET` primary viewport
uses the existing primary-plan bounds, while full site context is preserved
in a context inset. No source engineering geometry is recalculated, moved,
resized, or removed.

The candidate family and order are fixed: `RIGHT_RAIL`, then `BOTTOM_RAIL`.
The application evaluates candidates using the existing
`drawing-lint@1.0.0` report and the frozen occupancy/context/dimension floors.
The first candidate meeting every hard condition is selected. There is no
random search, browser measurement, route score, placement objective, or
geometry optimization.

`ENGINEERING_SHEET` is a business engineering drawing: it preserves the
existing engineering overlays and all room dimension groups, but hides
internal zone codes, source hash, portal debug text, schema identity, and raw
validation metadata. `ENGINEERING_REVIEW` keeps its existing diagnostics and
provenance visibility. This separates engineering geometry visibility from
debug/provenance visibility.

## Consequences

- For the representative fixture, `RIGHT_RAIL` passes the hard gate with main
  drawing occupancy `0.7008771929824561`, primary-plan screen occupancy
  `1.0`, and width/height ratios `1.0` each. The alternate `BOTTOM_RAIL`
  candidate fails the minimum main-drawing occupancy and is rejected.
- The representative engineering-sheet lint gate passes with zero errors,
  zero warnings, and zero unavailable required facts.
- `PRESENTATION`, `MOBILE_PREVIEW`, and `ENGINEERING_REVIEW` retain their
  baseline SVG bytes; only `ENGINEERING_SHEET` changes.
- The policy consumes supplied projection bounds and P1D drawing facts. It
  has no dependency on calculations, placement, access routing, site geometry
  solvers, MCP, database, or frontend modules.
- Layout JSON remains the engineering authority; SVG remains a projection.

## Non-goals

This decision does not alter labels, zone/site/building geometry, dimensions,
placement, objective ordering, candidate ranking, routes, truck validation,
or any engineering formula. It does not infer equipment, racks, grid,
columns, doors, or vehicles. It does not implement PDF/DXF/IFC, frontend, MCP,
auto-repair, P1E successor work, release, or deployment.
