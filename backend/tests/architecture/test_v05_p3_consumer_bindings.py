"""Architecture tests for V0.5 P3 consumer canonical binding alignment."""

from __future__ import annotations

from pathlib import Path

from cold_storage.modules.orchestration.domain.consumer_bindings import (
    CANONICAL_CALCULATOR_NAMES,
    CANONICAL_STAGE_ORDER,
)
from cold_storage.modules.orchestration.domain.dag import CALCULATOR_BINDINGS
from cold_storage.modules.schemes.domain import validation as schemes_validation
from cold_storage.modules.workflow.domain.steps import REQUIRED_SCHEME_CALCULATOR_NAMES

BACKEND_SRC = Path(__file__).resolve().parents[2] / "src" / "cold_storage"


def _read_python_files(path: Path) -> list[Path]:
    return [item for item in path.rglob("*.py") if "__pycache__" not in item.parts]


def test_canonical_consumer_calculator_names_match_dag_bindings() -> None:
    assert CANONICAL_CALCULATOR_NAMES == frozenset(CALCULATOR_BINDINGS.values())
    assert REQUIRED_SCHEME_CALCULATOR_NAMES == CANONICAL_CALCULATOR_NAMES


def test_workflow_schemes_required_identity_sets_equal_canonical_five() -> None:
    assert REQUIRED_SCHEME_CALCULATOR_NAMES == CANONICAL_CALCULATOR_NAMES
    assert schemes_validation._REQUIRED_CALCULATION_TYPES == frozenset(CANONICAL_STAGE_ORDER)


def test_report_and_scheme_assembly_do_not_import_calculator_functions() -> None:
    forbidden_pattern = "cold_storage.modules.calculations"
    checked_roots = (
        BACKEND_SRC / "modules" / "reports" / "application",
        BACKEND_SRC / "modules" / "reports" / "infrastructure" / "real_data_provider.py",
        BACKEND_SRC / "modules" / "schemes" / "application",
    )
    violations: list[str] = []
    for root in checked_roots:
        paths = [root] if root.is_file() else _read_python_files(root)
        for path in paths:
            content = path.read_text(encoding="utf-8")
            if forbidden_pattern in content:
                violations.append(str(path.relative_to(BACKEND_SRC.parent)))
    assert not violations, "Calculator domain imports found:\n" + "\n".join(violations)
