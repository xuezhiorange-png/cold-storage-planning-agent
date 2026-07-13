"""Package marker for the TASK-011C V1 manifest schema (D7, D8).

The schema file ``manifest.schema.json`` is owned by this package
and is the single, package-distributed source of the JSON Schema
definition. Runtime loading uses
``importlib.resources.files("cold_storage.evaluation.schema")``
— there is no fallback to a repository-relative path, no
fallback to ``Path(__file__).parent``, and no fallback to a
top-level ``evaluation/`` directory.
"""

from __future__ import annotations

from importlib import resources
from typing import Final

#: The package-owned schema filename. Single source of truth.
SCHEMA_FILENAME: Final[str] = "manifest.schema.json"

#: The package that owns the schema. Single source of truth.
SCHEMA_PACKAGE: Final[str] = "cold_storage.evaluation.schema"


def load_manifest_schema_text() -> str:
    """Load the manifest schema as UTF-8 text via importlib.resources.

    Returns
    -------
    str
        The UTF-8-decoded content of
        ``cold_storage/evaluation/schema/manifest.schema.json``.

    Raises
    ------
    FileNotFoundError
        If the schema is missing from the installed package
        (caller MUST treat this as a hard failure; no fallback).
    """
    files = resources.files(SCHEMA_PACKAGE)
    schema_file = files.joinpath(SCHEMA_FILENAME)
    # ``importlib.resources.files(...).joinpath(...).read_text(...)``
    # works in both source-checkout and installed-package mode on
    # Python 3.9+; the project requires 3.12, so the call is safe.
    return schema_file.read_text(encoding="utf-8")


__all__ = [
    "SCHEMA_FILENAME",
    "SCHEMA_PACKAGE",
    "load_manifest_schema_text",
]
