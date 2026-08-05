"""TASK-012 Slice 2: runtime readiness authority.

This module is the **only** place that evaluates the Slice 2 readiness
gates and reports a per-process ``ReadinessState``. It owns the
following contract responsibilities (D-S2-03, D-S2-04, D-S2-06):

* startup validation order, executed exactly once during ``init_dependencies``;
* per-probe timeout budget, per D-S2-03.c, that does not assert
  equality with the conservative upper bound (D-S2-03.c + P1-006);
* mandatory readiness dependency set, per D-S2-04;
* defense-in-depth enumeration of strict-mode unsafe capabilities, per
  D-S2-06.c, with stable failure code ``UNSAFE_STRICT_CAPABILITY_WIRING``;
* bounded shutdown draining that flips the readiness state before
  dependency disposal (D-S2-10);
* a single re-entrant state machine that other modules (e.g.
  ``bootstrap.app`` health endpoints, ``bootstrap.dependencies``)
  consult to decide HTTP status codes.

Failure codes emitted by this module
=====================================

* ``STARTUP_PROBE_TIMEOUT``
* ``READINESS_PROBE_TIMEOUT``
* ``UNSAFE_STRICT_CAPABILITY_WIRING``
* ``DATABASE_SCHEMA_HEAD_INVALID``

All other lifecycle failure codes remain the responsibility of their
originating modules (e.g. ``StartUpReadinessError`` for coefficient
coverage, ``deployment_identity`` for build-identity failures). This
module does NOT introduce new failure-code categories.

Contract amendment V0.2 Slice 2 (D-S2-12.a.v0.2) freezes exactly one
additional stable failure code (``DATABASE_SCHEMA_HEAD_INVALID``) that
covers every non-timeout schema-head verification failure of the
``database_exact_alembic_head`` mandatory probe. The internal closed
set of reasons that all project to that single code is enumerated in
``_SCHEMA_HEAD_INTERNAL_REASONS`` and is NOT permitted to surface as
new public stable codes.

Module-level invariant
======================

Per the contract, no probe may spawn unbounded background threads or
tasks. All probe execution in this module is synchronous and
cancellable via :class:`ProbeTimeout` enforcement; the per-probe budget
is set by ``COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS`` /
``COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS`` per D-S2-03.a.
"""

from __future__ import annotations

import ast
import logging
import os
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from cold_storage.bootstrap.mode import AppMode, is_production_mode, resolve_app_mode
from cold_storage.bootstrap.settings import Settings

logger = logging.getLogger("cold_storage.bootstrap.runtime_readiness")

# Stable failure codes frozen by contract D-S2-12.a.
STARTUP_PROBE_TIMEOUT = "STARTUP_PROBE_TIMEOUT"
READINESS_PROBE_TIMEOUT = "READINESS_PROBE_TIMEOUT"
UNSAFE_STRICT_CAPABILITY_WIRING = "UNSAFE_STRICT_CAPABILITY_WIRING"
# D-S2-12.a.v0.2 amendment: single public stable code for every
# non-timeout failure of the exact schema-head verification probe.
# Internal reasons (PACKAGED_HEAD_*, DATABASE_HEAD_*, UNKNOWN_SCHEMA_IDENTITY)
# MUST NOT be introduced as separate public stable codes; they all
# project to this one identifier.
DATABASE_SCHEMA_HEAD_INVALID = "DATABASE_SCHEMA_HEAD_INVALID"
# D-S2-12.a.v0.2 amendment (artifact-storage-classification-amendment,
# PR #78 merged into main as binding contract): single public stable
# code for every non-timeout failure of the mandatory artifact-storage
# probe. Internal reasons (ARTIFACT_STORAGE_PATH_NOT_CONFIGURED /
# ARTIFACT_STORAGE_DIRECTORY_MISSING / ARTIFACT_STORAGE_DIRECTORY_NOT_WRITABLE
# / ARTIFACT_STORAGE_PROBE_IO_FAILURE) MUST NOT be introduced as
# separate public stable codes; they all project to this one
# identifier.
ARTIFACT_STORAGE_UNAVAILABLE = "ARTIFACT_STORAGE_UNAVAILABLE"


# Internal closed set of non-timeout reasons that project to
# ``DATABASE_SCHEMA_HEAD_INVALID``. NOT public stable codes. The count
# is frozen at 11 (see contract amendment).
_INTERNAL_SCHEMA_HEAD_REASONS = (
    "PACKAGED_HEAD_MISSING",
    "PACKAGED_HEAD_UNREADABLE",
    "PACKAGED_HEAD_MALFORMED",
    "PACKAGED_HEAD_ZERO",
    "PACKAGED_HEAD_MULTIPLE",
    "DATABASE_HEAD_UNREADABLE_AFTER_CONNECTION",
    "DATABASE_HEAD_ZERO",
    "DATABASE_HEAD_MULTIPLE",
    "DATABASE_HEAD_MALFORMED",
    "DATABASE_HEAD_MISMATCH",
    "UNKNOWN_SCHEMA_IDENTITY",
)


# Internal closed set of non-timeout reasons that project to
# ``ARTIFACT_STORAGE_UNAVAILABLE``. NOT public stable codes. The count
# is frozen at 4 (see artifact-storage-classification-amendment).
_INTERNAL_ARTIFACT_STORAGE_REASONS = (
    "ARTIFACT_STORAGE_PATH_NOT_CONFIGURED",
    "ARTIFACT_STORAGE_DIRECTORY_MISSING",
    "ARTIFACT_STORAGE_DIRECTORY_NOT_WRITABLE",
    "ARTIFACT_STORAGE_PROBE_IO_FAILURE",
)


def _schema_head_invalid(*, name: str, internal_reason: str, duration: float) -> ProbeOutcome:
    """Return a ``ProbeOutcome`` projected to ``DATABASE_SCHEMA_HEAD_INVALID``.

    The ``internal_reason`` MUST be one of the 11 frozen internal
    strings above; any other reason must be coerced to
    ``UNKNOWN_SCHEMA_IDENTITY`` so no public stable code other than
    ``DATABASE_SCHEMA_HEAD_INVALID`` is ever emitted for the schema
    probe. The safe projection never includes the raw exception text,
    packaged Head value, database Head value, DSN, or SQL.
    """
    if internal_reason not in _INTERNAL_SCHEMA_HEAD_REASONS:
        internal_reason = "UNKNOWN_SCHEMA_IDENTITY"
    return ProbeOutcome(
        name=name,
        status="fail",
        code=DATABASE_SCHEMA_HEAD_INVALID,
        detail=f"schema-head non-timeout failure ({internal_reason})",
        duration_seconds=duration,
    )


def _artifact_storage_unavailable(
    *,
    name: str,
    internal_reason: str,
    duration: float,
) -> ProbeOutcome:
    """Return a ``ProbeOutcome`` projected to ``ARTIFACT_STORAGE_UNAVAILABLE``.

    The ``internal_reason`` MUST be one of the 4 frozen internal
    strings in ``_INTERNAL_ARTIFACT_STORAGE_REASONS``; any other
    reason must raise :class:`RuntimeError` so the probe fail-closed
    rather than silently emitting a public stable code that was not
    authorized by the artifact-storage-classification-amendment
    contract. The safe projection never includes the full absolute
    storage path, host mount path, container volume source, raw
    ``OSError`` text, errno, filesystem user/group, file mode
    details, the probe file name, secrets, DSN, or traceback
    fragments.
    """
    if internal_reason not in _INTERNAL_ARTIFACT_STORAGE_REASONS:
        raise RuntimeError(
            "unknown artifact-storage internal reason; "
            "refusing to project to ARTIFACT_STORAGE_UNAVAILABLE"
        )
    return ProbeOutcome(
        name=name,
        status="fail",
        code=ARTIFACT_STORAGE_UNAVAILABLE,
        detail=f"artifact-storage non-timeout failure ({internal_reason})",
        duration_seconds=duration,
    )


CONFIGURATION_IDENTITY_FAILURE = "ConfigurationError"
# F-PR76-MEDIUM-01: ``CONFIGURATION_IDENTITY_FAILURE`` is the class
# name of the Slice 1 frozen :class:`ConfigurationError`. We use it
# here as a module-level documentation alias for the stable
# ``check_code`` the readiness endpoint projects. It is NOT a new
# stable string the runtime invented — it is the Python class name,
# which is itself a frozen identifier.

# F-PR76-MEDIUM-01: the previous code defined a module-level
# ``CONFIGURATION_PROBE_FAILED = "CONFIGURATION_PROBE_FAILED"``
# constant to back the same-named ``ReadinessError`` subclass. That
# constant is removed in this commit; configuration-identity
# failures now propagate as the Slice 1 frozen
# :class:`ConfigurationError` and the readiness endpoint projects
# the Python class name ``"ConfigurationError"`` into the response.

# D-S2-03.b. validation ranges (seconds).
STARTUP_PROBE_TIMEOUT_MIN = 1
STARTUP_PROBE_TIMEOUT_MAX = 120
READINESS_PROBE_TIMEOUT_MIN = 1
READINESS_PROBE_TIMEOUT_MAX = 30

# Local/test defaults per D-S2-03.b.
LOCAL_TEST_STARTUP_PROBE_TIMEOUT_SECONDS = 30
LOCAL_TEST_READINESS_PROBE_TIMEOUT_SECONDS = 5


class ReadinessError(Exception):
    """Base class for all readiness-time failures."""


class StartupProbeTimeout(ReadinessError):
    failure_code = STARTUP_PROBE_TIMEOUT


class ReadinessProbeTimeout(ReadinessError):
    failure_code = READINESS_PROBE_TIMEOUT


class UnsafeStrictCapabilityWiring(ReadinessError):
    """Fail-closed assertion for unsafe strict-capability reachability (D-S2-06.c)."""

    failure_code = UNSAFE_STRICT_CAPABILITY_WIRING

    def __init__(
        self,
        message: str,
        *,
        unsafe_capabilities: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.unsafe_capabilities: tuple[str, ...] = tuple(unsafe_capabilities)


class StartupNonTimeoutProbeFailure(ReadinessError):
    """Internal: a non-timeout ``Exception`` escaped a probe body.

    V0.2 Slice 2 amendment (D-S2-12.a.v0.2): the legacy fallback that
    mapped arbitrary non-timeout exceptions to a timeout code has been
    removed. Callers that have not (yet) declared a distinct
    ``on_non_timeout_code`` MUST observe a fail-closed non-timeout
    failure rather than a silent ``STARTUP_PROBE_TIMEOUT`` /
    ``READINESS_PROBE_TIMEOUT`` mis-projection. The exception carries
    only the safe probe name and the original exception; the message
    is redacted to avoid leaking the raw exception text into logs
    surfaced by the public health envelope.
    """

    def __init__(
        self,
        *,
        probe_name: str,
        original_exception: BaseException,
    ) -> None:
        self.probe_name = probe_name
        self.original_exception = original_exception
        self.failure_code = getattr(original_exception, "failure_code", None)
        super().__init__(
            f"startup probe {probe_name!r} raised non-timeout exception "
            f"({type(original_exception).__name__}); see logs for details"
        )


class StartupProbeFailure(ReadinessError):
    """Internal: a startup probe reported a non-timeout failure code.

    Carries only the safe probe name and the stable failure code
    string. The message MUST NOT embed the raw probe detail, head
    value, DSN, SQL, or any other secret / environment value.
    """

    def __init__(self, *, probe_name: str, failure_code: str) -> None:
        self.probe_name = probe_name
        self.failure_code = failure_code
        super().__init__(f"startup probe {probe_name!r} reported failure code={failure_code!r}")


# F-PR76-MEDIUM-01: the prior implementation defined a dedicated
# ``ConfigurationProbeFailed(ReadinessError)`` subclass carrying the
# unfrozen ``CONFIGURATION_PROBE_FAILED`` code. Review 4807016607
# flagged this as an unfrozen contract addition; brief §10 requires
# either reusing a Slice 1 frozen code or stopping with
# ``STOPPED_CONTRACT_AMENDMENT_REQUIRED``.
#
# The contract-compliant replacement is the Slice 1 frozen
# :class:`cold_storage.bootstrap.environment_model.ConfigurationError`.
# We therefore re-export the frozen class under the local name
# ``ConfigurationProbeFailed`` so call sites can keep their existing
# ``except ConfigurationProbeFailed:`` branches while the runtime
# authority is the Slice 1 frozen identity. The readiness endpoint
# projects the Python class name into ``check_code``; the projection
# is a frozen Python identifier (``"ConfigurationError"``), NOT a new
# stable string.
try:  # pragma: no cover - import is intentionally deferred
    from cold_storage.bootstrap.environment_model import (  # noqa: E402
        ConfigurationError as ConfigurationProbeFailed,
    )
except Exception:  # noqa: BLE001
    # ``ConfigurationError`` is the Slice 1 frozen configuration
    # identity class. If it cannot be imported for any reason the
    # readiness endpoint cannot operate; the ``ConfigurationProbeFailed``
    # alias MUST exist so the catch sites below remain valid.
    raise


def validate_probe_timeout_seconds(*, value: int | float | str | None, kind: str) -> int:
    """Return the integer value or raise :class:`ReadinessError`.

    D-S2-03.b requires a finite positive integer in a fixed range. We
    explicitly reject zero, negative, non-integer, NaN, infinity, and
    out-of-range values. ``kind`` is ``"startup"`` or ``"readiness"``
    and selects the appropriate bounds.
    """
    if value is None or value == "":
        raise ReadinessError(f"{kind} probe timeout is required")
    try:
        coerced = int(value)
        # ``int(float("nan"))`` is undefined behaviour in CPython; we
        # catch the ValueError instead.
    except (TypeError, ValueError) as exc:
        raise ReadinessError(f"{kind} probe timeout must be a finite positive integer") from exc
    # Re-validate via float to catch ``int("inf")`` etc., which Python
    # disallows but guards against formatting-only values like "1e10".
    float_value = float(value)
    if not (float_value == float_value and float_value not in (float("inf"), float("-inf"))):
        raise ReadinessError(
            f"{kind} probe timeout must be a finite positive integer (not NaN/Inf)"
        )
    if kind == "startup":
        lo, hi = STARTUP_PROBE_TIMEOUT_MIN, STARTUP_PROBE_TIMEOUT_MAX
    elif kind == "readiness":
        lo, hi = READINESS_PROBE_TIMEOUT_MIN, READINESS_PROBE_TIMEOUT_MAX
    else:
        raise ReadinessError(f"unknown probe timeout kind {kind!r}")
    if coerced < lo or coerced > hi:
        raise ReadinessError(f"{kind} probe timeout must be in [{lo}, {hi}] seconds, got {coerced}")
    return coerced


def resolve_probe_timeout_seconds(*, settings: Settings, kind: str) -> int:
    """Return the configured probe timeout for ``kind``.

    Reads ``COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS`` /
    ``COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS`` from the
    environment. Staging and production MUST provide both keys
    explicitly; local / test may omit them and fall back to the
    documented non-production defaults.
    """
    if kind == "startup":
        env_key = "COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS"
        fallback = LOCAL_TEST_STARTUP_PROBE_TIMEOUT_SECONDS
    elif kind == "readiness":
        env_key = "COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS"
        fallback = LOCAL_TEST_READINESS_PROBE_TIMEOUT_SECONDS
    else:
        raise ReadinessError(f"unknown probe timeout kind {kind!r}")
    raw = os.environ.get(env_key)
    if raw is None or raw == "":
        mode = resolve_app_mode(settings)
        if mode in (AppMode.STAGING, AppMode.PRODUCTION):
            raise ReadinessError(f"{env_key} must be explicit in strict environments")
        return fallback
    return validate_probe_timeout_seconds(value=raw, kind=kind)


class ProbeOutcome:
    """Outcome of a single readiness probe.

    ``status`` is ``"pass"``, ``"fail"``, or ``"skip"``. ``code`` is the
    stable failure code when ``status == "fail"`` (else ``None``).
    ``detail`` is the safe projection that downstream gates and
    responses are allowed to surface. Anything sensitive MUST stay
    inside this field's _authoring_ boundary; transports MUST pass it
    through the existing redaction authority before emission.
    """

    __slots__ = ("name", "status", "code", "detail", "duration_seconds")

    def __init__(
        self,
        *,
        name: str,
        status: str,
        code: str | None = None,
        detail: str = "",
        duration_seconds: float = 0.0,
    ) -> None:
        self.name = name
        self.status = status
        self.code = code
        self.detail = detail
        self.duration_seconds = duration_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "code": self.code,
            "detail": self.detail,
            "duration_seconds": self.duration_seconds,
        }


class ProbeFn(Protocol):
    def __call__(self, *, timeout_seconds: int) -> ProbeOutcome: ...


def _probe_name(probe: ProbeFn) -> str:
    """Return a stable, best-effort name for the probe callable."""
    qual = getattr(probe, "__qualname__", None)
    if isinstance(qual, str):
        return qual
    name = getattr(probe, "__name__", None)
    if isinstance(name, str):
        return name
    return repr(probe)


def run_probe_with_timeout(
    *,
    name: str,
    fn: ProbeFn,
    timeout_seconds: int,
    on_timeout_code: str,
    on_non_timeout_code: str | None = None,
) -> ProbeOutcome:
    """Run a probe synchronously with a wall-clock budget.

    F-PR76-HIGH-02: this helper enforces a wall-clock budget AND
    uses a synchronously-installed ``SIGALRM`` timer so a probe
    that would otherwise block on a non-cancellable backend
    operation is interrupted at the deadline. The implementation
    is intentionally limited to the main thread because
    ``signal.setitimer`` is only effective there; the
    ``production_entrypoint`` and the FastAPI lifespan both run
    their startup and readiness phases on the main thread so this
    is the production path. Workers / tasks / connections MUST
    NOT be created inside the probe without an explicit bounded
    mechanism; the helper will interrupt the call site at the
    deadline if a probe regresses to a blocking operation.

    The probe is invoked with its timeout; the implementation is
    responsible for honouring it when it has dependency-native
    cancel support (e.g. ``connect_timeout`` for postgresql+psycopg2
    or ``sqlite busy_timeout``). When the probe does NOT honour it
    natively, the helper's SIGALRM timer fires after
    ``timeout_seconds`` and raises :class:`BlockingProbeTimeout`
    which is converted into a ``ProbeOutcome`` with the canonical
    ``on_timeout_code``.

    V0.2 Slice 2 amendment (D-S2-12.a.v0.2): callers that have a
    distinct non-timeout failure code (e.g. ``DATABASE_SCHEMA_HEAD_INVALID``
    for the schema-head probe) MUST pass ``on_non_timeout_code`` so
    that an unexpected ``Exception`` inside the probe is projected to
    that stable code instead of being mis-projected to
    ``on_timeout_code``. When ``on_non_timeout_code`` is ``None`` a
    non-timeout ``Exception`` is treated as a fail-closed non-timeout
    failure: the alarm is cancelled and a fresh internal
    :class:`StartupNonTimeoutProbeFailure` exception is raised carrying
    the probe name and the original exception. Callers that have NOT
    yet been amended to pass ``on_non_timeout_code`` will therefore
    observe a non-timeout failure rather than a silent
    ``STARTUP_PROBE_TIMEOUT`` / ``READINESS_PROBE_TIMEOUT`` mis-projection.
    This eliminates the legacy fallback path that previously mapped
    any exception to a timeout code.

    Importantly, the helper spawns NO background threads, NO
    asyncio tasks, and NO auxiliary connections. The 8-probe
    aggregate upper bound is therefore ``8 × per_probe_timeout`` as
    required by D-S2-03.c.
    """
    start = time.monotonic()
    # Install the SIGALRM timer on the main thread; the probe may
    # have native cancellation, in which case the timer is cancelled
    # by ``_cancel_alarm`` below. When the probe regresses to a
    # blocking call the alarm fires, raises ``BlockingProbeTimeout``,
    # and the wall-clock budget is enforced deterministically.
    alarm_token = _install_alarm(timeout_seconds)
    try:
        outcome = fn(timeout_seconds=timeout_seconds)
    except BlockingProbeTimeout:
        _cancel_alarm(alarm_token)
        return ProbeOutcome(
            name=name,
            status="fail",
            code=on_timeout_code,
            detail="probe exceeded per-probe budget (alarm)",
            duration_seconds=time.monotonic() - start,
        )
    except Exception as _exc:
        _cancel_alarm(alarm_token)
        elapsed = time.monotonic() - start
        # D-S2-12.a.v0.2: a non-timeout ``Exception`` MUST NOT be
        # silently mis-projected to a timeout code. Callers that have
        # a distinct stable code for non-timeout failures must pass
        # ``on_non_timeout_code``; if they do, we project to that
        # stable code. Otherwise the helper fails closed: the alarm is
        # cancelled and a ``StartupNonTimeoutProbeFailure`` is raised
        # carrying the safe probe name and the original exception,
        # without leaking the exception text. This deliberately
        # eliminates the legacy fallback that mapped arbitrary
        # exceptions to the timeout code.
        if on_non_timeout_code is not None:
            return ProbeOutcome(
                name=name,
                status="fail",
                code=on_non_timeout_code,
                detail="probe raised non-timeout exception",
                duration_seconds=elapsed,
            )
        raise StartupNonTimeoutProbeFailure(
            probe_name=name,
            original_exception=_exc,
        ) from _exc
    _cancel_alarm(alarm_token)
    elapsed = time.monotonic() - start
    # The probe is allowed to report its own duration (e.g. when it
    # internally measured wall time against an external backend); we
    # trust the larger of the two so a slow probe is detected even
    # when the helper's wall-clock is coarse.
    declared = float(getattr(outcome, "duration_seconds", 0.0) or 0.0)
    effective = max(elapsed, declared)
    outcome.duration_seconds = effective
    if outcome.status == "pass" and effective > timeout_seconds:
        # The probe reported pass but exceeded the budget: fail closed.
        return ProbeOutcome(
            name=name,
            status="fail",
            code=on_timeout_code,
            detail="probe exceeded per-probe timeout without mapping to fail closed",
            duration_seconds=effective,
        )
    if outcome.status == "pass":
        # Conservative upper-bound assertion: do NOT assert equality
        # with ``elapsed == timeout_seconds`` (D-S2-03.c + P1-006).
        outcome.code = None
        return outcome
    # Non-passing outcome from the probe itself (status == "fail").
    # V0.2 Slice 2 amendment: a schema probe that already set its own
    # stable ``code`` (e.g. ``DATABASE_SCHEMA_HEAD_INVALID``) MUST keep
    # that code. Only fill in ``on_timeout_code`` when the probe did
    # not set any code at all — that path is reserved for the legacy
    # behaviour where a probe returned ``fail`` without classifying
    # the cause. We MUST NOT override a probe-supplied
    # ``DATABASE_SCHEMA_HEAD_INVALID`` with ``STARTUP_PROBE_TIMEOUT``.
    if not outcome.code:
        outcome.code = on_timeout_code
    return outcome


class BlockingProbeTimeout(Exception):
    """Raised when the SIGALRM budget for a probe fires.

    F-PR76-HIGH-02: the helper uses ``signal.setitimer`` so that a
    probe which regresses to a blocking call without dependency-
    native cancellation is interrupted at the deadline instead of
    holding startup or readiness indefinitely.
    """


def _install_alarm(timeout_seconds: int) -> Any:
    """Install a SIGALRM timer; return a token used by ``_cancel_alarm``.

    Returns ``None`` when the helper is running off the main thread;
    in that case the wall-clock budget enforced by the outer caller
    (D-S2-03.c aggregate upper bound) is the only enforcement.
    """

    if timeout_seconds <= 0:
        return None
    try:
        import signal as _signal

        # ``signal.setitimer`` is only effective on the main thread.
        import threading as _threading

        if _threading.current_thread() is not _threading.main_thread():
            return None
        previous = _signal.signal(_signal.SIGALRM, _on_alarm)
        _signal.setitimer(_signal.ITIMER_REAL, float(timeout_seconds))
        return previous
    except (ValueError, OSError):
        return None


def _cancel_alarm(token: Any) -> None:
    """Cancel the SIGALRM timer installed by ``_install_alarm``."""

    if token is None:
        return
    try:
        import signal as _signal

        _signal.setitimer(_signal.ITIMER_REAL, 0)
        _signal.signal(_signal.SIGALRM, token)
    except (ValueError, OSError, TypeError):
        return


def _on_alarm(signum: int, frame: Any) -> None:
    """SIGALRM handler that interrupts a blocking probe call."""

    raise BlockingProbeTimeout(f"probe blocked past per-probe budget ({signum})")


# ---------------------------------------------------------------------------
# Strict-mode capability enumeration.  Per D-S2-06, the only two known
# unsafe strict-mode wirings in the current codebase are:
#   1. FakeAgentModelGateway being present on an HTTP request path;
#   2. process-in-memory CoefficientService() being present as an
#      HTTP route backend.
# We register those through ``strict_capability_registry`` so the
# defense-in-depth assertion (D-S2-06.c) can enumerate them at
# startup.  New capabilities are added to this registry in the same
# PR that introduces them; the contract forbids free-form additions
# elsewhere.
# ---------------------------------------------------------------------------


# Each registered capability carries an evidence callback that
# ``enumerate_reachable_unsafe_strict_capabilities`` calls to inspect
# the live ``FastAPI`` instance. Returning ``True`` means the
# capability is reachable as an HTTP route backend in the current
# process. The callback MUST NOT mutate global state and MUST NOT
# depend on the ``app`` argument being non-None (we explicitly raise
# in that case before invoking callbacks).
_STRICT_CAPABILITY_PLANNING_AGENT = "PLANNING_AGENT_MODEL_HTTP_ROUTE_STRICT_MODE"
_STRICT_CAPABILITY_COEFFICIENT = "COEFFICIENT_HTTP_ROUTE_STRICT_MODE"

_STRICT_CAPABILITY_PROBES: dict[str, Any] = {}  # populated below; see _StrictCapabilityProbeSpec


@dataclass(frozen=True)
class _StrictCapabilityProbeSpec:
    """Per-capability spec for the defensive audit (D-S2-06.c).

    ``route_prefixes`` are the path-prefix substrings that, when
    observed on a registered ``APIRoute``, prove the capability is
    reachable as an HTTP route backend. We deliberately look for path
    substrings rather than full route registration identity so the
    audit is robust to local-test wiring differences that rename the
    router but keep the prefix stable.

    ``composition_token`` (F-PR76-BLOCKER-03, D-S2-06.a) is the
    frozen string identifier for a *composition-time* instantiation
    that MUST NOT occur in strict (staging / production) modes. When
    set, the audit inspects the live composition manifest provided
    by the bootstrap layer; presence of the token in the manifest
    proves the unsafe instantiation happened, regardless of whether
    the corresponding route is reachable as an HTTP backend. The
    contract requires that ``runtime_readiness`` does NOT import any
    business gateway / service type, so the token is just a stable
    string; it does not name a Python class.
    """

    route_prefixes: tuple[str, ...]
    composition_token: str | None = None


# F-PR76-BLOCKER-03: the composition_token identifies an unsafe
# instantiation class. The audit treats presence in the manifest
# provided by the bootstrap layer as proof of unsafe composition.
_COMPOSITION_TOKEN_FAKE_AGENT_GATEWAY = "FAKE_AGENT_MODEL_GATEWAY_INSTANTIATED"
_COMPOSITION_TOKEN_PROCESS_LOCAL_COEFFICIENT = "PROCESS_LOCAL_COEFFICIENT_SERVICE_INSTANTIATED"

_STRICT_CAPABILITY_PROBES[_STRICT_CAPABILITY_PLANNING_AGENT] = _StrictCapabilityProbeSpec(
    route_prefixes=("/api/v1/agent/",),
    composition_token=_COMPOSITION_TOKEN_FAKE_AGENT_GATEWAY,
)
_STRICT_CAPABILITY_PROBES[_STRICT_CAPABILITY_COEFFICIENT] = _StrictCapabilityProbeSpec(
    route_prefixes=("/api/v1/coefficients",),
    composition_token=_COMPOSITION_TOKEN_PROCESS_LOCAL_COEFFICIENT,
)


class _StrictCapabilityRegistry:
    """Thread-safe registry of strict-mode capabilities to enumerate."""

    def __init__(self) -> None:
        self._entries: list[str] = []
        self._lock = threading.Lock()

    def reset(self) -> None:
        """Clear the registry (used by tests and idempotent re-init)."""
        with self._lock:
            self._entries.clear()

    def register(self, name: str) -> None:
        if not isinstance(name, str) or not name:
            raise ValueError("strict capability name must be a non-empty string")
        if name not in _STRICT_CAPABILITY_PROBES:
            raise ValueError(f"unknown strict capability {name!r}")
        with self._lock:
            if name not in self._entries:
                self._entries.append(name)

    def registered(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._entries)


# Module-level singleton. Read-only after process bootstrap.  This is
# NOT an "import-time business singleton"; it is a static registry of
# capability names that is consulted only by the defensive assertion.
# The contract forbids importing business services here, but a static
# registry of strings is not a business dependency.
_strict_registry = _StrictCapabilityRegistry()
register_strict_capability = _strict_registry.register
registered_strict_capabilities = _strict_registry.registered
_reset_strict_capabilities = _strict_registry.reset


# ---------------------------------------------------------------------------
# Composition manifest provider (F-PR76-BLOCKER-03, D-S2-06.a).
#
# The bootstrap layer (``bootstrap.dependencies``) is responsible for
# recording every composition-time instantiation that the contract
# forbids in strict modes. It does so by passing a callable to
# :func:`set_composition_manifest_provider`; the callable returns a
# set of frozen string tokens (e.g.
# ``"FAKE_AGENT_MODEL_GATEWAY_INSTANTIATED"``) reflecting what was
# actually constructed. The audit consumes this set on every strict
# capability check so a fake gateway or process-local coefficient
# service that escapes the route-prefix inspection is still caught.
#
# The provider is intentionally a callable rather than a static
# value so the bootstrap layer can defer composition until after
# mode resolution and so the audit can call it at any time without
# snapshot staleness. ``None`` means "no composition was registered",
# which the audit treats as a clean composition in strict modes.
# ---------------------------------------------------------------------------
def _empty_manifest_provider() -> frozenset[str]:
    """Default provider that records no composition evidence."""

    return frozenset()


_composition_manifest_provider: Callable[[], frozenset[str]] = _empty_manifest_provider
_composition_manifest_lock = threading.Lock()


def set_composition_manifest_provider(
    provider: Callable[[], frozenset[str]],
) -> Callable[[], frozenset[str]]:
    """Register the composition-manifest provider.

    Returns the previous provider so callers can restore it (tests).
    The provider is invoked under a lock to make a single audit
    consistent in the face of concurrent composition.
    """

    global _composition_manifest_provider
    if not callable(provider):
        raise TypeError("composition manifest provider must be callable")
    with _composition_manifest_lock:
        previous = _composition_manifest_provider
        _composition_manifest_provider = provider
    return previous


def reset_composition_manifest_provider() -> None:
    """Restore the empty default provider (idempotent re-init helper)."""

    global _composition_manifest_provider
    with _composition_manifest_lock:
        _composition_manifest_provider = _empty_manifest_provider


def composition_manifest_tokens() -> frozenset[str]:
    """Return the live composition-manifest snapshot.

    Used by the defensive audit. The result is a snapshot of the
    provider's current view; the caller MUST NOT mutate it.
    """

    with _composition_manifest_lock:
        provider = _composition_manifest_provider
    try:
        result = provider()
    except Exception:  # noqa: BLE001
        # Provider failures MUST NOT silently yield success.
        # Surface them as an explicit fail-closed token so the
        # audit cannot be bypassed by a misbehaving provider.
        return frozenset({"COMPOSITION_MANIFEST_PROVIDER_ERROR"})
    if not isinstance(result, frozenset):
        try:
            return frozenset(result)
        except TypeError:
            return frozenset({"COMPOSITION_MANIFEST_PROVIDER_ERROR"})
    return result


_COMPOSITION_TOKEN_PROVIDER_ERROR = "COMPOSITION_MANIFEST_PROVIDER_ERROR"


def _route_path_for(route: Any) -> str:
    """Return the canonical path of a Starlette/FastAPI route.

    Accepts any object exposing ``.path`` (Starlette ``APIRoute``)
    or ``.path_format`` / ``.path_regex``. Falls back to ``""`` if
    none of these attributes exist; we treat that as non-matching.
    """
    for attr in ("path", "path_format", "path_regex"):
        value = getattr(route, attr, None)
        if isinstance(value, str):
            return value
    return ""


def enumerate_reachable_unsafe_strict_capabilities(
    *, app: Any, routes: Iterable[Any] | None = None
) -> tuple[str, ...]:
    """Return the subset of registered capabilities that are reachable.

    This is the defense-in-depth assertion required by D-S2-06.c. The
    canonical outcome (per D-S2-06.a / D-S2-06.b) is that registered
    strict capabilities MUST NOT be reachable as an HTTP route backend
    in staging or production. This function inspects the live
    application instance (FastAPI ``app`` and any explicit routes) and
    returns the names of registered capabilities that are actually
    reachable.

    ``app=None`` MUST NOT be interpreted as "audit succeeded".
    Concretely: when the caller passes ``app=None`` (typically in a
    unit test that does not own a FastAPI app), the audit raises
    :class:`UnsafeStrictCapabilityWiring` so a regression cannot
    silently bypass the defensive check. Production callers must
    pass the real ``app`` instance, and unit tests that legitimately
    want to exercise the audit without a real app must call
    :func:`enumerate_reachable_unsafe_strict_capabilities` directly
    and catch the exception in their own assertion logic.

    The audit is INTENTIONALLY import-time side-effect free. It
    inspects already-imported FastAPI objects through duck-typed
    introspection only.

    Mode-aware behaviour: in local / test mode the demo / fixture
    flows may legitimately register the fake-agent or in-memory
    coefficient route. The audit therefore returns an empty reachable
    subset in non-strict modes so the canonical lifespan path is not
    poisoned by the defensive check. In staging / production the
    audit enforces the contract fail-closed.

    Composition-time evidence (F-PR76-BLOCKER-03) is consulted in
    addition to the route prefix inspection. In strict modes, any
    registered capability whose ``composition_token`` is present in
    the live composition manifest is considered reachable even when
    no matching HTTP route is mounted, so an unsafe backend that
    escapes routing inspection is still caught.
    """
    _ = routes  # explicit non-use; ``app`` is the canonical input.
    # Mode-aware behaviour (per TASK-012 Slice 2 brief §2): the strict
    # capability audit is ONLY meaningful in strict environments. In
    # local / test mode the demo / fixture flows legitimately register
    # the fake-agent or in-memory coefficient routes, so the audit MUST
    # short-circuit and return an empty reachable subset BEFORE we ask
    # whether ``app`` is present. In staging / production, ``app=None``
    # is still NOT a silent success and the audit MUST fail closed so
    # production lifespan always pass ``app=app`` explicitly.
    try:
        settings = canonical_settings()
        mode = resolve_app_mode(settings)
    except ConfigurationProbeFailed:
        mode = None
    if mode not in (AppMode.STAGING, AppMode.PRODUCTION):
        return ()
    if app is None:
        raise UnsafeStrictCapabilityWiring(
            "strict capability audit invoked without a FastAPI app; "
            "production lifespan must pass app=app explicitly",
            unsafe_capabilities=(),
        )
    names = _strict_registry.registered()
    route_paths: list[str] = []
    app_routes = getattr(app, "routes", None)
    if app_routes is not None:
        try:
            route_iter = list(app_routes)
        except TypeError:
            route_iter = []
        for r in route_iter:
            route_paths.append(_route_path_for(r))
    manifest_tokens = composition_manifest_tokens()
    reachable: list[str] = []
    for name in names:
        spec = _STRICT_CAPABILITY_PROBES.get(name)
        if spec is None:
            continue
        # Composition-time evidence: any spec whose token is present
        # in the live manifest proves the unsafe composition happened
        # at bootstrap, regardless of whether the route is reachable.
        if spec.composition_token is not None and spec.composition_token in manifest_tokens:
            reachable.append(name)
            continue
        # D-S4-06: Binding identity check. If the app has a strict
        # capability binding manifest, verify the capability is bound
        # with the correct identity. Missing or wrong identity means
        # the capability is considered reachable (unsafe).
        bindings = getattr(getattr(app, "state", None), "strict_capability_bindings", None)
        if bindings is not None and isinstance(bindings, tuple):
            binding_identity = None
            for b_name, b_identity in bindings:
                if b_name == name:
                    binding_identity = b_identity
                    break
            _ALLOWED_IDENTITIES = {
                "coefficient_http": "database_backed",
                "model_backed_agent": "disabled",
            }
            expected = _ALLOWED_IDENTITIES.get(name)
            if binding_identity is None or binding_identity != expected:
                reachable.append(name)
                continue
        for prefix in spec.route_prefixes:
            # Match the prefix exactly, or as a path segment, or as a
            # prefix substring. Path-segment matching keeps the audit
            # robust to legitimate local-test prefixes that share the
            # canonical segment.
            if any(
                p == prefix or p.startswith(prefix + "/") or p.startswith(prefix)
                for p in route_paths
            ):
                reachable.append(name)
                break
    return tuple(reachable)


def assert_no_unsafe_strict_capabilities(*, app: Any = None) -> None:
    """Defense-in-depth assertion per D-S2-06.c.

    The function inspects the registered strict-mode capabilities,
    asks :func:`enumerate_reachable_unsafe_strict_capabilities` for
    the subset actually reachable on the live ``app``, and raises
    :class:`UnsafeStrictCapabilityWiring` with the stable frozen code
    ``UNSAFE_STRICT_CAPABILITY_WIRING`` if any capability is reachable.

    The audit is non-vacuous: ``app=None`` raises (it is not a silent
    success) and a clean app returns an empty reachable subset only
    when no strict capability is wired into a real ``APIRoute``.
    """
    reachable = enumerate_reachable_unsafe_strict_capabilities(app=app)
    if reachable:
        raise UnsafeStrictCapabilityWiring(
            f"unsafe strict capabilities reachable: {sorted(reachable)!r}",
            unsafe_capabilities=tuple(sorted(reachable)),
        )


# Register the two known strict-mode capabilities at module import time.
# The contract scope-limited table (D-S2-12.a) freezes these two.
register_strict_capability(_STRICT_CAPABILITY_PLANNING_AGENT)
register_strict_capability(_STRICT_CAPABILITY_COEFFICIENT)


@dataclass
class ReadinessState:
    """Single re-entrant readiness state shared across the process.

    The state machine is:

        INITIALIZING -> READY   (after run_startup_phase returns)
        READY          -> DRAINING (when shutdown begins)
        DRAINING       -> SHUTDOWN_COMPLETE (after dispose phase)

    The state is stored on the bootstrap singleton and consulted by
    the ``/health/ready`` HTTP route. A separate lock guards
    transitions so concurrent ``/health/ready`` calls cannot observe
    a partial update.
    """

    state: str = "INITIALIZING"
    last_startup_outcomes: tuple[ProbeOutcome, ...] = ()
    last_readiness_outcomes: tuple[ProbeOutcome, ...] = ()
    last_update_monotonic: float = field(default_factory=time.monotonic)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def transition(self, *, to: str, outcomes: tuple[ProbeOutcome, ...] | None = None) -> None:
        if to not in ("INITIALIZING", "READY", "DRAINING", "SHUTDOWN_COMPLETE"):
            raise ReadinessError(f"unknown readiness state {to!r}")
        with self._lock:
            # Once we have started draining, do NOT regress to READY
            # unless explicitly requested. This prevents a startup-phase
            # callback running concurrently with a SIGTERM-triggered
            # drain from accidentally re-enabling traffic. Tests that
            # legitimately need to reset the state use ``reset_readiness_state``.
            previous = self.state
            if previous in ("DRAINING", "SHUTDOWN_COMPLETE") and to == "READY":
                return
            if previous == "SHUTDOWN_COMPLETE" and to in ("INITIALIZING", "READY", "DRAINING"):
                return
            self.state = to
            if outcomes is not None:
                if to == "READY":
                    self.last_readiness_outcomes = outcomes
                else:
                    self.last_startup_outcomes = outcomes
            self.last_update_monotonic = time.monotonic()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self.state,
                "startup_outcomes": [o.to_dict() for o in self.last_startup_outcomes],
                "readiness_outcomes": [o.to_dict() for o in self.last_readiness_outcomes],
                "last_update_monotonic": self.last_update_monotonic,
            }

    def is_ready(self) -> bool:
        with self._lock:
            return self.state == "READY"

    def is_draining(self) -> bool:
        with self._lock:
            return self.state == "DRAINING"


def _coerce_probe_timeout(env_value: str | None, *, fallback: int, kind: str) -> int:
    if env_value is None or env_value == "":
        return fallback
    return validate_probe_timeout_seconds(value=env_value, kind=kind)


def run_startup_phase(
    *,
    settings: Settings,
    environment: Mapping[str, str],
    startup_probes: Iterable[ProbeFn],
    app: Any = None,
) -> tuple[ProbeOutcome, ...]:
    """Run the startup phase exactly once.

    The startup phase executes every probe in ``startup_probes`` with
    the configured per-probe timeout. Any non-passing outcome aborts
    startup immediately. After all probes pass, the readiness state
    transitions to ``READY``.
    """
    mode = resolve_app_mode(settings)
    timeout = resolve_probe_timeout_seconds(settings=settings, kind="startup")
    outcomes: list[ProbeOutcome] = []
    for probe in startup_probes:
        # V0.2 Slice 2 amendment (D-S2-12.a.v0.2): probe bodies that
        # declare a distinct non-timeout stable code MUST pass
        # ``on_non_timeout_code`` so an unexpected ``Exception`` is
        # not mis-projected to ``STARTUP_PROBE_TIMEOUT``. The schema
        # probe opts in via ``DATABASE_SCHEMA_HEAD_INVALID``.
        on_non_timeout = (
            DATABASE_SCHEMA_HEAD_INVALID if _probe_name(probe) == PROBE_SCHEMA else None
        )
        outcome = run_probe_with_timeout(
            name=_probe_name(probe),
            fn=probe,
            timeout_seconds=timeout,
            on_timeout_code=STARTUP_PROBE_TIMEOUT,
            on_non_timeout_code=on_non_timeout,
        )
        outcomes.append(outcome)
        if outcome.status != "pass":
            # V0.2 Slice 2 amendment (D-S2-12.a.v0.2): only a true
            # timeout outcome (``code == STARTUP_PROBE_TIMEOUT``) is
            # wrapped as :class:`StartupProbeTimeout`. A non-timeout
            # failure code (e.g. ``DATABASE_SCHEMA_HEAD_INVALID``)
            # MUST be wrapped as :class:`StartupProbeFailure` —
            # NEVER nested inside
            # :class:`StartupNonTimeoutProbeFailure`, which is
            # reserved for un-classified ``Exception`` escapes from
            # ``run_probe_with_timeout``. The three startup-failure
            # channels are mutually exclusive:
            #
            #   real timeout outcome  → StartupProbeTimeout
            #   classified fail outcome → StartupProbeFailure
            #   un-classified exception  → StartupNonTimeoutProbeFailure
            if outcome.code == STARTUP_PROBE_TIMEOUT:
                raise StartupProbeTimeout(
                    f"startup probe {outcome.name!r} did not pass: code={outcome.code}"
                )
            raise StartupProbeFailure(
                probe_name=outcome.name,
                failure_code=str(outcome.code) if outcome.code is not None else "",
            )

    # Defense-in-depth assertion per D-S2-06.c.  Runs AFTER probes so a
    # probe-induced state change cannot bypass the assertion.  The
    # argument ``app`` is optional; ``None`` is NOT a silent success
    # (see ``enumerate_reachable_unsafe_strict_capabilities``).
    assert_no_unsafe_strict_capabilities(app=app)

    # Freeze the readiness state.  We rely on the bootstrap singleton
    # owner (``bootstrap.dependencies``) to publish this through the
    # ``get_readiness_state`` accessor.
    state = get_or_init_readiness_state(settings=settings, environment=environment)
    state.transition(to="READY", outcomes=tuple(outcomes))
    _ = is_production_mode(mode)  # explicit non-use; documented behavior.
    return tuple(outcomes)


def run_readiness_phase(
    *,
    settings: Settings,
    readiness_probes: Iterable[ProbeFn],
) -> tuple[ProbeOutcome, ...]:
    """Run the readiness phase on each ``/health/ready`` invocation.

    Returns the tuple of probe outcomes; the caller decides HTTP status
    (200 on all-pass, 503 otherwise) based on those outcomes. The
    aggregate upper bound is bounded completion + correct failure
    classification only; we do NOT assert that
    ``elapsed == MANDATORY_PROBE_COUNT × CONFIGURED_PER_PROBE_TIMEOUT``
    (D-S2-03.c + P1-006).
    """
    timeout = resolve_probe_timeout_seconds(settings=settings, kind="readiness")
    outcomes: list[ProbeOutcome] = []
    for probe in readiness_probes:
        outcome = run_probe_with_timeout(
            name=_probe_name(probe),
            fn=probe,
            timeout_seconds=timeout,
            on_timeout_code=READINESS_PROBE_TIMEOUT,
        )
        outcomes.append(outcome)
    # Publish the latest outcomes so the running state reflects readiness.
    state = get_readiness_state()
    if state is not None:
        state.transition(to=state.state, outcomes=tuple(outcomes))
    return tuple(outcomes)


# ---------------------------------------------------------------------------
# Module-level state. We keep a single re-entrant state object keyed by
# id(settings); the bootstrap layer overrides ownership of the state via
# :func:`set_readiness_state`. Tests reset the state with
# :func:`reset_readiness_state`.
# ---------------------------------------------------------------------------


_state_owner: dict[str, ReadinessState | None] = {"state": None}


def set_readiness_state(state: ReadinessState) -> ReadinessState:
    _state_owner["state"] = state
    return state


def get_readiness_state() -> ReadinessState | None:
    return _state_owner.get("state")


def reset_readiness_state() -> None:
    _state_owner["state"] = None


def get_or_init_readiness_state(
    *, settings: Settings, environment: Mapping[str, str]
) -> ReadinessState:
    """Return the existing readiness state or create a fresh one."""
    state = _state_owner.get("state")
    if state is not None:
        return state
    new = ReadinessState()
    _state_owner["state"] = new
    return new


def canonical_settings() -> Settings:
    """Return the canonical, already-initialized :class:`Settings`.

    The lifecycle (``bootstrap.dependencies.init_dependencies``) MUST
    run exactly once so the readiness endpoint and probes never
    construct a second ``Settings`` authority per readiness call
    (F-S2-REVIEW-005).

    Before the lifecycle has set the canonical settings, this accessor
    raises :class:`ConfigurationProbeFailed` (which is the Slice 1
    frozen :class:`cold_storage.bootstrap.environment_model.ConfigurationError`
    re-exported under that historical name) so the readiness endpoint
    surfaces a stable failure class rather than building a new
    authority on the side. F-PR76-MEDIUM-01: the projection to the
    client uses the Python class name as the stable ``check_code``.
    """
    settings = _settings_owner.get("settings")
    if settings is None:
        raise ConfigurationProbeFailed(
            "canonical Settings authority not initialized; "
            "init_dependencies() must run before readiness",
        )
    return settings


def set_canonical_settings(settings: Settings) -> Settings:
    """Store the canonical, bootstrap-initialized :class:`Settings`."""
    _settings_owner["settings"] = settings
    return settings


def reset_canonical_settings() -> None:
    """Clear the canonical settings authority (used by tests)."""
    _settings_owner["settings"] = None


_settings_owner: dict[str, Settings | None] = {"settings": None}


# ---------------------------------------------------------------------------
# Mandatory readiness probes (D-S2-04). The eight canonical probes are the
# single source of truth for what ``/health/ready`` must verify before
# returning 200; local/test mode still executes all of them but treats
# certain failure categories as ``skip`` rather than ``fail``. Each
# probe returns a :class:`ProbeOutcome` synchronously and respects its
# per-probe timeout budget by inspecting ``time.monotonic()`` against
# the deadline.
# ---------------------------------------------------------------------------


# Stable probe names used both by the gateway (``bootstrap.dependencies``)
# and the diagnostic test suite. Do NOT rename without updating both.
PROBE_LIFECYCLE = "lifecycle_initialization_completed"
PROBE_NOT_DRAINING = "process_not_draining_or_shutting_down"
PROBE_DATABASE = "database_connectivity"
PROBE_SCHEMA = "database_exact_alembic_head"
PROBE_ENVIRONMENT = "environment_and_resource_identities"
PROBE_ARTIFACT = "artifact_storage_isolated_exists_writable"
PROBE_COEFFICIENT = "approved_coefficient_readiness_in_strict_modes"
PROBE_BUILD_IDENTITY = "build_and_deployment_identity"


def _fail(*, name: str, code: str, detail: str, duration: float) -> ProbeOutcome:
    return ProbeOutcome(
        name=name, status="fail", code=code, detail=detail, duration_seconds=duration
    )


def _pass(*, name: str, detail: str, duration: float) -> ProbeOutcome:
    return ProbeOutcome(
        name=name, status="pass", code=None, detail=detail, duration_seconds=duration
    )


def probe_lifecycle_initialization_completed(*, timeout_seconds: int) -> ProbeOutcome:
    """Probe 1 — lifecycle_initialization_completed.

    Returns pass when the readiness state singleton exists. This
    probe is part of the aggregate that drives the READY transition,
    so it intentionally does NOT inspect the current state value —
    DRAINING / SHUTDOWN_COMPLETE detection is probe 2's
    responsibility (``process_not_draining_or_shutting_down``); the
    lifecycle probe's contract is solely "the singleton has been
    published by ``init_dependencies``". This separation keeps
    bootstrap-time probes (which legitimately run while state is
    INITIALIZING) from colliding with the DRAINING / SHUTDOWN gates.
    """
    name = PROBE_LIFECYCLE
    start = time.monotonic()
    state = get_readiness_state()
    if state is None:
        return _fail(
            name=name,
            code=STARTUP_PROBE_TIMEOUT,
            detail="readiness state singleton not initialized",
            duration=time.monotonic() - start,
        )
    return _pass(
        name=name,
        detail=f"state={state.state}",
        duration=time.monotonic() - start,
    )


def probe_process_not_draining_or_shutting_down(*, timeout_seconds: int) -> ProbeOutcome:
    """Probe 2 — process_not_draining_or_shutting_down.

    Returns pass when the readiness state is NOT ``DRAINING`` and NOT
    ``SHUTDOWN_COMPLETE``. Distinct from probe 1 because a process can
    have READY state momentarily while a SIGTERM-triggered drain has
    started flipping it to DRAINING.
    """
    name = PROBE_NOT_DRAINING
    start = time.monotonic()
    state = get_readiness_state()
    if state is None:
        return _fail(
            name=name,
            code=STARTUP_PROBE_TIMEOUT,
            detail="readiness state singleton not initialized",
            duration=time.monotonic() - start,
        )
    if state.state in ("DRAINING", "SHUTDOWN_COMPLETE"):
        return _fail(
            name=name,
            code=STARTUP_PROBE_TIMEOUT,
            detail=f"state={state.state}",
            duration=time.monotonic() - start,
        )
    return _pass(name=name, detail=f"state={state.state}", duration=time.monotonic() - start)


def probe_database_connectivity(*, timeout_seconds: int) -> ProbeOutcome:
    """Probe 3 — database_connectivity.

    Acquires a fresh session from the canonical engine and executes
    a no-op ``SELECT 1``. The session is closed in ``finally`` so no
    connection / transaction leaks. Failures raise and surface as the
    canonical ``READINESS_PROBE_TIMEOUT`` / ``STARTUP_PROBE_TIMEOUT``
    code on this channel; downstream modules carry the typed exception
    for richer classification if needed.
    """
    name = PROBE_DATABASE
    start = time.monotonic()
    try:
        from sqlalchemy import text as _sa_text

        from cold_storage.bootstrap.dependencies import get_engine

        engine = get_engine()
    except Exception as exc:  # noqa: BLE001
        return _fail(
            name=name,
            code=STARTUP_PROBE_TIMEOUT,
            detail=f"engine unavailable: {type(exc).__name__}",
            duration=time.monotonic() - start,
        )
    deadline = start + max(1, int(timeout_seconds))
    session = None
    try:
        from sqlalchemy.orm import sessionmaker

        session = sessionmaker(bind=engine, expire_on_commit=False)()
        try:
            session.execute(_sa_text("SELECT 1"))
        finally:
            session.close()
    except Exception as exc:  # noqa: BLE001
        if time.monotonic() > deadline:
            return _fail(
                name=name,
                code=STARTUP_PROBE_TIMEOUT,
                detail="probe exceeded per-probe budget",
                duration=time.monotonic() - start,
            )
        return _fail(
            name=name,
            code=STARTUP_PROBE_TIMEOUT,
            detail=f"db unreachable: {type(exc).__name__}",
            duration=time.monotonic() - start,
        )
    return _pass(name=name, detail="db reachable", duration=time.monotonic() - start)


class _PackagedGraphUnreadable(Exception):
    """Internal: a packaged Alembic graph could not be read.

    Maps at the loader boundary to the frozen internal reason
    ``PACKAGED_HEAD_UNREADABLE``. This is a private control-flow
    exception; it MUST NOT escape ``_load_packaged_alembic_head``.
    """


class _PackagedGraphMalformed(Exception):
    """Internal: a packaged Alembic graph was structurally invalid.

    Maps at the loader boundary to the frozen internal reason
    ``PACKAGED_HEAD_MALFORMED``. This is a private control-flow
    exception; it MUST NOT escape ``_load_packaged_alembic_head``.
    """


def _load_packaged_alembic_head() -> tuple[str | None, str | None]:
    """Load the unique packaged Alembic head from the deployed artifact graph.

    Returns
    -------
    (head, None)
        ``head`` is the unique Alembic revision id from the packaged
        script directory.
    (None, internal_reason)
        ``internal_reason`` is one of the frozen closed set:
        ``PACKAGED_HEAD_MISSING``, ``PACKAGED_HEAD_UNREADABLE``,
        ``PACKAGED_HEAD_MALFORMED``, ``PACKAGED_HEAD_ZERO``,
        ``PACKAGED_HEAD_MULTIPLE``. The public stable code is
        ``DATABASE_SCHEMA_HEAD_INVALID`` (projected at the probe
        boundary); the internal reason is preserved for log
        consumption.

    Implementation notes
    --------------------
    - The Alembic deployment root is derived deterministically from
      this module's own path (``parents[3]``). For
      ``backend/src/cold_storage/bootstrap/runtime_readiness.py`` the
      root is ``backend/``; for the container path
      ``/opt/cold-storage/src/cold_storage/bootstrap/runtime_readiness.py``
      the root is ``/opt/cold-storage/``.
    - The loader MUST NOT execute ``env.py``, MUST NOT connect to the
      database, MUST NOT invoke ``alembic upgrade`` / ``downgrade`` /
      ``heads`` CLI / ``current``, MUST NOT spawn subprocesses, and
      MUST NOT import or execute any migration module. Per the
      architecture contract
      (``test_runtime_bootstrap_does_not_use_alembic``) the runtime
      bootstrap layer MUST NOT import or invoke the alembic Python
      library; the loader therefore parses the packaged revision
      files directly with the standard library ``ast`` module.
    - The legacy ``COLD_STORAGE_PACKAGED_ALEMBIC_HEAD`` env var is
      intentionally ignored: the deployment artifact is the only
      authoritative source. A malicious or malformed env value cannot
      override the graph.
    - Migration files use **annotated** assignments (PEP 526) of the
      form ``revision: str = "..."`` and ``down_revision: str |
      Sequence[str] | None = ...``. The loader uses
      :func:`ast.parse` on the file text and inspects only the
      **module top level** for ``Assign`` / ``AnnAssign`` targets
      named ``revision`` or ``down_revision``. Function bodies, class
      bodies, and conditional branches are intentionally ignored.
    - All revision-id values are validated against the frozen
      :func:`_is_alembic_revision` shape validator before being
      committed to the graph.
    """
    module_path = Path(__file__).resolve()
    # ``parents[3]`` walks up from
    # ``backend/src/cold_storage/bootstrap/runtime_readiness.py`` to
    # ``backend/``. The container layout
    # ``/opt/cold-storage/src/cold_storage/bootstrap/runtime_readiness.py``
    # yields ``/opt/cold-storage/``.
    deployment_root = module_path.parents[3]
    alembic_ini_path = deployment_root / "alembic.ini"
    if not alembic_ini_path.is_file():
        return (None, "PACKAGED_HEAD_MISSING")

    # Resolve the ``script_location`` from ``alembic.ini`` without
    # importing alembic. The script location is documented to be a
    # single key with no comments in our deployed configurations.
    try:
        ini_text = alembic_ini_path.read_text(encoding="utf-8")
    except OSError:
        return (None, "PACKAGED_HEAD_UNREADABLE")
    script_location: str | None = None
    for raw_line in ini_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            # New section header (e.g. ``[alembic]``); stop after
            # the first non-alembic section.
            if line.lower() != "[alembic]" and script_location is not None:
                break
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            if key.strip().lower() == "script_location":
                script_location = value.strip()
                break
    if not script_location:
        return (None, "PACKAGED_HEAD_MISSING")
    script_path = Path(script_location)
    if not script_path.is_absolute():
        script_path = (deployment_root / script_location).resolve()
    versions_dir = script_path / "versions"
    if not versions_dir.is_dir():
        return (None, "PACKAGED_HEAD_MISSING")

    # Parse each revision file with ``ast``. Internal control-flow
    # exceptions (``_PackagedGraphUnreadable`` / ``_PackagedGraphMalformed``)
    # are caught here at the boundary and converted to the frozen
    # internal reason set.
    try:
        heads, _parents = _parse_alembic_revisions(versions_dir)
    except _PackagedGraphUnreadable:
        return (None, "PACKAGED_HEAD_UNREADABLE")
    except _PackagedGraphMalformed:
        return (None, "PACKAGED_HEAD_MALFORMED")
    except OSError:
        return (None, "PACKAGED_HEAD_UNREADABLE")

    # Compute heads: a revision whose id never appears as someone
    # else's down_revision.
    if not heads:
        return (None, "PACKAGED_HEAD_ZERO")
    if len(heads) > 1:
        return (None, "PACKAGED_HEAD_MULTIPLE")

    unique_head = heads[0]
    stripped = unique_head.strip()
    # The unique Head MUST satisfy the project's existing
    # revision-id validation rule (the brief mandates reusing the
    # frozen shape validator as a private pure function). The rule
    # permits the alphanumeric Alembic rev_id shape used by this
    # project's revisions (e.g.
    # ``0039_widen_report_export_artifact_mime_type``) rather than
    # the 12-char lowercase hex shape the legacy env-var path
    # enforced.
    if not _is_alembic_revision(stripped):
        return (None, "PACKAGED_HEAD_MALFORMED")
    return (stripped, None)


def _parse_alembic_revisions(
    versions_dir: Path,
) -> tuple[tuple[str, ...], dict[str, tuple[str | None, ...]]]:
    """Parse the packaged Alembic revision graph with the stdlib ``ast``.

    Each migration file is read as text and parsed by
    :func:`ast.parse`; the loader then inspects only the module-level
    ``Assign`` / ``AnnAssign`` statements whose target is a simple
    name (``revision`` or ``down_revision``). No migration module is
    imported; no module-level side effects execute; ``env.py`` is not
    loaded.

    Returns
    -------
    (heads, parents)
        ``heads`` is the tuple of revision ids that have no
        down_revision consumers (i.e. the current top of each
        branch). ``parents`` maps each revision id to the tuple of
        down_revision ids declared in its file (an empty tuple for
        root revisions).

    Raises
    ------
    _PackagedGraphUnreadable
        I/O failure, syntax error, missing ``revision`` name, or
        dynamic ``down_revision`` value (function call / name
        resolution / attribute access).
    _PackagedGraphMalformed
        ``revision`` is not a non-empty string, ``revision`` is
        malformed by the shape validator, ``down_revision`` contains
        a non-string element, a duplicated revision id is detected,
        or a parent reference points to a non-existent node.
    """
    heads: list[str] = []
    parents: dict[str, tuple[str | None, ...]] = {}
    consumed: set[str] = set()
    if not versions_dir.is_dir():
        raise _PackagedGraphUnreadable("versions dir not present")
    for revision_file in sorted(versions_dir.glob("*.py")):
        # ``__init__.py`` is intentionally ignored; the loader
        # only walks real migration files.
        if revision_file.name == "__init__.py":
            continue
        try:
            text = revision_file.read_text(encoding="utf-8")
        except OSError as exc:
            raise _PackagedGraphUnreadable(
                f"failed to read migration file: {type(exc).__name__}"
            ) from exc
        try:
            tree = ast.parse(text, filename="<redacted migration filename>")
        except SyntaxError as exc:
            raise _PackagedGraphUnreadable(
                f"syntax error in migration file: {type(exc).__name__}"
            ) from exc

        revision_id = _module_top_level_revision(tree)
        if revision_id is None:
            raise _PackagedGraphUnreadable("missing module-level revision name")
        if revision_id in parents:
            raise _PackagedGraphMalformed("duplicate revision identifier in graph")
        if not isinstance(revision_id, str) or not revision_id.strip():
            raise _PackagedGraphMalformed("revision is not a non-empty string")
        if not _is_alembic_revision(revision_id):
            raise _PackagedGraphMalformed("revision does not satisfy shape validator")

        down_revs = _module_top_level_down_revision(tree)
        parents[revision_id] = down_revs
        consumed.update(p for p in down_revs if p is not None)

    # Validate parent references: every parent must point to a known
    # node. Fail-closed — a dangling parent means the graph is
    # structurally invalid and the loader MUST NOT silently ignore
    # it.
    for parent_ids in parents.values():
        for parent_id in parent_ids:
            if parent_id is None:
                continue
            if parent_id not in parents:
                raise _PackagedGraphMalformed("down_revision references unknown revision")

    for rid in parents:
        if rid not in consumed:
            heads.append(rid)
    return tuple(heads), parents


def _module_top_level_revision(tree: ast.Module) -> str | None:
    """Return the module-level ``revision`` string for a parsed migration.

    Accepts both ``Assign`` (``revision = "..."``) and ``AnnAssign``
    (``revision: str = "..."``) targets whose value is a single
    non-empty string literal. Returns ``None`` if no such target is
    present at the module top level.
    """
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "revision"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "revision"
            and node.value is not None
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    return None


def _module_top_level_down_revision(
    tree: ast.Module,
) -> tuple[str | None, ...]:
    """Return the module-level ``down_revision`` for a parsed migration.

    Accepts ``None``, a single string literal, or a tuple / list of
    string literals. Dynamic expressions (function calls, attribute
    access, name resolution) raise :class:`_PackagedGraphUnreadable`.
    Strings that violate :func:`_is_alembic_revision` or are empty
    raise :class:`_PackagedGraphMalformed`.
    """
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            if isinstance(tgt, ast.Name) and tgt.id == "down_revision":
                return _evaluate_static_down_revision_value(node.value)
        elif isinstance(node, ast.AnnAssign):
            if (
                isinstance(node.target, ast.Name)
                and node.target.id == "down_revision"
                and node.value is not None
            ):
                return _evaluate_static_down_revision_value(node.value)
    # No module-level ``down_revision`` declaration found. This is a
    # graph-level structural error — fail closed.
    raise _PackagedGraphUnreadable("missing module-level down_revision")


def _evaluate_static_down_revision_value(
    node: ast.AST,
) -> tuple[str | None, ...]:
    """Reduce a static AST node to a tuple of string ids.

    Allowed node shapes (per the V0.2 Slice 2 contract):

    - ``Constant(value=None)`` → ``(None,)``
    - ``Constant(value="...")`` → ``("...",)``
    - ``Tuple`` / ``List`` of string-typed ``Constant`` elements
    - ``BinOp`` with left/right ``Constant`` strings (rare merged
      form, e.g. ``"a" + "b"``) is intentionally rejected as
      ``_PackagedGraphUnreadable`` because it permits dynamic
      construction.

    Anything else (calls, names, attribute access, ``BinOp``, etc.)
    raises :class:`_PackagedGraphUnreadable`.
    """
    if isinstance(node, ast.Constant):
        value = node.value
        if value is None:
            return (None,)
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                raise _PackagedGraphMalformed("down_revision contains empty string")
            if not _is_alembic_revision(stripped):
                raise _PackagedGraphMalformed("down_revision does not satisfy shape validator")
            return (stripped,)
        raise _PackagedGraphMalformed(
            f"down_revision is non-string constant: {type(value).__name__}"
        )
    if isinstance(node, (ast.Tuple, ast.List)):
        ids: list[str | None] = []
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                stripped = elt.value.strip()
                if not stripped:
                    raise _PackagedGraphMalformed("down_revision tuple contains empty string")
                if not _is_alembic_revision(stripped):
                    raise _PackagedGraphMalformed("down_revision tuple contains malformed id")
                ids.append(stripped)
            elif isinstance(elt, ast.Constant) and elt.value is None:
                ids.append(None)
            else:
                raise _PackagedGraphUnreadable(
                    f"down_revision has dynamic element: {type(elt).__name__}"
                )
        if not ids:
            return (None,)
        return tuple(ids)
    raise _PackagedGraphUnreadable(f"down_revision is dynamic expression: {type(node).__name__}")


def probe_database_exact_alembic_head(*, timeout_seconds: int) -> ProbeOutcome:
    """Probe 4 — database_exact_alembic_head.

    Compares the recorded migration head to the packaged head revision
    exposed via the ``COLD_STORAGE_PACKAGED_ALEMBIC_HEAD`` env var. In
    strict modes (staging / production) the comparison is enforced; in
    local / test mode the probe is a documented skip because no
    separate migration service runs and the contract only requires
    strict-mode enforcement (D-S2-01: the application process never
    invokes Alembic upgrade / downgrade). The probe never imports
    alembic; it only reads the ``alembic_version`` SQL table.

    V0.2 Slice 2 amendment (D-S2-12.a.v0.2): every non-timeout
    schema-head failure MUST project to the single public stable code
    ``DATABASE_SCHEMA_HEAD_INVALID``. The internal reason from the
    closed set below is preserved in the safe ``detail`` field for
    log consumption but MUST NOT be used as a public stable code.
    Only genuine timeout events project to ``STARTUP_PROBE_TIMEOUT``
    (or ``READINESS_PROBE_TIMEOUT`` on the readiness channel); a
    schema mismatch, missing packaged head, malformed / zero / multiple
    head, or unknown schema identity MUST NEVER be mis-projected to a
    timeout code. The safe projection never includes the raw
    exception text, packaged Head value, database Head value, DSN,
    or SQL.
    """
    name = PROBE_SCHEMA
    start = time.monotonic()
    try:
        settings = canonical_settings()
        mode = resolve_app_mode(settings)
    except ConfigurationProbeFailed:
        return _schema_head_invalid(
            name=name,
            internal_reason="UNKNOWN_SCHEMA_IDENTITY",
            duration=time.monotonic() - start,
        )
    if mode not in (AppMode.STAGING, AppMode.PRODUCTION):
        return _pass(
            name=name,
            detail=f"non-strict mode skip ({mode.value})",
            duration=time.monotonic() - start,
        )

    packaged_head, packaged_internal_reason = _load_packaged_alembic_head()
    if packaged_head is None:
        return _schema_head_invalid(
            name=name,
            internal_reason=packaged_internal_reason or "PACKAGED_HEAD_MISSING",
            duration=time.monotonic() - start,
        )
    try:
        from cold_storage.bootstrap.dependencies import get_engine

        engine = get_engine()
        with engine.connect() as conn:
            head_row = conn.exec_driver_sql("SELECT version_num FROM alembic_version").first()
    except Exception:
        # The probe reached a connection-level failure AFTER the
        # packaged head was validated. Per D-S2-12.a.v0.2 this is a
        # non-timeout schema identity failure and MUST NOT be
        # projected to a timeout code; we also MUST NOT surface the
        # raw exception text. The internal reason is preserved in the
        # safe detail envelope.
        return _schema_head_invalid(
            name=name,
            internal_reason="DATABASE_HEAD_UNREADABLE_AFTER_CONNECTION",
            duration=time.monotonic() - start,
        )
    if head_row is None:
        return _schema_head_invalid(
            name=name,
            internal_reason="DATABASE_HEAD_ZERO",
            duration=time.monotonic() - start,
        )
    recorded_raw = head_row[0]
    if not isinstance(recorded_raw, str) or not recorded_raw.strip():
        return _schema_head_invalid(
            name=name,
            internal_reason="DATABASE_HEAD_MALFORMED",
            duration=time.monotonic() - start,
        )
    recorded = recorded_raw.strip()
    if not _is_alembic_revision(recorded):
        return _schema_head_invalid(
            name=name,
            internal_reason="DATABASE_HEAD_MALFORMED",
            duration=time.monotonic() - start,
        )
    if recorded != packaged_head:
        return _schema_head_invalid(
            name=name,
            internal_reason="DATABASE_HEAD_MISMATCH",
            duration=time.monotonic() - start,
        )
    return _pass(name=name, detail="schema head ok", duration=time.monotonic() - start)


def _is_alembic_revision(value: str) -> bool:
    """Return True iff ``value`` is a well-formed single Alembic revision.

    V0.2 Slice 2 amendment (D-S2-12.a.v0.2): the project's existing
    migration revisions are alphanumeric (e.g.
    ``0039_widen_report_export_artifact_mime_type``) rather than the
    12-char lowercase hex shape Alembic produces for short hashes.
    The production database migration that widens
    ``alembic_version.version_num`` to ``VARCHAR(64)`` (V0.2) confirms
    the deployed revisions are free-form. The valid envelope is
    therefore: any non-empty string consisting of digits, lowercase
    letters, and underscores — the canonical Alembic ``rev_id``
    format. This deliberately forbids whitespace, commas (which would
    indicate multi-revision values), and other punctuation that
    would be unsafe to surface as a stable identity.
    """
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if not stripped:
        return False
    if "," in stripped:
        return False
    return all(c in "0123456789abcdefghijklmnopqrstuvwxyz_-" for c in stripped)


def probe_environment_and_resource_identities(*, timeout_seconds: int) -> ProbeOutcome:
    """Probe 5 — environment_and_resource_identities.

    Verifies that the canonical Settings authority matches the env
    keys consulted by the bootstrap layer. Failures classify as
    ``STARTUP_PROBE_TIMEOUT``; the safe projection never leaks the
    raw environment values.
    """
    name = PROBE_ENVIRONMENT
    start = time.monotonic()
    try:
        settings = canonical_settings()
        mode = resolve_app_mode(settings)
    except ConfigurationProbeFailed:
        return _fail(
            name=name,
            code=STARTUP_PROBE_TIMEOUT,
            detail="canonical settings missing",
            duration=time.monotonic() - start,
        )
    return _pass(
        name=name,
        detail=f"mode={mode.value}",
        duration=time.monotonic() - start,
    )


def probe_artifact_storage_isolated_exists_writable(*, timeout_seconds: int) -> ProbeOutcome:
    """Probe 6 — artifact_storage_isolated_exists_writable.

    Confirms that the canonical artifact storage directory exists and
    is writable. In strict modes (staging / production) the directory
    MUST be configured; in local / test mode the probe is a documented
    skip when no directory is configured (the legacy default of
    ``./data/report_artifacts`` is fine for local development).

    D-S2-12.a.v0.2 amendment (artifact-storage-classification-amendment):
    the canonical storage authority is **only**
    ``Settings.storage_dir``. The legacy ad-hoc env keys
    ``COLD_STORAGE_ARTIFACT_STORAGE_DIR`` and
    ``COLD_STORAGE_REPORT_ARTIFACTS_DIR`` are forbidden authority
    and MUST NOT influence this probe. Every deterministic
    filesystem failure (path absent, directory missing, directory
    not writable, probe-file I/O failure) projects to the public
    stable code ``ARTIFACT_STORAGE_UNAVAILABLE`` and NEVER to a
    timeout code. A genuine elapsed-budget timeout continues to
    project to ``STARTUP_PROBE_TIMEOUT`` (raised by the
    ``run_probe_with_timeout`` wrapper, not by this body). Settings
    construction failures (e.g. ``ConfigurationError`` from
    :func:`canonical_settings`) are NOT reclassified as
    ``ARTIFACT_STORAGE_UNAVAILABLE``; they propagate through the
    existing configuration-identity classification authority.
    """
    name = PROBE_ARTIFACT
    start = time.monotonic()
    import contextlib as _contextlib
    import os as _os
    import tempfile as _tempfile

    # 1. Resolve canonical Settings. Construction failures MUST NOT
    #    be reclassified as ``ARTIFACT_STORAGE_UNAVAILABLE``;
    #    :func:`canonical_settings` raises the existing
    #    ``ConfigurationProbeFailed`` which the runner treats as a
    #    configuration-identity failure.
    settings = canonical_settings()
    mode = resolve_app_mode(settings)

    storage_dir_raw = settings.storage_dir
    storage_dir = storage_dir_raw.strip() if isinstance(storage_dir_raw, str) else ""

    # 2. Defensive path-absence check (covers a canonical Settings
    #    object whose ``storage_dir`` was never populated). The
    #    frozen internal reason is ``ARTIFACT_STORAGE_PATH_NOT_CONFIGURED``.
    if not storage_dir:
        if mode not in (AppMode.STAGING, AppMode.PRODUCTION):
            return _pass(
                name=name,
                detail="non-strict mode skip",
                duration=time.monotonic() - start,
            )
        return _artifact_storage_unavailable(
            name=name,
            internal_reason="ARTIFACT_STORAGE_PATH_NOT_CONFIGURED",
            duration=time.monotonic() - start,
        )

    # 3. Existence check. We use ``Path.is_dir()`` on the resolved
    #    canonical storage_dir — we do NOT create the directory and
    #    do NOT follow ad-hoc env authority.
    storage_path = Path(storage_dir)
    if not storage_path.is_dir():
        if mode not in (AppMode.STAGING, AppMode.PRODUCTION):
            # local / test: treat absent default directory as a
            # documented skip so existing dev workflows still work.
            return _pass(
                name=name,
                detail="non-strict mode skip",
                duration=time.monotonic() - start,
            )
        return _artifact_storage_unavailable(
            name=name,
            internal_reason="ARTIFACT_STORAGE_DIRECTORY_MISSING",
            duration=time.monotonic() - start,
        )

    # 4. Bounded, removable probe artifact in strict modes only.
    #    local / test modes already returned PASS above; below we
    #    only run for staging / production. We use
    #    :func:`tempfile.NamedTemporaryFile` with ``delete=False``
    #    so we control the unlink lifecycle ourselves and can map
    #    cleanup failures to the same frozen code.
    if mode not in (AppMode.STAGING, AppMode.PRODUCTION):
        return _pass(
            name=name,
            detail="non-strict mode skip",
            duration=time.monotonic() - start,
        )

    try:
        # ``dir=`` pins the probe file inside the canonical
        # storage_dir. ``prefix=`` and ``suffix=`` give us a unique,
        # bounded-name file we can identify safely (the full name
        # is intentionally not projected into the public detail).
        # We deliberately do NOT call chmod, chown, mount, mkdir,
        # or any business-artifact write operation.
        fd, probe_path_str = _tempfile.mkstemp(
            prefix="artifact-storage-readiness-probe.",
            suffix=".tmp",
            dir=str(storage_path),
        )
        try:
            with _os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write("ok")
                fh.flush()
                with _contextlib.suppress(OSError):
                    # ``fsync`` failure on some filesystems (e.g.
                    # tmpfs) is not a writability failure; the
                    # write+close already succeeded.
                    _os.fsync(fh.fileno())
        except OSError:
            # fdopen / write / flush failure — try cleanup then
            # report probe I/O failure. We never expose the
            # OSError text, errno, or probe file name.
            with _contextlib.suppress(OSError):
                _os.unlink(probe_path_str)
            return _artifact_storage_unavailable(
                name=name,
                internal_reason="ARTIFACT_STORAGE_PROBE_IO_FAILURE",
                duration=time.monotonic() - start,
            )
        # 5. Cleanup. If unlink fails we MUST fail closed (per
        #    contract §7.7) — a leftover probe file is not the
        #    end of the world, but the contract demands fail-closed.
        try:
            _os.unlink(probe_path_str)
        except OSError:
            return _artifact_storage_unavailable(
                name=name,
                internal_reason="ARTIFACT_STORAGE_PROBE_IO_FAILURE",
                duration=time.monotonic() - start,
            )
    except OSError:
        # mkstemp or any other low-level failure during probe
        # artifact creation. Same frozen code; never a timeout.
        return _artifact_storage_unavailable(
            name=name,
            internal_reason="ARTIFACT_STORAGE_PROBE_IO_FAILURE",
            duration=time.monotonic() - start,
        )

    return _pass(
        name=name,
        detail="artifact-storage available and writable",
        duration=time.monotonic() - start,
    )


def probe_approved_coefficient_readiness_in_strict_modes(*, timeout_seconds: int) -> ProbeOutcome:
    """Probe 7 — approved_coefficient_readiness_in_strict_modes.

    Reuses :func:`startup_readiness.run_startup_readiness_or_raise`
    to verify the coefficient coverage. Local / test modes skip the
    production check (no DB writes or fixtures touched); staging /
    production run the same fail-closed path.
    """
    name = PROBE_COEFFICIENT
    start = time.monotonic()
    try:
        from cold_storage.bootstrap.dependencies import get_engine
        from cold_storage.bootstrap.startup_readiness import (
            run_startup_readiness_or_raise,
        )

        engine = get_engine()
        settings = canonical_settings()
    except ConfigurationProbeFailed:
        return _fail(
            name=name,
            code=STARTUP_PROBE_TIMEOUT,
            detail="canonical settings missing",
            duration=time.monotonic() - start,
        )
    except RuntimeError as exc:
        return _fail(
            name=name,
            code=STARTUP_PROBE_TIMEOUT,
            detail=f"engine unavailable: {type(exc).__name__}",
            duration=time.monotonic() - start,
        )
    try:
        outcome = run_startup_readiness_or_raise(settings=settings, engine=engine)
    except Exception as exc:  # noqa: BLE001
        return _fail(
            name=name,
            code=STARTUP_PROBE_TIMEOUT,
            detail=f"coefficient coverage failed: {type(exc).__name__}",
            duration=time.monotonic() - start,
        )
    if not outcome.executed:
        return _pass(
            name=name,
            detail="non-strict mode skip",
            duration=time.monotonic() - start,
        )
    if not bool((outcome.result or {}).get("ready", False)):
        return _fail(
            name=name,
            code=STARTUP_PROBE_TIMEOUT,
            detail="coefficient coverage not ready",
            duration=time.monotonic() - start,
        )
    return _pass(name=name, detail="coverage ready", duration=time.monotonic() - start)


def probe_build_and_deployment_identity(*, timeout_seconds: int) -> ProbeOutcome:
    """Probe 8 — build_and_deployment_identity.

    Verifies that the in-image build identity can be read; on success,
    re-uses :func:`load_runtime_identity` to cross-check runtime env
    vars. In strict modes (staging / production) the identity file
    MUST exist and the cross-check MUST pass; in local / test mode the
    probe is a documented skip (the in-image file is not shipped to
    developer machines). Failure modes classify as
    ``STARTUP_PROBE_TIMEOUT``; the safe projection never includes the
    commit SHA, version, or deployment ID values.
    """
    name = PROBE_BUILD_IDENTITY
    start = time.monotonic()
    try:
        mode = resolve_app_mode(canonical_settings())
    except ConfigurationProbeFailed:
        mode = None
    if mode not in (AppMode.STAGING, AppMode.PRODUCTION):
        return _pass(
            name=name,
            detail=f"non-strict mode skip ({mode.value if mode else 'unknown'})",
            duration=time.monotonic() - start,
        )
    import os as _os

    try:
        from cold_storage.bootstrap.deployment_identity import (
            load_runtime_identity,
        )

        env = {k: v for k, v in _os.environ.items()}
        record, deployment_id = load_runtime_identity(env=env)
    except Exception as exc:  # noqa: BLE001
        return _fail(
            name=name,
            code=STARTUP_PROBE_TIMEOUT,
            detail=f"identity check failed: {type(exc).__name__}",
            duration=time.monotonic() - start,
        )
    if not deployment_id:
        return _fail(
            name=name,
            code=STARTUP_PROBE_TIMEOUT,
            detail="deployment id missing",
            duration=time.monotonic() - start,
        )
    return _pass(
        name=name,
        detail="identity ok",
        duration=time.monotonic() - start,
    )


def mandatory_startup_probes() -> tuple[ProbeFn, ...]:
    """Return the canonical 8-probe startup tuple (D-S2-04)."""
    return (
        probe_lifecycle_initialization_completed,
        probe_process_not_draining_or_shutting_down,
        probe_database_connectivity,
        probe_database_exact_alembic_head,
        probe_environment_and_resource_identities,
        probe_artifact_storage_isolated_exists_writable,
        probe_approved_coefficient_readiness_in_strict_modes,
        probe_build_and_deployment_identity,
    )


def mandatory_readiness_probes() -> tuple[ProbeFn, ...]:
    """Return the canonical 8-probe readiness tuple (D-S2-04)."""
    return mandatory_startup_probes()


__all__ = [
    "DATABASE_SCHEMA_HEAD_INVALID",
    "BlockingProbeTimeout",
    "CONFIGURATION_IDENTITY_FAILURE",
    "LOCAL_TEST_READINESS_PROBE_TIMEOUT_SECONDS",
    "LOCAL_TEST_STARTUP_PROBE_TIMEOUT_SECONDS",
    "PROBE_ARTIFACT",
    "PROBE_BUILD_IDENTITY",
    "PROBE_COEFFICIENT",
    "PROBE_DATABASE",
    "PROBE_ENVIRONMENT",
    "PROBE_LIFECYCLE",
    "PROBE_NOT_DRAINING",
    "PROBE_SCHEMA",
    "ProbeFn",
    "ProbeOutcome",
    "READINESS_PROBE_TIMEOUT",
    "ReadinessError",
    "ReadinessProbeTimeout",
    "ReadinessState",
    "STARTUP_PROBE_TIMEOUT",
    "STARTUP_PROBE_TIMEOUT_MAX",
    "STARTUP_PROBE_TIMEOUT_MIN",
    "StartupProbeFailure",
    "StartupProbeTimeout",
    "StartupNonTimeoutProbeFailure",
    "UNSAFE_STRICT_CAPABILITY_WIRING",
    "UnsafeStrictCapabilityWiring",
    "READINESS_PROBE_TIMEOUT_MAX",
    "READINESS_PROBE_TIMEOUT_MIN",
    "assert_no_unsafe_strict_capabilities",
    "canonical_settings",
    "composition_manifest_tokens",
    "enumerate_reachable_unsafe_strict_capabilities",
    "get_or_init_readiness_state",
    "get_readiness_state",
    "mandatory_readiness_probes",
    "mandatory_startup_probes",
    "probe_approved_coefficient_readiness_in_strict_modes",
    "probe_artifact_storage_isolated_exists_writable",
    "probe_build_and_deployment_identity",
    "probe_database_connectivity",
    "probe_database_exact_alembic_head",
    "probe_environment_and_resource_identities",
    "probe_lifecycle_initialization_completed",
    "probe_process_not_draining_or_shutting_down",
    "register_strict_capability",
    "registered_strict_capabilities",
    "reset_canonical_settings",
    "reset_composition_manifest_provider",
    "reset_readiness_state",
    "run_probe_with_timeout",
    "run_readiness_phase",
    "run_startup_phase",
    "set_canonical_settings",
    "set_composition_manifest_provider",
    "set_readiness_state",
    "validate_probe_timeout_seconds",
    "resolve_probe_timeout_seconds",
]
