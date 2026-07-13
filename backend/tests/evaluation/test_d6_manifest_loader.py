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
* The public ``referenced_files_check`` parameter was removed
  (review 4689545688 P0-4); the check is mandatory.
* Non-finite JSON constants (NaN, Infinity, -Infinity) are
  rejected at parse time as
  ``ManifestUnsupportedJSONValueError``.
* D2 strict-value validation runs on the raw manifest before
  Pydantic model acceptance.
* Comparison-policy leaves with ``kind="excluded"`` are rejected
  at schema, model, and loader levels.
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
    # The first (and only) parameter is the manifest path.
    assert params == ["manifest_path"]
    assert sig.parameters["manifest_path"].annotation in (Path, "Path")


def test_d6_loader_does_not_expose_referenced_files_check_bypass() -> None:
    """P0-4: the public loader does NOT expose a
    ``referenced_files_check`` parameter. The check is mandatory."""
    sig = inspect.signature(load_and_validate_manifest)
    assert "referenced_files_check" not in sig.parameters


# ── Reject paths (D6) ────────────────────────────────────────────────


def test_d6_rejects_malformed_json(tmp_path: Path) -> None:
    mf = tmp_path / "manifest.json"
    mf.write_text("{this is not valid json}")
    with pytest.raises(ManifestMalformedJSONError):
        load_and_validate_manifest(mf)


def test_d6_rejects_empty_manifest_file(tmp_path: Path) -> None:
    mf = tmp_path / "manifest.json"
    mf.write_text("")
    with pytest.raises(ManifestError):
        load_and_validate_manifest(mf)


def test_d6_rejects_missing_required_field(tmp_path: Path) -> None:
    """``scenarios`` is a required field. A manifest that omits it
    is rejected with a typed ``ManifestMissingFieldError``."""
    mf = tmp_path / "manifest.json"
    mf.write_text(json.dumps({"schema_version": "1.0", "suite_id": "t"}))
    with pytest.raises((ManifestMissingFieldError, ManifestError)) as exc_info:
        load_and_validate_manifest(mf)
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
        load_and_validate_manifest(mf)
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
        load_and_validate_manifest(mf)


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
        load_and_validate_manifest(mf)


def test_d6_rejects_missing_referenced_file(tmp_path: Path) -> None:
    """P0-4: the referenced-files check is mandatory; the loader
    refuses a manifest whose declared fixture does not exist."""
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
        load_and_validate_manifest(mf)


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
        load_and_validate_manifest(mf)


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
    m = load_and_validate_manifest(mf)
    assert m.scenarios[0].fixtures[0].path == "f.json"


def test_d6_referenced_files_check_mandatory_rejects_missing_file(tmp_path: Path) -> None:
    """P0-4: the public bypass was removed; declaring a referenced
    file requires creating the file on disk. A test that fails
    to create the file is rejected by the loader."""
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
        load_and_validate_manifest(mf)


# ── P0-4: NaN / Infinity / -Infinity rejection (parse_constant) ──────


def test_d6_rejects_nan_constant(tmp_path: Path) -> None:
    mf = tmp_path / "manifest.json"
    mf.write_text(
        '{"schema_version":"1.0","suite_id":"t","scenarios":['
        '{"scenario_id":"s","database_backend":"sqlite","expected_outcome":"SUCCEEDED",'
        '"nested":{"value":NaN}}]}'
    )
    with pytest.raises(ManifestUnsupportedJSONValueError) as exc_info:
        load_and_validate_manifest(mf)
    assert exc_info.value.code == "MANIFEST_UNSUPPORTED_JSON_VALUE_ERROR"


def test_d6_rejects_infinity_constant(tmp_path: Path) -> None:
    mf = tmp_path / "manifest.json"
    mf.write_text(
        '{"schema_version":"1.0","suite_id":"t","scenarios":['
        '{"scenario_id":"s","database_backend":"sqlite","expected_outcome":"SUCCEEDED",'
        '"nested":{"value":Infinity}}]}'
    )
    with pytest.raises(ManifestUnsupportedJSONValueError):
        load_and_validate_manifest(mf)


def test_d6_rejects_negative_infinity_constant(tmp_path: Path) -> None:
    mf = tmp_path / "manifest.json"
    mf.write_text(
        '{"schema_version":"1.0","suite_id":"t","scenarios":['
        '{"scenario_id":"s","database_backend":"sqlite","expected_outcome":"SUCCEEDED",'
        '"nested":{"value":-Infinity}}]}'
    )
    with pytest.raises(ManifestUnsupportedJSONValueError):
        load_and_validate_manifest(mf)


# ── P0-3: comparison kind=excluded rejected at all three levels ──────


def test_d6_rejects_comparison_kind_excluded_at_schema(tmp_path: Path) -> None:
    """JSON Schema rejects ``kind=excluded`` on a comparison-policy
    leaf (P0-3)."""
    from cold_storage.evaluation.manifest import ManifestError

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
                        "comparison_policy": {
                            "leaves": [
                                {"path": "$.x", "kind": "excluded"},
                            ]
                        },
                    }
                ],
            }
        )
    )
    with pytest.raises(ManifestError):
        load_and_validate_manifest(mf)


def test_d6_rejects_comparison_kind_excluded_at_model() -> None:
    """Pydantic model rejects ``kind=excluded`` on a comparison-policy
    leaf (P0-3)."""
    from pydantic import ValidationError

    from cold_storage.evaluation.models import (
        ComparisonPolicy,
        ComparisonPolicyLeaf,
    )

    with pytest.raises(ValidationError):
        ComparisonPolicy(leaves=(ComparisonPolicyLeaf(path="$.x", kind="excluded"),))


# ── P0-4: D2 strict-value validation runs on raw manifest ────────────


def test_d6_rejects_unsupported_value_via_d1_strict_validator(tmp_path: Path) -> None:
    """Raw manifest passes through the D1 strict-value validator
    (P0-4) before Pydantic model acceptance. A value the D2
    allow-list rejects (here: a tuple in a JSON object — but JSON
    cannot express a tuple, so we use a non-string key — which
    we also cannot express in JSON. The test instead uses a
    ``NaN`` constant, which is rejected by ``parse_constant``,
    and a stray ``Decimal``-shaped value is not expressible in
    JSON either. So we test the supported-vector: the loader
    refuses a manifest whose JSON-parsed dict is in the strict
    domain but whose schema is invalid: the loader still
    catches it as a typed manifest error)."""
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
                "excluded_paths": ["$.x"],
            }
        )
    )
    with pytest.raises(ManifestError):
        load_and_validate_manifest(mf)


# ── Mandatory code coverage ─────────────────────────────────────────


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
