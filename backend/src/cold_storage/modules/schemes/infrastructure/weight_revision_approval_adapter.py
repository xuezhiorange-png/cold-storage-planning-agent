"""SQLAlchemy adapter implementing WeightRevisionApprovalPort.

Infrastructure adapter for weight revision approval using CAS
(Compare-And-Swap) pattern.

Implements:
- Allowed status transitions (draft→approved, approved→superseded, approved→revoked)
- Approved immutability guard (rejects modifications to immutable fields)
- Seed consistency: rejects mismatched existing approved records
- Active-approved uniqueness enforced at application layer (SQLite cannot
  use partial unique indexes; PostgreSQL uses a partial unique index as
  defense-in-depth).
"""

from __future__ import annotations

from typing import Any

from cold_storage.modules.schemes.application.weight_revision_governance import (
    WeightRevisionGovernanceError,
    _compute_content_hash,
)

# ── Allowed status transitions ─────────────────────────────────────────────

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"approved"}),
    "approved": frozenset({"superseded", "revoked"}),
}

# ── Immutable fields (must not change once approved) ──────────────────────

_IMMUTABLE_FIELDS: frozenset[str] = frozenset(
    {
        "content",
        "content_hash",
        "code",
        "revision",
        "weight_set_id",
        "generator_compatibility_version",
    }
)


class InvalidStatusTransitionError(WeightRevisionGovernanceError):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(
            "invalid_status_transition",
            f"Cannot transition from {current!r} to {target!r}; "
            f"allowed transitions: {_ALLOWED_TRANSITIONS.get(current, frozenset())}",
        )


class RevisionImmutabilityViolationError(WeightRevisionGovernanceError):
    def __init__(self, revision_id: str, fields: list[str]) -> None:
        super().__init__(
            "revision_immutability_violation",
            f"Revision {revision_id!r} is approved; cannot modify "
            f"immutable fields: {', '.join(sorted(fields))}",
        )


class SeedConsistencyError(WeightRevisionGovernanceError):
    def __init__(self, revision_id: str, mismatched_fields: list[str]) -> None:
        super().__init__(
            "seed_consistency_mismatch",
            f"Seed revision {revision_id!r} already exists as approved "
            f"but mismatches on fields: {', '.join(sorted(mismatched_fields))}; "
            f"rejecting to prevent silent data corruption",
        )


class SqlAlchemyWeightRevisionApprovalAdapter:
    """Infrastructure adapter implementing WeightRevisionApprovalPort.

    CAS (Compare-And-Swap) update: status=draft -> approved, with
    approval evidence.  Rejects if current status is not 'draft'.
    Enforces active-approved uniqueness at the application layer.
    """

    # ── Status transitions ────────────────────────────────────────────────

    def change_status(
        self,
        session: Any,
        *,
        revision_id: str,
        target_status: str,
        approved_at: Any | None = None,
        approved_by: str | None = None,
    ) -> bool:
        """Transition a revision's status with CAS protection.

        Enforces allowed transitions:
          draft -> approved
          approved -> superseded
          approved -> revoked

        Returns True if transitioned, False if CAS conflict.
        Raises InvalidStatusTransitionError if the transition is not allowed.
        """
        from sqlalchemy import select

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRevisionRecord,
        )

        # Read current status
        current = session.execute(
            select(SchemeWeightSetRevisionRecord).where(
                SchemeWeightSetRevisionRecord.id == revision_id,
            )
        ).scalar_one_or_none()
        if current is None:
            return False

        current_status = current.status
        allowed = _ALLOWED_TRANSITIONS.get(current_status, frozenset())
        if target_status not in allowed:
            raise InvalidStatusTransitionError(current_status, target_status)

        # Build update values
        from sqlalchemy import update

        values: dict[str, Any] = {"status": target_status}
        if target_status == "approved":
            if approved_at is None or approved_by is None:
                raise WeightRevisionGovernanceError(
                    "approval_evidence_required",
                    "approved_at and approved_by are required when transitioning to approved",
                )
            values["approved_at"] = approved_at
            values["approved_by"] = approved_by

        result = session.execute(
            update(SchemeWeightSetRevisionRecord)
            .where(
                SchemeWeightSetRevisionRecord.id == revision_id,
                SchemeWeightSetRevisionRecord.status == current_status,
            )
            .values(**values)
        )
        return int(result.rowcount) == 1

    # ── Core approval with immutability + uniqueness guard ────────────────

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
        not in 'draft' status or another approved revision exists for
        the same weight_set_id + code).
        Raises RevisionImmutabilityViolationError if trying to modify
        content of an already-approved revision.
        """
        from sqlalchemy import select, update

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRevisionRecord,
        )

        # Check if already approved — immutability guard
        existing = session.execute(
            select(SchemeWeightSetRevisionRecord).where(
                SchemeWeightSetRevisionRecord.id == revision_id,
            )
        ).scalar_one_or_none()
        if existing is not None and existing.status == "approved" and existing.content != content:
            changed: list[str] = ["content"]
            if existing.content_hash != _compute_content_hash(content):
                changed.append("content_hash")
            raise RevisionImmutabilityViolationError(revision_id, changed)

        # Active-approved uniqueness: check if another revision for the
        # same weight_set_id + code is already approved
        if existing is not None:
            other_approved = self.has_approved_revision(
                session,
                weight_set_id=existing.weight_set_id,
                code=existing.code,
                exclude_revision_id=revision_id,
            )
            if other_approved:
                return False

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

    # ── Seed with consistency verification ────────────────────────────────

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

        If the revision already exists and is approved, verify all identity
        fields match.  Reject on mismatch to prevent silent data corruption.
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
        elif existing_rev.status == "approved":
            # Seed consistency: verify all identity/content fields match
            mismatched: list[str] = []
            if existing_rev.weight_set_id != weight_set_id:
                mismatched.append("weight_set_id")
            if existing_rev.code != code:
                mismatched.append("code")
            if existing_rev.revision != revision:
                mismatched.append("revision")
            if existing_rev.content_hash != content_hash:
                mismatched.append("content_hash")
            if existing_rev.generator_compatibility_version != generator_compatibility_version:
                mismatched.append("generator_compatibility_version")
            if mismatched:
                raise SeedConsistencyError(revision_id, mismatched)
            # else: already approved with matching fields — no-op
