# ADR-043：冻结工厂功率上游面积权威与豆包 MCP 合同

- 状态：P0 contract frozen and merged; P1 backend upstream authority adapter merged; P2 MCP/Skill integration active
- 日期：2026-09-09
- 目标版本：`v2.1.0`
- 基线版本：`v2.0.0^{}` = `a7049ca93d238013c0cf62069fe1e0a89ff834d7`；该 SHA
  必须是当前 head 的祖先，后续 main 合并后允许前进
- 关联任务：[V2_1-version-plan.md](../tasks/V2_1-version-plan.md)
- 正式契约：[V2_1-P0-factory-power-upstream-authority-doubao-mcp-contract.md](../tasks/V2_1-P0-factory-power-upstream-authority-doubao-mcp-contract.md)
- P1 实施记录：[V2_1-P1-factory-power-upstream-authority-adapter-implementation.md](../tasks/V2_1-P1-factory-power-upstream-authority-adapter-implementation.md)
- P2 实施记录：[V2_1-P2-factory-power-mcp-doubao-skill-integration.md](../tasks/V2_1-P2-factory-power-mcp-doubao-skill-integration.md)

当前治理状态是：P0、P1 已在 `main` 合并；当前独立 P2 只实现入站 Doubao MCP、
V2.1 Skill 和 runbook，并调用既有 P1 adapter、V2.0 calculator 与 shared
presentation。前端、数据库、Ready、Merge、tag、release 和部署仍未授权。P0/P1
dispatch 时的 gate block 在文末/记录中原样保留，作为历史授权记录。

## Context

V2.0 已在 `v2.0.0` 完成工厂功率 deterministic calculator 和工作台/Aily 只读
呈现，但保留了两个必须在后续版本独立解决的上游映射问题：

1. `factory_area_m2` 必须从 canonical zone-plan 的 12 个 planned functional
   zones 绑定，而不能由用户、吞吐量、冷间面积或 legacy power 猜测。
2. `cold_storage_area_m2` 必须从 canonical zone rows 和现有
   `REFRIGERATED_ZONE_REGISTRY` 的 9 个冷区绑定，并明确包含冻果间和出货通道。

同时，stateless 豆包 MCP 不能依赖会话记忆中的面积，也不能把 Aily 的自由输入
或 LLM 推导当作工程 authority。新增工厂功率工具还必须 append 在 V1.8 五工具
之后，避免改变既有客户端语义。

## Decision

### 1. Five-key input remains the only operator/MCP input

用户和 MCP 只接收：

```text
daily_inbound_mass_kg
finished_storage_days
frozen_storage_days
main_packaging_storage_days
auxiliary_packaging_storage_days
```

面积字段不进入 input schema：

```text
USER_REENTERS_FACTORY_AREA=NO
USER_REENTERS_COLD_STORAGE_AREA=NO
DOUBAO_ASKS_FACTORY_AREA=NO
DOUBAO_ASKS_COLD_STORAGE_AREA=NO
MCP_FACTORY_AREA_INPUT_ALLOWED=NO
MCP_COLD_STORAGE_AREA_INPUT_ALLOWED=NO
MCP_REFRIGERATED_AREA_INPUT_ALLOWED=NO
MCP_TOTAL_AREA_INPUT_ALLOWED=NO
```

### 2. Zone plan is the sole upstream authority

```text
five KEY
  → cold_room_zone_plan@1.0.0
  → zone_plan.result.zones[]
  → V2.1 authority adapter
  → factory_power_estimation@2.0.0-p1
```

允许后端 stateless replay zone plan，但 replay 必须仍由原五 KEY 产生 canonical
zone result。Aily/Doubao 不计算、不猜测、不携带面积 authority。

### 3. Factory area is the exact 12-zone sum

`factory_area_m2` 是所有 12 个 canonical planned functional zones 的
`required_area_m2` Decimal 合计，并 quantize 到 0.01。`total_required_area_m2`
和 `total_area_m2` 只做一致性校验；任一不一致都返回
`FACTORY_AREA_TOTAL_MISMATCH`。

合同中的 12-zone set 必须与实际 `ColdRoomZonePlanner` 输出绑定。架构测试通过
既有 `build_zone_plan_from_inputs` assembler 读取
`zone_plan.result.zones[].zone_code`，并锁定：

```text
CONTRACT_EXPECTED_ZONE_SET == RUNTIME_COLD_ROOM_ZONE_PLANNER_ZONE_SET
RUNTIME_FACTORY_ZONE_COUNT=12
RUNTIME_FACTORY_ZONE_SET_EXACT=YES
```

zone set、required area、非负性、重复 code 和未知 code 都是 fail-closed
integrity 条件，不允许为继续计算而删行、补行或改温区。

### 4. Cold-storage area is the registry-filtered 9-zone sum

冷间面积直接按既有 registry 过滤 canonical zone rows。仅 9 个 registry 冷区的
温区必须完整匹配；`frozen_fruit_room=-18℃` 和 `shipping_channel=1~3℃` 都包含在内。
办公室、更衣室和包材库排除。历史 `refrigerated_area_m2` 不具有 V2.1 authority。

```text
FACTORY_AREA_AUTHORITY=SUM_ALL_ZONE_REQUIRED_AREA
COLD_STORAGE_AREA_AUTHORITY=REFRIGERATED_ZONE_REGISTRY
EXPECTED_FACTORY_ZONE_COUNT=12
EXPECTED_REFRIGERATED_ZONE_COUNT=9
REFRIGERATED_ZONE_CODE_TEMPERATURE_BAND_EXACT=YES
FROZEN_FRUIT_ROOM_INCLUDED=YES
SHIPPING_CHANNEL_INCLUDED=YES
REFRIGERATED_AREA_M2_IS_V21_AUTHORITY=NO
```

### 5. V2.0 calculator and presentation remain unchanged

V2.1 P0 不修改 V2.0 calculator、shared presentation、frontend 或 Aily runtime：

```text
V20_P1_CALCULATOR_UNCHANGED=YES
V20_P2_PRESENTATION_UNCHANGED=YES
FACTORY_POWER_FORMULA_RECUT=NO
INSTALLED_POWER_REPLACED=NO
POWER_CONFIGURATION_REPLACED=NO
```

P1 只负责绑定 upstream authority；当前 P2 才实现入站 MCP、Skill 和 runbook，且
不改变上游 calculator/presentation 或五阶段语义。

### 6. New MCP tool is an append-only, five-key, read-only presentation contract

冻结 `preview_factory_power` 为第 6 个工具。既有五工具顺序不变，旧
`preview_installed_power` 不被替换。新工具的输出必须来自
`project_factory_power_table()` 或相同的 shared presentation contract，不得在
MCP 层重算工程值。

### 7. No P3 is implied

V2.1 P0 不授权 P1、P2、Ready、Merge、tag、release、deployment 或任何下一 lane。
`NO_STEP_IMPLIES_THE_NEXT=TRUE` 是本 ADR 的强制门禁。

## Consequences

- 面积的工程含义从用户输入和旧字段歧义中移除，收敛到 canonical zone-plan lineage。
- total 字段不再能够绕过逐区校验；温区错误会在绑定前 fail closed。
- 豆包可以保持 stateless，不需要记忆上一次工程面积；后端 replay 仍使用同一
  `cold_room_zone_plan@1.0.0` authority。
- V1.8 五工具及 `preview_installed_power` 兼容性不被 P0 改变。
- P0 本身不提供 runtime adapter、MCP tool、Skill、数据库迁移或部署；P1 adapter
  与当前 P2 MCP/Skill 的独立实施边界分别记录在 P1/P2 task 文档中。
- 结果仍是概念设计阶段估算工厂电功率，单位 `kW`，需要人工复核；不是 kWh、
  计量值、电费、变压器选型或正式配电设计。

## Non-goals and gate record

~~~text
CONTRACT_FREEZE=YES
RUNTIME_IMPLEMENTATION=NO
MCP_IMPLEMENTATION=NO
SKILL_IMPLEMENTATION=NO
DATABASE_MIGRATION=NO
READY=NO
MERGE=NO
TAG=NO
RELEASE=NO
DEPLOYMENT=NO
OUTBOUND_LIVE_AILY_SESSION=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
~~~

P0 contract/architecture PASS 只代表合同已冻结并可进入独立 review；它不等价于
P1/P2 实现或 release readiness。

## Current P1 implementation record

下面是独立 P1 authorization/implementation record，不改写上面的 P0 historical
gate：

```text
TASK_ID=V21_P1_FACTORY_POWER_UPSTREAM_AUTHORITY_ADAPTER_IMPLEMENTATION_R1
TARGET_VERSION=v2.1.0
BASE_MAIN_SHA=1d0a8e23f550b3c9ced413932fde0995acb227c0
P0_STATUS=MERGED
P1_STATUS=IMPLEMENTATION_ACTIVE
P1_EXECUTED=YES
P2_STATUS=UNAUTHORIZED
P2_EXECUTED=NO
BACKEND_UPSTREAM_AUTHORITY_ADAPTER_IMPLEMENTATION=YES
FACTORY_AREA_BINDING_IMPLEMENTATION=YES
COLD_STORAGE_AREA_BINDING_IMPLEMENTATION=YES
V20_FACTORY_POWER_CALCULATOR_INVOCATION=YES
DOUBAO_MCP_IMPLEMENTATION=NO
MCP_IMPLEMENTED=NO
SKILL_IMPLEMENTED=NO
FRONTEND_CHANGED=NO
DATABASE_MIGRATION=NO
READY=NO
MERGE=NO
TAG=NO
RELEASE=NO
DEPLOYMENT=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P1 的 adapter 必须从成功且身份精确为 `cold_room_zone_plan@1.0.0` 的
`zone_plan.result.zones[]` 绑定全部 12 个 planned functional zones 的
`factory_area_m2`，并从运行时 `REFRIGERATED_ZONE_REGISTRY` 的 9 个 zone 绑定
`cold_storage_area_m2`。它不接受面积输入、不使用 `refrigerated_area_m2` fallback，
不复制 V2.0 公式，也不改变共享 presentation contract。上面的 P1 record 保留其
历史 gate；当前 P2 状态见下节。

## Current P2 integration record

以下是独立 P2 authorization/implementation record，不改写上方 P0 historical
gate 或 P1 implementation record：

```text
TASK_ID=V21_P2_FACTORY_POWER_MCP_DOUBAO_SKILL_INTEGRATION_R1
TARGET_VERSION=v2.1.0
BASE_MAIN_SHA=95b6cbf839ba584f29f13735b07f8f8309b1cf37
BASE_MAIN_CI_RUN_ID=34321050750
BASE_MAIN_CI_RESULT=SUCCESS
P0_STATUS=MERGED
P1_STATUS=MERGED
P2_STATUS=IMPLEMENTATION_ACTIVE
P2_EXECUTED=YES
ACTIVE_GOVERNANCE_LANE=V2.1_P2
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
SERVER_SIDE_CHAT_NLP=NO
OUTBOUND_LIVE_AILY_SESSION=NO
DATABASE_MIGRATION=NO
FRONTEND_CHANGED=NO
NEW_REST_ENDPOINT=NO
RELEASE_CLOSURE=UNAUTHORIZED
READY=NO
MERGE=NO
TAG=NO
RELEASE=NO
DEPLOYMENT=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P2 通过既有 zone preview execution 取得实际 canonical zone-plan `AdapterResult`，
调用 P1 adapter，再序列化并投影为 `preview_factory_power`。它只把 projector 的
table 逐单元格式化为 Markdown；不在 MCP/豆包侧计算面积、功率或 summary，不解析
服务器端中文聊天。五阶段 `CalculationType` 仍为五项，V1.8 Skill/runbook 保持
冻结。P2 结束后停在 Draft Review gate，release closure 仍需另行授权。
