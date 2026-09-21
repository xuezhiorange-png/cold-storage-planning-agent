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

## P1A implementation overlay — canvas and page composition

P1A is separately authorized to implement only the canvas correction described
by the frozen contract. The SVG renderer now keeps
`engineering_geometry_bounds`, `engineering_drawing_bounds` and
`page_layout_bounds` distinct. Authoritative site, building, zone, access and
truck geometry determines the first two; legend, area schedule, title block,
metadata and debug text live only in page space.

The public projection boundary supports deterministic `PRESENTATION`,
`MOBILE_PREVIEW`, `ENGINEERING_SHEET` and `ENGINEERING_REVIEW` page profiles.
Presentation and mobile are user-facing views: they hide complete truck
maneuver envelopes, corridor debug envelopes, portal debug text and raw
validation metadata while retaining the business plan, loading face and
major corridor expression. Engineering sheet/review profiles preserve the
full review overlays. All profiles consume the same source geometry.

Presentation and mobile use a `PRIMARY_PLAN_BOUNDS` focus derived only from
the authoritative building footprint and twelve zone rectangles. A small,
deterministic context inset retains the complete site/obstacle context; it is
not a second engineering geometry and does not mutate source coordinates.
The projection reports primary-plan occupancy plus width/height ratios, with
mobile floors of 0.65, 0.70 and 0.55 respectively. Page furniture remains in
page space and does not participate in the primary-plan measurement.

This overlay does not change the structured layout result, any engineering
coordinate, placement/routing/truck authority, MCP surface, database, PDF/DXF
export, or downstream authorization. P1B and later presentation work remain
independently unauthorized.

## P1B implementation overlay — monochrome CAD hierarchy

P1B is the authorized projection-only implementation of the style contract.
The default theme is `LAYOUT_DRAWING_STYLE_V1` / `CAD_FACTORY_LAYOUT` with
`COLOR_MODE=MONOCHROME_PRIMARY`. Presentation and mobile use zero review
accent colors; engineering sheet stays grayscale; explicit engineering review
may use at most one review accent. Zone fills, no-build hatch, entrances,
portals, loading face and page furniture use restrained black/white/gray
tokens, while the existing HEX-only theme validation remains fail-closed.

The renderer exposes semantic viewport stroke tokens `W5` through `W0` with
the ordering `3.0 > 2.2 > 1.6 > 1.1 > 0.75 > 0.45`. Building exterior is
W5, zone boundaries W3, portal/entrance W2, loading face W3, dimensions and
site auxiliary geometry W1, and hatch marks W0. These are presentation
properties only; source layout hashes, coordinates, building/zone/access/
truck geometry, loading face, P1A primary-plan bounds and page composition are
unchanged.

P1C label restructuring, racks/equipment/grid/columns, P2/P2D, MCP, frontend,
database and export work remain outside this overlay and unauthorized.
