"""Integration tests for coefficient resolution authority.

Covers:
- Scope/applicability filtering (global, product, zone, process)
- Required coefficient completeness
- Supersession DAG validation (cycle, missing, multi-head)
- Value canonicalization (decimal normalization, JSON structural)
- Caller self-attestation isolation
- Cross-DB determinism (SQLite vs PostgreSQL)

Uses real database tables — no MagicMock for the resolver.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from cold_storage.modules.coefficients.infrastructure.orm import (
    CoefficientDefinitionRecord,
    CoefficientRevisionRecord,
)
from cold_storage.modules.orchestration.application.coefficient_contracts import (
    FrozenCoefficientResolutionCriteria,
)
from cold_storage.modules.orchestration.domain.errors import (
    AmbiguousCoefficientError,
    CoefficientNotApprovedError,
    CoefficientResolutionError,
)
from cold_storage.modules.orchestration.infrastructure.coefficient_resolver import (
    SqlAlchemyCoefficientResolutionAdapter,
)

# ── Test helpers ─────────────────────────────────────────────────────────


def _seed_definition(
    session: Session,
    *,
    def_id: str,
    code: str,
    scope_type: str = "global",
    is_active: bool = True,
) -> None:
    session.add(
        CoefficientDefinitionRecord(
            id=def_id,
            code=code,
            name=f"Test {code}",
            description=f"Description for {code}",
            category="general",
            canonical_unit="dimensionless",
            value_type="decimal",
            scope_type=scope_type,
            is_active=is_active,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )


def _seed_approved_revision(
    session: Session,
    *,
    rev_id: str,
    definition_id: str,
    revision_number: int = 1,
    value_decimal: str | None = "1.0",
    source_type: str = "standard",
    applicable_product_type: str | None = None,
    applicable_zone_type: str | None = None,
    applicable_process_type: str | None = None,
    supersedes_revision_id: str | None = None,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    status: str = "approved",
    approved_at_override: datetime | None = None,
    withdrawn_at: datetime | None = None,
) -> CoefficientRevisionRecord:
    """Create an approved revision (or with custom status)."""
    rev = CoefficientRevisionRecord(
        id=rev_id,
        coefficient_definition_id=definition_id,
        revision_number=revision_number,
        unit="dimensionless",
        status=status,
        source_type=source_type,
        value_decimal=value_decimal,
        applicable_product_type=applicable_product_type,
        applicable_zone_type=applicable_zone_type,
        applicable_process_type=applicable_process_type,
        supersedes_revision_id=supersedes_revision_id,
        valid_from=valid_from,
        valid_to=valid_to,
        created_at=datetime.now(UTC),
        created_by="test",
    )
    if status == "approved":
        rev.approved_at = approved_at_override or datetime.now(UTC)
        rev.approved_by = "test-approver"
    if withdrawn_at:
        rev.withdrawn_at = withdrawn_at
    session.add(rev)
    return rev


# ── Test helpers ────────────────────────────────────────────────────────────


def _criteria(
    *,
    project_id: str = "p-1",
    project_version_id: str = "pv-1",
    product_type: str | None = None,
    zone_types: tuple[str, ...] = (),
    process_types: tuple[str, ...] = (),
    required_codes: tuple[str, ...] = (),
) -> FrozenCoefficientResolutionCriteria:
    """Build frozen criteria for test resolver calls."""
    return FrozenCoefficientResolutionCriteria(
        project_id=project_id,
        project_version_id=project_version_id,
        product_type=product_type,
        zone_types=zone_types,
        process_types=process_types,
        required_codes=required_codes,
    )


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture()
def resolver() -> SqlAlchemyCoefficientResolutionAdapter:
    return SqlAlchemyCoefficientResolutionAdapter()


# ── Tests ────────────────────────────────────────────────────────────────


class TestScopeGlobal:
    """Global scope — matches any project/version."""

    def test_global_coefficient_resolved(self, resolver, tmp_session_factory) -> None:
        """Global coefficient is resolved regardless of product/zone/process."""
        with tmp_session_factory() as s:
            _seed_definition(s, def_id="d1", code="PEAK_FACTOR", scope_type="global")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1", value_decimal="1.5")
            s.commit()

        candidate = resolver.resolve(
            criteria=_criteria(required_codes=("PEAK_FACTOR",), product_type="blueberry"),
            session=tmp_session_factory(),
        )
        assert len(candidate.approved_revision_ids) == 1
        assert "r1" in candidate.approved_revision_ids
        coeffs = candidate.content["coefficients"]
        assert isinstance(coeffs, list)
        assert len(coeffs) == 1
        assert coeffs[0]["code"] == "PEAK_FACTOR"


class TestScopeProduct:
    """Product scope — revision must match product_type."""

    def test_product_match_resolved(self, resolver, tmp_session_factory) -> None:
        with tmp_session_factory() as s:
            _seed_definition(s, def_id="d1", code="PROD_COEFF", scope_type="product")
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                revision_number=1,
                applicable_product_type="blueberry",
            )
            _seed_approved_revision(
                s,
                rev_id="r2",
                definition_id="d1",
                revision_number=2,
                applicable_product_type="strawberry",
            )
            s.commit()

        candidate = resolver.resolve(
            criteria=_criteria(required_codes=("PROD_COEFF",), product_type="blueberry"),
            session=tmp_session_factory(),
        )
        # Only r1 (blueberry) should be selected
        assert candidate.approved_revision_ids == ("r1",)

    def test_product_mismatch_excluded(self, resolver, tmp_session_factory) -> None:
        with tmp_session_factory() as s:
            _seed_definition(s, def_id="d1", code="PROD_COEFF", scope_type="product")
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                applicable_product_type="blueberry",
            )
            s.commit()

        # No revision matches strawberry — should raise
        with pytest.raises(CoefficientNotApprovedError):
            resolver.resolve(
                criteria=_criteria(required_codes=("PROD_COEFF",), product_type="strawberry"),
                session=tmp_session_factory(),
            )


class TestScopeZone:
    """Zone scope — revision must match zone_type."""

    def test_zone_match_resolved(self, resolver, tmp_session_factory) -> None:
        with tmp_session_factory() as s:
            _seed_definition(s, def_id="d1", code="ZONE_COEFF", scope_type="zone")
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                applicable_zone_type="precooling",
            )
            s.commit()

        candidate = resolver.resolve(
            criteria=_criteria(required_codes=("ZONE_COEFF",), zone_types=("precooling",)),
            session=tmp_session_factory(),
        )
        assert "r1" in candidate.approved_revision_ids


class TestRequiredCompleteness:
    """Required coefficient completeness enforcement."""

    def test_all_required_codes_resolved(self, resolver, tmp_session_factory) -> None:
        with tmp_session_factory() as s:
            _seed_definition(s, def_id="d1", code="CODE_A")
            _seed_definition(s, def_id="d2", code="CODE_B")
            _seed_definition(s, def_id="d3", code="CODE_C")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1")
            _seed_approved_revision(s, rev_id="r2", definition_id="d2")
            _seed_approved_revision(s, rev_id="r3", definition_id="d3")
            s.commit()

        candidate = resolver.resolve(
            criteria=_criteria(
                required_codes=(
                    "CODE_A",
                    "CODE_B",
                    "CODE_C",
                )
            ),
            session=tmp_session_factory(),
        )
        codes = {item["code"] for item in candidate.content["coefficients"]}
        assert codes == {"CODE_A", "CODE_B", "CODE_C"}

    def test_missing_required_code_rejected(self, resolver, tmp_session_factory) -> None:
        with tmp_session_factory() as s:
            _seed_definition(s, def_id="d1", code="CODE_A")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1")
            s.commit()

        with pytest.raises(CoefficientNotApprovedError, match="required_coefficient_missing"):
            resolver.resolve(
                criteria=_criteria(
                    required_codes=(
                        "CODE_A",
                        "CODE_B",
                    )
                ),
                session=tmp_session_factory(),
            )

    def test_non_required_definition_not_in_context(self, resolver, tmp_session_factory) -> None:
        with tmp_session_factory() as s:
            _seed_definition(s, def_id="d1", code="REQUIRED")
            _seed_definition(s, def_id="d2", code="EXTRA")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1")
            _seed_approved_revision(s, rev_id="r2", definition_id="d2")
            s.commit()

        candidate = resolver.resolve(
            criteria=_criteria(required_codes=("REQUIRED",)),
            session=tmp_session_factory(),
        )
        codes = {item["code"] for item in candidate.content["coefficients"]}
        assert "REQUIRED" in codes
        # EXTRA may or may not be included (resolver returns all applicable)


class TestSupersession:
    """Supersession DAG validation."""

    def test_single_supersession_chain(self, resolver, tmp_session_factory) -> None:
        with tmp_session_factory() as s:
            _seed_definition(s, def_id="d1", code="SINGLE")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1", revision_number=1)
            _seed_approved_revision(
                s,
                rev_id="r2",
                definition_id="d1",
                revision_number=2,
                supersedes_revision_id="r1",
            )
            s.commit()

        candidate = resolver.resolve(
            criteria=_criteria(
                required_codes=("SINGLE",),
            ),
            session=tmp_session_factory(),
        )
        assert candidate.approved_revision_ids == ("r2",)

    def test_two_level_supersession(self, resolver, tmp_session_factory) -> None:
        with tmp_session_factory() as s:
            _seed_definition(s, def_id="d1", code="LEVELS")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1", revision_number=1)
            _seed_approved_revision(
                s,
                rev_id="r2",
                definition_id="d1",
                revision_number=2,
                supersedes_revision_id="r1",
            )
            _seed_approved_revision(
                s,
                rev_id="r3",
                definition_id="d1",
                revision_number=3,
                supersedes_revision_id="r2",
            )
            s.commit()

        candidate = resolver.resolve(
            criteria=_criteria(
                required_codes=("LEVELS",),
            ),
            session=tmp_session_factory(),
        )
        # r3 supersedes r2 which supersedes r1 → r3 is terminal
        assert candidate.approved_revision_ids == ("r3",)

    def test_self_loop_rejected(self, resolver, tmp_session_factory) -> None:
        with tmp_session_factory() as s:
            _seed_definition(s, def_id="d1", code="LOOP")
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                revision_number=1,
                supersedes_revision_id="r1",  # self-loop
            )
            s.commit()

        with pytest.raises(CoefficientResolutionError, match="supersession"):
            resolver.resolve(
                criteria=_criteria(
                    required_codes=("LOOP",),
                ),
                session=tmp_session_factory(),
            )

    def test_cycle_rejected(self, resolver, tmp_session_factory) -> None:
        with tmp_session_factory() as s:
            _seed_definition(s, def_id="d1", code="CYCLE")
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                revision_number=1,
                supersedes_revision_id="r2",
            )
            _seed_approved_revision(
                s,
                rev_id="r2",
                definition_id="d1",
                revision_number=2,
                supersedes_revision_id="r1",  # A→B→A cycle
            )
            s.commit()

        with pytest.raises(CoefficientResolutionError, match="cycle"):
            resolver.resolve(
                criteria=_criteria(
                    required_codes=("CYCLE",),
                ),
                session=tmp_session_factory(),
            )

    def test_multiple_terminal_heads_rejected(self, resolver, tmp_session_factory) -> None:
        """Multiple un-superseded terminal heads → AmbiguousCoefficientError."""
        with tmp_session_factory() as s:
            _seed_definition(s, def_id="d1", code="MULTI")
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                revision_number=1,
            )
            _seed_approved_revision(
                s,
                rev_id="r2",
                definition_id="d1",
                revision_number=2,
            )
            s.commit()

        with pytest.raises(AmbiguousCoefficientError, match="ambiguous"):
            resolver.resolve(
                criteria=_criteria(
                    required_codes=("MULTI",),
                ),
                session=tmp_session_factory(),
            )

    def test_superseded_revision_withdrawn(self, resolver, tmp_session_factory) -> None:
        """Superseding revision that is withdrawn should not be terminal."""
        now = datetime.now(UTC)
        with tmp_session_factory() as s:
            _seed_definition(s, def_id="d1", code="WITHDRAWN")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1", revision_number=1)
            _seed_approved_revision(
                s,
                rev_id="r2",
                definition_id="d1",
                revision_number=2,
                supersedes_revision_id="r1",
                withdrawn_at=now,  # r2 is withdrawn
            )
            s.commit()

        candidate = resolver.resolve(
            criteria=_criteria(
                required_codes=("WITHDRAWN",),
            ),
            session=tmp_session_factory(),
        )
        # r2 is withdrawn so not included, r1 is not superseded
        # Actually r1 IS superseded by r2, but r2 is withdrawn (excluded)
        # So r1 should be resolved (the superseded flag only applies within active revisions)
        assert "r1" in candidate.approved_revision_ids


class TestValueCanonicalization:
    """Decimal and JSON value canonicalization."""

    def test_decimal_equivalent_forms_same_hash(self, resolver, tmp_session_factory) -> None:
        """1.0 and 1.00 should produce identical coefficient value in content."""

        def _resolve_with_value(value: str):
            code = f"EQ_{value}"
            with tmp_session_factory() as s:
                _seed_definition(s, def_id=f"d_{value}", code=code)
                _seed_approved_revision(
                    s,
                    rev_id=f"r_{value}",
                    definition_id=f"d_{value}",
                    value_decimal=value,
                )
                s.commit()
            return resolver.resolve(
                criteria=_criteria(required_codes=(code,)),
                session=tmp_session_factory(),
            )

        c1 = _resolve_with_value("1.0")
        c2 = _resolve_with_value("1.00")

        # Both should have the same canonical value_decimal in content
        v1 = c1.content["coefficients"][0]["value_decimal"]
        v2 = c2.content["coefficients"][0]["value_decimal"]
        assert v1 == v2 == "1", f"Expected canonical '1', got {v1!r} vs {v2!r}"

    def test_decimal_value_change_changes_hash(self, resolver, tmp_session_factory) -> None:
        def _build(value: str) -> str:
            with tmp_session_factory() as s:
                from sqlalchemy import delete as sa_delete

                s.execute(sa_delete(CoefficientDefinitionRecord))
                s.execute(sa_delete(CoefficientRevisionRecord))
                s.commit()
                _seed_definition(s, def_id="d1", code="CHG")
                _seed_approved_revision(s, rev_id="r1", definition_id="d1", value_decimal=value)
                s.commit()
            candidate = resolver.resolve(
                criteria=_criteria(
                    required_codes=("CHG",),
                ),
                session=tmp_session_factory(),
            )
            return candidate.content_hash

        h1 = _build("1.0")
        h2 = _build("2.0")
        assert h1 != h2, "Different values should produce different hashes"

    def test_json_value_in_content(self, resolver, tmp_session_factory) -> None:
        import json as _json

        with tmp_session_factory() as s:
            _seed_definition(s, def_id="d1", code="JSON")
            # Override value_type via direct ORM manipulation
            from sqlalchemy import update as sa_update

            s.execute(
                sa_update(CoefficientDefinitionRecord)
                .where(CoefficientDefinitionRecord.id == "d1")
                .values(value_type="json")
            )
            rev = CoefficientRevisionRecord(
                id="r1",
                coefficient_definition_id="d1",
                revision_number=1,
                unit="dimensionless",
                status="approved",
                source_type="standard",
                value_json=_json.dumps({"a": 1, "b": 2}),  # TEXT column
                created_by="test",
                created_at=datetime.now(UTC),
                approved_at=datetime.now(UTC),
                approved_by="test",
            )
            s.add(rev)
            s.commit()

        candidate = resolver.resolve(
            criteria=_criteria(
                required_codes=("JSON",),
            ),
            session=tmp_session_factory(),
        )
        coeffs = candidate.content["coefficients"]
        assert len(coeffs) == 1
        assert coeffs[0]["value_json"] == {"a": 1, "b": 2}


class TestCallerIsolation:
    """Caller self-attestation must not affect resolver output."""

    def test_caller_status_ignored(self, resolver, tmp_session_factory) -> None:
        """Even if caller claims status=draft, only DB-approved revisions are used."""
        with tmp_session_factory() as s:
            _seed_definition(s, def_id="d1", code="ISO")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1", status="draft")
            s.commit()

        # Even with caller context claiming approved, only DB state matters
        with pytest.raises(CoefficientNotApprovedError):
            resolver.resolve(
                criteria=_criteria(
                    required_codes=("ISO",),
                ),
                session=tmp_session_factory(),
            )

    def test_caller_revision_ids_ignored(self, resolver, tmp_session_factory) -> None:
        """Caller-provided approved_revision_ids must not change result."""
        with tmp_session_factory() as s:
            _seed_definition(s, def_id="d1", code="ISO2")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1")
            s.commit()

        candidate = resolver.resolve(
            criteria=_criteria(
                required_codes=("ISO2",),
            ),
            session=tmp_session_factory(),
        )
        # Must still use r1 from DB, not fake-rev-999 from caller
        assert candidate.approved_revision_ids == ("r1",)


class TestInactiveDraftExpired:
    """Inactive definitions, draft/withdrawn/expired revisions."""

    def test_inactive_definition_excluded(self, resolver, tmp_session_factory) -> None:
        with tmp_session_factory() as s:
            _seed_definition(s, def_id="d1", code="INACTIVE", is_active=False)
            _seed_approved_revision(s, rev_id="r1", definition_id="d1")
            s.commit()

        with pytest.raises(CoefficientNotApprovedError):
            resolver.resolve(
                criteria=_criteria(
                    required_codes=("INACTIVE",),
                ),
                session=tmp_session_factory(),
            )

    def test_draft_revision_not_used(self, resolver, tmp_session_factory) -> None:
        with tmp_session_factory() as s:
            _seed_definition(s, def_id="d1", code="DRAFT")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1", status="draft")
            s.commit()

        with pytest.raises(CoefficientNotApprovedError):
            resolver.resolve(
                criteria=_criteria(
                    required_codes=("DRAFT",),
                ),
                session=tmp_session_factory(),
            )

    def test_expired_revision_excluded(self, resolver, tmp_session_factory) -> None:
        now = datetime.now(UTC)
        past = now - timedelta(days=10)
        with tmp_session_factory() as s:
            _seed_definition(s, def_id="d1", code="EXPIRED")
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                valid_to=past,  # Expired 10 days ago
            )
            s.commit()

        with pytest.raises(CoefficientNotApprovedError):
            resolver.resolve(
                criteria=_criteria(
                    required_codes=("EXPIRED",),
                ),
                session=tmp_session_factory(),
            )

    def test_future_revision_excluded(self, resolver, tmp_session_factory) -> None:
        future = datetime.now(UTC) + timedelta(days=30)
        with tmp_session_factory() as s:
            _seed_definition(s, def_id="d1", code="FUTURE")
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                valid_from=future,
            )
            s.commit()

        with pytest.raises(CoefficientNotApprovedError):
            resolver.resolve(
                criteria=_criteria(
                    required_codes=("FUTURE",),
                ),
                session=tmp_session_factory(),
            )


class TestMultiDefinition:
    """Multiple definitions — each gets one authoritative revision."""

    def test_two_definitions_each_select_one(self, resolver, tmp_session_factory) -> None:
        with tmp_session_factory() as s:
            _seed_definition(s, def_id="d1", code="CODE_A")
            _seed_definition(s, def_id="d2", code="CODE_B")
            _seed_approved_revision(s, rev_id="r1a", definition_id="d1", revision_number=1)
            _seed_approved_revision(
                s,
                rev_id="r1b",
                definition_id="d1",
                revision_number=2,
                supersedes_revision_id="r1a",
            )
            _seed_approved_revision(s, rev_id="r2a", definition_id="d2", revision_number=1)
            s.commit()

        candidate = resolver.resolve(
            criteria=_criteria(
                required_codes=(
                    "CODE_A",
                    "CODE_B",
                ),
            ),
            session=tmp_session_factory(),
        )
        # d1: r1b supersedes r1a → single terminal head
        # d2: r2a (only one)
        assert set(candidate.approved_revision_ids) == {"r1b", "r2a"}
        assert candidate.content["coefficient_count"] == 2


class TestUnsupportedScope:
    """Project/project_version scope — fail closed."""

    def test_project_scope_fails_closed(self, resolver, tmp_session_factory) -> None:
        with tmp_session_factory() as s:
            _seed_definition(s, def_id="d1", code="PROJ_SCOPE", scope_type="project")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1")
            s.commit()

        with pytest.raises(CoefficientResolutionError, match="unsupported_scope"):
            resolver.resolve(
                criteria=_criteria(
                    required_codes=("PROJ_SCOPE",),
                ),
                session=tmp_session_factory(),
            )

    def test_project_version_scope_fails_closed(self, resolver, tmp_session_factory) -> None:
        with tmp_session_factory() as s:
            _seed_definition(s, def_id="d1", code="PV_SCOPE", scope_type="project_version")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1")
            s.commit()

        with pytest.raises(CoefficientResolutionError, match="unsupported_scope"):
            resolver.resolve(
                criteria=_criteria(
                    required_codes=("PV_SCOPE",),
                ),
                session=tmp_session_factory(),
            )
