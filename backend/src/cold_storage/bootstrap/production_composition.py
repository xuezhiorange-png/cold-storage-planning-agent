"""Production scheme service composition root.

Single canonical composition entry point for the production
``SchemeRun`` generation path.  Bridges
``schemes.infrastructure.production_repository`` and
``orchestration.infrastructure.archive_composition`` so that:

* every production ``ProductionSchemeService`` instance is constructed
  with ``make_production_archive_callable()`` bound into
  ``SqlAlchemyProductionSchemeRunRepository``;
* the archive INSERT and the ``scheme_runs`` INSERT share the same UoW,
  the same session, and the same ``session.commit()`` boundary;
* an archive builder failure rolls back the entire SchemeRun UoW
  (no half-committed ``scheme_runs`` rows).

Why a dedicated bootstrap module
================================

``production_repository.py`` is library code: its constructor accepts
``build_archive_callable=None`` so unit tests can opt out of the
archive side effect.  ``application.production_service.ProductionSchemeService``
is also library code: it accepts any ``run_repository`` port.  Left
alone, neither module constrains how the production wiring is built
and a caller could legitimately pass ``build_archive_callable=None``
and silently bypass the archive write.

``bootstrap.production_composition`` is the **only** place allowed
to build a production-mode ``SqlAlchemyProductionSchemeRunRepository``
with the archive closure.  Tests can still build their own
repository instances directly (for unit-level isolation); the
architecture test ``test_production_composition_must_wire_archive_callable``
guards this by stat-ing the bootstrap trees for stray
``SqlAlchemyProductionSchemeRunRepository(...)`` constructions.

Public API
==========

* :func:`compose_production_scheme_service` — the canonical factory.
  Pass a ``sessionmaker`` callable (zero-arg, returns a Session).
  Receive a ready-to-use ``ProductionSchemeService`` wired with the
  real archive closure.

* :func:`compose_production_scheme_service_from_session` —
  convenience factory that derives a ``sessionmaker`` from a live
  ``Session`` (shares ``session.bind`` engine, opens new Session
  per UoW request).

Architecture rules upheld
=========================

* ``bootstrap.production_composition`` may import from any module in
  the application tier **and** from infrastructure tier in both the
  schemes and orchestration modules.  This is the composition root
  for the application; module-load-time coupling is intentional.
* The production SchemeRun UoW session is owned by the **caller** of
  :func:`compose_production_scheme_service`, not by the composition
  layer.  This matches the ``ProductionSchemeService.generate_production_scheme_run``
  contract, which only ``commit()``s the UoW on success.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cold_storage.modules.coefficients.application.approval_service import (
    CoefficientApprovalService,
)
from cold_storage.modules.coefficients.application.resolver import (
    ApprovedCoefficientResolver,
)
from cold_storage.modules.coefficients.infrastructure.approval_adapters import (
    InMemoryRoleCheckAdapter,
    SqlAlchemyCoefficientApprovalLogAdapter,
    SqlAlchemyCoefficientAuditLogAdapter,
    SqlAlchemyCoefficientMutationAdapter,
    SqlAlchemyCoefficientRevisionReadAdapter,
    SystemClock,
)
from cold_storage.modules.coefficients.infrastructure.database import (
    DatabaseCoefficientService,
)
from cold_storage.modules.coefficients.infrastructure.transactional_repository import (
    TransactionalCoefficientApprovalRepository,
)
from cold_storage.modules.orchestration.application.production_source_binding import (
    ProductionSourceBindingUseCase,
)
from cold_storage.modules.orchestration.application.service import OrchestrationService
from cold_storage.modules.orchestration.application.source_binding_assembly import (
    Phase2AdapterCalculatorPort,
)
from cold_storage.modules.orchestration.infrastructure.archive_composition import (
    make_production_archive_callable,
)
from cold_storage.modules.schemes.application.production_service import (
    ProductionSchemeService,
)
from cold_storage.modules.schemes.infrastructure.production_read_ports import (
    SqlAlchemySourceBindingReadPort,
    SqlAlchemyWeightRevisionReadPort,
)
from cold_storage.modules.schemes.infrastructure.production_repository import (
    SqlAlchemyProductionSchemeRunRepository,
)
from cold_storage.modules.schemes.infrastructure.production_uow_impl import (
    SqlAlchemyProductionSchemeUnitOfWork,
)


def compose_production_scheme_service(
    session_factory: Callable[[], Any],
) -> ProductionSchemeService:
    """Return a ``ProductionSchemeService`` wired with the real archive closure.

    The returned service will create a ``production_source_archives``
    row alongside every successful ``scheme_runs`` completion.  If
    the archive builder raises, the UoW rolls back and no
    ``scheme_runs`` row is committed.

    Parameters
    ----------
    session_factory:
        Zero-arg callable that returns a SQLAlchemy ``Session``
        (``sessionmaker`` is the canonical instance).  Each
        invocation yields a fresh per-request session.
    """
    archive_callable = make_production_archive_callable()
    run_repository = SqlAlchemyProductionSchemeRunRepository(
        build_archive_callable=archive_callable,
    )

    def uow_factory() -> SqlAlchemyProductionSchemeUnitOfWork:
        return SqlAlchemyProductionSchemeUnitOfWork(session_factory)

    return ProductionSchemeService(
        uow_factory=uow_factory,
        binding_read_port=SqlAlchemySourceBindingReadPort(),
        weight_revision_read_port=SqlAlchemyWeightRevisionReadPort(),
        run_repository=run_repository,
    )


def compose_production_scheme_service_from_session(session: Any) -> ProductionSchemeService:
    """Return a ``ProductionSchemeService`` given an open ``Session``.

    Convenience for callers that already hold an open session and
    do not own a ``sessionmaker``.  The composition layer derives a
    fresh-session ``sessionmaker`` from ``session.bind``; every UoW
    request still gets its own ``Session`` instance so the
    archive-row and the SchemeRun INSERT share one transaction
    boundary, one ``commit()``, and one rollback on failure.
    """
    session_bind = session.bind

    def session_factory() -> Any:
        return type(session)(bind=session_bind, expire_on_commit=False)

    return compose_production_scheme_service(session_factory)


__all__ = [
    "compose_phase2_adapter_calculator_port",
    "compose_production_coefficient_approval_service",
    "compose_production_coefficient_resolver",
    "compose_production_coefficient_resolver_and_approval_service",
    "compose_production_scheme_service",
    "compose_production_scheme_service_from_session",
    "compose_production_source_binding_use_case",
    "compose_production_source_binding_use_case_with_strict_resolver",
]


def compose_phase2_adapter_calculator_port() -> Phase2AdapterCalculatorPort:
    """Return a production :class:`Phase2AdapterCalculatorPort` with default adapters.

    The factory binds the five Phase 2 production adapters
    (zone / cooling_load / equipment / power / investment) into a
    single :class:`CalculatorPort` implementation so the production
    :class:`TransactionBExecutor` can run the five-stage DAG without
    resorting to a mock calculator or a hand-written golden fixture.

    This is the **only** place that constructs a production-mode
    ``Phase2AdapterCalculatorPort``.  Tests can still build their
    own ``Phase2AdapterCalculatorPort(...)`` directly (with
    alternate adapter instances) for unit-level isolation.

    Phase 3 scope: this wiring is the minimum needed for the
    SourceBinding archive and SchemeService E2E use case.  The
    full 5-stage database roundtrip + approved non-demo
    coefficient governance is deferred to Phase 4 / Issue #35.
    """
    return Phase2AdapterCalculatorPort()


def compose_production_source_binding_use_case(
    service: OrchestrationService,
    verification_read_port: Any = None,
) -> ProductionSourceBindingUseCase:
    """Return a :class:`ProductionSourceBindingUseCase` from an :class:`OrchestrationService`.

    The use case is the application-level entry point that drives
    ``OrchestrationService.execute`` (Transaction A) and
    ``OrchestrationService.execute_transaction_b`` (Transaction B)
    end-to-end.  It returns the verified
    ``SourceBindingRecord.id`` for downstream ``SchemeService``
    consumption.

    Parameters
    ----------
    service:
        A fully-wired :class:`OrchestrationService`.  The
        composition root is intentionally **not** responsible for
        constructing this — it has 13 dependencies that are out of
        scope for the Phase 3 minimum-wiring mandate.  Callers
        that have already constructed an ``OrchestrationService``
        (e.g. integration tests) can pass it in.

    verification_read_port:
        Optional :class:`VerificationReadPort` for the use case's
        post-Transaction-B verification reads.  Defaults to
        ``None`` — the use case re-reads the orchestration
        fingerprint directly from the
        :class:`OrchestrationIdentityRecord` row, not through the
        verifier port, so the port is currently unused but kept
        in the signature for forward compatibility.

    Returns
    -------
    :class:`ProductionSourceBindingUseCase`
        The use case instance.  Caller is responsible for managing
        the surrounding session lifecycle (``session.begin()`` /
        ``session.commit()`` / ``session.rollback()``) per the
        production UoW contract.

    Phase 3 scope: the use case is wired at the composition root
    boundary but the full 5-stage database roundtrip is deferred
    to Phase 4 / Issue #35 follow-up.
    """
    if verification_read_port is None:
        # The use case re-reads the fingerprint from
        # ``OrchestrationIdentityRecord`` directly and does not
        # consume the verification port at the moment.  The
        # parameter is reserved for future use; we pass a
        # ``cast``-through-``Any`` shim so the type-checker does
        # not reject the call.  When the use case starts
        # consuming the port, the caller can pass a real
        # implementation here.
        from typing import cast

        from cold_storage.modules.orchestration.application.transaction_b import (
            VerificationReadPort,
        )

        verification_read_port = cast(VerificationReadPort, None)
    return ProductionSourceBindingUseCase(
        service=service,
        verification_read_port=verification_read_port,
    )


# ---------------------------------------------------------------------------
# Phase 4 Issue #35 Slice 1 — approved-coefficient composition wiring.
# Per Charles's Slice 1 boundary correction (2026-07-07): the wiring
# below is the **factory surface** for the production path; calling
# code (or a future ``bootstrap.dependencies`` integration) decides
# when to enable it at startup. The current main startup path does
# NOT auto-invoke these factories, so the existing demo / seed flow
# is unchanged until Slice 2 / Slice 3 explicitly opts in.
# ---------------------------------------------------------------------------


def compose_production_coefficient_resolver(
    *,
    engine: Any,
) -> ApprovedCoefficientResolver:
    """Build a production :class:`ApprovedCoefficientResolver`.

    The factory wires the SQLAlchemy read adapter against the
    production engine and uses a :class:`SystemClock` so the
    stale-approval check observes real wall-clock time. The
    resolver is consumed by
    :class:`CoefficientApprovalService.validate_startup_readiness`
    and (in later Slices) by per-stage orchestrator resolution.

    :param engine: A SQLAlchemy ``Engine`` already bound to the
        production database (either SQLite or PostgreSQL).

    :returns: A fully-wired resolver instance. Production callers
        invoke ``resolver.resolve(stage_name=..., calculation_type=...)``
        on the production entry point.
    """
    return ApprovedCoefficientResolver(
        read_port=SqlAlchemyCoefficientRevisionReadAdapter(engine),
        clock=SystemClock(),
    )


def compose_production_coefficient_approval_service(
    *,
    engine: Any,
    mutation_service: Any | None = None,
) -> CoefficientApprovalService:
    """Build a production :class:`CoefficientApprovalService`.

    The factory wires every Phase 4 Slice 1 port against the
    production engine. By default the factory constructs a
    :class:`DatabaseCoefficientService` bound to ``engine``, so
    the production approve / retire / submit paths go straight
    to the database.

    The default is **never** an in-memory
    :class:`CoefficientService`: production caller cannot
    accidentally invoke the parent in-memory class because the
    :class:`DatabaseCoefficientService` overrides every
    revision-mutation method.

    Callers that need to inject a different mutation target
    (e.g. for unit tests) can pass ``mutation_service=``. The
    argument name was renamed from ``in_memory_service`` (a
    pre-fixup misnomer) to ``mutation_service`` so that the
    default of None + the explicit ``DatabaseCoefficientService(engine)``
    fallback eliminates any silent in-memory production wiring.

    Note: this factory persists revision status, approval
    log rows, and audit log rows via the adapter stack. The
    transactional integrity of those three writes is enforced
    in :class:`TransactionalCoefficientApprovalRepository`
    (a separate concern; see commit 8 and the ``_TRANSACTIONAL``
    fields below). This factory wires the read / log /
    resolver adapters only.

    :param engine: A SQLAlchemy ``Engine``.
    :param mutation_service: Optional pre-constructed
        :class:`DatabaseCoefficientService` (or test double).
        When ``None`` (the production default) the factory
        constructs a fresh ``DatabaseCoefficientService(engine)``.
        The legacy ``in_memory_service`` kwarg is no longer
        accepted.

    :returns: A fully-wired approval service backed by the
        production engine. The legacy in-memory default was
        a fabrication; see commit 7 for the retract. Commit
        8 wires the transactional repository so the three
        writes (revision.status / audit_log / approval_log)
        commit in a single ``session.begin()``.
    """
    if mutation_service is None:
        mutation_target: Any = DatabaseCoefficientService(engine)
    else:
        mutation_target = mutation_service
    return CoefficientApprovalService(
        mutation_port=SqlAlchemyCoefficientMutationAdapter(mutation_target),
        approval_log=SqlAlchemyCoefficientApprovalLogAdapter(engine),
        audit_log=SqlAlchemyCoefficientAuditLogAdapter(engine),
        clock=SystemClock(),
        role_check=InMemoryRoleCheckAdapter(),
        transaction_port=TransactionalCoefficientApprovalRepository(engine),
    )


# ---------------------------------------------------------------------------
# Phase 4 Issue #35 Slice 2A — strict-resolver composition wiring.
#
# The factories below are additive: the existing
# ``compose_production_coefficient_resolver`` and
# ``compose_production_coefficient_approval_service`` factories are
# unchanged.  Slice 2A adds:
#
# 1. ``compose_production_coefficient_resolver_and_approval_service``
#    — a thin convenience that constructs both factories in one call.
#    Used by ``bootstrap.dependencies`` to populate the singleton
#    dict without duplicating wiring.
#
# 2. ``compose_production_source_binding_use_case_with_strict_resolver``
#    — builds a ``ProductionSourceBindingUseCase`` whose
#    ``coefficient_resolver`` slot is populated.  Callers that pass
#    ``use_case.coefficient_resolver`` (== non-None) traverse the
#    strict path; callers that pass a use case constructed without
#    this factory continue to run the legacy Phase 3 behaviour
#    verbatim — backward compat is therefore preserved.
# ---------------------------------------------------------------------------


def compose_production_coefficient_resolver_and_approval_service(
    *,
    engine: Any,
) -> tuple[ApprovedCoefficientResolver, CoefficientApprovalService]:
    """Return ``(resolver, approval_service)`` wired against ``engine``.

    The convenience factory exists so :func:`bootstrap.dependencies`
    can populate two singletons in one call instead of repeating the
    compose + store boilerplate. Both objects are constructed via
    the existing Slice 1 factories — no new port / adapter is added.

    :param engine: A SQLAlchemy ``Engine`` (SQLite or PostgreSQL).
    :returns: A 2-tuple ``(resolver, approval_service)``.
    """
    resolver = compose_production_coefficient_resolver(engine=engine)
    approval_service = compose_production_coefficient_approval_service(engine=engine)
    return resolver, approval_service


def compose_production_source_binding_use_case_with_strict_resolver(
    *,
    service: OrchestrationService,
    verification_read_port: Any = None,
    engine: Any,
) -> ProductionSourceBindingUseCase:
    """Build a :class:`ProductionSourceBindingUseCase` with the strict resolver wired in.

    The use case accepts an optional ``coefficient_resolver`` slot
    (see Slice 2A change to
    ``production_source_binding.ProductionSourceBindingUseCase``).
    When that slot is populated the use case performs a per-stage
    strict resolve of the five required stages before Transaction A
    runs.  When the slot is ``None`` (the legacy Phase 3 wiring)
    the use case behaves exactly as it did before Slice 2A — no
    code paths under ``coefficient_resolver is None`` were touched.

    :param service: A fully-wired :class:`OrchestrationService`.
    :param verification_read_port: Same role as in
        ``compose_production_source_binding_use_case``; defaults to
        ``None``.
    :param engine: A SQLAlchemy ``Engine`` for the resolver's read
        adapter.
    :returns: A use case whose ``coefficient_resolver`` is populated
        against the production engine.
    """
    if verification_read_port is None:
        from typing import cast

        from cold_storage.modules.orchestration.application.transaction_b import (
            VerificationReadPort,
        )

        verification_read_port = cast(VerificationReadPort, None)
    resolver = compose_production_coefficient_resolver(engine=engine)
    return ProductionSourceBindingUseCase(
        service=service,
        verification_read_port=verification_read_port,
        coefficient_resolver=resolver,
    )
