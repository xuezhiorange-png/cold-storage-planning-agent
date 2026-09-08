# ADR-042：冻结 V2.0 工厂功率估算与统一呈现契约

- 状态：Accepted for V2.0 P0 contract freeze; implementation not authorized
- 日期：2026-09-08
- 基线：v1.9.0 / main@8f48332435f4916bdb9ab8430d686678c1efc576
- 关联任务：V20_P0_FACTORY_POWER_ESTIMATION_AND_PRESENTATION_CONTRACT_R1

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

前端和 Aily 可以解释或查询 canonical 数据，但不得复制公式、重建数量、
重乘系数或建立出站实时 Aily 会话。

## Consequences

- 规则和边界拥有可被架构测试直接验证的单一契约来源。
- 后续运行时实现必须先解决 factory_area_m2 缺失和
  cold_storage_area_m2/refrigerated_area_m2 的名称及派生口径映射。
- V1.9 的最低估算字段与详细冷量快照的 subtotal_load_kw_r 明确区分；
  不允许无审计替换。
- 现有 installed_power@1.0.0、equipment.py、power.py、报告和前端在
  本 P0 中保持不变。
- 本 ADR 的接受不授予 P1、P2、Ready、Merge、标签、发布或正式设计权限。

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
