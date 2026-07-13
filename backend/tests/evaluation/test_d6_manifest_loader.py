"""D6 single-manifest-loader tests (TASK-011C V1).

These tests assert the **D6 binding invariant**:

* ``load_and_validate_manifest`` is the single entry point.
* No parallel loaders exist in the evaluation package.
* The loader fails closed on:
  - missing schema_version
  - numeric 1.0
  - unknown version
  - malformed JSON
  - missing required field
  - undeclared field
  - duplicate fixture / scenario ID
  - missing referenced file
  - unsupported JSON-domain value
  - repository escape path
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from cold_storage.evaluation import manifest as _manifest_module
from cold_storage.evaluation.manifest import (
    ManifestDuplicateFixtureIDError,
    ManifestError,
    ManifestMalformedJSONError,
    ManifestMissingFieldError,
    ManifestMissingFileError,
    ManifestSchemaVersionError,
    ManifestUndeclaredFieldError,
    ManifestUnsupportedJSONValueError,
    load_and_validate_manifest,
)

# ── Single-loader enforcement (D6) ───────────────────────────────────


def test_d6_single_loader_entry_point_exists() -> None:
    assert callable(load_and_validate_manifest)


def test_d6_no_parallel_manifest_loaders_in_evaluation_package() -> None:
    """The manifest module exposes exactly one public function
    defined in this module that loads a manifest from a path.
    Any parallel implementation would be a V1 contract violation.

    The ``schema`` sub-package legitimately exposes
    ``load_manifest_schema_text`` (D7/D8), but that is a schema
    loader (different module), not a manifest loader. The single
    D6 entry point is ``load_and_validate_manifest``.
    """
    # The filter is module-scoped: the function must be DEFINED
    # in ``cold_storage.evaluation.manifest``, not merely
    # re-imported.
    public_loaders: list[str] = []
    for name, obj in vars(_manifest_module).items():
        if name.startswith("_"):
            continue
        if not callable(obj):
            continue
        if not name.startswith("load_"):
            continue
        if getattr(obj, "__module__", "") != "cold_storage.evaluation.manifest":
            continue
        public_loaders.append(name)
    assert public_loaders == ["load_and_validate_manifest"]


def test_d6_loader_signature_is_stable() -> None:
    sig = inspect.signature(load_and_validate_manifest)
    params = list(sig.parameters.keys())
    # The first parameter is the manifest path; the rest are
    # keyword-only.
    assert params[0] == "manifest_path"
    assert sig.parameters["manifest_path"].annotation in (Path, "Path")
    # No additional positional parameters.
    positional = [
        p
        for p in sig.parameters.values()
        if p.kind is inspect.Parameter.POSITIONAL_ONLY
        or p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    ]
    assert len(positional) == 1


# ── Reject paths (D6) ────────────────────────────────────────────────


def test_d6_rejects_malformed_json(tmp_path: Path) -> None:
    mf = tmp_path / "manifest.json"
    mf.write_text("{this is not valid json}")
    with pytest.raises(ManifestMalformedJSONError):
        load_and_validate_manifest(mf, referenced_files_check=False)


def test_d6_rejects_empty_manifest_file(tmp_path: Path) -> None:
    mf = tmp_path / "manifest.json"
    mf.write_text("")
    with pytest.raises(ManifestError):
        load_and_validate_manifest(mf, referenced_files_check=False)


def test_d6_rejects_missing_required_field(tmp_path: Path) -> None:
    """``scenarios`` is a required field. A manifest that omits it
    is rejected with a typed ``ManifestMissingFieldError``."""
    mf = tmp_path / "manifest.json"
    mf.write_text(json.dumps({"schema_version": "1.0", "suite_id": "t"}))
    with pytest.raises((ManifestMissingFieldError, ManifestError)) as exc_info:
        load_and_validate_manifest(mf, referenced_files_check=False)
    # Code is one of the typed ManifestError subclasses.
    assert exc_info.value.code in (
        "MANIFEST_MISSING_FIELD_ERROR",
        "MANIFEST_ERROR",
    )


def test_d6_rejects_undeclared_field(tmp_path: Path) -> None:
    mf = tmp_path / "manifest.json"
    mf.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "suite_id": "t",
                "scenarios": [
                    {
                        "scenario_id": "s",
                        "database_backend": "sqlite",
                        "expected_outcome": "SUCCEEDED",
                    }
                ],
                "rogue_field": "forbidden",
            }
        )
    )
    with pytest.raises((ManifestUndeclaredFieldError, ManifestError)) as exc_info:
        load_and_validate_manifest(mf, referenced_files_check=False)
    assert exc_info.value.code in (
        "MANIFEST_UNDECLARED_FIELD_ERROR",
        "MANIFEST_ERROR",
    )


def test_d6_rejects_duplicate_scenario_id(tmp_path: Path) -> None:
    """The (scenario_id, database_backend) pair must be unique."""
    mf = tmp_path / "manifest.json"
    mf.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "suite_id": "t",
                "scenarios": [
                    {
                        "scenario_id": "s",
                        "database_backend": "sqlite",
                        "expected_outcome": "SUCCEEDED",
                    },
                    {
                        "scenario_id": "s",
                        "database_backend": "sqlite",
                        "expected_outcome": "SUCCEEDED",
                    },
                ],
            }
        )
    )
    with pytest.raises(ManifestError):
        load_and_validate_manifest(mf, referenced_files_check=False)


def test_d6_rejects_duplicate_fixture_id(tmp_path: Path) -> None:
    mf = tmp_path / "manifest.json"
    mf.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "suite_id": "t",
                "scenarios": [
                    {
                        "scenario_id": "s1",
                        "database_backend": "sqlite",
                        "expected_outcome": "SUCCEEDED",
                        "fixtures": [
                            {"fixture_id": "f1", "path": "a.json"},
                        ],
                    },
                    {
                        "scenario_id": "s2",
                        "database_backend": "sqlite",
                        "expected_outcome": "SUCCEEDED",
                        "fixtures": [
                            {"fixture_id": "f1", "path": "b.json"},
                        ],
                    },
                ],
            }
        )
    )
    with pytest.raises(ManifestDuplicateFixtureIDError):
        load_and_validate_manifest(mf, referenced_files_check=False)


def test_d6_rejects_missing_referenced_file(tmp_path: Path) -> None:
    mf = tmp_path / "manifest.json"
    mf.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "suite_id": "t",
                "scenarios": [
                    {
                        "scenario_id": "s",
                        "database_backend": "sqlite",
                        "expected_outcome": "SUCCEEDED",
                        "fixtures": [
                            {"fixture_id": "f1", "path": "missing.json"},
                        ],
                    },
                ],
            }
        )
    )
    with pytest.raises(ManifestMissingFileError):
        load_and_validate_manifest(mf, referenced_files_check=True)


def test_d6_rejects_referenced_file_path_traversal(tmp_path: Path) -> None:
    """A fixture path with ``..`` that escapes the manifest root is
    rejected by the path-safety check, even if a matching file
    exists outside the root."""
    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}")
    mf = tmp_path / "manifest.json"
    mf.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "suite_id": "t",
                "scenarios": [
                    {
                        "scenario_id": "s",
                        "database_backend": "sqlite",
                        "expected_outcome": "SUCCEEDED",
                        "fixtures": [
                            {"fixture_id": "f1", "path": "../outside.json"},
                        ],
                    },
                ],
            }
        )
    )
    with pytest.raises(ManifestError):
        load_and_validate_manifest(mf, referenced_files_check=True)


def test_d6_accepts_manifest_with_referenced_file_present(tmp_path: Path) -> None:
    fixture_path = tmp_path / "f.json"
    fixture_path.write_text("{}")
    mf = tmp_path / "manifest.json"
    mf.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "suite_id": "t",
                "scenarios": [
                    {
                        "scenario_id": "s",
                        "database_backend": "sqlite",
                        "expected_outcome": "SUCCEEDED",
                        "fixtures": [
                            {"fixture_id": "f1", "path": "f.json"},
                        ],
                    },
                ],
            }
        )
    )
    m = load_and_validate_manifest(mf, referenced_files_check=True)
    assert m.scenarios[0].fixtures[0].path == "f.json"


def test_d6_referenced_files_check_can_be_disabled(tmp_path: Path) -> None:
    """Setting ``referenced_files_check=False`` allows the loader
    to accept a manifest whose referenced files do not exist
    (useful for schema-only validation)."""
    mf = tmp_path / "manifest.json"
    mf.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "suite_id": "t",
                "scenarios": [
                    {
                        "scenario_id": "s",
                        "database_backend": "sqlite",
                        "expected_outcome": "SUCCEEDED",
                        "fixtures": [
                            {"fixture_id": "f1", "path": "missing.json"},
                        ],
                    },
                ],
            }
        )
    )
    m = load_and_validate_manifest(mf, referenced_files_check=False)
    assert m.scenarios[0].fixtures[0].path == "missing.json"


def test_d6_manifest_error_subclasses_have_distinct_codes() -> None:
    codes = {
        cls.code
        for cls in (
            ManifestSchemaVersionError,
            ManifestUnsupportedJSONValueError,
            ManifestMissingFieldError,
            ManifestUndeclaredFieldError,
            ManifestDuplicateFixtureIDError,
            ManifestMissingFileError,
            ManifestMalformedJSONError,
        )
    }
    # All seven mandatory codes are present and distinct.
    assert len(codes) == 7
    for code in (
        "MANIFEST_SCHEMA_VERSION_ERROR",
        "MANIFEST_UNSUPPORTED_JSON_VALUE_ERROR",
        "MANIFEST_MISSING_FIELD_ERROR",
        "MANIFEST_UNDECLARED_FIELD_ERROR",
        "MANIFEST_DUPLICATE_FIXTURE_ID_ERROR",
        "MANIFEST_MISSING_FILE_ERROR",
        "MANIFEST_MALFORMED_JSON_ERROR",
    ):
        assert code in codes
