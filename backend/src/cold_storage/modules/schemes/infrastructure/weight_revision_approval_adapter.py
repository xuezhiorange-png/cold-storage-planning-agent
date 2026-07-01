"""SQLAlchemy adapter implementing WeightRevisionApprovalPort.

Infrastructure adapter for weight revision approval using CAS
(Compare-And-Swap) pattern.
"""

from __future__ import annotations

from typing import Any

from cold_storage.modules.schemes.application.weight_revision_governance import (
    _compute_content_hash,
)


class SqlAlchemyWeightRevisionApprovalAdapter:
    """Infrastructure adapter implementing WeightRevisionApprovalPort.

    CAS (Compare-And-Swap) update: status=draft → approved, with
    approval evidence.  Rejects if current status is not 'draft'.
    Enforces active-approved uniqueness at the application layer.
    """

    def approve_revision(
        self,
        session: Any,
        *,
        revision_id: str,
        content: dict[str, Any],
        approved_at: Any,
        approved_by: str,
    ) -> bool:
        """CAS-approve a weight revision.

        Returns True if approved, False if CAS conflict (revision is
        not in 'draft' status).
        """
        from sqlalchemy import update

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRevisionRecord,
        )

        # CAS: only approve if currently 'draft'
        result = session.execute(
            update(SchemeWeightSetRevisionRecord)
            .where(
                SchemeWeightSetRevisionRecord.id == revision_id,
                SchemeWeightSetRevisionRecord.status == "draft",
            )
            .values(
                status="approved",
                approved_at=approved_at,
                approved_by=approved_by,
                content=content,
                content_hash=_compute_content_hash(content),
            )
        )
        return int(result.rowcount) == 1

    def has_approved_revision(
        self,
        session: Any,
        *,
        weight_set_id: str,
        code: str,
        exclude_revision_id: str | None = None,
    ) -> bool:
        """Check if an approved revision exists for weight_set_id + code."""
        from sqlalchemy import select

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRevisionRecord,
        )

        stmt = select(SchemeWeightSetRevisionRecord.id).where(
            SchemeWeightSetRevisionRecord.weight_set_id == weight_set_id,
            SchemeWeightSetRevisionRecord.code == code,
            SchemeWeightSetRevisionRecord.status == "approved",
        )
        if exclude_revision_id is not None:
            stmt = stmt.where(SchemeWeightSetRevisionRecord.id != exclude_revision_id)
        stmt = stmt.limit(1)
        return session.execute(stmt).scalar_one_or_none() is not None

    def seed_if_not_exists(
        self,
        session: Any,
        *,
        weight_set_id: str,
        code: str,
        name: str,
        revision_id: str,
        revision: int,
        content: dict[str, Any],
        generator_compatibility_version: str,
        approved_at: Any,
        approved_by: str,
    ) -> None:
        """Idempotently seed SchemeWeightSetRecord + SchemeWeightSetRevisionRecord.

        If the revision already exists and is approved, no-op.
        If it exists as draft, approve it.
        If it doesn't exist, create both records and approve.
        """
        from sqlalchemy import select

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRecord,
            SchemeWeightSetRevisionRecord,
        )

        # Ensure parent weight set exists
        existing_ws = session.execute(
            select(SchemeWeightSetRecord).where(SchemeWeightSetRecord.id == weight_set_id)
        ).scalar_one_or_none()
        if existing_ws is None:
            ws_rec = SchemeWeightSetRecord(
                id=weight_set_id,
                code=code,
                name=name,
                revision=revision,
                status="approved",
                source_type="system",
                criteria=content.get("criteria", []),
                requires_review=False,
                approved_at=approved_at,
            )
            session.add(ws_rec)
            session.flush()

        # Check if revision already exists
        existing_rev = session.execute(
            select(SchemeWeightSetRevisionRecord).where(
                SchemeWeightSetRevisionRecord.id == revision_id
            )
        ).scalar_one_or_none()

        content_hash = _compute_content_hash(content)

        if existing_rev is None:
            # Create revision record
            rev_rec = SchemeWeightSetRevisionRecord(
                id=revision_id,
                weight_set_id=weight_set_id,
                code=code,
                revision=revision,
                status="approved",
                content=content,
                content_hash=content_hash,
                generator_compatibility_version=generator_compatibility_version,
                approved_at=approved_at,
                approved_by=approved_by,
            )
            session.add(rev_rec)
            session.flush()
        elif existing_rev.status == "draft":
            # Approve existing draft
            self.approve_revision(
                session,
                revision_id=revision_id,
                content=content,
                approved_at=approved_at,
                approved_by=approved_by,
            )
        # else: already approved, no-op
