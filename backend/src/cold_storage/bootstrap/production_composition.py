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
    "compose_production_scheme_service",
    "compose_production_scheme_service_from_session",
]
