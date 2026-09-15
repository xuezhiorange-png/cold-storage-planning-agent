# V2.2 P2B1 — Truck maneuver template contract

## Current status

```ini
TASK_ID=V2_2_P2B1_TRUCK_MANEUVER_TEMPLATE_CONTRACT_R1
TARGET_VERSION=v2.2.0
BASE_MAIN_SHA=ccd6336de4810012deec64c1b0a5f3256ff13d85
ACTIVE_GOVERNANCE_LANE=V2.2_P2
P2_AUTHORIZED=true
P2B1_AUTHORIZED=true
TRUCK_REPRESENTATION=OPTION_C_APPROVED_MANEUVER_TEMPLATES
OWNER_APPROVED=true
OPTION_A_REJECTED_FOR_V2_2=true
OPTION_B_REJECTED_FOR_V2_2=true
DEFAULT_TRUCK=false
DEFAULT_TEMPLATE=false
KINEMATIC_SOLVER=false
DOCK_FACE_REFERENCE=shipping_channel.LONG_EDGE_LOADING_FACE
PLACEMENT_SEARCH=false
OBJECTIVE_PROFILE_FROZEN=false
P2_COMPLETE=false
P3_AUTHORIZED=false
P4_AUTHORIZED=false
P5_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## Review correction R2

```ini
TASK_ID=V2_2_P2B1_TRUCK_MANEUVER_TEMPLATE_CONTRACT_R2
PR_NUMBER=280
BASE_MAIN_SHA=ccd6336de4810012deec64c1b0a5f3256ff13d85
PREVIOUS_HEAD_SHA=370f0e79bc88f6c480f3d79c013acdb2c5ad6111
P1F_INPUT_CONTRACT_IDENTITY=truck-project-access-input@1.0.0
P1F_TRUCK_INPUT_BOUND=true
PROJECT_ID_BINDING_ENFORCED=true
VEHICLE_WIDTH_BINDING_ENFORCED=true
VEHICLE_LENGTH_BINDING_ENFORCED=true
PROJECT_SOURCE_REFERENCE_IMPLEMENTED=true
PROJECT_SOURCE_DIGEST_IMPLEMENTED=true
CANONICAL_TEMPLATE_HASH_SEPARATE_FROM_PROVENANCE=true
ENTRY_REFERENCE_ORIGIN_ENFORCED=true
FORWARD_AXIS_ENTRY_HEADING_ENFORCED=true
RUNTIME_CHANGED=true
PLACEMENT_SEARCH_IMPLEMENTED=false
OBJECTIVE_PROFILE_FROZEN=false
KINEMATIC_SOLVER_IMPLEMENTED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
P3_AUTHORIZED=false
```

R2 changes only this contract boundary. The historical P1F schema and its
module remain unchanged.

P2B1 implements only the machine contract and validation boundary for
project-supplied, approved, versioned two-dimensional maneuver envelopes. It
does not place a template, search for a route, optimize a layout, or produce a
drawing. The owner decision is Option C: a project must supply the geometry
that it wants a later placement stage to use.

## Versioned contract family

The implementation is in the layout domain module
`truck-maneuver-template-contract@1.0.0` and exposes these independent models:

- `TruckManeuverTemplateV1`: one maneuver envelope;
- `TruckManeuverTemplateSetV1`: the project collection, which may contain a
  subset of the approved classes;
- `TruckManeuverRequirementV1`: the classes required by a particular project
  layout candidate;
- `TruckManeuverProjectInputV1`: the project-level binding of the collection
  and its requirement.

The correction also exposes `BoundTruckManeuverProjectInputV1`. It binds the
maneuver project input to the explicit P1F project truck input
`truck-project-access-input@1.0.0`. Every template in the set must match the
P1F `vehicle_width_m` and `vehicle_length_m` exactly. Missing or incomplete P1F
input returns `PROJECT_INPUT_REQUIRED`; no default truck is created. The
binding records the canonical P1F input and its evidence hash.

The project geometry layer is separate from the historical
`TruckProjectAccessInputV1` (`truck-project-access-input@1.0.0`). The historical
P1F input and schema are not changed and remain evidence/completeness input,
not a maneuver geometry authority.

Every template is project-owned and must carry:

```text
schema_version=1.0.0
project_id
source_authority=PROJECT_INPUT
template_id
maneuver_class
vehicle_width_m
vehicle_length_m
envelope_geometry
reference                  # project engineering source/material identifier
reference_frame            # local coordinate-frame object
content_sha256
provided_by
```

The stable template identity is
`truck-maneuver-template:<project_id>:<template_id>@1.0.0`. A set and a project
input have corresponding versioned identities. `required_maneuver_classes`
binds only the maneuvers actually needed by a later candidate; no project is
forced to provide all three classes.

## Approved maneuver classes

The initial catalogue is deliberately closed:

```ini
MANEUVER_CLASSES=STRAIGHT_APPROACH,TURN_90,DOCK_REVERSE
MANEUVER_STRAIGHT_APPROACH=true
MANEUVER_90_DEGREE_TURN=true
MANEUVER_DOCK_REVERSE=true
```

`STRAIGHT_APPROACH` is a supplied approach envelope. It is not generated from
vehicle width and length. `TURN_90` must explicitly say
`turn_direction=LEFT` or `RIGHT`; the validator never mirrors one direction
into the other. `DOCK_REVERSE` must carry `dock_face_reference`,
`approach_pose`, and `final_dock_pose`, with the dock reference exactly equal
to `shipping_channel.LONG_EDGE_LOADING_FACE`.

No `U_TURN`, `THREE_POINT_TURN`, `PARALLEL_PARKING`, or `CUSTOM` class is
authorized in this version.

## Geometry and reference frame

`envelope_geometry` reuses the P2A `normalize_polygon` primitive. It is a
simple polygon describing the complete project-supplied two-dimensional
occupancy/safety envelope in the template frame. The boundary is exact:

```ini
COORDINATE_SYSTEM=LOCAL_CARTESIAN_METERS
GRID_M=0.001
FLOAT_EPSILON_ALLOWED=false
REFERENCE_FRAME=LOCAL_TEMPLATE_FRAME
FORWARD_AXIS=POSITIVE_X
ORIGIN_REFERENCE=ENTRY_REFERENCE_POINT
```

Coordinates must be finite, non-boolean, and on the 0.001 m grid. The polygon
must have at least three distinct vertices, positive area, no zero-length
edge, no repeated closing vertex, no self-intersection, no self-touch, no
hole, and no multipolygon. It is implicitly closed; callers must not repeat
the first point at the end.

`reference` is a non-empty project engineering source/material identifier. It
is not a coordinate object. The separate `reference_frame` records a vehicle
reference point plus `entry_pose` and `exit_pose`. Because
`ORIGIN_REFERENCE=ENTRY_REFERENCE_POINT`, the supplied template must contain
`vehicle_reference_point={x:0,y:0}` and
`entry_pose={x:0,y:0,rotation_deg:0}`. Pose headings are otherwise limited to
the same discrete orientations used by the transform primitive: 0, 90, 180,
or 270 degrees. These fields describe the reference frame; they do not define
a vehicle kinematic model.

## Hash and provenance

`content_sha256` is a project-provided digest for the referenced source
material. It is not calculated from, or replaced by, the maneuver template
validator. Public validation requires the exact lowercase form `sha256:`
followed by 64 hexadecimal characters. The template's own complete
serialization integrity is exposed separately as `canonical_template_hash`
(with `canonical_result_hash` retained as its compatibility alias). It covers
the template source reference and digest, project identity, class, vehicle
dimensions, polygon, coordinate frame, class-specific fields, and provenance.
Therefore `project source digest != canonical template hash`.

Reordering mapping keys does not change the canonical template hash. Changing
the polygon, vehicle dimensions, maneuver class, turn direction, pose,
project/template identity, source reference, source digest, or provenance does.
A malformed source digest is rejected; no caller-provided digest is promoted
to template integrity authority.

The validated models retain canonical serialized JSON internally and expose
copies of their decoded data. A consumer cannot mutate the held canonical
serialization through a returned dictionary and thereby change its identity.

## Transformation primitive

`transform_maneuver_template(template, translation, rotation_deg)` is the only
geometry operation in this task. It applies an exact integer-millimetre
translation and one of the four authorized rotations:

```text
0, 90, 180, 270
```

It transforms the supplied envelope and `reference_frame` poses and returns a
new hash-bound observation. The transformed `entry_pose` is exactly the
translation and requested rotation because the input entry reference is the
local origin. The observation carries `source_reference`,
`source_content_sha256`, and `canonical_template_hash` as separate fields. It
does not validate site containment, obstacle clearance, access feasibility,
route feasibility, or placement. Arbitrary angles, off-grid translations, and
caller-supplied default geometry are rejected.

## Completeness and future boundary

`TruckManeuverProjectInputV1.template_input_complete` is true only when every
class named by `required_maneuver_classes` is present in the project set.
Missing classes produce `TRUCK_MANEUVER_TEMPLATE_REQUIRED`; no default
vehicle or template is substituted. Even a complete template input does not
mean that a route or project layout is validated:

```ini
TRUCK_MANEUVER_TEMPLATE_INPUT_COMPLETE=PROJECT_REQUIREMENT_DEPENDENT
TRUCK_ROUTE_VALIDATED=false
PROJECT_LAYOUT_VALIDATED=false
```

The later placement stage must transform the entire supplied envelope before
checking it against site/buildable geometry, hard obstacles, and people/truck
policy. P2B1 only supplies the validated input and transform primitive.

The objective profile remains deliberately unfrozen. No placement search,
route search, optimizer, or tie-break authority is introduced here:

```ini
OBJECTIVE_PROFILE_FROZEN=false
PLACEMENT_SEARCH_IMPLEMENTED=false
```

The P2A local geometry authority, P1F historical input, existing zone
dimensions, MCP/tool contracts, frontend, database, and all prior calculator
identities remain unchanged. There is no P2 completion or P3 authorization in
this task.

## Error boundary

Validation fails closed with stable domain errors for malformed templates,
unauthorized maneuver classes, invalid polygon/reference-frame values,
malformed source digests, stale collection or wrapper hashes, missing required
class bindings, P1F project-input gaps, vehicle-dimension mismatches, invalid
dock-face references, and unsupported transform rotations. A project that lacks
a required class is incomplete, not implicitly routed by a server default.

The following capabilities are outside P2B1:

```ini
NO_DEFAULT_TRUCK=true
NO_DEFAULT_MANEUVER_GEOMETRY=true
NO_KINEMATIC_TRUCK_SOLVER=true
NO_PLACEMENT_SEARCH=true
NO_OBJECTIVE_AUTHORITY=true
NO_ROUTE_GENERATION=true
NO_PORTAL_PLACEMENT=true
NO_SITE_PLACEMENT=true
NO_SVG_GENERATION=true
NO_PDF_GENERATION=true
NO_DXF_GENERATION=true
NO_MCP_TOOL_7=true
P1F_HISTORICAL_INPUT_SCHEMA_MUTATED=false
P2A_GEOMETRY_AUTHORITY_MUTATED=false
P1F_TRUCK_INPUT_BOUND=true
PROJECT_SOURCE_REFERENCE=true
PROJECT_SOURCE_DIGEST=true
CANONICAL_TEMPLATE_HASH_SEPARATE_FROM_PROVENANCE=true
ENTRY_REFERENCE_ORIGIN_ENFORCED=true
FORWARD_AXIS_ENTRY_HEADING_ENFORCED=true
```
