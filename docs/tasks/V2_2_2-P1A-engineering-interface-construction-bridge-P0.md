# V2.2.2 P1A — Engineering Interface Construction Bridge P0

## PURPOSE

```ini
TASK_ID=V2_2_2_P1A_ENGINEERING_INTERFACE_CONSTRUCTION_BRIDGE_P0
MODE=ENGINEERING_CONTRACT_DRAFT_AND_READ_ONLY_AUTHORITY_AUDIT
AUDIT_HEAD=48ed4b43677b88c43d5dbad46cf66ba9edf38c69
PR_NUMBER=307
P0_CONTRACT_STATUS=OWNER_REVIEW_DRAFT_NOT_FROZEN
CURRENT_ARCHITECTURE=WHOLE_BUILDING_GROUP_BAND_COMPOSITION_WITH_RESERVED_PERIPHERAL_DOMAINS
PREFERRED_DIRECTION=B_COMPOSITION_TO_METRIC_TO_EXACT_ENGINEERING_CONSTRAINT_TRANSMISSION
ARCHITECTURE_RESET_AUTHORIZED=false
PRODUCTION_IMPLEMENTATION_AUTHORIZED=false
FORMAL_CONTRACT_AMENDMENT_AUTHORIZED=false
PACKAGING_IMPLEMENTATION_AUTHORIZED=false
MAX_RECOVERY_ROUNDS_PER_ARCHITECTURE=2
P3_COMPLETE=false
VERSION_PLAN_FROZEN=false
NEXT_PHASE_AUTHORIZED=false
```

本文件仅为Owner审核草案，不替代现有合同/ADR，不改变runtime，也不授权下述实现。
保留B/C hybrid整厂组织，使既有工程要求在构造之前可见、在metric层可核验，
而不是继续把HARD接口证书数量当作布局可用性的代理。
版本目标仍是至少5个distinct structured P2D full-pass、3类实质主要结构，
以及工艺、规整度、质量排序、同尺度Owner视觉与独立Tool7验收。

## ENGINEERING_AUTHORITY

唯一工程规则来源仍为已有server-owned权威：

- `dimension_handoff.EdgeOrientedConnectionV1`：Packaging LONG_EDGE → Sorting
  SHORT_EDGE_EXIT_SIDE，方向一致，direct/corridor均允许。不得把其改成新增MUST。
- `access_authority`：AccessRequirement/profile；人员portal 1.5m、corridor 2.0m；
  物料/冷间portal 2.4m、corridor 2.5m；Packaging portal 2.4m、corridor 5.0m、
  STRAIGHT_ONLY。这些为当前权威读值，不是本草案制定的新阈值；未来producer须读取来源对象。
- `LayoutAuthorityBindingV1.dimension_authorities`及共享shape helper，禁止复制尺寸推导。
- `ValidatedSiteGeometryV1.site.effective_buildable_boundary`与
  `obstacles.hard_obstacles`，不得bbox代替boundary，不得只读取no-build或升级conditional removal。
- 原process graph的7条MUST、原positive-shared-edge/non-overlap等exact谓词。
- project-bound Truck输入及`truck_maneuver`/`validate_truck_maneuver_chain`。
- 原`route_site_placement`是最终Access、Truck、interaction、footprint、
  `PROJECT_LAYOUT_VALIDATED`和`P2_COMPLETE`权威；construction证书不能替代它。

工程接口projection/intent/metric预检均须声明：
`engineering_authority=false`、`creates_new_hard_edge=false`、
`references_existing_engineering_authority=true`、`is_final_validation=false`。
它们是构造义务，不是新工程标准。

## SCOPE

本P0描述六条工程接口：Packaging→Sorting、Main entrance→Changing、Changing→Sorting、
Sorting→Secondary fruit、Sorting→Frozen、Truck entrance→Shipping。
首个后续实施切片仅Packaging；其它接口只提出传递责任，不实现新router或机动solver。
人员结构序列是Main entrance→Changing→Sorting，不要求新增共享边。
Office保持PERSONNEL_GROUP/PERSONNEL_INGRESS_DOMAIN；Office↔Shipping的既有MUST
不授权人员portal、门洞或人员物流混行。

## NON_GOALS

不reset架构，不恢复#302/#306 main-first/tail-repair，不引入历史/Golden/Xinzhao坐标seed。
不改production/tests/fixture/ADR/已有合同/evidence，不改zone order、family vocabulary、
scheduler、60000 placement节点预算、selector或P2D规则。
不运行新完整搜索或Access/Truck/P2D回放，不替换Truck输入、不做numeric calibration。
不commit/push/PR body/Ready/Merge/Tag/Release/Deploy；不启动R6A或自动进入下一阶段。

## DATA_HANDOFF

```text
ENGINEERING_AUTHORITY
  → COMPOSITION_INTENT (coordinate-free reference / allowed alternatives)
  → METRIC_CONSTRUCTION_CONSTRAINT (independent runtime artifact)
  → EXACT_PLACEMENT_CANDIDATE (same authoritative roles/shapes, exact predicates)
  → ACCESS/TRUCK/P2D_VALIDATION (unchanged final authority)
```

### 独立投影对象建议，非本轮schema实现

建议概念名`EngineeringInterfaceConstructionIntentV1`和独立metric支持结果。
本轮不添加Python类型，不改P0/P1 Plan/Handoff字段。
下一任务须审计serialization消费者并批准版本/兼容策略后才能集成。

| 必需字段 | 语义与校验 |
|---|---|
| SOURCE_AUTHORITY | 原requirement/profile/relation或project binding的identity及版本；不生成第二份规则列表 |
| REQUIRED_ROLES | 原接口端点；entrance为site segment引用而非新增room role；角色仍12个 |
| ALLOWED_GEOMETRIC_RELATIONSHIPS | 按来源保留DIRECT_SHARED_EDGE、CORRIDOR_MEDIATED或outdoor maneuver；合法替代为析取，不强迫共边 |
| EDGE_ORIENTATION | 原edge class/exit-side语义、alignment requirement；未知规则不能猜测 |
| PORTAL_CLEAR_WIDTH | 原profile及cold-room适用规则，引用来源；不是任意门尺寸 |
| CORRIDOR_CLEAR_WIDTH | 原profile，所有实际strip/envelope须满足，direct模式明确NOT_APPLICABLE |
| ROUTE_SHAPE_CONSTRAINT | 原STRAIGHT_ONLY或NOT_FROZEN；NOT_FROZEN不是新直线/转弯限制 |
| SITE_AND_OBSTACLE_SCOPE | validated有效boundary、full hard obstacles、当前placed blockers与source hashes |
| NECESSARY_CAPACITY_CONDITION | 声明保守必要条件及覆盖范围；空间非空不能推出已有可行证书 |
| EXACT_VALIDATION_AUTHORITY | 引用原portal/route/envelope/maneuver/site predicates及最终route_site_placement |
| UNSAT_PROOF_SCOPE | 否定证明覆盖的角色、shape、origin/portal/route替代、整数格、当前partial与遗漏项；无覆盖不能负判 |
| UNKNOWN_HANDLING | 静态无命中/资源耗尽/unsupported geometry/未覆盖替代均UNKNOWN；不可prune或冒充SUPPORTED |
| PROVENANCE_AND_VERSION | graph/zone-plan/P1/composition/handoff/site/obstacle/dimension/profile/relation/project hashes、exact partial hash、policy revision |

metric geometry不写回coordinate-free合同。公共application只接受原始canonical输入，
server-side绑定权威/replay projection，不接受caller metric slot、intent、support state作为authority。
host/domain未拥有最终polygon；不能由SHIPPING_TRUCK_INTERFACE_DOMAIN存在推出车辆空间PASS。

### 各层责任

| 层 | 负责 | 不负责 |
|---|---|---|
| composition | 同时表达整厂group/band/domain及从原工程规则派生的接口引用、允许拓扑/方向语义 | 不给门/通道坐标，不伪造容量、route或Truck PASS |
| metric | 绑定site、shape及当前几何，提出保守必要空间和可核验正向alternatives，记录覆盖/UNKNOWN | 不把有限事件域当全几何域，不生成最终layout |
| exact construction | fixed endpoints精确匹配；候选仍经过全部旧hard checks；消费/更新工程接口义务及诊断 | 不绕过计节点，不用未固定joint witness当模板，不以未知剪枝 |
| final engineering | 原Access/Truck/P2D重新验证实际候选及project inputs | 不用construction预检PASS替代真实调用 |

### A. Packaging→Sorting：两种合法实现必须保留

来源identity：`packaging-sorting-edge-connection@1.0.0`与
`packaging-sorting-straight-access@1.0.0`及原AccessRequirement。
Sorting语义保留SHORT_EDGE_EXIT_SIDE；当前router将它归为SHORT_EDGE，不得擅自发明
新的绝对east/west出口方向，也不得删除原exit-side标识。

**Direct alternative**：从权威旋转后footprint识别Packaging LONG与Sorting SHORT合法门面，
方向/alignment一致，共享segment满足原portal净宽，实际portal按旧谓词复验。
positive shared edge本身不能证明边类或portal合格。

**Straight corridor alternative**：分别选择允许门面和portal interval，形成无转弯的
原STRAIGHT_ONLY中心线及满足5.0m净宽的通道包络，检查effective polygon、full hard
obstacles及当前其它zones，端点进出按既有router/predicate语义，不能用自创碰撞豁免。
同一变量/房间shape及真实fixed geometry须一致。一个具体事件中心点未获证不是所有
portal interval/直线位置都无解。

必要条件提案：合法门面存在且长度可容portal；适用面方向/投影允许直线连接；
直线strip存在落在site必要空间并避开已固定障碍的机会。
所有必要空间必须是合法替代全集的超集，不能把site凹多边形bbox当充分证据。
若无法覆盖全部允许shape、门面、portal位置或corridor替代，则仅可得UNKNOWN。

当前历史direct共边错误只能否定该direct alternative。**只有两类合法实现均被覆盖充分、
可核验且绑定当前条件的证明排除，才允许整个接口PROVED_NO并拒绝candidate。**
不能因为没有straight witness、P2静态域不含、事件扫描cap或当前共享边不对而直接prune。
后续实现若做不到该soundness，应保留UNKNOWN并报告，不修改判据“证明成功”。
已有正向support为advisory，可迁移，非硬锁；后续未放置房间仍可能堵通道，完整候选须终验。

### B. 人员入口→Changing→Sorting

从ValidatedSite的实际main entrance segment绑定人员域，不只取“与Sorting相反侧”。
传递两条原Access需求的允许portal面、1.5m门净宽、2.0m通道机会及当前blockers。
composition表达入口/人员功能序列；metric评估必要连通余量；最终原router验证实际路径。
NOT_FROZEN不能解释为STRAIGHT_ONLY。ROUTE_SEARCH_EXHAUSTED不证明物理无路。
人员/Truck交叉及共用通道仍由原interaction政策评价，Office↔Shipping不新增权限。

### C. Secondary/Frozen支路

两条原MATERIAL Access从Sorting独立投影：portal2.4m、corridor2.5m，无新增MUST。
结构表达支路出口、与主流的层级和可共享/分离空间建议；metric保留可用face与通行净空
必要域，诊断支路间/主工艺/其它placed zones的竞争。
保持整厂轴网意图，不以人员或主通道的未经验证占位解决支路。
逐边witness不同不代表joint走廊都可用；若联合容量未证明，明确UNKNOWN，不做联合PASS。

### D. Shipping与Truck

工程传递需同时绑定Shipping权威shape、合法loading face alternatives、真实truck入口、
车辆reference pose、批准templates及maneuver envelope；terminal side仅为结构意图。
metric必须区分：

1. 必要参考点/姿态可达性（给定允许变换/串接域下）；
2. 已提供且批准的template覆盖范围；
3. transformed envelope在site/full obstacles/placed zones中的容量；
4. 原Truck chain验证实际输出。

模板域不可达只可声明给定模板域、当前face/输入下不可达，不声称全局车辆无路。
schema接受不等于工程扫掠代表性。未知/未签认project材料不得冒称真实项目就绪；
本轮不制造、替换或弱化模板，也不修改Truck validator。

## SAFETY_INVARIANTS

1. 所有新构造projection引用已有工程authority，原7MUST及12roles不变。
2. 必要条件只用于sound exclusion；必要域非空不是充分正证书。
3. 支持证书必须用当前fixed endpoints和原exact predicates复验；authority/partial/domain
   revision改变即失效，cache/backtracking不得污染parent/sibling。
4. UNKNOWN可继续，不可当正容量或负证明；资源耗尽无hard prune权限。
5. direct与corridor为合法析取；direct不合格不能隐式删除corridor。
6. 原node accounting、normal fallback及budget/scheduler/order不变。查询工作单独统计，
   查询资源契约和消费者schema修改均须单独批准。
7. 不把positive共享边等同通道/门，不把structural host等同最终metric footprint。
8. D01现行`ACCEPTED_PARTIAL_WITH_UNKNOWN_COUNT=0`仍未被正式修订；此草案不将P3改PASS。

## ACCEPTANCE_GATES

### 本轮P0文档门禁

仅指定新增文档；所有其它分析外置；authority矩阵具备13字段；D04未定归属不猜额度；
Truck原字节/来源/模板变换分层审查；静态检查及Git唯一文件范围通过。
不要求P0跑production replay/CI或证明Packaging已经恢复。

### 后续Packaging机制验收提案（待Owner单独授权）

- server-owned权威来源与provenance正确，坐标free合同保持；无role-specific recovery。
- 原direct正例和合法straight corridor正例均可获证；错误共享边仍保留未排除corridor。
- 独立小型整数毫米穷举验证必要传播不丢合法解，原portal/site/obstacle/overlap谓词复验。
- 覆盖错误朝向、宽度不足、corner、直线阻挡、资源/不完整域UNKNOWN、revision及回溯。
- 非充分负证明不能prune；未知不能SUPPORTED；原工程authority及P2 public结果/R1 parity不变。
- 不删除现行joint测试或零UNKNOWN门槛；独立Packaging切片PASS不等于P3完成。

## BUSINESS_OUTCOME

后续实施必须至少生成1个**新的、真实geometry不同于历史失败候选**的完整12区candidate，
并由原Access验证器实际给出Packaging→Sorting PASS，完整保存geometry/source hashes。
不得以仅hash/provenance变化、排除旧候选而剩0、新证书数或CI覆盖率代替业务结果。
placement保持60000，其他11条Access、Truck和P2D结果真实报告，BLOCKED/未评估与FAIL分开。
Packaging单项PASS绝不等于P2D full-pass。若只有排除、无新合格完整candidate，则业务FAIL；
若前置权限/输入/架构或资源能力无法满足，报告BLOCKED及证据，不放宽门槛。

该切片不承诺一次达成5/3。现有`candidate_by_family`每family首解即停，单次最多3个。
需后续独立提出多候选输出契约任务：在原预算治理下记录每family/composition实际几何、
工程验证、band/main-process组织和结构去重；不能用重复调用、微平移、mirror、hash或tail
置换凑5个。该任务编号、scheduler/终止策略和资源契约待批准，本轮不修改枚举器或selector。

## REGRESSION_REQUIREMENTS

后续具名allowlist必须包括P0/P1 coordinate-free/ownership、原process graph、dimension/shape、
ValidatedSite/full obstacles、P2 public hash及runtime count/digest、R1 parity、existing exact
construction、Access/Truck/P2D、server hash-only replay及geometry保真；新增独立oracle测试。
真实canonical replay与工程验证次数/预算须由下一任务明确授权，CI另验exact-head。
本轮仅文档静态检查，不执行这些runtime suites。

## OWNER_DECISIONS_REQUIRED

1. D04核定B/C hybrid identity、主实现与mixed correction归属，逐条确认原两轮计数及任何真实
   例外依据；本轮不追认例外，剩余额度UNKNOWN，ARCHITECTURE_REVIEW_CLOSED=false。
   D04未决恢复轮次归属状态：REQUIRES_OWNER_CLASSIFICATION。
2. D01 A安全准入/B联合正覆盖/C完整工程职责正式修订与现行P3门槛保留/迁移方案。
3. 批准此P0正式文字、producer/consumer/schema边界及后续Packaging独立TASK_ID/allowlist/
   机制与业务门禁、query资源契约、rollback、主尝试/修正/stop规则。
4. Truck真实项目模板/姿态/扫掠与入口/装卸权威材料由输入方提供并签认；schema不替代review。
5. 多候选输出契约另批准，5full-pass/3实质结构和质量/视觉不变；D03原合同冲突与numeric
   校准另决，不在本草案消除。

下一Packaging实施当前受D04未决与未获单项实施授权阻断；P0审稿可以完成，不自动开放实施。
回滚提案为具名commit后的Owner授权normal revert，不force/reset、不删除历史证据，
不把关闭新门禁当成功。出现范围漂移、权威变更、预算/调度依赖、unsound negative或无候选，
立即STOP，不自动开启恢复轮次。

## 审查来源与本轮交付

HEAD-pinned源码：`domain/dimension_handoff.py`、`access_authority.py`、`access_routing.py`、
`truck_maneuver.py`、`composition_placement.py`；原P0/reset、ADR-049/050及version-plan。
上一评审目录`/Users/charles/codex-r3-isolated.m45h1H/architecture-review.WMo1oB/`，
其manifest与报告hash已核验；D06固定candidate证据不重放、不注入runtime。

本轮独立目录：`/Users/charles/codex-r3-isolated.m45h1H/engineering-bridge-p0.92qZbY/`。
包含D04审查、Truck五层判定、13字段authority matrix、后续P1提案与source_manifest。
外部审计仅为本地可追溯证据，未独立归档。唯一仓库新增为本文件，未提交/未推送。
