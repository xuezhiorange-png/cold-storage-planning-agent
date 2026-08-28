# POST-V0.9 P7 — Production Scheme Button and Sidebar Copy

**Status:** Implementation authorized — Charles `可以派发` 2026-08-28  
**Authority:** 五阶段已落库仍不能跑方案评分；侧面一堆阻断  
**Parent on `main`:** `d6c3af953d0d8486fd5762e5797ecd336f44fbf2`  
**Target branch:** `cursor/post-v09-p7-scheme-button-6c68`

Enable **运行生产方案评分** when canonical five-stage results are
**persisted**, not when workflow step `DETERMINISTIC_CALCULATION` is
`COMPLETED`. Demo `requires_review=true` must not trap the button.

Do not auto-run scheme after 工程输入. Do not promote demo coefficients
to verified. Do not open formal export. Do not recut formulas.

Sibling packages: P4, P5, P6, P8 (P8 must not restyle this panel’s
enablement logic; P5 must not change this gate).

## 0. Governance

```text
TASK=POST_V09_P7_SCHEME_BUTTON_R1
GOVERNANCE_OWNER=POST-V0.9
BASE_MAIN_SHA=d6c3af953d0d8486fd5762e5797ecd336f44fbf2
PREVIOUS_RELEASE=v0.9.0
TARGET_BRANCH=cursor/post-v09-p7-scheme-button-6c68
TARGET_FILE=docs/tasks/POST_V09-P7-scheme-button-contract.md
TARGET_PR_STATE=DRAFT

POST_V09_P7_IMPLEMENTATION_AUTHORIZED=YES
FORMULA_RECUT_AUTHORIZED=NO
VUE_ENGINEERING_FORMULAS=NO
AUTO_RUN_PRODUCTION_SCHEME=NO
AILY_LIVE_IMPLEMENTATION=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
CHARLES_POST_V09_P7_LIVING_TEST_UPDATE_AUTHORIZED=YES
```

## 1. Button gate

Today `ProductionSchemeRunPanel` uses:

```ts
calcStep?.status === 'COMPLETED'
```

Demo review keeps that step at `REVIEW_REQUIRED`, so the button stays
disabled even when five canonical rows exist. Backend
`POST .../production-scheme-runs` only needs a persisted five-stage
SourceBinding.

**Required:** `fiveStageReady` is true iff persisted progress
`chainComplete` is true (five canonical slots present), using
`usePersistedPlanningResultsStore` and/or the `progress` already loaded
on 计算结果. If not persisted: keep disabled + banner 「需先完成五阶段持久化」.
If persisted with `requires_review=true`: **enable** the button; still
POST the existing API.

Header copy: **生产方案评分** (drop `(production-scheme-runs)`).
Result metadata: Chinese labels; hashes inside `<details>`.

## 2. Sidebar

`WorkflowGuidancePanel`:

- When five stages are persisted and the only remaining core blocker is
  `SCHEME_MISSING`, badge **进行中** (not 已阻断).
- 核心阻断 in that state: one Chinese line
  「还没跑生产方案评分，请到计算结果页运行」.
- One Chinese next action pointing at 计算结果. No English
  “Complete deterministic calculation（需先解决阻断项）”.
- Formal-export note stays non-blocking.
- `CALCULATION_REQUIRES_REVIEW` stays out of 核心阻断 (already filtered).

After a successful scheme run, existing backend should drop
`SCHEME_MISSING`; do not invent a new workflow API unless the frontend
cannot detect `chainComplete` without it. Prefer frontend-only.

## 3. Exclusive allowlist

```text
POST_V09_P7_FILE_ALLOWLIST
docs/tasks/POST_V09-P7-scheme-button-contract.md
backend/tests/architecture/test_post_v09_p7_scheme_button_contract.py
frontend/src/features/five-stage/components/ProductionSchemeRunPanel.vue
frontend/src/features/workflow/components/WorkflowGuidancePanel.vue
frontend/src/features/five-stage/components/ProductionSchemeRunPanel.test.ts
frontend/src/features/workflow/components/WorkflowGuidancePanel.test.ts
frontend/src/features/workbench/architecture/test_post_v09_p7_scheme_button.test.ts
```

Add the `*.test.ts` files if they do not exist. Do not edit
`FiveStageProgressPanel.vue` (P5). Do not edit `WorkbenchLayout.vue` (P8).

## 4. Out of scope

- Auto scheme-run from 工程输入
- Backend workflow aggregate rewrite (unless frontend cannot implement §2)
- Formal export eligibility change
