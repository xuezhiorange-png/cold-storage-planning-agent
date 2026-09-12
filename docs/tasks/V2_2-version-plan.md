# V2.2 — 受场地边界约束的工厂平面规划

## 当前授权（2026-09-12）

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

| 阶段 | 内容 | 当前状态 |
| --- | --- | --- |
| P0 | Contract Freeze | 本 Draft 合同评审 |
| P1 | Zone Dimensioning + Adjacency Engine | 未授权 |
| P2 | Site-Constrained Deterministic Placement Engine | 未授权 |
| P3 | Canonical SVG Drawing Projection | 未授权 |
| P4 | MCP Tool 7 + Doubao/Feishu Integration | 未授权 |
| P5 | Release Closure | 未授权 |

P1 的完成条件包括容量几何保留、显式定尺 profile、邻接与 access 语义验证；P2 才实现场地放置及可行性判定；P3 只从 canonical JSON 投影；P4 才实现第七个工具。每阶段必须单独授权、测试、Draft review；P0 不授权后续阶段。PDF/DXF 是未来投影方向，不因本分期表自动授权实现。

## 合同入口与未决工程事项

- [P0 合同](V2_2-P0-site-constrained-factory-layout-contract.md)：SiteLayoutInputV1 / SiteLayoutResultV1、几何、流向、错误与可复现性。
- [ADR-044](../architecture/ADR-044-site-constrained-factory-layout-authority.md)：权威分工及现有 capacity geometry 调查。
- 精确门宽、车辆转弯包络、人员/重车隔离尺寸、预冷多房间的组合尺寸、非网格区域定尺 profile 尚需工程决策。在 P1/P2 使用前必须冻结有版本的 profile；不得由 Agent 猜测，也不得将缺省值说成规范要求。
- 当前六工具、五 KEY、zone area、factory-power p2、schema p1 均不变。模型不得计算面积、尺寸或工程值；输出为概念规划、需工程复核，不是施工图。
