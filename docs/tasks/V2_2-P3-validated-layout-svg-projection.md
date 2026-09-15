# V2.2 P3 — Validated layout SVG projection

## Governance snapshot

```ini
TASK_ID=V2_2_P3_VALIDATED_LAYOUT_SVG_PROJECTION_R1
TARGET_VERSION=v2.2.0
BASE_MAIN_SHA=a1d035c4d42a2bc4895e6d3806d3f5fe77e7e0d2
P2_COMPLETE_REQUIRED=true
PROJECT_LAYOUT_VALIDATED_REQUIRED=true
P3_AUTHORIZED=true
P4_AUTHORIZED=false
P5_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

This task is the separately authorized P3 implementation. It does not
authorize MCP Tool 7, frontend integration, PDF/DXF export, release, or
deployment.

## Scope and authority

P3 is a projection only:

```text
site_validated_layout@1.0.0
        ↓
validated-layout-svg-projection@1.0.0
        ↓
static browser-readable SVG
```

The application boundary accepts the immutable P2D
`site_validated_layout@1.0.0` result and an already validated
`ValidatedSiteGeometryV1` context. P2D records the site-geometry hash instead
of duplicating the complete site input; P3 therefore requires that context and
checks it against `source_site_geometry_hash`. A mapping-supplied P2D
canonical hash is checked by `SiteAccessRoutingResultV1` before projection.

The input must have:

```ini
PROJECT_LAYOUT_VALIDATED=true
P2_COMPLETE=true
ACCESS_REQUIREMENT_COUNT=12
ACCESS_RESULT_COUNT=12
ACCESS_PASS_COUNT=12
TRUCK_ROUTE_VALIDATED=true
BUILDING_FOOTPRINT_PRESENT=true
```

Any other state fails closed with `VALIDATED_LAYOUT_REQUIRED`. P3 never calls
placement, routing, truck search, area calculation, or a calculator. Zone
rectangles, portals, corridor envelopes/centerlines, selected loading face,
truck maneuver envelopes, and the derived building footprint are copied from
the validated source result.

## Projection contract

The result is `ValidatedLayoutSvgProjectionV1` with identity
`validated-layout-svg-projection@1.0.0`. Its canonical payload binds the
source layout, zone plan, P1 handoff, site geometry, objective profile,
placement, and truck-maneuver hashes. It also includes the byte hash of the
SVG and the projection-only flags.

The source coordinate system remains `LOCAL_CARTESIAN_METERS` with a
`0.001m` source grid. The deterministic drawing transform maps engineering
coordinates to screen coordinates with a Y inversion:

```text
drawing_x = (engineering_x - drawing_min_x) × scale
drawing_y = (drawing_max_y - engineering_y) × scale
```

The transform is a display parameter; it never mutates source geometry. The
viewBox is derived from all source geometry plus deterministic annotation,
legend, and title-block margins. Concave site boundaries remain polygons; no
bounding-box replacement is performed.

Stable SVG group order is:

```text
site-boundary
site-constraints
building-footprint
zones
portals
corridors
truck-maneuvers
entrances
dimensions
labels
legend
```

Every zone has a stable `zone-{zone_code}` group and `data-zone-code`. The
source width/depth and geometry-derived actual rectangle area are displayed
only as presentation values; display rounding does not participate in any
engineering decision. Display labels come from a stable P3-only registry and
have `display_label_authority=false`.

The drawing includes the site and effective buildable boundaries, no-build
zones, existing buildings, the supplied building footprint, all twelve zone
rectangles, all source portals and corridor envelopes/centerlines, entrances,
the selected shipping loading face, truck maneuver envelopes/reference paths,
dimension annotations, a legend, and a deterministic title block.

## Static SVG and determinism

The serializer uses XML escaping for all source text and attribute values. It
does not emit scripts, `foreignObject`, external images/CSS/fonts, remote
references, JavaScript URLs, or event-handler attributes. The SVG has no
timestamp or random identifier. Replaying one identical source layout and
validated site geometry produces byte-identical SVG and identical SVG hash.

The SVG is renderable by a normal browser, but it is not a new engineering
authority. JSON remains the canonical layout authority; SVG is only a
projection. No PDF, DXF, PNG, CAD, BIM, MCP, REST, or frontend path is added
by P3.

## Representative evidence

The P3 tests reuse the P2D full-pass representative fixture. They verify
twelve zone groups and dimensions, the supplied portals/corridor envelope,
truck maneuver chain, loading face, entrances, constraints, legend, title
block, XML validity, security tokens, concave-site projection, source-hash
binding, and two-run byte/hash determinism.

```ini
P3_SVG_PROJECTION_IMPLEMENTED=true
SVG_RENDERABLE=true
SVG_DETERMINISTIC=true
MCP_TOOL_7_IMPLEMENTED=false
FRONTEND_INTEGRATION=false
PDF_EXPORT_IMPLEMENTED=false
DXF_EXPORT_IMPLEMENTED=false
P4_AUTHORIZED=false
P5_AUTHORIZED=false
```
