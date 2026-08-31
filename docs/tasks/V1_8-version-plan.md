# V1.8 总计划：理清每个区域的温度和层高

**状态：** 实现已授权（本包落地；等 main HEAD CI 绿后打 `v1.8.0`）  
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
V18_IMPLEMENTATION_AUTHORIZED=YES
V18_P0_IMPLEMENTATION_AUTHORIZED=YES
ZONE_THERMAL_INPUT_SURFACE=YES
ZONE_TEMPERATURE_FROM_ZONE_PLAN_BAND=YES
ZONE_TEMPERATURE_BAND_POINT=COLD_END
ZONE_TEMPERATURE_CATALOG_RECUT=YES
ZONE_HEIGHT_CATALOG_RECUT=YES
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

`V18_IMPLEMENTATION_AUTHORIZED=YES`：Charles 已回复「可以」。按 V18-T1 / V18-H1 实现。
打标签 `v1.8.0` 仍等实现完成后 **main HEAD CI 全绿**。不移动 `v1.7.0`。

---

## 1. 一句话

产品身份仍是 **豆包工作伙伴**。V1.7 已发布。V1.8 让操作者能按区看到冷却真正用的 **室内设计温度 °C** 和 **层高 m**。内核公式不动，`cooling_load@1.0.0` 不 bump。Charles 已批：**九个制冷分区层高一律 4.0 m**；室内设计温度**跟分区规划温区走，区间取低端**（8~10℃ → 8.0；1~3℃ → 1.0；−18℃ → −18.0）。货品目标温度跟室内设计温度同一张表。**本包落地后等 main HEAD CI 绿再打 `v1.8.0`。**

## 2. V1.7 核对对象（本版要改掉的血缘，不是公式）

分区规划已经按区登记了温区，冷却内核也已经按区读 `room_design_temperature` 和 `room_height`：

```text
Q_transmission ∝ U × A × (T_out − T_room)
V               = zone_area × room_height     # 渗透体积
wall_area       = room_height × 4 × √floor_area   # V1.5 正方形平面，本版不重切
```

公式在 [`cooling_load.py`](../../backend/src/cold_storage/modules/calculations/domain/cooling_load.py) 和 V1.5 绑定里，**本版不改**。

缺口曾在**输入血缘**：V1.7 组装器把 v05 单区演示目录打到**每一个**制冷分区：

```text
room_height              = 5.0 m
room_design_temperature  = -18.0 °C
product_target_temperature = -18.0 °C
outdoor_design_temperature = 30.0 °C
source_path = samples/v05-local-workbench/manifest.json
source_type = demo
```

分区规划温区（已有权威，`REFRIGERATED_ZONE_REGISTRY`）和冷却实际打入的数字对不上：

| 分区 | 规划温区 | 冷却室内设计温度（V1.7） | 冷却层高（V1.7） |
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

货品目标温度在 V1.7 也是每区 −18°C；货品质量仍是每区 20 t/天。**本版默认不改货品质量**（`ZONE_PRODUCT_MASS_CATALOG_RECUT=NO`）。

层高在仓库里**没有**第二份按区权威，只有 v05 的 5.0 m；本版用 Charles 批的 V18-H1 **4.0 m** 替换操作员最小路径层高，不改 v05 历史样本。

## 3. 操作者能看到什么

| 表面 | V1.7 | V1.8（本版落地） |
|---|---|---|
| 分区规划表 | **温区字符串**（8~10℃ / 1~3℃ / −18℃ / 常温），没有层高 | 不变 |
| 工作台冷负荷分区表 | `temperature_level` 枚举 + V1.7 五项冷量；**没有 °C，没有 m** | 增加室内设计温度 °C、层高 m |
| 豆包冷量分区表 | 与工作台同一套列 | 与工作台同一套列（含 °C / m） |
| 冷却输入叶子 | 每区已有 `room_design_temperature` / `room_height`，但结果快照不回写 | 快照回写内核实际使用的 °C / m |

诚实表注：室内设计温度取分区规划温区低端；层高演示 4.0 m；U 值与货品质量仍为 v05 演示目录，需复核。

## 4. 本版默认要露出的核对列（成功路径）

每个制冷分区在冷却快照 / 工作台 / 豆包分区表增加（拷贝冷却已经用过的输入，**禁止 Vue / prompt / 报告重算**）：

```text
room_design_temperature    # °C，内核该区实际使用的室内设计温度
room_height                # m，内核该区实际使用的层高
```

V1.7 五项冷量列保持。`temperature_level` 保持。历史只有五项的快照仍能解析（新列 optional）。设备血缘仍只绑 `zone_code` + `subtotal_load_kw_r`。

诚实表注：

**室内设计温度与层高按区回写冷却已用输入；层高为 Charles 演示目录 4.0 m；室内设计温度取分区规划温区低端（8 / 1 / −18 ℃），货品目标温度与之相同；U 值与货品质量仍为 v05 演示目录，需复核。**

层高从 5.0 改为 4.0 后，V1.5 墙面积绑定会用新高度，冷量数字和 golden hash **会变**；仍不 bump `cooling_load@1.0.0`。墙面积公式里的 `4` 是正方形四边，**不是**层高 4 米。

成功标志保持 V1.5 / V1.7：

```text
floor_area_from_zone_plan: true
envelope_wall_roof_from_plan: true
formula_recut_authorized: true   # 历史 V1.5 几何重切，本版不再新授权公式
```

本版闸门 `FORMULA_RECUT_AUTHORIZED=NO`：不授权新的公式重切。

目录数字已齐（层高 4.0 m，温区低端 8 / 1 / −18）；实现已授权。

## 5. 目录重切

```text
ZONE_TEMPERATURE_FROM_ZONE_PLAN_BAND=YES
ZONE_TEMPERATURE_BAND_POINT=COLD_END
ZONE_TEMPERATURE_CATALOG_RECUT=YES
ZONE_HEIGHT_CATALOG_RECUT=YES
ZONE_PRODUCT_MASS_CATALOG_RECUT=NO
ZONE_THERMAL_CATALOG_RECUT=NO
```

### 5.1 温度（规划温区低端）

Charles 2026-08-31：不要逐区重问温度，**用分区规划里已经登记的温区**；区间 **取低的**。权威是 `REFRIGERATED_ZONE_REGISTRY` / 分区规划结果的 `temperature_band`，单点规则是温区下限，不是 v05 的全局 −18°C，也不是中点。

<a id="V18-T1"></a>

| 规划温区 | 打入冷却的室内设计温度 °C |
|---|---|
| 8~10℃ | 8.0 |
| 1~3℃ | 1.0 |
| −18℃ | −18.0 |

按区展开：

| 分区 | 规划温区 | 室内设计温度 | 层高 |
|---|---|---|---|
| 一级预冷间 | 8~10℃ | 8.0 °C | 4.0 m |
| 二级预冷间 | 1~3℃ | 1.0 °C | 4.0 m |
| 原果暂存间 | 8~10℃ | 8.0 °C | 4.0 m |
| 分选包装间 | 8~10℃ | 8.0 °C | 4.0 m |
| 覆膜间 | 1~3℃ | 1.0 °C | 4.0 m |
| 成品间 | 1~3℃ | 1.0 °C | 4.0 m |
| 次果暂存间 | 8~10℃ | 8.0 °C | 4.0 m |
| 冻果间 | −18℃ | −18.0 °C | 4.0 m |
| 出货通道 | 1~3℃ | 1.0 °C | 4.0 m |

常温间不进冷量。

```text
source_type = demo
validity_status = unverified
requires_review = true
source_path = docs/tasks/V1_8-version-plan.md#V18-T1
```

同一温区的分区共用同一单点。**`product_target_temperature` 与 `room_design_temperature` 用同一张表**。未映射温区 fail-closed，禁止猜中点或热端。

温度和层高重切会改变 ΔT 与墙面积，因而改变冷量数字和 golden hash；**仍不 bump** `cooling_load@1.0.0`。

### 5.2 层高（Charles 已批）

<a id="V18-H1"></a>

Charles 2026-08-31：**九个制冷分区层高都是 4 米。**

```text
room_height = 4.0 m
source_type = demo
validity_status = unverified
requires_review = true
source_path = docs/tasks/V1_8-version-plan.md#V18-H1
```

不再使用 v05 的 5.0 m 作为操作员最小路径层高。不要改 `samples/v05-local-workbench/manifest.json` 历史样本；组装器改读本计划。V1.5 墙面积绑定消费该 4.0 m（公式已有，不重切）。缺层高仍 fail-closed。常温间不进冷量，本闸门不给常温间编层高。

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
| **P0** | 身份跟上 `v1.7.0`；本合同 + ADR（露出 T/H；层高 4.0 m；温区低端 8 / 1 / −18） |
| **P1** | 快照回写 `room_design_temperature` / `room_height`；组装器打 V18-T1 / V18-H1 |
| **P2** | 豆包分区表与工作台对齐；表注/测试；Aily 不 import calculations |
| **P3** | v1.8 技能 + 手册；冻结 v1.7 技能；`v1.8.0` 仅 **main HEAD CI 绿** 后打 |

## 8. 落地状态

1. **露出 T/H 两列** — 本包落地。  
2. **层高** — 已批并打入 4.0 m（V18-H1）。  
3. **温度** — 已批并打入规划温区低端 8.0 / 1.0 / −18.0；货品目标温度跟室内设计温度走（V18-T1）。  
4. Charles 已回复 **「可以」**；本切片落地后等 **main HEAD CI 绿** 再打 `v1.8.0`。不移动 `v1.7.0`。

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
