# R10 R2 独立 MAIN 接线准备

TASK_ID=`V2_2_2_STAGE_B_R10_R2_REAL_MAIN_PREPARATION_R1`

基线 PR319：`0cf97f6d4a4ba48947bc9bfdef25e97968eb9832`。独立 Draft PR320，分支`codex/stage-b-r10-r2-main-preparation-r1`；Base为`codex/stage-b-r10-entrance-coupled-spatial-r2`、精确SHA同上。先以准备说明提交建立真实PR编号，再一次冻结本轮Scope/Hash及接线；没有猜编号、回填未来HEAD或重复正式CI。

## 已完成接线，尚未授权执行

- `backend/scripts/run_stage_b_r10_r2_main.py`：原单次MAIN的两次精确PR/CI核查、预签发Grant要求、服务器输入、源码/运行依赖绑定、原共享池和证据导出顺序。Runner不调用approve，没有重试/Replay/Resume分支，输出必须新建。
- `backend/src/cold_storage/bootstrap/stage_b_r10_r2_main.py`：无参数固定可信登记簿工厂，构造不创建任务槽或授权文件。
- `backend/src/cold_storage/modules/layout/infrastructure/stage_b_r10_r2_main_execution.py`：独立TASK、Scope和CI合同，复用Fair Store、原PoolLease及单次MAIN累计保护；不新建授权系统。
- `backend/src/cold_storage/modules/layout/infrastructure/stage_b_r10_r2_main_evidence.py`：只读投影当前执行的几何、路径、首次基线和逐Handoff资源，缺失/歧义证据保持NOT_EVALUATED。

固定实验`V2_2_2_STAGE_B_R10_R2_REAL_MAIN_R1`，显式求解器`StageBEntranceCoupledSpatialFairSolver`；算法文件与PR319逐字节一致。第一阶段继承原R7，第二阶段仅使用既有R10 R2软顺序，不能自动进入R9局部路线复制。

策略Hash：`sha256:fc0082de49eb1e289c487c2f88c4a873f73b3a553077102dc7dc1aa0e11afcf5`。

规范化Owner Scope：`docs/tasks/V2_2_2-stage-b-r10-r2-owner-scope.txt`，UTF-8/LF；SHA256：`f01b5e900ae2bc97fa2330e63a93f6f6989208ad26c105a52ec98d064031a740`。Scope仅写已知开发Base，不含未来最终HEAD自引用；实际执行HEAD由原Git/source binding与正式CI证明动态绑定。Hash匹配本身不是Grant，准备任务不授权真实签发或消费。

独立登记槽为既有owner-pools目录下TASK SHA256 `a0b9edd4c3375d08c0ff1c5d22f8ae5cad574cb21318ff9995a0f011e4c2b4fc`。本轮只读确认该真实槽不存在，未创建、打开或清理；旧R9等已消费槽与历史账本不变。

## 原资源及工程保护

原合同：一次MAIN；49.9s Native、85s Elapsed、600000 Work、512MiB、100 Native Calls、20完整赋值检查、单要求20000 Host Work。原49.8s/84s搜索预留保持，六Handoff、四轮预热、模型与两阶段及工程验证共用累计账本。整笔Work预检查原样继承，不调整计费、不补充资源。

新Lease核实原有效基线已经在同Handoff持久化，才接受R7前缘和R10 R2协同回执；核实固定策略、原Hint未变、无新变量/约束及零额外复制/调用。拒绝SAME_PROXY_ROUTE回执。Runner采用R9已经使用的最终资源回读：包括单要求Host Work、导出后Elapsed/RSS；超限落盘并失败，保留原有异常，不把resource_caps_respected=false当成功退出。

P1、MUST、Site、Packaging、Access、精确单连通/零孔洞校核、生产默认和九/十二项比较均未修改。

## 正式CI合同

独立固定PR320身份、Head分支、PR319 Base分支和精确Base SHA。复用原`_github_admission`，精确当前HEAD、真实`.github/workflows/ci.yml`的pull_request成功；继续检查GitHub Actions来源的ci-gate、SQLite/PostgreSQL、分组覆盖及两份真实Linux RSS步骤/报告校验。额外明确列出architecture/lint/mypy三个原必要Job。Fast、Dispatch、Push、历史HEAD、其他PR/Base、缺失Job/RSS或运行前后身份变化都拒绝。

本轮没有正式完整CI；准备完成不等于正式准入PASS。后续必须对冻结最终HEAD取得正式CI及Owner独立执行许可；不得复用PR317/319旧证明。

## 未来输出及比较口径

复用原基础导出和R5质量快照/比较，继续输出实际SVG、candidate-index、area-quality-comparison、topology-rejections、原始journal/ledger、execution-record、resource-usage。

新增`r10-r2-organization-report.json`及逐Handoff汇总包括：

1. 原六个服务器Handoff的身份、首个有效基线及原持久化审计点的Native/Work，H1–H4实际有效候选。
2. 当前有效候选的Changing/Office/Coating需求和实际面积、实体尺寸/长宽比，Sorting/Changing原位置，建筑面积/周长/轮廓指标。
3. CP-SAT导出Portal与独立应用Access路径分别保存；不假定它们总相同（历史P01有250mm入口偏移差），正式指标用原实际应用几何。
4. 第二阶段真实激活回执、当前Hint的实际Portal参考、逐Handoff共享份额、原journal端点的Work/Native/调用/检查差分及原始终止状态。UNKNOWN不当INFEASIBLE；不完整端点不假造零消耗。
5. 原九项及十二项严格比较分开，仅当前执行、同Handoff/V2/Authority可比较。历史R9 P04不导入正式前沿或Hint；不把31mm刚性东移上界当固定新约束，不预设整体东移。
6. 原Work标签和未归类差额保留；R10标签独立列组。没有“扣掉R9复制费等于必然节省”的推断。Truck/P2D未经独立实证仍未通过。

## 验证与证据

新测试使用临时合成登记簿，两个CP-SAT Solve API始终拒绝。覆盖Scope/Hash/策略变更、旧授权/复制旧Grant、来源及预算篡改、缺Grant、未知锁/账本、单次消费、六Handoff共享额度、批量Work拒绝、原累计保护、真实PR/Base/完整CI/RSS和运行前后身份核查；全链失败不创建Claim。

另外从原`server_inputs()`绑定封存20t，实际构造六个完整Handoff的Reference模型与原面积定义，11条非货车Access身份覆盖、原P1/Site一致，均通过模型语法校验，Native为0。该测试不是工程可行性或首个布局证明。原R10 R2独立工程合成验收与新导出投影回归保持。

本地接线案例99项在分批回归中覆盖，原R10 R2 23项、旧累计保护/首次基线13项通过；架构771通过/16原有skip，CI契约65通过。初始两个测试Fixture装配错误和一次新Runner最终Host回读遗漏的失败记录保留；补齐后接线97项重新全通过，新增导出/UNKNOWN回归另验证。静态检查覆盖backend全量Ruff/Format、src全部462文件及新Runner；新Runner类型检查使用follow-imports=silent，避免将未改的历史R6脚本隐式导出诊断混为本轮变更。

本地原始记录位于`artifacts/stage-b-r10-r2-main-preparation-r1/`，包含JUnit、CI契约、源文件/Scope/输入绑定及历史保全回读。自动快速CI针对最终HEAD读取，运行中不得填SUCCESS。正式ci.yml没有改动，也不操作ci-full-request标签。

## 下一阶段命令（本轮不执行）

只有后续取得精确最终HEAD的正式CI、Owner确认，且原可信管理员独立签发合法Grant后，才允许一次：

```sh
cd backend
PYTHONPATH=src:scripts uv run python scripts/run_stage_b_r10_r2_main.py \
  --owner-instruction ../docs/tasks/V2_2_2-stage-b-r10-r2-owner-scope.txt \
  --output ../artifacts/stage-b-r10-r2-real-main-r1
```

输出目录必须不存在。无Grant、已有Claim/锁/历史、来源或CI不一致均停止，不自动修复、清理、重试或恢复。完成本轮后STOP，不自动触发正式CI、签发真实Grant或运行MAIN。
