# V1.9 版本计划：冻结依据与逐区域最低冷量估算实现

**状态：** V1.9 P0 文档契约保持冻结；V1.9 P1 已由 Charles 单独授权并在当前 Draft 分支完成最小运行时实现，等待 `CHARLES_V19_P1_IMPLEMENTATION_REVIEW`。
**上一版本：** V1.8 per-zone temperature and height（实现已授权，但本计划不改其运行时）。
**本分支基线：** `main@a04aac1ac2309cfbce500ead13cfc2fc4ab176ac`，tree `2b92afddaffcd9e6d289477e37a58b8d54fcd786`。
**权威来源：** `CHARLES_CONFIRMED_ENGINEERING_REFERENCE`。
**产品方向：** `PER_ZONE_COOLING_ESTIMATION_BASIS`。

本版只定义并冻结九个制冷分区的**最低估算制冷量依据**。结果字段统一为
`minimum_estimated_cooling_load_kw_r`，该最低计算值**等于**冻结依据；未来选定或设计的制冷能力必须“**不小于**”该最低值。它不是详细热负荷算法、正式热工设计值或设备选型输入。

```text
TASK=V19_P0_PER_ZONE_COOLING_ESTIMATION_BASIS_CONTRACT_FREEZE_R1
MODE=DOCS_CONTRACT_ARCH_TEST_ONLY
AUTHORIZATION=AUTHORIZED_FOR_THIS_P0_ONLY
BASE_MAIN_SHA=ae3814f3b0c644d5ae23aabfc24825ac7b29ca2b
BASE_MAIN_TREE_SHA=fcef44fe76ffe812172de1d1f9a0463503fbfa08
PER_ZONE_COOLING_ESTIMATION_BASIS=YES
ZONE_RULE_COUNT=9
PRECOOL_SOURCE_FIELD=position_count
AREA_SOURCE_FIELD=required_area_m2
AREA_SEMANTIC=PLANNED_ZONE_AREA
AUTHORITY_SOURCE=CHARLES_CONFIRMED_ENGINEERING_REFERENCE
MINIMUM_ESTIMATE_SEMANTICS=YES
EXISTING_ZONE_PLAN_REUSE=YES
USER_CONFIRMED_ESTIMATION_REFERENCE=YES
RUNTIME_IMPLEMENTATION_AUTHORIZED=NO
DETAILED_THERMAL_LOAD_ALGORITHM_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT_AUTHORIZED=NO
EQUIPMENT_SELECTION_RECUT_AUTHORIZED=NO
INSTALLED_POWER_RECUT_AUTHORIZED=NO
INVESTMENT_RECUT_AUTHORIZED=NO
FRONTEND_IMPLEMENTATION_AUTHORIZED=NO
PR_252_FORMULA_AUDIT_DIRECTION=SUPERSEDED_BY_PER_ZONE_COOLING_ESTIMATION_BASIS
PR_252_MERGE_AUTHORIZED=NO
PR_252_CLOSE_AUTHORIZED=NO
PR_252_RUNTIME_IMPLEMENTATION_AUTHORIZED=NO
V19_P1_AUTHORIZED=NO
RUNTIME_IMPLEMENTATION_EXECUTED=NO
FORMULA_RECUT_EXECUTED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 1. 数据血缘与字段语义

P0 复用既有 `zone-plan`，不新增、不改运行时 schema：

```text
zone_plan.result.zones[]
  ├─ zone_code
  ├─ position_count       # 预冷区的最终 reporting position count
  └─ required_area_m2     # 面积型区域的 canonical planned area
```

`required_area_m2` 是当前仓库真实 canonical 面积字段；本版把它的业务语义冻结为
`PLANNED_ZONE_AREA`。文档中的 `area_m2` 仅是面积单位的说明，落到契约时必须使用
`required_area_m2`。`raw_position_count` 是预冷内部计算中间值，不能作为估算依据。

所有九区的结果都使用 `minimum_estimated_cooling_load_kw_r`，并采用以下两层关系：

```text
ENGINEERING_REFERENCE:
required cooling capacity >= frozen reference basis

COMPUTED_MINIMUM_VALUE:
minimum_estimated_cooling_load_kw_r = frozen reference basis
```

`future_selected_or_design_cooling_capacity >= minimum_estimated_cooling_load_kw_r`
只是未来设计/选型的语义说明，不是本 P0 新增的 runtime 字段，也不授权设备选型算法。

允许的结果表述只有：`minimum estimated cooling load`、`minimum cooling capacity reference`、
“最低估算制冷量”或“最低制冷能力参考值”。禁止把它称为 exact cooling load、final design
cooling load、formal thermal load 或 precise heat load calculation。

## 2. 九个权威规则

面积型 reference factor 由 W/m² 换算为 kW/m²；换算只用于表达冻结的参考依据，不授权重切现有
`cooling_load` 计算。每一项均属于最低估算参考值，且 machine-readable rule 必须携带
`requires_review=true`，以保留人工工程复核能力；该标记不表示契约未冻结或结果无效。

| `zone_code` | 基础类型 | canonical source | Charles reference factor | 冻结参考表达 |
| --- | --- | --- | --- | --- |
| `primary_precooling_room` | `FINAL_POSITION_COUNT` | `position_count` | 20 kW(r)/final position | `minimum_estimated_cooling_load_kw_r = position_count * 20` |
| `secondary_precooling_room` | `FINAL_POSITION_COUNT` | `position_count` | 15 kW(r)/final position | `minimum_estimated_cooling_load_kw_r = position_count * 15` |
| `raw_fruit_buffer` | `ZONE_AREA` | `required_area_m2` | 400 W/m² | `minimum_estimated_cooling_load_kw_r = required_area_m2 * 0.40` |
| `sorting_packaging_room` | `ZONE_AREA` | `required_area_m2` | 300 W/m² | `minimum_estimated_cooling_load_kw_r = required_area_m2 * 0.30` |
| `coating_room` | `ZONE_AREA` | `required_area_m2` | 300 W/m² | `minimum_estimated_cooling_load_kw_r = required_area_m2 * 0.30` |
| `finished_goods_room` | `ZONE_AREA` | `required_area_m2` | 300 W/m² | `minimum_estimated_cooling_load_kw_r = required_area_m2 * 0.30` |
| `secondary_fruit_buffer` | `ZONE_AREA` | `required_area_m2` | 400 W/m² | `minimum_estimated_cooling_load_kw_r = required_area_m2 * 0.40` |
| `frozen_fruit_room` | `ZONE_AREA` | `required_area_m2` | 550 W/m² | `minimum_estimated_cooling_load_kw_r = required_area_m2 * 0.55` |
| `shipping_channel` | `ZONE_AREA` | `required_area_m2` | 300 W/m² | `minimum_estimated_cooling_load_kw_r = required_area_m2 * 0.30` |

一级、二级预冷都必须读取最终 `position_count`。不得读取或回退到
`raw_position_count`。面积型区域只能读取现有 zone-plan 的 `required_area_m2`；不得从加工厂建筑面积、
新的几何推导或另一个 demo 表生成面积。

## 3. Fail-closed 约束

未来实现若进入授权流程，以下任一条件都必须 fail closed，并返回可审计的缺失/未映射原因：

| 条件 | 处理 |
| --- | --- |
| 预冷区缺少 `position_count` | FAIL CLOSED |
| 面积型区域缺少 `required_area_m2` | FAIL CLOSED |
| `zone_code` 未映射到九区规则 | FAIL CLOSED |
| 规则缺少 reference factor | FAIL CLOSED |

禁止 fallback 到 `raw_position_count`、demo thermal catalog、`U × A × ΔT`、product sensible heat、
infiltration model、legacy cooling output、AI guessed values 或 arbitrary defaults。

## 4. 本 P0 的授权边界

本分支允许的变更只有 `docs/**` 与 `backend/tests/architecture/**`。P0 不实现结果服务、API、
数据库、迁移、前端、报告、设备选型、装机功率、投资或详细热工算法；也不重切任何现有
`cooling_load` 公式和输出。P0 本身不授权 P1；当前 P1 使用独立授权文档
`docs/tasks/V1_9-P1-per-zone-cooling-estimation-implementation.md`，不改变本
P0 的历史授权字段。

`EXISTING_ZONE_PLAN_REUSE=YES`、`USER_CONFIRMED_ESTIMATION_REFERENCE=YES` 和
`MINIMUM_ESTIMATE_SEMANTICS=YES` 是本契约的正向锁；所有运行时/重切/选型相关授权均为 `NO`。

## 5. PR #252 关系

现有 Draft PR #252（“V1.9：逐区核算冷量计算公式（定义冻结）”）不在本任务中 merge、close、
Ready、push 其 branch 或 rewrite。本契约只记录：

```text
PR_252_FORMULA_AUDIT_DIRECTION=SUPERSEDED_BY_PER_ZONE_COOLING_ESTIMATION_BASIS
PR_252_MERGE_AUTHORIZED=NO
PR_252_CLOSE_AUTHORIZED=NO
PR_252_RUNTIME_IMPLEMENTATION_AUTHORIZED=NO
```

“superseded”只表示审计方向被新的 `PER_ZONE_COOLING_ESTIMATION_BASIS` 取代，不表示 PR #252 已关闭。

## 6. P0 后续门禁与 P1 独立授权

P0 的 `RUNTIME_IMPLEMENTATION_AUTHORIZED=NO` 与 `V19_P1_AUTHORIZED=NO` 是 P0
历史事实，不因 P1 实现而改写。Charles 后续已明确单独授权 P1，当前计划记录如下：

```text
P0_CONTRACT_FROZEN=YES
P1_IMPLEMENTATION_SEPARATELY_AUTHORIZED=YES
V19_P1_IMPLEMENTATION_AUTHORIZED=YES
V19_P1_IMPLEMENTATION_EXECUTED=YES
RUNTIME_RULE_COUNT=9
PRECOOL_SOURCE_FIELD=position_count
AREA_SOURCE_FIELD=required_area_m2
MINIMUM_OUTPUT_FIELD=minimum_estimated_cooling_load_kw_r
PROVENANCE_SURFACE_IMPLEMENTED=YES
REQUIRES_REVIEW_ALL_RULES=YES
AMBIENT_ZONES_ENRICHED=NO
ZONE_PLAN_EXISTING_VALUES_CHANGED=NO
ZONE_PLANNING_ADAPTER_PRESERVES_V19_FIELDS=YES
SOURCE_SNAPSHOT_SCHEMA_PRESERVES_V19_FIELDS=YES
CALCULATION_TYPE_CHANGED=NO
ZONE_PLAN_VERSION_CHANGED=NO
COOLING_LOAD_FORMULA_RECUT=NO
EQUIPMENT_INPUT_CHANGED=NO
POWER_INPUT_CHANGED=NO
INVESTMENT_INPUT_CHANGED=NO
FRONTEND_CHANGED=NO
MIGRATION_CREATED=NO
PR252_STATE_CHANGED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P1 只消费已完成的 zone-plan `position_count` / `required_area_m2`，向九个
制冷区追加 `minimum_estimated_cooling_load_kw_r` 与
`cooling_estimation_basis`。它不修改 `cooling_load`、设备/功率/投资、前端、
迁移或五阶段 `CalculationType`。完成当前 Draft PR 后停止于
`CHARLES_V19_P1_IMPLEMENTATION_REVIEW`；不得 Ready、Merge、发布或开始下一
展示/设备选型阶段。
