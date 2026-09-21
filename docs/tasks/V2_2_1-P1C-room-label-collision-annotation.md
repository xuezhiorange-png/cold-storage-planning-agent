# V2.2.1 P1C — Room label and annotation collision overlay

```ini
TASK_ID=V2_2_1_P1C_ROOM_LABEL_COLLISION_ANNOTATION_R1
BASE_MAIN_SHA=aae74ad71fdedc6b29daf8373f581bb6aa99d81a
TARGET_VERSION=v2.2.1
ACTIVE_GOVERNANCE_LANE=V2.2.1_P1C
P1C_AUTHORIZED=YES
RESULT=PROJECTION_ONLY
```

## Authority boundary

P1C changes only the SVG presentation overlay. It consumes the validated P2D
geometry already consumed by P3 and does not change zone area, dimensions,
placement, candidate ranking, access routing, truck validation, loading-face
selection, building footprint, MCP, frontend, database or engineering
formulas.

```ini
ZONE_DIMENSIONING_CHANGED=NO
ZONE_AREA_AUTHORITY_CHANGED=NO
PLACEMENT_ALGORITHM_CHANGED=NO
PLACEMENT_OBJECTIVE_CHANGED=NO
CANDIDATE_SELECTION_CHANGED=NO
ACCESS_ROUTING_CHANGED=NO
TRUCK_VALIDATION_CHANGED=NO
LOADING_FACE_SELECTION_CHANGED=NO
BUILDING_FOOTPRINT_CHANGED=NO
P2_CHANGED=NO
P2D_CHANGED=NO
P4_CHANGED=NO
MCP_CHANGED=NO
DATABASE_CHANGED=NO
FRONTEND_CHANGED=NO
SOURCE_ENGINEERING_GEOMETRY_CHANGED=false
ENGINEERING_COORDINATES_MUTATED=false
```

## Room labels

Business views use the existing stable Chinese display-label registry. The
deterministic fallback order is:

```ini
LABEL_FALLBACK_ORDER=3_LINES>2_LINES>1_LINE>NUMERIC_ID
```

`3_LINES` is Chinese name, area, and width × depth. `2_LINES` is Chinese name
and area. `1_LINE` is the Chinese name. `NUMERIC_ID` is an index whose Chinese
name and area are available in the area schedule. A fixed candidate anchor
order (`CENTER`, `TOP`, `BOTTOM`, `LEFT`, `RIGHT`) and a fixed conservative
text-width estimate make the result independent of browser fonts and runtime
object ordering. A callout is used only when even the fixed numeric label does
not fit inside the room.

The area schedule is limited to:

```text
编号 | 中文名称 | 面积
```

Internal zone codes, source hashes, schema identities and portal/debug text
are not visible in `PRESENTATION`, `MOBILE_PREVIEW` or `ENGINEERING_SHEET`.
`ENGINEERING_REVIEW` retains the existing debug visibility and source
provenance.

## Collision and dimension semantics

The label planner checks the screen-space label box against the authoritative
room rectangle, visible portal segments and visible primary dimension
annotations. It reports:

```ini
ROOM_LABEL_WALL_CROSSING_COUNT=0
ROOM_LABEL_PRIMARY_COLLISION_COUNT=0
```

It never moves or resizes an engineering rectangle. Presentation retains a
small, deterministic selection of major room dimensions; mobile keeps the
primary-plan focus and suppresses room dimension chains. Engineering sheet and
engineering review retain the complete room dimension groups. Stable hidden
dimension identities remain in the SVG DOM for compatibility, but omitted
focused-view chains are not painted.

## Acceptance evidence

P1A canvas/focus, P1A2 visibility, P1B monochrome style, SVG theme security,
and deterministic SVG bytes/hashes remain required regressions. Owner visual
review of the unchanged representative 20 t/day full-pass fixture is a
separate acceptance gate; automated collision metrics do not replace it.

```ini
P1A_COMPOSITION_PRESERVED=true
P1A2_FOCUS_PRESERVED=true
P1B_MONOCHROME_STYLE_PRESERVED=true
INTERNAL_ZONE_CODE_VISIBLE=false
SOURCE_HASH_VISIBLE=false
PORTAL_DEBUG_TEXT_VISIBLE=false
SCHEMA_IDENTITY_VISIBLE=false
SAME_INPUT_SAME_SVG_BYTES=true
SAME_INPUT_SAME_SVG_HASH=true
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_AUTHORIZED=NO
RELEASE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```
