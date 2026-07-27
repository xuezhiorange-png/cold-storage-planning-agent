"""Slice 1 canonical environment model and secure configuration resolution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

CANONICAL_PREFIX = "COLD_STORAGE_"
CANONICAL_KEYS = (
    "ENVIRONMENT_ID",
    "DATABASE_ENVIRONMENT_ID",
    "SECRET_ENVIRONMENT_ID",
    "ARTIFACT_ENVIRONMENT_ID",
    "CONFIG_SCHEMA_VERSION",
    "APP_DEBUG",
    "APP_HOST",
    "APP_PORT",
    "DATABASE_BACKEND",
    "DATABASE_URL",
    "SQLITE_PATH",
    "REDIS_URL",
    "STORAGE_DIR",
    "OPENAI_API_KEY",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "CONFIG_FILE",
    "SECRET_MOUNT_DIR",
)
LEGACY_KEYS = (
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
)
_SENSITIVE_KEYS = frozenset({"DATABASE_URL", "REDIS_URL", "OPENAI_API_KEY", "POSTGRES_PASSWORD"})


class EnvironmentId(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


LEGACY_ENVIRONMENT_MAP: dict[str, EnvironmentId] = {"development": EnvironmentId.LOCAL, **{x.value: x for x in EnvironmentId}}


class ConfigurationError(ValueError):
    """Safe configuration failure; message never contains raw values."""


@dataclass(frozen=True)
class ResolutionEntry:
    canonical_key: str
    source: str
    environment_id: str
    legacy_key_used: bool = False
    default_used: bool = False
    redacted: bool = False
    validation_status: str = "PASS"
    warning_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConfigurationResolutionReport:
    environment_id: str
    entries: tuple[ResolutionEntry, ...] = ()
    warning_codes: tuple[str, ...] = ()
    validation_status: str = "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "environment_id": self.environment_id,
            "entries": [
                {
                    "canonical_key": e.canonical_key,
                    "source": e.source,
                    "environment_id": e.environment_id,
                    "legacy_key_used": e.legacy_key_used,
                    "default_used": e.default_used,
                    "redacted": e.redacted,
                    "validation_status": e.validation_status,
                    "warning_codes": list(e.warning_codes),
                }
                for e in self.entries
            ],
            "warning_codes": list(self.warning_codes),
            "validation_status": self.validation_status,
        }

    def __repr__(self) -> str:
        return (
            f"ConfigurationResolutionReport(environment_id={self.environment_id!r}, "
            f"validation_status={self.validation_status!r}, entries={len(self.entries)})"
        )


def normalize_environment(value: str) -> EnvironmentId:
    try:
        return LEGACY_ENVIRONMENT_MAP[value.strip().lower()]
    except (KeyError, AttributeError) as exc:
        raise ConfigurationError("invalid environment identity") from exc


def canonical_key_for_legacy(key: str) -> str:
    return "ENVIRONMENT_ID" if key == "APP_ENV" else key


def _safe_text(value: object) -> str:
    return str(value).strip()


def parse_environment_id(environ: Mapping[str, str]) -> tuple[EnvironmentId, tuple[str, ...]]:
    canonical = environ.get("COLD_STORAGE_ENVIRONMENT_ID")
    legacy = environ.get("APP_ENV")
    warnings: list[str] = []
    if canonical is None and legacy is None:
        return EnvironmentId.LOCAL, ()
    if canonical is not None:
        env_id = normalize_environment(canonical)
        if legacy is not None:
            if normalize_environment(legacy) != env_id:
                raise ConfigurationError("canonical and legacy environment identities conflict")
            warnings.append("DEPRECATED_LEGACY_CONFIG_KEY")
        return env_id, tuple(warnings)
    env_id = normalize_environment(legacy or "")
    if env_id in (EnvironmentId.STAGING, EnvironmentId.PRODUCTION):
        raise ConfigurationError("legacy environment key is forbidden in strict environments")
    warnings.append("DEPRECATED_LEGACY_CONFIG_KEY")
    return env_id, tuple(warnings)


def validate_prefixed_keys(
    environ: Mapping[str, str], environment_id: EnvironmentId
) -> tuple[str, ...]:
    known = {CANONICAL_PREFIX + key for key in CANONICAL_KEYS}
    unknown = sorted(k for k in environ if k.startswith(CANONICAL_PREFIX) and k not in known)
    if unknown and environment_id in (EnvironmentId.STAGING, EnvironmentId.PRODUCTION):
        raise ConfigurationError("unknown canonical configuration key")
    return ("UNKNOWN_COLD_STORAGE_KEY",) if unknown else ()


def validate_legacy_keys(environ: Mapping[str, str], environment_id: EnvironmentId) -> None:
    present = set(environ).intersection(LEGACY_KEYS)
    if present and environment_id in (EnvironmentId.STAGING, EnvironmentId.PRODUCTION):
        raise ConfigurationError("legacy configuration key is forbidden in strict environments")


def resolve_configuration(
    environ: Mapping[str, str],
) -> tuple[EnvironmentId, dict[str, str], ConfigurationResolutionReport]:
    environment_id, warnings = parse_environment_id(environ)
    validate_legacy_keys(environ, environment_id)
    warnings = warnings + validate_prefixed_keys(environ, environment_id)
    values: dict[str, str] = {}
    entries: list[ResolutionEntry] = []
    for key in CANONICAL_KEYS:
        canonical = CANONICAL_PREFIX + key
        legacy = key if key in LEGACY_KEYS else None
        if canonical in environ:
            values[key] = environ[canonical]
            entries.append(
                ResolutionEntry(
                    key,
                    "canonical_environment",
                    environment_id.value,
                    redacted=key in _SENSITIVE_KEYS,
                    warning_codes=warnings if key == "ENVIRONMENT_ID" else (),
                )
            )
        elif (
            environment_id in (EnvironmentId.LOCAL, EnvironmentId.TEST)
            and legacy
            and legacy in environ
        ):
            values[key] = environ[legacy]
            entries.append(
                ResolutionEntry(
                    key,
                    "legacy_environment",
                    environment_id.value,
                    legacy_key_used=True,
                    redacted=key in _SENSITIVE_KEYS,
                    warning_codes=("DEPRECATED_LEGACY_CONFIG_KEY",),
                )
            )
    values["ENVIRONMENT_ID"] = environment_id.value
    return (
        environment_id,
        values,
        ConfigurationResolutionReport(environment_id.value, tuple(entries), warnings),
    )


def validate_declared_identities(values: Mapping[str, str], environment_id: EnvironmentId) -> None:
    for key in ("DATABASE_ENVIRONMENT_ID", "SECRET_ENVIRONMENT_ID", "ARTIFACT_ENVIRONMENT_ID"):
        actual = values.get(key)
        if actual is None and environment_id in (EnvironmentId.STAGING, EnvironmentId.PRODUCTION):
            raise ConfigurationError("required declared resource identity is missing")
        if actual is not None and normalize_environment(actual) is not environment_id:
            raise ConfigurationError("declared resource identity does not match environment")
