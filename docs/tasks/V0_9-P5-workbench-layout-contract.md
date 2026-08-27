# V0.9 P5 — Workbench Layout And Non-Blocking Banners Contract

```text
TASK=V09_P5_WORKBENCH_LAYOUT_R1
PARENT_CONTRACT=docs/tasks/V0_9-P0-version-contract.md
PARENT_ISSUE=213
BASE_MAIN_SHA=d8474855ee0815552865ea36d98631a33111d674
BASE_TREE=60f9263053b6ae396d25c30a043b8fd8a258f1ed
PREVIOUS_RELEASE=v0.8.0
TARGET_BRANCH=cursor/v09-p5-workbench-layout-6c68
TARGET_FILE=docs/tasks/V0_9-P5-workbench-layout-contract.md
TARGET_PR_STATE=DRAFT

V09_P5_IMPLEMENTATION_AUTHORIZED=YES
V09_P1_IMPLEMENTATION_AUTHORIZED=NO
V09_P2_IMPLEMENTATION_AUTHORIZED=NO
V09_P3_IMPLEMENTATION_AUTHORIZED=NO
V09_P4_IMPLEMENTATION_AUTHORIZED=NO
V09_P6_IMPLEMENTATION_AUTHORIZED=NO
V09_P7_IMPLEMENTATION_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
AILY_LIVE_IMPLEMENTATION=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
VUE_ENGINEERING_FORMULAS=NO
```

This package implements **V0.9 P0 §7.6** only. It closes **V09-GAP-004**
(stacked 核心阻断 / 溯源阻断 / 正式导出 on every page) and **V09-GAP-006**
(lonely 960px column with unused viewport). It does not implement P1–P4,
P6, or P7.

## 1. Objective

Workbench chrome uses the screen: nav + content, with a desktop two-column
body (guidance / provenance aside + main) and a stacked layout at a
representative narrow width. Demo `requires_review`, unused knowledge OCR,
and formal-export ineligibility must not render as **核心阻断** on every
page. Real operator-step blockers (missing inputs / missing calculations
that stop the next fill-or-calculate step) remain visible.

## 2. Gaps closed

| ID | Gap | P5 treatment |
| --- | --- | --- |
| V09-GAP-006 | Single column; page `max-width` 960/760 leaves empty ocean | `WorkbenchLayout` two-column chrome; P5 pages use content-column width (`max-width: 1400px`) |
| V09-GAP-004 | Formal-export blockers and 溯源阻断 stacked as core stops | Filter review / formal-export / unused OCR out of 核心阻断; quiet unused provenance; short non-blocking formal-export note |

P4 owns draft-vs-formal export UX. P5 must not duplicate a large 正式导出
blocker list and must not change the export status machine.

## 3. Layout rules

```text
WORKBENCH_DESKTOP_TWO_COLUMN=YES
WORKBENCH_NARROW_STACK_ASIDE_ABOVE_MAIN=YES
NAV_MAY_WRAP=YES
PAGE_MAX_WIDTH_960_REMOVED_ON_P5_PAGES=YES
READABLE_MEASURE_MAX_WIDTH=1400px
ENGINEERING_INPUTS_PAGE_UNTOUCHED=YES
CALCULATIONS_PAGE_UNTOUCHED=YES
REPORTS_PAGE_UNTOUCHED=YES
```

- Desktop (`min-width: 961px`): `workbench-layout__body` is
  `minmax(260px, 22rem) minmax(0, 1fr)` — aside + main. Main fills leftover
  width. Aside may stick while scrolling.
- Narrow (`max-width: 960px`): body is one column; aside stacks above main;
  nav keeps `flex-wrap`.
- `ProjectPage`, `SchemesPage`, `PowerPage`, `InvestmentPage`: raise or
  remove 960px / 760px so they use the content column; cap at 1400px for a
  readable measure.
- Do not edit `EngineeringInputsPage`, `CalculationsPage`, `ReportsPage`,
  `EngineeringInputBundleForm`, `ZoneResultsTable`, `ReportExportPanel`.

## 4. Banner rules

```text
DEMO_REQUIRES_REVIEW_IS_NOT_CORE_STOP=YES
FORMAL_EXPORT_INELIGIBLE_IS_NOT_CORE_STOP=YES
UNUSED_OCR_PROVENANCE_IS_NOT_CORE_STOP=YES
OPERATOR_NOT_READY_BLOCKERS_REMAIN_VISIBLE=YES
FORMAL_EXPORT_STATUS_MACHINE_UNCHANGED=YES
NO_FABRICATED_OCR=YES
```

`WorkflowGuidancePanel`:

- **核心阻断** lists only blockers that stop the next operator step
  (example: `INPUT_MISSING`, `CALCULATION_MISSING`, `SCHEME_MISSING`,
  stale calculation/scheme lineage).
- Do **not** treat as 核心阻断: `*REQUIRES_REVIEW*`, scheme/human review
  pending, approval pending, `FORMAL_REPORT` / `REPORT_MISSING` /
  formal-export ineligibility, unused knowledge provenance codes.
- When the only remaining issues are review or formal-export, do not show
  the workflow badge as 已阻断. Draft work continues.
- Formal export is a short non-blocking note. Required copy:
  `正式导出与草稿导出不是同一件事；本条不阻止继续填写/计算.`
- Do not list a large formal-export blocker tree here (P4 owns that UX).

`KnowledgeProvenancePanel`:

- When provenance is `NOT_REQUIRED`, unused, or absent, collapse to a quiet
  note. Do not render 溯源阻断 as a core stop.
- Do not invent OCR rows, page evidence, or knowledge revisions.
- When knowledge **is** required and evidence is missing, keep fail-closed
  copy (`页面证据缺失；未伪造溯源数据`) without promoting it to workbench
  核心阻断.

## 5. Project leftover

`ProjectPage` (基本信息 / `planning-run`) remains a V0.4 leftover and MUST
stay labeled **non-authority**. Badge: `V0.4 遗留路径 (planning-run)`.

## 6. Exclusive allowlist

```text
V09_P5_FILE_ALLOWLIST
docs/tasks/V0_9-P5-workbench-layout-contract.md
frontend/src/features/workbench/WorkbenchLayout.vue
frontend/src/features/workflow/components/WorkflowGuidancePanel.vue
frontend/src/features/workflow/components/KnowledgeProvenancePanel.vue
frontend/src/features/project/components/ProjectPage.vue
frontend/src/features/schemes/components/SchemesPage.vue
frontend/src/features/power/components/PowerPage.vue
frontend/src/features/investment/components/InvestmentPage.vue
frontend/tests/workbench.test.ts
```

Forbidden in this package (not exhaustive): `zone_planning.py`, five-stage
formula files, `EngineeringInputBundleForm`, `CalculationsPage`,
`ZoneResultsTable`, `ReportsPage`, `ReportExportPanel`, Alembic, samples,
`v07_sample_loader.py`, `v08_sample_loader.py`, live Aily.

## 7. Acceptance criteria

```text
LAYOUT_TWO_COLUMN_DESKTOP=PASS
LAYOUT_STACK_NARROW=PASS
P5_PAGES_NOT_960_OR_760=PASS
CORE_BLOCKER_EXCLUDES_DEMO_REVIEW=PASS
CORE_BLOCKER_EXCLUDES_FORMAL_EXPORT=PASS
FORMAL_EXPORT_NOTE_NON_BLOCKING=PASS
UNUSED_PROVENANCE_QUIET=PASS
NO_FABRICATED_OCR=PASS
LEGACY_PROJECT_PAGE_LABELED=PASS
NO_VUE_ENGINEERING_FORMULAS=PASS
FORMULA_RECUT_AUTHORIZED=NO
AILY_LIVE_IMPLEMENTATION=NO
FRONTEND_WORKBENCH_TESTS_PASS=PASS
DRAFT=YES
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
```

Authoritative test surface:

```text
frontend/tests/workbench.test.ts
frontend/src/features/workflow/components/KnowledgeProvenancePanel.test.ts
```

(`KnowledgeProvenancePanel.test.ts` is frozen for this package; P5 must not
break its assertion bodies.)

## 8. Revision history

| Rev | Date | Change |
| --- | --- | --- |
| R1 | 2026-08-27 | P5 layout + non-blocking banners at `d847485` / P0 #213 / `v0.8.0` |
