# V2.2 — 受场地边界约束的工厂平面规划

## V2.2.1 P0 layout drawing style contract freeze (2026-09-20)

V2.2.0 已正式发布。V2.2.1 P0 只冻结 CAD-style drawing presentation
contract；它不修改 V2.2.0 的工程布局、P2/P2D/P3 runtime、MCP、数据库或发布
状态。历史 V2.2.0 blocks below remain historical snapshots.

详见 [`V2_2_1-P0-layout-drawing-style-contract.md`](V2_2_1-P0-layout-drawing-style-contract.md)
和 [ADR-045](../architecture/ADR-045-layout-drawing-style-projection.md)。

```ini
TASK_ID=V2_2_1_P0_LAYOUT_DRAWING_STYLE_CONTRACT_FREEZE_R1
BASE_RELEASE=v2.2.0
BASE_MAIN_SHA=34cd6b56c1d79dde9730898c6bd46e295e423334
TARGET_VERSION=v2.2.1
ACTIVE_GOVERNANCE_LANE=V2.2.1_P0
CURRENT_RELEASE=v2.2.0
V2_2_0_RELEASED=YES
V2_2_0_RELEASE_TARGET_SHA=34cd6b56c1d79dde9730898c6bd46e295e423334
STYLE_CONTRACT_CREATED=YES
STYLE_ID=LAYOUT_DRAWING_STYLE_V1
STYLE_NAME=CAD_FACTORY_LAYOUT
CANONICAL_ENGINEERING_AUTHORITY=STRUCTURED_LAYOUT_JSON
SVG_ROLE=PRESENTATION_PROJECTION
PRESENTATION_MODE_FROZEN=YES
ENGINEERING_REVIEW_MODE_FROZEN=YES
MOBILE_PREVIEW_PROFILE_FROZEN=YES
ENGINEERING_SHEET_PROFILE_FROZEN=YES
LAYOUT_ALGORITHM_CHANGED=NO
P2_CHANGED=NO
P2D_CHANGED=NO
P3_RUNTIME_CHANGED=NO
P4_CHANGED=NO
MCP_CHANGED=NO
DATABASE_CHANGED=NO
IMPLEMENTATION_STARTED=NO
P1_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_AUTHORIZED=NO
RELEASE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## V2.2.1 P1A canvas/viewBox/page composition (2026-09-20)

P0 is merged. P1A is the separately authorized presentation-runtime
correction for the existing P3 SVG only. It separates authoritative
engineering geometry bounds from page-layout bounds and provides deterministic
`PRESENTATION`, `MOBILE_PREVIEW` and `ENGINEERING_SHEET` compositions. It does
not change any P2/P2D geometry, candidate selection, routing, truck validation,
MCP contract or engineering formula.

详见 [`V2_2_1-P1A-canvas-viewbox-page-composition.md`](V2_2_1-P1A-canvas-viewbox-page-composition.md)。

```ini
TASK_ID=V2_2_1_P1A_CANVAS_VIEWBOX_PAGE_COMPOSITION_R1
BASE_MAIN_SHA=00f684b994c22fbab85227a6ae7b88ff8f697f54
TARGET_VERSION=v2.2.1
ACTIVE_GOVERNANCE_LANE=V2.2.1_P1A
ENGINEERING_BOUNDS_SEPARATED=YES
PAGE_LAYOUT_BOUNDS_SEPARATED=YES
PRESENTATION_OCCUPANCY>=0.70
MOBILE_PREVIEW_OCCUPANCY>=0.80
ENGINEERING_SHEET_OCCUPANCY>=0.70
LAYOUT_ALGORITHM_CHANGED=NO
P2_CHANGED=NO
P2D_CHANGED=NO
P4_CHANGED=NO
MCP_CHANGED=NO
DATABASE_CHANGED=NO
P1B_AUTHORIZED=NO
P1C_AUTHORIZED=NO
P1D_AUTHORIZED=NO
P1E_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_AUTHORIZED=NO
RELEASE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## V2.2.1 P1A2 presentation/mobile composition correction (Draft review)

P1A2 is a projection-only correction after visual review. It hides
engineering-review-only truck/corridor/portal overlays from the default
presentation and mobile views, and adds a deterministic primary-plan focus
with a small full-site context inset. The structured validated layout remains
the only geometry authority.

```ini
TASK_ID=V2_2_1_P1A2_PRESENTATION_MOBILE_COMPOSITION_CORRECTION_R1
PREVIOUS_HEAD_SHA=436c7923c9bd6f1da00b857465e1fdc81f1fdae7
PRESENTATION_REVIEW_OVERLAYS_HIDDEN=YES
MOBILE_REVIEW_OVERLAYS_HIDDEN=YES
ENGINEERING_REVIEW_OVERLAYS_PRESERVED=YES
PRIMARY_PLAN_BOUNDS_IMPLEMENTED=YES
SOURCE_ENGINEERING_GEOMETRY_CHANGED=NO
P2_CHANGED=NO
P2D_CHANGED=NO
P4_CHANGED=NO
MCP_CHANGED=NO
DATABASE_CHANGED=NO
P1B_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
```

## V2.2.1 P1B monochrome CAD visual hierarchy (Draft review)

P1B is the separately authorized presentation-only implementation of the
frozen `LAYOUT_DRAWING_STYLE_V1` / `CAD_FACTORY_LAYOUT` contract. It changes
the default SVG expression from a colorful functional-area map to a
black/white/gray CAD-style hierarchy with explicit W5–W0 stroke levels. It
does not change P1A/P1A2 canvas or focus composition and does not change any
validated engineering geometry or P2/P2D/P4/MCP behavior.

详见 [`V2_2_1-P1B-monochrome-cad-visual-hierarchy.md`](V2_2_1-P1B-monochrome-cad-visual-hierarchy.md)。

```ini
TASK_ID=V2_2_1_P1B_MONOCHROME_CAD_VISUAL_HIERARCHY_R1
BASE_MAIN_SHA=dd26be03438ba7e3b147e5b700e3815d80d70458
TARGET_VERSION=v2.2.1
ACTIVE_GOVERNANCE_LANE=V2.2.1_P1B
P1B_AUTHORIZED=YES
STYLE_ID=LAYOUT_DRAWING_STYLE_V1
STYLE_NAME=CAD_FACTORY_LAYOUT
COLOR_MODE=MONOCHROME_PRIMARY
W5_W0_IMPLEMENTED=YES
P1A_COMPOSITION_PRESERVED=YES
P1A2_FOCUS_PRESERVED=YES
SOURCE_ENGINEERING_GEOMETRY_CHANGED=NO
P2_CHANGED=NO
P2D_CHANGED=NO
P4_CHANGED=NO
MCP_CHANGED=NO
DATABASE_CHANGED=NO
FRONTEND_CHANGED=NO
P1C_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_AUTHORIZED=NO
RELEASE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## V2.2.1 P1E Engineering Sheet composition (Draft review)

P1E is separately authorized to correct only the `ENGINEERING_SHEET` page
composition. It focuses the main view on the authoritative building plan,
retains complete site information in a context inset, preserves full room
dimensions, and separates business-sheet visibility from engineering-review
debug/provenance visibility. A finite `RIGHT_RAIL` → `BOTTOM_RAIL` candidate
order is hard-gated by the existing P1D drawing lint and occupancy floors.

```ini
TASK_ID=V2_2_1_P1E_ENGINEERING_SHEET_COMPOSITION_R1
BASE_MAIN_SHA=2154c869ed202beeeb1903d1875508122a4ed829
ACTIVE_GOVERNANCE_LANE=V2.2.1_P1E
P1E_AUTHORIZED=true
COMPOSITION_IDENTITY=engineering-sheet-composition@1.0.0
ENGINEERING_SHEET_PRIMARY_PLAN_FOCUS=true
ENGINEERING_SHEET_CONTEXT_INSET_VISIBLE=true
FULL_SITE_CONTEXT_PRESERVED=true
ENGINEERING_SHEET_FULL_ROOM_DIMENSIONS=true
P1D_DRAWING_LINT_GATE=HARD_GATE
REPRESENTATIVE_MAIN_DRAWING_OCCUPANCY=0.7008771929824561
REPRESENTATIVE_PRIMARY_PLAN_SCREEN_OCCUPANCY=0.7943176771550949
REPRESENTATIVE_PRIMARY_PLAN_WIDTH_RATIO=0.8998748435544431
REPRESENTATIVE_PRIMARY_PLAN_HEIGHT_RATIO=0.8826979472140762
REPRESENTATIVE_DRAWING_LINT_ERRORS=0
REPRESENTATIVE_DRAWING_LINT_WARNINGS=0
PRESENTATION_SVG_BYTES_CHANGED=false
MOBILE_PREVIEW_SVG_BYTES_CHANGED=false
ENGINEERING_REVIEW_SVG_BYTES_CHANGED=false
ENGINEERING_SHEET_SVG_BYTES_CHANGED=true
SOURCE_ENGINEERING_GEOMETRY_CHANGED=false
ENGINEERING_COORDINATES_MUTATED=false
P2_CHANGED=false
P2D_CHANGED=false
P4_CHANGED=false
MCP_CHANGED=false
DATABASE_CHANGED=false
FRONTEND_CHANGED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

See the [P1E implementation evidence](V2_2_1-P1E-engineering-sheet-composition.md)
and [ADR-046](../architecture/ADR-046-engineering-sheet-composition.md). The
composition is presentation-only; passing automated lint does not replace
Owner visual review or authorize a subsequent phase.

## V2.2.1 P1F cross-fixture drawing robustness (R2 rerun; Owner review pending)

P1F evaluates the existing P1A–P1E drawing output across three reused,
P2D-validated full-chain fixtures and two bounds-only P1E composition cases.
After PR #298 merged the context-inset loading-face correction, the R2 rerun
verified the actual transformed SVG line endpoints against each fixture's
authoritative `shipping_loading_face_segment`. All 12 full-chain profile rows
pass Drawing Lint with zero errors or unavailable required facts, all six
previously failing PRESENTATION/MOBILE combinations now pass, and deterministic
replay is preserved. R2 changes no renderer feature or engineering/runtime
behavior. Owner visual review remains an independent pending gate. The detailed
fixture inventory, generated acceptance matrix, candidate-path checks, exact
SVG hashes, and regenerated viewable PNG/context crops are in the
[P1F robustness report](V2_2_1-P1F-cross-fixture-drawing-robustness.md).

```ini
TASK_ID=V2_2_1_P1F_CROSS_FIXTURE_DRAWING_ROBUSTNESS_RERUN_R2
PR_NUMBER=297
PREVIOUS_PR_HEAD_SHA=0631d9f3410b54ff862406922f110505949ac85f
NEW_BASE_MAIN_SHA=0ba8334a8fd6c4dde5b887c12a6a271d0cad1fce
ACTIVE_GOVERNANCE_LANE=V2.2.1_P1F
FULL_CHAIN_AUTHORITATIVE_FIXTURE_COUNT=3
COMPOSITION_ONLY_FIXTURE_COUNT=2
TOTAL_DRAWING_SCENARIO_COUNT=5
FULL_CHAIN_PROFILE_ROW_COUNT=12
PREVIOUS_FAILED_PROFILE_COMBINATIONS=6
AFTER_FAILED_PROFILE_COMBINATIONS=0
RIGHT_RAIL_PATH_VALIDATED=true
BOTTOM_RAIL_PATH_VALIDATED=true
DRAWING_LINT_FAILED_SCENARIO_COUNT=0
DETERMINISM_FAILED_SCENARIO_COUNT=0
VISUAL_BLOCKER_SCENARIO_COUNT=0
VISUAL_BLOCKER_PROFILE_COMBINATIONS=0
PRESENTATION_CONTEXT_LOADING_FACE_COMPLETE=true
MOBILE_CONTEXT_LOADING_FACE_COMPLETE=true
P1F_AUTOMATED_MATRIX_ACCEPTANCE=PASS
OWNER_VISUAL_REVIEW=REQUIRED
PREVIOUS_BLOCKER=CONTEXT_INSET_MISSING_SHIPPING_LOADING_FACE
PREVIOUS_BLOCKER_RESOLVED_BY_PR=298
PRESENTATION_SVG_SHA256=sha256:e89ca6e1f797fedca41780d2027e728b3a3f37db19c979c0fa9dc863531b2f1a
MOBILE_PREVIEW_SVG_SHA256=sha256:dc0b5313113e69fdfc6c59b88f4bd911316d74b71762bae83768c1bdd70153f2
ENGINEERING_SHEET_SVG_SHA256=sha256:96c82d7296d027a9b41b4b2d8198e7239bed61dbc0811259e0575e2ca3eb25d3
ENGINEERING_REVIEW_SVG_SHA256=sha256:48ea97310b955b3e5b94ea68eebed49c377031c74cb4eeba9db003e36042f37d
REPRESENTATIVE_PRIMARY_PLAN_SCREEN_OCCUPANCY=0.7943176771550949
REPRESENTATIVE_PRIMARY_PLAN_WIDTH_RATIO=0.8998748435544431
REPRESENTATIVE_PRIMARY_PLAN_HEIGHT_RATIO=0.8826979472140762
REPRESENTATIVE_DRAWING_BYTES_CHANGED=false
SOURCE_ENGINEERING_GEOMETRY_CHANGED=false
ENGINEERING_COORDINATES_MUTATED=false
P1G_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

## V2.2 post-P5 CI correction release overlay (2026-09-18)

The P5 readiness snapshot below remains historical. The post-P5 correction was
workflow-only: PR #288 installed the required CJK font in the lightweight lane;
the independent docs-only PR #289 then exercised that lane successfully.

```ini
TASK_ID=V2_2_0_POST_P5_CI_CORRECTION_RELEASE_R1
P5_MERGE_SHA=853db6ecd2acc2a47196feb048a2f860d4b2f6e4
CORRECTION_PR=288
CORRECTION_MERGE_SHA=959c8d00911f7f3075f7bd23be9c1307f4d616c7
WORKFLOW_ONLY=true
PRODUCTION_CODE_CHANGED=false
TEST_SEMANTICS_CHANGED=false
V2_2_RUNTIME_CHANGED=false
MCP_CHANGED=false
DATABASE_CHANGED=false
RELEASE_TARGET_EXACT_MAIN_CI_RUN=35336958482
RELEASE_TARGET_EXACT_MAIN_CI_STATUS=SUCCESS
V2_2_0_RELEASE_TARGET_SHA=959c8d00911f7f3075f7bd23be9c1307f4d616c7
V2_2_0_RELEASE_TARGET_REASON=POST_P5_WORKFLOW_ONLY_CI_PREREQUISITE_CORRECTION
P5_RUNTIME_AUTHORITY_CHANGED=false
RELEASE_BLOCKERS=NONE
TAG_AUTHORIZED=true
GITHUB_RELEASE_AUTHORIZED=true
DEPLOYMENT_AUTHORIZED=false
V2_2_0_RELEASED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## V2.2 P5 current release-closure overlay (2026-09-17)

P0–P4 are merged and V2.2 release closure is separately authorized as a
Draft readiness review. The historical P4 overlay below remains unchanged;
this block is the current state and does not authorize release execution.

```ini
TASK_ID=V2_2_P5_RELEASE_CLOSURE_R1
BASE_MAIN_SHA=31c888f446d2d4c5704221426d60685da91f43d8
TARGET_VERSION=v2.2.0
PREVIOUS_RELEASE=v2.1.2
P0_COMPLETE=YES
P1_COMPLETE=YES
P2_COMPLETE=YES
P3_COMPLETE=YES
P4_COMPLETE=YES
P5_AUTHORIZED=YES
P5_STATUS=RELEASE_CLOSURE_DRAFT_REVIEW
V2_2_0_RELEASE_READY=YES
MCP_TOOL_COUNT=7
REAL_TOOL7_FULL_CHAIN=PASS
PROJECT_LAYOUT_VALIDATED=YES
P2_COMPLETE=YES
RELEASE_BLOCKERS=NONE
RELEASE_TARGET_SHA=P5_FINAL_HEAD_AFTER_EVIDENCE_COMMIT
RELEASE_TARGET_SHA_POLICY=FINAL_P5_HEAD_PLUS_EXACT_MAIN_CI_AND_SEPARATE_RELEASE_AUTHORIZATION
TAG_AUTHORIZED=NO
GITHUB_RELEASE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
NEXT_FEATURE_LANE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

The complete closure evidence is in
[`V2_2-P5-release-closure.md`](V2_2-P5-release-closure.md). The P5 block
certifies readiness only; the older P4 authorization snapshot is retained as
historical evidence.

## V2.2 P4 current implementation overlay (2026-09-17)

P4 has a separate implementation authorization after the P3 projection
boundary. It appends the seventh MCP tool through the existing Doubao/Feishu
Streamable HTTP transport and consumes the already completed P1/P2/P3
authorities. Historical P0–P3 snapshots below remain unchanged.

```ini
TASK_ID=V2_2_P4_MCP_TOOL7_FINAL_INTEGRATION_R2
BASE_MAIN_SHA=efc1ce2e85b55e2e7fb907fee460ea4d2e84dc9d
MAIN_SHA_INTEGRATED=efc1ce2e85b55e2e7fb907fee460ea4d2e84dc9d
P3_COMPLETE=true
P4_AUTHORIZED=true
P4_STATUS=IMPLEMENTED_DRAFT_REVIEW
P4_WIRING_AND_TRANSPORT_IMPLEMENTED=true
P2_VALIDATED_CANDIDATE_SELECTOR_USED=true
P4_CANDIDATE_SELECTION_IMPLEMENTED=false
TOOL7_REAL_FULL_CHAIN_TEST=PASS
FIRST_P2C_CANDIDATE_P2D_RESULT=REJECTED
LATER_FULL_PASS_CANDIDATE_FOUND=true
P4_PRODUCTION_FULL_PASS=true
P4_COMPLETE=true
P4_BLOCKER=NONE
MCP_TOOL_COUNT=7
MCP_TOOL_7_NAME=preview_site_layout
MCP_TOOL_7_POSITION=7
EXISTING_SIX_TOOL_ORDER_PRESERVED=true
EXISTING_SIX_TOOL_CONTRACT_PRESERVED=true
SITE_LAYOUT_PROJECT_INPUT_USED=true
BACKEND_ZONE_PLAN_AUTHORITY_USED=true
P2_VALIDATED_LAYOUT_USED=true
P3_SVG_PROJECTION_USED=true
TRUCK_INPUT_BINDING_SERVER_SIDE=true
NO_CHAT_PARSING=true
NO_ENGINEERING_FORMULAS_IN_P4=true
P5_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

`preview_site_layout` is appended at position 7; the first six tools, their
order and their five-key contract are preserved. Tool 7 requires the five
business keys plus `site_constraints` and a complete project-bound
`truck_access`, then composes the existing canonical zone adapter, P1 handoff,
P2 validated layout and P3 SVG projection. P4 does not add a calculation type,
REST route, formula, second authority, or persistence. It remains a
concept-design response requiring engineering review, not a construction
drawing. See the [P4 implementation record](V2_2-P4-mcp-tool7-doubao-feishu-integration.md).

## V2.2 P2C 当前实现状态（2026-09-15）

Charles 已正式授权 `V2_2_P2C_DETERMINISTIC_PLACEMENT_ENGINE_R1`。P2C 在现有
P2A 几何谓词、P2B1 机动模板边界、P2B2 目标合同和 P1 项目 handoff 之上，新增
确定性的 12 区矩形放置 MVP。它可以为代表性工况生成真实的 zone `x/y`、旋转和
三个 flexible zone 的候选尺寸，并按已批准的 MUST/SHOULD 与 loading-side 目标
选择 canonical candidate。

```ini
TASK_ID=V2_2_P2C_DETERMINISTIC_PLACEMENT_ENGINE_R1
TARGET_VERSION=v2.2.0
BASE_MAIN_SHA=776d6836975d5f27a0261820548425e798919f03
ACTIVE_GOVERNANCE_LANE=V2.2_P2
P2C_AUTHORIZED=true
P2C_STATUS=IMPLEMENTED_DRAFT_REVIEW
PLACEMENT_SEARCH_IMPLEMENTED=true
PLACEMENT_SEARCH_PROFILE_IDENTITY=deterministic-placement-search@1.0.0
PLACEMENT_RESULT_IDENTITY=site_constrained_factory_layout@1.0.0
PLACEMENT_ZONE_COUNT=12
MUST_ADJACENT_COUNT=7
SHOULD_ADJACENT_COUNT=5
ROUTING_IMPLEMENTED=false
ACCESS_ROUTE_VALIDATED=false
TRUCK_ROUTE_VALIDATED=false
PROJECT_LAYOUT_VALIDATED=false
P2_COMPLETE=false
P3_AUTHORIZED=false
P4_AUTHORIZED=false
P5_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P2C 的 `PLACEMENT_FOUND` 只表示有限、确定性 candidate family 找到了满足
放置 hard constraints 的候选；搜索耗尽时返回 `LAYOUT_SEARCH_EXHAUSTED`，不声称
数学上的 `LAYOUT_INFEASIBLE`。它仍不生成 building footprint、portal/corridor
route、truck path 或图纸，亦不改变六个既有 MCP 工具。详见
[P2C deterministic placement engine](V2_2-P2C-deterministic-placement-engine.md)。

## V2.2 P2B2 当前目标合同状态（2026-09-15）

P2A 与 P2B1 已分别提供确定性 site-geometry predicates、项目机动模板合同和
离散变换原语。Charles 现已批准 P2B2 只冻结 objective profile；本阶段不执行
placement search、route generation 或评分计算。详细合同见
[P2B2 objective profile contract](V2_2-P2B2-objective-profile-contract.md)。

```ini
TASK_ID=V2_2_P2B2_OBJECTIVE_PROFILE_CONTRACT_FREEZE_R1
TARGET_VERSION=v2.2.0
ACTIVE_GOVERNANCE_LANE=V2.2_P2
P2_AUTHORIZED=true
P2B2_AUTHORIZED=true
OBJECTIVE_PROFILE_AUTHORIZED=true
OBJECTIVE_PROFILE_IMPLEMENTED=true
P2B2_REVIEW_CORRECTION_R2_APPLIED=true
P0_DECLARATION_ORDER_USED_AS_PRIORITY=false
ROUTE_OBJECTIVE_ORDER_FROZEN=false
PLACEMENT_SEARCH_IMPLEMENTED=false
ROUTING_IMPLEMENTED=false
P2C_AUTHORIZED=false
P2_COMPLETE=false
P3_AUTHORIZED=false
P4_AUTHORIZED=false
P5_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

本次机器合同固定字典序聚合、5 条 SHOULD 等权计数、真实 portal/corridor route
距离、loading-side 两种明确度量和三项暂时关闭的 site/building 指标；目标词汇表
不等于比较优先级，当前 placement 优先级仅为 SHOULD_ADJACENT →
LOADING_SIDE_PREFERENCE，route 优先级尚未冻结；不创建
加权分数、中心点/曼哈顿/直线代理或未经 Owner 确认的人员/车辆分离度量。

## P2B1 当前独立授权与实现状态（2026-09-15）

P2A / PR #279 已在 `ccd6336de4810012deec64c1b0a5f3256ff13d85` 合并。Charles
随后单独批准 `V2_2_P2B1_TRUCK_MANEUVER_TEMPLATE_CONTRACT_R1`，只实现项目提供的
批准机动包络模板合同与精确变换原语；不授权放置搜索、目标函数或图纸。
历史阶段中的 P2 未授权、P2A Draft 和 Option C 待裁决文字是当时快照，继续保留，
不覆盖本节当前状态。

```ini
P2_AUTHORIZED=true
P2B1_AUTHORIZED=true
TRUCK_REPRESENTATION=OPTION_C_APPROVED_MANEUVER_TEMPLATES
TRUCK_REPRESENTATION_OWNER_APPROVED=true
DEFAULT_TRUCK_ALLOWED=false
DEFAULT_MANEUVER_GEOMETRY_ALLOWED=false
KINEMATIC_TRUCK_SOLVER_REQUIRED=false
PLACEMENT_SEARCH_AUTHORIZED=false
OBJECTIVE_PROFILE_AUTHORIZED=false
P2B1_STATUS=IMPLEMENTED_DRAFT_REVIEW
P2_COMPLETE=false
P3_AUTHORIZED=false
P4_AUTHORIZED=false
P5_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P2B1 的三种且仅三种初始机动类别为 `STRAIGHT_APPROACH`、`TURN_90` 和
`DOCK_REVERSE`。模板由项目提供，使用 P2A 的本地米制、0.001m 网格和简单多边形
校验；模板集合可以只包含后续候选真正需要的类别，并通过
`required_maneuver_classes` 表达需求。旧 `TruckProjectAccessInputV1` 不变。
变换只允许 0/90/180/270 度，且不代表车辆运动学或路线可行。

## P2A 当前独立授权与实现状态（2026-09-15）

P1F / PR #278 已合并，基线 `50210aa7cc876ed8a93a099c82ef4a4f287da82a`。
Charles 已单独授权 P2；本轮仅实现 `V2_2_P2A_SITE_GEOMETRY_FOUNDATION_R1`。
历史 P0/P1 authorization block 中的 `P2_AUTHORIZED=false` 保留为当时快照，
不覆盖本节当前状态。

```ini
P1_COMPLETE=true
P1_CLOSURE_BLOCKERS=NONE
P2_AUTHORIZED=true
P2A_STATUS=IMPLEMENTED_DRAFT_REVIEW
P2_PLACEMENT_ENGINE_COMPLETE=false
P2_OBJECTIVE_PROFILE_FROZEN=false
P2_TRUCK_TURNING_REPRESENTATION_FROZEN=false
P2A_TRUCK_TURNING_REPRESENTATION_DECISION_REQUIRED=true
P3_AUTHORIZED=false
P4_AUTHORIZED=false
P5_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
GITHUB_RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P2A 只把 site/buildable polygon、障碍、入口和矩形 hard predicates 做成
确定性基础；不生成 zone/building 位置，不选择 flexible 长宽，不搜索路径，
不实现转弯 solver、SVG、MCP Tool 7 或后续阶段。详见
[P2A evidence](V2_2-P2A-site-geometry-foundation.md)。

## P1F 当前独立授权与 P1 收口（2026-09-15）

P1E / PR #277 已合并，基线 `4244379953028899958ce1579d488288a49c5b82`。
本轮为 P1F contract correction / Draft review。Charles 已裁决货车数值属于每个项目输入，
不属于 P1 的版本级常量。下文 P1E 及更早的“当前”标题、Draft、P1_COMPLETE=false
均保留为历史阶段快照，不覆盖本节当前状态。

见 [P1F 独立合同](../tasks/V2_2-P1F-project-truck-input-and-p1-closure.md)。
新 SiteLayoutProjectInputV1 组合旧 SiteLayoutInputV1 与独立 TruckProjectAccessInputV1；
旧场地 schema 不变，原9 concrete/3 flexible、12 access requirements和净宽规则不变。
未冻结的求解几何只要求版本化项目资料与来源，不发明半径、车型或净空方向。

```ini
TRUCK_ENGINEERING_VALUES_SCOPE=PROJECT_LEVEL_INPUT
TRUCK_VERSION_LEVEL_ENGINEERING_VALUES_REQUIRED=false
TRUCK_PROJECT_INPUT_CONTRACT_COMPLETE=true
P1_COMPLETE=true
P1_CLOSURE_BLOCKERS=NONE
P2_READY_FOR_SEPARATE_AUTHORIZATION=true
PROJECT_LAYOUT_VALIDATED=false
P2A_TRUCK_TURNING_REPRESENTATION_DECISION_REQUIRED=true
P2_AUTHORIZED=false
P3_AUTHORIZED=false
P4_AUTHORIZED=false
P5_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
GITHUB_RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P1 完成不等于具体项目输入齐全，更不等于布局 PASS。缺货车参数仍
PROJECT_INPUT_REQUIRED；齐全也不验证路线，不授权 P2。不关闭无关技术债。

## P1E 当前独立授权记录（2026-09-14）

P1D3 / PR #276 已合并，基线为 `3910b4fbb4dde1952c1e05d2f7720e87119d3b57`。
当前阶段为 P1E 二维通行规则实现 / Draft review；下文 P1D3 等“当前”标题、
Draft 和 access 尚未授权描述均为历史快照，保留原文，不作为本阶段状态。

`V2_2_P1E_ACCESS_PROFILE_AUTHORITY_R1` 的人员、手动托盘搬运、冷间门及
包材直通规则见 [P1E 独立合同](../tasks/V2_2-P1E-access-profile-authority.md)。
新 `p1-dimension-access-handoff@1.0.0` 嵌入原有 dimension handoff；
不修改 9 个已定尺区域、3 个 flexible authority、7 MUST / 5 SHOULD 或面积公式。
本次只验证已提供的净宽/拓扑观察，不生成路径，也不宣称最终布局已可通行。

```ini
P1E_AUTHORIZED=true
DIMENSION_AUTHORITY_COMPLETE=true
PERSONNEL_ACCESS_AUTHORITY_COMPLETE=true
MATERIAL_ACCESS_AUTHORITY_COMPLETE=true
TRUCK_ACCESS_CONTRACT_COMPLETE=true
TRUCK_ACCESS_ENGINEERING_VALUES_COMPLETE=false
P1_COMPLETE=false
P1_CLOSURE_REQUIRES_CONTRACT_DECISION=true
P2_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
```

真正剩余的是货车宽/长、转弯包络、直线进场段、装卸操作净空，以及这些参数
是否作为未来项目级输入的独立合同裁决；不能重复索要已经批准的人员/物料净宽。
本次不改变 SiteLayoutInputV1，不关闭无关技术债，不自动授权 P1 closure 或 P2。

## P1D3 当前独立授权 overlay（2026-09-14）

基线 `a848c2a3b44c6625db7a2546596f4bb3ceb3d7d3`；P1D1 / PR #275 已合并。
当前任务 V2_2_P1D3_FLEXIBLE_RECTANGLE_HANDOFF_CONTRACT_R1，Draft review。
下文旧 P1D1 Draft、8/4 和缺固定尺寸即阻断等文字为历史阶段快照，
不得覆盖本次 Owner 批准的 hybrid handoff。

P0_CONTRACT_SUPPORTS_FLEXIBLE_RECTANGLE=true
P1_REQUIRES_ALL_12_ZONES_FIXED_WIDTH_DEPTH=false
P1_REQUIRES_ALL_ZONES_HAVE_DIMENSION_AUTHORITY=true
P2_WIDTH_DEPTH_SELECTION_SCOPE=FLEXIBLE_RECTANGLE_ONLY

新内部入口 `build_dimension_handoff` / `hybrid_zone_dimension_handoff@1.0.0`，
独立 handoff schema1.0.0；旧 dimension_zones API及八区几何保持不变。
coating/changing/office为FLEXIBLE_AUTHORIZED，不生成width/depth，不是DIMENSIONED。
包材使用批准的整数候选profile；20t为9区DIMENSIONED+3区FLEXIBLE_AUTHORIZED。
现有面积与P1C0 exact/reporting规则不变；不向required_area重复加通道面积。
固定/确定性区不得被P2resize，flexible区可由未来P2在硬约束下选长宽。

包材LONG_EDGE→分选SHORT_EDGE_EXIT_SIDE是必须、方向对齐的独立连接authority，
允许direct或corridor，不加入共边MUST、不重复PACKAGING flow。
分选出口是相对本体短边，具体哪一侧留给P2，非cardinal direction。
office↔shipping不授权人员portal。ACCESS_PROFILE仍待独立P1E；
维持7MUST/5SHOULD，不能据dimension authority完整宣称P1完成或access通过。
SiteLayoutInputV1不变；最终成功layout仍必须输出12区真实具体几何。

详细决策与schema：`docs/tasks/V2_2-P1D3-flexible-rectangle-handoff-contract.md`。
P2实现、Ready/Merge、Tool7、tag/release/deployment均未授权。
本overlay不关闭任何无关技术债、不修改历史授权快照。

## P0 历史授权快照（2026-09-12）

```ini
TASK_ID=V2_2_P0_SITE_CONSTRAINED_FACTORY_LAYOUT_CONTRACT_FREEZE_R1
BASE_RELEASE=v2.1.2
BASE_MAIN_SHA=0a68597a40aa460ed31441c537ca37c3d4cfd1a7
TARGET_VERSION=v2.2.0
CURRENT_RELEASE=v2.1.2
V2_1_2_RELEASED=true
RELEASE_TARGET_SHA=0a68597a40aa460ed31441c537ca37c3d4cfd1a7
ACTIVE_GOVERNANCE_LANE=V2.2_P0
P0_AUTHORIZED=true
P0_STATUS=CONTRACT_FROZEN_DRAFT_REVIEW
P1_AUTHORIZED=false
P2_AUTHORIZED=false
P3_AUTHORIZED=false
P4_AUTHORIZED=false
P5_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
GITHUB_RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
DEPLOYMENT_EXECUTED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

v2.1.2 已发布；早期 release closure 文档中的 Draft / 未授权块是当时的历史快照，保持不变。本任务仅冻结未来能力的合同、权威、schema 和架构边界。

## 版本目标与分期

未来链路：五个业务输入 → canonical zone plan → 12 区面积 → site constraints → zone dimensioning → adjacency / process flow → placement → canonical layout JSON → SVG / PDF / future DXF projection。

当前主工艺物流以 Charles 在 `V2_2_P0_PROCESS_FLOW_AUTHORITY_CORRECTION_R1` 的最终确认为准：

raw_fruit_buffer → primary_precooling_room → sorting_packaging_room → secondary_precooling_room → coating_room → finished_goods_room → shipping_channel

修正基线为 `fe5c1c6f19326f739a55be558403ee7b535f8195`。
主链相邻六对为 MUST_ADJACENT；包材/次果/冻果侧物流不变，具体见当前 P0 合同与 ADR-044。
这是 contract authority correction，不启动 P1；上文初始 P0 授权块保留为历史记录。

| 阶段 | 内容 | 当前状态 |
| --- | --- | --- |
| P0 | Contract Freeze | MERGED，含主物流 authority correction |
| P1 | Zone Dimensioning + Adjacency Engine | P1A/P1B/P1C0/P1C MERGED；P1D1 Owner authority Draft review；非整个 P1 完成 |
| P2 | Site-Constrained Deterministic Placement Engine | 未授权 |
| P3 | Canonical SVG Drawing Projection | IMPLEMENTATION_ACTIVE，Draft review |
| P4 | MCP Tool 7 + Doubao/Feishu Integration | 未授权 |
| P5 | Release Closure | 未授权 |

P1 的完成条件包括容量几何保留、显式定尺 profile、邻接与 access 语义验证；P2 才实现场地放置及可行性判定；P3 只从 canonical JSON 投影；P4 才实现第七个工具。每阶段必须单独授权、测试、Draft review；P0 不授权后续阶段。PDF/DXF 是未来投影方向，不因本分期表自动授权实现。

## 合同入口与未决工程事项

历史 P1A 独立授权：`V2_2_P1A_ZONE_DIMENSIONING_AND_ADJACENCY_FOUNDATION_R1`，
基线 `e963256c56d20f90a880a61d0bc721d28c0a9c38`，ACTIVE_GOVERNANCE_LANE=V2.2_P1。
P1A 仅容量几何保留、定尺 profile 基础与邻接验证；4 区可定尺、8 区缺工程 authority。
详见 [P1A authority matrix](V2_2-P1A-zone-dimensioning-adjacency-foundation.md)。
P1A 已在 `ae9794d0454fa64ba7db6a94d9a3faeba5df00bd` 合并。
历史独立授权 `V2_2_P1B_PRECOOL_DIMENSION_AUTHORITY_R1`，以该提交为基线。
P1B 仅绑定 Charles 确认的 6/8 板位预冷间尺寸及并排组合；见
[P1B evidence](V2_2-P1B-precool-dimension-authority.md)。预期 6 区定尺 / 6 区 BLOCKED。
P1B 已在 `09d9973d1c0fb0ea1ead09601d252c22448d213a` 合并。
历史独立授权 `V2_2_P1C0_AREA_PRECISION_CONTRACT_CORRECTION_R1`，以该 SHA 为基线，
只修正通用 exact/reporting 面积语义；该阶段六区几何不变、sorting 仍 BLOCKED。
详见 [P1C0 evidence](V2_2-P1C0-area-precision-contract.md)。
P1C0 已在 `7785e877461a2c82980ed4e318bd04eabc0287df`（PR #273）合并。
历史独立授权 `V2_2_P1C_SORTING_PACKAGING_DIMENSION_AUTHORITY_R1`：
复用 exact/reporting 合同及上游分选网格，长边乘既定 1.1；7 区定尺、5 区 BLOCKED。
详见 [P1C evidence](V2_2-P1C-sorting-packaging-dimension-authority.md)。
P1C在`4f8c3a0c3b8e866695a917990588caffdd60defc`合并。
当前独立授权P1D1仅实现出货profile、更新办公室邻接并记录包材部分authority。
8区定尺/4区BLOCKED；覆膜、包材、更衣、办公室均不创建尺寸profile。
详见[P1D1](V2_2-P1D1-remaining-zone-owner-authority.md)。
P2/P3/P4/P5、其他四区profile、Ready/Merge、tag/release/deployment仍未授权。

- [P0 合同](V2_2-P0-site-constrained-factory-layout-contract.md)：SiteLayoutInputV1 / SiteLayoutResultV1、几何、流向、错误与可复现性。
- [ADR-044](../architecture/ADR-044-site-constrained-factory-layout-authority.md)：权威分工及现有 capacity geometry 调查。
- 预冷多房间组合尺寸由 P1B 单独确认。精确门宽、车辆转弯包络、人员/重车隔离尺寸、其他非网格区域定尺 profile 尚需工程决策；不得由 Agent 猜测。
- 当前六工具、五 KEY、zone area、factory-power p2、schema p1 均不变。模型不得计算面积、尺寸或工程值；输出为概念规划、需工程复核，不是施工图。

## V2.2 P2D 当前独立授权与实现状态（2026-09-15）

P2C 已合并并提供确定性十二分区 placement；Charles 现已独立授权
`V2_2_P2D_ACCESS_ROUTING_AND_TRUCK_VALIDATION_R1`。本阶段直接消费 P1/P2A/P2B1/P2C
的已验证结果，新增 portal、人员/物料 corridor、包装库直线路径、Option C 货车
机动链、人员/货车交互检查及非优化 building footprint derivation。它不改变面积、
尺寸、placement objective、既有 calculator、MCP 或数据库。

```ini
P1_COMPLETE=true
P2D_AUTHORIZED=true
P2D_STATUS=IMPLEMENTED_DRAFT_REVIEW
P2D_ACCESS_REQUIREMENT_COUNT=12
P2D_ROUTING_IMPLEMENTED=true
P2D_ROUTE_METRICS_AVAILABLE=true
P2D_ROUTE_OBJECTIVE_OPTIMIZATION_ACTIVE=false
P2D_TRUCK_REPRESENTATION=OPTION_C_APPROVED_MANEUVER_TEMPLATES
P2D_PROJECT_LAYOUT_VALIDATION=INPUT_CONDITIONAL
P2_COMPLETE=true|false
P3_AUTHORIZED=false
P4_AUTHORIZED=false
P5_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

`P2_COMPLETE=true` 只表示具体输入的 placement、十二条 access、货车 maneuver、
人员/货车政策和 derived footprint 均已通过；不代表 P3 或任何发布动作已获授权。
没有完整 project-bound truck maneuver input、路线搜索耗尽或出现 engineering review
时，结果保持 fail closed。详见 [P2D evidence](V2_2-P2D-access-routing-and-truck-validation.md)。

## V2.2 P3 当前独立授权与实现状态（2026-09-16）

Charles 已单独授权 `V2_2_P3_VALIDATED_LAYOUT_SVG_PROJECTION_R1`。P3 只消费
P2D 已通过的 `site_validated_layout@1.0.0` 与匹配的已验证 site geometry，生成
`validated-layout-svg-projection@1.0.0` 的静态 SVG。它不重算面积、尺寸、portal、
corridor、loading face、truck route 或 placement，也不创建新的工程 authority。

```ini
P2_COMPLETE_REQUIRED=true
PROJECT_LAYOUT_VALIDATED_REQUIRED=true
P3_AUTHORIZED=true
P3_STATUS=IMPLEMENTED_DRAFT_REVIEW
P3_SVG_PROJECTION_IDENTITY=validated-layout-svg-projection@1.0.0
P3_CANONICAL_LAYOUT_AUTHORITY=STRUCTURED_LAYOUT_JSON
P3_SVG_IS_PROJECTION=true
P3_ZONE_COUNT=12
P3_DETERMINISTIC=true
P3_STATIC_XML_SECURITY=PASS
P4_AUTHORIZED=false
P5_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P3 的输入必须同时满足 `project_layout_validated=true` 与 `p2_complete=true`，
并保留 P2D 的 source hashes、12 区、access、truck maneuver 和 building footprint。
P3 的 SVG 包含 site/buildable constraints、12 zones、portals、corridor envelopes
和 centerlines、entrances、selected loading face、truck maneuver envelopes/reference
paths、dimensions、legend 与 deterministic title block。SVG 不成为 layout authority；
P4 才可能讨论 MCP Tool 7，PDF/DXF 仍是未来独立投影方向。

详见 [P3 evidence](V2_2-P3-validated-layout-svg-projection.md)。

## V2.2.1 P1C 当前独立授权与实现边界（2026-09-22）

`V2_2_1_P1C_ROOM_LABEL_COLLISION_ANNOTATION_R1` 只修正 SVG 投影层的房间
标签、确定性候选锚点、碰撞指标、尺寸标注呈现和业务视图可见性。它复用
现有稳定中文名称，不改变任何工程几何、布局/路由/货车算法、P2/P2D/P4、
MCP、前端、数据库或公式 authority。

```ini
P1C_AUTHORIZED=YES
P1C_STATUS=IMPLEMENTATION_DRAFT_REVIEW
LABEL_FALLBACK_ORDER=3_LINES>2_LINES>1_LINE>NUMERIC_ID
ROOM_LABEL_WALL_CROSSING_COUNT=0
ROOM_LABEL_PRIMARY_COLLISION_COUNT=0
INTERNAL_ZONE_CODE_VISIBLE=false
SOURCE_HASH_VISIBLE=false
PORTAL_DEBUG_TEXT_VISIBLE=false
SCHEMA_IDENTITY_VISIBLE=false
P1A_COMPOSITION_PRESERVED=true
P1A2_FOCUS_PRESERVED=true
P1B_MONOCHROME_STYLE_PRESERVED=true
P2_CHANGED=NO
P2D_CHANGED=NO
P4_CHANGED=NO
MCP_CHANGED=NO
DATABASE_CHANGED=NO
FRONTEND_CHANGED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_AUTHORIZED=NO
RELEASE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P1C 的自动化结果不能替代 Owner 对 representative 20 t/day 图纸的视觉
审核，也不蕴含 P1D、P2、P3 后续授权。
