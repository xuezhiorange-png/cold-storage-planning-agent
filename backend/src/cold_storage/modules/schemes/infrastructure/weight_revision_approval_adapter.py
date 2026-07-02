"""SQLAlchemy adapter implementing WeightRevisionApprovalPort.

Infrastructure adapter for weight revision approval using CAS
(Compare-And-Swap) pattern.

Implements:
- Allowed status transitions (draft→approved, approved→superseded, approved→revoked)
- Approved immutability guard (rejects modifications to immutable fields)
- Seed consistency: rejects mismatched existing approved records
- Active-approved uniqueness enforced via scheme_weight_set_active_revisions
  authority table with composite PK (weight_set_id, code).  Provides atomic
  concurrent-safety for both SQLite and PostgreSQL.
- Database-level immutability triggers (P0-3) block direct ORM/SQL writes
  to immutable fields of approved revisions.
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

# ── Precise authority conflict classification ──────────────────────────────
# The authority table PK is (weight_set_id, code).
# PostgreSQL auto-names it: pk_scheme_weight_set_active_revisions
# SQLite names it: pk_scheme_weight_set_active_revisions (or similar)
_AUTHORITY_PK_CONSTRAINT = "pk_scheme_weight_set_active_revisions"
_AUTHORITY_TABLE = "scheme_weight_set_active_revisions"


def _is_authority_unique_conflict(exc: Any) -> bool:
    """Return True only if *exc* is an IntegrityError on the authority table PK.

    PostgreSQL: check SQLSTATE 23505 (unique_violation) + constraint name.
    SQLite: check error message contains the exact unique columns.
    """
    diag = getattr(exc, "orig", None)
    if diag is None:
        return False

    # PostgreSQL: psycopg2 Diagnostics object
    sqlstate = getattr(diag, "sqlstate", None)
    if sqlstate == "23505":
        # Unique violation — check constraint name
        constraint_name = getattr(diag, "constraint_name", None)
        if constraint_name == _AUTHORITY_PK_CONSTRAINT:
            return True
        # Fallback: check table name in the error
        table_name = getattr(diag, "table_name", None)
        if table_name == _AUTHORITY_TABLE:
            return True

    # SQLite: check error message for exact unique columns
    err_str = str(diag).lower()
    return (
        "unique constraint failed" in err_str
        and _AUTHORITY_TABLE in err_str
        and "weight_set_id" in err_str
        and "code" in err_str
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
    Uses scheme_weight_set_active_revisions authority table with composite
    PK (weight_set_id, code) for atomic concurrent-safe approval.
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

        Manages the active-revisions authority table:
          draft -> approved: claims authority row (atomic via UNIQUE PK)
          approved -> superseded/revoked: releases authority row

        Returns True if transitioned, False if CAS conflict.
        Raises InvalidStatusTransitionError if the transition is not allowed.
        """
        from sqlalchemy import delete, insert, select, update
        from sqlalchemy import exc as sa_exc

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetActiveRevisionRecord,
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
        values: dict[str, Any] = {"status": target_status}
        if target_status == "approved":
            if approved_at is None or approved_by is None:
                raise WeightRevisionGovernanceError(
                    "approval_evidence_required",
                    "approved_at and approved_by are required when transitioning to approved",
                )
            values["approved_at"] = approved_at
            values["approved_by"] = approved_by

        # For approval transitions, claim authority first (atomic via UNIQUE PK)
        if target_status == "approved":
            try:
                with session.begin_nested():
                    session.execute(
                        insert(SchemeWeightSetActiveRevisionRecord).values(
                            weight_set_id=current.weight_set_id,
                            code=current.code,
                            approved_revision_id=revision_id,
                            updated_at=approved_at,
                        )
                    )
            except sa_exc.IntegrityError as exc:
                if _is_authority_unique_conflict(exc):
                    raise WeightRevisionGovernanceError(
                        "active_revision_conflict",
                        f"Another revision is already approved for "
                        f"weight_set_id={current.weight_set_id}, code={current.code}",
                    ) from exc
                raise

        # CAS update
        result = session.execute(
            update(SchemeWeightSetRevisionRecord)
            .where(
                SchemeWeightSetRevisionRecord.id == revision_id,
                SchemeWeightSetRevisionRecord.status == current_status,
            )
            .values(**values)
        )

        if int(result.rowcount) == 1:
            if current_status == "approved":
                # Release authority row when deapproving
                session.execute(
                    delete(SchemeWeightSetActiveRevisionRecord).where(
                        SchemeWeightSetActiveRevisionRecord.approved_revision_id == revision_id,
                    )
                )
        elif target_status == "approved":
            # CAS failed after authority claimed — clean up
            session.execute(
                delete(SchemeWeightSetActiveRevisionRecord).where(
                    SchemeWeightSetActiveRevisionRecord.weight_set_id == current.weight_set_id,
                    SchemeWeightSetActiveRevisionRecord.code == current.code,
                    SchemeWeightSetActiveRevisionRecord.approved_revision_id == revision_id,
                )
            )

        return int(result.rowcount) == 1

    # ── Core approval with immutability + authority table guard ────────────

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
        the same weight_set_id + code via the authority table).
        Raises RevisionImmutabilityViolationError if trying to modify
        content of an already-approved revision.
        """
        from sqlalchemy import delete, insert, select, update
        from sqlalchemy import exc as sa_exc

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetActiveRevisionRecord,
            SchemeWeightSetRevisionRecord,
        )

        # Check if already approved — immutability guard
        existing = session.execute(
            select(SchemeWeightSetRevisionRecord).where(
                SchemeWeightSetRevisionRecord.id == revision_id,
            )
        ).scalar_one_or_none()
        if existing is None:
            return False

        if existing.status == "approved" and existing.content != content:
            changed: list[str] = ["content"]
            if existing.content_hash != _compute_content_hash(content):
                changed.append("content_hash")
            raise RevisionImmutabilityViolationError(revision_id, changed)

        # If already approved with same content, CAS conflict — nothing to do
        if existing.status == "approved":
            return False

        # Claim authority via UNIQUE composite PK (atomic)
        try:
            with session.begin_nested():
                session.execute(
                    insert(SchemeWeightSetActiveRevisionRecord).values(
                        weight_set_id=existing.weight_set_id,
                        code=existing.code,
                        approved_revision_id=revision_id,
                        updated_at=approved_at,
                    )
                )
        except sa_exc.IntegrityError as exc:
            if _is_authority_unique_conflict(exc):
                raise WeightRevisionGovernanceError(
                    "active_revision_conflict",
                    f"Another revision is already approved for "
                    f"weight_set_id={existing.weight_set_id}, code={existing.code}",
                ) from exc
            raise

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
                sealed_at=approved_at,
            )
        )

        if int(result.rowcount) == 0:
            # CAS failed — revision was not in 'draft' status.
            # Clean up the authority row we just inserted.
            session.execute(
                delete(SchemeWeightSetActiveRevisionRecord).where(
                    SchemeWeightSetActiveRevisionRecord.weight_set_id == existing.weight_set_id,
                    SchemeWeightSetActiveRevisionRecord.code == existing.code,
                    SchemeWeightSetActiveRevisionRecord.approved_revision_id == revision_id,
                )
            )
            return False

        return True

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
        from sqlalchemy import exc as sa_exc
        from sqlalchemy import insert, select

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetActiveRevisionRecord,
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
            # Claim authority row for this approval
            try:
                with session.begin_nested():
                    session.execute(
                        insert(SchemeWeightSetActiveRevisionRecord).values(
                            weight_set_id=weight_set_id,
                            code=code,
                            approved_revision_id=revision_id,
                            updated_at=approved_at,
                        )
                    )
            except sa_exc.IntegrityError as err:
                raise SeedConsistencyError(revision_id, ["authority_conflict"]) from err
        elif existing_rev.status == "draft":
            # Approve existing draft (handles authority table via approve_revision)
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
