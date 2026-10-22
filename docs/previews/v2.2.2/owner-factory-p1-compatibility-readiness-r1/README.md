# Owner业务输入 → P1兼容性与实施准入研究

TASK=V2_2_2_OWNER_FACTORY_INPUT_P1_COMPATIBILITY_READINESS_R1

**结论：业务规则可离线计算，但尚不具备正式P1实施/启用条件。**
不能把336kg/人·日替换成192kg/人·班后沿用旧流水线。
质量口径、两班分配、台位共用政策、功能面积及完整来源绑定都需要明确版本化。
本轮只新增分析、接口草案、测试与证据；不修改生产消费者、P1面积或历史布局。

## 一、旧规则的真实重放与有效路径

参考HEAD为`75188edb520c49bd4500008a68bd13aaa3448426`，两条CI均SUCCESS后开展。
完整计算器重放来源为封存的20吨Canonical输入，未把包装量新参数塞入旧输入。

|旧20吨事实|实际值|
|---|---|
|包装参数|16件/人·时 × 1.5kg/件 × 14时/日 =336kg/人·日|
|人员数|ceil(20000/336)=60|
|需求包装台|ceil(60/3)=20|
|布局格位|7×3=21，其中1个空格；不是把安装台数改成21|
|原始分选包装面积|565.76m²|
|面积系数/报告面积|1.1 / 622.34m²|
|P1精确面积/外廓|622.336m² / 45.76×13.6m|
|办公室/更衣室/覆膜间|60 / 40 / 80m²|
|总报告面积|2194.59m²|

[完整重放](legacy-canonical-replay.json)同时记录：
全快照相等、普通排序紧凑JSON字节相等、项目canonical JSON字节相等及两个不同口径的SHA。
普通JSON SHA不是生产canonical_hash，不混用。
真实P1 Dimension Handoff也与封存结果逐字节相等，未声称新Owner模式取得了服务器Authority。
这只是区域计算/尺寸投影，不是CP-SAT、Placement或新的整厂验收。

当前有效调用链及行号/文件SHA见[生产规则审计](legacy-current-rule-audit.json)：

```text
ColdRoomZonePlanInput
 -> plan(): raw kg/day /1000 -> <25t / [25,50)t / >=50t
 -> office(60,80,100), changing(40,80,120), coating(80,120,200)
 -> _sorting_packaging_zone(): ceil(raw kg/day / productivity)
 -> ceil(workers / workers_per_packing_table)
 -> _pack_sorting_rectangle -> _pack_rectangle
 -> round(raw area,2) -> round(raw area *1.1,2)
 -> canonical P1 binder / exact-area profile -> P2 dimensions and constraints
```

`office_fixed_area_m2=60`、`changing_fixed_area_m2=100`、`coating_fixed_area_m2=120`
是输入默认值，**不是当前生效的三项固定面积Authority**。
将三值改为正数1/2/3后，`result`完全不变，三项面积仍由吨位档决定。
这些字段仍被序列化且通过统一正数检查；设为0会拒绝，修改它们也会改变输入/完整结果Hash。
因此它们“参与输入与校验，但不消费为面积”，不是可以随意删掉的无影响字段。

同样，Input的`packing_area_factor=1.5`不是当前分选包装的1.1系数；
后者来自计算器构造时的业务配置。台位间距公式读模块常量，不读同名Input间距字段。
`workers_per_packing_table`则确实由Input消费，冻结案例为3；不能把这些输入默认值一概当成生效公式。

## 二、新规则的四个人数口径

`OwnerFactoryFunctionalInputsV1` / `owner-factory-functional-inputs@1.0.0`
原合同只读，历史字段及Hash原样保留。

|新量|计算|用途与限制|
|---|---|---|
|第一班人数N1|ceil(Q1/192)|第一班明确包装产品质量|
|第二班人数N2|ceil(Q2/192)|第二班明确包装产品质量|
|两班独立员工总数|N1+N2|独立个人柜位，不跨班共用|
|峰值同时包装人数|max(N1,N2)|无班次重叠的时序前提；可供台位政策评审|
|同时更衣人数|max(N1,N2)|整班更衣，不继续默认分批|

Q1/Q2必须有包装产品质量来源与明确分班。原果量不是包装成品量，数值相同也不等于语义相同。
详见[质量口径与班次合同](mass-basis-and-shift-allocation.md)和[逐字段兼容矩阵](owner-v1-input-mapping.json)。

## 三、包装台与面积：只做未批准敏感性分析

`PROPOSED_PEAK_CONCURRENCY_TABLE_POLICY=ENGINEERING_PROPOSAL_NOT_APPROVED`。
若原3人/台可以沿用，且同一批台位跨班共用：

```text
候选台数 = max(ceil(N1/3), ceil(N2/3)) = ceil(max(N1,N2)/3)
```

若明确不共用，两个班分别配台，候选库存为`ceil(N1/3)+ceil(N2/3)`。
二者都需要Owner另行审核；不能用员工总数自动计算生产并发台位。
历史3人/台、台间模块5.6×3.0m、长短向间距总量8.0/7.6m、格位排序和1.1系数
来自旧业务Authority，**不自动获准用于新包装箱工艺、班制和设备**。

本目录显式合成例均为20000kg包装产品，**不是旧20000kg原果的默认100%出成率转换**：

|明确合成分班kg|N1/N2|员工/柜位总数|峰值|共用台位假设|旧公式投影报告面积m²|
|---|---|---|---|---|---|
|10000 /10000|53 /53|106|53|18|538.56|
|16000 /4000|84 /21|105|84|28|759.62|

这些数值由真实旧排布算法只读计算，并非手写新工程结果。
详见[分班、台位与面积敏感性JSON](staffing-and-table-compatibility.json)。
不输出新Canonical/P1面积，不替换旧622.34，不计算新的正式整厂总面积。
新旧质量口径及定员语义不同，`COMPARISON_STATUS=NOT_COMPARABLE`：
不能把较小或较大的投影面积解释为新算法更优或更差。
分选包装P1还依赖实际上游格位和精确面积证据，不能只改面积数字。

## 四、其他房间与别名

旧25/50吨档只定义旧三种房间面积，不定义新SMALL/MEDIUM/LARGE办公室规模。
未知显式规模返回OWNER_INPUT_REQUIRED，不自动按20吨映射12人。
新柜位/同时人数不能乘无来源人均面积；新封膜100%设计负荷也不能决定设备台数或面积。
封膜运行时间独立待确认，不从包装设施16小时继承。
面积与下游影响详见[面积影响矩阵](area-impact-matrix.md)。

业务别名SECONDARY_PRECOOLING/COATING_ROOM/FINISHED_GOODS分别映射到
正式P0的SECONDARY_PRECOOL/COATING/FINISHED_STORAGE，不修改顺序或原枚举。
旧字段`GENDER_INDEPENDENT_ZONING_PRESET=false`名称有歧义；未来建议显式迁移为
`SEPARATE_GENDER_ZONES_PRESET=false`，表达“不预设男女独立功能区”。
本轮不改旧字段，不将false解释为卫生/隐私已合规。
详见[角色与字段迁移设计](role-and-field-alias-mapping.json)。

## 五、安全接入路径与当前阻断

1. A：`BUSINESS_RULES_READY=true`——Owner规则已确认、可离线计算。
2. B：`P1_INTEGRATION_IMPLEMENTATION_READY=false`——质量来源批准、台位/面积决策、
   版本身份与迁移/回退方案仍需审核；本次只完成准备就绪性审查。
3. C：`P1_PRODUCTION_ACTIVATED=false`——需要独立Owner授权的正式实现、回归和CI/版本验收。

离线草案[输出合同](p1-compatibility-output-contract.json)显式分开LEGACY_CANONICAL与OWNER_V1_PROPOSED。
离线来源检查实际读取文件并匹配字节SHA、质量、单位、项目、时段及分班数量；
但**文件内容匹配不等于项目真实性/Owner批准**，不能据此完成正式准入。
缺文件、伪Hash、来源错配或调用方verified字段均拒绝相应离线绑定；
即使合成来源匹配，正式接入仍BLOCKED。
[缺项与准入](missing-input-admission.json)分列输入、Authority决策及实现阻断。
[P1接入与回退设计](p1-integration-readiness.md)说明未来如何不破坏历史结果。

## 复现与范围

使用仓库已有锁定环境，不安装/升级依赖。在仓库根目录：

```sh
PYTHONPATH=backend/src backend/.venv/bin/python3 docs/previews/v2.2.2/owner-factory-p1-compatibility-readiness-r1/offline_compatibility.py
PYTHONPATH=backend/src backend/.venv/bin/python3 docs/previews/v2.2.2/owner-factory-p1-compatibility-readiness-r1/test_offline_compatibility.py
```

新业务数量采用精确有理数；旧结果及假设投影保留原生产float/round语义，不暗改历史精度。
同输入结果确定；测试与质量记录见[validation.json](validation.json)，完整性见[source_manifest.json](source_manifest.json)。
不改生产代码、旧Owner合同、8套布局、P0、P1/P2、Selector、Tool7、MCP、Truck或资源预算。
D01/D03/D04及262 UNKNOWN保留；无真实布局求解、原生求解调用或Owner Grant。
Stage B、P2D、版本均不因本次文档完成；不Ready/Merge/Release/Deploy，交付后STOP。
