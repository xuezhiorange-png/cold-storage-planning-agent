"""Persistence-backed coefficient resolution adapter.

Queries the real coefficient catalog (coefficient_definitions +
coefficient_revisions) from the current Transaction A session to
produce a ``ResolvedCoefficientContextCandidate``.

Caller self-attestation (source_type, validity_status, approved, etc.
in ``coefficient_resolution_context``) is NEVER accepted as proof
of approval.  Only database records with ``status='approved'`` are
treated as authority.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from cold_storage.modules.coefficients.infrastructure.orm import (
    CoefficientDefinitionRecord,
    CoefficientRevisionRecord,
)
from cold_storage.modules.orchestration.application.ports import (
    ResolvedCoefficientContextCandidate,
)
from cold_storage.modules.orchestration.domain.errors import (
    AmbiguousCoefficientError,
    CoefficientNotApprovedError,
    CoefficientResolutionError,
)
from cold_storage.modules.orchestration.domain.fingerprint import result_hash


class SqlAlchemyCoefficientResolutionAdapter:
    """Resolve approved coefficient context from the database catalog.

    Queries ``coefficient_definitions`` + ``coefficient_revisions`` within
    the caller's session.  Never trusts caller-provided approval flags.

    Canonical order: approved revisions sorted by
    ``revision_number DESC`` (most recent first), then ``revision_id ASC``
    for deterministic tie-breaking.
    """

    _SUPPORTED_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1.0.0"})

    def resolve(
        self,
        *,
        project_id: str,
        project_version_id: str,
        coefficient_resolution_context: dict[str, object],
        session: object | None = None,
    ) -> ResolvedCoefficientContextCandidate:
        if session is None:
            raise CoefficientResolutionError(
                "resolver",
                "Persistence-backed resolver requires a session",
            )

        if not isinstance(session, Session):
            raise CoefficientResolutionError(
                "resolver",
                f"Expected SQLAlchemy Session, got {type(session).__name__}",
            )

        # 1 — Find all approved revisions (ignoring caller-supplied flags)
        approved_revisions = self._query_approved_revisions(session)

        if not approved_revisions:
            raise CoefficientNotApprovedError("no_approved_revisions")

        # 2 — Canonical order: revision_number DESC, id ASC
        approved_revisions.sort(key=lambda r: (-r.revision_number, r.id))

        approved_ids = tuple(r.id for r in approved_revisions)

        # 3 — Build the resolved content from the catalog, not caller context
        content: dict[str, object] = {
            "source_type": "catalog",
            "resolver": "SqlAlchemyCoefficientResolutionAdapter",
            "schema_version": "1.0.0",
            "project_id": project_id,
            "project_version_id": project_version_id,
            "coefficient_count": len(approved_revisions),
            "coefficients": [
                {
                    "definition_id": r.coefficient_definition_id,
                    "revision_id": r.id,
                    "revision_number": r.revision_number,
                    "code": self._definition_code(session, r.coefficient_definition_id),
                    "status": r.status,
                    "unit": r.unit,
                    "source_type": r.source_type,
                    "approved_at": r.approved_at.isoformat() if r.approved_at else None,
                }
                for r in approved_revisions
            ],
        }

        return ResolvedCoefficientContextCandidate(
            project_id=project_id,
            project_version_id=project_version_id,
            schema_version="1.0.0",
            content=content,
            content_hash=result_hash(content),
            approved_revision_ids=approved_ids,
        )

    def _query_approved_revisions(
        self, session: Session
    ) -> list[CoefficientRevisionRecord]:
        """Return all approved coefficient revisions from the database.

        Only records with status='approved' are returned.  Caller-supplied
        coefficient_resolution_context flags are IGNORED.
        """
        from sqlalchemy import select

        now = datetime.now(UTC)
        stmt = (
            select(CoefficientRevisionRecord)
            .where(
                CoefficientRevisionRecord.status == "approved",
                CoefficientRevisionRecord.approved_at.isnot(None),
                # valid_from <= now (or NULL)
                (
                    CoefficientRevisionRecord.valid_from.is_(None)
                    | (CoefficientRevisionRecord.valid_from <= now)
                ),
                # valid_to >= now (or NULL)
                (
                    CoefficientRevisionRecord.valid_to.is_(None)
                    | (CoefficientRevisionRecord.valid_to >= now)
                ),
            )
            .order_by(
                CoefficientRevisionRecord.revision_number.desc(),
                CoefficientRevisionRecord.id.asc(),
            )
        )
        return list(session.execute(stmt).scalars().all())

    def _definition_code(self, session: Session, definition_id: str) -> str:
        """Lookup the coefficient code for a definition ID."""
        from sqlalchemy import select

        row = session.execute(
            select(CoefficientDefinitionRecord.code).where(
                CoefficientDefinitionRecord.id == definition_id
            )
        ).scalar_one_or_none()
        return row if row else f"unknown:{definition_id}"
