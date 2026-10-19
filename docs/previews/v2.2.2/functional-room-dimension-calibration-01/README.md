# 功能房间尺度校准：证据、条件模块与消费设计

TASK=REVIEW_FUNCTIONAL_ROOM_DIMENSION_CALIBRATION_01

WORK_PACKAGE=REVIEW-NUMERIC-CALIBRATION

## 结论：可提出条件化模块，尚不能冻结通用最小宽度

三类房间、24个真实几何已逐一复核，原8物理几何/6实质组织/4家族保持。
[原8套审图及质量基线](../stage-b/layout-quality-baseline-01/README.md)不修改。
Office60、Changing40、Coating80m²是**现有几何面积Authority**，不是使用人数、设备选型，
也未明确为装修后净使用面积。STAFF_COUNT=UNAVAILABLE。
缺少真实人数/配置、可比功能正例和净空间参考，NUMERIC_CALIBRATION_READY=false。
本轮没有新增Hard、人数默认值、比例上下限、房间坐标、Owner Grant或真实CP-SAT调用。

最直接的根因不是“面积算错”，而是柔性Authority只给面积和旋转，没有功能尺度。
GlobalModel在场地诱导有限域内从1mm起建立局部宽深，要求乘积≥面积，
再约束Site/障碍/MUST/Portal等。AccessModel保留父模型。
非null min/max width/depth或aspect_ratio_bounds目前会被
UNMODELED_FLEXIBLE_DIMENSION_RULE拒绝。这道Fail-closed本轮原样保留。
仅改配置并不会让模型支持这些字段；未来必须同时批准Authority和消费者实现。
源码位置/Hash见[code-audit.json](code-audit.json)，原件Hash见[baseline-integrity.json](baseline-integrity.json)。

## 一、标准适用性与证据等级

截至2026-10-19核查，食品卫生采用已于2026-09-02实施的
[GB14881-2025官方公开原文](https://www.jiyang.gov.cn/resources/public/20260527/6a16b7c6122a6678fef32fe9.pdf)，
不是把2013版继续当现行版。其4.1.3、5.1.5、5.2.1.3.2要求空间与人员、工艺、
卫生和设备维护相适应；没有给本任务可直接套用的统一房间短边或比例。
空间须支持设备、操作、维护的要求与“每个房间必须宽X米”不是一回事。

GB50072-2021与JGJ/T67-2019的现行目录、发布日期和实施日期已核查。
冷库标准不自动成为所有辅助房间的净宽表；办公标准公开试读未提供本次足以核实的
数值条文，故不采用网络转述的人均面积，不按60m²反算实际人数。
GB55031公告说明其适用时的强制层级，不代表工业生产房间全部适用，也未据公告推导门宽。
最终消防、职业卫生、无障碍及辅助建筑适用范围仍须项目专业设计复核。

|ID|来源|证据等级|核实边界|
|---|---|---|---|
|S01|[食品安全国家标准 食品生产通用卫生规范](https://www.jiyang.gov.cn/resources/public/20260527/6a16b7c6122a6678fef32fe9.pdf)|MANDATORY_REQUIREMENT|SOURCE_VERIFIED: effective 2026-09-02; replaces GB 14881-2013; assessed 2026-10-19|
|S02|[GB50072-2021 冷库设计标准（国标电子书库目录与试读）](https://ebook.chinabuilding.com.cn/zbooklib/book/detail/show?SiteID=1&bookID=142390)|ENGINEERING_INFERENCE|SOURCE_VERIFIED_CURRENT_CATALOG; effective 2021-12-01; replaces GB 50072-2010|
|S03|[办公建筑设计标准：现行目录与试读](https://ebook.chinabuilding.com.cn/zbooklib/book/detail/show?SiteID=1&bookID=123888)|RECOMMENDED_PRACTICE|SOURCE_VERIFIED_CURRENT_CATALOG; effective 2020-03-01; replaces JGJ67-2006|
|S04|[住建部发布《民用建筑通用规范》公告](https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2024/art_17339_767703.html)|MANDATORY_REQUIREMENT|PUBLICATION_VERIFIED; effective 2023-03-01; current project scope/code hierarchy requires professional review|
|S05|[MITTZON 米特丛书桌 s19529082 产品尺寸](https://www.ikea.cn/cn/zh/p/mittzon-mi-te-cong-shu-zhuo-bai-se-hei-se-s19529082/)|MANUFACTURER_REQUIREMENT|LIVE_MANUFACTURER_SPECIFICATION_NOT_A_STANDARD|
|S06|[Bisley Most Wanted 2024：MONOBLOC ML03S1](https://store.bisley.de/wp-content/uploads/bisley-_most_wanted.pdf)|MANUFACTURER_REQUIREMENT|CATALOGUE_MODEL_SPECIFIC_NOT_A_STANDARD; project procurement unconfirmed|
|S07|[ProDOSE Pineapple Wax Dosing Machine](https://cms.jbtmarel.com/en/products/prodose-pineapple-wax-dosing-machine/)|MANUFACTURER_REQUIREMENT|MANUFACTURER_MODEL_SPECIFIC_NOT_A_STANDARD|
|S08|[Talleres Arcot Wax Applicator](https://www.talleresarcot.com/en/wax-applicator/)|MANUFACTURER_REQUIREMENT|MANUFACTURER_CONFIGURATION_SPECIFIC_NOT_A_STANDARD|
|S09|[ROBOPAC ECOPLAT PLUS USE AND MAINTENANCE MANUAL](https://robopacusa.com/wp-content/uploads/2020/05/EcoPlat-Plus-User-Manual.pdf)|MANUFACTURER_REQUIREMENT|VERIFIED_LEGACY_MANUAL_SPECIFIC_TO_MODEL_EDITION; not project-bound or a current universal rule|
|S10|[Workplace facilities: welfare](https://www.hse.gov.uk/simple-health-safety/workplace-facilities/welfare.htm)|RECOMMENDED_PRACTICE|LIVE_UK_GUIDANCE; NOT_CHINESE_LAW|
|S11|[封存P1柔性尺寸Authority与8套真实几何](https://github.com/xuezhiorange-png/cold-storage-planning-agent/blob/78f42b3956d3569e5a887fb578ce5e773275cc5b/docs/previews/v2.2.2/stage-b/layout-quality-baseline-01/inputs/server_authorities.json)|PROJECT_SPECIFIC_INPUT|CURRENT_PROJECT_AUTHORITY_SNAPSHOT_UNCHANGED|

来源矩阵[engineering-sources.json](engineering-sources.json)逐项给出日期、版本、
条文/页码、适用功能、限制和核查状态。11项来源包含9项内容/发布规则/厂商/项目事实，
另2项仅核实目录元数据；不是11项都已提供可执行数值条文。
5条MANDATORY_REQUIREMENT条目中4条是食品卫生定性要求，1条是适用时的通用规范层级要求；
不是5条新数值门槛。2项推荐性参考、5项厂商规格与项目Authority相互独立。
U01办公数值条文/适用性、U02冷库完整范围/所谓通用房间宽度、U03项目选型及Envelope
仍UNVERIFIED。国外HSE只作定性参照，不当作中国强制规定。
仅提交链接、必要尺寸与自行转述；不提交标准、手册或厂商目录全文。

## 二、办公室：人数和功能布置先于比例

需确认常驻/峰值人数、工位、文件柜/设备、会议或值班功能、门窗、柱及家具使用方式。
几何面积、建筑面积、轴线尺寸、完成面净尺寸与家具布置后的通道必须分别记录。
本项目未明确其相互转换，不默认墙厚或把长边作为可连续摆放家具的净长。

条件模块（局部净坐标；桌后操作区与独立通道不共享）：

```text
W_clear >= rows*(desk_depth + user_zone) + through_aisle + side_storage
L_clear >= ceil(N_staff/rows)*desk_width + 2*end_space
```

只有全部参数有依据，才能评价该特定模块，不是所有办公布置的必要条件。
[IKEA示例桌](https://www.ikea.cn/cn/zh/p/mittzon-mi-te-cong-shu-zhuo-bai-se-hei-se-s19529082/)组装后1600×800mm，
不是本项目选型。1.656m短边布置一排800mm深桌，仅余856mm给所有其他占用；
两排相向桌仅余56mm，**这不是56mm可用通道**。椅退、通过、储物及门扇未获批准，
不能将上述余量称为功能PASS或正式违规。推荐比例范围仍为null。

## 三、更衣室：把储物容量、同时操作和卫生流程分开

每班人数、同时更衣人数和储物用户数是不同参数；柜体分格数不等于同时更衣容量。
需确认洁污衣物分存、鞋/换鞋/洗手等设施、门扇、凳和通道；不默认人数或男女比例。
单排、双排相向、柜体+独立通道可使用同一显式参数模块：

```text
units = ceil(storage_users / slots_per_unit)
L_clear >= ceil(units/rows)*locker_width + 2*end_space
W_clear >= rows*locker_depth + front_service_zone + bench + independent_aisle
```

front_service_zone须已含有依据的开门/人体/时序策略。不能自动用max合并同时占用的空间。
[Bisley ML03S1](https://store.bisley.de/wp-content/uploads/bisley-_most_wanted.pdf)表列322宽×500深×1700高mm，
与同页插图600mm宽的另一柜型区分。示例并非已批准的食品厂柜体。

在**两排500mm深柜沿相对长墙摆放**的明确假设下，柜体本身需1000mm，
已超过0.875/0.977m短边；即便忽略所有间隙，仍分别短125/23mm。
因此这两个几何不容纳该假设方案，但不能认定项目柜型已选或房间正式违规。
若只有单排500mm柜，余375/477mm尚要承担门扇和人体等空间，属于ENGINEERING_RISK，
没有依据直接把它称为合法通道。数学下界中的零间隙绝不是获许可的设计间距。

## 四、覆膜间：先确认工艺，再分别核验运行状态

“覆膜”可能是果品保鲜涂膜/打蜡、包装膜封装或托盘缠绕，设备不能互换。
需提供工艺类型、产品包装/产能、型号数量、上下料和前后Portal接口、缓冲、操作、
清洗检修、物料移动、净高及公用工程。

- [JBT ProDOSE](https://cms.jbtmarel.com/en/products/prodose-pineapple-wax-dosing-machine/)
  公布990W×633L×2018H mm；
  它是菠萝蜡液配比/供液设备，明确不是涂蜡应用机，不能拿其外廓替代完整覆膜线。
- [Arcot涂蜡机](https://www.talleresarcot.com/en/wax-applicator/)有与产能对应的1000/1500/2000mm宽度分类，
  不是已核实的整机安装包络；不得直接用2000>1950宣布该房间不合格。
- [Robopac手册](https://robopacusa.com/wp-content/uploads/2020/05/EcoPlat-Plus-User-Manual.pdf)Base标准型平面尺寸D2490、E1640mm；
  2.9图示另有带特定方向/基准的800mm周边和1500mm装卸最小标注，不能变成所有设备/所有侧的通道规则。
  它是托盘缠绕机，不是果品涂膜机。将E横跨1.950m短边时裸机尚余310mm，
  这不是正常操作、检修、装卸已经可用的证明。也不能从图像像素另猜安装坐标。

采用共同局部坐标下的真实区域集合：

```text
NORMAL = EQUIPMENT union OPERATION union MATERIAL_FLOW
MAINTENANCE = EQUIPMENT union MAINTENANCE union MATERIAL_FLOW(该工况确需的部分)
```

每个集合及停机/共享策略须有来源；缺失不是空集合。分别验证两种工况，不无条件同时相加，
也不默认检修时可以占用人员通道。离线函数只计算给定矩形集的必要包围范围，
不冒充真实碰撞、可达或功能可行性验证。
41.026×1.950m可容纳某类线性组织的可能性不能由大比例否定，亦不能由80m²面积肯定。

## 五、24个现有房间的条件影响

比例仅三位小数展示，计算使用整数mm及精确分数。原Authority/原Hash/原图不改。
所有行当前面积下界满足，功能状态均待输入；原8几何/6实质组织/4家族计数不变，
05/06重复组织不因本研究重新计数。结构家族Hash缩写仅为显示，JSON保留全值。

|候选|房间|面积m²|短边m|长边m|比例|主要Family Hash（缩写）|
|---|---|---|---|---|---|---|
|历史01|changing_room|50.5296|5.808|8.7|1.498|29c657d4bd13|
|历史01|coating_room|80.0052|6.612|12.1|1.830|29c657d4bd13|
|历史01|office|60.00008|2.456|24.43|9.947|29c657d4bd13|
|历史02|changing_room|40.002274|3.323|12.038|3.623|29c657d4bd13|
|历史02|coating_room|80.024861|6.143|13.027|2.121|29c657d4bd13|
|历史02|office|60.00008|2.456|24.43|9.947|29c657d4bd13|
|最新01|changing_room|85.57575|3.25|26.331|8.102|f7228d5e9773|
|最新01|coating_room|80.0007|1.95|41.026|21.039|f7228d5e9773|
|最新01|office|60.000512|2.816|21.307|7.566|f7228d5e9773|
|最新02|changing_room|40.000334|0.977|40.942|41.906|ac72b3817bb1|
|最新02|coating_room|80.006964|8.823|9.068|1.028|ac72b3817bb1|
|最新02|office|60.000764|2.908|20.633|7.095|ac72b3817bb1|
|最新03|changing_room|40.039125|0.875|45.759|52.296|a0d221eb7944|
|最新03|coating_room|80.0037|8.925|8.964|1.004|a0d221eb7944|
|最新03|office|60.000192|1.656|36.232|21.879|a0d221eb7944|
|最新04|changing_room|40.007682|4.082|9.801|2.401|f7228d5e9773|
|最新04|coating_room|80.004365|7.303|10.955|1.500|f7228d5e9773|
|最新04|office|60.000192|1.656|36.232|21.879|f7228d5e9773|
|最新05|changing_room|40.021566|4.083|9.802|2.401|f7228d5e9773|
|最新05|coating_room|80.001216|7.236|11.056|1.528|f7228d5e9773|
|最新05|office|60.000192|1.656|36.232|21.879|f7228d5e9773|
|最新06|changing_room|40.035452|4.084|9.803|2.400|f7228d5e9773|
|最新06|coating_room|80.006316|6.708|11.927|1.778|f7228d5e9773|
|最新06|office|60.000192|1.656|36.232|21.879|f7228d5e9773|

[existing-layout-impact.json](existing-layout-impact.json)逐行包含原始候选身份、
24份面积/短长边/比例、当前Authority、缺项、风险和条件筛查；[CSV](existing-layout-impact.csv)便于比较。
全部24行标ENGINEERING_RISK；未宣称24行都实际不可用。
针对未选的双排500mm柜体假设，有2个更衣室出现柜体本身就无法放入的必要条件失败。
这只是HYPOTHETICAL_OFFLINE_SCREENING，不是新增正式工程验收或约束。

## 六、校准提案与下一步

[functional-room-requirements.json](functional-room-requirements.json)保留当前面积，
将功能最短边、最小进深与推荐比例置null，列出逐功能用途参数。
[dimension-calibration-proposal.json](dimension-calibration-proposal.json)分别覆盖A面积、B短边、C进深、
D比例、E布置、F有依据例外和G缺失状态；不从8套问题样本反推经验上限。
本轮没有可比的同功能/净空间参考/设备与人数已批准的完整正例，不能冻结通用数值范围。

下一步需要Owner先确认[决策矩阵](owner-decision-matrix.md)，
再单独批准[P1/CP-SAT消费合同与实现](p1-cpsat-consumption-design.md)。
未来新Hard会有意缩小旧几何可行域，必须版本化、披露并独立回归，不能声称可行域未改变。
本轮则不修改现有消费者，不绕过UNMODELED_FLEXIBLE_DIMENSION_RULE。

## 七、复现与治理

使用已有Python3.12标准库，无需安装或升级依赖。在仓库根目录：

```sh
python3 docs/previews/v2.2.2/functional-room-dimension-calibration-01/calibrate.py
python3 docs/previews/v2.2.2/functional-room-dimension-calibration-01/render_review.py
python3 docs/previews/v2.2.2/functional-room-dimension-calibration-01/test_calibrate.py
```

准确测试及质量检查见[validation.json](validation.json)；未运行完整Backend或新的整厂验收。
数据与输出SHA见[source_manifest.json](source_manifest.json)。标准/目录/手册完整文件仅只读研究，
不提交，也不放入交付归档；来源URL和必要事实保留。
D01职责和262 UNKNOWN、D03历史分组/未校准目标、D04轮次及原预算均不变。
STAGE_B_COMPLETE=false；P2D_FULL_PASS_COUNT=0；VERSION_COMPLETE=false。
不Ready、Merge、Release、Deploy，不自动实施下一阶段。
