"""PostgreSQL integration tests for coefficient resolution authority.

Mirrors test_coefficient_resolver.py scenarios against a real PostgreSQL
database with Alembic head schema applied.

Covers:
- Scope/applicability filtering (global, product, zone, process)
- Required coefficient completeness
- Supersession DAG validation (cycle, missing, multi-head, self-loop)
- Value canonicalization (decimal normalization, JSON structural)
- Inactive definitions, draft/withdrawn/expired revisions
- Unit mismatch
- Exact required set (no extras, no missing)
- Cross-DB determinism: SQLite vs PostgreSQL output consistency

Tagged with ``@pytest.mark.postgresql`` — run with ``-m postgresql``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete as sa_delete
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

pytestmark = pytest.mark.postgresql

# ── Test helpers ─────────────────────────────────────────────────────────


def _seed_definition(
    session: Session,
    *,
    def_id: str,
    code: str,
    scope_type: str = "global",
    is_active: bool = True,
    value_type: str = "decimal",
    canonical_unit: str = "dimensionless",
) -> None:
    session.add(
        CoefficientDefinitionRecord(
            id=def_id,
            code=code,
            name=f"Test {code}",
            description=f"Description for {code}",
            category="general",
            canonical_unit=canonical_unit,
            value_type=value_type,
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
    value_json: str | None = None,
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
    unit: str = "dimensionless",
) -> CoefficientRevisionRecord:
    """Create a revision (approved by default)."""
    rev = CoefficientRevisionRecord(
        id=rev_id,
        coefficient_definition_id=definition_id,
        revision_number=revision_number,
        unit=unit,
        status=status,
        source_type=source_type,
        value_decimal=value_decimal,
        value_json=value_json,
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


def _criteria(
    *,
    project_id: str = "p-1",
    project_version_id: str = "pv-1",
    product_category: str | None = None,
    product_type: str | None = None,
    zone_types: tuple[str, ...] = (),
    process_types: tuple[str, ...] = (),
    required_codes: tuple[str, ...] = (),
) -> FrozenCoefficientResolutionCriteria:
    """Build frozen criteria for test resolver calls."""
    return FrozenCoefficientResolutionCriteria(
        project_id=project_id,
        project_version_id=project_version_id,
        product_category=product_category,
        product_type=product_type,
        zone_types=zone_types,
        process_types=process_types,
        required_codes=required_codes,
    )


def _clear_tables(session: Session) -> None:
    """Remove all coefficient data for a clean test state."""
    session.execute(sa_delete(CoefficientRevisionRecord))
    session.execute(sa_delete(CoefficientDefinitionRecord))
    session.commit()


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture()
def resolver() -> SqlAlchemyCoefficientResolutionAdapter:
    return SqlAlchemyCoefficientResolutionAdapter()


# ── Scope tests ──────────────────────────────────────────────────────────


class TestScopeGlobalPG:
    """Global scope on PostgreSQL — matches any project/version."""

    def test_global_coefficient_resolved(self, resolver, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="PEAK_FACTOR", scope_type="global")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1", value_decimal="1.5")
            s.commit()

        candidate = resolver.resolve(
            criteria=_criteria(required_codes=("PEAK_FACTOR",), product_type="blueberry"),
            session=pg_session_factory(),
        )
        assert len(candidate.approved_revision_ids) == 1
        assert "r1" in candidate.approved_revision_ids
        coeffs = candidate.content["coefficients"]
        assert len(coeffs) == 1
        assert coeffs[0]["code"] == "PEAK_FACTOR"


class TestScopeProductPG:
    """Product scope on PostgreSQL."""

    def test_product_match_resolved(self, resolver, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _clear_tables(s)
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
            session=pg_session_factory(),
        )
        assert candidate.approved_revision_ids == ("r1",)

    def test_product_mismatch_excluded(self, resolver, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="PROD_COEFF", scope_type="product")
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                applicable_product_type="blueberry",
            )
            s.commit()

        with pytest.raises(CoefficientNotApprovedError):
            resolver.resolve(
                criteria=_criteria(required_codes=("PROD_COEFF",), product_type="strawberry"),
                session=pg_session_factory(),
            )


class TestScopeZonePG:
    """Zone scope on PostgreSQL."""

    def test_zone_match_resolved(self, resolver, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _clear_tables(s)
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
            session=pg_session_factory(),
        )
        assert "r1" in candidate.approved_revision_ids


class TestScopeProcessPG:
    """Process scope on PostgreSQL."""

    def test_process_match_resolved(self, resolver, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="PROC_COEFF", scope_type="process")
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                applicable_process_type="freezing",
            )
            s.commit()

        candidate = resolver.resolve(
            criteria=_criteria(required_codes=("PROC_COEFF",), process_types=("freezing",)),
            session=pg_session_factory(),
        )
        assert "r1" in candidate.approved_revision_ids

    def test_process_mismatch_excluded(self, resolver, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="PROC_COEFF", scope_type="process")
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                applicable_process_type="freezing",
            )
            s.commit()

        with pytest.raises(CoefficientNotApprovedError):
            resolver.resolve(
                criteria=_criteria(required_codes=("PROC_COEFF",), process_types=("packing",)),
                session=pg_session_factory(),
            )


# ── Required completeness ────────────────────────────────────────────────


class TestRequiredCompletenessPG:
    """Required coefficient completeness enforcement on PostgreSQL."""

    def test_all_required_codes_resolved(self, resolver, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="CODE_A")
            _seed_definition(s, def_id="d2", code="CODE_B")
            _seed_definition(s, def_id="d3", code="CODE_C")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1")
            _seed_approved_revision(s, rev_id="r2", definition_id="d2")
            _seed_approved_revision(s, rev_id="r3", definition_id="d3")
            s.commit()

        candidate = resolver.resolve(
            criteria=_criteria(required_codes=("CODE_A", "CODE_B", "CODE_C")),
            session=pg_session_factory(),
        )
        codes = {item["code"] for item in candidate.content["coefficients"]}
        assert codes == {"CODE_A", "CODE_B", "CODE_C"}

    def test_missing_required_code_rejected(self, resolver, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="CODE_A")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1")
            s.commit()

        with pytest.raises(CoefficientNotApprovedError, match="required_coefficient_missing"):
            resolver.resolve(
                criteria=_criteria(required_codes=("CODE_A", "CODE_B")),
                session=pg_session_factory(),
            )

    def test_non_required_definition_not_in_context(self, resolver, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="REQUIRED")
            _seed_definition(s, def_id="d2", code="EXTRA")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1")
            _seed_approved_revision(s, rev_id="r2", definition_id="d2")
            s.commit()

        candidate = resolver.resolve(
            criteria=_criteria(required_codes=("REQUIRED",)),
            session=pg_session_factory(),
        )
        codes = {item["code"] for item in candidate.content["coefficients"]}
        assert codes == {"REQUIRED"}, f"Only REQUIRED should be in context, got {codes}"

    def test_exact_required_set(self, resolver, pg_session_factory) -> None:
        """Only the exact required set is returned — no extras."""
        with pg_session_factory() as s:
            _clear_tables(s)
            for i in range(5):
                _seed_definition(s, def_id=f"d{i}", code=f"EXACT_{i}")
                _seed_approved_revision(s, rev_id=f"r{i}", definition_id=f"d{i}")
            s.commit()

        candidate = resolver.resolve(
            criteria=_criteria(required_codes=("EXACT_1", "EXACT_3")),
            session=pg_session_factory(),
        )
        codes = [item["code"] for item in candidate.content["coefficients"]]
        assert sorted(codes) == ["EXACT_1", "EXACT_3"]
        assert candidate.content["coefficient_count"] == 2


# ── Supersession ─────────────────────────────────────────────────────────


class TestSupersessionPG:
    """Supersession DAG validation on PostgreSQL."""

    def test_single_supersession_chain(self, resolver, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _clear_tables(s)
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
            criteria=_criteria(required_codes=("SINGLE",)),
            session=pg_session_factory(),
        )
        assert candidate.approved_revision_ids == ("r2",)

    def test_two_level_supersession(self, resolver, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _clear_tables(s)
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
            criteria=_criteria(required_codes=("LEVELS",)),
            session=pg_session_factory(),
        )
        assert candidate.approved_revision_ids == ("r3",)

    def test_self_loop_rejected(self, resolver, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="LOOP")
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                revision_number=1,
                supersedes_revision_id="r1",
            )
            s.commit()

        with pytest.raises(CoefficientResolutionError, match="supersession"):
            resolver.resolve(
                criteria=_criteria(required_codes=("LOOP",)),
                session=pg_session_factory(),
            )

    def test_cycle_rejected(self, resolver, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _clear_tables(s)
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
                supersedes_revision_id="r1",
            )
            s.commit()

        with pytest.raises(CoefficientResolutionError, match="cycle"):
            resolver.resolve(
                criteria=_criteria(required_codes=("CYCLE",)),
                session=pg_session_factory(),
            )

    def test_multiple_terminal_heads_rejected(self, resolver, pg_session_factory) -> None:
        """Multiple un-superseded terminal heads → AmbiguousCoefficientError."""
        with pg_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="MULTI")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1", revision_number=1)
            _seed_approved_revision(s, rev_id="r2", definition_id="d1", revision_number=2)
            s.commit()

        with pytest.raises(AmbiguousCoefficientError, match="ambiguous"):
            resolver.resolve(
                criteria=_criteria(required_codes=("MULTI",)),
                session=pg_session_factory(),
            )

    def test_superseded_revision_withdrawn(self, resolver, pg_session_factory) -> None:
        """Superseding revision that is withdrawn should not be terminal."""
        now = datetime.now(UTC)
        with pg_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="WITHDRAWN")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1", revision_number=1)
            _seed_approved_revision(
                s,
                rev_id="r2",
                definition_id="d1",
                revision_number=2,
                supersedes_revision_id="r1",
                withdrawn_at=now,
            )
            s.commit()

        candidate = resolver.resolve(
            criteria=_criteria(required_codes=("WITHDRAWN",)),
            session=pg_session_factory(),
        )
        assert "r1" in candidate.approved_revision_ids


# ── Value canonicalization ───────────────────────────────────────────────


class TestValueCanonicalizationPG:
    """Decimal and JSON value canonicalization on PostgreSQL."""

    def test_decimal_equivalent_forms_same_hash(self, resolver, pg_session_factory) -> None:
        """1.0 and 1.00 should produce identical canonical value_decimal."""

        def _resolve_with_value(value: str):
            code = f"EQ_{value.replace('.', '_')}"
            with pg_session_factory() as s:
                _clear_tables(s)
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
                session=pg_session_factory(),
            )

        c1 = _resolve_with_value("1.0")
        c2 = _resolve_with_value("1.00")

        v1 = c1.content["coefficients"][0]["value_decimal"]
        v2 = c2.content["coefficients"][0]["value_decimal"]
        assert v1 == v2 == "1", f"Expected canonical '1', got {v1!r} vs {v2!r}"

    def test_decimal_value_change_changes_hash(self, resolver, pg_session_factory) -> None:
        def _build(value: str) -> str:
            with pg_session_factory() as s:
                _clear_tables(s)
                _seed_definition(s, def_id="d1", code="CHG")
                _seed_approved_revision(s, rev_id="r1", definition_id="d1", value_decimal=value)
                s.commit()
            candidate = resolver.resolve(
                criteria=_criteria(required_codes=("CHG",)),
                session=pg_session_factory(),
            )
            return candidate.content_hash

        h1 = _build("1.0")
        h2 = _build("2.0")
        assert h1 != h2, "Different values should produce different hashes"

    def test_json_value_in_content(self, resolver, pg_session_factory) -> None:
        import json as _json

        with pg_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="JSON", value_type="json")
            rev = CoefficientRevisionRecord(
                id="r1",
                coefficient_definition_id="d1",
                revision_number=1,
                unit="dimensionless",
                status="approved",
                source_type="standard",
                value_json=_json.dumps({"a": 1, "b": 2}),
                created_by="test",
                created_at=datetime.now(UTC),
                approved_at=datetime.now(UTC),
                approved_by="test",
            )
            s.add(rev)
            s.commit()

        candidate = resolver.resolve(
            criteria=_criteria(required_codes=("JSON",)),
            session=pg_session_factory(),
        )
        coeffs = candidate.content["coefficients"]
        assert len(coeffs) == 1
        assert coeffs[0]["value_json"] == {"a": 1, "b": 2}


# ── Unit mismatch ────────────────────────────────────────────────────────


class TestUnitMismatchPG:
    """Revision unit must match definition canonical_unit."""

    def test_unit_mismatch_raises(self, resolver, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _clear_tables(s)
            _seed_definition(
                s,
                def_id="d1",
                code="UNIT_MM",
                canonical_unit="kW",
            )
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                unit="W",  # mismatch: kW vs W
            )
            s.commit()

        with pytest.raises(CoefficientResolutionError, match="invalid_unit"):
            resolver.resolve(
                criteria=_criteria(required_codes=("UNIT_MM",)),
                session=pg_session_factory(),
            )

    def test_unit_match_resolves(self, resolver, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _clear_tables(s)
            _seed_definition(
                s,
                def_id="d1",
                code="UNIT_OK",
                canonical_unit="kW",
            )
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                unit="kW",
            )
            s.commit()

        candidate = resolver.resolve(
            criteria=_criteria(required_codes=("UNIT_OK",)),
            session=pg_session_factory(),
        )
        assert "r1" in candidate.approved_revision_ids


# ── Inactive / draft / withdrawn / expired ───────────────────────────────


class TestInactiveDraftExpiredPG:
    """Inactive definitions, draft/withdrawn/expired revisions on PostgreSQL."""

    def test_inactive_definition_excluded(self, resolver, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="INACTIVE", is_active=False)
            _seed_approved_revision(s, rev_id="r1", definition_id="d1")
            s.commit()

        with pytest.raises(CoefficientNotApprovedError):
            resolver.resolve(
                criteria=_criteria(required_codes=("INACTIVE",)),
                session=pg_session_factory(),
            )

    def test_draft_revision_not_used(self, resolver, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="DRAFT")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1", status="draft")
            s.commit()

        with pytest.raises(CoefficientNotApprovedError):
            resolver.resolve(
                criteria=_criteria(required_codes=("DRAFT",)),
                session=pg_session_factory(),
            )

    def test_withdrawn_revision_excluded(self, resolver, pg_session_factory) -> None:
        now = datetime.now(UTC)
        with pg_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="WDRN")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1", withdrawn_at=now)
            s.commit()

        with pytest.raises(CoefficientNotApprovedError):
            resolver.resolve(
                criteria=_criteria(required_codes=("WDRN",)),
                session=pg_session_factory(),
            )

    def test_expired_revision_excluded(self, resolver, pg_session_factory) -> None:
        now = datetime.now(UTC)
        past = now - timedelta(days=10)
        with pg_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="EXPIRED")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1", valid_to=past)
            s.commit()

        with pytest.raises(CoefficientNotApprovedError):
            resolver.resolve(
                criteria=_criteria(required_codes=("EXPIRED",)),
                session=pg_session_factory(),
            )

    def test_future_revision_excluded(self, resolver, pg_session_factory) -> None:
        future = datetime.now(UTC) + timedelta(days=30)
        with pg_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="FUTURE")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1", valid_from=future)
            s.commit()

        with pytest.raises(CoefficientNotApprovedError):
            resolver.resolve(
                criteria=_criteria(required_codes=("FUTURE",)),
                session=pg_session_factory(),
            )


# ── Canonical ordering ──────────────────────────────────────────────────


class TestCanonicalOrderPG:
    """Coefficient items are sorted by definition.code ASC."""

    def test_canonical_order_by_code(self, resolver, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _clear_tables(s)
            # Insert in reverse-alpha order
            _seed_definition(s, def_id="d3", code="ZZZ")
            _seed_definition(s, def_id="d1", code="AAA")
            _seed_definition(s, def_id="d2", code="MMM")
            _seed_approved_revision(s, rev_id="r3", definition_id="d3")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1")
            _seed_approved_revision(s, rev_id="r2", definition_id="d2")
            s.commit()

        candidate = resolver.resolve(
            criteria=_criteria(required_codes=("ZZZ", "AAA", "MMM")),
            session=pg_session_factory(),
        )
        codes = [item["code"] for item in candidate.content["coefficients"]]
        assert codes == sorted(codes), f"Expected sorted order, got {codes}"
        assert codes == ["AAA", "MMM", "ZZZ"]


# ── Content structure ────────────────────────────────────────────────────


class TestContentStructurePG:
    """Verify content dict structure and metadata fields."""

    def test_content_has_requirement_metadata(self, resolver, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="META")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1")
            s.commit()

        criteria = FrozenCoefficientResolutionCriteria(
            project_id="p-1",
            project_version_id="pv-1",
            required_codes=("META",),
            requirement_registry_version="1.0.0",
            calculator_version_vector={"zone": "1.0.0"},
            requirement_hash="abc123",
        )
        candidate = resolver.resolve(
            criteria=criteria,
            session=pg_session_factory(),
        )
        content = candidate.content
        assert content["requirement_registry_version"] == "1.0.0"
        assert content["calculator_version_vector"] == {"zone": "1.0.0"}
        assert content["required_codes"] == ["META"]
        assert content["requirement_hash"] == "abc123"
        assert content["schema_version"] == "1.0.0"
        assert content["source_type"] == "catalog"

    def test_approved_revision_ids_in_canonical_order(self, resolver, pg_session_factory) -> None:
        with pg_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="B_CODE")
            _seed_definition(s, def_id="d2", code="A_CODE")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1")
            _seed_approved_revision(s, rev_id="r2", definition_id="d2")
            s.commit()

        candidate = resolver.resolve(
            criteria=_criteria(required_codes=("B_CODE", "A_CODE")),
            session=pg_session_factory(),
        )
        # approved_revision_ids should be in canonical (code-sorted) order
        assert candidate.approved_revision_ids == ("r2", "r1")


# ── Cross-DB consistency ────────────────────────────────────────────────


class TestCrossDBConsistency:
    """Compare SQLite and PostgreSQL resolver output for same seed data.

    Ensures content, content_hash, approved_revision_ids, and canonical
    order are identical regardless of database backend.
    """

    def test_sqlite_pg_output_matches(self, pg_session_factory) -> None:
        """Run the same seed data through both SQLite (tmp) and PG resolvers."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from cold_storage.modules.orchestration.domain.fingerprint import result_hash

        # ── Seed shared test data ─────────────────────────────────────
        fixed_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

        def _seed_data(session: Session) -> None:
            _clear_tables(session)
            _seed_definition(session, def_id="d1", code="CROSS_A", scope_type="global")
            _seed_definition(
                session,
                def_id="d2",
                code="CROSS_B",
                scope_type="product",
            )
            _seed_approved_revision(session, rev_id="r1", definition_id="d1", value_decimal="2.5", approved_at_override=fixed_time)
            _seed_approved_revision(
                session,
                rev_id="r2",
                definition_id="d2",
                value_decimal="0.75",
                applicable_product_type="blueberry",
                approved_at_override=fixed_time,
            )
            session.commit()

        criteria = _criteria(
            required_codes=("CROSS_A", "CROSS_B"),
            product_type="blueberry",
        )
        resolver = SqlAlchemyCoefficientResolutionAdapter()

        # ── PostgreSQL result ─────────────────────────────────────────
        with pg_session_factory() as s:
            _seed_data(s)
        pg_result = resolver.resolve(
            criteria=criteria,
            session=pg_session_factory(),
        )

        # ── SQLite result ─────────────────────────────────────────────
        sqlite_engine = create_engine("sqlite:///:memory:")
        from cold_storage.modules.projects.infrastructure.orm import Base as ProjectBase

        ProjectBase.metadata.create_all(sqlite_engine)
        sqlite_factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
        with sqlite_factory() as s:
            _seed_data(s)
        sqlite_result = resolver.resolve(
            criteria=criteria,
            session=sqlite_factory(),
        )

        # ── Compare outputs ───────────────────────────────────────────
        assert sqlite_result.content == pg_result.content, (
            "Content dict must be identical across SQLite and PostgreSQL"
        )
        assert sqlite_result.content_hash == pg_result.content_hash, (
            "Content hash must be identical across SQLite and PostgreSQL"
        )
        assert sqlite_result.approved_revision_ids == pg_result.approved_revision_ids, (
            "Approved revision IDs (canonical order) must be identical"
        )

        # Verify both produce valid hashes
        assert result_hash(pg_result.content) == pg_result.content_hash
        assert result_hash(sqlite_result.content) == sqlite_result.content_hash

        sqlite_engine.dispose()
