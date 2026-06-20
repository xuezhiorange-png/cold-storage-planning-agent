# CODEX Tasks

This file decomposes the roadmap into Codex-sized tasks. Complete validation and
open a PR for each task before starting the next one.

## Task 0: Repository audit and governance

- Included: baseline preservation, sensitive-file review, audit docs, roadmap,
  AGENTS rules, CI baseline, PR template.
- Not included: business logic refactors, calculator formula changes, database
  redesign.

## Task 1: Runtime and quality baseline

- Included: align runtime configuration, clean backend formatting drift, remove
  import-time singletons where safe, tighten current tests.
- Not included: new business features, new planning formulas.

## Task 2: Project and immutable version workflow

- Included: project/version workflow hardening, approval locks, persistence
  cleanup, API/application split for version actions.
- Not included: coefficient governance, new calculations.

## Task 3: Coefficient registry

- Included: persistent coefficient registry, source metadata, review state,
  admin/update path, migration support.
- Not included: new cooling-load formulas or scheme generation changes.

## Task 4: Throughput, inventory, storage, precooling, and area calculations

- Included: deterministic calculator boundaries, validated input contracts,
  formula/source metadata, unit tests.
- Not included: refrigeration load sizing and equipment selection.

## Task 5: Cooling load and equipment capability

- Included: deterministic cooling-load/equipment calculators, result metadata,
  tests, API/application wiring.
- Not included: knowledge retrieval and report generation.

## Task 6: Scheme generation and comparison

- Included: deterministic scheme generation, score weighting, comparison output,
  persistence where needed.
- Not included: agent chat workflow.

## Task 7: Knowledge base

- Included: upload metadata, parsing, chunking, persistence, hybrid retrieval,
  fake embeddings.
- Not included: OCR service rollout without explicit approval.

## Task 8: Planning Agent

- Included: session model, tool orchestration, confirmation flow, fake/default
  model gateways, authorization boundaries.
- Not included: direct engineering math inside prompts.

## Task 9: Word and Excel reports

- Included: report versions, persisted output metadata, download endpoints,
  template governance.
- Not included: recomputing formulas inside templates.

## Task 10: Frontend workbench

- Included: split monolithic UI into feature modules, typed API layer, compact
  workbench flows, audit/report views.
- Not included: speculative future screens.

## Task 11: Evaluation and pilot readiness

- Included: fixture projects, acceptance scripts, result consistency checks,
  sample documents.
- Not included: production infra hardening.

## Task 12: Productionization and security

- Included: secrets handling, deployment hardening, environment separation, CI
  expansion, observability.
- Not included: unrelated feature expansion.
