# R5 单次真实实验准备（不授权执行）

Preparation: `V2_2_2_STAGE_B_R5_EXPERIMENT_PREPARATION`。
Execution identity: `V2_2_2_STAGE_B_R5_REAL_MAIN_R1`。
Base HEAD: `5097afc9b5d2910333036c518f4e91f1755b3693`。

本次只复用 R4 Store/Lease、服务器输入、正式 CI 验证及证据导出机制，
不修改 R5 算法、任何工程 Authority、生产默认、旧任务或累计资源保护。
本任务允许现有 PR #311 的接线、测试、Commit/Push 和自动快速 CI；
不请求正式完整 CI，不签发真实 Grant，不创建 Claim，不运行 MAIN。

## 一次冻结的身份

- PR #311，Head 分支 `codex/stage-b-area-efficient-layout-r5`。
- Base 分支 `codex/stage-b-first-stage-quality-r4`，Base SHA
  `4529144b187241702b82eb384887da15aa359aac`；不是 PR #310 的 Base。
- 固定服务器输入：既有封存 20t 回归 Fixture，不是新哨二期正式工程输入。
- 显式求解器：`StageBAreaEfficientQualityFairSearchSolver`。
- 软目标：`sha256:1fc76233d500120f2b80f44feb6ba557fd1e3181be123b113519d93faa13ba6d`。
- 组合策略：`sha256:ddccb804958e52c169ad1d1c0c2c6ecc259271e350e23207dba0b1a5e71db0a4`。
- 十二指标版本：`same-handoff-nine-metrics-plus-three-area-allocations@1.0.0`。
- UTF-8/LF Scope：`V2_2_2-stage-b-r5-owner-scope.txt`，SHA256
  `574701eece1f41db140e58c832403f1a7b23f6f8bfdb0302ab903864d6d36448`。

Scope Hash 仅校验这份固定实验范围，不是 Grant，不构成本轮执行许可。
复用原有做法：Scope 固定起始祖先，正式 CI 和管理员签发的 source binding
另行绑定最终实际 HEAD、所有后端源码/脚本/Scope、Fixture、锁文件、真实运行依赖
及 Plan/P1/Site/六个 Handoff。Scope 不嵌入自身未来提交 SHA，不取消精确 HEAD 校验。

## 后续正式准入（本轮不执行）

先由 Owner 单独批准最终 HEAD 的一次正式完整 PR CI。
`run_stage_b_r5_main.github_admission` 复用共享 `_github_admission`，验证
精确 HEAD、OPEN/DRAFT、实际 PR/Base 来源及前后身份、ci.yml 的 pull_request 运行、
ci-gate 的 GitHub Actions 身份、全部必需 Job（含 SQLite、PostgreSQL、
backend-partition-coverage）和原双真实 Linux RSS/报告校验步骤。
快速 CI、Dispatch、Push、历史 HEAD、缺项或跳过均不能放行。
原 PR #307/#310 的入口与准入规则保持不变。

完整 CI 成功后仍需 Owner 对最终精确 HEAD 单独授权真实 MAIN，
再按现有可信文件系统管理员流程签发新的 R5 一次性 Grant。
普通 Runner 不调用 approve、不创建或修复授权，不接受任意预算、策略、
PR、注册表或坐标参数。固定 R5 槽仅在真正签发/执行时由原 Store 创建；
构造 Store、准备任务与 Hash 匹配不消费任何槽。
缺少 Grant 时，在生成服务器输入、建立输出目录和 Claim 之前拒绝执行。
旧任务 Grant/Scope、已消费槽、残留 ledger/journal/lock 或未知中断必须硬停止，
不清理、不重置、不恢复、不重试。

六个 Handoff 和两阶段共享原单 MAIN 累计硬上限：49.9 s Native、85 s Elapsed、
600000 Work、512 MiB RSS、100 Native Calls、20 完整赋值、每需求 Host Work 20000。
保留原搜索安全余量、R3 整笔 Work 预检查、独立工程验证及第一阶段基线保护。
任何阶段均不补充额度；无 REPLAY/RESUME/第二次 MAIN。

## 后续结果证据

复用原候选工程证书、真实 SVG 导出与 Hash 检查，保存全部工程有效几何，
包括不增加 V2 数量的几何变体，不覆盖第一阶段基线。
新增的 `area-quality-comparison.json` 直接复用现有 R5 snapshot/comparator，列出：

- 三个辅助房间的 P1 需求、实际面积、配置及超配比例、实际尺寸和长宽比。
- 原九指标与新增十二指标的独立比较结果/计数，绝不静默重定义九指标。
- 实际建筑面积、周长、转折、凹角，实际人员路线长度/转向及 V2 身份。
- 原始资源账本、全部拓扑拒绝事件及其原证书；null/未知孔洞数不改写为零。

严格 Pareto 只限本次同一 Handoff、同 V2 组织且同 Authority 的完整证据；
跨组织输出 NOT_COMPARABLE_STRUCTURE，缺失比较输出 NOT_EVALUATED。
R2/R4 可以另作同口径历史事实对照，不能混入 R5 同次 Pareto 集合。
原比较事件逐项回读核对。无候选不制造布局；没有真实实验不宣称真实质量改善。
Coating 始终是 PACKAGING_BOX_FILM_SEALING，设备/装修净空仍 INPUT_REQUIRED，
Truck 仍 BLOCKED_PROJECT_INPUT，P2D_FULL_PASS_COUNT=0。

## 验证与停止

仅临时合成注册表和 Mock 执行链用于测试，禁止真实 Native/Grant/Claim。
覆盖 Scope/策略/预算篡改、PR/Base/正式 CI 缺项、旧授权重用、一次消费、
累计 Work 整笔拒绝、共享账本、独立九/十二报告及基线保留。
新测试纳入原隔离 Worker 和自动快速 CI；真实 Linux RSS 门禁不修改。
快速 CI 成功、源码冻结后 STOP，等待 Owner 下一次正式 CI 授权。
