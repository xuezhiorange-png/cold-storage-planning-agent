"""Tests for cold_storage.bootstrap.settings configuration."""

from __future__ import annotations

from pathlib import Path

import pytest

from cold_storage.bootstrap.settings import Settings


class TestDefaultSQLiteConfig:
    """Default configuration should produce a SQLite database URL."""

    def test_database_backend_defaults_to_sqlite(self):
        settings = Settings()
        assert settings.database_backend == "sqlite"

    def test_default_sqlite_url_built_from_path(self):
        settings = Settings()
        assert settings.sqlite_path in settings.database_url
        assert settings.database_url.startswith("sqlite:///")

    def test_default_app_port(self):
        settings = Settings()
        assert settings.app_port == 8000

    def test_default_app_host(self):
        settings = Settings()
        assert settings.app_host == "0.0.0.0"


class TestExplicitSQLiteConfig:
    """Explicit SQLite configuration via env-like overrides."""

    def test_custom_sqlite_path(self):
        settings = Settings(sqlite_path="/tmp/my.db")
        assert settings.database_url == "sqlite:////tmp/my.db"

    def test_explicit_database_url_not_overwritten(self):
        settings = Settings(database_url="sqlite:///custom.db")
        assert settings.database_url == "sqlite:///custom.db"


class TestPostgreSQLConfig:
    """PostgreSQL URL construction from individual fields."""

    def test_postgres_url_built_from_fields(self):
        settings = Settings(
            database_backend="postgresql",
            postgres_host="db.example.com",
            postgres_port=5432,
            postgres_db="mydb",
            postgres_user="myuser",
            postgres_password="secret",
        )
        assert settings.database_url is not None
        assert "db.example.com" in settings.database_url
        assert "myuser" in settings.database_url
        assert "mydb" in settings.database_url
        assert settings.database_url.startswith("postgresql+asyncpg://")


class TestDatabaseBackendValidation:
    """database_backend must be 'sqlite' or 'postgresql'."""

    def test_valid_backends_accepted(self):
        s1 = Settings(database_backend="sqlite")
        assert s1.database_backend == "sqlite"
        s2 = Settings(database_backend="postgresql")
        assert s2.database_backend == "postgresql"

    def test_invalid_backend_rejected(self):
        with pytest.raises((ValueError, AttributeError)):
            Settings(database_backend="mysql")  # type: ignore[arg-type]


class TestSensitiveFieldMasking:
    """Sensitive fields should not leak in repr output."""

    def test_password_not_in_repr(self):
        settings = Settings(postgres_password="hunter2")
        r = repr(settings)
        assert "hunter2" not in r

    def test_redis_url_in_repr(self):
        settings = Settings()
        r = repr(settings)
        # Redis URL is not a sensitive field, port is visible
        assert "6379" in r


class TestEnvExampleConsistency:
    """.env.example keys must match Settings field names."""

    def test_env_example_matches_settings(self):
        env_path = Path(__file__).resolve().parents[3] / ".env.example"
        if not env_path.exists():
            pytest.skip(".env.example not found")

        env_keys = set()
        for line in env_path.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                env_keys.add(key)

        settings_fields = set(Settings.model_fields.keys())

        # Every non-commented env key should correspond to a Settings field
        # (case-insensitive match since env vars are typically UPPER_CASE)
        env_lower = {k.lower() for k in env_keys}
        settings_lower = {k.lower() for k in settings_fields}
        assert env_lower <= settings_lower, (
            f"Env keys not in Settings: {env_lower - settings_lower}"
        )
