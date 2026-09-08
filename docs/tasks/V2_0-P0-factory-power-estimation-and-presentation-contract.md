# V2.0 P0：工厂功率估算与统一呈现契约

**状态：** 定义冻结，等待 Charles 独立 Review。
**基线：** v1.9.0 / main@8f48332435f4916bdb9ab8430d686678c1efc576。
**模式：** DOCS_CONTRACT_ARCHITECTURE_TEST_ONLY。
**权威：** 本文规则来自 Charles 已确认的 V2.0 P0 功率估算规则；当前代码审计结论只描述仓库事实，不构成运行时授权。

~~~text
TASK_ID=V20_P0_FACTORY_POWER_ESTIMATION_AND_PRESENTATION_CONTRACT_R1
V20_P0_CONTRACT_FROZEN=YES
RUNTIME_IMPLEMENTATION_AUTHORIZED=NO
FRONTEND_IMPLEMENTATION_AUTHORIZED=NO
AILY_IMPLEMENTATION_AUTHORIZED=NO
DATABASE_MIGRATION=NO
EQUIPMENT_MODEL_SELECTION=NO
TRANSFORMER_SIZING=NO
KWH_ESTIMATION=NO
ELECTRICITY_PRICE=NO
MONTHLY_BILL=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
P1_AUTHORIZED=NO
P2_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
~~~

## 1. 机器可读冻结矩阵

下面是本 P0 的唯一机器可读规则矩阵。架构测试直接解析本段 JSON，防止
系数、边界、功率池和非授权范围只停留在叙述层。

~~~json
{
  "schema_version": "2.0.0-p0",
  "task_id": "V20_P0_FACTORY_POWER_ESTIMATION_AND_PRESENTATION_CONTRACT_R1",
  "status": "P0_CONTRACT_FROZEN",
  "direction": "FACTORY_POWER_ESTIMATION_AND_PRESENTATION_CONTRACT",
  "unit_semantics": {
    "power_unit": "kW",
    "estimated_electrical_power": "kW",
    "energy_unit": "kWh",
    "not_energy": true,
    "not_metered_electricity": true,
    "not_daily_electricity_consumption": true
  },
  "factory_area_bands": [
    {
      "code": "SMALL",
      "predicate": "factory_area_m2 <= 2500",
      "lower_bound_exclusive_m2": null,
      "upper_bound_inclusive_m2": 2500
    },
    {
      "code": "MEDIUM",
      "predicate": "2500 < factory_area_m2 <= 5000",
      "lower_bound_exclusive_m2": 2500,
      "upper_bound_inclusive_m2": 5000
    },
    {
      "code": "LARGE",
      "predicate": "factory_area_m2 > 5000",
      "lower_bound_exclusive_m2": 5000,
      "upper_bound_inclusive_m2": null
    }
  ],
  "authority_audit": {
    "factory_area": {
      "target_field": "factory_area_m2",
      "current_literal_field": null,
      "status": "UNRESOLVED",
      "required_behavior": "fail_closed_until_authoritative_factory_area_is_mapped",
      "forbidden_substitutes": [
        "total_area_m2",
        "total_required_area_m2",
        "refrigerated_area_m2",
        "daily_inbound_mass_kg"
      ],
      "evidence": [
        "backend/src/cold_storage/modules/calculations/domain/zone_planning.py:ColdRoomZonePlanInput",
        "backend/src/cold_storage/modules/planning/application/service.py:build_power_configuration"
      ]
    },
    "zone_area": {
      "canonical_field": "required_area_m2",
      "semantic": "PLANNED_ZONE_AREA",
      "source_path": "zone_plan.result.zones[]",
      "status": "PRESENT"
    },
    "cold_storage_area": {
      "target_field": "cold_storage_area_m2",
      "current_literal_field": null,
      "current_equivalent_field": "refrigerated_area_m2",
      "mapping_status": "AMBIGUOUS_EXISTING_DERIVATIONS",
      "candidate_derivations": {
        "planning_application": "sum(required_area_m2 for zones with temperature_band != 常温), includes -18℃",
        "operator_minimal_lineage": "sum(required_area_m2 for zones with temperature_band in [8~10℃, 1~3℃]), excludes -18℃",
        "legacy_demo_overview": "sum(required_area_m2 for zones with temperature_band != 常温), includes -18℃"
      },
      "required_resolution": "freeze whether cold_storage_area_m2 includes -18℃ and publish one canonical derivation",
      "forbidden_substitute": "total_area_m2",
      "evidence": [
        "backend/src/cold_storage/modules/planning/application/service.py:build_investment_from_zone_result",
        "backend/src/cold_storage/modules/projects/application/preview_lineage_bind.py:bind_investment_inputs"
      ]
    },
    "precooling_output": {
      "source_path": "zone_plan.result.zones[]",
      "scheme_path": "zones[].schemes[]",
      "current_reporting_scheme": "6_position",
      "alternate_scheme": "8_position",
      "required_fields": [
        "reporting_scheme_id",
        "schemes[].room_count",
        "schemes[].position_count",
        "schemes[].required_area_m2",
        "position_count"
      ],
      "forbidden_source_field": "raw_position_count",
      "mapping_status": "CURRENT_REPORTING_SCHEME_IS_6_POSITION_WITH_8_POSITION_ALTERNATE"
    },
    "v19_per_zone_cooling_load": {
      "canonical_field": "minimum_estimated_cooling_load_kw_r",
      "provenance_field": "cooling_estimation_basis",
      "source_path": "zone_plan.result.zones[]",
      "unit": "kW(r)",
      "status": "PRESENT",
      "distinct_existing_field": "cooling_load.result.zones[].subtotal_load_kw_r",
      "mapping_status": "MINIMUM_ESTIMATE_AND_SUBTOTAL_ARE_DISTINCT_FIELDS"
    },
    "existing_calculator_boundaries": {
      "equipment_capability_module": "backend/src/cold_storage/modules/calculations/domain/equipment.py",
      "installed_power_module": "backend/src/cold_storage/modules/calculations/domain/power.py",
      "legacy_planning_power_module": "backend/src/cold_storage/modules/planning/application/service.py",
      "legacy_installed_power_identity": "installed_power@1.0.0",
      "v2_runtime_status": "NOT_IMPLEMENTED_IN_P0"
    }
  },
  "precooling_configurations": {
    "6_position": {
      "positions_per_room": 6,
      "air_coolers_per_room": 2,
      "positions_per_air_cooler": 3,
      "air_cooler_quantity_formula": "room_count * 2"
    },
    "8_position": {
      "positions_per_room": 8,
      "air_coolers_per_room": 2,
      "positions_per_air_cooler": 4,
      "air_cooler_quantity_formula": "room_count * 2"
    },
    "position_source_field": "position_count",
    "room_count_source_field": "schemes[].room_count",
    "forbidden_position_source_field": "raw_position_count"
  },
  "zone_rules": [
    {
      "zone_code": "primary_precooling_room",
      "quantity_basis": "PRECOOLING_SCHEME",
      "quantity_formula": "room_count * 2",
      "motor_kw_per_unit": 6.6,
      "defrost_kw_per_unit": 19.6,
      "motor_pool": "POOL_B",
      "defrost_pool": "POOL_A",
      "axial_fans_per_position": 4,
      "axial_fan_kw_per_unit": 0.5,
      "axial_fan_quantity_formula": "final_position_count * 4"
    },
    {
      "zone_code": "secondary_precooling_room",
      "quantity_basis": "PRECOOLING_SCHEME",
      "quantity_formula": "room_count * 2",
      "motor_kw_per_unit": 3.0,
      "defrost_kw_per_unit": 22.0,
      "motor_pool": "POOL_B",
      "defrost_pool": "POOL_A",
      "axial_fans_per_position": 4,
      "axial_fan_kw_per_unit": 0.5,
      "axial_fan_quantity_formula": "final_position_count * 4"
    },
    {
      "zone_code": "raw_fruit_buffer",
      "quantity_basis": "ZONE_AREA",
      "source_field": "required_area_m2",
      "quantity_formula": "ceil(required_area_m2 / 80)",
      "motor_kw_per_unit": 0.5,
      "defrost_kw_per_unit": 4.0,
      "motor_pool": "POOL_B",
      "defrost_pool": "POOL_A"
    },
    {
      "zone_code": "sorting_packaging_room",
      "quantity_basis": "ZONE_AREA",
      "source_field": "required_area_m2",
      "raw_count_formula": "ceil(required_area_m2 / 70)",
      "quantity_formula": "next_even_integer_greater_than_or_equal_to(raw_count)",
      "motor_kw_per_unit": 0.5,
      "defrost_kw_per_unit": 4.0,
      "motor_pool": "POOL_B",
      "defrost_pool": "POOL_A"
    },
    {
      "zone_code": "coating_room",
      "quantity_basis": "ZONE_AREA",
      "source_field": "required_area_m2",
      "quantity_formula": "ceil(required_area_m2 / 70)",
      "motor_kw_per_unit": 1.5,
      "defrost_kw_per_unit": 6.0,
      "motor_pool": "POOL_B",
      "defrost_pool": "POOL_A"
    },
    {
      "zone_code": "finished_goods_room",
      "quantity_basis": "ZONE_AREA",
      "source_field": "required_area_m2",
      "quantity_formula": "ceil(required_area_m2 / 70)",
      "motor_kw_per_unit": 1.5,
      "defrost_kw_per_unit": 6.0,
      "motor_pool": "POOL_B",
      "defrost_pool": "POOL_A"
    },
    {
      "zone_code": "secondary_fruit_buffer",
      "quantity_basis": "FIXED",
      "quantity": 1,
      "quantity_formula": "1",
      "motor_kw_per_unit": 1.0,
      "defrost_kw_per_unit": 8.0,
      "motor_pool": "POOL_B",
      "defrost_pool": "POOL_A"
    },
    {
      "zone_code": "frozen_fruit_room",
      "quantity_basis": "FIXED",
      "quantity": 1,
      "quantity_formula": "1",
      "motor_kw_per_unit": 3.0,
      "defrost_kw_per_unit": 26.0,
      "motor_pool": "POOL_B",
      "defrost_pool": "POOL_A"
    },
    {
      "zone_code": "shipping_channel",
      "quantity_basis": "ZONE_AREA",
      "source_field": "required_area_m2",
      "quantity_formula": "ceil(required_area_m2 / 50)",
      "motor_kw_per_unit": 2.0,
      "defrost_kw_per_unit": 12.0,
      "motor_pool": "POOL_B",
      "defrost_pool": "POOL_A"
    }
  ],
  "public_equipment": [
    {
      "equipment_code": "electric_sliding_door",
      "quantity_by_band": {
        "SMALL": 15,
        "MEDIUM": 30,
        "LARGE": 50
      },
      "unit_power_kw": 0.5,
      "pool": "POOL_B"
    },
    {
      "equipment_code": "fast_rolling_door",
      "quantity_by_band": {
        "SMALL": 6,
        "MEDIUM": 10,
        "LARGE": 16
      },
      "unit_power_kw": 0.5,
      "pool": "POOL_B"
    },
    {
      "equipment_code": "air_curtain",
      "quantity_by_band": {
        "SMALL": 4,
        "MEDIUM": 8,
        "LARGE": 12
      },
      "unit_power_kw": 0.4,
      "pool": "POOL_B"
    },
    {
      "equipment_code": "lift_door_and_loading_platform",
      "quantity_by_band": {
        "SMALL": 2,
        "MEDIUM": 3,
        "LARGE": 4
      },
      "unit_power_kw": 3.0,
      "pool": "POOL_B"
    },
    {
      "equipment_code": "ozone_and_humidification",
      "fixed_quantity": 1,
      "fixed_installed_power_kw": 30.0,
      "pool": "POOL_B"
    },
    {
      "equipment_code": "floor_heating_cable",
      "fixed_quantity": 1,
      "fixed_installed_power_kw": 4.0,
      "pool": "POOL_B"
    }
  ],
  "lighting": {
    "area_source_field": "cold_storage_area_m2",
    "area_source_current_equivalent_field": "refrigerated_area_m2",
    "cold_storage_lighting": {
      "quantity_formula": "ceil(cold_storage_area_m2 / 10)",
      "unit_power_kw": 0.04,
      "installed_power_formula": "quantity * 0.04",
      "pool": "POOL_B"
    },
    "uv_lighting": {
      "quantity_formula": "ceil(cold_storage_area_m2 / 20)",
      "unit_power_kw": 0.08,
      "installed_power_formula": "quantity * 0.08",
      "pool": "POOL_B"
    },
    "forbidden_area_substitute": "factory_area_m2"
  },
  "compressor_systems": {
    "main_system": {
      "included_zone_codes": [
        "primary_precooling_room",
        "secondary_precooling_room",
        "raw_fruit_buffer",
        "sorting_packaging_room",
        "coating_room",
        "finished_goods_room"
      ],
      "excluded_zone_codes": [
        "frozen_fruit_room",
        "secondary_fruit_buffer",
        "shipping_channel"
      ],
      "cooling_load_source_field": "minimum_estimated_cooling_load_kw_r",
      "cooling_load_source_path": "zone_plan.result.zones[]",
      "cooling_load_formula": "sum(authoritative cooling load for exactly the six included zones)",
      "main_system_cop": 3.3,
      "shaft_power_formula": "main_system_cooling_load_kw_r / 3.3",
      "pool": "POOL_B"
    },
    "dedicated_systems": [
      {
        "zone_code": "frozen_fruit_room",
        "shaft_power_by_band_kw": {
          "SMALL": 15.0,
          "MEDIUM": 25.0,
          "LARGE": 40.0
        },
        "pool": "POOL_B"
      },
      {
        "zone_code": "secondary_fruit_buffer",
        "shaft_power_by_band_kw": {
          "SMALL": 4.0,
          "MEDIUM": 6.0,
          "LARGE": 8.0
        },
        "pool": "POOL_B"
      },
      {
        "zone_code": "shipping_channel",
        "shaft_power_by_band_kw": {
          "SMALL": 8.0,
          "MEDIUM": 12.0,
          "LARGE": 16.0
        },
        "pool": "POOL_B"
      }
    ],
    "no_double_counting_rule": "excluded dedicated zones must not enter the main_system COP sum"
  },
  "evaporative_condenser": {
    "installed_power_by_band_kw": {
      "SMALL": 20.0,
      "MEDIUM": 30.0,
      "LARGE": 40.0
    },
    "pool": "POOL_B"
  },
  "production": {
    "installed_power_by_band_kw": {
      "SMALL": 200.0,
      "MEDIUM": 300.0,
      "LARGE": 400.0
    },
    "simultaneity_factor_name": "PRODUCTION_EQUIPMENT_SIMULTANEITY_FACTOR",
    "simultaneity_factor": 0.85,
    "coincident_power_formula": "production_equipment_installed_power_kw * 0.85",
    "pool": "POOL_C",
    "must_not_enter_other_pool": true
  },
  "power_pools": {
    "POOL_A": {
      "name": "DEFROST",
      "includes": [
        "all air-cooler defrost installed power"
      ],
      "includes_only": true,
      "installed_power_formula": "sum(all air-cooler defrost installed power)",
      "simultaneity_factor_name": "DEFROST_SIMULTANEITY_FACTOR",
      "simultaneity_factor": 0.30,
      "coincident_power_formula": "defrost_installed_power_kw * 0.30"
    },
    "POOL_B": {
      "name": "OTHER",
      "includes": [
        "air cooler motor power",
        "precooling axial fan power",
        "all compressor shaft power",
        "evaporative condenser power",
        "electric sliding doors",
        "fast rolling doors",
        "air curtains",
        "lift doors/loading platforms",
        "ozone/humidification",
        "floor heating cable",
        "cold-storage lighting",
        "UV lighting"
      ],
      "excludes": [
        "all air-cooler defrost installed power",
        "production equipment"
      ],
      "includes_only": true,
      "installed_power_formula": "sum(all non-defrost, non-production listed equipment)",
      "simultaneity_factor_by_band": {
        "SMALL": 1.0,
        "MEDIUM": 0.90,
        "LARGE": 0.80
      },
      "coincident_power_formula": "other_installed_power_kw * other_simultaneity_factor"
    },
    "POOL_C": {
      "name": "PRODUCTION",
      "includes": [
        "production equipment"
      ],
      "excludes": [
        "POOL_B"
      ],
      "includes_only": true,
      "installed_power_formula": "production_equipment_installed_power_kw",
      "simultaneity_factor": 0.85,
      "coincident_power_formula": "production_equipment_installed_power_kw * 0.85",
      "must_not_first_enter_other": true
    }
  },
  "final_power": {
    "estimated_total_power_formula": "estimated_total_power_kw = defrost_coincident_power_kw + other_coincident_power_kw + production_equipment_coincident_power_kw",
    "total_installed_power_formula": "total_installed_power_kw = defrost_installed_power_kw + other_installed_power_kw + production_equipment_installed_power_kw",
    "estimated_total_power_unit": "kW",
    "total_installed_power_unit": "kW"
  },
  "presentation_contract": {
    "canonical_source": "one_backend_canonical_result",
    "workbench_and_aily_read_same_result": true,
    "detail_fields": [
      "equipment_or_zone",
      "basis",
      "configured_quantity",
      "unit_power_kw",
      "installed_power_kw",
      "pool",
      "simultaneity_factor",
      "coincident_power_kw"
    ],
    "summary_fields": [
      "defrost_installed_power_kw",
      "defrost_coincident_power_kw",
      "other_installed_power_kw",
      "other_coincident_power_kw",
      "production_equipment_installed_power_kw",
      "production_equipment_coincident_power_kw",
      "total_installed_power_kw",
      "estimated_total_power_kw"
    ],
    "recalculation_locks": [
      "NO_AILY_RECALCULATION",
      "NO_FRONTEND_RECALCULATION",
      "NO_OUTBOUND_LIVE_AILY_SESSION"
    ]
  },
  "authorization": {
    "MODE": "DOCS_CONTRACT_ARCHITECTURE_TEST_ONLY",
    "RUNTIME_CODE_CHANGE": "NO",
    "FRONTEND_CODE_CHANGE": "NO",
    "AILY_RUNTIME_CHANGE": "NO",
    "OUTBOUND_LIVE_AILY_SESSION_AUTHORIZED": "NO",
    "DATABASE_MIGRATION": "NO",
    "EQUIPMENT_MODEL_SELECTION": "NO",
    "TRANSFORMER_SIZING": "NO",
    "KWH_ESTIMATION": "NO",
    "ELECTRICITY_PRICE": "NO",
    "MONTHLY_BILL": "NO",
    "READY_AUTHORIZED": "NO",
    "MERGE_AUTHORIZED": "NO",
    "P1_AUTHORIZED": "NO",
    "P2_AUTHORIZED": "NO",
    "NO_STEP_IMPLIES_THE_NEXT": "TRUE"
  }
}
~~~

## 2. 区域冷风机和预冷板位

预冷区按最终选定的 6-position 或 8-position 方案计算。一个方案间固定配置
两台冷风机；6-position 方案为每台三个位，8-position 方案为每台四个位。
一级预冷冷风机电机为 6.6 kW/台、化霜为 19.6 kW/台；二级预冷分别为
3.0 kW/台和 22.0 kW/台。每个预冷板位有四台 0.5 kW 轴流风机。

其余七个区域只使用 required_area_m2 或固定数量：

| 区域 | 数量规则 | 电机功率 | 化霜功率 |
| --- | --- | ---: | ---: |
| 原果暂存间 | ceil(area / 80) | 0.5 kW/台 | 4.0 kW/台 |
| 分选包装间 | ceil(area / 70) 后取不小于 raw_count 的偶数 | 0.5 kW/台 | 4.0 kW/台 |
| 覆膜间 | ceil(area / 70) | 1.5 kW/台 | 6.0 kW/台 |
| 成品间 | ceil(area / 70) | 1.5 kW/台 | 6.0 kW/台 |
| 次果暂存间 | 固定 1 台 | 1.0 kW/台 | 8.0 kW/台 |
| 冻果间 | 固定 1 台 | 3.0 kW/台 | 26.0 kW/台 |
| 出货通道 | ceil(area / 50) | 2.0 kW/台 | 12.0 kW/台 |

所有冷风机电机功率进入 POOL_B；所有冷风机化霜功率进入 POOL_A。
同一设备的电机与化霜功率必须作为两个明细分量呈现，不能在设备明细中
合并后丢失功率池归属。

## 3. 面积档位、公共设备和照明

加工厂面积档位只由权威 factory_area_m2 决定：

| 档位 | 边界 |
| --- | --- |
| SMALL | factory_area_m2 ≤ 2500 |
| MEDIUM | 2500 < factory_area_m2 ≤ 5000 |
| LARGE | factory_area_m2 > 5000 |

所以 2500 m² 和 5000 m² 都落在较低档位。当前仓库没有字面量
factory_area_m2 字段；后续实现必须先完成权威输入映射，缺失时 fail closed。

公共设备的数量和单台功率为：

| 设备 | SMALL / MEDIUM / LARGE 数量 | 单台功率 |
| --- | ---: | ---: |
| 冷库电动平移门 | 15 / 30 / 50 | 0.5 kW/套 |
| 快卷门 | 6 / 10 / 16 | 0.5 kW/套 |
| 风幕机 | 4 / 8 / 12 | 0.4 kW/套 |
| 升降门及装卸平台 | 2 / 3 / 4 | 3.0 kW/套 |

臭氧与加湿合计固定 30.0 kW，地坪加热丝固定 4.0 kW；两者均进入
POOL_B。

照明只使用冷间面积。当前仓库没有字面量 cold_storage_area_m2。
refrigerated_area_m2 是候选字段，但不同路径存在派生口径差异：有的按
非“常温”区域汇总并包含 −18℃，operator-minimal lineage 路径则只汇总
8~10℃ 和 1~3℃。因此 V2.0 的 canonical 语义名称
cold_storage_area_m2 在后续实现前必须先冻结是否包含冻果间，并发布唯一
派生来源；这不是整个加工厂建筑面积：

~~~text
cold_storage_lighting_count = ceil(cold_storage_area_m2 / 10)
cold_storage_lighting_power_kw = count * 0.04
uv_lighting_count = ceil(cold_storage_area_m2 / 20)
uv_lighting_power_kw = count * 0.08
~~~

## 4. 压缩机和冷凝器

主系统且仅主系统覆盖以下六个区域：

~~~text
primary_precooling_room
secondary_precooling_room
raw_fruit_buffer
sorting_packaging_room
coating_room
finished_goods_room
~~~

主系统制冷量是这六个区域的权威 V1.9 逐区最低估算制冷量之和，
来源字段为 minimum_estimated_cooling_load_kw_r，单位为 kW(r)。
主压缩机轴功率为：

~~~text
main_system_cooling_load_kw_r = sum(the six included zone values)
MAIN_SYSTEM_COP = 3.3
main_compressor_shaft_power_kw = main_system_cooling_load_kw_r / 3.3
~~~

冻果间、次果暂存区、出货通道分别使用 SMALL/MEDIUM/LARGE 的
15/25/40 kW、4/6/8 kW、8/12/16 kW 专用压缩机轴功率。这三个区域
不得再次进入主系统的 COP 汇总。主系统和三个专用系统的所有轴功率进入
POOL_B。

蒸发式冷凝器按面积档位为 20/30/40 kW，进入 POOL_B。

## 5. 生产功率与三池分离

生产设备装机功率按面积档位为 200/300/400 kW。生产同时系数固定为
0.85，生产计入功率为装机功率乘以 0.85，直接进入 POOL_C。
生产设备不得先进入 POOL_B 再乘面积档位系数。

化霜池 POOL_A 只包含所有区域冷风机化霜装机功率，使用 0.30；
其他池 POOL_B 包含所有非化霜、非生产列明功率，使用 SMALL/MEDIUM/LARGE
的 1.00/0.90/0.80；生产池 POOL_C 只包含生产设备，使用 0.85。
三池是互斥归属，最终计入功率只能由三池计入值相加得到。

## 6. 最终语义与统一呈现

保留完整装机功率，同时输出最终估算工厂电功率：

~~~text
estimated_total_power_kw =
  defrost_coincident_power_kw
  + other_coincident_power_kw
  + production_equipment_coincident_power_kw

total_installed_power_kw =
  defrost_installed_power_kw
  + other_installed_power_kw
  + production_equipment_installed_power_kw
~~~

这里的最终结果是 ESTIMATED_ELECTRICAL_POWER，单位为 kW。它明确不是
kWh 能量、不是电表计量电量、也不是日用电量。

工作台和豆包/Aily 后续只能读取同一个后端 canonical result。最小明细列为：
设备或区域、计算依据、配置数量、单台功率、装机功率、功率池、同时系数、
计入功率。总览至少列出化霜、其他设备、生产设备三池的装机/计入功率、
总装机功率和最终估算用电功率。任何前端或 Aily 重新计算都违反本契约。

~~~text
NO_AILY_RECALCULATION
NO_FRONTEND_RECALCULATION
NO_OUTBOUND_LIVE_AILY_SESSION
~~~

## 7. Fail-closed 与非授权

后续运行时若缺少 factory_area_m2、冷间面积映射、逐区 required_area_m2、
最终 position_count、V1.9 逐区最低估算字段或功率池所需输入，必须返回
可审计的缺失/未映射原因；不得猜测、使用建筑总面积替代或回退到旧演示清单。

本 P0 不改变以下任何运行时表面：

~~~text
RUNTIME_CODE_CHANGE=NO
FRONTEND_CODE_CHANGE=NO
AILY_RUNTIME_CHANGE=NO
OUTBOUND_LIVE_AILY_SESSION_AUTHORIZED=NO
DATABASE_MIGRATION=NO
EQUIPMENT_MODEL_SELECTION=NO
TRANSFORMER_SIZING=NO
KWH_ESTIMATION=NO
ELECTRICITY_PRICE=NO
MONTHLY_BILL=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
P1_AUTHORIZED=NO
P2_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
~~~

P0 仅把规则冻结为可审计契约；后端实现、工作台实现、豆包/Aily 实现和任何
发布动作都必须等待单独授权。
