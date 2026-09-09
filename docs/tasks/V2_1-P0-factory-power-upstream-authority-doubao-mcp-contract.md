# V2.1 P0：工厂功率上游权威与豆包 MCP 合同

本文件是 V2.1 P0 的正式契约。它冻结面积 authority、zone integrity、
`preview_factory_power` 的输入输出和消费者边界，但不实现任何 runtime、MCP 或
Skill。未来实现必须先通过本文件和
`backend/tests/architecture/test_v21_p0_factory_power_upstream_authority_doubao_mcp_contract.py`
的架构门禁。

## 状态与授权

~~~text
TASK_ID=V21_P0_FACTORY_POWER_UPSTREAM_AUTHORITY_AND_DOUBAO_MCP_CONTRACT_R1
TARGET_VERSION=v2.1.0
BASE_RELEASE=v2.0.0
BASE_MAIN_SHA=a7049ca93d238013c0cf62069fe1e0a89ff834d7
V2_0_RELEASE_TAG_PEELED_SHA=a7049ca93d238013c0cf62069fe1e0a89ff834d7
BASE_MAIN_SHA_IS_ANCESTOR_OF_HEAD=YES
CONTRACT_FREEZE=YES
VERSION_PLAN=YES
ADR=YES
ARCHITECTURE_LOCK=YES
RUNTIME_IMPLEMENTATION=NO
MCP_IMPLEMENTATION=NO
SKILL_IMPLEMENTATION=NO
DATABASE_MIGRATION=NO
READY=NO
MERGE=NO
TAG=NO
RELEASE=NO
DEPLOYMENT=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
~~~

本阶段只产生契约、版本计划、ADR 和架构测试。`P1_EXECUTED=NO`、
`P2_EXECUTED=NO`、`READY_EXECUTED=false`、`MERGE_EXECUTED=false`、
`TAG_CREATED=false`、`RELEASE_CREATED=false` 是本阶段的当前门禁事实。

## 1. Owner Decision：五 KEY 不变，面积不回问

用户输入仍严格为：

```text
daily_inbound_mass_kg
finished_storage_days
frozen_storage_days
main_packaging_storage_days
auxiliary_packaging_storage_days
```

下列字段禁止出现在用户/MCP 输入 schema 中：

```text
factory_area_m2
cold_storage_area_m2
refrigerated_area_m2
total_area_m2
```

```text
USER_REENTERS_FACTORY_AREA=NO
USER_REENTERS_COLD_STORAGE_AREA=NO
DOUBAO_ASKS_FACTORY_AREA=NO
DOUBAO_ASKS_COLD_STORAGE_AREA=NO
AILY_DERIVES_ENGINEERING_AREA=NO
AILY_GUESSES_ENGINEERING_AREA=NO
BACKEND_BINDS_AREA_FROM_UPSTREAM_AUTHORITY=YES
FACTORY_POWER_FORMULA_RECUT=NO
V20_P1_CALCULATOR_UNCHANGED=YES
V20_P2_PRESENTATION_UNCHANGED=YES
```

## 2. 唯一权威链

```text
五个用户 KEY
  → cold_room_zone_plan@1.0.0
  → zone_plan.result.zones[]
  → V2.1 upstream authority adapter
  → factory_area_m2 / cold_storage_area_m2 / validated zones[]
  → factory_power_estimation@2.0.0-p1
  → existing shared presentation
  → Aily / Doubao
```

```text
AREA_COMES_FROM_ZONE_PLAN=YES
AREA_COMES_FROM_USER=NO
AREA_COMES_FROM_LLM=NO
AREA_COMES_FROM_LEGACY_POWER=NO
```

`cold_room_zone_plan@1.0.0` 是上游规划 authority；Aily/Doubao 只能读取后端
canonical 结果。stateless 情况允许后端用原五 KEY 重放 zone plan，但不得由 Aily、
豆包或用户补面积。

## 3. factory_area_m2：12 个 planned functional zones 的合计

正式公式为：

```text
factory_area_m2 = quantize_0_01(
    SUM(
        Decimal(str(zone.required_area_m2))
        FOR zone IN canonical zone_plan.result.zones[]
    )
)
```

语义固定为 `SUM_ALL_PLANNED_FUNCTIONAL_ZONES`。canonical zone set 必须精确包含
以下 12 项，不能少算、重算或接受未知 zone：

| zone_code | 语义 |
| --- | --- |
| `office` | 办公 |
| `changing_room` | 更衣 |
| `primary_precooling_room` | 一级预冷 |
| `secondary_precooling_room` | 二级预冷 |
| `raw_fruit_buffer` | 原果暂存 |
| `sorting_packaging_room` | 分选包装 |
| `coating_room` | 覆膜 |
| `finished_goods_room` | 成品 |
| `secondary_fruit_buffer` | 次果暂存 |
| `frozen_fruit_room` | 冻果 |
| `packaging_material_storage` | 包材 |
| `shipping_channel` | 出货通道 |

```text
FACTORY_ZONE_COUNT=12
FACTORY_AREA_SEMANTIC=SUM_ALL_PLANNED_FUNCTIONAL_ZONES
```

这 12 个编码必须绑定到实际的 `ColdRoomZonePlanner` canonical 输出，而不是只在
合同 JSON 与测试常量之间互相复制。架构测试通过既有
`build_zone_plan_from_inputs(demo_inputs(), ColdRoomZonePlanner())` assembler 路径
读取 `zone_plan.result.zones[].zone_code`，并执行精确 cross-layer equality：

```text
CONTRACT_EXPECTED_ZONE_SET == RUNTIME_COLD_ROOM_ZONE_PLANNER_ZONE_SET
RUNTIME_FACTORY_ZONE_COUNT=12
RUNTIME_FACTORY_ZONE_SET_EXACT=YES
```

base lineage 只验证 `BASE_MAIN_SHA` 是当前 `HEAD` 的祖先，并验证
`v2.0.0^{}` 仍解析到该 SHA。`origin/main` 在后续合并后允许前进，不作为必须等于
本次 PR 基线的持久条件。

### total 字段的交叉校验

`zone_plan.result.total_required_area_m2` 和
`zone_plan.result.total_area_m2` 不是独立 authority。它们只能和 12 个 zone
row 的 Decimal 合计做 integrity cross-check：

```text
total_required_area_m2 == derived_factory_area
total_area_m2 == derived_factory_area
```

任一比较不成立必须 fail closed：

```text
FACTORY_AREA_TOTAL_MISMATCH
```

禁止忽略 `zones[]` 直接信任 total，也禁止发生 mismatch 后选择某个 total 继续。

## 4. cold_storage_area_m2：9 个 refrigerated zones 的合计

`cold_storage_area_m2` 的 authority 是 canonical zone rows 加上既有
`REFRIGERATED_ZONE_REGISTRY`，而不是历史模糊字段。registry 的源文件是：

```text
backend/src/cold_storage/modules/projects/application/operator_process_input.py
REFRIGERATED_ZONE_REGISTRY
```

冻结的 9 个 zone 与温区为：

| zone_code | temperature_band |
| --- | --- |
| `primary_precooling_room` | `8~10℃` |
| `secondary_precooling_room` | `1~3℃` |
| `raw_fruit_buffer` | `8~10℃` |
| `sorting_packaging_room` | `8~10℃` |
| `coating_room` | `1~3℃` |
| `finished_goods_room` | `1~3℃` |
| `secondary_fruit_buffer` | `8~10℃` |
| `frozen_fruit_room` | `-18℃` |
| `shipping_channel` | `1~3℃` |

```text
cold_storage_area_m2 = quantize_0_01(
    SUM(zone.required_area_m2 FOR zone_code IN REFRIGERATED_ZONE_REGISTRY)
)
REFRIGERATED_ZONE_COUNT=9
FROZEN_FRUIT_ROOM_INCLUDED=YES
SHIPPING_CHANNEL_INCLUDED=YES
AMBIENT_AREA_INCLUDED_IN_COLD_STORAGE_AREA=NO
REFRIGERATED_AREA_M2_IS_V21_AUTHORITY=NO
frozen_fruit_room=-18℃
shipping_channel=1~3℃
```

`office`、`changing_room` 和 `packaging_material_storage` 被明确排除。不得写成
`cold_storage_area_m2 = refrigerated_area_m2`，除非未来独立版本合同重新授权。

## 5. Zone integrity 与 fail-closed 错误

adapter 必须先验证 zone authority，再绑定两个面积。至少锁定：

```text
ZONE_CODE_UNIQUE=YES
EXPECTED_ZONE_SET_EXACT=YES
REQUIRED_AREA_PRESENT=YES
REQUIRED_AREA_NON_NEGATIVE=YES
REFRIGERATED_ZONE_CODE_TEMPERATURE_BAND_EXACT=YES
```

至少使用以下明确错误码：

```text
ZONE_AUTHORITY_SET_MISMATCH
DUPLICATE_ZONE_CODE
MISSING_ZONE_REQUIRED_AREA
INVALID_ZONE_REQUIRED_AREA
REFRIGERATED_ZONE_TEMPERATURE_MISMATCH
FACTORY_AREA_TOTAL_MISMATCH
REFRIGERATED_AREA_M2_FORBIDDEN_AS_AUTHORITY
```

仅 9 个 registry 冷区的 `zone_code` 与 `temperature_band` 必须与 registry 完全一致。
例如，`frozen_fruit_room` 被标成常温时必须返回
`REFRIGERATED_ZONE_TEMPERATURE_MISMATCH`，不能因温区错误而把它从冷间面积中
少算。未知 `fake_factory_area` 不得扩大 factory area。

## 6. V2.0 calculator 与 presentation 不变

V2.1 adapter 绑定上游 authority，不重设计 V2.0 公式。以下内容继续以
`factory_power_estimation@2.0.0-p1` 既有实现为 authority：

```text
CALCULATOR_IDENTITY=factory_power_estimation@2.0.0-p1
MAIN_SYSTEM_COP=3.3
POOL_A=DEFROST
POOL_B=OTHER
POOL_C=PRODUCTION
V20_P1_CALCULATOR_UNCHANGED=YES
V20_P2_PRESENTATION_UNCHANGED=YES
FACTORY_POWER_FORMULA_RECUT=NO
```

不得修改冷风机、公共设备、照明、专用压缩机、生产设备、同时系数或
`minimum_estimated_cooling_load_kw_r` 的既有语义。旧
`installed_power@1.0.0` 和 `power_configuration` 仍与 V2.0 factory power 分离：

```text
INSTALLED_POWER_REPLACED=NO
POWER_CONFIGURATION_REPLACED=NO
FIVE_STAGE_CALCULATION_TYPE_CHANGED=NO
```

## 7. Stateless Doubao MCP contract

冻结的新工具名为：

```text
NEW_MCP_TOOL=preview_factory_power
BUSINESS_NAME=估算工厂电功率
SOURCE_CALCULATOR=factory_power_estimation@2.0.0-p1
NEW_MCP_TOOL_POSITION=6
EXISTING_FIVE_TOOL_ORDER_CHANGED=NO
```

现有五工具顺序保持：

```text
preview_zone_plan
preview_cooling_load
preview_equipment
preview_installed_power
preview_investment
```

新工具只允许 append，不得替换 `preview_installed_power`。明确提到“工厂电功率”、
“估算工厂电功率”或“工厂总用电功率”时，未来 Skill/router 才能选择新工具；
“装机功率/五阶段装机功率”必须继续选择旧工具；仅说“功率”不在 P0 中静默改义。

```text
DOUBAO_CARRIES_ENGINEERING_AREA=NO
DOUBAO_CARRIES_ZONE_RESULT_AS_AUTHORITY=NO
BACKEND_STATELESS_ZONE_PLAN_REPLAY_ALLOWED=YES
```

### MCP input schema

新工具的 input schema 只包含原五 KEY：

```text
MCP_INPUT_REMAINS_FIVE_KEY=YES
MCP_FACTORY_AREA_INPUT_ALLOWED=NO
MCP_COLD_STORAGE_AREA_INPUT_ALLOWED=NO
MCP_REFRIGERATED_AREA_INPUT_ALLOWED=NO
MCP_TOTAL_AREA_INPUT_ALLOWED=NO
additionalProperties=false
```

未来 MCP 层必须把 schema 拒绝未知面积字段；P0 不实现该工具本身。

### MCP output schema

成功输出必须来自 `project_factory_power_table()` 或完全相同的 shared
presentation contract，不得在 MCP 层重算。最小合同为：

```text
reply_kind=factory_power_estimation_table
available=true
calculator_identity=factory_power_estimation@2.0.0-p1
canonical_result_hash=sha256:<64 hex>
details
summary
unit_semantics
review
provenance
assumptions
requires_review=true
UNIT=kW
```

呈现列继续为：设备/区域、计算依据、数量、单台功率、装机功率、功率池、同时
系数、计入功率。`summary` 只能读取 canonical result 的以下字段，不得复制公式：

```text
defrost_installed_power_kw
defrost_coincident_power_kw
other_installed_power_kw
other_coincident_power_kw
production_equipment_installed_power_kw
production_equipment_coincident_power_kw
total_installed_power_kw
estimated_total_power_kw
```

## 8. 产品语义

`preview_factory_power` 的结果是概念设计阶段估算工厂电功率，单位为 `kW`，
并且必须保留 `requires_review=true`。它不是：

```text
kWh
日耗电量
月耗电量
电费
电表计量值
变压器选型
正式配电设计
施工图
短路计算
电缆选型
保护整定
```

## 9. Hostile contract cases

P0 架构测试以这些 cases 锁定未来实现必须 fail closed：

| case | 输入/破坏 | 结果 |
| --- | --- | --- |
| A | MCP 传入 `factory_area_m2=9999` 或其他面积字段 | schema 拒绝，`MCP_INPUT_SCHEMA_REJECTED` |
| B | zone sum 为 2500，但 `total_area_m2=9999` | `FACTORY_AREA_TOTAL_MISMATCH` |
| C | `frozen_fruit_room.temperature_band=常温` | `REFRIGERATED_ZONE_TEMPERATURE_MISMATCH` |
| D | 缺失 `frozen_fruit_room` | `ZONE_AUTHORITY_SET_MISMATCH` |
| E | 重复 `zone_code` | `DUPLICATE_ZONE_CODE` |
| F | 注入 `fake_factory_area` | `ZONE_AUTHORITY_SET_MISMATCH` |
| G | 以 `refrigerated_area_m2` 替代 canonical zone rows | `REFRIGERATED_AREA_M2_FORBIDDEN_AS_AUTHORITY` |

## 10. P0 non-goals 与后续 gates

~~~text
P1_EXECUTED=NO
P2_EXECUTED=NO
RUNTIME_TEST_CHANGE_REQUIRED=NO
DATABASE_MIGRATION=NO
OUTBOUND_LIVE_AILY_SESSION=NO
READY=NO
MERGE=NO
TAG=NO
RELEASE=NO
DEPLOYMENT=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
~~~

P1 才能实现 adapter；P2 才能实现 MCP/Skill/router/runbook integration。P0 的
契约冻结、架构测试通过或 Draft PR 推送，都不自动授予后续阶段、Ready、Merge、
tag、release 或 deployment 权限。

## Machine-readable contract matrix

下面 JSON 是本文件的机器可读规则矩阵；它与上文同一份合同，供架构测试读取。

~~~json
{
  "contract_id": "V21_P0_FACTORY_POWER_UPSTREAM_AUTHORITY_AND_DOUBAO_MCP_CONTRACT_R1",
  "target_version": "v2.1.0",
  "base_release": "v2.0.0",
  "base_main_sha": "a7049ca93d238013c0cf62069fe1e0a89ff834d7",
  "operator_input": {
    "fields": [
      "daily_inbound_mass_kg",
      "finished_storage_days",
      "frozen_storage_days",
      "main_packaging_storage_days",
      "auxiliary_packaging_storage_days"
    ],
    "additional_properties": false,
    "forbidden_fields": [
      "factory_area_m2",
      "cold_storage_area_m2",
      "refrigerated_area_m2",
      "total_area_m2"
    ]
  },
  "factory_area": {
    "source": "zone_plan.result.zones[].required_area_m2",
    "semantic": "SUM_ALL_PLANNED_FUNCTIONAL_ZONES",
    "formula": "quantize_0_01(SUM(Decimal(str(zone.required_area_m2)) FOR zone IN zones))",
    "zone_codes": [
      "office",
      "changing_room",
      "primary_precooling_room",
      "secondary_precooling_room",
      "raw_fruit_buffer",
      "sorting_packaging_room",
      "coating_room",
      "finished_goods_room",
      "secondary_fruit_buffer",
      "frozen_fruit_room",
      "packaging_material_storage",
      "shipping_channel"
    ],
    "total_cross_checks": [
      "total_required_area_m2",
      "total_area_m2"
    ],
    "mismatch_error": "FACTORY_AREA_TOTAL_MISMATCH"
  },
  "runtime_binding": {
    "planner": "ColdRoomZonePlanner",
    "assembler": "cold_storage.modules.planning.application.service.build_zone_plan_from_inputs",
    "result_path": "zone_plan.result.zones[].zone_code",
    "contract_equality": "CONTRACT_EXPECTED_ZONE_SET == RUNTIME_COLD_ROOM_ZONE_PLANNER_ZONE_SET",
    "refrigerated_registry": "REFRIGERATED_ZONE_REGISTRY",
    "refrigerated_temperature_scope": "REFRIGERATED_ONLY",
    "factory_zone_count": 12,
    "zone_code_unique": true,
    "expected_zone_set_exact": true
  },
  "cold_storage_area": {
    "source": "zone_plan.result.zones[].required_area_m2 + REFRIGERATED_ZONE_REGISTRY",
    "registry_source": "backend/src/cold_storage/modules/projects/application/operator_process_input.py",
    "zone_temperature_bands": [
      {"zone_code": "primary_precooling_room", "temperature_band": "8~10℃"},
      {"zone_code": "secondary_precooling_room", "temperature_band": "1~3℃"},
      {"zone_code": "raw_fruit_buffer", "temperature_band": "8~10℃"},
      {"zone_code": "sorting_packaging_room", "temperature_band": "8~10℃"},
      {"zone_code": "coating_room", "temperature_band": "1~3℃"},
      {"zone_code": "finished_goods_room", "temperature_band": "1~3℃"},
      {"zone_code": "secondary_fruit_buffer", "temperature_band": "8~10℃"},
      {"zone_code": "frozen_fruit_room", "temperature_band": "-18℃"},
      {"zone_code": "shipping_channel", "temperature_band": "1~3℃"}
    ],
    "included": [
      "primary_precooling_room",
      "secondary_precooling_room",
      "raw_fruit_buffer",
      "sorting_packaging_room",
      "coating_room",
      "finished_goods_room",
      "secondary_fruit_buffer",
      "frozen_fruit_room",
      "shipping_channel"
    ],
    "excluded": [
      "office",
      "changing_room",
      "packaging_material_storage"
    ],
    "forbidden_substitute": "refrigerated_area_m2"
  },
  "zone_integrity": {
    "required": [
      "ZONE_CODE_UNIQUE",
      "EXPECTED_ZONE_SET_EXACT",
      "REQUIRED_AREA_PRESENT",
      "REQUIRED_AREA_NON_NEGATIVE",
      "REFRIGERATED_ZONE_CODE_TEMPERATURE_BAND_EXACT"
    ],
    "errors": [
      "ZONE_AUTHORITY_SET_MISMATCH",
      "DUPLICATE_ZONE_CODE",
      "MISSING_ZONE_REQUIRED_AREA",
      "INVALID_ZONE_REQUIRED_AREA",
      "REFRIGERATED_ZONE_TEMPERATURE_MISMATCH",
      "FACTORY_AREA_TOTAL_MISMATCH",
      "REFRIGERATED_AREA_M2_FORBIDDEN_AS_AUTHORITY"
    ]
  },
  "v20_boundary": {
    "calculator_identity": "factory_power_estimation@2.0.0-p1",
    "main_system_cop": "3.3",
    "p1_calculator_unchanged": true,
    "p2_presentation_unchanged": true,
    "factory_power_formula_recut": false,
    "installed_power_replaced": false,
    "power_configuration_replaced": false
  },
  "doubao_mcp": {
    "new_tool": "preview_factory_power",
    "position": 6,
    "existing_five_tool_order": [
      "preview_zone_plan",
      "preview_cooling_load",
      "preview_equipment",
      "preview_installed_power",
      "preview_investment"
    ],
    "existing_five_tool_order_changed": false,
    "input_schema": {
      "type": "object",
      "properties": {
        "daily_inbound_mass_kg": {"type": "number"},
        "finished_storage_days": {"type": "number"},
        "frozen_storage_days": {"type": "number"},
        "main_packaging_storage_days": {"type": "number"},
        "auxiliary_packaging_storage_days": {"type": "number"}
      },
      "required": [
        "daily_inbound_mass_kg",
        "finished_storage_days",
        "frozen_storage_days",
        "main_packaging_storage_days",
        "auxiliary_packaging_storage_days"
      ],
      "additionalProperties": false
    },
    "output_fields": [
      "reply_kind",
      "available",
      "calculator_identity",
      "canonical_result_hash",
      "details",
      "summary",
      "unit_semantics",
      "review",
      "provenance",
      "assumptions"
    ]
  },
  "semantics": {
    "unit": "kW",
    "requires_review": true,
    "concept_design_estimate": true,
    "not_metered_energy": true,
    "not_formal_electrical_design": true
  },
  "gates": {
    "contract_freeze": true,
    "runtime_implementation": false,
    "mcp_implementation": false,
    "skill_implementation": false,
    "database_migration": false,
    "ready": false,
    "merge": false,
    "tag": false,
    "release": false,
    "deployment": false,
    "no_step_implies_the_next": true
  },
  "hostile_cases": [
    {"id": "A_AREA_INPUT", "error": "MCP_INPUT_SCHEMA_REJECTED"},
    {"id": "B_TOTAL_MISMATCH", "error": "FACTORY_AREA_TOTAL_MISMATCH"},
    {"id": "C_FROZEN_TEMPERATURE", "error": "REFRIGERATED_ZONE_TEMPERATURE_MISMATCH"},
    {"id": "D_FROZEN_MISSING", "error": "ZONE_AUTHORITY_SET_MISMATCH"},
    {"id": "E_DUPLICATE_ZONE", "error": "DUPLICATE_ZONE_CODE"},
    {"id": "F_UNKNOWN_ZONE", "error": "ZONE_AUTHORITY_SET_MISMATCH"},
    {"id": "G_REFRIGERATED_SUBSTITUTE", "error": "REFRIGERATED_AREA_M2_FORBIDDEN_AS_AUTHORITY"}
  ]
}
~~~
