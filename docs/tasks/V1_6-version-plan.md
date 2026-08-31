# V1.6 总计划：电力风机演示目录一份权威

**状态：** 已发布（V1.6 v05 power-fan demo catalog）  
**产品标签：** `v1.6.0` at `cd702b0`（闸门块保持历史冻结）  
**上一产品标签：** `v1.5.0`  
**基线 `main` SHA：** `536603d`  
**权威：** Charles 选定主题 — TD-008 剩余中的**风机电气目录**（不是从设备发明 kW(e)）：蒸发/冷凝风机不再一边内核默认 0、一边 Aily 硬编码 10/8。工作台组装器与豆包预览读**同一份** `samples/v05-local-workbench/manifest.json` 叶子。  
**打开这一份即可看懂 1.6 做什么。** 实现合同见
[`V1_6-P0-power-fan-catalog-contract.md`](V1_6-P0-power-fan-catalog-contract.md)，
决策记录见 [`ADR-038`](../architecture/ADR-038-v05-power-fan-demo-catalog.md)。

```text
TASK=V16_OVERALL_VERSION_PLAN_R1
GOVERNANCE_OWNER=V1.6
PREVIOUS_RELEASE=v1.5.0
BASE_MAIN_SHA=536603d
TARGET_FILE=docs/tasks/V1_6-version-plan.md
V16_IMPLEMENTATION_AUTHORIZED=YES
V16_P0_IMPLEMENTATION_AUTHORIZED=YES
TD008_POWER_FAN_DEMO_AUTHORITY=YES
TD008_EQUIPMENT_CATALOG_UNIFIED=NO
FAN_KW_FROM_EQUIPMENT=NO
KEEP_INSTALLED_POWER_VERSION=YES
KEEP_OPERATOR_SCHEMA=OperatorProcessInputV1@1.1.0
AILY_OUTBOUND_LIVE_SESSION=NO
FORMULA_RECUT_AUTHORIZED=NO
KEEP_AILY_V15_SKILL_FROZEN=YES
KEEP_AILY_V16_SKILL=YES
KEEP_CALCULATOR_IDENTITY=cold_room_zone_plan@1.0.0,cooling_load@1.0.0,equipment@1.0.0,installed_power@1.0.0,investment_estimate@1.0.0
KEEP_ZONE_PLAN_VERSION=YES
KEEP_COOLING_LOAD_VERSION=YES
KEEP_EQUIPMENT_VERSION=YES
KEEP_INVESTMENT_VERSION=YES
NO_STEP_IMPLIES_THE_NEXT=TRUE
AGENT_TO_ENGINEERING_VALUE=NO
DELETE_PATH_A_SAVE_INPUTS=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
MARK_REVIEWED_AS_MODEL_TOOL=NO
EXTEND_API_V1_AGENT_FOR_AILY=NO
POWER_CONFIGURATION_REPLACES_INSTALLED_POWER=NO
COOLING_LOAD_FORMULA_RECUT=NO
EQUIPMENT_FORMULA_RECUT=NO
INSTALLED_POWER_FORMULA_RECUT=NO
INVESTMENT_FORMULA_RECUT=NO
V05_COMPRESSOR_120_NOT_AUTHORITY=YES
```

`V16_IMPLEMENTATION_AUTHORIZED=YES`：本文件冻结「1.6 做什么」。产品标签
`v1.6.0` 已打在 `cd702b0`。本文件闸门保持历史冻结，不改写成 V1.7。
不移动 `v1.5.0` / `v1.6.0`。

---

## 1. 一句话

产品身份仍是 **豆包工作伙伴**。V1.5 已发布。V1.6 让蒸发/冷凝风机电气 kW(e) 以 v05 工作台样本为**唯一演示目录**：`10.0` / `8.0`，`source_type=demo`。压缩机仍来自设备结果。不 bump `installed_power@1.0.0`。不把内核 dataclass 默认改成 10/8。

## 2. 目录合同（冻结后不可默默改）

内核 [`power.py`](../../backend/src/cold_storage/modules/calculations/domain/power.py) 的
`InstalledPowerCalcInput` 风机默认仍是 **`0` / `0`**（缺输入 fail-closed）。
**不要**把 dataclass 默认改成 10/8。

本版唯一演示权威（读值，诚实标记一律 demo）：

```text
installed_power_inputs.evaporator_fan_power_kw_e = 10.0
installed_power_inputs.condenser_fan_power_kw_e  = 8.0
source_type=demo
validity_status=unverified
requires_review=true
source_path=samples/v05-local-workbench/manifest.json
```

共享读取模块（工作台组装器 + Aily，**禁止第二套字面量**）：

[`projects/application/demo_power_fan_catalog.py`](../../backend/src/cold_storage/modules/projects/application/demo_power_fan_catalog.py)

v05 压缩机 `120.0` **不是**操作员权威（`V05_COMPRESSOR_120_NOT_AUTHORITY=YES`）。
九区设备目录不从 v05 单区 `Z1` 重调（`TD008_EQUIPMENT_CATALOG_UNIFIED=NO`）。

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

## 4. 诚实标志与表注（成功路径）

压缩机路径保持：

```text
power_from_demo_catalog: false
```

风机表注：**蒸发/冷凝风机电气来自 v05 演示目录（10 / 8 kW(e)），不是设备结果，需复核。**

V1.5 围护血缘保持已发布语义（本版不重切公式）：

```text
floor_area_from_zone_plan: true
envelope_wall_roof_from_plan: true
formula_recut_authorized: true
```

本版闸门 `FORMULA_RECUT_AUTHORIZED=NO`：不授权新的公式重切。

## 5. 包划分

| 切片 | 内容 |
|---|---|
| **P0** | 身份 `v1.5.0` 已发布；本总计划 + 合同 + ADR-038 |
| **P1** | 共享读 v05 10/8；组装器 demo 叶；工作台五阶段与预览对齐 |
| **P2** | Aily 删硬编码 10/8；表注/MCP 文案/测试；不 import calculations |
| **P3** | v1.6 技能 + 手册；冻结 v1.5 技能指针；`v1.6.0` 仅在 **main HEAD CI 绿** 后打 |

V1.5 技能文件保持冻结：`docs/contracts/aily/v1.5/**`。
V1.3 技能保持冻结：`docs/contracts/aily/v1.3/**`。

可选只读 `GET /api/v1/demo/power-fan-catalog`（与 V1.4 五 KEY 演示 GET 同类）。
工程输入五 KEY 表单默认仍空。`demo_overview` 仍是遗留表面，不升格为新公式源。

## 6. 实现约束

- 工作台五阶段与豆包 `preview_installed_power` / `concept-preview` 风机叶子走同一加载器。
- Aily API / MCP / application **不得** `import cold_storage.modules.calculations`。
- Vue / 报告模板 / prompt **不得** 写装机功率公式，也不得第二套 10/8 字面量当计算源。
- 不扩展 `/api/v1/agent/**`。`mark_reviewed` / `approve` 不是模型工具。
- 不移动标签 `v0.9.0` / `v1.0.0` / `v1.1.0` / `v1.2.0` / `v1.3.0` / `v1.4.0` / `v1.5.0`。
- Issues **#11 / #13 / #17 / #176 / #20** 保持 CLOSED。

## 7. 本版不做

- 从设备 / COP 发明风机 kW(e)（`FAN_KW_FROM_EQUIPMENT=NO`）。
- bump `installed_power@1.0.0` 或任何计算器 `@1.0.0`。
- 改五 KEY；吨≠每天；豆包解析聊天。
- 把 `InstalledPowerCalcInput` 风机默认改成 10/8。
- 把 v05 压缩机 `120` 当操作员权威。
- 用 v05 `Z1` 重调九区设备目录。
- TD-024 出站；`AILY_OUTBOUND_LIVE_SESSION=NO`。
- 删 Path A `save_inputs`。
- 重开 #11 / #13 / #17 / #176 / #20。
- 再做一遍 V1.5 墙/屋面绑定（已发布）。
