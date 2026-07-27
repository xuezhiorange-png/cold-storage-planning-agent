"""Explicit safe defaults for local/test only."""

from __future__ import annotations

from cold_storage.bootstrap.mode import AppMode

DEFAULTS: dict[AppMode, dict[str, str]] = {
    AppMode.LOCAL: {
        "CONFIG_SCHEMA_VERSION": "1",
        "APP_DEBUG": "false",
        "APP_HOST": "127.0.0.1",
        "APP_PORT": "8000",
        "DATABASE_BACKEND": "sqlite",
        "SQLITE_PATH": "./cold_storage_dev.db",
        "STORAGE_DIR": "./artifacts/local",
    },
    AppMode.TEST: {
        "CONFIG_SCHEMA_VERSION": "1",
        "APP_DEBUG": "false",
        "APP_HOST": "127.0.0.1",
        "APP_PORT": "8000",
        "DATABASE_BACKEND": "sqlite",
    },
    AppMode.STAGING: {"STORAGE_DIR": "/var/lib/cold-storage/staging/artifacts"},
    AppMode.PRODUCTION: {"STORAGE_DIR": "/var/lib/cold-storage/production/artifacts"},
}


def allowed_defaults(mode: AppMode) -> dict[str, str]:
    return dict(DEFAULTS[mode])
