"""Pydantic-compatible secure settings facade for Slice 1."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import Field, PrivateAttr, field_validator, model_validator
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
from cold_storage.modules.planning_agent.domain.errors import AgentProviderFailureCode


class AgentCapabilityState(StrEnum):
    """Closed P2 Agent capability states.

    P2-A can resolve disabled and syntactically not-ready states. The ready
    state remains unavailable until later provider and composition evidence is
    supplied by P2-B/P2-C.
    """

    DISABLED = "AGENT_CAPABILITY_DISABLED"
    ENABLED_READY = "AGENT_CAPABILITY_ENABLED_READY"
    ENABLED_NOT_READY = "AGENT_CAPABILITY_ENABLED_NOT_READY"


CapabilityState = AgentCapabilityState


@dataclass(frozen=True, slots=True)
class AgentCapabilityResolution:
    """Provider-neutral result of P2-A configuration resolution."""

    enablement_intent_present: bool
    state: AgentCapabilityState
    configuration_valid: bool
    provider: str | None = None
    model: str | None = None
    timeout_seconds: int | None = None
    max_retries: int | None = None
    failure_code: AgentProviderFailureCode | None = None
    provider_readiness_verified: bool = False
    real_agent_routes_enabled: bool = False


AgentConfigurationResolution = AgentCapabilityResolution


def _non_empty(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def resolve_agent_capability(
    *,
    provider: str | None,
    model: str | None,
    timeout_seconds: int | None,
    max_retries: int | None,
    mimo_api_key: str | None,
) -> AgentCapabilityResolution:
    """Resolve MiMo PAYG configuration without claiming provider readiness."""

    enablement_intent_present = provider is not None or model is not None
    optional_values_valid = (
        timeout_seconds is None or (type(timeout_seconds) is int and 1 <= timeout_seconds <= 30)
    ) and (max_retries is None or (type(max_retries) is int and 0 <= max_retries <= 1))
    if not optional_values_valid:
        return AgentCapabilityResolution(
            enablement_intent_present=enablement_intent_present,
            state=(
                AgentCapabilityState.ENABLED_NOT_READY
                if enablement_intent_present
                else AgentCapabilityState.DISABLED
            ),
            configuration_valid=False,
            provider=provider,
            model=model,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            failure_code=AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID,
        )
    if not enablement_intent_present:
        return AgentCapabilityResolution(
            enablement_intent_present=False,
            state=AgentCapabilityState.DISABLED,
            configuration_valid=True,
            provider=provider,
            model=model,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

    if (
        not _non_empty(provider)
        or not _non_empty(model)
        or timeout_seconds is None
        or max_retries is None
    ):
        return AgentCapabilityResolution(
            enablement_intent_present=True,
            state=AgentCapabilityState.ENABLED_NOT_READY,
            configuration_valid=False,
            provider=provider,
            model=model,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            failure_code=AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_MISSING,
        )

    if provider != "mimo" or model != "mimo-v2.5":
        return AgentCapabilityResolution(
            enablement_intent_present=True,
            state=AgentCapabilityState.ENABLED_NOT_READY,
            configuration_valid=False,
            provider=provider,
            model=model,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            failure_code=AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_INVALID,
        )

    if not _non_empty(mimo_api_key):
        return AgentCapabilityResolution(
            enablement_intent_present=True,
            state=AgentCapabilityState.ENABLED_NOT_READY,
            configuration_valid=False,
            provider=provider,
            model=model,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            failure_code=AgentProviderFailureCode.AGENT_PROVIDER_CONFIGURATION_MISSING,
        )

    if (
        not isinstance(mimo_api_key, str)
        or not mimo_api_key.startswith("sk-")
        or len(mimo_api_key) <= len("sk-")
    ):
        return AgentCapabilityResolution(
            enablement_intent_present=True,
            state=AgentCapabilityState.ENABLED_NOT_READY,
            configuration_valid=False,
            provider=provider,
            model=model,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            failure_code=AgentProviderFailureCode.AGENT_PROVIDER_CREDENTIAL_INVALID,
        )

    # P2-A proves syntax and completeness only. Provider/schema probes,
    # composition, and route audit remain later-slice authority.
    return AgentCapabilityResolution(
        enablement_intent_present=True,
        state=AgentCapabilityState.ENABLED_NOT_READY,
        configuration_valid=True,
        provider=provider,
        model=model,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )


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
    mimo_api_key: str | None = Field(default=None, validation_alias="COLD_STORAGE_MIMO_API_KEY")
    aily_connector_shared_secret: str | None = Field(
        default=None, validation_alias="COLD_STORAGE_AILY_CONNECTOR_SHARED_SECRET"
    )
    agent_provider: str | None = Field(default=None, validation_alias="COLD_STORAGE_AGENT_PROVIDER")
    agent_model: str | None = Field(default=None, validation_alias="COLD_STORAGE_AGENT_MODEL")
    agent_timeout_seconds: int | None = Field(
        default=None, validation_alias="COLD_STORAGE_AGENT_TIMEOUT_SECONDS"
    )
    agent_max_retries: int | None = Field(
        default=None, validation_alias="COLD_STORAGE_AGENT_MAX_RETRIES"
    )
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
    # TASK-012 Slice 2: build / deployment identity env vars.
    # These are surfaced through Settings for diagnostics; the canonical
    # authority at runtime is the in-image file under
    # ``/opt/cold-storage/build-identity.json``. See
    # ``bootstrap.deployment_identity`` and contract section D-S2-02.
    build_commit_sha: str | None = Field(
        default=None, validation_alias="COLD_STORAGE_BUILD_COMMIT_SHA"
    )
    build_version: str | None = Field(default=None, validation_alias="COLD_STORAGE_BUILD_VERSION")
    deployment_id: str | None = Field(default=None, validation_alias="COLD_STORAGE_DEPLOYMENT_ID")
    # TASK-012 Slice 2: probe-timeout configuration keys.
    # Numeric validation is owned by ``bootstrap.runtime_readiness``;
    # settings carries strings here to keep the existing settings
    # model backwards compatible.
    startup_probe_timeout_seconds: str | None = Field(
        default=None, validation_alias="COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS"
    )
    readiness_probe_timeout_seconds: str | None = Field(
        default=None, validation_alias="COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS"
    )

    _resolution_report: ConfigurationResolutionReport | None = PrivateAttr(default=None)
    _warnings: tuple[str, ...] = PrivateAttr(default=())
    _database_url_constructed_locally: bool = PrivateAttr(default=False)
    _agent_capability_resolution: AgentCapabilityResolution | None = PrivateAttr(default=None)

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

    @property
    def agent_enablement_intent_present(self) -> bool:
        return self.agent_provider is not None or self.agent_model is not None

    @property
    def agent_capability_resolution(self) -> AgentCapabilityResolution:
        if self._agent_capability_resolution is None:
            return resolve_agent_capability(
                provider=self.agent_provider,
                model=self.agent_model,
                timeout_seconds=self.agent_timeout_seconds,
                max_retries=self.agent_max_retries,
                mimo_api_key=self.mimo_api_key,
            )
        return self._agent_capability_resolution

    @property
    def agent_capability_state(self) -> AgentCapabilityState:
        return self.agent_capability_resolution.state

    @property
    def capability_state(self) -> AgentCapabilityState:
        """Compatibility alias for the canonical Agent capability state."""
        return self.agent_capability_state

    @property
    def agent_configuration_valid(self) -> bool:
        return self.agent_capability_resolution.configuration_valid

    @property
    def production_provider_ready(self) -> bool:
        """P2-A never asserts provider readiness from configuration alone."""
        return self.agent_capability_resolution.provider_readiness_verified

    @field_validator("agent_timeout_seconds", "agent_max_retries", mode="before")
    @classmethod
    def _parse_agent_integer(cls, value: Any) -> Any:
        if value is None or type(value) is int:
            return value
        if isinstance(value, str):
            candidate = value.strip()
            if re.fullmatch(r"[+-]?\d+", candidate):
                return int(candidate)
        raise ValueError("Agent configuration value must be an integer")

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
            {str(k): str(v) for k, v in source_for_resolution.items() if v is not None}
        )
        if unknown and env_id in (EnvironmentId.STAGING, EnvironmentId.PRODUCTION):
            raise ConfigurationError("unknown canonical configuration key")
        for key, value in normalized.items():
            if key in CANONICAL_KEYS and value is not None:
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
        self._agent_capability_resolution = resolve_agent_capability(
            provider=self.agent_provider,
            model=self.agent_model,
            timeout_seconds=self.agent_timeout_seconds,
            max_retries=self.agent_max_retries,
            mimo_api_key=self.mimo_api_key,
        )
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
