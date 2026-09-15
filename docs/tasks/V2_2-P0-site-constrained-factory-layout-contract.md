# V2.2 P0 — Site-constrained factory layout contract

## P2A 当前独立授权与实现状态（2026-09-15）

P1F / PR #278 已合并；当前基线为
`50210aa7cc876ed8a93a099c82ef4a4f287da82a`。Charles 已单独授权 P2A，历史
P0/P1 的未授权快照原样保留。

```ini
TASK_ID=V2_2_P2A_SITE_GEOMETRY_FOUNDATION_R1
P1_COMPLETE=true
P1_CLOSURE_BLOCKERS=NONE
P2_AUTHORIZED=true
P2A_STATUS=IMPLEMENTED_DRAFT_REVIEW
SITE_GEOMETRY_FOUNDATION_IMPLEMENTED=true
POLYGON_VALIDATION_IMPLEMENTED=true
BUILDABLE_CONTAINMENT_IMPLEMENTED=true
ENTRANCE_SEGMENT_VALIDATION_IMPLEMENTED=true
HARD_OBSTACLE_VALIDATION_IMPLEMENTED=true
PLACED_RECTANGLE_PRIMITIVE_IMPLEMENTED=true
FLEXIBLE_RECTANGLE_CANDIDATE_VALIDATION_IMPLEMENTED=true
PLACEMENT_SEARCH_IMPLEMENTED=false
OBJECTIVE_PROFILE_IMPLEMENTED=false
TRUCK_TURNING_SOLVER_IMPLEMENTED=false
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

P2A 的完整边界和输出见 [P2A evidence](V2_2-P2A-site-geometry-foundation.md)。
本 overlay 不改变 12 区面积、P1 handoff、既有 dimension/access authority 或
五阶段/MCP 合同；不把 geometry foundation 说成 placement 完成。

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

## 状态与边界

```ini
TASK_ID=V2_2_P0_SITE_CONSTRAINED_FACTORY_LAYOUT_CONTRACT_FREEZE_R1
BASE_RELEASE=v2.1.2
BASE_MAIN_SHA=0a68597a40aa460ed31441c537ca37c3d4cfd1a7
TARGET_VERSION=v2.2.0
ACTIVE_GOVERNANCE_LANE=V2.2_P0
SITE_LAYOUT_CONTRACT_FROZEN=true
V22_P0_MCP_IMPLEMENTATION=false
V22_P0_RUNTIME_IMPLEMENTATION=false
V22_P0_FRONTEND_IMPLEMENTATION=false
V22_P0_LAYOUT_ENGINE_IMPLEMENTATION=false
EXISTING_MCP_TOOL_COUNT=6
EXISTING_MCP_TOOL_ORDER_CHANGED=false
EXISTING_MCP_CONTRACT_CHANGED=false
EXISTING_FIVE_KEY_SCHEMA_CHANGED=false
FUTURE_MCP_TOOL_NAME=preview_site_layout
FUTURE_MCP_TOOL_POSITION=7
CALCULATOR_ID=site_constrained_factory_layout
INITIAL_VERSION=1.0.0
FUTURE_IDENTITY=site_constrained_factory_layout@1.0.0
CANONICAL_LAYOUT_AUTHORITY=STRUCTURED_LAYOUT_JSON
SVG_IS_PROJECTION=true
PDF_IS_PROJECTION=true
DXF_IS_FUTURE_PROJECTION=true
DRAWING_IS_NOT_CALCULATION_AUTHORITY=true
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
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P0 定义未来 contract，并以文档结构、现有源代码与不可变基线守卫验证；不提供几何校验器、优化器或可调用的第七工具。下面所有 input/output 描述均为未来接口，不能被描述为当前可执行能力。

## SiteLayoutInputV1

机器可读字段 schema：[SiteLayoutInputV1 JSON Schema](V2_2-site-layout-input-v1.schema.json)。它只验证结构、枚举及数值范围；polygon 包含、自交、入口沿边等几何语义由未来引擎验证，P0 不实现。schema 中 default 是合同注释，未来 canonical normalization 才填充，JSON Schema validation 本身不修改输入。

坐标为 local Cartesian meters：origin=(0,0)，X 向 local east / drawing right，Y 向 local north / drawing up。坐标可为负数；不接受 latitude、longitude、EPSG 或 GIS projection。`north_angle_degrees` 是从图纸 +Y 顺时针到真实北向的角度，有限数值，[0,360)，可选默认 0。NORTH/EAST/SOUTH/WEST loading preference 使用图纸坐标轴，北向仅作方向元数据，避免隐含旋转几何。

```ini
COORDINATE_SYSTEM=LOCAL_CARTESIAN_METERS
COORDINATE_UNIT=m
ORIGIN=(0,0)
X_AXIS=LOCAL_EAST_OR_DRAWING_RIGHT
Y_AXIS=LOCAL_NORTH_OR_DRAWING_UP
AUTO_SETBACK_CALCULATION=false
SHARED_ENTRANCE_ALLOWED=true
```

| 字段 | 必填 / 缺省 | 结构与语义 |
| --- | --- | --- |
| site_boundary | 必填 | PolygonV1 |
| buildable_boundary | 可选 | PolygonV1；缺省 effective_buildable_boundary=site_boundary |
| main_entrance | 必填 | AccessSegmentV1；人员/一般入口 |
| truck_entrance | 必填 | AccessSegmentV1；物流车辆入口 |
| preferred_loading_side | 可选 / UNSPECIFIED | NORTH / EAST / SOUTH / WEST / NEAREST_TRUCK_ENTRANCE / UNSPECIFIED；仅 preference |
| no_build_zones | 可选 / [] | PolygonV1[]；硬禁建障碍 |
| existing_buildings | 可选 / [] | {id, name, footprint: PolygonV1, retained: boolean}[]；id 唯一 |
| north_angle_degrees | 可选 / 0 | 如上 |

所有对象拒绝未知字段；required area、factory_area_m2、cold_storage_area_m2、zone_area_m2 不属于 site input。现有五 KEY 仍为 daily_inbound_mass_kg、finished_storage_days、frozen_storage_days、main_packaging_storage_days、auxiliary_packaging_storage_days，schema 不变。未来工具将 site constraints 作为独立结构桥接；具体 MCP wrapper 在 P4 冻结，不把 site 字段加进已有工具。源 zone-plan 由后端执行/读取 canonical 结果并验证 identity/hash，不能把模型回传的 areas 当权威。

PolygonV1 的 JSON shape：

```json
{"type":"polygon","points":[{"x":0,"y":0},{"x":100,"y":0},{"x":100,"y":80},{"x":0,"y":80}]}
```

points 至少三个互异顶点；隐式闭合，不要求重复末点。若提供首尾重复点则返回 INVALID_SITE_BOUNDARY（其他 polygon 按所属字段返回相应错误），不静默删除点。禁止重复顶点、零长边、自交、自触及零面积；允许凹简单多边形，不支持 holes/multipolygon。每个 x/y 是有限数值，不接受 bool、NaN、Infinity 或数值字符串。输入坐标精度冻结为 0.001 m 网格，超出精度拒绝而不静默取整；面积用 Decimal/整数网格几何并保留至少 0.000001 m² 精度，投影显示取舍不回写 canonical geometry。

buildable_boundary 必须全域包含于 site_boundary（允许共享边），不能仅测试顶点；跨过凹边界仍算越界。缺省边界不意味着已经满足法规退界。no_build_zones 和 existing_buildings footprints 同样须在 site 内；彼此重叠可作为障碍并集处理，不重复扣面积。retained=true 为硬障碍；retained=false 仅记录，不授权拆除、不意味着场地已清空，成功结果必须警告其依赖另行确认的移除条件并 requires_review=true。

AccessSegmentV1：

```json
{"start":{"x":5,"y":0},"end":{"x":12,"y":0}}
```

入口正长度，整条 segment 位于 site boundary 上（可以跨连续共线边，不能跨角弦穿过内部）。两入口允许重合，结果 accesses 必须记录 shared=true。不能只验证端点就接受中间离开 boundary 的线段。

障碍合同：building footprint ∩ no_build_zone = empty，zone footprint ∩ no_build_zone = empty；retained building 同理。这里 empty 按闭集合解释，连边界接触也禁止。场地/buildable 边界允许接触；zone 间允许共享边，禁止内部重叠，这样与邻接合同一致。不得用浮点 epsilon 偷放行硬越界。

## 上游面积、容量与定尺

```ini
ZONE_COUNT=12
ZONE_AREA_AUTHORITY=COLD_ROOM_ZONE_PLAN
SITE_LAYOUT_MAY_NOT_RECALCULATE_ZONE_AREA=true
RECTANGULAR_ZONE_FOOTPRINT=true
ORTHOGONAL_LAYOUT_ONLY=true
FREE_ROTATION=false
```

精确 zone set：office、changing_room、primary_precooling_room、secondary_precooling_room、raw_fruit_buffer、sorting_packaging_room、coating_room、finished_goods_room、secondary_fruit_buffer、frozen_fruit_room、packaging_material_storage、shipping_channel。必须唯一且完整，不增删合并；required_area_m2 从成功的 `cold_room_zone_plan@1.0.0` 原样读取，源 formula authority 与 exact payload hash 同时记录。当前 formula authority 为 POST-V2.1.1-charles-engineering-rule-adjustments。缺失、身份不符、非成功结果、非法 area、重复/未知 zone 均 fail closed。

ZoneDimensionV1：zone_code、required_area_m2、width_m、depth_m、actual_area_m2、rotation_deg、area_requirement；placement 阶段才有 x/y，其中 x/y 是旋转后 axis-aligned footprint 的左下角，width/depth 为未旋转边长，rotation 仅 0 或 90。0° extent=(width,depth)，90° extent=(depth,width)，避免绕原点旋转导致位置歧义。width/depth 正且符合 0.001 m 网格；actual_area_m2=width_m×depth_m 必须精确成立；坐标、面积均有限。actual area 是外包络面积，不能替代原 required area。

### P1C0 独立面积精度合同修正

`V2_2_P1C0_AREA_PRECISION_CONTRACT_CORRECTION_R1` 明确修正原 P0 无条件 reported-area 下限，
不是特定 zone 豁免。`required_area_m2` 兼容字段始终原样保留 canonical zone-plan reporting 值，
在 `AreaRequirementV1.reported_required_area_m2` 中记录相同数值与来源。

- 有版本化、可追溯并验证过的 exact authority 且 reporting projection 相等时：
  `actual_area_m2>=exact_geometry_required_area_m2`。
- 没有 exact authority 时：`actual_area_m2>=reported_required_area_m2`，不放宽。
- 提供 exact authority 但来源或投影验证失败：fail closed，不能悄悄丢弃错误证据。
- `NO_EPSILON=true`、`NO_SPECIAL_CASE=true`、`NO_GEOMETRY_INFLATION_FOR_REPORTING_ROUNDING=true`。

`cold-room-zone-plan-binary64-product-2dp@1.0.0` 记录 0.01 m² quantum、来源与算法：
按源 operands 顺序执行 Python binary64 乘积，再 `round(product, 2)`；不是 ROUND_HALF_UP。
exact requirement 则使用同一 operands 的独立 Decimal 精确乘积。若上游先 round raw area，
这里的源 operand 必须是那个已输出的 raw 值，不能改成另一套计算顺序。
源 snapshot/hash、operand JSON Pointer、profile identity、Owner authority 均须绑定；
元数据对象不是用户输入或 Owner 审批证明，未来生产 binder 必须单独审查授权。
P1C0 不接入 sorting profile；六个当前可定尺区域继续走严格 reported 下限。

[ADR-044](../architecture/ADR-044-site-constrained-factory-layout-authority.md) 调查证明 1.67/2.40/2.0 是网格比排序，不是建筑外框硬比例。容量几何作为上游保留：n_long/n_short、selected scheme、room_count、position_count、aisle layout、pitch/clearance 不得被 layout engine 重排缩减。已有完整容量 envelope 可整体旋转和平移；尺寸不足的区域使用另行审查的 versioned dimensioning profile，禁止 LLM 补值。profile 不得改变 zone area formula；分选包装 1.1 已计入 required area，不得再乘。预冷多房间必须在 zone 矩形包络中保留选定房间数，不把 zone rectangle 谎称单个冷间。

未来 result 记录 dimensioning_profile_identity、capacity_geometry_reference 与 geometry assumptions。无法绑定足够的几何权威时返回 ZONE_DIMENSIONING_AUTHORITY_REQUIRED；P0 不冻结无证据的门宽、车辆回转半径或单间长宽。

## Process flow、adjacency 与 access

主物流（方向固定）：raw_fruit_buffer → primary_precooling_room → sorting_packaging_room → secondary_precooling_room → coating_room → finished_goods_room → shipping_channel。

本节以 Charles 最终确认的业务 authority 为准：一级预冷后先分选包装，再进入二级预冷。
本次 contract-only correction 为 `V2_2_P0_PROCESS_FLOW_AUTHORITY_CORRECTION_R1`，
基线 `fe5c1c6f19326f739a55be558403ee7b535f8195`。
原主链六组 MUST_ADJACENT 保持不变；P1D1 单独授权追加 office ↔ shipping_channel，
当前总计七组 MUST。包材侧物流保留，不列入 MUST 集合。
历史 P0 Git 快照仍保留当时记录，不能作为当前主物流 authority。

侧物流：packaging_material_storage → sorting_packaging_room。
次果：sorting_packaging_room → secondary_fruit_buffer。
冻果：sorting_packaging_room → frozen_fruit_room。
人员：main_entrance → changing_room → production_area。production_area 是生产区集合的 flow endpoint group，不是第 13 区；本合同以 sorting_packaging_room 作为进入该组的逻辑节点。office 属人员侧，不属于主原果物流链。

ZONE_ADJACENCY 指两个区域共享正长度边段且内部不重叠；角点接触不算邻接。MUST 邻接的可通行开口需由 access profile 明确；本 P0 邻接本身不证明门洞、消防分隔或卫生合规。ZONE_ACCESS_PROXIMITY 指区域与入口的可达路径距离，是另一种关系，不要求多边形共边。

| 关系 | 对象对（无向，物流方向由 flows 表示） |
| --- | --- |
| MUST_ADJACENT / ZONE_ADJACENCY | raw_fruit_buffer ↔ primary_precooling_room |
| MUST_ADJACENT / ZONE_ADJACENCY | primary_precooling_room ↔ sorting_packaging_room |
| MUST_ADJACENT / ZONE_ADJACENCY | sorting_packaging_room ↔ secondary_precooling_room |
| MUST_ADJACENT / ZONE_ADJACENCY | secondary_precooling_room ↔ coating_room |
| MUST_ADJACENT / ZONE_ADJACENCY | coating_room ↔ finished_goods_room |
| MUST_ADJACENT / ZONE_ADJACENCY | finished_goods_room ↔ shipping_channel |
| MUST_ADJACENT / ZONE_ADJACENCY | office ↔ shipping_channel |
| SHOULD_ADJACENT / ZONE_ADJACENCY | sorting_packaging_room ↔ coating_room |
| SHOULD_ADJACENT / ZONE_ADJACENCY | sorting_packaging_room ↔ secondary_fruit_buffer |
| SHOULD_ADJACENT / ZONE_ADJACENCY | sorting_packaging_room ↔ frozen_fruit_room |
| SHOULD_ADJACENT / ZONE_ADJACENCY | changing_room ↔ sorting_packaging_room |
| SHOULD_ADJACENT / ZONE_ADJACENCY | office ↔ primary_precooling_room |
| SHOULD_ADJACENT / ZONE_ACCESS_PROXIMITY | shipping_channel ↔ truck_entrance |

AVOID_ADJACENT 分类保留，但当前强制规则集合为空。office ↔ shipping_channel 的新 MUST
不等于 office 必须贴装卸面或已满足人员/重车安全分隔；office ↔ truck loading face、
people entrance ↔ heavy truck maneuvering area 的避让细节仍为 ENGINEERING_DECISION_REQUIRED。
不得以未批准避让规则否定已批准 zone 邻接，也不得据此声称安全合规。

Required access：main entrance 必须存在可通行连接到 changing_room/生产侧，truck entrance 必须连接到 shipping_channel 装卸侧。通路在 site 内且不穿硬障碍；跨建筑边界必须有显式 portal。路径/门宽/通行包络由有版本的 access profile 提供，不能仅凭入口存在或欧氏距离就声称 required access satisfied。缺 profile 则返回 ACCESS_PROFILE_REQUIRED；P1/P2 冻结后才可实现对应校验。

## Hard / soft

HARD：建筑与所有 zone 在有效可建域内；zone 在 building 内；zone 内部无重叠；与禁建和 retained 障碍无交集；actual_area 满足上述已验证的面积下限；全部 MUST_ADJACENT；required access。building footprint 是简单正交 polygon（矩形或直角折线包络），允许包络内非 zone 面积作为 circulation/residual，不允许把 gross_area 当 12 区面积权威。

SOFT：SHOULD_ADJACENT、material flow 更短、loading side preference、compactness、circulation length、people/truck separation、shape regularity、unused-site efficiency。硬约束先满足，再优化软目标。未来 objective profile 明确各项方向、单位、权重、归一化、tie-break；P0 不伪造权重。不得以软分抵扣硬违例。

## SiteLayoutResultV1（schema_version=1.0.0）

以下为字段类型合同，不是已计算的平面图；成功结果禁止以示例零尺寸代替有效几何。所有对象字段明确列出；扩展必须修改 schema 合同。

| 字段 | 类型 / authority |
| --- | --- |
| schema_version | literal 1.0.0 |
| available | boolean；只有完整硬校验通过时为 true |
| calculator | {id, version, identity} = site_constrained_factory_layout / 1.0.0 / site_constrained_factory_layout@1.0.0 |
| algorithm | {identity, version, dimensioning_profile_identity, access_profile_identity, objective_profile_identity, seed}；seed integer 或 null |
| source_zone_plan | {calculator_identity, formula_authority, result_hash}；backend 绑定的 canonical source |
| site | SiteLayoutInputV1 所有输入字段及 effective_buildable_boundary |
| building | {footprint: PolygonV1, gross_area_m2}；gross area 与 polygon 几何面积一致 |
| zones | ZoneDimensionV1[12]；每行附 capacity_geometry_reference、dimensioning_profile_identity |
| accesses | {id, kind, from_ref, to_ref, path, width_m, shared, profile_identity}[]；kind=PEOPLE/LOGISTICS，path 为米制点数组 |
| flows | {kind, from_ref, to_ref, path, length_m}[]；kind=MATERIAL/PACKAGING/SECONDARY/FROZEN/PEOPLE |
| constraint_evaluation | {hard_constraints_passed, violations, soft_scores}；每个 violation 含 code、constraint_id、object_refs、message |
| assumptions / warnings / sources | 可追溯数组；标明 demo/unverified 来源，不发明规范依据 |
| requires_review | literal true |
| canonical_result_hash | sha256:<64 lowercase hex> |
| error | null 或 {category, code, message, details} |

失败响应 available=false；building=null、zones/accesses/flows=[]，hard_constraints_passed=false；error 必填，不输出伪成功图或 hash。输入不合法时 canonical_result_hash=null；不可行性诊断也不能作为成功布局。源字段只在已验证时填写，否则 null。soft_scores 在失败时为空；工程值只能由既有 calculator 与未来 deterministic geometry engine 输出，projection 不重算。

## 可复现性与 hash

```ini
DETERMINISTIC_LAYOUT_REQUIRED=true
RANDOM_LAYOUT_WITHOUT_FIXED_SEED=false
```

同一完整规范化输入/源结果/算法及 profile 身份产生同一结果。若优化器使用随机搜索，seed 必须显式固定并纳入 algorithm identity/hash；否则固定排序和 tie-break。禁止 wall-clock 截断产生不确定结果，采用确定性迭代预算并写入 algorithm profile。

hash preimage 包含 normalized site input、source zone-plan identity/formula authority/result_hash、algorithm/profile/seed、完整 layout result（排除自身 hash、传输 correlation/timestamp）。source hash 由 backend 对 exact serialized canonical zone result 重算，调用方不得自报覆盖。canonical JSON 使用 UTF-8、key 字典序、无空白、有限数值转精确十进制字符串、无多余尾零、负零归零；zone 按 zone_code，其他记录按稳定 id 排序。polygon 转逆时针，从字典序最小点开始，隐式闭合；列表中输入顺序无工程意义的障碍按稳定几何/id 排序。所有规范化只能改变表达，不得改变几何。SVG/PDF/future DXF 读取该 JSON 与单位，可在 projection-only 层翻转屏幕 Y 轴，不影响 hash 与坐标权威。

## 错误合同

| code | category / 条件 |
| --- | --- |
| INVALID_SITE_BOUNDARY | INVALID_INPUT；缺失、零面积、非有限、重复顶点/精度非法 |
| SELF_INTERSECTING_SITE_BOUNDARY | INVALID_INPUT；自交或自触 |
| INVALID_BUILDABLE_BOUNDARY | INVALID_INPUT；buildable polygon 结构非法 |
| BUILDABLE_BOUNDARY_OUTSIDE_SITE | INVALID_INPUT；可建域越出 site |
| INVALID_ENTRANCE | INVALID_INPUT；缺失、零长或整段不在 boundary |
| NO_BUILD_ZONE_OUTSIDE_SITE | INVALID_INPUT；禁建区越界 |
| EXISTING_BUILDING_OUTSIDE_SITE | INVALID_INPUT；既有建筑越界 |
| INVALID_NO_BUILD_ZONE / INVALID_EXISTING_BUILDING | INVALID_INPUT；障碍结构非法 |
| ZONE_PLAN_REQUIRED | INVALID_INPUT；无后端 canonical source |
| ZONE_PLAN_IDENTITY_INVALID | INVALID_INPUT；非成功源、identity/hash/12-zone set/area 非法 |
| INVALID_LAYOUT_PREFERENCE | INVALID_INPUT；loading enum、north angle 或未知字段非法 |
| ZONE_DIMENSIONING_AUTHORITY_REQUIRED / ACCESS_PROFILE_REQUIRED | AUTHORITY_REQUIRED；缺少已冻结几何/通行 profile |
| INSUFFICIENT_BUILDABLE_AREA | VALID_INPUT_BUT_NO_FEASIBLE_LAYOUT；面积必要条件不满足 |
| LAYOUT_INFEASIBLE | VALID_INPUT_BUT_NO_FEASIBLE_LAYOUT；确定性引擎证明无可行布局 |
| HARD_CONSTRAINT_UNSATISFIABLE | VALID_INPUT_BUT_NO_FEASIBLE_LAYOUT；明确硬约束冲突 |
| LAYOUT_SEARCH_EXHAUSTED | SEARCH_INCOMPLETE；预算耗尽但无无解证明，不得伪报几何不可行 |

顺序：结构/数值 → polygon → 包含/access → source → profiles → 可行性 → 优化；错误保留精确 code 与对象定位。失败不回退到无约束布局。

## Hostile contract acceptance matrix

P1/P2 实现必须覆盖下列行为；P0 测试只锁合同与基线，不冒充实际 geometry validator。

| case | 预期 |
| --- | --- |
| bow-tie site | SELF_INTERSECTING_SITE_BOUNDARY |
| 三共线顶点 / 重复闭合点 / NaN | INVALID_SITE_BOUNDARY |
| buildable 边跨出凹 site，端点均在内 | BUILDABLE_BOUNDARY_OUTSIDE_SITE |
| entrance 端点在 boundary 但弦不在 boundary | INVALID_ENTRANCE |
| obstacle 越界 | NO_BUILD_ZONE_OUTSIDE_SITE / EXISTING_BUILDING_OUTSIDE_SITE |
| 注入 zone_area_m2 / factory_area_m2 / cold_storage_area_m2 | INVALID_LAYOUT_PREFERENCE；不成为面积权威 |
| 未知/重复/缺失 zone、伪造 source hash | ZONE_PLAN_IDENTITY_INVALID |
| actual_area 小于已验证 exact 下限，或无 exact authority 时小于 reported 下限 | hard failure；available=false |
| 两矩形仅角点接触却要求 MUST | HARD_CONSTRAINT_UNSATISFIABLE |
| 与禁建/retained 障碍相触 | hard failure；available=false |
| site 面积足够但形状不容纳不可重排容量几何 | LAYOUT_INFEASIBLE（需证明） |
| required access 无通路 | HARD_CONSTRAINT_UNSATISFIABLE |
| preference 与 hard 边界冲突 | hard 优先；记录 preference 未满足 |
| 同输入重复执行、变更输入对象 key 顺序 | canonical hash 相同 |
| 修改 zone source / site / algorithm seed | hash preimage 必须变化 |

## Non-scope 与治理

NO_LAYOUT_ALGORITHM_IMPLEMENTATION、NO_SVG_GENERATION、NO_PDF_GENERATION、NO_DXF_GENERATION、NO_CAD_GENERATION、NO_3D_MODEL、NO_BIM、NO_GIS、NO_FIRE_CODE_AUTOMATION、NO_STRUCTURAL_DESIGN、NO_REFRIGERATION_PIPE_ROUTING、NO_ELECTRICAL_ROUTING、NO_EQUIPMENT_ROOM_DETAILED_LAYOUT、NO_AUTOMATIC_SETBACK_CODE_LOOKUP、NO_MACHINE_LEARNING_LAYOUT。历史图纸学习亦不在 P0。输出仅概念规划，必须工程复核，不是施工图，不控制设备。

当前工具顺序保持 preview_zone_plan → preview_cooling_load → preview_equipment → preview_installed_power → preview_investment → preview_factory_power。现有 upstream area、factory_power_estimation@2.0.0-p2、result schema 2.0.0-p1 原样保留。

架构测试使用本任务初次纳入 guard 的不可变 commit 作为历史 scope 终点；当前候选尚未提交时只校验 candidate diff。完成后 HEAD 仅作历史 target ancestry，禁止使用 moving origin/main 作为历史终点。允许文件仅 docs/** 与 backend/tests/architecture/**。分期与授权见 [version plan](V2_2-version-plan.md)。

## P0 验证记录（2026-09-12）

在同一 GitHub 仓库的独立 clone、指定 v2.1.2 基线与本候选九文件上，使用锁定依赖和 Python 3.12：

- 定向 P0 architecture：21 passed（包括 released planner 的真实 12-zone replay）。
- 全量 architecture：610 passed、16 个既有 skipped；没有添加 skip/xfail。
- ruff check 与 ruff format --check：PASS，792 files already formatted。
- mypy src：PASS，356 source files。
- git diff --check：PASS。
- backend/src、frontend/src、backend/alembic、.github/workflows、deployment、既有 MCP/Skill/runbook：diff empty。

本地原目录出现文件读取停滞，验证转到独立 clone；初次全量运行的历史测试子进程选中了无 pytest 的系统 python3，修正执行环境 PATH 后全量通过，没有修改该历史测试。P0 的结构性 schema 测试不表示布局/几何算法已实现。
