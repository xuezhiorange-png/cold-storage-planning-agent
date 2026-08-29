# V1.1 豆包工作伙伴接入分区规划内核操作手册

本手册供 Charles 在**豆包工作伙伴**（`aily.feishu.cn` 工作伙伴详情页）里，把本系统
分区规划内核接到技能工具上。该产品的自定义工具走 **MCP 协议**，**没有**
「从 OpenAPI 导入」，详情页也**没有**「连接器」标签。

## 范围与边界

- 本系统是**冷库概念设计规划助手**，不是施工图设计、注册工程师签章或现场设备控制。
- 演示系数仍为 `source_type=demo`、`validity_status=unverified`，输出常带
  `requires_review=true`。所有数值仅供概念比选，须人工复核。
- **本手册仅描述人在飞书 UI / 豆包技能配置中的导入步骤。**
  `AILY_OUTBOUND_LIVE_SESSION=NO`：本仓库**不会**从代码侧打开飞书出站会话、**不会**实现飞书 SDK 出站调用、**不会**在 Python 中新增联网逻辑。
- 不扩展 `/api/v1/agent/**`。不声称生产 RBAC。
- 豆包负责听懂自然语言（例如「20 吨的加工厂」）；本系统**不解析聊天原文**，只接受五个 KEY 的结构化 JSON。

## 前置条件

- 本仓库已合并 V1.1 P0 inbound 连接器实现（`POST /api/v1/aily/v1/zone-plan`）。
- OpenAPI 文件路径：
  `docs/contracts/aily/v1.1/aily-to-system-zone-plan.openapi.yaml`
- 技能说明参考：
  - `docs/contracts/aily/v1.1/README.md`（§ 豆包 skill notes）
  - P2 技能包（若已合并）：
    `docs/contracts/aily/v1.1/doubao-skill.v1.md`

## 第一步：让连接器能访问 API

连接器需要能 `POST` 到本系统的 zone-plan 预览接口。

### 本地验证（开发机）

1. 安装并迁移（见 `docs/DEVELOPMENT.md`）：

   ```bash
   make install
   make migrate
   ```

2. 启动后端（默认监听 `http://127.0.0.1:8000`）：

   ```bash
   cd backend
   PYTHONPATH=src UV_CACHE_DIR=../.uv-cache uv run uvicorn cold_storage.bootstrap.app:create_app --factory --reload
   ```

3. 本地连接器 Base URL 示例：`http://127.0.0.1:8000`
   完整路径：`http://127.0.0.1:8000/api/v1/aily/v1/zone-plan`

   若豆包租户无法访问你的笔记本，请改用下方「已部署环境」；勿将本地地址当作生产 URL。

### 已部署环境

使用**你的已部署 origin**（例如 `https://your-deployment.example.com`），勿编造本仓库未提供的生产域名。

完整路径：`{你的 deployed origin}/api/v1/aily/v1/zone-plan`

确保该 origin 对飞书 / 豆包租户出站网络可达（防火墙、TLS、反向代理已放行）。

### 快速自检（curl）

五个 KEY 齐全时应返回 200 与 `markdown_table`：

```bash
curl -sS -X POST "${ORIGIN}/api/v1/aily/v1/zone-plan" \
  -H 'Content-Type: application/json' \
  -d '{
    "daily_inbound_mass_kg": 20000,
    "finished_storage_days": 7,
    "frozen_storage_days": 10,
    "main_packaging_storage_days": 4,
    "auxiliary_packaging_storage_days": 12
  }'
```

将 `ORIGIN` 换成本地或 deployed origin（无尾斜杠）。

## 第二步：豆包工作伙伴只认 MCP，不要找 OpenAPI 导入

你现在打开的「程学致的智能伙伴」详情页（人设 / 技能 / 模型 / 安全）就是对的产品。
自定义工具入口也是对的：

**技能 → 工具 → 添加工具 → 自定义工具 →「添加自定义 MCP 工具」**（MCP / SSE）

这里要填的是 **MCP 服务地址**，不能上传 OpenAPI yaml。官方说明：自定义工具走 MCP 协议
（[添加和使用 MCP](https://aily.feishu.cn/hc/1u7kleqg/fiogabrc)）。

### 不要做的事

- 不要在这个详情页找「连接器」标签或「从 OpenAPI 导入」。**没有这两个入口。**
- 不要把 `POST /api/v1/aily/v1/zone-plan` 的 REST 地址填进 MCP 对话框。那是普通 HTTP JSON
  接口，不是 MCP；填进去连不上。
- 不要把仓库里的
  `docs/contracts/aily/v1.1/aily-to-system-zone-plan.openapi.yaml`
  上传到这个对话框。

### 「从 OpenAPI 导入」在哪个产品

那是**另一个后台**：飞书智能伙伴创建平台里，给 **Workflow / Smartflow** 用的 HTTP
自定义连接器。官方文章写的入口是：

> 从 Workflow 和 Smartflow 中找到自定义连接器入口

来源：[飞书智能伙伴 Aily 之自定义连接器](https://www.feishu.cn/content/ya5j9hjw)。

低代码 / 集成平台的「集成」里也可以导入 OpenAPI/Postman，同样**不是**豆包工作伙伴详情页。
本手册**不猜测**创建平台的后台 URL。若租户没有开通创建平台 / Workflow，就不要走这条路。

### 本仓库现状（卡住的原因）

- 已有能力：REST `POST /api/v1/aily/v1/zone-plan`（可用上面 curl 自检）。
- **尚未**提供远程 MCP（SSE / Streamable HTTP）服务。所以在当前这个 UI 里，还没有可填的
  MCP 地址。
- 可选请求头 `X-Aily-Connector-Key`：环境变量 `COLD_STORAGE_AILY_CONNECTOR_SHARED_SECRET`
  未设置时接口保持开放；设置后须带该头，否则 401。MCP 尚未落地前，不必在飞书 UI 里配这个头。

要继续留在豆包工作伙伴：需要在本仓库增加一层 MCP，把五个 KEY 转到现有分区内核，再把
**公网 HTTPS 的 MCP 地址**填进「添加自定义 MCP 工具」。MCP 层不得自己算工程数。

## 第三步：映射五个 KEY（豆包侧语义，MCP 与 REST 相同）

本系统要求的五个叶子字段（与 `OperatorProcessInputV1` 一致）：

| 字段 | 含义 | 单位 |
| --- | --- | --- |
| `daily_inbound_mass_kg` | 每天进货质量 | kg/day |
| `finished_storage_days` | 成品储存天数 | day |
| `frozen_storage_days` | 冻果储存天数 | day |
| `main_packaging_storage_days` | 主包材储存天数 | day |
| `auxiliary_packaging_storage_days` | 辅包材储存天数 | day |

**吨 = 每天。** 用户口语「多少吨」一律按**吨/天**理解；由豆包换算，本系统不解析「20 吨的加工厂」等原话。

### 换算示例（与仓库测试一致，仅供说明）

| 用户说法（豆包理解） | 连接器应发送的 JSON 字段 |
| --- | --- |
| 每天 20 吨进货 | `daily_inbound_mass_kg`: `20000`（20 × 1000 kg/day） |
| 成品存 7 天 | `finished_storage_days`: `7` |
| 冻果存 10 天 | `frozen_storage_days`: `10` |
| 主包材存 4 天 | `main_packaging_storage_days`: `4` |
| 辅包材存 12 天 | `auxiliary_packaging_storage_days`: `12` |

OpenAPI 提供两种请求示例：

- `five_key_flat`：五个字段均为扁平数字（推荐连接器默认）。
- `tonne_unit_leaf`：`daily_inbound_mass_kg` 为 `{ "value": 20, "unit": "吨" }` 叶子，其余四天字段仍为数字；豆包须在调用前完成吨→kg/day 或按本系统 assembler 接受的叶子格式传值。

完整扁平示例 body：

```json
{
  "daily_inbound_mass_kg": 20000,
  "finished_storage_days": 7,
  "frozen_storage_days": 10,
  "main_packaging_storage_days": 4,
  "auxiliary_packaging_storage_days": 12
}
```

在豆包技能 / 参数抽取配置中，**禁止**把用户整句聊天原文作为 `message` 字段发给本接口；必须输出上述 KEY JSON。

## 第四步：错误处理（HTTP 400）

缺 KEY 或无效参数时，接口返回 400，body 形如：

```json
{
  "error": {
    "code": "MISSING_ENGINEERING_PARAMETER",
    "message": "OperatorProcessInputV1 five KEY are incomplete",
    "missing_keys": ["frozen_storage_days"],
    "ask_operator": "请提供：冻果储存天数"
  }
}
```

豆包行为：

1. 读取 `error.ask_operator`（若有）向用户追问缺失项。
2. 结合 `error.missing_keys` 知道缺哪些字段。
3. **不要**自行编造面积或工程数值。

若用户只发送 `{"message": "要建一个20吨的加工厂"}`，本系统会 400 并列出五个缺失 KEY——这证明聊天解析必须由豆包完成，而非本连接器。

## 第五步：成功响应——展示表格

HTTP 200 时，响应包含（节选）：

- `reply_kind`: `zone_plan_table`
- `calculator_name`: `cold_room_zone_plan`
- `calculator_version`: `1.0.0`（**勿与 zone 内核版本混淆；V1.1 不 bump 该版本**）
- `markdown_table`：Markdown 表格字符串——**原样发给用户**（分区面积、货位等）
- `table`：结构化表格对象（供 UI 二次渲染）
- `extra_tables`：附加表（若有）
- `requires_review`：常为 `true`——须告知用户「概念设计，需复核」
- `warnings`：演示系数等警告（若有）

豆包回复用户时应：

1. 优先展示 `markdown_table`。
2. 若存在 `extra_tables`，可按需摘要说明。
3. 当 `requires_review` 为 true 时，明确说明数值待工程复核，非最终施工图依据。

本预览**不持久化**项目版本（`persisted` 常为 false）；正式五阶段落库与报告导出不在本连接器范围内。

## 第六步：粘贴 / 引用豆包技能

将下列内容交给豆包技能编辑（或粘贴 P2 技能包全文，若 `doubao-skill.v1.md` 已合并）：

1. 阅读 `docs/contracts/aily/v1.1/README.md` 中「豆包 skill notes」四条原则。
2. 若存在 P2 技能包，以
   `docs/contracts/aily/v1.1/doubao-skill.v1.md` 为**既定技能文件**（P2 skill pack, if present）。
3. 技能须写明：听懂用户 → 换算五个 KEY → 调用 MCP 工具（五个 KEY JSON，不要发聊天原文）→ 展示 `markdown_table` → 标注概念设计与复核要求。MCP 落地前，这一步无法在飞书 UI 里点通。

## 概念设计声明

本连接器输出仅供冷库**概念设计比选**与分区面积预览，**不是施工图**，不能用于施工招标、消防报审或设备最终选型。演示系数未验证，须由具备资质的设计方复核。

## 相关文档

- P0 连接器契约：`docs/tasks/V1_1-P0-aily-zone-plan-connector-contract.md`
- P4 契约：`docs/tasks/V1_1-P4-feishu-import-runbook-contract.md`
- ADR：`docs/architecture/ADR-031-aily-conversation-zone-plan.md`
