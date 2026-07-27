"""Slice 1 environment model tests."""

from __future__ import annotations

import pytest

from cold_storage.bootstrap.environment_model import (
    ConfigurationError,
    EnvironmentId,
    resolve_configuration,
    validate_declared_identities,
)


def test_modes_are_exactly_four() -> None:
    assert tuple(x.value for x in EnvironmentId) == ("local", "test", "staging", "production")


def test_default_and_legacy_environment_resolution() -> None:
    assert resolve_configuration({})[0] is EnvironmentId.LOCAL
    assert resolve_configuration({"APP_ENV": "development"})[0] is EnvironmentId.LOCAL
    assert resolve_configuration({"APP_ENV": "test"})[0] is EnvironmentId.TEST


def test_strict_legacy_rejection() -> None:
    with pytest.raises(ConfigurationError):
        resolve_configuration(
            {"COLD_STORAGE_ENVIRONMENT_ID": "production", "APP_ENV": "production"}
        )


def test_declared_identities_are_required_and_matching_in_strict_modes() -> None:
    values = {
        "DATABASE_ENVIRONMENT_ID": "production",
        "SECRET_ENVIRONMENT_ID": "production",
        "ARTIFACT_ENVIRONMENT_ID": "production",
    }
    validate_declared_identities(values, EnvironmentId.PRODUCTION)
    with pytest.raises(ConfigurationError):
        validate_declared_identities(
            {**values, "DATABASE_ENVIRONMENT_ID": "staging"}, EnvironmentId.PRODUCTION
        )
