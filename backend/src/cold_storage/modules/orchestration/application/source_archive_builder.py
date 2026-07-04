"""Application-layer source archive builder.

Public entry point:

    build_archive_for_completed_scheme_run(
        session, write_port,
        *,
        scheme_run_id, source_binding_id, source_contract_version,
        binding_schema_version, combined_source_hash,
        weight_set_revision_id, weight_set_content_hash,
        weight_set_generator_compatibility_version,
        execution_snapshot_id, coefficient_context_id,
        orchestration_identity_id, authoritative_attempt_id,
        orchestration_fingerprint, source_slots,
        project_id, project_version_id, generator_compatibility_version,
        actor, captured_at=None,
    ) -> str  # archive_id

The builder:
    1. Validates inputs (source_mode=production invariants)
    2. Assembles the archive_payload using canonical_archive_v1
    3. Computes archive_hash = SHA-256(canonical_json_v1(payload))
    4. Delegates the INSERT to ``write_port.add_archive(...)``
    5. Does NOT commit/rollback the surrounding UoW

It does NOT import from
``cold_storage.modules.orchestration.infrastructure``; concrete SQL
insertion is the responsibility of the production binding infrastructure
adapter (see ``infrastructure.source_archive_repository``).

The ``session`` parameter is typed as ``Any`` so this module stays free
of SQLAlchemy imports.  The write port receives the session and is
responsible for using it.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from cold_storage.modules.orchestration.application.canonical_archive_v1 import (
    ALLOWED_REASONS,
    ARCHIVE_SCHEMA_VERSION_V1,
    REASON_COMPLETED,
    assemble_archive_payload,
    compute_archive_hash,
)
from cold_storage.modules.orchestration.application.ports import (
    ProductionSourceArchiveWritePort,
)
from cold_storage.modules.orchestration.domain.errors import (
    SourceArchiveBuildError,
)


def build_archive_for_completed_scheme_run(
    session: Any,
    write_port: ProductionSourceArchiveWritePort,
    *,
    scheme_run_id: str,
    source_binding_id: str | None,
    source_contract_version: str,
    binding_schema_version: str | None,
    combined_source_hash: str | None,
    weight_set_revision_id: str | None,
    weight_set_content_hash: str | None,
    weight_set_generator_compatibility_version: str | None,
    execution_snapshot_id: str | None,
    coefficient_context_id: str | None,
    orchestration_identity_id: str | None,
    authoritative_attempt_id: str | None,
    orchestration_fingerprint: str | None,
    source_slots: Mapping[str, dict[str, str]],
    project_id: str,
    project_version_id: str,
    generator_compatibility_version: str,
    actor: str,
    captured_at: datetime | None = None,
) -> str:
    """Build the archive row for a finished production SchemeRun.

    Returns the new archive uuid.  Re-raises SourceArchiveBuildError on
    any failure; in that case the caller is expected to roll back the UoW.

    The SQL INSERT is delegated to ``write_port`` (an infrastructure
    adapter) so this module never imports from
    ``cold_storage.modules.orchestration.infrastructure``.
    """
    if not isinstance(actor, str) or not actor:
        raise SourceArchiveBuildError(f"actor must be non-empty str, got {actor!r}")
    # Defensive — currently only 'completed' is implemented for the
    # forward-write path.  'pre_downgrade' is reserved for a future
    # migration helper.  We do NOT raise here because ALLOWED_REASONS
    # already contains REASON_COMPLETED; this is a no-op marker for
    # future readers.
    _ = REASON_COMPLETED in ALLOWED_REASONS

    captured = captured_at or datetime.now(UTC)

    # 1. Validate production invariants — source_binding_id and
    # combined_source_hash MUST be non-null for production SchemeRuns.
    # This mirrors the production-mode CHECK constraint on scheme_runs
    # (``ck_scheme_run_source_mode_nullity``).  We refuse here so an
    # archive row never references a NULL binding.
    if not source_binding_id:
        raise SourceArchiveBuildError(
            "production SchemeRun must have a non-null source_binding_id; "
            "archive refuses to be written for legacy SchemeRuns"
        )
    if not combined_source_hash:
        raise SourceArchiveBuildError(
            "production SchemeRun must have a non-null combined_source_hash"
        )

    # 2. Assemble payload.
    payload = assemble_archive_payload(
        scheme_run_id=scheme_run_id,
        source_binding_id=source_binding_id,
        source_contract_version=source_contract_version,
        binding_schema_version=binding_schema_version,
        combined_source_hash=combined_source_hash,
        weight_set_revision_id=weight_set_revision_id,
        weight_set_content_hash=weight_set_content_hash,
        weight_set_generator_compatibility_version=(weight_set_generator_compatibility_version),
        execution_snapshot_id=execution_snapshot_id,
        coefficient_context_id=coefficient_context_id,
        orchestration_identity_id=orchestration_identity_id,
        authoritative_attempt_id=authoritative_attempt_id,
        orchestration_fingerprint=orchestration_fingerprint,
        source_slots=dict(source_slots),
        project_id=project_id,
        project_version_id=project_version_id,
        generator_compatibility_version=generator_compatibility_version,
        captured_at=captured,
    )

    # 3. Compute archive_hash (also defends against binary floats).
    archive_hash = compute_archive_hash(payload)

    # 4. Delegate the INSERT to the infrastructure adapter.
    archive_id = str(uuid4())
    write_port.add_archive(
        session,
        archive_id=archive_id,
        scheme_run_id=scheme_run_id,
        source_binding_id=source_binding_id,
        source_contract_version=source_contract_version,
        archive_schema_version=ARCHIVE_SCHEMA_VERSION_V1,
        archive_payload=payload,
        archive_hash=archive_hash,
        combined_source_hash=combined_source_hash,
        weight_set_revision_id=weight_set_revision_id,
        weight_set_content_hash=weight_set_content_hash,
        binding_schema_version=binding_schema_version,
        execution_snapshot_id=execution_snapshot_id,
        coefficient_context_id=coefficient_context_id,
        orchestration_identity_id=orchestration_identity_id,
        authoritative_attempt_id=authoritative_attempt_id,
        orchestration_fingerprint=orchestration_fingerprint,
        created_at=captured,
        created_by=actor,
        reason=REASON_COMPLETED,
    )

    return archive_id
