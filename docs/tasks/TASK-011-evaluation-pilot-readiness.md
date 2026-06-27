# Task 11 — Evaluation and Pilot Readiness

Status: Phase A implemented; awaiting engineering review

Issue: #20

Branch: `codex/task-11-evaluation`

Base: `main@9a815910571281704bf1768e6be78261a26f9117`

## 1. Goal

Create a repeatable, repository-owned evaluation baseline that demonstrates the existing cold-storage planning workflow with synthetic fixtures, deterministic acceptance checks, and pilot run instructions.

Task 11 validates the system built by Tasks 0–10. It does not introduce new engineering formulas, a new orchestration runtime, production infrastructure hardening, or speculative product features.

## 2. Design principles

1. **Evaluation must execute production paths.** Fixtures may seed inputs, but expected results must be produced by existing application services and public API workflows.
2. **The manifest fails closed.** Unknown schema versions, duplicate IDs, missing files, undeclared expectations, and invalid comparison policies are errors.
3. **Expected values are reviewable contracts.** Every expected value must identify its source: invariant, approved coefficient/version, existing API contract, or reviewed golden output.
4. **Nondeterminism must be explicit.** Excluded timestamps, generated identifiers, and container metadata must be listed by JSON path with a reason.
5. **Golden updates are controlled changes.** A fixture may not silently rewrite its own expected result.
6. **Synthetic data only.** No real customer, farm, factory, personal, secret, or confidential information is permitted.
7. **Task 12 remains out of scope.** No deployment, secret, observability, or production security hardening is included.

## 3. Proposed repository layout

```text
evaluation/
├── README.md
├── manifest.schema.json
├── manifest.json
├── fixtures/
│   ├── projects/
│   │   ├── baseline-feasible.v1.json
│   │   ├── high-throughput-review.v1.json
│   │   └── invalid-blocked.v1.json
│   └── documents/
│       ├── README.md
│       └── provenance.json
├── expected/
│   ├── baseline-feasible.v1.json
│   ├── high-throughput-review.v1.json
│   ├── invalid-blocked.v1.json
│   └── multilingual-report.v1.json
├── runner/
│   ├── __init__.py
│   ├── cli.py
│   ├── manifest.py
│   ├── canonicalize.py
│   ├── execute.py
│   └── compare.py
└── runs/
    └── .gitkeep

backend/tests/evaluation/
├── test_manifest_validation.py
├── test_fixture_consistency.py
├── test_sqlite_acceptance.py
├── test_postgresql_acceptance.py
└── test_report_artifact_consistency.py

docs/pilot/
└── TASK-011-PILOT-RUNBOOK.md
```

`evaluation/runs/` is generated output and must be ignored except for `.gitkeep`. No current-run success may be inferred from stale files in this directory.

## 4. Manifest contract

The root manifest contains:

```json
{
  "schema_version": "1.0",
  "suite_id": "cold-storage-pilot-v1",
  "suite_revision": 1,
  "scenarios": []
}
```

Each scenario must include:

- `scenario_id`: stable kebab-case identifier;
- `fixture_revision`: positive integer;
- `project_input_path`: repository-relative path;
- `document_refs`: optional declared sample documents;
- `required_stages`: ordered subset of supported workflow stages;
- `expected_outcome`: `success`, `review_required`, `validation_error`, `blocked`, or `feature_unavailable`;
- `comparison_policy`: exact field assertions, decimal policies, ignored paths, and artifact checks;
- `expected_path`: repository-relative expected-result contract;
- `provenance`: source and review rationale for the expectation.

Validation rules:

- `schema_version` must be recognized exactly;
- scenario IDs must be unique;
- all referenced files must exist and remain inside `evaluation/`;
- fixture revisions must be positive integers;
- unknown keys are rejected unless the schema explicitly allows them;
- every ignored path requires a non-empty reason;
- every decimal tolerance requires a field path, scale/unit, and named rationale;
- duplicate expected field paths are rejected;
- report expectations must declare locale, format, mode, revision, and integrity checks.

## 5. Frozen scenario matrix

### 5.1 `baseline-feasible`

Purpose: exercise the normal end-to-end planning workflow.

Required stages:

1. project creation;
2. immutable project version creation;
3. input validation;
4. planning calculation;
5. zone plan;
6. scheme generation/comparison;
7. investment estimate;
8. power configuration;
9. audit/version relationship verification;
10. zh-CN formal-or-draft report export according to existing eligibility rules.

Expected outcome: `success`.

### 5.2 `high-throughput-review`

Purpose: verify that the existing backend deterministically propagates `requires_review`, blocker, or review metadata for a deliberately demanding synthetic project.

Expected outcome: `review_required` or `blocked`, whichever current production contracts actually produce. The implementation phase must record the observed contract and may not change formulas merely to force a preferred outcome.

### 5.3 `invalid-blocked`

Purpose: verify a deterministic validation or domain blocker response.

Expected outcome: `validation_error` or `blocked`.

No successful calculation, scheme, investment, power, or report artifact may be fabricated for this scenario.

### 5.4 `multilingual-report`

Purpose: generate zh-CN and en-US report artifacts from the same persisted planning result/version and verify localization metadata, revision linkage, status transitions, and integrity hashes.

Expected outcome: `success`.

The frontend or evaluation runner must not translate report content or recompute engineering values.

### 5.5 Optional `sample-document-grounding`

This scenario is allowed only if existing Task 7/8 APIs can ingest and retrieve a small repository-owned synthetic or permissively licensed document without adding new production functionality.

If that prerequisite is not met, the scenario must be omitted rather than replaced with a fake success.

## 6. Execution model

The runner command surface is frozen as:

```bash
cd backend
PYTHONPATH=src uv run python -m cold_storage.evaluation.cli validate --manifest ../evaluation/manifest.json
PYTHONPATH=src uv run python -m cold_storage.evaluation.cli run --manifest ../evaluation/manifest.json --database sqlite
```

PostgreSQL execution uses the same runner with `--database postgresql` and the repository's existing database environment variables.

The runner must:

1. validate the manifest before any database or filesystem mutation;
2. allocate a unique run ID;
3. create an isolated database or transaction scope;
4. clear/create a unique generated-artifact directory for that run;
5. execute the existing application/API workflow;
6. capture raw outputs separately from normalized outputs;
7. canonicalize only paths authorized by the scenario policy;
8. compare normalized output to the expected contract;
9. verify persisted relationships and artifact integrity;
10. write `summary.json` and a concise console report;
11. return exit code `0` only when every declared check passes.

The runner must not update expected files during a normal run.

## 7. Canonicalization and comparison

### 7.1 Exact fields

Exact equality is required for:

- enum/status values;
- booleans and review flags;
- integer counts;
- stable business identifiers declared by the fixture;
- version and revision references;
- coefficient/template/catalog versions;
- content/result hashes;
- locale, format, and render mode;
- blocker/error codes;
- ordered zone/scheme/equipment identities where ordering is contractually deterministic.

### 7.2 Decimal fields

Use decimal strings or `Decimal` quantization according to the existing field contract. A tolerance is permitted only when:

- the field path is named explicitly;
- the unit and scale are declared;
- the existing engineering/API contract permits tolerance;
- the tolerance is narrow and reviewed.

A global epsilon is prohibited.

### 7.3 Ignored fields

Generated timestamps, database IDs, request IDs, temporary paths, and binary container metadata may be excluded only by exact path and documented reason.

Ignoring an entire object or wildcard branch solely to make a fixture pass is prohibited.

### 7.4 Reports

Report checks must prefer existing semantic/integrity metadata:

- report ID and revision linkage;
- template/catalog version;
- locale, format, and mode;
- artifact status;
- content/integrity hash;
- non-zero size;
- successful download through the existing API.

Byte-for-byte binary equality is required only when the existing Task 9 contract guarantees deterministic binary output.

## 8. Database isolation

### SQLite

- create a unique temporary database for each evaluation run;
- never read or write `backend/cold_storage_dev.db`;
- remove temporary databases on success;
- preserve failed-run artifacts only in the run-specific directory for diagnosis.

### PostgreSQL

- use a dedicated test database/schema supplied through CI environment variables;
- run current Alembic migrations before evaluation;
- isolate fixtures by schema, transaction, or explicit run namespace;
- clean up declared fixture records after each run;
- never target a developer or production database.

## 9. Golden expectation governance

Expected files may change only when all of the following are present:

1. an intentional production-contract change already approved in another task/PR, or a reviewed correction to the fixture itself;
2. a written explanation of every changed expectation path;
3. before/after normalized output attached to the PR or committed as reviewable text;
4. full SQLite and relevant PostgreSQL evaluation passes;
5. no formula, coefficient, scoring, or report logic change is hidden inside Task 11 merely to make the golden pass.

No `--update-golden` command is included in the initial implementation. Golden updates are explicit file edits reviewed in Git.

## 10. Pilot runbook contract

The runbook must include:

- prerequisites and exact tool versions inherited from the repository;
- database setup for SQLite and PostgreSQL;
- one-command or minimal-command evaluation execution;
- scenario purpose and expected visible result;
- frontend navigation for the baseline scenario;
- report generation and download verification;
- how to interpret validation, comparison, integrity, and infrastructure failures;
- cleanup and rerun instructions;
- a statement that Task 11 proves pilot reproducibility, not production readiness.

## 11. CI boundary

Task 11 may add an evaluation job or extend existing backend jobs only when runtime remains reasonable and deterministic.

Minimum CI coverage:

- manifest/schema validation;
- fixture path and provenance validation;
- SQLite acceptance evaluation;
- PostgreSQL persistence-sensitive evaluation;
- report artifact consistency;
- all existing backend/frontend/compose jobs remain green.

CI must not commit generated artifacts or rewrite golden files.

## 12. Implementation phases

### Phase A — Contract and harness

- manifest schema and strict validator;
- canonicalization/comparison library;
- runner skeleton and isolated run directories;
- unit tests for fail-closed behavior.

### Phase B — Core pilot fixtures

- baseline feasible;
- high-throughput/review-required;
- invalid/blocked;
- expected normalized contracts;
- SQLite acceptance path.

### Phase C — Persisted/report verification

- PostgreSQL-sensitive checks;
- audit/version relationships;
- zh-CN/en-US reports;
- artifact integrity and download checks.

### Phase D — Pilot runbook and CI

- demo instructions;
- cleanup/re-run process;
- CI integration;
- final drift and repeatability checks.

## 13. Acceptance gates

Task 11 is complete only when:

- a fresh checkout reproduces every mandatory scenario;
- manifest validation fails closed;
- repeated runs yield identical normalized results;
- SQLite and required PostgreSQL checks pass;
- stale files cannot satisfy the current run;
- fixtures are synthetic and provenance-audited;
- declared successful scenarios verify calculations, schemes, investment, power, reports, and persisted links through existing contracts;
- blocked scenarios cannot produce fabricated success artifacts;
- zh-CN and en-US report checks pass from the same persisted result/version;
- existing lint, typecheck, tests, build, migrations, and repository CI remain green;
- PR remains Draft until engineering review is complete;
- Task 12 has not started.

## 14. Delivery rules

- No production code implementation begins until this design is reviewed.
- Do not alter engineering formulas, coefficients, scoring rules, or report calculations in Task 11.
- Do not commit real customer data or confidential documents.
- Do not weaken existing tests or comparison rules to make a fixture pass.
- Do not merge, turn Ready, or start Task 12 before engineering review authorizes it.
