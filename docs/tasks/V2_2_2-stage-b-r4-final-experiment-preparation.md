# R4 最终实验准备：接线、范围Hash与PR310正式CI

Preparation task: `V2_2_2_STAGE_B_R4_FINAL_EXPERIMENT_PREPARATION`。
固定起点：`6b114ac3cda934b07e7d8fbe00d95904e7aa996a`，开发PR #310。
新的一次性实验任务：`V2_2_2_STAGE_B_R4_REAL_MAIN_R1`。

本任务只完成准备与一次正式验收，**不授权MAIN、Grant签发或Claim消费**。
不存在第二套求解器、签名、公私钥、授权服务或新的预算体系。

## 1. 已固定的Owner范围

`V2_2_2-stage-b-r4-owner-scope.txt` 为UTF-8/LF规范化文件，SHA256：

`c9c080ed9a9226de4632cec0513a5842c844a3d8621d332a25a78b10224209fd`

范围文件同时约束实验ID、PR身份、两级策略、原Minimax/反馈策略、20t输入身份、
一次MAIN和共享资源、禁止重放/重试/补预算，以及必须另获精确HEAD执行确认。
Hash匹配只证明范围字节一致，**不是Grant或执行许可**。

不把包含自己的最终提交SHA写回范围文件形成自引用。文件中的BASE_HEAD是祖先；
最终执行HEAD由既有Store将真实`git HEAD`、源码文件、锁文件/安装依赖Hash、Plan、
P1、typed Site、六个服务器Handoff和固定策略一起绑定，入口另核验该精确HEAD的
正式PR CI。没有取消任何精确HEAD或依赖校验。

R4组合策略：
`sha256:fad41d6d4be18248b9a5ee93e299a591876e40e2422ac0ed5aa3924c2e2e5156`。

第一阶段策略：
`sha256:ce5fd7a398ecfc93ed98ccc9108209fe011402d4dd81b697da9e8b70886fb940`。

原R3反馈策略：
`sha256:4341a26ac10e7bca12f53a2a64866908dee10c8e1af516bb0b2e90ba578660a2`。
本轮不改R4算法、Minimax、九指标比较、Pareto Hint、拓扑或工程硬约束。
适配层同时校验导入的四项策略Hash与本范围的固定值，未来算法改版不能仅因
更新import而沿用本Owner范围；任何不一致在构造Store前拒绝，不创建新任务记录。

## 2. 固定入口与原可信机制

入口：`backend/scripts/run_stage_b_r4_main.py`，只提供
`--owner-instruction`和`--output`。没有Caller可选的任务、PR、策略、坐标、预算、
Grant路径或注册表参数。

`bootstrap/stage_b_r4_main.py` 固定使用原可信管理员注册表目录，任务槽为实验ID的
SHA256：`1a2df896c60d7849625bf7f17857c7762d8577f3441e9852756df9ad746749b2`。
准备时该槽不存在；构造Store不创建目录。本轮不创建真实执行记录。

适配层`stage_b_r4_main_execution.py`复用原`FairMultiSolutionPoolExecutionStore`、
`PoolLease`和更紧的`FeasibilityFirstMainLease`。预签发Grant必须来自既有可信文件系统
管理员边界。入口永不调用`approve`；缺失Grant、既有Claim/账本/锁、未知中断状态
一律拒绝，不修复、不覆盖、不换任务槽。旧Owner字节、旧策略、旧任务和篡改预算
不能用于新任务。

第一阶段使用`StageBFirstStageBalancedQualityFairSearchSolver`。独立工程通过的
基线先保存，第二阶段复用同一模型、当前Handoff和累计账本。原精确拓扑见证切除、
R3整笔Work预检查、实际Pareto才更新的Hint，以及九项几何/路线/轮廓比较不变。
Lease按真实事件结构验证第一阶段/第二阶段/质量事实，以及嵌套guidance中的Hint
策略Hash，避免将正常R3 Pareto Hint误当成旧策略事件。

共享硬上限：Native49.9秒、Elapsed85秒、Work600000、RSS512MiB、Native Calls100、
完整赋值检查20、单requirement host work20000。原49.8/84搜索安全余量也保留。
六个Handoff、两个阶段不各领预算；仅MAIN，不能REPLAY/RESUME/第二次MAIN。

## 3. PR310的精确HEAD正式CI准入

实际只读核实并固定：

- repository：`xuezhiorange-png/cold-storage-planning-agent`
- PR：310，OPEN/DRAFT，Head ref：`codex/stage-b-first-stage-quality-r4`
- Base ref：`codex/v2.2.2-p1a-structural-hard-interface-reservation-p0`
- Base SHA：`9c13a134b6008c8960996eedf016dc2b4754a013`

共享查询逻辑抽取为私有`_github_admission`。原`github_admission(repo)`仍固定PR307、
main、原祖先与原必需Job，默认接口和规则不放宽。R4入口传入上述固定身份与Base SHA，
不是沿用307，也不从Owner文件/环境/CLI接收可更改的准入身份。

R4要求当前本地HEAD等于PR310 HEAD；正式workflow ID/path为`.github/workflows/ci.yml`，
事件为真实`pull_request`；Run关联PR、Head仓库、分支、SHA、Base仓库/分支/SHA必须
一致。最新匹配Run必须COMPLETED/SUCCESS，拒绝用旧SUCCESS绕过较新的PENDING。

九个必需Job必须唯一且实际成功：classify-changes、backend-sqlite、backend-postgresql、
backend-partition-coverage、frontend、compose-config、release-evidence、
recovery-foundation、ci-gate。SQLite内两次真实Linux RSS、双报告校验和隔离回归
步骤也必须全部成功。ci-gate检查必须来自GitHub Actions App15368且Check Suite对应
这次Run。缺项、重复、SKIPPED、取消、分页不完整或身份矛盾均fail closed。

查询前后复核同一PR身份及本地HEAD；服务器输入/依赖准备后、创建Claim前再次复核。
Base移动、PR retarget、旧HEAD、Fast CI、Dispatch和Push成功均不能放行。

## 4. 提交前检查和一次正式验收

本地使用Mock与临时合成注册表，新增测试禁止任何`CpSolver.solve`调用；真实注册表
只读Hash对账。覆盖固定Scope/Hash、旧授权/预算/来源篡改、无Grant阻断、一次消费、
同账本、Work整笔预检查、真实事件结构，以及PR310/Base/Job/RSS/App身份反例。
原PR307准入测试完整保留。新增测试接入原独立resource worker及自动快速CI。

源码和本地检查全部结束后一次Commit/Push。先等待最终HEAD快速CI通过，确认没有
同HEAD正式验收后，仅添加一次`ci-full-request`标签，触发真实labeled事件完整CI。
不使用workflow_dispatch、不反复移除/添加标签、不重跑失败CI。
本轮不改变完整CI的测试集合、资源门槛、分组策略或最终ci-gate名称。

提交前实测：最终准入119 PASS（新实验测试中Native调用被禁止），历史入口/Work
组合256 PASS；去重并合并771项架构回归后为1032个pytest PASS，另35个CI契约
PASS。16项原有skip单列；macOS显式排除1项真实Linux RSS，不计PASS。
Ruff、Format、Mypy（443源码/入口及两个共享CI脚本）、diff检查通过。
完整CI前不把这些本地结果当作Linux物理RSS或正式验收通过。

完整CI完成后回读Job/步骤和原两份Linux RSS JUnit，使用既有`verified_receipt`
验证真实Linux、两个不同PID、原guard超限拒绝与无skip/xfail，不重新加压。
完整CI失败则保留失败日志、报告阻断，不自行开下一次验收。

## 5. 后续执行与本轮停止点

正式CI成功后保持最终HEAD和PR310 OPEN/DRAFT不变，报告已具备条件并停止。
Owner仍须对该最终精确HEAD另行确认唯一一次MAIN，之后才可由原可信管理员流程
读取固定Owner字节、重新核验正式CI、服务器来源和安装依赖，签发合法一次性Grant。
普通runner不能代签，不能把本准备任务或本文件当作预签发Grant。

后续输出复用既有exporter：有效候选原JSON/SVG、候选索引、工程证书、基线与同
Handoff比较事件、拓扑拒绝、累计资源账本与消耗。未完成验证的指标保持未知。
封存20t输入不是新哨二期正式工程Authority；Truck仍BLOCKED_PROJECT_INPUT，
功能适用性INPUT_REQUIRED，P2D_FULL_PASS_COUNT=0。

本轮`REAL_MAIN_EXECUTED=false`、`GRANT_CREATED=false`、`CLAIM_CONSUMED=false`。
不修改#307/#308/#309原分支，不自动Ready/Merge/Release/Deploy。
