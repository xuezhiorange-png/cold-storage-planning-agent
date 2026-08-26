# V0.8 P1 — Process Input Assembler Contract

```text
TASK=V08_P1_PROCESS_INPUT_ASSEMBLER_R1
PARENT_CONTRACT=docs/tasks/V0_8-P0-operator-minimal-input-contract.md
BASE_MAIN_SHA=e69e5d984b0bd62419d8f5c50d2685d970dcef7e
BASE_SUBJECT=V0.8 P0: freeze operator-minimal process-input contract (#208)
PREVIOUS_RELEASE=v0.7.0
TARGET_BRANCH=cursor/v08-p1-process-input-assembler-6c68
V08_P1_IMPLEMENTATION_AUTHORIZED=YES
AILY_LIVE_IMPLEMENTATION=NO
```

## 1. Objective

Expand `OperatorProcessInputV1` (five operator KEY leaves) into execution-authoritative
`EngineeringInputBundleV1` in the application layer, persist the assembled bundle,
and bind typed upstream lineage at the correct stage boundaries. Vue, calculator
formulas, samples, and tags are out of scope for P1.

## 2. Dual-path request shapes

| Path | Request body | Validation timing |
| --- | --- | --- |
| A — full bundle (V0.5/V0.6/V0.7) | `{ "engineering_input_bundle": EngineeringInputBundleV1, "idempotency_key": "..." }` | All KEY leaves required at submit (`validation_mode=full`). |
| B — operator-minimal | `{ "operator_process_input": OperatorProcessInputV1, "idempotency_key": "..." }` OR five-field payload without `EngineeringInputBundleV1` schema | Five KEY leaves validated before assembly; assembled bundle validated with `validation_mode=operator_minimal`; lineage-bound leaves may be `state=lineage_pending` until their producing stage persists. |

`project_version_identity` is filled from the bound route project version, not operator typing.

`idempotency_key` `payload_hash` is computed on the **assembled** `EngineeringInputBundleV1`.

## 3. V0.5 auto-feed amendment (operator-minimal path only)

```text
OPERATOR_PROCESS_INPUT_FIVE_KEY_LEAVES_ONLY=YES
ZONE_RESULT_TO_COOLING_LOAD_IDENTITY_AND_PLAN_AREA_LINEAGE=YES
ZONE_RESULT_TO_COOLING_LOAD_ENVELOPE_AUTO_FEED=NO
PERSISTED_UPSTREAM_RESULT_TO_DOWNSTREAM_TYPED_INPUT=YES
DEMO_CATALOG_TO_EXPLICIT_BUNDLE_LEAF=YES
DEMO_DEFAULT_TO_AUTHORITATIVE_INPUT_WITHOUT_BUNDLE_LEAF=NO
POWER_CONFIGURATION_TO_INSTALLED_POWER_AUTO_FEED=NO
AGENT_TO_ENGINEERING_VALUE=NO
```

## 4. Lineage extensions (P1)

| Stage | Bind when `persisted_upstream_confirmed` | Source → target |
| --- | --- | --- |
| `cooling_load` | after `zone` persist | zone `zones[].zone_code` / `zone_name` / `temperature_band` / `required_area_m2` → cooling `zone_code` / `zone_name` / `temperature_level` / `zone_area` / `floor_area` |
| `equipment` | after `cooling_load` persist | cooling `zones[].subtotal_load_kw_r` → equipment `design_cooling_load_kw_r` |
| `power` | after `equipment` persist | equipment `compressor_operating_capacity_kw` with catalog `compressor_cop` (or `total_compressor_input_power_kw_e` when present) → installed power `compressor_input_power_kw_e` |
| `investment` | after `zone` + `power` persist | zone totals + power `total_installed_power_kw_e` → investment area / position / power; operator-minimal also binds `refrigerated_area_m2` / `frozen_area_m2` by summing persisted zone `required_area_m2` grouped by `temperature_band` |

Type mismatch or `zone_code` mismatch → `UPSTREAM_LINEAGE_BIND_FAILED` (fail-closed).

## 5. Leaf catalog source table (operator-minimal assembly)

### 5.1 Operator KEY (`source_type=user`)

| Leaf | Unit |
| --- | --- |
| `zone_planning_inputs.daily_inbound_mass_kg` | kg/day |
| `zone_planning_inputs.working_time_h_per_day` | h/day |
| `zone_planning_inputs.finished_storage_days` | day |
| `zone_planning_inputs.packaging_storage_days` | day |
| `zone_planning_inputs.precooling_required_ratio` | ratio |

### 5.2 Zone remainder (`ColdRoomZonePlanInput` dataclass defaults)

Copied at runtime from `backend/src/cold_storage/modules/calculations/domain/zone_planning.py`
`ColdRoomZonePlanInput` field defaults. `DemoZoneCoefficient` entries are provenance-only in
`coefficient_context.demo_coefficient_leaves`.

**E1–E8 non-resolution (consumer uses Input default, metadata marks conflict):**

| ID | Field | Input default | Demo catalog | Bundle metadata |
| --- | --- | --- | --- | --- |
| E1 | `frozen_fruit_ratio` | 0.10 | 0.05 | `validity_status=conflict`, `requires_review=true` |
| E2 | `frozen_storage_days` | 5 | 14 | `validity_status=conflict`, `requires_review=true` |
| E3 | `storage_position_capacity_kg` | 400 | 500 | `validity_status=conflict`, `requires_review=true` |
| E8 | `raw_holding_hours` | 6.6666666667 | 6.6666666667 | copied from Input default; not recut |

### 5.3 Cooling identity + plan area (`source_type=persisted`, lineage after zone)

`temperature_band` → `TemperatureLevel` mapping (`source_type=demo`, `requires_review=true`):

| `temperature_band` | `temperature_level` |
| --- | --- |
| `8~10℃` | `precooling` |
| `1~3℃` | `medium_temperature` |
| `-18℃` | `low_temperature` |

`常温` zones are excluded from cooling-load zones. Unmapped band → fail-closed.

### 5.4 Cooling envelope / thermal catalog (`samples/v05-local-workbench/manifest.json`)

Applied per refrigerated zone; **not scaled** by `required_area_m2`:

| Leaf | Value | Source |
| --- | --- | --- |
| `room_height` | 5.0 m | manifest |
| `wall_area` | 200.0 m² | manifest |
| `roof_area` | 100.0 m² | manifest |
| `outdoor_design_temperature` | 30.0 °C | manifest |
| `operating_hours_per_day` | operator `working_time_h_per_day` | user KEY |
| `product_mass_per_day` | operator `daily_inbound_mass_kg` | user KEY |
| `product_entry_temperature` | 20.0 °C | manifest |
| `product_target_temperature` | band table (9.0 / 2.0 / -18.0 °C) | demo mapping |
| `cooling_duration` | 8.0 h | manifest |
| `u_value_wall` | 0.25 | manifest |
| `u_value_roof` | 0.20 | manifest |
| `u_value_floor` | 0.30 | manifest |
| `product_specific_heat` | 3.6 kJ/(kg·K) | manifest |
| coefficients `design_margin_ratio` / `diversity_factor` / `air_change_rate` / `respiration_heat` / `worker_heat_gain` / `motor_efficiency` | 1.1 / 0.85 / 0.5 / 0.0 / 0.275 / 0.85 | manifest |

### 5.5 Equipment grouping

Systems grouped by zone-plan `temperature_band`. Per-zone leaves from `ZoneEquipmentInput` defaults
(`evaporator_count=1`, `defrost_method=electric`, `evaporation_temperature_c=-10`).
`condensing_temperature_c=40.0` from `samples/v07-trust-loop/manifest.json`.
Equipment coefficients from v05 workbench manifest (`redundancy_ratio` 1.0, margins 1.1, `compressor_cop` 2.5).
`design_cooling_load_kw_r` is lineage-bound after cooling stage.

### 5.6 Installed power

`compressor_input_power_kw_e` lineage-bound after equipment stage from persisted
`compressor_operating_capacity_kw` and explicit catalog `compressor_cop` (equipment
calculator relationship; canonical equipment snapshot may omit
`total_compressor_input_power_kw_e`). When the typed electrical total is present on
the equipment snapshot, bind that field directly.
`evaporator_fan_power_kw_e` / `condenser_fan_power_kw_e` copied from `InstalledPowerCalcInput` defaults (0).

### 5.7 Investment

All investment KEY leaves lineage-bound on operator-minimal path after zone + power persist.

## 6. Allowlist (exclusive)

```text
V08_P1_FILE_ALLOWLIST
docs/tasks/V0_8-P1-process-input-assembler-contract.md
backend/src/cold_storage/modules/projects/application/operator_process_input.py
backend/src/cold_storage/modules/projects/application/engineering_input_bundle.py
backend/src/cold_storage/modules/projects/application/five_stage_execution.py
backend/src/cold_storage/bootstrap/app.py
backend/tests/architecture/test_v08_p1_operator_process_input_contract.py
backend/tests/unit/test_v08_p1_operator_process_input_assembler.py
backend/tests/integration/test_v08_p1_five_field_execution_sqlite.py
backend/tests/integration/test_v08_p1_five_field_execution_postgresql.py
```

## 7. Acceptance criteria

- Operator-minimal POST with five KEY + `idempotency_key` persists all five canonical stages on unmodified `create_app`.
- Full `EngineeringInputBundleV1` POST path unchanged; V0.5 assertion bodies still pass.
- Missing operator KEY → `MISSING_ENGINEERING_PARAMETER`.
- Catalog hole after assembly → `MISSING_ENGINEERING_PARAMETER`.
- Lineage type / `zone_code` mismatch → `UPSTREAM_LINEAGE_BIND_FAILED`.
- `app.py` contains no engineering formula literals or catalog numbers.
- Assembled bundle is the execution/idempotency authority; reports continue to read persisted results only.

## 8. Not in P1

- Vue operator form (P2)
- `samples/v08-process-input` (P3)
- Calculator formula edits
- Tag / Release / merge authorization
