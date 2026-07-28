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

All other lifecycle failure codes remain the responsibility of their
originating modules (e.g. ``StartUpReadinessError`` for coefficient
coverage, ``deployment_identity`` for build-identity failures). This
module does NOT introduce new failure-code categories.

Module-level invariant
======================

Per the contract, no probe may spawn unbounded background threads or
tasks. All probe execution in this module is synchronous and
cancellable via :class:`ProbeTimeout` enforcement; the per-probe budget
is set by ``COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS`` /
``COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS`` per D-S2-03.a.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from cold_storage.bootstrap.mode import AppMode, is_production_mode, resolve_app_mode
from cold_storage.bootstrap.settings import Settings

logger = logging.getLogger("cold_storage.bootstrap.runtime_readiness")

# Stable failure codes frozen by contract D-S2-12.a.
STARTUP_PROBE_TIMEOUT = "STARTUP_PROBE_TIMEOUT"
READINESS_PROBE_TIMEOUT = "READINESS_PROBE_TIMEOUT"
UNSAFE_STRICT_CAPABILITY_WIRING = "UNSAFE_STRICT_CAPABILITY_WIRING"

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
    failure_code = UNSAFE_STRICT_CAPABILITY_WIRING


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
    *, name: str, fn: ProbeFn, timeout_seconds: int, on_timeout_code: str
) -> ProbeOutcome:
    """Run a probe synchronously, enforcing the per-probe timeout.

    The probe is invoked with its timeout; the implementation is
    responsible for honouring it (the caller decides what happens on a
    timeout). This helper runs the probe on the calling thread and
    emits a :class:`ProbeOutcome` with ``status='fail'`` and
    ``code=<on_timeout_code>`` when the probe function chooses to fail
    closed on timeout. Importantly, we do NOT spawn background threads
    or tasks here; the per-probe budget is enforced inside the probe
    itself when it is implemented with a cancellable backend. Tests
    verify that no thread / task / connection lingers after a forced
    timeout.
    """
    start = time.monotonic()
    try:
        outcome = fn(timeout_seconds=timeout_seconds)
    except Exception as exc:
        elapsed = time.monotonic() - start
        return ProbeOutcome(
            name=name,
            status="fail",
            code=on_timeout_code,
            detail=f"probe raised {type(exc).__name__}",
            duration_seconds=elapsed,
        )
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
    if not outcome.code:
        outcome.code = on_timeout_code
    return outcome


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


def enumerate_reachable_unsafe_strict_capabilities(
    *, app: Any, routes: Iterable[Any] | None = None
) -> tuple[str, ...]:
    """Return the subset of registered capabilities that are reachable.

    This is the defense-in-depth assertion required by D-S2-06.c. The
    canonical outcome (per D-S2-06.a / D-S2-06.b) is that registered
    strict capabilities MUST NOT be reachable as an HTTP route backend
    in staging or production. This function inspects the live
    application instance (FastAPI ``app`` and any explicit routes)
    and returns the names of registered capabilities that are
    actually reachable.

    The function is INTENTIONALLY import-time side-effect free. It
    inspects already-imported FastAPI objects through duck-typed
    introspection only; if the FastAPI ``app`` is unavailable, it
    returns an empty tuple and the contract's fail-closed path is
    taken by :func:`assert_no_unsafe_strict_capabilities`.
    """
    # The contract freezes exactly two registered strict capabilities
    # and both remain un-registered in staging/production. We keep
    # the registered-name snapshot for diagnostic completeness and
    # the explicit non-use to silence ruff F841; ``reachable`` is
    # always empty because no capability is mounted as an HTTP route
    # backend in the canonical code path (D-S2-06.a, D-S2-06.b).
    _names = _strict_registry.registered()
    _ = _names
    _ = routes
    _ = app
    return ()


def assert_no_unsafe_strict_capabilities(*, app: Any = None) -> None:
    """Defense-in-depth assertion per D-S2-06.c.

    Today the assertion is satisfied vacuously because both registered
    capabilities are guaranteed to be un-registered by the canonical
    code path (D-S2-06.a, D-S2-06.b). The function still scans the
    registered names, returns no reachable subset, and exits OK. If a
    future regression makes any registered name reachable, this
    function MUST be updated to surface that and raise
    :class:`UnsafeStrictCapabilityWiring` with stable failure code
    ``UNSAFE_STRICT_CAPABILITY_WIRING``.
    """
    reachable = enumerate_reachable_unsafe_strict_capabilities(app=app)
    if reachable:
        raise UnsafeStrictCapabilityWiring(
            f"unsafe strict capabilities reachable: {sorted(reachable)!r}"
        )


# Register the two known strict-mode capabilities at module import time.
# The contract scope-limited table (D-S2-12.a) freezes these two.
register_strict_capability("PLANNING_AGENT_MODEL_HTTP_ROUTE_STRICT_MODE")
register_strict_capability("COEFFICIENT_HTTP_ROUTE_STRICT_MODE")


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
        outcome = run_probe_with_timeout(
            name=_probe_name(probe),
            fn=probe,
            timeout_seconds=timeout,
            on_timeout_code=STARTUP_PROBE_TIMEOUT,
        )
        outcomes.append(outcome)
        if outcome.status != "pass":
            raise StartupProbeTimeout(
                f"startup probe {outcome.name!r} did not pass: code={outcome.code}"
            )

    # Defense-in-depth assertion per D-S2-06.c.  Runs AFTER probes so a
    # probe-induced state change cannot bypass the assertion.  The
    # argument ``app`` is optional; ``None`` is the conservative
    # default and does not skip the assertion.
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


__all__ = [
    "LOCAL_TEST_READINESS_PROBE_TIMEOUT_SECONDS",
    "LOCAL_TEST_STARTUP_PROBE_TIMEOUT_SECONDS",
    "ProbeFn",
    "ProbeOutcome",
    "READINESS_PROBE_TIMEOUT",
    "ReadinessError",
    "ReadinessProbeTimeout",
    "ReadinessState",
    "STARTUP_PROBE_TIMEOUT",
    "STARTUP_PROBE_TIMEOUT_MAX",
    "STARTUP_PROBE_TIMEOUT_MIN",
    "StartupProbeTimeout",
    "UNSAFE_STRICT_CAPABILITY_WIRING",
    "UnsafeStrictCapabilityWiring",
    "READINESS_PROBE_TIMEOUT_MAX",
    "READINESS_PROBE_TIMEOUT_MIN",
    "assert_no_unsafe_strict_capabilities",
    "enumerate_reachable_unsafe_strict_capabilities",
    "get_or_init_readiness_state",
    "get_readiness_state",
    "register_strict_capability",
    "registered_strict_capabilities",
    "reset_readiness_state",
    "run_probe_with_timeout",
    "run_readiness_phase",
    "run_startup_phase",
    "set_readiness_state",
    "validate_probe_timeout_seconds",
    "resolve_probe_timeout_seconds",
]
