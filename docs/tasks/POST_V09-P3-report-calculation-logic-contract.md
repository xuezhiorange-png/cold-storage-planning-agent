# POST-V0.9 P3 — Report Calculation Logic Projection

**Status:** Implementation authorized — reports show five KEY + persisted formulas  
**Authority:** Charles `可以派发` 2026-08-27: 报告要体现计算逻辑; also bind
operator five KEY into 输入条件  
**Parent on `main`:** `c6f806575a3d100bd00ef22aa7600f3c7109c7ee`  
**ADR:** `docs/architecture/ADR-030-report-calculation-logic-projection.md`  
**Target branch:** `cursor/post-v09-p3-report-calculation-logic-6c68`

This package implements **P3 only**. Reports **read** persisted calculation
runs. They MUST NOT recalculate formulas. Vue MUST NOT duplicate formulas.

Sibling packages (do not implement here):

- P1: `docs/tasks/POST_V09-P1-hide-planning-run-nav-contract.md`
- P2: `docs/tasks/POST_V09-P2-stage-result-display-contract.md`

## 0. Contract identity and governance

```text
TASK=POST_V09_P3_REPORT_CALCULATION_LOGIC_R1
GOVERNANCE_OWNER=POST-V0.9
BASE_MAIN_SHA=c6f806575a3d100bd00ef22aa7600f3c7109c7ee
BASE_SUBJECT=Align workbench workflow guidance with V0.9 five KEY. (#223)
PREVIOUS_RELEASE=v0.9.0
TARGET_BRANCH=cursor/post-v09-p3-report-calculation-logic-6c68
TARGET_FILE=docs/tasks/POST_V09-P3-report-calculation-logic-contract.md
TARGET_PR_STATE=DRAFT

POST_V09_P3_IMPLEMENTATION_AUTHORIZED=YES
POST_V09_P1_IMPLEMENTATION_AUTHORIZED=NO
POST_V09_P2_IMPLEMENTATION_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT=NO
VUE_ENGINEERING_FORMULAS=NO
REPORTS_MUST_NOT_RECALCULATE=YES
KEEP_REPORT_TYPE_IDENTITY=cold_storage_concept_design@1.0.0
ADDITIVE_SCHEMA_ONLY=YES
AILY_LIVE_IMPLEMENTATION=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
CHARLES_POST_V09_P3_LIVING_TEST_UPDATE_AUTHORIZED=YES
```

## 1. Objective

Operator draft/formal JSON and Word/PDF must show:

1. The five operator KEY that produced the run.
2. The persisted calculation logic (`formula_id` / `expression` /
   `description`, and `steps` when stored), bound to `calculation_id`.

Do not recut cooling/equipment/power/investment **formulas**. Do not bump
calculator `VERSION`. Do not bump report type identity off
`cold_storage_concept_design@1.0.0`.

## 2. Schema (additive)

Keep `$id` / `report_metadata.schema_version` const
`cold_storage_concept_design@1.0.0`.

### 2.1 `input_conditions`

Existing properties stay. Add **optional** scalars (numbers, not measured
dicts):

```text
daily_inbound_mass_kg
finished_storage_days
frozen_storage_days
main_packaging_storage_days
auxiliary_packaging_storage_days
```

`additionalProperties` remains false. Do not add deleted V0.8 KEY
(`working_time_h_per_day`, `packaging_storage_days`,
`precooling_required_ratio`).

### 2.2 `calculation_logic` (new optional section)

```text
calculation_logic.stages[]:
  stage                  zone | cooling_load | equipment | power | investment
  calculator_name
  calculator_version
  calculation_id
  formulas[]: formula_id, formula_version, expression, description
  steps[]:    step_id, formula, description, inputs, output_name, output_value
```

All of those fields are copied from persistence. Omit a stage that has
no run. Omit `steps` when the run has none. Do not synthesize placeholder
steps.

Add `calculation_logic` to:

- `COLD_STORAGE_CONCEPT_DESIGN_V1` properties
- `_REPORT_SCHEMA_PROPERTIES`
- `_SECTION_KEYS` / `_SECTION_BUILD_ORDER` (after `input_conditions`,
  before or after `assumptions` is fine; pick one and test it)

Do not add it to template `required_sections` if that would fail-closed
historical templates. The section is **optional** in schema; when the
assembler has formulas, it MUST populate the section.

## 3. Source binding (fail-closed, no guessing)

Five KEY, in order of preference, first complete persisted source wins:

1. Five-stage execution snapshot `operator_process_input` / assembled
   `zone_planning_inputs` leaves.
2. Canonical `cold_room_zone_plan` run `input_snapshot` leaves of the
   same names.
3. Omit the KEY. Never read V0.4 `version.input_snapshot` fields
   `working_time_h_per_day` / `utilization_factor` as substitutes.

Formulas: `CalculationRunRecord.formulas` as returned by GET calculations
/ the reports persisted-calculation reader. Also accept
`result_snapshot.formula_references` if that is how a run stored them.

Steps: `result_snapshot.steps` or `result_snapshot.result.steps` when the
value is a list of mappings with the keys in §2.2. If absent, omit.

Each `calculation_logic` stage MUST include `calculation_id` from the
persisted run. Citations may point `section_key=calculation_logic`.

Reports still MUST NOT call calculator domain functions.

## 4. Canonical render (the actual Word/PDF hole)

Today `input_conditions` is not a `_TEXT_SECTION`. Arrays are skipped;
the section often becomes `empty` / `not_provided`.

This package MUST:

- Render the five KEY scalars in **输入条件** (text fields or a small
  table). If those scalars exist in JSON, Word/PDF must not be empty for
  that section.
- Render `calculation_logic` as one or more **tables** (`content_type_code`
  `table`, new `table_key` such as `calculation_logic_formulas` /
  `calculation_logic_steps`). Localizer must translate those table keys
  (fail-closed `MissingTranslationError` for unknown keys still applies —
  add catalog entries).
- Existing investment breakdown / cooling measured-value metrics stay.

Do not reimplement PDF/DOCX layout engines. Use the existing table
section path (`docx_renderer` / `pdf_renderer` already render `table`).

Locale catalogs (`zh_cn.py`, `en_us.py`):

```text
section.calculation_logic
field.daily_inbound_mass_kg
field.finished_storage_days
field.frozen_storage_days
field.main_packaging_storage_days
field.auxiliary_packaging_storage_days
```

plus table header keys used by the new tables. Catalog `version` stays
`1.0.0`.

## 5. Workbench preview

`ReportExportPanel` “已持久化报告摘要” currently shows only
`project_summary` (+ scheme review_authority). Extend it to list the five
KEY from `input_conditions` and a compact formula list from
`calculation_logic` when those objects exist on revision content.

No Vue arithmetic.

## 6. Exclusive allowlist

```text
POST_V09_P3_FILE_ALLOWLIST
docs/tasks/POST_V09-P3-report-calculation-logic-contract.md
docs/architecture/ADR-030-report-calculation-logic-projection.md
backend/tests/architecture/test_post_v09_p3_report_calculation_logic_contract.py
backend/src/cold_storage/modules/reports/domain/schema.py
backend/src/cold_storage/modules/reports/domain/quality.py
backend/src/cold_storage/modules/reports/application/assembler.py
backend/src/cold_storage/modules/reports/application/canonical_render_model_builder.py
backend/src/cold_storage/modules/reports/application/persisted_calculation_reads.py
backend/src/cold_storage/modules/reports/application/render_model_localizer.py
backend/src/cold_storage/modules/reports/infrastructure/real_data_provider.py
backend/src/cold_storage/modules/reports/infrastructure/persisted_calculation_query.py
backend/src/cold_storage/modules/reports/localization/zh_cn.py
backend/src/cold_storage/modules/reports/localization/en_us.py
backend/src/cold_storage/modules/reports/localization/catalog.py
frontend/src/features/reports/components/ReportExportPanel.vue
frontend/src/features/reports/types.ts
frontend/src/features/reports/composables/useReportExport.test.ts
backend/tests/test_reports/test_post_v09_p3_calculation_logic.py
backend/tests/test_reports/test_localization.py
backend/tests/unit/test_reports_rendering.py
backend/tests/test_reports/test_real_production_e2e.py
backend/tests/test_reports/test_real_storage_e2e.py
backend/tests/test_reports/test_scheme_provenance_golden_e2e.py
frontend/src/features/reports/architecture/test_post_v09_p3_report_preview.test.ts
```

`CHARLES_POST_V09_P3_LIVING_TEST_UPDATE_AUTHORIZED=YES` means tests on
this allowlist (especially `test_localization.py` schema-property
registry and `test_reports_rendering.py` section lists) may be updated
to **admit** the additive section and five KEY. Do not weaken:

- fail-closed missing translation
- fail-closed missing engineering parameter
- reports-must-not-recalculate assertions
- on-disk calculator formula identity tests

If a V0.9 P6/P7 integration assertion fails only because JSON now has
extra allowed keys, update that assertion on this allowlist **or** add
the extra check to `test_post_v09_p3_calculation_logic.py` and skipif
the old equality. Prefer extending `assert_report_trust_loop_json` in a
P3 test module copy rather than editing
`backend/tests/integration/v09_p6_operator_fixtures.py` (not on the
allowlist).

Forbidden: `zone_planning.py`, cooling/equipment/power/investment formula
modules, `WorkbenchLayout.vue`, `CalculationsPage.vue`, Alembic, live Aily,
calculator `VERSION` bumps.

## 7. Acceptance criteria

```text
P3-AC-01 Draft JSON after five-stage contains the five KEY on input_conditions when those leaves were persisted
P3-AC-02 Draft JSON contains calculation_logic.stages with calculation_id and at least formulas[] when the run stored formulas
P3-AC-03 Word/PDF draft render is HTTP 200 and canonical model is not empty/not_provided for input_conditions when KEY exist
P3-AC-04 Word/PDF includes a calculation_logic table when formulas exist
P3-AC-05 Missing KEY/formulas omitted; no silent defaults; no calculator re-entry from reports
P3-AC-06 ReportExportPanel preview shows KEY + formula list when present
P3-AC-07 Architecture allowlist vs origin/main on this branch
P3-AC-08 Report type identity remains cold_storage_concept_design@1.0.0
```

Seed path for tests: existing V0.9 sample / five-stage execution on
unmodified `create_app`. Do not add a new loader module.

## 8. Not in P3

- Hiding 基本信息 (P1)
- Calculations page stage tables (P2)
- Auto production-scheme-run
- Stable English `item_key` for investment (TD-022)
- Recutting zone/cooling formulas
- Merge, tag, Release

## 9. Rollback

Revert this PR. Reports return to inherited V0.6 mapping without KEY or
logic tables.

## Revision history

| Rev | Date | Notes |
| --- | --- | --- |
| R1 | 2026-08-27 | Charles 可以派发: report shows KEY + persisted calculation logic |
| R2 | 2026-08-27 | Admit additive `calculation_logic` in frozen canonical section-key sets |
