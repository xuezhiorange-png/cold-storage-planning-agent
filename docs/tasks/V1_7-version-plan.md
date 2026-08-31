# V1.7 总计划：按区核对制冷量如何计算

**状态：** 实现已授权（V1.7 per-zone cooling component surface）  
**上一产品标签：** `v1.6.0` at `cd702b0`  
**基线 `main` SHA：** `cd702b0`  
**权威：** Charles 选定主题 — 下一版主要核对一件事：**每个区域的制冷量是如何计算的。**  
这是**核对 / 露出内核已有分项**，不是改 `Q = U × A × ΔT`，也不是从设备发明冷量。  
**打开这一份即可看懂 1.7 打算做什么。**

```text
TASK=V17_OVERALL_VERSION_PLAN_R1
GOVERNANCE_OWNER=V1.7
PREVIOUS_RELEASE=v1.6.0
BASE_MAIN_SHA=cd702b0
TARGET_FILE=docs/tasks/V1_7-version-plan.md
V17_IMPLEMENTATION_AUTHORIZED=YES
V17_P0_IMPLEMENTATION_AUTHORIZED=YES
COOLING_ZONE_COMPONENT_SURFACE=YES
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
KEEP_AILY_V16_SKILL_FROZEN=YES
KEEP_AILY_V17_SKILL=YES
AGENT_TO_ENGINEERING_VALUE=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
DELETE_PATH_A_SAVE_INPUTS=NO
ZONE_THERMAL_CATALOG_RECUT=NO
TD008_EQUIPMENT_CATALOG_UNIFIED=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
MARK_REVIEWED_AS_MODEL_TOOL=NO
EXTEND_API_V1_AGENT_FOR_AILY=NO
```

`V17_IMPLEMENTATION_AUTHORIZED=YES`：本文件冻结「1.7 核对什么」且实现已授权。
打标签 `v1.7.0` 仍等 **main HEAD CI 全绿** 后。不移动 `v1.6.0`。

---

## 1. 一句话

产品身份仍是 **豆包工作伙伴**。V1.6 已发布。V1.7 让操作者能按区核对冷量：每个制冷分区的小计从哪五项来、用了哪些输入、哪些仍是演示目录。内核公式不动，`cooling_load@1.0.0` 不 bump。

## 2. 今天实际怎么算（核对对象，不是要改的公式）

内核 [`cooling_load.py`](../../backend/src/cold_storage/modules/calculations/domain/cooling_load.py) 对**每一个制冷分区**先算五项，再加总：

```text
Q_zone = Q_transmission + Q_product + Q_infiltration + Q_internal + Q_defrost
```

| 分项 | 内核公式（已有，本版不改） |
|---|---|
| 围护传热 | `Q = U × A × ΔT`（墙/屋面：室外−室内；地板：邻室−室内，负值钳为 0）后 ÷1000 → kW(r) |
| 产品 | `m × c × ΔT / (t × 3600)` + 包装 + 呼吸（呼吸仅预冷/中温） |
| 渗透 | 显热 `ρ × V̇ × cp × ΔT / 3600`；有湿度时再加潜热 |
| 内部 | 人员 + 照明 + 设备散热 + 蒸发风机热 |
| 融霜 | `P × t × (1−η) / operating_hours / 1000` |

然后按 `temperature_level` 分组，乘演示 **多样性 0.85**，再乘演示 **设计裕量 1.10**：

```text
Q_level_diversified = Σ Q_zone × diversity_factor
Q_design = Σ Q_level_diversified × design_margin_ratio
```

面积血缘（V1.5，已发布，本版不重切）：

```text
floor_area = zone_area = required_area_m2
roof_area  = floor_area
wall_area  = room_height × 4 × √floor_area   # 正方形平面
room_height = v05 演示目录 5.0 m
```

常温间不进冷量。五个 KEY 不变。吨 = 每天。

## 3. 今天核对时会看到的缺口

内核**已经**按区写出传热 / 产品 / 渗透 / 内部 / 融霜和小计（`CalculationStep` + zone dict）。

落到操作者眼前时被收窄了：

| 表面 | 现在能看到什么 |
|---|---|
| 豆包冷量表 | 全厂分项合计 + 分区表只有 **名称 + 小计 kW(r)** |
| 适配器持久化 `zones` | 往往只留 `zone_code` + `subtotal_load_kw_r`，分项在投影时丢掉 |
| 工作台冷负荷页 | 标量是全厂合计；分区表**想**显示分项列，但若快照被收窄则列空 |

更关键的诚实问题（本版**默认不改数字来源**，只标清楚）：

- 九个制冷分区共用 v05 演示热工：室内 **−18°C**、货品 **20000 kg/day**、进货 20°C、冷却 8 h、U 值 0.25/0.20/0.30。
- 各区真正不同的，主要是 **分区规划面积**（以及呼吸是否按温区启用）。
- 人员 / 照明 / 风机热 / 融霜功率在操作员最小路径上多为 0，所以内部和融霜经常是 0。
- 多样性 0.85、裕量 1.10、空气渗透系数仍是演示目录。

**不把「每区都摊 20 吨、都按 −18°C」改成分区真热工。** 那是另一次输入血缘重切（闸门 `ZONE_THERMAL_CATALOG_RECUT=NO`）。若 Charles 要把它并进 1.7，必须显式改闸门后再实现。

## 4. 本版要露出的核对表（成功路径）

每个制冷分区至少持久化并展示（读内核结果，**禁止 Vue / prompt / 报告重算**）：

```text
zone_code
zone_name
temperature_level
transmission_load_kw_r     # 围护
product_load_kw_r          # 产品（含包装/呼吸合计，与内核一致）
infiltration_load_kw_r
internal_load_kw_r
defrost_load_kw_r
subtotal_load_kw_r
```

可选（若快照已有、不新发明）：墙/屋面/地板传热三列。

豆包 `preview_cooling_load` / `concept-preview` 的分区表与工作台落库分区表**列一致**。
全厂合计表仍可保留，但须标明是各区加总后再乘多样性/裕量。

诚实表注（建议）：

**分区冷量按内核五项加总；面积来自分区几何（正方形平面 + 演示层高）；U 值、室内外设计温度、货品热工仍为演示目录（各区目前共用 v05 热工），需复核。**

成功标志保持 V1.5：

```text
floor_area_from_zone_plan: true
envelope_wall_roof_from_plan: true
formula_recut_authorized: true   # 历史 V1.5 几何重切，本版不再新授权公式
```

本版闸门 `FORMULA_RECUT_AUTHORIZED=NO`：不授权新的公式重切。

## 5. 操作者五个 KEY（不变）

```text
zone_planning_inputs.daily_inbound_mass_kg
zone_planning_inputs.finished_storage_days
zone_planning_inputs.frozen_storage_days
zone_planning_inputs.main_packaging_storage_days
zone_planning_inputs.auxiliary_packaging_storage_days
```

缺 KEY → `MISSING_ENGINEERING_PARAMETER` + `ask_operator`。不为核对新加 KEY。

## 6. 包划分（授权后）

| 切片 | 内容 |
|---|---|
| **P0** | 身份跟上 `v1.6.0`；本合同 + ADR（露出分项，不改内核公式） |
| **P1** | 适配器/落库不再丢掉分区五项；工作台读持久化结果 |
| **P2** | 豆包分区表与工作台对齐；表注/测试；Aily 不 import calculations |
| **P3** | v1.7 技能 + 手册；冻结 v1.6 技能；`v1.7.0` 仅 **main HEAD CI 绿** 后打 |

## 7. 本版不做

- 改 `Q = U × A × ΔT` 或 bump `cooling_load@1.0.0`。
- 在 Vue / 报告模板 / prompt 里重算分区冷量。
- 把每区货品质量 / 室内温度改成分区真热工（除非 Charles 改 `ZONE_THERMAL_CATALOG_RECUT=YES`）。
- 从设备或 COP 反推 kW(r)。
- 改五 KEY；吨≠每天；豆包解析聊天。
- TD-024 出站；`AILY_OUTBOUND_LIVE_SESSION=NO`。
- 删 Path A `save_inputs`；收口九区设备目录。
- 重开 #11 / #13 / #17 / #176 / #20。
- 移动 `v1.6.0` 及更早产品标签。
