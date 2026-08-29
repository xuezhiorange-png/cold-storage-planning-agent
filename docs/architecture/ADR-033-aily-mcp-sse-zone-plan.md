# ADR-033: Aily MCP SSE Zone-Plan Transport

- Status: Accepted (V1.1 P5 inbound MCP)
- Date: 2026-08-29
- Context: V1.1 P0 delivered `POST /api/v1/aily/v1/zone-plan`. P4 runbook
  told operators to import OpenAPI as a custom connector. Charles opened
  豆包工作伙伴「程学致的智能伙伴」and found only 人设 / 技能 / 模型 / 安全.
  技能 → 工具 → 自定义工具 is **添加自定义 MCP 工具** (MCP / SSE). There is
  no connector tab and no OpenAPI yaml upload. Charles authorized wrapping
  the existing zone kernel as remote MCP.

## Decision

### 1. Product surface is MCP SSE

豆包工作伙伴 custom tools speak MCP over SSE. Operators paste:

`{origin}/api/v1/aily/v1/mcp/sse`

into 添加自定义 MCP 工具. They must not paste the REST zone-plan URL.

OpenAPI import remains a **different product** (Aily 创建平台 Workflow /
Smartflow). This repository does not guess that console URL.

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
to SSE GET and messages POST, same as REST. Unset remains open. This is
not production RBAC.

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
