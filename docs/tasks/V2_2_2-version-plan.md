# V2.2.2 版本开发总计划 — Owner 审核草案

> **最新进度导航（2026-10-15）：见[第12节 R1–R15 对账](#r1-r15-current-reconciliation)。** 第1–11节及其授权/CI/“当前”字段是2026-10-09审查历史，原文保留；后续状态以第12节具名证据及适用范围补充，不倒改历史。MCP八工具上线不代表v2.2.2完成。

> **DRAFT / NOT FROZEN / DOCUMENTATION ONLY。** 本文是对既有合同、任务和证据的对账，不替代或修改原始权威合同，不授权任何实施。待 Owner 审核后，文档提交、计划冻结及后续任务分别授权。

```ini
TASK_ID=V2_2_2_VERSION_MASTER_PLAN_RECONCILIATION_R1
MODE=DOCUMENTATION_ONLY_OWNER_REVIEW
OWNER_REVIEW_CORRECTION_TASK_ID=V2_2_2_VERSION_MASTER_PLAN_OWNER_REVIEW_CORRECTION_R1
OWNER_REVIEW_CORRECTION_MODE=DOCUMENTATION_ONLY_REVISION
OWNER_REVIEW_FRAMEWORK_STATUS=CONDITIONALLY_ACCEPTED_NOT_FROZEN
DECISION_ALIGNMENT_TASK_ID=V2_2_2_OWNER_DECISION_ALIGNMENT_D01_D03_D04_R1
DECISION_ALIGNMENT_MODE=DOCUMENTATION_ONLY_DECISION_ALIGNMENT
DECISION_ALIGNMENT_BASE_HEAD=f6b17fb6d34b637ea5887af1b420e5da5ef244c8
OWNER_DIRECTION_APPROVED=true
FORMAL_CONTRACT_AMENDMENT_AUTHORIZED=false
REVIEW_BASE_HEAD=183229a3a1251cd32eed45f73d9073b1d739143e
BASE_MAIN_SHA=a0ef560de778770e4c26c4d027a239afe78eeadd
BRANCH=codex/v2.2.2-p1a-structural-hard-interface-reservation-p0
PR_NUMBER=307
PR_STATE=OPEN_DRAFT
PLAN_STATUS=OWNER_REVIEW_DRAFT_NOT_FROZEN
STRUCTURED_P2D_FULL_PASS_CANDIDATE_COUNT_TARGET=5
MAJOR_LAYOUT_FAMILY_TARGET=3
MAX_RECOVERY_ROUNDS_PER_ARCHITECTURE=2
ACCEPTED_PARTIAL_WITH_UNKNOWN_COUNT_TARGET=0
P3_COMPLETE=false
R6A_IMPLEMENTATION_AUTHORIZED=false
NEXT_PHASE_AUTHORIZED=false
COMMIT_AUTHORIZED_BY_THIS_TASK=false
PUSH_AUTHORIZED_BY_THIS_TASK=false
NO_STEP_IMPLIES_THE_NEXT=true
```

审查日期：2026-10-09（Asia/Shanghai）。实施环境仅为健康独立 clone `/Users/charles/codex-r3-isolated.m45h1H/repo`；原工作区及其锁不属于本轮。本文中的“完成”必须带阶段/证据范围，不能等同于 merged、版本验收或发布。

## 1. 权威顺序与审查来源

1. Owner 当前明确授权决定可执行范围；本轮仅允许这份新草案和仓库外只读分析证据。
2. 原始产品/质量合同与后续正式架构合同保持原文。合同差异列入待裁决项，本文不能消除差异或降低门槛。
3. exact SHA 的任务/evidence、GitHub terminal 状态用于认定实际进度。早期 `CURRENT`、`PENDING`、`AUTHORIZED=false` 字段是各阶段快照，不能遮盖后续单独授权和真实终态。
4. CI、机制实现、候选构造、工程验证、质量验收、Owner 视觉审核、Ready/Merge、发布是独立信号。

必读来源已逐项交叉核对：

| 引用 | 权威资料 | 本次用途 |
|---|---|---|
| C01 | [V2_2-version-plan.md](V2_2-version-plan.md) | v2.2.0/v2.2.1 历史链与 v2.2.2 P0、reset S1–S4；不是本分支当前进度总账 |
| C02 | [V2.2.2 P0](V2_2_2-P0-process-flow-layout-regularity-contract.md) | 产品质量、原子指标、工程/质量分层、原始验收要求 |
| C03 | [P0A](V2_2_2-P0A-canonical-fixture-regularity-calibration.md) | 真实 Xinzhao fixture、v2.2.1 hard-pass/Owner regularity-fail 历史 |
| C04 | [P0B](V2_2_2-P0B-owner-positive-layout-reference-set.md) | 五份 Owner-positive PDF、定性规则、数值不可推断 |
| C05 | [P0C](V2_2_2-P0C-golden-layout-abstraction-and-calibration.md) | 五份 overlay Owner PASS；结构入口与 numeric calibration 分离 |
| C06 | [P1A reset contract](V2_2_2-P1A-architecture-reset-whole-building-composition-contract.md) | whole-building architecture、12-role coverage、5/3交付目标、两轮恢复停止规则 |
| C07 | [ADR-047](../architecture/ADR-047-process-flow-layout-regularity-authority.md) | 工艺/规整度质量权威与校准边界 |
| C08 | [ADR-049](../architecture/ADR-049-whole-building-group-band-composition.md) | B/C hybrid、结构多样性、Owner 视觉门禁 |
| C09 | [ADR-050](../architecture/ADR-050-structural-hard-interface-projection.md) | P0/P1/P2/R1/P3/R2/R3/R4 的证明语义和历史 supersession |

同时审查 PR [#302](https://github.com/xuezhiorange-png/cold-storage-planning-agent/pull/302)、[#306](https://github.com/xuezhiorange-png/cold-storage-planning-agent/pull/306)、[#307](https://github.com/xuezhiorange-png/cold-storage-planning-agent/pull/307) 的 live metadata、commit 列表、body/terminal 记录，以及下表对应 evidence。历史 PR 不是新实现的代码来源。

## 2. 产品目标和交付边界：不降为“12 个矩形”

V2.2.2 的目标是**工程有效且一眼能读懂的完整加工工厂组织**：

- 主工艺路径清晰、方向正确，Sorting/Packaging 是明确核心；原料、预冷、加工、成品、Shipping 连续。
- 冷间、包材、次果、冻果有明确功能分组和主/支流层级；不把支流伪造为新增 MUST。
- Office、Changing 保持人员组/人员域，与生产物流合理分离；Office↔Shipping 的空间 HARD interface 不改变 functional ownership，也不自动授权人员 portal。
- 主要轴网、兼容房间进深和主体轮廓协调；真实不规则场地、障碍和有目的的 L/翼部不为“矩形美观”让步。
- 交付至少 **5 个 distinct structured P2D full-pass 候选**，覆盖至少 **3 类实质不同的主要布局结构**。家族词汇、rotation/mirror、微小平移、hash/provenance 变化、尾部置换都不能替代有效方案多样性。
- 先工程 hard validation，再工艺/规整度原子评价和质量排序，最后同尺度方案图与 Owner 视觉审核；再独立进行 Tool 7 集成和版本发布验收。

Golden/PDF 是定性组织参考，不是尺寸、坐标、runtime seed 或工程权威。输出始终为概念规划与设计辅助，不是施工图，不替代专业工程审查、不控制现场设备。

5个full-pass与3类主要结构必须来自可追溯的真实工程验证结果：每个计入候选须能关联输入/场地权威、实际几何及其identity、生成版本、逐项Access/Truck/P2D结果和验证版本；主要结构分类须对应这些已验证候选的实质组织差异。重复几何、仅坐标微调、镜像/旋转或topology标签不能补足数量。计数和结构去重证据均须接受审核，当前尚未达成该版本门槛。

## 3. 编号与状态治理

### 3.1 必须区分的编号空间

| 编号空间 | 含义 | 不可混同 |
|---|---|---|
| `V2_2_P0…P5` | v2.2.0 历史：合同、dimension、placement/P2D、SVG、Tool7、release | 不能把其历史 P3 SVG PASS 算作当前 P1A/P3 capacity PASS |
| `V2_2_1_*` | 已有 drawing/style/lint/release 历史 | 不证明新结构候选质量或工程 full-pass |
| `V2_2_2_P0/P0A/P0B/P0C` | 产品/参考/校准准备 | overlay PASS 不等于新方案视觉 PASS |
| `V2_2_2_P1A_*_P1_S1…S4` | whole-building 正式实施切片 | S1 topology/S3 hard subset 不等于 P1A 或版本完成 |
| `V2_2_2_P1A_STRUCTURAL_*_P0/P1`、metric `P2/P3` | P1A 内 HARD-interface 子链 | 子链 P2 PASS 不等于工程 `P2_COMPLETE=true` |
| `CRn` / `Rn` | correction/recovery 或诊断任务，须按真实 scope 分类 | 字母/数字不是新版本阶段，也不自动重置 architecture round counter |
| R4 文档内部 P0…P4 | 一轮任务内部步骤 | 不代表正式项目 P4 已授权 |
| 下表 `REVIEW-*` | 本草案建议工作包、非正式 TASK_ID | Owner 必须确认正式编号/依赖/验收并单独授权 |

现有权威文件没有为全部未来 v2.2.2 交付工作冻结一套完整 TASK_ID。本文不借用 v2.2.0 的 P2/P3/P4/P5 编号，也不擅自宣布 `P1-S5` 或 `R6A` 已获授权。完整性仅指“现有已知任务和已识别剩余工作包完成盘点”，不声称覆盖所有未知未来任务。未来正式TASK_ID、范围、依赖及验收尚待批准，不能提前称为冻结完成。

### 3.2 状态词

`COMPLETE_IN_SCOPE`=指定切片已完成，不蕴含后续；`PARTIAL`=已有产物但验收缺口保留；`FAIL_HISTORICAL`=历史失败保留；`DIAGNOSIS_COMPLETE`=诊断结论，不是业务成功；`BLOCKED`=列明真实依赖；`NOT_AUTHORIZED`=不能实施；`OWNER_REVIEW_DRAFT`=可审稿、未冻结。

### 3.3 Recovery stop rule 原样保留

`MAX_RECOVERY_ROUNDS_PER_ARCHITECTURE=2`：C06/C08 明确为同一 architecture 主实现后的最多两轮 bounded correction；届时仍无 structured 12-zone candidate 则 `ARCHITECTURE_REVIEW_REQUIRED`。没有候选和有一个候选但未满足质量/证明要求是不同失败条件，后者也不自动授权无限迭代。

历史 #302 的多轮恢复、#306 CR1–CR7、#307 P3/R2/R3/R4 必须进 architecture/authorization ledger；不能按 commit 数、改名或新建子步骤重新计数。RCA/R5、Git 环境诊断/隔离交付不是新的布局恢复实现。R3/R4 有明确 Owner 单独授权，不据轮号单独断言其越权；现有证据不足以证明统一 round ledger 已冻结，也不能给出“恢复额度自动重置”的结论。D04 要求 Owner 核定历史架构边界、例外授权和下一轮可执行范围；本轮不会修订停止规则。#306 CR8、#307 R6A 均不得自行启动。

## 4. 版本任务总表

各行均记录九个必需字段。`E*` 为第5节可定位证据，`D*` 为第8节 Owner 决策。长 TASK_ID 换行显示不改变其正式身份。

### 4.1 原始合同、准备与 whole-building 实施

| TASK_ID | OBJECTIVE | DEPENDENCIES | DELIVERABLES | ACCEPTANCE_GATES | CURRENT_STATUS | EVIDENCE_REFERENCE | BLOCKERS | OWNER_AUTHORIZATION |
|---|---|---|---|---|---|---|---|---|
| `V2_2_2_P0_PROCESS_FLOW_AND_LAYOUT_REGULARITY_CONTRACT_R1` | 冻结工艺/规整度产品合同 | v2.2.1 技术有效但视觉不合格 | C02/C07、原子指标与权威边界 | hard/quality 分层、route事实、不得猜阈值 | COMPLETE_IN_SCOPE：合同存在；不是质量runtime完成 | C01–C03、C07 | numeric calibration、D02/D03 | 历史合同授权；本轮不得修改 |
| `V2_2_2_P0A_XINZHAO_CANONICAL_FIXTURE_INGEST_AND_REPLAY_R2` | 获得真实 canonical 输入及历史对照 | 原始Owner bytes、v2.2.1 runtime | fixture、replay、calibration matrix | raw hash、12/12 Access、Truck及历史hash复现 | COMPLETE_IN_SCOPE；numeric校准未完成 | E01 | 正例room/route精度不足 | 历史evidence授权；不是runtime授权 |
| `V2_2_2_P0B_OWNER_POSITIVE_LAYOUT_REFERENCE_SET_R1` | 五份正例定性组织依据 | Owner PDF原件 | source hashes、五正一负比较 | 来源可核对、定性/工程值分离 | COMPLETE_IN_SCOPE | E02 | PDFs不提供权威route/room metrics | 历史参考分析授权 |
| `V2_2_2_P0C_GOLDEN_LAYOUT_ABSTRACTION_AND_CALIBRATION_R1` | Golden抽象、overlay、校准入口分拆 | P0A/P0B | 五overlay、classifier词汇、depth-pair policy | Owner五份overlay PASS；不冒充numeric ready | COMPLETE_IN_SCOPE视觉抽象；numeric BLOCKED | E03/C05 | comparable exact正例geometry、depth/outline/purpose | 历史evidence授权；P1B阈值实施未授权 |
| `V2_2_2_P1A_ARCHITECTURE_RESET_P0_WHOLE_BUILDING_COMPOSITION_CONTRACT_R1` | 从失败tail架构回归整体工厂 | #302 terminal FAIL、P0C | C06/C08：B/C hybrid、5/3、两轮stop | 12roles完整分配；不得继承旧recovery | COMPLETE_IN_SCOPE合同；不是整架构完成 | E04/C06/C08 | 后续runtime与全链业务验证 | 历史合同授权；本轮不改 |
| `V2_2_2_P1A_WHOLE_BUILDING_COMPOSITION_P1_S1` | 全组/带/域结构生成 | reset合同、canonical roles | 3families、6plans、12-role assignments | family-first、全角色域、非工程权威 | COMPLETE_IN_SCOPE | E05 | topology不等于有效候选 | 历史单独实施授权 |
| `V2_2_2_P1A_WHOLE_BUILDING_COMPOSITION_P1_S2` | site/dimension authority绑定及handoff | S1、ValidatedSite、dimension refs | 6 coordinate-free handoffs、server replay | 角色/组/域覆盖、provenance、防caller注入 | COMPLETE_IN_SCOPE | E06 | 不计算几何可行性 | 历史单独实施授权 |
| `V2_2_2_P1A_WHOLE_BUILDING_COMPOSITION_P1_S3` | composition-native exact MVP | S2、工程谓词 | bounded exact constructor、canonical replay | 60000节点；site/dimensions/nonoverlap/MUST/intent | FAIL_HISTORICAL主尝试0候选；由下行CR1补充 | E07 | 主尝试未成12区；不抹去失败 | 历史主尝试授权 |
| `V2_2_2_P1A_WHOLE_BUILDING_COMPOSITION_P1_S3_CR1` | bounded anchor修正恢复MVP | S3主尝试 | 1个LINEAR完整候选 | hard subset、determinism、预算不增 | COMPLETE_IN_SCOPE S3-MVP；不是P2D full-pass | E08 | 单家族单几何、Access未过 | 历史CR1授权；不授权CR2 |
| `V2_2_2_P1A_COMPOSITION_NATIVE_HARD_VALIDATION_P1_S4` | 真实候选接既有工程链 | S3候选、project truck输入 | hash-only server replay、原样Access/Truck/P2D结果 | 不修几何、不弱化authority；记录所有12需求 | bridge COMPLETE_IN_SCOPE；候选 FAIL_ACCESS | E09 | Access7/12、Truck失败、footprint/P2未完成 | 历史S4授权；非后续优化授权 |

### 4.2 冻结诊断分支 #306

以下全部是 S4 correction/diagnostic 历史，不是新增正式版本阶段。共同依赖 S4 和各前轮，交付为构造机制/回放/根因证据；共同验收要求保持工程authority/60000 placement/20000 Access/20000 Truck不变，业务目标是完整候选及non-Truck改善，不能以CI替代。逐行细节仍以 SHA-pinned E10 为准。

| TASK_ID | OBJECTIVE | DEPENDENCIES | DELIVERABLES | ACCEPTANCE_GATES | CURRENT_STATUS | EVIDENCE_REFERENCE | BLOCKERS | OWNER_AUTHORIZATION |
|---|---|---|---|---|---|---|---|---|
| `V2_2_2_P1A_COMPOSITION_NATIVE_HARD_VALIDATION_P1_S4_CR1` | access-critical construction | S4 | 非权威interface intents | 完整候选+non-Truck>7/11 | FAIL_HISTORICAL：候选退化为0 | E10/CR1 | 无可验证新候选 | 历史Owner task；现在冻结 |
| `V2_2_2_P1A_COMPOSITION_NATIVE_HARD_VALIDATION_P1_S4_CR2` | 恢复order/lane及验证阶段覆盖 | CR1 | 两lane、non-Truck先行 | Truck不得提前阻断完整候选 | FAIL_HISTORICAL：仍0候选 | E10/CR2 | 构造未闭环 | 历史Owner task；现在冻结 |
| `V2_2_2_P1A_COMPOSITION_NATIVE_HARD_VALIDATION_P1_S4_CR3` | optimistic主链forward check | CR1–2 | 有界positive/negative/UNKNOWN | 只有exhaustive negative剪枝 | FAIL_HISTORICAL：witness未被primary利用 | E10/CR3 | 构造回放缺口 | 历史Owner task；现在冻结 |
| `V2_2_2_P1A_COMPOSITION_NATIVE_HARD_VALIDATION_P1_S4_CR4` | witness replay/inheritance | CR1–3 | 非硬锁witness机制 | hard复验、fallback、真实消费 | FAIL_HISTORICAL：无新完整候选 | E10/CR4 | known lane未恢复witness消费 | 历史Owner task；现在冻结 |
| `V2_2_2_P1A_COMPOSITION_NATIVE_HARD_VALIDATION_P1_S4_CR5` | composition意图传播 | CR1–4 | projection propagation、funnel | 保守传播、witness gate | FAIL_HISTORICAL；已排除late-intent为主瓶颈 | E10/CR5 | physical domain及未展开；全aggregate曾未完成 | 历史Owner task；现在冻结 |
| `V2_2_2_P1A_COMPOSITION_NATIVE_HARD_VALIDATION_P1_S4_CR6` | mandatory successor容量 | CR1–5 | successor finite domain/证据 | 主search等价域、UNKNOWN不剪 | FAIL_HISTORICAL：0候选 | E10/CR6 | Finished physical容量 | 历史Owner task；现在冻结 |
| `V2_2_2_P1A_COMPOSITION_NATIVE_HARD_VALIDATION_P1_S4_CR7` | exact successor free-space与归因 | CR1–6 | 13attempts×2、blocker closure | 完整归因+control+determinism+CI | DIAGNOSIS_COMPLETE；业务FAIL，0候选 | E10/CR7 | known lane11/12，Office失败 | 历史Owner task；CR8未授权 |
| `V2_2_2_P1A_S4_POST_CR7_SHIPPING_OFFICE_ZERO_MODIFICATION_AUDIT` | 审计全部11个Shipping的Office容量 | CR7实际parent/domain | 11/11均0附件的诊断结论 | hard subset、完整survivor集合、零修改 | DIAGNOSIS_COMPLETE；非global无解 | E11/C09 | structural跨组interface缺失 | 历史只读授权；不得移植runtime |

### 4.3 当前 #307：HARD-interface 子链与证明演进

| TASK_ID | OBJECTIVE | DEPENDENCIES | DELIVERABLES | ACCEPTANCE_GATES | CURRENT_STATUS | EVIDENCE_REFERENCE | BLOCKERS | OWNER_AUTHORIZATION |
|---|---|---|---|---|---|---|---|---|
| `V2_2_2_P1A_STRUCTURAL_HARD_INTERFACE_RESERVATION_P0` | 每条HARD边在结构层可见 | clean main、#306诊断 | 7typed interfaces/plan/handoff | 7/7、4intra/3cross、ownership/coordinate-free | COMPLETE_IN_SCOPE；不是容量证明 | E11/C09 | 后续reservation实现 | 历史P0授权 |
| `V2_2_2_P1A_STRUCTURAL_HARD_INTERFACE_RESERVATION_P1` | topology attachment slot/gate | 子P0 | 6×7reservations+assessments | 1:1、真实hosts、6topological gates PASS | COMPLETE_IN_SCOPE | E12/C09 | topology非metric footprint | 历史P1授权 |
| `V2_2_2_P1A_METRIC_INTERFACE_RESERVATION_REALIZATION_P2` | pairwise site/dimension metric域 | 子P1、ValidatedSite、shapes | 42realizations、7unique完整域 | 42NONEMPTY、6gates、完整hard obstacles、parity | COMPLETE_IN_SCOPE pairwise有限域 | E13 | 不证明其他房间/联合/全布局 | 历史P2授权 |
| `V2_2_2_P1A_EXACT_PLACEMENT_HARD_OBSTACLE_AUTHORITY_PARITY_R1` | exact/P2 obstacle authority对齐 | P2识别gap | shared fail-closed parser、retained/conditional tests | full hard obstacles、shape/canonical parity、CI | COMPLETE_IN_SCOPE；早期失败保留 | E14 | 不实现reservation消费 | 历史R1授权；不新授权P3 |
| `V2_2_2_P1A_METRIC_RESERVATION_CONSUMPTION_P3` | dynamic partial保护static metric支持 | 子P2/R1 | runtime domain/support lifecycle | 完整候选≥1、7consumed、regressions/CI | FAIL_HISTORICAL：0候选、CI失败 | E15 | static域排他性错配 | 历史P3主尝试；R2已正式修订该排他契约 |
| `V2_2_2_P1A_P3_FINITE_DOMAIN_EXCLUSION_RCA_R1` | 独立检查static/exact覆盖 | P3失败、真实START control | 0/7static membership根因审计 | 区分finite枚举与几何覆盖 | DIAGNOSIS_COMPLETE；非实现轮 | C09、E15/E16 | 静态域不能覆盖动态合法geometry | 历史只读授权 |
| `V2_2_2_P1A_P3_CONDITIONAL_METRIC_SUPPORT_R2` | fixed-endpoint条件化证书 | RCA、原hard authorities | dynamic/static-positive/direct-final | sound NONE、UNKNOWN不剪、完整候选+7direct | PARTIAL：1候选、213accepted pairwise UNKNOWN | E16 | 共享未放置角色联合未证 | 历史R2实施授权；不是P3完成 |
| `V2_2_2_P1A_P3_JOINT_METRIC_CAPACITY_PROOF_R3` | 统一共享角色、connected-component证书 | R2 | joint query/certificate、逐层proof ledger | 共同geometry、零accepted UNKNOWN、候选及CI | PARTIAL：1候选、265joint UNKNOWN/317 | E17 | 275query UNKNOWN，joint proof未闭环 | 历史R3授权；不可冒充正式新阶段 |
| `V2_2_2_P1A_P3_JOINT_UNKNOWN_PROOF_CLOSURE_R4` | 同caps下联合证明收敛 | R3 | propagation、exact复验、两次回放 | 60000/256/1024不变；零UNKNOWN强验收 | PARTIAL：55SUPPORTED、262UNKNOWN/317 | E18 | 192zero-check、75caps、成本上升 | 历史R4授权；未授权R6A |
| `V2_2_2_P1A_P3_PROOF_COVERAGE_RCA_R5` | 独立根因/覆盖/验收边界审计 | R4实际trace | 272明细、独立小穷举/192empty covers、报告 | 只读、分scope、不修改负证明/验收 | DIAGNOSIS_COMPLETE；P3仍PARTIAL | E19 | 80queries未定；D01/D04 | 已完成只读授权；非R5修复轮 |

Git lock/process诊断、P0 duplicate只读审计/隔离、R2已有commit交付、R3 isolated checkout recovery 是环境/交付任务，不是版本功能阶段或新容量证明。它们保留在原任务/PR记录，不折算候选数量、proof coverage 或 recovery额度。本轮不检查/处理原工作区锁或旧隔离目录。

### 4.4 未交付工作包：建议顺序，不是实施授权

| TASK_ID | OBJECTIVE | DEPENDENCIES | DELIVERABLES | ACCEPTANCE_GATES | CURRENT_STATUS | EVIDENCE_REFERENCE | BLOCKERS | OWNER_AUTHORIZATION |
|---|---|---|---|---|---|---|---|---|
| `V2_2_2_VERSION_MASTER_PLAN_RECONCILIATION_R1` | 统一版本总账供审核 | C01–C09、E04/E10–E19 | 本草案、差异/决策表 | 原目标/门槛保留、进度可追溯、无代码改动 | OWNER_REVIEW_DRAFT | 本文、仓库外source manifest | Owner审稿/正式冻结 | 本轮仅创建草案；commit/push未授权 |
| `REVIEW-SAFETY-CONTRACT`（正式ID待批准） | 决定P3安全门禁与joint强验收关系 | R5、D01/D04 | 经Owner批准的scope/invariant/round ledger | 不弱化authority、不UNKNOWN冒PASS；原强门槛批准前有效 | BLOCKED_OWNER_DECISION | C09/E19 | 未批准契约方向 | NOT_AUTHORIZED；R6A=false |
| `REVIEW-MULTI-CANDIDATE`（正式ID待批准） | 恢复多种完整规整候选构造 | 安全合同、architecture stop决策 | 完整12区候选集、真实结构/geometry distinctness | hard subset、bounded determinism、3类有效结构的可验证覆盖 | PARTIAL基础；新实施NOT_AUTHORIZED | E05/E08/E18、C06 | 现仅1geometry；P3不完整 | NOT_AUTHORIZED；不得靠改order/budget开始 |
| `REVIEW-HARD-VALIDATION`（正式ID待批准） | 对新结构候选真实Access/Truck/P2D | 可回放完整候选、project-bound inputs | 每候选12Access、Truck、interaction、footprint/P2D | 至少5distinct structured full-pass；无repair/bypass | NOT_COMPLETE；可行性基线未证 | E09是历史失败，不是当前候选结论 | 新候选无standalone全链证明；P3/phase决策 | NOT_AUTHORIZED |
| `REVIEW-NUMERIC-CALIBRATION`（P1B入口；正式实施ID待批准） | 补可比较正例指标和阈值证据 | P0C、Owner结构化正例、D02/D03 | room-level depth/outline、purpose、label、版本阈值提案 | comparable granularity、不可用不当PASS、Owner批准 | BLOCKED_NUMERIC_CALIBRATION | C02–C05/C07 | exact正例room/footprint/route与appendage purpose不足 | NOT_AUTHORIZED；可规划并行取证，不能自行做 |
| `REVIEW-QUALITY-ASSESSMENT`（正式ID待批准） | route工艺与规整度评价 | 完整hard-valid候选、route事实、metric contract | 原子quality sidecar、source/version/unavailable | P0所有硬质量门槛；numeric缺失fail-closed | NOT_COMPLETE | C02/C07 | route映射、numeric calibration、D02/D03 | NOT_AUTHORIZED |
| `REVIEW-QUALITY-RANKING`（正式ID待批准） | full-pass后的字典序排名与多方案比较 | 工程full-pass集合、质量事实 | winner-vs-next、结构distinctness说明 | P0质量优先序、保留P2B2末级tie-break；无weighted抵消 | NOT_COMPLETE | C02/C06/C07 | 无5full-pass与已验收质量事实 | NOT_AUTHORIZED；不改selector |
| `REVIEW-OWNER-GALLERY`（正式ID待批准） | 同尺度方案图与Owner审核 | 5full-pass、3实质结构、质量说明 | 统一canvas/scale/orientation的图集、Owner签认 | 12区/场地/障碍/组带/流向/支路/人员/Shipping齐全 | NOT_COMPLETE | C06/C08；P0C overlay不抵扣 | 当前有效多方案不足 | NOT_AUTHORIZED；非renderer redesign授权 |
| `REVIEW-TOOL7-INTEGRATION`（正式ID待批准） | 新结构/评价链独立接Tool7 | 上游工程/质量/Owner门禁完成 | server-owned integration、schema兼容、真实调用证据 | 原六工具/7号工具合同、无caller geometry、真实全链 | NOT_COMPLETE_FOR_V222 | C01历史Tool7能力不可替代 | 上游未完成；public sidecar contract待审 | NOT_AUTHORIZED |
| `REVIEW-VERSION-ACCEPTANCE-RELEASE`（正式ID待批准） | 版本验收及独立release决策 | 上述全部、exact-head CI、Owner | closure matrix、release notes、冻结目标SHA | 5/3、工艺/规整/视觉/集成均通过；发布动作单独授权 | NOT_COMPLETE | C02/C06，旧版closure只作模板参考 | 全部未闭环门禁 | NOT_AUTHORIZED；Ready/Merge/Tag/Release/Deploy=false |

## 5. PR、SHA 与 evidence 对照

| 引用 | 证据/任务 | 当前可证明范围 |
|---|---|---|
| E01 | [P0A matrix](evidence/v2_2_2_p0a/regularity-calibration-matrix.json)；C03 | 原始fixture已获得；v2.2.1历史Access12/12、Truck/P2通过但Owner规整度FAIL |
| E02 | [P0B matrix](evidence/v2_2_2_p0b/owner-layout-reference-matrix.json)；C04 | 5份正例reference来源与定性分析，不是5个新工程候选 |
| E03 | [P0C evidence目录](evidence/v2_2_2_p0c/)；C05 | 五overlay Owner PASS；numeric NOT_READY |
| E04 | PR302 head `0de6161ff46a100c05441e1910889c7b1854dcff`；C06/C08；[terminal PR](https://github.com/xuezhiorange-png/cold-storage-planning-agent/pull/302) | CLOSED_UNMERGED、44commits/323files历史；0structured12区/0structuredP2D；保留legacy control不算新结构成功 |
| E05 | [S1 task](V2_2_2-P1A-whole-building-composition-P1-S1.md)；[6plans](evidence/v2_2_2_p1a_reset_s1/xinzhao_whole_building_compositions.json) | 3topology families/6plans |
| E06 | [S2 task](V2_2_2-P1A-whole-building-composition-P1-S2.md)；[handoffs](evidence/v2_2_2_p1a_reset_s2/xinzhao_composition_authority_binding.json) | 6server-bound coordinate-free handoffs |
| E07 | [S3 task](V2_2_2-P1A-whole-building-composition-P1-S3.md)；[主尝试](evidence/v2_2_2_p1a_reset_s3/xinzhao_composition_exact_placements.json) | 主尝试FAIL，0候选 |
| E08 | [S3 CR1 evidence](evidence/v2_2_2_p1a_reset_s3/xinzhao_composition_exact_placements_cr1.json) | 1个hard-subset候选，50621nodes；非P2D通过 |
| E09 | [S4 task](V2_2_2-P1A-composition-native-hard-validation-P1-S4.md)；[12条Access/Truck/P2D](evidence/v2_2_2_p1a_reset_s4/xinzhao_composition_candidate_hard_validation.json) | 历史control `sha256:4a4b8f6695526ea0bd1cf30238ae4c7c45b35e6d9677b0c4bd8f98228e8f3c47`：Access7/12、nonTruck7/11、Truck失败 |
| E10 | [PR306记录](https://github.com/xuezhiorange-png/cold-storage-planning-agent/pull/306)；[CR7 task at frozen SHA](https://github.com/xuezhiorange-png/cold-storage-planning-agent/blob/4823fae99958eefddd32dc0afe42b729df00f415/docs/tasks/V2_2_2-P1A-composition-native-hard-validation-P1-S4-CR7.md)；[CR7 evidence](https://github.com/xuezhiorange-png/cold-storage-planning-agent/blob/4823fae99958eefddd32dc0afe42b729df00f415/docs/tasks/evidence/v2_2_2_p1a_s4_cr7/xinzhao_exact_successor_free_space_and_physical_blocker_attribution.json) | OPEN_DRAFT冻结HEAD；13attempts、55964nodes、0候选；LINEAR11/12。CR1–CR6逐SHA/task/evidence链接保留在PR，不复制runtime |
| E11 | [子P0 task](V2_2_2-P1A-structural-hard-interface-reservation-P0.md)；[contract JSON](evidence/v2_2_2_p1a_structural_hard_interface_reservation_p0/xinzhao_mandatory_hard_interface_contract.json) | #306后11/11 Shipping无Office附件的诊断引用；#307 P0七条投影。零修改audit原始明细未在本分支独立重跑，不伪称本轮新测 |
| E12 | [子P1 task](V2_2_2-P1A-structural-hard-interface-reservation-P1.md)；[gate JSON](evidence/v2_2_2_p1a_structural_hard_interface_reservation_p1/xinzhao_structural_interface_reservation_capacity_gate.json) | 42topological reservations/assessments；6gates |
| E13 | [子P2 task](V2_2_2-P1A-metric-interface-reservation-realization-P2.md)；[metric JSON](evidence/v2_2_2_p1a_metric_interface_reservation_p2/xinzhao_metric_interface_reservation_realization.json) | 42NONEMPTY、6gates、7unique static domains；不含其余房间 |
| E14 | [R1 task](V2_2_2-P1A-exact-placement-hard-obstacle-authority-parity-R1.md)；[parity JSON](evidence/v2_2_2_p1a_exact_placement_hard_obstacle_authority_parity_r1/hard_obstacle_authority_parity.json) | full hard-obstacle source parity；初始CI失败及最终修正均保留 |
| E15 | [P3 task](V2_2_2-P1A-metric-reservation-consumption-P3.md)；[failed evidence](evidence/v2_2_2_p1a_metric_reservation_consumption_p3/xinzhao_dynamic_metric_reservation_consumption.json) | `ff4626...`：0候选、6838nodes、12attempts、原回归/CI失败；不能称低节点为改善 |
| E16 | [R2 task](V2_2_2-P1A-P3-conditional-metric-support-R2.md)；[conditional evidence](evidence/v2_2_2_p1a_p3_conditional_metric_support_r2/xinzhao_conditional_metric_support.json) | `8c921b...`：1候选、7direct、213pairwise UNKNOWN；只修条件化覆盖契约 |
| E17 | [R3 task](V2_2_2-P1A-P3-joint-metric-capacity-proof-R3.md)；[joint evidence](evidence/v2_2_2_p1a_p3_joint_metric_capacity_proof_r3/xinzhao_joint_metric_capacity.json) | `9e5666...`：52/317joint SUPPORTED、265UNKNOWN |
| E18 | [R4 task](V2_2_2-P1A-P3-joint-unknown-proof-closure-R4.md)；[R4 query evidence](evidence/v2_2_2_p1a_p3_joint_unknown_proof_closure_r4/xinzhao_joint_unknown_proof_closure.json) | `183229...`：55/317joint SUPPORTED、262UNKNOWN、1候选；不是P3 PASS |
| E19 | R5仓库外报告 `/Users/charles/codex-r3-isolated.m45h1H/r5-audit.t1D5r2/R5-independent-audit.md`；同目录 `unknown_queries_272.csv`、`query_audit.json`、独立oracle JSON | LOCAL_ONLY_NOT_INDEPENDENTLY_ARCHIVED；本地报告结论DIAGNOSIS_CONFIRMED，192诊断empty covers、80queries unresolved；未提交、未独立归档，不冒充远端可用或已独立归档证据；后续归档必须独立授权 |

### 5.1 Live GitHub 核验与当前分支 lineage

本轮只读核验：origin指向指定repo；remote main=`a0ef560de778770e4c26c4d027a239afe78eeadd`。#302 CLOSED、unmerged、head `0de6161...`；#306 OPEN_DRAFT、head `4823fae...`；#307 OPEN_DRAFT、head `183229...`。未编辑任何PR。

#307现有9commits按子阶段为：P0 `aa955636...` → P1 `45766142...` → P2 `f4961f1f...` → R1初稿 `3147194d...` → R1最终修正 `112f3011...` → 原P3失败 `ff4626fc...` → R2 `8c921b0f...` → R3 `9e566603...` → R4 `183229a3...`。#306七个CRcommits为诊断历史，未被本任务或#307作为代码基线。

| 记录 | PR CI / Push CI | 解读 |
|---|---|---|
| #302 terminal `0de6161...` | 37220083027 / 37220079201，FAIL | R15 distinct full-pass skeleton 1 vs required≥2；该历史测试不是版本5/3目标的替代 |
| #306 CR7 `4823fae...` | 37488915814 / 37488909788，attempt1 SUCCESS | 机制测试成功、业务0候选FAIL，两者并列 |
| #307 原P3 `ff4626...` | 37646066543 / 37646058449，attempt1 FAIL | 0候选、原回归失败；保留，不被R2成功覆盖 |
| #307 R4 当前精确HEAD | 37785727500 / 37785718983，attempt1 SUCCESS | 本轮API确认completed/success/head183229；仍R4 PARTIAL/P3不完整 |

其他阶段CI及失败/rerun留在PR/任务历史，本草案不是删减后的CI成功清单。R1初稿失败、CR5 push attempt1失败/attempt2成功、observer/local失败不能擦除。标准CI的既有集成覆盖不等于独立新候选业务验收。本轮无测试/搜索/CI rerun。

## 6. 当前实际进度与尚未达到的最终门禁

| 事实/最终门禁 | 当前证据 | 尚缺什么 |
|---|---|---|
| 3类实质布局结构 | 3个topology families、6compositions已经存在 | 至少3类真实完整且full-pass的结构；不能拿schema标签充数 |
| ≥5 structured P2D full-pass候选 | 当前R4只有1个construction complete候选 | 新结构链尚无独立证明达到5；不得把已观察数写成5，也不把未运行写成5个失败 |
| 当前候选工程geometry | 12roles、最终7/7direct HARD-interface certificates | Access12需求、Truck、interaction、derived footprint、真实P2D全链 |
| 历史S4工程验证 | control Access7/12、Truck未通过、P2=false | 当前候选重新独立验收；旧7/12不是当前新测结果 |
| P3强验收 | accepted317，joint SUPPORTED55，UNKNOWN262；另root UNKNOWN10 | `ACCEPTED_PARTIAL_WITH_UNKNOWN_COUNT=0`仍有效但未达成；Owner若改契约须正式批准 |
| 工艺流线 | semantic/route指标合同存在 | actual route聚合、receiving映射、方向/回折/turn/支路crossing事实；不得用centroid代理 |
| 规整度 | qualitative正例、exact负例、classifier词汇 | 可比room-level numeric calibration和真实新候选评价 |
| 质量排序/多方案比较 | 原有P2B2 selector存在 | 新质量事实、hard-pass后排序、winner-vs-next、版本多样性验收 |
| Owner视觉 | P0C五reference overlays已PASS | 新候选同尺度gallery审核；不是参考图overlay复用 |
| Tool7 / version closure | 旧版本已有工具和投影 | 新结构候选/quality链单独集成和release closure，不从CI推断 |

当前candidate hash为 `sha256:554e77dd6e5b0da7bdecb97558bc4f16a8b1bd5c073ff18b080714a6462375ab`。R2证据明确：相对pre-P3 control，hash变化来自construction provenance，geometry未变；因此不能把新hash称为新增主要方案。

P2 metric public hash保持 `sha256:412a5ec8f51a84ceebddd4b663e89fe50a76d7cc8997c239b02dcb4c5dfc6677`；642482个unique pairwise slots/7domains、42realizations/6gates不是642482个完整布局。原权威7条MUST是主链6边+Office↔Shipping；不得因七个main-chain角色误写为主链7边再另加Office而变成8条。

### 6.1 原始质量验收不得丢失

按C02保留：`PROCESS_FLOW_ORDER_PASS`；verified `MAIN_FLOW_BACKTRACK_COUNT=0`；普通场地主流turn目标≤1（不规则场地例外需真实边界/障碍原因，不以search exhaustion豁免）；支路不跨主流；functional grouping；人员/物流路线分离事实；major-zone grid目标0.90；depth-pair policy；主建筑component目标1；compactness各原子事实；关键interface shared-edge/portal质量；实际route length与可比shortest route效率。

工程hard gate仍先行：site/full hard obstacles、权威dimensions、non-overlap、graph MUST、portals/Access、loading face/Truck、personnel-truck政策、derived footprint/P2D。`PROJECT_LAYOUT_VALIDATED`和工程`P2_COMPLETE`含义不变；`PROCESS_FLOW_VALIDATED`/`LAYOUT_REGULARITY_VALIDATED`另列。Required事实UNAVAILABLE不能变成0/PASS。

质量排序顺序原样保留：process order → backtrack → turns → required adjacency quality → grid → depth → compactness → route efficiency → side branches → personnel/logistics；其后保留P2B2 SHOULD/loading/canonical JSON tie-break。不引入weighted总分抵销硬失败。

## 7. P3三项责任与安全契约决策

| 层次 | 所证明内容 | 当前状态 | 不可推导 |
|---|---|---|---|
| A HARD-interface安全容量门禁 | 当前partial下可核验positive；有覆盖充分negative才prune；UNKNOWN明确保留 | 条件化机制已有，soundness验证有范围限制 | UNKNOWN不是正容量；有限事件未命中不是工程无解 |
| B Joint HARD component正证明 | 一个角色一份geometry、整个8-role/7-edge component共同满足几何/intent | R4仅55accepted获证书，262UNKNOWN | 七份独立pairwise不能合成B；B不含未来全部12roles |
| C 完整12区及工程可行性 | 全角色geometry，再由既有Access/Truck/P2D独立验证 | 1construction候选；新链full-pass未证明 | final7/7证书不等于C；CI不替代C |

R3 Owner明确授权提升B要求，不能称为未授权代码扩张；但产品路线已有“证明closure替代多方案业务交付”的偏移风险。原P3强验收**不删除、不作废**。本草案只提议Owner考虑将A安全剪枝、B正证明覆盖率分成不同阶段责任；批准前 `P3_COMPLETE=false`，不能以“有一个完整候选”倒推所有317个partial可完成。

现行 `ACCEPTED_PARTIAL_WITH_UNKNOWN_COUNT=0` 强验收继续有效；R3的265、R4的262 accepted joint UNKNOWN及其PARTIAL结果全部保留。A的安全剪枝正确性、B的联合正证明覆盖率、C的完整工程验证应分别报告，但“分别报告”不是已批准的责任拆分。只有Owner明确裁决并另行授权正式合同/ADR/测试修订后，才能确立不同于现行要求的新验收责任。本轮不能用建议口径宣布P3完成。

R5对272queries重新分类：192zero-check=174Finished空origin cover+18Coating/Finished无共享边pair；其余80queries（75cap+5nonzero-unproven）未定。空域依据相对canonical construction footprints/整数mm，不是所有flexible工程几何；独立小oracle零反例不等于独立穷举了538历史负结果。此诊断不能直接授权新negative路径或R6A。若保持B全覆盖目标，不能只改善sampling去正证明已确认空域的同一partial；必须有正式可校验negative或改变经授权构造路径，仍不得篡改UNKNOWN统计。

## 8. Owner待批准事项与停止条件

| 决策 | 问题/选项 | 建议审核输出 | 未批准前 | REVIEW_RECOMMENDATION | OWNER_DECISION_STATUS | IMPLEMENTATION_IMPACT |
|---|---|---|---|---|---|---|
| D01 P3职责/验收 | A=SAFE_CAPACITY_ADMISSION；B=JOINT_POSITIVE_COVERAGE；C=FULL_ENGINEERING_VALIDATION | 见8.3三层精确invariant、证明范围、UNKNOWN、测试和验收边界 | 现行零UNKNOWN强验收与历史PARTIAL保留，P3=false，R6A=false | 按Owner同意方向形成三层责任修订提案，不以C成功倒推全部partial具备B | DIRECTION_APPROVED_FORMAL_AMENDMENT_PENDING_OWNER | 方向批准不等于合同修订或实施授权；正式批准后才可按allowlist另行修订合同/ADR/测试 |
| D02 numeric calibration | room-level depth、exact正例outline、appendage purpose如何取得和标注 | 可比样本、eligibility/classifier版本、阈值提案与Owner批准 | numeric P1B BLOCKED，不能宣称规整度PASS | 先批准取证协议和可比粒度；depth0.80不冻结，occupancy/notch/appendage不猜值 | PENDING_OWNER | 取证、阈值冻结、runtime评价各需独立授权；当前不改数值门槛 |
| D03 原始合同差异 | 冲突一：P0的grid 0.90目标与ADR-047未校准numeric gate；冲突二：P0将secondary_precooling_room归FINISHED_SIDE_GROUP，P1A reset归PROCESSING_CORE_GROUP | 见8.4两项独立修订提案、历史兼容与迁移方案 | 两项实际权威冲突仍存在；不改原始合同、当前runtime分组或numeric gate | 保留0.90原始目标并单列gate校准状态；建议当前P1A继续PROCESSING_CORE_GROUP，历史P0口径版本化兼容 | DIRECTION_APPROVED_FORMAL_AMENDMENT_PENDING_OWNER | 实际合同文字、版本适用范围与迁移细则仍待正式批准；本轮无权威或runtime变更 |
| D04 round ledger/architecture stop | 各轮对应架构、主尝试、修正行为、Owner授权及原两轮限制归属，见8.1/8.5 | 对REQUIRES_OWNER_CLASSIFICATION逐项裁定并完成新布局实施前架构审核 | MAX=2保持；不根据改名/新子链自动重置；不补造历史豁免 | 按方向批准建立架构级账本，分主实现、布局修正、证明机制、诊断、环境恢复 | DIRECTION_APPROVED_FORMAL_AMENDMENT_PENDING_OWNER | 历史计数和例外未自动批准；架构审核完成且新任务另行授权后，才可开展新布局实施 |
| D05 正式版本剩余任务编号 | REVIEW-*工作包正式TASK_ID及依赖、交付、门槛 | Owner核定正式编号与逐任务scope | 仅完成现有已知任务和已识别剩余工作包盘点；future IDs未冻结 | 建议保留业务工作包映射后再分配正式ID，避免借旧版P3编号 | PENDING_OWNER | 编号批准不等于实施批准；后续仍需独立授权 |
| D06 下一次实施/验证顺序 | 区分已有候选工程诊断性复核、多结构候选生成实施、numeric calibration取证、最终业务验收，见8.2 | 分别确认输入、范围、依赖、证据性质及授权 | 四类工作均不因草案自动获授权；不触发Access/Truck/P2D或新layout | 建议将诊断与实施、取证与最终验收分开审批；独立可规划不等于可执行 | PENDING_OWNER | 诊断不能抵扣5/3最终门槛；生成、取证、验收均须各自批准，当前不执行 |
| D07 草案审核、提交、冻结 | 版本表框架有条件通过，但未授权冻结 | 正式批准修订草案，再单独授权doc commit/push/计划冻结 | 不commit/push、不改PR body；PLAN_STATUS保持草案 | 建议先审D01–D06，再明确冻结范围；不从本轮修订授权推断后续 | PENDING_OWNER | 本轮仅修改目标草案；发布/Ready/Merge等授权继续为false |

### 8.1 D04独立架构恢复轮次账本（未冻结）

本账本独立于4组38项任务表，不新增正式版本任务。架构名称用于标识证据中的实现谱系，不代表Owner已经批准新的计数边界。`REQUIRES_OWNER_CLASSIFICATION`表示原两轮限制归属、主尝试边界或例外尚不能据现有证据确定；不得据此断言越权、自动豁免或额度重置。历史授权证据引用不等于本轮重新授权。

| 轮次/记录 | 对应架构谱系 | 主尝试参照 | 实际修正/诊断行为 | Owner授权证据/可追溯性 | 是否属于原两轮限制/待裁定项 |
|---|---|---|---|---|---|
| #302既有主实现及多轮恢复（逐轮计数未核定） | 旧R2/tail-capacity生命周期 | E04 terminal及C06/C08否定的旧主实现；精确主尝试边界待核定 | 多轮tail/recovery，最终0structured12区；R15失败保留 | E04/PR302历史记录；不得仅凭commit列表补造每轮Owner授权 | REQUIRES_OWNER_CLASSIFICATION：需Owner补齐逐轮主尝试/授权映射；不能把44commits当44轮或已获豁免 |
| S3主尝试 | whole-building group/band composition | S3，E07 | composition-native exact MVP，0候选 | C06/C08及E07既有任务记录 | 主尝试，不作为修正轮；两轮规则的精确计数起点仍待Owner核定 |
| S3 CR1 | 同上 | S3主尝试 | anchor修正恢复1个hard-subset候选 | E08及S3任务中的CR1历史授权/结果 | REQUIRES_OWNER_CLASSIFICATION：是否计入该架构原两轮及后续S4是否同一计数链 |
| S4 bridge | 同上，工程桥接切片 | S3 MVP后S4，E09 | 接既有工程验证；不是新的布局恢复实现 | E09历史S4授权 | 工程桥接非恢复行为；不得据S4编号重置架构计数 |
| #306 CR1 | whole-building exact/access-aware构造修正谱系 | S4失败候选 | access-critical construction | Owner CR1任务；E10/CR1对应历史记录 | REQUIRES_OWNER_CLASSIFICATION：原两轮归属及例外未冻结 |
| #306 CR2 | 同上 | S4及CR1 | order/lane及验证阶段覆盖 | Owner CR2任务；E10/CR2 | REQUIRES_OWNER_CLASSIFICATION |
| #306 CR3 | 同上 | S4及CR1–2 | optimistic forward check | Owner CR3任务；E10/CR3 | REQUIRES_OWNER_CLASSIFICATION |
| #306 CR4 | 同上 | S4及CR1–3 | witness replay/inheritance | Owner CR4任务；E10/CR4 | REQUIRES_OWNER_CLASSIFICATION |
| #306 CR5 | 同上 | S4及CR1–4 | composition projection propagation | Owner CR5任务；E10/CR5 | REQUIRES_OWNER_CLASSIFICATION |
| #306 CR6 | 同上 | S4及CR1–5 | mandatory successor容量传播 | Owner CR6任务；E10/CR6 | REQUIRES_OWNER_CLASSIFICATION |
| #306 CR7 | 同上 | S4及CR1–6 | exact free-space实现及blocker诊断，业务0候选 | Owner CR7任务；E10 frozen SHA/task/evidence | REQUIRES_OWNER_CLASSIFICATION：含生产修正，不能仅因diagnostic closure而自动排除 |
| post-CR7 Shipping/Office audit | 冻结#306诊断 | CR7实际parent | 只读11个Shipping附件容量审计 | Owner零修改audit指令；E11引用，不冒充本轮新测 | 只读诊断，不是布局修正轮；不重置/续增额度 |
| #307 structural子P0/P1、metric P2 | clean-main HARD-interface重设计子链 | E11–E13；是否构成独立计数架构待Owner核定 | contract、topological reservation、pairwise metric realization | Owner明确clean-main P0及后续P1/P2授权；C09/E11–E13 | REQUIRES_OWNER_CLASSIFICATION：不能由新PR或子阶段名称自动重置原规则 |
| #307 R1 authority parity及最终修正 | 同上 | P2 authority gap | shared hard-obstacle parser及修正；不改变search算法 | Owner R1指令；E14及两次commit/失败历史 | REQUIRES_OWNER_CLASSIFICATION：authority remediation是否计入、两commit如何计轮待裁定 |
| #307 P3原主尝试 | conditional/reservation消费演进的前身 | E15，ff4626... | static finite-domain消费，0候选 | Owner P3主任务；C09/E15 | 主尝试身份有任务依据；与全局architecture计数边界仍REQUIRES_OWNER_CLASSIFICATION |
| #307 P3 exclusion RCA R1 | 同上诊断 | P3原失败 | 只读static/exact覆盖审计 | Owner只读RCA指令；C09/E15/E16 | 只读诊断，不是恢复实现轮 |
| #307 P3 R2 | 条件化metric support | P3失败及RCA | 契约修订+scoped实现，1候选、213UNKNOWN | Owner路线B/R2明确指令；C09/E16 | REQUIRES_OWNER_CLASSIFICATION：明确任务授权不自动证明两轮规则豁免 |
| #307 P3 R3 | 通用joint HARD-component证明 | R2基础 | 共享变量联合证明，265UNKNOWN | Owner R3明确指令；C09/E17 | REQUIRES_OWNER_CLASSIFICATION：是否同架构修正及例外待批准 |
| #307 P3 R4 | 同上 | R3 PARTIAL | 同caps约束传播，262UNKNOWN | Owner R4明确指令；C09/E18 | REQUIRES_OWNER_CLASSIFICATION：不从R4内部P0–P4重计阶段/轮次 |
| #307 P3 R5 | 同上只读诊断 | R4 PARTIAL | proof coverage/root-cause审计，无修复代码 | Owner R5 DIAGNOSTIC_ONLY；E19 LOCAL_ONLY_NOT_INDEPENDENTLY_ARCHIVED | 只读诊断，不是R5恢复实现轮；归档另授权 |
| Git环境恢复/已有commit交付 | 环境与交付，不是布局架构 | 既有任务工作产物 | lock/process审计、授权隔离、独立clone、已有commit交付 | 各次限定Owner环境授权；不得复用旧锁授权 | 非布局恢复轮；不抵扣也不增加恢复额度 |

账本不输出猜测的“已用/剩余轮数”。D04批准前，下一轮实施继续未授权，原MAX=2及architecture-review停止条件不变。

### 8.2 D06四类工作边界（仅规划，均待授权）

| 工作类别 | 输入/目的 | 可交付证据 | 不可冒称 | 当前授权 |
|---|---|---|---|---|
| 已有候选工程诊断性复核 | 固定SHA、固定实际候选及project-bound inputs；查清现状与失败原因 | 可追溯逐项工程结果、失败归因与复现条件 | 不能等同多结构生成实施或版本最终5/3验收；复核仍需明确是否允许调用Access/Truck/P2D | NOT_AUTHORIZED_BY_THIS_DRAFT |
| 后续多结构候选生成实施 | 经Owner批准的安全合同与恢复轮次范围 | 多种完整construction candidates及真实去重/结构证据 | 不等于P2D full-pass；不自动允许改预算、order、scheduler或旧recovery继承 | NOT_AUTHORIZED_BY_THIS_DRAFT |
| numeric calibration取证 | Owner批准的正例、room/outline/route粒度及标注协议 | 可比原子事实、来源、eligibility、阈值提案 | 取证不等于阈值冻结或候选规整度PASS | NOT_AUTHORIZED_BY_THIS_DRAFT |
| 最终业务验收 | 可追溯5个distinct P2D full-pass、3类主要结构、质量与视觉证据 | 版本closure及Owner验收结论 | 不以诊断、topology标签、重复候选或CI全绿替代；验收也不自动授权发布 | NOT_AUTHORIZED_BY_THIS_DRAFT |

### 8.3 D01三层验收责任修订提案（方向已同意，合同未修订）

以下为待正式审核的规范提案，不是已生效规则。三层必须独立出具状态，不能以一层通过代替另一层。历史依据为原P3任务、R3/R4 Owner强验收与C09；`ACCEPTED_PARTIAL_WITH_UNKNOWN_COUNT=0`继续保留。R2的213 pairwise UNKNOWN、R3的265 joint UNKNOWN、R4的262 joint UNKNOWN及PARTIAL结论不重算、不抹除；root queries与accepted partial的分母保持区分。

| 层次 | 精确invariant（提案） | 证明范围 | UNKNOWN处理 | 必需测试/证据 | 验收边界（待批准） |
|---|---|---|---|---|---|
| A SAFE_CAPACITY_ADMISSION | 任一容量剪枝必须有与当前partial及authority绑定、覆盖声明充分且可复核的否定证书；`PRUNE_WITHOUT_SOUND_NEGATIVE_CERTIFICATE_COUNT=0`；`ACCEPTED_PARTIAL_WITH_VERIFIED_PROVED_ZERO_CAPACITY_COUNT=0`。这些计数不证明所有实际零容量状态已被识别 | 现有HARD interfaces/必要联合约束下的安全准入；证书须声明shape/origin-space覆盖、适用约束与资源完整性；不声称未证明的几何全集覆盖 | 未找到witness、static域未命中或cap耗尽只能UNKNOWN；UNKNOWN可继续但必须单列，不作正容量保证；已失效证书不得授权剪枝 | 独立小型整数穷举；negative覆盖/资源保护/域revision/回溯隔离；KNOWN-valid control prefixes不得误剪；记录每次剪枝的证书identity、authority、partial hash及适用范围 | 若正式批准分层，可单独判定“安全剪枝机制通过”，但不得据此宣称B全覆盖、当前P3完成或工程full-pass；零观测反例不等于全域soundness证明 |
| B JOINT_POSITIVE_COVERAGE | 每个计为SUPPORTED的connected HARD component必须有统一角色几何赋值，逐项exact复验通过；`JOINT_SUPPORTED_WITHOUT_VALID_CERTIFICATE_COUNT=0`。覆盖率=获证accepted partial数/全部accepted partial数，另报root queries；不可减少统计范围 | 当前8-role/7-edge component及当前placed约束，通用graph-driven扩展；每个role唯一shape/bounds。只有pairwise证书不能计component SUPPORTED | 无完整统一赋值即UNKNOWN；不因UNKNOWN或positive probe耗尽而剪枝；不能将必要空间非空当正证书 | 共享角色冲突/多边一致性、exact revalidation、graph extension、域revision、backtracking；逐partial状态明细可重汇总，独立小oracle检查false positive/negative，保留冷暖耗时与内存 | 现行零UNKNOWN门槛仍有效且未达成。未来是否将B作为独立覆盖率阶段、阈值及P3责任如何归属须正式批准；本提案不设新数值、不宣布豁免 |
| C FULL_ENGINEERING_VALIDATION | 每个计入full-pass的实际12-role候选须通过既有site/dimension/non-overlap/MUST、完整Access、Truck及P2D权威；`COUNTED_FULL_PASS_WITH_MISSING_REQUIRED_VALIDATION_COUNT=0` | 完整候选及project-bound工程输入；包括既有interaction/footprint权威，不只8-role component或7条证书 | 未运行、BLOCKED、UNKNOWN或required事实缺失不得计full-pass；保留真实上游失败，不伪造footprint或以CI抵扣 | 可回放候选geometry/input/hash/authority版本、逐项Access/Truck/P2D结果、结构去重依据；至少5个distinct structured full-pass、3类实质结构；质量与Owner视觉另验收 | 7/7 direct certificates只证明对应hard interfaces，不等于C。C通过不倒推历史全部partial具备B，也不自动授权Tool7/发布 |

正式修订批准件必须回答：A/B如何分别命名与归属、B是否仍要求全覆盖、P3总体完成条件如何表述、历史结果如何展示、测试allowlist及未来授权边界。在此之前禁止按提案重命名当前P3为PASS。

### 8.4 D03两项合同修订与兼容提案

**D03-GRID：产品目标与可执行numeric gate分离。** 保留P0原始 `major-zone grid target=0.90`，不删除、不降低，也不把目标直接当作已经校准的可执行gate。建议正式合同同时记录 `PRODUCT_GRID_TARGET=0.90`、`NUMERIC_GATE_CALIBRATION_STATUS=NOT_CALIBRATED_PENDING_OWNER`、指标版本、eligible zone集合、分母、容差/轴网提取规则、来源及review状态。后者是提议字段，不是本轮runtime schema变更。没有批准的校准协议和可比样本，不宣称numeric regularity PASS；亦不把未校准解释为目标作废。

迁移方案：历史报告保留原值、原policy版本和原判定；新报告待正式批准后并列展示产品目标、测量事实和gate校准状态。旧版“目标达到”不得无条件转换为新版“正式gate PASS”。需校准时按D02独立授权取证，不在本轮发明容差、depth/compactness/appendage阈值。拟修订位置为P0/C07及本计划的术语/适用范围对照，实际文件修改另授权。

**D03-GROUP：当前P1A保持PROCESSING_CORE_GROUP，历史P0归属显式保留。** 建议正式确认 `secondary_precooling_room` 在当前P1A结构生成中继续属于 `PROCESSING_CORE_GROUP`；P0原始 `FINISHED_SIDE_GROUP` 是实际不同的functional ownership口径，不通过band映射或“意思一致”消解。该建议不改变当前runtime，不增删role/MUST，不改变dimension/shape/site权威。

迁移方案：正式批准后以合同/policy版本标识适用范围，历史P0报告和fixture不就地重写；保留原group标签，并附显式旧→新映射及原因。依赖group的P0质量指标、calibration eligibility与未来报告须逐项影响审计，不能只改标签假定指标不变。若需按新口径重算，另行授权并保留新旧证据，不能沿用旧PASS。当前P1A plan/handoff及P0/P1 interface projection保持既有输出；schema/version兼容性审计先于任何迁移实现。Owner仍需批准正式文字、适用版本、历史兼容规则及受影响指标清单。

### 8.5 D04架构级分类与新布局实施前门禁

以下是8.1逐轮账本的架构级索引；行为分类按任务scope描述，不自动决定原两轮计数。混合行为保留双重分类，不用“证明改动”或“diagnostic”名称掩盖真实布局构造变化。

| 架构/切片 | 主实现 | 真正布局修正 | 证明机制/权威对齐 | 只读诊断/环境 | 原两轮归属与审核要求 |
|---|---|---|---|---|---|
| #302旧R2/tail生命周期 | E04旧主实现，精确边界待核定 | 多轮tail/recovery，逐轮证据待Owner分类 | 不能仅凭commit标题拆分轮次 | 历史诊断不抵扣修正 | REQUIRES_OWNER_CLASSIFICATION；terminal失败不被新计划豁免 |
| S3 whole-building MVP | S3主尝试 | S3 CR1 anchor修正 | hard subset与intent约束 | 证据回放不独立计修正 | REQUIRES_OWNER_CLASSIFICATION：主尝试起点及CR1计数须核定 |
| S4工程桥接 | bridge实施，不是新布局主架构 | bridge本身无post-validation几何修复 | 接既有工程权威 | 诊断结果7/12/Truck失败 | 不由S4切片名称重置S3架构轮次 |
| #306 access-aware构造 | 延续S4失败后的构造修正谱系，是否独立主尝试待审 | CR1/2、CR4及CR5–7涉及候选构造/排序/传播等实际变化 | CR3及CR5–7含forward/capacity/free-space证明，CR4含witness replay；混合行为不自动免计 | post-CR7只读audit；Git环境任务另列 | CR1–7逐条REQUIRES_OWNER_CLASSIFICATION，见8.1；原分支冻结不继承代码 |
| #307 structural/metric与P3 | clean-main子P0/P1/P2，原P3为消费主尝试；架构计数边界待审 | P3/R2改变准入及构造生命周期；不能把它们全部视为纯证明无布局影响 | R1权威对齐；R2条件化契约；R3/R4联合证明与传播 | exclusion RCA/R5只读；独立clone/lock恢复属环境 | REQUIRES_OWNER_CLASSIFICATION；明确Owner任务授权不自动等于恢复stop例外 |

**新布局实施前必须完成架构审核。** 审核件至少包含：架构identity与baseline；主尝试及逐轮行为分类；每轮Owner授权原文/可定位证据；两轮限制归属；若有例外则提供真实单独授权（没有则不补造）；terminal/stop记录；新的范围、验收、rollback和预算不变约束。任一历史计数未能核定则继续标REQUIRES_OWNER_CLASSIFICATION，不能以本账本推算可用额度。架构审核完成仍不等于新任务获实施授权，R6A及下一阶段继续false。

### 8.6 拟议合同变更allowlist、禁止项与验收证据

本节仅是未来正式修订的候选allowlist，不授予写入这些文件的权限；**本轮实际allowlist只有 `docs/tasks/V2_2_2-version-plan.md`**。

| 待批准范围 | 拟允许的最小变更 | 正式批准前/之后的边界 | 必须提交的审核证据 |
|---|---|---|---|
| D01责任合同 | 原P3任务及R3/R4验收条款的具名补充/修订记录；ADR-050的A/B/C职责与supersession；本计划对应状态说明 | 保留历史原门槛、失败/PARTIAL与trace；具体文件/段落和是否采用附录须Owner批准；不由文档修订自动修改生产机制 | 旧→新invariant映射、UNKNOWN分母与scope、sound negative边界、联合正证书要求、P3完成条件及迁移说明 |
| D03-GRID | P0工艺/规整度合同及ADR-047中产品0.90目标与gate校准状态的明确区分；本计划对照 | 只在正式授权后修改；不得删除0.90或凭空冻结numeric阈值；P0A/P0C原证据不覆盖 | 校准协议/样本缺口、版本与eligible集合、旧判定兼容及不可推导项；校准实施另授权 |
| D03-GROUP | P0、P1A reset合同及ADR-049必要的适用版本/ownership兼容说明；本计划映射 | 不改当前runtime分组、历史原数据或HARD graph；具体变更段落待批 | 历史FINISHED_SIDE与当前PROCESSING_CORE对照、受影响quality/calibration消费者清单、schema版本审计及迁移方案 |
| D04治理 | P1A reset合同/ADR-049中architecture identity、恢复轮次计数与例外审批的具名澄清；本计划账本 | MAX_RECOVERY_ROUNDS_PER_ARCHITECTURE=2不变，不追认不存在的授权，不以新编号清零 | 逐轮可定位授权、主尝试/混合行为分类、未定项、Owner裁决与新布局实施前审核记录 |
| 后续测试适配（独立授权） | 仅与获批新合同直接对应的断言、文档一致性和兼容测试；具体test路径须另列 | 本轮TESTS_CHANGED=false；不得删除既有安全测试/缩分母/把UNKNOWN改SUPPORTED；生产实现不在文档修订allowlist | 小型独立穷举、negative soundness/positive exact复验、历史control及prefix兼容、回溯与domain revision、group/schema/质量版本迁移回归；测试无法证明的scope明确列出 |

禁止修改：process_graph MUST/flows、12个roles、dimension/shape/site/full hard-obstacle权威、P0/P1 coordinate-free contract语义、P2 public policy/result、60000 placement budget、zone order、scheduler、families、Access/Truck/P2D工程权威；禁止历史坐标seed、#302/#306 recovery移植、旧证据覆盖、原工作区/锁操作。本提案不授权production/tests/ADR/原合同写入，不启动搜索优化或新的工程验证。

正式修订验收要求：提供逐段diff与批准号、38项/4组/9字段不丢失、5full-pass/3实质结构/原质量目标不降级、历史验收保留、未决项不冒称批准；证据绑定SHA/input/authority及真实scope，R5仍为LOCAL_ONLY_NOT_INDEPENDENTLY_ARCHIVED，归档另授权。实施后的工程结果必须另行取得，不能借本轮文档审核补造。任何改动超出具名allowlist，STOP再请求授权。

这些方向有助于多方案开发：A明确何时可以安全剪枝，避免静态有限域或资源耗尽误杀合法候选；B单列联合证明覆盖及成本，避免把未证UNKNOWN包装成正容量或把证明覆盖混作工程布局；C让5个full-pass/3类结构回到真实业务交付。D03避免未校准gate或group口径冲突误导质量评价；D04要求先审核架构与恢复额度，防止继续无边界修正。上述是职责与治理方向，不是性能/候选数量改善的已验证结论，也不授权立即恢复布局实施。

停止条件：HEAD/remote PR变更或未知Git writer/I/O异常；发现范围外文件改动；需改原始合同或测试才可“对齐”；需提高budget/改scheduler/order；无可靠覆盖却要求negative；UNKNOWN冒充SUPPORTED；试图以家族标签/CI/hash数替代5/3/质量/视觉；触及recovery stop需architecture review；任何后续工作无Owner授权。均STOP，不自动绕过。

## 9. 建议业务实施顺序与允许规划的并行项

1. **版本合同统一与安全门禁决策**：审核本文、D01/D03/D04/D05，批准后才冻结修改范围与下一TASK。
2. **多种完整规整候选构造**：在批准的安全契约下恢复可回放、多结构的完整候选；不是再造proof/DFS架构或顺序调参。此阶段产物只能叫construction candidates。
3. **真实Access/Truck/P2D**：现有bridge按候选真实调用，保留失败和预算；至少5个distinct structured full-pass、3类真实结构。不能先quality排名掩盖hard失败。
4. **工艺流线与规整度评价**：使用工程route事实、项目receiving authority及批准的numeric calibration。事实提取与样本校准可以在单独授权后平行推进；metric正例取证不依赖全新搜索成功，但新候选评价依赖真实候选/route。
5. **hard-pass后的质量排序与多方案比较**：依赖步骤3集合和步骤4质量事实，提供原子解释和winner-vs-next；不能提前改selector。
6. **同尺度方案图与Owner视觉审核**：依赖足够full-pass且结构distinct的集合，确认完整工厂可读性，不以P0C overlay审核抵扣。图集规格可预先规划，生成/实施仍另授权。
7. **Tool7集成与版本发布验收**：上游门禁通过后独立授权；兼容旧工具/transport/public schema、真实新链验收、精确HEAD CI。Ready/Merge/Tag/Release/Deploy各自单独授权。

真正阻断关系：完整候选→工程验证；真实route→工艺事实；numeric正例校准→依赖阈值的规整度验收；full-pass+quality事实→排序；5/3有效集合→最终视觉/版本验收。非必需强行串行：参考证据整理、Owner阈值/角色映射决策、schema/图集规格审查可规划并行。对是否让工程验证在P3未闭环时独立进行，本文不自行许可，交D06裁决。

## 10. 差异说明：本草案新增了什么，没有改什么

| 旧/分散口径 | 本草案对账 | 原始合同是否改动 |
|---|---|---|
| C01中旧版P2/P3/P4完成与本版混读 | 分版本、分子链、分candidate/quality/release | 否 |
| P0 snapshot fixture/PDF缺失、P0C overlay曾pending | 当前fixture已获得、5PDF/5overlay PASS；numeric仍未ready | 否，历史原文保留 |
| reset合同/ADR写runtime未授权 | 按后续S1–S4与#307各Owner task确认已做范围 | 否，不倒改历史授权 |
| 有3families/6plans就当3个有效方案 | 标为topology inventory，不满足full-pass多样性目标 | 否 |
| 子P2 metric PASS或final7/7就当P2D full-pass | 分离pairwise/联合/12区/Access/Truck/P2D | 否 |
| R2/R3/R4全绿CI可能当P3完成 | 保留R4 PARTIAL、262UNKNOWN、P3=false | 否 |
| 证明查询cap下降就当证明增量 | cap216→75但positive只52→55；197unproven及R5空域单列 | 否 |
| correction/diagnosis/internal步骤混成正式阶段 | 所有编号标scope；future正式ID待Owner核定 | 否 |
| numeric、角色组与round归属差异隐含 | D02/D03/D04显式待审，不选有利口径 | 否 |

**未经授权范围扩张未在本轮核实为既成事实**：R3强joint目标有Owner明确指令，不将它污名化为越权；但验收概念混同、恢复无限延长及证明工作偏离产品交付的风险已经明确识别，必须Owner决策。本文不替旧任务补造授权或宣布历史stop违规已被豁免。

## 11. 本轮交付/自检

唯一仓库变更文件：`docs/tasks/V2_2_2-version-plan.md`（首次草案为新增文件，本次为已入库文件的修订）。现有合同/ADR/production/tests/evidence均不改。本轮审查不是新搜索、测试或工程验收，不产生新的P3业务PASS。执行文档字段、冻结目标和只改一文件的只读自检；不运行runtime suites或CI。

仓库外审查来源快照：`/Users/charles/codex-r3-isolated.m45h1H/version-plan-review.mhUKrM/` 中 `source_manifest.json`、三个 `pr-*-read-only-snapshot.json` 和只读capture脚本。它们记录当时完整SHA/来源digest，非正式入库evidence、非计划冻结。R5报告及相关CSV/JSON明确为 `LOCAL_ONLY_NOT_INDEPENDENTLY_ARCHIVED`；后续独立归档须Owner另行授权，本草案修订不授权归档。

版本任务完整性仅限“现有已知任务和已识别剩余工作包完成盘点”；38项、4组及全部9字段保留，未批准的未来正式TASK_ID不是冻结完成。

前次审核修订及文档交付记录保留：草案已由独立documentation commit f6b17fb6...入库，仍未冻结。本次决策对齐仅修改该现有草案，不创建新commit或push。

本次完成意味着 **OWNER_DECISION_ALIGNMENT_DRAFT_READY**，`PLAN_STATUS=OWNER_REVIEW_DRAFT_NOT_FROZEN`。D01/D03/D04为方向已同意、正式合同修订待批准；D02/D05/D06/D07仍PENDING_OWNER。原零UNKNOWN强验收和P3=false不变，不是v2.2.2或P1A完成。等待正式合同变更、架构分类及逐任务授权；不commit、不push、不改PR body、不Ready/Merge、不Tag/Release/Deploy、不启动R6A或其他实施。

<a id="r1-r15-current-reconciliation"></a>

## 12. 2026-10-15：R1–R15 实际成果与剩余交付路线（Owner 审核增补）

### 12.1 先看结论、原目标和下一项工作

**已得到：一个可核验的CP-SAT重建完整布局；固定布局的11项非货车Access生产源码验证；参数化Truck软件能力；八工具MCP生产集成、公网部署。尚未得到：新哨真实Truck/P2D full-pass、多结构5方案集合、正式工艺/规整度评价与排序、最终图集及新布局Tool7闭环。**

本轮原始产品目标仍是“完整、工艺方向清楚、主流程无折返、分组与建筑轮廓规整、主功能区轴网协调、人员与物流合理分离的整厂方案”，不是“能摆12个矩形”或“能调用第8个工具”。C02/C06/C07/C08/C09的原文均已重新读取；本节不修改它们。

```ini
TASK_ID=V2_2_2_VERSION_PLAN_R1_R15_RECONCILIATION
MODE=DOCUMENTATION_ONLY
RECONCILIATION_DATE=2026-10-15
START_HEAD=64b842919d0fcb05264b7902e2b3a8a8c1b3a47e
DOCUMENT_ALLOWLIST=docs/tasks/V2_2_2-version-plan.md
DOC_COMMIT_PUSH_AUTHORIZED_BY_CURRENT_TASK=true
PLAN_STATUS=OWNER_REVIEW_DRAFT_NOT_FROZEN
STRUCTURED_P2D_FULL_PASS_CANDIDATE_COUNT_TARGET=5
MAJOR_LAYOUT_FAMILY_TARGET=3
MAIN_FLOW_BACKTRACK_COUNT_TARGET=0
MAJOR_ZONE_GRID_ALIGNMENT_PRODUCT_TARGET=0.90
NUMERIC_GATE_CALIBRATION_STATUS=NOT_CALIBRATED_PENDING_OWNER
VERIFIED_NEW_STRUCTURED_P2D_FULL_PASS_CANDIDATE_COUNT=0
VERIFIED_FULL_PASS_MAJOR_LAYOUT_FAMILY_COUNT=0
P3_COMPLETE=false
P3_R4_ACCEPTED_JOINT_UNKNOWN_HISTORICAL_COUNT=262
VERSION_COMPLETE=false
OWNER_REVIEW_REQUIRED=true
NEXT_DEVELOPMENT_AUTHORIZED=false
SERVER_REPLAY_ACCEPTED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

“0”指本次能计入**新结构完整工程验收集合**的已核验数量，不是项目无解证明；历史v2.2.1 fixture full-pass、3个family词汇、6个topology plans、实验候选数量或新Hash均不能填补5/3门槛。0.90保留为原产品目标，不能伪装成已经校准生效的numeric gate。

**建议下一项正式开发：`REVIEW-MULTI-CANDIDATE`阶段A——可信全局求解成果与整厂结构的生产整合。** 先由Owner在现有`REVIEW-SAFETY-CONTRACT`内完成D01/D03/D04的具名范围和合同决策，再另行授权实施；不重新启动泛化证明研究，不回到逐房间/尾部修补。同步由Owner准备真实Truck资料和质量校准输入。本文不授予这项开发、依赖安装或生产资源映射的实施权限。

### 12.2 证据分级与本次核验范围

| 级别 | 可采信内容 | 不可推导 |
|---|---|---|
| `GITHUB_EXACT_HEAD_VERIFIED` | 本轮读取真实PR、commit和指定SHA的terminal CI；可定位生产源码 | 不能证明布局质量、工程full-pass或部署已验收 |
| `LOCAL_ARCHIVE_SHA_VERIFIED` | 本地持久化归档SHA及其Manifest中每个文件均重算匹配；已读取相关原始验证JSON | 不是本轮重跑求解/工程链；本地归档也不是远端仓库内正式evidence |
| `OWNER_REPORTED` | Owner本次明确回执；可记录Owner观察和接受的范围 | 不是Codex独立客户端复测、截图/逐项原始调用证据或工程批准 |
| `NOT_VERIFIED` | 仅历史任务叙述，原件缺失或无法验证 | 不补造Hash、路径、PASS、候选数量或来源批准 |

持久化来源根目录记为 `A=/Users/charles/Documents/Codex/cold-storage-planning-agent/artifacts/`；以下相对`A`的路径用于Owner本机审计，不宣称GitHub读者可直接下载。归档均在`A/archives/`。本轮只读核对，不改原报告、Manifest或归档，不登录/修改服务器，不运行CP-SAT、Truck或新工程验证。

| 引用 | EVIDENCE_SOURCE | EVIDENCE_VERIFIED / 核验边界 |
|---|---|---|
| N01 | 历史全局求解R1–R8任务叙述及本轮Owner对账指令 | `OWNER_REPORTED`；历史原件/完整来源链`NOT_VERIFIED`，尤其原R8原件丢失；少量恢复源码不能替代完整证据。不得从重建结果倒填历史PASS |
| N02 | `solver-feasibility-recovery-r1/evidence/results.md`、`candidates/new_best_candidate.json`、`validation/independent_validation.json`及其Manifest；`solver-feasibility-recovery-r1-2026-10-12.tar.gz` | `LOCAL_ARCHIVE_SHA_VERIFIED`：464项；新候选规范化Hash独立重算一致，12区/7 MUST及独立11 Access、共存、无孔洞、原Footprint/Site验证证据；不是历史R8Hash或原Access/P2D PASS |
| N03 | `r9-access-validator-closure-rebuilt-r1/evidence/results.md`及实际逐项/资源结果；`r9-access-validator-closure-rebuilt-r1-2026-10-12-portable.tar.gz` | `LOCAL_ARCHIVE_SHA_VERIFIED`：465项；冻结原10 PASS/1资源中断、隔离11 PASS；通用几何和元数据当时仍有缺口 |
| N04 | `r10-access-validator-engineering-closure/validation/`的geometry、portal、typed-Site、Application及footprint JSON；`evidence/results.md`；同名归档 | `LOCAL_ARCHIVE_SHA_VERIFIED`：939项；隔离Domain/Application非货车11 PASS、原来源绑定、独立几何与实际Application通道建筑复核；合法Mapping明确为实验适配器 |
| N05 | `r11-access-production-integration/typed_site_application_validation.json`、`independent_access_validation.json`、`building_footprint_validation.json`及报告/归档；生产commit `514d013…`、最终`5df2d537…` | 归档114项匹配；`GITHUB_EXACT_HEAD_VERIFIED`确认源码集成和最终CI成功。固定布局生产源码Domain/Application各11 PASS，不是server-generated placement或正式Server Replay |
| N06 | `r12-truck-p2d-engineering-validation/p2d_application_validation.json`、Truck来源清单、Owner缺项表及报告/归档 | 归档47项匹配；原应用实际12结果=11非货车PASS+1 `BLOCKED_PROJECT_MANEUVER_INPUT_REQUIRED`；`project_layout_validated=false`、`p2_complete=false` |
| N07 | `r13-truck-parameterized/results.md`、`synthetic_input.json`、实际结果/SVG及归档；最终commit `03b99f2c…` | 归档47项匹配，生产源码/最终CI核实；3段Option C合成机动软件PASS，真实项目批准和完整动力学仿真均非其结论 |
| N08 | `r14-truck-mcp-integration/results.md`、HTTP原始结果、Schema/冻结七工具快照及归档；初始commit `d0975789…` | 归档63项匹配；Tool8实现存在，但该初始SHA两条CI实际FAIL，不能只沿用其报告中的PENDING |
| N09 | `r14-exact-head-ci-remediation/results.md`、wheel/测试证据及归档；修复commit `64b84291…`、GitHub最终CI | 封存归档27项匹配；工作目录`evidence/final-pr.json`有1项与Manifest不符，**不宣称工作目录全量匹配，也不修历史文件**。最终状态以封存记录及本轮GitHub精确HEAD核验为准 |
| N10 | `r15-controlled-backend-restart-deployment/validation/deployment_result.json`、`public-external/`原始HTTPS结果/SVG、报告/归档 | 归档75项匹配；记录部署目标SHA、active服务、公网8工具、合成Truck三段/包络/SVG哈希。不是本轮服务器复测；前6工具实际计算与第7工具缺参合同回归，非新Tool7完整出图验收 |
| N11 | Owner本次指令：“豆包已经发现全部8个工具，并成功调用preview_truck、返回和显示合成车辆路线SVG” | `OWNER_REPORTED`：记录客户端发现/调用/显示成功回执；N10当时客户端`NOT_EVALUATED`历史不改。本轮未新增独立豆包测试或新哨工程批准 |

归档SHA256（本轮重算；不修改历史摘要）：

| 引用 | 归档文件名 | SHA256 |
|---|---|---|
| N02 | `solver-feasibility-recovery-r1-2026-10-12.tar.gz` | `9333e4db8daba5948fa8cbe7e566adf32be4d88070139295f9503fe587f4da94` |
| N03 | `r9-access-validator-closure-rebuilt-r1-2026-10-12-portable.tar.gz` | `2dd4b5e778c79a35c5ebc65ce23c187bef06d39f701072261194bc70839ff09b` |
| N04 | `r10-access-validator-engineering-closure.tar.gz` | `04f175b519fc40815a7b1c1fddae85df78484fdb111347f470a1886b00158e10` |
| N05 | `r11-access-production-integration.tar.gz` | `08188542cef11cec11084aaedef389e44ce63b2f828678f49fc9be4f7c51b139` |
| N06 | `r12-truck-p2d-engineering-validation.tar.gz` | `64505cf0cd3d070822bf9b589faa2485a8e9b0af31a7fbcb7628e7aa7749664a` |
| N07 | `r13-truck-parameterized.tar.gz` | `0a2d8d7a1d72b37fd53bb1fa2c980be00f006aa28ca084e1995feae00408ca30` |
| N08 | `r14-truck-mcp-integration.tar.gz` | `4e030465077813ea847108b8afbe336cb49ded412212f79f4d91c9b24b951e41` |
| N09 | `r14-exact-head-ci-remediation.tar.gz` | `52c86281297a9f97413f794e9149aa387bed61438d5c17518aaff4bcfde825d6` |
| N10 | `r15-controlled-backend-restart-deployment.tar.gz` | `068d04cf8e9b43334ae90f25aa3f36ebe752de08d95f49e02f9f26e1b9fe6643` |

可信重建候选：`sha256:870d7c48cf2a1f65f8bcf5df0ecc3030e422e0707b9831f9e85565ff62690811`。按N02声明的`zones`以`zone_code`排序、canonical JSON规则重算一致。原Fixture raw SHA仍为`d03ecae9e1e2808cba346eb83a39f853c8a4b366acc103669af1cf868363901e`；这不是历史R8 Hash恢复成功的声明。

### 12.3 R1–R15最新任务总账（独立编号空间）

本节“全局R1–R15”与第4.3节P1A/P3内的R1–R5、旧PR #302的R15断言**互不等同**。下列索引只便于连接表格，不是新TASK_ID、架构identity或恢复轮数。`B0`是可信重建，`R14-CI`是同轮后续修复，不伪造成R16。

| 索引 | TASK_ID |
|---|---|
| R1 | `V2_2_2_GLOBAL_CONSTRAINT_LAYOUT_SOLVER_R1` |
| R2 | `V2_2_2_GLOBAL_CONSTRAINT_LAYOUT_SOLVER_R2_ENGINEERING_CLOSURE` |
| R3 | `V2_2_2_GLOBAL_CONSTRAINT_LAYOUT_SOLVER_R3_ACCESS_ENGINEERING_VALIDATION` |
| R4 | `V2_2_2_GLOBAL_CONSTRAINT_LAYOUT_SOLVER_R4_ACCESS_GEOMETRIC_FEASIBILITY_PROOF` |
| R5 | `V2_2_2_GLOBAL_CONSTRAINT_LAYOUT_SOLVER_R5_ACCESS_AWARE_GLOBAL_LAYOUT` |
| R6 | `V2_2_2_GLOBAL_CONSTRAINT_LAYOUT_SOLVER_R6_ENGINEERING_QUALITY_OPTIMIZATION` |
| R7 | `V2_2_2_GLOBAL_CONSTRAINT_LAYOUT_SOLVER_R7_CORRIDOR_STRUCTURE_AND_BUILDING_COMPACTNESS` |
| R8 | `V2_2_2_GLOBAL_CONSTRAINT_LAYOUT_SOLVER_R8_HOLE_FREE_BUILDING_AND_PERSONNEL_ROUTE_CLOSURE` |
| B0 | `V2_2_2_REBUILT_CP_SAT_FEASIBILITY_RECOVERY_R1` |
| R9 | `V2_2_2_R9_ACCESS_VALIDATOR_CLOSURE_REBUILT_R1` |
| R10 | `V2_2_2_R10_ACCESS_VALIDATOR_ENGINEERING_CLOSURE` |
| R11 | `V2_2_2_R11_ACCESS_VALIDATOR_PRODUCTION_INTEGRATION` |
| R12 | `V2_2_2_R12_TRUCK_ENGINEERING_AND_P2D_VALIDATION` |
| R13 | `V2_2_2_R13_TRUCK_PARAMETERIZED_CAPABILITY_IMPLEMENTATION` |
| R14 | `V2_2_2_R14_TRUCK_MCP_PRODUCTION_INTEGRATION` |
| R14-CI | `V2_2_2_R14_EXACT_HEAD_CI_REMEDIATION` |
| R15 | `V2_2_2_R15_CONTROLLED_BACKEND_RESTART_DEPLOYMENT`；此前同轮公网预检、认证续办暂停和升级机制阻断保留，不视为当时已部署 |

以下两表按索引连接，连同上表TASK_ID完整记录指定的11个字段。

| 索引 | OBJECTIVE | DELIVERABLE | ACTUAL_RESULT | EVIDENCE_SOURCE | EVIDENCE_VERIFIED |
|---|---|---|---|---|---|
| R1 | 同一CP-SAT模型构造12区 | 全局模型/候选/Oracle | 历史记录：完整12区、7 MUST、Packaging PASS；不重新认定原件已验证 | N01 | 原件`NOT_VERIFIED` |
| R2 | Flexible软优化与工程闭环尝试 | 多候选/质量与Access诊断 | 历史记录：质量改善、非货车6 PASS/5资源中断；不是P2D | N01 | 原件`NOT_VERIFIED` |
| R3 | 固定R2布局的Access优化 | 插桩/隔离性能实验 | 历史记录：6 PASS、1 BLOCKED、4资源/累计额度未完成；不能当工程FAIL | N01 | 原件`NOT_VERIFIED`，最后一项未新计费执行不等于运行后中断 |
| R4 | 判定5项固定几何可达性 | 精确谓词反例/路线/不可行证书 | 历史记录：3物流合法、2人员固定布局不可行、5谓词反例；原证书不能凭叙述重建为PROVEN | N01；N03/N04仅复现缺陷类型 | 原件`NOT_VERIFIED`，复现不等于原字节恢复 |
| R5 | 12区与11 Access联合建模 | 通道感知全局模型/候选 | 历史记录：独立11几何及共存、原10 PASS/1中断；房间狭长 | N01 | 原件`NOT_VERIFIED` |
| R6 | 房间形状与面积优化 | 质量Pareto/通道与建筑证据 | 历史记录：形状改善但走廊、人员路线增加；非全面质量成功 | N01 | 原件`NOT_VERIFIED` |
| R7 | 通道结构和建筑紧凑度 | 新候选/并集与轮廓诊断 | 历史记录：质量取舍、封闭孔洞，不能推荐为有效建筑轮廓 | N01 | 原件`NOT_VERIFIED` |
| R8 | 无孔洞、人员路线及原Access闭环 | 求解器/候选/完整证据包 | 历史原件丢失；不沿用旧Hash或直接记PASS；后续恢复另列B0 | N01 | `NOT_VERIFIED` |
| B0 | 重建可长期复现的工程几何基线 | 新候选870d…、完整源码/JSON/SVG/归档 | 1个新完整12区，7/7 MUST、独立11 Access/共存、无孔洞，原Footprint/Site通过；原Access/Truck/P2D当轮未执行 | N02 | `LOCAL_ARCHIVE_SHA_VERIFIED` |
| R9 | 固定B0解决入口资源中断 | 隔离优化及原始/独立对照 | 原10 PASS/1 Host中断；隔离11 PASS；独立当前矩形布局通过；语义等价PARTIAL | N03 | 同上 |
| R10 | 通用谓词、Portal、typed-Site和应用验证 | 精确修复/11项应用结果/实际建筑 | 隔离11/11、精确几何、元数据、来源、共存与建筑通过；Truck原缺输入分支保留 | N04 | 同上 |
| R11 | 将验证器修复迁入生产代码 | 源码/测试/固定候选验证/CI | 生产源码Domain/Application各11 PASS；独立几何/typed-Site/Footprint通过；不是正式Server Replay | N05 | 归档核验+`GITHUB_EXACT_HEAD_VERIFIED` |
| R12 | 查验真实Truck并尝试P2D | 来源清单/缺项/原应用结果 | `R12_TRUCK_PROJECT_INPUT_BLOCKED`；11非货车PASS+Truck BLOCKED，P2D未完成 | N06 | 归档核验；不是实际获批准车辆验证 |
| R13 | 用户结构化Truck参数入口 | Domain/Application/CLI/独立Schema | Option C合成三段机动/SVG PASS；尺寸/来源/入口/碰撞/人车待审fail-closed；真实资料仍缺 | N07 | 归档+生产源码/CI核验 |
| R14 | 添加第8个`preview_truck` | MCP适配器/包内Schema/HTTP测试 | 八工具本地调用成功；初始CI实际失败，未以本地成功掩盖 | N08 | 归档+生产源码/失败CI核验 |
| R14-CI | 修复3项旧断言冲突 | 仅打包与工具列表测试修正 | 合法Schema仍打包、原7 Schema严格保留；本地Backend6522 PASS/470跳过，最终PR/Push CI成功 | N09 | 归档核验；工作目录快照例外已明示；CI独立核验 |
| R15 | 实际公网发布及软件调用 | 备份/独立版本/受控重启/HTTPS结果 | 目标HEAD实际上线8工具；合成Truck三段、Envelope及SVG哈希通过；本轮Owner补充豆包发现/调用/显示成功 | N10+N11 | 部署原始结果/归档核验；客户端为`OWNER_REPORTED` |

| 索引 | PRODUCTION_INTEGRATED | CI_STATUS | DEPLOYMENT_STATUS | VERSION_ACCEPTANCE_CONTRIBUTION | REMAINING_BLOCKER |
|---|---|---|---|---|---|
| R1 | false（全局求解实验） | 原实验`NOT_VERIFIED` | 未核验部署 | 同时求解构造路线探索 | 原件及生产整合；不能计full-pass |
| R2 | false | 同上 | 同上 | 形状质量与工程闭环取舍探索 | 原始质量/候选证据未核验 |
| R3 | false | 同上 | 同上 | 将资源中断与路径FAIL分开 | 性能实验不能作可达性结论 |
| R4 | false | 同上 | 同上 | 将搜索域与工程几何、谓词缺陷分开 | 原证书未核验，负证明不可扩大范围 |
| R5 | false | 同上 | 同上 | 通道进入全局模型的实验路线 | 可恢复性、生产构造与质量 |
| R6 | false | 同上 | 同上 | 房间/面积/路线Pareto评价 | 未证明全面改善或原归档完整 |
| R7 | false | 同上 | 同上 | 并集与孔洞纳入候选拒绝的需求 | 有孔洞不等于建筑PASS |
| R8 | false（不得拿B0冒充） | 同上 | 同上 | 历史目标保留 | 历史完整原件丢失 |
| B0 | false（求解器仍隔离） | 无本轮新增生产CI | 候选/求解器不是公网新布局链 | 可信单候选几何基线，支持后续固定回归 | 不是5/3、真实Truck/P2D或质量验收 |
| R9 | false（隔离修复后由R11迁入） | 无对应生产commit CI | 当轮未部署 | 原入口资源瓶颈取得可复现改善 | 当时通用谓词/元数据/应用层缺口 |
| R10 | false（隔离，随后R11迁入） | 隔离测试不替代生产CI | 当轮未部署 | Access工程闭环的迁移依据 | 不等于原应用整体p2_complete |
| R11 | true（验证器修复） | 最终`5df2d537…` PR/Push SUCCESS | 后随R15目标代码上线 | 11项非货车正式源码能力 | Truck资料、P2D、全局生成/质量链 |
| R12 | 无新生产代码，仅生产源码复核 | 审计基线CI SUCCESS；非新功能CI | 无新增部署 | 真实Truck缺项边界，阻止fixture伪验收 | Owner批准的实际车辆/入口/模板/装卸依据 |
| R13 | true（通用Truck扩展） | 最终`03b99f2c…` PR/Push SUCCESS | 后随R15上线 | 用户参数化Option C软件能力 | 合成资料不补真实新哨输入 |
| R14 | true（MCP Tool8） | `d0975789…` PR/Push FAILURE | 初始未部署；随后修复版本上线 | 对外调用接口和包内Schema | 不能跳过失败CI或替代Tool7新布局集成 |
| R14-CI | true（仅测试修复） | `64b84291…` PR/Push SUCCESS | R15部署该精确SHA | 消除实际CI冲突，保持历史功能断言 | CI绿不证明版本布局质量 |
| R15 | true（既有生产能力上线，非CP-SAT集成） | 部署目标CI SUCCESS | `DEPLOYED`于实际HTTPS Origin | 八工具可用；豆包软件验收有Owner回执 | 认证仍未启用；真实Truck/P2D、5/3、质量与新Tool7链仍未完成 |

生产源码与CI定位（本轮只读更新状态，原报告中PENDING/失败记录不覆盖）：

| 切片 | 精确HEAD | PR CI / Push CI与本次终态 |
|---|---|---|
| R11 | `5df2d537bb752980e939bbf80301ac35250d47a2` | [38288182450](https://github.com/xuezhiorange-png/cold-storage-planning-agent/actions/runs/38288182450) / [38288176217](https://github.com/xuezhiorange-png/cold-storage-planning-agent/actions/runs/38288176217)：SUCCESS / SUCCESS |
| R13 | `03b99f2cc60b462783b4a71b9ef1a27689a68db8` | [38421699200](https://github.com/xuezhiorange-png/cold-storage-planning-agent/actions/runs/38421699200) / [38421694620](https://github.com/xuezhiorange-png/cold-storage-planning-agent/actions/runs/38421694620)：SUCCESS / SUCCESS |
| R14初始 | `d097578940871c5aca96a56efce93ec26da2c506` | [38450690416](https://github.com/xuezhiorange-png/cold-storage-planning-agent/actions/runs/38450690416) / [38450684570](https://github.com/xuezhiorange-png/cold-storage-planning-agent/actions/runs/38450684570)：FAILURE / FAILURE |
| R14修复 / R15部署 | `64b842919d0fcb05264b7902e2b3a8a8c1b3a47e` | [38593554620](https://github.com/xuezhiorange-png/cold-storage-planning-agent/actions/runs/38593554620) / [38593543535](https://github.com/xuezhiorange-png/cold-storage-planning-agent/actions/runs/38593543535)：SUCCESS / SUCCESS |

实际公网MCP：`https://mcp.coldstorageamz.site/api/v1/aily/v1/mcp/sse`，Streamable HTTP，8工具，`preview_truck`第8。R15服务器原始证据保留首次就绪探测超时及后续通过，不把它删除为“从无异常”；认证未加固单列运维风险，不以本轮文档授权处理。Owner豆包回执也不能替代新整厂方案视觉审核或真实Truck批准。

### 12.4 版本目标完成矩阵：能力完成不等于版本完成

状态仅用`COMPLETE / PARTIAL / BLOCKED / NOT_STARTED`，每项必须同时读取范围列。

| VERSION_TARGET | CURRENT_STATUS | 已有证据及完成范围 | 距离原目标的缺口 / 完成标准 |
|---|---|---|---|
| `12_ZONE_LAYOUT_GENERATION` | PARTIAL | B0有一个可复现全局12区构造；S1/S2有全组结构合同 | 将全局求解与整厂结构生产生命周期整合，持续生成server-owned完整候选，不是固定旧坐标或传统顺序修补 |
| `MUST_ADJACENCY` | COMPLETE | 固定870d…候选实际7/7，N02/N05/N06；工程Graph未变 | 仅该基线能力范围完成；所有未来候选仍须重新7/7，不能继承此PASS |
| `NON_TRUCK_ACCESS` | COMPLETE | 同一固定候选生产源码Domain/Application11/11、独立几何/共存及typed-Site通过 | 不包括第12项Truck、不等于新候选全通过或正式Server Replay |
| `TRUCK_ENGINEERING_VALIDATION` | BLOCKED | R13/R14/R15通用软件合成测试成功；N06真实项目来源缺失 | Owner提交真实车辆尺寸、实测入口净宽/限制、批准的完整机动模板与装卸面、原件SHA/姿态/审核；真实绑定与几何通过 |
| `P2D_FULL_PASS` | BLOCKED | 原应用12结果中11 PASS、Truck BLOCKED，`p2_complete=false` | 全部Access、真实Truck、人车交互、Footprint/Site与原应用最终P2D逐项通过；需评审不得转PASS |
| `DISTINCT_FULL_PASS_CANDIDATES` | BLOCKED | 本次可计入新结构full-pass集合为0/5；1个可信construction基线不抵扣 | ≥5个几何/主要组织真正不同、同各自身份完整full-pass的候选及去重证据 |
| `MAJOR_LAYOUT_FAMILIES` | PARTIAL | 3个结构词汇/6个topology plans已实现 | full-pass集合实质结构覆盖≥3；当前可核验合格family为0，不按标签/旋转/微移/尾部置换计数 |
| `PROCESS_FLOW_ASSESSMENT` | PARTIAL | P0/ADR-047指标合同存在，实验有路线长度等局部事实 | 原Receiving映射、实际route顺序/回折/turn/支路等原子指标与解释；verified backtrack=0，缺事实不填0 |
| `REGULARITY_ASSESSMENT` | PARTIAL | 有定性正例、实验比例/面积/并集/轮廓事实 | 完整分组/轴网/进深/轮廓/净效率评价，D02/D03校准及Owner批准；0.90目标不是已生效gate |
| `QUALITY_RANKING` | NOT_STARTED | 原P2B2比较器及隔离软目标/Pareto不等于新生产质量排序 | 对真实full-pass集合实施P0字典序原子比较，输出`WHY_THIS_CANDIDATE_WON`及winner-vs-next，不以加权分抵硬失败 |
| `MULTI_CANDIDATE_GALLERY` | PARTIAL | 实验画图和可信单基线SVG存在，不补造丢失的旧比较图 | ≥5个full-pass、≥3实质结构的同尺度/方向整厂图集与真实质量对照 |
| `OWNER_VISUAL_ACCEPTANCE` | NOT_STARTED | P0C参考overlay已审核；豆包合成Truck SVG有Owner显示成功回执 | 针对最终新5/3整厂集合的Owner视觉判断/签认；两类历史回执不抵扣 |
| `TOOL7_NEW_LAYOUT_CHAIN_INTEGRATION` | NOT_STARTED | 原Tool7仍在；新上线的是Tool8，不是CP-SAT多方案自动布局链 | server-owned多结构构造→工程full-pass→质量排序→多方案图纸真实接入Tool7，兼容全部8工具 |
| `VERSION_RELEASE_ACCEPTANCE` | BLOCKED | 功能子集已生产集成/部署；PR仍Draft未合并 | 5/3、零回折、质量/校准/视觉/Tool7、真实工程链和版本closure全部闭环；Ready/Merge/Release/Deploy各自另授权 |

独立通道几何“可共存”不自动等于P0质量层的`PERSONNEL_LOGISTICS_SEPARATION=PASS`；实际共享/交叉及其工程使用策略仍须按原权威和Owner评审分别判定。

### 12.5 P3历史与正式决策继续保留

1. **三条证据链分开：** 原P3证明机制（E15–E19/C09）≠独立CP-SAT实验（N01/N02）≠固定完整候选的正式源码工程验证（N05/N06）。B0或11 Access成功不能证明历史全部partial存在joint capacity。
2. `P3_COMPLETE=false`；原P3-R4的317个accepted partial中55 SUPPORTED、262 accepted joint UNKNOWN保留，另10个root UNKNOWN按原分母保留。`ACCEPTED_PARTIAL_WITH_UNKNOWN_COUNT_TARGET=0`未被本节取消；不能自动重算262为0或以新求解器成功豁免旧门禁。
3. D01职责、D03-GRID与D03-GROUP、D04架构级round ledger仍为`DIRECTION_APPROVED_FORMAL_AMENDMENT_PENDING_OWNER`。0.90产品目标与numeric gate校准状态分离；P0的Secondary归FINISHED_SIDE与当前P1A归PROCESSING_CORE差异仍须具名正式决定，不以“意思相同”消解。
4. `MAX_RECOVERY_ROUNDS_PER_ARCHITECTURE=2`及原停止规则保持。全局R1–R15的主实现/布局优化/证明/诊断/环境恢复/代码集成/部署应按真实行为分类并补齐D04授权映射；不能用新编号或MCP上线自动清零计数。已有后续Owner单项授权不是本计划追认一切架构例外。
5. D06须区分**已另获授权并执行的R9–R15工作**与未来未授权工作；本次只登记事实，不再把已做范围称为未授权，也不由已做范围推导后续任务获批。D05未来正式编号仍待批准；D07本次仅doc commit/push已授权，计划冻结/原合同修订仍未授权。
6. 正式资源合同不变：`PLACEMENT_NODE_BUDGET=60000`、`ACCESS_ROUTE_NODE_BUDGET=20000`、`TRUCK_NODE_BUDGET=20000`、`JOINT_EVALUATION_CAP=256`、`JOINT_ORIGIN_EVENT_CAP=1024`、`EXISTING_JOINT_WORK_PROTECTION=8192`；Host保护沿实际冻结合同。CP-SAT原生branches/conflicts/wall time不是RS primitive work，实验账本不能静默变成生产资源合同，也不能为新family重置预算。

### 12.6 剩余工作包：交付顺序、依赖和具体完成标准

沿用第4.4节`REVIEW-*`映射；“阶段A/B”只是同一工作包内的交付切片建议，不是新正式TASK_ID或恢复额度。所有未来实施均为`NOT_AUTHORIZED_BY_THIS_DOCUMENT`。第一项是整合已有真实成果，不是再开展无边界证明研究。

| TASK_ID或待批准工作包名称 | OBJECTIVE | DEPENDENCIES | DELIVERABLES | ACCEPTANCE_GATES | CURRENT_STATUS | EVIDENCE_REFERENCE | BLOCKERS | OWNER_AUTHORIZATION |
|---|---|---|---|---|---|---|---|---|
| `REVIEW-SAFETY-CONTRACT`（开工前具名决策） | 确认CP-SAT整合与原整厂架构、安全证明职责/轮次适用关系 | C02/C06/C08/C09、D01/D03/D04及本对账 | 具名合同适用/历史保留/架构身份与轮次结论；下项allowlist和验收 | 不把历史UNKNOWN改PASS、不降低5/3、不改工程权威/预算、不以改名重置恢复；批准与实施分开 | BLOCKED：方向已同意、正式修订待批 | 第8节、12.5、N02 | D01/D03/D04正式决策 | 本轮仅审核增补；正式合同修订与新实施另批 |
| `REVIEW-MULTI-CANDIDATE`阶段A：整厂结构生产整合（建议下一开发） | 将可信全局求解成果纳入group/band/domain→全12区联合求解，不固定历史房间/后补尾部 | 上行Owner决定；N02–N05、原Plan/Handoff/Authority | 生产适配器、输入/候选身份与来源、完整房间/Portal/Corridor/拓扑模型、确定性与累计资源账本、测试 | ≥1个server-owned完整construction candidate，12区/7 MUST/Site/全障碍/尺寸旋转/非重叠，独立11 Access/共存/Packaging及原Footprint/Site；明确仍非真实Truck/P2D；不得假造Mapping为server-produced | PARTIAL实验基础；生产整合NOT_STARTED | C06/C08/C09、N02、N05/N06 | 求解器依赖/资源映射与结构兼容范围须批准；旧P3未被解决 | 待批准正式TASK_ID、代码/依赖allowlist及资源映射；不增加原预算 |
| `REVIEW-MULTI-CANDIDATE`阶段B：多结构生成 | 生成至少5套不同construction candidates，覆盖≥3种实质组织 | 阶段A的生产全局生成入口 | 候选池、几何/主要band/主工艺结构去重、family coverage与搜索截断证据 | 全角色同时建模、每候选独立硬复核；不是标签、旋转、微移或尾部置换凑数；construction数量和full-pass数量分栏 | PARTIAL结构词汇；合格多结构集合未交付 | E05/E06、N02、12.4 | family覆盖与有限模型域需明确；不足只能UNKNOWN/未达成 | 待另行授权；不得借family循环重置预算 |
| `REVIEW-HARD-VALIDATION` | 对每个新候选取得真实完整工程full-pass | 阶段A/B候选身份；Owner真实Truck来源/实测入口与装卸/批准模板 | 各候选12 Access、Truck链/包络、人车交互、typed-Site、实际通道并集/原Footprint、原应用P2D完整输出 | 每个计数候选所有原门禁PASS，`p2_complete=true`；待工程评审不得转PASS；最终≥5 distinct full-pass且≥3实质结构；不得跨候选拼结果 | BLOCKED_REAL_TRUCK_INPUT | N05/N06、C06/C08 | 缺真实车辆及工程批准，合成模板不能填补 | Owner先给输入并批准验证；合成软件验证可单独授权但不得计真实验收 |
| `REVIEW-NUMERIC-CALIBRATION` | 完成可比正例与数值gate批准依据 | Owner室级/建筑/route正例与用途标注，D02/D03 | 数据来源/精度/eligibility/classifier版本、进深/轮廓/轴网原子测量及阈值提案 | 保留0.90产品目标；不猜depth/compactness/appendage阈值，正式批准前不启用；不可比资料不得充正例 | BLOCKED_OWNER_INPUT | C02–C05/C07、D02/D03 | exact正例、用途和标注粒度未齐 | 与构造可并行取证，取证/阈值冻结/实施分别授权 |
| `REVIEW-QUALITY-ASSESSMENT` | 自动计算并解释工艺与规整度原子事实 | 实际同候选route/portal与项目Receiving映射；批准的指标/校准版本 | 顺序、回折/turn、支路、功能组、轴网/进深、轮廓/凹口、实际路线与效率、人员物流分离质量sidecar | 主流程顺序正确、verified backtrack=0；普通场地turn目标与例外按C02；所有所需事实有来源/单位/版本/状态，缺失不填0/PASS；不以中心距代route | PARTIAL合同/实验指标；正式实现未完成 | C02/C07、N02/N05 | Owner Receiving映射、D02/D03、可比最短路径依据 | 可先批准事实提取，与A/B并行；最终质量验收依赖真实工程结果与校准 |
| `REVIEW-QUALITY-RANKING` | 工程full-pass后质量优先选择 | 至少可比较的full-pass集合+上行质量事实 | 原子字典序排序、候选对比、`WHY_THIS_CANDIDATE_WON`、winner-vs-next | 原P0顺序：process order→backtrack→turns→required adjacency→grid→depth→compactness→route efficiency→branches→personnel/logistics，最后原P2B2 tie-break；不以加权总分掩盖硬失败/UNAVAILABLE | NOT_STARTED（旧P2B2不是本项完成） | C02/C07、第6.1节 | full-pass和完整quality事实未齐 | 待独立授权，不提前改selector |
| `REVIEW-OWNER-GALLERY` | 交付可审核的多方案整厂图集 | ≥5 full-pass、≥3实质结构、完整质量事实 | ≥5套统一坐标方向/比例/配色整厂图，12区、主流/支路、人员/货车入口、Shipping装卸面、建筑与障碍、质量值齐全 | 图纸从各自已验证JSON/route生成；Hash/几何一致；Owner对工艺清晰、分组、轴网、轮廓及分离做具名视觉判断 | PARTIAL绘图基础；最终图集及视觉审核未开始 | C06/C08、N02；N11不抵扣 | 合格多方案不足；需要Owner视觉判断 | 图集规格可并行审核；生成和最终签认分别授权，不是施工图 |
| `REVIEW-TOOL7-INTEGRATION` | 将新多结构自动布局全链接入Tool7 | 生产全局构造+真实工程验证+质量排序/图集门禁 | server-owned生成/选择/投影链、兼容公开Schema与8工具、真实业务调用/资源与来源测试 | 不是输入一个实验候选伪Server Replay；不以Tool8替代；同候选完整链和原7/新增8兼容通过 | NOT_STARTED_FOR_NEW_LAYOUT_CHAIN | N05/N08/N10、12.4 | 新布局/质量上游未完成 | 待独立授权；不因现有公网8工具自动接入 |
| `REVIEW-VERSION-ACCEPTANCE-RELEASE` | 正式核验v2.2.2全部产品目标 | 上述交付、D01/D03/D04正式处理、最终exact-head CI和Owner签认 | 5/3去重计数与工程/质量/视觉闭环矩阵、版本说明和指定SHA | 全部原目标实际满足；未决质量/人员车辆交互不得隐藏；版本验收与Ready/Merge/Tag/Release/Deploy分别决定 | BLOCKED，VERSION_COMPLETE=false | C02/C06/C08及本增补 | 真实Truck/P2D、5/3、质量与Tool7链均未完成 | 本轮仅文档提交推送；正式验收、冻结和发布动作均另批 |

**串行主交付：** 具名开工决策 → 整厂生产整合A → 多结构construction B → 每候选真实完整工程验证 → 合格集合的质量排序 → 5/3同尺度图集与Owner视觉审核 → 新链Tool7及正式版本验收。验证可在候选产生后逐个流水进行，不必等候选池全部结束；每条证据仍绑定自身候选。

**可并行但须各自授权：** Owner真实Truck资料准备、人车交互工程决策、Receiving映射；numeric正例取证及校准提案；质量事实提取/测试设计；图集规范审核。它们可与A/B并行，但不能以合成资料填真实工程门禁、以未批准阈值做正式质量判定，或在full-pass前发布质量获胜结论。

**真正的Owner输入与判断：** 实际车辆尺寸及来源、入口实测净宽/限制、批准机动包络/坐标姿态/模板Hash、装卸面确认及审批；人车共享/交叉需要的工程评审；Receiving角色映射；可比较的室级/outline/route正例与用途；numeric gate和分组适用版本决定；最后5/3新整厂方案视觉签认。不得靠fixture-project/fixture-engineer或豆包合成SVG显示成功代替这些输入。

### 12.7 本次文档交付、适用检查与停止边界

本轮唯一允许变更并提交的文件为`docs/tasks/V2_2_2-version-plan.md`。2026-10-09第1–11节保留原文；仅增加顶部导航和本节。当前任务授权该文档正常Commit/Push，不授权改其他源码/测试/合同/历史证据，也不改变原章节当时“未授权提交”的历史事实。

提交前检查实时HEAD仍为`64b842919d0fcb05264b7902e2b3a8a8c1b3a47e`、唯一文件allowlist、历史原文一致、17条本节任务索引及完整字段、14项目标状态、5/3/0回折/0.90目标、262 UNKNOWN与D01/D03/D04保留、相对链接/表格/`git diff --check`。适用文档/架构检查按仓库既有机制执行，不为修改一份计划重跑求解、Truck或服务器验收。

本次实际检查：单文件范围、去掉新增导航后历史全文一致、17条任务索引/14项目标及字段覆盖、目标/UNKNOWN保留、相对链接/表格/代码围栏自检通过，`git diff --check`通过。现有完整Architecture Suite为 **768 passed / 16 skipped**（19.28秒）；未修改测试或运行新布局/Truck验证。本地文档门禁通过不冒充提交后的CI成功。

提交后只读取本次精确HEAD的PR状态/CI。尚未结束写`PENDING`；不得用R14的绿色CI冒充本次文档commit CI。历史归档读验不等于重跑工程PASS，Owner回执不伪装独立复测。计划仍待Owner审核/冻结；`VERSION_COMPLETE=false`、`NEXT_DEVELOPMENT_AUTHORIZED=false`。不Ready、Merge、Deploy，不自动启动任何新布局开发，完成后STOP。
