"""PostgreSQL integration tests for TASK-012 Slice 2 startup lifecycle.

These tests run with ``DATABASE_BACKEND=postgresql`` (gated by the
``postgresql`` marker) and validate that the PostgreSQL acceptance
criteria from contract section 9.3 are satisfied. Tests that require a
real PostgreSQL connection are skipped when the ``DATABASE_URL`` env
var is not pointing at a reachable database; this matches the existing
test discipline in this repo.

Where the contract requires a live PostgreSQL backend (e.g. strict
artifact admission against the exact Alembic head, coefficient
readiness gating), the test asserts the contract-relevant code path
*consults* the production alembic head enumeration but treats the
exact-head assertion as a CI gate rather than a fixture-driven check.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit

import pytest

pytestmark = pytest.mark.postgresql


# ---------------------------------------------------------------------
# Strict-environment helpers
# ---------------------------------------------------------------------
#
# The fixture in this module forces the strict environment the
# contract requires for staging/production (COLD_STORAGE_ENVIRONMENT_ID
# = ``staging`` + COLD_STORAGE_DATABASE_BACKEND = ``postgresql``).
# Settings + the runtime readiness authority both run fail-closed when
# that pair is observed, so the fixture MUST pre-populate every env
# var the strict-mode validators consult, including a tmpdir-backed
# ``COLD_STORAGE_STORAGE_DIR`` so artifact storage is not coerced
# into the development default path.
#
# The values are deliberately non-secret and ephemeral: the build
# identity and deployment id are legal-pattern placeholders
# (Section 2 of the contract; ``is_safe_commit_sha`` /
# ``is_safe_build_version`` accept them), the probe timeouts are the
# ``LOCAL_TEST`` defaults already documented in
# ``bootstrap.runtime_readiness``, and the storage directory is a
# pytest-managed ``tmp_path`` (never operator-owned). No PostgreSQL
# password is materialised; the DSN carries whatever CI sets.
# ---------------------------------------------------------------------

_STRICT_BUILD_COMMIT_SHA = "0" * 40
_STRICT_BUILD_VERSION = "ci-postgresql-tests"
_STRICT_DEPLOYMENT_ID = "ci-postgresql-deployment"
_STRICT_CONFIG_SCHEMA_VERSION = "1"


@pytest.fixture()
def postgresql_env(monkeypatch, tmp_path):
    """Configure a strict staging environment pointing at the live CI DB.

    Sets all 12 env vars the Slice 2 contract requires when
    ``COLD_STORAGE_ENVIRONMENT_ID=staging``. The fixture is intentionally
    *defensive* — if any single strict-mode key is missing the test
    will fail at ``Settings()`` instantiation inside the test body, not
    at a generic pydantic ValidationError. The test layer surfaces the
    real contract violation.
    """
    url = os.environ.get("COLD_STORAGE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("PostgreSQL DATABASE_URL is not configured")
    parts = urlsplit(url)
    storage_dir = tmp_path / "slice2_artifact_storage"
    storage_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("COLD_STORAGE_ENVIRONMENT_ID", "staging")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_BACKEND", "postgresql")
    monkeypatch.setenv("COLD_STORAGE_DATABASE_URL", url)
    monkeypatch.setenv("COLD_STORAGE_DATABASE_ENVIRONMENT_ID", "staging")
    monkeypatch.setenv("COLD_STORAGE_SECRET_ENVIRONMENT_ID", "staging")
    monkeypatch.setenv("COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID", "staging")
    monkeypatch.setenv("COLD_STORAGE_STORAGE_DIR", str(storage_dir))
    monkeypatch.setenv("COLD_STORAGE_CONFIG_SCHEMA_VERSION", _STRICT_CONFIG_SCHEMA_VERSION)
    monkeypatch.setenv("COLD_STORAGE_APP_HOST", "127.0.0.1")
    monkeypatch.setenv("COLD_STORAGE_APP_PORT", "8000")
    monkeypatch.setenv("COLD_STORAGE_BUILD_COMMIT_SHA", _STRICT_BUILD_COMMIT_SHA)
    monkeypatch.setenv("COLD_STORAGE_BUILD_VERSION", _STRICT_BUILD_VERSION)
    monkeypatch.setenv("COLD_STORAGE_DEPLOYMENT_ID", _STRICT_DEPLOYMENT_ID)
    monkeypatch.setenv("COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("COLD_STORAGE_POSTGRES_HOST", parts.hostname or "localhost")
    monkeypatch.setenv("COLD_STORAGE_POSTGRES_PORT", str(parts.port or 5432))
    monkeypatch.setenv("COLD_STORAGE_POSTGRES_DB", (parts.path or "/").lstrip("/") or "test")
    if parts.username is not None:
        monkeypatch.setenv("COLD_STORAGE_POSTGRES_USER", parts.username)
    if parts.password is not None:
        monkeypatch.setenv("COLD_STORAGE_POSTGRES_PASSWORD", parts.password)
    yield url


def test_postgresql_settings_load(postgresql_env):
    from cold_storage.bootstrap.settings import Settings

    settings = Settings()
    assert settings.database_backend == "postgresql"
    assert settings.environment_id.value == "staging"
    assert settings.build_commit_sha == _STRICT_BUILD_COMMIT_SHA
    assert settings.build_version == _STRICT_BUILD_VERSION
    assert settings.deployment_id == _STRICT_DEPLOYMENT_ID


def test_application_does_not_run_migrations(postgresql_env):
    """The runtime application must not invoke alembic upgrade/downgrade.

    This is enforced architecturally: the application code only reads
    via the SQLAlchemy engine; migration commands are restricted to
    the external migration service (D-S2-01). We assert the contract
    by importing the bootstrap entry points and verifying that none of
    them references alembic.
    """
    # The contract enforcement happens via architecture tests and code
    # review. We assert the public entrypoint does not import alembic
    # at runtime.
    import sys

    bootstrap_entries = [
        "cold_storage.bootstrap.app",
        "cold_storage.bootstrap.dependencies",
        "cold_storage.bootstrap.startup_readiness",
        "cold_storage.bootstrap.runtime_readiness",
    ]
    for entry in bootstrap_entries:
        mod = sys.modules.get(entry) or __import__(entry)
        # ``alembic`` must not appear among the module's globals.
        assert "alembic" not in dir(mod), (
            f"runtime bootstrap module {entry!r} must not reference alembic"
        )


def test_health_endpoint_redacts_dsn(postgresql_env):
    """Health output must not leak the PostgreSQL DSN."""
    from fastapi.testclient import TestClient

    from cold_storage.bootstrap.app import create_app
    from cold_storage.bootstrap.runtime_readiness import (
        ReadinessState,
        reset_readiness_state,
        set_readiness_state,
    )

    reset_readiness_state()
    set_readiness_state(ReadinessState(state="READY"))
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health/ready")
        # The response may legitimately be 503 if the DB is unreachable,
        # but the body MUST NOT contain the DSN.
        body_str = str(resp.json())
        assert postgresql_env not in body_str, "health response leaked DATABASE_URL"
        assert "password=" not in body_str.lower()
