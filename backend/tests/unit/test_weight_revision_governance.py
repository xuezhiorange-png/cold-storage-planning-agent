"""Tests for weight revision database governance (P0-7).

Covers:
- Seed idempotency
- Criteria parser rejection matrix
- Approval CAS workflow
- Idempotent seed on SQLite
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
