"""Architecture boundary tests for the schemes module — enforce layering
rules: domain purity, API thinness, no leaked infrastructure concerns."""

from __future__ import annotations

import re
from pathlib import Path

BACKEND_SRC = Path(__file__).resolve().parents[2] / "src" / "cold_storage"
SCHEMES_DIR = BACKEND_SRC / "modules" / "schemes"


def _read_python_files(path: Path) -> list[Path]:
    """Collect all .py files under a directory, excluding __pycache__."""
    return [item for item in path.rglob("*.py") if "__pycache__" not in item.parts]


# ---------------------------------------------------------------------------
# 1) Scheme domain has no FastAPI / SQLAlchemy imports
# ---------------------------------------------------------------------------


def test_scheme_domain_has_no_fastapi_sqlalchemy_imports() -> None:
    """1) Files under schemes/domain/ must not import FastAPI or SQLAlchemy."""
    domain_files = _read_python_files(SCHEMES_DIR / "domain")
    assert domain_files, f"No domain files found in {SCHEMES_DIR / 'domain'}"

    forbidden = ("fastapi", "sqlalchemy")
    for path in domain_files:
        content = path.read_text()
        for dep in forbidden:
            assert f"import {dep}" not in content and f"from {dep}" not in content, (
                f"Scheme domain file imports forbidden module '{dep}': {path.name}"
            )


# ---------------------------------------------------------------------------
# 2) Scheme domain doesn't access the database
# ---------------------------------------------------------------------------


def test_scheme_domain_has_no_database_access() -> None:
    """2) Scheme domain files must not reference database objects or sessions."""
    domain_files = _read_python_files(SCHEMES_DIR / "domain")
    assert domain_files

    db_patterns = (
        "Session",
        "session",
        "engine",
        "create_engine",
        "sessionmaker",
        "MetaData",
        "Base.metadata",
        "commit()",
        "rollback()",
        "execute(",
        "session.get(",
        "session.query(",
    )
    for path in domain_files:
        content = path.read_text()
        for pattern in db_patterns:
            # Skip string literals and comments
            lines = content.split("\n")
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith('"') or stripped.startswith("'"):
                    continue
                # We check the raw line — false positives in strings are acceptable
                # for a boundary test; it should still catch real violations.
                assert pattern not in stripped, (
                    f"Scheme domain file references database pattern '{pattern}': "
                    f"{path.name} — line: {stripped[:80]}"
                )


# ---------------------------------------------------------------------------
# 3) Scheme API doesn't contain scoring formulas
# ---------------------------------------------------------------------------


def test_scheme_api_has_no_scoring_formulas() -> None:
    """3) API routes must not contain scoring/normalization formula logic."""
    api_files = _read_python_files(SCHEMES_DIR / "api")
    assert api_files, f"No API files found in {SCHEMES_DIR / 'api'}"

    # Patterns that indicate inline scoring formulas
    formula_patterns = [
        re.compile(r"normalize\s*\("),
        re.compile(r"weighted.*contribution", re.IGNORECASE),
        re.compile(r"100\s*\*\s*\(.*-\s*min\)\s*/\s*\(.*max\s*-\s*min\)"),
        re.compile(r"ROUND_HALF_UP"),
        re.compile(r"quantize\s*\("),
        re.compile(r"score_candidates\s*\("),
        re.compile(r"validate_weight_set\s*\("),
    ]
    for path in api_files:
        content = path.read_text()
        for pattern in formula_patterns:
            match = pattern.search(content)
            assert not match, (
                f"Scheme API file contains scoring formula pattern '{pattern.pattern}': {path.name}"
            )


# ---------------------------------------------------------------------------
# 4) Scheme API doesn't import calculation details
# ---------------------------------------------------------------------------


def test_scheme_api_does_not_import_calculation_details() -> None:
    """4) API routes must not import scoring/validation internals from domain."""
    api_files = _read_python_files(SCHEMES_DIR / "api")
    assert api_files

    forbidden_imports = [
        "from cold_storage.modules.schemes.domain.scoring",
        "from cold_storage.modules.schemes.domain.validation",
        "import cold_storage.modules.schemes.domain.scoring",
        "import cold_storage.modules.schemes.domain.validation",
    ]
    for path in api_files:
        content = path.read_text()
        for imp in forbidden_imports:
            assert imp not in content, (
                f"Scheme API imports calculation detail: '{imp}' in {path.name}"
            )


# ---------------------------------------------------------------------------
# Bonus: Infrastructure boundary tests
# ---------------------------------------------------------------------------


def test_scheme_api_has_no_sqlalchemy_imports() -> None:
    """API routes must not import SQLAlchemy directly."""
    api_files = _read_python_files(SCHEMES_DIR / "api")
    assert api_files
    for path in api_files:
        content = path.read_text()
        assert "from sqlalchemy" not in content, f"Scheme API imports SQLAlchemy: {path.name}"
        assert "import sqlalchemy" not in content, f"Scheme API imports SQLAlchemy: {path.name}"


def test_scheme_api_has_no_database_session() -> None:
    """API routes must not reference database sessions directly."""
    api_files = _read_python_files(SCHEMES_DIR / "api")
    assert api_files
    for path in api_files:
        content = path.read_text()
        assert "Session(" not in content, f"Scheme API creates Session: {path.name}"
        assert "sessionmaker" not in content, f"Scheme API uses sessionmaker: {path.name}"
