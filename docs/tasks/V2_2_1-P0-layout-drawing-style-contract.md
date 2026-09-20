# V2.2.1 P0 — Layout drawing style contract freeze

## Governance snapshot

```ini
TASK_ID=V2_2_1_P0_LAYOUT_DRAWING_STYLE_CONTRACT_FREEZE_R1
BASE_RELEASE=v2.2.0
BASE_MAIN_SHA=34cd6b56c1d79dde9730898c6bd46e295e423334
TARGET_VERSION=v2.2.1
ACTIVE_GOVERNANCE_LANE=V2.2.1_P0
P0_AUTHORIZED=YES
STYLE_CONTRACT_CREATED=YES
STYLE_ID=LAYOUT_DRAWING_STYLE_V1
STYLE_NAME=CAD_FACTORY_LAYOUT
CANONICAL_ENGINEERING_AUTHORITY=STRUCTURED_LAYOUT_JSON
SVG_ROLE=PRESENTATION_PROJECTION
IMPLEMENTATION_STARTED=NO
P1_AUTHORIZED=NO
LAYOUT_ALGORITHM_CHANGED=NO
P2_CHANGED=NO
P2D_CHANGED=NO
P3_RUNTIME_CHANGED=NO
P4_CHANGED=NO
MCP_CHANGED=NO
DATABASE_CHANGED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_AUTHORIZED=NO
RELEASE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

This is a presentation-contract freeze only. It does not implement or
authorize a renderer correction. V2.2.0 remains the released engineering
baseline; the style contract is the proposed V2.2.1 P0 input for a separately
authorized implementation stage.

## Authority and purpose

The P2/P2D result and its structured `site_validated_layout@1.0.0` JSON remain
the only engineering authority. The P3 SVG is a presentation projection:

```text
validated engineering geometry
        -> drawing model
        -> static SVG projection
```

The drawing must express the already validated layout in a CAD/factory-plan
language. It must never recalculate a more attractive layout, change a zone
rectangle, select another loading face, regenerate a portal or corridor,
rerun a route search, rerun truck validation, or call an engineering
calculator. Presentation labels, colors, line weights, page placement and
annotation fallbacks have no authority over engineering geometry.

The following boundaries are frozen as unchanged:

```ini
ZONE_DIMENSIONING_CHANGED=FALSE
ZONE_AREA_AUTHORITY_CHANGED=FALSE
PLACEMENT_ALGORITHM_CHANGED=FALSE
PLACEMENT_OBJECTIVE_CHANGED=FALSE
CANDIDATE_SELECTION_CHANGED=FALSE
ACCESS_ROUTING_CHANGED=FALSE
TRUCK_VALIDATION_CHANGED=FALSE
LOADING_FACE_SELECTION_CHANGED=FALSE
BUILDING_FOOTPRINT_AUTHORITY_CHANGED=FALSE
MCP_TOOL7_INPUT_CHANGED=FALSE
MCP_TOOL7_ENGINEERING_OUTPUT_CHANGED=FALSE
TOOLS_1_TO_6_CHANGED=FALSE
FACTORY_POWER_CHANGED=FALSE
DATABASE_CHANGED=FALSE
P3_PRESENTATION_MAY_CALL_ZONE_CALCULATOR=FALSE
P3_PRESENTATION_MAY_CALL_PLACEMENT_SEARCH=FALSE
P3_PRESENTATION_MAY_CALL_ROUTE_SEARCH=FALSE
P3_PRESENTATION_MAY_CALL_CANDIDATE_SELECTOR=FALSE
P3_PRESENTATION_MAY_CALL_TRUCK_VALIDATOR=FALSE
P3_PRESENTATION_MAY_USE_ENGINEERING_FORMULAS=FALSE
```

## Owner golden drawing references

The five owner-provided drawings are positive style references only. They
freeze presentation semantics, not dimensions, coefficients, geometry, or
runtime training data. No source PDF binary is part of this contract.

| ID | Reference | Style role |
| --- | --- | --- |
| GD-001 | 竹园 | Regular factory layout |
| GD-002 | 潇湘 | High-density internal arrangement |
| GD-003 | 牟定 | Irregular site masterplan |
| GD-004 | 双龙营 | Architectural single-building plan |
| GD-005 | 盘龙 | Signed/fused production drawing; primary reference |

```ini
GOLDEN_REFERENCE_COUNT=5
PRIMARY_GOLDEN_REFERENCE=GD-005_PANLONG
GOLDEN_REFERENCES_ARE_ENGINEERING_AUTHORITY=FALSE
GOLDEN_REFERENCES_ARE_RUNTIME_TRAINING_DATA=FALSE
ORIGINAL_GOLDEN_PDF_SUBMITTED=FALSE
```

The implementation may extract drawing-expression rules such as hierarchy,
line weight, annotation fallback, and page composition. It may not reverse
engineer dimensions from a drawing, hardcode a project value, or use a golden
drawing to optimize placement.

## Drawing modes

Both modes consume exactly the same validated layout geometry. Changing mode
is a view/projection choice and never repeats engineering work.

```ini
PRESENTATION_MODE_FROZEN=TRUE
ENGINEERING_REVIEW_MODE_FROZEN=TRUE
DEFAULT_DRAWING_MODE=PRESENTATION
```

### PRESENTATION

The normal business drawing shows:

- site boundary and effective buildable boundary;
- building footprint and spatial boundaries;
- all zones with Chinese business names and area;
- major dimensions selected by the page profile;
- main entrance, truck entrance, major corridors and loading face;
- the authoritative final truck docking position when present;
- no-build areas, an area schedule, legend and title block;
- racks or process equipment only when those objects are present in a
  structured authoritative source.

The normal business drawing hides implementation/debug identifiers:

- internal zone codes and portal IDs;
- source, canonical and result hashes;
- schema/identity strings and `project_layout_validated`/
  `p2_complete` status text;
- debug corridor envelopes, debug truck envelopes and debug source hashes;
- raw access requirement records unless the selected output profile explicitly
  opts into review information.

### ENGINEERING_REVIEW

The review drawing may additionally show portals, corridor centerlines and
envelopes, truck maneuver envelopes, access requirements, complete engineering
dimensions, source geometry and validation/debug IDs. These overlays are
diagnostic projections of the same source result; they do not create a second
authority.

## Visual hierarchy and palette

```ini
COLOR_MODE=MONOCHROME_PRIMARY
MAX_ACCENT_COLORS=1
```

The default drawing is primarily monochrome and must not become a large
colored functional-area map. A single accent color may be used for review,
debug, or a necessary path. No-build hatching, portals, truck envelopes and
debug lines must remain visually subordinate to the building and room
structure.

The semantic hierarchy is:

| Element | Relative emphasis |
| --- | --- |
| Building exterior wall | strongest |
| Important interior wall | strong |
| Ordinary partition | medium-strong |
| Room text | strong |
| Axis/grid | medium |
| Column | medium-strong |
| Rack/storage | medium-light |
| Equipment | medium-light |
| Vehicle | medium-light |
| Site auxiliary line | light |
| Road/turning auxiliary | light |
| Dimension auxiliary line | medium-light |

Relative stroke levels are frozen instead of absolute print millimetres so
they can be normalized to an SVG viewport:

```ini
W5=EXTERIOR_WALL
W4=MAJOR_PARTITION_OR_KEY_SITE_BOUNDARY
W3=NORMAL_WALL_OR_COLUMN
W2=RACK_EQUIPMENT_OR_DOOR
W1=GRID_OR_DIMENSION
W0=AUXILIARY_BACKGROUND
ALL_GRAPHICS_USE_ONE_STROKE_WIDTH=FALSE
```

## Stable SVG layer contract

The implementation must emit the following stable semantic layer order. A
debug layer, if needed by `ENGINEERING_REVIEW`, is separate from the default
presentation layers.

```text
01 site-background
02 site-boundary
03 road-and-yard
04 grid
05 columns
06 building-exterior-wall
07 interior-wall
08 doors-and-openings
09 zones
10 racks-and-storage
11 process-equipment
12 truck-and-loading
13 no-build-area
14 primary-dimensions
15 room-labels
16 callouts
17 schedule-table
18 title-block
```

Layer order is a presentation contract, not an instruction to invent absent
geometry. Structured source objects determine whether a layer has content.

## Evidence honesty: no inferred objects

The drawing layer may define support for the following objects, but an object
is rendered only when it exists in an authoritative structured input:

```ini
UNAUTHORIZED_EQUIPMENT_INFERENCE=FALSE
UNAUTHORIZED_RACK_INFERENCE=FALSE
UNAUTHORIZED_GRID_INFERENCE=FALSE
UNAUTHORIZED_COLUMN_INFERENCE=FALSE
UNAUTHORIZED_TRUCK_GEOMETRY_INFERENCE=FALSE
```

In particular, do not infer racks in finished goods, packaging lines in the
sorting room, a six-metre column grid, columns, doors, equipment, parking,
or rack counts from room dimensions. Missing structured authority remains
empty. A maneuver envelope is not an authoritative vehicle outline.

## Room labels and schedules

The default business drawing uses stable Chinese display names. It must not
show `finished_goods_room`, `changing_room`, `portal-xxx`, schema versions,
hashes, or identities as the primary room label.

Illustrative presentation semantics are:

```text
成品间
602.6 ㎡
33.4 × 18.6 m
```

Large rooms may use three lines, medium rooms two lines, small rooms the
short name, and extremely small rooms a numeric ID. The area schedule then
maps the ID to the Chinese name and area:

```text
08  更衣室  23.5㎡
```

The fallback order is fixed:

```text
3 lines -> 2 lines -> 1 line -> numeric id + external schedule
```

The implementation must not solve crowding by shrinking text without bound.
Display labels are presentation-only and never alter engineering semantics.

The default area schedule contains only:

- index;
- Chinese zone name;
- area.

Width × depth is optional. Internal zone code, schema, hash and result
identity are not default schedule fields.

## Label collision and avoidance

Room labels are placed without changing source rectangles. The following are
hard presentation checks:

```ini
ROOM_LABEL_WALL_CROSSING_COUNT=0
ROOM_LABEL_PRIMARY_COLLISION_COUNT=0
```

A label must not cross a wall, cover a door, cover a primary dimension, or
seriously overlap a primary equipment symbol. When the room cannot hold all
text, use the frozen fallback order, a leader/callout, or the schedule. Do
not emit a knowingly overlapping label.

## Dimension annotations

The presentation hierarchy is:

```ini
LEVEL_1_TOTAL_DIMENSIONS
LEVEL_2_MAJOR_ZONE_DIMENSIONS
LEVEL_3_ROOM_DIMENSIONS
LEVEL_4_ENGINEERING_REVIEW_DIMENSIONS
```

`PRESENTATION` normally shows level 1 and selected level 2 dimensions. A full
room dimension chain belongs to `ENGINEERING_REVIEW`. Horizontal edges receive
horizontal dimensions and vertical edges receive vertical dimensions. Display
rounding is annotation-only and never participates in calculation or source
geometry. The source engineering unit remains metres.

## Vehicle and loading expression

`PRESENTATION` prioritizes the truck outline when an authoritative outline is
available, the final docking position, the selected loading face and a
necessary direction arrow. It hides a complete maneuver envelope and dense
reference path by default. `ENGINEERING_REVIEW` may show the full truck
validation geometry.

If only maneuver geometry is authoritative, the drawing must not fabricate a
vehicle outline or vehicle dimensions. The selected loading face is copied
from the validated layout and is never changed by the renderer.

## Grid, columns and no-build areas

```ini
GRID_RENDERING_CAPABILITY=TRUE
AUTO_INVENT_GRID=FALSE
```

Formal grid/column rendering requires authoritative axes, spacing and/or
column coordinates in the input. Building dimensions alone are not evidence
for a structural grid.

No-build zones keep their source geometry exactly. The default expression is
low-weight outline plus hatch; large saturated red or high-contrast fills are
not the default and must not dominate the drawing.

## Canvas, viewBox and information boxes

The renderer must distinguish engineering geometry bounds from page-layout
bounds:

```ini
ENGINEERING_GEOMETRY_BOUNDS_SEPARATE_FROM_PAGE_LAYOUT_BOUNDS=TRUE
MAIN_DRAWING_TARGET_OCCUPANCY=0.78
MAIN_DRAWING_MIN_OCCUPANCY=0.70
MAIN_DRAWING_MAX_OCCUPANCY=0.88
LEGEND_PARTICIPATES_IN_ENGINEERING_BOUNDS=FALSE
TITLE_BLOCK_PARTICIPATES_IN_ENGINEERING_BOUNDS=FALSE
AREA_SCHEDULE_PARTICIPATES_IN_ENGINEERING_BOUNDS=FALSE
SOURCE_METADATA_PARTICIPATES_IN_ENGINEERING_BOUNDS=FALSE
DEBUG_TEXT_PARTICIPATES_IN_ENGINEERING_BOUNDS=FALSE
```

The main drawing bounds are determined first from the authoritative site,
building, zone, access and truck geometry. Legend, schedule, title block,
metadata and debug text are then placed in page space. They must not shrink
the main engineering drawing into a small corner of a mobile canvas.

Legend, area schedule and title block use a deterministic free-space-aware
placement contract. Candidate regions may include right, bottom, top-right
and bottom-left; the contract does not freeze a particular placement
algorithm. Regardless of candidate selection:

```ini
TITLE_BLOCK_OVERLAP=FALSE
AREA_TABLE_OVERLAP=FALSE
LEGEND_OVERLAP=FALSE
```

## Output profiles

Two output profiles are frozen:

### MOBILE_PREVIEW

The mobile profile optimizes first-screen readability without changing source
geometry:

```ini
MOBILE_PREVIEW_PROFILE_FROZEN=TRUE
MAIN_DRAWING_SCREEN_OCCUPANCY_MIN=0.80
DEBUG_LAYER=FALSE
TITLE_BLOCK_COLLAPSED=TRUE
AREA_TABLE_COLLAPSED=TRUE
```

It must not reproduce a page with excessive empty space and a tiny plan.

### ENGINEERING_SHEET

The engineering-sheet profile is suitable for desktop and future A3/A2/PDF
projection. It may show full dimensions, schedule, title block, grid and
review overlays. Its existence does not authorize PDF/DXF export.

```ini
ENGINEERING_SHEET_PROFILE_FROZEN=TRUE
FULL_DIMENSIONS_ALLOWED=TRUE
SCHEDULE_ALLOWED=TRUE
TITLE_BLOCK_ALLOWED=TRUE
GRID_ALLOWED=TRUE
REVIEW_OVERLAYS_ALLOWED=TRUE
```

## Drawing modes for site and building

The contract exposes two semantic drawing modes; automatic mode selection is
not part of this P0:

```ini
DRAWING_MODE_SITE_MASTERPLAN
DRAWING_MODE_BUILDING_LAYOUT
AUTO_DRAWING_MODE_SELECTION=FALSE
```

`SITE_MASTERPLAN` may show site boundary, building footprint, authoritative
roads and yards, entrances, authoritative truck circulation, loading,
no-build areas and existing buildings. `BUILDING_LAYOUT` may show rooms,
walls, authoritative doors, corridors, authoritative racks/equipment, the
truck/loading interface and dimensions.

## Title block and scale

The title block may contain project name, drawing title, scale, version and
date. It must not contain validation flags, source hashes or debug status.
The renderer must not claim a physical scale it does not possess:

```ini
SCALE=SCHEMATIC
FALSE_PHYSICAL_PRINT_SCALE=FALSE
```

The title block is still deterministic: any displayed date must come from an
authoritative input, not the current clock. A timestamp or runtime object ID
must never make otherwise identical drawings differ.

## Automatic acceptance contract for future implementation

The future implementation is accepted only when it can demonstrate all of
the following without changing the source layout:

```ini
SVG_XML_VALID=TRUE
MAIN_DRAWING_OCCUPANCY>=0.70
ROOM_LABEL_WALL_CROSSING_COUNT=0
ROOM_LABEL_PRIMARY_COLLISION_COUNT=0
TITLE_BLOCK_OVERLAP=FALSE
AREA_TABLE_OVERLAP=FALSE
LEGEND_OVERLAP=FALSE
INTERNAL_ZONE_CODE_VISIBLE=FALSE
SOURCE_HASH_VISIBLE=FALSE
PORTAL_DEBUG_TEXT_VISIBLE=FALSE
SCHEMA_IDENTITY_VISIBLE=FALSE
UNAUTHORIZED_EQUIPMENT_INFERENCE=FALSE
UNAUTHORIZED_RACK_INFERENCE=FALSE
UNAUTHORIZED_GRID_INFERENCE=FALSE
SAME_INPUT_SAME_DRAWING_BYTES=TRUE
SAME_INPUT_SAME_DRAWING_HASH=TRUE
```

The occupancy check applies to the selected output profile; the `MOBILE_PREVIEW`
profile has its stronger `0.80` first-screen minimum. Debug visibility is
allowed only under `ENGINEERING_REVIEW`, never by default.

## Delivery boundary and next authorization

This P0 adds no renderer, no unit/integration runtime behavior, no frontend,
no MCP surface, no database migration, and no export path. It does not
authorize implementation of the style contract, P1, P4, P5, release, or
deployment.

```ini
IMPLEMENTATION_STARTED=FALSE
P1_AUTHORIZED=FALSE
P2_AUTHORIZED=FALSE
P3_RUNTIME_CHANGED=FALSE
P4_AUTHORIZED=FALSE
P5_AUTHORIZED=FALSE
READY_AUTHORIZED=FALSE
MERGE_AUTHORIZED=FALSE
TAG_AUTHORIZED=FALSE
RELEASE_AUTHORIZED=FALSE
DEPLOYMENT_AUTHORIZED=FALSE
NO_STEP_IMPLIES_THE_NEXT=TRUE
```
