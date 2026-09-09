# V2.1 豆包工作伙伴工厂功率 MCP 接入手册

本手册用于配置 V2.1 的入站 Streamable HTTP MCP。V1.8 手册
`docs/runbooks/v18-doubao-aily-connector.md` 保持冻结，不要覆盖或修改它。

## 范围与边界

- V2.1 新增第 6 个 MCP 工具 `preview_factory_power`。
- 五个既有工具的顺序、输入和语义不变；`preview_installed_power` 仍是五阶段装机功率。
- 用户只提供五个业务 KEY；不要要求或发送任何工程面积。
- 后端从 canonical zone-plan 重放/复用上游结果，经 P1 adapter 调用
  `factory_power_estimation@2.0.0-p1`，MCP 不重算工程值。
- 结果是概念设计阶段估算工厂电功率，单位 `kW`，`requires_review=true`；不是
  `kWh`、日/月耗电量、电费、电表计量值、变压器选型、正式配电设计、施工图、短路
  计算、电缆选型或保护整定。
- 本仓库不发起 outbound live Aily session，不执行部署。

## MCP 地址

```text
MCP URL: {ORIGIN}/api/v1/aily/v1/mcp/sse
Transport: Streamable HTTP
Content-Type: application/json
```

配置时使用 POST JSON-RPC。不要把地址配置成 GET SSE；legacy GET SSE 只是兼容
传输路径。公网隧道如使用本地服务，应指向后端 `127.0.0.1:8000`，不是前端
Vite `:5173`。

## 工具顺序与输入

`tools/list` 必须精确返回以下顺序：

```text
1 preview_zone_plan
2 preview_cooling_load
3 preview_equipment
4 preview_installed_power
5 preview_investment
6 preview_factory_power
```

第 6 个工具 description 应出现“估算工厂电功率”、`kW`、概念设计和需复核提示。
六个工具都使用五个 KEY schema：`additionalProperties=false`。

允许的 key 只有：

```text
daily_inbound_mass_kg
finished_storage_days
frozen_storage_days
main_packaging_storage_days
auxiliary_packaging_storage_days
```

禁止发送 `factory_area_m2`、`cold_storage_area_m2`、`refrigerated_area_m2`、
`total_area_m2`、`zone_plan`、`chat_text` 或任意未知字段。多余字段即使五个 KEY
齐全，也会收到 `MCP_INPUT_SCHEMA_REJECTED`，不要删除后静默重试。

## 自检 1：tools/list

```bash
curl -sS -X POST "${ORIGIN}/api/v1/aily/v1/mcp/sse" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

核对 `result.tools[*].name` 与上面的六项顺序一致；核对第 6 项的
`inputSchema.required` 正好是五个 KEY，且 `additionalProperties` 为 `false`。

## 自检 2：preview_factory_power

用户示例：每天 20 吨、成品 7 天、冻果 10 天、主包材 4 天、辅包材 12 天。豆包
只发送以下 JSON，不发送面积；不要传面积：

```bash
curl -sS -X POST "${ORIGIN}/api/v1/aily/v1/mcp/sse" \
  -H 'Content-Type: application/json' \
  -d '{
    "jsonrpc":"2.0",
    "id":3,
    "method":"tools/call",
    "params":{
      "name":"preview_factory_power",
      "arguments":{
        "daily_inbound_mass_kg":20000,
        "finished_storage_days":7,
        "frozen_storage_days":10,
        "main_packaging_storage_days":4,
        "auxiliary_packaging_storage_days":12
      }
    }
  }'
```

成功时应有：

```text
ok=true
reply_kind=factory_power_estimation_table
available=true
calculator_identity=factory_power_estimation@2.0.0-p1
canonical_result_hash=sha256:<64 hex>
requires_review=true
persisted=false
markdown_table 非空
details 非空
summary 非空
```

把 `markdown_table` 原样展示，并保留 `summary` 的关键字段。不要在豆包侧重新
加总、round、换算或推导功率。

## 意图路由

“工厂电功率”“估算工厂电功率”“工厂总用电功率”“这个厂大概需要多少电功率”或
“整个加工厂估算功率”调用 `preview_factory_power`。 “装机功率”“五阶段装机功率”
或“压缩机和风机装机功率”调用 `preview_installed_power`。只有“功率”时保留既有
V1.8 语义，无法判定就澄清装机功率还是估算工厂总电功率；服务器不解析中文聊天。

## 错误处理

- 缺少五 KEY：使用 `MISSING_ENGINEERING_PARAMETER` 的 `missing_keys` 和
  `ask_operator` 追问原业务参数，不追问面积。
- 未知/面积/聊天字段：使用 `MCP_INPUT_SCHEMA_REJECTED`，`missing_keys=[]`、
  `ask_operator=""`。
- 后端 authority blocker：保留原始 `code`、`message`、`details`，不要 fallback。
- `V20_FACTORY_POWER_CANONICAL_RESULT_UNAVAILABLE`：结果不可用，不补造任何表格、
  summary 或 hash。
