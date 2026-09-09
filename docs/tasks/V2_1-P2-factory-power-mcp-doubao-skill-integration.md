# V2.1 P2：工厂功率 MCP 与豆包 Skill 集成实施记录

本任务是在已合并的 V2.1 P0 合同和 P1 upstream authority adapter 之上的独立
P2 实施。P2 只把五个既有 operator KEY 接入第 6 个 `preview_factory_power`
MCP 工具，并新增 V2.1 豆包 Skill 与连接器 runbook。V2.0 calculator、P1
adapter、shared presentation 和 V1.8 五阶段工具继续是既有 authority；本文件
不授权公式重切或任何下一治理阶段。

```text
TASK_ID=V21_P2_FACTORY_POWER_MCP_DOUBAO_SKILL_INTEGRATION_R1
TARGET_VERSION=v2.1.0
BASE_MAIN_SHA=95b6cbf839ba584f29f13735b07f8f8309b1cf37
BASE_MAIN_CI_RUN_ID=34321050750
BASE_MAIN_CI_RESULT=SUCCESS
BRANCH=feat/v2-1-p2-factory-power-mcp-doubao-integration-r1
PR_STATE=OPEN_DRAFT
P0_STATUS=MERGED
P1_STATUS=MERGED
P2_STATUS=IMPLEMENTATION_ACTIVE
P2_EXECUTED=YES
RELEASE_CLOSURE=UNAUTHORIZED
MCP_TOOL_COUNT=6
NEW_MCP_TOOL=preview_factory_power
NEW_MCP_TOOL_POSITION=6
EXISTING_FIVE_TOOL_ORDER_CHANGED=NO
MCP_INPUT_REMAINS_FIVE_KEY=YES
MCP_RUNTIME_REJECTS_AREA_INPUT=YES
MCP_RUNTIME_REJECTS_UNKNOWN_INPUT=YES
FACTORY_POWER_FROM_P1_ADAPTER=YES
FACTORY_POWER_FROM_SHARED_PROJECTOR=YES
MCP_ENGINEERING_RECALCULATION=NO
V20_CALCULATOR_CHANGED=NO
P1_ADAPTER_CHANGED=NO
V20_PRESENTATION_CHANGED=NO
CONCEPT_PREVIEW_STAGE_COUNT=5
CALCULATION_TYPE_CHANGED=NO
V18_SKILL_CHANGED=NO
V18_RUNBOOK_CHANGED=NO
V21_SKILL_CREATED=YES
V21_RUNBOOK_CREATED=YES
OUTBOUND_LIVE_AILY_SESSION=NO
DATABASE_MIGRATION=NO
FRONTEND_CHANGED=NO
NEW_REST_ENDPOINT=NO
SERVER_SIDE_CHAT_NLP=NO
READY=NO
MERGE=NO
TAG=NO
RELEASE=NO
DEPLOYMENT=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 1. Runtime chain

`preview_factory_power` 是 stateless application preview。它严格复用既有
`assemble_preview_context(...)` 和 `ZonePlanningAdapter` 的 zone authority 执行
路径，从实际 `AdapterResult` 构造带身份的
`cold_room_zone_plan@1.0.0` envelope，然后依次调用：

```text
five operator KEY
  -> assemble_preview_context(...)
  -> existing ZonePlanningAdapter
  -> canonical zone-plan AdapterResult
  -> calculate_factory_power_from_zone_plan(...)
  -> serialize_factory_power_result(...)
  -> project_factory_power_table(...)
  -> pure Markdown copy of table rows
  -> preview_factory_power MCP response
```

P2 不计算面积、冷量、设备、COP、化霜、照明、生产设备、功率池、同时系数或
任何 summary。`factory_power_estimation@2.0.0-p1` 仍是唯一工厂功率计算 authority；
`project_factory_power_table()` 仍是共享只读 presentation boundary。

## 2. 输入与 fail-closed 边界

MCP 的 `inputSchema` 和 runtime application boundary 都只允许以下五个 KEY：

```text
daily_inbound_mass_kg
finished_storage_days
frozen_storage_days
main_packaging_storage_days
auxiliary_packaging_storage_days
```

`factory_area_m2`、`cold_storage_area_m2`、`refrigerated_area_m2`、
`total_area_m2`、`zone_plan`、`chat_text` 以及任意未知字段均返回
`MCP_INPUT_SCHEMA_REJECTED`，且 `missing_keys=[]`、`ask_operator=""`。缺少原五
KEY 时继续返回既有 `MISSING_ENGINEERING_PARAMETER`，只追问缺少的业务参数，绝不
追问工程面积。

P1 adapter 或 V2.0 calculator 的 blocker 保留原始 `code`、`message`、`details`，
不降级成泛化错误、不 fallback。shared projector 不可用时，MCP 返回
`V20_FACTORY_POWER_CANONICAL_RESULT_UNAVAILABLE`，不补 details、summary 或 hash。

## 3. 工具兼容性与概念预览边界

现有五个工具顺序不变：

```text
1 preview_zone_plan
2 preview_cooling_load
3 preview_equipment
4 preview_installed_power
5 preview_investment
6 preview_factory_power
```

`preview_installed_power` 仍表示 `installed_power@1.0.0` 五阶段装机功率；它不被
新工具 alias 或替换。`/api/v1/aily/v1/concept-preview` 继续只有五阶段，P2 不
增加 `stages.factory_power`、新的 REST route、CalculationType 或数据库迁移。

## 4. 输出与展示

成功响应保留 shared projector 的 `reply_kind`、`available`、calculator identity、
`canonical_result_hash`、`details`、`summary`、`unit_semantics`、`review`、
`provenance` 和 `assumptions`，并标记 `persisted=false`、`requires_review=true`。
新增的 `markdown_table` 只逐单元复制 projector `table.columns` 与 `table.rows`，
不做加总、乘除、round、插值或 summary 重建。结果单位为 `kW`，是概念设计阶段
估算工厂电功率，需要工程复核；不是 `kWh`、日/月耗电量、电费、电表计量值、
变压器选型、正式配电设计、施工图、短路计算、电缆选型或保护整定。

## 5. Doubao Skill 与 runbook

V2.1 Skill 位于 `docs/contracts/aily/v2.1/`，V1.8 Skill 与 runbook 保持冻结。
明确的“工厂电功率”意图路由到 `preview_factory_power`；明确的“装机功率”意图
继续路由到 `preview_installed_power`；只有“功率”时不得静默改变 V1.8 语义，
必要时澄清。自然语言理解由豆包负责，server-side 不新增 NLP router。

V2.1 runbook 位于 `docs/runbooks/v21-doubao-aily-connector.md`，记录
Streamable HTTP 地址、六个工具的顺序、`tools/list` 自检和
`preview_factory_power` 的五 KEY `tools/call` 示例。本仓库不建立 outbound live
Aily session。

## 6. Acceptance locks

测试覆盖：成功 smoke、面积/未知字段注入、缺 KEY、P1/V2 blocker 原样传播、
projector unavailable、MCP/直接 P1 parity、不同 correlation id 的 determinism、
HTTP `tools/list`/`tools/call`、既有五工具回归以及 V2.0/V2.1 architecture scope。
P2 architecture lock 同时证明 P1 adapter、V2.0 calculator/presentation、五阶段
CalculationType、V1.8 Skill/runbook、frontend、数据库和 outbound surface 未被
本任务改变。

本 PR 完成后停在 Draft Review gate：不执行 Ready、Merge、tag、release、部署或
下一 feature lane。
