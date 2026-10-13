# R14 — parameterized Truck preview, MCP Tool 8

This round appends `preview_truck` after the original seven tools in the same
`cold-storage-zone-plan` MCP server. Historical P4 delivered seven tools; that
documented fact and all seven original input schemas/descriptions are preserved.

```ini
MCP_TOOL_COUNT=8
MCP_TOOL_8_NAME=preview_truck
PUBLIC_MCP_DEPLOYED=false
DOUBAO_CLIENT_IMAGE_ACCEPTANCE=NOT_EVALUATED
REAL_XINZHAO_TRUCK_INPUT=BLOCKED
REAL_XINZHAO_P2D_COMPLETE=false
```

## Structured input

The package-owned `aily/application/truck_preview.schema.json` describes the
existing R13 extension and the actual unchanged P1F/Option C nested fields. It
does not invent dimensions, safety clearances, maneuver templates or mandatory
engineering inputs. The Domain remains the exact authoritative validator.
Every mandatory top-level field has a Chinese MCP description.

Provide `schema_version`, `mode`, `vehicle_type`, `vehicle_body`,
`vehicle_source_reference`, `truck_access`, `truck_maneuver`, `entrance`,
`shipping_loading_face`, `loading_face_reference`, `site_geometry`, `evidence`,
`approval_reference`. `additionalProperties=false`. See R13's
[parameter documentation](V2_2_2-R13-parameterized-truck-preview.md).

Document limits remain 32 files, 1 MiB decoded bytes/file, 8 MiB total. MCP
arguments also retain the R13 CLI's 12,000,000 UTF-8 JSON byte bound. No inputs
or complete Base64 are logged by the adapter. Errors expose codes, limited
field identifiers and Chinese prompts, not exception stacks or uploaded bytes.

`SYNTHETIC_TEST` is software testing only. `OWNER_PROJECT` must supply actual
documents and matching approval records. Source integrity never authenticates
reviewer identity or grants real project approval automatically.

## Call through existing authenticated Streamable HTTP

The mount and connector key gate are unchanged. Substitute the already-running
local service URL, and supply the JSON-RPC request in `truck-call.json`:

```sh
curl -X POST http://127.0.0.1:8000/api/v1/aily/v1/mcp/sse \
  -H 'Content-Type: application/json' \
  -H "X-Aily-Connector-Key: $R14_CONNECTOR_KEY" \
  --data-binary @truck-call.json
```

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{
  "protocolVersion":"2024-11-05","capabilities":{},
  "clientInfo":{"name":"truck-preview-client","version":"1.0"}}}
```

Then `tools/list`, and `tools/call` with `params.name="preview_truck"` and
the R13 structured input in `params.arguments`. Actual runnable synthetic
input and call request are retained in the R14 evidence archive. Nothing here
deploys or changes the public server or proves a Doubao client rendered an image.

## Output and acceptance boundaries

`ok=true` means invocation and input validation completed. It does **not** imply
`engineering_pass=true`: native search exhaustion and personnel engineering
review remain their actual states. Input errors return `ok=false`, an unchanged
native error code where available, and Chinese `ask_operator`.

`result` preserves the complete original R13 result, including its original
`canonical_result_hash`. The wrapper's `calculation_hash` only references that
hash; it is not a digest of the changed MCP wrapper. SVG bytes are taken verbatim
from R13. `drawing.svg_sha256` independently hashes their UTF-8 bytes. No drawing
is invented for failed or review-required cases. Both `structuredContent` and
JSON-compatible `TextContent` carry the result.

No Truck algorithm, layouts, engineering Authority, official search budgets,
typed-Site/P2D validation, original CLI, or original seven-tool business flow is
changed. Legacy SSE routes remain available. Local HTTP E2E is not public
deployment, real project acceptance, Truck dynamics simulation or Server Replay.
