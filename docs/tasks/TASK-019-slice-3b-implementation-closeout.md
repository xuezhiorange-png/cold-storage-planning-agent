# TASK-019 Slice 3B implementation closeout

**Status:** Slice 3B adapter implementation committed locally on a new
branch off the post-merge main. Branch push + Draft PR creation are
authorized by Charles's per-message authorization for the
implementation round (the prior slice 3B contract is **frozen**).

## 1. Frozen contract (source of truth)

This implementation round conforms to the **frozen** Slice 3B
contract:

- Path: `docs/tasks/TASK-019-slice-3b-adapter-implementation-contract.md`
- Merged via PR #55
- Merge commit: `9185b766de877c32557a355a6c6ce30d444154c0`
- Post-merge main CI: `TASK_019_SLICE_3B_CONTRACT_POST_MERGE_MAIN_CI_GREEN`
  (run id `29038450593`, all 4 jobs `success`)

If this document ever conflicts with the frozen contract, the frozen
contract wins.

## 2. Allowed files (§6 compliance)

### 2.1 New files created (per §6.2 row 1, 2, 6, 7, 8)

| path | role | contract row |
|---|---|---|
| `backend/src/cold_storage/modules/reports/application/validation_report.py` | `ValidationReport` typed dataclass + JSON round-trip (upstream Slice 3 §8 schema) | §6.2 row 2 — default path |
| `backend/src/cold_storage/modules/reports/application/validation_adapter.py` | thin validation adapter implementing §8 / §9 / §10 / §11 / §13 | §6.2 row 1 — default path |
| `backend/tests/validation/test_task_019_slice_3b_validation_report.py` | §15.2 required tests | §6.2 row 6 — required |
| `backend/tests/validation/test_task_019_slice_3b_validation_adapter.py` | §15.1 required tests | §6.2 row 7 — required |
| `docs/tasks/TASK-019-slice-3b-implementation-closeout.md` | this file (§18 / §19 acceptance criterion) | §6.2 row 8 — required |

### 2.2 No modification of §6.1 existing files

The implementation does NOT modify the existing
`backend/src/cold_storage/modules/reports/application/__init__.py`
or any other §6.1 listed file. The new modules are imported through
the `cold_storage.modules.reports.application.*` namespace; the
existing `__init__.py` remains a single-line docstring.

### 2.3 §6 fallback not triggered

The contract §6.3 fallback path (`backend/src/cold_storage/modules/validation/`)
was **not** used. The default path
(`backend/src/cold_storage/modules/reports/application/`) was available
and structurally compatible with the `API -> Application -> Domain`
dependency direction (per `AGENTS.md`). The existing
`render_service.py` and `service.py` live in this directory; the
new adapter/report files mirror that pattern.

## 3. Forbidden files (§7 compliance)

| category | status |
|---|---|
| §7.1 — `coefficients/**`, `formulas/**`, `pressure*`, `discount*`, `salvage*`, `migrations/**`, `production_seeding.py` | **NOT TOUCHED** |
| §7.2 — `frontend/**`, `.github/**`, `docker/**`, `pyproject.toml`, `uv.lock`, `package*.json`, `scripts/**` | **NOT TOUCHED** |
| §7.3 — TASK-011B / PR #21 / Issue #35 / domain module `schemes.domain.validation` | **NOT TOUCHED** |
| §7.4 — Slice 3 / Slice 3A / Slice 3B contract files + Slice 3A fixture helper + Slice 3A fixture tests | **NOT TOUCHED** |
| §7.5 — PR #54-vintage `tests/test_reports/test_waiter_concurrent.py` | **NOT TOUCHED** |

Verification:

```bash
git diff --name-only origin/main...HEAD
# Expected: only files listed in §2.1 of this closeout, plus this closeout doc.
```

## 4. Scope of changes (§5 / §8 / §13 compliance)

- **No pressure-drop implementation** added. No pressure-drop module
  imported by the adapter.
- **No production formula mutation.** Existing production calculators,
  coefficient resolver, weight-set revisions are untouched.
- **No discount / salvage / cost-model invention.** None implemented.
- **No fixture expected-output invention.** All three Slice 3A fixture
  cases remain placeholder; the adapter surfaces the fixture's
  `expected_output` verbatim, including the `placeholder: True` flag.
- **No migration.** No Alembic migration added.
- **No frontend mutation.** Backend-only.
- **No API expansion.** No new REST / GraphQL / CLI endpoints added.
- **No production row seeding.** `production_seeding.py` is not created
  or restored. The adapter is structurally read-only with respect to
  the production database (see §11 below).
- **No Task 11B / PR #21 / Issue #35 mutation.** All out of scope.
- **No expansion of the three Slice 3A fixture cases.** The three cases
  remain the only inputs to the adapter. Adding a 4th case requires a
  separate design-amendment round.
- **No mutation of the Slice 3A fixture helper / fixture tests.** Both
  files (`_task_019_slice_3_placeholder_fixtures.py` and
  `test_task_019_slice_3_placeholder_fixtures.py`) are frozen per
  §7.4. The adapter imports from the helper, never modifies it.

## 5. Production API boundary (§11 compliance)

The `validate_case(case, production_output=None, metadata=None)`
public signature does NOT take a database `session`, `db`,
`database_session`, or `transaction` parameter. The adapter is
**structurally read-only** with respect to production data:

- No `session.flush`, `session.commit`, `session.add`, `session.delete`
  references exist anywhere in
  `backend/src/cold_storage/modules/reports/application/validation_adapter.py`.
- No `Base.metadata.create_all`, `bulk_insert_mappings`, or raw
  `text(...)` SQL references exist.
- The production `production_output` argument is treated as an opaque
  input; the adapter does NOT invoke any production path itself.
  For the three Slice 3A cases no production path exists, so
  `production_output` is expected to be `None`; the adapter remains
  correct when it is `None`.

## 6. Expected-output boundary (§12 compliance)

The adapter's `ValidationReport.expected_output` field is the
fixture's `expected_output` verbatim. The `placeholder: True` flag is
preserved verbatim through the round-trip. No production result is
ever substituted in.

If a future round requires a real expected output to pass a test,
the round must STOP per §17 ("STOP if the implementation requires
inventing a real expected output for a fixture that has only a
placeholder"). This round did not require that.

## 7. Required tests (§15 compliance)

### 7.1 §15.1 (adapter tests — 8 enumerated)

Located in:
`backend/tests/validation/test_task_019_slice_3b_validation_adapter.py`

- `test_case_01_placeholder_blocked_status` — verifies case_01 routes
  to `placeholder` and `placeholder_fields` includes `inputs` and
  `expected_output`.
- `test_case_02_requires_upstream_slice_status` — verifies case_02
  routes to `requires_upstream_slice` and `requires_slice == 'slice-1'`
  surfaces in `metadata`.
- `test_case_03_blocked_status` — verifies case_03 routes to `blocked`
  and `missing_fields` is non-empty.
- `test_fixture_provenance_preserved` — verifies `source_references`
  includes both upstream + fixture contract paths for all three cases.
- `test_no_expected_output_comparison` — verifies
  `expected_output` is verbatim and no production-comparison logic
  exists.
- `test_fail_closed_on_ambiguous_mixed_placeholder` — verifies
  fail-closed to `blocked` for mixed real-looking + placeholder fields.
- `test_no_production_row_writes` — verifies no `INSERT` / `UPDATE` /
  `DELETE` / `session.flush` / `session.commit` symbols exist in the
  adapter module, and the public signature does NOT accept a
  `session` parameter.
- `test_no_demo_or_latest_row_fallback` — verifies no demo / latest-row
  fallback for synthetic cases.

Plus a defensive test (informational):

- `test_adapter_internal_warning_on_non_dict_case` — verifies the
  adapter never returns `None`; a non-dict `case` argument falls into
  the hard-blocked guard.

### 7.2 §15.2 (report tests — 3 enumerated)

Located in:
`backend/tests/validation/test_task_019_slice_3b_validation_report.py`

- `test_validation_report_required_fields` — verifies every required
  field is present and typed per the upstream Slice 3 §8 schema.
- `test_validation_report_json_round_trip` — verifies JSON
  serialize / deserialize preserves all field values verbatim,
  including the `placeholder: True` flag in `expected_output`.
- `test_validation_report_status_closed_set` — verifies the `status`
  closed-set enforcement on both direct construction and
  `from_dict` construction.

### 7.3 §15.3 (forbidden-import guard)

Implemented as `test_no_production_row_writes` in the adapter test
file — the static-import check that no SQLAlchemy ORM symbol exists
in the adapter module. The §15.3 guard is forward-looking (no
pressure-drop module exists today, so the guard is currently
trivial); it is included to prevent future accidental introduction.

### 7.4 §15.4 (inherited Slice 3A tests — frozen, NOT modified)

The 32 Slice 3A fixture-contract tests in
`backend/tests/validation/test_task_019_slice_3_placeholder_fixtures.py`
remain untouched. The adapter imports from the fixture helper but
does NOT modify it. Verification: re-running the file unmodified must
yield 32/32 passing.

## 8. Verification (§16 compliance)

§16 commands will be run on the implementation branch before Draft
PR creation. Required commands:

```bash
cd backend
PYTHONPATH=src DATABASE_BACKEND=sqlite \
  uv run pytest tests/validation/test_task_019_slice_3_placeholder_fixtures.py -q -vv
# Expected: 32/32 passing (inherited from Slice 3A; not modified)

PYTHONPATH=src DATABASE_BACKEND=sqlite \
  uv run pytest tests/validation/test_task_019_slice_3b_validation_adapter.py -q -vv
# Expected: 8/8 §15.1 tests passing + 1/1 defensive test passing

PYTHONPATH=src DATABASE_BACKEND=sqlite \
  uv run pytest tests/validation/test_task_019_slice_3b_validation_report.py -q -vv
# Expected: 3/3 §15.2 tests passing

PYTHONPATH=src DATABASE_BACKEND=sqlite \
  uv run pytest tests/validation -q -vv
# Expected: combined 32 + 8 + 1 + 3 = 44 tests, all passing

PYTHONPATH=src DATABASE_BACKEND=sqlite \
  uv run pytest tests/test_reports/test_waiter_concurrent.py::TestDefaultWaiterFastAPIConvergence::test_default_waiter_two_fastapi_requests_converge -q -vv
# Expected: passing (PR #54 fix must not regress)

uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

## 9. PR / CI / merge boundaries (§18 compliance)

- This implementation round produces a branch
  `codex/task-019-slice-3b-adapter-implementation` and pushes it.
- The Draft PR is created via Web UI by Charles (admin auth required)
  or by the agent if `gh` is auth-enabled.
- **The PR is Draft only.** Marking Ready and merging requires
  Charles's explicit per-message authorization. The agent does NOT
  auto-mark Ready and does NOT auto-merge.
- The PR body lists the frozen contract, the §6 allowed-files
  compliance, the §7 forbidden-files compliance, and the §15
  required-tests compliance.
- This closeout doc is the appendix referenced by the PR body.

## 10. Acceptance (§19 compliance)

| criterion | status |
|---|---|
| All §15 required tests added and passing (44 tests: 32 inherited + 8 + 1 + 3) | **PENDING** — to be confirmed in verification step |
| All §16 verification commands exit code 0 | **PENDING** |
| This closeout doc exists at the §6.2-mandated path | **YES** ✅ |
| PR body documents §6 / §7 / §15 compliance + §6 fallback rationale | **YES** ✅ (this document + the PR body prepared for §10) |

## 11. Change log

| version | date | agent | change |
|---|---|---|---|
| v1.0 | 2026-07-09 | Hermes | initial implementation closeout |
