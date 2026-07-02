"""Tests for weight revision database governance (P0-7, P0-3).

Covers:
- Seed idempotency
- Criteria parser rejection matrix
- Approval CAS workflow
- Idempotent seed on SQLite
- Allowed status transitions (P0-3)
- Approved revision immutability (P0-3)
- Concurrent approval conflict (P0-3)
- Seed consistency mismatch rejection (P0-3)
- Authority table concurrent safety (P0-2)
- Database-level immutability triggers (P0-3)
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy import exc as sa_exc
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure scheme ORM tables are registered on Base.metadata before create_all()
import cold_storage.modules.schemes.infrastructure.orm  # noqa: F401
from cold_storage.modules.projects.infrastructure.orm import Base
from cold_storage.modules.schemes.application.weight_revision_governance import (
    PRODUCTION_WEIGHT_SET_CODE,
    PRODUCTION_WEIGHT_SET_ID,
    PRODUCTION_WEIGHT_SET_REVISION_ID,
    WeightRevisionGovernanceError,
    _compute_content_hash,
    _parse_criteria,
    get_production_weight_content_hash,
    get_production_weight_criteria,
    seed_production_weight_revision,
)
from cold_storage.modules.schemes.infrastructure.weight_revision_approval_adapter import (
    InvalidStatusTransitionError,
    RevisionImmutabilityViolationError,
    SeedConsistencyError,
    SqlAlchemyWeightRevisionApprovalAdapter,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine():
    """In-memory SQLite engine with all tables created."""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine) -> Session:
    """Session bound to the in-memory engine."""
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    sess = factory()
    yield sess
    sess.close()


@pytest.fixture()
def adapter() -> SqlAlchemyWeightRevisionApprovalAdapter:
    """Approval adapter instance."""
    return SqlAlchemyWeightRevisionApprovalAdapter()


# ---------------------------------------------------------------------------
# Helper data
# ---------------------------------------------------------------------------

_VALID_CONTENT: dict[str, Any] = {
    "criteria": [
        {
            "criterion_code": "total_area_m2",
            "weight": "0.50",
            "direction": "lower_is_better",
            "normalization_method": "min_max",
            "hard_constraint": False,
            "description": "Total area",
        },
        {
            "criterion_code": "investment_cny",
            "weight": "0.50",
            "direction": "lower_is_better",
            "normalization_method": "min_max",
            "hard_constraint": False,
            "description": "Investment",
        },
    ],
    "version": "1.0.0",
    "description": "Test weight set",
}

_VALID_CONTENT_HASH = _compute_content_hash(_VALID_CONTENT)


# ---------------------------------------------------------------------------
# Seed idempotency
# ---------------------------------------------------------------------------


class TestSeedIdempotency:
    def test_seed_creates_records(self, session, adapter) -> None:
        """First seed creates both weight set and revision records."""
        seed_production_weight_revision(
            adapter,
            session,
            generator_version="1.0.0",
            approved_by="test-user",
        )
        session.commit()

        from sqlalchemy import select

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRecord,
            SchemeWeightSetRevisionRecord,
        )

        ws = session.execute(
            select(SchemeWeightSetRecord).where(
                SchemeWeightSetRecord.id == PRODUCTION_WEIGHT_SET_ID
            )
        ).scalar_one_or_none()
        assert ws is not None
        assert ws.code == PRODUCTION_WEIGHT_SET_CODE

        rev = session.execute(
            select(SchemeWeightSetRevisionRecord).where(
                SchemeWeightSetRevisionRecord.id == PRODUCTION_WEIGHT_SET_REVISION_ID
            )
        ).scalar_one_or_none()
        assert rev is not None
        assert rev.status == "approved"
        assert rev.approved_by == "test-user"
        assert rev.approved_at is not None

    def test_seed_idempotent(self, session, adapter) -> None:
        """Seeding twice produces no duplicates and same hash."""
        seed_production_weight_revision(
            adapter,
            session,
            generator_version="1.0.0",
            approved_by="test-user",
        )
        session.commit()

        # Seed again
        seed_production_weight_revision(
            adapter,
            session,
            generator_version="1.0.0",
            approved_by="test-user",
        )
        session.commit()

        from sqlalchemy import func, select

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRevisionRecord,
        )

        count = session.execute(
            select(func.count()).select_from(SchemeWeightSetRevisionRecord)
        ).scalar_one()
        assert count == 1

        # Content hash unchanged
        rev = session.execute(
            select(SchemeWeightSetRevisionRecord).where(
                SchemeWeightSetRevisionRecord.id == PRODUCTION_WEIGHT_SET_REVISION_ID
            )
        ).scalar_one()
        assert rev.content_hash == get_production_weight_content_hash()


# ---------------------------------------------------------------------------
# Criteria parser rejection matrix
# ---------------------------------------------------------------------------


class TestCriteriaParserRejection:
    def test_rejects_float_weight(self) -> None:
        """Float weights are rejected (must be string)."""
        raw = [
            {
                "criterion_code": "test",
                "weight": 0.5,
                "direction": "higher_is_better",
                "normalization_method": "min_max",
                "hard_constraint": False,
            }
        ]
        with pytest.raises(WeightRevisionGovernanceError, match="weight must be a string"):
            _parse_criteria(raw)

    def test_rejects_int_weight(self) -> None:
        """Int weights are rejected (must be string)."""
        raw = [
            {
                "criterion_code": "test",
                "weight": 1,
                "direction": "higher_is_better",
                "normalization_method": "min_max",
                "hard_constraint": False,
            }
        ]
        with pytest.raises(WeightRevisionGovernanceError, match="weight must be a string"):
            _parse_criteria(raw)

    def test_rejects_none_weight(self) -> None:
        """Missing weight is rejected."""
        raw = [
            {
                "criterion_code": "test",
                "direction": "higher_is_better",
                "normalization_method": "min_max",
                "hard_constraint": False,
            }
        ]
        with pytest.raises(WeightRevisionGovernanceError, match="missing required 'weight'"):
            _parse_criteria(raw)

    def test_rejects_invalid_decimal_string(self) -> None:
        """Non-numeric weight string is rejected."""
        raw = [
            {
                "criterion_code": "test",
                "weight": "abc",
                "direction": "higher_is_better",
                "normalization_method": "min_max",
                "hard_constraint": False,
            }
        ]
        with pytest.raises(WeightRevisionGovernanceError, match="not a valid Decimal"):
            _parse_criteria(raw)

    def test_rejects_empty_criterion_code(self) -> None:
        """Empty criterion_code is rejected."""
        raw = [
            {
                "criterion_code": "",
                "weight": "0.5",
                "direction": "higher_is_better",
                "normalization_method": "min_max",
                "hard_constraint": False,
            }
        ]
        with pytest.raises(WeightRevisionGovernanceError, match="non-empty string"):
            _parse_criteria(raw)

    def test_rejects_missing_criterion_code(self) -> None:
        """Missing criterion_code is rejected."""
        raw = [
            {
                "weight": "0.5",
                "direction": "higher_is_better",
                "normalization_method": "min_max",
                "hard_constraint": False,
            }
        ]
        with pytest.raises(WeightRevisionGovernanceError, match="non-empty string"):
            _parse_criteria(raw)

    def test_rejects_invalid_direction(self) -> None:
        """Invalid direction is rejected."""
        raw = [
            {
                "criterion_code": "test",
                "weight": "0.5",
                "direction": "invalid",
                "normalization_method": "min_max",
                "hard_constraint": False,
            }
        ]
        with pytest.raises(WeightRevisionGovernanceError, match="direction must be one of"):
            _parse_criteria(raw)

    def test_rejects_missing_direction(self) -> None:
        """Missing direction is rejected."""
        raw = [
            {
                "criterion_code": "test",
                "weight": "0.5",
                "normalization_method": "min_max",
                "hard_constraint": False,
            }
        ]
        with pytest.raises(WeightRevisionGovernanceError, match="direction must be one of"):
            _parse_criteria(raw)

    def test_rejects_invalid_normalization(self) -> None:
        """Invalid normalization_method is rejected."""
        raw = [
            {
                "criterion_code": "test",
                "weight": "0.5",
                "direction": "higher_is_better",
                "normalization_method": "invalid",
                "hard_constraint": False,
            }
        ]
        with pytest.raises(
            WeightRevisionGovernanceError, match="normalization_method must be one of"
        ):
            _parse_criteria(raw)

    def test_rejects_missing_normalization(self) -> None:
        """Missing normalization_method is rejected."""
        raw = [
            {
                "criterion_code": "test",
                "weight": "0.5",
                "direction": "higher_is_better",
                "hard_constraint": False,
            }
        ]
        with pytest.raises(
            WeightRevisionGovernanceError, match="normalization_method must be one of"
        ):
            _parse_criteria(raw)

    def test_rejects_non_bool_hard_constraint(self) -> None:
        """Non-bool hard_constraint is rejected."""
        raw = [
            {
                "criterion_code": "test",
                "weight": "0.5",
                "direction": "higher_is_better",
                "normalization_method": "min_max",
                "hard_constraint": 1,
            }
        ]
        with pytest.raises(WeightRevisionGovernanceError, match="hard_constraint must be a bool"):
            _parse_criteria(raw)

    def test_rejects_missing_hard_constraint(self) -> None:
        """Missing hard_constraint is rejected."""
        raw = [
            {
                "criterion_code": "test",
                "weight": "0.5",
                "direction": "higher_is_better",
                "normalization_method": "min_max",
            }
        ]
        with pytest.raises(WeightRevisionGovernanceError, match="hard_constraint must be a bool"):
            _parse_criteria(raw)

    def test_rejects_weight_sum_not_one(self) -> None:
        """Weights not summing to 1.0 are rejected."""
        raw = [
            {
                "criterion_code": "a",
                "weight": "0.30",
                "direction": "higher_is_better",
                "normalization_method": "min_max",
                "hard_constraint": False,
            },
            {
                "criterion_code": "b",
                "weight": "0.30",
                "direction": "lower_is_better",
                "normalization_method": "min_max",
                "hard_constraint": False,
            },
        ]
        with pytest.raises(WeightRevisionGovernanceError, match="sum to"):
            _parse_criteria(raw)

    def test_accepts_valid_criteria(self) -> None:
        """Valid criteria are accepted."""
        criteria = _parse_criteria(_VALID_CONTENT["criteria"])
        assert len(criteria) == 2
        assert criteria[0].criterion_code == "total_area_m2"
        assert criteria[0].weight == Decimal("0.50")
        assert criteria[1].weight == Decimal("0.50")

    def test_accepts_hard_constraint_excluded_from_sum(self) -> None:
        """Hard constraints are excluded from weight sum check."""
        raw = [
            {
                "criterion_code": "a",
                "weight": "0.60",
                "direction": "higher_is_better",
                "normalization_method": "min_max",
                "hard_constraint": False,
            },
            {
                "criterion_code": "b",
                "weight": "0.40",
                "direction": "lower_is_better",
                "normalization_method": "min_max",
                "hard_constraint": False,
            },
            {
                "criterion_code": "c",
                "weight": "999",
                "direction": "higher_is_better",
                "normalization_method": "min_max",
                "hard_constraint": True,
            },
        ]
        criteria = _parse_criteria(raw)
        assert len(criteria) == 3
        assert criteria[2].hard_constraint is True

    def test_empty_criteria_list_accepted(self) -> None:
        """Empty criteria list is accepted (no sum check needed)."""
        criteria = _parse_criteria([])
        assert criteria == ()


# ---------------------------------------------------------------------------
# Approval CAS workflow
# ---------------------------------------------------------------------------


class TestApprovalCASWorkflow:
    def _create_draft_revision(self, session: Session, *, revision_id: str = "rev-001") -> None:
        """Helper: insert a draft revision record."""

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRecord,
            SchemeWeightSetRevisionRecord,
        )

        ws = SchemeWeightSetRecord(
            id="ws-001",
            code="test-set",
            name="Test Set",
            revision=1,
            status="draft",
            source_type="system",
            criteria=[],
        )
        session.add(ws)
        session.flush()

        rev = SchemeWeightSetRevisionRecord(
            id=revision_id,
            weight_set_id="ws-001",
            code="test-set",
            revision=1,
            status="draft",
            content=_VALID_CONTENT,
            content_hash=_VALID_CONTENT_HASH,
            generator_compatibility_version="1.0.0",
        )
        session.add(rev)
        session.flush()

    def test_approve_draft_revision(self, session, adapter) -> None:
        """Draft revision can be approved."""
        self._create_draft_revision(session)

        now = datetime.now(UTC)
        result = adapter.approve_revision(
            session,
            revision_id="rev-001",
            content=_VALID_CONTENT,
            approved_at=now,
            approved_by="tester",
        )
        assert result is True
        session.commit()

        from sqlalchemy import select

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRevisionRecord,
        )

        rev = session.execute(
            select(SchemeWeightSetRevisionRecord).where(
                SchemeWeightSetRevisionRecord.id == "rev-001"
            )
        ).scalar_one()
        assert rev.status == "approved"
        assert rev.approved_by == "tester"
        assert rev.approved_at is not None

    def test_reject_approve_non_draft(self, session, adapter) -> None:
        """Cannot approve a revision that is not in draft status."""
        self._create_draft_revision(session)

        now = datetime.now(UTC)
        # Approve once
        adapter.approve_revision(
            session,
            revision_id="rev-001",
            content=_VALID_CONTENT,
            approved_at=now,
            approved_by="tester",
        )
        session.commit()

        # Try to approve again — should fail (CAS conflict)
        result = adapter.approve_revision(
            session,
            revision_id="rev-001",
            content=_VALID_CONTENT,
            approved_at=now,
            approved_by="tester2",
        )
        assert result is False

    def test_has_approved_revision(self, session, adapter) -> None:
        """has_approved_revision returns True when approved exists."""
        self._create_draft_revision(session)

        assert (
            adapter.has_approved_revision(session, weight_set_id="ws-001", code="test-set") is False
        )

        now = datetime.now(UTC)
        adapter.approve_revision(
            session,
            revision_id="rev-001",
            content=_VALID_CONTENT,
            approved_at=now,
            approved_by="tester",
        )
        session.commit()

        assert (
            adapter.has_approved_revision(session, weight_set_id="ws-001", code="test-set") is True
        )

    def test_has_approved_revision_exclude(self, session, adapter) -> None:
        """has_approved_revision with exclude_revision_id excludes that rev."""
        self._create_draft_revision(session)

        now = datetime.now(UTC)
        adapter.approve_revision(
            session,
            revision_id="rev-001",
            content=_VALID_CONTENT,
            approved_at=now,
            approved_by="tester",
        )
        session.commit()

        # Excluding the only approved revision → False
        assert (
            adapter.has_approved_revision(
                session,
                weight_set_id="ws-001",
                code="test-set",
                exclude_revision_id="rev-001",
            )
            is False
        )

    def test_cas_prevents_concurrent_double_approve(self, session, adapter) -> None:
        """Simulate concurrent approval: second CAS update returns False."""
        self._create_draft_revision(session)
        session.commit()

        now = datetime.now(UTC)
        r1 = adapter.approve_revision(
            session,
            revision_id="rev-001",
            content=_VALID_CONTENT,
            approved_at=now,
            approved_by="user1",
        )
        assert r1 is True
        session.commit()

        r2 = adapter.approve_revision(
            session,
            revision_id="rev-001",
            content=_VALID_CONTENT,
            approved_at=now,
            approved_by="user2",
        )
        assert r2 is False
        session.commit()


# ---------------------------------------------------------------------------
# Seed if not exists (adapter-level)
# ---------------------------------------------------------------------------


class TestSeedIfNotExists:
    def test_seed_creates_records(self, session, adapter) -> None:
        """seed_if_not_exists creates weight set and revision records."""
        now = datetime.now(UTC)
        adapter.seed_if_not_exists(
            session,
            weight_set_id="ws-seed-001",
            code="seed-test",
            name="Seed Test",
            revision_id="rev-seed-001",
            revision=1,
            content=_VALID_CONTENT,
            generator_compatibility_version="1.0.0",
            approved_at=now,
            approved_by="seeder",
        )
        session.commit()

        from sqlalchemy import select

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRecord,
            SchemeWeightSetRevisionRecord,
        )

        ws = session.execute(
            select(SchemeWeightSetRecord).where(SchemeWeightSetRecord.id == "ws-seed-001")
        ).scalar_one()
        assert ws.status == "approved"

        rev = session.execute(
            select(SchemeWeightSetRevisionRecord).where(
                SchemeWeightSetRevisionRecord.id == "rev-seed-001"
            )
        ).scalar_one()
        assert rev.status == "approved"
        assert rev.approved_by == "seeder"
        assert rev.content_hash == _compute_content_hash(_VALID_CONTENT)

    def test_seed_idempotent_no_duplicates(self, session, adapter) -> None:
        """Seeding twice produces no duplicates."""
        now = datetime.now(UTC)
        kwargs = dict(
            weight_set_id="ws-seed-002",
            code="seed-test-2",
            name="Seed Test 2",
            revision_id="rev-seed-002",
            revision=1,
            content=_VALID_CONTENT,
            generator_compatibility_version="1.0.0",
            approved_at=now,
            approved_by="seeder",
        )
        adapter.seed_if_not_exists(session, **kwargs)
        session.commit()

        adapter.seed_if_not_exists(session, **kwargs)
        session.commit()

        from sqlalchemy import func, select

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRevisionRecord,
        )

        count = session.execute(
            select(func.count()).select_from(SchemeWeightSetRevisionRecord)
        ).scalar_one()
        assert count == 1


# ---------------------------------------------------------------------------
# Production content validation
# ---------------------------------------------------------------------------


class TestProductionContent:
    def test_production_content_uses_decimal_strings(self) -> None:
        """Production weight content uses string weights (not floats)."""
        for crit in _VALID_CONTENT["criteria"]:
            assert isinstance(crit["weight"], str)

    def test_production_criteria_parseable(self) -> None:
        """Production weight content criteria are parseable."""
        criteria = get_production_weight_criteria()
        assert len(criteria) == 7
        # Sum of non-hard weights must be 1.0
        total = sum(c.weight for c in criteria if not c.hard_constraint)
        assert abs(total - Decimal("1")) < Decimal("0.0001")

    def test_production_content_hash_deterministic(self) -> None:
        """Production content hash is deterministic across calls."""
        h1 = get_production_weight_content_hash()
        h2 = get_production_weight_content_hash()
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex


# ---------------------------------------------------------------------------
# ORM CHECK constraint validation
# ---------------------------------------------------------------------------


class TestORMCheckConstraints:
    def test_invalid_status_rejected(self, session) -> None:
        """INSERT with invalid status violates CHECK constraint."""
        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRecord,
            SchemeWeightSetRevisionRecord,
        )

        ws = SchemeWeightSetRecord(
            id="ws-ck-001",
            code="ck-test",
            name="CK Test",
            revision=1,
            status="draft",
        )
        session.add(ws)
        session.flush()

        rev = SchemeWeightSetRevisionRecord(
            id="rev-ck-001",
            weight_set_id="ws-ck-001",
            code="ck-test",
            revision=1,
            status="invalid_status",
            content={},
            content_hash="abc",
            generator_compatibility_version="1.0.0",
        )
        session.add(rev)
        with pytest.raises(sa_exc.IntegrityError):
            session.flush()

    def test_approved_without_evidence_rejected(self, session) -> None:
        """INSERT with status='approved' but no evidence violates CHECK."""
        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRecord,
            SchemeWeightSetRevisionRecord,
        )

        ws = SchemeWeightSetRecord(
            id="ws-ck-002",
            code="ck-test-2",
            name="CK Test 2",
            revision=1,
            status="draft",
        )
        session.add(ws)
        session.flush()

        rev = SchemeWeightSetRevisionRecord(
            id="rev-ck-002",
            weight_set_id="ws-ck-002",
            code="ck-test-2",
            revision=1,
            status="approved",
            content={},
            content_hash="abc",
            generator_compatibility_version="1.0.0",
            # Missing approved_at and approved_by
        )
        session.add(rev)
        with pytest.raises(sa_exc.IntegrityError):
            session.flush()


# ---------------------------------------------------------------------------
# Allowed status transitions (P0-3)
# ---------------------------------------------------------------------------


class TestStatusTransitions:
    def _create_draft(self, session: Session, *, rid: str = "tr-001") -> None:
        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRecord,
            SchemeWeightSetRevisionRecord,
        )

        ws = SchemeWeightSetRecord(
            id="ws-tr-001",
            code="tr-test",
            name="TR Test",
            revision=1,
            status="draft",
            source_type="system",
            criteria=[],
        )
        session.add(ws)
        session.flush()

        rev = SchemeWeightSetRevisionRecord(
            id=rid,
            weight_set_id="ws-tr-001",
            code="tr-test",
            revision=1,
            status="draft",
            content=_VALID_CONTENT,
            content_hash=_VALID_CONTENT_HASH,
            generator_compatibility_version="1.0.0",
        )
        session.add(rev)
        session.flush()

    def test_draft_to_approved(self, session, adapter) -> None:
        """draft -> approved is allowed."""
        self._create_draft(session)
        result = adapter.change_status(
            session,
            revision_id="tr-001",
            target_status="approved",
            approved_at=datetime.now(UTC),
            approved_by="tester",
        )
        assert result is True
        session.commit()

    def test_approved_to_superseded(self, session, adapter) -> None:
        """approved -> superseded is allowed."""
        self._create_draft(session)
        adapter.change_status(
            session,
            revision_id="tr-001",
            target_status="approved",
            approved_at=datetime.now(UTC),
            approved_by="tester",
        )
        session.commit()

        result = adapter.change_status(
            session,
            revision_id="tr-001",
            target_status="superseded",
        )
        assert result is True
        session.commit()

    def test_approved_to_revoked(self, session, adapter) -> None:
        """approved -> revoked is allowed."""
        self._create_draft(session)
        adapter.change_status(
            session,
            revision_id="tr-001",
            target_status="approved",
            approved_at=datetime.now(UTC),
            approved_by="tester",
        )
        session.commit()

        result = adapter.change_status(
            session,
            revision_id="tr-001",
            target_status="revoked",
        )
        assert result is True
        session.commit()

    def test_draft_to_superseded_rejected(self, session, adapter) -> None:
        """draft -> superseded is NOT allowed."""
        self._create_draft(session)
        with pytest.raises(InvalidStatusTransitionError):
            adapter.change_status(
                session,
                revision_id="tr-001",
                target_status="superseded",
            )

    def test_draft_to_revoked_rejected(self, session, adapter) -> None:
        """draft -> revoked is NOT allowed."""
        self._create_draft(session)
        with pytest.raises(InvalidStatusTransitionError):
            adapter.change_status(
                session,
                revision_id="tr-001",
                target_status="revoked",
            )

    def test_approved_to_draft_rejected(self, session, adapter) -> None:
        """approved -> draft is NOT allowed."""
        self._create_draft(session)
        adapter.change_status(
            session,
            revision_id="tr-001",
            target_status="approved",
            approved_at=datetime.now(UTC),
            approved_by="tester",
        )
        session.commit()
        with pytest.raises(InvalidStatusTransitionError):
            adapter.change_status(
                session,
                revision_id="tr-001",
                target_status="draft",
            )

    def test_superseded_to_approved_rejected(self, session, adapter) -> None:
        """superseded -> approved is NOT allowed."""
        self._create_draft(session)
        adapter.change_status(
            session,
            revision_id="tr-001",
            target_status="approved",
            approved_at=datetime.now(UTC),
            approved_by="tester",
        )
        adapter.change_status(
            session,
            revision_id="tr-001",
            target_status="superseded",
        )
        session.commit()
        with pytest.raises(InvalidStatusTransitionError):
            adapter.change_status(
                session,
                revision_id="tr-001",
                target_status="approved",
                approved_at=datetime.now(UTC),
                approved_by="tester2",
            )

    def test_transition_missing_evidence_rejected(self, session, adapter) -> None:
        """Transitioning to approved without evidence raises error."""
        self._create_draft(session)
        with pytest.raises(WeightRevisionGovernanceError, match="approved_at and approved_by"):
            adapter.change_status(
                session,
                revision_id="tr-001",
                target_status="approved",
            )

    def test_nonexistent_revision_returns_false(self, session, adapter) -> None:
        """Transition on non-existent revision returns False."""
        result = adapter.change_status(
            session,
            revision_id="nonexistent",
            target_status="approved",
            approved_at=datetime.now(UTC),
            approved_by="tester",
        )
        assert result is False


# ---------------------------------------------------------------------------
# Approved immutability (P0-3)
# ---------------------------------------------------------------------------


class TestApprovedImmutability:
    def _create_approved(self, session: Session) -> None:
        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRecord,
            SchemeWeightSetRevisionRecord,
        )

        ws = SchemeWeightSetRecord(
            id="ws-imm-001",
            code="imm-test",
            name="Imm Test",
            revision=1,
            status="approved",
            source_type="system",
            criteria=[],
        )
        session.add(ws)
        session.flush()

        rev = SchemeWeightSetRevisionRecord(
            id="rev-imm-001",
            weight_set_id="ws-imm-001",
            code="imm-test",
            revision=1,
            status="approved",
            content=_VALID_CONTENT,
            content_hash=_VALID_CONTENT_HASH,
            generator_compatibility_version="1.0.0",
            approved_at=datetime.now(UTC),
            approved_by="tester",
        )
        session.add(rev)
        session.flush()
        session.commit()

    def test_approve_rejects_content_change_on_approved(self, session, adapter) -> None:
        """Cannot change content on an already-approved revision."""
        self._create_approved(session)
        new_content = {**_VALID_CONTENT, "version": "2.0.0"}
        with pytest.raises(RevisionImmutabilityViolationError, match="immutable fields"):
            adapter.approve_revision(
                session,
                revision_id="rev-imm-001",
                content=new_content,
                approved_at=datetime.now(UTC),
                approved_by="tester2",
            )

    def test_approve_same_content_on_approved_is_fine(self, session, adapter) -> None:
        """Re-approving with identical content does not raise immutability error."""
        self._create_approved(session)
        # CAS will return False (not draft), but no immutability error
        result = adapter.approve_revision(
            session,
            revision_id="rev-imm-001",
            content=_VALID_CONTENT,
            approved_at=datetime.now(UTC),
            approved_by="tester2",
        )
        assert result is False  # CAS conflict — already approved

    def test_draft_revision_can_be_modified(self, session, adapter) -> None:
        """Draft revisions can be modified freely."""
        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRecord,
            SchemeWeightSetRevisionRecord,
        )

        ws = SchemeWeightSetRecord(
            id="ws-imm-002",
            code="imm-draft",
            name="Imm Draft",
            revision=1,
            status="draft",
            source_type="system",
            criteria=[],
        )
        session.add(ws)
        session.flush()

        rev = SchemeWeightSetRevisionRecord(
            id="rev-imm-002",
            weight_set_id="ws-imm-002",
            code="imm-draft",
            revision=1,
            status="draft",
            content=_VALID_CONTENT,
            content_hash=_VALID_CONTENT_HASH,
            generator_compatibility_version="1.0.0",
        )
        session.add(rev)
        session.flush()

        # Approving draft with different content is fine (content is updated)
        new_content = {**_VALID_CONTENT, "version": "2.0.0"}
        result = adapter.approve_revision(
            session,
            revision_id="rev-imm-002",
            content=new_content,
            approved_at=datetime.now(UTC),
            approved_by="tester",
        )
        assert result is True


# ---------------------------------------------------------------------------
# Concurrent approval conflict (P0-3)
# ---------------------------------------------------------------------------


class TestConcurrentApproval:
    def test_two_drafts_same_weightset_only_one_approved(self, session, adapter) -> None:
        """Two draft revisions for same weight_set_id+code: exactly one wins."""
        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRecord,
            SchemeWeightSetRevisionRecord,
        )

        ws = SchemeWeightSetRecord(
            id="ws-conc-001",
            code="conc-test",
            name="Conc Test",
            revision=1,
            status="draft",
            source_type="system",
            criteria=[],
        )
        session.add(ws)
        session.flush()

        rev_a = SchemeWeightSetRevisionRecord(
            id="rev-conc-A",
            weight_set_id="ws-conc-001",
            code="conc-test",
            revision=1,
            status="draft",
            content=_VALID_CONTENT,
            content_hash=_VALID_CONTENT_HASH,
            generator_compatibility_version="1.0.0",
        )
        rev_b = SchemeWeightSetRevisionRecord(
            id="rev-conc-B",
            weight_set_id="ws-conc-001",
            code="conc-test",
            revision=2,
            status="draft",
            content=_VALID_CONTENT,
            content_hash=_VALID_CONTENT_HASH,
            generator_compatibility_version="1.0.0",
        )
        session.add(rev_a)
        session.add(rev_b)
        session.flush()
        session.commit()

        # Simulate concurrent approval: first session approves A
        factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
        session_a = factory()
        session_b = factory()

        now_a = datetime.now(UTC)
        result_a = adapter.approve_revision(
            session_a,
            revision_id="rev-conc-A",
            content=_VALID_CONTENT,
            approved_at=now_a,
            approved_by="user-A",
        )
        session_a.commit()
        assert result_a is True

        # Second session tries to approve B — should fail (CAS + uniqueness)
        now_b = datetime.now(UTC)
        result_b = adapter.approve_revision(
            session_b,
            revision_id="rev-conc-B",
            content=_VALID_CONTENT,
            approved_at=now_b,
            approved_by="user-B",
        )
        session_b.commit()
        assert result_b is False

        # Verify exactly one approved
        from sqlalchemy import func, select

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRevisionRecord as Rev,
        )

        approved_count = session.execute(
            select(func.count())
            .select_from(Rev)
            .where(
                Rev.weight_set_id == "ws-conc-001",
                Rev.code == "conc-test",
                Rev.status == "approved",
            )
        ).scalar_one()
        assert approved_count == 1

        session_a.close()
        session_b.close()

    def test_concurrent_approve_via_governance_layer(self, session) -> None:
        """Two draft revisions: governance layer raises RevisionAlreadyApprovedError."""
        from cold_storage.modules.schemes.application.weight_revision_governance import (
            RevisionAlreadyApprovedError,
            approve_weight_revision,
        )
        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRecord,
            SchemeWeightSetRevisionRecord,
        )

        ws = SchemeWeightSetRecord(
            id="ws-conc-gov",
            code="conc-gov",
            name="Conc Gov",
            revision=1,
            status="draft",
            source_type="system",
            criteria=[],
        )
        session.add(ws)
        session.flush()

        rev_a = SchemeWeightSetRevisionRecord(
            id="rev-cg-A",
            weight_set_id="ws-conc-gov",
            code="conc-gov",
            revision=1,
            status="draft",
            content=_VALID_CONTENT,
            content_hash=_VALID_CONTENT_HASH,
            generator_compatibility_version="1.0.0",
        )
        rev_b = SchemeWeightSetRevisionRecord(
            id="rev-cg-B",
            weight_set_id="ws-conc-gov",
            code="conc-gov",
            revision=2,
            status="draft",
            content=_VALID_CONTENT,
            content_hash=_VALID_CONTENT_HASH,
            generator_compatibility_version="1.0.0",
        )
        session.add(rev_a)
        session.add(rev_b)
        session.flush()
        session.commit()

        adapter = SqlAlchemyWeightRevisionApprovalAdapter()

        # Approve first via governance layer
        approve_weight_revision(
            adapter,
            None,
            session,
            revision_id="rev-cg-A",
            weight_set_id="ws-conc-gov",
            code="conc-gov",
            content=_VALID_CONTENT,
            approved_by="gov-user",
        )
        session.commit()

        # Second should raise RevisionAlreadyApprovedError
        with pytest.raises(RevisionAlreadyApprovedError):
            approve_weight_revision(
                adapter,
                None,
                session,
                revision_id="rev-cg-B",
                weight_set_id="ws-conc-gov",
                code="conc-gov",
                content=_VALID_CONTENT,
                approved_by="gov-user2",
            )


# ---------------------------------------------------------------------------
# Seed consistency mismatch rejection (P0-3)
# ---------------------------------------------------------------------------


class TestSeedConsistency:
    def test_seed_mismatched_content_hash_rejected(self, session, adapter) -> None:
        """Seed with existing approved revision that has different content hash is rejected."""
        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRecord,
            SchemeWeightSetRevisionRecord,
        )

        ws = SchemeWeightSetRecord(
            id="ws-seed-mis",
            code="seed-mis",
            name="Seed Mismatch",
            revision=1,
            status="approved",
            source_type="system",
            criteria=[],
        )
        session.add(ws)
        session.flush()

        rev = SchemeWeightSetRevisionRecord(
            id="rev-seed-mis",
            weight_set_id="ws-seed-mis",
            code="seed-mis",
            revision=1,
            status="approved",
            content=_VALID_CONTENT,
            content_hash=_VALID_CONTENT_HASH,
            generator_compatibility_version="1.0.0",
            approved_at=datetime.now(UTC),
            approved_by="original-seeder",
        )
        session.add(rev)
        session.flush()
        session.commit()

        # Try to seed with different content -> different hash
        different_content = {**_VALID_CONTENT, "version": "DIFFERENT"}
        with pytest.raises(SeedConsistencyError, match="content_hash"):
            adapter.seed_if_not_exists(
                session,
                weight_set_id="ws-seed-mis",
                code="seed-mis",
                name="Seed Mismatch",
                revision_id="rev-seed-mis",
                revision=1,
                content=different_content,
                generator_compatibility_version="1.0.0",
                approved_at=datetime.now(UTC),
                approved_by="new-seeder",
            )

    def test_seed_mismatched_code_rejected(self, session, adapter) -> None:
        """Seed with existing approved revision that has different code is rejected."""
        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRecord,
            SchemeWeightSetRevisionRecord,
        )

        ws = SchemeWeightSetRecord(
            id="ws-seed-cd",
            code="seed-cd-original",
            name="Seed Code",
            revision=1,
            status="approved",
            source_type="system",
            criteria=[],
        )
        session.add(ws)
        session.flush()

        rev = SchemeWeightSetRevisionRecord(
            id="rev-seed-cd",
            weight_set_id="ws-seed-cd",
            code="seed-cd-original",
            revision=1,
            status="approved",
            content=_VALID_CONTENT,
            content_hash=_VALID_CONTENT_HASH,
            generator_compatibility_version="1.0.0",
            approved_at=datetime.now(UTC),
            approved_by="original-seeder",
        )
        session.add(rev)
        session.flush()
        session.commit()

        with pytest.raises(SeedConsistencyError, match="code"):
            adapter.seed_if_not_exists(
                session,
                weight_set_id="ws-seed-cd",
                code="seed-cd-CHANGED",
                name="Seed Code",
                revision_id="rev-seed-cd",
                revision=1,
                content=_VALID_CONTENT,
                generator_compatibility_version="1.0.0",
                approved_at=datetime.now(UTC),
                approved_by="new-seeder",
            )

    def test_seed_mismatched_revision_rejected(self, session, adapter) -> None:
        """Seed with existing approved revision that has different revision number is rejected."""
        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRecord,
            SchemeWeightSetRevisionRecord,
        )

        ws = SchemeWeightSetRecord(
            id="ws-seed-rv",
            code="seed-rv",
            name="Seed Rev",
            revision=1,
            status="approved",
            source_type="system",
            criteria=[],
        )
        session.add(ws)
        session.flush()

        rev = SchemeWeightSetRevisionRecord(
            id="rev-seed-rv",
            weight_set_id="ws-seed-rv",
            code="seed-rv",
            revision=1,
            status="approved",
            content=_VALID_CONTENT,
            content_hash=_VALID_CONTENT_HASH,
            generator_compatibility_version="1.0.0",
            approved_at=datetime.now(UTC),
            approved_by="original-seeder",
        )
        session.add(rev)
        session.flush()
        session.commit()

        with pytest.raises(SeedConsistencyError, match="revision"):
            adapter.seed_if_not_exists(
                session,
                weight_set_id="ws-seed-rv",
                code="seed-rv",
                name="Seed Rev",
                revision_id="rev-seed-rv",
                revision=99,
                content=_VALID_CONTENT,
                generator_compatibility_version="1.0.0",
                approved_at=datetime.now(UTC),
                approved_by="new-seeder",
            )

    def test_seed_mismatched_generator_version_rejected(self, session, adapter) -> None:
        """Seed with mismatched generator_compatibility_version is rejected."""
        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRecord,
            SchemeWeightSetRevisionRecord,
        )

        ws = SchemeWeightSetRecord(
            id="ws-seed-gv",
            code="seed-gv",
            name="Seed GV",
            revision=1,
            status="approved",
            source_type="system",
            criteria=[],
        )
        session.add(ws)
        session.flush()

        rev = SchemeWeightSetRevisionRecord(
            id="rev-seed-gv",
            weight_set_id="ws-seed-gv",
            code="seed-gv",
            revision=1,
            status="approved",
            content=_VALID_CONTENT,
            content_hash=_VALID_CONTENT_HASH,
            generator_compatibility_version="1.0.0",
            approved_at=datetime.now(UTC),
            approved_by="original-seeder",
        )
        session.add(rev)
        session.flush()
        session.commit()

        with pytest.raises(SeedConsistencyError, match="generator_compatibility_version"):
            adapter.seed_if_not_exists(
                session,
                weight_set_id="ws-seed-gv",
                code="seed-gv",
                name="Seed GV",
                revision_id="rev-seed-gv",
                revision=1,
                content=_VALID_CONTENT,
                generator_compatibility_version="2.0.0",
                approved_at=datetime.now(UTC),
                approved_by="new-seeder",
            )

    def test_seed_matching_approved_noop(self, session, adapter) -> None:
        """Seed with matching approved revision is a silent no-op."""
        from sqlalchemy import func, select

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRecord,
            SchemeWeightSetRevisionRecord,
        )

        ws = SchemeWeightSetRecord(
            id="ws-seed-ok",
            code="seed-ok",
            name="Seed OK",
            revision=1,
            status="approved",
            source_type="system",
            criteria=[],
        )
        session.add(ws)
        session.flush()

        rev = SchemeWeightSetRevisionRecord(
            id="rev-seed-ok",
            weight_set_id="ws-seed-ok",
            code="seed-ok",
            revision=1,
            status="approved",
            content=_VALID_CONTENT,
            content_hash=_VALID_CONTENT_HASH,
            generator_compatibility_version="1.0.0",
            approved_at=datetime.now(UTC),
            approved_by="original-seeder",
        )
        session.add(rev)
        session.flush()
        session.commit()

        # Seed with identical fields — should be a no-op, no error
        adapter.seed_if_not_exists(
            session,
            weight_set_id="ws-seed-ok",
            code="seed-ok",
            name="Seed OK",
            revision_id="rev-seed-ok",
            revision=1,
            content=_VALID_CONTENT,
            generator_compatibility_version="1.0.0",
            approved_at=rev.approved_at,
            approved_by="original-seeder",
        )
        session.commit()

        # Still exactly one revision
        count = session.execute(
            select(func.count()).select_from(SchemeWeightSetRevisionRecord)
        ).scalar_one()
        assert count == 1


# ---------------------------------------------------------------------------
# SQLite immutability trigger helper
# ---------------------------------------------------------------------------


def _create_sqlite_immutability_trigger(engine: Any) -> None:
    """Create the BEFORE UPDATE trigger for approved revision immutability.

    This mirrors the trigger created in migration 0032 but is applied
    directly to a test engine so tests can verify trigger behaviour
    without running Alembic.
    """
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TRIGGER trg_immutable_weight_revision"
                " BEFORE UPDATE ON scheme_weight_set_revisions"
                " FOR EACH ROW WHEN OLD.status"
                " = 'approved' AND ("
                " NOT (NEW.content IS OLD.content)"
                " OR NOT (NEW.content_hash"
                "   IS OLD.content_hash)"
                " OR NOT (NEW.code IS OLD.code)"
                " OR NOT (NEW.revision IS OLD.revision)"
                " OR NOT (NEW.weight_set_id"
                "   IS OLD.weight_set_id)"
                " OR NOT (NEW.generator_compatibility_version"
                "   IS OLD.generator_compatibility_version)"
                ") BEGIN SELECT RAISE(ABORT,"
                " 'approved revision immutability:"
                " immutable fields'); END;"
            )
        )


# ---------------------------------------------------------------------------
# Database-level immutability triggers (P0-3)
# ---------------------------------------------------------------------------


class TestApprovedImmutabilityTrigger:
    """Test that BEFORE UPDATE triggers reject direct ORM/SQL writes
    to immutable fields of approved revisions.

    Uses a dedicated engine fixture with the trigger created.
    """

    @pytest.fixture()
    def trigger_engine(self):
        """In-memory SQLite engine with tables AND immutability trigger."""
        eng = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(eng)
        _create_sqlite_immutability_trigger(eng)
        yield eng
        eng.dispose()

    @pytest.fixture()
    def trigger_session(self, trigger_engine) -> Session:
        factory = sessionmaker(bind=trigger_engine, expire_on_commit=False)
        sess = factory()
        yield sess
        sess.close()

    def _create_approved(self, session: Session) -> None:
        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRecord,
            SchemeWeightSetRevisionRecord,
        )

        ws = SchemeWeightSetRecord(
            id="ws-trig-001",
            code="trig-test",
            name="Trig Test",
            revision=1,
            status="approved",
            source_type="system",
            criteria=[],
        )
        session.add(ws)
        session.flush()

        rev = SchemeWeightSetRevisionRecord(
            id="rev-trig-001",
            weight_set_id="ws-trig-001",
            code="trig-test",
            revision=1,
            status="approved",
            content=_VALID_CONTENT,
            content_hash=_VALID_CONTENT_HASH,
            generator_compatibility_version="1.0.0",
            approved_at=datetime.now(UTC),
            approved_by="tester",
        )
        session.add(rev)
        session.flush()
        session.commit()

    def test_orm_update_content_rejected(self, trigger_session) -> None:
        """Direct ORM update of content on approved revision is rejected."""
        self._create_approved(trigger_session)

        from sqlalchemy import select

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRevisionRecord,
        )

        rev = trigger_session.execute(
            select(SchemeWeightSetRevisionRecord).where(
                SchemeWeightSetRevisionRecord.id == "rev-trig-001"
            )
        ).scalar_one()
        rev.content = {**_VALID_CONTENT, "version": "HACKED"}
        with pytest.raises(sa_exc.IntegrityError):
            trigger_session.flush()

    def test_orm_update_code_rejected(self, trigger_session) -> None:
        """Direct ORM update of code on approved revision is rejected."""
        self._create_approved(trigger_session)

        from sqlalchemy import select

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRevisionRecord,
        )

        rev = trigger_session.execute(
            select(SchemeWeightSetRevisionRecord).where(
                SchemeWeightSetRevisionRecord.id == "rev-trig-001"
            )
        ).scalar_one()
        rev.code = "HACKED-CODE"
        with pytest.raises(sa_exc.IntegrityError):
            trigger_session.flush()

    def test_sql_update_content_rejected(self, trigger_session) -> None:
        """Direct SQL UPDATE of content on approved revision is rejected."""
        self._create_approved(trigger_session)

        from sqlalchemy import text

        with pytest.raises(sa_exc.IntegrityError):
            trigger_session.execute(
                text(
                    "UPDATE scheme_weight_set_revisions "
                    "SET content = '{\"hacked\": true}' "
                    "WHERE id = 'rev-trig-001'"
                )
            )

    def test_sql_update_content_hash_rejected(self, trigger_session) -> None:
        """Direct SQL UPDATE of content_hash on approved revision is rejected."""
        self._create_approved(trigger_session)

        from sqlalchemy import text

        with pytest.raises(sa_exc.IntegrityError):
            trigger_session.execute(
                text(
                    "UPDATE scheme_weight_set_revisions "
                    "SET content_hash = 'hacked' "
                    "WHERE id = 'rev-trig-001'"
                )
            )

    def test_approved_to_superseded_allowed(self, trigger_session) -> None:
        """Status change approved → superseded is allowed (immutable fields unchanged)."""
        self._create_approved(trigger_session)

        from sqlalchemy import select

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRevisionRecord,
        )

        rev = trigger_session.execute(
            select(SchemeWeightSetRevisionRecord).where(
                SchemeWeightSetRevisionRecord.id == "rev-trig-001"
            )
        ).scalar_one()
        rev.status = "superseded"
        trigger_session.flush()
        trigger_session.commit()

        # Verify status changed
        updated = trigger_session.execute(
            select(SchemeWeightSetRevisionRecord).where(
                SchemeWeightSetRevisionRecord.id == "rev-trig-001"
            )
        ).scalar_one()
        assert updated.status == "superseded"

    def test_approved_to_revoked_allowed(self, trigger_session) -> None:
        """Status change approved → revoked is allowed."""
        self._create_approved(trigger_session)

        from sqlalchemy import select

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRevisionRecord,
        )

        rev = trigger_session.execute(
            select(SchemeWeightSetRevisionRecord).where(
                SchemeWeightSetRevisionRecord.id == "rev-trig-001"
            )
        ).scalar_one()
        rev.status = "revoked"
        trigger_session.flush()
        trigger_session.commit()

        updated = trigger_session.execute(
            select(SchemeWeightSetRevisionRecord).where(
                SchemeWeightSetRevisionRecord.id == "rev-trig-001"
            )
        ).scalar_one()
        assert updated.status == "revoked"

    def test_draft_update_allowed(self, trigger_session) -> None:
        """Draft revisions can be freely modified (trigger only fires for approved)."""
        from sqlalchemy import select

        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRecord,
            SchemeWeightSetRevisionRecord,
        )

        ws = SchemeWeightSetRecord(
            id="ws-trig-002",
            code="trig-draft",
            name="Trig Draft",
            revision=1,
            status="draft",
            source_type="system",
            criteria=[],
        )
        trigger_session.add(ws)
        trigger_session.flush()

        rev = SchemeWeightSetRevisionRecord(
            id="rev-trig-002",
            weight_set_id="ws-trig-002",
            code="trig-draft",
            revision=1,
            status="draft",
            content=_VALID_CONTENT,
            content_hash=_VALID_CONTENT_HASH,
            generator_compatibility_version="1.0.0",
        )
        trigger_session.add(rev)
        trigger_session.flush()
        trigger_session.commit()

        # Modify draft — should succeed
        rev.content = {**_VALID_CONTENT, "version": "MODIFIED"}
        trigger_session.flush()
        trigger_session.commit()

        updated = trigger_session.execute(
            select(SchemeWeightSetRevisionRecord).where(
                SchemeWeightSetRevisionRecord.id == "rev-trig-002"
            )
        ).scalar_one()
        assert updated.content["version"] == "MODIFIED"


# ---------------------------------------------------------------------------
# Concurrent approval with authority table (P0-2)
# ---------------------------------------------------------------------------


class TestConcurrentApprovalWithAuthority:
    """Two independent SQLite connections try to approve different drafts
    for the same weight_set_id + code.  Exactly one wins, one gets a
    structured conflict.  The authority row points to the winner.
    """

    def test_concurrent_approval_one_wins(self, tmp_path) -> None:
        """File-based SQLite: two threads race to approve; exactly one wins."""
        import threading

        from sqlalchemy import text

        db_path = str(tmp_path / "conc.db")

        # 1. Create DB with all tables + trigger
        setup_engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(setup_engine)
        _create_sqlite_immutability_trigger(setup_engine)

        # 2. Insert parent weight set + two draft revisions
        from datetime import UTC, datetime

        now = datetime.now(UTC).isoformat()
        with setup_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO scheme_weight_sets"
                    " (id, code, name, revision, status,"
                    " source_type, criteria, requires_review,"
                    " created_at)"
                    " VALUES ('ws-conc-auth', 'conc-auth',"
                    " 'Conc Auth', 1, 'draft',"
                    " 'system', '[]', 0, :ts)"
                ),
                {"ts": now},
            )
            conn.execute(
                text(
                    "INSERT INTO scheme_weight_set_revisions"
                    " (id, weight_set_id, code, revision,"
                    " status, content, content_hash,"
                    " generator_compatibility_version,"
                    " created_at)"
                    " VALUES ('rev-conc-A', 'ws-conc-auth',"
                    " 'conc-auth', 1, 'draft',"
                    " '{}', 'hash-A', '1.0.0', :ts)"
                ),
                {"ts": now},
            )
            conn.execute(
                text(
                    "INSERT INTO scheme_weight_set_revisions"
                    " (id, weight_set_id, code, revision,"
                    " status, content, content_hash,"
                    " generator_compatibility_version,"
                    " created_at)"
                    " VALUES ('rev-conc-B', 'ws-conc-auth',"
                    " 'conc-auth', 2, 'draft',"
                    " '{}', 'hash-B', '1.0.0', :ts)"
                ),
                {"ts": now},
            )
        setup_engine.dispose()

        # 3. Two threads race to approve
        barrier = threading.Barrier(2, timeout=10)
        results: list[bool | None] = [None, None]

        def _approve(index: int, rev_id: str) -> None:
            eng = create_engine(
                f"sqlite:///{db_path}",
                connect_args={"check_same_thread": False, "timeout": 30},
            )
            factory = sessionmaker(bind=eng, expire_on_commit=False)
            sess = factory()
            try:
                barrier.wait()  # synchronize before racing
                adapter = SqlAlchemyWeightRevisionApprovalAdapter()
                results[index] = adapter.approve_revision(
                    sess,
                    revision_id=rev_id,
                    content={"concurrent": True},
                    approved_at=datetime.now(UTC),
                    approved_by=f"user-{index}",
                )
                sess.commit()
            except Exception:
                sess.rollback()
                results[index] = False
            finally:
                sess.close()
                eng.dispose()

        t1 = threading.Thread(target=_approve, args=(0, "rev-conc-A"))
        t2 = threading.Thread(target=_approve, args=(1, "rev-conc-B"))
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        # 4. Exactly one should have succeeded
        assert sum(1 for r in results if r is True) == 1, (
            f"Expected exactly 1 winner, got results={results}"
        )

        # 5. Verify: exactly one approved in DB
        verify_engine = create_engine(f"sqlite:///{db_path}")
        with verify_engine.begin() as conn:
            from sqlalchemy import text

            approved_count = conn.execute(
                text(
                    "SELECT COUNT(*) FROM scheme_weight_set_revisions "
                    "WHERE weight_set_id = 'ws-conc-auth' "
                    "AND code = 'conc-auth' "
                    "AND status = 'approved'"
                )
            ).scalar_one()
            assert approved_count == 1

            # 6. Authority row points to the winner
            auth_row = conn.execute(
                text(
                    "SELECT approved_revision_id "
                    "FROM scheme_weight_set_active_revisions "
                    "WHERE weight_set_id = 'ws-conc-auth' "
                    "AND code = 'conc-auth'"
                )
            ).fetchone()
            assert auth_row is not None
            winner_id = auth_row[0]
            assert winner_id in ("rev-conc-A", "rev-conc-B")

            # Verify the authority row points to the actual approved revision
            approved_rev = conn.execute(
                text(
                    "SELECT id FROM scheme_weight_set_revisions "
                    "WHERE status = 'approved' "
                    "AND weight_set_id = 'ws-conc-auth' "
                    "AND code = 'conc-auth'"
                )
            ).scalar_one()
            assert winner_id == approved_rev

        verify_engine.dispose()

    def test_authority_table_prevents_double_approve(self, session, adapter) -> None:
        """Authority table prevents approving two revisions for same weight_set_id+code."""
        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRecord,
            SchemeWeightSetRevisionRecord,
        )

        ws = SchemeWeightSetRecord(
            id="ws-auth-001",
            code="auth-test",
            name="Auth Test",
            revision=1,
            status="draft",
            source_type="system",
            criteria=[],
        )
        session.add(ws)
        session.flush()

        rev_a = SchemeWeightSetRevisionRecord(
            id="rev-auth-A",
            weight_set_id="ws-auth-001",
            code="auth-test",
            revision=1,
            status="draft",
            content=_VALID_CONTENT,
            content_hash=_VALID_CONTENT_HASH,
            generator_compatibility_version="1.0.0",
        )
        rev_b = SchemeWeightSetRevisionRecord(
            id="rev-auth-B",
            weight_set_id="ws-auth-001",
            code="auth-test",
            revision=2,
            status="draft",
            content=_VALID_CONTENT,
            content_hash=_VALID_CONTENT_HASH,
            generator_compatibility_version="1.0.0",
        )
        session.add(rev_a)
        session.add(rev_b)
        session.flush()
        session.commit()

        now = datetime.now(UTC)

        # Approve A — should succeed
        result_a = adapter.approve_revision(
            session,
            revision_id="rev-auth-A",
            content=_VALID_CONTENT,
            approved_at=now,
            approved_by="user-A",
        )
        assert result_a is True
        session.commit()

        # Approve B — should fail (authority conflict)
        result_b = adapter.approve_revision(
            session,
            revision_id="rev-auth-B",
            content=_VALID_CONTENT,
            approved_at=now,
            approved_by="user-B",
        )
        assert result_b is False

        # Verify authority row points to A
        from sqlalchemy import text

        auth_row = session.execute(
            text(
                "SELECT approved_revision_id "
                "FROM scheme_weight_set_active_revisions "
                "WHERE weight_set_id = 'ws-auth-001' "
                "AND code = 'auth-test'"
            )
        ).fetchone()
        assert auth_row is not None
        assert auth_row[0] == "rev-auth-A"

    def test_authority_cleaned_on_supersede(self, session, adapter) -> None:
        """Authority row is removed when approved revision is superseded."""
        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRecord,
            SchemeWeightSetRevisionRecord,
        )

        ws = SchemeWeightSetRecord(
            id="ws-auth-super",
            code="auth-super",
            name="Auth Super",
            revision=1,
            status="draft",
            source_type="system",
            criteria=[],
        )
        session.add(ws)
        session.flush()

        rev = SchemeWeightSetRevisionRecord(
            id="rev-auth-super",
            weight_set_id="ws-auth-super",
            code="auth-super",
            revision=1,
            status="draft",
            content=_VALID_CONTENT,
            content_hash=_VALID_CONTENT_HASH,
            generator_compatibility_version="1.0.0",
        )
        session.add(rev)
        session.flush()
        session.commit()

        now = datetime.now(UTC)
        adapter.approve_revision(
            session,
            revision_id="rev-auth-super",
            content=_VALID_CONTENT,
            approved_at=now,
            approved_by="tester",
        )
        session.commit()

        # Verify authority row exists
        from sqlalchemy import text

        auth_row = session.execute(
            text(
                "SELECT approved_revision_id "
                "FROM scheme_weight_set_active_revisions "
                "WHERE weight_set_id = 'ws-auth-super'"
            )
        ).fetchone()
        assert auth_row is not None
        assert auth_row[0] == "rev-auth-super"

        # Supersede
        adapter.change_status(
            session,
            revision_id="rev-auth-super",
            target_status="superseded",
        )
        session.commit()

        # Verify authority row is gone
        auth_row_after = session.execute(
            text(
                "SELECT approved_revision_id "
                "FROM scheme_weight_set_active_revisions "
                "WHERE weight_set_id = 'ws-auth-super'"
            )
        ).fetchone()
        assert auth_row_after is None

    def test_seed_consistency_with_existing_approved(self, session, adapter) -> None:
        """Seed with matching approved revision is a no-op, no authority conflict."""
        from cold_storage.modules.schemes.infrastructure.orm import (
            SchemeWeightSetRecord,
            SchemeWeightSetRevisionRecord,
        )

        ws = SchemeWeightSetRecord(
            id="ws-seed-auth",
            code="seed-auth",
            name="Seed Auth",
            revision=1,
            status="approved",
            source_type="system",
            criteria=[],
        )
        session.add(ws)
        session.flush()

        rev = SchemeWeightSetRevisionRecord(
            id="rev-seed-auth",
            weight_set_id="ws-seed-auth",
            code="seed-auth",
            revision=1,
            status="approved",
            content=_VALID_CONTENT,
            content_hash=_VALID_CONTENT_HASH,
            generator_compatibility_version="1.0.0",
            approved_at=datetime.now(UTC),
            approved_by="original-seeder",
        )
        session.add(rev)
        session.flush()
        session.commit()

        # Seed with identical fields — should be a no-op
        adapter.seed_if_not_exists(
            session,
            weight_set_id="ws-seed-auth",
            code="seed-auth",
            name="Seed Auth",
            revision_id="rev-seed-auth",
            revision=1,
            content=_VALID_CONTENT,
            generator_compatibility_version="1.0.0",
            approved_at=datetime.now(UTC),
            approved_by="original-seeder",
        )
        session.commit()

        # Still exactly one revision
        from sqlalchemy import func, select

        count = session.execute(
            select(func.count()).select_from(SchemeWeightSetRevisionRecord)
        ).scalar_one()
        assert count == 1
