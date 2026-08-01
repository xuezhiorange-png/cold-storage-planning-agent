"""Bootstrap-level startup-readiness check — Phase 4 Slice 2A.

This module is the **only** place that turns the result of
``CoefficientApprovalService.validate_startup_readiness`` into a
fail-closed startup decision. The check is gated on
:func:`bootstrap.mode.resolve_app_mode` so production mode fails
closed while development / test mode stays as-is (no demo /
migration / fixtures breakage).

Why the check lives here, not in the orchestrator
=================================================

* The orchestrator runs only when an end-to-end attempt fires; we
  want a *startup* failure, not a per-request one. Raising in the
  lifespan hook surfaces the problem at the deploy step.
* The composition root already owns the wiring of
  :class:`CoefficientApprovalService` against a SQLAlchemy
  ``Engine`` (see Slice 1's
  ``bootstrap.production_composition.compose_production_coefficient_approval_service``
  factory). The readiness check simply reuses that factory.
* Putting the result aggregator here keeps the resolver /
  approval service surfaces unchanged: those still raise the
  per-stage typed errors and the bootstrap layer is the one that
  folds them into a single
  :class:`StartupReadinessError` (or a single
  :class:`MissingApprovedCoefficientError` for the legacy single-
  bucket case, should the inventory stay empty apart from one
  stage).

Why we only consult the existing service
========================================

* No new business logic is introduced. The resolver / approval
  service already do the per-stage filtering (demo / stale /
  missing citation / invalid citation) and return a structured
  dict. This module adds the bootstrap-level fail-closed gate
  and the aggregated exception.
* No ports / adapters are added (architecture layer stay
  stable; see Slice 2A plan §3.2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cold_storage.bootstrap.mode import (
    AppMode,
    resolve_app_mode,
)
from cold_storage.bootstrap.settings import Settings
from cold_storage.modules.coefficients.application.approval_service import (
    CoefficientApprovalService,
)
from cold_storage.modules.coefficients.domain.exceptions import (
    StartupReadinessError,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine


# Canonical 5-stage required-coverage list.  Mirrors the orchestrator's
# fixed stage order in ``orchestration.domain.dag`` and the table in
# ``source_binding_assembly._STAGE_ADAPTER_TABLE``.  Keep in sync with
# both — they encode the same production roundtrip contract.
#
# ``calculation_type`` is the second axis of the pool key
# ``(stage_name, calculation_type, source_type)`` from design contract §5.1.
# All five stages today use a single canonical calculation type,
# which matches the calculator adapter bindings; should that change
# in a future Slice, this tuple is the only place that needs to
# carry the catalogue.
_REQUIRED_STAGES: tuple[tuple[str, str | None], ...] = (
    ("zone", "ZONE"),
    ("cooling_load", "COOLING_LOAD"),
    ("equipment", "EQUIPMENT"),
    ("power", "POWER"),
    ("investment", "INVESTMENT"),
)


def get_required_stages() -> list[tuple[str, str | None]]:
    """Return the canonical required-stages list (immutable copy).

    Returning a fresh list (not the module-level tuple) means
    callers cannot accidentally mutate the canonical catalogue.
    The list shape is the second axis of the
    ``(stage_name, calculation_type)`` pool key per design
    contract §5.1.
    """
    return list(_REQUIRED_STAGES)


class ReadinessCheckOutcome:
    """Outcome of a readiness check.

    Carries enough state for the operator log line / test
    assertion to distinguish "skipped" vs "passed" vs "raised".

    * ``mode`` — the mode the check ran under.
    * ``executed`` — True when the check actually consulted the
      production database (``PRODUCTION`` mode), False when it
      was a non-production skip.
    * ``result`` — the dict returned by
      :meth:`CoefficientApprovalService.validate_startup_readiness`,
      or ``None`` when the check was skipped.
    """

    __slots__ = ("mode", "executed", "result")

    def __init__(
        self,
        *,
        mode: AppMode,
        executed: bool,
        result: dict[str, Any] | None,
    ) -> None:
        self.mode = mode
        self.executed = executed
        self.result = result

    def __repr__(self) -> str:
        if not self.executed:
            return f"ReadinessCheckOutcome(mode={self.mode!r}, executed=False)"
        assert self.result is not None
        return (
            f"ReadinessCheckOutcome(mode={self.mode!r}, executed=True, "
            f"ready={self.result['ready']})"
        )


def _build_approval_service(engine: Engine) -> CoefficientApprovalService:
    """Build a production :class:`CoefficientApprovalService` from an engine.

    Delegates to the Slice 1 factory so the readiness gateway uses
    the same wiring as the composition root. The factory itself
    accepts an optional ``mutation_service`` for test fakes; in the
    readiness path we always want the production wiring against
    ``engine``, so we do **not** pass a mutation target.
    """
    from cold_storage.bootstrap.production_composition import (
        compose_production_coefficient_approval_service,
    )

    return compose_production_coefficient_approval_service(engine=engine)


def run_startup_readiness_or_raise(
    *,
    settings: Settings,
    engine: Engine,
) -> ReadinessCheckOutcome:
    """Conditional fail-closed startup readiness check.

    Behaviour matrix (TASK-012 Slice 2, D-S2-05):

    =================  ==========================================
    Mode              Effect
    =================  ==========================================
    ``PRODUCTION``    Consults the production database via
                      :class:`CoefficientApprovalService`. If any
                      of the four buckets (missing / stale /
                      demoted / citation) returned by
                      :meth:`CoefficientApprovalService.validate_startup_readiness`
                      is non-empty, raise
                      :class:`StartupReadinessError` with the full
                      inventory so operators can remediate in one
                      cycle.
    ``STAGING``       Same fail-closed path as production (per
                      D-S2-05 "staging and production use the
                      same classes of startup and readiness
                      checks"). Staging must not fall through a
                      local/test skip path.
    ``DEVELOPMENT``   Skipped; returns ``ReadinessCheckOutcome``
                      with ``executed=False``.
    ``TEST``          Same as ``DEVELOPMENT`` — skipped.
    =================  ==========================================

    Calling this function in non-production mode is intentionally
    a no-op; the production codebase achieves fail-closed
    behaviour without ever needing to touch the test or
    development paths. Charles's Slice 2A constraint: "do not
    hook into demo/dev/test default paths".

    The function never raises :class:`MissingApprovedCoefficientError`
    or its siblings — those are routed through the *resolver*, not
    the readiness aggregator. The single raise here is
    :class:`StartupReadinessError`. Operators can branch on
    ``isinstance(exc, StartupReadinessError)`` without parsing
    message text.
    """
    # Per D-S2-05, staging now uses the same fail-closed classes as
    # production. We key on ``settings.environment_id`` (which is
    # the ``EnvironmentId`` StrEnum canonical to Slice 1) rather than
    # ``settings.app_env`` (a ``Literal`` without the staging value)
    # so staging is correctly classified as production-equivalent.
    from cold_storage.bootstrap.environment_model import EnvironmentId

    env_id = settings.environment_id
    if env_id not in (EnvironmentId.STAGING, EnvironmentId.PRODUCTION):
        return ReadinessCheckOutcome(mode=resolve_app_mode(settings), executed=False, result=None)

    approval_service = _build_approval_service(engine)
    result = approval_service.validate_startup_readiness(
        stage_names=get_required_stages(),
    )

    ready = bool(result.get("ready", False))
    if ready:
        return ReadinessCheckOutcome(mode=resolve_app_mode(settings), executed=True, result=result)

    buckets: dict[str, list[dict[str, str]]] = {
        "missing": list(result.get("missing", [])),
        "stale": list(result.get("stale", [])),
        "demoted": list(result.get("demoted", [])),
        "citation": list(result.get("citation", [])),
    }
    raise StartupReadinessError(buckets=buckets, ready=ready)


__all__ = [
    "ReadinessCheckOutcome",
    "get_required_stages",
    "run_startup_readiness_or_raise",
]
