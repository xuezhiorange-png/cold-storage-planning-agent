"""Canonical four-environment mode helpers."""

from __future__ import annotations

from enum import StrEnum


class AppMode(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


def resolve_app_mode(settings: object) -> AppMode:
    value = getattr(settings, "environment_id", getattr(settings, "app_env", None))
    try:
        return AppMode(str(value))
    except ValueError as exc:
        raise ValueError("unknown environment mode") from exc


def is_production_mode(mode: AppMode) -> bool:
    return mode is AppMode.PRODUCTION


def is_test_or_development(mode: AppMode) -> bool:
    return mode in (AppMode.LOCAL, AppMode.TEST)


__all__ = ["AppMode", "is_production_mode", "is_test_or_development", "resolve_app_mode"]
