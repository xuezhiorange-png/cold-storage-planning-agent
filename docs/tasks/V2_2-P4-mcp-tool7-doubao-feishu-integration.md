# V2.2 P4 — MCP Tool 7 / Doubao / Feishu integration

## Current implementation snapshot

This document is the P4 implementation record. Earlier P0–P3 authorization
snapshots remain historical and are not rewritten here.

```ini
TASK_ID=V2_2_P4_MCP_TOOL7_DOUBAO_FEISHU_INTEGRATION_R1
BASE_MAIN_SHA=cd0a2cc16a9b49296a25b398d4a17dbd4f63b67b
TARGET_VERSION=v2.2.0
P3_COMPLETE=YES
P4_AUTHORIZED=YES
P4_STATUS=IMPLEMENTED_DRAFT_REVIEW

MCP_TOOL_COUNT=7
MCP_TOOL_7_NAME=preview_site_layout
MCP_TOOL_7_POSITION=7
MCP_TOOL_7_IMPLEMENTED=YES
EXISTING_SIX_TOOL_ORDER_PRESERVED=YES
EXISTING_SIX_TOOL_CONTRACT_PRESERVED=YES
EXISTING_FIVE_KEY_SCHEMA_PRESERVED=YES

SITE_LAYOUT_PROJECT_INPUT_USED=YES
BACKEND_ZONE_PLAN_AUTHORITY_USED=YES
P1_DIMENSION_ACCESS_HANDOFF_USED=YES
P2_VALIDATED_LAYOUT_USED=YES
P3_SVG_PROJECTION_USED=YES
MCP_STREAMABLE_HTTP_REUSED=YES
NO_CHAT_PARSING=YES
NO_ENGINEERING_FORMULAS_IN_P4=YES

SITE_LAYOUT_RESULT_IDENTITY=site_validated_layout@1.0.0
SVG_PROJECTION_IDENTITY=validated-layout-svg-projection@1.0.0
P4_INPUT=FIVE_BUSINESS_KEYS_PLUS_SITE_CONSTRAINTS_AND_TRUCK_ACCESS
MCP_INPUT_AUTHORITY=FIVE_BUSINESS_KEYS_PLUS_SITE_CONSTRAINTS_AND_TRUCK_ACCESS
P4_INPUT_ADDITIONAL_PROPERTIES=false
P4_CALLER_SUPPLIED_ENGINEERING_AUTHORITY=REJECTED
P4_STATELESS_ZONE_REPLAY=YES
P4_RESULT_PERSISTED=false
P4_WIRING_AND_TRANSPORT_IMPLEMENTED=YES
P4_PRODUCTION_FULL_PASS=NO
P4_COMPLETE=NO
P4_BLOCKER=EXISTING_P2C_P2D_PACKAGING_SORTING_STRAIGHT_ROUTE_MISMATCH

P5_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_AUTHORIZED=NO
RELEASE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## Tool contract

The existing MCP surface remains, in order:

1. `preview_zone_plan`
2. `preview_cooling_load`
3. `preview_equipment`
4. `preview_installed_power`
5. `preview_investment`
6. `preview_factory_power`

P4 appends `preview_site_layout` at position 7. The first six tools retain
their five business-key schema and invocation semantics. Tool 7 accepts those
same five keys plus `site_constraints` and a complete project-bound
`truck_access` object. It rejects caller-supplied areas, zone plans, hashes,
placements, validated layouts, SVG, chat text, and unknown top-level fields.

The server continues to expose the existing Streamable HTTP paths:

* `/api/v1/aily/v1/mcp/sse`
* `/api/v1/aily/v1/mcp`

The existing connector-key check and the five-key missing-parameter behavior
are unchanged. Missing project inputs fail closed; the application does not
invent a rectangular site, vehicle dimensions, maneuver templates, or route.

## Authority chain

Tool 7 is an application/transport composition only:

```text
five business keys
  -> existing zone-planning adapter
  -> P1 dimension/access handoff
  -> SiteLayoutProjectInputV1 inputs
  -> P2 placement and access/truck validation
  -> site_validated_layout@1.0.0
  -> validated-layout-svg-projection@1.0.0
  -> MCP structured response
```

P4 does not duplicate zone-area, dimension, placement, adjacency, routing,
truck, building-footprint, or SVG formulas. The P2 and P3 authorities remain
fail-closed and their result/provenance hashes are returned to the consumer.
The SVG is a projection of the validated structured layout JSON, not a new
calculation authority. P3's runtime theme validation, mapping hash check,
static-XML boundary, and deterministic output remain in force.

The P2 search and route budgets used by this boundary are deterministic
orchestration limits. A search failure remains an authoritative failure; P4
does not fabricate a layout or turn a partial result into a success.

## Response and review semantics

On a validated input, the response exposes the P2 layout identity, source
hashes, twelve zones, building footprint, access observations, entrances,
loading-face and truck validation data, together with the P3 SVG, viewBox and
SVG hash. It marks the result as concept design, `requires_review=true`, and
not a construction drawing. The response is not persisted.

The five existing preview tools are still the normal five-stage workflow.
`preview_site_layout` is a supplemental seventh capability; it does not add a
CalculationType, change the concept-preview stages, or replace
`preview_installed_power`.

## Evidence boundary

The focused P4 tests exercise the real application boundary and use the
existing P2D full-pass representative authorities as a controlled downstream
fixture. The production boundary still invokes the real P2C/P2D functions with
bounded budgets and propagates their failures. No P2/P3 runtime behavior was
changed to make P4 pass.

The real end-to-end replay through the current P2C placement search and P2D
routing path is not a full-pass input at this baseline: the canonical P2C
candidate is rejected by the existing
`PACKAGING_SORTING_STRAIGHT_ROUTE_REQUIRED` rule. This is an upstream P2C/P2D
compatibility blocker, so P4 reports the failure closed and does not change
placement, routing, or P3 behavior to manufacture a success.

```ini
P4_WIRING_AND_TRANSPORT_IMPLEMENTED=YES
P4_PRODUCTION_FULL_PASS=NO
P4_COMPLETE=NO
P4_BLOCKER=EXISTING_P2C_P2D_PACKAGING_SORTING_STRAIGHT_ROUTE_MISMATCH
```

P4 does not authorize P5, Ready, merge, tag, release, or deployment.
