# POST-V0.9 P6 — Human-Readable Report Composition

**Status:** Implementation authorized — Charles `可以派发` 2026-08-28  
**Authority:** 输出的报告也是让人能看懂，不是直接把网页内容一抄  
**Parent on `main`:** `d6c3af953d0d8486fd5762e5797ecd336f44fbf2`  
**Target branch:** `cursor/post-v09-p6-report-readability-6c68`

Draft/formal Word and PDF must read like a concept-design handout:
Chinese section titles, **tables of results**, short labeled values.
They must not dump workbench chrome, English JSON keys, UUID walls, or
`calculation_id` / `result_hash` as the body.

Reports **copy** persisted values. They MUST NOT recalculate formulas.
Keep report type identity `cold_storage_concept_design@1.0.0`.
Additive catalog keys only (zh-CN and en-US key sets must match).

Sibling packages (do not implement here): P4, P5, P7, P8.

## 0. Governance

```text
TASK=POST_V09_P6_REPORT_READABILITY_R1
GOVERNANCE_OWNER=POST-V0.9
BASE_MAIN_SHA=d6c3af953d0d8486fd5762e5797ecd336f44fbf2
PREVIOUS_RELEASE=v0.9.0
TARGET_BRANCH=cursor/post-v09-p6-report-readability-6c68
TARGET_FILE=docs/tasks/POST_V09-P6-report-readability-contract.md
TARGET_PR_STATE=DRAFT

POST_V09_P6_IMPLEMENTATION_AUTHORIZED=YES
REPORTS_MUST_NOT_RECALCULATE=YES
KEEP_REPORT_TYPE_IDENTITY=cold_storage_concept_design@1.0.0
ADDITIVE_SCHEMA_ONLY=YES
FORMULA_RECUT_AUTHORIZED=NO
VUE_ENGINEERING_FORMULAS=NO
AILY_LIVE_IMPLEMENTATION=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
CHARLES_POST_V09_P6_LIVING_TEST_UPDATE_AUTHORIZED=YES
```

Do not add a new ADR unless schema `$id` would change (it must not).

## 1. Render behavior

Canonical builder stays locale-free. Localizer translates catalog keys.
No hardcoded Chinese/English in the builder.

### 1.1 `input_conditions`

Emit a **table**: 参数 / 数值 / 单位 for the five operator KEY when
present. Keep `text_fields` populated with the same scalars so existing
readers still see `daily_inbound_mass_kg`. Prefer `content_type_code=table`
so Word renders a table (P3 living test that required `text` may be
retargeted).

Units: kg/day for mass; day for the four day KEY.

### 1.2 `throughput_inventory_area`

If `zone_details` (or persisted `zones`) is a list of objects, emit a
table: 区域名称 / 温区 / 面积 / 板位 from persisted
`zone_name`, `temperature_band`, `required_area_m2`, `position_count`.
Also surface `daily_inbound_mass_kg` and `total_area_m2` as labeled
values (text_fields and/or leading table caption rows). Do not dump
the whole zone dict.

### 1.3 `calculation_logic`

Keep the section (schema unchanged). Operator-facing table columns:

- stage (catalog `stage.zone` / `stage.cooling_load` / …)
- formula_id
- expression
- description

**Drop `calculation_id` from the rendered table.** JSON `stages[].calculation_id`
may still exist for citations. Catalog title may read **计算依据**
(keep key `section.calculation_logic`).

### 1.4 Other sections

Cooling / equipment / electrical: if only measured-value metrics exist,
render them as a compact 项目/数值/单位 table rather than a paragraph
list of English field paths. Do not invent zone_loads that were never
projected.

Citations / quality / provenance stay as appendix-like sections. Do not
promote hashes into 项目概况.

## 2. Exclusive allowlist

```text
POST_V09_P6_FILE_ALLOWLIST
docs/tasks/POST_V09-P6-report-readability-contract.md
backend/tests/architecture/test_post_v09_p6_report_readability_contract.py
backend/src/cold_storage/modules/reports/application/canonical_render_model_builder.py
backend/src/cold_storage/modules/reports/application/render_model_localizer.py
backend/src/cold_storage/modules/reports/localization/zh_cn.py
backend/src/cold_storage/modules/reports/localization/en_us.py
backend/tests/test_reports/test_post_v09_p3_calculation_logic.py
backend/tests/test_reports/test_post_v09_p6_report_readability.py
backend/tests/test_reports/test_localization.py
backend/tests/unit/test_reports_rendering.py
```

If a frozen e2e title assertion fails only because `section.calculation_logic`
display string changed, living-test update of that assertion is authorized
on this branch; do not weaken “must not recalculate”.

Do not edit Vue except if `ReportExportPanel` currently inlines raw JSON
as the operator preview — then you may show the same tables the render
model already has, still without formulas in Vue. Add that file to the
allowlist in the PR if needed.

## 3. Out of scope

- zone_planning.py
- Frontend workbench pages (P5/P8)
- Scheme-runs
