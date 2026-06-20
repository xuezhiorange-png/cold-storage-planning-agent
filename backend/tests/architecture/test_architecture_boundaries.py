"""Architecture boundary tests — enforce module dependencies and layering rules."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

BACKEND_SRC = Path(__file__).resolve().parents[2] / "src" / "cold_storage"


def read_python_files(path: Path) -> list[Path]:
    return [item for item in path.rglob("*.py") if "__pycache__" not in item.parts]


# ---------------------------------------------------------------------------
# Original tests
# ---------------------------------------------------------------------------


def test_domain_has_no_framework_dependencies() -> None:
    forbidden = ("fastapi", "sqlalchemy", "redis", "openai")
    domain_files = [path for path in read_python_files(BACKEND_SRC) if "domain" in path.parts]

    assert domain_files
    for path in domain_files:
        content = path.read_text()
        has_forbidden_import = any(
            f"import {name}" in content or f"from {name}" in content for name in forbidden
        )
        assert not has_forbidden_import, path


def test_calculations_are_pure() -> None:
    forbidden = ("sqlalchemy", "redis", "requests", "httpx", "os.environ", "openai")
    calc_files = read_python_files(BACKEND_SRC / "modules" / "calculations")

    assert calc_files
    for path in calc_files:
        content = path.read_text()
        assert not any(term in content for term in forbidden), path


def test_agent_has_no_database_dependency() -> None:
    agent_files = read_python_files(BACKEND_SRC / "modules" / "planning_agent")
    assert agent_files
    for path in agent_files:
        content = path.read_text()
        assert "sqlalchemy" not in content
        assert "Session" not in content


def test_no_global_dumping_ground_modules() -> None:
    forbidden_names = {
        "utils.py",
        "helpers.py",
        "misc.py",
        "managers.py",
        "common_service.py",
        "base_manager.py",
        "service_v2.py",
        "temp.py",
    }

    found = {path.name for path in read_python_files(BACKEND_SRC)}
    assert forbidden_names.isdisjoint(found)


# ---------------------------------------------------------------------------
# New boundary tests
# ---------------------------------------------------------------------------

# Patterns that should NOT appear in the bootstrap/app.py file
ENGINEERING_FORMULA_PATTERNS = [
    re.compile(r"\b\d+\.?\d*\s*kW\b", re.IGNORECASE),
    re.compile(r"\b\d+\.?\d*\s*CNY\b"),
    re.compile(r"\b\d+\s*\*\s*\d+"),  # multiplication like 123 * 456
    re.compile(r"cooling_load"),
    re.compile(r"equipment_requirement"),
]


def test_app_py_has_no_engineering_formulas() -> None:
    """bootstrap/app.py should not contain engineering formulas."""
    app_file = BACKEND_SRC / "bootstrap" / "app.py"
    assert app_file.exists(), f"{app_file} not found"
    content = app_file.read_text()

    for pattern in ENGINEERING_FORMULA_PATTERNS:
        match = pattern.search(content)
        assert not match, (
            f"bootstrap/app.py contains engineering pattern {pattern.pattern!r} "
            f"at position {match.start()}"
        )


def test_api_routes_do_not_import_calculation_details() -> None:
    """API routes should not directly import low-level calculation domain types."""
    app_file = BACKEND_SRC / "bootstrap" / "app.py"
    assert app_file.exists()
    content = app_file.read_text()

    # Direct imports from calculations domain should be minimal
    # (only the orchestration helpers and high-level types are allowed)
    forbidden_domain_imports = [
        "from cold_storage.modules.calculations.domain.coefficients",
        "from cold_storage.modules.calculations.domain.cooling_load",
        "from cold_storage.modules.calculations.domain.equipment",
    ]
    for imp in forbidden_domain_imports:
        assert imp not in content, f"app.py imports forbidden domain detail: {imp}"


def test_no_import_time_database_connections() -> None:
    """No module should call create_engine at import time (outside factory functions)."""
    all_py_files = read_python_files(BACKEND_SRC)

    for path in all_py_files:
        content = path.read_text()
        lines = content.split("\n")

        for _i, line in enumerate(lines):
            stripped = line.strip()
            # Skip lines inside function/method bodies (indented)
            # and skip imports, comments, and strings
            if stripped.startswith("def ") or stripped.startswith("class "):
                continue
            if stripped.startswith("#") or stripped.startswith('"') or stripped.startswith("'"):
                continue

            # A top-level (non-indented) create_engine call is suspicious
            if (
                "create_engine(" in stripped
                and not stripped.startswith("def ")
                and not line.startswith("    ")
                and not line.startswith("\t")
            ):
                # Allow it inside factory functions (indented)
                # Only flag truly top-level calls
                pass  # Most create_engine calls are inside functions; check if truly top-level

    # Alternative approach: scan for create_engine calls that are NOT indented
    # (i.e., at module level)
    for path in all_py_files:
        content = path.read_text()
        lines = content.split("\n")
        for _i, line in enumerate(lines):
            if "create_engine(" in line and not line.startswith(" ") and not line.startswith("\t"):
                # This is a top-level create_engine — flag it
                pytest.fail(
                    f"Top-level create_engine call found in {path}:{_i + 1}: {line.strip()}"
                )
