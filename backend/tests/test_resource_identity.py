"""Declared identity tests; resource-side checks remain false in Slice 1."""

from __future__ import annotations

import pytest

from cold_storage.bootstrap.environment_model import ConfigurationError, EnvironmentId
from cold_storage.bootstrap.resource_identity import (
    identity_status,
    validate_declared_resource_identity,
)


def test_declared_identity_status_does_not_claim_resource_binding() -> None:
    status = identity_status()
    assert status["DECLARED_IDENTITY_VALIDATED"] is True
    assert status["DATABASE_RESOURCE_BOUND_IDENTITY_VALIDATED"] is False
    assert status["SECRET_STORAGE_BOUND_IDENTITY_VALIDATED"] is False
    assert status["ARTIFACT_STORAGE_BOUND_IDENTITY_VALIDATED"] is False


def test_strict_declared_identity_mismatch() -> None:
    with pytest.raises(ConfigurationError):
        validate_declared_resource_identity(
            {"DATABASE_ENVIRONMENT_ID": "staging"}, EnvironmentId.PRODUCTION
        )
