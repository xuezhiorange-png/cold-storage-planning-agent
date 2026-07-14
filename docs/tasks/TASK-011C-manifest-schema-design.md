# TASK-011C Manifest Schema Implementation Design

Status: CORRECTED_IN_DRAFT_PR_63_PENDING_SIXTH_RE_REVIEW
Date: 2026-07-13
PR: https://github.com/xuezhiorange-png/cold-storage-planning-agent/pull/63
Branch: codex/task-011c-c1-manifest-canonicalization
Authority lineage:
  - Original C-1 authorization: Issue #20 comment 4959798219
  - .gitignore amendment: Issue #20 comment 4960173798
  - Architecture amendment (P0-1 carve-out for models.py):
    Issue #20 comment 4963778355
Binding review corrections:
  - First review: PR #63 review 4689545688
    - Source review platform state: COMMENTED
    - Source review body verdict: TASK_011C_C1_REVIEW_CHANGES_REQUESTED
  - Second re-review: PR #63 review 4689835238
    - Second re-review platform state: COMMENTED
    - Second re-review body verdict: TASK_011C_C1_RE_REVIEW_CHANGES_REQUESTED
  - Strict re-execution authority: Issue #20 comment 4964070401
  - Third re-review: PR #63 review 4690110096
    - Third re-review platform state: COMMENTED
    - Third re-review body verdict: TASK_011C_C1_THIRD_RE_REVIEW_CHANGES_REQUESTED
  - Full third re-review findings: PR #63 conversation comment 4964388017
  - Fourth re-review: PR #63 review 4690297649
    - Fourth re-review platform state: COMMENTED
    - Fourth re-review body verdict: TASK_011C_C1_FOURTH_RE_REVIEW_CHANGES_REQUESTED
  - Fifth re-review: PR #63 review 4690695361
    - Fifth re-review platform state: COMMENTED
    - Fifth re-review body verdict: TASK_011C_C1_FIFTH_RE_REVIEW_CHANGES_REQUESTED

Note on platform state vs body verdict:
  This repository is personally maintained. GitHub records
  self-review submissions as COMMENTED; the binding correction
  disposition is carried by the review body verdict (which is
  TASK_011C_C1_REVIEW_CHANGES_REQUESTED /
  TASK_011C_C1_RE_REVIEW_CHANGES_REQUESTED /
  TASK_011C_C1_THIRD_RE_REVIEW_CHANGES_REQUESTED /
  TASK_011C_C1_FOURTH_RE_REVIEW_CHANGES_REQUESTED /
  TASK_011C_C1_FIFTH_RE_REVIEW_CHANGES_REQUESTED). The body
  verdict is the binding signal, NOT the platform state.

Contract: docs/tasks/TASK-011C-remaining-evaluation-scenarios-contract.md
Base SHA: 1b532431d78346dc3e45601ee6df6fc1974f7e05

The latest current PR #63 Head SHA, the latest current
PR-head CI run / state, per-round test counts, and per-round
external evidence (per-round reports, log captures, wheel
artifacts, machine-local transient artifacts) are intentionally
verified externally during the corresponding review / Ready /
merge authorization rounds and are NOT frozen in this mutable
design-branch row. Per-round execution evidence is external to
this frozen design record.

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

### 10.1 C-1 allowed tracked paths

The C-1 allowlist is composed of two parts: the original
22 paths authorized by Issue #20 comment 4959798219, plus
1 additional path authorized by the architecture amendment
in Issue #20 comment 4963778355 (the
`test_phase1_identity_foundation_boundary.py` carve-out
test for the `database_backend` typed-model field). The
total C-1 correction path count is 23.

```
ORIGINAL_C1_PATHS=22
ARCHITECTURE_AMENDMENT_PATHS=1
TOTAL_C1_CORRECTION_PATHS=23
```

#### 10.1.1 Original C-1 paths (22, per Issue #20 comment 4959798219)

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

#### 10.1.2 Architecture amendment path (1, per Issue #20 comment 4963778355)

```
backend/tests/architecture/test_phase1_identity_foundation_boundary.py
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

## 11. Required validation gates

The C-1 implementation must pass the following validation
gates. Specific test counts, exit codes, CI run IDs, and
per-round execution evidence are intentionally NOT frozen in
this mutable design-branch row; they are verified externally
during the corresponding review / Ready / merge authorization
round.

```
REQUIRED_VALIDATION_GATES:
  - focused C-1 tests
  - exact architecture guard tests (P0 of review 4690110096)
  - full evaluation tests
  - full architecture tests
  - ruff check
  - ruff format check
  - mypy
  - source resource load
  - installed-package resource load
  - cwd-independence
  - SQLite CI
  - PostgreSQL CI
```

### 11.1 Frozen design facts (NOT mutable per-round)

The following are frozen design facts that survive per-round
corrections and review rebases:

- CanonicalBytes = bytes (canonicalizer returns actual
  UTF-8 bytes; the value is already encoded and may be
  passed directly to `hashlib.sha256`).
- `D3_V1_EXCLUDED_JSON_PATHS=[]` (V1 exclusion set is empty;
  non-empty raises).
- `ComparisonKind.EXCLUDED` is absent from V1 (rejected at
  schema, model, and loader levels).
- The public `referenced_files_check` loader bypass is
  absent (P0-4 of review 4689545688); the check is mandatory.
- NaN / Infinity / -Infinity are rejected at JSON parse
  time via `parse_constant` (P0-4 of review 4689545688).
- Relative manifest paths are rejected before any file I/O
  (P0-3 of review 4689835238); the loader never resolves a
  relative input against cwd.
- `keep_db` constructor / public function arguments are
  removed; cleanup is mandatory and deterministic
  (P1-2 of review 4689545688).
- The literal `database_backend` token in `models.py` is
  restricted to the exact allowlist (P0 of review
  4690110096): three `database_backend: DatabaseBackend`
  field declarations in `ScenarioDeclaration` /
  `RunRecord` / `SummaryRecord` and the two
  `s.database_backend.value` reads in
  `Manifest._validate_unique_scenarios`. No `Field(alias=
  ...)`, no `Field(serialization_alias=...)`, no
  forward-compat branches.

### 11.2 Per-round external evidence

Per-round execution evidence (per-round reports, log
captures, wheel artifacts, scratch files, etc.) lives
outside this repository. The mutable design-branch row
deliberately does NOT reference per-host scratch paths
or machine-local transient artifacts, and does NOT
record specific per-round test counts; those are
re-derived on demand by the next review / Ready / merge
authorization round.

```
PER_ROUND_EVIDENCE=EXTERNAL
```

## 12. Architecture guard exact-allowlist contract (P0 of review 4690110096)

The `database_backend` token carve-out in
`models.py` is enforced by an exact AST allowlist. Every
code-level `database_backend` occurrence in `models.py`
must match one of two exact shapes; all other shapes are
REJECTED.

### 12.1 AUTHORIZED_FIELD (3 occurrences)

An `ast.AnnAssign` of the form
`database_backend: DatabaseBackend` (no default value),
inside one of the approved field classes
`ScenarioDeclaration`, `RunRecord`, `SummaryRecord`, at
class body scope (not inside a method or function body).

```
NODE_TYPE=ast.AnnAssign
TARGET=ast.Name("database_backend")
ANNOTATION=ast.Name("DatabaseBackend")
VALUE=None
CONTAINING_CLASS in {ScenarioDeclaration, RunRecord, SummaryRecord}
CONTAINING_FUNCTION=None
```

### 12.2 AUTHORIZED_VALIDATOR_READ (2 occurrences)

An `ast.Attribute` reading `s.database_backend`, whose
parent is `ast.Attribute(attr="value")`, inside the exact
`Manifest._validate_unique_scenarios` method decorated
with `@field_validator("scenarios")`.

```
NODE_TYPE=ast.Attribute
ATTR="database_backend"
VALUE=ast.Name("s")
PARENT=ast.Attribute(attr="value")
CONTAINING_CLASS=Manifest
CONTAINING_FUNCTION=_validate_unique_scenarios
DECORATOR=field_validator("scenarios")
```

### 12.3 REJECTED (everything else)

Any other shape is REJECTED. The classifier is not
forward-compatible: `Field(alias="database_backend")`,
`Field(serialization_alias="database_backend")`, ordinary
method attribute reads, unrelated validators, wrong
receivers, missing `.value`, etc. are all rejected.
```

### 12.4 Exact occurrence cardinality contract (P0-1 of review 4690297649)

The real `models.py` MUST have exactly the following
code-level `database_backend` occurrence counts; no more,
no fewer. If the real model surface ever grows a 4th
typed field or a 3rd validator read, this contract and
the architecture guard test file's constants MUST be
updated in lockstep — never silently widened.

```
AUTHORIZED_FIELD_COUNT=3
AUTHORIZED_VALIDATOR_READ_COUNT=2
TOTAL_DATABASE_BACKEND_OCCURRENCE_COUNT=5
REJECTED_OCCURRENCE_COUNT=0
```

Per-class field occurrence counter MUST be exactly:

```
Counter(
    {
        "ScenarioDeclaration": 1,
        "RunRecord": 1,
        "SummaryRecord": 1,
    }
)
```

### 12.5 Exact decorator contract

The Manifest validator MUST carry the exact
`@field_validator("scenarios")` decorator, with no other
positional arguments and no keyword arguments.

```
DECORATOR_FUNCTION=field_validator
POSITIONAL_ARGUMENT_COUNT=1
POSITIONAL_ARGUMENT_0="scenarios"
KEYWORD_ARGUMENT_COUNT=0
```

Any of the following is REJECTED:

* `@field_validator("other", "scenarios")`
* `@field_validator("scenarios", "other")`
* `@field_validator("scenarios", mode="before")`
* `@field_validator(*FIELDS)`
* bare non-`Call` decorators.

### 12.6 Exact full decorator stack contract (P0 of fifth re-review)

The fourth re-review (PR #63 review 4690297649) closed the
single-decorator argument shape (§12.5) but the fifth
re-review (PR #63 review 4690695361) found that the
production validator's `decorator_list` was not yet
asserted as a complete stack. Per the fifth re-review:

> The validator is authorized only when its complete
> `decorator_list` contains exactly two nodes in the frozen
> order. Merely containing an exact
> `@field_validator("scenarios")` call is insufficient.

The full frozen stack is:

```
EXACT_DECORATOR_COUNT=2
EXACT_DECORATOR_ORDER=field_validator_then_classmethod
DECORATOR_INDEX_0=field_validator("scenarios")
DECORATOR_INDEX_1=classmethod
EXTRA_DECORATORS_ALLOWED=NO
DUPLICATE_DECORATORS_ALLOWED=NO
REVERSED_ORDER_ALLOWED=NO
MISSING_CLASSMETHOD_ALLOWED=NO
```

The validator function is
`Manifest._validate_unique_scenarios`. Its full AST
`decorator_list` MUST be exactly:

1. `ast.Call` with `func=ast.Name("field_validator")`,
   exactly 1 positional argument equal to the literal
   string `"scenarios"`, and 0 keyword arguments.
2. `ast.Name("classmethod")` — bare, no call, no arguments.

Any of the following is REJECTED with the stable marker
`DATABASE_BACKEND_DECORATOR_STACK_MISMATCH`:

* decorator count `!= 2` (one extra, one missing, or
  empty);
* duplicate `@field_validator("scenarios")` at any
  position;
* duplicate `@classmethod` at any position;
* missing `@classmethod` (only `@field_validator(...)`
  present);
* reversed order (`@classmethod` before
  `@field_validator("scenarios")`);
* any extra decorator at any position (e.g.
  `@other_decorator` before the field_validator or after
  the classmethod);
* bare `@field_validator` (no call arguments);
* `@field_validator(*FIELDS)` (unpacked args);
* multi-arg `@field_validator("other", "scenarios")` or
  `@field_validator("scenarios", "other")`;
* keyword arg `@field_validator("scenarios", mode="before")`.

The check is implemented in
`_has_exact_manifest_validator_decorator_stack` (in
`backend/tests/architecture/test_phase1_identity_foundation_boundary.py`)
and invoked from
`_assert_all_database_backend_occurrences_authorized`. The
real production `models.py` and synthetic test sources use
the **same** checker; there is no test-only lenient
allowlist.

The exact-cardinality invariants from §12.4 remain
unmodified and are re-asserted on top of the new
decorator-stack check (decorator stack enforcement is
**additive**, never a relaxation):

```
AUTHORIZED_FIELD_COUNT=3
AUTHORIZED_VALIDATOR_READ_COUNT=2
TOTAL_DATABASE_BACKEND_OCCURRENCE_COUNT=5
REJECTED_OCCURRENCE_COUNT=0
```
