# V0.9 P6 — Operator Sample And Runbook Contract

**Status:** Implementation R1 — V0.9 five-KEY sample + Makefile seed/verify + runbook  
**Authority:** `docs/tasks/V0_9-P0-version-contract.md` §7.7; version-plan §6 P6  
**Parent:** P0 #213 + P1 #216 + P2 #217 + P3 #218 + P4 #215 + P5 #214 on `main`  
**Previous release:** `v0.8.0`  
**Target branch:** `cursor/v09-p6-operator-sample-runbook-6c68`

This package implements **P6 only**: a bundled V0.9 operator sample that posts
the five KEY in P0 §3.1, seeds/verifies on **unmodified** `create_app`, and
documents the path. It does not recut formulas, does not mutate V0.7/V0.8
loaders, and does not authorize merge, tag, Release, or P7.

Companion documents:

- Overall plan: `docs/tasks/V0_9-version-plan.md`
- P0 contract: `docs/tasks/V0_9-P0-version-contract.md`
- V0.8 sample pattern (read-only): `docs/tasks/V0_8-P3-operator-sample-runbook-contract.md`

## 0. Contract identity and governance

```text
TASK=V09_P6_OPERATOR_SAMPLE_RUNBOOK_R1
PARENT_ISSUE=213
PARENT_CONTRACT=docs/tasks/V0_9-P0-version-contract.md
GOVERNANCE_OWNER=V0.9
BASE_MAIN_SHA=567732f7079ad04a9e53a585f5f40d208bf6f999
BASE_TREE=1d73aa7c59b41925e732d4cf0add3712ca32024d
BASE_SUBJECT=V0.9 P3: display persisted zone schemes, need vs actual, and docks (#218)
PREVIOUS_RELEASE=v0.8.0
TARGET_BRANCH=cursor/v09-p6-operator-sample-runbook-6c68
TARGET_FILE=docs/tasks/V0_9-P6-operator-sample-runbook-contract.md
TARGET_PR_STATE=DRAFT

V09_P6_IMPLEMENTATION_AUTHORIZED=YES
V09_P1_IMPLEMENTATION_AUTHORIZED=NO
V09_P2_IMPLEMENTATION_AUTHORIZED=NO
V09_P3_IMPLEMENTATION_AUTHORIZED=NO
V09_P4_IMPLEMENTATION_AUTHORIZED=NO
V09_P5_IMPLEMENTATION_AUTHORIZED=NO
V09_P7_IMPLEMENTATION_AUTHORIZED=NO
FORMULA_RECUT_AUTHORIZED=NO
COOLING_LOAD_FORMULA_RECUT=NO
AILY_LIVE_IMPLEMENTATION=NO
PRODUCTION_RBAC_CLAIM=NO
VUE_ENGINEERING_FORMULAS=NO
CAD_BIM_CONSTRUCTION_DRAWINGS=NO
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
RELEASE_PUBLICATION_AUTHORIZED=NO
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

P0 may still record `V09_P6_IMPLEMENTATION_AUTHORIZED=NO`. This file
overrides that for the sample/runbook package only. Do not edit P0.

## 1. Objective

On unmodified `create_app`:

```text
POST /api/v1/projects
 → POST .../five-stage-execution (operator_process_input + idempotency_key)
 → P1 assembler expands V0.9 five KEY into EngineeringInputBundleV1
 → five canonical stages persist (P2 zone plan includes shipping_channel
    and dual precooling schemes)
 → draft export without review (P4)
 → optional verify-path trust loop: trusted TestClient mark_reviewed /
    approve / formal export
```

The manifest contains **only** `OperatorProcessInputV1` 1.1.0 five KEY
leaves plus project metadata and `idempotency_key`. It must **not**
contain `engineering_input_bundle`.

## 2. Frozen sample identity

| Item | Frozen value |
| --- | --- |
| Sample id | `v09-process-input` |
| Manifest | `samples/v09-process-input/manifest.json` |
| Loader module | `backend/src/cold_storage/bootstrap/v09_sample_loader.py` |
| Trusted actor (TestClient seam) | `v09-local-trusted-reviewer` |
| Untrusted actor | `system` |
| Production weight revision | `wsr-production-default-v1` |
| Production scheme profile | `balanced` |

### 2.1 Operator KEY values (frozen; same literals as P1 sqlite integration)

```text
schema_id: OperatorProcessInputV1
schema_version: 1.1.0
```

| Leaf | Value | Unit |
| --- | --- | --- |
| `daily_inbound_mass_kg` | 20000 | kg/day |
| `finished_storage_days` | 7 | day |
| `frozen_storage_days` | 10 | day |
| `main_packaging_storage_days` | 4 | day |
| `auxiliary_packaging_storage_days` | 12 | day |

Project metadata: name **V0.9 算子最小输入示例项目**, location **山东**,
product_category **blueberry**, idempotency_key **v09-process-input-initial**.

Manifest MUST NOT contain:

```text
engineering_input_bundle
working_time_h_per_day
packaging_storage_days
precooling_required_ratio
```

### 2.2 Assembler / HTTP rules

Clone the V0.8 P3 loader **pattern** into a new module. Do **not** import
`v08_sample_loader` as a required runtime dependency. Do **not** edit
`v07_sample_loader.py` or `v08_sample_loader.py`.

Loader posts `operator_process_input` (not `engineering_input_bundle`) to
`POST .../five-stage-execution`. Demo catalog leaves stay
`requires_review=true`. Precooling rooms may still receive the v05 freezer
envelope demo package (`COOLING_LOAD_FORMULA_RECUT=NO`).

Public API families:

- `POST/GET /api/v1/projects/**`
- `POST .../five-stage-execution` with `operator_process_input`
- `POST .../production-scheme-runs`
- `POST/GET /api/v1/reports/**` including `mode=draft` and `mode=formal` render

**Forbidden loader paths:** `planning-run`, legacy `scheme-runs` as report
authority, `GET /api/v1/demo/scheme-comparison`, Alembic inside the loader.

### 2.3 Coexistence

`v07-trust-loop`, `v08-process-input`, and `v09-process-input` coexist.
Existing `seed-v07-sample` / `verify-v07-sample` / `seed-v08-sample` /
`verify-v08-sample` targets must remain.

### 2.4 Draft vs formal on the verify path

P4 policy: draft export is independent of review. P6 verify MUST:

1. After report generate (status still draft/generated), render **draft**
   zh-CN and en-US DOCX+PDF (`mode=draft`) **without** `mark_reviewed`.
2. Then, only on the verify/trust-loop path, use trusted TestClient actor
   `v09-local-trusted-reviewer` for `mark_reviewed` → `approve` → **formal**
   zh-CN/en-US DOCX+PDF. This is **not** production RBAC.
3. Untrusted actor `system` must fail-closed on `mark_reviewed`.

## 3. Makefile targets (P6 owns additive lines only)

| Target | Purpose |
| --- | --- |
| `seed-v09-sample` | Seed via `v09_sample_loader` |
| `verify-v09-sample` | Full verify (five-stage + draft export + trust loop) |
| `smoke-v09-local` | Alias for `verify-v09-sample` |

Add those names to `.PHONY`. Do not rewrite unrelated targets.

## 4. Exclusive allowlist

P6 allowlist = P0 §7.7 ∪ architecture test.

```text
V09_P6_FILE_ALLOWLIST
docs/tasks/V0_9-P6-operator-sample-runbook-contract.md
samples/v09-process-input/manifest.json
backend/src/cold_storage/bootstrap/v09_sample_loader.py
docs/runbooks/v09-process-input-runbook.md
Makefile
backend/tests/integration/v09_p6_operator_fixtures.py
backend/tests/integration/test_v09_p6_operator_sample_sqlite.py
backend/tests/integration/test_v09_p6_operator_sample_postgresql.py
backend/tests/architecture/test_v09_p6_operator_sample_contract.py
```

`samples/v09-process-input/**` in P0 is this manifest (and only this
directory). Do not add extra sample assets unless required to seed.

Architecture tests:

- Contract flags present (`BASE_MAIN_SHA`, `V09_P6_IMPLEMENTATION_AUTHORIZED=YES`,
  `MERGE_AUTHORIZED=NO`, `AILY_LIVE_IMPLEMENTATION=NO`).
- P0 §7.7 paths (treating `samples/v09-process-input/**` as the manifest
  file) ⊆ this allowlist.
- `git diff --name-only origin/main` plus untracked stays on this
  allowlist. Enforce only when the branch name contains `v09-p6-operator`
  (`GITHUB_HEAD_REF` in CI). Wrap long `skipif` reasons so ruff E501
  cannot fail.
- Loader and tests do not edit `zone_planning.py` / `cooling_load.py`.
- Manifest five KEY only; no `engineering_input_bundle`.

Gate any leftover merged architecture tests that assert “current branch
diff vs origin/main must look like package N” with skipif, same as P2/P3.
Do not weaken on-disk formula identity checks.

## 5. Hard non-goals

```text
V07_SAMPLE_LOADER_MUTATION=NO
V08_SAMPLE_LOADER_MUTATION=NO
BOOTSTRAP_APP_MUTATION=NO
ZONE_PLANNING_PY_EDIT=NO
COOLING_LOAD_FORMULA_RECUT=NO
VUE_MUTATION=NO
FORMULA_RECUT_AUTHORIZED=NO
AILY_LIVE_IMPLEMENTATION=NO
PRODUCTION_RBAC_CLAIM=NO
V05_V06_V07_V08_TEST_ASSERTION_MUTATION=NO
ALEMBIC_INSIDE_LOADER=NO
PLANNING_RUN=NO
```

P6 must not:

- edit Vue, `zone_planning.py`, cooling/equipment/power/investment
- mutate `test_v05_*` / `test_v06_*` / `test_v07_*` / `test_v08_*`
  assertion bodies
- claim production RBAC or live Aily
- implement P7 controlled-acceptance matrix

If Makefile/living tests fail because `.PHONY` must list the new
targets, fix on this PR (standing 红了就修). If a merged architecture
test still requires a previous package’s diff shape, skipif-gate it to
that package’s branch and add the file to this allowlist in the same
commit.

## 6. Tests required

| Surface | Must prove |
| --- | --- |
| Manifest | V0.9 five KEY only; schema 1.1.0; no bundle; no V0.8 removed KEY |
| SQLite + PostgreSQL | unmodified `create_app` seed persists five canonical calculators |
| Zone snapshot | persisted `cold_room_zone_plan` includes `shipping_channel`; primary/secondary precooling `schemes` length 2 |
| Fail-closed | missing operator KEY → `MISSING_ENGINEERING_PARAMETER`; zero partial canonical chain |
| Draft export | `mode=draft` render succeeds before `mark_reviewed` |
| Trust loop | trusted actor can complete formal; untrusted `system` fail-closes `mark_reviewed` |
| Architecture | allowlist vs origin/main on the P6 branch |

## 7. Acceptance criteria

```text
V09_SAMPLE_FIVE_KEY_ONLY=PASS
V09_SCHEMA_VERSION_1_1_0=PASS
NO_ENGINEERING_INPUT_BUNDLE_IN_MANIFEST=PASS
SEED_ON_UNMODIFIED_CREATE_APP=PASS
FIVE_CANONICAL_CALCULATORS_PERSIST=PASS
SHIPPING_CHANNEL_IN_PERSISTED_ZONES=PASS
DUAL_PRECOOL_SCHEMES_IN_PERSISTED_JSON=PASS
DRAFT_EXPORT_WITHOUT_REVIEW=PASS
FORMAL_EXPORT_STILL_GATED=PASS
UNTRUSTED_MARK_REVIEWED_FAIL_CLOSED=PASS
MISSING_OPERATOR_KEY_FAIL_CLOSED=PASS
V07_V08_SAMPLE_LOADERS_UNCHANGED=PASS
MAKEFILE_V07_V08_TARGETS_UNCHANGED=PASS
AILY_LIVE_IMPLEMENTATION=NO
PRODUCTION_RBAC_CLAIM=NO
DRAFT=YES
MERGE_AUTHORIZED=NO
TAG_PUBLICATION_AUTHORIZED=NO
```

Authoritative test surface:

```text
backend/tests/architecture/test_v09_p6_operator_sample_contract.py
backend/tests/integration/test_v09_p6_operator_sample_sqlite.py
backend/tests/integration/test_v09_p6_operator_sample_postgresql.py
```

## 8. Verification

```text
cd backend && uv run ruff format tests/architecture/test_v09_p6_operator_sample_contract.py \
  tests/integration/v09_p6_operator_fixtures.py \
  tests/integration/test_v09_p6_operator_sample_sqlite.py \
  tests/integration/test_v09_p6_operator_sample_postgresql.py \
  src/cold_storage/bootstrap/v09_sample_loader.py
cd backend && uv run ruff check <same files>
cd backend && PYTHONPATH=src uv run pytest -q \
  tests/architecture/test_v09_p6_operator_sample_contract.py \
  tests/integration/test_v09_p6_operator_sample_sqlite.py
```

PostgreSQL test requires the CI postgres job (or local compose). Do not
skip writing it.

## 9. Not in P6

- Vue display (P3, merged)
- Draft-vs-formal UI copy (P4, merged)
- Workbench layout (P5, merged)
- Controlled acceptance matrix (P7)
- Tag / Release / merge authorization

## 10. Revision history

| Rev | Date | Change |
| --- | --- | --- |
| R1 | 2026-08-27 | P6 sample + runbook at `567732f` / P3 #218 / `v0.8.0` |
