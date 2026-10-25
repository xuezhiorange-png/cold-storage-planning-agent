# R9 Changing 位置、门面和人员廊协同搜索

TASK_ID=V2_2_2_STAGE_B_R9_CHANGING_FRONTAGE_CORRIDOR_JOINT_OPTIMIZATION_R1

基线为 PR313 的 `67f92f36dfc573ead40b8d7bf7172cd67dd1646d`。独立分支、独立 Draft PR；不修改 PR313。本轮是算法开发与离线验证，没有真实 MAIN、Grant、Claim 或正式完整 CI。合成结果不是封存20t或新哨工程改善。

## 真实依据与选择

R8 对10套有效几何/4类V2的原件只读分析给出：

- P03→P06 的 Changing.xmin 同为14.7m，xmax从41.031退至39.719m。现有东门随房间缩短向西退，实际人员路线满足 `L=76.085−xmax`，由35.054增至36.366m。只改尺寸不移动位置会抵消面积/比例收益。
- P07 为39.683×1.008m、40.000464m²。1.008m短边装不下原1.5m门；实际选Ymax长边门。原人员通道2m、门前外伸1m使路径多0.766m回折（19.696−18.930）。这证明既有路径回折，不证明可以直接删去导引段。
- P07→P10 的比例39.368056→19.121、外路线19.696→19.610m/3→2转，同时面积升到76.484m²、Coating变狭长、轮廓变复杂；V2也变化，不能宣布正式Pareto改善。
- 东侧禁建区、二次果缓冲、原Sorting/Changing关系和Packaging接缝仍限制调整。未证明存在40m²附近、比例合理、短动线且其他指标均不恶化的整厂新布局。

R8来源为本机封存目录 `artifacts/stage-b-r8-layout-organization-quality-analysis-r1/` 中的 geometry-evidence.json、人员路线与组织建议报告。368份原证据/登记簿文件SHA256逐一回读保持一致；私有Grant/Claim不提交本PR。

## 最小实现

新增 `stage_b_changing_frontage_corridor.py`，显式端口 `StageBChangingFrontageCorridorFairSolver`，继承R7；没有改 bootstrap、Runner、Selector或生产默认。

第一阶段：复用R7的同一Reference模型、目标、原廊道顺序、首次可行机制、Hint与验证流程。没有第一阶段的R9钩子。六个封存Handoff只构建模型（测试禁止CpSolver.solve），R7/R9第一阶段proto逐字一致。

第二阶段：原执行流先独立验收并保存基线，再通过R7的 `begin_improvement` 完成同模型/份额核对、当前有效物理Hint、延后R6前缘。R9随后前置以下软顺序：

1. 从当前Site入口所在边确定朝入口的合法Changing门面优先次序。
2. 先选择Changing朝入口的物理边坐标（东为X，西为x，北为Y，南为y），偏向靠近该边入口。
3. 对当前w/d与横向位置作区间二分，再选择原六点人员廊模板的法向/横向坐标。
4. 保留后面的R7/R6门面、合法Portal偏移、工艺接缝与原廊道策略。

使用 `SELECT_LOWER_HALF` 区间二分；没有枚举几十万mm值的中位值选择。正常Presolve与PARTIAL_FIXED_SEARCH保持继承原配置。此顺序是可回溯的软偏好：不固定历史坐标，不创建变量、硬约束或目标，不声称必能缩短路线/改善房间。原面积紧凑度目标继续负责目标优化；原精确拓扑/Site/独立Access负责最终接收。

门面适配、1.5m净宽、2m廊宽、原可选偏移、cw/2法线、碰撞与MUST均仍由原Authority/AccessModel控制。R9读取并比对Authority与模型已有pw/cw，错误引用或缺失人员要求拒绝；不能借策略创建新门。

## 搜索反馈、质量与资源

R6小集合物理Hint只来自本次工程有效候选。有效搜索阈值与正式十二指标Pareto继续独立；九指标与十二指标比较函数都未改。不同V2严格NOT_COMPARABLE_STRUCTURE；Tradeoff不能提升成Pareto。第一有效基线始终保留。

原FEASIBLE/OPTIMAL/UNKNOWN处理、首次严格代理改善回调、孔洞精确切除和终止规则均继承，没有多一次Solve、模型重建、恢复学习状态的假设或自动重试。代理值相同的路线改善不触发“严格代理改善”回调；R9本轮仅改变搜索顺序，不保证此类改善会更早反馈。

新增Work逐项记真实route/Authority/物理引用读取、策略深拷贝与元数据写入；整个写入批次先charge成功再清空旧策略。份额仍由原累计账本控制。合成同模型的准备/策略Work为1565→1703（新增138），不是减少计账；该数不含独立离线Access测量，也不是完整MAIN资源总数。

## 离线可复核证据

[合成实际几何对照](../previews/v2.2.2/stage-b-r9-changing-frontage-corridor-r1/synthetic-layout-comparison.svg) 与 [原始结果](../previews/v2.2.2/stage-b-r9-changing-frontage-corridor-r1/synthetic-comparison.json)。

八功能块的非平凡合成场景，两组使用相同的显式position-MIN合成回退（不是生产新增策略），完全相同硬模型/面积目标、原1.5mPortal候选和2m廊包络。R7基线顺序Changing为x4..8m，R9为x6..10m，均y4..6m、8m²/比例2。实际人员路线9→7m、转向均2。原独立 `route_access_requirement` 接收两条实际路径，长度与求解几何一致；精确矩形并集均1连通/0孔洞，原MUST接触保持。生产Presolve开启、单Worker、种子3、PARTIAL_FIXED_SEARCH下结果可复核；另外保留关闭Presolve的独立对照，不混用证据。该位置对照是无先前基线Hint的软顺序消融；真实二阶段保留当前有效Hint，可能先返回重复基线，再由原枚举语义继续探索，不能把该消融当作真实二阶段效率预测。接受基线后的同模型/Hint/资源/UNKNOWN契约另行测试；固定代理的有效Hint负对照确实再次返回同一物理位置，明确保留此限制。

合成域的四个位置×门面组合逐一保持可行。六个封存Handoff在R9软顺序前后，去掉软策略的完整proto一致；没有封存输入Native调用。P07净宽不适配与0.766m回折、P03/P06门后退机制均由原坐标/函数复算；未生成替代历史候选。

不能由这一合成例断言整厂房间面积/比例或轮廓已改善。合成例的Changing尺寸未改变，证明的是协同位置选择与实际通行收益；真实面积与形状效果为NOT_EVALUATED。

## 后期234796 Work窗口审计：保留全部原校核

[只读覆盖原语回读](../previews/v2.2.2/stage-b-r9-changing-frontage-corridor-r1/coverage-reuse-audit.json) 对10套封存几何重新执行原包含谓词（没有Native求解），只测12个房间的覆盖。每套同一不可变footprint的 `_polygon_edges` 被重复调用113–117次。源码还在各次Site校核重复规范化同一Site边界/障碍，足迹生成后再规范化足迹。这确定了可研究复用的**不可变边表/规范化输入**，并不证明任何包含/碰撞查询可省略。

未实现缓存：仍缺完整调用生命周期、Authority/坐标Key、异常顺序及原Host计量等价证明；10套footprint各异，也不能跨候选复用PASS。原始234796是历史窗口Work，离线调用次数/计时不冒充该窗口的逐函数成本。Site、Footprint、覆盖及Work观察器完全未修改。

## 策略身份与后续边界

R7策略仍为 `sha256:e669e1a82f2e59cfa8cda122cda45596ba812e816aec673d4a67b7717e63e458`。
R9为 `sha256:73866388edf08ab4f2805cc99d145ad930dc2bdd86752e0badac7cffdfda559e`。

旧R5/R6/R7策略授权不能选择R9。没有新增执行接线、Owner Scope、授权架构、实际Grant/Claim或任务槽。本轮提交后仅自动快速CI；未来如需真实R9实验，须由Owner另行决定现有机制下的独立实验准备与精确HEAD正式CI。当前不请求执行授权，不自动进入准备。

## 本地验证

- R9针对性40 PASS（包括六Handoff只构模、四物理/门面赋值、原Access、基线/UNKNOWN/资源拒绝、跨V2和旧策略拒绝）。最终版本独立复跑通过。
- R9/R7/R6/R5/平衡策略/资源/原Access Hint组合334 PASS；1项physical_rss_linux显式排除，状态NOT_RUN_ENVIRONMENT_SPECIFIC，不计PASS。
- 架构771 PASS /16原有skip。第一次调用的嵌套python3误选macOS系统解释器、缺pytest；正确PATH下该唯一失败Node独立通过，没有修改测试。
- CI契约64 PASS（含原50次独立Git清理重复），分组/共享Fixture契约7 PASS。
- Ruff、Format、Mypy452源文件、git diff --check通过。
- 快速CI增加R9测试文件一项，原工作流触发与门禁不改；正式完整CI未请求。
