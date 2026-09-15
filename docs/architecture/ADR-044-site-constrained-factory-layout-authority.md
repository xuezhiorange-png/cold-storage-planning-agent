# ADR-044 — Site-constrained factory layout authority

## P2C 当前实现 overlay（2026-09-15）

P2C 已在 P2A/P2B1/P2B2 的既有合同之上实现
`site-constrained-deterministic-placement@1.0.0`。该 placement engine 只消费
权威 zone plan、P1 project handoff、已验证 site geometry 和已批准 objective profile，
在有限的稳定 anchor family 中放置 12 个矩形区域，并把结果写成
`site_constrained_factory_layout@1.0.0` 的 canonical JSON。

```ini
P2C_AUTHORIZED=true
P2C_STATUS=IMPLEMENTED_DRAFT_REVIEW
PLACEMENT_SEARCH_IMPLEMENTED=true
PLACEMENT_SEARCH_PROFILE_IDENTITY=deterministic-placement-search@1.0.0
PLACEMENT_RESULT_SCHEMA_VERSION=1.0.0
ZONE_AREA_AUTHORITY=COLD_ROOM_ZONE_PLAN
FIXED_RECTANGLE_RESIZE_ALLOWED=false
DETERMINISTIC_GRID_RECTANGLE_RESIZE_ALLOWED=false
FLEXIBLE_DIMENSION_SELECTION_ALLOWED=true
NO_ASPECT_RATIO_AUTHORITY_CREATED=true
MUST_ADJACENT_COUNT=7
SHOULD_ADJACENT_COUNT=5
PLACEMENT_OBJECTIVE_ORDER=SHOULD_ADJACENT,LOADING_SIDE_PREFERENCE
ROUTING_IMPLEMENTED=false
ACCESS_ROUTE_VALIDATED=false
TRUCK_ROUTE_VALIDATED=false
PROJECT_LAYOUT_VALIDATED=false
LAYOUT_INFEASIBLE_PROOF_IMPLEMENTED=false
P2_COMPLETE=false
P3_AUTHORIZED=false
P4_AUTHORIZED=false
P5_AUTHORIZED=false
NO_MCP_TOOL_7=true
NO_SVG_PDF_DXF=true
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

固定/确定性矩形只允许平移和 0/90 度旋转；coating、changing、office 的
`FLEXIBLE_RECTANGLE` 只允许在现有 required area 下选择正的 0.001m 网格尺寸。
所有 zone 使用 P2A 的 exact inside/obstacle/overlap/positive-edge predicates。
MUST adjacency 仍是 7 条，SHOULD adjacency 仍是 5 条；候选比较严格沿用
P2B2 的 placement-stage lexicographic objective，未启用任何 weighted score 或
geometry proxy。

成功结果不等于最终项目布局通过。placement-level observable facts 可以记录
direct shared edge 和 shipping loading face，但 portal、corridor、人员/物料/货车
路线仍是 `PENDING_ROUTE_VALIDATION`。P2C 不生成 building footprint、route、portal、
SVG/PDF/DXF，不改 MCP、frontend、database 或 release boundary。

## P2B2 当前 Owner 决策与 objective contract（2026-09-15）

Charles 已批准 `V2_2_P2B2_OBJECTIVE_PROFILE_CONTRACT_FREEZE_R1`。新增的
`site-constrained-objective-profile@1.0.0` 只记录目标元数据和未来评估边界，
不执行布局放置、路径生成或工程评分。P2C 仍需单独授权。

```ini
OBJECTIVE_AGGREGATION=LEXICOGRAPHIC
WEIGHTED_SCORE=false
OBJECTIVE_VOCABULARY_COUNT=8
OBJECTIVE_STAGING=PLACEMENT_THEN_ROUTE_THEN_FINAL_TIE_BREAK
P0_DECLARATION_ORDER_USED_AS_PRIORITY=false
PLACEMENT_OBJECTIVE_ORDER=SHOULD_ADJACENT,LOADING_SIDE_PREFERENCE
ROUTE_OBJECTIVE_ORDER_FROZEN=false
SHOULD_ADJACENT_EQUAL_PRIORITY=true
SHOULD_ADJACENT_METRIC=SATISFIED_COUNT
SHOULD_ADJACENT_COUNT=5
SHIPPING_TRUCK_ENTRANCE_PROXIMITY_IN_SHOULD_COUNT=false
ROUTE_OBJECTIVES_REQUIRE_ACTUAL_PORTAL_CORRIDOR_ROUTE=true
CENTROID_PROXY_ALLOWED=false
EDGE_MANHATTAN_PROXY_ALLOWED=false
STRAIGHT_LINE_PROXY_ALLOWED=false
CARDINAL_LOADING_SIDE_METRIC=BINARY_MATCH
UNSPECIFIED_LOADING_SIDE_SCORING=DISABLED
NEAREST_TRUCK_ENTRANCE_METRIC=MIN_LOADING_FACE_TO_TRUCK_ENTRANCE_SEGMENT_DISTANCE
NEAREST_TRUCK_ENTRANCE_COMPARATOR=EXACT_MIN_SEGMENT_TO_SEGMENT_SQUARED_EUCLIDEAN_DISTANCE
NEAREST_TRUCK_ENTRANCE_INTERNAL_UNIT=MM2
FLOAT_EPSILON_ALLOWED=false
SQRT_REQUIRED_FOR_RANKING=false
COMPACTNESS_ACTIVE=false
SHAPE_REGULARITY_ACTIVE=false
UNUSED_SITE_EFFICIENCY_ACTIVE=false
DEFER_UNTIL_BUILDING_ROUTE_AUTHORITY_COMPLETE=true
FINAL_TIE_BREAK=CANONICAL_NORMALIZED_FULL_LAYOUT_JSON_LEXICAL
FINAL_TIE_BREAK_AFTER_EXACT_OBJECTIVE_VECTOR=true
RAW_MAPPING_ORDER_ALLOWED=false
HASH_AS_TIE_BREAK=false
PLACEMENT_SEARCH_IMPLEMENTED=false
ROUTING_IMPLEMENTED=false
P2C_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

The eight P0 soft objectives form a vocabulary; their declaration or
serialization order is not a priority order. Lexicographic evaluation is
staged as placement, then route, then the final tie-break. The currently frozen
placement order is `SHOULD_ADJACENT` followed by `LOADING_SIDE_PREFERENCE`.
The route-objective order is not frozen because actual portal/corridor routes
and complete Owner-approved route semantics do not yet exist. The five SHOULD
zone adjacencies are counted equally. The shipping/truck entrance relation
remains a separate access proximity. `UNSPECIFIED` loading side is not scored;
cardinal loading sides use binary match.

For `NEAREST_TRUCK_ENTRANCE`, the business metric remains the minimum distance
between the loading-face and truck-entrance segments, but the ranking
comparator is exact minimum segment-to-segment squared Euclidean distance in
`MM2`. Floating epsilon and square-root ranking are forbidden. P2B2 freezes
this comparator boundary only; it does not implement a segment-distance
evaluator.

Compactness, shape regularity and unused-site efficiency remain disabled. The
existing personnel/truck shared-route prohibition and crossing-review policy stay
in the access authority; P2B2 does not invent a new separation metric.

## P2B2 implementation boundary

The pure domain model and architecture lock are recorded in
`backend/src/cold_storage/modules/layout/domain/objective_profile.py` and
`backend/tests/architecture/test_v22_p2b2_objective_profile_contract.py`.
They do not change P0/P1/P2A/P2B1 geometry, access, calculator, MCP, frontend,
database, or release contracts.

## P2B1 当前 Owner 决策与合同（2026-09-15）

Charles 已正式选择并批准 Option C：`TRUCK_REPRESENTATION=OPTION_C_APPROVED_MANEUVER_TEMPLATES`。
P2B1 只建立项目提供的、批准的、版本化二维机动包络模板合同；模板是后续放置
阶段的输入 authority，不是服务器默认车型、LLM 生成几何或车辆运动学模型。

```ini
TRUCK_REPRESENTATION=OPTION_C_APPROVED_MANEUVER_TEMPLATES
TRUCK_REPRESENTATION_OWNER_APPROVED=true
OPTION_A_REJECTED_FOR_V2_2=true
OPTION_B_REJECTED_FOR_V2_2=true
MANEUVER_CLASSES=STRAIGHT_APPROACH,TURN_90,DOCK_REVERSE
DEFAULT_TRUCK_ALLOWED=false
DEFAULT_MANEUVER_GEOMETRY_ALLOWED=false
KINEMATIC_TRUCK_SOLVER_REQUIRED=false
PLACEMENT_SEARCH_AUTHORIZED=false
OBJECTIVE_PROFILE_AUTHORIZED=false
P2_COMPLETE=false
P3_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

模板使用 P2A 的 `LOCAL_CARTESIAN_METERS`、0.001m 网格和简单 polygon primitive，
通过项目 identity、provenance、reference frame 和 `content_sha256` 绑定。
`TURN_90` 必须明确左右方向；`DOCK_REVERSE` 必须引用
`shipping_channel.LONG_EDGE_LOADING_FACE`。模板集合和
`required_maneuver_classes` 不要求每个项目同时提供三类模板。
`transform_maneuver_template` 只做精确离散旋转/平移，不做 placement、route、
obstacle 或 feasibility solver。旧 P1F `TruckProjectAccessInputV1` 与 P2A
几何 authority 保持不变。

## P2A 当前实现 overlay（2026-09-15）

在已合并的 P1F handoff 之上，`V2_2_P2A_SITE_GEOMETRY_FOUNDATION_R1` 仅新增
`site-geometry-foundation@1.0.0` 的精确二维几何验证基础。输入必须绑定
`p1-project-access-handoff@1.0.0`；site/buildable polygon、入口和障碍使用整数
毫米 predicate，边界/障碍接触规则与 P0 一致。

P2A 不放置 12 区、不选择 flexible rectangle 尺寸、不生成 building envelope、
route、portal 或 drawing。P1 的 9 concrete / 3 flexible dimension authority、
12 access requirements、7 MUST / 5 SHOULD 和所有面积/容量 authority 不变。

```ini
P2A_STATUS=IMPLEMENTED_DRAFT_REVIEW
P2_PLACEMENT_ENGINE_COMPLETE=false
P2_OBJECTIVE_PROFILE_FROZEN=false
P2_TRUCK_TURNING_REPRESENTATION_FROZEN=false
P2A_TRUCK_TURNING_REPRESENTATION_DECISION_REQUIRED=true
P2A_RECOMMENDED_TRUCK_REPRESENTATION=OPTION_C_APPROVED_MANEUVER_TEMPLATES
NO_FLOATING_EPSILON=true
NO_ZONE_AREA_RECALCULATION=true
NO_PLACEMENT_SEARCH=true
NO_MCP_TOOL_7=true
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

Truck width/length and project evidence remain input facts; the three evidence
slots are not turning geometry. The first solver representation remains an
independent Owner decision.

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

状态：P0/P1A/P1B/P1C0/P1C 已合并；P1D1 Owner authority 独立授权、Draft review。
P2/P3/P4 未授权。以下原始 P0 调查和历史 authorization snapshot 保留。
基线：v2.1.2 / `0a68597a40aa460ed31441c537ca37c3d4cfd1a7`。

## 决策

### P1D1 Owner authority overlay（2026-09-14）

基线 PR #274 merge `4f8c3a0c3b8e866695a917990588caffdd60defc`。
出货通道短边固定6.5m，长边为装卸面；每坑2m，坑间及两侧墙净距分别至少2.5m。
长边取 max(2×2.5+N×2+(N−1)×2.5, required_area/6.5)，向上对齐0.001m；
N与面积仅从canonical source读取。20t宽6.5m、深7.693m、实际面积50.0045m²，由面积约束控制。
组合器为zone_dimensioning_foundation@1.4.0，schema1.2.0；不生成基坑位置或场外通路。
office↔shipping_channel追加MUST，office↔primary_precooling_room追加SHOULD；
graph升至charles-v22-process-flow@1.1.0。原主链六对及所有有向流不变。
覆膜无固定尺寸authority，仍BLOCKED；包材仅确认1.2×1.0m模块及长边通道≥3m，
未确认行列和k的通道口径，不实现profile；更衣无新尺寸；办公室仅更新邻接。
共8区定尺/4区BLOCKED，旧七区几何不变。P2、Ready/Merge、发布部署均未授权。
详见P1D1 task evidence；以下为历史阶段快照。

### P1C sorting production overlay（2026-09-14，历史）

独立授权 `V2_2_P1C_SORTING_PACKAGING_DIMENSION_AUTHORITY_R1`，基线为 PR #273
merge `7785e877461a2c82980ed4e318bd04eabc0287df`。sorting 只消费 canonical 上游
已选网格，以 5.6/3.0 节距和 8.0/7.6 边缘空间投影原矩形，长边乘既定 1.1。
不重算人数/台数/面积 authority、不搜索长宽比、不改变 zone planner。
profile 为 `upstream-sorting-long-edge-envelope@1.0.0`；组合器升至
`zone_dimensioning_foundation@1.3.0`，schema 继续 1.1.0（结构未变）。
backend 内部 binder 验证网格、raw area 和 factor，将 raw_required_area_m2 与
sorting_packaging_area_factor 从源快照绑定为 ExactAreaAuthorityV1；reported 值原样保留。
通用 precheck 和最终 model 统一读取 AreaRequirementV1 的几何下限，无 exact 仍严格。
20t 为 45.76×13.60=622.336 m²，reported 622.34 m²；不得补长至 45.761。
原六区记录不变，sorting 新增可定尺，共 7 区定尺 / 5 区缺 authority。
无其他 profile、placement、P2、MCP、发布或部署授权。

### P1C0 面积精度 overlay（2026-09-14，历史阶段快照）

任务 `V2_2_P1C0_AREA_PRECISION_CONTRACT_CORRECTION_R1` 修正 P0 无条件 reported-area 下限。
上游 required_area 原样保留为 reported authority；actual_area 始终是 width×depth 精确乘积。
只有 source/profile 绑定及 reporting projection 均通过的 exact requirement 才作为几何下限；
没有 exact authority 时仍严格比较 reported 值，错误 authority/projection 必须拒绝。
不使用 epsilon、不按 zone 特判、不因 reporting rounding 扩大房间。

AreaRequirementV1 记录两种 authority；ExactAreaAuthorityV1 从不可变源快照的有序 operands
重放 Decimal 乘积，验证 JSON Pointer/值/hash；AreaReportingProjectionV1 单独重放
Python binary64 乘积及 round(...,2)，identity 为
`cold-room-zone-plan-binary64-product-2dp@1.0.0`，不是 ROUND_HALF_UP。
该 provenance 机制不替代 Owner 批准：本轮不绑定任何生产 exact profile。
synthetic 合同允许 45.76×13.60=622.336 和 reported 622.34 同时真实记录，
不把 622.336 改写为 622.34，不把长边改为 45.761。

当前组合器 `zone_dimensioning_foundation@1.2.0`，输出 schema 1.1.0，新增 area_requirement；
历史 1.1.0 语义不静默变更。六区工程几何和容量不变，hash 因版本/元数据升级变化。
sorting 仍 BLOCKED，P1C 正式 profile、其他五区、P2 和发布/部署均未授权。
以下 P1B/P1A/P0 为历史决策，新增 overlay 只修正精度语义。

### P1B 独立 authority overlay（2026-09-14）

`V2_2_P1B_PRECOOL_DIMENSION_AUTHORITY_R1` 单独确认一级/二级预冷采用相同房间几何：
6 板位 `4.90 × 10.05 m`；8 板位 `4.90 × 12.95 m`。
profile 分别为 `precool-room-6-position@1.0.0` / `precool-room-8-position@1.0.0`。
多间长边平行、短边方向并排：width=N×4.90，depth 保持单间深度。
N 和方案只读取上游 reporting scheme，不优化、不重选、不重新计算容量。
42/56 m² 仍仅为上游方案面积 evidence，不反推尺寸；包络不足则 fail closed，不扩大房间。
P1A 的四个 storage profile 不变，其他六区仍缺 authority；历史 P0/P1A 调查保持原文。
当前组合器 identity 为 `zone_dimensioning_foundation@1.1.0`，明确区别 P1A 的 1.0.0；
不是新 zone planner 或 site placement calculator。详见 P1B task evidence。

Agent 理解需求并编排；deterministic calculator 拥有工程计算；deterministic layout engine 拥有定尺、放置和几何校验；MCP 仅桥接工具。JSON 是平面规划权威，SVG/PDF/DXF 是只读投影。现有 `cold_room_zone_plan@1.0.0` 的 `required_area_m2` 是唯一功能区面积权威，site layout 不重算面积。

```ini
AGENT_RESPONSIBILITY=UNDERSTAND_AND_ORCHESTRATE
CALCULATOR_RESPONSIBILITY=DETERMINISTIC_ENGINEERING_CALCULATION
LAYOUT_ENGINE_RESPONSIBILITY=DETERMINISTIC_GEOMETRY_PLACEMENT
MCP_RESPONSIBILITY=TOOL_BRIDGE
CANONICAL_LAYOUT_AUTHORITY=STRUCTURED_LAYOUT_JSON
ZONE_PLAN_GEOMETRY_REUSED_AS_UPSTREAM=true
LAYOUT_DIMENSIONING_HAS_SEPARATE_AUTHORITY=true
UPSTREAM_CAPACITY_GEOMETRY_MAY_BE_REPACKED=false
```

两项 geometry 决策分别管辖容量内部几何和建筑外轮廓，互不替代。布局可以增加包络面积，不能缩减容量或将增加的面积回写成 zone-plan required area。

## v2.1.2 源码调查

调查对象：`backend/src/cold_storage/modules/calculations/domain/zone_planning.py`，固定在上述基线。

`_pack_rectangle` 以 `n_long / n_short` 排列候选，先偏好 `ASPECT_RATIO_MIN=1.67` 至 `ASPECT_RATIO_MAX=2.40`，再比较 unused cells、与 `ASPECT_RATIO_TARGET=2.0` 的距离、面积。这是网格行列比的排序偏好，不是外墙长宽比的硬限制；没有带内候选时算法仍能选择带外候选。`PackedRectangleLayout.to_dict()` 输出的 `layout.aspect_ratio` 也来自网格比。

| 区域 | 现有容量几何 | 布局可复用 / 禁止事项 |
| --- | --- | --- |
| raw_fruit_buffer | `_pack_three_side_aisle_rectangle`；托盘 pitch、三侧通道、n_long/n_short | 保留网格与通道；只允许整体平移、90°旋转和扩大外围 |
| finished_goods_room / secondary_fruit_buffer / frozen_fruit_room | `_pack_one_long_side_aisle_rectangle`；单长边通道 | 同上，不交换内部 pitch/通道语义来挤入场地 |
| sorting_packaging_room | `_pack_sorting_rectangle`；桌距、边部净距、网格；raw area × 1.1 后为 required area | 保留原始桌阵与净距，外包络至少覆盖 final required area；不得重复乘 1.1 |
| primary / secondary precooling | reporting_scheme_id=6_position；schemes 的 room_count、position_count、42/56 m² 单间面积 | 保留选定方案与房间数；没有权威 width/depth 时不能从面积宣称已有房间长宽 |
| office / changing_room / coating_room | 分档固定面积 | 需独立定尺 profile；不套托盘网格比 |
| packaging_material_storage | position count × 单位面积系数 | 数量和面积不变；无已冻结长宽 |
| shipping_channel | platform_count × 平台面积 | 平台数量不变；需明确装卸面和 access profile |

源码未输出一套适用于所有 12 区的建筑 width/depth。P1 application boundary 可读取 canonical metadata 并绑定有版本的定尺 profile，domain 几何引擎只消费验证后的几何需求，不反向依赖 Agent/MCP/DB。必要的几何派生属于 deterministic dimensioning，不属于 LLM；不得复制 zone capacity 或面积公式。精确尺寸不足时应返回 `ZONE_DIMENSIONING_AUTHORITY_REQUIRED`，而不是任意选 2:1 长宽比。

## 接口与取舍

### 主工艺物流 authority correction

`V2_2_P0_PROCESS_FLOW_AUTHORITY_CORRECTION_R1`，基线
`fe5c1c6f19326f739a55be558403ee7b535f8195`：Charles 最终确认主物流为：

raw_fruit_buffer → primary_precooling_room → sorting_packaging_room → secondary_precooling_room → coating_room → finished_goods_room → shipping_channel

一级预冷之后先分选包装，再二级预冷。MUST_ADJACENT 精确为六组：

- raw_fruit_buffer ↔ primary_precooling_room
- primary_precooling_room ↔ sorting_packaging_room
- sorting_packaging_room ↔ secondary_precooling_room
- secondary_precooling_room ↔ coating_room
- coating_room ↔ finished_goods_room
- finished_goods_room ↔ shipping_channel

邻接仍为无向几何关系；物流方向由有向主链单独表达。
packaging_material_storage → sorting_packaging_room、sorting_packaging_room → secondary_fruit_buffer、
sorting_packaging_room → frozen_fruit_room 保持不变。包材分支不再列入六组 MUST 集合。
本修正仅变更合同 authority 和回归锁；不改变 production/MCP/frontend/database/layout engine，
也不授权 P1。历史 P0 snapshot 不覆盖本次当前业务决策。

未来 `site_constrained_factory_layout@1.0.0`、`preview_site_layout`（第 7 位）使用独立 site contract；不改现有五 KEY 或六工具。后端获取并验证 canonical zone-plan，外部传来的 hash 或面积不能自证权威。传给未来引擎的是 backend 绑定的源数据，输出记录源 identity、formula authority、精确源 payload 的 hash 和算法/profile 身份。

第一版使用本地米制平面、矩形区域、0/90°放置；地块可为简单凹多边形。面积足够不代表几何可行。硬约束必须全部通过才返回 available=true；软分数不能抵消越界、重叠、容量不足或 MUST 邻接失败。

概念规划不提供消防、结构、机电详细设计结论；不实现法规退界推导。办公室与装卸面、人员入口与重车回转区的避让需要工程依据，P0 标记 `ENGINEERING_DECISION_REQUIRED`，不发明尺寸或强制禁邻接规则。

完整字段、精度、错误及分期见 [P0 contract](../tasks/V2_2-P0-site-constrained-factory-layout-contract.md) 与 [version plan](../tasks/V2_2-version-plan.md)。

## P2D access routing and final-layout validation (2026-09-15)

P2D adds a validation layer after P2C placement. The layer consumes the
already-bound P1 access requirements rather than reconstructing process or
access authority. There must be twelve results for the twelve authoritative
requirements, including the separate truck requirement. Every non-truck result
uses the existing P1 profile and predicate semantics for portal width, corridor
width, edge orientation and the packaging straight-route rule.

Direct shared-edge access is attempted before a corridor. Corridor search is a
finite deterministic orthogonal graph over integer millimetres on the existing
`0.001m` grid. A node budget is the only search cutoff; exhaustion is not an
infeasibility proof. P2D exposes actual route lengths as evidence, but
route-objective ordering remains inactive.

Truck validation uses only the project-bound
`OPTION_C_APPROVED_MANEUVER_TEMPLATES` chain. It rechecks project provenance,
template identity/hashes, pose continuity, entrance entry, selected shipping
loading-face docking and transformed-envelope clearance. It does not infer a
vehicle, turning radius or kinematic solution. Personnel/truck shared routes
remain prohibited. A geometry crossing/contact does not prove that the crossing
is necessary: without separate engineering authority it is
`REQUIRES_ENGINEERING_REVIEW` with `crossing_necessary=UNDETERMINED`, and cannot
produce a fully validated project result.

Incident-zone corridors are portal-only. The open interval immediately after
the origin portal and immediately before the destination portal must not enter
the incident-zone interior; positive-area corridor-envelope overlap is rejected
and exact selected-portal boundary contact is allowed. The predicate is exact
on the existing integer-millimetre grid and does not use a midpoint shortcut.

When all eleven non-truck routes pass, P2D may derive a non-optimized building
footprint from the twelve zone rectangles plus generated personnel/material
corridor envelopes. The footprint must contain those geometries, remain inside
the effective buildable boundary and clear hard obstacles. Compactness, shape
regularity and unused-site efficiency remain inactive. The final
`site_validated_layout@1.0.0` result binds zone-plan, P1 handoff, site geometry,
objective profile, placement and truck-binding hashes. `p2_complete` is
conditional on every hard predicate passing and is not a release or next-stage
authorization.

P2D does not modify the canonical zone plan, P1/P2C dimension or objective
authority, MCP tools, frontend, database, or release state. It does not
implement SVG/PDF/DXF projection, MCP Tool 7, placement optimization or vehicle
kinematics. P3 remains independently unauthorized.

## P1A separate implementation decision

基线 `e963256c56d20f90a880a61d0bc721d28c0a9c38`；Charles 独立授权
`V2_2_P1A_ZONE_DIMENSIONING_AND_ADJACENCY_FOUNDATION_R1`。
新增 module-first `layout/domain`（pure profiles/dimensioning/adjacency）和
`layout/application`（canonical source/profile binding），不新建 service、API 或数据库。
现有 planner 的四类储存矩形网格可按已有 pitch/aisle 投影外边长；不重排容量。
预冷 room edges、分选包装扩大包络和其他独立 profile 未冻结，8 区明确 BLOCKED。
无 placement/x/y 生成；几何谓词仅消费外部观察矩形，不能作完整布局验收。
`zone_dimensioning_foundation@1.0.0` 与未来 site placement identity 分开。
详见 [P1A evidence / authority matrix](../tasks/V2_2-P1A-zone-dimensioning-adjacency-foundation.md)。

## P3 SVG projection decision (2026-09-16)

P3 is a separately authorized presentation boundary after the validated P2D
result. The canonical authority remains the structured
`site_validated_layout@1.0.0` JSON; SVG identity is
`validated-layout-svg-projection@1.0.0` and is projection-only. The projection
requires both `project_layout_validated=true` and `p2_complete=true`, verifies
the P2D source hashes and matching `ValidatedSiteGeometryV1`, and fails closed
for an incomplete or tampered source result.

The renderer copies, without recomputation or mutation, the selected zone
rectangles, portals, corridor envelopes and centerlines, loading face, truck
maneuver envelopes/reference paths, and derived building footprint. It applies
only a deterministic engineering-metre to SVG-screen transform with inverted
Y, stable layer/group IDs, XML escaping, and a deterministic viewBox/legend/
title block. Display labels and display rounding are non-authoritative.

P3 does not implement placement, routing, engineering formulas, MCP Tool 7,
REST, frontend integration, PDF, DXF, or deployment. P4 and P5 remain
independently unauthorized.
