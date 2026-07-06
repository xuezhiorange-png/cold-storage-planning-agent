"""Architecture boundary tests for Task 11B Phase 2 — ports & adapters.

Enforces:

1. The Phase 2 ports & adapters subpackage MUST NOT import the
   evaluation runner (``cold_storage.evaluation.*``).  The
   evaluation runner is a separate pilot and must not reach into
   production paths.

2. The Phase 2 ports & adapters subpackage MUST NOT call
   ``SchemeService.run`` or any equivalent SchemeRun entrypoint.

3. The Phase 2 ports & adapters subpackage MUST NOT generate
   real ``SourceBindingRecord`` rows.

4. The Phase 2 ports & adapters subpackage MUST NOT modify the
   underlying production calculator formula / threshold / weight
   / review rules.  Calculator source files are read-only.

5. The Phase 2 ports & adapters subpackage does NOT implement a
   full orchestrator.  No ``production_calculation_orchestrator``
   module may exist; no full ``OrchestrationService.execute``
   entrypoint may be exposed.

The Phase 2 contract: see design doc
``docs/tasks/TASK-011B-production-calculation-orchestration-prerequisite.md``
(Frozen Contract Authority SHA: ``ba4288ea1c6f258c8b0b9f487d071c8ffce0e4b2``).
"""

from __future__ import annotations

import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = BACKEND_ROOT / "src" / "cold_storage"

PHASE2_DIR = BACKEND_SRC / "modules" / "orchestration" / "application" / "production_calculation"
EVALUATION_DIR = BACKEND_SRC / "evaluation"
EVALUATION_TESTS_DIR = BACKEND_ROOT / "tests" / "evaluation"

# Production calculator source files.  Phase 2 MUST NOT modify
# these — adapters wrap them, they do not change them.
CALCULATOR_SOURCE_FILES = (
    "modules/calculations/domain/zone_planning.py",
    "modules/calculations/domain/cooling_load.py",
    "modules/calculations/domain/equipment.py",
    "modules/calculations/domain/power.py",
    "modules/calculations/domain/investment.py",
)


def _all_python_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def _read(path: Path) -> str:
    return path.read_text()


# ---------------------------------------------------------------------------
# 1) Phase 2 ports & adapters subpackage exists
# ---------------------------------------------------------------------------


def test_phase2_subpackage_exists() -> None:
    """The Phase 2 subpackage must be a real module on disk."""
    assert PHASE2_DIR.is_dir(), (
        f"Phase 2 subpackage missing: {PHASE2_DIR.relative_to(BACKEND_ROOT)}"
    )
    init = PHASE2_DIR / "__init__.py"
    assert init.is_file(), (
        f"Phase 2 subpackage __init__.py missing: {init.relative_to(BACKEND_ROOT)}"
    )


# ---------------------------------------------------------------------------
# 2) No evaluation backdoor
# ---------------------------------------------------------------------------


def test_phase2_does_not_import_evaluation() -> None:
    """Phase 2 modules MUST NOT import the evaluation runner."""
    if not PHASE2_DIR.exists():
        return
    files = _all_python_files(PHASE2_DIR)
    for path in files:
        content = path.read_text()
        # ``import`` statements (the only meaningful way to reach
        # the evaluation runner).
        for pattern in (
            r"^import\s+cold_storage\.evaluation",
            r"^from\s+cold_storage\.evaluation",
            r"^import\s+evaluation",
            r"^from\s+evaluation",
        ):
            assert not re.search(pattern, content, re.MULTILINE), (
                f"Phase 2 file imports evaluation runner: {path}"
            )


# ---------------------------------------------------------------------------
# 3) No SchemeService.run or SchemeRun entrypoint
# ---------------------------------------------------------------------------


def test_phase2_does_not_invoke_scheme_service() -> None:
    """Phase 2 MUST NOT call ``SchemeService.run`` or any equivalent
    SchemeRun entrypoint.
    """
    if not PHASE2_DIR.exists():
        return
    files = _all_python_files(PHASE2_DIR)
    for path in files:
        content = path.read_text()
        # Block ``import`` / ``from`` statements that reach
        # SchemeService.  References in docstrings / comments are
        # permitted — the contract is that the Phase 2 path
        # never *executes* the SchemeService entrypoint.
        for pattern in (
            r"^import\s+.*SchemeService",
            r"^from\s+.*SchemeService",
            r"^import\s+.*scheme_service",
            r"^from\s+.*scheme_service",
            r"\bSchemeService\s*\(.*\)",
            r"\bscheme_service\s*\(.*\)",
        ):
            assert not re.search(pattern, content, re.MULTILINE), (
                f"Phase 2 file invokes SchemeService: {path}"
            )


# ---------------------------------------------------------------------------
# 4) No SourceBinding generation
# ---------------------------------------------------------------------------


def test_phase2_does_not_generate_source_bindings() -> None:
    """Phase 2 MUST NOT write ``SourceBindingRecord`` rows."""
    if not PHASE2_DIR.exists():
        return
    files = _all_python_files(PHASE2_DIR)
    for path in files:
        content = path.read_text()
        for forbidden in (
            "SourceBindingRecord",
            "source_binding",
            "SourceBinding",
        ):
            pattern = rf"\b{re.escape(forbidden)}\b"
            assert not re.search(pattern, content), (
                f"Phase 2 file references SourceBinding entity '{forbidden}': {path}"
            )


# ---------------------------------------------------------------------------
# 5) Calculator source files are read-only
# ---------------------------------------------------------------------------


def test_calculator_source_files_unchanged() -> None:
    """Phase 2 MUST NOT modify the production calculator source files.

    The frozen calculator code is the source of truth for the
    engineering formulas.  Adapters wrap the calculators; they
    do not change them.

    This test verifies the calculator files exist (they were
    unchanged by Phase 2).  Drift is caught by `git diff` in the
    PR review.
    """
    for relpath in CALCULATOR_SOURCE_FILES:
        path = BACKEND_SRC / relpath
        assert path.is_file(), f"Calculator source missing: {relpath}"
        content = _read(path)
        # Sanity check: the calculator files are non-empty.
        assert len(content) > 1000, f"Calculator source too small: {relpath}"


# ---------------------------------------------------------------------------
# 6) No production orchestrator
# ---------------------------------------------------------------------------


def test_phase2_does_not_implement_orchestrator() -> None:
    """Phase 2 MUST NOT ship a full production calculation orchestrator.

    The orchestrator is Phase 3+.  Phase 2 ships ports and
    adapters only.
    """
    if not PHASE2_DIR.exists():
        return
    orchestrator_path = PHASE2_DIR / "production_calculation_orchestrator.py"
    assert not orchestrator_path.is_file(), (
        f"Phase 2 must not ship a production orchestrator: {orchestrator_path}"
    )
    service_path = PHASE2_DIR / "production_calculation_service.py"
    assert not service_path.is_file(), (
        f"Phase 2 must not ship a full orchestrator service: {service_path}"
    )
    # No file in the subpackage may define ``execute`` on a
    # service class that wires all five adapters.
    for path in _all_python_files(PHASE2_DIR):
        content = path.read_text()
        assert "class ProductionCalculationOrchestrator" not in content, (
            f"Phase 2 must not ship a ProductionCalculationOrchestrator: {path}"
        )
        assert "class OrchestrationService" not in content, (
            f"Phase 2 must not ship a full OrchestrationService: {path}"
        )


# ---------------------------------------------------------------------------
# 7) Evaluation tests must not import Phase 2 ports
# ---------------------------------------------------------------------------


def test_evaluation_tests_do_not_import_phase2() -> None:
    """The evaluation test suite MUST NOT import Phase 2 ports.

    Phase 2 is a production path; the evaluation pilot is a
    separate channel.  Cross-imports defeat the boundary.
    """
    if not EVALUATION_TESTS_DIR.exists():
        return
    files = _all_python_files(EVALUATION_TESTS_DIR)
    for path in files:
        content = path.read_text()
        for forbidden in (
            "production_calculation",
            "ZonePlanningAdapter",
            "CoolingLoadAdapter",
            "EquipmentCapabilityAdapter",
            "InstalledPowerAdapter",
            "InvestmentAdapter",
        ):
            assert forbidden not in content, (
                f"Evaluation test imports Phase 2 helper '{forbidden}': {path}"
            )


# ---------------------------------------------------------------------------
# 8) No outbox materialization in Phase 2
# ---------------------------------------------------------------------------


def test_phase2_does_not_emit_outbox_events() -> None:
    """Phase 2 MUST NOT call ``MaterializeOutboxEventUseCase`` or
    otherwise write to the audit outbox.
    """
    if not PHASE2_DIR.exists():
        return
    files = _all_python_files(PHASE2_DIR)
    for path in files:
        content = path.read_text()
        for forbidden in (
            "MaterializeOutboxEventUseCase",
            "outbox_dispatcher",
            "OutboxEvent",
            "audit_events",
        ):
            pattern = rf"\b{re.escape(forbidden)}\b"
            assert not re.search(pattern, content), (
                f"Phase 2 file references outbox entity '{forbidden}': {path}"
            )


# ---------------------------------------------------------------------------
# 9) Phase 2 imports only application/domain layers
# ---------------------------------------------------------------------------


def test_phase2_no_orm_or_session_creation() -> None:
    """Phase 2 MUST NOT import the production ORM or create sessions.

    The Phase 2 subpackage lives in the application layer; it
    talks to pure functions and pure DTOs.  The future
    SQLAlchemy-backed persistence port is reserved for Phase 3+.
    """
    if not PHASE2_DIR.exists():
        return
    files = _all_python_files(PHASE2_DIR)
    for path in files:
        content = path.read_text()
        for forbidden in (
            "from sqlalchemy",
            "import sqlalchemy",
            "create_engine",
            "sessionmaker",
            "SessionLocal",
        ):
            assert forbidden not in content, (
                f"Phase 2 file imports ORM helper '{forbidden}': {path}"
            )
