# R7 单次真实 MAIN 接线准备

TASK_ID：`V2_2_2_STAGE_B_R7_REAL_MAIN_PREPARATION_R1`。
准备基线：`aab1bb8dce8acf06379809a4ea15b5b4cea19b06`，PR #313。
本轮只开发接线、临时合成登记簿测试、正常提交及自动快速CI；不执行真实MAIN，
不创建真实Grant/Claim，不触发正式完整CI。

## 固定身份

| 项目 | 绑定 |
| --- | --- |
| 任务 | `V2_2_2_STAGE_B_R7_REAL_MAIN_R1` |
| 求解器 | `StageBFirstFeasibleRecoveryFairSolver` |
| PR / Head分支 | #313 / `codex/stage-b-r7-first-feasible-search-r1` |
| Base分支 | `codex/stage-b-r6-frontage-joint-search-r1` |
| Base SHA | `83e044686a8cbe180807c1478869207d908f7755` |
| R7策略 | `sha256:e669e1a82f2e59cfa8cda122cda45596ba812e816aec673d4a67b7717e63e458` |
| 原R6内核 | `sha256:5584fd5bb8a833905bc0f441bcdc1da8d9876f619d75b7d9fd948c843a2fd95d` |
| Reference准备 | `sha256:31d228d6995aa7d2d71fd5a5fe740868aecda89b2526ff88081efb41f4fb80df` |
| 前缘/接缝 | `sha256:ac9ce2d9b8f6d196705c12f91d28bb113b31ab31eebb4cf79aa319a030e38923` |
| Owner Scope | `docs/tasks/V2_2_2-stage-b-r7-owner-scope.txt`，UTF-8/LF |
| Scope SHA256 | `11aa91474ff6fbafcf2baac6042421abe126bce2d54b97e29a5caf4eca299788` |

Scope中的BASE_HEAD只表示准备父提交，不是未来执行HEAD。实际HEAD在运行时读取，必须同时
匹配本地、PR、正式完整CI和预签发Grant。因此没有未来Commit SHA的自引用Hash，也不需要
为了最终HEAD再修改Scope。Hash匹配不等于合法Grant，准备任务不等于真实执行许可。

## 复用机制与准入顺序

新增 `run_stage_b_r7_main.py`、`stage_b_r7_main_execution.py` 和固定bootstrap。
仍使用原 `FairMultiSolutionPoolExecutionStore`、`FeasibilityFirstMainLease`、共享
`_github_admission`、server_inputs/fair_binding、运行依赖Hash和工程导出器，不引入授权体系。
R6 Runner、Store、Scope、搜索算法和历史登记簿均不修改。

- bootstrap无参数、只读构造，固定根目录为
  `~/.local/state/cold-storage-planning-agent/owner-pools/<SHA256(R7_TASK)>`。
- Runner先检查原Scope字节、已提交源码和正式CI，再要求预签发Grant；无Grant时不创建输入、
  输出、Claim或账本。Runner没有approve调用，CLI只有原Owner指令路径和新输出目录。
- `server_binding()`读取原封存20t回归输入、Canonical/P1/Site和六个服务器Handoff，
  绑定实际代码HEAD、全部相关已跟踪源码/资源、Scope及真实安装依赖字节Hash。
- 准入固定PR313及实际Base分支/SHA，要求精确HEAD的 `ci.yml`、`pull_request` 事件、
  全部原必需Job及GitHub Actions来源的ci-gate成功。保留SQLite/PostgreSQL、分组覆盖、
  双Linux真实RSS/报告步骤验证；Fast、Push、Dispatch、旧HEAD、错误PR/Base均拒绝。
- 输入/依赖准备后重新检查源码、Grant绑定及PR/Base/CI，才创建新输出并执行唯一
  `store.open("MAIN")`。拒绝任何旧Claim、未知账本、锁或中断残留；不删除、不重置、不恢复。
- 只有以后正式完整CI成功并单独取得Owner最终许可，可信管理员才可使用现有approve流程
  独立预签发R7 Grant。普通Runner永不签发，旧R6 Grant/已消费槽不能授权R7。

使用 `FROZEN_20T_REGRESSION_FIXTURE_NOT_XINZHAO`，不代表新哨正式工程数据。

## 搜索与共享资源保持原样

R7算法文件不修改。第一阶段没有前缘前缀；第二阶段在原独立工程验收反馈后复用同一个
模型、物理Hint、代理及资源账本。原九项与十二项严格比较、独立搜索阈值、基线保护、精确
孔洞切除、单连通和Access校核均保持原样，生产默认不变。

原算法后续Hint和阈值事件仍带R6内核Hash，不能伪装成R7 Hash。新Lease绑定完整策略元组，
按真实事件结构分别验证：第一阶段Reference回执、R7转场、R6 Hint/阈值内核回执。
第一阶段 `FINAL_MODEL_SEARCH_APPLIED` 事件直接拒绝；第二阶段转场必须已有同Handoff
的已保存基线，并验证原前缘Hash、同模型、零额外Native调用及无硬域变更回执。

共享上限仍为MAIN=1、Native49.9s、Elapsed85s、Work600000、RSS512MiB、Native Calls100、
完整赋值20、每requirement Host Work20000。原49.8s/84s搜索目标和所有累计保护原样复用。
六个Handoff、预热、模型、两个阶段、工程验证共同消费；无阶段重置、额外额度或重试。

## 工程输出及首次有效基线计量

| 输出 | 含义 |
| --- | --- |
| `candidate-index.json` / `previews/` | 原始真实有效候选、阶段、几何Hash和SVG；无候选不造图 |
| `area-quality-comparison.json` | Office/Changing/Coating需求与实际面积、尺寸及比例，原九项与十二项独立比较 |
| `search-recovery.json` | 首次工程有效布局是否找到，与整体质量改善分别报告 |
| `r7-search-feedback.json` | 原始前缘转场、Hint、阈值及正式质量事件 |
| `work-breakdown.json` | 原始计费标签；将延后前缘读写/重排单列，原总数和未归类值不变 |
| `topology-rejections.json` | 原始全部拓扑拒绝证书，unknown不改为0 |
| `resource-ledger.json` / `journal.jsonl` / `execution-record.json` | 原持久化账本、检查点及完整执行记录 |
| `source-binding.json` / `ci-admission.json` | 实际来源与精确HEAD正式验收证据 |

首套有效基线只从已导出、同Handoff/同几何的原始基线事件识别。用其原始event sequence与
journal中 `STAGE_B_ENUMERATION_AUDIT_RECORD` 计数精确对应，读取当时Native、Work和Elapsed。
测量点明确为 `INDEPENDENTLY_ACCEPTED_BASELINE_PERSISTENCE_AUDIT`，不是原生Callback见证时间。
不使用较早candidate快照近似，也不使用整个MAIN末尾消耗代替。检查点缺失或重复时计量为
NOT_EVALUATED；没有有效基线时不填0秒，不报告恢复成功。

搜索恢复不自动等于布局质量改善。原九/十二指标、同Handoff/V2/Authority限制和
FunctionalFit=INPUT_REQUIRED保持；Truck/P2D没有独立实证不得通过。

## 验证与本轮终点

接线测试统一禁止实际 `CpSolver.solve`，仅在临时合成登记簿创建测试授权/Claim。
覆盖Owner Hash/策略与旧Scope拒绝、独立任务槽、源码/输入/依赖/CI变动的pre-Claim拒绝、
单次消费、资源整笔预检查与回退保护、R7转场真实嵌套回执，以及首次有效基线计量的完整/
缺失/重复/身份冲突情况。模拟资源状态测试不冒充真实进程RSS验收。

原R7生产边界测试只允许新增的这个专用Runner路径，其他生产入口仍被原断言覆盖。
完成本地回归和自动快速CI后停止；正式完整CI、真实Grant/Claim、MAIN、Ready/Merge/Deploy
均不在本轮执行范围。
