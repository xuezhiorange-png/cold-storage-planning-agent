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


#: Approved field-class set for the exact-typed-field
#: ``database_backend`` declaration surface. Per P0 of review
#: 4690110096, the architecture guard no longer permits ANY
#: "approved class attribute access" — instead the guard only
#: accepts an exact, narrow surface: a Pydantic typed
#: ``AnnAssign`` whose target name is ``database_backend`` and
#: whose annotation is the literal ``DatabaseBackend`` symbol,
#: inside one of these classes, with no default value.
_EXACT_FIELD_CLASSES: frozenset[str] = frozenset(
    {
        "ScenarioDeclaration",
        "RunRecord",
        "SummaryRecord",
    }
)


#: The exact Manifest validator function whose body may read
#: ``s.database_backend.value``. Any other validator or any
#: other read shape is REJECTED.
_EXACT_MANIFEST_UNIQUE_VALIDATOR_NAME: str = "_validate_unique_scenarios"


#: The exact receiver name used inside the body of
#: :data:`_EXACT_MANIFEST_UNIQUE_VALIDATOR_NAME`. The guard
#: rejects ``value.database_backend``, ``self.database_backend``,
#: ``obj.database_backend``, etc.
_EXACT_MANIFEST_UNIQUE_RECEIVER: str = "s"


#: The exact trailing attribute that must follow
#: ``s.database_backend`` inside
#: :data:`_EXACT_MANIFEST_UNIQUE_VALIDATOR_NAME`. The guard
#: rejects ``s.database_backend`` (without ``.value``).
_EXACT_MANIFEST_UNIQUE_TAIL_ATTR: str = "value"


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


def _is_exact_manifest_uniqueness_validator(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    containing_cls: ast.ClassDef | None,
) -> bool:
    """Return True if ``fn`` is the exact
    ``Manifest._validate_unique_scenarios`` ``@field_validator("scenarios")``
    method that the typed-model surface uses to read
    ``s.database_backend.value``.

    The check is exact: function name must be
    :data:`_EXACT_MANIFEST_UNIQUE_VALIDATOR_NAME`, the parent
    class name must be ``Manifest``, and the function must
    carry a ``@field_validator("scenarios")`` decorator. Any
    other shape is REJECTED.
    """
    if fn.name != _EXACT_MANIFEST_UNIQUE_VALIDATOR_NAME:
        return False
    if containing_cls is None or containing_cls.name != "Manifest":
        return False
    has_field_validator_scenarios = False
    for decorator in fn.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        func = decorator.func
        if not (isinstance(func, ast.Name) and func.id == "field_validator"):
            continue
        for arg in decorator.args:
            if isinstance(arg, ast.Constant) and arg.value == "scenarios":
                has_field_validator_scenarios = True
                break
    return has_field_validator_scenarios


def _is_exact_database_backend_field(
    node: ast.AST,
    parents: dict[int, ast.AST],
) -> bool:
    """Exact allowlist predicate: is ``node`` one of the three
    legal ``database_backend: DatabaseBackend`` field
    declarations in :data:`_EXACT_FIELD_CLASSES`?

    Required shape:

    * ``ast.AnnAssign``
    * ``target`` is ``ast.Name(id="database_backend")``
    * ``annotation`` is ``ast.Name(id="DatabaseBackend")``
    * ``value`` is ``None`` (no default)
    * containing class is in :data:`_EXACT_FIELD_CLASSES`
    * containing function is ``None`` (the field is at class
      body scope, not inside a method)

    Any deviation (wrong annotation, default value, wrong
    class, inside a function body) is rejected.
    """
    if not isinstance(node, ast.AnnAssign):
        return False
    if not isinstance(node.target, ast.Name):
        return False
    if node.target.id != "database_backend":
        return False
    if not isinstance(node.annotation, ast.Name):
        return False
    if node.annotation.id != "DatabaseBackend":
        return False
    if node.value is not None:
        return False
    containing_cls = _containing_class(node, parents)
    if containing_cls is None:
        return False
    if containing_cls.name not in _EXACT_FIELD_CLASSES:
        return False
    return _containing_function(node, parents) is None


def _is_exact_manifest_uniqueness_read(
    node: ast.AST,
    parents: dict[int, ast.AST],
) -> bool:
    """Exact allowlist predicate: is ``node`` the
    ``s.database_backend`` attribute access inside
    ``Manifest._validate_unique_scenarios``, whose parent
    is the ``.value`` attribute access?

    The full read expression is ``s.database_backend.value``.
    Python parses it as::

        Attribute(
            attr="value",
            value=Attribute(
                attr="database_backend",
                value=Name(id="s"),
            ),
        )

    The collector picks the inner ``Attribute(attr=
    "database_backend", value=Name("s"))`` node. This
    predicate verifies that node is exactly that inner
    attribute, that its parent is the ``.value`` Attribute,
    that the receiver is ``s``, and that the surrounding
    function is the exact Manifest validator.

    Required shape:

    * ``ast.Attribute`` with ``attr == "database_backend"``
      and ``value`` is ``ast.Name(id="s")``
    * parent is ``ast.Attribute(attr="value")``
    * parent context is ``ast.Load``
    * containing function is
      :data:`_EXACT_MANIFEST_UNIQUE_VALIDATOR_NAME` on
      ``Manifest`` (decorator
      ``@field_validator("scenarios")``)

    Any deviation (wrong receiver, wrong parent attr, wrong
    validator, different class) is rejected.
    """
    if not isinstance(node, ast.Attribute):
        return False
    if node.attr != "database_backend":
        return False
    # The value of this attribute must be the receiver
    # ``ast.Name(id="s")``.
    receiver = node.value
    if not isinstance(receiver, ast.Name):
        return False
    if receiver.id != _EXACT_MANIFEST_UNIQUE_RECEIVER:
        return False
    # The parent must be the ``.value`` Attribute.
    parent = parents.get(id(node))
    if parent is None:
        return False
    if not isinstance(parent, ast.Attribute):
        return False
    if parent.attr != _EXACT_MANIFEST_UNIQUE_TAIL_ATTR:
        return False
    if not isinstance(parent.ctx, ast.Load):
        return False
    # Must be inside the exact Manifest validator.
    containing_fn = _containing_function(node, parents)
    if containing_fn is None:
        return False
    containing_cls = _containing_class(node, parents)
    return _is_exact_manifest_uniqueness_validator(containing_fn, containing_cls)


def _collect_database_backend_occurrences(
    tree: ast.AST,
) -> list[tuple[ast.AST, int, int, str | None, str | None, str | None]]:
    """Collect every code-level reference to the token
    ``database_backend`` in ``tree``.

    The returned tuple is ``(node, line, column, containing_class,
    containing_function, parent_node_type)``. The function
    walks the tree ONCE and uses the parent map for
    containing-class / containing-function resolution; it does
    NOT re-walk the tree per node.

    A node is a "code-level reference" if it is one of:

    * ``ast.AnnAssign`` whose ``target`` is an
      ``ast.Name(id="database_backend")``;
    * ``ast.Assign`` whose target list contains a Name with
      ``id == "database_backend"``;
    * ``ast.NamedExpr`` whose target is a Name with
      ``id == "database_backend"``;
    * ``ast.arg`` with ``arg == "database_backend"``;
    * ``ast.Name`` with ``id == "database_backend"`` (free
      Name load / store);
    * ``ast.Constant`` with ``value == "database_backend"``;
    * ``ast.Attribute`` with ``attr == "database_backend"``;
    * ``ast.keyword`` whose ``arg == "alias"`` or
      ``arg == "serialization_alias"`` and whose value
      unparse contains ``"database_backend"``;
    * ``ast.Subscript`` whose ``slice`` is a
      ``Constant(value="database_backend")``;
    * ``ast.Call`` whose function is ``getattr`` or
      ``setattr`` (any argument shape).
    """
    occurrences: list[tuple[ast.AST, int, int, str | None, str | None, str | None]] = []
    parents = _build_parent_map(tree)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "database_backend"
        ):
            containing_cls = _containing_class(node, parents)
            containing_fn = _containing_function(node, parents)
            occurrences.append(
                (
                    node,
                    node.lineno,
                    node.col_offset,
                    containing_cls.name if containing_cls else None,
                    containing_fn.name if containing_fn else None,
                    type(parents.get(id(node))).__name__
                    if parents.get(id(node)) is not None
                    else None,
                )
            )
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "database_backend":
                    containing_cls = _containing_class(node, parents)
                    containing_fn = _containing_function(node, parents)
                    occurrences.append(
                        (
                            node,
                            node.lineno,
                            node.col_offset,
                            containing_cls.name if containing_cls else None,
                            containing_fn.name if containing_fn else None,
                            type(parents.get(id(node))).__name__
                            if parents.get(id(node)) is not None
                            else None,
                        )
                    )
                    break
        elif (
            isinstance(node, ast.NamedExpr)
            and isinstance(node.target, ast.Name)
            and node.target.id == "database_backend"
        ) or (isinstance(node, ast.arg) and node.arg == "database_backend"):
            containing_cls = _containing_class(node, parents)
            containing_fn = _containing_function(node, parents)
            occurrences.append(
                (
                    node,
                    node.lineno,
                    node.col_offset,
                    containing_cls.name if containing_cls else None,
                    containing_fn.name if containing_fn else None,
                    type(parents.get(id(node))).__name__
                    if parents.get(id(node)) is not None
                    else None,
                )
            )
        elif isinstance(node, ast.Name) and node.id == "database_backend":
            parent = parents.get(id(node))
            if isinstance(parent, ast.AnnAssign) and parent.target is node:
                continue
            if isinstance(parent, ast.Assign) and any(t is node for t in parent.targets):
                continue
            if isinstance(parent, ast.NamedExpr) and parent.target is node:
                continue
            containing_cls = _containing_class(node, parents)
            containing_fn = _containing_function(node, parents)
            occurrences.append(
                (
                    node,
                    node.lineno,
                    node.col_offset,
                    containing_cls.name if containing_cls else None,
                    containing_fn.name if containing_fn else None,
                    type(parent).__name__ if parent is not None else None,
                )
            )
        elif (isinstance(node, ast.Constant) and node.value == "database_backend") or (
            isinstance(node, ast.Attribute) and node.attr == "database_backend"
        ):
            containing_cls = _containing_class(node, parents)
            containing_fn = _containing_function(node, parents)
            occurrences.append(
                (
                    node,
                    node.lineno,
                    node.col_offset,
                    containing_cls.name if containing_cls else None,
                    containing_fn.name if containing_fn else None,
                    type(parents.get(id(node))).__name__
                    if parents.get(id(node)) is not None
                    else None,
                )
            )
        elif isinstance(node, ast.keyword) and node.arg in {"alias", "serialization_alias"}:
            try:
                value_text = ast.unparse(node.value)
            except Exception:  # pragma: no cover
                value_text = ""
            if "database_backend" in value_text:
                containing_cls = _containing_class(node, parents)
                containing_fn = _containing_function(node, parents)
                occurrences.append(
                    (
                        node,
                        node.lineno,
                        node.col_offset,
                        containing_cls.name if containing_cls else None,
                        containing_fn.name if containing_fn else None,
                        type(parents.get(id(node))).__name__
                        if parents.get(id(node)) is not None
                        else None,
                    )
                )
        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Constant)
            and node.slice.value == "database_backend"
        ):
            containing_cls = _containing_class(node, parents)
            containing_fn = _containing_function(node, parents)
            occurrences.append(
                (
                    node,
                    node.lineno,
                    node.col_offset,
                    containing_cls.name if containing_cls else None,
                    containing_fn.name if containing_fn else None,
                    type(parents.get(id(node))).__name__
                    if parents.get(id(node)) is not None
                    else None,
                )
            )
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in {
                "getattr",
                "setattr",
            }:
                containing_cls = _containing_class(node, parents)
                containing_fn = _containing_function(node, parents)
                occurrences.append(
                    (
                        node,
                        node.lineno,
                        node.col_offset,
                        containing_cls.name if containing_cls else None,
                        containing_fn.name if containing_fn else None,
                        type(parents.get(id(node))).__name__
                        if parents.get(id(node)) is not None
                        else None,
                    )
                )
    return occurrences


def _classify_database_backend_occurrence(
    node: ast.AST,
    parents: dict[int, ast.AST],
) -> str:
    """Classify a single ``database_backend`` occurrence with
    the exact allowlist.

    Per P0 of review 4690110096 the architecture contract is
    narrowed: only two exact shapes are AUTHORIZED, and
    everything else is REJECTED. The two authorized shapes
    are:

    1. :func:`_is_exact_database_backend_field` — an
       ``ast.AnnAssign`` of the form
       ``database_backend: DatabaseBackend`` (no default)
       inside one of
       :data:`_EXACT_FIELD_CLASSES`.

    2. :func:`_is_exact_manifest_uniqueness_read` — an
       ``ast.Attribute`` of the form ``s.database_backend.value``
       inside the exact
       ``Manifest._validate_unique_scenarios`` validator.

    The classifier returns one of:

    * ``"AUTHORIZED_FIELD"``;
    * ``"AUTHORIZED_VALIDATOR_READ"``;
    * ``"REJECTED"``.

    No generic / forward-compat allow is permitted. Anything
    not matching an exact predicate is rejected.
    """
    if _is_exact_database_backend_field(node, parents):
        return "AUTHORIZED_FIELD"
    if _is_exact_manifest_uniqueness_read(node, parents):
        return "AUTHORIZED_VALIDATOR_READ"
    return "REJECTED"


def _assert_all_database_backend_occurrences_authorized(
    source: str,
    path: Path,
) -> None:
    """Enforce the exact-allowlist contract.

    Per P0 of review 4690110096, every code-level
    ``database_backend`` occurrence in ``source`` MUST match
    either the exact field-declaration allowlist or the exact
    Manifest validator read allowlist. Any occurrence that
    does not is REJECTED, and the assertion fails.
    """
    tree = ast.parse(source, filename=str(path))
    parents = _build_parent_map(tree)
    occurrences = _collect_database_backend_occurrences(tree)
    authorized_field: list[tuple[int, int]] = []
    authorized_validator_read: list[tuple[int, int]] = []
    rejected: list[tuple[int, int, str]] = []
    for (
        node,
        line,
        col,
        _cls,
        _fn,
        _parent_type,
    ) in occurrences:
        verdict = _classify_database_backend_occurrence(node, parents)
        if verdict == "AUTHORIZED_FIELD":
            authorized_field.append((line, col))
        elif verdict == "AUTHORIZED_VALIDATOR_READ":
            authorized_validator_read.append((line, col))
        elif verdict == "REJECTED":
            node_type = type(node).__name__
            rejected.append((line, col, node_type))
    assert not rejected, (
        f"models.py has REJECTED database_backend occurrences "
        f"(P0 of review 4690110096 carve-out is exact): {rejected!r}"
    )
    assert authorized_field, (
        "models.py has zero AUTHORIZED_FIELD database_backend "
        "occurrences; the exact allowlist requires the three "
        "Pydantic typed-field declarations"
    )
    assert authorized_validator_read, (
        "models.py has zero AUTHORIZED_VALIDATOR_READ "
        "database_backend occurrences; the exact allowlist "
        "requires the two Manifest._validate_unique_scenarios "
        "reads of s.database_backend.value"
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
    """The exact three typed field declarations and the
    Manifest validator read are AUTHORIZED.

    Per P0 of review 4690110096, the only two AUTHORIZED
    shapes are:

    1. ``database_backend: DatabaseBackend`` in
       ``ScenarioDeclaration`` / ``RunRecord`` /
       ``SummaryRecord``;
    2. ``s.database_backend.value`` read inside
       ``Manifest._validate_unique_scenarios``.

    This positive test includes BOTH shapes.
    """
    _assert_authorized(
        "from pydantic import BaseModel, field_validator\n"
        "from enum import Enum\n"
        "from typing import Tuple\n"
        "class DatabaseBackend(str, Enum):\n"
        "    SQLITE = 'sqlite'\n"
        "class ScenarioDeclaration(BaseModel):\n"
        "    database_backend: DatabaseBackend\n"
        "class RunRecord(BaseModel):\n"
        "    database_backend: DatabaseBackend\n"
        "class SummaryRecord(BaseModel):\n"
        "    database_backend: DatabaseBackend\n"
        "class Manifest(BaseModel):\n"
        "    scenarios: Tuple[ScenarioDeclaration, ...]\n"
        "    @field_validator('scenarios')\n"
        "    @classmethod\n"
        "    def _validate_unique_scenarios(cls, value):\n"
        "        for s in value:\n"
        "            key = (s.scenario_id, s.database_backend.value)\n"
        "        return value\n"
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
    the approved set (e.g., a free helper class) is REJECTED.
    """
    _assert_rejected("class NotApproved:\n    database_backend: str = 'sqlite'\n")


# ---------------------------------------------------------------------------
# P0 of review 4690110096 — exact allowlist adversarial tests
# ---------------------------------------------------------------------------


def test_classifier_rejects_wrong_field_annotation_str() -> None:
    """9.1: Wrong field annotation (``database_backend: str``)
    is REJECTED. The exact allowlist requires the annotation
    to be exactly the literal ``DatabaseBackend`` symbol.
    """
    _assert_rejected(
        "from pydantic import BaseModel\n"
        "class ScenarioDeclaration(BaseModel):\n"
        "    database_backend: str\n"
    )


def test_classifier_rejects_wrong_field_annotation_any() -> None:
    """9.1: ``database_backend: Any`` is REJECTED."""
    _assert_rejected(
        "from pydantic import BaseModel\n"
        "from typing import Any\n"
        "class RunRecord(BaseModel):\n"
        "    database_backend: Any\n"
    )


def test_classifier_rejects_approved_class_method_attribute_read() -> None:
    """9.2: ``self.database_backend`` read inside an
    ``ScenarioDeclaration.helper`` method is REJECTED. The
    exact allowlist only permits field declarations; ordinary
    method attribute reads are NOT allowed.
    """
    _assert_rejected(
        "from pydantic import BaseModel\n"
        "from enum import Enum\n"
        "class DatabaseBackend(str, Enum):\n"
        "    SQLITE = 'sqlite'\n"
        "class ScenarioDeclaration(BaseModel):\n"
        "    database_backend: DatabaseBackend\n"
        "    def helper(self):\n"
        "        return self.database_backend\n"
    )


def test_classifier_rejects_unrelated_manifest_validator() -> None:
    """9.3: ``@field_validator("other")`` on ``Manifest`` reading
    ``value.database_backend`` is REJECTED. The exact allowlist
    only permits the unique-scenarios validator.
    """
    _assert_rejected(
        "from pydantic import BaseModel, field_validator\n"
        "from enum import Enum\n"
        "class DatabaseBackend(str, Enum):\n"
        "    SQLITE = 'sqlite'\n"
        "class Manifest(BaseModel):\n"
        "    @field_validator('other')\n"
        "    @classmethod\n"
        "    def validate_other(cls, value):\n"
        "        return value.database_backend\n"
    )


def test_classifier_rejects_other_model_field_validator() -> None:
    """9.4: A different model class's ``@field_validator`` is
    REJECTED, even with the same function name shape.
    """
    _assert_rejected(
        "from pydantic import BaseModel, field_validator\n"
        "from enum import Enum\n"
        "class DatabaseBackend(str, Enum):\n"
        "    SQLITE = 'sqlite'\n"
        "class OtherModel(BaseModel):\n"
        "    @field_validator('x')\n"
        "    @classmethod\n"
        "    def validate_x(cls, value):\n"
        "        return value.database_backend\n"
    )


def test_classifier_rejects_wrong_receiver_in_manifest_validator() -> None:
    """9.5: ``Manifest._validate_unique_scenarios`` with the
    wrong receiver (``value`` instead of ``s``) is REJECTED.
    """
    _assert_rejected(
        "from pydantic import BaseModel, field_validator\n"
        "from enum import Enum\n"
        "class DatabaseBackend(str, Enum):\n"
        "    SQLITE = 'sqlite'\n"
        "class Manifest(BaseModel):\n"
        "    @field_validator('scenarios')\n"
        "    @classmethod\n"
        "    def _validate_unique_scenarios(cls, value):\n"
        "        return value.database_backend\n"
    )


def test_classifier_rejects_missing_value_attribute() -> None:
    """9.6: ``s.database_backend`` (without the trailing
    ``.value``) inside the exact validator is REJECTED. The
    exact allowlist requires the trailing ``.value``.
    """
    _assert_rejected(
        "from pydantic import BaseModel, field_validator\n"
        "from enum import Enum\n"
        "class DatabaseBackend(str, Enum):\n"
        "    SQLITE = 'sqlite'\n"
        "class Manifest(BaseModel):\n"
        "    @field_validator('scenarios')\n"
        "    @classmethod\n"
        "    def _validate_unique_scenarios(cls, value):\n"
        "        for s in value:\n"
        "            key = s.database_backend\n"
        "        return value\n"
    )


def test_classifier_rejects_field_alias_database_backend() -> None:
    """9.7: ``Field(alias="database_backend")`` is REJECTED.
    The current implementation does not use any alias, and
    the exact allowlist does not include alias shapes.
    """
    _assert_rejected(
        "from pydantic import BaseModel, Field\n"
        "from enum import Enum\n"
        "class DatabaseBackend(str, Enum):\n"
        "    SQLITE = 'sqlite'\n"
        "class ScenarioDeclaration(BaseModel):\n"
        "    backend: DatabaseBackend = Field(alias='database_backend')\n"
    )


def test_classifier_rejects_field_serialization_alias_database_backend() -> None:
    """9.7: ``Field(serialization_alias="database_backend")`` is
    REJECTED.
    """
    _assert_rejected(
        "from pydantic import BaseModel, Field\n"
        "class _M(BaseModel):\n"
        "    backend: int = Field(serialization_alias='database_backend')\n"
    )


def test_classifier_rejects_self_database_backend_in_unapproved_class() -> None:
    """``self.database_backend`` inside a class that is NOT in
    the approved field-class set is REJECTED.
    """
    _assert_rejected(
        "from pydantic import BaseModel\n"
        "from enum import Enum\n"
        "class DatabaseBackend(str, Enum):\n"
        "    SQLITE = 'sqlite'\n"
        "class Helper(BaseModel):\n"
        "    database_backend: DatabaseBackend\n"
        "    def method(self):\n"
        "        return self.database_backend\n"
    )
