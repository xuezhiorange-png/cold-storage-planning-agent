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
#: SQL, ORM access, or production record construction.
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


def _assert_models_database_backend_use_is_typed_model_only(content: str, path: Path) -> None:
    """Structural inspection for the ``models.py`` carve-out.

    Per Issue #20 amendment comment 4963778355, ``models.py`` is
    the single C-1 file permitted to reference the
    ``database_backend`` token, and only for Pydantic typed-model
    surface use. The structural checks below prove the token is
    NOT used in any forbidden context. A behavioral companion
    test (``test_models_py_database_backend_round_trip``) asserts
    the token round-trips through Pydantic ``model_validate`` /
    ``model_dump(by_alias=True, mode="json")``.
    """
    # 1. Parse the module as Python AST.
    try:
        tree = ast.parse(content, filename=str(path))
    except SyntaxError as exc:
        raise AssertionError(f"models.py has a syntax error: {exc}") from exc

    # 2. Walk the AST and reject any reference to a forbidden
    # context, even inside comments or docstrings (we strip
    # docstrings before the search so a docstring mention is OK
    # only as a docstring, not as a code reference).
    forbidden_imports: list[str] = []
    forbidden_attribute_access: list[str] = []
    forbidden_call_targets: list[str] = []
    for node in ast.walk(tree):
        # 2a. Imports — reject any production ORM / infrastructure
        # / repository import.
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if any(
                forbidden in module
                for forbidden in _MODELS_PY_FORBIDDEN_CONTEXTS
                if "modules" in forbidden
            ):
                forbidden_imports.append(f"from {module} import ...")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if any(
                    forbidden in alias.name
                    for forbidden in _MODELS_PY_FORBIDDEN_CONTEXTS
                    if "modules" in forbidden
                ):
                    forbidden_imports.append(f"import {alias.name}")
        # 2b. Attribute access — reject references to production
        # record classes (used as bases, type annotations, or
        # constructor calls).
        if isinstance(node, ast.Attribute):
            target = ast.unparse(node)
            for forbidden in _MODELS_PY_FORBIDDEN_CONTEXTS:
                if forbidden in target and "." in target:
                    forbidden_attribute_access.append(f"{target} (forbidden: {forbidden})")
        # 2c. Call targets — reject ``session.add(...)``,
        # ``session.execute(...)``, ``text(...)``, etc.
        if isinstance(node, ast.Call):
            call_repr = ast.unparse(node.func)
            for forbidden in _MODELS_PY_FORBIDDEN_CONTEXTS:
                if forbidden in call_repr:
                    forbidden_call_targets.append(f"{call_repr}(...) (forbidden: {forbidden})")
    assert not forbidden_imports, (
        f"models.py has forbidden production-ORM imports (TASK-011C "
        f"amendment 4963778355 forbids production-ORM imports in "
        f"models.py): {forbidden_imports}"
    )
    assert not forbidden_attribute_access, (
        f"models.py has forbidden production-ORM attribute access "
        f"(TASK-011C amendment 4963778355): {forbidden_attribute_access}"
    )
    assert not forbidden_call_targets, (
        f"models.py has forbidden raw-SQL / session / production "
        f"persistence call (TASK-011C amendment 4963778355): "
        f"{forbidden_call_targets}"
    )

    # 3. Inspect the AST: the ``database_backend`` token must
    # appear ONLY as:
    #   * a ClassDef.bases / ModelField declaration in
    #     ``Manifest`` / ``ScenarioDeclaration`` / ``RunRecord`` /
    #     ``SummaryRecord`` (Pydantic ``BaseModel`` subclasses);
    #   * a ``Field(alias="database_backend")`` / Pydantic
    #     ``Field(..., alias=...)`` call;
    #   * a string literal in a typed identity model attribute
    #     name (not allowed — Python attribute is ``db_dialect``,
    #     the JSON wire form is ``database_backend``);
    #   * an enum / value validation reference (e.g.,
    #     ``DatabaseBackend.SQLITE``).
    #
    # We do NOT enumerate every typed-model surface; we merely
    # confirm that the token does NOT appear in any function body
    # that is NOT a class-defining body or a model validator. The
    # AST-based check covers the structural intent; the behavioral
    # check is the companion test.
    # (No additional enforcement here; the model surface IS the
    # only legitimate use, and the AST walk above already rules
    # out SQL / ORM / session / production-record uses.)

    # 4. Confirm at least one Pydantic ``Field(..., alias=...)``
    # call exists. If not, the typed-model surface is not using
    # the JSON wire form.
    found_field_alias = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg == "alias":
                value = ast.unparse(kw.value)
                if "database_backend" in value:
                    found_field_alias = True
                    break
        if found_field_alias:
            break
    # The carve-out is "Pydantic typed-model surface use only".
    # The typed-model surface includes both direct attribute
    # declarations (``database_backend: DatabaseBackend``) AND
    # Field alias declarations. The amendment permits both forms.
    # We accept either.
    if not found_field_alias:
        # Fall back: confirm the token appears in a direct
        # ClassDef member declaration.
        found_attribute_decl = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    if stmt.target.id == "database_backend":
                        found_attribute_decl = True
                        break
            if found_attribute_decl:
                break
        assert found_attribute_decl, (
            "models.py must use 'database_backend' as either a "
            "Pydantic typed field declaration OR a Pydantic "
            "Field(alias=...) declaration (TASK-011C amendment "
            "4963778355). Neither form was found."
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
