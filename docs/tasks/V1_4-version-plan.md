# V1.4 总计划：操作员工作台债务（TD-023 + TD-008）

**状态：** 已发布（V1.4 workbench debt）  
**产品标签：** `v1.4.0` at `c58f0ae`（闸门块保持历史冻结）  
**上一产品标签：** `v1.3.0`  
**基线 `main` SHA：** `0496010`  
**权威：** Charles 选定主题 — TD-023 引导步改名 + TD-008 演示数字一份权威；合成一个版本  
**打开这一份即可看懂 1.4 做什么。** 实现合同见
[`V1_4-P0-workbench-debt-contract.md`](V1_4-P0-workbench-debt-contract.md)，
决策记录见 [`ADR-036`](../architecture/ADR-036-workbench-operator-input-and-demo-defaults.md)。

```text
TASK=V14_OVERALL_VERSION_PLAN_R1
GOVERNANCE_OWNER=V1.4
PREVIOUS_RELEASE=v1.3.0
BASE_MAIN_SHA=0496010
TARGET_FILE=docs/tasks/V1_4-version-plan.md
V14_IMPLEMENTATION_AUTHORIZED=YES
V14_P0_IMPLEMENTATION_AUTHORIZED=YES
TD023_OPERATOR_PROCESS_INPUT_STEP=YES
TD008_OPERATOR_DEMO_FIVE_KEY_AUTHORITY=YES
TD008_POWER_EQUIPMENT_CATALOG_UNIFIED=NO
AILY_OUTBOUND_LIVE_SESSION=NO
FORMULA_RECUT_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT=NO
EQUIPMENT_FORMULA_RECUT=NO
INSTALLED_POWER_FORMULA_RECUT=NO
INVESTMENT_FORMULA_RECUT=NO
ENVELOPE_WALL_ROOF_FROM_PLAN=NO
KEEP_OPERATOR_SCHEMA=OperatorProcessInputV1@1.1.0
KEEP_ZONE_PLAN_VERSION=YES
KEEP_COOLING_LOAD_VERSION=YES
KEEP_EQUIPMENT_VERSION=YES
KEEP_INSTALLED_POWER_VERSION=YES
KEEP_INVESTMENT_VERSION=YES
KEEP_CALCULATOR_IDENTITY=cold_room_zone_plan@1.0.0,cooling_load@1.0.0,equipment@1.0.0,installed_power@1.0.0,investment_estimate@1.0.0
KEEP_AILY_V13_SKILL=YES
AGENT_TO_ENGINEERING_VALUE=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
MARK_REVIEWED_AS_MODEL_TOOL=NO
EXTEND_API_V1_AGENT_FOR_AILY=NO
DELETE_PATH_A_SAVE_INPUTS=NO
POWER_CONFIGURATION_REPLACES_INSTALLED_POWER=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

`V14_IMPLEMENTATION_AUTHORIZED=YES`：本文件冻结「1.4 做什么」。产品标签
`v1.4.0` 已打在 `c58f0ae`。本文件闸门保持历史冻结，不改写成 V1.5。

---

## 1. 一句话

V1.3 已经让豆包预览走工作台血缘。V1.4 还操作员工作台两笔公开债务：
引导第一步改成与「工程输入」一致的 `OPERATOR_PROCESS_INPUT`，
五 KEY 才是输入权威；操作员演示数字以 `samples/v09-process-input` 为唯一来源。

## 2. 为什么是这一包

| 债务 | 现状 | 本版 |
|---|---|---|
| TD-023 | 引导步仍叫 `PROJECT_INPUT`；V0.4 `save_inputs` 单独即可把第一步标成完成；下一步文案 `Complete project input` | 步骤 id `OPERATOR_PROCESS_INPUT`，文案「完成工程输入」；只有已持久化的 V0.9 五 KEY 或五阶段跑完才算输入完成 |
| TD-008 | Vue `parameterCatalog` / 遗留 `designInputs` 写 `25000` / `2.5` 天；规范样本是 `20000 / 7 / 10 / 4 / 12` | 五 KEY + 仓储天数默认只读这份样本；前端不再另写一套 |
| 墙/屋面几何 | 仍演示目录 | **本版不做** |
| TD-024 出站 | 关 | **本版不做** |
| 设备/电力演示目录双份 | 仍可指向 v05 catalog | **本版不假装清零**（`TD008_POWER_EQUIPMENT_CATALOG_UNIFIED=NO`） |

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

## 4. TD-023 行为（冻结）

- 操作员可见第一步稳定 id：**`OPERATOR_PROCESS_INPUT`**，对外文案「工程输入」。
- **输入权威：** 已持久化的 `OperatorProcessInputV1@1.1.0` 五 KEY，或 `five_stage_complete`（五阶段规范计算器已齐）。
- V0.4 `save_inputs` **不再单独**把引导步进到「已完成」。Path A `save_inputs` 接口保留（`DELETE_PATH_A_SAVE_INPUTS=NO`）。
- 空 snapshot 的缺失 KEY 列表继续是 V0.9 五 KEY，不把已删 KEY（如 `working_time_h_per_day`）当缺失。
- 工作流聚合契约版本随步骤 id 变更为 **`WorkflowAggregateV2`**。
- 下一步文案：第一步为「完成工程输入」。

## 5. TD-008 行为（冻结）

- **唯一操作员演示权威：** [`samples/v09-process-input/manifest.json`](../../samples/v09-process-input/manifest.json) 的五 KEY：`20000 / 7 / 10 / 4 / 12`。
- 前端不得再内嵌第二套五 KEY / 仓储天数演示数字；缺省值从该样本（共享 typed fixture）或后端只读接口读取。Vue 仍不算公式。
- `GET /api/v1/demo/overview`（`demo_overview.py`）标成**遗留 overview、非操作员默认**；本版不把 overview 改成新公式源，也不改其计算器输入以免假装它是操作员权威。
- 工程输入表单默认仍为空（禁止默默替操作员填 KEY）；遗留 V0.4 设计输入页的 ton/天与仓储天数默认改读 v09。
- 风机 kW(e)、墙屋面目录仍可指向 `samples/v05-local-workbench/manifest.json`。

## 6. 包划分

| 包 | 内容 |
|---|---|
| **P0** | 本总计划 + P0 合同 + ADR-036；身份文档跟上 `v1.3.0` |
| **P1** | TD-023 步骤 id、完成条件、文案、前后端测试 |
| **P2** | TD-008 五 KEY / 仓储天数单一来源 + 测试 |
| **P3** | 冻结 V1.3 技能指针（不改预览公式）；`v1.4.0` 仅在 `main` HEAD CI 全绿后 |

V1.3 文件保持冻结：`docs/contracts/aily/v1.3/**`、
[`V1_3-version-plan.md`](V1_3-version-plan.md)、ADR-035。
飞书仍粘贴 V1.3 技能；本版不发新技能包。

## 7. 实现约束

- Aily API / MCP / application **不得** `import cold_storage.modules.calculations`。
- 不扩展 `/api/v1/agent/**`。`mark_reviewed` / `approve` 不是模型工具。
- 不把公式写进 Vue / 报告模板 / prompt。
- 不把 `power_configuration` 提升成替代 `installed_power`。
- 不移动标签 `v0.9.0` / `v1.0.0` / `v1.1.0` / `v1.2.0` / `v1.3.0`。
- Issues **#11 / #13 / #17 / #176 / #20** 保持 CLOSED。

## 8. 本版不做

- 墙 / 屋面由几何推导（`FORMULA_RECUT_AUTHORIZED=NO`）。
- TD-024 豆包出站直连。
- TD-019 系数元数据晋级。
- 删 Path A `save_inputs`。
- 生产 RBAC、施工图、现场设备控制。
- 改五个 KEY；解析聊天。
