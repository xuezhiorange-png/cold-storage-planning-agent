# V2.2.2 版本开发总计划 — Owner 审核草案

> **DRAFT / NOT FROZEN / DOCUMENTATION ONLY。** 本文是对既有合同、任务和证据的对账，不替代或修改原始权威合同，不授权任何实施。待 Owner 审核后，文档提交、计划冻结及后续任务分别授权。

```ini
TASK_ID=V2_2_2_VERSION_MASTER_PLAN_RECONCILIATION_R1
MODE=DOCUMENTATION_ONLY_OWNER_REVIEW
OWNER_REVIEW_CORRECTION_TASK_ID=V2_2_2_VERSION_MASTER_PLAN_OWNER_REVIEW_CORRECTION_R1
OWNER_REVIEW_CORRECTION_MODE=DOCUMENTATION_ONLY_REVISION
OWNER_REVIEW_FRAMEWORK_STATUS=CONDITIONALLY_ACCEPTED_NOT_FROZEN
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
| D01 P3职责/验收 | A安全容量门禁、B联合正证明覆盖率、C完整Access/Truck/P2D工程验证是否分别承担验收责任 | 明确三层invariant、证明范围、UNKNOWN处理、正式合同/ADR050/测试变更allowlist | 现行零UNKNOWN强验收与历史PARTIAL保留，P3=false，R6A=false | 建议分别评审安全性与正证明覆盖，不以C成功倒推全部partial具备B；责任拆分仅为提案 | PENDING_OWNER | 若批准新责任划分，须另行授权合同/ADR/测试及实现变更；本轮不执行、不降低现行门槛 |
| D02 numeric calibration | room-level depth、exact正例outline、appendage purpose如何取得和标注 | 可比样本、eligibility/classifier版本、阈值提案与Owner批准 | numeric P1B BLOCKED，不能宣称规整度PASS | 先批准取证协议和可比粒度；depth0.80不冻结，occupancy/notch/appendage不猜值 | PENDING_OWNER | 取证、阈值冻结、runtime评价各需独立授权；当前不改数值门槛 |
| D03 原始合同差异 | 冲突一：P0的grid 0.90目标与ADR-047未校准numeric gate；冲突二：P0将secondary_precooling_room归FINISHED_SIDE_GROUP，P1A reset归PROCESSING_CORE_GROUP | 分别裁定目标与可执行gate的关系、功能组归属及迁移/兼容要求；明确哪份合同如何正式修订 | 两项实际权威冲突保留，不能假设一致；不改原始合同、不重写角色归属 | 建议先做两项独立裁决，不以band映射解释自动消解functional group冲突 | PENDING_OWNER | 若需修改合同、group mapping或评价阈值，须另行批准范围及回归要求；本轮无任何权威变更 |
| D04 round ledger/architecture stop | 各轮对应架构、主尝试、修正行为、Owner授权及原两轮限制归属，见8.1独立账本 | 对REQUIRES_OWNER_CLASSIFICATION逐项裁定，形成架构计数及例外授权记录 | MAX=2保持；不根据改名/新子链自动重置；不补造历史豁免 | 建议先冻结账本分类和剩余可执行范围，再讨论下一轮 | PENDING_OWNER | 分类未完成不授权新恢复；历史明确任务授权不自动等于两轮规则豁免 |
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

唯一仓库新增文件：`docs/tasks/V2_2_2-version-plan.md`。现有合同/ADR/production/tests/evidence均不改。本轮审查不是新搜索、测试或工程验收，不产生新的P3业务PASS。执行文档字段、内部链接/证据存在、冻结目标和只改一文件的只读自检；不运行runtime suites或CI。

仓库外审查来源快照：`/Users/charles/codex-r3-isolated.m45h1H/version-plan-review.mhUKrM/` 中 `source_manifest.json`、三个 `pr-*-read-only-snapshot.json` 和只读capture脚本。它们记录当时完整SHA/来源digest，非正式入库evidence、非计划冻结。R5报告及相关CSV/JSON明确为 `LOCAL_ONLY_NOT_INDEPENDENTLY_ARCHIVED`；后续独立归档须Owner另行授权，本草案修订不授权归档。

版本任务完整性仅限“现有已知任务和已识别剩余工作包完成盘点”；38项、4组及全部9字段保留，未批准的未来正式TASK_ID不是冻结完成。

本次Owner审核修订完成意味着 **OWNER_REVIEW_CORRECTION_READY**，`PLAN_STATUS=OWNER_REVIEW_DRAFT_NOT_FROZEN`。版本表框架有条件通过不等于D01–D07已裁决，不是v2.2.2、P1A或P3完成。等待Owner正式批准；不commit、不push、不改PR body、不Ready/Merge、不Tag/Release/Deploy、不启动R6A或其他实施。
