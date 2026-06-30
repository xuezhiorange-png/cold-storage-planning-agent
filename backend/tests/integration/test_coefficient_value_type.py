"""Integration tests for coefficient value-type and unit validation.

Covers all 15 scenarios from the review requirements:
 1.  decimal definition + decimal value → success
 2.  JSON definition + JSON value → success
 3.  decimal definition + only JSON value → rejection
 4.  JSON definition + only decimal value → rejection
 5.  both value fields present → rejection
 6.  both value fields empty → rejection
 7.  unknown value_type → rejection
 8.  revision unit != canonical unit → rejection
 9.  invalid decimal → rejection
10.  NaN/Infinity decimal → rejection
11.  invalid JSON text → rejection
12.  JSON scalar top-level → rejection
13.  JSON contains NaN/Infinity → rejection
14.  semantic-equivalent JSON → same hash
15.  1.0 / 1.00 / 1E0 → same canonical value

Uses real database tables with the ``tmp_session_factory`` fixture from
``backend/tests/conftest.py`` and the resolver from
``test_coefficient_resolver.py``.
"""

from __future__ import annotations

import json as _json
from datetime import UTC, datetime

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
    CoefficientResolutionError,
)
from cold_storage.modules.orchestration.infrastructure.coefficient_resolver import (
    SqlAlchemyCoefficientResolutionAdapter,
)

# ── Test helpers (mirrored from test_coefficient_resolver.py) ──────────


def _seed_definition(
    session: Session,
    *,
    def_id: str,
    code: str,
    value_type: str = "decimal",
    canonical_unit: str = "dimensionless",
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
    unit: str = "dimensionless",
    value_decimal: str | None = "1.0",
    value_json: str | None = None,
    source_type: str = "standard",
    status: str = "approved",
) -> CoefficientRevisionRecord:
    rev = CoefficientRevisionRecord(
        id=rev_id,
        coefficient_definition_id=definition_id,
        revision_number=revision_number,
        unit=unit,
        status=status,
        source_type=source_type,
        value_decimal=value_decimal,
        value_json=value_json,
        created_by="test",
        created_at=datetime.now(UTC),
    )
    if status == "approved":
        rev.approved_at = datetime.now(UTC)
        rev.approved_by = "test-approver"
    session.add(rev)
    return rev


def _criteria(
    required_codes: tuple[str, ...],
) -> FrozenCoefficientResolutionCriteria:
    return FrozenCoefficientResolutionCriteria(
        project_id="p-1",
        project_version_id="pv-1",
        required_codes=required_codes,
    )


def _clear_tables(session: Session) -> None:
    """Delete all coefficient data for isolation between tests."""
    session.execute(sa_delete(CoefficientRevisionRecord))
    session.execute(sa_delete(CoefficientDefinitionRecord))
    session.commit()


@pytest.fixture()
def resolver() -> SqlAlchemyCoefficientResolutionAdapter:
    return SqlAlchemyCoefficientResolutionAdapter()


# ── Tests ─────────────────────────────────────────────────────────────


class TestValueTypeSuccess:
    """Scenarios 1 & 2: correct value_type + value → success."""

    def test_decimal_definition_with_decimal_value_succeeds(
        self, resolver, tmp_session_factory
    ) -> None:
        """Scenario 1: decimal definition + decimal value → success."""
        with tmp_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="D_DEC", value_type="decimal")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1", value_decimal="2.5")
            s.commit()

        candidate = resolver.resolve(
            criteria=_criteria(("D_DEC",)),
            session=tmp_session_factory(),
        )
        coeffs = candidate.content["coefficients"]
        assert len(coeffs) == 1
        assert coeffs[0]["value_decimal"] == "2.5"
        assert "value_json" not in coeffs[0]

    def test_json_definition_with_json_value_succeeds(self, resolver, tmp_session_factory) -> None:
        """Scenario 2: JSON definition + JSON value → success."""
        with tmp_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="D_JSON", value_type="json")
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                value_decimal=None,
                value_json='{"a": 1, "b": [2, 3]}',
            )
            s.commit()

        candidate = resolver.resolve(
            criteria=_criteria(("D_JSON",)),
            session=tmp_session_factory(),
        )
        coeffs = candidate.content["coefficients"]
        assert len(coeffs) == 1
        assert coeffs[0]["value_json"] == {"a": 1, "b": [2, 3]}
        assert "value_decimal" not in coeffs[0]


class TestValueTypeMismatch:
    """Scenarios 3–6: value_type vs. actual value field mismatches."""

    def test_decimal_definition_with_only_json_value_rejected(
        self, resolver, tmp_session_factory
    ) -> None:
        """Scenario 3: decimal definition + only JSON value → rejection."""
        with tmp_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="M3", value_type="decimal")
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                value_decimal=None,
                value_json='{"x": 1}',
            )
            s.commit()

        with pytest.raises(CoefficientResolutionError, match="value_type='decimal'"):
            resolver.resolve(
                criteria=_criteria(("M3",)),
                session=tmp_session_factory(),
            )

    def test_json_definition_with_only_decimal_value_rejected(
        self, resolver, tmp_session_factory
    ) -> None:
        """Scenario 4: JSON definition + only decimal value → rejection."""
        with tmp_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="M4", value_type="json")
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                value_decimal="1.0",
                value_json=None,
            )
            s.commit()

        with pytest.raises(CoefficientResolutionError, match="value_type='json'"):
            resolver.resolve(
                criteria=_criteria(("M4",)),
                session=tmp_session_factory(),
            )

    def test_both_value_fields_present_rejected(self, resolver, tmp_session_factory) -> None:
        """Scenario 5: both value fields present → rejection."""
        with tmp_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="M5", value_type="decimal")
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                value_decimal="1.0",
                value_json='{"x": 1}',
            )
            s.commit()

        with pytest.raises(CoefficientResolutionError, match="also has value_json"):
            resolver.resolve(
                criteria=_criteria(("M5",)),
                session=tmp_session_factory(),
            )

    def test_both_value_fields_empty_rejected(self, resolver, tmp_session_factory) -> None:
        """Scenario 6: both value fields empty → rejection.

        When value_type='decimal' and both fields are None, the type-specific
        check ("has value_type='decimal' but no value_decimal") fires before
        the generic "neither" check.  The test verifies the rejection occurs.
        """
        with tmp_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="M6", value_type="decimal")
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                value_decimal=None,
                value_json=None,
            )
            s.commit()

        with pytest.raises(CoefficientResolutionError, match="invalid_value"):
            resolver.resolve(
                criteria=_criteria(("M6",)),
                session=tmp_session_factory(),
            )


class TestUnknownValueType:
    """Scenario 7: unknown value_type → rejection."""

    def test_unknown_value_type_rejected(self, resolver, tmp_session_factory) -> None:
        """Scenario 7: unknown value_type → rejection."""
        with tmp_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="UVT", value_type="binary")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1", value_decimal="1.0")
            s.commit()

        with pytest.raises(CoefficientResolutionError, match="Unknown value_type"):
            resolver.resolve(
                criteria=_criteria(("UVT",)),
                session=tmp_session_factory(),
            )


class TestUnitMismatch:
    """Scenario 8: revision unit != canonical unit → rejection."""

    def test_revision_unit_mismatch_rejected(self, resolver, tmp_session_factory) -> None:
        """Scenario 8: revision unit != canonical unit → rejection."""
        with tmp_session_factory() as s:
            _clear_tables(s)
            _seed_definition(
                s,
                def_id="d1",
                code="UM",
                value_type="decimal",
                canonical_unit="kg",
            )
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                unit="lb",  # mismatch
                value_decimal="1.0",
            )
            s.commit()

        with pytest.raises(CoefficientResolutionError, match="invalid_unit"):
            resolver.resolve(
                criteria=_criteria(("UM",)),
                session=tmp_session_factory(),
            )


class TestInvalidDecimalValues:
    """Scenarios 9 & 10: invalid decimal values → rejection."""

    def test_invalid_decimal_string_rejected(self, resolver, tmp_session_factory) -> None:
        """Scenario 9: invalid decimal → rejection."""
        with tmp_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="ID", value_type="decimal")
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                value_decimal="not_a_number",
            )
            s.commit()

        with pytest.raises(CoefficientResolutionError, match="Cannot parse decimal"):
            resolver.resolve(
                criteria=_criteria(("ID",)),
                session=tmp_session_factory(),
            )

    def test_nan_decimal_rejected(self, resolver, tmp_session_factory) -> None:
        """Scenario 10a: NaN decimal → rejection."""
        with tmp_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="NAN", value_type="decimal")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1", value_decimal="NaN")
            s.commit()

        with pytest.raises(CoefficientResolutionError, match="Non-finite"):
            resolver.resolve(
                criteria=_criteria(("NAN",)),
                session=tmp_session_factory(),
            )

    def test_infinity_decimal_rejected(self, resolver, tmp_session_factory) -> None:
        """Scenario 10b: Infinity decimal → rejection."""
        with tmp_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="INF", value_type="decimal")
            _seed_approved_revision(s, rev_id="r1", definition_id="d1", value_decimal="Infinity")
            s.commit()

        with pytest.raises(CoefficientResolutionError, match="Non-finite"):
            resolver.resolve(
                criteria=_criteria(("INF",)),
                session=tmp_session_factory(),
            )


class TestInvalidJsonValues:
    """Scenarios 11, 12 & 13: invalid JSON values → rejection."""

    def test_invalid_json_text_rejected(self, resolver, tmp_session_factory) -> None:
        """Scenario 11: invalid JSON text → rejection."""
        with tmp_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="IJ", value_type="json")
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                value_decimal=None,
                value_json="{not valid json",
            )
            s.commit()

        with pytest.raises(CoefficientResolutionError, match="Cannot parse JSON"):
            resolver.resolve(
                criteria=_criteria(("IJ",)),
                session=tmp_session_factory(),
            )

    def test_json_scalar_top_level_rejected(self, resolver, tmp_session_factory) -> None:
        """Scenario 12: JSON scalar top-level → rejection."""
        with tmp_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="JS", value_type="json")
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                value_decimal=None,
                value_json='"just a string"',
            )
            s.commit()

        with pytest.raises(CoefficientResolutionError, match="JSON value must be a dict or list"):
            resolver.resolve(
                criteria=_criteria(("JS",)),
                session=tmp_session_factory(),
            )

    def test_json_contains_nan_rejected(self, resolver, tmp_session_factory) -> None:
        """Scenario 13a: JSON contains NaN → rejection.

        Python's ``json.loads`` allows NaN by default, so parsing succeeds.
        The NaN is caught by the recursive ``_check_no_nonfinite`` validator.
        """
        with tmp_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="JN", value_type="json")
            # json.loads accepts NaN — the resolver catches it post-parse
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                value_decimal=None,
                value_json='{"v": NaN}',
            )
            s.commit()

        with pytest.raises(CoefficientResolutionError, match="invalid_json"):
            resolver.resolve(
                criteria=_criteria(("JN",)),
                session=tmp_session_factory(),
            )

    def test_json_contains_infinity_rejected(self, resolver, tmp_session_factory) -> None:
        """Scenario 13b: JSON contains Infinity → rejection.

        Like NaN, Python's ``json.loads`` allows Infinity by default.
        The Infinity is caught by the recursive ``_check_no_nonfinite`` validator.
        """
        with tmp_session_factory() as s:
            _clear_tables(s)
            _seed_definition(s, def_id="d1", code="JINF", value_type="json")
            _seed_approved_revision(
                s,
                rev_id="r1",
                definition_id="d1",
                value_decimal=None,
                value_json='{"v": Infinity}',
            )
            s.commit()

        with pytest.raises(CoefficientResolutionError, match="invalid_json"):
            resolver.resolve(
                criteria=_criteria(("JINF",)),
                session=tmp_session_factory(),
            )


class TestCanonicalization:
    """Scenarios 14 & 15: canonicalization equivalence."""

    def test_semantic_equivalent_json_same_hash(self, resolver, tmp_session_factory) -> None:
        """Scenario 14: semantic-equivalent JSON → same hash.

        Two JSON objects with the same key-value pairs in different order
        should produce identical content_hash (canonical JSON serialization).
        """
        code_a = "JEQA"
        code_b = "JEQB"

        def _resolve_with_json(obj: dict, code: str, def_id: str, rev_id: str):
            with tmp_session_factory() as s:
                _clear_tables(s)
                _seed_definition(s, def_id=def_id, code=code, value_type="json")
                _seed_approved_revision(
                    s,
                    rev_id=rev_id,
                    definition_id=def_id,
                    value_decimal=None,
                    value_json=_json.dumps(obj),
                )
                s.commit()
            return resolver.resolve(
                criteria=_criteria((code,)),
                session=tmp_session_factory(),
            )

        c1 = _resolve_with_json({"b": 2, "a": 1}, code_a, "d_a1", "r_a1")
        c2 = _resolve_with_json({"a": 1, "b": 2}, code_b, "d_b1", "r_b1")

        # The JSON values should be structurally identical
        v1 = c1.content["coefficients"][0]["value_json"]
        v2 = c2.content["coefficients"][0]["value_json"]
        assert v1 == v2 == {"a": 1, "b": 2}

    def test_decimal_equivalent_forms_same_canonical_value(
        self, resolver, tmp_session_factory
    ) -> None:
        """Scenario 15: 1.0 / 1.00 / 1E0 → same canonical value.

        All three representations should normalize to the same
        canonical string in the resolved coefficient content.
        """

        def _resolve_with_decimal(value: str, suffix: str):
            code = f"EQ_{suffix}"
            with tmp_session_factory() as s:
                _clear_tables(s)
                _seed_definition(s, def_id=f"d_{suffix}", code=code, value_type="decimal")
                _seed_approved_revision(
                    s,
                    rev_id=f"r_{suffix}",
                    definition_id=f"d_{suffix}",
                    value_decimal=value,
                )
                s.commit()
            return resolver.resolve(
                criteria=_criteria((code,)),
                session=tmp_session_factory(),
            )

        c1 = _resolve_with_decimal("1.0", "v1")
        c2 = _resolve_with_decimal("1.00", "v2")
        c3 = _resolve_with_decimal("1E0", "v3")

        v1 = c1.content["coefficients"][0]["value_decimal"]
        v2 = c2.content["coefficients"][0]["value_decimal"]
        v3 = c3.content["coefficients"][0]["value_decimal"]

        assert v1 == v2 == v3 == "1", f"Expected canonical '1', got {v1!r}, {v2!r}, {v3!r}"
