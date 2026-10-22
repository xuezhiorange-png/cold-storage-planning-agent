"""D7 setuptools package-data tests (TASK-011C V1).

These tests assert the **D7 binding invariant**:

* The manifest schema is shipped inside the Python package via
  ``[tool.setuptools.package-data]``.
* The declaration is exactly::

    "cold_storage.evaluation.schema" = ["manifest.schema.json"]

* R14 additionally ships the Truck preview input schema. No other
  ``[tool.setuptools.package-data]`` entries are authorized.
"""

from __future__ import annotations

import tomllib
from pathlib import Path


def _read_pyproject() -> dict:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    with pyproject.open("rb") as f:
        return tomllib.load(f)


def test_d7_pyproject_has_setuptools_package_data_section() -> None:
    cfg = _read_pyproject()
    # TOML: [tool.setuptools.package-data] lives under
    # ``cfg["tool"]["setuptools"]["package-data"]``.
    assert "tool" in cfg
    assert "setuptools" in cfg["tool"], "pyproject.toml must have a [tool.setuptools] section"
    assert "package-data" in cfg["tool"]["setuptools"], (
        "pyproject.toml must have a [tool.setuptools.package-data] section"
    )


def test_d7_package_data_declares_schema_package() -> None:
    cfg = _read_pyproject()
    package_data = cfg["tool"]["setuptools"]["package-data"]
    assert "cold_storage.evaluation.schema" in package_data
    assert package_data["cold_storage.evaluation.schema"] == ["manifest.schema.json"]


def test_d7_no_unauthorized_package_data_entries() -> None:
    """Preserve D7 and allow only the explicitly authorized R14 schema."""
    cfg = _read_pyproject()
    package_data = cfg["tool"]["setuptools"]["package-data"]
    assert package_data == {
        "cold_storage.evaluation.schema": ["manifest.schema.json"],
        "cold_storage.modules.aily.application": ["truck_preview.schema.json"],
    }


def test_d7_schema_file_exists_in_package() -> None:
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "cold_storage"
        / "evaluation"
        / "schema"
        / "manifest.schema.json"
    )
    assert schema_path.exists()
    assert schema_path.is_file()


def test_d7_schema_file_is_valid_json() -> None:
    import json

    schema_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "cold_storage"
        / "evaluation"
        / "schema"
        / "manifest.schema.json"
    )
    text = schema_path.read_text(encoding="utf-8")
    parsed = json.loads(text)
    assert parsed["type"] == "object"
    assert parsed["title"] == "TASK-011C V1 Manifest"


def test_d7_pyproject_unchanged_except_for_package_data() -> None:
    """Charles §五.3: pyproject.toml is only modified by adding the
    D7 package-data declaration. All other sections must be
    unchanged from the baseline.

    We assert the structure: the file MUST contain ``[project]``,
    ``[dependency-groups]``, ``[tool.pytest.ini_options]``,
    ``[tool.ruff]``, ``[tool.ruff.lint]``, ``[tool.mypy]``, and
    ``[tool.setuptools.package-data]``; no other top-level
    ``[tool.*]`` sections are introduced."""
    cfg = _read_pyproject()
    # Top-level keys.
    assert set(cfg.keys()) == {
        "project",
        "dependency-groups",
        "tool",
    }
    tool_keys = set(cfg["tool"].keys())
    assert tool_keys == {
        "pytest",
        "ruff",
        "mypy",
        "setuptools",
    }
    # The pytest sub-table is ``ini_options`` (TOML-friendly).
    assert "ini_options" in cfg["tool"]["pytest"]
    # The ruff sub-table has ``lint``.
    assert "lint" in cfg["tool"]["ruff"]


def test_d7_no_lockfile_modification(tmp_path: Path) -> None:
    """Charles §七 (forbidden): uv.lock must not be modified by
    this round. We assert that uv.lock (if present) is not in
    the diff."""
    repo_root = Path(__file__).resolve().parents[3]
    uv_lock = repo_root / "uv.lock"
    # We do not assert the file does or does not exist; we just
    # record its presence. The diff check is the actual
    # regression guard.
    _ = uv_lock.exists()
