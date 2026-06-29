"""Integration test: calculator-coefficient contract catalog existence.

Verifies that every coefficient code referenced by the calculator-coefficient
requirement registry (``REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION``) exists
as an active ``CoefficientDefinitionRecord`` in the database.

This test is the catalog-side enforcement of ADR-026.  If a code is added to
the registry but missing from the catalog seed data, this test will fail.

Uses the ``tmp_session_factory`` fixture (SQLite-backed) from the root conftest
and seeds real ``CoefficientDefinitionRecord`` rows via the canonical
:func:`~cold_storage.modules.coefficients.domain.catalog.seed_catalog`.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from cold_storage.modules.coefficients.domain.catalog import (
    COEFFICIENT_CATALOG,
)
from cold_storage.modules.coefficients.infrastructure.orm import (
    CoefficientDefinitionRecord,
    CoefficientRevisionRecord,
)
from cold_storage.modules.coefficients.infrastructure.seed import (
    seed_catalog,
)
from cold_storage.modules.orchestration.application.coefficient_contracts import (
    REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION,
    derive_required_codes_for_version_vector,
)

# ── Canonical calculator version vector (mirrors service.py) ─────────────

_CALCULATOR_VERSION_VECTOR: dict[str, str] = {
    "zone": "1.0.0",
    "cooling_load": "1.0.0",
    "equipment": "1.0.0",
    "power": "1.0.0",
    "investment": "1.0.0",
}

# Codes that are intentionally shared across multiple calculators
_INTENTIONALLY_SHARED_CODES: frozenset[str] = frozenset(
    {
        "power.design_margin_ratio",
    }
)

# Minimum expected registry version (non-empty check)
_REGISTRY_VERSION = "1.0.0"


# ── Helpers ──────────────────────────────────────────────────────────────


def _all_registry_codes() -> set[str]:
    """Return the deduplicated set of all codes in the registry."""
    codes: set[str] = set()
    for required in REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION.values():
        codes.update(required)
    return codes


# ── Tests ────────────────────────────────────────────────────────────────


class TestCalculatorCoefficientContract:
    """Verify the calculator-coefficient requirement contract against the catalog."""

    def test_registry_version_is_non_empty(self) -> None:
        """Registry version must be a non-empty string."""
        assert _REGISTRY_VERSION, "Registry version must be non-empty"

    def test_registry_is_non_empty(self) -> None:
        """Registry must contain at least one entry."""
        assert REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION, (
            "REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION is empty"
        )

    def test_every_calculator_in_version_vector_has_registry_binding(
        self,
    ) -> None:
        """Every calculator in _CALCULATOR_VERSION_VECTOR must have a registry entry."""
        for calc_name, calc_version in _CALCULATOR_VERSION_VECTOR.items():
            key = (calc_name, calc_version)
            assert key in REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION, (
                f"Calculator {key!r} from _CALCULATOR_VERSION_VECTOR "
                f"has no binding in REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION"
            )

    def test_no_unknown_calculators_in_registry(self) -> None:
        """Registry must not contain calculators not in _CALCULATOR_VERSION_VECTOR."""
        known_keys = {(name, ver) for name, ver in _CALCULATOR_VERSION_VECTOR.items()}
        for key in REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION:
            assert key in known_keys, f"Registry key {key!r} is not in _CALCULATOR_VERSION_VECTOR"

    def test_no_unexpected_shared_codes(self) -> None:
        """Codes shared across calculators must be in the intentional set."""
        code_to_calculators: dict[str, list[tuple[str, str]]] = {}
        for key, codes in REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION.items():
            for code in codes:
                code_to_calculators.setdefault(code, []).append(key)

        for code, calculators in code_to_calculators.items():
            if len(calculators) > 1:
                assert code in _INTENTIONALLY_SHARED_CODES, (
                    f"Code {code!r} is shared across {calculators} but is not "
                    f"in _INTENTIONALLY_SHARED_CODES"
                )

    def test_all_codes_exist_as_active_definitions(
        self,
        tmp_session_factory,
    ) -> None:
        """Every code in the registry must exist as an active definition."""
        with tmp_session_factory() as session:
            seed_catalog(session)

        required_codes = _all_registry_codes()
        with tmp_session_factory() as session:
            rows = (
                session.query(CoefficientDefinitionRecord)
                .filter(
                    CoefficientDefinitionRecord.code.in_(sorted(required_codes)),
                )
                .all()
            )

        found_codes = {r.code for r in rows}
        missing = required_codes - found_codes
        assert not missing, f"Missing CoefficientDefinitionRecord for codes: {sorted(missing)}"

        inactive = {r.code for r in rows if not r.is_active}
        assert not inactive, f"Inactive CoefficientDefinitionRecord for codes: {sorted(inactive)}"

    def test_catalog_definitions_have_correct_metadata(
        self,
        tmp_session_factory,
    ) -> None:
        """Seeded catalog definitions must have correct metadata fields."""
        with tmp_session_factory() as session:
            seed_catalog(session)

        expected_by_code = {entry["code"]: entry for entry in COEFFICIENT_CATALOG}

        with tmp_session_factory() as session:
            rows = session.execute(select(CoefficientDefinitionRecord)).scalars().all()

        for row in rows:
            expected = expected_by_code[row.code]
            assert row.value_type == expected["value_type"], (
                f"{row.code}: value_type={row.value_type!r}, expected={expected['value_type']!r}"
            )
            assert row.canonical_unit == expected["canonical_unit"], (
                f"{row.code}: canonical_unit={row.canonical_unit!r}, "
                f"expected={expected['canonical_unit']!r}"
            )
            assert row.scope_type == expected["scope_type"], (
                f"{row.code}: scope_type={row.scope_type!r}, expected={expected['scope_type']!r}"
            )
            assert row.is_active is True, f"{row.code}: is_active={row.is_active!r}, expected=True"

    def test_each_code_has_exactly_one_approved_revision(
        self,
        tmp_session_factory,
    ) -> None:
        """Each catalog code must have exactly one approved revision after seeding."""
        with tmp_session_factory() as session:
            seed_catalog(session)

        with tmp_session_factory() as session:
            defs = session.execute(select(CoefficientDefinitionRecord)).scalars().all()
            for defn in defs:
                revisions = (
                    session.execute(
                        select(CoefficientRevisionRecord).where(
                            CoefficientRevisionRecord.coefficient_definition_id == defn.id
                        )
                    )
                    .scalars()
                    .all()
                )
                assert len(revisions) == 1, (
                    f"{defn.code}: expected 1 revision, got {len(revisions)}"
                )
                assert revisions[0].status == "approved", (
                    f"{defn.code}: revision status={revisions[0].status!r}, expected='approved'"
                )

    def test_derive_required_codes_returns_consistent_results(self) -> None:
        """derive_required_codes_for_version_vector returns sorted, deduplicated codes."""
        codes = derive_required_codes_for_version_vector(_CALCULATOR_VERSION_VECTOR)

        # Must be a tuple
        assert isinstance(codes, tuple)

        # Must be sorted
        assert list(codes) == sorted(codes), "Codes must be sorted"

        # Must be deduplicated
        assert len(codes) == len(set(codes)), "Codes must be deduplicated"

        # Must contain all expected codes
        expected = _all_registry_codes()
        assert set(codes) == expected, (
            f"Mismatch: derived={sorted(set(codes))}, expected={sorted(expected)}"
        )

    def test_derive_required_codes_raises_for_unknown_calculator(self) -> None:
        """derive_required_codes_for_version_vector raises for unknown calculators."""
        with pytest.raises(ValueError, match="not found"):
            derive_required_codes_for_version_vector({"unknown_calc": "1.0.0"})

    def test_no_duplicate_codes_within_single_calculator(self) -> None:
        """Each calculator's required_codes must not contain duplicates."""
        for key, codes in REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION.items():
            assert len(codes) == len(set(codes)), (
                f"Calculator {key!r} has duplicate codes: "
                f"{sorted(c for c in codes if codes.count(c) > 1)}"
            )
