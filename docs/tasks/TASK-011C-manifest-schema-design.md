# TASK-011C Manifest Schema Implementation Design

Status: IMPLEMENTED (working tree, awaiting commit)
Authority lineage: Issue #20 comment 4959798219 (original C-1 authorization)
                  Issue #20 comment 4960173798 (.gitignore amendment)
Contract: docs/tasks/TASK-011C-remaining-evaluation-scenarios-contract.md
Branch: codex/task-011c-c1-manifest-canonicalization
Base SHA: 1b532431d78346dc3e45601ee6df6fc1974f7e05

This document is the independent design record for the C-1 manifest /
canonicalization foundation implementation, written from the frozen contract
plus the actual C-1 working tree. It does not copy or extract PR #21 files.

## 1. Authority and lineage

```
AUTHORITY_COMMENT_ID=4959798219
GITIGNORE_AMENDMENT_COMMENT_ID=4960173798
BASE_SHA=1b532431d78346dc3e45601ee6df6fc1974f7e05
BRANCH=codex/task-011c-c1-manifest-canonicalization
PR_BASE=main
PR_MODE=DRAFT
```

C-1 only. C-2 (compare / evaluate / runners) and C-3 (expected-output
authoring) are NOT authorized and are out of scope for this round.

## 2. Schema versioning (D5, frozen)

```
MANIFEST_SCHEMA_VERSION=1.0   # literal string, NOT numeric
REJECT_NUMERIC_1_0=YES
REJECT_UNKNOWN_VERSION=YES
REJECT_MISSING_VERSION=YES
```

`MANIFEST_SCHEMA_VERSION` is a string literal "1.0". The loader rejects:
- `1.0` (float), `1` (int) — must be exactly the JSON string `"1.0"`.
- any other value (`"0.9"`, `"2.0"`, `"1.0.0"`, etc.).
- missing `schema_version` field.

## 3. Manifest schema path and resource loading (D7, D8)

```
MANIFEST_SCHEMA_PATH=backend/src/cold_storage/evaluation/schema/manifest.schema.json
RESOURCE_LOADING=importlib.resources.files
PACKAGE=cold_storage.evaluation.schema
LOADER_FUNCTION=load_manifest_schema_text
```

Runtime access is exclusively via:
```python
importlib.resources.files("cold_storage.evaluation.schema").joinpath(
    "manifest.schema.json"
)
```

Forbidden fallbacks (must remain absent in code, configuration, and tests):
- `Path(__file__).parent ...` (anywhere referencing the schema).
- repository-relative paths.
- `cwd`-relative paths.
- top-level `evaluation/` schema copy.
- second `manifest.schema.json` anywhere in the repository.

## 4. Manifest loader (D6, frozen)

```
MANIFEST_LOADER=backend/src/cold_storage/evaluation/manifest.py::load_and_validate_manifest
SINGLE_LOADER=YES
```

`manifest.py` exposes exactly one public loader entry point. It performs
two-layer validation per D2:
1. JSON Schema validation (D5/D7/D8).
2. Application-level recursive strict-value validation (D2 allow-list).

Defined exception subclasses (lives in `manifest.py` to keep ownership
within the allowlist; `errors.py` is unmodified per C-1 allowlist):
- `ManifestSchemaVersionError` (D5)
- `ManifestUnsupportedJSONValueError` (D2)
- `ManifestMissingFieldError`
- `ManifestUndeclaredFieldError`
- `ManifestDuplicateFixtureIDError` / `ManifestDuplicateScenarioIDError`
- `ManifestMissingFileError`
- `ManifestMalformedJSONError`

Forbidden:
- CLI-side manifest loading.
- test-side manifest loading re-implementation.
- second manifest loader symbol.

## 5. Canonicalization (D1, D2, D3, D4)

```
CANONICALIZER=backend/src/cold_storage/evaluation/canonicalization.py::canonicalize_production_outputs
SIGNATURE=(value, *, excluded_paths) -> CanonicalBytes
SINGLE_CANONICALIZER=YES
```

Properties (from contract §10.1–10.4):
- Strict JSON value domain only (D2 allow-list).
- Fail closed on `NaN`, `Infinity`, `-Infinity`, `Decimal`, `datetime`,
  `date`, `time`, `tuple` (as array), `set`/`frozenset`, `bytes`/
  `bytearray`, custom classes, non-string mapping keys, unsupported
  enums, implicit `str(value)`.
- Object keys must be strings, sorted deterministically.
- Array order is preserved.
- Decimal fields must be pre-serialized as canonical strings before
  canonicalization; the canonicalizer does not call `float()` or
  quantize implicitly.
- Canonical byte serialization is deterministic UTF-8 JSON with fixed
  separators and sorted object keys.

Exclusion set (D3, binding):

```
D3_V1_EXCLUDED_JSON_PATHS=[]   # empty, FROZEN
NO_WILDCARD_EXCLUSIONS=YES
NO_ADDITIONAL_EXACT_PATHS=YES
```

Any future exclusion requires a contract amendment and Charles
authorization; C-1 must not add paths.

Numeric policy (D4):

```
NUMERIC_POLICY=EXACT_EQUALITY_DEFAULT
GLOBAL_FLOAT_TOLERANCE=FORBIDDEN
UNDECLARED_QUANTIZATION=FORBIDDEN
UNDECLARED_TOLERANCE=FORBIDDEN
```

No global float tolerance. No per-field tolerance unless separately
Charles-approved.

## 6. Path safety

Path resolution for manifest-declared resources is performed exclusively
through `backend/src/cold_storage/evaluation/paths.py`. The module rejects:
- absolute paths,
- `..` traversal,
- symlink escape where applicable,
- repository / package root escape,
- empty or otherwise invalid paths,
- undeclared external resources,
- cwd-dependent resolution.

`.gitignore` is NOT modified by path safety; the amendment in
`# §四 amendment` covers tracked-file visibility only.

## 7. Typed models (C-1 subset)

`backend/src/cold_storage/evaluation/models.py` provides Pydantic typed
models for the C-1 surface only:
- `Manifest`
- `ScenarioDeclaration`
- `FixtureReference`
- `ExpectedOutputReference`
- `ComparisonPolicy`
- `SchemaVersion` (literal `"1.0"` via `Literal["1.0"]`)
- `ManifestPath` (resource reference)

Models forbid unknown fields, preserve exact strings/enums, do not
coerce arbitrary values, do not accept numeric `schema_version`, and do
not introduce global float tolerance.

The full C-2 runner orchestration model is NOT implemented in C-1.

## 8. SQLite isolation foundation (C-1 subset)

`backend/src/cold_storage/evaluation/sqlite_scope.py` provides the
per-scenario SQLite isolation foundation only:
- scenario isolation,
- explicit cleanup,
- no stale DB reuse,
- no cross-scenario leakage,
- safe temporary paths,
- deterministic ownership.

The module does not run the full multi-scenario runner, does not
manufacture production ORM rows, does not duplicate `production_seeding.py`,
does not directly construct `CalculationRunRecord`, and does not bypass
production services.

## 9. Package distribution (D7, frozen)

`backend/pyproject.toml` declares (incremental, additive — no other
sections are modified):

```toml
[tool.setuptools.package-data]
"cold_storage.evaluation.schema" = ["manifest.schema.json"]
```

`uv.lock` is NOT modified.

## 10. C-1 allowlist and C-2/C-3 non-authorization

### 10.1 C-1 allowed tracked paths (this round)

```
backend/src/cold_storage/evaluation/canonicalization.py
backend/src/cold_storage/evaluation/manifest.py
backend/src/cold_storage/evaluation/models.py
backend/src/cold_storage/evaluation/paths.py
backend/src/cold_storage/evaluation/sqlite_scope.py
backend/src/cold_storage/evaluation/schema/__init__.py
backend/src/cold_storage/evaluation/schema/manifest.schema.json
backend/tests/evaluation/test_manifest_schema.py
backend/tests/evaluation/test_manifest_loader.py
backend/tests/evaluation/test_canonicalization.py
backend/tests/evaluation/test_canonicalization_d1.py
backend/tests/evaluation/test_path_safety.py
backend/tests/evaluation/test_d2_strict_value_domain.py
backend/tests/evaluation/test_d3_excluded_paths_policy.py
backend/tests/evaluation/test_d4_numeric_exact.py
backend/tests/evaluation/test_d5_schema_version.py
backend/tests/evaluation/test_d6_manifest_loader.py
backend/tests/evaluation/test_d7_distribution.py
backend/tests/evaluation/test_d8_resource_loading.py
docs/tasks/TASK-011C-manifest-schema-design.md
backend/pyproject.toml   # D7 package-data addition only
.gitignore              # C-1 allowlist addition only
```

### 10.2 Not authorized in this round

- C-2: `compare.py`, `evaluate.py`, `json_path.py`, `runners/sqlite.py`,
  `runners/postgresql.py`.
- C-3: any expected-output authoring, sign-off, baseline golden mutation.
- `invalid_blocked` fixture / expected output authoring.
- `high_throughput_review` files.
- D9 production prerequisite.
- TASK-011D, Task 12.
- Issue #20 closure.
- PR #21 / PR #23 mutation.
- PR transition to Ready or merge.

## 11. Verification summary (working tree)

The following is the post-amendment working-tree result. Full execution
detail is in `/root/task-011c-c1-implementation-report.md` and the
current round's per-step logs under `/tmp/pr62-step*.log` equivalents
captured during this round.

```
FOCUSED_C1_TESTS=171 passed (16.65s)
RUFF_CHECK=PASS
RUFF_FORMAT_CHECK=PASS
MYPY=PASS
SOURCE_RESOURCE_LOAD=PASS     (importlib.resources, source checkout)
INSTALLED_PACKAGE_RESOURCE_LOAD=PASS   (built wheel installed in
                                          isolated venv at /tmp/pr62-iso-venv)
CWD_INDEPENDENCE=PASS
BASELINE_GOLDEN_UNCHANGED=YES
ADAPTER_UNCHANGED=YES
EXECUTE_UNCHANGED=YES
CLI_UNCHANGED=YES
ERRORS_UNCHANGED=YES
RUN_DIRECTORY_UNCHANGED=YES
PRODUCTION_CODE_UNCHANGED=YES
```

This document is the implementation design record. It does not authorize
C-2 or C-3 work, and it is not a sign-off on the C-1 contract itself.
