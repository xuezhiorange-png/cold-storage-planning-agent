# Task 10 — Frontend Planning Workbench

Status: implemented; awaiting engineering review

Issue: #18

Branch: `codex/task-10-frontend-workbench`

Base: `main@253feb38449611959bfce7c63504570fb8aa5bd2`

## 1. Goal

Modularize the current Vue workbench into explicit feature-owned modules while preserving backend-owned engineering behavior, existing workflow outcomes, and the compact desktop planning experience.

The frontend is an orchestration and presentation layer. It must not reproduce engineering formulas, scoring rules, report localization logic, artifact state transitions, or authorization decisions already owned by backend services.

## 2. Current-state problem

`frontend/src/App.vue` currently combines:

- backend response interfaces;
- demo fixtures and default planning data;
- workflow navigation;
- API orchestration;
- presentation formatting;
- project, calculation, scheme, investment, power, report, and agent views.

This concentration makes API changes, test isolation, stale-request handling, and report workflow integration unnecessarily risky.

## 3. Target architecture

```text
frontend/src/
├── app/
│   ├── AppShell.vue
│   ├── router.ts
│   └── navigation.ts
├── api/
│   ├── httpClient.ts
│   ├── errors.ts
│   └── contracts/
├── features/
│   ├── project/
│   ├── calculations/
│   ├── schemes/
│   ├── investment/
│   ├── power/
│   ├── reports/
│   └── agent/
├── shared/
│   ├── components/
│   ├── composables/
│   ├── formatters/
│   └── types/
└── App.vue
```

The exact filenames may evolve, but the ownership boundaries are mandatory.

## 4. Application shell contract

`App.vue` must become a thin root component. It may own only:

- application shell composition;
- top-level router host;
- global navigation container;
- global error boundary or notification host;
- agent entry point when globally available.

It must not own:

- feature response interfaces;
- demo result tables;
- engineering result formatting;
- direct feature API calls;
- report export state;
- scheme recommendation logic;
- feature-specific loading or error state.

## 5. Feature ownership

### 5.1 Project

Owns project overview, factory metadata, design input forms, validation display, dirty state, and request mapping.

### 5.2 Calculations

Owns planning-run execution state, zone results, calculation summaries, backend blocker display, and calculation result tables.

### 5.3 Schemes

Owns scheme list, recommendation display, feasibility state, comparison tables, weight-set metadata, and blocked/unavailable states.

### 5.4 Investment

Owns investment breakdown tables and deterministic display formatting of backend-provided monetary values.

### 5.5 Power

Owns equipment power rows, summary rows, installed/demand power display, and review flags.

### 5.6 Reports

Owns report/revision status, locale selection, output format, render mode, export request state, artifact list, completed download, and backend error rendering.

Supported report UI inputs must map to backend contracts:

- locale: `zh-CN` or `en-US`;
- format: DOCX or PDF;
- mode: draft or formal, subject to backend eligibility rules;
- template version only when exposed by backend APIs.

The UI must not translate report content, construct report artifacts, or bypass formal-export rules.

### 5.7 Agent

Owns conversation display, tool proposal state, confirmation UI, authorization feedback, and tool-result presentation. It must not execute engineering calculations locally.

## 6. Typed API layer

All HTTP calls must use a shared typed transport abstraction.

Required behavior:

- configurable API base URL;
- JSON request/response handling;
- binary artifact download handling;
- normalized transport and backend error models;
- abort/cancellation support where multiple requests may race;
- no silent fallback from backend errors to demo data;
- typed contracts outside Vue components;
- explicit payload-to-view-model mapping when presentation shaping is required.

Backend snake_case fields may remain in generated/raw API contracts. Feature view models may use frontend conventions only through explicit mappers.

## 7. State ownership

Use local component or composable state by default.

Pinia is allowed only for state that must:

- survive route changes;
- be shared by unrelated feature trees;
- coordinate a multi-view workflow;
- preserve a selected project/version/session across views.

Do not create a single global store containing every feature.

## 8. Concurrency and stale-response rules

For user-triggered requests:

- a newer request must not be overwritten by an older response;
- cancelled requests must not surface as user-facing failures;
- repeated export submissions must respect backend idempotency behavior;
- route changes must not update unmounted feature state;
- loading state must terminate on success, handled error, or cancellation.

## 9. View-state contract

Every data-owning feature must define deterministic states for:

- initial;
- loading;
- success with data;
- success with empty data;
- validation failure;
- authorization failure;
- backend conflict or blocked operation;
- recoverable transport failure;
- non-recoverable failure.

Retries must repeat only safe operations. Write operations must not be automatically retried unless the backend idempotency contract makes this explicit.

## 10. Accessibility and responsive behavior

- Form controls require labels and accessible validation messages.
- Tables require semantic headers.
- Dialogs and drawers require keyboard focus management.
- Status changes should be exposed to assistive technology where practical.
- Keyboard focus must remain visible.
- Desktop remains the primary engineering layout.
- Core project, result, scheme, and report workflows must remain usable on narrower screens without hiding critical actions.

## 11. Non-goals

- No client-side engineering formulas.
- No client-side scheme scoring or recommendation.
- No report content translation or string replacement.
- No speculative screens unsupported by backend capabilities.
- No broad visual rebrand.
- No replacement of Vue, Element Plus, ECharts, Pinia, or Vue Router.
- No Task 11 evaluation fixtures.
- No Task 12 deployment or security hardening.
- No implementation of Issue #17 unless a direct integration blocker is proven.

## 12. Required tests

At minimum:

1. application shell and route navigation;
2. API transport success and normalized error handling;
3. request cancellation and stale-response protection;
4. project input validation and payload mapping;
5. calculation summary and zone result rendering;
6. scheme recommendation, infeasible, and unavailable states;
7. investment and power table rendering;
8. report locale/format/mode request mapping;
9. report pending, completed, failed, and blocked states;
10. artifact download success and integrity/error response handling;
11. agent confirmation and authorization states;
12. critical narrow-screen workflow smoke tests.

Tests must assert user-visible outcomes and request contracts, not internal implementation details alone.

## 13. Quality gates

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm run test
npm run build
```

Repository CI must keep these jobs green:

- `frontend`;
- `backend-sqlite`;
- `backend-postgresql`;
- `compose-config`.

## 14. Acceptance criteria

- `App.vue` is a thin shell.
- Feature-owned fixtures and response interfaces are removed from `App.vue`.
- Major workflows have explicit feature-module ownership.
- API contracts and transport are centralized and typed.
- No engineering formula is duplicated in the frontend.
- Existing backend-driven planning outcomes remain unchanged.
- Task 9 report locale/export/artifact workflows are usable in the UI.
- Loading, empty, blocked, authorization, retry, and stale-response states are covered by tests.
- Frontend lint, typecheck, tests, and build pass.
- All repository CI jobs pass on the current PR Head.

## 15. Delivery rules

- Keep the PR Draft during implementation.
- Do not merge or enable auto-merge before final verification.
- Avoid unrelated backend changes.
- Any required backend change must be minimal, separately identified in the PR, and covered by backend tests.
- Do not begin Task 11 until Task 10 is merged and closed.