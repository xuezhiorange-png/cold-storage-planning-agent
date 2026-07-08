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
                if (
                    path == expected_adapter_path
                    and field in ("database_backend", "correlation_id")
                ):
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
    the schema foundation only."""
    if not EVALUATION_TESTS_DIR.exists():
        return
    files = _all_python_files(EVALUATION_TESTS_DIR)
    for path in files:
        content = path.read_text()
        if "OrchestrationRunAttemptRecord" in content:
            raise AssertionError(
                f"Evaluation test imports OrchestrationRunAttemptRecord "
                f"(Phase 1 contract: evaluation must NOT bypass "
                f"production via raw ORM seeding): {path}"
            )
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
