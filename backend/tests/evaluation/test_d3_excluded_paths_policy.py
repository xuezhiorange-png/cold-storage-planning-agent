"""D3 excluded-paths policy tests (TASK-011C V1).

These tests assert the **D3 binding invariant**:

* The V1 exclusion set is empty (``D3_V1_EXCLUDED_JSON_PATHS=[]``).
* Wildcard exclusions are forbidden.
* Adding any exact path to the exclusion set requires a separate
  Charles authorization.
* The canonicalizer refuses any non-empty ``excluded_paths``.
* The manifest model refuses any non-empty ``excluded_paths``.

These are behavioral tests, not source-text grep.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from cold_storage.evaluation.canonicalization import (
    EmptyExclusionSetRequired,
    WildcardExclusionForbidden,
    canonicalize_production_outputs,
)
from cold_storage.evaluation.models import Manifest

# ── Canonicalizer-side enforcement (D1) ──────────────────────────────


def test_d3_empty_exclusion_set_accepted() -> None:
    out = canonicalize_production_outputs({"x": 1}, excluded_paths=())
    assert out == '{"x":1}'


def test_d3_empty_list_exclusion_accepted() -> None:
    out = canonicalize_production_outputs({"x": 1}, excluded_paths=[])
    assert out == '{"x":1}'


def test_d3_single_exact_path_rejected() -> None:
    with pytest.raises(EmptyExclusionSetRequired):
        canonicalize_production_outputs({"x": 1}, excluded_paths=["$.x"])


def test_d3_multiple_exact_paths_rejected() -> None:
    with pytest.raises(EmptyExclusionSetRequired):
        canonicalize_production_outputs({"x": 1}, excluded_paths=["$.x", "$.y"])


def test_d3_wildcard_star_rejected_with_wildcard_specific_error() -> None:
    with pytest.raises(WildcardExclusionForbidden):
        canonicalize_production_outputs({"x": 1}, excluded_paths=["*"])


def test_d3_wildcard_inside_path_rejected() -> None:
    with pytest.raises(WildcardExclusionForbidden):
        canonicalize_production_outputs({"x": 1}, excluded_paths=["$.*.x"])


# ── Manifest-model enforcement ───────────────────────────────────────


def test_d3_manifest_with_empty_excluded_paths_accepted() -> None:
    m = Manifest.model_validate(
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
            "excluded_paths": [],
        }
    )
    assert m.excluded_paths == ()


def test_d3_manifest_omitted_excluded_paths_defaults_to_empty() -> None:
    m = Manifest.model_validate(
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
        }
    )
    assert m.excluded_paths == ()


def test_d3_manifest_with_exact_path_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Manifest.model_validate(
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
                "excluded_paths": ["$.some.path"],
            }
        )
    assert "excluded_paths" in str(exc_info.value)


def test_d3_manifest_with_wildcard_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Manifest.model_validate(
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
                "excluded_paths": ["$.*.id"],
            }
        )
    assert "excluded_paths" in str(exc_info.value)


# ── Integration: manifest loader refuses non-empty exclusion ─────────


def test_d3_manifest_loader_rejects_non_empty_exclusion(tmp_path: Path) -> None:
    """End-to-end: write a manifest with excluded_paths=[…] to
    disk and confirm the loader refuses it."""
    from cold_storage.evaluation.manifest import (
        ManifestError,
        load_and_validate_manifest,
    )

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
        load_and_validate_manifest(mf, referenced_files_check=False)


def test_d3_manifest_loader_rejects_wildcard_exclusion(tmp_path: Path) -> None:
    from cold_storage.evaluation.manifest import (
        ManifestError,
        load_and_validate_manifest,
    )

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
                "excluded_paths": ["$..id"],
            }
        )
    )
    with pytest.raises(ManifestError):
        load_and_validate_manifest(mf, referenced_files_check=False)
