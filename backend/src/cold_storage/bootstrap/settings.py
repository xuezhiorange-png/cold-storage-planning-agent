"""Pydantic-compatible secure settings facade for Slice 1."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import Field, PrivateAttr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from cold_storage.bootstrap.code_defaults import allowed_defaults
from cold_storage.bootstrap.environment_model import (
    CANONICAL_KEYS,
    CANONICAL_PREFIX,
    LEGACY_KEYS,
    ConfigurationError,
    ConfigurationResolutionReport,
    EnvironmentId,
    resolve_configuration,
    validate_declared_identities,
)
from cold_storage.bootstrap.mode import AppMode
from cold_storage.bootstrap.resource_identity import validate_declared_resource_identity


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore", case_sensitive=True)

    environment_id: EnvironmentId = Field(
        default=EnvironmentId.LOCAL, validation_alias="COLD_STORAGE_ENVIRONMENT_ID"
    )
    database_environment_id: str | None = Field(
        default=None, validation_alias="COLD_STORAGE_DATABASE_ENVIRONMENT_ID"
    )
    secret_environment_id: str | None = Field(
        default=None, validation_alias="COLD_STORAGE_SECRET_ENVIRONMENT_ID"
    )
    artifact_environment_id: str | None = Field(
        default=None, validation_alias="COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID"
    )
    config_schema_version: int = Field(
        default=1, validation_alias="COLD_STORAGE_CONFIG_SCHEMA_VERSION"
    )
    app_debug: bool = Field(default=False, validation_alias="COLD_STORAGE_APP_DEBUG")
    app_host: str = Field(default="127.0.0.1", validation_alias="COLD_STORAGE_APP_HOST")
    app_port: int = Field(default=8000, validation_alias="COLD_STORAGE_APP_PORT")
    database_backend: Literal["sqlite", "postgresql"] = Field(
        default="sqlite", validation_alias="COLD_STORAGE_DATABASE_BACKEND"
    )
    database_url: str | None = Field(default=None, validation_alias="COLD_STORAGE_DATABASE_URL")
    sqlite_path: str | None = Field(
        default="./cold_storage_dev.db", validation_alias="COLD_STORAGE_SQLITE_PATH"
    )
    redis_url: str | None = Field(default=None, validation_alias="COLD_STORAGE_REDIS_URL")
    storage_dir: str | None = Field(default=None, validation_alias="COLD_STORAGE_STORAGE_DIR")
    openai_api_key: str | None = Field(default=None, validation_alias="COLD_STORAGE_OPENAI_API_KEY")
    postgres_host: str | None = Field(default=None, validation_alias="COLD_STORAGE_POSTGRES_HOST")
    postgres_port: int | None = Field(default=None, validation_alias="COLD_STORAGE_POSTGRES_PORT")
    postgres_db: str | None = Field(default=None, validation_alias="COLD_STORAGE_POSTGRES_DB")
    postgres_user: str | None = Field(default=None, validation_alias="COLD_STORAGE_POSTGRES_USER")
    postgres_password: str | None = Field(
        default=None, validation_alias="COLD_STORAGE_POSTGRES_PASSWORD"
    )
    config_file: str | None = Field(default=None, validation_alias="COLD_STORAGE_CONFIG_FILE")
    secret_mount_dir: str | None = Field(
        default=None, validation_alias="COLD_STORAGE_SECRET_MOUNT_DIR"
    )

    _resolution_report: ConfigurationResolutionReport | None = PrivateAttr(default=None)
    _warnings: tuple[str, ...] = PrivateAttr(default=())
    _database_url_constructed_locally: bool = PrivateAttr(default=False)

    @property
    def app_env(self) -> str:
        """Compatibility read-only property; canonical key is ENVIRONMENT_ID."""
        return self.environment_id.value

    @property
    def resolution_report(self) -> ConfigurationResolutionReport | None:
        return self._resolution_report

    @property
    def warnings(self) -> tuple[str, ...]:
        return self._warnings

    @model_validator(mode="before")
    @classmethod
    def _canonicalize_sources(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        source = dict(data)
        if "app_env" in source and not any(str(k).startswith(CANONICAL_PREFIX) for k in source):
            source = {"COLD_STORAGE_ENVIRONMENT_ID": source["app_env"]}
        if not any(str(k).startswith(CANONICAL_PREFIX) for k in source) and not any(
            k in source for k in LEGACY_KEYS
        ):
            source.update(
                {
                    k: v
                    for k, v in os.environ.items()
                    if k.startswith(CANONICAL_PREFIX) or k in LEGACY_KEYS
                }
            )
        aliases = {"COLD_STORAGE_" + key: key for key in CANONICAL_KEYS}
        normalized = {aliases.get(str(k), str(k)): v for k, v in source.items()}
        source_for_resolution = {
            k: v for k, v in source.items() if not str(k).startswith(CANONICAL_PREFIX)
        }
        source_for_resolution.update(
            {"COLD_STORAGE_" + k: v for k, v in normalized.items() if k in CANONICAL_KEYS}
        )
        unknown = [
            k
            for k in source
            if str(k).startswith(CANONICAL_PREFIX)
            and str(k) not in {"COLD_STORAGE_" + x for x in CANONICAL_KEYS}
        ]
        if unknown:
            source_for_resolution.update({k: source[k] for k in unknown})
        env_id, values, report = resolve_configuration(
            {str(k): str(v) for k, v in source_for_resolution.items()}
        )
        if unknown and env_id in (EnvironmentId.STAGING, EnvironmentId.PRODUCTION):
            raise ConfigurationError("unknown canonical configuration key")
        for key, value in normalized.items():
            if key in CANONICAL_KEYS:
                values[key] = str(value)
        # Discrete PostgreSQL fields override DATABASE_URL only when they were
        # explicitly provided in the same input layer. Env-injected partial
        # discrete fields (e.g. POSTGRES_PASSWORD alone) must NOT cause the
        # URL to be dropped — the URL is the user's authoritative source.
        #
        # Precedence contract (must hold in all environments):
        #   explicit COLD_STORAGE_DATABASE_BACKEND
        #   > explicit legacy DATABASE_BACKEND
        #   > inference from DATABASE_URL or POSTGRES_*
        #   > code default
        # Inherited/injected POSTGRES_* MUST NOT silently flip a caller that
        # explicitly chose sqlite. Discrete PostgreSQL fields are only used to
        # infer the backend when the caller did not pick one.
        discrete_keys_present = any(
            key in normalized
            for key in (
                "POSTGRES_HOST",
                "POSTGRES_PORT",
                "POSTGRES_DB",
                "POSTGRES_USER",
                "POSTGRES_PASSWORD",
            )
        )
        url_present = "DATABASE_URL" in normalized
        if discrete_keys_present and not url_present and "DATABASE_BACKEND" not in normalized:
            values["DATABASE_BACKEND"] = "postgresql"
        defaults = allowed_defaults(AppMode(env_id.value))
        for key, value in defaults.items():
            values.setdefault(key, value)
        if env_id in (EnvironmentId.STAGING, EnvironmentId.PRODUCTION):
            if values.get("APP_DEBUG", "false").lower() == "true":
                raise ConfigurationError("debug is forbidden in strict environments")
            values.setdefault("ENVIRONMENT_ID", env_id.value)
            if values.get("APP_HOST") is None or values.get("APP_PORT") is None:
                raise ConfigurationError("strict environment requires explicit application binding")
            if values.get("DATABASE_BACKEND") != "postgresql":
                raise ConfigurationError("strict environment requires PostgreSQL")
            if values.get("SQLITE_PATH"):
                raise ConfigurationError("SQLite is forbidden in strict environments")
            if values.get("CONFIG_SCHEMA_VERSION") != "1":
                raise ConfigurationError("unsupported configuration schema version")
        validate_declared_identities(values, env_id)
        validate_declared_resource_identity(values, env_id)
        cls._pending_report = report  # type: ignore[attr-defined]
        result: dict[str, object] = {}
        for key, value in values.items():
            field_name = cls._field_name(key)
            if field_name not in cls.model_fields:
                continue
            alias = cls.model_fields[field_name].validation_alias
            result[str(alias) if alias is not None else field_name] = value
        return result

    @staticmethod
    def _field_name(key: str) -> str:
        return key.lower()

    @model_validator(mode="after")
    def _validate_complete(self) -> Settings:
        if not 1 <= self.app_port <= 65535:
            raise ConfigurationError("application port outside allowed range")
        if self.storage_dir is None:
            self.storage_dir = allowed_defaults(AppMode(self.environment_id)).get("STORAGE_DIR")
        if self.environment_id in (EnvironmentId.STAGING, EnvironmentId.PRODUCTION):
            self._validate_storage_path()
            self._validate_postgresql()
        if (
            self.environment_id is EnvironmentId.TEST
            and self.sqlite_path == "./cold_storage_dev.db"
        ):
            raise ConfigurationError("test SQLite path must be injected")
        self._resolution_report = getattr(type(self), "_pending_report", None)
        self._warnings = self._resolution_report.warning_codes if self._resolution_report else ()
        return self

    def _validate_storage_path(self) -> None:
        path = Path(self.storage_dir or "")
        if not path.is_absolute() or ".git" in path.parts:
            raise ConfigurationError("strict storage path must be outside repository")
        forbidden = (
            {"local", "test", "production"}
            if self.environment_id is EnvironmentId.STAGING
            else {"local", "test", "staging"}
        )
        if forbidden.intersection(path.parts):
            raise ConfigurationError("storage path crosses environment boundary")

    def _validate_postgresql(self) -> None:
        discrete = [
            self.postgres_host,
            self.postgres_port,
            self.postgres_db,
            self.postgres_user,
            self.postgres_password,
        ]
        # URL takes precedence: if DATABASE_URL is provided, discrete fields
        # are optional and never block configuration. Discrete fields are
        # only consulted when the URL was constructed locally from them.
        if (
            self.database_url is None
            and any(v not in (None, "") for v in discrete)
            and not all(v not in (None, "") for v in discrete)
        ):
            raise ConfigurationError("incomplete PostgreSQL configuration")
        if self.database_url is not None and not self.database_url.startswith(
            "postgresql+psycopg2://"
        ):
            raise ConfigurationError("unsupported PostgreSQL driver")
        # Cross-check URL and discrete fields ONLY when the URL was constructed
        # locally from discrete fields. When the user supplied the URL directly,
        # we trust the explicit source; discrete fields provided separately
        # (e.g. by env injection) are not re-asserted against the URL.
        if (
            self.database_url is not None
            and self._database_url_constructed_locally
            and all(v not in (None, "") for v in discrete)
        ):
            parsed = urlsplit(self.database_url)
            if (
                parsed.hostname != self.postgres_host
                or parsed.port != self.postgres_port
                or parsed.path.lstrip("/") != self.postgres_db
                or parsed.username != self.postgres_user
                or parsed.password != self.postgres_password
            ):
                raise ConfigurationError(
                    "DATABASE_URL and discrete PostgreSQL configuration differ"
                )

    @model_validator(mode="after")
    def _build_database_url(self) -> Settings:
        # URL construction respects the same precedence contract as
        # ``_canonicalize_sources``: an explicit backend choice wins over
        # inherited discrete PostgreSQL fields. When the caller picked
        # sqlite (and provided a SQLITE_PATH), we always build the
        # sqlite URL regardless of any stray POSTGRES_* values inherited
        # from the surrounding environment. Conversely, when the caller
        # did NOT pick a backend, a complete discrete PostgreSQL field
        # set is sufficient evidence to construct the psycopg2 URL.
        if self.database_url is not None:
            return self
        if self.database_backend == "sqlite":
            self.database_url = f"sqlite:///{self.sqlite_path}"
            return self
        # backend is "postgresql" here (inferred or explicit). Construct
        # the URL from discrete fields when they are all populated; if
        # any are missing, the URL stays None and the strict-env validator
        # will fail-closed in staging/production as documented.
        if all(
            v not in (None, "")
            for v in (
                self.postgres_host,
                self.postgres_port,
                self.postgres_db,
                self.postgres_user,
                self.postgres_password,
            )
        ):
            self.database_url = f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            self._database_url_constructed_locally = True
        return self

    def __repr_args__(self) -> list[tuple[str, object]]:
        from cold_storage.bootstrap.configuration_redactor import redact

        return list(redact(self.model_dump()).items())

    def __str__(self) -> str:
        return repr(self)


def get_settings() -> Settings:
    return Settings()
