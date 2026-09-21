# V2.2.1 P1B — Monochrome CAD visual hierarchy

## Governance snapshot

```ini
TASK_ID=V2_2_1_P1B_MONOCHROME_CAD_VISUAL_HIERARCHY_R1
BASE_MAIN_SHA=dd26be03438ba7e3b147e5b700e3815d80d70458
TARGET_VERSION=v2.2.1
ACTIVE_GOVERNANCE_LANE=V2.2.1_P1B
P1B_AUTHORIZED=YES
STYLE_ID=LAYOUT_DRAWING_STYLE_V1
STYLE_NAME=CAD_FACTORY_LAYOUT
COLOR_MODE=MONOCHROME_PRIMARY
PRESENTATION_ACCENT_COLOR_COUNT=0
MOBILE_ACCENT_COLOR_COUNT=0
ENGINEERING_SHEET_ACCENT_COLOR_COUNT=0
ENGINEERING_REVIEW_ACCENT_COLOR_COUNT<=1
W5=3.0
W4=2.2
W3=1.6
W2=1.1
W1=0.75
W0=0.45
SOURCE_ENGINEERING_GEOMETRY_CHANGED=NO
P1A_COMPOSITION_PRESERVED=YES
P1A2_FOCUS_PRESERVED=YES
ZONE_DIMENSIONING_CHANGED=NO
PLACEMENT_ALGORITHM_CHANGED=NO
PLACEMENT_OBJECTIVE_CHANGED=NO
ACCESS_ROUTING_CHANGED=NO
TRUCK_VALIDATION_CHANGED=NO
P2_CHANGED=NO
P2D_CHANGED=NO
P4_CHANGED=NO
MCP_CHANGED=NO
DATABASE_CHANGED=NO
FRONTEND_CHANGED=NO
P1C_AUTHORIZED=NO
P1D_AUTHORIZED=NO
P1E_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_AUTHORIZED=NO
RELEASE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## Scope and authority

P1B changes only the SVG presentation projection. The validated structured
layout remains the engineering authority; no source geometry, zone area,
placement, access route, truck maneuver, loading face, MCP contract or
calculation is changed. The renderer consumes the same P1A/P1A2 composition
and context inset.

The default `SvgDrawingThemeV1` is now monochrome-first: ordinary zones use
`#FAFAFA`, cold zones use the lighter-gray distinction `#F3F3F3`, corridors
use `#F7F7F7`, and the main structural strokes are black/gray. No-build hatch
uses the server-owned light-gray `#B5B5B5` token. Existing HEX-only runtime
theme validation remains unchanged.

The semantic stroke hierarchy is explicit and strictly descending:

```ini
W5=EXTERIOR_WALL
W4=MAJOR_PARTITION_OR_KEY_SITE_BOUNDARY
W3=NORMAL_WALL_OR_COLUMN
W2=RACK_EQUIPMENT_OR_DOOR
W1=GRID_OR_DIMENSION
W0=AUXILIARY_BACKGROUND
```

The implementation maps the existing building outline to W5, zone boundaries
to W3, portals/entrances to W2, loading face to W3, dimensions and auxiliary
site geometry to W1, and hatch marks to W0. These mappings affect paint and
stroke presentation only.

## Profile visibility

`PRESENTATION` and `MOBILE_PREVIEW` retain the P1A2 primary-plan focus and
hide complete truck maneuver/debug overlays. They expose no review accent.
`ENGINEERING_SHEET` preserves review geometry in neutral grayscale. Only the
explicit `ENGINEERING_REVIEW` profile may use the reserved theme truck color
as one review accent. The source maneuver/corridor/portal data remains in the
validated input and is not deleted or rewritten.

Page furniture keeps its P1A placement and uses the same grayscale hierarchy:
white background, gray boundary swatches, light-gray fills/hatch and black
structural outline. No label-collision or label-content redesign is included.

## Acceptance evidence

The P1B focused tests assert the palette, strict W5–W0 ordering, semantic
stroke mappings, zero default business-view accents, at-most-one engineering
review accent, SVG security, determinism and P1A/P1A2 geometry/composition
invariants. Visual evidence is generated from the unchanged representative
20 t/day full-pass fixture for Owner review; automated metrics do not replace
that visual decision.

P1C remains separately unauthorized.
