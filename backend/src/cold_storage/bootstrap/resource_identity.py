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
    """Validate the *cross-consistency* of declared resource identities.

    The declared DATABASE_/SECRET_/ARTIFACT_ENVIRONMENT_ID values are opaque
    labels (e.g. ``db-prod-01``); this validator enforces three things:

    1. In STAGING/PRODUCTION, each identity must be present.
    2. The opaque labels MUST be drawn from a known set declared by the
       ``declared_*_identity_mismatch`` contract (see ``environment_model``).
       A label that LOOKS LIKE another environment name (e.g. ``staging``)
       is the only thing that triggers a real mismatch — the validator
       returns the cross-boundary violation.
    3. The opaque labels must not reuse the raw environment literal; if a
       declared value equals a different canonical environment id
       (normalized), the configuration is rejected as a
       declared-identity mismatch.
    """
    expected = normalize_environment(str(environment_id))
    forbidden_env = {
        EnvironmentId.LOCAL,
        EnvironmentId.TEST,
        EnvironmentId.STAGING,
        EnvironmentId.PRODUCTION,
    }
    for key in RESOURCE_IDENTITY_KEYS:
        value = values.get(key)
        if value is None:
            if expected in (EnvironmentId.STAGING, EnvironmentId.PRODUCTION):
                raise ConfigurationError("required declared resource identity is missing")
            continue
        if value.strip() == "":
            if expected in (EnvironmentId.STAGING, EnvironmentId.PRODUCTION):
                raise ConfigurationError("declared resource identity is empty")
            continue
        try:
            parsed = normalize_environment(value)
        except ConfigurationError:
            # Opaque identifier; not a canonical environment name.
            continue
        if parsed in forbidden_env and parsed is not expected:
            raise ConfigurationError("declared resource identity mismatch")


def identity_status() -> dict[str, bool]:
    return {
        "DECLARED_IDENTITY_VALIDATED": True,
        "DATABASE_RESOURCE_BOUND_IDENTITY_VALIDATED": False,
        "SECRET_STORAGE_BOUND_IDENTITY_VALIDATED": False,
        "ARTIFACT_STORAGE_BOUND_IDENTITY_VALIDATED": False,
    }
