# V1.9 总计划：逐个区域核算冷量计算公式

**状态：** 定义冻结（等待 Charles 授权实现）  
**上一产品标签：** `v1.8.0` at `ae3814f`  
**基线 `main` SHA：** `ae3814f`  
**权威：** Charles 选定主题 — 下一版主要核对一件事：**每个制冷分区的冷量计算公式。**  
这是**按区露出内核已有 `CalculationStep`（公式 + 输入 + 结果）**（默认），不是改 `Q = U × A × ΔT`，也不是让模型重算 kW(r)。  
改公式必须另开 `FORMULA_RECUT_AUTHORIZED=YES`，且不得 bump 计算器身份，除非 Charles 另批。  
**打开这一份即可看懂 1.9 打算做什么。**

```text
TASK=V19_OVERALL_VERSION_PLAN_R1
GOVERNANCE_OWNER=V1.9
PREVIOUS_RELEASE=v1.8.0
BASE_MAIN_SHA=ae3814f
TARGET_FILE=docs/tasks/V1_9-version-plan.md
V19_IMPLEMENTATION_AUTHORIZED=NO
V19_P0_IMPLEMENTATION_AUTHORIZED=NO
COOLING_ZONE_FORMULA_AUDIT_SURFACE=YES
KEEP_COOLING_LOAD_VERSION=YES
FORMULA_RECUT_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT=NO
ZONE_PRODUCT_MASS_CATALOG_RECUT=NO
ZONE_THERMAL_CATALOG_RECUT=NO
KEEP_OPERATOR_SCHEMA=OperatorProcessInputV1@1.1.0
KEEP_CALCULATOR_IDENTITY=cold_room_zone_plan@1.0.0,cooling_load@1.0.0,equipment@1.0.0,installed_power@1.0.0,investment_estimate@1.0.0
KEEP_ZONE_PLAN_VERSION=YES
KEEP_EQUIPMENT_VERSION=YES
KEEP_INSTALLED_POWER_VERSION=YES
KEEP_INVESTMENT_VERSION=YES
AILY_OUTBOUND_LIVE_SESSION=NO
KEEP_AILY_V18_SKILL_FROZEN=YES
KEEP_AILY_V19_SKILL=YES
AGENT_TO_ENGINEERING_VALUE=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
DELETE_PATH_A_SAVE_INPUTS=NO
TD008_EQUIPMENT_CATALOG_UNIFIED=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
MARK_REVIEWED_AS_MODEL_TOOL=NO
EXTEND_API_V1_AGENT_FOR_AILY=NO
```

`V19_IMPLEMENTATION_AUTHORIZED=NO`：本文件冻结「1.9 核算什么」。未收到 Charles **可以** 前不要改适配器、快照、工作台或豆包。
打标签 `v1.9.0` 仍等实现完成后 **main HEAD CI 全绿**。不移动 `v1.8.0`。

---

## 1. 一句话

产品身份仍是 **豆包工作伙伴**。V1.8 已发布。V1.9 让操作者能**按区**核对冷量：每一项用了哪条公式、打入了哪些数、内核算出多少 kW(r)。内核公式不动，`cooling_load@1.0.0` 不 bump。Vue / 豆包 / 报告只读持久化步骤，禁止重算。

## 2. 今天实际怎么算（核对对象，不是要改的公式）

内核 [`cooling_load.py`](../../backend/src/cold_storage/modules/calculations/domain/cooling_load.py) 对**每一个制冷分区**已经写出 `CalculationStep`：

```text
Q_zone = Q_transmission + Q_product + Q_infiltration + Q_internal + Q_defrost
```

| 分项 | 内核已有公式（本版默认不改） | 操作员最小路径上常见输入 |
|---|---|---|
| 围护传热 | `Q = U × A × ΔT`（墙/屋面：室外−室内；地板：邻室−室内，负值钳为 0）后 ÷1000 → kW(r) | U 墙/屋/地 0.25 / 0.20 / 0.30；室外 30°C；室内 V18-T1；面积来自分区几何 |
| 产品 | `m × c × ΔT / (t × 3600)` + 包装 + 呼吸（呼吸仅预冷/中温） | 每区 20000 kg/day；进货 20°C；目标跟室内；c=3.6；冷却 8 h；包装常为 0 |
| 渗透 | 显热 `ρ × V̇ × cp × ΔT / 3600`；有湿度时再加潜热 | 体积 = 面积 × 4.0 m；换气 0.5 次/h；湿度常缺 → 仅显热并告警 |
| 内部 | 人员 + 照明 + 设备散热 + 蒸发风机热 | 操作员路径人员/照明/风机功率多为 0，故内部常为 0 |
| 融霜 | `P × t × (1−η) / operating_hours / 1000` | 功率/时长多为 0，步骤常不出现 |
| 小计 | `transmission + product + infiltration + internal + defrost` | 与 V1.7 分区小计同一数字 |

然后按 `temperature_level` 分组，乘演示 **多样性 0.85**，再乘演示 **设计裕量 1.10**（全厂步骤 `CL-GROUP` / `CL-FINAL`，不是分区公式）：

```text
Q_level_diversified = Σ Q_zone × diversity_factor
Q_design = Σ Q_level_diversified × design_margin_ratio
```

面积血缘（V1.5，已发布，本版不重切）：

```text
floor_area = zone_area = required_area_m2
roof_area  = floor_area
wall_area  = room_height × 4 × √floor_area   # 正方形平面；4 是四边，不是 4 m
room_height = V18-H1 演示目录 4.0 m
```

室内温度（V1.8，已发布，本版不重切）：规划温区低端 8.0 / 1.0 / −18.0 °C。常温间不进冷量。五个 KEY 不变。吨 = 每天。

## 3. 今天核算时会看到的缺口

内核**已经**按区写出公式、输入、结果。落到操作者眼前时被收窄了：

| 表面 | 现在能看到什么 |
|---|---|
| 工作台冷负荷分区表 | V1.7 五项 kW(r) + V1.8 °C / m；**没有公式，没有逐步输入** |
| 豆包冷量分区表 | 与工作台同一套列 |
| 适配器冷却快照 | 拷贝五项 + T/H；`_build_steps` 已能把 `CalculationStep` 译成 dict，**但没有写进冷却 payload** |
| 工作台「计算依据」 | 读 `formula_references`；新内核走 `steps`，冷却这条路径通常**空** |
| 全厂分项标量 | 传热/产品显热/包装/渗透/人员/照明/风机/融霜/裕量合计，不是逐步公式 |

诚实问题（本版**默认不改数字来源**，只把公式步骤露出来）：

- 九个制冷分区货品质量仍共用 v05 **20000 kg/day**。
- U 值、室外 30°C、进货 20°C、冷却 8 h、c=3.6、换气 0.5、多样性 0.85、裕量 1.10 仍是演示目录。
- 内部和融霜在操作员最小路径上经常是 0（缺人员/照明/风机/融霜功率叶子）。
- 湿度常缺，渗透只算显热。

**不把公式改成别的算法。** 那是 `FORMULA_RECUT_AUTHORIZED=YES`（本版默认 NO）。  
**不把每区 20 吨改成分区真货量。** 那是 `ZONE_PRODUCT_MASS_CATALOG_RECUT=YES`（本版 NO）。

## 4. 本版默认要露出的核算表（成功路径，授权后）

每个制冷分区持久化并展示内核 `CalculationStep` 拷贝（**禁止 Vue / prompt / 报告重算或改写公式字符串**）：

```text
zone_code
zone_name
step_id
output_name          # 如 total_transmission_load_kw_r
formula              # 内核已有字符串，原样拷贝
inputs               # 内核已有输入叶子，原样拷贝
output_value         # 内核已有结果
```

工作台与豆包增加**同一张**分区公式表（列一致）。V1.7 五项数字列和 V1.8 °C / m 列保持。设备血缘仍只绑 `zone_code` + `subtotal_load_kw_r`。

全厂多样性 / 裕量步骤可同表附在末尾（无 `zone_code`），并标明不是分区公式。

诚实表注：

**分区公式与输入来自内核 CalculationStep，未改公式；U 值、货品质量、换气与裕量仍为演示目录，需复核。**

成功标志保持 V1.5 / V1.7 / V1.8：

```text
floor_area_from_zone_plan: true
envelope_wall_roof_from_plan: true
formula_recut_authorized: true   # 历史 V1.5 几何重切，本版不再新授权公式
```

本版闸门 `FORMULA_RECUT_AUTHORIZED=NO`：不授权新的公式重切。

历史没有公式步骤的冷却快照仍须能解析（新列 / 新表 optional，`extra="forbid"`）。

## 5. 操作者五个 KEY（不变）

```text
zone_planning_inputs.daily_inbound_mass_kg
zone_planning_inputs.finished_storage_days
zone_planning_inputs.frozen_storage_days
zone_planning_inputs.main_packaging_storage_days
zone_planning_inputs.auxiliary_packaging_storage_days
```

缺 KEY → `MISSING_ENGINEERING_PARAMETER` + `ask_operator`。不为核算新加 KEY。

## 6. 包划分（授权后）

| 切片 | 内容 |
|---|---|
| **P0** | 身份跟上 `v1.8.0`；本合同 + ADR（露出步骤，不改内核公式） |
| **P1** | 适配器把分区 `CalculationStep` 写入冷却快照；历史快照仍解析 |
| **P2** | 工作台 + 豆包分区公式表对齐；表注/测试；Aily 不 import calculations；Vue 源码不含公式字面量 |
| **P3** | v1.9 技能 + 手册；冻结 v1.8 技能；`v1.9.0` 仅 **main HEAD CI 绿** 后打 |

## 7. 等 Charles 拍板的两件事

1. **实现授权：** 回复 **可以** 后才改代码。未授权只冻结本合同。  
2. **若其实要改公式：** 必须显式把 `FORMULA_RECUT_AUTHORIZED` 改成 YES，并另批要改哪一条、改成什么。默认**不改**。

## 8. 本版不做

- 改 `Q = U × A × ΔT` 或 bump `cooling_load@1.0.0`。
- 在 Vue / 报告模板 / prompt 里重算或硬编码公式。
- 把每区货品质量 / U 值 / 换气改成「真热工」（除非 Charles 改对应闸门）。
- 从设备或 COP 反推 kW(r)。
- 改五 KEY；吨≠每天；豆包解析聊天。
- TD-024 出站；`AILY_OUTBOUND_LIVE_SESSION=NO`。
- 删 Path A `save_inputs`；收口九区设备目录。
- 重开 #11 / #13 / #17 / #176 / #20。
- 移动 `v1.8.0` 及更早产品标签。
- 改冻结的 `docs/contracts/aily/v1.8/**`。
