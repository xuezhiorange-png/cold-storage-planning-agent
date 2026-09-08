# ADR-042：冻结 V2.0 工厂功率估算与统一呈现契约

- 状态：Accepted; P0 contract frozen, P1 merged, P2 read-only presentation merged; V2.0 implementation complete and released; release closure active (historical and completed); V2.1 P0 active
- 日期：2026-09-08
- 当前主线：v2.0.0 / main@a7049ca93d238013c0cf62069fe1e0a89ff834d7
- 关联任务：V20_RELEASE_CLOSURE_READINESS_R1

## Context

V1.9 已把九个制冷区域的最低估算制冷量写入
zone_plan.result.zones[] 的
minimum_estimated_cooling_load_kw_r，并保留
cooling_estimation_basis。当前仓库仍有独立的设备能力计算器、
五阶段 installed_power@1.0.0 和旧的演示型 build_power_configuration。
这些现有表面不能直接表达 V2.0 所要求的冷风机数量、化霜/其他/生产
三池、面积档位和最终估算工厂电功率。

本 ADR 只冻结未来实现必须遵守的工程边界和消费者呈现边界。它不把
现有演示代码升级为 V2.0 运行时，也不改变任何计算结果、数据库结构、
工作台或豆包输出。

## Decision

### 1. 面积档位由加工厂面积唯一决定

V2.0 使用权威 factory_area_m2，边界为：

~~~text
SMALL  = factory_area_m2 <= 2500
MEDIUM = 2500 < factory_area_m2 <= 5000
LARGE  = factory_area_m2 > 5000
~~~

2500 m² 和 5000 m² 均归较低档。当前
ColdRoomZonePlanInput 没有 factory_area_m2，旧
build_power_configuration() 也不使用 total_area_m2；后续实现必须
先补齐权威输入映射并在缺失时 fail closed。任何吞吐量、total_area_m2、
refrigerated_area_m2 或 zone area 的替代都不被默许。

### 2. 区域面积和冷间面积分开命名

逐区面积的权威字段是
zone_plan.result.zones[].required_area_m2，语义为
PLANNED_ZONE_AREA。照明业务字段名为 cold_storage_area_m2。
当前仓库没有同名字段，但应用层已有候选字段
refrigerated_area_m2；不同路径的派生口径并不一致：规划/演示路径按
非“常温”区域汇总并包含 −18℃，operator-minimal lineage 路径只汇总
8~10℃ 和 1~3℃。后续实现必须先冻结是否包含冻果间，并在 canonical
result 中保留唯一来源和语义；不能把全厂建筑总面积当作冷间面积。

### 3. 冷风机数量按九区规则冻结

一级和二级预冷均支持 6-position 与 8-position 方案。每个方案间固定
两台冷风机，分别为每台 3 个板位和 4 个板位。冷风机电机/化霜功率为：

| 区域 | 电机 | 化霜 |
| --- | ---: | ---: |
| 一级预冷间 | 6.6 kW/台 | 19.6 kW/台 |
| 二级预冷间 | 3.0 kW/台 | 22.0 kW/台 |

每个预冷板位配置四台 0.5 kW 轴流风机。其余七个区域的数量分别按
required_area_m2 的 80、70、70、70、固定 1、固定 1、50 m² 规则
计算；分选包装间先算 ceil(area/70)，再取不小于 raw_count 的偶数。
对应电机和化霜系数以 P0 契约 JSON 为唯一矩阵。

后续实现只能读取最终被选定的 scheme 的 room_count/position_count。
现有 planner 的 raw_position_count 是中间量，永远不能成为冷风机或
冷量的回退输入。

### 4. 主压缩机系统禁止重复计数

主系统且仅主系统覆盖：

~~~text
primary_precooling_room
secondary_precooling_room
raw_fruit_buffer
sorting_packaging_room
coating_room
finished_goods_room
~~~

主系统制冷量是上述六区的权威 V1.9
minimum_estimated_cooling_load_kw_r 之和。主压缩机轴功率使用固定
MAIN_SYSTEM_COP=3.3。冻果间、次果暂存区和出货通道各自使用
SMALL/MEDIUM/LARGE 的 15/25/40、4/6/8、8/12/16 kW 专用功率，
并且不得再次进入主系统的 COP 汇总。所有主系统和专用系统轴功率
属于 POOL_B。

### 5. 三个功率池必须互斥

- POOL_A=DEFROST：只包含所有冷风机化霜装机功率，系数 0.30。
- POOL_B=OTHER：包含冷风机电机、预冷轴流风机、全部压缩机轴功率、
  蒸发式冷凝器、公共门/风幕/升降平台、臭氧与加湿、地坪加热、
  冷间照明和紫外线；系数按 SMALL/MEDIUM/LARGE 为 1.00/0.90/0.80。
- POOL_C=PRODUCTION：只包含生产设备，装机功率按面积档位为
  200/300/400 kW，系数固定 0.85。

生产设备不得先进入 POOL_B。最终估算功率是三池计入功率之和，同时保留
三池装机功率之和。结果语义是估算电功率 kW，不是 kWh、计量电量或日
用电量。

### 6. Workbench 和 Doubao/Aily 共享一个 canonical result

两个消费者都只能读取同一个后端 canonical result。明细至少提供：
设备/区域、依据、配置数量、单台功率、装机功率、功率池、同时系数和
计入功率。总览至少提供三池装机/计入功率、总装机功率和最终估算
用电功率。

~~~text
NO_AILY_RECALCULATION
NO_FRONTEND_RECALCULATION
NO_OUTBOUND_LIVE_AILY_SESSION
~~~

## P1 implementation addendum (separate authorization)

The P0 authorization block above remains historical and is intentionally not
rewritten. Charles separately authorized the V2.0 P1 backend implementation
under `V20_P1_FACTORY_POWER_ESTIMATION_CANONICAL_RESULT_IMPLEMENTATION_R1`.
This addendum records the implementation boundary without changing the P0
contract or granting a later gate.

~~~text
P0_CONTRACT_FROZEN=YES
P1_IMPLEMENTATION_SEPARATELY_AUTHORIZED=YES
V20_P1_IMPLEMENTATION_AUTHORIZED=YES
V20_P1_IMPLEMENTATION_EXECUTED=YES
V20_P1_IMPLEMENTATION_STATUS=IMPLEMENTATION_MERGED_IN_MAIN
V20_P1_MERGE_COMMIT_SHA=2a1a2797767a52834143a78b3e80193b5752b2e6
CALCULATOR_IDENTITY=factory_power_estimation@2.0.0-p1
DISTINCT_FROM=installed_power@1.0.0
FACTORY_AREA_AUTHORITY_REQUIRED=YES
COLD_STORAGE_AREA_AUTHORITY_REQUIRED=YES
RAW_POSITION_COUNT_USED=NO
REPORTING_SCHEME_BINDING_REQUIRED=YES
LEGACY_REFERENCE_POWER_ROWS_USED_AS_AUTHORITY=NO
DATABASE_MIGRATION_AUTHORIZED=NO
FRONTEND_IMPLEMENTATION_AUTHORIZED=NO
AILY_IMPLEMENTATION_AUTHORIZED=NO
OUTBOUND_LIVE_AILY_SESSION_AUTHORIZED=NO
P2_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_AUTHORIZED=NO
RELEASE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
~~~

The implementation is additive in the calculations Domain at
`factory_power_estimation.py`. It uses a typed/static copy of the P0 rule
matrix, requires explicit area authorities and selected pre-cooling schemes,
fails closed on missing V1.9 minimum cooling loads, and emits one deterministic
canonical result with Decimal arithmetic and auditable detail/summary fields.
It does not replace the five-stage `CalculationType`, bind the legacy
`installed_power@1.0.0` calculator, alter existing persistence, or add a
migration. Frontend, report, Aily/Doubao, outbound-session, P2, Ready, Merge,
tag, and release work remain separately gated.

前端和 Aily 可以解释或查询 canonical 数据，但不得复制公式、重建数量、
重乘系数或建立出站实时 Aily 会话。

## P2 read-only presentation addendum (separate authorization)

The P0 authorization lock and the P1 implementation record above remain
historical records. P1 was merged at
`2a1a2797767a52834143a78b3e80193b5752b2e6`. Charles separately authorized the
following P2 consumer-alignment slice; it does not grant Ready, Merge, tag, or
release authority.

~~~text
TASK_ID=V20_P2_FACTORY_POWER_CANONICAL_RESULT_READ_ONLY_PRESENTATION_ALIGNMENT_R1
P0_CONTRACT_FROZEN=YES
P1_IMPLEMENTATION_MERGED=YES
P1_MERGE_COMMIT_SHA=2a1a2797767a52834143a78b3e80193b5752b2e6
P2_IMPLEMENTATION_SEPARATELY_AUTHORIZED=YES
V20_P2_IMPLEMENTATION_AUTHORIZED=YES
V20_P2_IMPLEMENTATION_EXECUTED=YES
CANONICAL_SOURCE=factory_power_estimation@2.0.0-p1
WORKBENCH_READ_ONLY=YES
AILY_READ_ONLY=YES
WORKBENCH_AND_AILY_READ_SAME_RESULT=YES
FRONTEND_RECALCULATION=NO
AILY_RECALCULATION=NO
INSTALLED_POWER_REPLACED=NO
POWER_CONFIGURATION_USED_AS_V2_AUTHORITY=NO
FIVE_STAGE_CALCULATION_TYPE_CHANGED=NO
OUTBOUND_LIVE_AILY_SESSION_AUTHORIZED=NO
DATABASE_MIGRATION_CREATED=NO
P3_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_AUTHORIZED=NO
RELEASE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
~~~

P2 adds a shared read-only presentation model under the calculations
application boundary and an independent Aily/Doubao projector. Both copy the
serialized P1 canonical result, preserve the exact calculator identity and
engineering fields, and use the same canonical-result integrity hash. The
workbench adds a separate V2 card while retaining the legacy
`installed_power@1.0.0` card and `power_configuration` supplemental surface.
Missing or malformed V2 data fails closed; it never falls back to either
legacy power surface. No calculation trigger, migration, schema change,
outbound Aily session, or P3 work is included.

## V2.0 release closure status

P0、P1、P2 的原始 authorization blocks 保留为历史记录；其中的
`P2_AUTHORIZED=NO`、`READY_AUTHORIZED=NO` 和 `MERGE_AUTHORIZED=NO` 不代表
当前 release closure 的授权状态。当前实施事实和候选发布就绪评估如下：

~~~text
V20_IMPLEMENTATION_COMPLETE=YES
P0_STATUS=MERGED
P1_STATUS=MERGED
P2_STATUS=MERGED
P1_MERGE_COMMIT_SHA=2a1a2797767a52834143a78b3e80193b5752b2e6
V20_P2_PR_NUMBER=258
V20_P2_REVIEW_RESULT=PASS
V20_P2_BLOCKER_COUNT=0
V20_P2_FINAL_HEAD_SHA=2759538bcd32f7468de50c740ca17d7fbe18f49b
V20_P2_MERGE_COMMIT_SHA=5d5a9cad010a629bf52f6534fba37d047c330e00
V20_P3_DEFINED=NO
V20_P3_EXECUTED=NO
TARGET_RELEASE=v2.0.0
V2_0_0_RELEASE_CANDIDATE=YES
V2_0_0_RELEASE_READY=YES
TAG_CREATION_AUTHORIZED=NO
GITHUB_RELEASE_CREATION_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
NEXT_FEATURE_LANE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
~~~

The release-closure block above is the historical readiness record. V2.0 release
execution subsequently completed at `v2.0.0`; the active governance lane is now
V2.1 P0 and no V2.1 implementation is implied.

## V2.0 release execution completed

~~~text
V2_0_0_RELEASED=YES
V2_0_0_TAG=v2.0.0
V2_0_0_RELEASE_COMMIT=a7049ca93d238013c0cf62069fe1e0a89ff834d7
GITHUB_RELEASE_CREATED=YES
ACTIVE_GOVERNANCE_LANE=V2.1_P0
NO_STEP_IMPLIES_THE_NEXT=TRUE
~~~

v2.0.0 已发布；该事实不改写 P0/P1/P2 的历史 authorization blocks。

## Consequences

- 规则和边界拥有可被架构测试直接验证的单一契约来源。
- 后续运行时实现必须先解决 factory_area_m2 缺失和
  cold_storage_area_m2/refrigerated_area_m2 的名称及派生口径映射。
- V1.9 的最低估算字段与详细冷量快照的 subtotal_load_kw_r 明确区分；
  不允许无审计替换。
- 现有 installed_power@1.0.0、equipment.py、power.py、报告和前端在
  本 P0 中保持不变。
- 本 ADR 的接受不授予 P1、P2、Ready、Merge、标签、发布或正式设计权限。
- 历史 P2 Draft PR 和 CI 通过不自动授予 Ready、Merge、标签、发布或正式设计权限；
  V2.0 的独立 release gate 已在 `v2.0.0` 完成，V2.1 P0 仍需遵守自己的
  implementation、Ready、Merge、tag、Release、部署和正式设计 gate。

## Alternatives rejected

1. 直接在旧 build_power_configuration() 上改系数：它按日入库量缩放旧
   演示清单，且不具备本 ADR 的三池互斥和面积档位语义。
2. 用 total_area_m2 作为 factory_area_m2：当前 total_area_m2 是规划
   区域面积合计，不是加工厂面积。
3. 用 total_area_m2 作为 cold_storage_area_m2：它还可能包含常温包材库，
   不能替代冷间面积；refrigerated_area_m2 的现有派生口径也必须先统一。
4. 把生产设备放进 OTHER：会错误应用面积档位系数，违反 POOL_C=0.85。
5. 把三个专用区域再放入主系统 COP 汇总：会造成冷量和压缩机轴功率
   重复计数。
6. 在 Vue、报告模板或 Aily 中重算：破坏后端 canonical result 的
   可追溯性和消费者一致性。

## Authorization lock

~~~text
MODE=DOCS_CONTRACT_ARCHITECTURE_TEST_ONLY
RUNTIME_IMPLEMENTATION_AUTHORIZED=NO
FRONTEND_IMPLEMENTATION_AUTHORIZED=NO
AILY_IMPLEMENTATION_AUTHORIZED=NO
OUTBOUND_LIVE_AILY_SESSION_AUTHORIZED=NO
RUNTIME_CODE_CHANGE=NO
FRONTEND_CODE_CHANGE=NO
AILY_RUNTIME_CHANGE=NO
DATABASE_MIGRATION=NO
EQUIPMENT_MODEL_SELECTION=NO
TRANSFORMER_SIZING=NO
KWH_ESTIMATION=NO
ELECTRICITY_PRICE=NO
MONTHLY_BILL=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
P1_AUTHORIZED=NO
P2_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
~~~

~~~text
NO_AILY_RECALCULATION
NO_FRONTEND_RECALCULATION
NO_OUTBOUND_LIVE_AILY_SESSION
~~~
