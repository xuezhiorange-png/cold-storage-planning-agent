# ADR-033: Aily MCP Streamable HTTP Zone-Plan Transport

- Status: Accepted (V1.1 P5 inbound MCP; Feishu path corrected 2026-08-29)
- Date: 2026-08-29
- Context: V1.1 P0 delivered `POST /api/v1/aily/v1/zone-plan`. P4 runbook
  first described OpenAPI import, then MCP. An earlier P5 mount spoke MCP
  over GET SSE (`event: endpoint` then `POST /messages/`). Charles opened
  豆包工作伙伴「程学致的智能伙伴」and found only 人设 / 技能 / 模型 / 安全.
  Custom tools are **添加自定义 MCP 工具**. There is no connector tab and no
  OpenAPI yaml upload. On a public HTTPS origin Charles confirmed Feishu
  does **not** GET SSE: it POSTs JSON-RPC to the pasted URL and requires a
  complete JSON response (Streamable HTTP). trycloudflare buffers GET SSE
  into HTTP 200 with 0 bytes; Feishu then fails with
  `generic call psm=lark.aily.canvas...`.

## Decision

### 1. Product surface is MCP Streamable HTTP

豆包工作伙伴 custom tools speak MCP over **Streamable HTTP**. Operators paste
the full path:

`https://<origin>/api/v1/aily/v1/mcp/sse`

into 添加自定义 MCP 工具, and must set 传输方式 to **Streamable HTTP**.
They must not paste the REST zone-plan URL, a bare origin, or treat the
URL as GET SSE.

Feishu POSTs JSON-RPC to that address: `initialize` → `tools/list` →
`tools/call`. The server must answer with complete JSON
(`json_response=true` / `is_json_response_enabled=True`), not a long-lived
SSE stream.

OpenAPI import remains a **different product** (Aily 创建平台 Workflow /
Smartflow). This repository does not guess that console URL.

GET `/sse` plus POST `/messages/` may stay as optional legacy SSE. They are
not the Feishu 请求地址. SSE is unavailable through trycloudflare and Feishu
cloud for this connector.

### 2. MCP is a second inbound transport, not a second kernel

The only model-visible tool is `preview_zone_plan`. It calls
`invoke_preview_zone_plan_tool` → existing `preview_zone_plan` →
`cold_room_zone_plan@1.0.0`. Do not bump that `VERSION`. API/MCP layers
must not import `cold_storage.modules.calculations` or contain formulas.

REST `POST /api/v1/aily/v1/zone-plan` stays for curl and Workflow
connectors.

### 3. Same five KEY, same fail-closed rules

吨 always means per day. 豆包 owns NLP. Missing KEY return `ok=false` with
`ask_operator`. Chat utterances are not tool fields. `mark_reviewed` /
`approve` are not tools. `/api/v1/agent/**` is not extended.

### 4. Outbound live session stays off

`AILY_OUTBOUND_LIVE_SESSION=NO`. This package does not create Feishu
sessions, does not call Feishu SDKs, and does not register the MCP URL
inside Feishu from this app. Operators paste the URL by hand.

### 5. Optional transport secret

`X-Aily-Connector-Key` / `COLD_STORAGE_AILY_CONNECTOR_SHARED_SECRET` apply
to Streamable HTTP POST, legacy SSE GET, and messages POST, same as REST.
Unset remains open. This is not production RBAC.

### 6. Public tunnel targets the backend, not Vite

The API listens on `:8000`. A public tunnel must forward to
`127.0.0.1:8000`. Pointing the tunnel at Vite `:5173` stalls streams
through the frontend proxy.

## Consequences

- 豆包 can call the zone kernel from the workbench MCP dialog.
- The origin must be HTTPS-reachable from Feishu cloud; `127.0.0.1` will
  not work for the tenant.
- Cooling/equipment/power/investment formula recut remains out of scope.

## Alternatives rejected

1. Keep telling operators to import OpenAPI on the partner detail page —
   that button does not exist.
2. Let 豆包 calculate area in the prompt — forbidden
   (`AGENT_TO_ENGINEERING_VALUE=NO`).
3. Implement MCP inside Domain or the calculations module — forbidden
   dependency direction; MCP SDK stays in `aily/api`.
4. Extend `/api/v1/agent/**` — rejected by ADR-027.
5. Use GET SSE as the Feishu 请求地址 — Feishu POSTs JSON-RPC; trycloudflare
   buffers GET SSE to an empty 200.
