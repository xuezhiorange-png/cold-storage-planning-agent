# V0.9 P4 — Draft vs Formal Export Contract

**Status:** Implementation R1 — operator-visible draft export independent of review  
**Authority:** `docs/tasks/V0_9-P0-version-contract.md` §3.5, §7.5, V09-E7/E8  
**ADR:** `docs/architecture/ADR-029-v09-operator-key-and-workbench-recut.md` §4  
**Parent:** V0.9 P0 #213  
**Previous release:** `v0.8.0`  
**Target branch:** `cursor/v09-p4-draft-formal-export-6c68`

This package makes **draft report export** reachable without review. Formal
export stays gated to approved/archived. Frontend only. It does not implement
Feishu, production RBAC, or backend status-machine changes.

## 0. Contract identity and governance

```text
TASK=V09_P4_DRAFT_FORMAL_EXPORT_R1
PARENT_ISSUE=213
PARENT_CONTRACT=docs/tasks/V0_9-P0-version-contract.md
GOVERNANCE_OWNER=V0.9
BASE_MAIN_SHA=d8474855ee0815552865ea36d98631a33111d674
BASE_TREE=60f9263053b6ae396d25c30a043b8fd8a258f1ed
PREVIOUS_RELEASE=v0.8.0
TARGET_BRANCH=cursor/v09-p4-draft-formal-export-6c68
TARGET_FILE=docs/tasks/V0_9-P4-draft-formal-export-contract.md
TARGET_PR_STATE=DRAFT

V09_P4_IMPLEMENTATION_AUTHORIZED=YES
V09_P1_IMPLEMENTATION_AUTHORIZED=NO
V09_P2_IMPLEMENTATION_AUTHORIZED=NO
V09_P3_IMPLEMENTATION_AUTHORIZED=NO
V09_P5_IMPLEMENTATION_AUTHORIZED=NO
V09_P6_IMPLEMENTATION_AUTHORIZED=NO
V09_P7_IMPLEMENTATION_AUTHORIZED=NO
DRAFT_EXPORT_INDEPENDENT_OF_REVIEW=YES
FORMAL_EXPORT_REQUIRES_APPROVED_OR_ARCHIVED=YES
BROWSER_MARK_REVIEWED_IS_NOT_PRODUCTION_RBAC=YES
FEISHU_REVIEW_IMPLEMENTATION=NO
PRODUCTION_RBAC_CLAIM=NO
AILY_LIVE_IMPLEMENTATION=NO
FORMULA_RECUT_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 1. Objective

On the reports workbench, draft render/download must remain available when:

- `formalExportEligible=false`
- workflow / panel surfaces `FORMAL_EXPORT_BLOCKED` or equivalent formal
  ineligibility (`FORMAL_REPORT_NOT_APPROVED`, not approved/archived)
- browser `mark_reviewed` fail-closes (actor is `system`; trusted TestClient
  seam only — not production RBAC)

Formal export remains a separate, gated action. Default export mode stays
`draft`. Existing draft export API usage is unchanged: `mode=draft` against
backend `DRAFT_EXPORT_STATUSES`. No new backend routes.

Locked policy (P0 §3.5 / V09-E7 / V09-E8):

```text
DRAFT_EXPORT_INDEPENDENT_OF_REVIEW=YES
FORMAL_EXPORT_REQUIRES_APPROVED_OR_ARCHIVED=YES
BROWSER_MARK_REVIEWED_IS_NOT_PRODUCTION_RBAC=YES
FEISHU_REVIEW_IMPLEMENTATION=NO
```

## 2. Required operator-visible behavior

1. Separate **草稿导出** and **正式导出** in copy and controls. Default mode
   remains `draft`.
2. Formal blockers MUST NOT disable draft render or draft download.
3. Formal blockers MUST NOT be presented as the only / global export error
   while the operator is on the draft path.
4. `displayedBlockers` MUST NOT map `formalExportBlockers` into the generic
   panel banner whenever formal is ineligible. Draft path ignores formal
   eligibility.
5. Formal controls MAY stay disabled until eligible. Copy MUST state:
   **正式导出需要已批准/归档，草稿导出不需要审核.**
6. Review action errors (including browser `mark_reviewed` fail-closed) stay
   in the review error slot. They MUST NOT become the default “cannot export”
   banner.

Backend authority (read-only for this package; do not edit):

| Set | Statuses | UI consequence |
| --- | --- | --- |
| `DRAFT_EXPORT_STATUSES` | `draft`, `generated`, `under_review`, `reviewed` | Draft render/download stays reachable |
| `FORMAL_EXPORT_STATUSES` | `approved`, `archived` only | Formal control disabled until eligible; do not weaken |

## 3. P4 exclusive allowlist

```text
V09_P4_FILE_ALLOWLIST
docs/tasks/V0_9-P4-draft-formal-export-contract.md
frontend/src/features/reports/components/ReportsPage.vue
frontend/src/features/reports/components/ReportExportPanel.vue
frontend/src/features/reports/composables/useReportExport.ts
frontend/tests/features/reports/useReportWorkflow.test.ts
frontend/tests/features/reports/errorMessages.test.ts
```

Natural Vue coverage for `ReportExportPanel.vue` may also live at
`frontend/src/features/reports/components/ReportExportPanel.test.ts`
(co-located; not a backend or P5 file).

## 4. Hard non-goals

```text
FEISHU_REVIEW_IMPLEMENTATION=NO
PRODUCTION_RBAC_CLAIM=NO
AILY_LIVE_IMPLEMENTATION=NO
FORMULA_RECUT_AUTHORIZED=NO
BACKEND_FORMAL_EXPORT_STATUSES_MUTATION=NO
ZONE_PLANNING_PY_EDIT=NO
WORKFLOW_GUIDANCE_PANEL_EDIT=NO
V05_V06_V07_V08_TEST_ASSERTION_MUTATION=NO
NEW_BACKEND_EXPORT_ROUTES=NO
```

P4 must not:

- implement Feishu review or claim production RBAC
- edit `backend/**` (including `FORMAL_EXPORT_STATUSES` / `zone_planning.py`)
- edit `WorkflowGuidancePanel.vue` (P5 owns workbench banners)
- weaken formal export to statuses other than approved/archived
- make `mark_reviewed` look like a browser production role
- invent new backend export routes
- embed engineering formulas in Vue or prompts

## 5. Implementation notes (frontend)

- `createDefaultExportForm().mode` remains `'draft'`.
- Draft render calls existing `POST .../render` with `mode: 'draft'`.
- Formal render still uses `mode: 'formal'` and may stay client-disabled while
  `formalExportEligible` is false. Backend revalidates on render/download.
- `selectDisplayedExportBlockers` (draft mode) returns only non-formal action
  blockers. It never copies `formalExportBlockers` onto the draft path.
- Formal ineligibility copy is labeled as **formal-only** and states that it
  does not block draft export.
- `runReviewAction` must not dump review blockers into the export blocker list.

## 6. Acceptance criteria

```text
DRAFT_EXPORT_INDEPENDENT_OF_REVIEW=PASS
DEFAULT_EXPORT_MODE_DRAFT=PASS
DRAFT_CONTROLS_ENABLED_WHEN_FORMAL_INELIGIBLE=PASS
FORMAL_OPTION_DISABLED_UNTIL_ELIGIBLE=PASS
FORMAL_BLOCKERS_NOT_GLOBAL_DRAFT_ERROR=PASS
NO_FALSE_FORMAL_EXPORT_BLOCKED_ON_DRAFT_PATH=PASS
POLICY_COPY_APPROVED_OR_ARCHIVED_AND_DRAFT_NEEDS_NO_REVIEW=PASS
FORMAL_EXPORT_STATUSES_UNCHANGED=PASS
FEISHU_REVIEW_IMPLEMENTATION=NO
PRODUCTION_RBAC_CLAIM=NO
AILY_LIVE_IMPLEMENTATION=NO
BACKEND_UNCHANGED=PASS
WORKFLOW_GUIDANCE_PANEL_UNCHANGED=PASS
FRONTEND_VITEST_P4_SURFACE_PASS=PASS
DRAFT=YES
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
```

Authoritative frontend test surface:

```text
frontend/tests/features/reports/useReportWorkflow.test.ts
frontend/tests/features/reports/errorMessages.test.ts
frontend/src/features/reports/components/ReportExportPanel.test.ts
```

## 7. Revision history

| Rev | Date | Change |
| --- | --- | --- |
| R1 | 2026-08-27 | Initial P4 draft/formal export split at `d847485` / P0 #213 |
