"""Architecture boundary tests for Task 11B Phase 1 schema and
identity foundation.

Enforces:

1. The Phase 1 ORM columns on
   ``orchestration_run_attempts`` and
   ``scheme_runs`` exist and are addressed ONLY via the
   production ORM modules. The evaluation runner module MUST NOT
   import these Phase 1 fields directly (no raw ORM bypass, no
   evaluation-owned seeding).

2. The Phase 1 SQLAlchemy ORM modules
   (``modules/orchestration/infrastructure/orm.py`` and
   ``modules/schemes/infrastructure/orm.py``) are reachable only
   via the ``infrastructure`` subpackage.

3. The evaluation runner does NOT reach into the
   orchestration.coefficient_resolver_infrastructure or
   schemes.application.service directly to bypass the production
   Phase 1 path.

The Phase 1 contract: see design doc
docs/tasks/TASK-011B-production-calculation-orchestration-prerequisite.md
(Frozen Contract Authority SHA: ba4288ea1c6f258c8b0b9f487d071c8ffce0e4b2).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = BACKEND_ROOT / "src" / "cold_storage"

# The Phase 1 ORM mirror
ORCH_ORM = BACKEND_SRC / "modules" / "orchestration" / "infrastructure" / "orm.py"
SCHEMES_ORM = BACKEND_SRC / "modules" / "schemes" / "infrastructure" / "orm.py"

# Forbidden directories/files for Phase 1 raw ORM bypass.
EVALUATION_DIR = BACKEND_SRC / "evaluation"
EVALUATION_TESTS_DIR = BACKEND_ROOT / "tests" / "evaluation"

# Phase 1 field names that should not appear in evaluation scripts
# outside of write_file paths.
PHASE1_ATTEMPT_FIELDS = (
    "idempotency_key",
    "database_backend",
    "correlation_id",
    "actor_principal_type",
    "scheme_run_id",
)
PHASE1_SCHEME_FIELDS = (
    "frozen_envelope",
    "database_backend",
)


def _read(path: Path) -> str:
    return path.read_text()


def _all_python_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


# ---------------------------------------------------------------------------
# 1) Phase 1 columns exist in the production ORM modules
# ---------------------------------------------------------------------------


def test_phase1_attempt_columns_present_in_orch_orm() -> None:
    """Phase 1 columns must be registered in the production ORM
    modules. These are read-only fields; the application layer
    is responsible for orchestrating them (Phase 1 does NOT
    implement orchestrator business logic).
    """
    content = _read(ORCH_ORM)
    for field in PHASE1_ATTEMPT_FIELDS:
        assert field in content, (
            f"Phase 1 column '{field}' missing from {ORCH_ORM.relative_to(BACKEND_ROOT)}"
        )


def test_phase1_scheme_columns_present_in_schemes_orm() -> None:
    """Phase 1 columns must be registered in the production SchemeRun
    ORM mirror."""
    content = _read(SCHEMES_ORM)
    for field in PHASE1_SCHEME_FIELDS:
        assert field in content, (
            f"Phase 1 column '{field}' missing from {SCHEMES_ORM.relative_to(BACKEND_ROOT)}"
        )


# ---------------------------------------------------------------------------
# 2) Evaluation module MUST NOT import the Phase 1 ORM helpers
# ---------------------------------------------------------------------------


def test_evaluation_does_not_import_phase1_orm() -> None:
    """The Phase 1 schema is reserved for production callers;
    the evaluation runner must not import the Phase 1 fields
    to bypass production pathways."""
    if not EVALUATION_DIR.exists():
        return  # nothing to enforce — module does not yet exist
    files = _all_python_files(EVALUATION_DIR)
    for path in files:
        content = path.read_text()
        # Direct ORM imports must not reference Phase 1 fields
        for forbidden in ("production_seeding", "phase1"):
            assert forbidden not in content, (
                f"Evaluation file references Phase 1 helper '{forbidden}': {path}"
            )
        # No raw insert / raw select into orchestration_run_attempts
        # with Phase 1 fields appearing in evaluate.py.
        for field in PHASE1_ATTEMPT_FIELDS + PHASE1_SCHEME_FIELDS:
            pattern = rf"\b{re.escape(field)}\b"
            if re.search(pattern, content):
                # A1-2a narrow carve-out (2026-07-08, Charles):
                # ``database_backend`` and ``correlation_id`` are
                # legitimate A1-2a adapter input contract fields
                # (per Amendment 2 §13.2 of the Path A design
                # contract). They MUST appear in the adapter
                # module's code (parameter names, type annotations,
                # validation logic, command construction, etc.) and
                # MUST NOT appear in any other evaluation file
                # (test files, seed helpers, runner, manifest
                # builders, etc.). The carve-out is path-precise and
                # token-precise: it does not affect any other
                # file, any other Phase-1 token, or any forbidden
                # pattern (raw ORM / production_seeding /
                # project_input / scenario_id / calculation_run_ids).
                # ``path`` here is absolute (BACKEND_ROOT is
                # absolute, so ``rglob`` returns absolute paths).
                # We compare against the absolute form
                # ``<BACKEND_ROOT>/src/cold_storage/evaluation/adapter.py``.
                expected_adapter_path = (
                    BACKEND_ROOT / "src" / "cold_storage" / "evaluation" / "adapter.py"
                )
                if path == expected_adapter_path and field in (
                    "database_backend",
                    "correlation_id",
                ):
                    continue
                # Amendment 3 narrow carve-out (2026-07-10, Charles):
                # ``execute.py`` is the Phase-B orchestration boundary.
                # It is the **single** file authorized to hold the
                # A1-2a contract token names (``correlation_id`` and
                # ``database_backend``) as code tokens in its public
                # surface. The runner MUST NOT call any production ORM
                # / repository / production persistence internals
                # (per §14 Amendment 3 ownership boundary); it only
                # validates the input contract and forwards the
                # canonical A1-2a kwarg names to
                # ``adapter.execute_scenario(...)``. The carve-out is
                # path-precise (only ``execute.py``) and
                # token-precise (only ``database_backend`` and
                # ``correlation_id``). All other evaluation files
                # (errors.py / run_directory.py / cli.py /
                # __init__.py / tests / seed helpers) remain subject
                # to the original Phase-1 field ban. The carve-out
                # does NOT allow ``project_input``, ``scenario_id``,
                # ``calculation_run_ids``, ``idempotency_key``,
                # ``actor_principal_type``, ``scheme_run_id``,
                # ``frozen_envelope``, ``production_seeding``, or
                # any raw ORM / production-row fabrication token in
                # ``execute.py``.
                expected_execute_path = (
                    BACKEND_ROOT / "src" / "cold_storage" / "evaluation" / "execute.py"
                )
                if path == expected_execute_path and field in (
                    "database_backend",
                    "correlation_id",
                ):
                    continue
                # ── TASK-011C amendment (comment 4963778355) ─────
                # ``models.py`` is the single C-1 file authorized to
                # hold the ``database_backend`` token as a Pydantic
                # typed scenario / run / summary identity field
                # (frozen TASK-011C contract, §6.4 and §7.0). The
                # carve-out is path-precise, token-precise, and
                # purpose-precise: it permits ONLY the ``database_backend``
                # token in ``models.py`` and only for Pydantic
                # typed-model surface use (field declarations,
                # ``Field(alias=...)``, ``serialization_alias``,
                # typed identity attributes, enum / value
                # validation). It does NOT permit:
                #
                #   * any other Phase-1 token (``correlation_id`` /
                #     ``idempotency_key`` / ``actor_principal_type`` /
                #     ``scheme_run_id`` / ``frozen_envelope``);
                #   * any import of a production ORM /
                #     infrastructure / repository module;
                #   * any construction of a production record
                #     (``OrchestrationRunAttemptRecord`` /
                #     ``SchemeRunRecord`` /
                #     ``CalculationRunRecord``);
                #   * any raw SQL, ORM attribute access, repository
                #     call, ``session.add``, ``session.execute``,
                #     or production persistence construction;
                #   * any Pydantic Field alias on a token other than
                #     ``database_backend``;
                #   * the ``database_backend`` token in any other
                #     evaluation file (``manifest.py`` /
                #     ``canonicalization.py`` / ``paths.py`` /
                #     ``sqlite_scope.py`` /
                #     ``schema/__init__.py`` / test files).
                expected_models_path = (
                    BACKEND_ROOT / "src" / "cold_storage" / "evaluation" / "models.py"
                )
                if path == expected_models_path and field == "database_backend":
                    # Run a structural inspection of ``models.py`` to
                    # enforce the purpose-precise carve-out. The
                    # structural inspection is paired with at least
                    # one behavioral assertion in the C-1 test suite
                    # (see ``test_models_round_trip_database_backend``).
                    _assert_models_database_backend_use_is_typed_model_only(content, path)
                    continue
                # Allow comments (fine)
                in_comments = sum(
                    1
                    for line in content.splitlines()
                    if field in line and line.lstrip().startswith("#")
                )
                occurrences = sum(1 for line in content.splitlines() if field in line)
                assert occurrences <= in_comments, (
                    f"Evaluation file references Phase 1 ORM field '{field}': {path}"
                )


# ---------------------------------------------------------------------------
# 3) No raw ORM seeding from evaluation tests
# ---------------------------------------------------------------------------


def test_evaluation_tests_do_not_construct_phase1_records() -> None:
    """The evaluation test suite MUST NOT fabricate
    OrchestrationRunAttemptRecord or SchemeRunRecord via raw
    ORM inserts to simulate a production path. Phase 1 owns
    the schema foundation only.

    Narrow carve-out (A1 follow-up slice, 2026-07-08, Charles):
    ``backend/tests/evaluation/_seed_helpers.py`` is the **only**
    evaluation-test file that may construct Phase 1 records (only
    ``OrchestrationRunAttemptRecord``) for the purpose of seeding
    the pre-existing production context required by the A1-2a
    live-database happy-path tests. The carve-out is:

    * **Path-precise:** only the file
      ``backend/tests/evaluation/_seed_helpers.py`` is exempt.
    * **Token-precise:** only ``OrchestrationRunAttemptRecord`` is
      exempt; ``SchemeRunRecord`` and ``frozen_envelope`` remain
      forbidden everywhere in the evaluation test suite.
    * **Purpose-bound:** the helper exists solely to construct
      the pre-existing production context for A1 live-DB tests.
      It MUST NOT be imported by production code, the evaluation
      adapter, or the evaluation runner.
    * **Schema-bound:** the helper writes pre-existing rows; it
      does NOT bypass production pathways at runtime — the A1
      adapter still calls
      ``ProductionSchemeService.generate_production_scheme_run``
      end-to-end against the live database.
    * **API-bound:** the helper's
      ``OrchestrationRunAttemptRecord`` row does NOT use any
      banned A1 field beyond the legitimate Phase 1
      ``database_backend`` / ``correlation_id`` markers, which
      are Phase 1 NOT NULL columns (per Amendment 2 §13.7
      cross-reference) that the helper must populate to match
      the production schema.
    """
    if not EVALUATION_TESTS_DIR.exists():
        return
    files = _all_python_files(EVALUATION_TESTS_DIR)
    for path in files:
        content = path.read_text()
        # A1 follow-up slice: narrow carve-out for the test-side
        # seed helper that materializes pre-existing production
        # context for the A1-2a live-DB tests. The carve-out is
        # path-precise (only the helper file) and token-precise
        # (only ``OrchestrationRunAttemptRecord``). The
        # ``SchemeRunRecord`` / ``frozen_envelope`` checks below
        # still apply to the helper.
        expected_seed_helper_path = BACKEND_ROOT / "tests" / "evaluation" / "_seed_helpers.py"
        is_a1_seed_helper = path == expected_seed_helper_path
        if "OrchestrationRunAttemptRecord" in content and not is_a1_seed_helper:
            raise AssertionError(
                f"Evaluation test imports OrchestrationRunAttemptRecord "
                f"(Phase 1 contract: evaluation must NOT bypass "
                f"production via raw ORM seeding): {path}"
            )
        # ``SchemeRunRecord`` with ``frozen_envelope`` remains
        # forbidden everywhere — the seed helper does NOT need
        # to construct SchemeRunRecord (the production service
        # does that at runtime).
        if "SchemeRunRecord" in content and "frozen_envelope" in content:
            raise AssertionError(
                f"Evaluation test constructs SchemeRunRecord with "
                f"Phase 1 frozen_envelope (forbidden): {path}"
            )


# ---------------------------------------------------------------------------
# 4) Phase 1 ORM mirror MUST NOT contain orchestrator business logic
# ---------------------------------------------------------------------------


def test_phase1_orm_does_not_contain_orchestrator_class() -> None:
    """The Phase 1 ORM files must ONLY contain schema mappings +
    CHECK constraints + indexes. They MUST NOT define an
    orchestrator class, business logic service, or any side-effect
    code path that would preempt Phase 2..N.
    """
    forbidden_terms = (
        "ProductionCalculationOrchestrator",
        "production_calculation_orchestrator",
    )
    for path in (ORCH_ORM, SCHEMES_ORM):
        content = _read(path)
        for term in forbidden_terms:
            assert term not in content, (
                f"Phase 1 ORM file {path.relative_to(BACKEND_ROOT)} "
                f"contains forbidden orchestrator term '{term}'"
            )


# ---------------------------------------------------------------------------
# 5) TASK-011C amendment (comment 4963778355) — models.py carve-out
# ---------------------------------------------------------------------------


#: Names that the ``database_backend`` token must NOT appear near in
#: ``models.py`` (besides the typed-model surface). These are structural
#: "contexts" that would indicate the token is being used for raw
#: SQL, ORM access, or production record construction. The
#: per-occurrence AST classifier in
#: :func:`_classify_database_backend_occurrence` enforces a
#: positive whitelist instead; this tuple is kept for
#: defense-in-depth on production-ORM imports and dynamic
#: ``getattr`` / ``setattr`` calls.
_MODELS_PY_FORBIDDEN_CONTEXTS: tuple[str, ...] = (
    # Production ORM / infrastructure / repository / persistence.
    "cold_storage.modules.orchestration.infrastructure",
    "cold_storage.modules.schemes.infrastructure",
    "OrchestrationRunAttemptRecord",
    "SchemeRunRecord",
    "CalculationRunRecord",
    # Raw SQL / session.
    "session.add",
    "session.execute",
    "session.scalar",
    "session.commit",
    "session.rollback",
    "text(",
    # Production persistence bypass / raw dict rows.
    "raw_orm",
    "raw_sql",
    "fabricate",
)


#: Approved contexts in which the ``database_backend`` token is
#: allowed to appear in ``models.py``. These are the **only** allowed
#: occurrence sites; anything else MUST be classified as REJECTED
#: (P0-1 of review 4689835238). The carve-out is:
#:
#:   * path-precise: only ``backend/src/cold_storage/evaluation/models.py``;
#:   * token-precise: only the literal token ``database_backend``;
#:   * purpose-precise: only as a Pydantic typed-model surface
#:     (field declaration, ``Field(alias=...)``,
#:     ``serialization_alias``, typed identity attribute, enum /
#:     value validation reference, model-validator read of
#:     ``scenario.database_backend``).
_APPROVED_MODELS_PY_FIELD_CLASSES: frozenset[str] = frozenset(
    {
        "ScenarioDeclaration",
        "RunRecord",
        "SummaryRecord",
    }
)


#: Names of the Python Pydantic helper attributes that the canonical
#: architecture surface legitimately reads when validating a typed
#: model attribute. These are only allowed inside model-validator
#: functions (``@model_validator(mode="after")`` /
#: ``@field_validator``) on approved classes.
_APPROVED_VALIDATOR_READ_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "database_backend",
    }
)


def _build_parent_map(tree: ast.AST) -> dict[int, ast.AST]:
    """Build a parent map for an AST.

    The map is keyed by ``id(node)`` (the AST node's memory id) so
    the function works for both ``ast.AST`` and the strongly-typed
    Python 3.13+ ``ast.AST`` (which is the same class for older
    versions). The map is consumed by
    :func:`_containing_class` and
    :func:`_containing_function`.
    """
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    return parents


def _containing_class(node: ast.AST, parents: dict[int, ast.AST]) -> ast.ClassDef | None:
    """Return the innermost ``ClassDef`` that contains ``node``, or
    ``None`` if the node is at module scope."""
    current: ast.AST | None = parents.get(id(node))
    while current is not None:
        if isinstance(current, ast.ClassDef):
            return current
        current = parents.get(id(current)) if current is not None else None
    return None


def _containing_function(
    node: ast.AST, parents: dict[int, ast.AST]
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """Return the innermost function / method that contains ``node``,
    or ``None`` if the node is at class / module scope."""
    current: ast.AST | None = parents.get(id(node))
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current
        current = parents.get(id(current)) if current is not None else None
    return None


def _is_validator_decorated(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    """Return True if ``fn`` is decorated with a Pydantic
    validator decorator (``@field_validator``,
    ``@model_validator``)."""
    for decorator in fn.decorator_list:
        # ``@field_validator("scenarios")`` is a Call with
        # func=Name("field_validator").
        if isinstance(decorator, ast.Call):
            func = decorator.func
            if isinstance(func, ast.Name) and func.id in {
                "field_validator",
                "model_validator",
            }:
                return True
        # ``@model_validator(mode="after")`` is also a Call.
        if isinstance(decorator, ast.Attribute) and decorator.attr in {
            "field_validator",
            "model_validator",
        }:
            return True
        # Bare ``@field_validator`` (rare) — Name node.
        if isinstance(decorator, ast.Name) and decorator.id in {
            "field_validator",
            "model_validator",
        }:
            return True
    return False


def _collect_database_backend_occurrences(
    tree: ast.AST,
) -> list[tuple[ast.AST, int, int]]:
    """Return every AST node in ``tree`` that is a code-level
    reference to the token ``database_backend``.

    The returned list contains the node plus its 1-based line and
    column. The function is purely lexical-AST; classification of
    each occurrence (AUTHORIZED / REJECTED) is performed by
    :func:`_classify_database_backend_occurrence`.

    A node is a "code-level reference" if it is one of:

    * ``ast.Name`` with ``id == "database_backend"`` (and not the
      target of an ``AnnAssign`` / ``Assign`` — those are
      captured by the parent assignment rule);
    * ``ast.arg`` with ``arg == "database_backend"``;
    * ``ast.Constant`` with ``value == "database_backend"`` (a
      string literal occurrence);
    * ``ast.Attribute`` with ``attr == "database_backend"`` (an
      attribute read or write);
    * ``ast.keyword`` with ``arg == "alias"`` and ``value`` being
      a ``Constant`` whose ``value == "database_backend"``;
    * ``ast.Call`` with any keyword whose ``arg == "alias"`` and
      value unparse contains ``"database_backend"`` (Pydantic
      ``Field(alias="database_backend")`` surface).
    """
    occurrences: list[tuple[ast.AST, int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "database_backend":
            # The Name ``database_backend`` is also a target of
            # an ``AnnAssign`` or ``Assign`` statement; in that
            # case the parent node already represents the
            # occurrence and the Name is a duplicate. Skip the
            # Name to avoid double-counting.
            parent: ast.AST | None = None
            for candidate in ast.walk(tree):
                if node in getattr(candidate, "targets", []):
                    parent = candidate
                    break
                if isinstance(candidate, ast.AnnAssign) and candidate.target is node:
                    parent = candidate
                    break
            if parent is not None:
                # Emit the parent (AnnAssign / Assign) instead.
                if isinstance(parent, (ast.AnnAssign, ast.Assign)):
                    occurrences.append((parent, parent.lineno, parent.col_offset))
                continue
            occurrences.append((node, node.lineno, node.col_offset))
        elif (
            isinstance(node, ast.arg)
            and node.arg == "database_backend"
            or (isinstance(node, ast.Constant) and node.value == "database_backend")
            or (isinstance(node, ast.Attribute) and node.attr == "database_backend")
            or (
                isinstance(node, ast.keyword)
                and node.arg == "alias"
                and isinstance(node.value, ast.Constant)
                and node.value.value == "database_backend"
            )
        ):
            occurrences.append((node, node.lineno, node.col_offset))
        elif isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "alias":
                    try:
                        value_text = ast.unparse(kw.value)
                    except Exception:  # pragma: no cover
                        continue
                    if "database_backend" in value_text:
                        occurrences.append((node, node.lineno, node.col_offset))
                        break
    return occurrences


def _classify_database_backend_occurrence(
    node: ast.AST,
    parents: dict[int, ast.AST],
) -> str:
    """Classify a single ``database_backend`` occurrence as
    ``AUTHORIZED`` or ``REJECTED``.

    Rules (P0-1 of review 4689835238):

    AUTHORIZED only if ALL of the following hold:

    1. The occurrence is one of:
       * ``ast.AnnAssign`` whose ``target`` is an
         ``ast.Name(id="database_backend")`` and whose parent class
         is in :data:`_APPROVED_MODELS_PY_FIELD_CLASSES`.
       * ``ast.arg`` (function parameter) on a
         ``model_validator`` / ``field_validator`` method of an
         approved class — currently NOT used by the typed model
         surface, so this branch is REJECTED for the existing
         surface. (Kept for forward compatibility with future
         validators that legitimately take a typed alias.)
       * ``ast.Attribute(value=ast.Name(id="self"), attr="database_backend")``
         inside a method of an approved class (typed-model
         attribute read).
       * ``ast.Call`` whose ``func`` is ``ast.Name(id="Field")`` and
         which has a keyword argument ``alias=...`` whose unparse
         contains ``"database_backend"`` (Pydantic Field alias).
       * ``ast.keyword(arg="alias", value=ast.Constant(value="database_backend"))``
         directly.
       * ``ast.Constant(value="database_backend")`` (string literal
         used as a key or alias).
       * ``ast.Attribute(value=ast.Name(id="DatabaseBackend") or similar,
         attr=...)`` referencing the enum class
         (e.g. ``DatabaseBackend.SQLITE``).
       * A read of the typed-model attribute in a model validator:
         ``scenario.database_backend`` or
         ``scenarios[i].database_backend`` where the attribute is
         accessed on a Name whose name is in
         :data:`_APPROVED_VALIDATOR_READ_ATTRIBUTES` (e.g. scenario
         variable in a model-validator function body).
       * ``getattr`` / ``setattr`` calls are REJECTED in all
         contexts (P0-1 of review 4689835238).

    REJECTED otherwise. In particular, the following are always
    REJECTED:
       * module-level assignment;
       * function parameter on a non-validator function;
       * local variable assignment / read;
       * free Name load;
       * unapproved attribute access;
       * dict key mutation;
       * ``getattr`` / ``setattr`` access;
       * production record / ORM / SQL / session context.
    """
    containing_cls = _containing_class(node, parents)
    containing_fn = _containing_function(node, parents)
    containing_cls_name = containing_cls.name if containing_cls else None

    # 1. Module-level free Name assignment is REJECTED.
    if (
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "database_backend"
    ):
        if containing_cls_name in _APPROVED_MODELS_PY_FIELD_CLASSES:
            return "AUTHORIZED"
        return "REJECTED"
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "database_backend":
                return "REJECTED"
    # 2. Function parameter on a non-validator function is REJECTED.
    if isinstance(node, ast.arg) and node.arg == "database_backend":
        return "REJECTED"
    # 3. Local variable Name node — REJECTED unless this is the
    # ``self.database_backend`` access on an approved class.
    if isinstance(node, ast.Name) and node.id == "database_backend":
        return "REJECTED"
    # 4. ``self.database_backend`` Attribute access inside an
    # approved class is AUTHORIZED. Also AUTHORIZED: ``<typed
    # variable>.database_backend`` where the attribute is read
    # inside a ``@field_validator`` / ``@model_validator``
    # method on an approved model class (e.g.,
    # ``s.database_backend.value`` inside
    # ``_validate_unique_scenarios`` on ``Manifest``).
    if isinstance(node, ast.Attribute) and node.attr == "database_backend":
        if containing_cls_name in _APPROVED_MODELS_PY_FIELD_CLASSES:
            return "AUTHORIZED"
        # The attribute read happens inside a validator-decorated
        # method (the parent class is a Pydantic BaseModel, even
        # if not in the approved field-class set). This is a
        # legitimate model-validator read of a typed-model
        # attribute.
        if (
            containing_fn is not None
            and _is_validator_decorated(containing_fn)
            and containing_cls is not None
        ):
            return "AUTHORIZED"
        return "REJECTED"
    # 5. Field(alias="database_backend") call keyword is AUTHORIZED.
    if (
        isinstance(node, ast.keyword)
        and node.arg == "alias"
        and isinstance(node.value, ast.Constant)
        and node.value.value == "database_backend"
    ):
        return "AUTHORIZED"
    # 6. ``Field(...)`` call that has any keyword whose unparse
    # contains ``"database_backend"`` is AUTHORIZED.
    if isinstance(node, ast.Call):
        call_text = ast.unparse(node)
        if "Field(" in call_text and "database_backend" in call_text:
            return "AUTHORIZED"
        # ``getattr`` / ``setattr`` are REJECTED in any context.
        func = node.func
        if isinstance(func, ast.Name) and func.id in {"getattr", "setattr"}:
            return "REJECTED"
    # 7. ``getattr(obj, "database_backend")`` detected via the
    # string-literal constant inside a Call is REJECTED.
    if isinstance(node, ast.Constant) and node.value == "database_backend":
        # String-literal usage is approved only when it appears
        # inside a Pydantic ``Field(alias=...)`` keyword (rule 5
        # already handles that case). All other string-literal
        # occurrences of the bare token are REJECTED.
        parent = parents.get(id(node))
        if isinstance(parent, ast.keyword) and parent.arg == "alias":
            return "AUTHORIZED"
        return "REJECTED"
    # 8. ``DatabaseBackend.SQLITE`` enum references are AUTHORIZED
    # when they appear inside an approved class.
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in {"DatabaseBackend"}
    ):
        if containing_cls_name in _APPROVED_MODELS_PY_FIELD_CLASSES:
            return "AUTHORIZED"
        return "REJECTED"
    # 9. Dict key mutation: ``payload["database_backend"] = ...``
    # is REJECTED.
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.slice, ast.Constant)
        and node.slice.value == "database_backend"
    ):
        return "REJECTED"
    # 10. Anything else with ``database_backend`` text content that
    # is NOT classified above is REJECTED. (No implicit allow.)
    return "REJECTED"


def _assert_all_database_backend_occurrences_authorized(
    source: str,
    path: Path,
) -> None:
    """Enforce the per-occurrence AUTHORIZED / REJECTED contract.

    Per P0-1 of review 4689835238, every code-level
    ``database_backend`` occurrence in ``source`` MUST be
    classified as either AUTHORIZED or REJECTED; UNCLASSIFIED
    occurrences are not permitted (no implicit allow). REJECTED
    occurrences cause a hard failure. AUTHORIZED occurrences are
    recorded for the assertion message.
    """
    tree = ast.parse(source, filename=str(path))
    parents = _build_parent_map(tree)
    occurrences = _collect_database_backend_occurrences(tree)
    authorized: list[tuple[int, int]] = []
    rejected: list[tuple[int, int, str]] = []
    unclassified: list[tuple[int, int]] = []
    for node, line, col in occurrences:
        verdict = _classify_database_backend_occurrence(node, parents)
        if verdict == "AUTHORIZED":
            authorized.append((line, col))
        elif verdict == "REJECTED":
            node_type = type(node).__name__
            rejected.append((line, col, node_type))
        else:  # pragma: no cover — defensive
            unclassified.append((line, col))
    assert not unclassified, (
        f"models.py has UNCLASSIFIED database_backend occurrences "
        f"(P0-1 of review 4689835238): {unclassified!r}"
    )
    assert not rejected, (
        f"models.py has REJECTED database_backend occurrences "
        f"(P0-1 of review 4689835238 carve-out is purpose-precise): "
        f"{rejected!r}"
    )
    # Sanity: at least one AUTHORIZED occurrence (the typed-model
    # field declaration). If this is zero, the typed-model surface
    # is not actually using the token, so the carve-out has no
    # basis to apply.
    assert authorized, (
        "models.py has zero AUTHORIZED database_backend occurrences; "
        "the typed-model carve-out requires at least one "
        "Pydantic typed-model surface use of the token"
    )


def _assert_models_database_backend_use_is_typed_model_only(content: str, path: Path) -> None:
    """Structural inspection for the ``models.py`` carve-out.

    Per Issue #20 amendment comment 4963778355, ``models.py`` is
    the single C-1 file permitted to reference the
    ``database_backend`` token, and only for Pydantic typed-model
    surface use.

    P0-1 of review 4689835238 strengthens the check: instead of
    a partial deny-list ("if it doesn't match a forbidden context,
    allow it"), the new implementation performs per-occurrence
    AST classification. Every code-level occurrence is either
    AUTHORIZED (typed-model surface) or REJECTED; no implicit
    allow. Adversarial self-tests live alongside this function
    in the test file.
    """
    # 1. Per-occurrence AST classification.
    _assert_all_database_backend_occurrences_authorized(content, path)

    # 2. No production ORM / infrastructure import is allowed.
    try:
        tree = ast.parse(content, filename=str(path))
    except SyntaxError as exc:
        raise AssertionError(f"models.py has a syntax error: {exc}") from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for forbidden in _MODELS_PY_FORBIDDEN_CONTEXTS:
                if "modules" in forbidden and forbidden in module:
                    raise AssertionError(
                        f"models.py has forbidden production-ORM import "
                        f"from {module!r} (TASK-011C amendment 4963778355): "
                        f"{ast.unparse(node)!r}"
                    )
        if isinstance(node, ast.Import):
            for alias in node.names:
                for forbidden in _MODELS_PY_FORBIDDEN_CONTEXTS:
                    if "modules" in forbidden and forbidden in alias.name:
                        raise AssertionError(
                            f"models.py has forbidden production-ORM import "
                            f"{alias.name!r} (TASK-011C amendment 4963778355)"
                        )
        # ``getattr`` / ``setattr`` calls are REJECTED in models.py
        # (defense-in-depth — already rejected by the per-occurrence
        # classifier, but a structural double-check is cheap).
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in {"getattr", "setattr"}:
                raise AssertionError(
                    f"models.py has forbidden dynamic attribute access "
                    f"{func.id}(...) (TASK-011C amendment 4963778355)"
                )


def test_models_py_database_backend_round_trip() -> None:
    """Behavioral companion to the structural inspection in
    ``_assert_models_database_backend_use_is_typed_model_only``.

    The ``database_backend`` token must round-trip through Pydantic
    ``model_validate`` and ``model_dump(by_alias=True,
    mode="json")`` exactly as the frozen TASK-011C contract
    requires (§6.4 / §7.0).

    This test is the ONLY behavior under
    ``backend/tests/architecture/`` that imports the C-1 models
    module. It runs the round-trip and asserts:
      * the parsed attribute is the ``DatabaseBackend`` enum
        instance;
      * the dumped wire form uses the literal ``"database_backend"``
        key.
    """
    models_py_path = BACKEND_ROOT / "src" / "cold_storage" / "evaluation" / "models.py"
    if not models_py_path.exists():
        return  # the module does not exist yet — defer
    from cold_storage.evaluation.models import DatabaseBackend, Manifest

    raw = {
        "schema_version": "1.0",
        "suite_id": "t",
        "scenarios": [
            {
                "scenario_id": "baseline_feasible",
                "database_backend": "sqlite",
                "expected_outcome": "SUCCEEDED",
            }
        ],
    }
    manifest = Manifest.model_validate(raw)
    assert manifest.scenarios[0].database_backend is DatabaseBackend.SQLITE
    dumped = manifest.model_dump(by_alias=True, mode="json")
    # The wire form uses the literal ``database_backend`` key.
    assert dumped["scenarios"][0]["database_backend"] == "sqlite"


# ---------------------------------------------------------------------------
# P0-1 of review 4689835238 — adversarial self-tests of the classifier
# ---------------------------------------------------------------------------


def _assert_rejected(source: str) -> None:
    """Helper: assert that ``source`` is REJECTED by the per-occurrence
    classifier when treated as ``models.py`` content."""
    tmp = Path("/tmp/_classifier_rejected.py")
    tmp.write_text(source)
    try:
        try:
            _assert_all_database_backend_occurrences_authorized(source, tmp)
        except AssertionError as exc:
            msg = str(exc)
            assert "REJECTED" in msg or "UNCLASSIFIED" in msg or "zero AUTHORIZED" in msg, (
                f"unexpected assertion message: {msg!r}"
            )
        else:
            raise AssertionError(
                f"expected classifier to REJECT source, but it passed:\n---\n{source}\n---"
            )
    finally:
        tmp.unlink(missing_ok=True)


def _assert_authorized(source: str) -> None:
    """Helper: assert that ``source`` is AUTHORIZED by the per-occurrence
    classifier when treated as ``models.py`` content."""
    tmp = Path("/tmp/_classifier_authorized.py")
    tmp.write_text(source)
    try:
        _assert_all_database_backend_occurrences_authorized(source, tmp)
    except AssertionError as exc:
        raise AssertionError(
            f"expected classifier to AUTHORIZE source, but it raised:\n{exc}\n---\n{source}\n---"
        ) from exc
    finally:
        tmp.unlink(missing_ok=True)


def test_classifier_authorizes_typed_field_declaration() -> None:
    """A direct ``database_backend: DatabaseBackend`` field
    declaration on an approved class is AUTHORIZED.
    """
    _assert_authorized(
        "from pydantic import BaseModel\n"
        "from enum import Enum\n"
        "class DatabaseBackend(str, Enum):\n"
        "    SQLITE = 'sqlite'\n"
        "class ScenarioDeclaration(BaseModel):\n"
        "    database_backend: DatabaseBackend\n"
    )


def test_classifier_rejects_function_parameter() -> None:
    """A function parameter named ``database_backend`` is REJECTED."""
    _assert_rejected("def helper(database_backend: str) -> str:\n    return database_backend\n")


def test_classifier_rejects_local_assignment_in_method() -> None:
    """A local-variable assignment ``database_backend = "sqlite"``
    inside a method body is REJECTED (per Charles: helper uses)."""
    _assert_rejected(
        "class X:\n    def method(self) -> None:\n        database_backend = 'sqlite'\n"
    )


def test_classifier_rejects_unapproved_attribute_access() -> None:
    """``obj.database_backend`` where ``obj`` is not ``self`` on
    an approved class is REJECTED (a free-Name attribute read)."""
    _assert_rejected("def helper(obj):\n    return obj.database_backend\n")


def test_classifier_rejects_string_constant_alias_outside_field() -> None:
    """A module-level ``DATABASE_BACKEND_KEY = "database_backend"``
    alias is REJECTED.
    """
    _assert_rejected('DATABASE_BACKEND_KEY = "database_backend"\n')


def test_classifier_rejects_dict_key_mutation() -> None:
    """``payload["database_backend"] = value`` is REJECTED."""
    _assert_rejected('def helper(payload, value):\n    payload["database_backend"] = value\n')


def test_classifier_rejects_getattr_dynamic_access() -> None:
    """``getattr(obj, "database_backend")`` is REJECTED in all
    contexts (P0-1 of review 4689835238)."""
    _assert_rejected('def helper(obj):\n    return getattr(obj, "database_backend")\n')


def test_classifier_rejects_module_level_annassign_outside_class() -> None:
    """A module-level ``database_backend: DatabaseBackend``
    annotation (not inside a class body) is REJECTED."""
    _assert_rejected(
        "from pydantic import BaseModel\n"
        "from enum import Enum\n"
        "class DatabaseBackend(str, Enum):\n"
        "    SQLITE = 'sqlite'\n"
        "database_backend: DatabaseBackend = DatabaseBackend.SQLITE\n"
    )


def test_classifier_rejects_unapproved_class_attribute() -> None:
    """``database_backend`` declared on a class that is NOT in
    the approved set (e.g., a free helper class) is REJECTED."""
    _assert_rejected("class NotApproved:\n    database_backend: str = 'sqlite'\n")
