# V0.8 P2 — Operator Workbench Contract

```text
TASK=V08_P2_OPERATOR_WORKBENCH_R1
PARENT_CONTRACT=docs/tasks/V0_8-P0-operator-minimal-input-contract.md
BASE_MAIN_SHA=1961d7ab5cd4e76c5e7a077700b9eda31f0e737e
BASE_SUBJECT=V0.8 P1: assemble operator-minimal process input into EngineeringInputBundleV1 (#209)
PREVIOUS_RELEASE=v0.7.0
TARGET_BRANCH=cursor/v08-p2-operator-workbench-6c68
V08_P2_IMPLEMENTATION_AUTHORIZED=YES
AILY_LIVE_IMPLEMENTATION=NO
```

## 1. Objective

Shrink the operator **工程输入** workbench to the five process KEY leaves only.
Submit compact `OperatorProcessInputV1`; the P1 application assembler expands it
into `EngineeringInputBundleV1` on the backend. Vue must not assemble cooling
geometry, equipment, installed power, investment KEY, or copy catalog numbers.

## 2. Operator-visible surface

| Leaf path | Unit |
| --- | --- |
| `zone_planning_inputs.daily_inbound_mass_kg` | kg/day |
| `zone_planning_inputs.working_time_h_per_day` | h/day |
| `zone_planning_inputs.finished_storage_days` | day |
| `zone_planning_inputs.packaging_storage_days` | day |
| `zone_planning_inputs.precooling_required_ratio` | ratio |

`project_version_identity` is bound from the workbench project version context,
not typed by the operator.

Page title: **操作员过程输入 / OperatorProcessInputV1**.

## 3. Submit shape (path B — operator-minimal)

```json
{
  "operator_process_input": {
    "schema_id": "OperatorProcessInputV1",
    "schema_version": "1.0.0",
    "zone_planning_inputs": {
      "daily_inbound_mass_kg": { "value": "...", "unit": "kg/day", "state": "provided" },
      "working_time_h_per_day": { "value": "...", "unit": "h/day", "state": "provided" },
      "finished_storage_days": { "value": "...", "unit": "day", "state": "provided" },
      "packaging_storage_days": { "value": "...", "unit": "day", "state": "provided" },
      "precooling_required_ratio": { "value": "...", "unit": "ratio", "state": "provided" }
    }
  },
  "idempotency_key": "<uuid derived from stable five-KEY JSON>"
}
```

**Forbidden:** POST `engineering_input_bundle` from the operator workbench.

`idempotency_key` is derived from a stable JSON serialization of the five KEY
numeric leaves. Backend hashes the **assembled** bundle for replay semantics (P1).

## 4. Frontend prohibitions

```text
VUE_ASSEMBLES_COOLING_GEOMETRY=NO
VUE_ASSEMBLES_EQUIPMENT_KEY=NO
VUE_ASSEMBLES_INSTALLED_POWER_KEY=NO
VUE_ASSEMBLES_INVESTMENT_KEY=NO
VUE_COPIES_CATALOG_NUMBERS=NO
VUE_EMBEDS_ENGINEERING_FORMULAS=NO
COEFFICIENT_ID_AS_OPERATOR_KEYPAD=NO
DEFAULT_PREFILL_OPERATOR_KEY_NUMBERS=NO
```

- Cooling-zone geometry, U-values, equipment systems, installed-power components,
  investment quantities, and coefficient IDs must not appear as operator KEY
  controls.
- Catalog/provenance metadata may display read-only for review; it is not a
  second engineering keypad.
- Default form state leaves all five KEY numerics `null` (no silent `20000` etc.).

## 5. Legacy V0.4 page

`ProjectPage.vue` (基本信息 / `planning-run`) remains with badge
**V0.4 遗留路径 (planning-run)**. Copy must state it is **not** V0.8
five-stage authority. Do not delete; do not promote to V0.8 authority.

## 6. P2 exclusive allowlist

```text
V08_P2_FILE_ALLOWLIST
docs/tasks/V0_8-P2-operator-workbench-contract.md
frontend/src/features/five-stage/components/EngineeringInputBundleForm.vue
frontend/src/features/five-stage/components/EngineeringInputsPage.vue
frontend/src/features/five-stage/model/engineeringInputForm.ts
frontend/src/stores/fiveStageExecution.ts
frontend/src/features/five-stage/api/fiveStageApi.ts
frontend/src/api/contracts/fiveStage.ts
frontend/src/features/project/components/ProjectPage.vue
frontend/src/features/five-stage/architecture/test_v08_p2_five_key_operator_form.test.ts
```

Out of scope: `backend/**`, `samples/**`, assembler, calculators, tags, Release.

## 7. Acceptance criteria

```text
OPERATOR_FIVE_KEY_FORM_ONLY=PASS
POST_OPERATOR_PROCESS_INPUT=PASS
NO_ENGINEERING_INPUT_BUNDLE_FROM_WORKBENCH=PASS
NO_COOLING_EQUIPMENT_POWER_INVESTMENT_KEYPAD=PASS
NO_FORMULA_LITERALS_IN_FIVE_STAGE_UI=PASS
DEFAULT_KEY_NULL_NOT_PREFILLED=PASS
V05_P2_ARCHITECTURE_GUARDS_PASS=PASS
V08_P2_ARCHITECTURE_TEST_PASS=PASS
FRONTEND_VITEST_PASS=PASS
FRONTEND_LINT_PASS=PASS
LEGACY_PROJECT_PAGE_LABELED=PASS
MISSING_OPERATOR_KEY_FAIL_CLOSED=PASS
DRAFT=YES
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
```

Authoritative frontend architecture test:

```text
frontend/src/features/five-stage/architecture/test_v08_p2_five_key_operator_form.test.ts
```

## 8. Revision history

| Rev | Date | Change |
| --- | --- | --- |
| R1 | 2026-08-26 | Initial P2 operator workbench at `1961d7a` / P1 assembler baseline |
