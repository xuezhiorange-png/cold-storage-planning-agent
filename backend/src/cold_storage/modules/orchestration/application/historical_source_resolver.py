"""Historical source resolver for SchemeRun reads.

Public entry point::

    resolve_scheme_run_sources_for_history(
        session, scheme_run_row,
        *,
        read_port, online_source_lookup,
    ) -> ResolvedSchemeRunSources

Decision tree (matches design contract):
    1. scheme_run_row.source_mode == 'legacy'
       → return LegacySourceBundle (no archive needed)
    2. Try online source binding lookup
       → if successful and verifies → return VerifiedOnlineSourceBundle
    3. online lookup fails OR not present
       → load production_source_archives[scheme_run_id] via read_port
       → if archive missing → raise SchemeRunHistoricalSourceUnavailableError
       → if archive_schema_version is unknown
         → raise SchemeSourceArchiveUnsupportedSchemaError
       → recompute archive_hash from archive_payload
         → if mismatch → raise SchemeSourceArchiveIntegrityError
       → if archive.combined_source_hash != scheme_run.combined_source_hash
         → raise SchemeRunHistoricalSourceTamperedError(field='combined_source_hash')
       → check each source_slot.result_hash against the SchemeRun row's
         ``*_result_hash`` columns
         → first mismatch raises SchemeRunHistoricalSourceTamperedError(field=<slot>)
       → check archive.weight_set_content_hash matches scheme_run
       → check archive.binding_schema_version matches scheme_run
       → return VerifiedArchiveSourceBundle

The module does NOT import SQLAlchemy.  ``session`` is typed as Any;
``read_port`` and ``online_source_lookup`` are callables supplied by the
caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from cold_storage.modules.orchestration.application.canonical_archive_v1 import (
    ARCHIVE_SCHEMA_VERSION_V1 as _EXPORTER_ARCHIVE_SCHEMA_V1,
)
from cold_storage.modules.orchestration.application.ports import (
    ProductionSourceArchiveReadPort,
)
from cold_storage.modules.orchestration.domain.errors import (
    SchemeRunHistoricalSourceTamperedError,
    SchemeRunHistoricalSourceUnavailableError,
    SchemeSourceArchiveIntegrityError,
    SchemeSourceArchiveUnsupportedSchemaError,
)

# Application uses its own canonical ARCHIVE_SCHEMA_VERSION_V1 re-export.
ARCHIVE_SCHEMA_VERSION_V1 = _EXPORTER_ARCHIVE_SCHEMA_V1


# Mapping scheme_run_row column name -> archive source_slots key.
# These mirror the SchemeRunRecord column names from migration 0029 and
# the source_slots contract in canonical_archive_v1.
# Wrapped in MappingProxyType so it is read-only at runtime
# (architecture rule: no module-level mutable singletons).
_SLOT_TO_SCHEME_RUN_COLUMN_INNER = {
    "zone": "zone_result_hash",
    "cooling_load": "cooling_load_result_hash",
    "equipment": "equipment_result_hash",
    "power": "power_result_hash",
    "investment": "investment_result_hash",
}
SLOT_TO_SCHEME_RUN_COLUMN: Mapping[str, str] = MappingProxyType(
    _SLOT_TO_SCHEME_RUN_COLUMN_INNER
)


# ── Result bundles ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class LegacySourceBundle:
    """A legacy SchemeRun has no archive and no online source to verify."""

    scheme_run_id: str
    source_mode: str  # always 'legacy' here


@dataclass(frozen=True, slots=True)
class VerifiedOnlineSourceBundle:
    """SchemeRun is a production run whose online source is still verifiable."""

    scheme_run_id: str
    source_binding_id: str
    combined_source_hash: str
    source_slots: Mapping[str, Mapping[str, str]]


@dataclass(frozen=True, slots=True)
class VerifiedArchiveSourceBundle:
    """SchemeRun is a production run read from the frozen archive."""

    scheme_run_id: str
    archive_id: str
    archive_hash: str
    combined_source_hash: str
    source_slots: Mapping[str, Mapping[str, str]]
    captured_at: datetime


ResolvedSchemeRunSources = (
    LegacySourceBundle | VerifiedOnlineSourceBundle | VerifiedArchiveSourceBundle
)


# ── Online source lookup protocol ───────────────────────────────────────────


class OnlineSchemeRunSourceLookupPort(Protocol):
    """Read-only online lookup for SchemeRun source identity.

    Returns a dict-shaped snapshot of the SchemeRun's online source
    bindings + slot result hashes, or None if no binding exists.

    Implementations live in infrastructure — typically in the schemes
    module's SourceBinding read port.  This Protocol lives in the
    orchestration application layer so the orchestration resolver does
    not depend on the schemes module's infrastructure directly.
    """

    def find_online_scheme_run_sources(
        self,
        session: Any,
        scheme_run_id: str,
    ) -> Mapping[str, Any] | None:
        """Return online source binding snapshot, or None if absent.

        Contract: the returned mapping MUST contain at least
        ``source_binding_id`` (str), ``combined_source_hash`` (str),
        and ``source_slots`` (dict[str, dict[str, str]]) populated with
        at least the five canonical slots.
        """
        ...


# ── Resolver entry point ────────────────────────────────────────────────────


def resolve_scheme_run_sources_for_history(
    session: Any,
    scheme_run_row: Mapping[str, Any],
    *,
    read_port: ProductionSourceArchiveReadPort,
    online_source_lookup: OnlineSchemeRunSourceLookupPort | None = None,
) -> ResolvedSchemeRunSources:
    """Resolve the historical source identity for a SchemeRun.

    Parameters
    ----------
    session :
        An active SQLAlchemy session (typed as Any; infrastructure owns
        the binding).
    scheme_run_row :
        A read snapshot of the SchemeRun.  Must expose ``id``,
        ``source_mode``, and (for production SchemeRuns) the
        ``combined_source_hash`` plus the five ``*_result_hash`` columns.
    read_port :
        ProductionSourceArchiveReadPort (already implemented in
        infrastructure layer).
    online_source_lookup :
        Optional callable that returns the online SourceBinding snapshot.
        If None, the resolver skips the online lookup and goes straight
        to the archive read.
    """
    scheme_run_id = scheme_run_row["id"]
    source_mode = scheme_run_row.get("source_mode", "legacy")

    # 1. Legacy SchemeRuns never participate in archive resolution.
    if source_mode == "legacy":
        return LegacySourceBundle(scheme_run_id=scheme_run_id, source_mode="legacy")

    if source_mode != "production":
        # Defensive — only legacy/production are valid modes.
        raise SchemeRunHistoricalSourceUnavailableError(scheme_run_id)

    # 2. Try online first.
    if online_source_lookup is not None:
        online = online_source_lookup.find_online_scheme_run_sources(
            session, scheme_run_id
        )
        if online is not None:
            return VerifiedOnlineSourceBundle(
                scheme_run_id=scheme_run_id,
                source_binding_id=online["source_binding_id"],
                combined_source_hash=online["combined_source_hash"],
                source_slots=online["source_slots"],
            )

    # 3. Online missing → load archive.
    archive_row = read_port.find_by_scheme_run_id(session, scheme_run_id)
    if archive_row is None:
        # 4. Neither online nor archive → fail closed.
        raise SchemeRunHistoricalSourceUnavailableError(scheme_run_id)

    # 5. Validate archive_schema_version.
    archive_schema_version = archive_row.get("archive_schema_version")
    if archive_schema_version != ARCHIVE_SCHEMA_VERSION_V1:
        raise SchemeSourceArchiveUnsupportedSchemaError(
            scheme_run_id, archive_schema_version or "<missing>"
        )

    # 6. Recompute archive_hash and compare.
    payload = archive_row["archive_payload"]
    from cold_storage.modules.orchestration.application.canonical_archive_v1 import (  # noqa: I001  # lazy import avoids circular import
        compute_archive_hash_v1,
    )
    recomputed = compute_archive_hash_v1(payload)
    if recomputed != archive_row["archive_hash"]:
        raise SchemeSourceArchiveIntegrityError(archive_hash=archive_row["archive_hash"])

    # 7. Compare combined_source_hash.
    expected_combined = scheme_run_row.get("combined_source_hash")
    if expected_combined is None or expected_combined != archive_row["combined_source_hash"]:
        raise SchemeRunHistoricalSourceTamperedError(
            scheme_run_id, field="combined_source_hash"
        )

    # 8. Compare per-slot result_hashes.
    archive_slots = archive_row["source_slots"]
    for slot_key, column_name in SLOT_TO_SCHEME_RUN_COLUMN.items():
        if slot_key not in archive_slots:
            raise SchemeRunHistoricalSourceTamperedError(
                scheme_run_id, field=f"source_slots.{slot_key}"
            )
        archive_slot_hash = archive_slots[slot_key].get("result_hash")
        scheme_slot_hash = scheme_run_row.get(column_name)
        if scheme_slot_hash != archive_slot_hash:
            raise SchemeRunHistoricalSourceTamperedError(
                scheme_run_id, field=column_name
            )

    # 9. Compare weight_set_content_hash and binding_schema_version.
    if scheme_run_row.get("weight_set_content_hash") != archive_row.get(
        "weight_set_content_hash"
    ):
        raise SchemeRunHistoricalSourceTamperedError(
            scheme_run_id, field="weight_set_content_hash"
        )
    if scheme_run_row.get("binding_schema_version") != archive_row.get(
        "binding_schema_version"
    ):
        raise SchemeRunHistoricalSourceTamperedError(
            scheme_run_id, field="binding_schema_version"
        )

    # 10. All checks pass.
    return VerifiedArchiveSourceBundle(
        scheme_run_id=scheme_run_id,
        archive_id=archive_row["id"],
        archive_hash=archive_row["archive_hash"],
        combined_source_hash=archive_row["combined_source_hash"],
        source_slots=archive_slots,
        captured_at=archive_row["created_at"],
    )
