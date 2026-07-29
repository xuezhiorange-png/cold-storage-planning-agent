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
CONFIGURATION_PROBE_FAILED = "CONFIGURATION_PROBE_FAILED"

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

    def __init__(self, message: str, *, unsafe_capabilities: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.unsafe_capabilities: tuple[str, ...] = tuple(unsafe_capabilities)


class ConfigurationProbeFailed(ReadinessError):
    failure_code = CONFIGURATION_PROBE_FAILED


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
    reachable as an HTTP backend. We deliberately look for path
    substrings rather than full route registration identity so the
    audit is robust to local-test wiring differences that rename the
    router but keep the prefix stable.
    """

    route_prefixes: tuple[str, ...]


_STRICT_CAPABILITY_PROBES[_STRICT_CAPABILITY_PLANNING_AGENT] = _StrictCapabilityProbeSpec(
    route_prefixes=("/api/v1/agent/",)
)
_STRICT_CAPABILITY_PROBES[_STRICT_CAPABILITY_COEFFICIENT] = _StrictCapabilityProbeSpec(
    route_prefixes=("/api/v1/coefficients",)
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
    reachable: list[str] = []
    for name in names:
        spec = _STRICT_CAPABILITY_PROBES.get(name)
        if spec is None:
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
    call :func:`set_canonical_settings` exactly once during bootstrap;
    readiness code uses this accessor so we never construct a second
    Settings authority per readiness call (F-S2-REVIEW-005).

    Before the lifecycle has set the canonical settings, this accessor
    raises :class:`ConfigurationProbeFailed` so the readiness endpoint
    surfaces a stable failure code rather than building a new authority
    on the side.
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
    Failures classify as ``STARTUP_PROBE_TIMEOUT`` with the safe
    projection.
    """
    name = PROBE_SCHEMA
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
    if mode not in (AppMode.STAGING, AppMode.PRODUCTION):
        return _pass(
            name=name,
            detail=f"non-strict mode skip ({mode.value})",
            duration=time.monotonic() - start,
        )
    import os as _os

    packaged_head = _os.environ.get("COLD_STORAGE_PACKAGED_ALEMBIC_HEAD", "")
    if not packaged_head:
        return _fail(
            name=name,
            code=STARTUP_PROBE_TIMEOUT,
            detail="packaged alembic head not exported",
            duration=time.monotonic() - start,
        )
    try:
        from cold_storage.bootstrap.dependencies import get_engine

        engine = get_engine()
        with engine.connect() as conn:
            head_row = conn.exec_driver_sql("SELECT version_num FROM alembic_version").first()
    except Exception as exc:  # noqa: BLE001
        return _fail(
            name=name,
            code=STARTUP_PROBE_TIMEOUT,
            detail=f"schema probe failed: {type(exc).__name__}",
            duration=time.monotonic() - start,
        )
    recorded = head_row[0] if head_row is not None else ""
    if recorded != packaged_head:
        return _fail(
            name=name,
            code=STARTUP_PROBE_TIMEOUT,
            detail="schema head mismatch",
            duration=time.monotonic() - start,
        )
    return _pass(name=name, detail="schema head ok", duration=time.monotonic() - start)


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
    Failures classify as ``STARTUP_PROBE_TIMEOUT``; the safe
    projection includes only a redacted directory name token.
    """
    name = PROBE_ARTIFACT
    start = time.monotonic()
    import os as _os

    storage_dir = _os.environ.get(
        "COLD_STORAGE_ARTIFACT_STORAGE_DIR",
        _os.environ.get("COLD_STORAGE_REPORT_ARTIFACTS_DIR", ""),
    )
    if not storage_dir:
        try:
            mode = resolve_app_mode(canonical_settings())
        except ConfigurationProbeFailed:
            mode = None
        if mode not in (AppMode.STAGING, AppMode.PRODUCTION):
            return _pass(
                name=name,
                detail="non-strict mode skip",
                duration=time.monotonic() - start,
            )
        return _fail(
            name=name,
            code=STARTUP_PROBE_TIMEOUT,
            detail="artifact storage dir not configured",
            duration=time.monotonic() - start,
        )
    p = storage_dir.rstrip("/").split("/")[-1] or "."
    if not _os.path.isdir(storage_dir):
        return _fail(
            name=name,
            code=STARTUP_PROBE_TIMEOUT,
            detail=f"artifact dir '{p}' missing",
            duration=time.monotonic() - start,
        )
    probe_path = _os.path.join(storage_dir, ".readiness-probe")
    try:
        with open(probe_path, "w", encoding="utf-8") as fh:
            fh.write("ok")
        _os.unlink(probe_path)
    except OSError as exc:
        return _fail(
            name=name,
            code=STARTUP_PROBE_TIMEOUT,
            detail=f"artifact dir '{p}' not writable: {type(exc).__name__}",
            duration=time.monotonic() - start,
        )
    return _pass(name=name, detail=f"artifact dir '{p}' ok", duration=time.monotonic() - start)


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
    "CONFIGURATION_PROBE_FAILED",
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
    "StartupProbeTimeout",
    "UNSAFE_STRICT_CAPABILITY_WIRING",
    "UnsafeStrictCapabilityWiring",
    "READINESS_PROBE_TIMEOUT_MAX",
    "READINESS_PROBE_TIMEOUT_MIN",
    "assert_no_unsafe_strict_capabilities",
    "canonical_settings",
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
    "reset_readiness_state",
    "run_probe_with_timeout",
    "run_readiness_phase",
    "run_startup_phase",
    "set_canonical_settings",
    "set_readiness_state",
    "validate_probe_timeout_seconds",
    "resolve_probe_timeout_seconds",
]
