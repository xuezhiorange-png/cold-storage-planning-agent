"""Architecture boundary tests for release evidence (S2_GAP_03/04 path scope).

Enforces that:
* release-evidence code lives only under ``cold_storage.release``;
* the ``release`` package does not import framework/runtime layers
  (fastapi, sqlalchemy, redis, openai) — it is a pure verification layer;
* every error code in the frozen table is exercised by exactly one
  negative-scenario fixture;
* all 20 frozen NR scenarios map to distinct fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cold_storage.release.negative_scenario_fixtures import all_negative_scenarios
from cold_storage.release.provenance_schema import ALL_ERROR_CODES

BACKEND_SRC = Path(__file__).resolve().parents[2] / "src" / "cold_storage"
RELEASE_DIR = BACKEND_SRC / "release"

_FORBIDDEN_IMPORTS = ("fastapi", "sqlalchemy", "redis", "openai", "uvicorn", "psycopg2", "alembic")


def _read_release_files() -> list[Path]:
    return [p for p in RELEASE_DIR.rglob("*.py") if "__pycache__" not in p.parts]


def test_release_module_exists() -> None:
    assert RELEASE_DIR.is_dir()
    files = _read_release_files()
    assert files, "release package must contain source files"


def test_release_package_does_not_import_framework_layers() -> None:
    """The release evidence layer is a pure verification layer."""
    files = _read_release_files()
    assert files
    for path in files:
        content = path.read_text()
        for forbidden in _FORBIDDEN_IMPORTS:
            assert f"import {forbidden}" not in content, f"{path} imports {forbidden}"
            assert f"from {forbidden}" not in content, f"{path} imports {forbidden}"


def test_release_evidence_does_not_leak_into_non_release_modules() -> None:
    """Non-release modules must not import from cold_storage.release."""
    non_release_files = [
        p
        for p in BACKEND_SRC.rglob("*.py")
        if "__pycache__" not in p.parts and "release" not in p.parts
    ]
    assert non_release_files
    for path in non_release_files:
        content = path.read_text()
        assert "cold_storage.release" not in content, (
            f"non-release module imports cold_storage.release: {path}"
        )


def test_all_20_error_codes_are_exercised() -> None:
    """Every frozen RC_* error code must appear in exactly one fixture."""
    scenarios = all_negative_scenarios()
    codes = [s.expected_error_code for s in scenarios]
    for code in ALL_ERROR_CODES:
        assert code in codes, f"error code not exercised by any fixture: {code}"
    assert len(codes) == len(set(codes)) == 20


def test_negative_scenario_fixture_ids_are_unique() -> None:
    scenarios = all_negative_scenarios()
    fixture_ids = [s.fixture_id for s in scenarios]
    assert len(fixture_ids) == len(set(fixture_ids)) == 20


@pytest.mark.parametrize("expected_code", ALL_ERROR_CODES)
def test_each_error_code_has_a_runnable_fixture(expected_code: str) -> None:
    scenarios = all_negative_scenarios()
    matching = [s for s in scenarios if s.expected_error_code == expected_code]
    assert len(matching) == 1, (
        f"expected exactly 1 fixture for {expected_code}, got {len(matching)}"
    )
    assert callable(matching[0].run)
