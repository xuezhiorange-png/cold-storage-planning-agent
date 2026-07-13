"""D5 schema-version literal tests (TASK-011C V1).

These tests assert the **D5 binding invariant**:

* Exactly ``schema_version="1.0"`` is accepted.
* Missing version is rejected.
* Numeric ``1.0`` (non-string) is rejected.
* Unknown version is rejected.
* Forward compatibility is fail-closed.
* Backward compatibility is not implicit.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from cold_storage.evaluation.manifest import (
    ManifestSchemaVersionError,
    load_and_validate_manifest,
)
from cold_storage.evaluation.models import MANIFEST_SCHEMA_VERSION, Manifest


def test_d5_literal_string_1_0_accepted() -> None:
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
    assert m.schema_version == "1.0"


def test_d5_numeric_1_0_rejected_at_model() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Manifest.model_validate(
            {
                "schema_version": 1.0,  # float, not str
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
    assert "schema_version" in str(exc_info.value)


def test_d5_integer_1_rejected_at_model() -> None:
    with pytest.raises(ValidationError):
        Manifest.model_validate(
            {
                "schema_version": 1,
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


def test_d5_unknown_version_rejected_at_model() -> None:
    with pytest.raises(ValidationError):
        Manifest.model_validate(
            {
                "schema_version": "1.1",
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


def test_d5_unknown_version_2_0_rejected() -> None:
    with pytest.raises(ValidationError):
        Manifest.model_validate(
            {
                "schema_version": "2.0",
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


def test_d5_empty_string_version_rejected() -> None:
    with pytest.raises(ValidationError):
        Manifest.model_validate(
            {
                "schema_version": "",
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


def test_d5_missing_version_rejected_at_model() -> None:
    with pytest.raises(ValidationError):
        Manifest.model_validate(
            {
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


def test_d5_loader_rejects_numeric_version(tmp_path: Path) -> None:
    mf = tmp_path / "manifest.json"
    mf.write_text(
        json.dumps(
            {
                "schema_version": 1.0,
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
    with pytest.raises(ManifestSchemaVersionError):
        load_and_validate_manifest(mf, referenced_files_check=False)


def test_d5_loader_rejects_unknown_version(tmp_path: Path) -> None:
    mf = tmp_path / "manifest.json"
    mf.write_text(
        json.dumps(
            {
                "schema_version": "2.5",
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
    with pytest.raises(ManifestSchemaVersionError):
        load_and_validate_manifest(mf, referenced_files_check=False)


def test_d5_loader_rejects_missing_version(tmp_path: Path) -> None:
    mf = tmp_path / "manifest.json"
    mf.write_text(
        json.dumps(
            {
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
    with pytest.raises(ManifestSchemaVersionError):
        load_and_validate_manifest(mf, referenced_files_check=False)


def test_d5_loader_accepts_literal_1_0(tmp_path: Path) -> None:
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
            }
        )
    )
    m = load_and_validate_manifest(mf, referenced_files_check=False)
    assert m.schema_version == "1.0"


def test_d5_frozen_constant() -> None:
    assert MANIFEST_SCHEMA_VERSION == "1.0"
