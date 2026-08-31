# V1.8 豆包工作伙伴五阶段预览 MCP 接入操作手册

本手册供 Charles 在**豆包工作伙伴**里配置 V1.8 五阶段对话预览（分区温度/层高 + 五项冷量）。
V1.7 手册 `docs/runbooks/v17-doubao-aily-connector.md` 与技能 `docs/contracts/aily/v1.7/**`
保持冻结历史；本文件描述 V1.8 增量。飞书请改粘贴 V1.8 技能。

## 范围与边界

- 五阶段预览是**入站传输**，不是第二套内核；`persisted: false`；不是 Transaction B。
- `FORMULA_RECUT_AUTHORIZED=NO`：本版不授权新的公式重切。V1.5 墙/屋面几何绑定保持已发布。
- `ZONE_TEMPERATURE_CATALOG_RECUT=YES`：室内设计温度取分区规划温区**低端**（8 / 1 / −18 ℃）。
- `ZONE_HEIGHT_CATALOG_RECUT=YES`：九个制冷分区层高 **4.0 m**。
- `ZONE_PRODUCT_MASS_CATALOG_RECUT=NO`：货品质量仍每区 20 t/天。
- **冷量**：分区冷量按内核五项加总（传热 / 产品 / 渗透 / 内部 / 化霜 + 小计），
  并回写室内设计温度与层高，与工作台 `COOLING_ZONE_COLUMNS` 同一组字段。成功标志：`floor_area_from_zone_plan: true`，
  `envelope_wall_roof_from_plan: true`，`formula_recut_authorized: true`。
  表注须含：分区冷量按内核五项加总；地板、墙、屋面来自分区几何（正方形平面 + 演示层高）；
  U 值与设计温度仍为演示目录；室内设计温度取分区规划温区低端；层高 4.0 m。
- **设备**：内存字段拷贝冷负荷 `subtotal_load_kw_r` → `design_cooling_load_kw_r`（仍只绑小计）。
- **装机功率**：压缩机电气 kW(e) 来自设备 `total_compressor_input_power_kw_e`
  （`power_from_demo_catalog: false`），**不是** kW(r)/COP。
  蒸发/冷凝风机电气来自 v05 演示目录（10 / 8 kW(e)），不是设备结果，需复核。
  不从设备发明风机 kW(e)（`FAN_KW_FROM_EQUIPMENT=NO`）。
- **投资**：面积与功率来自分区合计 + 装机功率（`investment_from_demo_catalog: false`）。
- `AILY_OUTBOUND_LIVE_SESSION=NO`：本仓库不会打开飞书出站会话。
- 不扩展 `/api/v1/agent/**`。不暴露 `mark_reviewed` / `approve`。
- 豆包负责 NLP；本系统只接受五个 KEY，不解析聊天原文。

## 传输地址（与 V1.6 相同）

```text
MCP Streamable HTTP: {ORIGIN}/api/v1/aily/v1/mcp/sse
传输方式：Streamable HTTP（不要选 SSE）
公网隧道指向 127.0.0.1:8000，不要指 Vite :5173
```

REST（可选一次性五表）：

```text
POST {ORIGIN}/api/v1/aily/v1/zone-plan
POST {ORIGIN}/api/v1/aily/v1/concept-preview
GET  {ORIGIN}/api/v1/demo/power-fan-catalog
```

## MCP 工具列表（`tools/list` 顺序）

1. `preview_zone_plan` — 分区规划（对话第一步）
2. `preview_cooling_load` — 冷负荷（分区五项 + 地板/墙/屋面来自分区几何；U 值演示目录）
3. `preview_equipment` — 设备能力
4. `preview_installed_power` — 装机功率（压缩机来自设备电气；风机来自 v05 目录）
5. `preview_investment` — 投资估算（来自分区+功率）

五个工具共用同一五个 KEY inputSchema；`validate_input=false`；可选
`X-Aily-Connector-Key` 与 V1.6 相同。

## 技能包

- `docs/contracts/aily/v1.8/doubao-skill.v1.md`（粘贴到豆包技能）
- `docs/contracts/aily/v1.8/doubao-skill.v1.json`（机器可读元数据）

历史冻结：`docs/contracts/aily/v1.7/**`、`docs/runbooks/v17-doubao-aily-connector.md`。

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

`preview_cooling_load` 的 description 应含「分区冷量按内核五项加总」。
`preview_installed_power` 的 description 应含 v05 演示目录。

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

响应 `ok: true`，`floor_area_from_zone_plan` 为 true，`envelope_wall_roof_from_plan` 为 true，
`formula_recut_authorized` 为 true；`markdown_table` 含正方形平面 + 演示层高、U 值演示目录，
以及「分区冷量按内核五项加总」「温区低端」「4.0 m」。`extra_tables` 分区表列须含室内设计温度、层高、传热 / 产品 / 渗透 / 内部 / 化霜 / 小计。

### 3. tools/call — equipment / power

将 `name` 换为 `preview_equipment` 或 `preview_installed_power`，同样五个 KEY。
设备 `compressor_operating_capacity_kw` 应大于 0；功率 `total_installed_power_kw_e` 应大于 0，
且 `power_from_demo_catalog` 为 **false**（压缩机来自设备，不是 120 kW(e) 演示目录）。
功率 `markdown_table` / caption 应含：**蒸发/冷凝风机电气来自 v05 演示目录（10 / 8 kW(e)）**。

### 4. tools/call — investment

将 `name` 换为 `preview_investment`，同样五个 KEY；应返回投资表、`requires_review: true`，
且 `investment_from_demo_catalog` 为 **false**。

### 5. REST concept-preview

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

应返回 `reply_kind: concept_preview`，`stages` 含 zone / cooling_load / equipment / power / investment；
顶层 `floor_area_from_zone_plan: true`，`envelope_wall_roof_from_plan: true`，
`formula_recut_authorized: true`，`persisted: false`。
冷量分区 extra table 与工作台同一组五项字段。
功率表注与工作台五阶段风机叶子同为 v05 的 10 / 8 kW(e)。

### 6. GET fan catalog

```bash
curl -sS "${ORIGIN}/api/v1/demo/power-fan-catalog"
```

应返回 `source_type: demo`，`requires_review: true`，蒸发风机 `10.0`，冷凝风机 `8.0`。

## 向用户说明（豆包话术）

- 概念设计、需复核、演示系数、不是施工图。
- 冷量：**分区冷量按内核五项加总**；**地板、墙、屋面来自分区几何（正方形平面 + 演示层高）**；
  U 值与设计温度仍为演示目录；室内设计温度取分区规划温区低端（8 / 1 / −18 ℃），层高 4.0 m，货品目标温度与室内设计温度相同，货品质量仍为 v05 演示目录，需复核。
- 设备：内存拷贝冷负荷分区 subtotal，不是二次算 kW。
- 功率：压缩机电气来自设备结果，不是 kW(r)/COP；**蒸发/冷凝风机电气来自 v05 演示目录（10 / 8 kW(e)），不是设备结果，需复核。**
- 投资：面积与功率来自分区与装机功率，不是演示占位。
