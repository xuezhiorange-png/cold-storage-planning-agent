"""Manifest loader integration tests (TASK-011C V1).

These tests assert the **integration behavior** of
``load_and_validate_manifest`` end-to-end: file read, JSON parse,
JSON Schema validation, pydantic model validation, and SHA
derivation.
"""

from __future__ import annotations

import json
from pathlib import Path

from cold_storage.evaluation.manifest import (
    compute_manifest_sha,
    load_and_validate_manifest,
)


def _write_manifest(
    tmp_path: Path,
    body: dict,
    *,
    name: str = "manifest.json",
) -> Path:
    mf = tmp_path / name
    mf.write_text(json.dumps(body))
    return mf


def test_loader_returns_typed_manifest(tmp_path: Path) -> None:
    mf = _write_manifest(
        tmp_path,
        {
            "schema_version": "1.0",
            "suite_id": "t11c-v1",
            "scenarios": [
                {
                    "scenario_id": "baseline_feasible",
                    "database_backend": "sqlite",
                    "expected_outcome": "SUCCEEDED",
                }
            ],
        },
    )
    m = load_and_validate_manifest(mf, referenced_files_check=False)
    assert m.suite_id == "t11c-v1"
    assert m.schema_version == "1.0"
    assert len(m.scenarios) == 1


def test_loader_sha_is_deterministic(tmp_path: Path) -> None:
    body = {
        "schema_version": "1.0",
        "suite_id": "t",
        "scenarios": [
            {
                "scenario_id": "s1",
                "database_backend": "sqlite",
                "expected_outcome": "SUCCEEDED",
            }
        ],
    }
    mf = _write_manifest(tmp_path, body)
    m1 = load_and_validate_manifest(mf, referenced_files_check=False)
    m2 = load_and_validate_manifest(mf, referenced_files_check=False)
    assert compute_manifest_sha(m1) == compute_manifest_sha(m2)


def test_loader_sha_is_independent_of_field_order(tmp_path: Path) -> None:
    """The canonicalizer sorts keys, so the SHA is order-independent."""
    a_body = {
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
    b_body = {
        "scenarios": [
            {
                "expected_outcome": "SUCCEEDED",
                "database_backend": "sqlite",
                "scenario_id": "s",
            }
        ],
        "suite_id": "t",
        "schema_version": "1.0",
    }
    mf_a = _write_manifest(tmp_path, a_body, name="a.json")
    mf_b = _write_manifest(tmp_path, b_body, name="b.json")
    m_a = load_and_validate_manifest(mf_a, referenced_files_check=False)
    m_b = load_and_validate_manifest(mf_b, referenced_files_check=False)
    assert compute_manifest_sha(m_a) == compute_manifest_sha(m_b)


def test_loader_with_baseline_scenario(tmp_path: Path) -> None:
    """A minimal V1 manifest that includes the
    ``baseline_feasible`` scenario loads successfully."""
    mf = _write_manifest(
        tmp_path,
        {
            "schema_version": "1.0",
            "suite_id": "t11c-v1-baseline",
            "scenarios": [
                {
                    "scenario_id": "baseline_feasible",
                    "database_backend": "sqlite",
                    "expected_outcome": "SUCCEEDED",
                }
            ],
            "provenance": {
                "contract_authority_comment_id": 4959798219,
            },
            "excluded_paths": [],
        },
    )
    m = load_and_validate_manifest(mf, referenced_files_check=False)
    assert m.scenarios[0].scenario_id == "baseline_feasible"
    assert m.scenarios[0].db_dialect.value == "sqlite"
    assert m.scenarios[0].expected_outcome.value == "SUCCEEDED"


def test_loader_rejects_file_with_no_extension(tmp_path: Path) -> None:
    """A file without a JSON extension still loads (the loader
    does not require ``.json``)."""
    mf = tmp_path / "manifest"
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
            }
        )
    )
    m = load_and_validate_manifest(mf, referenced_files_check=False)
    assert m.suite_id == "t"


def test_loader_computes_64_char_hex_sha(tmp_path: Path) -> None:
    mf = _write_manifest(
        tmp_path,
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
        },
    )
    m = load_and_validate_manifest(mf, referenced_files_check=False)
    sha = compute_manifest_sha(m)
    assert len(sha) == 64
    int(sha, 16)  # must be valid hex
