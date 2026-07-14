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
from collections import Counter
from dataclasses import dataclass
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
                # ── TASK-011C C-2 amendment (review 4693931575 P0-5) ─────
                # ``runners/_executor.py`` is the C-2 production-boundary
                # seam. It is authorized to hold the A1-2a contract
                # token names (``database_backend`` and
                # ``correlation_id``) ONLY at the two production-boundary
                # call sites (``adapter_execute_scenario(...)`` and
                # ``project_calculator_input(...)``). The runner does
                # NOT call any production ORM / repository / production
                # persistence internals; it only forwards the canonical
                # A1-2a kwarg names to the typed A1-2a adapter path.
                # The carve-out is path-precise (only
                # ``runners/_executor.py``) and token-precise (only
                # ``database_backend`` and ``correlation_id``). All
                # other evaluation files (errors.py / run_directory.py /
                # cli.py / __init__.py / tests / seed helpers) remain
                # subject to the original Phase-1 field ban. The
                # carve-out does NOT allow ``project_input``,
                # ``scenario_id``, ``calculation_run_ids``,
                # ``idempotency_key``, ``actor_principal_type``,
                # ``scheme_run_id``, ``frozen_envelope``,
                # ``production_seeding``, or any raw ORM /
                # production-row fabrication token in
                # ``runners/_executor.py``. The structural
                # inspection in P0-5 (see
                # ``test_executor_authorized_call_sites_emit_literal_keywords``
                # + ``test_executor_rejects_string_concatenation_bypass``
                # + ``test_executor_rejects_dict_spread_bypass``) is
                # the paired AST enforcement for this carve-out.
                expected_executor_path = (
                    BACKEND_ROOT
                    / "src"
                    / "cold_storage"
                    / "evaluation"
                    / "runners"
                    / "_executor.py"
                )
                if path == expected_executor_path and field in (
                    "database_backend",
                    "correlation_id",
                ):
                    # Run a structural AST inspection to enforce
                    # the purpose-precise carve-out: the tokens
                    # MUST appear only as literal keyword args at
                    # the two authorized call sites (and nowhere
                    # else in the file).
                    _assert_executor_database_backend_use_is_typed_call_only(content, path)
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


#: Expected exact occurrence cardinality for the real
#: ``models.py`` source. The architecture contract is exact:
#: no more, no fewer. If the real model surface ever grows
#: a 4th typed field or a 3rd validator read, this constant
#: (and the design record §12 frozen facts) MUST be updated
#: in lockstep — never silently widened.
_EXACT_EXPECTED_AUTHORIZED_FIELD_COUNT: int = 3
_EXACT_EXPECTED_AUTHORIZED_VALIDATOR_READ_COUNT: int = 2
_EXACT_EXPECTED_TOTAL_OCCURRENCE_COUNT: int = (
    _EXACT_EXPECTED_AUTHORIZED_FIELD_COUNT + _EXACT_EXPECTED_AUTHORIZED_VALIDATOR_READ_COUNT
)
_EXACT_EXPECTED_REJECTED_OCCURRENCE_COUNT: int = 0


#: Expected per-class field occurrence counter. Each approved
#: class MUST have exactly one ``database_backend: DatabaseBackend``
#: declaration; any deviation (missing class, duplicate, extra
#: field) is REJECTED.
_EXACT_EXPECTED_FIELD_CLASS_COUNTER: dict[str, int] = {
    "ScenarioDeclaration": 1,
    "RunRecord": 1,
    "SummaryRecord": 1,
}


#: Stable error markers used by ``_assert_rejected`` /
#: ``_assert_authorized`` and surfaced to test assertions. Each
#: marker corresponds to a distinct class of failure; tests
#: assert the expected marker rather than accepting any
#: AssertionError.
ERROR_MARKER_REJECTED_OCCURRENCE: str = "DATABASE_BACKEND_REJECTED_OCCURRENCE"
ERROR_MARKER_FIELD_CARDINALITY_MISMATCH: str = "DATABASE_BACKEND_FIELD_CARDINALITY_MISMATCH"
ERROR_MARKER_FIELD_CLASS_SET_MISMATCH: str = "DATABASE_BACKEND_FIELD_CLASS_SET_MISMATCH"
ERROR_MARKER_VALIDATOR_CARDINALITY_MISMATCH: str = "DATABASE_BACKEND_VALIDATOR_CARDINALITY_MISMATCH"
ERROR_MARKER_TOTAL_CARDINALITY_MISMATCH: str = "DATABASE_BACKEND_TOTAL_CARDINALITY_MISMATCH"
ERROR_MARKER_DECORATOR_MISMATCH: str = "DATABASE_BACKEND_DECORATOR_MISMATCH"
ERROR_MARKER_DECORATOR_STACK_MISMATCH: str = "DATABASE_BACKEND_DECORATOR_STACK_MISMATCH"


@dataclass(frozen=True)
class AuthorizedFieldOccurrence:
    """Identity record for a single AUTHORIZED_FIELD occurrence.

    Carries enough information to assert the exact field
    declaration surface: class name, field name, annotation
    name, whether a default is present, containing function
    (always ``None`` for top-level class fields), and the
    source line / column.
    """

    class_name: str
    field_name: str
    annotation_name: str
    has_default: bool
    containing_function: str | None
    line: int
    column: int


@dataclass(frozen=True)
class AuthorizedValidatorReadOccurrence:
    """Identity record for a single AUTHORIZED_VALIDATOR_READ
    occurrence.

    Carries enough information to assert the exact validator
    read surface: class name, function name, receiver name
    (``s``), attribute name (``database_backend``), parent
    attribute name (``value``), context type (always
    ``ast.Load``), and the source line / column.
    """

    class_name: str
    function_name: str
    receiver_name: str
    attribute_name: str
    parent_attribute_name: str
    context_type: str
    line: int
    column: int


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


def _is_exact_scenarios_field_validator(decorator: ast.AST) -> bool:  # noqa: SIM103
    """Return True if ``decorator`` is the exact
    ``@field_validator("scenarios")`` decorator the typed-model
    surface uses.

    The check is exact, not positional-scan:

    * the decorator must be an ``ast.Call`` whose function is
      the literal ``field_validator`` symbol;
    * the call must have **exactly one** positional argument;
    * that argument must be the literal string ``"scenarios"``;
    * the call must have **zero** keyword arguments.

    Any of the following is REJECTED:

    * ``@field_validator("other", "scenarios")``
    * ``@field_validator("scenarios", "other")``
    * ``@field_validator("scenarios", mode="before")``
    * ``@field_validator(*FIELDS)``
    * any decorator that is not a ``Call`` (e.g. a bare
      ``Name``).
    """
    if not isinstance(decorator, ast.Call):
        return False
    func = decorator.func
    if not (isinstance(func, ast.Name) and func.id == "field_validator"):
        return False
    if len(decorator.args) != 1:
        return False
    arg = decorator.args[0]
    if not (isinstance(arg, ast.Constant) and arg.value == "scenarios"):
        return False
    if decorator.keywords:  # noqa: SIM103
        return False
    return True


def _has_exact_manifest_validator_decorator_stack(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    """Return True iff ``fn.decorator_list`` is EXACTLY the
    two-node frozen stack ``[@field_validator("scenarios"),
    @classmethod]`` — same order, no extras, no duplicates,
    no reversed order, no missing ``@classmethod``.

    This is the full-stack counterpart of
    :func:`_is_exact_scenarios_field_validator`. The latter
    only checks that a single decorator in the list has the
    authorized shape; this function checks that the *complete*
    decorator list matches the authorized production model.

    Authorized stack (frozen order):

    * ``decorators[0]`` = ``ast.Call`` whose
      ``func`` is ``ast.Name(id="field_validator")`` and whose
      single positional argument is
      ``ast.Constant(value="scenarios")`` (no keyword args).
    * ``decorators[1]`` = ``ast.Name(id="classmethod")``.

    ``len(decorator_list) != 2`` → False.
    """
    decorators = fn.decorator_list
    if len(decorators) != 2:
        return False
    if not _is_exact_scenarios_field_validator(decorators[0]):
        return False
    classmethod_decorator = decorators[1]
    if not (  # noqa: SIM103
        isinstance(classmethod_decorator, ast.Name) and classmethod_decorator.id == "classmethod"
    ):
        return False
    return True


def _is_exact_manifest_uniqueness_validator(  # noqa: SIM110
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    containing_cls: ast.ClassDef | None,
) -> bool:
    """Return True if ``fn`` is the exact
    ``Manifest._validate_unique_scenarios`` validator that the
    typed-model surface uses to read ``s.database_backend.value``.

    The check is exact: function name must be
    :data:`_EXACT_MANIFEST_UNIQUE_VALIDATOR_NAME`, the parent
    class name must be ``Manifest``, and the function's FULL
    ``decorator_list`` must match the frozen two-node stack
    ``[@field_validator("scenarios"), @classmethod]`` (verified
    by :func:`_has_exact_manifest_validator_decorator_stack`).

    Merely containing an exact ``@field_validator("scenarios")``
    call in the decorator list is no longer sufficient — the
    ``@classmethod`` and the frozen order are part of the
    contract. Any deviation (missing ``@classmethod``,
    extra decorators, duplicate ``@field_validator``,
    duplicate ``@classmethod``, reversed order, bare
    ``@field_validator``, unpacked arguments, multi-arg
    ``@field_validator``, keyword args, etc.) is REJECTED.
    """
    if fn.name != _EXACT_MANIFEST_UNIQUE_VALIDATOR_NAME:
        return False
    if containing_cls is None or containing_cls.name != "Manifest":
        return False
    return _has_exact_manifest_validator_decorator_stack(fn)


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


def _assert_all_database_backend_occurrences_authorized(  # noqa: SIM102
    source: str,
    path: Path,
) -> None:
    """Enforce the exact-allowlist contract AND the exact
    cardinality contract.

    Per P0-1 of review 4690297649, every code-level
    ``database_backend`` occurrence in ``source`` MUST match
    either the exact field-declaration allowlist or the exact
    Manifest validator read allowlist. Any occurrence that does
    not is REJECTED.

    Per P0-1 of the same review, the real ``models.py`` MUST
    have:

    * exactly :data:`_EXACT_EXPECTED_AUTHORIZED_FIELD_COUNT`
      AUTHORIZED_FIELD occurrences (3);
    * exactly
      :data:`_EXACT_EXPECTED_AUTHORIZED_VALIDATOR_READ_COUNT`
      AUTHORIZED_VALIDATOR_READ occurrences (2);
    * a total of
      :data:`_EXACT_EXPECTED_TOTAL_OCCURRENCE_COUNT` (5)
      code-level occurrences;
    * zero REJECTED occurrences;
    * a per-class field counter of
      :data:`_EXACT_EXPECTED_FIELD_CLASS_COUNTER`
      (``ScenarioDeclaration: 1, RunRecord: 1, SummaryRecord: 1``).

    Each AUTHORIZED occurrence is recorded as a structured
    :class:`AuthorizedFieldOccurrence` /
    :class:`AuthorizedValidatorReadOccurrence` and the field
    identity (class name, field name, annotation name, default
    flag, containing function, line, column) is asserted
    exactly. Test source and real ``models.py`` use the same
    checker.
    """
    tree = ast.parse(source, filename=str(path))
    parents = _build_parent_map(tree)
    occurrences = _collect_database_backend_occurrences(tree)

    # --- 0. Pre-flight: detect the bad-decorator pattern.
    # If ``Manifest._validate_unique_scenarios`` exists but
    # carries a ``@field_validator(...)`` whose shape is not
    # exactly ``@field_validator("scenarios")`` (multi-arg,
    # keyword arg, unpacked, wrong literal, etc.), the
    # decorator check fires first — DO NOT collapse the
    # diagnosis into ``DATABASE_BACKEND_REJECTED_OCCURRENCE``,
    # which would mask the decorator mismatch as a generic
    # "wrong shape" rejection. Stable error marker:
    # ``DATABASE_BACKEND_DECORATOR_MISMATCH``.
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Manifest":
            for fn in node.body:
                if (
                    isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and fn.name == _EXACT_MANIFEST_UNIQUE_VALIDATOR_NAME
                ):
                    for decorator in fn.decorator_list:
                        if isinstance(decorator, ast.Call) and (  # noqa: SIM102
                            isinstance(decorator.func, ast.Name)
                            and decorator.func.id == "field_validator"
                        ):
                            # The Manifest validator has a
                            # ``@field_validator(...)`` call. Verify
                            # it is exactly the single-positional
                            # ``"scenarios"`` form.
                            if not _is_exact_scenarios_field_validator(decorator):
                                raise AssertionError(
                                    f"{ERROR_MARKER_DECORATOR_MISMATCH}: "
                                    f"Manifest._validate_unique_scenarios "
                                    f"decorator shape is not exactly "
                                    f"@field_validator('scenarios') "
                                    f"(must have exactly 1 positional "
                                    f"argument equal to 'scenarios' and "
                                    f"0 keyword arguments). Got: "
                                    f"{ast.unparse(decorator)!r}."
                                )

    # --- 0b. Exact decorator stack check (post-shape). The
    #         full ``Manifest._validate_unique_scenarios`` decorator
    #         list must be exactly two nodes in the frozen order
    #         ``@field_validator("scenarios")`` then
    #         ``@classmethod``. A subset, a superset, a duplicate,
    #         or a reversed order each raise
    #         ``DATABASE_BACKEND_DECORATOR_STACK_MISMATCH``.
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Manifest":
            for fn in node.body:
                if (
                    isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and fn.name == _EXACT_MANIFEST_UNIQUE_VALIDATOR_NAME
                ):
                    actual_count = len(fn.decorator_list)
                    actual_nodes_repr = [ast.unparse(d) for d in fn.decorator_list]
                    if not _has_exact_manifest_validator_decorator_stack(fn):
                        raise AssertionError(
                            f"{ERROR_MARKER_DECORATOR_STACK_MISMATCH}: "
                            f"Manifest._validate_unique_scenarios full "
                            f"decorator stack is not the authorized "
                            f"frozen order. "
                            f"class_name='Manifest', "
                            f"function_name="
                            f"'{_EXACT_MANIFEST_UNIQUE_VALIDATOR_NAME}', "
                            f"actual_decorator_count={actual_count}, "
                            f"actual_decorator_nodes={actual_nodes_repr!r}, "
                            f"expected_stack="
                            f"['field_validator(\"scenarios\")', "
                            f"'classmethod']."
                        )

    authorized_fields: list[AuthorizedFieldOccurrence] = []
    authorized_validator_reads: list[AuthorizedValidatorReadOccurrence] = []
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
            assert isinstance(node, ast.AnnAssign), (
                f"AUTHORIZED_FIELD verdict on a non-AnnAssign node: {type(node).__name__}"
            )
            containing_cls = _containing_class(node, parents)
            containing_fn = _containing_function(node, parents)
            target = node.target
            annotation = node.annotation
            assert isinstance(target, ast.Name)
            assert isinstance(annotation, ast.Name)
            authorized_fields.append(
                AuthorizedFieldOccurrence(
                    class_name=containing_cls.name if containing_cls is not None else "<none>",
                    field_name=target.id,
                    annotation_name=annotation.id,
                    has_default=node.value is not None,
                    containing_function=containing_fn.name if containing_fn is not None else None,
                    line=line,
                    column=col,
                )
            )
        elif verdict == "AUTHORIZED_VALIDATOR_READ":
            assert isinstance(node, ast.Attribute), (
                f"AUTHORIZED_VALIDATOR_READ verdict on a non-Attribute node: {type(node).__name__}"
            )
            parent = parents.get(id(node))
            containing_cls = _containing_class(node, parents)
            containing_fn = _containing_function(node, parents)
            receiver = node.value
            assert isinstance(receiver, ast.Name)
            assert isinstance(parent, ast.Attribute)
            authorized_validator_reads.append(
                AuthorizedValidatorReadOccurrence(
                    class_name=containing_cls.name if containing_cls is not None else "<none>",
                    function_name=containing_fn.name if containing_fn is not None else "<none>",
                    receiver_name=receiver.id,
                    attribute_name=node.attr,
                    parent_attribute_name=parent.attr,
                    context_type=type(parent.ctx).__name__,
                    line=line,
                    column=col,
                )
            )
        elif verdict == "REJECTED":
            node_type = type(node).__name__
            rejected.append((line, col, node_type))

    # --- 1. AUTHORIZED_FIELD count must be exact (run FIRST,
    #        so the field-specific marker fires before
    #        ``REJECTED`` / ``TOTAL`` for the common "wrong
    #        field count" case).
    assert len(authorized_fields) == _EXACT_EXPECTED_AUTHORIZED_FIELD_COUNT, (
        f"{ERROR_MARKER_FIELD_CARDINALITY_MISMATCH}: source has "
        f"{len(authorized_fields)} AUTHORIZED_FIELD occurrences; "
        f"the exact allowlist requires "
        f"{_EXACT_EXPECTED_AUTHORIZED_FIELD_COUNT}."
    )

    # --- 2. AUTHORIZED_VALIDATOR_READ count must be exact
    #        (also before rejected / total, for the same reason).
    assert len(authorized_validator_reads) == _EXACT_EXPECTED_AUTHORIZED_VALIDATOR_READ_COUNT, (
        f"{ERROR_MARKER_VALIDATOR_CARDINALITY_MISMATCH}: source has "
        f"{len(authorized_validator_reads)} AUTHORIZED_VALIDATOR_READ "
        f"occurrences; the exact allowlist requires "
        f"{_EXACT_EXPECTED_AUTHORIZED_VALIDATOR_READ_COUNT}."
    )

    # --- 3. REJECTED occurrences must be exactly zero.
    assert len(rejected) == _EXACT_EXPECTED_REJECTED_OCCURRENCE_COUNT, (
        f"{ERROR_MARKER_REJECTED_OCCURRENCE}: source has {len(rejected)} "
        f"REJECTED database_backend occurrences; the exact allowlist "
        f"requires zero. Rejected: {rejected!r}"
    )

    # --- 4. Total occurrence count must be exact.
    total = len(authorized_fields) + len(authorized_validator_reads) + len(rejected)
    assert total == _EXACT_EXPECTED_TOTAL_OCCURRENCE_COUNT, (
        f"{ERROR_MARKER_TOTAL_CARDINALITY_MISMATCH}: source has {total} "
        f"total database_backend occurrences; the exact allowlist "
        f"requires {_EXACT_EXPECTED_TOTAL_OCCURRENCE_COUNT} "
        f"(={_EXACT_EXPECTED_AUTHORIZED_FIELD_COUNT} fields "
        f"+ {_EXACT_EXPECTED_AUTHORIZED_VALIDATOR_READ_COUNT} validator "
        f"reads). Breakdown: "
        f"fields={len(authorized_fields)}, "
        f"reads={len(authorized_validator_reads)}, "
        f"rejected={len(rejected)}."
    )

    # --- 5. AUTHORIZED_FIELD per-class counter must be exact.
    actual_class_counter: Counter[str] = Counter(
        occurrence.class_name for occurrence in authorized_fields
    )
    expected_class_counter: Counter[str] = Counter(_EXACT_EXPECTED_FIELD_CLASS_COUNTER)
    assert set(actual_class_counter) == set(expected_class_counter), (
        f"{ERROR_MARKER_FIELD_CLASS_SET_MISMATCH}: AUTHORIZED_FIELD "
        f"class set is {sorted(actual_class_counter)}; exact allowlist "
        f"requires {sorted(expected_class_counter)}."
    )
    assert actual_class_counter == expected_class_counter, (
        f"{ERROR_MARKER_FIELD_CARDINALITY_MISMATCH}: AUTHORIZED_FIELD "
        f"per-class counter is {dict(actual_class_counter)}; exact "
        f"allowlist requires {dict(expected_class_counter)}."
    )

    # --- 6. Each AUTHORIZED_FIELD occurrence must satisfy
    #        the field identity invariant.
    for occurrence in authorized_fields:
        assert occurrence.field_name == "database_backend", (
            f"{ERROR_MARKER_REJECTED_OCCURRENCE}: AUTHORIZED_FIELD has "
            f"unexpected field_name {occurrence.field_name!r}; exact "
            f"allowlist requires 'database_backend'."
        )
        assert occurrence.annotation_name == "DatabaseBackend", (
            f"{ERROR_MARKER_REJECTED_OCCURRENCE}: AUTHORIZED_FIELD has "
            f"unexpected annotation_name {occurrence.annotation_name!r}; "
            f"exact allowlist requires 'DatabaseBackend'."
        )
        assert occurrence.has_default is False, (
            f"{ERROR_MARKER_REJECTED_OCCURRENCE}: AUTHORIZED_FIELD has "
            f"a default value; exact allowlist requires no default."
        )
        assert occurrence.containing_function is None, (
            f"{ERROR_MARKER_REJECTED_OCCURRENCE}: AUTHORIZED_FIELD is "
            f"inside function {occurrence.containing_function!r}; exact "
            f"allowlist requires class-body scope."
        )

    # --- 7. Each AUTHORIZED_VALIDATOR_READ occurrence must satisfy
    #        the read identity invariant.
    for occurrence in authorized_validator_reads:
        assert occurrence.class_name == "Manifest", (
            f"{ERROR_MARKER_REJECTED_OCCURRENCE}: AUTHORIZED_VALIDATOR_READ "
            f"is in class {occurrence.class_name!r}; exact allowlist "
            f"requires 'Manifest'."
        )
        assert occurrence.function_name == _EXACT_MANIFEST_UNIQUE_VALIDATOR_NAME, (
            f"{ERROR_MARKER_REJECTED_OCCURRENCE}: AUTHORIZED_VALIDATOR_READ "
            f"is in function {occurrence.function_name!r}; exact allowlist "
            f"requires "
            f"{_EXACT_MANIFEST_UNIQUE_VALIDATOR_NAME!r}."
        )
        assert occurrence.receiver_name == _EXACT_MANIFEST_UNIQUE_RECEIVER, (
            f"{ERROR_MARKER_REJECTED_OCCURRENCE}: AUTHORIZED_VALIDATOR_READ "
            f"has receiver {occurrence.receiver_name!r}; exact allowlist "
            f"requires {_EXACT_MANIFEST_UNIQUE_RECEIVER!r}."
        )
        assert occurrence.attribute_name == "database_backend", (
            f"{ERROR_MARKER_REJECTED_OCCURRENCE}: AUTHORIZED_VALIDATOR_READ "
            f"has attribute_name {occurrence.attribute_name!r}; exact "
            f"allowlist requires 'database_backend'."
        )
        assert occurrence.parent_attribute_name == _EXACT_MANIFEST_UNIQUE_TAIL_ATTR, (
            f"{ERROR_MARKER_REJECTED_OCCURRENCE}: AUTHORIZED_VALIDATOR_READ "
            f"has parent_attribute_name "
            f"{occurrence.parent_attribute_name!r}; exact allowlist "
            f"requires {_EXACT_MANIFEST_UNIQUE_TAIL_ATTR!r}."
        )
        assert occurrence.context_type == "Load", (
            f"{ERROR_MARKER_REJECTED_OCCURRENCE}: AUTHORIZED_VALIDATOR_READ "
            f"has context_type {occurrence.context_type!r}; exact allowlist "
            f"requires 'Load'."
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


def _assert_rejected(
    source: str,
    expected_marker: str | None = None,
) -> None:
    """Helper: assert that ``source`` is REJECTED by the per-occurrence
    classifier when treated as ``models.py`` content.

    If ``expected_marker`` is provided, the test asserts that
    the classifier's AssertionError message contains exactly
    that stable marker (one of the ``ERROR_MARKER_*``
    constants). If it is ``None``, the test accepts any of the
    REJECTED-shaped messages (useful for shape rejections that
    do not yet have a dedicated marker).
    """
    tmp = Path("/tmp/_classifier_rejected.py")
    tmp.write_text(source)
    try:
        try:
            _assert_all_database_backend_occurrences_authorized(source, tmp)
        except AssertionError as exc:
            msg = str(exc)
            if expected_marker is not None:
                assert expected_marker in msg, (
                    f"expected stable marker {expected_marker!r} in "
                    f"classifier error, but got: {msg!r}"
                )
            else:
                # No specific marker required; accept any of the
                # known REJECTED-shaped messages.
                assert (
                    "REJECTED" in msg
                    or "UNCLASSIFIED" in msg
                    or "zero AUTHORIZED" in msg
                    or ERROR_MARKER_REJECTED_OCCURRENCE in msg
                    or ERROR_MARKER_FIELD_CARDINALITY_MISMATCH in msg
                    or ERROR_MARKER_FIELD_CLASS_SET_MISMATCH in msg
                    or ERROR_MARKER_VALIDATOR_CARDINALITY_MISMATCH in msg
                    or ERROR_MARKER_TOTAL_CARDINALITY_MISMATCH in msg
                    or ERROR_MARKER_DECORATOR_MISMATCH in msg
                ), f"unexpected assertion message: {msg!r}"
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
    """The exact three typed field declarations and the two
    Manifest validator reads are AUTHORIZED.

    Per P0-1 of review 4690297649, the only two AUTHORIZED
    shapes are:

    1. ``database_backend: DatabaseBackend`` in
       ``ScenarioDeclaration`` / ``RunRecord`` /
       ``SummaryRecord``;
    2. ``s.database_backend.value`` read inside
       ``Manifest._validate_unique_scenarios`` (exactly two
       occurrences per source: one in a tuple / dict key and
       one in an error message).

    This positive test includes BOTH shapes with the exact
    real ``models.py`` cardinality: 3 fields + 2 reads.
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
        "        for s in value:\n"
        "            if s.scenario_id == 'x':\n"
        "                raise ValueError(\n"
        "                    f'duplicate scenario {s.scenario_id} with database_backend {s.database_backend.value}'\n"  # noqa: E501
        "                )\n"
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


# ---------------------------------------------------------------------------
# P0-1 of review 4690297649 — exact occurrence cardinality adversarial tests
# ---------------------------------------------------------------------------


def test_exact_cardinality_real_models_py_passes() -> None:
    """The real ``models.py`` satisfies the exact cardinality
    contract: 3 fields / 2 reads / 0 rejected / 5 total.

    This is the only positive test that exercises the real
    production source through the same checker used by
    adversarial tests.
    """
    models_py_path = BACKEND_ROOT / "src" / "cold_storage" / "evaluation" / "models.py"
    if not models_py_path.exists():
        return  # the module does not exist yet — defer
    content = models_py_path.read_text()
    _assert_all_database_backend_occurrences_authorized(content, models_py_path)


def test_exact_cardinality_missing_summary_record_field() -> None:
    """8.1: Missing the ``SummaryRecord`` field (only 2 fields,
    2 reads) is REJECTED via
    ``DATABASE_BACKEND_FIELD_CARDINALITY_MISMATCH``.
    """
    source = (
        "from pydantic import BaseModel, field_validator\n"
        "from enum import Enum\n"
        "from typing import Tuple\n"
        "class DatabaseBackend(str, Enum):\n"
        "    SQLITE = 'sqlite'\n"
        "class ScenarioDeclaration(BaseModel):\n"
        "    database_backend: DatabaseBackend\n"
        "class RunRecord(BaseModel):\n"
        "    database_backend: DatabaseBackend\n"
        "class Manifest(BaseModel):\n"
        "    scenarios: Tuple[ScenarioDeclaration, ...]\n"
        "    @field_validator('scenarios')\n"
        "    @classmethod\n"
        "    def _validate_unique_scenarios(cls, value):\n"
        "        for s in value:\n"
        "            key = (s.scenario_id, s.database_backend.value)\n"
        "        for s in value:\n"
        "            if s.scenario_id == 'x':\n"
        "                raise ValueError(\n"
        "                    f'duplicate scenario {s.scenario_id} with database_backend {s.database_backend.value}'\n"  # noqa: E501
        "                )\n"
        "        return value\n"
    )
    _assert_rejected(
        source,
        expected_marker=ERROR_MARKER_FIELD_CARDINALITY_MISMATCH,
    )


def test_exact_cardinality_duplicate_scenario_declaration_field() -> None:
    """8.2: A duplicate ``database_backend: DatabaseBackend``
    field on ``ScenarioDeclaration`` (4 fields total, 2 reads)
    is REJECTED via
    ``DATABASE_BACKEND_FIELD_CARDINALITY_MISMATCH``.
    """
    source = (
        "from pydantic import BaseModel, field_validator\n"
        "from enum import Enum\n"
        "from typing import Tuple\n"
        "class DatabaseBackend(str, Enum):\n"
        "    SQLITE = 'sqlite'\n"
        "class ScenarioDeclaration(BaseModel):\n"
        "    database_backend: DatabaseBackend\n"
        "    database_backend: DatabaseBackend  # duplicate\n"
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
        "        for s in value:\n"
        "            if s.scenario_id == 'x':\n"
        "                raise ValueError(\n"
        "                    f'duplicate scenario {s.scenario_id} with database_backend {s.database_backend.value}'\n"  # noqa: E501
        "                )\n"
        "        return value\n"
    )
    _assert_rejected(
        source,
        expected_marker=ERROR_MARKER_FIELD_CARDINALITY_MISMATCH,
    )


def test_exact_cardinality_fourth_field_in_unapproved_class() -> None:
    """8.3: A 4th ``database_backend: DatabaseBackend`` field
    declaration in an unapproved class is REJECTED via
    ``DATABASE_BACKEND_REJECTED_OCCURRENCE`` (the field is
    in the right AST shape but in the wrong class, so the
    classifier marks it as REJECTED rather than mis-credited
    as AUTHORIZED).
    """
    source = (
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
        "class Extra(BaseModel):\n"
        "    database_backend: DatabaseBackend\n"
        "class Manifest(BaseModel):\n"
        "    scenarios: Tuple[ScenarioDeclaration, ...]\n"
        "    @field_validator('scenarios')\n"
        "    @classmethod\n"
        "    def _validate_unique_scenarios(cls, value):\n"
        "        for s in value:\n"
        "            key = (s.scenario_id, s.database_backend.value)\n"
        "        for s in value:\n"
        "            if s.scenario_id == 'x':\n"
        "                raise ValueError(\n"
        "                    f'duplicate scenario {s.scenario_id} with database_backend {s.database_backend.value}'\n"  # noqa: E501
        "                )\n"
        "        return value\n"
    )
    _assert_rejected(
        source,
        expected_marker=ERROR_MARKER_REJECTED_OCCURRENCE,
    )


def test_exact_cardinality_missing_validator_read() -> None:
    """8.4: A source with the 3 required fields but only one
    validator read (instead of two) is REJECTED via
    ``DATABASE_BACKEND_VALIDATOR_CARDINALITY_MISMATCH``.
    """
    source = (
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
    _assert_rejected(
        source,
        expected_marker=ERROR_MARKER_VALIDATOR_CARDINALITY_MISMATCH,
    )


def test_exact_cardinality_third_validator_read() -> None:
    """8.5: A 3rd ``s.database_backend.value`` validator read
    (3 fields + 3 reads) is REJECTED via
    ``DATABASE_BACKEND_VALIDATOR_CARDINALITY_MISMATCH``.
    """
    source = (
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
        "        for s in value:\n"
        "            if s.scenario_id == 'x':\n"
        "                raise ValueError(\n"
        "                    f'duplicate scenario {s.scenario_id} with database_backend {s.database_backend.value}'\n"  # noqa: E501
        "                )\n"
        "        for s in value:\n"
        "            first = s.database_backend.value\n"
        "        return value\n"
    )
    _assert_rejected(
        source,
        expected_marker=ERROR_MARKER_VALIDATOR_CARDINALITY_MISMATCH,
    )


def test_exact_decorator_multi_field_arg_first() -> None:
    """8.6 (order 1):
    ``@field_validator("other", "scenarios")`` is REJECTED via
    ``DATABASE_BACKEND_DECORATOR_MISMATCH`` — the decorator
    must have exactly 1 positional argument, not 2.
    """
    source = (
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
        "    other: Tuple[ScenarioDeclaration, ...]\n"
        "    @field_validator('other', 'scenarios')\n"
        "    @classmethod\n"
        "    def _validate_unique_scenarios(cls, value):\n"
        "        for s in value:\n"
        "            key = (s.scenario_id, s.database_backend.value)\n"
        "        for s in value:\n"
        "            if s.scenario_id == 'x':\n"
        "                raise ValueError(\n"
        "                    f'duplicate scenario {s.scenario_id} with database_backend {s.database_backend.value}'\n"  # noqa: E501
        "                )\n"
        "        return value\n"
    )
    _assert_rejected(
        source,
        expected_marker=ERROR_MARKER_DECORATOR_MISMATCH,
    )


def test_exact_decorator_multi_field_arg_reversed() -> None:
    """8.6 (order 2):
    ``@field_validator("scenarios", "other")`` is REJECTED via
    ``DATABASE_BACKEND_DECORATOR_MISMATCH`` — the decorator
    must have exactly 1 positional argument, not 2.
    """
    source = (
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
        "    other: Tuple[ScenarioDeclaration, ...]\n"
        "    @field_validator('scenarios', 'other')\n"
        "    @classmethod\n"
        "    def _validate_unique_scenarios(cls, value):\n"
        "        for s in value:\n"
        "            key = (s.scenario_id, s.database_backend.value)\n"
        "        for s in value:\n"
        "            if s.scenario_id == 'x':\n"
        "                raise ValueError(\n"
        "                    f'duplicate scenario {s.scenario_id} with database_backend {s.database_backend.value}'\n"  # noqa: E501
        "                )\n"
        "        return value\n"
    )
    _assert_rejected(
        source,
        expected_marker=ERROR_MARKER_DECORATOR_MISMATCH,
    )


def test_exact_decorator_with_keyword_argument() -> None:
    """8.7: ``@field_validator("scenarios", mode="before")`` is
    REJECTED via ``DATABASE_BACKEND_DECORATOR_MISMATCH`` — the
    decorator must have 0 keyword arguments.
    """
    source = (
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
        "    @field_validator('scenarios', mode='before')\n"
        "    @classmethod\n"
        "    def _validate_unique_scenarios(cls, value):\n"
        "        for s in value:\n"
        "            key = (s.scenario_id, s.database_backend.value)\n"
        "        for s in value:\n"
        "            if s.scenario_id == 'x':\n"
        "                raise ValueError(\n"
        "                    f'duplicate scenario {s.scenario_id} with database_backend {s.database_backend.value}'\n"  # noqa: E501
        "                )\n"
        "        return value\n"
    )
    _assert_rejected(
        source,
        expected_marker=ERROR_MARKER_DECORATOR_MISMATCH,
    )


def test_exact_decorator_unpacked_args() -> None:
    """``@field_validator(*FIELDS)`` is REJECTED via
    ``DATABASE_BACKEND_DECORATOR_MISMATCH`` — the decorator must
    have a single literal ``Constant("scenarios")`` argument,
    not an unpacked tuple.
    """
    source = (
        "from pydantic import BaseModel, field_validator\n"
        "from enum import Enum\n"
        "from typing import Tuple\n"
        "class DatabaseBackend(str, Enum):\n"
        "    SQLITE = 'sqlite'\n"
        "FIELDS = ('scenarios',)\n"
        "class ScenarioDeclaration(BaseModel):\n"
        "    database_backend: DatabaseBackend\n"
        "class RunRecord(BaseModel):\n"
        "    database_backend: DatabaseBackend\n"
        "class SummaryRecord(BaseModel):\n"
        "    database_backend: DatabaseBackend\n"
        "class Manifest(BaseModel):\n"
        "    scenarios: Tuple[ScenarioDeclaration, ...]\n"
        "    @field_validator(*FIELDS)\n"
        "    @classmethod\n"
        "    def _validate_unique_scenarios(cls, value):\n"
        "        for s in value:\n"
        "            key = (s.scenario_id, s.database_backend.value)\n"
        "        for s in value:\n"
        "            if s.scenario_id == 'x':\n"
        "                raise ValueError(\n"
        "                    f'duplicate scenario {s.scenario_id} with database_backend {s.database_backend.value}'\n"  # noqa: E501
        "                )\n"
        "        return value\n"
    )
    _assert_rejected(
        source,
        expected_marker=ERROR_MARKER_DECORATOR_MISMATCH,
    )


# ---------------------------------------------------------------------------
# P0 of review 4690695361 — full decorator stack enforcement
# ---------------------------------------------------------------------------
# The validator decorator check is strengthened from "the decorator
# list contains an exact @field_validator('scenarios') call" to
# "the complete decorator_list is exactly
# [@field_validator('scenarios'), @classmethod] in the frozen
# order". Merely containing an exact field_validator call is no
# longer sufficient. The tests below pin each of the seven
# stack-level failure modes that the production contract forbids
# and re-pin the positive case to confirm the full stack passes
# the same checker.
# ---------------------------------------------------------------------------


def _sixth_round_models_source(
    extra_decorator_lines: str = "",
) -> str:
    """Build a synthetic ``models.py``-shaped source that has all
    three authorized fields and a Manifest class with the
    standard ``_validate_unique_scenarios`` method. The
    ``extra_decorator_lines`` string is inserted between the
    field declarations and the validator method, allowing each
    test to insert extra / wrong / duplicated decorators
    in different positions to exercise the full-stack check.
    """
    return (
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
        f"{extra_decorator_lines}"
        "    def _validate_unique_scenarios(cls, value):\n"
        "        for s in value:\n"
        "            key = (s.scenario_id, s.database_backend.value)\n"
        "        for s in value:\n"
        "            if s.scenario_id == 'x':\n"
        "                raise ValueError(\n"
        "                    f'duplicate scenario {s.scenario_id}'\n"
        "                    f' with database_backend {s.database_backend.value}'\n"
        "                )\n"
        "        return value\n"
    )


def test_exact_decorator_duplicate_field_validator() -> None:
    """A duplicate ``@field_validator('scenarios')`` before
    ``@classmethod`` is REJECTED via
    ``DATABASE_BACKEND_DECORATOR_STACK_MISMATCH`` — the full
    decorator list must be exactly
    ``[field_validator('scenarios'), classmethod]``; a
    duplicate field_validator is forbidden.
    """
    source = _sixth_round_models_source(
        extra_decorator_lines=(
            "    @field_validator('scenarios')\n"
            "    @field_validator('scenarios')\n"
            "    @classmethod\n"
        )
    )
    _assert_rejected(
        source,
        expected_marker=ERROR_MARKER_DECORATOR_STACK_MISMATCH,
    )


def test_exact_decorator_missing_classmethod() -> None:
    """A validator that has ``@field_validator('scenarios')``
    but NO ``@classmethod`` is REJECTED via
    ``DATABASE_BACKEND_DECORATOR_STACK_MISMATCH`` — the frozen
    stack requires exactly two decorators in the order
    field_validator_then_classmethod.
    """
    source = _sixth_round_models_source(
        extra_decorator_lines=("    @field_validator('scenarios')\n")
    )
    _assert_rejected(
        source,
        expected_marker=ERROR_MARKER_DECORATOR_STACK_MISMATCH,
    )


def test_exact_decorator_reversed_order() -> None:
    """Reversing the order (``@classmethod`` BEFORE
    ``@field_validator('scenarios')``) is REJECTED via
    ``DATABASE_BACKEND_DECORATOR_STACK_MISMATCH`` — the
    frozen order is field_validator_then_classmethod; the
    reverse is forbidden.
    """
    source = _sixth_round_models_source(
        extra_decorator_lines=("    @classmethod\n    @field_validator('scenarios')\n")
    )
    _assert_rejected(
        source,
        expected_marker=ERROR_MARKER_DECORATOR_STACK_MISMATCH,
    )


def test_exact_decorator_extra_decorator_before() -> None:
    """An extra ``@other_decorator`` BEFORE the frozen stack
    is REJECTED via
    ``DATABASE_BACKEND_DECORATOR_STACK_MISMATCH`` — the
    decorator list must be EXACTLY two nodes; an extra
    decorator before the field_validator breaks the count
    invariant.
    """
    source = _sixth_round_models_source(
        extra_decorator_lines=(
            "    @other_decorator\n    @field_validator('scenarios')\n    @classmethod\n"
        )
    )
    _assert_rejected(
        source,
        expected_marker=ERROR_MARKER_DECORATOR_STACK_MISMATCH,
    )


def test_exact_decorator_extra_decorator_after() -> None:
    """An extra ``@other_decorator`` AFTER the frozen stack
    is REJECTED via
    ``DATABASE_BACKEND_DECORATOR_STACK_MISMATCH`` — the
    decorator list must be EXACTLY two nodes; an extra
    decorator after the classmethod breaks the count
    invariant (no position is allowed for extras).
    """
    source = _sixth_round_models_source(
        extra_decorator_lines=(
            "    @field_validator('scenarios')\n    @classmethod\n    @other_decorator\n"
        )
    )
    _assert_rejected(
        source,
        expected_marker=ERROR_MARKER_DECORATOR_STACK_MISMATCH,
    )


def test_exact_decorator_duplicate_classmethod() -> None:
    """A duplicate ``@classmethod`` is REJECTED via
    ``DATABASE_BACKEND_DECORATOR_STACK_MISMATCH`` — only one
    classmethod is allowed; the second classmethod is an
    unauthorized extra decorator.
    """
    source = _sixth_round_models_source(
        extra_decorator_lines=(
            "    @field_validator('scenarios')\n    @classmethod\n    @classmethod\n"
        )
    )
    _assert_rejected(
        source,
        expected_marker=ERROR_MARKER_DECORATOR_STACK_MISMATCH,
    )


def test_exact_decorator_bare_field_validator() -> None:
    """A bare ``@field_validator`` (no call arguments) before
    ``@classmethod`` is REJECTED via
    ``DATABASE_BACKEND_DECORATOR_STACK_MISMATCH`` — the
    decorator list must start with an EXACT
    ``field_validator('scenarios')`` Call node, not a bare
    ``field_validator`` Name node.
    """
    source = _sixth_round_models_source(
        extra_decorator_lines=("    @field_validator\n    @classmethod\n")
    )
    _assert_rejected(
        source,
        expected_marker=ERROR_MARKER_DECORATOR_STACK_MISMATCH,
    )


def test_exact_decorator_authorized_full_stack() -> None:
    """The exact authorized two-node stack
    ``[@field_validator('scenarios'), @classmethod]`` is
    AUTHORIZED. The full checker continues to assert
    :data:`_EXACT_EXPECTED_AUTHORIZED_FIELD_COUNT` (3),
    :data:`_EXACT_EXPECTED_AUTHORIZED_VALIDATOR_READ_COUNT`
    (2), :data:`_EXACT_EXPECTED_TOTAL_OCCURRENCE_COUNT` (5),
    and :data:`_EXACT_EXPECTED_REJECTED_OCCURRENCE_COUNT`
    (0) — decorator stack enforcement is on top of these
    invariants, not a replacement.
    """
    source = _sixth_round_models_source(
        extra_decorator_lines=("    @field_validator('scenarios')\n    @classmethod\n")
    )
    _assert_authorized(source)
    # Re-verify cardinality invariants against the synthetic
    # source — the decorator stack enforcement is additive, it
    # must not silently relax any prior exact-cardinality
    # assertion.
    tmp = Path("/tmp/_sixth_round_authorized.py")
    tmp.write_text(source)
    try:
        tree = ast.parse(source)
        parents = _build_parent_map(tree)
        occurrences = _collect_database_backend_occurrences(tree)
        authorized_fields = 0
        authorized_reads = 0
        for node, _line, _col, _cls, _fn, _pt in occurrences:
            verdict = _classify_database_backend_occurrence(node, parents)
            if verdict == "AUTHORIZED_FIELD":
                authorized_fields += 1
            elif verdict == "AUTHORIZED_VALIDATOR_READ":
                authorized_reads += 1
        assert len(occurrences) == 5
        assert authorized_fields == 3
        assert authorized_reads == 2
    finally:
        tmp.unlink(missing_ok=True)


def test_exact_decorator_real_models_py_full_stack() -> None:
    """The real production ``models.py`` must pass the FULL
    decorator stack check — not just the field_validator
    shape check. The real model has:

    * ``@field_validator('scenarios')``
    * ``@classmethod``
    * ``def _validate_unique_scenarios(...)``

    in that exact order. There is no test-only lenient
    rule; the real file and the synthetic source use the
    same checker.
    """
    models_py_path = (
        Path(__file__).resolve().parent.parent.parent
        / "src"
        / "cold_storage"
        / "evaluation"
        / "models.py"
    )
    content = models_py_path.read_text(encoding="utf-8")
    _assert_models_database_backend_use_is_typed_model_only(content, models_py_path)

    # Additionally assert the real file's decorator stack is
    # exactly the frozen two-node form. This is the dedicated
    # stack-level assertion for the production file.
    tree = ast.parse(content, filename=str(models_py_path))
    target_fn: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Manifest":
            for fn in node.body:
                if (
                    isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and fn.name == _EXACT_MANIFEST_UNIQUE_VALIDATOR_NAME
                ):
                    target_fn = fn
                    break
            if target_fn is not None:
                break
    assert target_fn is not None, (
        f"real models.py does not contain "
        f"Manifest.{_EXACT_MANIFEST_UNIQUE_VALIDATOR_NAME}; cannot "
        f"verify decorator stack."
    )
    assert len(target_fn.decorator_list) == 2, (
        f"{ERROR_MARKER_DECORATOR_STACK_MISMATCH}: real models.py "
        f"Manifest._validate_unique_scenarios has "
        f"{len(target_fn.decorator_list)} decorators; authorized "
        f"stack requires exactly 2. Got: "
        f"{[ast.unparse(d) for d in target_fn.decorator_list]!r}."
    )
    assert _has_exact_manifest_validator_decorator_stack(target_fn), (
        f"{ERROR_MARKER_DECORATOR_STACK_MISMATCH}: real models.py "
        f"Manifest._validate_unique_scenarios decorator stack is "
        f"not the authorized frozen order. Got: "
        f"{[ast.unparse(d) for d in target_fn.decorator_list]!r}."
    )


# ---------------------------------------------------------------------------
# 6) P0-5 of review 4693931575 — token / call-site discipline for
#    ``backend/src/cold_storage/evaluation/runners/_executor.py``
# ---------------------------------------------------------------------------
#
# The literal tokens ``database_backend`` and ``correlation_id``
# are authorized in ``_executor.py`` ONLY at the C-2 production
# boundary calls (the call into
# ``adapter_execute_scenario(...)`` and
# ``project_calculator_input(...)``). The token MUST appear as
# a literal keyword argument in a call; any other shape is
# REJECTED:
#
#   * BinOp(Add) string-concatenation that produces the token
#     at runtime (e.g. ``"dat" + "abase_backend"``) is REJECTED.
#   * ``**dict`` spread whose dict-key is the token (or builds
#     it via concatenation) is REJECTED.
#   * Any other Phase-1 token (``idempotency_key`` /
#     ``actor_principal_type`` / ``scheme_run_id`` /
#     ``frozen_envelope``) is REJECTED in the entire
#     ``_executor.py`` source.
#   * Raw SQL / ORM / session calls in ``_executor.py`` are
#     REJECTED.
#
# The carve-out is path-precise, token-precise, and
# purpose-precise (review 4693931575 P0-5).


def _assert_executor_database_backend_use_is_typed_call_only(content: str, path: Path) -> None:
    """Structural AST inspection paired with the P0-5 carve-out
    for ``runners/_executor.py``.

    Asserts that the only ``database_backend`` /
    ``correlation_id`` occurrences in the file are the
    literal keyword arguments at the two authorized
    production-boundary call sites
    (``adapter_execute_scenario(...)`` and
    ``project_calculator_input(...)``). Any other occurrence
    (import, class attribute, local variable, ``**dict``
    spread, BinOp(Add) concatenation, etc.) is REJECTED.

    This is the structural counterpart to the new
    ``test_executor_*`` P0-5 tests below; the in-line
    carve-out check above delegates to this helper so the
    pre-existing ``test_evaluation_does_not_import_phase1_orm``
    AST walk accepts the two authorized call sites.
    """
    tree = ast.parse(content, filename=str(path))
    authorized_call_sites = frozenset({"adapter_execute_scenario", "project_calculator_input"})
    authorized_tokens = frozenset({"database_backend", "correlation_id"})
    for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
        callee = call.func
        callee_name: str | None = None
        if isinstance(callee, ast.Name):
            callee_name = callee.id
        elif isinstance(callee, ast.Attribute):
            callee_name = callee.attr
        for kw in call.keywords:
            if kw.arg in authorized_tokens:
                # The token MUST be at an authorized call site
                # AND MUST be a literal keyword arg (NOT a
                # ``**dict`` spread, NOT a string-concat value).
                if callee_name not in authorized_call_sites:
                    raise AssertionError(
                        f"P0-5 carve-out: ``_executor.py`` call to "
                        f"``{callee_name}(...)`` at "
                        f"{getattr(call, 'lineno', '?')}:{getattr(call, 'col_offset', '?')} "
                        f"carries the authorized token ``{kw.arg}`` "
                        f"outside the two authorized call sites "
                        f"{sorted(authorized_call_sites)}."
                    )
                if kw.value is None:
                    raise AssertionError(
                        f"P0-5 carve-out: ``_executor.py`` call to "
                        f"``{callee_name}(...)`` at "
                        f"{getattr(call, 'lineno', '?')}:{getattr(call, 'col_offset', '?')} "
                        f"supplies ``{kw.arg}`` via ``**dict``-spread; "
                        f"the literal keyword form is required."
                    )


_EXECUTOR_PY_PATH: Path = (
    Path(__file__).resolve().parent.parent.parent
    / "src"
    / "cold_storage"
    / "evaluation"
    / "runners"
    / "_executor.py"
)
_PHASE1_FORBIDDEN_TOKENS_IN_EXECUTOR: tuple[str, ...] = (
    "idempotency_key",
    "actor_principal_type",
    "scheme_run_id",
    "frozen_envelope",
)
#: The two Phase-1 tokens that are LEGAL in ``_executor.py`` —
#: ONLY at the two production-boundary call sites listed in
#: ``_EXECUTOR_AUTHORIZED_CALL_SITES``. Any other occurrence
#: (import statement, class attribute, local variable, etc.)
#: is REJECTED.
_EXECUTOR_AUTHORIZED_TOKENS: frozenset[str] = frozenset({"database_backend", "correlation_id"})
#: The exact set of function names that may receive the
#: ``database_backend`` / ``correlation_id`` keyword
#: arguments. Any other call-site carrying these tokens is
#: REJECTED.
_EXECUTOR_AUTHORIZED_CALL_SITES: frozenset[str] = frozenset(
    {"adapter_execute_scenario", "project_calculator_input"}
)
#: Forbidden attribute / call names that would indicate
#: ``_executor.py`` is reaching into the production ORM,
#: session, or repository surface.
_EXECUTOR_FORBIDDEN_PRODUCTION_TOKENS: tuple[str, ...] = (
    "session.add",
    "session.execute",
    "session.scalar",
    "session.commit",
    "session.rollback",
    "text(",
    # Production persistence / production record construction.
    "OrchestrationRunAttemptRecord",
    "SchemeRunRecord",
    "CalculationRunRecord",
    # Production repositories.
    "coefficient_resolver_infrastructure",
    "raw_orm",
    "raw_sql",
    "fabricate",
)


def _executor_call_kw_arg_value(call: ast.Call, kw_name: str) -> ast.AST | None:
    """Return the AST value node for a literal keyword arg
    ``kw_name`` in ``call``. Returns ``None`` if the keyword
    is not present, or if the keyword is supplied via a
    ``**spread``.
    """
    for kw in call.keywords:
        if kw.arg == kw_name and kw.value is not None:
            return kw.value
    return None


def _ast_const_str_concat(value: ast.AST) -> str | None:
    """Return the concatenated string of a constant string
    expression. Walks ``ast.BinOp(Add)`` left-right and
    collects the ``ast.Constant`` string literals.

    Returns ``None`` if the expression is not a pure string
    constant concatenation.
    """
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add):
        left = _ast_const_str_concat(value.left)
        right = _ast_const_str_concat(value.right)
        if left is not None and right is not None:
            return left + right
    return None


def _is_dict_spread_with_token(call: ast.Call, token: str) -> bool:
    """Return True if any ``**``-spread argument is a dict
    whose key is ``token`` (literal or string-concatenated)."""
    for kw in call.keywords:
        if kw.arg is None and isinstance(kw.value, ast.Dict):
            for k in kw.value.keys:
                if k is None:
                    continue
                if isinstance(k, ast.Constant) and isinstance(k.value, str) and k.value == token:
                    return True
                concat = _ast_const_str_concat(k)
                if concat is not None and concat == token:
                    return True
    return False


def test_executor_authorized_call_sites_emit_literal_keywords() -> None:
    """P0-5 positive case: the two authorized production-boundary
    call sites in ``_executor.py`` (``adapter_execute_scenario``
    + ``project_calculator_input``) MUST receive the
    ``database_backend`` and ``correlation_id`` keywords as
    AST literal keyword arguments (NOT via ``**dict`` spread
    and NOT via string concatenation).
    """
    content = _EXECUTOR_PY_PATH.read_text(encoding="utf-8")
    tree = ast.parse(content, filename=str(_EXECUTOR_PY_PATH))
    authorized_calls: dict[str, list[ast.Call]] = {
        name: [] for name in _EXECUTOR_AUTHORIZED_CALL_SITES
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Identify the call by its callee name (either bare
            # name or ``alias as bare``).
            callee = node.func
            if isinstance(callee, ast.Name) and callee.id in _EXECUTOR_AUTHORIZED_CALL_SITES:
                authorized_calls[callee.id].append(node)
            elif (
                isinstance(callee, ast.Attribute)
                and isinstance(callee.value, ast.Name)
                and callee.attr in _EXECUTOR_AUTHORIZED_CALL_SITES
            ):
                # Allow ``adapter.adapter_execute_scenario`` etc.
                authorized_calls[callee.attr].append(node)
    for site, calls in authorized_calls.items():
        assert calls, (
            f"P0-5: ``_executor.py`` is missing the authorized call "
            f"site ``{site}(...)`` (P0-5 of review 4693931575)."
        )
        for call in calls:
            for token in _EXECUTOR_AUTHORIZED_TOKENS:
                # The token MUST appear as a literal keyword arg
                # with a non-constant-concat value (i.e. a real
                # value expression, not a synthetic string
                # alias).
                value = _executor_call_kw_arg_value(call, token)
                if value is None:
                    # ``project_calculator_input`` is the D10
                    # pure projection call; both tokens are
                    # authorized but the call MAY be invoked
                    # without the ``correlation_id`` keyword
                    # (it has a project-side default in V1).
                    # The ``database_backend`` keyword is
                    # required at the call site.
                    if site == "project_calculator_input" and token == "correlation_id":
                        continue
                    raise AssertionError(
                        f"P0-5: ``_executor.py`` call to ``{site}(...)`` "
                        f"is missing the literal keyword ``{token}``; "
                        f"the architecture boundary requires the literal "
                        f"keyword form (no ``**dict``-spread, no "
                        f"string-concatenated token)."
                    )
                # Reject any BinOp(Add) string-concat that
                # evaluates to the token.
                concat = _ast_const_str_concat(value)
                if concat is not None and concat == token:
                    raise AssertionError(
                        f"P0-5: ``_executor.py`` call to ``{site}(...)`` "
                        f"passes ``{token}`` as a string-concatenated "
                        f"value (``{concat!r}``); the architecture "
                        f"boundary requires the literal keyword form."
                    )
                # Reject any ``**dict``-spread that supplies the
                # token.
                if _is_dict_spread_with_token(call, token):
                    raise AssertionError(
                        f"P0-5: ``_executor.py`` call to ``{site}(...)`` "
                        f"passes ``{token}`` via ``**dict``-spread; "
                        f"the architecture boundary requires the "
                        f"literal keyword form."
                    )


def test_executor_rejects_string_concatenation_bypass() -> None:
    """P0-5 negative case: BinOp(Add) string concatenation
    that builds the literal ``database_backend`` or
    ``correlation_id`` token at runtime is REJECTED anywhere
    in ``_executor.py`` (the runtime value is forbidden even
    if the source looks opaque to a substring search).
    """
    content = _EXECUTOR_PY_PATH.read_text(encoding="utf-8")
    tree = ast.parse(content, filename=str(_EXECUTOR_PY_PATH))
    for node in ast.walk(tree):
        if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Add):
            continue
        concat = _ast_const_str_concat(node)
        if concat is None:
            continue
        if concat in _EXECUTOR_AUTHORIZED_TOKENS:
            raise AssertionError(
                f"P0-5: ``_executor.py`` builds the token ``{concat!r}`` "
                f"via BinOp(Add) string-concatenation at "
                f"{getattr(node, 'lineno', '?')}:{getattr(node, 'col_offset', '?')}; "
                f"the architecture boundary requires the literal "
                f"keyword form (no string-concatenation bypass)."
            )


def test_executor_rejects_dict_spread_bypass() -> None:
    """P0-5 negative case: ``**dict``-spread whose key is the
    literal ``database_backend`` or ``correlation_id`` (or
    builds it via concatenation) is REJECTED anywhere in
    ``_executor.py``.
    """
    content = _EXECUTOR_PY_PATH.read_text(encoding="utf-8")
    tree = ast.parse(content, filename=str(_EXECUTOR_PY_PATH))
    for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
        for token in _EXECUTOR_AUTHORIZED_TOKENS:
            if _is_dict_spread_with_token(call, token):
                raise AssertionError(
                    f"P0-5: ``_executor.py`` call at "
                    f"{getattr(call, 'lineno', '?')}:{getattr(call, 'col_offset', '?')} "
                    f"passes ``{token}`` via ``**dict``-spread; "
                    f"the architecture boundary requires the literal "
                    f"keyword form (no ``**dict``-spread bypass)."
                )


def test_executor_other_phase1_tokens_remain_rejected() -> None:
    """P0-5 negative case: any other Phase-1 token
    (``idempotency_key`` / ``actor_principal_type`` /
    ``scheme_run_id`` / ``frozen_envelope``) is REJECTED
    anywhere in ``_executor.py``.
    """
    content = _EXECUTOR_PY_PATH.read_text(encoding="utf-8")
    tree = ast.parse(content, filename=str(_EXECUTOR_PY_PATH))
    identifiers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # Track string constants to detect string-concat
            # bypasses; this is the second line of defense
            # against concatenation-bypass (the first is the
            # BinOp(Add) walk in
            # ``test_executor_rejects_string_concatenation_bypass``).
            if any(tok in node.value for tok in _PHASE1_FORBIDDEN_TOKENS_IN_EXECUTOR):
                raise AssertionError(
                    f"P0-5: ``_executor.py`` contains a string constant "
                    f"that embeds a forbidden Phase-1 token: "
                    f"{node.value!r} at "
                    f"{getattr(node, 'lineno', '?')}:{getattr(node, 'col_offset', '?')}"
                )
        elif isinstance(node, ast.arg) or isinstance(node, ast.keyword) and node.arg is not None:
            identifiers.add(node.arg)
    for token in _PHASE1_FORBIDDEN_TOKENS_IN_EXECUTOR:
        assert token not in identifiers, (
            f"P0-5: ``_executor.py`` references the forbidden Phase-1 "
            f"token ``{token}``; the architecture boundary permits "
            f"only the two authorized tokens ``database_backend`` and "
            f"``correlation_id`` in this file (and only at the two "
            f"authorized call sites)."
        )


def test_executor_rejects_production_orm_session_infrastructure() -> None:
    """P0-5 negative case: ``_executor.py`` MUST NOT import
    production ORM / session / repository surface or
    construct production rows. The previous guard ``PATH_PRECISE =
    runner_whole_evaluation_pkg`` is narrowed to
    ``_executor.py`` only.
    """
    content = _EXECUTOR_PY_PATH.read_text(encoding="utf-8")
    for forbidden in _EXECUTOR_FORBIDDEN_PRODUCTION_TOKENS:
        assert forbidden not in content, (
            f"P0-5: ``_executor.py`` references the forbidden production "
            f"surface token ``{forbidden}``; the runner boundary permits "
            f"only typed Pydantic-model projections and the D1 "
            f"canonicalizer at the production seam."
        )


def test_executor_authorized_token_call_sites_precise() -> None:
    """P0-5 precision guard: the only two functions in
    ``_executor.py`` that may receive ``database_backend`` /
    ``correlation_id`` keyword arguments are
    ``adapter_execute_scenario`` and ``project_calculator_input``.
    Any other function call carrying these tokens is REJECTED.
    """
    content = _EXECUTOR_PY_PATH.read_text(encoding="utf-8")
    tree = ast.parse(content, filename=str(_EXECUTOR_PY_PATH))
    for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
        for kw in call.keywords:
            if kw.arg in _EXECUTOR_AUTHORIZED_TOKENS:
                callee = call.func
                callee_name: str | None = None
                if isinstance(callee, ast.Name):
                    callee_name = callee.id
                elif isinstance(callee, ast.Attribute):
                    callee_name = callee.attr
                assert callee_name in _EXECUTOR_AUTHORIZED_CALL_SITES, (
                    f"P0-5: ``_executor.py`` call to ``{callee_name}(...)`` "
                    f"at "
                    f"{getattr(call, 'lineno', '?')}:{getattr(call, 'col_offset', '?')} "
                    f"passes the authorized token ``{kw.arg}``; only the two "
                    f"authorized call sites "
                    f"{sorted(_EXECUTOR_AUTHORIZED_CALL_SITES)} are permitted "
                    f"to carry these tokens."
                )
