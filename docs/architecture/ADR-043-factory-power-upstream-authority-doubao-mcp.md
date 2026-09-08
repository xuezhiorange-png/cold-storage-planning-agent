# ADR-043：冻结工厂功率上游面积权威与豆包 MCP 合同

- 状态：Proposed; V2.1 P0 contract frozen; runtime/MCP/Skill implementation not authorized
- 日期：2026-09-09
- 目标版本：`v2.1.0`
- 基线版本：`v2.0.0` at `main@a7049ca93d238013c0cf62069fe1e0a89ff834d7`
- 关联任务：[V2_1-version-plan.md](../tasks/V2_1-version-plan.md)
- 正式契约：[V2_1-P0-factory-power-upstream-authority-doubao-mcp-contract.md](../tasks/V2_1-P0-factory-power-upstream-authority-doubao-mcp-contract.md)

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

zone set、required area、非负性、重复 code 和未知 code 都是 fail-closed
integrity 条件，不允许为继续计算而删行、补行或改温区。

### 4. Cold-storage area is the registry-filtered 9-zone sum

冷间面积直接按既有 registry 过滤 canonical zone rows。9 个 registry 温区必须
完整匹配；`frozen_fruit_room=-18℃` 和 `shipping_channel=1~3℃` 都包含在内。
办公室、更衣室和包材库排除。历史 `refrigerated_area_m2` 不具有 V2.1 authority。

```text
FACTORY_AREA_AUTHORITY=SUM_ALL_ZONE_REQUIRED_AREA
COLD_STORAGE_AREA_AUTHORITY=REFRIGERATED_ZONE_REGISTRY
EXPECTED_FACTORY_ZONE_COUNT=12
EXPECTED_REFRIGERATED_ZONE_COUNT=9
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

未来 P1 只负责绑定 upstream authority；未来 P2 才能实现 MCP 和 Skill/router。

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
- 本 ADR 不提供 runtime adapter、MCP tool、Skill、数据库迁移或部署。
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
