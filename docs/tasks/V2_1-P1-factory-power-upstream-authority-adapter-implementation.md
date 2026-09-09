# V2.1 P1：工厂功率上游权威 adapter 实施记录

本任务是 V2.1 P0 合同冻结后的独立 P1 backend 实施。P0 的历史授权快照
保留在 `V2_1-P0-factory-power-upstream-authority-doubao-mcp-contract.md`；本文件
只记录当前 P1 的授权、实现边界和验收锁。P1 不实现 Doubao MCP、Skill、前端或
数据库变化。

```text
TASK_ID=V21_P1_FACTORY_POWER_UPSTREAM_AUTHORITY_ADAPTER_IMPLEMENTATION_R1
TARGET_VERSION=v2.1.0
BASE_MAIN_SHA=1d0a8e23f550b3c9ced413932fde0995acb227c0
BASE_MAIN_CI_RUN_ID=34299161658
BASE_MAIN_CI_RESULT=SUCCESS
BRANCH=feat/v2-1-p1-factory-power-upstream-authority-adapter-r1
PR_STATE=OPEN_DRAFT
P0_STATUS=MERGED
P1_STATUS=IMPLEMENTATION_ACTIVE
P1_EXECUTED=YES
P2_STATUS=UNAUTHORIZED
P2_EXECUTED=NO
BASE_MAIN_SHA_IS_ANCESTOR_OF_HEAD=YES
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 1. P1 目标与权威链

P1 只把已经成功生成的 canonical
`cold_room_zone_plan@1.0.0` 结果接到既有
`factory_power_estimation@2.0.0-p1`。P1 不增加任何用户输入，也不让豆包、Aily
或 LLM 提供或猜测工程面积：

```text
five operator KEY
  -> cold_room_zone_plan@1.0.0
  -> zone_plan.result.zones[]
  -> factory_power_upstream_authority adapter
  -> factory_area_m2 + cold_storage_area_m2 + canonical zone rows
  -> factory_power_estimation@2.0.0-p1
```

```text
CANONICAL_ZONE_PLAN_IDENTITY_REQUIRED=YES
FACTORY_AREA_FROM_12_ZONE_ROWS=YES
FACTORY_AREA_ZONE_COUNT=12
FACTORY_AREA_TOTAL_CROSS_CHECK=YES
COLD_STORAGE_AREA_FROM_REFRIGERATED_REGISTRY=YES
REFRIGERATED_ZONE_COUNT=9
FROZEN_FRUIT_ROOM_INCLUDED=YES
SHIPPING_CHANNEL_INCLUDED=YES
REFRIGERATED_TEMPERATURE_INTEGRITY=YES
REFRIGERATED_AREA_M2_USED_AS_AUTHORITY=NO
FACTORY_POWER_FORMULA_RECUT=NO
```

实现位置为
`backend/src/cold_storage/modules/projects/application/factory_power_upstream_authority.py`。
它位于 application boundary，复用 projects application 已有的
`REFRIGERATED_ZONE_REGISTRY`，再调用 calculations domain 已有的
`calculate_factory_power_estimation_from_mapping`。

## 2. canonical zone-plan 校验

adapter 只接受成功且身份精确匹配的完整 CalculationResult：

```text
success=true
calculator_name=cold_room_zone_plan
calculator_version=1.0.0
result.zones[]
```

未验证的任意 `zones=[]`、用户面积字段、`refrigerated_area_m2` 替代路径都在
adapter 边界 fail closed。12 个 zone code 必须精确为：

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

每个 row 的 `required_area_m2` 使用 `Decimal(str(value))`，拒绝缺失、布尔值、
非数值、NaN、Infinity 和负数。重复、缺失或未知 zone 分别以
`DUPLICATE_ZONE_CODE`、`ZONE_AUTHORITY_SET_MISMATCH` 等明确错误阻断。

## 3. 面积绑定规则

`factory_area_m2` 只由全部 12 个 canonical zone rows 计算：

```text
factory_area_m2 = quantize_0_01(
    SUM(Decimal(str(zone.required_area_m2)) FOR zone IN zones)
)
```

`total_required_area_m2` 和 `total_area_m2` 不是独立 authority。adapter 重新
计算逐区合计，并以相同的 Decimal / 0.01 精度校验两个字段；任一不一致都返回
`FACTORY_AREA_TOTAL_MISMATCH`，不会选择一个值继续计算。

`cold_storage_area_m2` 只按 canonical zone rows 过滤既有
`REFRIGERATED_ZONE_REGISTRY` 的 9 个 code 求和。registry 不在 P1 复制；9 个
区域及温区由运行时 registry 直接提供：

```text
primary_precooling_room=8~10℃
secondary_precooling_room=1~3℃
raw_fruit_buffer=8~10℃
sorting_packaging_room=8~10℃
coating_room=1~3℃
finished_goods_room=1~3℃
secondary_fruit_buffer=8~10℃
frozen_fruit_room=-18℃
shipping_channel=1~3℃
```

9 个 refrigerated rows 的 `zone_code` 与 `temperature_band` 必须完全匹配运行时
registry；例如冻果间被标为常温时返回
`REFRIGERATED_ZONE_TEMPERATURE_MISMATCH`，不能动态少算面积。办公室、更衣室和
包材库不计入冷间面积。`refrigerated_area_m2` 不是 V2.1 authority，不能 fallback。

## 4. V2.0 calculator boundary

面积绑定后，adapter 只构造既有 calculator 所需的
`factory_area_m2`、`cold_storage_area_m2` 和 `zone_plan.result.zones[]`，随后调用
原有 `factory_power_estimation@2.0.0-p1`。P1 不复制或修改冷风机、化霜、压缩机、
COP、公共设备、照明、生产设备、功率池或同时系数规则。

```text
V20_CALCULATOR_INVOKED=YES
V20_CALCULATOR_CHANGED=NO
V20_PRESENTATION_CHANGED=NO
ADAPTER_ONLY_BINDS_AUTHORITY=YES
RAW_POSITION_COUNT_FALLBACK=NO
SUBTOTAL_LOAD_FALLBACK=NO
```

canonical rows 的 reporting scheme、selected scheme、
`minimum_estimated_cooling_load_kw_r` 和其它 V2 calculator authority 不由 adapter
补写或修复，继续由 V2 calculator fail closed。当前 V1.9 planner 的
`cooling_estimation_basis` 是结构化值，而未修改的 V2.0 parser 的兼容字段是
确定性的 JSON 文本；adapter 仅在 calculator mapping 边界做稳定序列化，不改变
任何工程字段，也不重新计算任何结果。

## 5. Determinism 与测试锁

同一 canonical zone-plan 重复运行时，两个面积值和
`FactoryPowerEstimationResult.canonical_json()` 必须完全相同。P1 unit tests
覆盖 canonical identity、12-zone/9-zone authority、Decimal 校验、total mismatch、
温区 mismatch、重复/缺失/未知 zone、禁止替代字段、V2 calculator scheme/minimum
load fail-closed 边界，并以手工 P0 authority payload 和 adapter 结果做 canonical
JSON parity：

```text
ADAPTER_GOLDEN_PARITY_RESULT=PASS
ADAPTER_RECALCULATES_FACTORY_POWER=NO
```

V2.1 P0、V2.0 P0/P1/P2/release architecture locks 继续验证基线 lineage、V2.0
calculator/presentation 不变、既有五阶段 CalculationType 不变、MCP surface 不变、
无 migration 和无 outbound live Aily。

## 6. P1 gate 与明确非目标

P1 当前停在 Draft Review gate；本任务不执行 Ready、Merge、tag、release、部署或
下一 feature lane：

```text
DOUBAO_MCP_IMPLEMENTATION=NO
MCP_IMPLEMENTED=NO
MCP_TOOL_COUNT_CHANGED=NO
SKILL_IMPLEMENTED=NO
FRONTEND_CHANGED=NO
DATABASE_MIGRATION=NO
CALCULATION_TYPE_CHANGED=NO
DATABASE_MIGRATION_CREATED=NO
OUTBOUND_LIVE_AILY_SESSION_EXECUTED=NO
P2_EXECUTED=NO
READY_EXECUTED=NO
MERGE_EXECUTED=NO
TAG_CREATED=NO
RELEASE_CREATED=NO
DEPLOYMENT_EXECUTED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P2 仍负责未来的五 KEY stateless replay、`preview_factory_power` MCP tool 和
Skill/router integration；P1 不预先实现这些能力。
