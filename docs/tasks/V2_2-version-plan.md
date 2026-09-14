# V2.2 — 受场地边界约束的工厂平面规划

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
| P1 | Zone Dimensioning + Adjacency Engine | P1A/P1B/P1C0 MERGED；P1C sorting 尺寸 authority Draft review；非整个 P1 完成 |
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
当前独立授权 `V2_2_P1C_SORTING_PACKAGING_DIMENSION_AUTHORITY_R1`：
复用 exact/reporting 合同及上游分选网格，长边乘既定 1.1；7 区定尺、5 区 BLOCKED。
详见 [P1C evidence](V2_2-P1C-sorting-packaging-dimension-authority.md)。
P2/P3/P4/P5、其他五区 profile、Ready/Merge、tag/release/deployment 仍未授权。

- [P0 合同](V2_2-P0-site-constrained-factory-layout-contract.md)：SiteLayoutInputV1 / SiteLayoutResultV1、几何、流向、错误与可复现性。
- [ADR-044](../architecture/ADR-044-site-constrained-factory-layout-authority.md)：权威分工及现有 capacity geometry 调查。
- 预冷多房间组合尺寸由 P1B 单独确认。精确门宽、车辆转弯包络、人员/重车隔离尺寸、其他非网格区域定尺 profile 尚需工程决策；不得由 Agent 猜测。
- 当前六工具、五 KEY、zone area、factory-power p2、schema p1 均不变。模型不得计算面积、尺寸或工程值；输出为概念规划、需工程复核，不是施工图。
