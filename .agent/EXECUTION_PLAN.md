# 冷库规划设计 Agent V1 Execution Plan

## Repository Baseline

- Checked Git status: repository has no commits on `main`.
- Checked `.codegraph/`: absent, so CodeGraph is skipped.
- Existing application files: none before this implementation.
- Git branch creation was attempted but `.git` is read-restricted in the sandbox, so implementation continues in the current worktree.

## Milestones

| Milestone | Scope | Status |
| --- | --- | --- |
| 0 | Engineering scaffold, docs, health checks, CI, Makefile | **Implemented** |
| 1 | Domain models, ORM, Alembic, units, coefficient registry, audit | Implemented baseline |
| 2 | Deterministic calculators | Implemented baseline |
| 3 | Project and calculation API | Implemented baseline |
| 4 | Deterministic schemes | Implemented baseline |
| 5 | Knowledge ingestion and retrieval | Implemented baseline |
| 6 | Planning Agent with fake gateways | Implemented baseline |
| 7 | Word and Excel reports | Implemented baseline |
| 8 | Vue workbench | Implemented baseline |
| 9 | Seed, demo, acceptance | Implemented baseline |

## Architecture Review Log

- Domain modules do not import FastAPI, SQLAlchemy, Redis, or model SDKs.
- Calculation modules are pure and do not access persistence, files, HTTP, Redis, environment variables, or model SDKs.
- Agent service uses explicit gateway contracts and does not access database sessions or ORM models.
- Demo coefficients are marked unverified and require review.
- Backend verification: pytest, ruff, ruff format check, and mypy pass.
- Frontend verification: Vitest, vue-tsc, ESLint, and production build pass.
- Known issue: npm audit reports transitive vulnerabilities; tracked as TD-004.
- V1.1 update: project/version/input/calculation/audit API flow now uses SQLAlchemy-backed persistence with integration coverage.
- V1.2 update: added a production-input-driven planning run. Backend now exposes a
  project-version `/planning-run` endpoint that saves inputs, runs zone planning and
  investment estimation, records both calculation snapshots, and returns a combined
  summary. Frontend now lets users change daily throughput and related planning
  parameters, then refreshes total area, position count, zone rows, and investment
  rows from the backend response.
- V1.3 update: split finished-goods inventory days from packaging-material
  inventory days, made packaging storage area respond to inventory days, and added
  a demo power-configuration table with installed power, demand factor, and
  estimated demand power. Demo overview now includes the power module and total
  installed power.
- V1.4 update: replaced the coarse power-configuration table with a reference
  equipment-detail table modeled after the provided processing-factory power
  parameter sheet. The response now includes equipment rows with sequence, name,
  area, quantity, defrost power, defrost total power, running power, total power,
  plus summary rows for defrost, running equipment, refrigeration total,
  production equipment total, and grand total.
- V1.5 update: corrected the power-configuration baseline against
  `/Users/charles/Desktop/副本元谋冷库设备.xlsx`, using the workbook's `莱富康`
  sheet as the source. Default 25 t/day values now match the Excel rows and
  formulas: defrost simultaneous power 249.09 kW, running power 933.98 kW,
  refrigeration total 1183.07 kW, production equipment total 284.40 kW, and
  grand total 1467.47 kW.
- V1.6 update: filled every left-sidebar workbench page with structured sample
  content so the prototype no longer falls back to placeholder pages. Added
  sample matrices for parameter completeness, schemes, scheme comparison,
  knowledge sources, report queue, version history, and audit records, and
  tightened the frontend layout for wide equipment and planning tables.
- V1.7 update: made core cold-room planning assumptions configurable from the
  deterministic calculator and demo planning API. The zone planner now accepts
  raw holding hours, storage position capacity, secondary-fruit ratio,
  frozen-fruit ratio, frozen storage days, and precooling position capacity,
  returns the applied planning parameter snapshot, and the Vue parameter form
  sends these values when regenerating the regional plan.
- V1.8 update: replaced the demo area-planning formulas with the user-confirmed
  processing-factory logic. Office, changing room, and coating room now use fixed
  areas; primary and secondary precooling use pallet weight, cooldown time, and
  daily working hours; raw fruit, finished goods, and frozen fruit use storage
  ratios/days and pallet weights; secondary fruit area is derived from frozen
  room area; sorting/packing uses labor productivity and packing table spacing;
  packaging storage uses the provided Excel formula split into main and auxiliary
  packaging storage days. The default 25 t/day demo now yields 1785.57 m2 and
  341 positions before later engineering refinements.
- V1.9 update: precooling pallet positions now round up to the smallest valid
  multiple of either 6 or 8 after the theoretical position count is calculated.
  The default 25 t/day demo rounds primary precooling from 19 to 24 positions,
  leaves secondary precooling at 8 positions, and updates the default total to
  1813.57 m2 and 346 positions.
- V1.10 update: removed the visible peak-factor input from the Vue workbench and
  fixed the planning request to use a neutral factor internally. Improved mobile
  layout by turning the sidebar into a sticky horizontal navigation bar, reducing
  mobile spacing, and preserving horizontal scrolling for wide planning and
  equipment tables.

- V1.11 update: compacted the design-parameter form layout. The form now auto-fits multiple columns on desktop, uses two compact columns on normal mobile widths, and only falls back to one column on very narrow screens. Verified with frontend unit tests, lint, typecheck, and production build.
- V1.12 update: replaced the design-parameter form's fixed column grid with a
  content-sized wrap layout. Short numeric fields now use narrower widths, long
  labels get wider fields, units sit beside labels instead of consuming another
  row, and summary chips fill the remaining row width. Verified with frontend
  unit tests, lint, typecheck, and production build.
- V1.13 update: removed the peak-factor concept from the active factory planning
  workflow. The design-parameter catalog, Vue planning request, demo planning
  defaults, project input validation, planning agent extraction allowlist,
  throughput/inventory formulas, zone-planning formula references, and demo
  overview no longer expose or depend on peak factor. Added frontend regression
  coverage to ensure the parameter is not displayed or submitted.
- V1.14 update: fixed mobile rendering by adding the missing viewport metadata
  and increasing mobile touch/readability styles. Mobile now uses 16px body text,
  larger page titles, 44px inputs and buttons, larger parameter labels, readable
  status chips, and larger table/card text. Verified with frontend unit tests,
  lint, typecheck, and production build.
- V1.15 update: replaced the mobile horizontal sidebar with a left-top menu
  button and slide-out drawer. The drawer has a backdrop, close action, and
  closes automatically after choosing a page, while the desktop sidebar remains
  unchanged. Added regression coverage for opening the mobile menu and selecting
  a page from the drawer.
- V1.16 update: renamed the product header to "冷库规划设计助手V1" and moved it to
  the global top bar. Removed the product title from the menu drawer/sidebar so
  the menu only contains navigation actions. Verified with frontend unit tests,
  lint, typecheck, and production build.
- V1.17 update: changed the project overview summary to the planting-base
  business narrative: factory name, covered planting area, yield basis in tons
  per thousand mu, derived peak yield, and main varieties. Synced the demo
  overview API fields and updated frontend/backend tests.
- V1.18 update: made the project overview editable for the required fields:
  factory name, planting area, and planted varieties. Peak yield remains derived
  from planting area at 20 tons per thousand mu, and the overview narrative
  updates immediately when these fields change. Added frontend regression
  coverage for editing the overview inputs.
- V1.19 update: simplified the project overview page to only show the three
  required inputs: factory name, planting area, and planted varieties. Removed
  the generated narrative and derived summary chips from the visible UI, and kept
  the three inputs aligned in one row on desktop.
- V1.20 update: added a direct main workflow navigation bar above the page
  content: basic information, design parameters, calculation results, scheme
  comparison, investment/power, and report output. The full drawer menu remains
  available for secondary pages, but the primary workflow no longer requires
  opening the menu. Also compressed the project overview fields into one-line
  label/input rows.
- V1.21 update: removed the redundant content header that repeated the demo
  project name, active page title, missing/review counts, and concept-design
  badge. The page now goes directly from the global header to the workflow
  navigation and active content.
- V1.22 update: compacted the overall workbench layout across pages by reducing
  global work-area padding, workflow-nav spacing, form gaps, table row heights,
  summary/card padding, module-card minimum heights, and agent-panel spacing.
  Mobile keeps readable text and touch targets while trimming excess vertical
  whitespace.
- V1.23 update: merged the design-parameter form into the basic-information
  page, removed the module summary cards below basic information, removed the
  design-parameter catalog rows, and removed visible "用户确认值" source labels
  from the active UI. Basic information now leads directly into editable design
  parameters.
- V1.24 update: removed the standalone design-parameters module from both the
  main workflow and drawer menu because those inputs now live under basic
  information. Reworked the calculation-results page into a compact table with
  explicit headers instead of separate loose cards.
- V1.25 update: removed the menu button/drawer entirely and kept navigation on
  the visible workflow bar only. Replaced the calculation-results card-like
  layout with a real compact HTML table so results read as rows and columns.
- V1.26 update: changed the calculation-results page from generic calculator
  summaries to the cold-room/function-area area table. It now lists each area,
  temperature band, handled throughput, design storage mass, pallet positions,
  estimated area, and a footer total for total positions and total area.
- V1.27 update: fixed LAN development access by starting Vite and FastAPI on
  0.0.0.0, and persisted Vite's dev server host setting in vite.config.ts.
  Verified the LAN frontend URL and the proxied demo planning API both return
  successfully from the host machine.
- V1.28 update: simplified the calculation-results area table by removing
  temperature band and handled-throughput columns. The visible result table now
  focuses on zone name, design storage mass, pallet positions, estimated area,
  and the total area footer.
- V1.29 update: reordered the calculation-results table so estimated area is
  the second column immediately after the zone name. The footer now aligns total
  area under the area column and total pallet positions under the position
  column.
- V1.30 update: compressed the calculation-results table for mobile by removing
  the fixed 780px minimum width, switching to fixed table layout, reducing cell
  padding and font size, and adding a regression test to keep the table from
  forcing horizontal scrolling.
- V1.31 update: converted the power-configuration view from block/grid rows to
  a compact HTML table with sequence, equipment name, area, quantity, running
  power, total power, and summary footer rows. Removed the old 980px power-row
  minimum width so the page follows the same mobile table strategy as
  calculation results.
- V1.32 update: renamed the main workflow entry from investment/power to power
  estimation ("用电估算") and added an investment-estimation block to that page.
  The page now contains both a compact investment estimate table and the compact
  power configuration table.
- V1.33 update: split investment estimation into its own top workflow step.
  The main workflow is now basic information, calculation results, scheme
  comparison, investment estimation, power estimation, and report output. The
  investment table was removed from the power-estimation page and remains a
  standalone compact table under investment estimation.
- V1.34 update: changed axial-fan power configuration from a fixed reference
  quantity to the planning rule `(primary precooling positions + secondary
  precooling positions) * 4`. Updated API planning runs, demo overview, frontend
  default power rows, and tests so the default 24+8 precooling positions produce
  128 axial fans and 70.40 kW axial-fan total power.
- V1.35 update: changed investment-estimation breakdown to the user-provided
  five categories: civil/steel structure, cold-room refrigeration equipment,
  high/low-voltage distribution, dormitory/living area, and monitoring/opening
  supplies. Existing demo amounts are temporarily regrouped into the new
  categories while preserving the total investment until detailed unit-cost
  logic is provided.
- V1.36 update: replaced regrouped investment placeholders with deterministic
  formulas: civil/steel structure = (total area + 1000) * 900 CNY/m2,
  refrigeration = total area * 1400 CNY/m2, high/low-voltage distribution =
  total power * 650 CNY/kW, monitoring/opening supplies = fixed 200,000 CNY.
  Dormitory/living area remains a visible line item with 0 until its independent
  formula is specified; the 1000 m2 allowance is included in civil/steel
  structure.
- V1.37 update: compacted the basic-information fields so factory name,
  planting area, and planted varieties stay in three columns on mobile and
  desktop. Reduced label and input font sizes, input height, and field gaps for
  the overview block.
- V1.38 update: compacted the full design-parameter form under basic
  information. Replaced the flex row layout with an auto-fit CSS grid, removed
  mobile overrides that forced wide 142px controls and 16px inputs, and kept
  labels/inputs small so multiple parameters fit per row.
- V1.39 update: changed the workbench visual system to a deep-blue B2B tool
  style, moved the AI assistant from a persistent right-side panel into a
  single top-bar icon popover, and renamed the planting-area field to planting
  mu count ("定植亩数") without showing a separate mu unit suffix.
- V1.40 update: preserved the current cold-storage project as a clean GitHub
  baseline on `main`, added a repository audit/governance branch, hardened
  `.gitignore`, and introduced audit, roadmap, ADR, CI, contribution, and task
  governance documents without changing business logic.
- V1.41 update (Task 0 completion): applied `ruff format` to
  `demo_overview.py` and `investment.py` to fix CI formatting drift.
  All local quality checks now pass. Docker Compose validation passes on
  GitHub Actions. No business logic or calculation changes.
- V1.42 update (Task 1): aligned runtime configuration with dual
  SQLite/PostgreSQL modes, removed import-time singletons from
  `dependencies.py`, added FastAPI lifespan for engine lifecycle
  management, extracted planning orchestration from `bootstrap/app.py` to
  `modules/planning/application/service.py`, added 35 new tests
  (settings, lifecycle, orchestration, architecture), created ADR-008 and
  ADR-009.
- V1.43 update (Task 2): implemented immutable project version workflow
  with full state machine (draft → generated → under_review → reviewed →
  approved → archived), added version snapshots (input, calculation,
  assumption), parent_version_id for version lineage, immutability rules
  for approved/archived versions, 62 new tests (state machine, versioning,
  API integration), created ADR-010.
