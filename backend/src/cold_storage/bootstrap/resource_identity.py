"""Declared resource identity validation; no resource-side I/O."""

from __future__ import annotations

from collections.abc import Mapping

from cold_storage.bootstrap.environment_model import (
    ConfigurationError,
    EnvironmentId,
    normalize_environment,
)

RESOURCE_IDENTITY_KEYS = (
    "DATABASE_ENVIRONMENT_ID",
    "SECRET_ENVIRONMENT_ID",
    "ARTIFACT_ENVIRONMENT_ID",
)


def validate_declared_resource_identity(
    values: Mapping[str, str], environment_id: str | EnvironmentId
) -> None:
    expected = normalize_environment(str(environment_id))
    for key in RESOURCE_IDENTITY_KEYS:
        value = values.get(key)
        if value is None:
            if expected in (EnvironmentId.STAGING, EnvironmentId.PRODUCTION):
                raise ConfigurationError("required declared resource identity is missing")
            continue
        if normalize_environment(value) is not expected:
            raise ConfigurationError("declared resource identity mismatch")


def identity_status() -> dict[str, bool]:
    return {
        "DECLARED_IDENTITY_VALIDATED": True,
        "DATABASE_RESOURCE_BOUND_IDENTITY_VALIDATED": False,
        "SECRET_STORAGE_BOUND_IDENTITY_VALIDATED": False,
        "ARTIFACT_STORAGE_BOUND_IDENTITY_VALIDATED": False,
    }
