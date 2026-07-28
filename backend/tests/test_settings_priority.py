"""Slice 1 settings priority tests."""

from __future__ import annotations

import pytest

from cold_storage.bootstrap.environment_model import ConfigurationError, resolve_configuration


def test_canonical_environment_wins_when_legacy_matches() -> None:
    env_id, values, report = resolve_configuration(
        {"COLD_STORAGE_ENVIRONMENT_ID": "local", "APP_ENV": "development"}
    )
    assert env_id.value == "local"
    assert values["ENVIRONMENT_ID"] == "local"
    assert "DEPRECATED_LEGACY_CONFIG_KEY" in report.warning_codes


def test_canonical_environment_conflict_fails_closed() -> None:
    with pytest.raises(ConfigurationError):
        resolve_configuration({"COLD_STORAGE_ENVIRONMENT_ID": "local", "APP_ENV": "production"})


def test_unrelated_os_variables_are_ignored() -> None:
    env_id, _, report = resolve_configuration({"PATH": "/usr/bin", "HOME": "/root"})
    assert env_id.value == "local"
    assert report.warning_codes == ()
