# V1.3 总计划：对话预览对齐工作台血缘

**状态：** 实现已授权（V1.3 inbound preview lineage）  
**上一产品标签：** `v1.2.0`  
**基线 `main` SHA：** `cb8a00b`  
**权威：** 推荐主题 — 豆包五阶段预览在内存里走与工作台相同的阶段血缘；不重切公式、不落库、不开出站  
**打开这一份即可看懂 1.3 做什么。** 实现合同见
[`V1_3-P0-aily-preview-lineage-contract.md`](V1_3-P0-aily-preview-lineage-contract.md)，
决策记录见 [`ADR-035`](../architecture/ADR-035-aily-preview-workbench-lineage.md)。

```text
TASK=V13_OVERALL_VERSION_PLAN_R1
GOVERNANCE_OWNER=V1.3
PREVIOUS_RELEASE=v1.2.0
BASE_MAIN_SHA=cb8a00b
TARGET_FILE=docs/tasks/V1_3-version-plan.md
V13_IMPLEMENTATION_AUTHORIZED=YES
V13_P0_IMPLEMENTATION_AUTHORIZED=YES
AILY_INBOUND_PREVIEW_LINEAGE=YES
AILY_OUTBOUND_LIVE_SESSION=NO
FORMULA_RECUT_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT=NO
EQUIPMENT_FORMULA_RECUT=NO
INSTALLED_POWER_FORMULA_RECUT=NO
INVESTMENT_FORMULA_RECUT=NO
ENVELOPE_FROM_ZONE_AREA=floor_and_zone_area_only
ENVELOPE_WALL_ROOF_FROM_PLAN=NO
KEEP_OPERATOR_SCHEMA=OperatorProcessInputV1@1.1.0
KEEP_ZONE_PLAN_VERSION=YES
KEEP_COOLING_LOAD_VERSION=YES
KEEP_EQUIPMENT_VERSION=YES
KEEP_INSTALLED_POWER_VERSION=YES
KEEP_INVESTMENT_VERSION=YES
KEEP_CALCULATOR_IDENTITY=cold_room_zone_plan@1.0.0,cooling_load@1.0.0,equipment@1.0.0,installed_power@1.0.0,investment_estimate@1.0.0
AGENT_TO_ENGINEERING_VALUE=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
MARK_REVIEWED_AS_MODEL_TOOL=NO
EXTEND_API_V1_AGENT_FOR_AILY=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

`V13_IMPLEMENTATION_AUTHORIZED=YES`：本文件冻结「1.3 做什么」且实现已授权。
代码、技能包见 P1–P3；打标签 `v1.3.0` 仍等 `main` HEAD CI 全绿后。

---

## 1. 一句话

V1.2 已经让豆包能出示五张概念表。V1.3 让后面四张表的数字
**跟操作员工作台「跑完分区再往下」一致**：分区面积进入冷量地板面积，
设备电气 kW(e) 进入装机功率，分区合计与功率进入投资估算。
仍然不落库、不重切公式、不从墙/屋面几何发明面积。

## 2. 为什么是这一包（V1.2 留下的用户可见缺口）

豆包工作伙伴在 V1.2 可以问分区 / 冷量 / 设备 / 功率 / 投资。
诚实缺口是对话预览 **没有走工作台已有的阶段血缘**（因为对话 `persisted: false`）：

| 绑定 | V1.2 对话 | V1.3 对话（本版） | 工作台落库后 |
|---|---|---|---|
| 分区 `required_area_m2` → 冷量 `floor_area` / `zone_area` | 否（演示目录） | 是（内存） | 已有 |
| 冷量 kW(r) → 设备 | 已有字段拷贝 | 保持 | 已有 |
| 设备 kW(e) → 装机功率 | 否（演示 120 / 10 / 8 kW(e)） | 是 | 已有 |
| 分区合计 + 功率 → 投资 | 否（演示 1000 / 800 / 200 m² 等） | 是 | 已有 |
| 墙 / 屋面面积、U 值从几何推导 | 否 | **否** | 否 |
| 对话写入项目版本 / 出站飞书会话 | 否 | **否** | 工作台有落库；出站仍关 |

工作台落库路径已经在
[`five_stage_execution.py`](../../backend/src/cold_storage/modules/projects/application/five_stage_execution.py)
里绑定地板面积（V0.8：`ZONE_RESULT_TO_COOLING_LOAD_IDENTITY_AND_PLAN_AREA_LINEAGE=YES`）。
V0.8 同时锁死 `ZONE_RESULT_TO_COOLING_LOAD_ENVELOPE_AUTO_FEED=NO`：
**不得**用分区面积悄悄推出墙、屋面面积。V1.3 遵守同一条。

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

## 4. 对话流程（与 V1.2 相同，只改数字来源）

1. 用户自然说；豆包把「吨」当成每天吨。
2. 缺 KEY → `ask_operator`，禁止默默填。
3. 五个 KEY 齐 → **仍然先** `preview_zone_plan`。
4. 用户问冷量 / 设备 / 功率 / 投资 → 同一套 MCP 工具或 REST `concept-preview`；
   豆包原样展示 `markdown_table`。
5. 成功回复仍声明：概念设计、需复核、演示系数、`requires_review=true`。
6. 诚实话术改为：**地板 / 规划面积来自分区结果；墙、屋面、U 值仍是演示目录。**

飞书 MCP 地址不变：`{ORIGIN}/api/v1/aily/v1/mcp/sse`（Streamable HTTP，不要 GET SSE）。
隧道仍指后端 `:8000`，不是 Vite `:5173`。

## 5. 包划分

| 包 | 内容 | 本文件冻结时 |
|---|---|---|
| **P0** | 本总计划 + P0 合同 + ADR-035 | 本 PR（定义冻结；实现未授权） |
| **P1** | 预览编排复用工作台血缘（地板面积 / 设备 kW(e) / 投资） | 派发后 |
| **P2** | REST / MCP 标志位与测试 | 派发后 |
| **P3** | v1.3 技能包 + 操作手册；冻结 v1.2 | 派发后 |
| 标签 | `v1.3.0` 仅在 `main` HEAD CI 全绿后 | 派发后 |
| Later | 墙/屋面几何重切 | `FORMULA_RECUT_AUTHORIZED=NO` |
| Later | 出站直播豆包会话 | `AILY_OUTBOUND_LIVE_SESSION=NO` |

V1.2 文件保持冻结：`docs/contracts/aily/v1.2/**`、
[`V1_2-version-plan.md`](V1_2-version-plan.md)、ADR-034。

## 6. 实现约束（派发后仍必须遵守）

- Aily API / MCP / application **不得** `import cold_storage.modules.calculations`。
- **不得**在 aily 里用 COP 从 kW(r) 推 kW(e)。
- 复用工作台绑定语义，不复制工程公式到 Vue、报告模板或 prompt。
- 设备规范快照保留 `total_compressor_input_power_kw_e`，或预览走工作台已有的电气捕获适配器。
- 不扩展 `/api/v1/agent/**`。`mark_reviewed` / `approve` 不是模型工具。
- 不移动标签 `v0.9.0` / `v1.0.0` / `v1.1.0` / `v1.2.0`。
- Issues **#11 / #13 / #17 / #176 / #20** 保持 CLOSED。

## 7. 本版不做

- 墙 / 屋面由层高 × 周长推出来（那才是冷量几何重切）。
- TD-024 豆包出站直连（需要飞书租户技能配线）。
- 工作台债务 TD-023 / TD-008 / TD-019。
- 系数晋级、生产 RBAC、施工图、现场设备控制。
- 改五个 KEY；解析聊天；对话写入已批准项目版本。

## 8. 备选主题（只有 Charles 明确要才换）

1. 冷量几何重切（墙/屋面从分区面积推导）— 更大，工作台和豆包一起改，可能 bump `cooling_load` VERSION。
2. 只修设备快照电气 kW(e) — 功率表诚实，冷量和投资仍演示。
3. 出站 TD-024 — 前置是飞书配线，仓库不能独自完成。

## 9. 派发后流程

1. Charles 回复可以按本计划做（或点名换成第 8 节某一备选）。
2. 将 `V13_IMPLEMENTATION_AUTHORIZED` 改为 `YES`。
3. 开实现分支 `cursor/v13-preview-lineage-742e`（与本计划分支分开）。
4. 先合合同/ADR 已冻结内容，再改代码与技能。
5. 主干 CI 全绿后再打 `v1.3.0`，再告诉 Charles `git pull`。
