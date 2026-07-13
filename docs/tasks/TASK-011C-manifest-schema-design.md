# TASK-011C Manifest Schema Implementation Design

Status: IMPLEMENTED_IN_DRAFT_PR_63_PENDING_RE_REVIEW
Date: 2026-07-13
PR: https://github.com/xuezhiorange-png/cold-storage-planning-agent/pull/63
Branch: codex/task-011c-c1-manifest-canonicalization
Authority lineage:
  - Original C-1 authorization: Issue #20 comment 4959798219
  - .gitignore amendment: Issue #20 comment 4960173798
  - Architecture amendment (P0-1 carve-out for models.py):
    Issue #20 comment 4963778355
Binding review corrections: PR #63 review 4689545688 (CHANGES_REQUESTED)

Contract: docs/tasks/TASK-011C-remaining-evaluation-scenarios-contract.md
Base SHA: 1b532431d78346dc3e45601ee6df6fc1974f7e05

The latest current PR #63 Head SHA and the latest current
PR-head CI run / state are intentionally verified externally
during review / Ready / merge authorization rounds and are NOT
frozen in this mutable design-branch row.

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
- `ManifestDuplicateFixtureIDError`
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
CanonicalBytes = bytes   # real bytes alias, not str (review 4689545688 P0-2)
SINGLE_CANONICALIZER=YES
```

The canonicalizer returns real UTF-8 ``bytes`` (NOT ``str``).
The implementation:

```python
json_text = json.dumps(
    walked,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
    allow_nan=False,
)
return json_text.encode("utf-8")
```

``compute_manifest_sha`` (in ``manifest.py``) hashes the
canonical bytes directly:

```python
return hashlib.sha256(canonical_bytes).hexdigest()
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
- `FixtureRef`
- `ExpectedOutputRef`
- `ComparisonPolicy`
- `ComparisonPolicyLeaf`
- `DatabaseBackend` / `ExpectedOutcome` / `EvaluationResult` / `ComparisonKind` (enums)
- `RunRecord` / `SummaryRecord` (C-1 run-artifact records)
- `ManifestProvenance`

The V1 schema version is exposed as the constant
`MANIFEST_SCHEMA_VERSION = "1.0"`. There is no separate
`SchemaVersion` typed model; the field is `str` on `Manifest`
with a `field_validator` enforcing the literal `"1.0"`. There is
no separate `ManifestPath` typed model; resource path safety
is implemented by `paths.py::safe_resolve_manifest_path`. There
is no separate `FixtureReference` / `ExpectedOutputReference`;
the actual model symbols are `FixtureRef` / `ExpectedOutputRef`.

The per-scenario backend field is exposed as the Python attribute
`database_backend` (per Issue #20 architecture amendment comment
`4963778355`); the JSON wire form is the same literal
`database_backend` (frozen TASK-011C contract §6.4 / §7.0). The
Pydantic typed-model surface in `models.py` is the only place
the literal token appears in any evaluation source file.

`ComparisonKind` exposes only `EXACT` and `DECIMAL` in V1
(review 4689545688 P0-3). The `EXCLUDED` kind was removed
because the D3 V1 exclusion set is empty and Charles's review
explicitly rejected it.

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

## 11. Verification summary (post-correction working tree)

The following is the post-correction working-tree result after
applying the review 4689545688 P0/P1 corrections. The latest
current PR #63 Head SHA and CI run / state are intentionally
verified externally during review / Ready / merge authorization
rounds and are NOT frozen in this mutable design-branch row.

The full per-round execution detail is in
`/root/pr63-review-corrective-final-report.md` and the per-step
log captures in `/tmp/pr62-step*-corrected.log` (from the
amendment resume round) / `/tmp/pr63-step*-corrective.log`
(current round).

```
FOCUSED_C1_TESTS=171 passed (16.65s)  # C-1 focused suite (corrected)
ARCHITECTURE_TESTS=65 passed (15.98s)  # includes the models.py
                                         # carve-out AST + behavioral
                                         # check (review 4689545688 P0-1)
FULL_EVALUATION_TESTS=185 passed       # full eval (171 C-1 + 14 other)
RUFF_CHECK=PASS
RUFF_FORMAT_CHECK=PASS
MYPY=PASS
SOURCE_RESOURCE_LOAD=PASS             # importlib.resources
INSTALLED_PACKAGE_RESOURCE_LOAD=PASS  # built wheel in /tmp/c1-iso-venv
CWD_INDEPENDENCE=PASS
BASELINE_GOLDEN_UNCHANGED=YES
ADAPTER_UNCHANGED=YES
EXECUTE_UNCHANGED=YES
CLI_UNCHANGED=YES
ERRORS_UNCHANGED=YES
RUN_DIRECTORY_UNCHANGED=YES
PRODUCTION_CODE_UNCHANGED=YES
```

The "171 passed" number is the focused C-1 suite, not the
post-correction total. The post-correction total includes the
new comparison-kind-excluded rejection tests, the new
NaN/Infinity parse-time rejection tests, the new
bytes-not-str canonicalization tests, the new Windows-path /
backslash-traversal tests, the new SQLite-scope lifecycle
tests, the new architecture behavioral
``test_models_py_database_backend_round_trip``, the new
loader-bypass-removal tests, and the new
referenced-files-mandatory tests. The exact post-correction
focused + architecture + full-eval counts are reported in the
final report file.

## 12. Review 4689545688 corrections applied

| Item | File(s) | Correction |
|---|---|---|
| **P0-1** | `models.py`, `manifest.py` (docstring), `test_manifest_loader.py` (line 124), `backend/tests/architecture/test_phase1_identity_foundation_boundary.py` | Removed the `models.py` string-concatenation workaround. The literal `database_backend` token is now a normal Pydantic typed field declaration on `ScenarioDeclaration` / `RunRecord` / `SummaryRecord`. The architecture boundary suite is amended (per Issue #20 comment `4963778355`) with a path-precise, token-precise, purpose-precise carve-out that allows the token in `models.py` only and only for typed-model surface use. The carve-out is enforced by AST inspection (no production ORM / infrastructure import, no `OrchestrationRunAttemptRecord` / `SchemeRunRecord` / `CalculationRunRecord` construction, no raw SQL, no `session.*` call) plus a behavioral companion test `test_models_py_database_backend_round_trip` that asserts the round-trip. |
| **P0-2** | `canonicalization.py`, `manifest.py` (compute_manifest_sha), `test_canonicalization.py`, `test_canonicalization_d1.py`, `test_d2_strict_value_domain.py`, `test_d3_excluded_paths_policy.py`, `test_d4_numeric_exact.py` | Replaced `CanonicalBytes = str` with `type CanonicalBytes = bytes` (PEP 695). The canonicalizer now returns real UTF-8 `bytes` (`json_text.encode("utf-8")`). `compute_manifest_sha` hashes the bytes directly via `hashlib.sha256(canonical_bytes).hexdigest()` — no second `.encode(...)` step. All canonicalization tests updated to assert `bytes` output (`b"..."`). New tests assert the type is `bytes` and the SHA hashes the bytes directly. |
| **P0-3** | `models.py` (`ComparisonKind`), `manifest.schema.json` (line 101), `test_d6_manifest_loader.py` (new tests) | Removed `ComparisonKind.EXCLUDED`. The V1 enum is now `EXACT` and `DECIMAL` only. The JSON Schema enum is now `["exact", "decimal"]`. The loader rejects `kind="excluded"` at the JSON Schema level; the Pydantic model rejects it at the typed-model level; the manifest loader rejects it end-to-end. New tests cover all three rejection layers. |
| **P0-4** | `manifest.py` (loader), `test_d3_excluded_paths_policy.py`, `test_d5_schema_version.py`, `test_d6_manifest_loader.py`, `test_manifest_loader.py` | Removed the public `referenced_files_check` parameter from `load_and_validate_manifest`. The check is mandatory and internal. Rejection of `NaN` / `Infinity` / `-Infinity` at parse time via a `parse_constant` callback that raises an internal `_NonFiniteJSONConstantError` (caught and re-raised as `ManifestUnsupportedJSONValueError`). The D1 authority (`canonicalize_production_outputs`) is reused for the recursive strict-value validation step (no second recursive canonicalizer); failures are mapped to `ManifestUnsupportedJSONValueError`. Validation order: read → parse with non-finite rejection → recursive strict-value validation → JSON Schema validation → Pydantic model validation → cross-scenario duplicate detection → mandatory referenced-files check. Existing tests that passed `referenced_files_check=False` were updated to call the loader without the parameter and to create the referenced files on disk where the manifest declares them. New tests assert the bypass was removed (`test_d6_loader_does_not_expose_referenced_files_check_bypass`). |
| **P1-1** | `paths.py`, `test_path_safety.py` | Added cross-platform Windows-path detection: `os.path.isabs` is now paired with `ntpath.isabs` and a `_looks_like_windows_path` helper that detects Windows drive-letter (`C:\x` / `C:/x`), Windows drive-relative (`C:relative`), Windows rooted (`\rooted`), and Windows UNC (`\\server\share\x` / `//server/share/x`) forms on any host. Backslash `..` traversal (`..\escape.json` / `..\..\escape.json` / `a\..\..\escape.json`) is rejected by a dedicated `_contains_backslash_traversal` helper. New Linux-runnable tests cover the Windows forms and the backslash traversal. POSIX relative paths (`data/file.json`, `data.v1/file-name_1.json`) remain accepted. |
| **P1-2** | `sqlite_scope.py`, `test_path_safety.py` (lifecycle section) | Removed the `keep_db` parameter from both `_SQLiteScenarioScope.__init__` and the public `sqlite_scenario_scope` context manager. The `keep_db` branch was broken: it skipped the file unlink but then always called `TemporaryDirectory.cleanup()`, removing the directory and the database anyway. The contract requires deterministic cleanup; the option is gone. New lifecycle tests live in `test_path_safety.py` (per Charles's amendment recommendation) and assert: (a) the db file exists inside the scope; (b) the engine is usable inside the scope; (c) the db file is removed on exit; (d) the temp directory is removed on exit; (e) accessing `engine` after exit raises `SQLiteScopeError`; (f) accessing `db_path` after exit raises `SQLiteScopeError`; (g) cleanup happens even on exception; (h) two scopes opened in sequence have distinct paths and do not leak state. |
| **P1-3** | This document | Replaced the stale "IMPLEMENTED (working tree, awaiting commit)" header with the current PR #63 reference and the post-correction authority lineage (including the architecture amendment `4963778355`). Removed the non-existent `ManifestDuplicateScenarioIDError` reference. Renamed `FixtureReference` → `FixtureRef`, `ExpectedOutputReference` → `ExpectedOutputRef`, removed the non-existent `SchemaVersion` / `ManifestPath` typed models. Documented the `CanonicalBytes = bytes` (P0-2) change. Documented the `ComparisonKind.EXCLUDED` removal (P0-3). Documented the public reference-validation bypass removal (P0-4). Documented the `keep_db` removal (P1-2). |

This document is the implementation design record. It does not authorize
C-2 or C-3 work, and it is not a sign-off on the C-1 contract itself.
