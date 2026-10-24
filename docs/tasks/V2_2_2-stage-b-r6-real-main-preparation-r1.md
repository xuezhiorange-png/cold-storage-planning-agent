# R6 单次 MAIN 入口准备

TASK_ID：`V2_2_2_STAGE_B_R6_REAL_MAIN_PREPARATION_R1`。
起始 HEAD：`5527df6160f1b6e257ce42556691b2b166089ede`，目标 PR #312。
本任务仅接线、临时登记簿测试及自动快速 CI；不签发真实 Grant，不消费真实 Claim，
不运行真实 MAIN，不触发正式完整 CI。

## 固定身份与来源

| 项目 | 绑定 |
| --- | --- |
| 实验任务 | `V2_2_2_STAGE_B_R6_REAL_MAIN_R1` |
| 求解器 | `StageBFrontageJointSearchFairSolver` |
| PR / Head 分支 | #312 / `codex/stage-b-r6-frontage-joint-search-r1` |
| Base 分支 | `codex/stage-b-area-efficient-layout-r5` |
| Base SHA | `f38f98c3a36346bc0837939558ee2d9936b5687b` |
| Owner Scope | `docs/tasks/V2_2_2-stage-b-r6-owner-scope.txt`，UTF-8 / LF |
| Owner Scope SHA256 | `fffd389f7b56a2907869ae21bb7ddab20d5adde0637f26aa928dd40ca0975998` |
| R6 组合策略 | `sha256:5584fd5bb8a833905bc0f441bcdc1da8d9876f619d75b7d9fd948c843a2fd95d` |
| Reference 准备策略 | `sha256:31d228d6995aa7d2d71fd5a5fe740868aecda89b2526ff88081efb41f4fb80df` |
| 功能前缘 / 工艺接缝策略 | `sha256:ac9ce2d9b8f6d196705c12f91d28bb113b31ab31eebb4cf79aa319a030e38923` |
| 原面积软目标 | `sha256:1fc76233d500120f2b80f44feb6ba557fd1e3181be123b113519d93faa13ba6d` |
| 原 Native 反馈策略 | `sha256:4341a26ac10e7bca12f53a2a64866908dee10c8e1af516bb0b2e90ba578660a2` |

Scope 中的 BASE_HEAD 是本次准备的父提交。实际执行 HEAD 在运行时读取并绑定，
必须同时匹配当时本地 HEAD、PR HEAD、预签发 Grant 和正式 CI，因此没有自引用 Hash
循环，也不需要为了最终提交 SHA 再改写 Scope。Hash 匹配不等于合法 Grant。

## 复用与拒绝顺序

- `bootstrap/stage_b_r6_main.py` 只构造现有可信文件系统 Store，固定任务根目录为
  `~/.local/state/cold-storage-planning-agent/owner-pools/<SHA256(TASK)>`。
  构造器不创建目录、签发或消费授权。
- `R6MainStore` 复用 `FairMultiSolutionPoolExecutionStore`，`R6MainLease` 继承
  `FeasibilityFirstMainLease` 的计量、防回退、持久化和资源保护。
  R5 Store、Runner 和历史任务均不修改。
- Runner 先校验 Scope 原始字节、已提交源码及正式 CI，再读取预签发 Grant；没有
  Grant 时不生成服务器输入、不创建输出目录、不消费 Claim。
- `server_binding()` 只读取现有 `server_inputs`、`fair_binding`、实际 HEAD、全部相关
  已跟踪源码 / 非 Python 运行资源、Owner Scope、依赖锁文件和 Runtime Dependencies。
  六个 Handoff、P1 / Site / Plan Hash、策略和合同均进入同一 Binding。
- 在输入与依赖准备后，重新验证源码、Binding、PR/Base/正式 CI，再创建新输出目录并
  执行唯一一次 `store.open("MAIN")`。任何未知账本、Claim、锁或其他任务槽残留均拒绝，
  不删除、不重置、不恢复。直接调用 Store.open 也必须先通过未消费槽检查。
- 正式 CI 使用原共享 `_github_admission`，固定为本 PR/Base、精确 HEAD、
  `.github/workflows/ci.yml`、`pull_request` 事件及原必需 Job；包含 SQLite、PostgreSQL、
  `backend-partition-coverage`、双真实 Linux RSS / 报告步骤和 GitHub Actions 的 `ci-gate`。
  快速 CI、Dispatch、Push、旧 HEAD、错误 Base、skip / pending / failure 都不能替代。

## 搜索与资源

显式使用 R6 类，原 R5 和生产默认选择器保持不变。Reference 增量事实记录、前缘 / 门面 /
接缝软顺序、当前工程有效候选的物理 Hint、独立搜索阈值、原始基线保存及精确拓扑切除
均由原 R6 算法直接执行。新增 Lease 仅验证这些新事件的策略身份与严格递减回执；
不改变搜索目标、物理可行域或正式比较规则。

Native 仍采用原生产配置：Presolve 默认启用，完整阶段使用 `PARTIAL_FIXED_SEARCH`，
一个 Worker。没有复制合成演示专用的禁用 Presolve / `FIXED_SEARCH` 设置。

共享硬上限保持 MAIN=1、Native≤49.9s、Elapsed≤85s、Work≤600000、RSS≤512MiB、
Native Calls≤100、完整赋值≤20、每个 requirement Host Work≤20000。
原 49.8s / 84s 搜索目标及导出余量不变。六个 Handoff、四轮预热、模型构造、两个阶段和
工程校核共用累计账本。无阶段重置、重试、Replay、Resume 或第二次 MAIN。

## 输出与判定

复用既有工程评审导出器，保留全部有效候选原始几何、证书、SVG 和 Hash。

| 输出 | 内容 |
| --- | --- |
| `candidate-index.json` / `previews/` | 原有效候选、阶段、几何 Hash、真实 SVG |
| `area-quality-comparison.json` | Office / Changing / Coating 的需求与实际面积、超配、实体长宽及比例；路线及轮廓事实；原九项和十二项独立比较 |
| `execution-summary.json` | 原始基线、第二阶段、有效几何、可计数 V2 组织及两套比较计数 |
| `r6-search-feedback.json` | 原前缘决策、模型策略、Hint 和阈值更新事件 |
| `topology-rejections.json` | 全部原始拒绝证书，null / unknown 不改写为 0 |
| `work-breakdown.json` | 原标签分组、模型准备、物理 Hint、反馈、拓扑 / 切除、验证 / 导出、Host Work；保留未归类和未能对账部分 |
| `resource-ledger.json` / `journal.jsonl` / `execution-record.json` | 原持久化账本、逐次快照及所有事件 |
| `resource-usage.json` | 原累计 Native、Elapsed、Work、RSS、调用与完整赋值计数及是否守限 |

Work 分组只读原计数，不降低系数或改写账本。Native Host 的可观察原语计数与 CP-SAT
内部搜索 Work 分开标记。搜索阈值递减不计入正式 Pareto 改善，0.000714 m² 的面积增加
仍按原十二项规则判为 Tradeoff。跨 Handoff、跨 V2 或未配对候选不默认视作 Pareto。

后续可与 Owner 提供的 R5 Changing 参考事实（40.000464m² / 39.368056，
85.575750m² / 8.101846）对照；这些数值不是求解 Seed、工程硬约束或自动 Pareto 配对。
必须读取封存 R5 几何并说明可比性后再形成实际对照。封存 20t 输入不代表新哨二期审批。

## 后续执行方式——本轮不执行

只有最终 HEAD 的正式完整 CI 成功、且 Owner 再次明确授权该精确 HEAD 后，可信管理员
才可按现有流程独立签发一次 R6 Grant。管理员可复用 `server_binding()` 生成与 Runner
完全相同的源绑定；签发前须核实 Scope、完整 CI、HEAD、运行环境及任务根目录从未存在。
普通 Runner 没有批准入口，CLI 仅支持 `--owner-instruction` 和新的 `--output`。

未来独立授权后的 MAIN 命令为：

```sh
cd backend
PYTHONPATH=src:scripts uv run python scripts/run_stage_b_r6_main.py \
  --owner-instruction ../docs/tasks/V2_2_2-stage-b-r6-owner-scope.txt \
  --output ../artifacts/stage-b-r6-real-main-r1
```

该命令不会自动签发 Grant。输出目录必须不存在。任何失败或资源中断后保留 Claim 和
原账本，立即停止。本准备任务结束时不执行以上命令，不请求正式 CI 或真实执行授权。

## 本地验证

R6 接线 109 项测试在原独立 Worker 框架下全部通过；与原 R5 接线、共享 GitHub 准入合并
回归 254 项通过。原 R6 搜索回归 53 项、架构 771 项（16 项原有 skip）、CI 契约 64 项
通过；Ruff、Format、Mypy（src 与新 Runner）及 diff 检查通过。接线测试统一禁止实际
`CpSolver.solve`，Grant/Claim 仅在临时合成登记簿中创建，生产 Presolve / PARTIAL_FIXED
配置通过无 Native 的参数探针验证。

旧 R6 测试原先禁止任何脚本导入该策略；本次仅允许新增的这个专用 Runner 路径，
其余生产入口仍被原断言检查，算法源码和 R5 历史代码未修改。真实 Linux 物理 RSS 不在
本轮本地执行；后续正式 CI 准入仍要求原双 Worker 与报告校验成功。
