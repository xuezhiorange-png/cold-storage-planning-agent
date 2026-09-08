# V2.0 P1：工厂功率估算 canonical result 实现

## 授权与边界

本任务记录 V2.0 P1 的独立实施 gate。P0 契约文档和 ADR-042 中的 P0 授权
块仍然是历史事实，尤其是 `P1_AUTHORIZED=NO` 与
`RUNTIME_IMPLEMENTATION_AUTHORIZED=NO`；本文件不改写它们来伪造授权。

~~~text
TASK_ID=V20_P1_FACTORY_POWER_ESTIMATION_CANONICAL_RESULT_IMPLEMENTATION_R1
P0_CONTRACT_FROZEN=YES
P1_IMPLEMENTATION_SEPARATELY_AUTHORIZED=YES
V20_P1_IMPLEMENTATION_AUTHORIZED=YES
BACKEND_DETERMINISTIC_POWER_IMPLEMENTATION=YES
CANONICAL_RESULT_IMPLEMENTATION=YES
BACKEND_TESTS=YES
P1_DOCUMENTATION=YES

FACTORY_AREA_AUTHORITY_REQUIRED=YES
COLD_STORAGE_AREA_AUTHORITY_REQUIRED=YES
RAW_POSITION_COUNT_USED=NO
REPORTING_SCHEME_BINDING_REQUIRED=YES
LEGACY_REFERENCE_POWER_ROWS_USED_AS_AUTHORITY=NO

POOL_A_FACTOR=0.30
POOL_B_SMALL_FACTOR=1.00
POOL_B_MEDIUM_FACTOR=0.90
POOL_B_LARGE_FACTOR=0.80
POOL_C_FACTOR=0.85
MAIN_SYSTEM_COP=3.3

FRONTEND_CHANGED=NO
AILY_CHANGED=NO
OUTBOUND_LIVE_AILY_SESSION=NO
MIGRATION_CREATED=NO
P2_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_AUTHORIZED=NO
RELEASE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
~~~

实现状态：`V20_P1_IMPLEMENTATION_EXECUTED=YES`。Review Correction R1 已按
独立评审意见完成：mapping-built input 与 direct typed input 共用同一 nested
canonical validation boundary，所有执行面积分母和照明/UV 数值均来自可审计的
静态 registry，并由架构测试从 P0 machine-readable matrix 派生锁定。当前仍停在
独立 re-review gate，不推导 Ready、Merge、tag 或 release。

~~~text
CORRECTION_TASK_ID=V20_P1_FACTORY_POWER_ESTIMATION_CANONICAL_RESULT_REVIEW_CORRECTION_R1
SOURCE_PR=257
SOURCE_HEAD_SHA=ce683e69f8014bfa17242a19c0cd2d7ebbafa293
TYPED_CANONICAL_VALIDATION_UNIFIED=YES
DIRECT_TYPED_FAIL_CLOSED=YES
AREA_DENOMINATORS_EXECUTION_LOCKED=YES
LIGHTING_RUNTIME_REGISTRY_LOCKED=YES
UV_RUNTIME_REGISTRY_LOCKED=YES
READY_EXECUTED=NO
MERGE_EXECUTED=NO
TAG_CREATED=NO
RELEASE_CREATED=NO
~~~

## 实现边界

运行时边界为
`backend/src/cold_storage/modules/calculations/domain/factory_power_estimation.py`，
计算器身份固定为：

~~~text
CALCULATOR_ID=factory_power_estimation
CALCULATOR_VERSION=2.0.0-p1
CALCULATOR_IDENTITY=factory_power_estimation@2.0.0-p1
DISTINCT_FROM=installed_power@1.0.0
~~~

规则以 P0 machine-readable matrix 为唯一治理来源；运行时使用 typed/static
registry，不读取或解析 Markdown/JSON。P1 采用 additive boundary，保留既有
五阶段 `CalculationType` 和 legacy power calculator 的行为，不修改
`power.py`、`reference_power_rows()`、`build_power_configuration()` 或现有
阶段持久化绑定。

## 输入权威与 fail closed

- 必须显式提供 `factory_area_m2`。只接受 SMALL `<=2500`、MEDIUM
  `2500<area<=5000`、LARGE `>5000`；缺失或非法输入返回结构化 blocker，
  不从 total area、吞吐量、日入库量或 zone area 猜测。
- 必须显式提供 `cold_storage_area_m2`。本 P1 不决定它是否包含 −18℃ 冻果间，
  也不把 `refrigerated_area_m2` 或 total area 静默当作替代值。
- 区域面积只来自 `zone_plan.result.zones[].required_area_m2`。
- 一级、二级预冷通过 `reporting_scheme_id` 精确选择 `schemes[]`；从选中方案
  读取 `room_count` 和 `position_count`。缺失、未知、重复或不完整均 fail
  closed。`raw_position_count` 永远不是回退输入。
- 主系统六区只读取各行的
  `minimum_estimated_cooling_load_kw_r`，并在 canonical input snapshot 中保留
  对应的 `cooling_estimation_basis`；缺失、非数值、非有限或负值均 fail
  closed，不切换到 subtotal 或其他冷量字段。
- 九个受控制冷区域必须恰好出现一次；缺少、重复、未知区域均返回结构化
  blocker。

## 规则实现

运行时 registry 与 P0 JSON 由架构测试逐项比对，覆盖：

- 一级/二级预冷每间 2 台冷风机；选中方案的最终板位数乘 4 配置 0.5 kW
  轴流风机；电机进入 POOL_B，化霜拆成独立明细进入 POOL_A。
- raw、分选包装、涂布、成品和出货区域分别使用 P0 的面积规则；分选包装
  先计算 `ceil(required_area_m2 / 70)`，再取不小于 raw count 的偶数。
- 公共设备严格使用 P0 的面积档位数量和功率：电动平移门为 15/30/50、
  0.5 kW/套、POOL_B；快速卷帘门 6/10/16；风幕 4/8/12；升降门/装卸平台
  2/3/4；臭氧与加湿 30 kW；地坪加热 4 kW。
- 照明和紫外线分别为 `ceil(cold_storage_area_m2 / 10) * 0.04 kW` 和
  `ceil(cold_storage_area_m2 / 20) * 0.08 kW`，均进入 POOL_B。
- 主系统严格聚合六区的 V1.9 最低估算冷量并除以 `MAIN_SYSTEM_COP=3.3`；
  冻果、次果暂存和出货通道分别使用 15/25/40、4/6/8、8/12/16 kW 专用
  压缩机，不能重复进入主系统汇总；蒸发式冷凝器使用 20/30/40 kW。
- 生产设备为 200/300/400 kW，独立进入 POOL_C，乘固定 0.85，不经过
  POOL_B。

每条 canonical detail 都拆分设备/区域、依据、配置数量、单台功率、装机功率、
功率池、同时系数和计入功率。summary 保留 POOL_A/POOL_B/POOL_C 的装机及
计入功率、总装机功率和 `estimated_total_power_kw`。内部使用 Decimal；JSON
边界使用稳定的十进制字符串，不引入新的任意 rounding policy。单位是 kW，
并明确不是 kWh、计量电量或日用电量。

## 未授权事项与持久化边界

本 P1 没有前端、工作台、报告、Aily/Doubao runtime 或 outbound live session
改动；消费者后续只能读取同一个后端 canonical result，不能复制公式或重算。
没有新增 Alembic migration、表或列，也没有设备厂商选型、变压器校核、kWh、
电价、月度电费或正式电气设计。如果未来 generic persistence 不能在现有结构
下保存该结果，必须先另行处理 schema gate，不在本 P1 偷加迁移。

## 测试证据与停止点

- P1 unit tests 覆盖面积边界、九区数量、预冷 6/8-position、公共设备、照明、
  六区主压缩机、专用系统、冷凝器、三池互斥、summary、Decimal 重放及 mapping/
  direct typed hostile fail-closed 输入；面积分母边界必须能反映执行值漂移。
- P1 architecture test 将 P0 JSON 与 runtime registry 对照，并锁定 P0 历史
  授权、P1 独立授权、legacy/外部副作用边界、五阶段枚举、前端/Aily/迁移范围。
- 本任务完成后仅创建并保持 Draft PR，等待 Charles 独立 Review；不执行 Ready、
  Merge、tag 或 release。
