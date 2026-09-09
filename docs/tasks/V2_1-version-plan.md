# V2.1 版本计划：工厂功率上游权威与豆包 MCP 合同

**状态：** V2.1 P0 已合并；P1 upstream authority adapter 正在实施（本分支 Draft）；P2 未授权。
**目标版本：** `v2.1.0`。**基线版本：** `v2.0.0`。
**V2.0 release lineage：** `v2.0.0^{}` 解析为
`a7049ca93d238013c0cf62069fe1e0a89ff834d7`；该 SHA 必须是当前 head 的祖先，后续
`main` 合并后允许继续前进。
**当前治理阶段：** V2.1 P1 backend upstream authority adapter implementation。

V2.1 P0 已冻结并合并从 `cold_room_zone_plan@1.0.0` 绑定工厂面积/冷间面积的
权威链路、`preview_factory_power` 的输入输出合同、现有五工具兼容性和
fail-closed 边界。当前单独授权的 P1 只实现 backend adapter 与既有 V2.0
calculator 的接入；MCP tool、Skill、数据库迁移和下一阶段仍未授权。

~~~text
TASK_ID=V21_P0_FACTORY_POWER_UPSTREAM_AUTHORITY_AND_DOUBAO_MCP_CONTRACT_R1
TARGET_VERSION=v2.1.0
BASE_RELEASE=v2.0.0
BASE_MAIN_SHA=a7049ca93d238013c0cf62069fe1e0a89ff834d7
CONTRACT_FREEZE=YES
VERSION_PLAN=YES
ADR=YES
ARCHITECTURE_LOCK=YES
RUNTIME_IMPLEMENTATION=NO
MCP_IMPLEMENTATION=NO
SKILL_IMPLEMENTATION=NO
DATABASE_MIGRATION=NO
READY=NO
MERGE=NO
TAG=NO
RELEASE=NO
DEPLOYMENT=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
~~~

上面的 P0 authorization block 是 P0 dispatch 时的历史快照，保留其中的
`RUNTIME_IMPLEMENTATION=NO`、`MCP_IMPLEMENTATION=NO` 等历史 gate，不将历史
`NO` 改写成后续授权。当前状态由下面独立的 P1 record 表示：

```text
TASK_ID=V21_P1_FACTORY_POWER_UPSTREAM_AUTHORITY_ADAPTER_IMPLEMENTATION_R1
TARGET_VERSION=v2.1.0
BASE_MAIN_SHA=1d0a8e23f550b3c9ced413932fde0995acb227c0
BASE_MAIN_CI_RUN_ID=34299161658
BASE_MAIN_CI_RESULT=SUCCESS
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

## Owner Decision

用户仍只提供 V1.8 已冻结的五个业务参数：

```text
daily_inbound_mass_kg
finished_storage_days
frozen_storage_days
main_packaging_storage_days
auxiliary_packaging_storage_days
```

用户、豆包/Aily 和任何 LLM 都不得被要求填写、推导或猜测
`factory_area_m2`、`cold_storage_area_m2`、`total_area_m2` 或
`refrigerated_area_m2`。面积只能由后端从 canonical zone-plan 结果绑定。

```text
USER_REENTERS_FACTORY_AREA=NO
USER_REENTERS_COLD_STORAGE_AREA=NO
DOUBAO_ASKS_FACTORY_AREA=NO
DOUBAO_ASKS_COLD_STORAGE_AREA=NO
AILY_DERIVES_ENGINEERING_AREA=NO
AILY_GUESSES_ENGINEERING_AREA=NO
BACKEND_BINDS_AREA_FROM_UPSTREAM_AUTHORITY=YES
FACTORY_POWER_FORMULA_RECUT=NO
V20_P1_CALCULATOR_UNCHANGED=YES
V20_P2_PRESENTATION_UNCHANGED=YES
```

## V2.1 权威链

```text
USER FIVE KEY
    ↓
cold_room_zone_plan@1.0.0
    ↓
zone_plan.result.zones[]
    ↓
V2.1 FACTORY POWER AUTHORITY ADAPTER
    ↓
factory_area_m2 + cold_storage_area_m2 + zones[]
    ↓
factory_power_estimation@2.0.0-p1
    ↓
existing shared presentation
    ↓
Aily / Doubao
```

```text
AREA_COMES_FROM_ZONE_PLAN=YES
AREA_COMES_FROM_USER=NO
AREA_COMES_FROM_LLM=NO
AREA_COMES_FROM_LEGACY_POWER=NO
AREA_RECALCULATED_BY_AILY=NO
AREA_DERIVED_BY_BACKEND_FROM_CANONICAL_ZONE_RESULT=YES
```

## 面积权威与 zone integrity

`factory_area_m2` 的唯一语义是
`SUM_ALL_PLANNED_FUNCTIONAL_ZONES`。adapter 必须对 canonical
`zone_plan.result.zones[]` 做精确 zone-set、唯一性、面积存在性和非负性校验，
再以 Decimal 计算：

```text
derived_factory_area = quantize_0_01(
    SUM(Decimal(str(zone.required_area_m2)) FOR zone IN zones)
)
```

当前 12 个 canonical functional zones 必须精确为：

```text
office
changing_room
primary_precooling_room
secondary_precooling_room
raw_fruit_buffer
sorting_packaging_room
coating_room
finished_goods_room
secondary_fruit_buffer
frozen_fruit_room
packaging_material_storage
shipping_channel
```

`total_required_area_m2` 和 `total_area_m2` 不是独立面积 authority，只能做
完整性校验；二者都必须等于 `derived_factory_area`。任何不一致都必须 fail
closed，错误码为 `FACTORY_AREA_TOTAL_MISMATCH`，不能选择其中一个继续计算。

12 个 zone code 必须由实际的 `ColdRoomZonePlanner` canonical 输出锁定。架构测试
通过既有 `build_zone_plan_from_inputs` assembler 读取
`zone_plan.result.zones[].zone_code`，并验证：

```text
CONTRACT_EXPECTED_ZONE_SET == RUNTIME_COLD_ROOM_ZONE_PLANNER_ZONE_SET
RUNTIME_FACTORY_ZONE_COUNT=12
RUNTIME_FACTORY_ZONE_SET_EXACT=YES
```

`cold_storage_area_m2` 只从上述 zone rows 中属于现有
`REFRIGERATED_ZONE_REGISTRY` 的 9 个 zone 汇总。registry 的权威定义位于
`backend/src/cold_storage/modules/projects/application/operator_process_input.py`；
V2.1 不创造第二份温区 authority，也不把 `refrigerated_area_m2` 当作替代字段。

```text
FACTORY_ZONE_COUNT=12
REFRIGERATED_ZONE_COUNT=9
REFRIGERATED_ZONE_CODE_TEMPERATURE_BAND_EXACT=YES
FROZEN_FRUIT_ROOM_INCLUDED=YES
SHIPPING_CHANNEL_INCLUDED=YES
AMBIENT_AREA_INCLUDED_IN_COLD_STORAGE_AREA=NO
REFRIGERATED_AREA_M2_IS_V21_AUTHORITY=NO
```

9 个 refrigerated zone 的 `zone_code` 与 `temperature_band` 必须与 registry 完全一致；
冻果间
为 `-18℃`，出货通道为 `1~3℃`。缺失冻果间、注入未知 zone、重复 code、缺失或
负面积、温区错配均不得静默修正或少算。

## V2.0 runtime boundary

V2.1 只负责未来的 `UPSTREAM_AUTHORITY_BINDING`，不改变
`factory_power_estimation@2.0.0-p1` 的 calculator identity、规则矩阵、
`MAIN_SYSTEM_COP=3.3`、`POOL_A/B/C`、simultaneity factors、设备规则或
五阶段 `CalculationType`。旧 `preview_installed_power` 仍是
`installed_power@1.0.0` 五阶段装机功率；新工具不替换旧工具，也不把
`power_configuration` 变为 authority。

```text
FACTORY_POWER_FORMULA_RECUT=NO
V20_P1_CALCULATOR_UNCHANGED=YES
V20_P2_PRESENTATION_UNCHANGED=YES
INSTALLED_POWER_REPLACED=NO
POWER_CONFIGURATION_REPLACED=NO
FIVE_STAGE_CALCULATION_TYPE_CHANGED=NO
```

## Stateless Doubao 与 MCP 合同

豆包 MCP 继续按 stateless preview 处理。豆包不携带工程面积，不把上一次的
zone result 当作 authority；若后端没有可复用的 in-memory upstream result，允许
后端用五个 KEY 重放 `cold_room_zone_plan@1.0.0`，再从这次 canonical 输出绑定面积。
这不是 Aily 重算，也不是用户补录面积。

新工具只追加在现有五工具之后：

```text
1 preview_zone_plan
2 preview_cooling_load
3 preview_equipment
4 preview_installed_power
5 preview_investment
6 preview_factory_power
```

`preview_installed_power` 不得被替换；模糊的“功率”在本 P0 不改变 V1.8 既有
语义。只有明确的“工厂电功率/估算工厂电功率/工厂总用电功率”等意图才路由到
`preview_factory_power`，具体 Skill/router 实现留给单独授权的 P2。

新工具输入 schema 仍只允许五个 KEY，`additionalProperties=false`。任何面积
字段（包括 `factory_area_m2`、`cold_storage_area_m2`、`refrigerated_area_m2`、
`total_area_m2`）都不是 MCP 输入。

成功输出必须来自 `project_factory_power_table()` 或相同的 shared presentation
contract。MCP 层不得重算 canonical result 中的 summary、details 或功率池。
输出至少保留 `reply_kind`、`available`、`calculator_identity`、
`canonical_result_hash`、`details`、`summary`、`unit_semantics`、`review`、
`provenance` 和 `assumptions`，单位继续是 `kW`，并且 `requires_review=true`。

## 分阶段计划

| 阶段 | 状态 | 允许内容 |
| --- | --- | --- |
| P0 | **MERGED** | upstream authority、面积/温区 integrity、MCP 输入输出合同、架构锁 |
| P1 | **IMPLEMENTATION_ACTIVE（本分支 Draft）** | 后端从 canonical zone-plan 绑定面积并接入既有 V2.0 calculator |
| P2 | **UNAUTHORIZED** | `preview_factory_power` MCP、Doubao Skill/router/runbook integration |
| Release Closure | **未进入** | V2.1.0 release closure/readiness；需独立授权 |

P1 实施记录见
[V2_1-P1-factory-power-upstream-authority-adapter-implementation.md](V2_1-P1-factory-power-upstream-authority-adapter-implementation.md)。
P0 不实现 P2。除本文件外，正式规则矩阵见
[V2_1-P0-factory-power-upstream-authority-doubao-mcp-contract.md](V2_1-P0-factory-power-upstream-authority-doubao-mcp-contract.md)，
架构决策见
[ADR-043-factory-power-upstream-authority-doubao-mcp.md](../architecture/ADR-043-factory-power-upstream-authority-doubao-mcp.md)。

V1.8 的既有 Skill、合同和 runbook 保持冻结历史；本任务不修改
`docs/contracts/aily/v1.8/` 或 `docs/runbooks/v18-doubao-aily-connector.md`。
