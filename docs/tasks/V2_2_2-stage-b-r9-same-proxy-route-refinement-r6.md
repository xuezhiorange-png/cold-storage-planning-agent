# R9 同代理人员路线择优与枚举推进 R6

TASK_ID=V2_2_2_STAGE_B_R9_SAME_PROXY_ROUTE_REFINEMENT_R6

Base: `1f7f1ddf6f63715254efa065b708a4dca44ee21a` (PR315).
独立 Draft 分支；PR313/314/315、生产默认、旧 Runner/Owner Scope/授权机制不变。

## 实际工程结论

在独立完整合成场景中，原 R9 的 **32.749m** 人员路线被新策略继续优化到 **22.499m**。
房间几何逐项相同、R5 面积代理均1225、原130项物理 Hint 保留；新见证由实际 Native Solve 生成，
未注入已知24.999m参考路线、Portal或坐标。

两份见证分别通过原12区、7 MUST、11条非货车Access、Site、Footprint、单连通零孔洞、
独立原生Access及 `_eligible()` 工程验收。新门面/通道改变V2组织，原九/十二指标均返回
`NOT_COMPARABLE_STRUCTURE`。这是合成路线搜索机制成立的证据，不是正式Pareto或真实整厂改善。
Truck与P2D未验收。

| 指标 | 原R9有效见证 | 同房间局部择优 |
|---|---:|---:|
| 人员路线 | 32.749m | 22.499m |
| 人员转向 | 3 | 2 |
| 面积代理 | 1225 | 1225 |
| Changing | (40.001,20)m，4×10m | 完全相同 |
| 建筑周长 | 251.904m | 231.404m |
| 轮廓转折 | 42 | 40 |
| V2是否相同 | — | false |
| 原九/十二指标结论 | — | NOT_COMPARABLE_STRUCTURE |

[实际几何对照](../previews/v2.2.2/r9-same-proxy-route-refinement-r6/route-refinement-comparison.svg)
与[实测数据](../previews/v2.2.2/r9-same-proxy-route-refinement-r6/measurement.json)。

## 最小接线和独立身份

新增显式 `StageBSameProxyRouteRefinementFairSolver`，继承R9。
策略Hash：`sha256:4e0d3b0403f714dacf6a6612514d4101be824f3a3c3d4e8d6c36cfc14dbf7f5a`。
旧R9：`sha256:73866388edf08ab4f2805cc99d145ad930dc2bdd86752e0badac7cffdfda559e`。

`global_cp_sat_solver.iter_solutions()` 仅新增默认None的内部
`before_accepted_geometry_cut` 扩展点。它只在第二阶段且原应用流返回ENGINEERING_ACCEPTED后调用。
`yield from` 将每份路线候选重新交给原应用流验收；没有提前宣布Native见证有效。
旧策略不提供此钩子，原第一阶段、旧枚举、UNKNOWN与资源路径保持不变。
新类仍要求独立匹配的新 `balanced_quality_policy_hash`；旧策略身份不能自动选择它。
未新增Runner、Store、Grant、Claim或Owner指令文件。新代码也没有正式完整CI证明，不能运行真实MAIN。

## 临时范围与安全退出

新增 `stage_b_route_refinement.py`：

1. 保存本次已验收候选的房间、人员路线和面积代理，按物理房间几何标记最多处理一次。
2. 先计费再复制完成的CP模型到普通 `CpModel`；不复制Reference所有权/创建事实凭证。
3. **仅在副本**固定已验收房间几何、原面积代理、包装及其他非目标Access的当前物理见证。
   人员入口到Changing的原合法面、Portal候选、六个路径点及通道包络继续由原模型决定。
   这是一个明确局部子域，不声称一次遍历全局所有可能Access组织。
4. 保留原Hint。严格更短路线条件可能使部分提示不再满足局部范围，由CP-SAT修复软提示；不清空提示。
5. 最多2次局部Solve；每次不超过1.5s，且不超过当前剩余Handoff Native/Elapsed份额的四分之一。
   同一个Ledger、原Native调用/检查/Work保护；没有重新分配份额。
6. 局部目标只最小化**原导出中心线实际长度**。面积代理已固定，不修改原R5目标或全局模型。
7. 只对原工程接受的路线更新局部长度阈值。非法拓扑/工程拒绝不更新基线；只切除精确路线点见证。
   相同实际Portal/导出路径的重复见证有指纹检测和明确次数上限，辅助变量变化不能制造新候选。
8. 无更短路线、UNKNOWN、达到次数限制时丢弃局部副本；UNKNOWN不是全局INFEASIBLE。
   资源耗尽保留基线并按原机制停止。关闭生成器也执行finally清理。
9. 主模型从原Solver继续原精确房间几何切除；局部固定、目标、长度界、Hint均不回写。

新路线见证单独调用原九/十二指标记录事实，不把局部Solver安装到全局代理/Hint前沿。
原基线、正式比较规则与原Pool房间几何去重不变。

## 长度表达式为什么不是距离代理

`exported_length_expression()` 对原六点导出算法建立有限状态栈定义：
重复点跳过；三个共线点替换末点（包含反向共线）；否则追加。
最终长度是保留点之间的实际曼哈顿段长之和，而非入口到房间的直线距离。
所有定义只写临时副本；没有新增直通、最小宽度、最大面积或比例硬限制。

8种实际CP-SAT回归直接对照原 `AccessModel.export_routes()`，覆盖零长度、重复点、
共线反向折返、混合转向。每份完整工程路线又逐项核对CP长度、导出折线和原独立Access测量。
工程Authority的门宽、通道宽、碰撞、Site与拓扑检查未变。

## 完整合成对照与成本

复用原R3/R4/R5诊断的1t/day完整独立合成Plan/P1/Typed Site/Handoff，非封存20t。
仅测试工厂绑定同一个预先设计的场景族：Changing x在[40,42]m原整数mm区间，门面和路线自由。
R7第一阶段及原预热照常执行，无历史候选Hint或强制路线。

| 资源 | 原R9对照 | 新策略 |
|---|---:|---:|
| 每组Native上限 | 8s | 8s |
| 保守累计Native | 7.927499708s | 7.893648251s |
| Solver wall | 7.906116s | 7.878075s |
| Work | 176027 | 357531 |
| 实际Native调用 | 9 | 10 |
| 完整赋值检查 | 4 | 6 |
| 有效路线见证 | 4 | 6 |
| 不同房间几何 | 3 | 3 |

两组是各自8s上限的有限比较实验，不把两组耗时之和冒充一次8s实验。
新增两次局部Solve实际Solver wall合计0.417945s；模型复制计费129281 Work，新增总Work181504。
成本明显增加；不能凭总体时间接近宣称提速。目标32.749m→22.499m局部调用耗时0.221431s。

每次Solve前检查剩余额度并预留80ms，返回后核对原实际累计计时；超过则RESOURCE_FAIL。
本次两组均未超额。原R4约8.015s超额记录和历史证据保留，不追溯改判PASS。
新策略最终因本地6次检查额度正常停止；最后一次仅尝试入场，未实际调用Solve，不计入10次调用。

计时后发现新增审计事件只传composition字段，不满足原PoolLease的四字段来源合同；
已补齐原Plan/P1/Site/Handoff来源，并用原 `PoolLease.record_enumeration()` 做零Native契约验证。
此修正只涉及审计来源，不改变模型、Solve、候选或资源限制；未重复计时实验。
内存测试适配器保存全部原Ledger模型/Host计量；真实Lease的持久化写入和整厂运行成本未测。

## 机制证明与测试

- 两组前五次实际模型SHA相同，覆盖原预热与第一阶段有效基线26.750m。
- 新策略退出局部阶段后的所有全局模型SHA逐字匹配对照，包含目标、硬约束、原130项Hint和后续切除。
- 局部两份路线分别22.500m和22.499m；每份只新增路线见证，不增加房间几何。
- 新测试包含真实CP无更短路线、UNKNOWN无假改善、工程拒绝不更新、跨V2不升级Pareto、
  无资源不复制/不求解、关闭流释放副本、旧策略默认关闭、旧策略身份拒绝、原审计来源契约。
- 最终新策略29项单元测试通过；组合既有策略/原枚举/资源/Pool回归454 PASS、1项Linux物理RSS显式排除（组合运行含此前27项新测试，不能重复相加计数）。
  架构771 PASS/16原有skip；CI契约64 PASS（含50次Git清理回归）；Ruff/Format/Mypy453源文件通过。
- 快速CI包含新测试。完整CI不请求；不把快速CI成功当正式执行准入。

原始逐次Native日志、完整pbtxt、应用验收JSON、资源事件与读回脚本位于本地任务独立证据目录：
`artifacts/stage-b-r9-same-proxy-route-refinement-r6/`（外部归档）。

REAL_FACTORY_LAYOUT_IMPROVED=NOT_EVALUATED。
不运行MAIN，不创建真实Grant/Claim，不Ready/Merge/Deploy。交付独立Draft PR及快速CI后STOP。
