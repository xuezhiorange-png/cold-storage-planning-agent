# V1.2 豆包工作伙伴五阶段预览 MCP 接入操作手册

本手册供 Charles 在**豆包工作伙伴**里配置 V1.2 五阶段对话预览。
V1.1 手册 `docs/runbooks/v11-doubao-aily-connector.md` 保持冻结；本文件仅描述 V1.2 增量。

## 范围与边界

- 五阶段预览是**入站传输**，不是第二套内核；`persisted: false`；不是 Transaction B。
- `FORMULA_RECUT_AUTHORIZED=NO`：**冷量仍用演示围护**，不是分区面积自动带入冷负荷。
- `AILY_OUTBOUND_LIVE_SESSION=NO`：本仓库不会打开飞书出站会话。
- 不扩展 `/api/v1/agent/**`。不暴露 `mark_reviewed` / `approve`。
- 豆包负责 NLP；本系统只接受五个 KEY，不解析聊天原文。

## 传输地址（与 V1.1 相同）

```text
MCP Streamable HTTP: {ORIGIN}/api/v1/aily/v1/mcp/sse
传输方式：Streamable HTTP（不要选 SSE）
公网隧道指向 127.0.0.1:8000，不要指 Vite :5173
```

REST（可选一次性五表）：

```text
POST {ORIGIN}/api/v1/aily/v1/zone-plan
POST {ORIGIN}/api/v1/aily/v1/concept-preview
```

## MCP 工具列表（`tools/list` 顺序）

1. `preview_zone_plan` — 分区规划（对话第一步）
2. `preview_cooling_load` — 冷负荷（演示围护）
3. `preview_equipment` — 设备能力
4. `preview_installed_power` — 装机功率
5. `preview_investment` — 投资估算

五个工具共用同一五个 KEY inputSchema；`validate_input=false`；可选
`X-Aily-Connector-Key` 与 V1.1 相同。

## 技能包

- `docs/contracts/aily/v1.2/doubao-skill.v1.md`（粘贴到豆包技能）
- `docs/contracts/aily/v1.2/doubao-skill.v1.json`（机器可读元数据）

## 自检清单

### 1. tools/list

```bash
curl -sS -X POST "${ORIGIN}/api/v1/aily/v1/mcp/sse" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

必须 HTTP 200，且 `tools` 名称顺序为：

`preview_zone_plan`, `preview_cooling_load`, `preview_equipment`,
`preview_installed_power`, `preview_investment`

### 2. tools/call — cooling

```bash
curl -sS -X POST "${ORIGIN}/api/v1/aily/v1/mcp/sse" \
  -H 'Content-Type: application/json' \
  -d '{
    "jsonrpc":"2.0","id":3,"method":"tools/call",
    "params":{"name":"preview_cooling_load","arguments":{
      "daily_inbound_mass_kg":20000,
      "finished_storage_days":7,
      "frozen_storage_days":10,
      "main_packaging_storage_days":4,
      "auxiliary_packaging_storage_days":12
    }}
  }'
```

响应 `ok: true`，`markdown_table` 含演示围护说明；`envelope_from_zone_area` 为 false。

### 3. tools/call — investment

将 `name` 换为 `preview_investment`，同样五个 KEY；应返回投资表与 `requires_review: true`。

### 4. REST concept-preview

```bash
curl -sS -X POST "${ORIGIN}/api/v1/aily/v1/concept-preview" \
  -H 'Content-Type: application/json' \
  -d '{
    "daily_inbound_mass_kg": 20000,
    "finished_storage_days": 7,
    "frozen_storage_days": 10,
    "main_packaging_storage_days": 4,
    "auxiliary_packaging_storage_days": 12
  }'
```

应返回 `reply_kind: concept_preview`，`stages` 含 zone / cooling_load / equipment / power / investment。

## 向用户说明（豆包话术）

- 概念设计、需复核、演示系数、不是施工图。
- 冷量：**演示围护**，不是把分区规划面积自动带进冷负荷。
