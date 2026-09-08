# V2.0 版本计划：工厂功率估算与统一呈现契约

**状态：** V2.0 P0 契约冻结；P1 已合并到 `main`，P2 只读消费者对齐已由 Charles 单独授权并在本分支实施，当前等待 P2 独立 Review。
**上一版本：** v1.9.0 at main@8f48332435f4916bdb9ab8430d686678c1efc576。
**本版方向：** 冷间设备数量、设备装机功率、化霜/其他/生产功率池、同时系数和工厂最终估算电功率。
**产品身份：** 冷库规划与概念设计辅助工具，不替代正式电气设计、设备选型、变压器容量校核或计量。

~~~text
TASK_ID=V20_P0_FACTORY_POWER_ESTIMATION_AND_PRESENTATION_CONTRACT_R1
EXPECTED_BASELINE=v1.9.0
BASE_MAIN_SHA=8f48332435f4916bdb9ab8430d686678c1efc576
V20_STATUS=P0_CONTRACT_FROZEN
V20_P0_AUTHORIZED=YES
MODE=DOCS_CONTRACT_ARCHITECTURE_TEST_ONLY
RUNTIME_IMPLEMENTATION_AUTHORIZED=NO
FRONTEND_IMPLEMENTATION_AUTHORIZED=NO
AILY_IMPLEMENTATION_AUTHORIZED=NO
OUTBOUND_LIVE_AILY_SESSION_AUTHORIZED=NO
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

## 当前实施状态：V2.0 P1

上面的 P0 授权块是 P0 gate 的历史记录，原样保留。其中的
`P1_AUTHORIZED=NO` 和 `RUNTIME_IMPLEMENTATION_AUTHORIZED=NO` 不代表本次
P1 gate；本节记录 Charles 对 P1 的独立授权及本分支实际实施范围。

~~~text
TASK_ID=V20_P1_FACTORY_POWER_ESTIMATION_CANONICAL_RESULT_IMPLEMENTATION_R1
P0_CONTRACT_FROZEN=YES
P1_IMPLEMENTATION_SEPARATELY_AUTHORIZED=YES
V20_P1_IMPLEMENTATION_AUTHORIZED=YES
V20_P1_IMPLEMENTATION_EXECUTED=YES
V20_P1_IMPLEMENTATION_STATUS=IMPLEMENTATION_MERGED_IN_MAIN
V20_P1_MERGE_COMMIT_SHA=2a1a2797767a52834143a78b3e80193b5752b2e6
V20_CANONICAL_RESULT=IMPLEMENTED_ADDITIVELY
FACTORY_AREA_AUTHORITY_REQUIRED=YES
COLD_STORAGE_AREA_AUTHORITY_REQUIRED=YES
REPORTING_SCHEME_BINDING_REQUIRED=YES
RAW_POSITION_COUNT_USED=NO
LEGACY_REFERENCE_POWER_ROWS_USED_AS_AUTHORITY=NO
FRONTEND_IMPLEMENTATION_AUTHORIZED=NO
AILY_IMPLEMENTATION_AUTHORIZED=NO
OUTBOUND_LIVE_AILY_SESSION_AUTHORIZED=NO
DATABASE_MIGRATION_AUTHORIZED=NO
P2_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_AUTHORIZED=NO
RELEASE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
~~~

P1 新增独立的纯 Domain 计算边界和 typed canonical result 序列化；Review
Correction R1 已补齐 direct typed fail-closed 校验，并将执行中的面积分母、照明
和 UV 数值纳入 P0→runtime 架构锁。它不替换
五阶段 `CalculationType`，不接入旧 `installed_power@1.0.0`，也不新增数据库
迁移、前端呈现或 Aily/Doubao 出站会话。实现细节和测试证据见
[V2_0-P1-factory-power-estimation-canonical-result-implementation.md](V2_0-P1-factory-power-estimation-canonical-result-implementation.md)。

~~~text
NO_AILY_RECALCULATION
NO_FRONTEND_RECALCULATION
NO_OUTBOUND_LIVE_AILY_SESSION
~~~

## 当前实施状态：V2.0 P2

P1 canonical calculator 已在 `main@2a1a2797767a52834143a78b3e80193b5752b2e6`
合并。Charles 随后单独授权 P2，本切片只把已经存在的
`factory_power_estimation@2.0.0-p1` 结果投影到工作台和 Aily/Doubao 的只读
呈现边界；不触发计算、不替换五阶段 power、不改数据库结构。

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

P2 的共享 read-model 只做 canonical result 的 shape validation、字段复制、中文
呈现标签和完整性 hash。工作台保留独立的“估算工厂电功率（V2.0）”卡片；旧
`installed_power@1.0.0` 仍是五阶段 power，`power_configuration` 仍是补充/演示
数据。缺失或非法的 V2 结果在两侧均显式不可用，绝不回退到旧功率结果。
实现细节、跨消费者 golden test 和门禁记录见
[V2_0-P2-factory-power-read-only-presentation-alignment.md](V2_0-P2-factory-power-read-only-presentation-alignment.md)。

本计划的 P0 段落只冻结规则和数据呈现边界；当前 P1/P2 实施仍受各自任务文件和
授权块约束。正式契约和机器可读规则矩阵见
[V2_0-P0-factory-power-estimation-and-presentation-contract.md](V2_0-P0-factory-power-estimation-and-presentation-contract.md)；
架构决策见
[ADR-042-factory-power-estimation-and-presentation-contract.md](../architecture/ADR-042-factory-power-estimation-and-presentation-contract.md)。

## 1. P0 冻结目标

P0 冻结以下六件事：

1. 九个制冷区域的冷风机数量、单台电机功率和化霜功率；
2. 公共设备、蒸发式冷凝器、照明、紫外线和生产设备的装机功率规则；
3. 主压缩机系统的六区边界、COP=3.3 和三个专用压缩机组；
4. POOL_A=DEFROST、POOL_B=OTHER、POOL_C=PRODUCTION 的互斥归属；
5. 各功率池同时系数和最终 estimated_total_power_kw；
6. 工作台与豆包/Aily 共同读取的 canonical result 与最小呈现列。

所有规则均是概念设计阶段的估算契约。实现后仍须保留输入、单位、公式、系数、
来源、假设、警告和人工复核状态；本 P0 不批准任何具体厂商型号或正式电气方案。

## 2. 当前代码审计结论

P0 对照 v1.9.0 基线完成了字段和边界审计。下面的“当前字段”是仓库事实，
不是本 P0 新增的运行时字段。

| 审计对象 | 当前仓库事实 | V2.0 契约处理 |
| --- | --- | --- |
| 加工厂面积档位输入 | ColdRoomZonePlanInput 没有 factory_area_m2；build_power_configuration() 收到 total_area_m2 后明确未使用，并按日入库量比例缩放旧演示清单 | 目标字段仍是 factory_area_m2；在后续实现前必须完成权威输入映射。不得用 total_area_m2、吞吐量或冷间面积代替 |
| 区域面积 | zone_plan.result.zones[] 每行有 required_area_m2；total_area_m2/total_required_area_m2 是所有规划区域的合计 | required_area_m2 冻结为逐区 PLANNED_ZONE_AREA |
| 冷间面积 | 当前没有字面量 cold_storage_area_m2；refrigerated_area_m2 在不同路径存在口径差异：规划/演示路径按非“常温”区域汇总，operator-minimal lineage 路径只汇总 8~10℃ 与 1~3℃ | 照明规则的业务字段名为 cold_storage_area_m2；refrigerated_area_m2 只能作为候选字段，必须先冻结是否包含 −18℃ 冻果间并统一来源，不能改用全厂建筑面积 |
| 预冷 6/8-position 输出 | zone_planning.py 同时输出 schemes[] 中的 6_position 与 8_position，每个方案有 room_count、position_count、required_area_m2；当前 reporting scheme 是 6_position | 冻结方案级 2 台冷风机/间、3/4 个板位/台；后续实现必须读取最终被选定的方案，不得读取 raw_position_count |
| V1.9 逐区冷量字段 | zone_plan.result.zones[] 有 minimum_estimated_cooling_load_kw_r 和 cooling_estimation_basis；详细冷量快照另有 subtotal_load_kw_r | 主系统的“六区权威制冷量”契约字段明确使用 V1.9 最低估算字段；subtotal_load_kw_r 是现有详细冷量阶段字段，不得无映射静默替换 |
| 现有设备/功率边界 | equipment.py 是能力计算器；power.py 是五阶段 installed_power@1.0.0；旧 build_power_configuration() 仍使用参考设备清单、日入库量缩放、0.90 运行系数并把化霜并入 refrigeration | V2.0 规则只在本契约中冻结。后续运行时必须建立可审计的 V2 canonical result；本 P0 不改上述模块或其版本 |

当前发现的字段映射问题与边界审计事项，均留给独立实现闸门：

~~~text
MAPPING_ISSUE_FACTORY_AREA=NO_LITERAL_AUTHORITY_FIELD
MAPPING_ISSUE_COLD_STORAGE_AREA=CONFLICTING_EXISTING_DERIVATIONS
MAPPING_ISSUE_PRECOOLING_SELECTION=CURRENT_REPORTING_SCHEME_IS_6_POSITION_WITH_8_POSITION_ALTERNATE
MAPPING_ISSUE_V19_DETAIL_LOAD=MINIMUM_ESTIMATE_AND_SUBTOTAL_ARE_DISTINCT_FIELDS
~~~

这些记录不构成 P1 授权，也不允许实现者自行猜测映射。

## 3. 后续切片与门禁

| 切片 | 状态 | 允许内容 |
| --- | --- | --- |
| P0 | **本 PR：契约冻结** | 规则矩阵、字段审计、ADR、架构测试 |
| P1 | **已合并到 main；Review Correction R1 已完成** | 后端确定性计算、canonical result 和持久化边界；不包含消费者接入或 schema 变更 |
| P2 | **已授权；本分支实施，等待独立 Review** | 工作台与豆包/Aily 只读呈现对齐；不包含重新计算、迁移或旧 power 替换 |
| 发布 | 未授权 | 任何 release/tag 必须另过发布门禁；不由 P0 推导 |

P0 Review 的通过只证明契约可审计；P1 和 P2 均须以各自明确的授权与独立门禁为准，
不因当前 P2 实施或测试通过而推导 Ready、Merge、发布或生产设计。
NO_STEP_IMPLIES_THE_NEXT=TRUE。

## 4. 不在本版

~~~text
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
OUTBOUND_LIVE_AILY_SESSION_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
~~~

最终结果的术语必须保持为“估算工厂电功率”，单位为 kW。它不是 kWh 能量、
不是电表计量值，也不是日用电量。
