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
from cold_storage.bootstrap.settings import AgentCapabilityState, Settings
from cold_storage.modules.planning_agent.domain.errors import AgentProviderFailureCode


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


def test_p2_canonical_agent_keys_are_typed_and_configuration_is_not_provider_ready() -> None:
    settings = Settings.model_validate(
        {
            "COLD_STORAGE_AGENT_PROVIDER": "openai",
            "COLD_STORAGE_AGENT_MODEL": "gpt-test",
            "COLD_STORAGE_AGENT_TIMEOUT_SECONDS": "1",
            "COLD_STORAGE_AGENT_MAX_RETRIES": "0",
            "COLD_STORAGE_OPENAI_API_KEY": "test-only-secret",
        }
    )

    assert settings.agent_provider == "openai"
    assert settings.agent_model == "gpt-test"
    assert settings.agent_timeout_seconds == 1
    assert settings.agent_max_retries == 0
    assert settings.agent_enablement_intent_present is True
    assert settings.agent_capability_state is AgentCapabilityState.ENABLED_NOT_READY
    assert settings.agent_configuration_valid is True
    assert settings.production_provider_ready is False


def test_strict_agent_disabled_configuration_does_not_require_agent_fields() -> None:
    settings = Settings.model_validate(strict_env("production"))

    assert settings.agent_enablement_intent_present is False
    assert settings.agent_capability_state is AgentCapabilityState.DISABLED
    assert settings.agent_configuration_valid is True
    assert settings.agent_timeout_seconds is None
    assert settings.agent_max_retries is None
    assert settings.openai_api_key is None


@pytest.mark.parametrize(
    "extra",
    [
        {"COLD_STORAGE_OPENAI_API_KEY": "test-only-secret"},
        {"COLD_STORAGE_AGENT_TIMEOUT_SECONDS": "10"},
        {"COLD_STORAGE_AGENT_MAX_RETRIES": "1"},
    ],
)
def test_non_selection_agent_facts_do_not_create_enablement_intent(
    extra: dict[str, str],
) -> None:
    settings = Settings.model_validate(extra)

    assert settings.agent_enablement_intent_present is False
    assert settings.agent_capability_state is AgentCapabilityState.DISABLED
    assert settings.agent_configuration_valid is True


@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"COLD_STORAGE_AGENT_TIMEOUT_SECONDS": 1},
        {"COLD_STORAGE_AGENT_TIMEOUT_SECONDS": 30},
        {"COLD_STORAGE_AGENT_MAX_RETRIES": 0},
        {"COLD_STORAGE_AGENT_MAX_RETRIES": 1},
    ],
)
def test_disabled_agent_accepts_valid_optional_bounds_without_enablement_intent(
    extra: dict[str, int],
) -> None:
    settings = Settings.model_validate(extra)

    assert settings.agent_enablement_intent_present is False
    assert settings.agent_capability_state is AgentCapabilityState.DISABLED
    assert settings.agent_configuration_valid is True
    assert settings.agent_capability_resolution.failure_code is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("COLD_STORAGE_AGENT_TIMEOUT_SECONDS", 0),
        ("COLD_STORAGE_AGENT_TIMEOUT_SECONDS", -1),
        ("COLD_STORAGE_AGENT_TIMEOUT_SECONDS", 31),
        ("COLD_STORAGE_AGENT_MAX_RETRIES", -1),
        ("COLD_STORAGE_AGENT_MAX_RETRIES", 2),
    ],
)
def test_invalid_disabled_optional_bounds_fail_closed_without_enablement_intent(
    field: str, value: int
) -> None:
    settings = Settings.model_validate({field: value})

    assert settings.agent_enablement_intent_present is False
    assert settings.agent_capability_state is AgentCapabilityState.DISABLED
    assert settings.agent_configuration_valid is False
    assert (
        settings.agent_capability_resolution.failure_code
        is AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID
    )


@pytest.mark.parametrize(
    "extra",
    [
        {"COLD_STORAGE_AGENT_PROVIDER": "openai"},
        {"COLD_STORAGE_AGENT_MODEL": "gpt-test"},
    ],
)
def test_partial_provider_model_selection_is_enabled_not_ready(
    extra: dict[str, str],
) -> None:
    settings = Settings.model_validate(extra)

    assert settings.agent_enablement_intent_present is True
    assert settings.agent_capability_state is AgentCapabilityState.ENABLED_NOT_READY
    assert settings.agent_configuration_valid is False
    assert (
        settings.agent_capability_resolution.failure_code
        is AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_MISSING
    )


def test_enabled_configuration_requires_timeout_retry_and_openai_key() -> None:
    base = {
        "COLD_STORAGE_AGENT_PROVIDER": "openai",
        "COLD_STORAGE_AGENT_MODEL": "gpt-test",
        "COLD_STORAGE_AGENT_TIMEOUT_SECONDS": "10",
        "COLD_STORAGE_AGENT_MAX_RETRIES": "1",
    }

    for missing_key in (
        "COLD_STORAGE_AGENT_TIMEOUT_SECONDS",
        "COLD_STORAGE_AGENT_MAX_RETRIES",
        "COLD_STORAGE_OPENAI_API_KEY",
    ):
        values = dict(base)
        values.pop(missing_key, None)
        settings = Settings.model_validate(values)
        assert settings.agent_capability_state is AgentCapabilityState.ENABLED_NOT_READY
        assert settings.agent_configuration_valid is False
        assert (
            settings.agent_capability_resolution.failure_code
            is AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_MISSING
        )


def test_unknown_provider_fails_closed_without_provider_fallback() -> None:
    settings = Settings.model_validate(
        {
            "COLD_STORAGE_AGENT_PROVIDER": "unknown-provider",
            "COLD_STORAGE_AGENT_MODEL": "gpt-test",
            "COLD_STORAGE_AGENT_TIMEOUT_SECONDS": "10",
            "COLD_STORAGE_AGENT_MAX_RETRIES": "0",
        }
    )

    assert settings.agent_capability_state is AgentCapabilityState.ENABLED_NOT_READY
    assert settings.agent_configuration_valid is False
    assert (
        settings.agent_capability_resolution.failure_code
        is AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID
    )


@pytest.mark.parametrize("timeout", [1, 30])
def test_agent_timeout_accepts_closed_inclusive_boundaries(timeout: int) -> None:
    settings = Settings.model_validate(
        {
            "COLD_STORAGE_AGENT_PROVIDER": "openai",
            "COLD_STORAGE_AGENT_MODEL": "gpt-test",
            "COLD_STORAGE_AGENT_TIMEOUT_SECONDS": timeout,
            "COLD_STORAGE_AGENT_MAX_RETRIES": 0,
            "COLD_STORAGE_OPENAI_API_KEY": "test-only-secret",
        }
    )

    assert settings.agent_timeout_seconds == timeout
    assert settings.agent_configuration_valid is True


@pytest.mark.parametrize("timeout", [0, -1, 31])
def test_agent_timeout_out_of_range_is_enabled_not_ready(timeout: int) -> None:
    settings = Settings.model_validate(
        {
            "COLD_STORAGE_AGENT_PROVIDER": "openai",
            "COLD_STORAGE_AGENT_MODEL": "gpt-test",
            "COLD_STORAGE_AGENT_TIMEOUT_SECONDS": timeout,
            "COLD_STORAGE_AGENT_MAX_RETRIES": 0,
            "COLD_STORAGE_OPENAI_API_KEY": "test-only-secret",
        }
    )

    assert settings.agent_capability_state is AgentCapabilityState.ENABLED_NOT_READY
    assert settings.agent_configuration_valid is False
    assert (
        settings.agent_capability_resolution.failure_code
        is AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID
    )


@pytest.mark.parametrize("retries", [0, 1])
def test_agent_retries_accept_frozen_values(retries: int) -> None:
    settings = Settings.model_validate(
        {
            "COLD_STORAGE_AGENT_PROVIDER": "openai",
            "COLD_STORAGE_AGENT_MODEL": "gpt-test",
            "COLD_STORAGE_AGENT_TIMEOUT_SECONDS": 10,
            "COLD_STORAGE_AGENT_MAX_RETRIES": retries,
            "COLD_STORAGE_OPENAI_API_KEY": "test-only-secret",
        }
    )

    assert settings.agent_max_retries == retries
    assert settings.agent_configuration_valid is True


@pytest.mark.parametrize("retries", [-1, 2])
def test_agent_retries_out_of_range_is_enabled_not_ready(retries: int) -> None:
    settings = Settings.model_validate(
        {
            "COLD_STORAGE_AGENT_PROVIDER": "openai",
            "COLD_STORAGE_AGENT_MODEL": "gpt-test",
            "COLD_STORAGE_AGENT_TIMEOUT_SECONDS": 10,
            "COLD_STORAGE_AGENT_MAX_RETRIES": retries,
            "COLD_STORAGE_OPENAI_API_KEY": "test-only-secret",
        }
    )

    assert settings.agent_capability_state is AgentCapabilityState.ENABLED_NOT_READY
    assert settings.agent_configuration_valid is False
    assert (
        settings.agent_capability_resolution.failure_code
        is AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("COLD_STORAGE_AGENT_TIMEOUT_SECONDS", "1.5"),
        ("COLD_STORAGE_AGENT_MAX_RETRIES", "not-an-integer"),
    ],
)
def test_agent_numeric_settings_reject_non_integer_values(field: str, value: str) -> None:
    with pytest.raises((ConfigurationError, ValidationError)):
        Settings.model_validate(
            {
                "COLD_STORAGE_AGENT_PROVIDER": "openai",
                "COLD_STORAGE_AGENT_MODEL": "gpt-test",
                "COLD_STORAGE_AGENT_TIMEOUT_SECONDS": "10",
                "COLD_STORAGE_AGENT_MAX_RETRIES": "0",
                "COLD_STORAGE_OPENAI_API_KEY": "test-only-secret",
                field: value,
            }
        )
