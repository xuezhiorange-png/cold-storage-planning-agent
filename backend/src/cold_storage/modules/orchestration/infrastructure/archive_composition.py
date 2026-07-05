"""Production archive closure composition.

Cross-module seam that lets ``schemes.infrastructure.production_repository``
inject a real archive-writing closure via
``SqlAlchemyProductionSchemeRunRepository(build_archive_callable=...)``
without coupling the schemes module to the orchestration application
layer's ``build_archive_for_completed_scheme_run`` at import time.

The closure returned by :func:`make_production_archive_callable`:

    * Captures ``session`` at *call time* (not capture time), so the
      caller (UoW) keeps ownership of the transaction boundary.
    * Constructs ``SqlAlchemyProductionSourceArchiveRepository(session)``
      as a per-call adapter instance; this matches the application
      layer's expectation that the write port uses the live session.
    * Invokes the application builder
      (``build_archive_for_completed_scheme_run``) lazy-imported at
      first use, so module-load side effects are confined to the
      orchestration module.

The closure signature is ``Callable[[Any, Any], str]`` (compatible with
``schemes.infrastructure.production_repository.BuildArchiveCallable``):
it takes the live ``session`` and the persisted ``SchemeRun`` domain
shapes produced by ``_persist_run_record`` inside
``SqlAlchemyProductionSchemeRunRepository.save_production_run`` and
returns the new archive uuid.

Architecture notes
==================

* ``schemes.infrastructure.production_repository`` does NOT import this
  module.  Construction is left to the bootstrap / test that owns
  composition.
* Lazy imports are confined to this single function body.  Both
  ``orchestration.application.source_archive_builder`` and
  ``orchestration.infrastructure.source_archive_repository`` live
  within the same module (no cross-module dependency added here).
* This module stays in the ``orchestration.infrastructure`` tier; the
  ``schemes.infrastructure`` tier can import it because both are at
  the same architecture layer.

Frozen v1 contract
==================

The five source slots — *zone*, *cooling_load*, *equipment*, *power*,
*investment* — MUST be presented to the application builder as an
ordered sequence of ``(slot_name, slot_payload)`` tuples in that exact
order.  See ``canonical_archive_v1.SOURCE_SLOT_ORDER_V1``.  Hash
computation relies on the order; reordering or sorting destroys the
archive identity.  ``persisted_run`` carries the slots as five
individual ``*_calculation_id`` / ``*_result_hash`` fields; this
composer's job is to convert that flat representation into the
ordered sequence the builder requires.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# Slot order MUST match ``canonical_archive_v1.SOURCE_SLOT_ORDER_V1``.
# Each row maps the public slot name to the two ``PersistedSchemeRun``
# attribute names that hold its ``calculation_id`` and ``result_hash``.
_SLOT_FIELD_TABLE_V1: tuple[tuple[str, str, str], ...] = (
    ("zone", "zone_calculation_id", "zone_result_hash"),
    ("cooling_load", "cooling_load_calculation_id", "cooling_load_result_hash"),
    ("equipment", "equipment_calculation_id", "equipment_result_hash"),
    ("power", "power_calculation_id", "power_result_hash"),
    ("investment", "investment_calculation_id", "investment_result_hash"),
)


def _ordered_source_slots_v1(persisted_run: Any) -> list[tuple[str, dict[str, str]]]:
    """Project ``persisted_run`` into the v1 ordered slot sequence.

    Returns a ``list[tuple[str, dict[str, str]]]`` in fixed order
    (``zone`` … ``investment``).  Each slot payload carries the two
    identity strings the resolver uses to verify a source binding
    readback later: ``calculation_id`` and ``result_hash``.
    """
    slots: list[tuple[str, dict[str, str]]] = []
    for slot_name, calc_attr, hash_attr in _SLOT_FIELD_TABLE_V1:
        calc_id = getattr(persisted_run, calc_attr)
        result_hash = getattr(persisted_run, hash_attr)
        slots.append(
            (
                slot_name,
                {"calculation_id": calc_id, "result_hash": result_hash},
            )
        )
    return slots


def make_production_archive_callable() -> Callable[[Any, Any], str]:
    """Return a closure bound to ``SqlAlchemyProductionSourceArchiveRepository``.

    The returned callable conforms to the
    ``schemes.infrastructure.production_repository.BuildArchiveCallable``
    shape and is intended to be passed straight to
    ``SqlAlchemyProductionSchemeRunRepository(build_archive_callable=...)``.

    Lazy import: keep module-load side effects confined to the
    orchestration module.  The caller (a bootstrap, factory, or test)
    invokes this once at composition time, receives the closure, and
    passes it to the repository constructor.
    """

    def _archive_builder(session: Any, persisted_run: Any) -> str:
        """Construct write port + delegate to orchestration application builder.

        The closure expects ``persisted_run`` to expose the canonical
        flat attributes consumed by
        :func:`build_archive_for_completed_scheme_run`.  Raising
        ``AttributeError`` on a missing key is acceptable: the UoW rolls
        back, and the Schemes repository surfaces the same exception
        to ``ProductionSchemeService``, which converts it to a
        ``SchemeRunPersistenceError``.
        """
        # Lazy import: keeps schemes.infrastructure decoupled from
        # orchestration.application at module load.
        from cold_storage.modules.orchestration.application.source_archive_builder import (  # noqa: E501
            build_archive_for_completed_scheme_run,
        )
        from cold_storage.modules.orchestration.infrastructure.source_archive_repository import (  # noqa: E501
            SqlAlchemyProductionSourceArchiveRepository,
        )

        # Snapshot the persisted-run attributes.  We re-read through
        # ``getattr`` so this module stays clear of any cross-module
        # type re-export.
        source_slots: list[tuple[str, dict[str, str]]] = _ordered_source_slots_v1(persisted_run)

        write_port = SqlAlchemyProductionSourceArchiveRepository(session=session)
        archive_id = build_archive_for_completed_scheme_run(
            session=session,
            write_port=write_port,
            scheme_run_id=persisted_run.id,
            source_binding_id=persisted_run.source_binding_id,
            source_contract_version=persisted_run.source_contract_version,
            binding_schema_version=persisted_run.binding_schema_version,
            combined_source_hash=persisted_run.combined_source_hash,
            weight_set_revision_id=persisted_run.weight_set_revision_id,
            weight_set_content_hash=persisted_run.weight_set_content_hash,
            weight_set_generator_compatibility_version=(
                persisted_run.weight_set_generator_compatibility_version
            ),
            execution_snapshot_id=persisted_run.execution_snapshot_id,
            coefficient_context_id=persisted_run.coefficient_context_id,
            orchestration_identity_id=persisted_run.orchestration_identity_id,
            authoritative_attempt_id=persisted_run.authoritative_attempt_id,
            orchestration_fingerprint=persisted_run.orchestration_fingerprint,
            source_slots=source_slots,
            project_id=persisted_run.project_id,
            project_version_id=persisted_run.project_version_id,
            generator_compatibility_version=persisted_run.generator_version,
            actor="production.uow",
        )
        return archive_id

    return _archive_builder


__all__ = ["make_production_archive_callable"]
