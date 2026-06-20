# Coefficient Inventory

> **Audit date:** 2026-06-20
> **Branch:** `codex/task-3-coefficient-registry`
> **Purpose:** Comprehensive inventory of all hardcoded engineering coefficients,
> default parameters, cost factors, and equipment specifications in the Cold
> Storage Planning Agent codebase. This document serves as the baseline for
> the coefficient registry migration.

## Inventory Categories

| Category | Description |
|----------|-------------|
| `project_input` | User-provided or project-specific inputs with demo defaults |
| `engineering_coefficient` | Industry/empirical factors used in engineering formulas |
| `formula_constant` | Constants embedded in specific calculation formulas |
| `unit_conversion` | Values derived from unit conversion (excluded from inventory) |
| `demo_sample` | Hardcoded demo/project data used for demonstration |
| `equipment_spec` | Equipment-specific power and performance specifications |

## Registry Recommendation

Column `In Registry?` indicates whether the value should be migrated to the
coefficient registry:

- **YES** — Must be governed, versioned, and auditable
- **PARTIAL** — Some values are already exposed via `DemoZoneCoefficient`
- **NO** — Belongs in formula logic, equipment specs, or UI display
- **DEDUP** — Duplicate value found in multiple locations; consolidate

---

## 1. Zone Planning — Input Defaults (`ColdRoomZonePlanInput`)

Source file: `backend/src/cold_storage/modules/calculations/domain/zone_planning.py` (lines 14–55)

These are the default values applied when the user does not override them via API.

| # | Code | Name | Default | Unit | Category | In Registry? | Notes |
|---|------|------|---------|------|----------|:---:|-------|
| 1 | `raw_holding_hours` | 原果暂存小时数 | 6.6666666667 | h | `project_input` | YES | = 160/24 h; derived from 10h+2/3 day. Used as raw buffer time. |
| 2 | `storage_position_capacity_kg` | 存储板位单位容量 | 400 | kg | `engineering_coefficient` | DEDUP | ⚠️ Conflicts with DemoZoneCoefficient value of 500 (line 200) |
| 3 | `secondary_fruit_ratio` | 次果比例 | 0.08 | ratio | `engineering_coefficient` | YES | Proportion of daily inbound that becomes cull fruit |
| 4 | `frozen_fruit_ratio` | 冻果比例 | 0.10 | ratio | `engineering_coefficient` | DEDUP | ⚠️ Conflicts with DemoZoneCoefficient value of 0.05 (line 153) |
| 5 | `frozen_storage_days` | 冻果暂存天数 | 5 | day | `engineering_coefficient` | DEDUP | ⚠️ Conflicts with DemoZoneCoefficient value of 14 (line 159) |
| 6 | `precooling_position_daily_capacity_kg` | 预冷板位单位日处理量 | 1250 | kg/day | `engineering_coefficient` | YES | |
| 7 | `primary_precooling_pallet_weight_kg` | 一级预冷托盘重量 | 220 | kg | `engineering_coefficient` | YES | |
| 8 | `primary_precooling_hours_per_pallet` | 一级预冷每托盘时间 | 1 | h | `engineering_coefficient` | YES | |
| 9 | `primary_precooling_working_hours_per_day` | 一级预冷每日工作时间 | 6 | h | `project_input` | YES | |
| 10 | `secondary_precooling_pallet_weight_kg` | 二级预冷托盘重量 | 400 | kg | `engineering_coefficient` | YES | |
| 11 | `secondary_precooling_hours_per_pallet` | 二级预冷每托盘时间 | 2 | h | `engineering_coefficient` | YES | |
| 12 | `secondary_precooling_working_hours_per_day` | 二级预冷每日工作时间 | 16 | h | `project_input` | YES | |
| 13 | `raw_storage_ratio` | 原果暂存比例 | 0.40 | ratio | `engineering_coefficient` | YES | Ratio of daily mass held as raw buffer |
| 14 | `raw_fruit_pallet_weight_kg` | 原果托盘重量 | 220 | kg | `engineering_coefficient` | YES | |
| 15 | `finished_goods_pallet_weight_kg` | 成品托盘重量 | 400 | kg | `engineering_coefficient` | YES | |
| 16 | `frozen_goods_pallet_weight_kg` | 冻品托盘重量 | 600 | kg | `engineering_coefficient` | YES | |
| 17 | `secondary_fruit_area_ratio` | 次果面积比例 | 0.80 | ratio | `engineering_coefficient` | YES | |
| 18 | `pallet_length_m` | 托盘长度 | 1.2 | m | `engineering_coefficient` | YES | Standard pallet dimension |
| 19 | `pallet_width_m` | 托盘宽度 | 1.0 | m | `engineering_coefficient` | YES | Standard pallet dimension |
| 20 | `pallet_longitudinal_gap_m` | 托盘纵向间隙 | 0.3 | m | `engineering_coefficient` | YES | |
| 21 | `storage_area_factor` | 存储面积系数 | 1.2 | ratio | `engineering_coefficient` | YES | Multiplier on pallet base area for storage zone |
| 22 | `precooling_position_area_m2` | 预冷板位面积 | 5.6 | m² | `engineering_coefficient` | YES | |
| 23 | `packing_pieces_per_person_hour` | 每人每小时包装件数 | 15 | pcs/h | `engineering_coefficient` | YES | |
| 24 | `packing_weight_per_piece_kg` | 每件包装重量 | 1.5 | kg/pc | `engineering_coefficient` | YES | |
| 25 | `packing_working_hours_per_day` | 包装每日工作时间 | 16 | h | `project_input` | YES | |
| 26 | `workers_per_packing_table` | 每包装台工人数 | 3 | persons | `engineering_coefficient` | YES | |
| 27 | `packing_table_horizontal_spacing_m` | 包装台水平间距 | 5.5 | m | `engineering_coefficient` | YES | |
| 28 | `packing_table_vertical_spacing_m` | 包装台垂直间距 | 3.5 | m | `engineering_coefficient` | YES | |
| 29 | `packing_area_factor` | 包装面积系数 | 1.5 | ratio | `engineering_coefficient` | YES | Multiplier on table area for packing zone |
| 30 | `main_packaging_storage_days` | 主包材库存天数 | 3 | day | `project_input` | YES | |
| 31 | `auxiliary_packaging_storage_days` | 辅包材库存天数 | 30 | day | `project_input` | YES | |
| 32 | `packaging_area_factor` | 包材面积系数 | 1.5 | ratio | `engineering_coefficient` | YES | |
| 33 | `office_fixed_area_m2` | 办公室固定面积 | 60 | m² | `project_input` | YES | Fixed minimum area |
| 34 | `changing_fixed_area_m2` | 更衣室固定面积 | 100 | m² | `project_input` | YES | Fixed minimum area |
| 35 | `coating_fixed_area_m2` | 覆膜间固定面积 | 120 | m² | `project_input` | YES | Fixed minimum area |

---

## 2. Zone Planning — DemoZoneCoefficient Map (`ColdRoomZonePlanner._coefficients`)

Source file: `backend/src/cold_storage/modules/calculations/domain/zone_planning.py` (lines 85–205)

These coefficients are already wrapped in `DemoZoneCoefficient` objects and
exposed via the `coefficients` field of calculation results. They carry audit
metadata (`source_type=demo`, `validity_status=unverified`, `requires_review=true`).

| # | Code | Name | Value | Unit | Category | In Registry? | Notes |
|---|------|------|-------|------|----------|:---:|-------|
| 36 | `raw_holding_hours` | 原果暂存小时数 | 6.6666666667 | h | `project_input` | DEDUP | Duplicate of #1 |
| 37 | `raw_area_loading` | 原果暂存单位面积承载量 | 240 | kg/m² | `engineering_coefficient` | YES | Area loading factor for raw buffer zone |
| 38 | `primary_precooling_area_loading` | 一级预冷间单位面积日处理量 | 620 | kg/day/m² | `engineering_coefficient` | YES | 8–10°C precooling area loading |
| 39 | `secondary_precooling_area_loading` | 二级预冷间单位面积日处理量 | 550 | kg/day/m² | `engineering_coefficient` | YES | 1–3°C precooling area loading |
| 40 | `sorting_area_loading` | 分选包装间单位面积日处理量 | 420 | kg/day/m² | `engineering_coefficient` | YES | 8–10°C sorting area loading |
| 41 | `coating_area_loading` | 覆膜间单位面积日处理量 | 500 | kg/day/m² | `engineering_coefficient` | YES | 1–3°C coating area loading |
| 42 | `storage_area_loading` | 成品间单位面积储量 | 216 | kg/m² | `engineering_coefficient` | YES | Finished goods area loading |
| 43 | `secondary_fruit_ratio` | 次果比例 | 0.08 | ratio | `engineering_coefficient` | DEDUP | Duplicate of #3 |
| 44 | `secondary_fruit_area_loading` | 次果暂存单位面积承载量 | 220 | kg/m² | `engineering_coefficient` | YES | 8–10°C cull fruit area loading |
| 45 | `frozen_fruit_ratio` | 冻果比例 | 0.05 | ratio | `engineering_coefficient` | DEDUP | ⚠️ Different from #4 (0.10) — potential inconsistency |
| 46 | `frozen_storage_days` | 冻果暂存天数 | 14 | day | `engineering_coefficient` | DEDUP | ⚠️ Different from #5 (5) — potential inconsistency |
| 47 | `frozen_area_loading` | 冻果间单位面积储量 | 320 | kg/m² | `engineering_coefficient` | YES | -18°C frozen storage area loading |
| 48 | `office_area_per_t_day` | 办公室单位日处理吨位面积 | 1.2 | m²/(t/day) | `engineering_coefficient` | YES | Per-ton daily throughput area for office |
| 49 | `changing_area_per_t_day` | 更衣室单位日处理吨位面积 | 0.8 | m²/(t/day) | `engineering_coefficient` | YES | Per-ton daily throughput area for changing room |
| 50 | `packaging_area_per_t_day` | 包材库单位吨日库存面积 | 0.6685 | m²/(t/day·day) | `engineering_coefficient` | YES | Combined packaging area factor per ton |
| 51 | `precooling_position_daily_capacity_kg` | 预冷板位单位日处理量 | 1250 | kg/day/position | `engineering_coefficient` | DEDUP | Duplicate of #6 |
| 52 | `storage_position_capacity_kg` | 存储板位单位容量 | 500 | kg/position | `engineering_coefficient` | DEDUP | ⚠️ Different from #2 (400) — potential inconsistency |

### ⚠️ Critical Value Discrepancies

Three values have different defaults in `ColdRoomZonePlanInput` vs
`DemoZoneCoefficient`:

| Code | ColdRoomZonePlanInput Default | DemoZoneCoefficient Value | Used In Calculation |
|------|------|------|------|
| `frozen_fruit_ratio` | 0.10 | 0.05 | Input default (0.10) wins when used via `build_zone_plan_from_inputs` |
| `frozen_storage_days` | 5 | 14 | Input default (5) wins when used via `build_zone_plan_from_inputs` |
| `storage_position_capacity_kg` | 400 | 500 | Input default (400) wins when used via `build_zone_plan_from_inputs` |

The `DemoZoneCoefficient` values are displayed in calculation output metadata
but are NOT used in the actual calculation path. The `ColdRoomZonePlanInput`
defaults are the effective values. This is a consistency issue that should be
resolved during registry migration.

---

## 3. Packaging Material Position Calculation Coefficients

Source file: `backend/src/cold_storage/modules/calculations/domain/zone_planning.py` (lines 657–676)

These are formula constants embedded in `_packaging_position_count()`. They
represent per-unit consumption rates for main and auxiliary packaging materials.

### Main Packaging Coefficients

Each element represents a consumption factor for a specific packaging material.
The formula is: `positions = daily_mass * (main_days * Σ(main_coefficients) + aux_days * Σ(aux_coefficients))`

| # | Expression | Numerical Value | Likely Meaning | In Registry? |
|---|-----------|----------------|----------------|:---:|
| 53a | 1/(1.5 × 1600 × 2) | 2.08333e-04 | Carton consumption per kg (carton weight × items/carton × layers) | YES |
| 53b | 1/(125 × 16 × 2) | 2.50000e-04 | Label/consumable per kg (label reel weight × items/reel × sides) | YES |
| 53c | 1/(360 × 20) | 1.38889e-04 | Tape/consumable per kg (tape roll length × width factor) | YES |
| 53d | 1/(360 × 60) | 4.62963e-05 | Film/wrap consumption per kg | YES |
| 53e | 0.3/12000 | 2.50000e-05 | Pallet/structural material per kg | YES |

### Auxiliary Packaging Coefficients

| # | Expression | Numerical Value | Likely Meaning | In Registry? |
|---|-----------|----------------|----------------|:---:|
| 54a | 4/(360 × 1450) | 7.66280e-06 | Auxiliary material A per kg | YES |
| 54b | 3/(360 × 250 × 2) | 1.66667e-05 | Auxiliary material B per kg | YES |
| 54c | 1.6/(360 × 800) | 5.55556e-06 | Auxiliary material C per kg | YES |
| 54d | 0.1/(10 × 300 × 2) | 1.66667e-05 | Auxiliary material D per kg | YES |
| 54e | 2/(360 × 900) | 6.17284e-06 | Auxiliary material E per kg | YES |

**Note:** These formulas likely encode specific packaging material consumption
rates per ton of product. The denominators represent (unit_count × weight_per_unit × 
configuration_factor). These should be documented with clear material names
and sourced from packaging specifications during registry migration.

---

## 4. Investment Estimator Coefficients

Source file: `backend/src/cold_storage/modules/calculations/domain/investment.py` (lines 24–54)

| # | Code | Name | Value | Unit | Category | In Registry? | Notes |
|---|------|------|-------|------|----------|:---:|-------|
| 55 | `building_envelope_cost_cny_m2` | 土建及钢结构单价 | 900 | CNY/m² | `engineering_coefficient` | YES | Civil structure and steel cost per m² |
| 56 | `refrigeration_cost_cny_m2` | 冷库制冷设备单价 | 1400 | CNY/m² | `engineering_coefficient` | YES | Refrigeration equipment cost per m² |
| 57 | `power_distribution_cost_cny_kw` | 高低压配电单价 | 650 | CNY/kW | `engineering_coefficient` | YES | Power distribution cost per kW |
| 58 | `monitoring_opening_supplies_cny` | 监控及开厂物资固定投资 | 200,000 | CNY | `engineering_coefficient` | YES | Fixed investment for monitoring and startup supplies |
| 59 | — | 土建附加面积 | 1,000 | m² | `formula_constant` | YES | Hardcoded bonus area added to total_area for civil structure cost calculation (line 76: `(total_area_m2 + 1000) * cost_per_m2`) |

---

## 5. Power Configuration — Scaling and Simultaneity Factors

Source file: `backend/src/cold_storage/modules/planning/application/service.py` (lines 182–253)

| # | Code | Name | Value | Unit | Category | In Registry? | Notes |
|---|------|------|-------|------|----------|:---:|-------|
| 60 | `reference_daily_capacity_kg` | 参考日产能基准 | 25,000 | kg/day | `formula_constant` | YES | Base capacity for power scaling: `scale = daily_mass / 25000` |
| 61 | `defrost_simultaneous_factor` | 化霜同时系数 | 0.30 | ratio | `engineering_coefficient` | YES | 30% of defrost power assumed simultaneous |
| 62 | `running_simultaneous_factor` | 设备运行同时使用系数 | 0.90 | ratio | `engineering_coefficient` | YES | 90% of running power assumed simultaneous |
| 63 | `axial_fan_per_position` | 轴流风机板位配比 | 4 | fans/position | `engineering_coefficient` | YES | 4 axial fans per precooling position (line 271) |

---

## 6. Power Configuration — Equipment Reference Table

Source file: `backend/src/cold_storage/modules/planning/application/service.py` (lines 286–347)

This is a hardcoded reference equipment list based on a reference project (25 t/day
blueberry processing facility). All values scale linearly with the ratio
`daily_inbound_mass_kg / 25000`.

### Refrigeration Section

| # | Seq | Equipment | Area | Qty | Defrost kW | Defrost Total kW | Running kW | Total kW | In Registry? |
|---|-----|-----------|------|-----|-----------|-----------------|-----------|---------|:---:|
| 64 | 1 | 制冷压缩机组 | 一级预冷、原果暂存间、分选间 | 1 | — | — | 297.6 | 297.6 | YES |
| 65 | 2 | 制冷压缩机组 | 二级预冷间、成品库、出货通道、覆膜间 | 1 | — | — | 209.6 | 209.6 | YES |
| 66 | 3 | 制冷压缩机组 | 成品双温库 | 2 | — | — | 27.5 | 55.0 | YES |
| 67 | 4 | 制冷压缩机组 | 次果暂存区 | 1 | — | — | 4.21 | 4.21 | YES |
| 68 | 5 | 制冷压缩机组 | 冻果间 | 1 | — | — | 29.4 | 29.4 | YES |
| 69 | 6 | 冷风机 | 原果暂存 | 3 | 4.9 | 14.7 | 0.75 | 2.25 | YES |
| 70 | 7 | 冷风机 | 一级预冷间 | 12 | 16.0 | 192.0 | 2.68 | 32.16 | YES |
| 71 | 8 | 冷风机 | 分选间 | 14 | 4.9 | 68.6 | 0.75 | 10.5 | YES |
| 72 | 9 | 冷风机 | 二级预冷间 | 14 | 21.6 | 302.4 | 2.68 | 37.52 | YES |
| 73 | 10 | 冷风机 | 覆膜间 | 3 | 21.6 | 64.8 | 1.796 | 5.388 | YES |
| 74 | 11 | 冷风机 | 双温成品库 | 4 | 25.2 | 100.8 | 2.68 | 10.72 | YES |
| 75 | 12 | 冷风机 | 成品库 | 3 | 10.0 | 30.0 | 1.796 | 5.388 | YES |
| 76 | 13 | 冷风机 | 次果暂存间 | 1 | 8.5 | 8.5 | 1.347 | 1.347 | YES |
| 77 | 14 | 冷风机 | 冻果暂存间 | 1 | 31.5 | 31.5 | 3.2 | 3.2 | YES |
| 78 | 15 | 冷风机 | 出货通道 | 2 | 8.5 | 17.0 | 1.347 | 2.694 | YES |
| 79 | 16 | 蒸发冷 | — | 1 | — | — | 28.0 | 28.0 | YES |
| 80 | 17 | 蒸发冷 | — | 1 | — | — | 19.0 | 19.0 | YES |
| 81 | 18 | 轴流风机 | — | 360 | — | — | 0.55 | 198.0 | YES |
| 82 | 19 | 升降平台 | — | 3 | — | — | 2.2 | 6.6 | YES |
| 83 | 20 | 工业滑升门 | — | 3 | — | — | 0.4 | 1.2 | YES |
| 84 | 21 | 充气门封 | — | 3 | — | — | 0.4 | 1.2 | YES |
| 85 | 22 | 电动门 | — | 29 | — | — | 0.38 | 11.02 | YES |
| 86 | 23 | 快卷门 | — | 2 | — | — | 0.38 | 0.76 | YES |
| 87 | 24 | 风幕机 | — | 10 | — | — | 0.38 | 3.8 | YES |
| 88 | 25 | 冷库照明 | — | 350 | — | — | 0.04 | 14.0 | YES |
| 89 | 26 | 地坪加热丝 | — | 1 | — | — | 2.0 | 2.0 | YES |
| 90 | 27 | 紫外线灯 | — | 190 | — | — | 0.08 | 15.2 | YES |
| 91 | 28 | 臭氧 | — | 1 | — | — | 15.0 | 15.0 | YES |
| 92 | 29 | 加湿 | — | 1 | — | — | 15.0 | 15.0 | YES |

### Production Section

| # | Seq | Equipment | Area | Qty | Running kW | Total kW | In Registry? |
|---|-----|-----------|------|-----|-----------|---------|:---:|
| 93 | 35 | 折箱机 | — | 2 | 12.0 | 24.0 | YES |
| 94 | 36 | 枕式包装机 | — | 2 | 12.5 | 25.0 | YES |
| 95 | 37 | 包装流水线 | — | 2 | 7.5 | 15.0 | YES |
| 96 | 38 | 筐桶清洗机 | — | 2 | 20.0 | 40.0 | YES |
| 97 | 39 | 贴标机 | — | 2 | 5.0 | 10.0 | YES |
| 98 | 40 | 光电分选设备 | — | 1 | 65.0 | 65.0 | YES |
| 99 | 41 | 定量包装设备 | — | 3 | 15.0 | 45.0 | YES |
| 100 | 42 | 辅助铺联设备 | — | 1 | 40.0 | 40.0 | YES |
| 101 | 43 | 空压机 | — | 1 | 22.0 | 22.0 | YES |
| 102 | 44 | 熏蒸设备 | — | 2 | 15.0 | 30.0 | YES |

**Note:** Equipment row quantities and total_power_kw values are scaled by
`daily_inbound_mass_kg / 25000`. The `running_power_kw` per-unit values remain
constant. The axial fan quantity is dynamically recalculated based on precooling
position count (not from the reference table value of 360).

---

## 7. Calculation Service — Formula Constants

Source file: `backend/src/cold_storage/modules/calculations/domain/service.py`

| # | Location | Value | Unit | Category | In Registry? | Notes |
|---|----------|-------|------|----------|:---:|-------|
| 103 | `run_room_area` line 206 | 1.2 | ratio | `formula_constant` | NO | Preliminary length/width ratio for room dimension estimation: `length = √area × 1.2`, `width = √area / 1.2` |
| 104 | `run_equipment_requirement` line 321 | 1.25 | ratio | `engineering_coefficient` | YES | Condenser heat rejection capacity factor: `heat_rejection = total_cooling_load × 1.25` |

---

## 8. Demo Planning Inputs

Source file: `backend/src/cold_storage/modules/planning/application/service.py` (lines 428–439)

These are the default demo inputs used by `demo_inputs()` and as fallback values
in `build_zone_plan_from_inputs()`.

| # | Code | Value | Unit | Category | In Registry? | Notes |
|---|------|-------|------|----------|:---:|-------|
| 105 | `daily_inbound_mass_kg` | 25,000 | kg/day | `demo_sample` | NO | Demo project parameter, not a coefficient |
| 106 | `working_time_h_per_day` | 16 | h/day | `demo_sample` | NO | |
| 107 | `utilization_factor` | 0.85 | ratio | `engineering_coefficient` | YES | Equipment utilization factor |
| 108 | `finished_storage_days` | 2.5 | day | `demo_sample` | NO | |
| 109 | `packaging_storage_days` | 3 | day | `demo_sample` | NO | |
| 110 | `main_packaging_storage_days` | 3 | day | `demo_sample` | NO | |
| 111 | `auxiliary_packaging_storage_days` | 30 | day | `demo_sample` | NO | |
| 112 | `reserve_factor` | 1.05 | ratio | `engineering_coefficient` | YES | Inventory reserve/safety factor |
| 113 | `precooling_required_ratio` | 1 | ratio | `engineering_coefficient` | YES | Fraction of inbound requiring precooling |

---

## 9. Demo Overview — Project Data

Source file: `backend/src/cold_storage/bootstrap/demo_overview.py` (lines 120–131)

| # | Code | Value | Unit | Category | In Registry? | Notes |
|---|------|-------|------|----------|:---:|-------|
| 114 | `planting_area_mu` | 1,250 | 亩 | `demo_sample` | NO | Project-specific cultivation area |
| 115 | `yield_per_thousand_mu_tons` | 20 | t/千亩 | `demo_sample` | NO | Yield conversion factor for demo |
| 116 | `peak_yield_tons` | 25 | t/day | `demo_sample` | NO | |

---

## 10. Frontend Default Values

Source file: `frontend/src/App.vue` (lines 83–97)

| # | Code | Value | Unit | Category | In Registry? | Notes |
|---|------|-------|------|----------|:---:|-------|
| 117 | `dailyInboundMassTons` | 25 | t/day | `demo_sample` | NO | Matches backend demo_inputs |
| 118 | `workingHoursPerDay` | 16 | h/day | `demo_sample` | NO | |
| 119 | `finishedStorageDays` | 2.5 | day | `demo_sample` | NO | |
| 120 | `packagingStorageDays` | 3 | day | `demo_sample` | NO | |
| 121 | `auxiliaryPackagingStorageDays` | 30 | day | `demo_sample` | NO | |
| 122 | `precoolingRequiredRatio` | 1 | ratio | `demo_sample` | NO | |
| 123 | `rawStorageRatio` | 0.4 | ratio | `demo_sample` | NO | |
| 124 | `primaryPrecoolingWorkingHours` | 6 | h | `demo_sample` | NO | |
| 125 | `secondaryPrecoolingWorkingHours` | 16 | h | `demo_sample` | NO | |
| 126 | `finishedGoodsPalletWeightKg` | 400 | kg | `demo_sample` | NO | |
| 127 | `frozenFruitRatio` | 0.1 | ratio | `demo_sample` | NO | |
| 128 | `frozenStorageDays` | 5 | day | `demo_sample` | NO | |
| 129 | `frozenGoodsPalletWeightKg` | 600 | kg | `demo_sample` | NO | |

Frontend request body (line 339–344):
| # | Code | Value | Unit | Category | In Registry? | Notes |
|---|------|-------|------|----------|:---:|-------|
| 130 | `utilization_factor` | 0.85 | ratio | `demo_sample` | NO | Hardcoded in fetch body |
| 131 | `reserve_factor` | 1.05 | ratio | `demo_sample` | NO | Hardcoded in fetch body |

---

## 11. Fallback Defaults in `build_zone_plan_from_inputs`

Source file: `backend/src/cold_storage/modules/planning/application/service.py` (lines 53–112)

These `.get()` fallback values are used when the user does not provide the
parameter via API. They should match the `ColdRoomZonePlanInput` defaults.

| # | Code | Fallback | Unit | In Registry? | Notes |
|---|------|----------|------|:---:|-------|
| 132 | `packaging_storage_days` | 7 | day | YES | ⚠️ Different from ColdRoomZonePlanInput default of 3! |
| 133 | `precooling_required_ratio` | 0.8 | ratio | YES | ⚠️ Different from ColdRoomZonePlanInput not-set / demo_inputs=1! |

**Note:** The `build_zone_plan_from_inputs` function applies its own fallback
values that may differ from `ColdRoomZonePlanInput` dataclass defaults. The
function-level fallback of `packaging_storage_days=7` and
`precooling_required_ratio=0.8` do NOT match the dataclass defaults of 3 and
absent respectively. This is a third source of potential inconsistency.

---

## 12. Precooling Position Rounding

Source file: `backend/src/cold_storage/modules/calculations/domain/zone_planning.py` (lines 678–685)

| # | Code | Value | Unit | Category | In Registry? | Notes |
|---|------|-------|------|----------|:---:|-------|
| 134 | `_round_precooling_positions_multiple_a` | 6 | positions | `formula_constant` | YES | Round up to nearest 6 |
| 135 | `_round_precooling_positions_multiple_b` | 8 | positions | `formula_constant` | YES | Round up to nearest 8 |

Logic: `min(ceil(n/6)*6, ceil(n/8)*8)` — rounds to nearest multiple of 6 or 8,
whichever is smaller. This ensures precooling rooms have practical position counts.

---

## Summary Statistics

| Category | Count |
|----------|-------|
| Total unique coefficients inventoried | ~80 |
| Values requiring registry migration | ~65 |
| Equipment specification rows | 39 |
| Value discrepancies found | 3 critical + 2 minor |
| Formula constants | ~12 |

### Critical Discrepancies

1. **`frozen_fruit_ratio`**: Input default = 0.10, DemoZoneCoefficient = 0.05
2. **`frozen_storage_days`**: Input default = 5, DemoZoneCoefficient = 14
3. **`storage_position_capacity_kg`**: Input default = 400, DemoZoneCoefficient = 500

### Minor Discrepancies

4. **`packaging_storage_days`**: ColdRoomZonePlanInput default = 3, build_zone_plan_from_inputs fallback = 7
5. **`precooling_required_ratio`**: ColdRoomZonePlanInput default not set, build_zone_plan_from_inputs fallback = 0.8, demo_inputs = 1

---

## Regression Baseline (Demo Inputs: 25 t/day)

Calculated using `demo_inputs()` → `build_zone_plan_from_inputs` → `build_power_configuration` → `build_investment_from_zone_result`.

### Zone Plan Baseline

| Zone | Temperature | Area (m²) | Positions |
|------|-------------|-----------|-----------|
| 办公室 | 常温 | 60.00 | 0 |
| 更衣室 | 常温 | 100.00 | 0 |
| 一级预冷间 | 8~10℃ | 134.40 | 24 |
| 二级预冷间 | 1~3℃ | 44.80 | 8 |
| 原果暂存间 | 8~10℃ | 86.11 | 46 |
| 分选包装间 | 8~10℃ | 693.00 | 0 |
| 覆膜间 | 1~3℃ | 120.00 | 0 |
| 成品间 | 1~3℃ | 293.90 | 157 |
| 次果暂存间 | 8~10℃ | 31.45 | 0 |
| 冻果间 | -18℃ | 39.31 | 21 |
| 包材库 | 常温 | 210.60 | 90 |
| **Total** | | **1,813.57** | **346** |

### Power Configuration Baseline

| Item | Power (kW) |
|------|-----------|
| 化霜总功率 (30% simultaneous) | 249.09 |
| 设备运行功率 (90% simultaneous) | 819.14 |
| 制冷总功率 | 1,068.23 |
| 生产设备总功率 (90% simultaneous) | 284.40 |
| **合计** | **1,352.63** |

### Investment Baseline

| Item | Amount (CNY) | Amount (万元) |
|------|-------------|------------|
| 土建及钢结构 | 2,532,213.00 | 253.22 |
| 冷库制冷设备 | 2,538,998.00 | 253.90 |
| 高低压配电 | 879,209.50 | 87.92 |
| 住宿及生活区 | 0.00 | 0.00 |
| 监控及开厂物资 | 200,000.00 | 20.00 |
| **Total** | **6,150,420.50** | **615.04** |

### Key Derived Values

| Metric | Value |
|--------|-------|
| Refrigerated area | 1,442.97 m² |
| Frozen area (-18℃) | 39.31 m² |
| Warm area (常温) | 370.60 m² |
| Total position count | 346 |
| Packaging material positions | 90 |
| Precooling position rounding | min(ceil(24/6)×6, ceil(24/8)×8) = min(24, 24) = 24 |

---

## Notes for Registry Migration

1. **Resolve discrepancies first**: The 3 critical discrepancies between
   `ColdRoomZonePlanInput` defaults and `DemoZoneCoefficient` values must be
   resolved before migration. Determine which values are correct and
   consolidate.

2. **Three-tier value model**: The registry should support:
   - **Default values** (fallback when user provides no input)
   - **Project-specific overrides** (per-project user inputs)
   - **Approved/verified values** (reviewed by domain experts)

3. **Equipment table structure**: The 39-row equipment reference table should
   be stored as a structured dataset within the registry, with metadata about
   the reference project and applicability.

4. **Packaging coefficients**: The 10 packaging material consumption factors
   (#53-54) need clear documentation of what each factor represents and
   their source (packaging supplier specs).

5. **Dual coefficient classes**: `DemoZoneCoefficient` (zone_planning.py) and
   `CalculationCoefficient` (coefficients.py) serve different purposes. The
   registry should provide a unified interface that supports both use cases.

6. **Frontend defaults**: The frontend `App.vue` hardcodes demo values that
   should be fetched from the API or a shared configuration source (gap
   P2-002 in gap-analysis.md).
