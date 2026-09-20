# V2.2.1 P1A — Canvas, viewBox and page composition

## Governance snapshot

```ini
TASK_ID=V2_2_1_P1A_CANVAS_VIEWBOX_PAGE_COMPOSITION_R1
BASE_MAIN_SHA=00f684b994c22fbab85227a6ae7b88ff8f697f54
TARGET_VERSION=v2.2.1
ACTIVE_GOVERNANCE_LANE=V2.2.1_P1A
P0_STATUS=MERGED
P1A_AUTHORIZED=YES
P1B_AUTHORIZED=NO
P1C_AUTHORIZED=NO
P1D_AUTHORIZED=NO
P1E_AUTHORIZED=NO
LAYOUT_ALGORITHM_CHANGED=NO
P2_CHANGED=NO
P2D_CHANGED=NO
P4_CHANGED=NO
MCP_CHANGED=NO
DATABASE_CHANGED=NO
ENGINEERING_FORMULAS_CHANGED=NO
PRESENTATION_OCCUPANCY>=0.70
MOBILE_PREVIEW_OCCUPANCY>=0.80
ENGINEERING_SHEET_OCCUPANCY>=0.70
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_AUTHORIZED=NO
RELEASE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## Scope and authority

P1A corrects only the P3 SVG canvas and page composition. The validated
`site_validated_layout@1.0.0` remains the sole engineering authority. P1A does
not recalculate, resize, move, reroute, revalidate or reselect any engineering
geometry. It changes only the drawing transform and page-space arrangement.

The renderer now exposes two independent spaces:

```text
authoritative site/building/zone/access/truck geometry
    -> ENGINEERING_GEOMETRY_BOUNDS
    -> ENGINEERING_DRAWING_BOUNDS
    -> page composition and furniture
    -> SVG viewBox
```

`legend`, `area-schedule`, `title-block`, source metadata and debug text are
page furniture. They are not part of `engineering_geometry_bounds` and cannot
shrink the engineering drawing. `drawing_bounds` remains a compatibility alias
for the engineering drawing rectangle; `page_layout_bounds` is the full SVG
page space.

## Deterministic profiles

The application boundary accepts `page_profile` with these stable values:

- `PRESENTATION`: the primary factory plan plus legend, area schedule and
  title block in a deterministic page-furniture column; the complete site is
  retained in a small context inset.
- `MOBILE_PREVIEW`: the primary factory plan is the first-screen subject and
  page furniture is hidden; the complete site is retained in a context inset.
- `ENGINEERING_SHEET`: the complete engineering drawing plus the full page
  furniture composition for desktop/future sheet projection.
- `ENGINEERING_REVIEW`: the complete engineering drawing with review overlays
  and raw review metadata, without page furniture.

All profiles use the same source coordinates and the same engineering-to-SVG
Y inversion. `MOBILE_PREVIEW` does not delete or simplify engineering geometry;
it only collapses non-essential page furniture.

The representative 20 t/day full-pass layout produced these measured values:

```ini
BEFORE_MAIN_DRAWING_OCCUPANCY=0.6527
BEFORE_VIEWBOX=2780x1940
PRESENTATION_OCCUPANCY=0.7799991789
MOBILE_PREVIEW_OCCUPANCY=1
ENGINEERING_SHEET_OCCUPANCY=0.7799991789
PRESENTATION_SOURCE_GEOMETRY_OCCUPANCY=0.7167912254
```

The legacy value is the authoritative source-geometry rectangle divided by the
legacy page viewBox. The new acceptance occupancy is the engineering drawing
rectangle divided by page layout bounds; the source-geometry ratio is also
reported to make the remaining annotation margin explicit.

```ini
MAIN_DRAWING_TARGET_OCCUPANCY=0.78
MAIN_DRAWING_MIN_OCCUPANCY=0.70
MAIN_DRAWING_MAX_OCCUPANCY=0.88
MOBILE_PREVIEW_OCCUPANCY_MIN=0.80
TITLE_BLOCK_OVERLAP=FALSE
AREA_TABLE_OVERLAP=FALSE
LEGEND_OVERLAP=FALSE
```

## Determinism and geometry preservation

Page furniture rectangles are chosen by deterministic arithmetic. The
target-derived furniture width is rounded upward on the existing 0.001 m
projection grid; this is a presentation-space choice and does not mutate
source engineering coordinates. The renderer has no clock, random value,
runtime UUID or unordered iteration in the composition decision.

The P1A tests verify that the source layout/site hashes, zone coordinates,
building geometry, no-build geometry, loading face, portals, corridors and
truck geometry are unchanged across profiles. They also verify byte-identical
SVG and hash output for repeated renders of the same profile/input.

## P1A2 presentation/mobile composition correction (R1)

The initial P1A automated bounds checks passed, but visual review found that a
full-site/truck review rectangle could still make the actual factory plan look
small on a mobile screen. This correction changes projection visibility and
page composition only. It does not change the validated layout result or any
engineering geometry.

```ini
TASK_ID=V2_2_1_P1A2_PRESENTATION_MOBILE_COMPOSITION_CORRECTION_R1
PREVIOUS_HEAD_SHA=436c7923c9bd6f1da00b857465e1fdc81f1fdae7
P1A_INITIAL_AUTOMATED_ACCEPTANCE=PASS
P1A_INITIAL_VISUAL_ACCEPTANCE=FAIL
PRESENTATION_REVIEW_OVERLAYS_HIDDEN=TRUE
MOBILE_REVIEW_OVERLAYS_HIDDEN=TRUE
ENGINEERING_REVIEW_OVERLAYS_PRESERVED=TRUE
TRUCK_MANEUVER_ENVELOPE_VISIBLE_IN_PRESENTATION=FALSE
TRUCK_MANEUVER_ENVELOPE_VISIBLE_IN_MOBILE=FALSE
TRUCK_MANEUVER_ENVELOPE_VISIBLE_IN_ENGINEERING_REVIEW=TRUE
CORRIDOR_DEBUG_ENVELOPE_VISIBLE_IN_PRESENTATION=FALSE
CORRIDOR_DEBUG_ENVELOPE_VISIBLE_IN_MOBILE=FALSE
PORTAL_DEBUG_TEXT_VISIBLE_IN_PRESENTATION=FALSE
PORTAL_DEBUG_TEXT_VISIBLE_IN_MOBILE=FALSE
PRIMARY_PLAN_BOUNDS_IMPLEMENTED=TRUE
PRIMARY_PLAN_OBJECTS=BUILDING_FOOTPRINT_PLUS_ALL_ZONES
SITE_CONTEXT_INSET_ALLOWED=TRUE
SOURCE_GEOMETRY_MUTATED=FALSE
SOURCE_ENGINEERING_GEOMETRY_CHANGED=FALSE
P2_CHANGED=FALSE
P2D_CHANGED=FALSE
P4_CHANGED=FALSE
MCP_CHANGED=FALSE
DATABASE_CHANGED=FALSE
P1B_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
```

`PRIMARY_PLAN_SCREEN_OCCUPANCY` is the primary-plan bounding rectangle area
divided by the focused drawing viewport area. `PRIMARY_PLAN_WIDTH_RATIO` and
`PRIMARY_PLAN_HEIGHT_RATIO` report the corresponding width and height ratios.
The representative acceptance floors remain 0.65, 0.70 and 0.55. A small,
deterministically scaled context inset retains the complete site and obstacle
context without allowing the site extent or truck review envelope to control
the main mobile composition. Source hashes, schema/result identity and raw
review metadata remain available in the structured projection result but are
not printed in the default presentation/mobile SVG.

## Delivery boundary

This task adds no PDF/DXF export, frontend integration, MCP change, database
change, P2/P2D change, or engineering-style redesign. Chinese label redesign,
final monochrome W5–W0 styling, rack/equipment/column symbols and later
presentation phases remain separately unauthorized.
