# POST-V0.9 P1 — Hide V0.4 基本信息 From Operator Nav

**Status:** Implementation authorized — operator nav / default landing  
**Authority:** Charles `可以派发` 2026-08-27 after local use of `v0.9.0` + #221/#223  
**Parent on `main`:** `v0.9.0` tag `5e38159` plus hotfixes #221 / #223 (`c6f8065`)  
**Target branch:** `cursor/post-v09-p1-hide-planning-run-nav-6c68`

This package implements **P1 only**: take the V0.4 `planning-run` page off the
operator path. It does not delete the leftover route. It does not display
five-stage result tables (P2). It does not recut report JSON (P3).

Sibling packages (do not implement here):

- P2: `docs/tasks/POST_V09-P2-stage-result-display-contract.md`
- P3: `docs/tasks/POST_V09-P3-report-calculation-logic-contract.md`

## 0. Contract identity and governance

```text
TASK=POST_V09_P1_HIDE_PLANNING_RUN_NAV_R1
GOVERNANCE_OWNER=POST-V0.9
BASE_MAIN_SHA=c6f806575a3d100bd00ef22aa7600f3c7109c7ee
BASE_SUBJECT=Align workbench workflow guidance with V0.9 five KEY. (#223)
PREVIOUS_RELEASE=v0.9.0
TARGET_BRANCH=cursor/post-v09-p1-hide-planning-run-nav-6c68
TARGET_FILE=docs/tasks/POST_V09-P1-hide-planning-run-nav-contract.md
TARGET_PR_STATE=DRAFT

POST_V09_P1_IMPLEMENTATION_AUTHORIZED=YES
POST_V09_P2_IMPLEMENTATION_AUTHORIZED=NO
POST_V09_P3_IMPLEMENTATION_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT=NO
VUE_ENGINEERING_FORMULAS=NO
AILY_LIVE_IMPLEMENTATION=NO
PRODUCTION_RBAC_CLAIM=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 1. Objective

Operator workbench no longer presents **基本信息** as a first-class step.
Opening the app lands on **工程输入**. The V0.4 `planning-run` page remains
reachable only by explicit URL and stays labeled non-authority.

## 2. Required operator-visible behavior

```text
NAV_HIDES_基本信息=YES
NAV_STARTS_WITH_工程输入=YES
DEFAULT_LANDING= /workbench/engineering-inputs
LEFTOVER_ROUTE_KEPT= /workbench/project
LEFTOVER_BADGE_UNCHANGED= V0.4 遗留路径 (planning-run)
INVESTMENT_EMPTY_POINTS_TO_工程输入=YES
```

Nav labels after this package (order):

1. 工程输入
2. 计算结果
3. 方案比选
4. 投资估算
5. 用电配置
6. 报告输出

Do **not** add a replacement 项目选择器 in this package.

Redirects that currently go to `/workbench/project` must go to
`/workbench/engineering-inputs`:

- `path: '/'`
- `path: '/workbench'` empty child
- catch-all `/:pathMatch(.*)*`
- App shell link **规划工作台** (`AppShell.vue`)

Keep `path: 'project'` and `ProjectPage.vue`. Do not delete
`ProjectInputsPanel`. Do not change leftover badge copy (V0.8 architecture
tests assert `不是 V0.8 五阶段权威输入`).

`InvestmentPage` empty state currently says 请在「基本信息」页面生成规划.
Replace with operator-path copy that points at **工程输入** and five KEY /
`OperatorProcessInputV1`. Do not mention 基本信息 as the way to generate
planning.

## 3. Tests that must move with the nav

Update existing tests so they match the new default landing and six-item
nav. Known fixtures:

| File | What to change |
| --- | --- |
| `frontend/src/app/router.test.ts` | root / unknown path → `/workbench/engineering-inputs` |
| `frontend/tests/workbench.test.ts` | default route; nav must contain 工程输入 and must **not** contain 基本信息; leftover-badge test must `push('/workbench/project')` before asserting; narrow-screen nav click map drops 基本信息 (6 links, include 工程输入) |

`beforeEach` helpers that `push('/workbench/project')` only to get a mounted
workbench may keep doing so **or** push engineering-inputs. The leftover
label test must visit `/workbench/project` explicitly.

## 4. Exclusive allowlist

```text
POST_V09_P1_FILE_ALLOWLIST
docs/tasks/POST_V09-P1-hide-planning-run-nav-contract.md
backend/tests/architecture/test_post_v09_p1_hide_planning_run_nav_contract.py
frontend/src/features/workbench/WorkbenchLayout.vue
frontend/src/app/router.ts
frontend/src/app/router.test.ts
frontend/src/app/AppShell.vue
frontend/src/features/investment/components/InvestmentPage.vue
frontend/tests/workbench.test.ts
frontend/src/features/workbench/architecture/test_post_v09_p1_hide_planning_run_nav.test.ts
```

`ProjectPage.vue` is **not** on the allowlist. Leave leftover copy alone.

Forbidden (not exhaustive): `zone_planning.py`, cooling/equipment/power/investment
formula files, `EngineeringInputBundleForm`, `CalculationsPage`,
`ZoneResultsTable`, report assembler/schema/templates, Alembic, samples,
live Aily, P2/P3 files.

## 5. Acceptance criteria

```text
P1-AC-01 Nav has six operator links; first is 工程输入; 基本信息 absent
P1-AC-02 `/` and `/workbench` land on `/workbench/engineering-inputs`
P1-AC-03 `/workbench/project` still renders leftover badge + planning-run note
P1-AC-04 Investment empty copy points at 工程输入, not 基本信息
P1-AC-05 Vue file-scan: no engineering formulas added
P1-AC-06 Architecture allowlist vs origin/main on this branch
```

## 6. Not in P1

- Project picker / rename / multi-project
- Deleting `planning-run` API or `ProjectPage`
- Auto-running production scheme-runs
- Five-stage result tables (P2)
- Report KEY / formula projection (P3)
- Merge, tag, Release

## 7. Rollback

Revert this PR. Nav and default landing return to 基本信息.

## Revision history

| Rev | Date | Notes |
| --- | --- | --- |
| R1 | 2026-08-27 | Charles 可以派发: hide leftover 基本信息 |
