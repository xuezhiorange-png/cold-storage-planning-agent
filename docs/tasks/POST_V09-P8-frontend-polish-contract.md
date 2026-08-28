# POST-V0.9 P8 — Operator Workbench Visual Polish

**Status:** Implementation authorized — Charles `可以派发` 2026-08-28  
**Authority:** 网站前端能不能美观一点 — **separate** from result-table
column maps (P5)  
**Parent on `main`:** `d6c3af953d0d8486fd5762e5797ecd336f44fbf2`  
**Target branch:** `cursor/post-v09-p8-frontend-polish-6c68`

Polish the **operator workbench chrome**: header, nav, page frames, form
layout, empty states. Do not change which engineering numbers appear.
Do not change scheme-button enablement. Do not recut formulas. Do not
recompose Word reports.

Sibling packages: P4, P5, P7, P6. Exclusive files: do **not** edit the
P5 result-table Vue files or P7 panels.

## 0. Governance

```text
TASK=POST_V09_P8_FRONTEND_POLISH_R1
GOVERNANCE_OWNER=POST-V0.9
BASE_MAIN_SHA=d6c3af953d0d8486fd5762e5797ecd336f44fbf2
PREVIOUS_RELEASE=v0.9.0
TARGET_BRANCH=cursor/post-v09-p8-frontend-polish-6c68
TARGET_FILE=docs/tasks/POST_V09-P8-frontend-polish-contract.md
TARGET_PR_STATE=DRAFT

POST_V09_P8_IMPLEMENTATION_AUTHORIZED=YES
FORMULA_RECUT_AUTHORIZED=NO
VUE_ENGINEERING_FORMULAS=NO
AILY_LIVE_IMPLEMENTATION=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
CHARLES_POST_V09_P8_LIVING_TEST_UPDATE_AUTHORIZED=YES
```

## 1. Visual lock (what “美观” means this package)

Keep the existing navy workbench identity (`#071a31` / `#123a63`). Do not
introduce a second design language or illustration pack.

Required:

1. **AppShell** — product name 冷库规划工作台. English subtitle may stay
   at 11px or be removed. Header less cramped; no extra routes.
2. **WorkbenchLayout nav** — six operator items stay (工程输入 | 计算结果 |
   方案比选 | 投资估算 | 用电配置 | 报告输出). Look like a **process strip**
   (clear active step), not scattered pills. Do **not** bring back 基本信息 /
   planning-run.
3. **Engineering input** — page title **工程输入**. Drop
   `(OperatorProcessInputV1)` from the visible header. Five KEY form:
   aligned labels, consistent control width, primary submit still 提交.
4. **Schemes / 投资估算 / 用电配置 / 报告输出** — same card radius, padding,
   and heading weight as 工程输入. Drop English schema/API ids from
   visible titles (`power_configuration` may remain only in the existing
   supplemental warning that it cannot replace installed_power).
5. **CalculationSummary** — keep four totals; remove emoji icons if
   present; typography consistent with the shell.
6. **Empty states** — short Chinese, not a dashed box that looks like a
   placeholder wireframe.
7. Optional: `frontend/src/app/operator-workbench.css` tokens imported
   from AppShell so pages inherit spacing/color without each page
   inventing hex codes.

Do not add a project picker. Do not delete `ProjectPage.vue`. Do not
change router paths.

## 2. Exclusive allowlist

```text
POST_V09_P8_FILE_ALLOWLIST
docs/tasks/POST_V09-P8-frontend-polish-contract.md
backend/tests/architecture/test_post_v09_p8_frontend_polish_contract.py
frontend/src/app/AppShell.vue
frontend/src/app/operator-workbench.css
frontend/src/features/workbench/WorkbenchLayout.vue
frontend/src/features/workbench/architecture/test_post_v09_p1_hide_planning_run_nav.test.ts
frontend/src/features/five-stage/components/EngineeringInputsPage.vue
frontend/src/features/five-stage/components/EngineeringInputBundleForm.vue
frontend/src/features/five-stage/components/BundleLeafField.vue
frontend/src/features/calculations/components/CalculationSummary.vue
frontend/src/features/calculations/components/CalculationSummary.test.ts
frontend/src/features/schemes/components/SchemesPage.vue
frontend/src/features/investment/components/InvestmentPage.vue
frontend/src/features/power/components/PowerPage.vue
frontend/src/features/reports/components/ReportsPage.vue
frontend/src/features/reports/components/ReportExportPanel.vue
frontend/src/features/workbench/architecture/test_post_v09_p8_frontend_polish.test.ts
```

`operator-workbench.css` is new. If unused, do not add it.

**Forbidden on this branch:**  
`ZoneResultsTable.vue`, `CoolingLoadResultsTable.vue`,
`EquipmentResultsTable.vue`, `InstalledPowerResultsTable.vue`,
`InvestmentResultsTable.vue`, `FiveStageProgressPanel.vue`,
`ProductionSchemeRunPanel.vue`, `WorkflowGuidancePanel.vue`,
`zone_planning.py`, report assembler/canonical builder.

P1 arch test may still require nav **not** to contain 基本信息 — keep that.

## 3. Verification

If browser tools are available, walk 工程输入 → 计算结果 → 方案比选 →
投资估算 → 用电配置 → 报告输出. Otherwise vitest for layout copy and
nav items. Say in the PR what could not be clicked.

## 4. Out of scope

- Result column maps (P5)
- Scheme button logic (P7)
- Word/PDF section composition (P6)
- Zone formulas (P4)
