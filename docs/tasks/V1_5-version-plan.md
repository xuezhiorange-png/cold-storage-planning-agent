# V1.5 总计划：冷量墙/屋面从分区几何进入

**状态：** 实现已授权（V1.5 envelope wall/roof geometry bind）  
**上一产品标签：** `v1.4.0`  
**基线 `main` SHA：** `c58f0ae`  
**权威：** Charles 选定主题 — 授权公式重切的**输入血缘**（不是改 `Q = U × A × ΔT` 内核）：墙、屋面面积不再用 v05 演示目录的固定 `200` / `100` m²，而从分区 `required_area_m2` 推导。工作台落库路径和豆包内存预览走**同一绑定**。  
**打开这一份即可看懂 1.5 做什么。** 实现合同见
[`V1_5-P0-envelope-geometry-contract.md`](V1_5-P0-envelope-geometry-contract.md)，
决策记录见 [`ADR-037`](../architecture/ADR-037-envelope-wall-roof-from-zone-geometry.md)。

```text
TASK=V15_OVERALL_VERSION_PLAN_R1
GOVERNANCE_OWNER=V1.5
PREVIOUS_RELEASE=v1.4.0
BASE_MAIN_SHA=c58f0ae
TARGET_FILE=docs/tasks/V1_5-version-plan.md
V15_IMPLEMENTATION_AUTHORIZED=YES
V15_P0_IMPLEMENTATION_AUTHORIZED=YES
FORMULA_RECUT_AUTHORIZED=YES
COOLING_LOAD_FORMULA_RECUT=envelope_wall_roof_geometry_only
ENVELOPE_WALL_ROOF_FROM_PLAN=YES
ENVELOPE_FROM_ZONE_AREA=floor_wall_roof_from_plan
KEEP_COOLING_LOAD_VERSION=YES
KEEP_OPERATOR_SCHEMA=OperatorProcessInputV1@1.1.0
KEEP_ZONE_PLAN_VERSION=YES
KEEP_EQUIPMENT_VERSION=YES
KEEP_INSTALLED_POWER_VERSION=YES
KEEP_INVESTMENT_VERSION=YES
KEEP_CALCULATOR_IDENTITY=cold_room_zone_plan@1.0.0,cooling_load@1.0.0,equipment@1.0.0,installed_power@1.0.0,investment_estimate@1.0.0
AILY_OUTBOUND_LIVE_SESSION=NO
KEEP_AILY_V13_SKILL_FROZEN=YES
KEEP_AILY_V15_SKILL=YES
TD008_POWER_EQUIPMENT_CATALOG_UNIFIED=NO
EQUIPMENT_FORMULA_RECUT=NO
INSTALLED_POWER_FORMULA_RECUT=NO
INVESTMENT_FORMULA_RECUT=NO
AGENT_TO_ENGINEERING_VALUE=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
MARK_REVIEWED_AS_MODEL_TOOL=NO
EXTEND_API_V1_AGENT_FOR_AILY=NO
DELETE_PATH_A_SAVE_INPUTS=NO
POWER_CONFIGURATION_REPLACES_INSTALLED_POWER=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

`V15_IMPLEMENTATION_AUTHORIZED=YES`：本文件冻结「1.5 做什么」且实现已授权。
打标签 `v1.5.0` 仍等 `main` HEAD CI 全绿后。不移动 `v1.4.0`。

---

## 1. 一句话

产品身份仍是 **豆包工作伙伴**。V1.4 已发布。V1.5 让冷量围护的**墙面积、屋面面积**跟分区规划面积走同一血缘：正方形平面 + 演示层高。U 值与设计温度仍是演示目录，需复核。不 bump `cooling_load@1.0.0`。

## 2. 几何合同（冻结后不可默默改）

分区规划只产出 `required_area_m2`，没有周长。本版**不新增 KEY**。明确的演示几何假设（`source_type=demo`，`validity_status=unverified`，`requires_review=true`）：

| 叶子 | 本版来源 |
|---|---|
| `floor_area` / `zone_area` | 已有：分区 `required_area_m2` |
| `roof_area` | `= floor_area`（单层平面） |
| `wall_area` | `= room_height × 4 × √floor_area`（正方形平面） |
| `room_height` | **仍演示目录** `5.0` m（v05 catalog） |
| `u_value_*`、室外/室内设计温度、货品热物性 | **仍演示/系数目录** |

不采用 `wall = floor × height`（ADR-035 已否）。缺层高则 fail-closed，不默猜。推导放在共享绑定
[`preview_lineage_bind.py`](../../backend/src/cold_storage/modules/projects/application/preview_lineage_bind.py)
里，**不写进** [`cooling_load.py`](../../backend/src/cold_storage/modules/calculations/domain/cooling_load.py)
内核，因此 **不 bump** `cooling_load@1.0.0`（与 V1.3 地板绑定同一纪律）。

## 3. 操作者五个 KEY（不变）

```text
zone_planning_inputs.daily_inbound_mass_kg          kg/day
zone_planning_inputs.finished_storage_days          day
zone_planning_inputs.frozen_storage_days            day
zone_planning_inputs.main_packaging_storage_days    day
zone_planning_inputs.auxiliary_packaging_storage_days  day
```

吨 = 每天。豆包理解自然语言。本系统不解析聊天。
`OperatorProcessInputV1` schema_version 仍为 `1.1.0`。

计算器身份冻结，不 bump `VERSION`：

```text
cold_room_zone_plan@1.0.0
cooling_load@1.0.0
equipment@1.0.0
installed_power@1.0.0
investment_estimate@1.0.0
```

## 4. 诚实标志（成功路径）

```text
floor_area_from_zone_plan: true
envelope_wall_roof_from_plan: true
formula_recut_authorized: true
```

技能/表注改为：**地板、墙、屋面来自分区几何（正方形平面 + 演示层高）；U 值与设计温度仍为演示目录，需复核。**

常温间仍跳过。风机 kW(e) 仍可声明演示（设备结果没有风机功率，不发明）。

## 5. 包划分

| 切片 | 内容 |
|---|---|
| **P0** | 身份 `v1.4.0`；本总计划 + 合同 + ADR-037 |
| **P1** | 共享绑定：roof=floor；wall=height×4×√A；工作台落库覆盖目录 200/100 |
| **P2** | Aily REST/MCP 标志、表注、测试；不 import calculations |
| **P3** | v1.5 技能 + 手册；冻结 v1.3 技能指针；`v1.5.0` 仅在 **main HEAD CI 绿** 后打 |

V1.3 技能文件保持冻结：`docs/contracts/aily/v1.3/**`。
ADR-028 / ADR-035 正文保持历史冻结；本版用 ADR-037 覆盖
`ZONE_RESULT_TO_COOLING_LOAD_ENVELOPE_AUTO_FEED` 在 V1.5 的语义。

## 6. 实现约束

- 工作台五阶段与豆包 `concept-preview` / `preview_cooling_load` 走同一绑定。
- Aily API / MCP / application **不得** `import cold_storage.modules.calculations`。
- Vue / 报告模板 / prompt **不得** 写墙屋面公式。
- 不扩展 `/api/v1/agent/**`。`mark_reviewed` / `approve` 不是模型工具。
- 不移动标签 `v0.9.0` / `v1.0.0` / `v1.1.0` / `v1.2.0` / `v1.3.0` / `v1.4.0`。
- Issues **#11 / #13 / #17 / #176 / #20** 保持 CLOSED。

## 7. 本版不做

- 改五 KEY；吨≠每天；豆包解析聊天。
- 改 `Q = U × A × ΔT` 内核或 bump `cooling_load@1.0.0`。
- TD-024 出站；`AILY_OUTBOUND_LIVE_SESSION=NO`。
- 把风机 kW(e) 从设备发明出来。
- 收口 TD-008 电力/设备目录剩余；删 Path A `save_inputs`。
- 重开 #11 / #13 / #17 / #176 / #20。
