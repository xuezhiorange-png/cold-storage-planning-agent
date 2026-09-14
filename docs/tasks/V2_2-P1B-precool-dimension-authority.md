# V2.2 P1B — Precool dimension authority

## 独立授权与边界

```ini
TASK_ID=V2_2_P1B_PRECOOL_DIMENSION_AUTHORITY_R1
BASE_MAIN_SHA=ae9794d0454fa64ba7db6a94d9a3faeba5df00bd
TARGET_VERSION=v2.2.0
ACTIVE_LANE=V2.2_P1
P1A_STATUS=MERGED
P1B_STATUS=DRAFT_REVIEW
RESULT=PARTIAL_ENGINEERING_AUTHORITY
DIMENSIONED_ZONE_COUNT=6
BLOCKED_ZONE_COUNT=6
ROOM_ARRANGEMENT=LONG_SIDES_PARALLEL
AREA_AUTHORITY_PRESERVED=true
UPSTREAM_SCHEME_PRESERVED=true
UPSTREAM_ROOM_COUNT_PRESERVED=true
UPSTREAM_POSITION_COUNT_PRESERVED=true
SITE_PLACEMENT_IMPLEMENTED=false
MCP_RUNTIME_CHANGED=false
FRONTEND_CHANGED=false
DATABASE_MIGRATION_CHANGED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
P2_AUTHORIZED=false
TAG_AUTHORIZED=false
GITHUB_RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## Authority 与实现

Charles 本任务指令是尺寸 authority，不是规范自动推导或演示系数。
一级/二级共享 `precool-room-6-position@1.0.0`（4.90×10.05 m）与
`precool-room-8-position@1.0.0`（4.90×12.95 m）。组合 width=N×4.90，
depth=10.05 或 12.95；不沿长边串联，无 x/y、building footprint 或场地 solver。

`layout/domain/precool_dimensioning.py` 拥有冻结 profile 和组合。
`layout/application/dimension_zones.py` 仅为两类预冷绑定新 profile。
当前组合器升级 `zone_dimensioning_foundation@1.1.0`；schema 1.0.0 保持，
P1A `zone_dimensioning_foundation@1.0.0` 留作历史证据，不暗示旧 profile 集合未变。
四个 storage profile 和 generic dimensioning / adjacency predicates 未改变。

source 必须通过现有完整 canonical envelope / exact 12-zone / formula authority 验证。
仅匹配 reporting_scheme_id 对应的唯一 schemes 项；读取 room_count、positions_per_room、
position_count，与区域 position_count、可选 room_count 交叉验证，不赋予新容量值。
area 与选定方案面积必须一致；42/56 m² 不用于反推边长。
数值必须为正整数计数（技术上限 10^12），零房间明确拒绝，不生成零面积矩形。
所有计算使用独立 Decimal context，无随机值或调用方精度依赖。
整份 source 和 profile metadata 进入 canonical JSON/hash；不信任调用方提供的 hash。

## Fail closed

- 未知/缺失 reporting ID：`UNKNOWN_PRECOOL_GEOMETRY_PROFILE`。
- 缺失/重复选定项、非法计数、计数不一致：`INVALID_UPSTREAM_PRECOOL_SCHEME`。
- 区域/选定项面积不一致：`UPSTREAM_PRECOOL_AREA_MISMATCH`。
- 冻结包络小于 required area：`PRECOOL_GEOMETRY_AREA_INSUFFICIENT`，返回 required/actual/边长 evidence。
- 其他六区：`ZONE_DIMENSIONING_AUTHORITY_REQUIRED`；access 仍 `ACCESS_PROFILE_REQUIRED`。

不会修补 source，不 fallback 6_position，不重选更优方案，不放大房间以满足面积。
仅对当前 dimensioned 子集报告面积不变量，不声称全布局或 access 验收通过。

## 当前 20t canonical replay

实际 ColdRoomZonePlanner 生成五 KEY 为 20000/7/10/4/12 的源结果（复用 P1A fixture）。
上游 `cold_room_zone_plan@1.0.0` 和 `POST-V2.1.1-charles-engineering-rule-adjustments` 不改。
一级仍 7 batches/day、1540 kg/day/position；二级仍14 h/day、2800 kg/day/position。

| Zone | reporting scheme | room count | position count | single room m | combined m | required m² | actual m² |
| --- | --- | ---: | ---: | --- | --- | ---: | ---: |
| primary_precooling_room | 6_position | 3 | 18 | 4.90×10.05 | 14.70×10.05 | 126.00 | 147.735 |
| secondary_precooling_room | 6_position | 2 | 12 | 4.90×10.05 | 9.80×10.05 | 84.00 | 98.490 |

两行的方案/间数/板位/required area 与原 source 完全一致；source 不变。
已定尺：上述两区 + raw_fruit_buffer、finished_goods_room、secondary_fruit_buffer、frozen_fruit_room。
仍 BLOCKED：office、changing_room、sorting_packaging_room、coating_room、packaging_material_storage、shipping_channel。
分选包装 required area 622.34 m² 不变，未再次乘1.1。

## 验证与历史保留

新增独立 P1B 单元和 architecture tests。现有 P1A 当前重放测试仅更新独立授权后的
可定尺集合为 6，所有原网格、area、hash、upstream 和 blocked invariants 保留；
P1A task 文档的历史 4/8 状态与 immutable introducing-commit scope guard 不改。
本轮 scope guard 采用本任务 base → immutable introducing commit；提交前检查 candidate diff，
未来 HEAD 仅验证 ancestor，不把 moving origin/main 用作历史终点。
本地测试和 exact-head CI 结果在 PR body 中绑定实际 head，预期 CI_SCOPE=BACKEND。
不改计算公式、MCP 六工具/五 KEY、Skill、前端、migration 或部署。
