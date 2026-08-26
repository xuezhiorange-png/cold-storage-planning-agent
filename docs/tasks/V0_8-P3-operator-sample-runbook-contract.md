# V0.8 P3 Operator-Minimal Sample and Runbook Contract

**Status:** Definition freeze R1 — operator-minimal process-input sample + runbook
**Authority:** Parent contract `docs/tasks/V0_8-P0-operator-minimal-input-contract.md` §6.4
**Requires:** P1 assembler (`OperatorProcessInputV1` → `EngineeringInputBundleV1`)
**Target branch:** `cursor/v08-p3-operator-sample-runbook-6c68`

P3 delivers the bundled V0.8 operator-minimal sample: five KEY leaves only in
the manifest, backend assembler expansion, five-stage persistence, and the
operator runbook on **unmodified** `create_app`.

## 0. Contract identity and governance

```text
TASK=V08_P3_OPERATOR_SAMPLE_RUNBOOK_R1
PARENT_CONTRACT=docs/tasks/V0_8-P0-operator-minimal-input-contract.md
GOVERNANCE_OWNER=V0.8
BASE_MAIN_SHA=1961d7ab5cd4e76c5e7a077700b9eda31f0e737e
BASE_SUBJECT=V0.8 P1: assemble operator-minimal process input into EngineeringInputBundleV1 (#209)
PREVIOUS_RELEASE=v0.7.0
TARGET_BRANCH=cursor/v08-p3-operator-sample-runbook-6c68
TARGET_FILE=docs/tasks/V0_8-P3-operator-sample-runbook-contract.md
TARGET_PR_STATE=DRAFT
```

```text
V08_P3_IMPLEMENTATION_AUTHORIZED=YES
V08_P4_IMPLEMENTATION_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
COEFFICIENT_PROMOTION_AUTHORIZED=NO
PRODUCTION_RBAC_CLAIM=NO
AILY_LIVE_IMPLEMENTATION=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## 1. Objective

On **unmodified** `create_app`, the V0.8 operator-minimal sample must complete:

```text
POST /api/v1/projects
 → POST .../five-stage-execution (operator_process_input + idempotency_key)
 → assembler expands five KEY into EngineeringInputBundleV1
 → five canonical stages persist
 → POST .../production-scheme-runs (optional verify path)
 → report create/generate/submit-review/trusted mark-reviewed/approve/formal export (verify path)
```

The manifest contains **only** `OperatorProcessInputV1` five KEY leaves plus
project metadata and `idempotency_key`. It must **not** contain
`engineering_input_bundle`.

### 1.1 Non-goals (hard boundaries)

```text
V07_SAMPLE_LOADER_MUTATION=NO
V07_MANIFEST_MUTATION=NO
BOOTSTRAP_APP_MUTATION=NO
ASSEMBLER_IMPLEMENTATION_MUTATION=NO
VUE_MUTATION=NO
CALCULATOR_FORMULA_CHANGE=NO
COEFFICIENT_PROMOTION=NO
DEMO_SCHEME_COMPARISON_BINDING=NO
LEGACY_SCHEME_RUNS_AS_REPORT_AUTHORITY=NO
PLANNING_RUN=NO
ALEMBIC_INSIDE_LOADER=NO
V05_V06_V07_TEST_ASSERTION_MUTATION=NO
OUTBOX_TEST_MUTATION=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
AILY_LIVE_IMPLEMENTATION=NO
PRODUCTION_DEPLOYMENT_AUTHORIZED=NO
PRODUCTION_RBAC_CLAIM=NO
```

## 2. Frozen operator sample identity

| Item | Frozen value |
| --- | --- |
| Sample id | `v08-process-input` |
| Manifest | `samples/v08-process-input/manifest.json` |
| Loader module | `backend/src/cold_storage/bootstrap/v08_sample_loader.py` |
| Trusted actor (TestClient seam) | `v08-local-trusted-reviewer` |
| Untrusted actor | `system` |
| Production weight revision | `wsr-production-default-v1` |
| Production scheme profile | `balanced` |

### 2.1 Operator KEY values (frozen; same as P1 integration tests)

| Leaf | Value | Unit |
| --- | --- | --- |
| `daily_inbound_mass_kg` | 20000 | kg/day |
| `working_time_h_per_day` | 16 | h/day |
| `finished_storage_days` | 7 | day |
| `packaging_storage_days` | 1 | day |
| `precooling_required_ratio` | 0.6 | ratio |

Project metadata: name **V0.8 算子最小输入示例项目**, location **山东**,
product_category **blueberry**, idempotency_key **v08-process-input-initial**.

### 2.2 Assembler path rule

The loader posts `operator_process_input` (not `engineering_input_bundle`) to
`POST .../five-stage-execution`. The application assembler (P1) expands catalog
and lineage leaves. Demo catalog leaves remain `requires_review=true`.

Precooling rooms receive the v05 workbench freezer envelope demo leaves
(including `-18°C` room design temperature). These are **not** operator-typed
values and require engineering review.

### 2.3 HTTP-only loader rule

Public API families used by the loader:

- `POST/GET /api/v1/projects/**`
- `POST .../five-stage-execution` with `operator_process_input`
- `POST .../production-scheme-runs`
- `POST/GET /api/v1/reports/**`

**Forbidden loader paths:** `planning-run`, legacy `scheme-runs` as report
authority, `GET /api/v1/demo/scheme-comparison`, Alembic inside the loader.

### 2.4 Coexistence with V0.7 sample

`v07-trust-loop` and `v08-process-input` samples coexist. P3 must not mutate
`v07_sample_loader.py` or `samples/v07-trust-loop/**`.

## 3. Makefile targets (P3 owns)

| Target | Purpose |
| --- | --- |
| `seed-v08-sample` | Seed operator-minimal sample via loader |
| `verify-v08-sample` | Full verify path (five-stage + trust loop) |
| `smoke-v08-local` | Alias for `verify-v08-sample` |

Existing `seed-v07-sample` / `verify-v07-sample` targets must remain unchanged.

## 4. Allowlist (exclusive)

```text
V08_P3_FILE_ALLOWLIST
docs/tasks/V0_8-P3-operator-sample-runbook-contract.md
samples/v08-process-input/**
backend/src/cold_storage/bootstrap/v08_sample_loader.py
docs/runbooks/v08-process-input-runbook.md
Makefile
backend/tests/integration/v08_p3_operator_fixtures.py
backend/tests/integration/test_v08_p3_operator_sample_sqlite.py
backend/tests/integration/test_v08_p3_operator_sample_postgresql.py
```

## 5. Acceptance criteria

- Manifest contains only five KEY leaves; no `engineering_input_bundle`.
- `seed_v08_sample` on unmodified `create_app` persists all five canonical
  calculators: `cold_room_zone_plan`, `cooling_load`, `equipment`,
  `installed_power`, `investment_estimate`.
- Missing operator KEY → `MISSING_ENGINEERING_PARAMETER` with zero partial chain.
- `verify_v08_sample` completes report trust loop with trusted TestClient actor.
- Untrusted `mark-reviewed` fail-closed.
- SQLite and PostgreSQL integration tests pass without mutating V0.5/V0.6/V0.7
  assertion bodies or outbox tests.
- Runbook documents migrate → seed → verify and assembler/demo review notes.

## 6. Not in P3

- Vue operator workbench (P2)
- Controlled acceptance matrix (P4)
- Calculator formula edits
- Tag / Release / merge authorization
- Live Aily enablement
