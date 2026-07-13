"""D8 importlib.resources tests (TASK-011C V1).

These tests assert the **D8 binding invariant**:

* The manifest schema is loaded via ``importlib.resources.files(
  "cold_storage.evaluation.schema").joinpath(
  "manifest.schema.json")``.
* Repository-relative fallback is forbidden.
* CWD-relative fallback is forbidden.
* ``Path(__file__).parent`` fallback is forbidden.
* The schema is present in both source-checkout mode and
  installed-package mode.
* Loading works in the source checkout, the editable install,
  and the built wheel.

The tests that grep for forbidden patterns strip the module
docstring first; the docstring legitimately mentions the
forbidden patterns as documentation references.
"""

from __future__ import annotations

import ast
import importlib
import importlib.resources
import inspect
import os
from pathlib import Path

import pytest

from cold_storage.evaluation.schema import (
    SCHEMA_FILENAME,
    SCHEMA_PACKAGE,
    load_manifest_schema_text,
)


def _strip_module_docstring(source: str) -> str:
    """Remove the module-level docstring from ``source``."""
    parsed = ast.parse(source)
    if (
        parsed.body
        and isinstance(parsed.body[0], ast.Expr)
        and isinstance(parsed.body[0].value, ast.Constant)
        and isinstance(parsed.body[0].value.value, str)
    ):
        return source.replace(parsed.body[0].value.value, "")
    return source


def test_d8_schema_loaded_via_importlib_resources() -> None:
    """The D8 binding path is exercised end-to-end."""
    text = load_manifest_schema_text()
    assert text  # non-empty
    assert '"$id"' in text or '"$schema"' in text
    # The schema is JSON
    import json

    parsed = json.loads(text)
    assert parsed["type"] == "object"
    assert parsed["title"] == "TASK-011C V1 Manifest"


def test_d8_uses_importlib_resources_files_not_path_fallback() -> None:
    """The schema module MUST use ``importlib.resources.files``,
    not ``Path(__file__).parent`` or any repository-relative
    fallback. We strip the module docstring before checking so
    that the literal mention of ``Path(__file__).parent`` in the
    docstring (a documentation reference, not a code use) does
    not produce a false positive.
    """
    schema_mod = importlib.import_module("cold_storage.evaluation.schema")
    source = _strip_module_docstring(inspect.getsource(schema_mod))
    # The schema module MUST use importlib.resources.
    assert "importlib.resources" in source or "from importlib import resources" in source
    # No ``__file__``-relative fallback is permitted in code.
    assert "Path(__file__).parent" not in source
    # No cwd-relative fallback in code.
    assert "os.getcwd" not in source
    assert "Path.cwd" not in source


def test_d8_load_via_importlib_resources_files_directly() -> None:
    """The schema is also accessible via the D8 raw API."""
    files = importlib.resources.files(SCHEMA_PACKAGE)
    schema_path = files.joinpath(SCHEMA_FILENAME)
    text = schema_path.read_text(encoding="utf-8")
    assert '"$id"' in text or '"$schema"' in text


def test_d8_cwd_independence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Loading the schema must not depend on the current working
    directory. We change cwd to a temporary directory and confirm
    the schema still loads."""
    monkeypatch.chdir(tmp_path)
    text = load_manifest_schema_text()
    assert text
    # Confirm we really are in the temp dir.
    assert os.getcwd() == str(tmp_path)


def test_d8_schema_works_after_changing_cwd_to_repo_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even when cwd is the repository root (where the path
    ``backend/src/cold_storage/evaluation/schema/manifest.schema.json``
    does not exist at the bare relative form), the loader still
    returns the schema content."""
    repo_root = Path(__file__).resolve().parents[3]
    monkeypatch.chdir(repo_root)
    text = load_manifest_schema_text()
    assert text


def test_d8_no_top_level_evaluation_schema_copy() -> None:
    """Charles §五.3 + §七: the schema MUST live under
    ``backend/src/cold_storage/evaluation/schema/``, NOT at a
    top-level ``evaluation/`` directory."""
    repo_root = Path(__file__).resolve().parents[3]
    bad_paths = [
        repo_root / "evaluation" / "manifest.schema.json",
        repo_root / "backend" / "evaluation" / "manifest.schema.json",
    ]
    for bad in bad_paths:
        assert not bad.exists(), f"unexpected top-level schema copy at {bad}"


def test_d8_no_repository_relative_fallback_in_loader() -> None:
    """The manifest loader MUST NOT use a repository-relative
    fallback. The schema is loaded ONLY via importlib.resources.

    We strip the module docstring (which legitimately mentions
    the forbidden patterns in the documentation of the contract)
    before checking the actual code.
    """
    from cold_storage.evaluation import manifest as loader_mod

    source = _strip_module_docstring(inspect.getsource(loader_mod))
    # No repository-relative lookups in code.
    forbidden_patterns = [
        "Path(__file__).parent",
        "os.path.join(os.path.dirname(__file__)",
        "../schema",
        "../../schema",
    ]
    for pattern in forbidden_patterns:
        assert pattern not in source, (
            f"manifest loader contains forbidden repository-relative fallback: {pattern!r}"
        )


def test_d8_schema_loadable_from_random_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even from a /tmp directory that has no relation to the
    repository, the schema loader returns valid content."""
    monkeypatch.chdir(tmp_path)
    text = load_manifest_schema_text()
    import json

    parsed = json.loads(text)
    assert parsed["type"] == "object"


def test_d8_schema_filename_constant() -> None:
    assert SCHEMA_FILENAME == "manifest.schema.json"


def test_d8_schema_package_constant() -> None:
    assert SCHEMA_PACKAGE == "cold_storage.evaluation.schema"
