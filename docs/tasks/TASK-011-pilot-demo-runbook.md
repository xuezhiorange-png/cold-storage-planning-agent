# TASK-011 Pilot/Demo Runbook

> Repository-owned operations manual for the TASK-011 multilingual report pilot.
> All commands in this document have been verified against the implementation
> shipped through merged PR #67 at base SHA `8aa5b844a81178bd3dc8124057d2f9207b357a2d`.
> This runbook is **Slice 2** of the frozen remaining-pilot-readiness contract
> (`docs/tasks/TASK-011-remaining-pilot-readiness-definition.md`); Slice 3
> closure evidence, PATH_A follow-up Issue, Issue #20 closure, and Task 12
> are explicitly **NOT** covered here.

## 1. Status and authority

```text
TASK=TASK-011
SLICE=2
DOCUMENT_TYPE=PILOT_DEMO_RUNBOOK
IMPLEMENTATION_SOURCE_MAIN_SHA=8aa5b844a81178bd3dc8124057d2f9207b357a2d
SOURCE_IMPLEMENTATION_PR=67
SOURCE_IMPLEMENTATION_MERGE_COMMIT=8aa5b844a81178bd3dc8124057d2f9207b357a2d
ISSUE_NUMBER=20
CONTRACT_PATH=docs/tasks/TASK-011-remaining-pilot-readiness-definition.md
CONTRACT_BLOB_SHA=8bfdf30c238cb9cc84fcd355c313d762e321854b
RUNBOOK_PATH=docs/tasks/TASK-011-pilot-demo-runbook.md
RUNBOOK_STATUS=AUTHORED_PENDING_REVIEW
ISSUE20_CLOSED_BY_THIS_DOCUMENT=NO
SLICE3_CLOSURE_EVIDENCE_COMPLETED=NO
PATH_A_FOLLOW_UP_ISSUE_CREATED_BY_THIS_DOCUMENT=NO
FRESH_CHECKOUT_SQLITE_EVIDENCE_COMPLETED=NO
FRESH_CHECKOUT_POSTGRESQL_EVIDENCE_COMPLETED=NO
TASK12_AUTHORIZED=NO
```

This document does **NOT** claim the following (each of these requires a
separate authorization round):

- `RUNBOOK_MERGED=YES`
- `ISSUE20_CLOSED=YES`
- `FRESH_CHECKOUT_EVIDENCE=PASS`
- `TASK011_COMPLETE=YES`

## 2. Scope

This runbook demonstrates the TASK-011 multilingual report pilot on a
fresh-checkout repository. It exercises the same frozen scenario matrix
that the CI verification round exercises, but at operator-controlled
scale and under operator-controlled state. Operators can use it to
validate environment readiness, debug a failing pilot locally, or
produce reproducible evidence for Slice 3 closure.

```text
SOURCE_SCENARIO=baseline_feasible
LOCALES=zh-CN,en-US
FORMATS=DOCX,PDF
MODE=draft
RENDER_COUNT_PER_RUN=4
REPEAT_COUNT_PER_BACKEND=2
BACKENDS=sqlite,postgresql
ONE_REPORT_REVISION_PER_RUN=YES
```

Explicitly **excluded** from this runbook (and from TASK-011 scope):

- `formal`-mode pilot (formal-mode render is deferred from TASK-011C V1)
- `high_throughput_review` implementation (deferred from TASK-011C V1)
- production deployment hardening
- real customer data
- real farm data
- real factory data
- external OCR / model / translation services
- Task 12 (the multilingual writeback round, which remains blocked)

## 3. Prerequisites

The following are required before any pilot command can succeed.

### 3.1 Tooling

- **Git** — used to fetch the pinned base SHA and verify the worktree.
- **Python** — `>=3.12` (the project's `pyproject.toml` and `uv.lock`
  resolve to CPython 3.12).
- **uv** — `>=0.11` (the project uses `uv sync --frozen` to install
  backend dependencies; `uv` is the canonical entry point).
- **Docker / Docker Compose** — optional for the pilot itself. The
  pilot only requires a SQLAlchemy URL. Compose becomes relevant if
  you choose to run PostgreSQL via the bundled `docker-compose.yml`
  rather than a remote cluster.

### 3.2 System libraries for DOCX/PDF rendering

The render service emits real DOCX and PDF binaries. The following
Python wheels are pulled in by `uv sync --frozen`:

- `python-docx` — DOCX rendering
- `pymupdf` — PDF rendering

No additional OS-level LibreOffice / wkhtmltopdf dependency is required
on the runner; rendering is performed in pure Python inside the backend
service.

### 3.3 SQLite

SQLite is bundled with Python's standard library; no separate install
is required. The pilot writes to a per-run, operator-owned file path;
the runner rejects any database URL pointing at a non-empty file.

### 3.4 PostgreSQL

PostgreSQL is **only** required for the postgresql backend leg. The
pilot does **NOT** provision or migrate the database itself. The
operator must pre-create an empty database (with the production schema
already applied via Alembic at the matching `main` SHA) before the
run. The pilot refuses to connect to any database that already holds
content from a prior run.

### 3.5 Frontend

- **Node.js** — version matching `frontend/package.json` engines
  (modern Vite / Vue 3 toolchain).
- **npm** or **pnpm** — for `npm install` / `pnpm install`.
- Browser for manual exercise: Chrome / Firefox / Safari latest stable.

### 3.6 Network and ports

- Backend listens on `http://localhost:8000` (FastAPI / uvicorn).
- Frontend dev server listens on `http://localhost:5173` (Vite default).
- PostgreSQL, if local, listens on `localhost:5432` (or compose-mapped).

### 3.7 Disk and temp directories

- Free disk space: at least **2 GB** in `$PILOT_ROOT` and in the OS temp
  directory (`/tmp` on Linux) — each pilot run writes DOCX + PDF
  binaries, `pilot-run.json`, `pilot-summary.json`, per-artifact
  metadata, and per-artifact semantic-checks JSON for all 4 renders.
- `mktemp -d` is used to isolate per-run root directories; ensure
  `/tmp` is writeable.

### 3.8 Secrets and sensitive values

This runbook does **NOT** require or reference:

- A GitHub PAT
- Database passwords
- Real connection strings
- Any secret example value

Sensitive variables use placeholder syntax only (e.g.
`"$TASK011_PILOT_POSTGRESQL_URL"` is left to the operator to export).

## 4. Fresh-checkout setup

Run from a clean shell. This section exercises the same SHA the merged
PR #67 ships at.

```bash
git clone https://github.com/xuezhiorange-png/cold-storage-planning-agent.git
cd cold-storage-planning-agent
git checkout 8aa5b844a81178bd3dc8124057d2f9207b357a2d

# Identity gate
test "$(git rev-parse HEAD)" = "8aa5b844a81178bd3dc8124057d2f9207b357a2d" \
  && echo "FRESH_CHECKOUT_IDENTITY=PASS" \
  || { echo "FRESH_CHECKOUT_IDENTITY=FAIL"; exit 1; }

cd backend
uv sync --frozen
```

Expected stdout from `git rev-parse HEAD`:

```text
8aa5b844a81178bd3dc8124057d2f9207b357a2d
```

Expected stdout from `FRESH_CHECKOUT_IDENTITY`:

```text
FRESH_CHECKOUT_IDENTITY=PASS
```

When `main` advances past this SHA in the future, the Slice 3 closure
evidence round will re-bind the runbook's "execute at SHA" line to the
new frozen main. The reviewed source of this document remains
`8aa5b844a81178bd3dc8124057d2f9207b357a2d`.

## 5. SQLite commands

The frozen contract requires two SQLite pilot runs. Each run is
isolated: a fresh `mktemp -d` output root, a fresh SQLite database
file, and a distinct `--repeat-index`.

### 5.1 Run 1 — repeat-index 1

```bash
cd backend
REPO_BACKEND_ROOT="$(pwd -P)"
IMPLEMENTATION_HEAD_SHA="$(git rev-parse HEAD)"
PILOT_ROOT="$(mktemp -d)"

uv run python tests/pilot/run_multilingual_report_pilot.py run \
  --backend sqlite \
  --database-url "sqlite:///${PILOT_ROOT}/task011-pilot.sqlite3" \
  --manifest "${REPO_BACKEND_ROOT}/tests/evaluation/data/task011-pilot-sqlite.v1.json" \
  --output-root "${PILOT_ROOT}/run-1" \
  --repeat-index 1 \
  --commit-sha "${IMPLEMENTATION_HEAD_SHA}"
```

### 5.2 Run 2 — repeat-index 2

Run 2 MUST use:

- A brand-new `PILOT_ROOT` (so the SQLite database file is on a
  separate filesystem location).
- A brand-new SQLite database file under that new `PILOT_ROOT`.
- `--repeat-index 2`.
- An independent output root (`run-2`).

```bash
cd backend
REPO_BACKEND_ROOT="$(pwd -P)"
IMPLEMENTATION_HEAD_SHA="$(git rev-parse HEAD)"
PILOT_ROOT="$(mktemp -d)"

uv run python tests/pilot/run_multilingual_report_pilot.py run \
  --backend sqlite \
  --database-url "sqlite:///${PILOT_ROOT}/task011-pilot.sqlite3" \
  --manifest "${REPO_BACKEND_ROOT}/tests/evaluation/data/task011-pilot-sqlite.v1.json" \
  --output-root "${PILOT_ROOT}/run-2" \
  --repeat-index 2 \
  --commit-sha "${IMPLEMENTATION_HEAD_SHA}"
```

It is forbidden to:

- Reuse the first run's SQLite database file.
- Reuse the first run's `output-root`.
- Pin `--repeat-index` to `1` for both runs.

## 6. PostgreSQL commands

The frozen contract requires two PostgreSQL pilot runs. The
composition script does not provision or migrate the database; the
operator is responsible for the database lifecycle.

### 6.1 Operator-side prerequisites

Before the first PostgreSQL run, the operator must:

1. Create a **test-only** PostgreSQL database. The database MUST be
   empty (no shared schema with production). The pilot refuses any
   pre-existing content.
2. Apply the production Alembic migrations at the matching `main`
   SHA. The migrations are the canonical source of the database
   schema; do not run a hand-edited schema.
3. Export `TASK011_PILOT_POSTGRESQL_URL` in the operator's shell:

```bash
export TASK011_PILOT_POSTGRESQL_URL="postgresql+psycopg2://<user>:<password>@<host>:5432/<test_db>"
```

The `<user>`, `<password>`, `<host>`, and `<test_db>` values are
operator-controlled and **MUST NOT** be committed or written to any
file under this repository. The variable should be exported in a
private shell session; this runbook does not provide example values.

### 6.2 Run 1 — repeat-index 1

```bash
cd backend
test -n "${TASK011_PILOT_POSTGRESQL_URL:-}"

REPO_BACKEND_ROOT="$(pwd -P)"
IMPLEMENTATION_HEAD_SHA="$(git rev-parse HEAD)"
PILOT_ROOT="$(mktemp -d)"

uv run python tests/pilot/run_multilingual_report_pilot.py run \
  --backend postgresql \
  --database-url "$TASK011_PILOT_POSTGRESQL_URL" \
  --manifest "${REPO_BACKEND_ROOT}/tests/evaluation/data/task011-pilot-postgresql.v1.json" \
  --output-root "${PILOT_ROOT}/run-1" \
  --repeat-index 1 \
  --commit-sha "${IMPLEMENTATION_HEAD_SHA}"
```

### 6.3 Run 2 — repeat-index 2

Run 2 MUST use a brand-new database/schema (drop and recreate, or use
a different test database). It MUST also use a brand-new `PILOT_ROOT`
output root.

```bash
cd backend
test -n "${TASK011_PILOT_POSTGRESQL_URL:-}"

REPO_BACKEND_ROOT="$(pwd -P)"
IMPLEMENTATION_HEAD_SHA="$(git rev-parse HEAD)"
PILOT_ROOT="$(mktemp -d)"

uv run python tests/pilot/run_multilingual_report_pilot.py run \
  --backend postgresql \
  --database-url "$TASK011_PILOT_POSTGRESQL_URL" \
  --manifest "${REPO_BACKEND_ROOT}/tests/evaluation/data/task011-pilot-postgresql.v1.json" \
  --output-root "${PILOT_ROOT}/run-2" \
  --repeat-index 2 \
  --commit-sha "${IMPLEMENTATION_HEAD_SHA}"
```

### 6.4 PostgreSQL isolation requirements

- Use a test-only database. Never point the pilot at production.
- Two runs MUST NOT share a polluted database. After run 1, drop or
  recreate the database before run 2.
- The connection URL MUST NOT be logged, written to a file inside the
  repository, or otherwise persisted.
- Cleanup of the output root via the `cleanup` sub-command is NOT
  equivalent to cleaning up the database. The operator is responsible
  for the database lifecycle separately from the output-root
  lifecycle.
- The database lifecycle (create / migrate / drop) is managed by the
  operator, not by the pilot.

## 7. Expected PASS evidence

Each successful run produces the following structure under
`${PILOT_ROOT}/run-N/`:

```text
pilot-run.json
artifacts/zh-CN/docx/report.docx
artifacts/zh-CN/docx/artifact-metadata.json
artifacts/zh-CN/docx/semantic-checks.json
artifacts/zh-CN/pdf/report.pdf
artifacts/zh-CN/pdf/artifact-metadata.json
artifacts/zh-CN/pdf/semantic-checks.json
artifacts/en-US/docx/report.docx
artifacts/en-US/docx/artifact-metadata.json
artifacts/en-US/docx/semantic-checks.json
artifacts/en-US/pdf/report.pdf
artifacts/en-US/pdf/artifact-metadata.json
artifacts/en-US/pdf/semantic-checks.json
pilot-summary.json
```

- `pilot-run.json` is written before any artifact.
- `pilot-summary.json` is written **last**, after all four renders
  have landed and after the per-artifact integrity and semantic
  checks have been recorded.
- DOCX and PDF binary contents can differ between runs even when
  semantic content is identical. Container metadata (timestamps,
  font-table reordering, etc.) is rendered by the underlying library
  and is not part of the contract. The contract compares
  `file_sha256` against the on-disk bytes and the persisted
  `source_content_hash` against the report revision; it does not
  compare DOCX/PDF binaries across runs.

## 8. Relationship and integrity checks

The four renders inside one run are bound to a single source
revision. Within one `pilot-run.json` / `pilot-summary.json` /
artifact set, the following fields MUST be equal across all four
artifacts:

```text
project_id
project_version_id
report_id
report_revision_id
revision_number
report_revision_content_hash
source_content_hash
report_type
report_schema_version
render_mode=draft
```

The contract requires:

```text
source_content_hash == report_revision_content_hash
```

This is a single source-of-truth invariant: the four artifacts are
siblings of one persisted revision, not independent recalculations.

Each individual artifact MUST independently satisfy:

```text
artifact_status=completed
file_size_bytes > 0
DOWNLOAD_BYTES_SHA256 == file_sha256
DOWNLOAD_HEADER_X_CONTENT_SHA256 == file_sha256
DOWNLOAD_HEADER_X_SOURCE_CONTENT_HASH == source_content_hash
DOWNLOAD_HEADER_X_REPORT_LOCALE == locale
DOWNLOAD_HEADER_X_TEMPLATE_LOCALE == template_locale
```

## 9. Hash distinctions

The pilot surfaces four distinct hash surfaces. Operators MUST NOT
treat them as interchangeable.

| Hash | What it identifies |
|---|---|
| `report_revision_content_hash` | The persisted report revision — the report's semantic identity |
| `source_content_hash` | The combined source binding that produced this revision |
| `file_sha256` | The byte integrity of a single downloadable artifact (one per render) |
| `localized_template_content_hash` | The specific locale-bound template variant that was rendered |

The contract invariant is `source_content_hash ==
report_revision_content_hash`. The `file_sha256` is independent and
specifically tracks on-disk bytes for that one artifact.

DOCX and PDF are container formats. Two artifacts produced by the
same revision can have **different** `file_sha256` because the
container metadata (timestamps, font-table order, optional fields)
is determined by the rendering library and is not part of the
business contract. A binary `file_sha256` difference between runs is
**NOT** a business-semantic failure; the semantic-checks JSON files
are the authoritative business-content check.

It is forbidden to:

- Compare DOCX/PDF `file_sha256` between separate runs and call it a
  regression.
- Substitute `file_sha256` for `source_content_hash` in any
  integrity assertion.

## 10. Backend / API execution path

The pilot CLI is the canonical entry point. The backend modules it
exercises, in execution order, are:

1. **Manifest loader** — `run_multilingual_report_pilot._load_pilot_manifest`
   (path: `backend/tests/pilot/run_multilingual_report_pilot.py`).
2. **Raw manifest identity gate** — `_assert_raw_manifest_path_identity`
   (lexical-absolute path validation, symlink-component rejection,
   `..` / `.` / repeated-separator rejection).
3. **Frozen-manifest identity validator** — `validate_frozen_manifest_identity`
   (path / suite / scenario / backend / expected_outcome /
   expected_output triple / excluded_paths / fixtures /
   comparison_policy).
4. **Evaluation runner** — `run_scenario_via_markers` driven by the
   seeded `scheme_run` from the A1 seed fixture.
5. **Manifest-to-golden binding** —
   `_verify_manifest_golden_binding` / `_load_manifest_golden`.
6. **Report service + report revision creation** — `ReportService` /
   `ReportRenderService` (modules: `reports.application`,
   `reports.domain`).
7. **Render service** — `ReportRenderService.render` →
   `_find_template` (locale-bound) →
   `ReportArtifactStorage` (per-locale/per-format directory).
8. **Artifact storage** — `ReportArtifactStorage` under
   `artifacts/<locale>/<fmt>/`.
9. **Verified download** — `_build_download_artifact` mirrors
   `reports.api.routes.download_export`: `verify_download` +
   `get_artifact_path` + reconstructed headers
   (`X-Content-SHA256`, `X-Source-Content-Hash`, `X-Template-Version`,
   `X-Report-Locale`, `X-Template-Locale`,
   `X-Translation-Catalog-Version`,
   `X-Translation-Catalog-Content-Hash`,
   `X-Localized-Template-Content-Hash`).
10. **Pilot verifier** — `verify_multilingual_report_pilot`
    (typed `PilotVerificationError` for any acceptance mismatch).
11. **Summary projection** — `aggregate_p1_4_acceptance` +
    `pilot-summary.json` write (last).

There is **no second orchestration runtime**. The pilot CLI is the
single process boundary. Each backend module listed above is invoked
from inside `_cmd_run` (path: `run_multilingual_report_pilot.py:1584`).

## 11. Frontend demo path

The frontend ships one report export surface. The route is:

```text
/workbench/reports  →  ReportsPage.vue
                      └─ ReportExportPanel.vue
                         └─ useReportExport composable
                            └─ reportsApi client (api/v1/reports/...)
```

### 11.1 Starting the stack

```bash
# Terminal 1 — backend
cd backend
uv sync --frozen
uv run uvicorn cold_storage.app:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — frontend
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The default route redirects to
`/workbench/project`; click the **Reports** navigation entry to land
on `/workbench/reports`.

### 11.2 Operator flow

1. On `/workbench/reports`, the `ReportsPage` loads the available
   reports for the current project (loaded via
   `reportsApi.list(projectId)`).
2. Expand a report card; `ReportExportPanel.vue` loads the report's
   revisions and current exports via
   `reportsApi.listRevisions(reportId)` / `reportsApi.listExports(...)`.
3. Pick a revision number; trigger `handleRender(reportId, revisionNumber)`
   with the active export form (`createDefaultExportForm()`). The
   export form exposes locale and format selection.
4. After the render completes, click **Download** on the resulting
   artifact. The download passes through
   `reportsApi.download(reportId, artifactId)`, which surfaces the
   integrity headers in `Content-Disposition`, `X-Content-SHA256`,
   `X-Source-Content-Hash`, etc.

### 11.3 Pilot integrity fields: backend-only

The frontend surfaces `file_name`, `file_size_bytes`, `file_sha256`,
`revision_number`, `generated_at`, `locale`, `template_locale`,
`translation_catalog_version`,
`translation_catalog_content_hash`, and
`localized_template_content_hash` in the artifact list and detail
panels (see `frontend/src/api/contracts/reports.ts`).

The following fields are **NOT** rendered on the frontend — they
appear only in the backend's `pilot-summary.json` /
`pilot-run.json` / per-artifact metadata:

- `pilot_check_id`
- `source_commit_sha`
- `manifest_scenario_id`
- `manifest_expected_outcome`
- `manifest_golden_comparison_result`
- `canonical_section_key_set` / `canonical_numeric_field_path_set` /
  `canonical_numeric_value_and_unit_set` (semantic-checks JSON).
- `overall_result`

Operators who need these fields MUST inspect the backend output root
directly.

### 11.4 Known frontend limitation

The current frontend does **NOT** expose a switch for:

- `--repeat-index`
- `--backend` (SQLite vs PostgreSQL)
- `--commit-sha`
- `--manifest` (path to the frozen manifest)

These are CLI-only controls. The frontend consumes a single backend
deployment and exercises whatever render form the user picks in the
panel.

## 12. Failure interpretation

The pilot CLI exposes five stable exit codes, defined at
`run_multilingual_report_pilot.py:196-200`:

```text
EXIT_OK = 0
EXIT_INFRA_ERROR = 1
EXIT_INPUT_ERROR = 2
EXIT_BACKEND_ERROR = 3
EXIT_VERIFIER_ERROR = 4
```

### 12.1 Exit code 0 (`EXIT_OK`)

Both run sub-commands return 0 only on full success. The composition
script writes a single-line JSON to stdout summarizing the run
(`pilot-summary.json` is also written to disk for the `run`
sub-command).

### 12.2 Exit code 1 (`EXIT_INFRA_ERROR`)

Reserved for infrastructure-level failures that do not map cleanly to
either a manifest / input error or a backend runner error. In
practice this surface is rare; see the stderr line `code=` for the
typed `PilotCompositionError.code`.

### 12.3 Exit code 2 (`EXIT_INPUT_ERROR`)

Triggered by `PilotCompositionError.code` in
`{"INPUT_ERROR", "MANIFEST_ERROR", "MANIFEST_IDENTITY_MISMATCH",
"MANIFEST_SCENARIO_MISMATCH", "MANIFEST_GOLDEN_PATH_UNSAFE",
"MANIFEST_GOLDEN_MISSING", "MANIFEST_GOLDEN_INVALID",
"SEED_BINDING_MISSING", "UNSAFE_OUTPUT_ROOT"}`. This category covers:

- **Manifest / identity rejection** — the manifest path is not the
  canonical authority, contains `..` / `.` / repeated separators,
  contains a symlinked component, or disagrees with the
  `--backend` / `--repeat-index` /
  `--commit-sha` arguments.
- **Unsafe output-root rejection** — the requested output root is
  relative, contains symlinks, or lives under
  `$HOME` / the repository root / `backend/` root / filesystem root.
  The `cleanup` sub-command rejects relative output roots and the
  same unsafe-path set.
- **Stale-output rejection** — the requested output root already
  exists and is non-empty. The pilot refuses to overwrite a prior
  run; the operator must `cleanup` it first or use a new
  `PILOT_ROOT`.

### 12.4 Exit code 3 (`EXIT_BACKEND_ERROR`)

Triggered when `PilotCompositionError.code == "BACKEND_RUNNER_FAILED"`
— the backend runner returned a non-`SUCCEEDED` outcome. This
indicates a problem inside the evaluation runner (database, seed,
scheme-run, etc.) rather than the manifest itself. The stderr
line carries the outcome string and the typed code.

### 12.5 Exit code 4 (`EXIT_VERIFIER_ERROR`)

Triggered by any `PilotVerificationError` raised by
`verify_multilingual_report_pilot`. This is the canonical verifier
failure signal: download integrity, semantic numeric mismatch,
report-content mismatch, etc. The stderr line is
`PILOT_VERIFICATION_ERROR code=<typed-code>: <message>`.

This runbook does **NOT** prescribe an automated recovery flow for
verifier-side failures. Operators must inspect the on-disk
`pilot-run.json`, `pilot-summary.json`, and per-artifact
`semantic-checks.json` files and decide whether the failure is a
true regression or an environment issue.

## 13. Stale-output demonstration

The pilot refuses to overwrite a non-empty output root. This
behaviour can be demonstrated safely inside a fresh `mktemp -d`:

```bash
cd backend

REPO_BACKEND_ROOT="$(pwd -P)"
IMPLEMENTATION_HEAD_SHA="$(git rev-parse HEAD)"
PILOT_ROOT="$(mktemp -d)"

# Step 1 — first successful run.
uv run python tests/pilot/run_multilingual_report_pilot.py run \
  --backend sqlite \
  --database-url "sqlite:///${PILOT_ROOT}/task011-pilot.sqlite3" \
  --manifest "${REPO_BACKEND_ROOT}/tests/evaluation/data/task011-pilot-sqlite.v1.json" \
  --output-root "${PILOT_ROOT}/run-1" \
  --repeat-index 1 \
  --commit-sha "${IMPLEMENTATION_HEAD_SHA}"

# Step 2 — repeat the same command. The pilot refuses before any
# DB / report / managed-file side-effect runs.
uv run python tests/pilot/run_multilingual_report_pilot.py run \
  --backend sqlite \
  --database-url "sqlite:///${PILOT_ROOT}/task011-pilot.sqlite3" \
  --manifest "${REPO_BACKEND_ROOT}/tests/evaluation/data/task011-pilot-sqlite.v1.json" \
  --output-root "${PILOT_ROOT}/run-1" \
  --repeat-index 1 \
  --commit-sha "${IMPLEMENTATION_HEAD_SHA}"

echo "exit=$?"
```

The second invocation exits with code 2 (`EXIT_INPUT_ERROR`) and
stderr text `code=INPUT_ERROR: --output-root '${PILOT_ROOT}/run-1'
already exists and is non-empty; the pilot refuses to overwrite a
prior run.`

The expected properties of the rejection:

- The pilot performs no database migration, no seed, no scheme-run,
  no render, and no managed-file write on the rejected attempt.
- The existing `${PILOT_ROOT}/run-1/` contents are preserved
  byte-for-byte until the operator explicitly runs `cleanup`.
- The output root MUST live under `PILOT_ROOT` (an
  operator-owned `mktemp -d` directory). Do **NOT** point this
  demonstration at the repository root, `backend/`, `$HOME`, or
  any other non-owned path — the path safety gate will reject it
  with `code=UNSAFE_OUTPUT_ROOT` (also exit 2) before reaching the
  stale-output check.

## 14. Cleanup and rerun

Use the `cleanup` sub-command to remove an operator-owned output
root. The cleanup path goes through the shared authority
`remove_managed_output_root` which enforces an ownership marker
(`pilot-run.json`) and a parent-directory boundary.

```bash
cd backend
uv run python tests/pilot/run_multilingual_report_pilot.py cleanup \
  --output-root "${PILOT_ROOT}/run-1"
```

Cleanup rules:

- The output root MUST be the same path that was created by a
  previous `run` invocation in the same shell session (or otherwise
  contains the ownership marker `pilot-run.json`).
- Relative paths are rejected (`EXIT_INPUT_ERROR`).
- Paths whose components are symlinks are rejected.
- Paths under the repository root, `backend/` root, `$HOME`, or the
  filesystem root are rejected (`UNSAFE_OUTPUT_ROOT`).
- Cleanup ONLY removes the output root. It does NOT drop a database
  (SQLite file or PostgreSQL schema); the operator manages that
  lifecycle separately.

After cleanup, a rerun MUST create a fresh `PILOT_ROOT` (and, for
PostgreSQL, a fresh database/schema) and a fresh output root. Do NOT
reuse the previous run's `PILOT_ROOT` after cleanup.

## 15. Synthetic-data confirmation

```text
SYNTHETIC_REPOSITORY_OWNED_DATA_ONLY=YES
REAL_CUSTOMER_DATA=NO
REAL_FARM_DATA=NO
REAL_FACTORY_DATA=NO
PERSONAL_DATA=NO
CONFIDENTIAL_DATA=NO
SECRET_DATA=NO
```

The pilot manifests and seed data shipped in this repository are
synthetic and owned by the repository. The pilot is intended for
concept-design and integration-validation work on the engineering
domain; it does not exercise real customer, real farm, or real
factory data.

## 16. Known limitations

- **Draft render only.** The pilot exercises the `draft` render mode.
  `formal`-mode rendering is deferred from TASK-011C V1.
- **`high_throughput_review` deferred.** The high-throughput-review
  pipeline is out of scope for TASK-011C V1 and will be tracked as a
  PATH_A follow-up Issue, separately from this runbook.
- **Not a load test.** Two runs per backend is the frozen contract
  scale. This runbook is not a benchmark and does not characterize
  pilot throughput.
- **Not a production deployment certification.** This runbook does
  not validate production hardening, secret management, multi-tenant
  isolation, or failover behaviour. It validates the freeze contract.
- **Not external OCR / model / translation validation.** The pilot
  renders DOCX/PDF from the bundled `python-docx` / `pymupdf`
  libraries. No external OCR / LLM / translation service is invoked.
- **Different artifact binary hash can be legitimate.** See §9. A
  `file_sha256` difference across runs is not a regression; check
  the semantic-checks JSON files instead.
- **Task 12 is out of scope.** Task 12 (the multilingual writeback
  round) is not part of TASK-011 and remains blocked until Slice 3
  closure evidence is published.

## 17. Closure boundary

```text
RUNBOOK_MERGE_DOES_NOT_CLOSE_ISSUE20=YES
SLICE3_REQUIRED=YES
PATH_A_FOLLOW_UP_ISSUE_REQUIRED=YES
FRESH_CHECKOUT_SQLITE_EVIDENCE_REQUIRED=YES
FRESH_CHECKOUT_POSTGRESQL_EVIDENCE_REQUIRED=YES
CLOSURE_COMMENT_REQUIRED=YES
SEPARATE_CHARLES_CLOSURE_AUTHORIZATION_REQUIRED=YES
TASK12_REMAINS_BLOCKED=YES
```

The merge of this runbook does NOT, by itself, close Issue #20.
The remaining steps before Issue #20 can be closed are:

1. **Slice 3 — Closure evidence**: collect fresh-checkout SQLite and
   PostgreSQL pilot outputs in the Slice 3 closure-evidence round.
2. **PATH_A follow-up Issue**: create the follow-up Issue that tracks
   the `high_throughput_review` and `formal`-mode scope deferred
   from TASK-011C V1.
3. **Closure comment**: post a single closure summary comment on
   Issue #20 linking the runbook, the closure evidence, and the
   PATH_A follow-up Issue.
4. **Explicit Charles authorization**: Issue #20 closure requires
   Charles's separate authorization in a dedicated round. No agent
   round may close Issue #20 without it.
5. **Task 12 remains blocked** until Issue #20 is closed.

---

*This runbook is a docs-only deliverable. It does not modify any
code, test, fixture, golden, schema, or workflow file in the
repository.*