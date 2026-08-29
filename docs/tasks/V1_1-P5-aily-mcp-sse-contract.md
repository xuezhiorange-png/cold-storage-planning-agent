# V1.1 P5 Aily MCP Streamable HTTP Zone-Plan Transport Contract

**Status:** Implementation — 豆包工作伙伴 custom tools are MCP Streamable HTTP  
**Authority:** Charles 2026-08-29: 详情页只有 MCP；飞书「请求地址」对
`/api/v1/aily/v1/mcp/sse` **POST JSON-RPC**；传输方式必须选 **Streamable HTTP**；
GET SSE / `event: endpoint` / `POST /messages/` 不是飞书路径  
**Previous release:** `v1.0.0`  
**Base `main` SHA:** `fa55ce2` (MCP SSE mount already on `main`; this package
switches the Feishu path to Streamable HTTP `json_response=true`)  
**Target branch:** `cursor/v11-aily-mcp-streamable-http-742e`

Companion: `docs/tasks/V1_1-P0-aily-zone-plan-connector-contract.md`,
`docs/architecture/ADR-033-aily-mcp-sse-zone-plan.md`.

## 0. Governance

```text
TASK=V11_P5_AILY_MCP_STREAMABLE_HTTP_R1
GOVERNANCE_OWNER=V1.1
PREVIOUS_RELEASE=v1.0.0
BASE_MAIN_SHA=fa55ce2
TARGET_BRANCH=cursor/v11-aily-mcp-streamable-http-742e
TARGET_FILE=docs/tasks/V1_1-P5-aily-mcp-sse-contract.md

V11_P5_IMPLEMENTATION_AUTHORIZED=YES
AILY_OUTBOUND_LIVE_SESSION=NO
DO_NOT_BUMP_ZONE_PLAN_VERSION=YES
KEEP_CALCULATOR_IDENTITY=cold_room_zone_plan@1.0.0
KEEP_OPERATOR_SCHEMA=OperatorProcessInputV1@1.1.0
FORMULA_RECUT_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT=NO
EQUIPMENT_FORMULA_RECUT=NO
INSTALLED_POWER_FORMULA_RECUT=NO
INVESTMENT_FORMULA_RECUT=NO
AGENT_TO_ENGINEERING_VALUE=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
MARK_REVIEWED_AS_MODEL_TOOL=NO
EXTEND_API_V1_AGENT_FOR_AILY=NO
IMPLEMENT_FEISHU_SDK_OUTBOUND=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
FEISHU_MCP_TRANSPORT=STREAMABLE_HTTP
JSON_RESPONSE=true
GET_SSE_IS_NOT_FEISHU_PATH=YES
```

## 1. Objective

On unmodified `create_app`:

```text
豆包工作伙伴 (NLP)
 → 技能 → 工具 → 添加自定义 MCP 工具
 → 传输方式 = Streamable HTTP（不要选 SSE）
 → POST JSON-RPC https://<origin>/api/v1/aily/v1/mcp/sse
   initialize → tools/list → tools/call
 → 响应 = 完整 JSON（json_response=true；不是长连接 SSE）
 → MCP tool preview_zone_plan (five KEY)
 → invoke_preview_zone_plan_tool
 → existing preview_zone_plan / cold_room_zone_plan@1.0.0
 → JSON + markdown_table
```

REST `POST /api/v1/aily/v1/zone-plan` stays. MCP does not replace the kernel;
it is another inbound transport. Vue and reports are unchanged.

This package does **not** open a live Feishu outbound session from this repo.

GET `/api/v1/aily/v1/mcp/sse` plus POST `/messages/` may remain as optional
legacy SSE. They are **not** the Feishu 请求地址. trycloudflare buffers GET SSE
to HTTP 200 + 0 bytes; Feishu then reports `generic call psm=lark.aily.canvas...`.

## 2. Operator KEY (unchanged)

```text
zone_planning_inputs.daily_inbound_mass_kg
zone_planning_inputs.finished_storage_days
zone_planning_inputs.frozen_storage_days
zone_planning_inputs.main_packaging_storage_days
zone_planning_inputs.auxiliary_packaging_storage_days
```

**吨 always means per day.** 豆包 owns semantics. Missing KEY → `ok=false`
plus `ask_operator`. No silent defaults. Chat `message` is not a tool field.

## 3. MCP

- Feishu transport: **Streamable HTTP** (`json_response=true`)
- 请求地址: `https://<origin>/api/v1/aily/v1/mcp/sse` (full path; no trailing slash on origin)
- Alias POST: `/api/v1/aily/v1/mcp` (same Streamable HTTP JSON-RPC)
- Feishu POSTs JSON-RPC to that URL: `initialize` → `tools/list` → `tools/call`
- Response must be complete JSON, not a long-lived SSE stream
- Tool name: `preview_zone_plan`
- Optional header `X-Aily-Connector-Key` (same as REST P3)
- Backend listens `:8000`; public tunnel must point at `127.0.0.1:8000`, not Vite `:5173`

Do not paste `POST /api/v1/aily/v1/zone-plan` into the MCP URL field.
Do not paste a bare origin. Do not treat the URL as GET SSE (`event: endpoint`
then `POST /messages/`). Do not upload OpenAPI on the partner detail page
(that entry does not exist).

Self-check (ORIGIN with no trailing slash). GET SSE alone does not count:

```text
curl -sS -X POST "${ORIGIN}/api/v1/aily/v1/mcp/sse" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"0.1"}}}'
```

Then POST `tools/list` to the same URL. Must be HTTP 200 and list `preview_zone_plan`.

## 4. Non-goals

```text
AILY_OUTBOUND_LIVE_SESSION=NO
COOLING_LOAD_FORMULA_RECUT=NO
EQUIPMENT_FORMULA_RECUT=NO
INSTALLED_POWER_FORMULA_RECUT=NO
INVESTMENT_FORMULA_RECUT=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
PRODUCTION_RBAC_CLAIM=NO
AGENT_TO_ENGINEERING_VALUE=NO
EXTEND_API_V1_AGENT_FOR_AILY=NO
```

Do not bump `cold_room_zone_plan` `VERSION`. Do not reopen #11 / #13 / #17 /
#176 / #20. Do not move `v0.9.0` / `v1.0.0`. Do not recut the zone-plan kernel.

## 5. Allowlist (this package)

```text
V11_P5_FILE_ALLOWLIST
backend/pyproject.toml
backend/uv.lock
backend/src/cold_storage/bootstrap/app.py
backend/src/cold_storage/modules/aily/api/mcp_sse.py
backend/src/cold_storage/modules/aily/application/mcp_zone_plan.py
backend/tests/unit/test_v11_aily_mcp_zone_plan.py
backend/tests/unit/test_v11_aily_mcp_protocol.py
backend/tests/integration/test_v11_aily_mcp_sse_http.py
backend/tests/architecture/test_v11_p5_aily_mcp_sse_contract.py
docs/tasks/V1_1-P5-aily-mcp-sse-contract.md
docs/architecture/ADR-033-aily-mcp-sse-zone-plan.md
docs/runbooks/v11-doubao-aily-connector.md
docs/contracts/aily/v1.1/README.md
docs/contracts/aily/v1.1/doubao-skill.v1.md
docs/contracts/aily/v1.1/doubao-skill.v1.json
docs/tasks/V1_1-version-plan.md
docs/TECH_DEBT.md
```

## 6. Expert decisions

| ID | Decision |
| --- | --- |
| V11-P5-E1 | 豆包工作伙伴 custom tools are MCP Streamable HTTP (complete JSON), not GET SSE and not OpenAPI import |
| V11-P5-E2 | MCP tool calls existing `preview_zone_plan`; no formulas in the MCP layer |
| V11-P5-E3 | 吨 always means per day; 豆包 owns semantics |
| V11-P5-E4 | Outbound live Feishu session stays off |
| V11-P5-E5 | trycloudflare / 飞书云 cannot use GET SSE; tunnel must target `:8000` |

## 7. Closed issues

#11 / #13 / #17 / #176 / #20 stay CLOSED.
