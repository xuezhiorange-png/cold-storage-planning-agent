# V1.8 总计划：理清每个区域的温度和层高

**状态：** 定义已冻结，**实现未授权**（等 Charles 回复「可以」）  
**上一产品标签：** `v1.7.0` at `60f741c`  
**基线 `main` SHA：** `60f741c`  
**权威：** Charles 选定主题 — 下一版主要理清一件事：**每个制冷分区冷却实际用的室内设计温度和层高。**  
这是**按区露出已绑定输入**（默认），不是改 `Q = U × A × ΔT`，也不是让模型编 °C / m。  
按区改数字必须另开目录闸门，且数字必须来自已有仓库权威或 Charles 批的演示表。  
**打开这一份即可看懂 1.8 打算做什么。**

```text
TASK=V18_OVERALL_VERSION_PLAN_R1
GOVERNANCE_OWNER=V1.8
PREVIOUS_RELEASE=v1.7.0
BASE_MAIN_SHA=60f741c
TARGET_FILE=docs/tasks/V1_8-version-plan.md
V18_IMPLEMENTATION_AUTHORIZED=NO
V18_P0_IMPLEMENTATION_AUTHORIZED=NO
ZONE_THERMAL_INPUT_SURFACE=YES
ZONE_TEMPERATURE_CATALOG_RECUT=NO
ZONE_HEIGHT_CATALOG_RECUT=NO
ZONE_PRODUCT_MASS_CATALOG_RECUT=NO
ZONE_THERMAL_CATALOG_RECUT=NO
KEEP_COOLING_LOAD_VERSION=YES
FORMULA_RECUT_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT=NO
KEEP_OPERATOR_SCHEMA=OperatorProcessInputV1@1.1.0
KEEP_CALCULATOR_IDENTITY=cold_room_zone_plan@1.0.0,cooling_load@1.0.0,equipment@1.0.0,installed_power@1.0.0,investment_estimate@1.0.0
KEEP_ZONE_PLAN_VERSION=YES
KEEP_EQUIPMENT_VERSION=YES
KEEP_INSTALLED_POWER_VERSION=YES
KEEP_INVESTMENT_VERSION=YES
AILY_OUTBOUND_LIVE_SESSION=NO
KEEP_AILY_V17_SKILL_FROZEN=YES
KEEP_AILY_V18_SKILL=YES
AGENT_TO_ENGINEERING_VALUE=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
DELETE_PATH_A_SAVE_INPUTS=NO
TD008_EQUIPMENT_CATALOG_UNIFIED=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
MARK_REVIEWED_AS_MODEL_TOOL=NO
EXTEND_API_V1_AGENT_FOR_AILY=NO
```

`V18_IMPLEMENTATION_AUTHORIZED=NO`：本文件冻结「1.8 核对什么」，**在 Charles 回复「可以」之前不改组装器、内核、工作台、豆包。**  
打标签 `v1.8.0` 仍等实现完成后 **main HEAD CI 全绿**。不移动 `v1.7.0`。

---

## 1. 一句话

产品身份仍是 **豆包工作伙伴**。V1.7 已发布。V1.8 让操作者能按区看到冷却真正用的 **室内设计温度 °C** 和 **层高 m**。内核公式不动，`cooling_load@1.0.0` 不 bump。默认**不改**现在每区共用的 −18°C / 5.0 m。

## 2. 今天实际怎么用（核对对象，不是要改的公式）

分区规划已经按区登记了温区，冷却内核也已经按区读 `room_design_temperature` 和 `room_height`：

```text
Q_transmission ∝ U × A × (T_out − T_room)
V               = zone_area × room_height     # 渗透体积
wall_area       = room_height × 4 × √floor_area   # V1.5 正方形平面，本版不重切
```

公式在 [`cooling_load.py`](../../backend/src/cold_storage/modules/calculations/domain/cooling_load.py) 和 V1.5 绑定里，**本版不改**。

缺口在**输入血缘**：组装器把 v05 单区演示目录打到**每一个**制冷分区：

```text
room_height              = 5.0 m
room_design_temperature  = -18.0 °C
product_target_temperature = -18.0 °C
outdoor_design_temperature = 30.0 °C
source_path = samples/v05-local-workbench/manifest.json
source_type = demo
```

分区规划温区（已有权威，`REFRIGERATED_ZONE_REGISTRY`）和冷却实际打入的数字对不上：

| 分区 | 规划温区 | 冷却室内设计温度（今天） | 冷却层高（今天） |
|---|---|---|---|
| 一级预冷间 | 8~10℃ | −18.0 °C | 5.0 m |
| 二级预冷间 | 1~3℃ | −18.0 °C | 5.0 m |
| 原果暂存间 | 8~10℃ | −18.0 °C | 5.0 m |
| 分选包装间 | 8~10℃ | −18.0 °C | 5.0 m |
| 覆膜间 | 1~3℃ | −18.0 °C | 5.0 m |
| 成品间 | 1~3℃ | −18.0 °C | 5.0 m |
| 次果暂存间 | 8~10℃ | −18.0 °C | 5.0 m |
| 冻果间 | −18℃ | −18.0 °C | 5.0 m |
| 出货通道 | 1~3℃ | −18.0 °C | 5.0 m |

常温间不进冷量。五个 KEY 不变。吨 = 每天。

货品目标温度今天也是每区 −18°C；货品质量仍是每区 20 t/天。**本版默认不改货品质量**（`ZONE_PRODUCT_MASS_CATALOG_RECUT=NO`）。

层高在仓库里**没有**第二份按区权威，只有 v05 的 5.0 m。

## 3. 今天操作者能看到什么

| 表面 | 现在能看到什么 |
|---|---|
| 分区规划表 | **温区字符串**（8~10℃ / 1~3℃ / −18℃ / 常温），没有层高 |
| 工作台冷负荷分区表 | `temperature_level` 枚举 + V1.7 五项冷量；**没有 °C，没有 m** |
| 豆包冷量分区表 | 与工作台同一套列 |
| 冷却输入叶子 | 每区已有 `room_design_temperature` / `room_height`，但结果快照不回写 |

所以操作者无法在冷量页核对「这一区用了几度、几米」。

## 4. 本版默认要露出的核对列（成功路径）

每个制冷分区在冷却快照 / 工作台 / 豆包分区表增加（拷贝冷却已经用过的输入，**禁止 Vue / prompt / 报告重算**）：

```text
room_design_temperature    # °C，内核该区实际使用的室内设计温度
room_height                # m，内核该区实际使用的层高
```

V1.7 五项冷量列保持。`temperature_level` 保持。历史只有五项的快照仍能解析（新列 optional）。设备血缘仍只绑 `zone_code` + `subtotal_load_kw_r`。

诚实表注（建议，默认不改数字时）：

**室内设计温度与层高按区回写冷却已用输入；各区目前仍共用 v05 演示目录（−18°C / 5.0 m），与分区规划温区字符串不是同一份数字，需复核。**

成功标志保持 V1.5 / V1.7：

```text
floor_area_from_zone_plan: true
envelope_wall_roof_from_plan: true
formula_recut_authorized: true   # 历史 V1.5 几何重切，本版不再新授权公式
```

本版闸门 `FORMULA_RECUT_AUTHORIZED=NO`：不授权新的公式重切。

只做露出、不改目录时，冷量数字和 golden hash **应保持不变**（只多两列）。

## 5. 目录重切（默认关，须 Charles 显式改闸门并批数字）

默认：

```text
ZONE_TEMPERATURE_CATALOG_RECUT=NO
ZONE_HEIGHT_CATALOG_RECUT=NO
ZONE_PRODUCT_MASS_CATALOG_RECUT=NO
ZONE_THERMAL_CATALOG_RECUT=NO
```

### 5.1 温度

分区规划温区是**区间**（8~10℃、1~3℃），不是单点。V0.8 已写明：冷却不得把区间中点悄悄当成设计温度。

仓库里**没有**「8~10℃ → 某单点 °C」的已发布目录。因此：

- 禁止实现时用模型判断 8 / 9 / 10。
- 若 Charles 把 `ZONE_TEMPERATURE_CATALOG_RECUT` 改为 `YES`，必须同时批一张演示表（`source_type=demo`，`validity_status=unverified`，`requires_review=true`）。
- 为避免预冷间围护按 8~10℃、货品仍按冻到 −18℃，温度重切开启时 **`product_target_temperature` 与 `room_design_temperature` 用同一张表**。这不是公式重切。
- 未映射温区 fail-closed，禁止猜。

候选项（**未批准，不得当实现权威**；仅把已有温区字符串写成单点的两种读法）：

| 规划温区 | 候选项 A：区间冷端 | 候选项 B：继续今天 |
|---|---|---|
| 8~10℃ | 8.0 °C | −18.0 °C |
| 1~3℃ | 1.0 °C | −18.0 °C |
| −18℃ | −18.0 °C | −18.0 °C |

Charles 也可以另给表。中点 9 / 2 不是本文件的推荐，除非他指定。

温度重切会改变 ΔT，因而改变冷量数字和 golden hash；**仍不 bump** `cooling_load@1.0.0`。

### 5.2 层高

仓库只有 v05 **5.0 m**。没有按区 / 按温区的第二权威。

- 默认：九个制冷分区继续 5.0 m，但按区露出。
- 若 Charles 把 `ZONE_HEIGHT_CATALOG_RECUT` 改为 `YES`，必须给演示层高表。禁止模型编 6 m / 4.5 m。
- 层高若改，V1.5 墙面积绑定自动用新高度（公式已有，不重切）。缺层高仍 fail-closed。

### 5.3 本版仍不改

室外 30°C、U 值、每区 20 t 货品、冷却 8 h、多样性 0.85、裕量 1.10、设备蒸发温度默认 −10°C。

## 6. 操作者五个 KEY（不变）

```text
zone_planning_inputs.daily_inbound_mass_kg
zone_planning_inputs.finished_storage_days
zone_planning_inputs.frozen_storage_days
zone_planning_inputs.main_packaging_storage_days
zone_planning_inputs.auxiliary_packaging_storage_days
```

缺 KEY → `MISSING_ENGINEERING_PARAMETER` + `ask_operator`。不为温度/层高新加 KEY。

## 7. 包划分（授权后）

| 切片 | 内容 |
|---|---|
| **P0** | 身份跟上 `v1.7.0`；本合同 + ADR（露出 T/H，目录重切默认关） |
| **P1** | 快照回写 `room_design_temperature` / `room_height`；工作台读持久化结果。**仅当闸门 YES** 时组装器改目录 |
| **P2** | 豆包分区表与工作台对齐；表注/测试；Aily 不 import calculations |
| **P3** | v1.8 技能 + 手册；冻结 v1.7 技能；`v1.8.0` 仅 **main HEAD CI 绿** 后打 |

## 8. 请 Charles 在「可以」时一并确认

1. **露出 T/H 两列** — 本版默认要做。  
2. **温度是否改数字？** 默认否。若是：选冷端 8 / 1 / −18，或另给表；并确认货品目标温度跟室内设计温度走。  
3. **层高是否改数字？** 默认否（继续 5.0 m）。若是：请给按区或按温区演示表。

只回「可以」、不改闸门 → 只露出、不改 −18°C / 5.0 m。

## 9. 本版不做

- 改 `Q = U × A × ΔT` 或 bump `cooling_load@1.0.0`。
- 在 Vue / 报告模板 / prompt 里算 ΔT 或墙面积。
- 未批闸门就把每区温度/层高/货品质量改成「真热工」。
- 用温区中点当默认设计温度。
- 改五 KEY；吨≠每天；豆包解析聊天。
- TD-024 出站；`AILY_OUTBOUND_LIVE_SESSION=NO`。
- 删 Path A `save_inputs`；收口九区设备目录。
- 重开 #11 / #13 / #17 / #176 / #20。
- 移动 `v1.7.0` 及更早产品标签。
- 改冻结的 `docs/contracts/aily/v1.7/**`。
