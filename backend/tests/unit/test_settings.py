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


def test_explicit_database_backend_wins_over_inherited_postgres_env() -> None:
    """Regression: an explicit ``DATABASE_BACKEND=sqlite`` must survive an
    environment that has a complete set of ``POSTGRES_*`` variables inherited
    from a parent process (this is the real failure mode that hit
    ``tests/evaluation/test_postgresql_acceptance.py::
    test_baseline_golden_consumed_by_production_path`` under CI's
    ``backend-postgresql`` job: the ``a1_engine`` fixture set
    ``DATABASE_BACKEND=sqlite`` + ``SQLITE_PATH=<temp>`` in a subprocess that
    inherited ``POSTGRES_*`` from the job's service container, and the old
    discrete-key heuristic silently flipped the backend to ``postgresql``).
    """

    monkeypatch = pytest.MonkeyPatch()
    try:
        for inherited_key, inherited_value in (
            ("POSTGRES_HOST", "db.example"),
            ("POSTGRES_PORT", "5432"),
            ("POSTGRES_DB", "inherited_db"),
            ("POSTGRES_USER", "inherited_user"),
            ("POSTGRES_PASSWORD", "inherited_password"),
        ):
            monkeypatch.setenv(inherited_key, inherited_value)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        # The autouse ``clear_env`` fixture guarantees no canonical
        # ``COLD_STORAGE_*`` aliases are present; the explicit SQLite
        # configuration therefore has to be supplied via the legacy keys
        # to mimic the alembic subprocess path that triggered the bug.
        monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
        monkeypatch.setenv("SQLITE_PATH", "/tmp/explicit-test.db")
        settings = Settings()
    finally:
        monkeypatch.undo()

    assert settings.database_backend == "sqlite"
    assert settings.sqlite_path == "/tmp/explicit-test.db"
    assert settings.database_url == "sqlite:////tmp/explicit-test.db"


def test_inherited_postgres_fields_infer_postgresql_when_backend_unset() -> None:
    """Counterpart to the regression above: when the caller does NOT pick a
    database backend and the environment provides a complete discrete
    ``POSTGRES_*`` set, the backend is inferred as ``postgresql`` and the
    ``postgresql+psycopg2`` driver is used. This guarantees the previous
    behavior (the one the old heuristic protected) is preserved outside the
    buggy edge case."""

    monkeypatch = pytest.MonkeyPatch()
    try:
        for inherited_key, inherited_value in (
            ("POSTGRES_HOST", "db.example"),
            ("POSTGRES_PORT", "5432"),
            ("POSTGRES_DB", "inherited_db"),
            ("POSTGRES_USER", "inherited_user"),
            ("POSTGRES_PASSWORD", "inherited_password"),
        ):
            monkeypatch.setenv(inherited_key, inherited_value)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("DATABASE_BACKEND", raising=False)
        monkeypatch.delenv("SQLITE_PATH", raising=False)
        settings = Settings()
    finally:
        monkeypatch.undo()

    assert settings.database_backend == "postgresql"
    assert settings.database_url is not None
    assert settings.database_url.startswith("postgresql+psycopg2://")
