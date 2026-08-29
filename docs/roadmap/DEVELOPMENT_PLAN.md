# Development Plan

> **V0.9 P0 freeze (2026-08-27, `main@0dc8de5b3c711aaa662b0bbda3988def037fda3b`,
> release `v0.8.0`):** Tasks 0–12 below remain the original roadmap register.
> V0.5 five-stage workbench is **complete** at tag `v0.5.0`. V0.6 report
> assembly is **complete** at tag `v0.6.0`. V0.7 trust loop is **complete**
> at tag `v0.7.0` (`docs/tasks/V0_7-P0-trust-loop-contract.md`). V0.8
> operator-minimal process input is **complete** at tag `v0.8.0`
> (`docs/tasks/V0_8-P0-operator-minimal-input-contract.md`). **Active
> umbrella:** V0.9 P0 contract (`docs/tasks/V0_9-P0-version-contract.md`)
> plus overall plan (`docs/tasks/V0_9-version-plan.md`). V0.9 operator
> workbench is **complete** at `v1.0.0`. **V1.1 豆包工作伙伴 inbound connector
> is complete at `v1.1.0`.** Later umbrellas (outbound live Aily session,
> cooling/equipment formula recut) stay unauthorized until Charles dispatches.

## Task 0: Local Baseline, Repository Audit, And Governance

- Goal: preserve the current local project safely and establish audit/governance artifacts.
- Scope: baseline push, sensitive review, audit docs, roadmap, AGENTS rules, CI baseline, PR template.
- Non-scope: business logic refactors, calculator rewrites, database redesign.
- Inputs: current local repository snapshot and GitHub target repository.
- Deliverables: baseline commit/tag, governance branch, audit docs, governance files.
- Database changes: none.
- Tests: repository/tooling checks and current runnable validation commands.
- Acceptance: baseline exists on `main`, governance branch exists, draft PR is open.
- Risks: existing history contamination, wrong remote, sensitive file leakage.
- Rollback: reset remote branch to baseline tag or close governance PR; local preservation branch remains.
- Recommended branch name: `codex/task-0-repository-audit`
- Recommended PR title: `Task 0: Audit and standardize existing cold-storage project`

## Task 1: Existing System Runnability And Quality Baseline

- Goal: align current runtime behavior, bootstrap boundaries, and quality gates with the actual repository state.
- Scope: runtime config cleanup, formatting fixes, startup wiring cleanup, CI truthfulness.
- Non-scope: new business calculations and feature expansion.
- Inputs: Task 0 audit findings and validation baseline.
- Deliverables: clean quality gates, documented environment selection, thinner bootstrap seams.
- Database changes: possible config/migration wiring only, no schema redesign.
- Tests: pytest, ruff, mypy, frontend quality, migration smoke checks.
- Acceptance: validation baseline passes without known formatting drift; runtime docs match implementation.
- Risks: environment-specific regressions when untangling global singletons.
- Rollback: revert the Task 1 PR and keep baseline tag untouched.
- Recommended branch name: `codex/task-1-quality-baseline`
- Recommended PR title: `Task 1: Stabilize current runtime and quality baseline`

## Task 2: Projects And Immutable Versions

- Goal: harden project/version lifecycle and approval lock behavior.
- Scope: application services, persistence cleanup, response schema shaping, version immutability rules.
- Non-scope: coefficient governance and new engineering formulas.
- Inputs: existing project/version ORM and API endpoints.
- Deliverables: robust version workflow with explicit approved-lock behavior.
- Database changes: additive schema changes if needed for version metadata.
- Tests: unit, integration, approval-lock regression tests.
- Acceptance: approved versions cannot be modified and version APIs are consistently typed.
- Risks: accidental change to existing project/version behavior.
- Rollback: revert PR and restore previous API behavior from baseline tag.
- Recommended branch name: `codex/task-2-project-versions`
- Recommended PR title: `Task 2: Harden project and immutable version workflow`

## Task 3: Engineering Coefficient Registry

- Goal: move demo coefficients into a structured, reviewable registry.
- Scope: persistence model, service APIs, migrations, review metadata, source/version tracking.
- Non-scope: new cooling-load or equipment formulas.
- Inputs: embedded coefficients in calculation modules.
- Deliverables: coefficient registry, retrieval API/service, audit trail.
- Database changes: new coefficient tables and migrations.
- Tests: registry CRUD, source metadata, review-flag propagation.
- Acceptance: calculators can reference registered coefficients with source and review metadata.
- Risks: coefficient drift during extraction from embedded constants.
- Rollback: revert PR and keep embedded coefficient map.
- Recommended branch name: `codex/task-3-coefficient-registry`
- Recommended PR title: `Task 3: Add coefficient registry and review metadata`

## Task 4: Throughput, Inventory, Storage, Precooling, And Area Calculations

- Goal: formalize deterministic engineering calculators and move orchestration out of routes.
- Scope: calculator contracts, input validation, service wiring, result metadata, persistence hooks.
- Non-scope: cooling load and equipment sizing.
- Inputs: current `CalculationService` and zone planning inputs.
- Deliverables: stable deterministic calculator interfaces and API/application integration.
- Database changes: none or additive result metadata only.
- Tests: calculator unit tests and endpoint/application regression tests.
- Acceptance: calculations are deterministic, typed, and route handlers stay thin.
- Risks: behavior drift if formulas are accidentally changed during extraction.
- Rollback: restore previous calculator service and keep formula outputs from baseline.
- Recommended branch name: `codex/task-4-core-calculations`
- Recommended PR title: `Task 4: Extract and stabilize core deterministic calculations`

## Task 5: Cooling Load And Equipment Capability

- Goal: isolate cooling-load and equipment capability calculations with deterministic services.
- Scope: cooling-load contracts, equipment requirement logic, metadata, persistence.
- Non-scope: scheme comparison, knowledge retrieval, UI refactor.
- Inputs: current calculator service and demo equipment assumptions.
- Deliverables: dedicated deterministic load/equipment calculation path.
- Database changes: none or additive result storage fields.
- Tests: load/equipment unit tests and result persistence coverage.
- Acceptance: cooling-load and equipment capability run outside API-route formula code.
- Risks: hidden assumptions in current helper logic.
- Rollback: revert PR and fall back to baseline helper path.
- Recommended branch name: `codex/task-5-cooling-and-equipment`
- Recommended PR title: `Task 5: Isolate cooling-load and equipment calculations`

## Task 6: Cold-Room Scheme Generation And Comparison

- Goal: formalize scheme generation and comparison as module-owned behavior.
- Scope: deterministic scheme generation, scoring, assumptions, comparison outputs.
- Non-scope: knowledge indexing and chat workflows.
- Inputs: current `SchemeService` and zone-planning outputs.
- Deliverables: explicit scheme-generation API/application path and scoring metadata.
- Database changes: optional additive persistence for scheme runs and weight sets.
- Tests: scheme generation, comparison scoring, API regression tests.
- Acceptance: scheme output is deterministic and versionable.
- Risks: implicit scoring assumptions in current sample logic.
- Rollback: revert PR and preserve sample scheme generation.
- Recommended branch name: `codex/task-6-schemes`
- Recommended PR title: `Task 6: Formalize cold-room scheme generation and comparison`

## Task 7: Professional Knowledge Base

- Goal: implement durable knowledge ingestion and retrieval.
- Scope: upload metadata, parsing, chunking, retrieval, fake embeddings, OCR boundaries.
- Non-scope: unrestricted external OCR or production search infra hardening.
- Inputs: in-memory `KnowledgeService` baseline.
- Deliverables: persisted knowledge documents and hybrid retrieval service.
- Database changes: document/chunk metadata tables and possibly vector support.
- Tests: parser, indexing, retrieval, and `requires_ocr` behavior.
- Acceptance: knowledge results are durable, searchable, and explicitly reviewed.
- Risks: document parsing variability and storage growth.
- Rollback: revert PR and keep in-memory sample search.
- Recommended branch name: `codex/task-7-knowledge-base`
- Recommended PR title: `Task 7: Build durable knowledge ingestion and retrieval`

## Task 8: Cold Storage Planning Agent

- Goal: add sessioned planning-agent workflows that orchestrate tools without doing engineering math.
- Scope: session model, message flow, tool selection, confirmation/authorization boundaries, gateway interfaces.
- Non-scope: direct DB access from agent code and direct formula execution in prompts.
- Inputs: current fake gateway and agent service baseline.
- Deliverables: session-aware agent workflow with fake/default gateways and test coverage.
- Database changes: additive agent session/message tables if needed.
- Tests: structured-output, tool selection, missing-parameter, and authorization tests.
- Acceptance: agent proposes changes and delegates calculations without fabricating engineering values.
- Risks: hidden prompt coupling and cross-layer leakage.
- Rollback: revert PR and retain fake extraction endpoint only.
- Recommended branch name: `codex/task-8-planning-agent`
- Recommended PR title: `Task 8: Add sessioned planning-agent orchestration`

## Task 9: Word And Excel Reports

- Goal: make report generation durable and auditable.
- Scope: persisted report versions, templates, download endpoints, consistency checks.
- Non-scope: recalculating formulas inside report templates.
- Inputs: current `ReportService` sample generation path.
- Deliverables: versioned report artifacts and API delivery.
- Database changes: additive report metadata tables.
- Tests: report generation, API consistency, artifact existence, and versioning tests.
- Acceptance: reports are produced from persisted results and tracked by version.
- Risks: file-system versus object-store ownership decisions.
- Rollback: revert PR and keep sample docx/xlsx generation only.
- Recommended branch name: `codex/task-9-reports`
- Recommended PR title: `Task 9: Add durable report generation and delivery`

## Task 10: Frontend Planning Workbench

- Goal: modularize the workbench and align it with backend-owned data flows.
- Scope: feature modules, typed API clients, workflow views, compact tables, agent entry, responsive layout.
- Non-scope: speculative future screens or unrelated visual redesigns.
- Inputs: current monolithic `App.vue` baseline and backend APIs.
- Deliverables: maintainable frontend feature structure and workflow-driven UI.
- Database changes: none directly.
- Tests: frontend unit/integration view tests, build, lint, typecheck.
- Acceptance: no engineering formulas are duplicated in UI components and workflow views are modular.
- Risks: regressions in current compact workbench flows.
- Rollback: revert PR and return to baseline single-component UI.
- Recommended branch name: `codex/task-10-frontend-workbench`
- Recommended PR title: `Task 10: Modularize the frontend planning workbench`

## Task 11: Evaluation And Pilot Readiness

- Goal: assemble pilot-grade sample projects, documents, and evaluation checks.
- Scope: fixtures, demo scripts, acceptance verification, result consistency checks.
- Non-scope: production deployment hardening.
- Inputs: previous task outputs and sample documents.
- Deliverables: evaluation artifacts and repeatable pilot verification.
- Database changes: optional seed data only.
- Tests: acceptance scripts and consistency checks.
- Acceptance: a defined demo/pilot scenario can be reproduced from repository artifacts.
- Risks: sample data drift from current planning logic.
- Rollback: remove new evaluation fixtures and scripts.
- Recommended branch name: `codex/task-11-evaluation`
- Recommended PR title: `Task 11: Add evaluation baseline and pilot fixtures`

## Task 12: Productionization And Security

- Goal: harden deployment, secrets, observability, and environment separation.
- Scope: environment management, deployment docs, Docker/runtime verification, CI expansion, security controls.
- Non-scope: unrelated feature changes.
- Inputs: stabilized runtime/configuration from earlier tasks.
- Deliverables: production-readiness controls and documented operating model.
- Database changes: environment/configuration related only unless explicitly needed.
- Tests: deployment smoke tests, compose checks, migration validation, security/config checks.
- Acceptance: documented production path with clear rollback and secret-handling rules.
- Risks: infra drift between local and deployment environments.
- Rollback: revert hardening changes and fall back to baseline local-only operating model.
- Recommended branch name: `codex/task-12-productionization`
- Recommended PR title: `Task 12: Harden deployment, security, and operations`
