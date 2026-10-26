# R9 资源受控 MAIN 接线准备

TASK_ID=V2_2_2_STAGE_B_R9_RESOURCE_BOUND_MAIN_PREPARATION_R1

基线：PR #317，`34d2052d53aa8575f3794917e27b1677a094f668`。
正式实验：`V2_2_2_STAGE_B_R9_RESOURCE_BOUND_REAL_MAIN_R1`。
本轮只准备接线，未授权真实 MAIN、实际 Grant/Claim 或正式 CI。

## 固定入口与身份

- Runner：`backend/scripts/run_stage_b_r9_main.py`；只接受 `--owner-instruction` 和新的 `--output`。
- Store/Lease：`stage_b_r9_main_execution.R9MainStore / R9MainLease`，复用原 Fair Store、PoolLease、R3 整笔预检查和 Feasibility First 单次资源保护。
- Bootstrap：`cold_storage.bootstrap.stage_b_r9_main.approved_r9_main_store()`；登记簿父目录仍由原可信 bootstrap 固定，任务槽使用新 TASK 的 SHA256，不接受 CLI、环境变量或配置指定替代槽。
- 求解器：`StageBResourceBoundRouteRefinementFairSolver`。
- 策略：`sha256:ce8c264012510d9655e9d28ca283a98c99775c913df8e976b4ad3e2d5ac17272`。原路线、联合门面、R7 首次可行、Reference、软目标、回调与严格比较版本逐层固定；旧授权不能选择本任务。
- Owner Scope：`docs/tasks/V2_2_2-stage-b-r9-owner-scope.txt`，UTF-8/LF 原始字节 SHA256：`df0792cf845346a7ebe620509f7fac4c8f631ac6328bdb1b633b12e7d33cf3eb`。
- Scope 固定起始 HEAD、PR/分支/Base、策略和预算，不包含未来最终 Commit SHA。实际执行 HEAD、全部源码文件、Scope、依赖锁和 Runtime Dependencies 在 `server_binding()` 中重新读取后绑定 Grant，无自引用，也不取消精确 HEAD 校验。

## 正式 CI 与一次性消费

PR #317 / Head ref `codex/stage-b-r9-route-resource-scaling-r7` / Base ref `codex/stage-b-r9-same-proxy-route-r6` / Base SHA `c52b51c7866ee439f1513780003f31b23501aedb`。

新入口复用 `_github_admission`：当前本地/PR HEAD、来源与 Base 身份一致，必须是当前精确 HEAD 的 `.github/workflows/ci.yml`、真实 `pull_request`、全部必要 Job、分组覆盖、SQLite/PostgreSQL、两个真实 Linux RSS 和 GitHub Actions 的 ci-gate 成功。Fast、Dispatch、Push 或旧 HEAD 均不能替代。

执行顺序不变：Owner 原字节 Hash → 已提交源码 → 正式 CI → 只读检查预先签发的 Grant → 服务器输入/六 Handoff/源码/依赖绑定 → 再核 PR/CI → 新输出目录 → 唯一一次持久化 Claim → Pool。

管理员只有在未来单独取得 Owner 对精确 HEAD 的执行授权后，才能使用原可信文件系统签发流程与 `R9MainStore.approve()` 独立签发。本轮未调用真实签发接口。普通 Runner 没有 approve 调用；Hash 匹配不是 Grant。任何已有 Claim、锁、账本或不明残留均拒绝，不删除、不重置、不自动修复。

## 共享资源与回执

一个 MAIN、六 Handoff、预热、模型构造、第一阶段、第二阶段和工程验证共用一个原累计账本：Native≤49.9s、Elapsed≤85s、Work≤600000、RSS≤512MiB、Native calls≤100、完整检查≤20、每要求 Host Work≤20000。原 49.8s/84s 搜索安全保留仍在，不扩大额度。RETRY/REPLAY/RESUME 均禁止。

原资源策略每 Handoff 最多一次局部模型复制，并在复制前检查真实剩余资源；原路线算法和计费没有变化。新 Lease 校验真实三层回执：第二阶段 guidance 保留联合门面 Hash，路线回执为父路线 Hash，资源回执另带资源策略 Hash。不能把三者都误认成最外层 ce8 Hash。资源不足的 SKIP 保存明确原因并保持原活跃 Handoff；实际 guard/precharge 错误继续拒绝，不能伪装 SKIP。

## 输出与结果区分

复用原真实几何导出器、SVG、候选 Hash、`_eligible()` 和工程证书。`candidate-index.json` 保留有效路线见证，原 Pool 仍按原房间几何/V2 去重；同房间不同路线不能增加房间几何数。

- `search-recovery.json`：通过独立工程验证的首套基线、首次基线保存审计时的 Native/Work、每 Handoff 基线、第二阶段启动。缺失或多义的 journal 不补零。
- `area-quality-comparison.json`：Office/Changing/Coating 的 P1 需求面积、实际面积、超配、实体尺寸、比例，人员真实路线/转向、建筑轮廓；原九项和十二项严格比较分别呈现。
- `r9-route-resource-report.json`：六 Handoff 初始份额及原持久化快照推导的结束余量；每次 ADMITTED/SKIPPED/RESOURCE_FAILED、精确 skip 原因、复制完成回执、原始错误、有效 Hint、同房间同代理路线、V2 可比性及原比较函数结果。复制中断不能证明是否完成时填 NOT_EVALUATED，而不是零。
- `work-breakdown.json`：原计费标签与总额，ROUTE_* 单列；Native Host 与 CP-SAT 内部搜索工作不混淆。
- `resource-ledger.json`、`journal.jsonl`、`execution-record.json`、原候选与拓扑拒绝、运行依赖、输入与源文件绑定完整保留。

首次布局恢复、同房间路线缩短、正式整体 Pareto 改善是三个独立结论。22.500m 仅为旧合成见证，不是 20t 结果。跨 Handoff/V2 不能合并成正式 Pareto 集合；Truck/P2D 没有独立实证时不通过。

## 本地验证

- R9 Grant/Claim、Hash/预算/来源、CI、重复消费、SKIP/fail-closed、导出与份额回读：156 个独立 Node ID 通过（155 项主回归，加最终 Host Work 报告双分支重验，重叠不重复计数）；使用临时合成登记簿，两种 Native Solve API 均被禁止。
- 原 R7 关键执行回归：12 PASS（119 项按此次范围未选）；原文件未改。
- 架构：771 PASS，16 项原有 skip。
- CI 契约：64 PASS，含 50 次临时 Git 清理循环。
- 六个真实封存 20t Handoff 仅构模：各 27400 变量、38640/38644 约束，P1/Plan/Site/六 Handoff 与实际服务器读取一致；Native0、真实 Grant0。
- 两套封存合成几何重新经过原独立几何、完整应用/Access/Site/Footprint、原生 Access 和 `_eligible()`：PASS；无新 Native，不产生新布局。
- 旧合成回执只读验证新报告接口：26.750→22.500、同 V2、原九/十二严格比较保持原结论。该项不算新实验。
- Ruff/Format/Mypy（含新 Runner 和导出脚本）/YAML/diff：通过。自动快速 CI 的最终 Run/HEAD 见本轮冻结回执；不触发正式 CI。

源码、资源策略、原 P1/MUST/Access/Topology 权威和比较函数未改；R5/R6/R7 的真实可信登记簿和历史 PR 不受影响。准备完成后冻结源码，仅等待 Owner 审核，不自动执行任何下一阶段。

## 自动快速 CI 隔离契约修正

首个接线提交 `ea348bafaa7b0f1251cb21d64b9bfc60d2a80064` 的快速 CI `40298288784` 为 FAILURE：Stage B 1139 PASS、1 项既有默认策略隔离断言失败。新报告脚本直接导入面积比较模块，触发了该模块只能由原 R5 入口直接引用的隔离契约。本地提交前漏跑了这一旧契约；失败记录保留，不将其称为通过。

最小兼容修正将只读报告投影归位到 layout Infrastructure，Runner 只调用 R9 报告接口；复用原十二项比较函数及其中的原九项结果。R5 脚本未显式导出比较器，本地类型检查拒绝后未采用脚本间隐式重导出。不修改旧测试、比较函数、R5/R9 求解器、Owner Scope/Hash、资源预算或默认入口；无字符串拆分、动态导入或门禁豁免。原失败 Run 不重跑；修正提交只产生自动快速 CI，最终 Head/Run 以冻结回执为准。
