# 八套布局质量事实基线（非排名）

TASK=REVIEW_NUMERIC_CALIBRATION_AND_LAYOUT_QUALITY_BASELINE_01

## 结论与边界

8套物理几何、6套V2实质组织、4类主要家族保持不变；最新05/06不增加V2计数。
封存证据的12区、7 MUST、11项非Truck Access/共存和Footprint/Site验证不被本报告改写。
**工程几何有效不代表房间可用、工艺顺畅或P2D完整通过。** 全部Truck未获真实工程验收，P2D full-pass=0。
本轮仅重算离线事实，不新建候选、Grant或正式工程验收，也不执行求解、质量排序和Owner设计签认。

## 逐套主要问题：事实、风险与待校准项

- 历史01：Office 2.456×24.430m（9.947）；入口路线58.629m/3转向。人员绕行是实际记录，
  但缺同端点最短可行路线，不能断言全部距离可消除。
- 历史02：Office同上；入口11.214m/3转向，Changing比例3.623。入口变短并未解决Office尺度问题。
- 最新01：Coating 41.026×1.950m（21.039），Changing 26.331×3.250m且面积85.575750m²。
  面积充足不证明覆膜设备、检修和作业净空能布置；需设备Envelope和人员依据。
- 最新02：Changing 40.942×0.977m（41.906）；入口39.037m/1转向。
  共享长边上可有1.5m门，不意味着房间0.977m短边已经满足更衣柜/人员操作净空。
- 最新03：Changing 45.759×0.875m（52.296）；Office 1.656×36.232m（21.879）。
  路线16.502m虽较短，也不能抵消功能空间使用风险。
- 最新04：Changing 4.082×9.801m（2.401），Office仍1.656×36.232m；入口47.352m/3转向。
- 最新05/06：Office同04；入口47.419/47.947m；物理尺寸变化不新增实质组织。

以上尺寸为MEASURED_FACT；过度狭长可能影响设备和操作为ENGINEERING_RISK；
缺设备、人数、柜位、检修/通行/工艺净空为CALIBRATION_REQUIRED。
本轮未发现可据现有正式权威直接认定的FORMAL_CONTRACT_VIOLATION，
**不等于正式判定房间功能可用**，也不新增硬长宽比、最小深度或面积上限。

## 房间与实际人员路线对比

|候选|V2计数|Office 实际宽×深 m（比例）|Changing 实际宽×深 m（比例）|Coating 实际宽×深 m（比例）|入口→Changing m / 转向|
|---|---|---|---|---|---|
|历史01|计入|2.456×24.43（9.947）|5.808×8.7（1.498）|6.612×12.1（1.830）|58.629 / 3|
|历史02|计入|2.456×24.43（9.947）|12.038×3.323（3.623）|6.143×13.027（2.121）|11.214 / 3|
|最新01|计入|2.816×21.307（7.566）|26.331×3.25（8.102）|41.026×1.95（21.039）|34.679 / 2|
|最新02|计入|2.908×20.633（7.095）|40.942×0.977（41.906）|9.068×8.823（1.028）|39.037 / 1|
|最新03|计入|1.656×36.232（21.879）|45.759×0.875（52.296）|8.964×8.925（1.004）|16.502 / 1|
|最新04|计入|1.656×36.232（21.879）|4.082×9.801（2.401）|7.303×10.955（1.500）|47.352 / 3|
|最新05|不重复计入|1.656×36.232（21.879）|4.083×9.802（2.401）|7.236×11.056（1.528）|47.419 / 3|
|最新06|不重复计入|1.656×36.232（21.879）|4.084×9.803（2.400）|6.708×11.927（1.778）|47.947 / 3|

完整96行见[逐房间表](rooms.md)、[CSV](rooms.csv)；接触边长度、功能组、顺位、实际门见[facts.json](facts.json)。
宽/深是应用旋转后的物理坐标轴尺寸，原名义尺寸同时保留，避免把90°旋转误认为宽深变化。

## 主工艺、支流与人员组织

保留Receiving→原果暂存→一级预冷→分选包装→二级预冷→覆膜→成品→Shipping。
Receiving没有项目映射；不把truck_entrance当Receiving。其余6条主流程记录均为DIRECT_SHARED_EDGE：
两个相同Portal点的0m中心线不描述进门后到出门前的室内搬运路径。
因此PROCESS_FLOW_ORDER_PASS、MAIN_FLOW_BACKTRACK_COUNT、MAIN_FLOW_TURN_COUNT、
MAIN_PROCESS_ROUTE_LENGTH_M、PROCESS_ROUTE_EFFICIENCY_RATIO全部UNAVAILABLE。
房间相对方向作为独立事实保存，绝不改名为正式折返次数或转弯数。

两条人员Requirement、包材→Sorting、Sorting→次果/冻果的真实接口表见[路线证据](routes.md)。
所有Changing→Sorting及包材/次果/冻果接口都是共享门，不提供室内连续流线。
已记录Corridor仅为入口人员通道；与物流Envelope没有正面积交叉不等于工厂整体人货分离。
Office的空间接触/位置不自动创建人员Portal。完整物流、Receiving及Office通行资料缺失时，
PERSONNEL_LOGISTICS_SEPARATION、SIDE_BRANCH_CROSSES_MAIN_FLOW保持UNAVAILABLE。
当前P1A Secondary归PROCESSING_CORE_GROUP；历史P0 FINISHED_SIDE_GROUP原文不改。
P1A分组/结构意图不是FUNCTIONAL_GROUPING_PASS，后者仍待完整可验证功能与路线事实。

## 建筑与轴网（精确毫米，不是视觉评分）

|候选|轴网率|建筑面积 m²|周长 m|占包围矩形比例|反角|转折|凹口|连通分量|
|---|---|---|---|---|---|---|---|---|
|历史01|0.3|2358.60838|437.174|0.568298|18|40|4|1|
|历史02|0.3|2253.270715|484.128|0.542918|23|50|4|1|
|最新01|0.3|2345.750462|493.972|0.567708|22|48|5|1|
|最新02|0.4|2308.897562|482.522|0.587851|20|44|4|1|
|最新03|0.3|2263.862517|448.986|0.545638|19|42|4|1|
|最新04|0.3|2325.531739|495.43|0.560502|22|48|4|1|
|最新05|0.3|2325.676474|495.562|0.560537|22|48|4|1|
|最新06|0.3|2326.75146|483.2|0.560796|21|46|4|1|

轴网按P0 §6及P0A既有正共享墙线算法，五个主要房间共20个边界incidences。
0.30或0.40是测量事实，低于0.90产品目标；0.90正式numeric gate未校准，不能据此宣布正式违规或PASS。
进深按P0C depth-pair@1.0.0：五个主要房间没有重复的同类房间bank，不能比较不同功能角色的任意房间。
允许的特殊Secondary/Finished对在当前P1A中分属不同组/带，不能以历史P0分组覆盖。
因此逐对排除十个组合后，eligible_pair_count=0，DEPTH_ALIGNMENT为NOT_APPLICABLE，
不是0%或100%；JSON保留十对排除依据。未来若有合法同bank对，还须项目局部朝向和近远边对应权威。
反角由有向叉积精确计算；转折包含凸角，两者不同。凹口按已存在P0C classifier V1，
使用精确顶点分解、包围矩形内外部口袋连通分量计数；**没有引入新凹口宽度阈值**。
突出翼部是否无意义需要Owner目的证据，ISOLATED_APPENDAGE_COUNT保持UNAVAILABLE。
表内占用率只作六位小数展示，JSON保留精确分数；几何判定没有取整。
面积/周长/占用率在不同候选间可比，但不按这些值排名。75.46×55m场地及三块NO_BUILD_ZONE
均保存在原typed Site；这些真实禁建区域能限制主体形状，不能以单纯矩形/低占用率判劣。
本轮没有证明每一个凹口/翼部均由禁建区所必需，也没有证明其全都可消除。
Shipping Loading Face按原应用段和方向保存，未添加货车尺寸、扫掠或进场证明。

## 校准条件与最值得解决的问题

NUMERIC_CALIBRATION_READY=false。五份Golden图的Owner overlay PASS只支持连续生产带/中心、
成组冷间、从属支路及有目的翼部等定性组织；不提供房间级精确正例尺寸、完整Footprint、
工艺运输路线或可比深度对。不能把0.75–1.00的Golden组Envelope轴网与这里房间墙线的0.30–0.40
混作同粒度正反例并冻结门槛。P0C证据与ADR-047的NOT_READY仍有效。

下一步优先取证并解决**更衣室/办公室/覆膜房间的功能可用尺度**：收集人数/柜位、设备台数与尺寸、
作业/检修/物料移动Envelope、卫生分区与专业审核依据，再形成按功能区划分的可比正例和范围提案。
这是建议，不是本轮实施授权；不在此发明任何新的数值区间。人员路线缩短应同时保护房间可用性。
并行缺项：Receiving正式映射、每房间进出Portal间运输连接、配置的工艺前进方向/工艺带、
同端点最短可行路线证据、Office人员通行路线、交叉评审依据、翼部目的及合法Truck输入。
取得这些资料后才能完成工艺/分离/路线效率评价和数值校准。

## 来源、算法与可复现性

原始JSON对照各自封存Manifest与归档字节；[sources.json](sources.json)记录归档/原件/投影/SVG Hash。
inputs是原件所选完整子树的证据投影，不是新候选；不修改原始JSON/SVG或历史Hash。
每项Sidecar指标有VALUE/UNIT/STATUS/SOURCE/CALCULATION_METHOD/DEFINITION_VERSION/EVIDENCE_HASH/
UNAVAILABLE_REASON；非终止小数另存EXACT_RATIONAL，展示小数不参与几何等值比较。
状态计数按每个metric wrapper（含每对共享边）计，房间Bundle不按96×字段重复累计。
仅MEASURED、DERIVED、NOT_APPLICABLE、UNAVAILABLE，缺项为null而非0。

全部脚本只用Python标准库，不导入生产求解、Access搜索、Selector、Grant或模型SDK。
在仓库根目录执行（使用已有Python3.12环境，无新依赖）：

```sh
python3 docs/previews/v2.2.2/stage-b/layout-quality-baseline-01/analyze.py
python3 docs/previews/v2.2.2/stage-b/layout-quality-baseline-01/render_report.py
python3 docs/previews/v2.2.2/stage-b/layout-quality-baseline-01/test_analyze.py
```

仅需要重建来源投影时，prepare_sources.py接收持久化artifacts根目录；它只读封存tar/JSON，
校验指定归档SHA后提取字段，不运行任何历史执行入口。通常重放分析无需原执行会话或私有Grant。
本轮专项测试与质量检查真实记录见[validation.json](validation.json)；未重跑完整Backend，
没有将历史PDF例外改为PASS。最终exact-head CI另行核验，运行中报告PENDING。

D01三层责任、D03历史口径、D04恢复停止边界及262 UNKNOWN保持；未重置恢复轮次。
STAGE_B_COMPLETE=false；P3_COMPLETE=false；P2D_FULL_PASS_COUNT=0；VERSION_COMPLETE=false。
不Ready、Merge、Deploy；不自动进入任何下一任务。

## 原始GitHub审图链接

不修改原图、不按本报告排名：

- [历史01](https://github.com/xuezhiorange-png/cold-storage-planning-agent/blob/2219ab6ce8ae4f1a493d083810c29b0364b5efc6/docs/previews/v2.2.2/stage-b/multi-solution-validation-01/candidate-01/layout.svg)；几何 `sha256:48c48e4514a812132c2bdec1f2863f1c62162ccb5c95fe366ab7aa84ee439525`；SVG SHA256 `e28ec6efe882764bf15a5315ca66683ae08e9dde7fab75f32c5f73846bd10de7`。
- [历史02](https://github.com/xuezhiorange-png/cold-storage-planning-agent/blob/2219ab6ce8ae4f1a493d083810c29b0364b5efc6/docs/previews/v2.2.2/stage-b/multi-solution-validation-01/candidate-02/layout.svg)；几何 `sha256:01dc0a46e213c7e92071ca1d88d7482d7cf829cd2411965ef3a323d1ca9095be`；SVG SHA256 `4346cbec87de7105369c42288116210bea6659e577ccdcb0eb4a32addfdd8c36`。
- [最新01](https://github.com/xuezhiorange-png/cold-storage-planning-agent/blob/2219ab6ce8ae4f1a493d083810c29b0364b5efc6/docs/previews/v2.2.2/stage-b/guided-fair-validation-02/candidate-01/layout.svg)；几何 `sha256:a8873398fbf9fa257dc6c4633b7e0137e4f16fc85f4b42aeaa5d9ba1d82736d6`；SVG SHA256 `9d1b31fe47284ab2445cd54e82cde658f2664749f1f4c1365f663d6a920f426f`。
- [最新02](https://github.com/xuezhiorange-png/cold-storage-planning-agent/blob/2219ab6ce8ae4f1a493d083810c29b0364b5efc6/docs/previews/v2.2.2/stage-b/guided-fair-validation-02/candidate-02/layout.svg)；几何 `sha256:b60a8b043353ec2aed3bd26f71791c1e5f11e8041ae98ceb0fbdfdd75e2c60ae`；SVG SHA256 `72c9a516f041e4e649ace669c9844b49a74603806a57a1164a772709ab888500`。
- [最新03](https://github.com/xuezhiorange-png/cold-storage-planning-agent/blob/2219ab6ce8ae4f1a493d083810c29b0364b5efc6/docs/previews/v2.2.2/stage-b/guided-fair-validation-02/candidate-03/layout.svg)；几何 `sha256:77b1023e62b8877f07df81a6c90c8455af249848a2cc604c92685ac7872658fb`；SVG SHA256 `5cc9569308f483c5ccd4e3f55b82853a79fe85bbb43cc4bac6a1ab273245f01c`。
- [最新04](https://github.com/xuezhiorange-png/cold-storage-planning-agent/blob/2219ab6ce8ae4f1a493d083810c29b0364b5efc6/docs/previews/v2.2.2/stage-b/guided-fair-validation-02/candidate-04/layout.svg)；几何 `sha256:110c73358a13b504b3c8e3e3b03d46f3ee8a2652648b326c961641e023857359`；SVG SHA256 `f72fe66fc21f8a0d632825069f192e9dd4c56e5e7bbe8993578f7f93326dfa27`。
- [最新05](https://github.com/xuezhiorange-png/cold-storage-planning-agent/blob/2219ab6ce8ae4f1a493d083810c29b0364b5efc6/docs/previews/v2.2.2/stage-b/guided-fair-validation-02/candidate-05/layout.svg)；几何 `sha256:f9cbb4ccfae57eb43fdad2e0aa6731c03585803ec3b164754182bb3208dee216`；SVG SHA256 `082dc3fc5ab576331b6e33f5db7cc80ed174ecf9a1d019ee48a1e8c05a7702f7`。
- [最新06](https://github.com/xuezhiorange-png/cold-storage-planning-agent/blob/2219ab6ce8ae4f1a493d083810c29b0364b5efc6/docs/previews/v2.2.2/stage-b/guided-fair-validation-02/candidate-06/layout.svg)；几何 `sha256:b7353dcda7daf1b58743d2a8b6d3a53a683b9fc81cec02fba250a2f9dca579e4`；SVG SHA256 `d1ae2e0bc4ec6babcab212689b29d2188629730664f8cb80724eb6ba5474842e`。
