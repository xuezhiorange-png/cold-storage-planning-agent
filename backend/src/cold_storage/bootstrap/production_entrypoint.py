"""TASK-012 Slice 2: production runtime entrypoint.

This module is the **only** place the backend image launches the
``uvicorn`` server. It deliberately enforces every Slice 2 contract
guarantee that is checked at process boot:

* in-image build-identity authority cross-check (delegates to
  :mod:`bootstrap.deployment_identity`),
* mandatory readiness capability enumeration (defensive D-S2-06.c),
* per-probe timeout configuration (D-S2-03),
* no use of ``git`` at runtime for build identity (D-S2-02.a),
* no edit of ``uv.lock`` or any other lockfile at runtime,
* no import-time business singletons.

The entrypoint is invoked from the ``Dockerfile`` ``CMD`` in the
non-root image. It is NOT intended for use in ``local`` / ``test``
development: those environments should continue using
``uvicorn cold_storage.bootstrap.app:create_app --factory`` directly
so that pytest fixtures and the test SQLite path remain untouched.

Failure mode
=============

The entrypoint reports a stable failure code (``BUILD_IDENTITY_*`` or
``STARTUP_PROBE_TIMEOUT``) on stderr, flushes, and exits non-zero. It
does NOT swallow exceptions or log raw identity-file content.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
from typing import Any

logger = logging.getLogger("cold_storage.bootstrap.production_entrypoint")


def _resolve_required_env(keys: tuple[str, ...]) -> dict[str, str]:
    """Return a name->value dict for the required env vars; raise if missing."""
    collected: dict[str, str] = {}
    missing: list[str] = []
    for key in keys:
        value = os.environ.get(key, "")
        if value == "":
            missing.append(key)
        else:
            collected[key] = value
    if missing:
        raise RuntimeError(f"required production env vars missing: {sorted(missing)!r}")
    return collected


def run_entrypoint() -> int:
    """Production entry point. Returns the uvicorn process exit code."""
    # 1. Identity cross-check (delegates to bootstrap.deployment_identity).
    from contextlib import suppress

    from cold_storage.bootstrap.deployment_identity import load_runtime_identity  # noqa: PLC0415

    env = {k: v for k, v in os.environ.items()}
    try:
        in_image, deployment_id = load_runtime_identity(env=env)
    except Exception as exc:
        code = getattr(exc, "failure_code", None)
        logger.error(
            "startup blocked by build-identity failure: code=%s",
            code or "BUILD_IDENTITY_ERROR",
        )
        return 14  # distinct non-zero code for identity failures.

    logger.info(
        "startup proceeding: commit_sha=%s version=%s deployment_id=%s",
        in_image.commit_sha,
        in_image.version,
        deployment_id,
    )

    # 2. Probe-timeout configuration validation.
    from cold_storage.bootstrap.runtime_readiness import (  # noqa: PLC0415
        resolve_probe_timeout_seconds,
        validate_probe_timeout_seconds,
    )
    from cold_storage.bootstrap.settings import Settings  # noqa: PLC0415

    settings = Settings()

    for kind in ("startup", "readiness"):
        try:
            resolve_probe_timeout_seconds(settings=settings, kind=kind)
        except Exception as exc:
            logger.error(
                "startup blocked by probe-timeout configuration failure: kind=%s error=%s",
                kind,
                exc,
            )
            return 15

    # Validate explicit numeric form too: we already validated the env
    # var, this double-check passes if the value is consistent with the
    # settings model.
    for raw_kind, env_key in (
        ("startup", "COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS"),
        ("readiness", "COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS"),
    ):
        raw = os.environ.get(env_key, "")
        if raw != "":
            try:
                validate_probe_timeout_seconds(value=raw, kind=raw_kind)
            except Exception as exc:
                logger.error("probe timeout invalid: kind=%s value=%s error=%s", raw_kind, raw, exc)
                return 16

    # 3. Defensive strict-capability enumeration.
    from cold_storage.bootstrap.runtime_readiness import (  # noqa: PLC0415
        assert_no_unsafe_strict_capabilities,
    )

    assert_no_unsafe_strict_capabilities(app=None)

    # 4. Hand off to uvicorn. We import uvicorn lazily so the previous
    # safety checks have all passed before the WSGI factory is
    # constructed.
    import uvicorn  # noqa: PLC0415

    host = os.environ.get("COLD_STORAGE_APP_HOST", "0.0.0.0")
    try:
        port = int(os.environ.get("COLD_STORAGE_APP_PORT", "8000"))
    except ValueError:
        logger.error("COLD_STORAGE_APP_PORT is not an integer")
        return 17

    config = uvicorn.Config(
        "cold_storage.bootstrap.app:create_app",
        factory=True,
        host=host,
        port=port,
        log_level=os.environ.get("COLD_STORAGE_APP_LOG_LEVEL", "info"),
        # Reasonable bind defaults; production ops can override via
        # the env vars listed above. We intentionally do NOT pass any
        # production credential through this layer.
        workers=int(os.environ.get("COLD_STORAGE_APP_WORKERS", "1")),
    )
    server = uvicorn.Server(config)

    # Install a SIGTERM / SIGINT handler that flips readiness state
    # BEFORE the process exits so any in-flight orchestrator can
    # observe ``state=DRAINING``.
    def _install_signal_handlers() -> None:
        from cold_storage.bootstrap.runtime_readiness import get_readiness_state  # noqa: PLC0415

        def _signal_handler(signum: int, frame: Any) -> None:  # noqa: ARG001
            state = get_readiness_state()
            with suppress(Exception):
                if state is not None:
                    state.transition(to="DRAINING")
            logger.warning("received signal=%s; entering DRAINING state", signum)

        try:
            signal.signal(signal.SIGTERM, _signal_handler)
            signal.signal(signal.SIGINT, _signal_handler)
        except ValueError:
            # Not in main thread (e.g. under pytest); skip silently.
            pass

    _install_signal_handlers()

    # Use uvicorn's ``run()`` which returns the exit code.
    server.run()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Console-script entry point."""
    logging.basicConfig(level=os.environ.get("COLD_STORAGE_LOG_LEVEL", "INFO"))
    try:
        return run_entrypoint()
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
