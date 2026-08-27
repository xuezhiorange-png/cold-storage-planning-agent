# V0.9 P1 — Operator KEY Assembler Contract

**Status:** Implementation R1 — V0.9 five KEY `OperatorProcessInputV1` + assembler + 工程输入  
**Authority:** `docs/tasks/V0_9-P0-version-contract.md` §3, §6, §7.2; `docs/tasks/V0_9-version-plan.md` §2; ADR-029  
**Parent:** V0.9 P0 `#213` merged  
**Previous release:** `v0.8.0`

```text
TASK=V09_P1_OPERATOR_KEY_ASSEMBLER_R1
PARENT_CONTRACT=docs/tasks/V0_9-P0-version-contract.md
BASE_MAIN_SHA=d8474855ee0815552865ea36d98631a33111d674
BASE_TREE=60f9263053b6ae396d25c30a043b8fd8a258f1ed
BASE_SUBJECT=V0.9 P0: freeze version contract (KEY recut, DAG, dispatch NO for P1–P7) (#213)
PREVIOUS_RELEASE=v0.8.0
TARGET_BRANCH=cursor/v09-p1-operator-key-assembler-6c68
TARGET_FILE=docs/tasks/V0_9-P1-operator-key-assembler-contract.md
TARGET_PR_STATE=DRAFT

V09_P1_IMPLEMENTATION_AUTHORIZED=YES
V09_P2_IMPLEMENTATION_AUTHORIZED=NO
V09_P3_IMPLEMENTATION_AUTHORIZED=NO
V09_P4_IMPLEMENTATION_AUTHORIZED=NO
V09_P5_IMPLEMENTATION_AUTHORIZED=NO
V09_P6_IMPLEMENTATION_AUTHORIZED=NO
V09_P7_IMPLEMENTATION_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
DEMO_COEFFICIENT_CONFLICT_RESOLUTION=NO
AILY_LIVE_IMPLEMENTATION=NO
PRODUCTION_RBAC_CLAIM=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

This package implements **P1 only**. It does not recut zone formulas, does
not edit `zone_planning.py`, does not add `shipping_channel` to the
refrigerated-zone cooling registry, does not mutate V0.5–V0.8 assertion
bodies, and does not authorize P2–P7, tag, or Release.

## 1. Objective

On the operator path:

```text
OperatorProcessInputV1 (V0.9 five KEY, schema_version 1.1.0)
 → application assembler (catalog + identity; no new planner geometry)
 → EngineeringInputBundleV1 (execution authority)
 → five-stage-execution on unmodified create_app
```

Vue **工程输入** presents only the five KEY in §2 plus submit. It posts
`{ operator_process_input, idempotency_key }`. It MUST NOT post
`engineering_input_bundle`. It MUST NOT compute formulas.

Full `EngineeringInputBundleV1` remains Path A for V0.5–V0.8 clients.

## 2. V0.9 operator KEY (exactly these)

```text
schema_id: OperatorProcessInputV1
schema_version: 1.1.0
```

| Leaf | Unit |
| --- | --- |
| `zone_planning_inputs.daily_inbound_mass_kg` | kg/day |
| `zone_planning_inputs.finished_storage_days` | day |
| `zone_planning_inputs.frozen_storage_days` | day |
| `zone_planning_inputs.main_packaging_storage_days` | day |
| `zone_planning_inputs.auxiliary_packaging_storage_days` | day |

Removed from the operator surface (MUST NOT appear on Vue 工程输入):

```text
zone_planning_inputs.working_time_h_per_day
zone_planning_inputs.packaging_storage_days
zone_planning_inputs.precooling_required_ratio
```

`project_version_identity` is filled from the bound route project version.

Missing operator KEY on the **chosen** path fail-closes
`MISSING_ENGINEERING_PARAMETER`. Assembler and Vue MUST NOT silently
`.get()` defaults for operator KEY.

```text
MISSING_OPERATOR_PROCESS_KEY_LEAF → MISSING_ENGINEERING_PARAMETER
OPERATOR_PRECOOLING_RATIO_KEY → FORBIDDEN (V0.9 path does not accept it)
CALCULATOR_SILENT_DEFAULT_AS_NEW_AUTHORITY → FORBIDDEN
```

## 3. Dual-path V0.8 compatibility (CRITICAL)

Do not break V0.8 tests. Keep a V0.8 compact path.

Detection:

| Signal | Path |
| --- | --- |
| `schema_version` `1.1.0` | V0.9 — require the five KEY in §2 |
| `schema_version` `1.0.0` | V0.8 — require the V0.8 five KEY |
| `schema_version` omitted and V0.8 five KEY present | V0.8 (omitted-as-V0.8) |
| `schema_version` omitted and V0.9 five KEY present without a complete V0.8 set | V0.9 |

V0.8 five KEY (assemble as today):

```text
daily_inbound_mass_kg
working_time_h_per_day
finished_storage_days
packaging_storage_days
precooling_required_ratio
```

`OPERATOR_FIVE_KEY_FIELDS` and `OPERATOR_PROCESS_SCHEMA_VERSION` remain the
V0.8 (`1.0.0`) constants so V0.8 callers and `_KEY_ZONE_FIELDS` (calculator
required leaves at submit for Path A / assembled V0.8) stay stable.

V0.9 publishes `OPERATOR_V09_FIVE_KEY_FIELDS` and
`OPERATOR_PROCESS_SCHEMA_VERSION_V09 = 1.1.0`.

## 4. V0.9 assembly rules (do not invent numbers; do not recut formulas)

Assembler copies existing production authority into explicit bundle leaves.

### 4.1 Operator KEY (`source_type=user`)

The five leaves in §2. `frozen_storage_days` is a user KEY on this path
and is **no longer** a conflict-catalog overwrite.

`main_packaging_storage_days` / `auxiliary_packaging_storage_days` map onto
those `ColdRoomZonePlanInput` dataclass fields as user KEY (not hardcoded
3 / 30).

Those three leaves are also projected onto the zone execution snapshot so
the existing planner dataclass receives them. P1 does not change planner
formulas.

### 4.2 Catalog / derived leftovers required by the current planner

The zone planner (`FORMULA_RECUT_AUTHORIZED=NO`) still requires the V0.8
calculator leaves. On the V0.9 path the assembler supplies them; Vue must
not.

| Leaf | V0.9 rule |
| --- | --- |
| `precooling_required_ratio` | **Not** operator KEY. Catalog leaf value `1.0` (V09-E1 100% precool). `source_type=demo`, `validity_status=unverified`, `requires_review=true`. Do not accept it from the operator form. |
| `working_time_h_per_day` | **Not** operator KEY. Copy existing sample/dataclass-required catalog already in repo: **16 h/day** as used by the V0.8 sample (`samples/v08-process-input/manifest.json`). `source_type=demo`, `requires_review=true`. Cooling-load `operating_hours_per_day` is fed from this catalog leaf, **not** from operator. |
| `packaging_storage_days` | Legacy single field. Not required from operator. Copy `main_packaging_storage_days` into it as derived user leaf with `source_path=zone_planning_inputs.main_packaging_storage_days`. Do not guess a third number. |

Remaining `ColdRoomZonePlanInput` defaults continue to copy as demo catalog
leaves. E1 / E3 conflict rows (`frozen_fruit_ratio`,
`storage_position_capacity_kg`) stay `validity_status=conflict`,
`requires_review=true`. Do not pick E1/E3/E6–E8 winners.

### 4.3 `shipping_channel` deferred to P2

P0 §7.2 names zone identity including `shipping_channel`. **P1 MUST NOT
add `shipping_channel` to `REFRIGERATED_ZONE_REGISTRY`.** The zone planner
does not emit that zone until P2 (`FORMULA_RECUT_AUTHORIZED=YES`). Adding
it here would create a cooling identity with no matching persisted zone
result. P2 owns registry + planner emission together.

### 4.4 `bootstrap/app.py`

May accept the compact operator payload and pass it to the assembler
only. No formulas. No new catalog numeric literals in `app.py` (catalog
copies live in `operator_process_input.py` as today).

### 4.5 `five_stage_execution.py`

Only as required so a V0.9 compact payload validates after assembly. No
formula changes.

## 5. Frontend rule

V0.9 工程输入 (`EngineeringInputBundleForm.vue` +
`EngineeringInputsPage.vue`) MUST present only the five KEY in §2 plus
submit.

It MUST NOT present `precooling_required_ratio`, `working_time_h_per_day`,
or legacy `packaging_storage_days` as operator KEY.

Submit posts `{ operator_process_input, idempotency_key }` with
`schema_version: 1.1.0`. MUST NOT post `engineering_input_bundle`. MUST
NOT compute formulas.

Stale copy that tells operators to fill full `EngineeringInputBundleV1`
must not appear on `EngineeringInputsPage.vue`. (Calculations empty-state
copy is P5.)

Leftover Path A `buildEngineeringInputBundle` may remain in the form
model for V0.5 full-bundle tests; it is not the operator submit path.

## 6. Exclusive allowlist

```text
V09_P1_FILE_ALLOWLIST
docs/tasks/V0_9-P1-operator-key-assembler-contract.md
backend/src/cold_storage/modules/projects/application/operator_process_input.py
backend/src/cold_storage/modules/projects/application/engineering_input_bundle.py
backend/src/cold_storage/modules/projects/application/five_stage_execution.py
backend/src/cold_storage/bootstrap/app.py
frontend/src/features/five-stage/components/EngineeringInputBundleForm.vue
frontend/src/features/five-stage/components/EngineeringInputsPage.vue
frontend/src/features/five-stage/model/engineeringInputForm.ts
frontend/src/stores/fiveStageExecution.ts
frontend/src/features/five-stage/api/fiveStageApi.ts
frontend/src/api/contracts/fiveStage.ts
backend/tests/architecture/test_v09_p1_operator_key_contract.py
backend/tests/unit/test_v09_p1_operator_process_input_assembler.py
backend/tests/integration/test_v09_p1_five_field_execution_sqlite.py
backend/tests/integration/test_v09_p1_five_field_execution_postgresql.py
frontend/src/features/five-stage/architecture/test_v09_p1_five_key_operator_form.test.ts
```

**Forbidden in this package:**

```text
backend/src/cold_storage/modules/calculations/domain/zone_planning.py
backend/src/cold_storage/bootstrap/v07_sample_loader.py
backend/src/cold_storage/bootstrap/v08_sample_loader.py
test_v05_* / test_v06_* / test_v07_* / test_v08_* assertion bodies
cooling_load.py / equipment.py / installed_power.py / investment.py
```

## 7. Tests required

| Surface | Must prove |
| --- | --- |
| Architecture | V0.9 KEY list present; Vue/file-scan no `precooling_required_ratio` / `working_time` on operator form; allowlist vs `origin/main`; no `zone_planning.py` edits |
| Unit | V0.9 five KEY assemble; missing KEY fail-closed; frozen/main/aux days land on bundle; precooling ratio catalog 1.0; V0.8 five KEY still assembles |
| Integration sqlite + postgresql | V0.9 five-field five-stage-execution on unmodified `create_app` persists canonical five; missing KEY zero canonical rows |
| Frontend architecture | Form fields + submit `operator_process_input` |

## 8. Acceptance criteria

```text
V09_P1_FIVE_KEY_ASSEMBLED=PASS
V09_OPERATOR_FORM_FIVE_KEY_ONLY=PASS
V09_PRECOOLING_RATIO_NOT_OPERATOR_KEY=PASS
V09_WORKING_TIME_CATALOG_NOT_OPERATOR=PASS
V08_COMPACT_PATH_PRESERVED=PASS
MISSING_OPERATOR_KEY_FAIL_CLOSED=PASS
DEMO_CATALOG_LEAVES_REQUIRE_REVIEW=PASS
SHIPPING_CHANNEL_REGISTRY_DEFERRED_TO_P2=PASS
ZONE_PLANNING_PY_UNCHANGED=PASS
FORMULA_RECUT_AUTHORIZED=NO
AILY_LIVE_IMPLEMENTATION=NO
MERGE_AUTHORIZED=NO
DRAFT=YES
```

## 9. Not in P1

- Zone formula recut / `shipping_channel` emission (P2)
- Zone result display (P3)
- Draft vs formal export copy (P4)
- Workbench layout / blocker banners / CalculationsPage empty-state (P5)
- V0.9 sample loader (P6)
- Controlled acceptance (P7)
- Tag / Release / merge authorization

## 10. Revision history

| Rev | Date | Change |
| --- | --- | --- |
| R1 | 2026-08-27 | V0.9 P1 assembler + 工程输入 five KEY at `d847485` / `v0.8.0` |
