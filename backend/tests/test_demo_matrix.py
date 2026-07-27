"""Required Slice 1 demo matrix."""

from __future__ import annotations

import pytest

from cold_storage.bootstrap.environment_model import ConfigurationError
from cold_storage.bootstrap.settings import Settings


def _settings(values: dict[str, object]) -> Settings:
    return Settings.model_validate(values)


def test_required_demo_matrix() -> None:
    cases = [
        ({"COLD_STORAGE_ENVIRONMENT_ID": "local"}, True),
        ({"COLD_STORAGE_ENVIRONMENT_ID": "test", "COLD_STORAGE_SQLITE_PATH": "/tmp/test.db"}, True),
        (
            {
                "COLD_STORAGE_ENVIRONMENT_ID": "staging",
                "COLD_STORAGE_CONFIG_SCHEMA_VERSION": "1",
                "COLD_STORAGE_APP_DEBUG": "false",
                "COLD_STORAGE_APP_HOST": "127.0.0.1",
                "COLD_STORAGE_APP_PORT": "8000",
                "COLD_STORAGE_DATABASE_BACKEND": "postgresql",
                "COLD_STORAGE_DATABASE_URL": "postgresql+psycopg2://u:p@db:5432/x",
                "COLD_STORAGE_DATABASE_ENVIRONMENT_ID": "staging",
                "COLD_STORAGE_SECRET_ENVIRONMENT_ID": "staging",
                "COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID": "staging",
                "COLD_STORAGE_STORAGE_DIR": "/var/lib/cold-storage/staging/artifacts",
            },
            True,
        ),
        (
            {
                "COLD_STORAGE_ENVIRONMENT_ID": "production",
                "COLD_STORAGE_CONFIG_SCHEMA_VERSION": "1",
                "COLD_STORAGE_APP_DEBUG": "false",
                "COLD_STORAGE_APP_HOST": "127.0.0.1",
                "COLD_STORAGE_APP_PORT": "8000",
                "COLD_STORAGE_DATABASE_BACKEND": "postgresql",
                "COLD_STORAGE_DATABASE_URL": "postgresql+psycopg2://u:p@db:5432/x",
                "COLD_STORAGE_DATABASE_ENVIRONMENT_ID": "production",
                "COLD_STORAGE_SECRET_ENVIRONMENT_ID": "production",
                "COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID": "production",
                "COLD_STORAGE_STORAGE_DIR": "/var/lib/cold-storage/production/artifacts",
            },
            True,
        ),
        (
            {
                "COLD_STORAGE_ENVIRONMENT_ID": "production",
                "COLD_STORAGE_DATABASE_BACKEND": "sqlite",
            },
            False,
        ),
        ({"COLD_STORAGE_ENVIRONMENT_ID": "production", "COLD_STORAGE_APP_DEBUG": "true"}, False),
        (
            {
                "COLD_STORAGE_ENVIRONMENT_ID": "production",
                "COLD_STORAGE_DATABASE_BACKEND": "postgresql",
                "COLD_STORAGE_POSTGRES_HOST": "db",
                "COLD_STORAGE_POSTGRES_PORT": "5432",
                "COLD_STORAGE_POSTGRES_DB": "x",
                "COLD_STORAGE_POSTGRES_USER": "u",
                "COLD_STORAGE_POSTGRES_PASSWORD": "",
            },
            False,
        ),
        (
            {
                "COLD_STORAGE_ENVIRONMENT_ID": "production",
                "COLD_STORAGE_DATABASE_ENVIRONMENT_ID": "production",
                "COLD_STORAGE_SECRET_ENVIRONMENT_ID": "production",
                "COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID": "staging",
            },
            False,
        ),
        (
            {
                "COLD_STORAGE_ENVIRONMENT_ID": "production",
                "COLD_STORAGE_DATABASE_ENVIRONMENT_ID": "staging",
                "COLD_STORAGE_SECRET_ENVIRONMENT_ID": "production",
                "COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID": "production",
            },
            False,
        ),
        (
            {
                "COLD_STORAGE_ENVIRONMENT_ID": "production",
                "COLD_STORAGE_DATABASE_ENVIRONMENT_ID": "production",
                "COLD_STORAGE_SECRET_ENVIRONMENT_ID": "staging",
                "COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID": "production",
            },
            False,
        ),
        (
            {
                "COLD_STORAGE_ENVIRONMENT_ID": "local",
                "COLD_STORAGE_DATABASE_URL": "postgresql+psycopg2://user:password@host/db",
                "COLD_STORAGE_POSTGRES_PASSWORD": "password",
            },
            True,
        ),
    ]
    assert len(cases) == 11
    for values, expected in cases:
        if expected:
            _settings(values)
        else:
            with pytest.raises((ConfigurationError, ValueError)):
                _settings(values)
