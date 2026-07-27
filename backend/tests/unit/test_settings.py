"""Tests for the Slice 1 four-environment secure settings contract."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from cold_storage.bootstrap.environment_model import (
    ConfigurationError,
    EnvironmentId,
    resolve_configuration,
)
from cold_storage.bootstrap.settings import Settings


@pytest.fixture(autouse=True)
def clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("COLD_STORAGE_") or key in {
            "APP_ENV",
            "APP_DEBUG",
            "APP_HOST",
            "APP_PORT",
            "DATABASE_BACKEND",
            "DATABASE_URL",
            "SQLITE_PATH",
            "POSTGRES_HOST",
            "POSTGRES_PORT",
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "REDIS_URL",
            "STORAGE_DIR",
            "OPENAI_API_KEY",
        }:
            monkeypatch.delenv(key, raising=False)


def strict_env(mode: str = "production") -> dict[str, str]:
    return {
        "COLD_STORAGE_ENVIRONMENT_ID": mode,
        "COLD_STORAGE_CONFIG_SCHEMA_VERSION": "1",
        "COLD_STORAGE_APP_DEBUG": "false",
        "COLD_STORAGE_APP_HOST": "127.0.0.1",
        "COLD_STORAGE_APP_PORT": "8000",
        "COLD_STORAGE_DATABASE_BACKEND": "postgresql",
        "COLD_STORAGE_DATABASE_URL": "postgresql+psycopg2://u:p@db:5432/cold_storage",
        "COLD_STORAGE_DATABASE_ENVIRONMENT_ID": mode,
        "COLD_STORAGE_SECRET_ENVIRONMENT_ID": mode,
        "COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID": mode,
        "COLD_STORAGE_STORAGE_DIR": f"/var/lib/cold-storage/{mode}/artifacts",
    }


def test_four_canonical_environment_modes() -> None:
    assert [x.value for x in EnvironmentId] == ["local", "test", "staging", "production"]
    assert Settings().environment_id is EnvironmentId.LOCAL
    assert Settings().app_env == "local"


def test_legacy_development_maps_to_local() -> None:
    env_id, _, report = resolve_configuration({"APP_ENV": "development"})
    assert env_id is EnvironmentId.LOCAL
    assert "DEPRECATED_LEGACY_CONFIG_KEY" in report.warning_codes


def test_canonical_legacy_conflict_fails_closed() -> None:
    with pytest.raises((ConfigurationError, ValidationError)):
        Settings.model_validate({"COLD_STORAGE_ENVIRONMENT_ID": "test", "APP_ENV": "production"})


@pytest.mark.parametrize("mode", ["staging", "production"])
def test_strict_modes_require_canonical_environment_and_reject_legacy(mode: str) -> None:
    values = strict_env(mode)
    values["APP_DEBUG"] = "false"
    with pytest.raises((ConfigurationError, ValidationError)):
        Settings.model_validate({**values, "APP_ENV": mode})


def test_unknown_prefixed_key_policy() -> None:
    with pytest.raises((ConfigurationError, ValidationError)):
        Settings.model_validate({**strict_env(), "COLD_STORAGE_TYPO": "x"})
    _, _, report = resolve_configuration({"COLD_STORAGE_TYPO": "x"})
    assert "UNKNOWN_COLD_STORAGE_KEY" in report.warning_codes


def test_discrete_postgresql_uses_psycopg2_and_redacts_password() -> None:
    settings = Settings.model_validate(
        {
            "COLD_STORAGE_ENVIRONMENT_ID": "local",
            "COLD_STORAGE_DATABASE_BACKEND": "postgresql",
            "COLD_STORAGE_POSTGRES_HOST": "db",
            "COLD_STORAGE_POSTGRES_PORT": 5432,
            "COLD_STORAGE_POSTGRES_DB": "cold_storage",
            "COLD_STORAGE_POSTGRES_USER": "user",
            "COLD_STORAGE_POSTGRES_PASSWORD": "secret-password",
        }
    )
    assert settings.database_url.startswith("postgresql+psycopg2://")
    assert "secret-password" not in repr(settings)


def test_env_example_uses_canonical_names_and_safe_driver() -> None:
    content = (Path(__file__).resolve().parents[3] / ".env.example").read_text()
    assert "COLD_STORAGE_ENVIRONMENT_ID=local" in content
    assert "postgresql+psycopg2" in content
    assert "postgresql+asyncpg" not in content
    assert "password@" not in content
