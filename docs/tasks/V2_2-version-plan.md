# V2.2 — 受场地边界约束的工厂平面规划

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
距离、loading-side 两种明确度量和三项暂时关闭的 site/building 指标；不创建
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
| P3 | Canonical SVG Drawing Projection | 未授权 |
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
