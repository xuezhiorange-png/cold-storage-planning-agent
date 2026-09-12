# ADR-044 — Site-constrained factory layout authority

状态：P0 已合并；P1A dimensioning/adjacency foundation 独立授权、Draft review。
P2/P3/P4 未授权。以下原始 P0 调查和历史 authorization snapshot 保留。
基线：v2.1.2 / `0a68597a40aa460ed31441c537ca37c3d4cfd1a7`。

## 决策

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
