# R7 首次工程可行搜索恢复

TASK_ID：`V2_2_2_STAGE_B_R7_FIRST_FEASIBLE_SEARCH_RECOVERY_R1`。
基线：`83e044686a8cbe180807c1478869207d908f7755`，独立分支；PR312、历史结果和已消费槽不变。
本轮只运行合成 Native、构造完整模型、有限回归和快速 CI，不运行封存20t Native。

## 原始失败证据与判断边界

R6 有24次 Native 调用：21次预热、3次完整模型。第一阶段有效基线0，工程校核0，
第二阶段0。累计 Native 49.806357s、Work 221157，消耗内部49.8s Native搜索目标，
没有碰到600000 Work上限。另三个 Handoff 在完整基础模型取得 INFEASIBLE 证明后短路；
既有逻辑没有把 UNKNOWN 当作 INFEASIBLE，也没有证明整个项目不可行。

| 调用 | Handoff | 完整模型Wall s | Deterministic s | Branches | Conflicts | 状态 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 5 | CENTRAL_PROCESS_CORE:X:NEGATIVE:r0 | 5.703429 | 1.601956199 | 5253623 | 995 | UNKNOWN |
| 19 | LINEAR_BANDED:Y:POSITIVE:r1 | 15.142105 | 3.611248396 | 16970827 | 1462 | UNKNOWN |
| 24 | PROCESS_SPINE_WITH_PERIPHERAL_BANKS:Y:POSITIVE:r1 | 16.488860 | 3.621279046 | 18699466 | 1495 | UNKNOWN |

[全部24次调用、份额、阶段、终止依据及最终策略明细](../previews/v2.2.2/stage-b-r7-first-feasible-search-r1/r6-native-calls.json)
包含实际 Wall/Monotonic/Deterministic Time、Branches、Conflicts、完整模型标志及名义份额上界。
名义上界仍受调用时 Elapsed 和资源保护限制，不冒充未保存的精确 max_time 参数。

R6 原始响应未记录详细 Presolve 轨迹或逐次完整参数，故其实际 Presolve 时间、消除变量数
为 NOT_RECORDED。Worker1、Seed3、默认 Presolve、PARTIAL_FIXED_SEARCH 是固定源码配置证据，
与实际保存的搜索轨迹分开标明，不能反推不存在的历史日志。

已证实的配置差异：R5 最终模型仅有原 corridor-MIN 组；R6 在此前加入12组、166个不同布尔
引用，共13组。顺序为入口面、三个工艺/人员关系的通道与直连面、Packaging接口、三个原MUST组、
Portal偏移，最后原corridor组。三个实际最终模型的构造回读索引与封存事件一致，JSON保存每组
变量名称、域、顺序及索引范围。

Reference只改变Python事实记录，不改变CP-SAT变量、约束或面积目标。六个Handoff逐模型比对；
R5/R6预热仍是相同四阶段和1/8份额规则。双方均保存见证fingerprint且相同的预热有14项，
其余项不能比较。没有封存最终 Hint 的全部变量/值，因此实际最终 Hint 完全相同尚未证明。

**真实R6失败的唯一因果根因尚未证明。** 已证实的是有界完整搜索未返回赋值；新增前缘顺序
是有源码差异和合成证据支持的风险因素，不能仅凭三次UNKNOWN宣称它就是唯一根因。

## A/B/C隔离与可复现的合成恢复

- A：原R5普通模型及corridor顺序。
- B：Reference模型，不启用前缘前缀。
- C：Reference模型，完整R6前缘前缀。
- R7：实际新增策略的第一阶段，延后前缘。

三次轮换A/B/C运行顺序。各组输入、硬约束、目标、2秒预算相同，OR-Tools 9.15.6755、
Worker1、Seed3、Presolve=true、PARTIAL_FIXED_SEARCH、stop_after_first_solution=true、512MiB。
诊断日志开关在各组一致；原始Presolve日志留在本地，公开证据保存摘要Hash及真实响应。

原八房间场景是负对照：生产Presolve使A/B/C均零分支，不能证明前缀退化。
原关闭Presolve/FIXED_SEARCH对照继续保留：12m/3转与9m/2转只说明测试专用配置的选择语义。

非平凡场景在相同八房间中加入六个独立合成Office服务块，使用0.5m网格、NoOverlap2D及
两种朝向的1m服务净空带。它是明确的测试假设，不是已知设备/装修数据或生产Authority。
该场景使入口面选择与实际内部矩形排布耦合，各组使用完全相同的约束。

| 组 | 重复 | 首见证中位s | Branches | Conflicts | Deterministic s | 目标代理 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 3 | 0.009115 | 1116 | 98 | 0.002140479 | 1125 |
| B | 3 | 0.009198 | 1116 | 98 | 0.002140479 | 1125 |
| C | 3 | 0.010748 | 1347 | 207 | 0.002924117 | 1125 |
| R7 | 3 | 0.009108 | 1116 | 98 | 0.002140479 | 1125 |

各次实际返回均为OPTIMAL，该场景首次见证已达到代理下界；没有重标FEASIBLE。
墙钟保留原实测值，测试不使用脆弱的毫秒耗时断言。操作数和确定性时间可重复，R7恢复B的
搜索行为。此场景全部实际路线12m/3转、建筑单连通零孔洞，独立原路线谓词及几何校核通过；
恢复的是首次搜索操作数，不声称该场景布局几何变好，更不声称整厂改善。

单组消融发现入口面组0或Portal偏移组11单独启用均能复现额外分支/冲突；固定通道组1、
Packaging组7单独启用与B一致。仅删除入口组不能消除偏移组的重表达影响，不能强行归因于
单个组。完整消融、实际几何、参数和响应见[实测数据](../previews/v2.2.2/stage-b-r7-first-feasible-search-r1/ablation.json)。

## 最小实现及两阶段机制

新增 `stage_b_first_feasible_recovery.py`，原R5/R6算法和共享求解器不修改。

R7 Policy：`sha256:e669e1a82f2e59cfa8cda122cda45596ba812e816aec673d4a67b7717e63e458`。
R5与R6的`_run`和FairNative份额/调度方法经AST比较一致；差异与具体Handoff调用记录保存在JSON，
未通过调整Worker、Seed、Presolve或共享资源份额制造恢复效果。

1. `StageBFirstFeasibleRecoveryFairSolver._continuation_options`仅去掉第一阶段
   `final_model_search`回调，原corridor顺序和R5面积目标保留，使用R6 Reference准备。
2. `_FirstFeasibleRecoveryNative.begin_improvement`只在原工程验收反馈转场后调用；
   父方法检查原份额、复用代理与当前有效物理Hint，再安装原前缘并重排软策略元数据。
   同一Handoff、同一个CpModel、同一个账本；转场没有Solve、没有clone、没有重建模型。
   重复转场拒绝，没有增加原有Native调用语义。
3. 原始基线先被独立验收、记录并交给Pool，之后才能转场。未知或孔洞拒绝不创建基线，
   UNKNOWN原样终止、不重试；孔洞仍走既有精确见证切除。
4. 新增真实策略复制/重排Work标签 `R7_DEFERRED_STRATEGY_REORDER`，总预算和整笔预检查
   不变。没有剩余份额时在前缘写入前拒绝，基线不丢失。
5. 原小集合物理Hint、独立搜索阈值、九项和十二项严格Pareto比较均直接继承。
   跨Solve的学习状态不保证保留，搜索代理进步不等于正式质量进步。

## 验证与执行边界

- 新增25项R7测试，在原独立Worker框架下25 PASS。
- 本地快速工作流同选择749 PASS，1项Linux实际RSS显式排除，未计PASS。
- 架构771 PASS /16项原有skip；Ruff、Format、Mypy及CI契约结果随PR验收记录。
- 729种物理赋值全部保留。六个封存20t Handoff仅构造模型，测试强制禁止任何Native Solve，
  原变量、约束、目标逐字一致。第二阶段两种原入口几何均仍可扩展。
- 原精确孔洞切除拒绝环形并保留开口几何。另对封存R5四套完整候选只读重跑原
  `validate_native_access_geometry`（11项非Truck Access）及原精确union检查，四套全通过；
  没有新增Native或改写历史候选。八房间合成路线检查不冒充完整11项工厂验收。

P1、Site、MUST、Access、Packaging、Truck、P2D、资源保护器、生产默认、Owner Scope及历史
Grant/Claim不改。R7显式新Policy，旧R5/R6授权不能激活它。本轮不开发Runner、不创建任务槽、
不签发Grant、不请求真实执行或正式完整CI。PR312保持原HEAD。

只有合成搜索恢复已获证据；真实整厂首次可行能力、整体质量均NOT_EVALUATED。
完成快速CI后停止，等待Owner审核。
