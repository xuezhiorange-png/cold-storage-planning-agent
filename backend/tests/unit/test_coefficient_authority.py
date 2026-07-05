"""Tests for coefficient authority features.

Covers:
- validate_required_codes() canonicalization and rejection rules
- REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION registry integrity
- _validate_caller_conflicts() conflict detection for all fields
- _derive_frozen_criteria() authoritative derivation and snapshot consistency
"""

from __future__ import annotations

import pytest

from cold_storage.modules.orchestration.application.coefficient_contracts import (
    REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION,
    derive_required_codes_for_version_vector,
    validate_required_codes,
)
from cold_storage.modules.orchestration.application.service import (
    _derive_frozen_criteria,
    _LoadedVersion,
    _validate_caller_conflicts,
)
from cold_storage.modules.orchestration.domain.contracts import (
    OrchestrationRequestCommand,
)
from cold_storage.modules.orchestration.domain.errors import (
    CoefficientResolutionError,
)

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_command(
    *,
    project_id: str = "p1",
    project_version_id: str = "pv1",
    coefficient_resolution_context: dict[str, object] | None = None,
    actor: str = "tester",
    correlation_id: str = "corr-1",
) -> OrchestrationRequestCommand:
    return OrchestrationRequestCommand(
        project_id=project_id,
        project_version_id=project_version_id,
        coefficient_resolution_context=coefficient_resolution_context or {},
        actor=actor,
        correlation_id=correlation_id,
    )


def _make_version(
    *,
    project_id: str = "p1",
    project_product_category: str = "blueberry",
    status: str = "approved",
    input_snapshot: dict[str, object] | None = None,
) -> _LoadedVersion:
    return _LoadedVersion(
        project_id=project_id,
        project_product_category=project_product_category,
        status=status,
        input_snapshot=input_snapshot,
    )


# ── 1. validate_required_codes ────────────────────────────────────────────


class TestRequiredCodesValidation:
    """Unit tests for validate_required_codes()."""

    def test_valid_list_returns_sorted_tuple(self) -> None:
        result = validate_required_codes(["c", "a", "b"])
        assert result == ("a", "b", "c")
        assert isinstance(result, tuple)

    def test_valid_tuple_returns_sorted_tuple(self) -> None:
        result = validate_required_codes(("z", "m", "a"))
        assert result == ("a", "m", "z")

    def test_non_list_tuple_rejected(self) -> None:
        with pytest.raises(CoefficientResolutionError, match="must be a list or tuple"):
            validate_required_codes("not_a_list")

    def test_dict_rejected(self) -> None:
        with pytest.raises(CoefficientResolutionError, match="must be a list or tuple"):
            validate_required_codes({"a": 1})

    def test_int_rejected(self) -> None:
        with pytest.raises(CoefficientResolutionError, match="must be a list or tuple"):
            validate_required_codes(42)

    def test_non_string_member_rejected(self) -> None:
        with pytest.raises(CoefficientResolutionError, match="must be a string"):
            validate_required_codes(["valid", 123])

    def test_none_member_rejected(self) -> None:
        with pytest.raises(CoefficientResolutionError, match="must be a string"):
            validate_required_codes(["valid", None])

    def test_blank_member_rejected(self) -> None:
        with pytest.raises(CoefficientResolutionError, match="must not be blank"):
            validate_required_codes(["valid", ""])

    def test_whitespace_only_member_rejected(self) -> None:
        with pytest.raises(CoefficientResolutionError, match="must not be blank"):
            validate_required_codes(["valid", "   "])

    def test_duplicate_rejected(self) -> None:
        with pytest.raises(CoefficientResolutionError, match="duplicate"):
            validate_required_codes(["a", "b", "a"])

    def test_empty_list_returns_empty_tuple(self) -> None:
        assert validate_required_codes([]) == ()

    def test_none_returns_empty_tuple(self) -> None:
        assert validate_required_codes(None) == ()

    def test_order_does_not_affect_canonical_result(self) -> None:
        r1 = validate_required_codes(["b", "a", "c"])
        r2 = validate_required_codes(["c", "b", "a"])
        assert r1 == r2 == ("a", "b", "c")

    def test_strips_whitespace(self) -> None:
        result = validate_required_codes(["  code_a  ", "code_b"])
        assert result == ("code_a", "code_b")

    def test_single_element(self) -> None:
        assert validate_required_codes(["only"]) == ("only",)

    def test_field_name_in_error(self) -> None:
        with pytest.raises(CoefficientResolutionError, match="my_field"):
            validate_required_codes("bad", field_name="my_field")


# ── 2. Calculator requirement registry ────────────────────────────────────


class TestCalculatorRequirementRegistry:
    """Tests for REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION and
    derive_required_codes_for_version_vector()."""

    EXPECTED_CALCULATORS = {
        "zone",
        "cooling_load",
        "equipment",
        "power",
        "investment",
    }

    def test_all_five_calculators_present(self) -> None:
        calc_names = {key[0] for key in REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION}
        assert calc_names == self.EXPECTED_CALCULATORS

    def test_all_codes_are_real_from_catalog(self) -> None:
        """Every code in the registry must follow the namespace.name pattern
        and correspond to known categories (area, pallet, power, investment)."""
        known_prefixes = {"area.", "pallet.", "power.", "investment."}
        for key, codes in REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION.items():
            for code in codes:
                assert any(code.startswith(prefix) for prefix in known_prefixes), (
                    f"Code {code!r} for {key} does not match known catalog prefixes"
                )

    def test_all_entries_are_tuples(self) -> None:
        for key, codes in REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION.items():
            assert isinstance(codes, tuple), f"{key} codes should be tuple"
            assert len(codes) > 0, f"{key} codes should be non-empty"

    def test_all_codes_are_non_empty_strings(self) -> None:
        for key, codes in REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION.items():
            for code in codes:
                assert isinstance(code, str) and code.strip(), (
                    f"Empty/non-string code in {key}: {code!r}"
                )

    def test_derive_returns_sorted_deduped_tuple(self) -> None:
        version_vector = {
            "zone": "1.0.0",
            "cooling_load": "1.0.0",
            "equipment": "1.0.0",
            "power": "1.0.0",
            "investment": "1.0.0",
        }
        result = derive_required_codes_for_version_vector(version_vector)
        assert isinstance(result, tuple)
        assert list(result) == sorted(result)
        assert len(result) == len(set(result)), "Should be deduplicated"

    def test_derive_covers_all_registry_codes(self) -> None:
        """The full derivation should be a superset of every individual calculator."""
        version_vector = {
            "zone": "1.0.0",
            "cooling_load": "1.0.0",
            "equipment": "1.0.0",
            "power": "1.0.0",
            "investment": "1.0.0",
        }
        result = derive_required_codes_for_version_vector(version_vector)
        result_set = set(result)
        for key, codes in REQUIRED_COEFFICIENTS_BY_CALCULATOR_VERSION.items():
            for code in codes:
                assert code in result_set, (
                    f"Code {code!r} from {key} missing from derive_required_codes result"
                )

    def test_unknown_calculator_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            derive_required_codes_for_version_vector({"nonexistent": "9.9.9"})

    def test_wrong_version_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            derive_required_codes_for_version_vector({"zone": "99.0.0"})

    def test_single_calculator_derivation(self) -> None:
        result = derive_required_codes_for_version_vector({"zone": "1.0.0"})
        assert result == (
            "area.auxiliary_area_ratio",
            "area.circulation_allowance_ratio",
        )

    def test_shared_code_deduplication(self) -> None:
        """power.design_margin_ratio is shared by cooling_load and power;
        derivation must deduplicate."""
        result = derive_required_codes_for_version_vector(
            {"cooling_load": "1.0.0", "power": "1.0.0"}
        )
        # power.design_margin_ratio appears in both, should appear once
        assert result.count("power.design_margin_ratio") == 1


# ── 3. _validate_caller_conflicts ─────────────────────────────────────────


class TestCallerConflictValidation:
    """Tests for _validate_caller_conflicts()."""

    # -- product_category --

    def test_product_category_match_passes(self) -> None:
        _validate_caller_conflicts(
            caller_ctx={"product_category": "blueberry"},
            product_category="blueberry",
            product_type=None,
            zone_types=(),
            process_types=(),
            required_codes=(),
        )

    def test_product_category_conflict_raises(self) -> None:
        with pytest.raises(CoefficientResolutionError, match="product_category"):
            _validate_caller_conflicts(
                caller_ctx={"product_category": "strawberry"},
                product_category="blueberry",
                product_type=None,
                zone_types=(),
                process_types=(),
                required_codes=(),
            )

    def test_product_category_none_frozen_passes(self) -> None:
        """When frozen product_category is None, caller can say anything."""
        _validate_caller_conflicts(
            caller_ctx={"product_category": "blueberry"},
            product_category=None,
            product_type=None,
            zone_types=(),
            process_types=(),
            required_codes=(),
        )

    def test_product_category_none_caller_passes(self) -> None:
        """When caller has no product_category, no conflict."""
        _validate_caller_conflicts(
            caller_ctx={},
            product_category="blueberry",
            product_type=None,
            zone_types=(),
            process_types=(),
            required_codes=(),
        )

    # -- product_type --

    def test_product_type_match_passes(self) -> None:
        _validate_caller_conflicts(
            caller_ctx={"product_type": "IQF"},
            product_category=None,
            product_type="IQF",
            zone_types=(),
            process_types=(),
            required_codes=(),
        )

    def test_product_type_conflict_raises(self) -> None:
        with pytest.raises(CoefficientResolutionError, match="product_type"):
            _validate_caller_conflicts(
                caller_ctx={"product_type": "block_frozen"},
                product_category=None,
                product_type="IQF",
                zone_types=(),
                process_types=(),
                required_codes=(),
            )

    # -- zone_type --

    def test_zone_type_match_passes(self) -> None:
        _validate_caller_conflicts(
            caller_ctx={"zone_type": "freezer"},
            product_category=None,
            product_type=None,
            zone_types=("freezer",),
            process_types=(),
            required_codes=(),
        )

    def test_zone_type_conflict_raises(self) -> None:
        with pytest.raises(CoefficientResolutionError, match="zone_type"):
            _validate_caller_conflicts(
                caller_ctx={"zone_type": "cooler"},
                product_category=None,
                product_type=None,
                zone_types=("freezer",),
                process_types=(),
                required_codes=(),
            )

    def test_zone_types_plural_alias_works(self) -> None:
        """zone_types (plural) alias should be recognized and match."""
        _validate_caller_conflicts(
            caller_ctx={"zone_types": ["freezer", "antechamber"]},
            product_category=None,
            product_type=None,
            zone_types=("antechamber", "freezer"),
            process_types=(),
            required_codes=(),
        )

    def test_zone_singular_plural_alias_disagreement_raises(self) -> None:
        """zone_type and zone_types both present with different values → error."""
        with pytest.raises(CoefficientResolutionError, match="disagree"):
            _validate_caller_conflicts(
                caller_ctx={"zone_type": "freezer", "zone_types": ["cooler"]},
                product_category=None,
                product_type=None,
                zone_types=("freezer",),
                process_types=(),
                required_codes=(),
            )

    def test_zone_type_empty_frozen_rejects_caller(self) -> None:
        """Frozen zone_types empty + caller non-empty → criteria_conflict."""
        with pytest.raises(CoefficientResolutionError, match="zone_type"):
            _validate_caller_conflicts(
                caller_ctx={"zone_type": "freezer"},
                product_category=None,
                product_type=None,
                zone_types=(),
                process_types=(),
                required_codes=(),
            )

    # -- process_type --

    def test_process_type_match_passes(self) -> None:
        _validate_caller_conflicts(
            caller_ctx={"process_type": "blast_freeze"},
            product_category=None,
            product_type=None,
            zone_types=(),
            process_types=("blast_freeze",),
            required_codes=(),
        )

    def test_process_type_conflict_raises(self) -> None:
        with pytest.raises(CoefficientResolutionError, match="process_type"):
            _validate_caller_conflicts(
                caller_ctx={"process_type": "cold_store"},
                product_category=None,
                product_type=None,
                zone_types=(),
                process_types=("blast_freeze",),
                required_codes=(),
            )

    def test_process_types_plural_alias_works(self) -> None:
        _validate_caller_conflicts(
            caller_ctx={"process_types": ["precool", "blast_freeze"]},
            product_category=None,
            product_type=None,
            zone_types=(),
            process_types=("blast_freeze", "precool"),
            required_codes=(),
        )

    def test_process_singular_plural_disagreement_raises(self) -> None:
        with pytest.raises(CoefficientResolutionError, match="disagree"):
            _validate_caller_conflicts(
                caller_ctx={
                    "process_type": "blast_freeze",
                    "process_types": ["cold_store"],
                },
                product_category=None,
                product_type=None,
                zone_types=(),
                process_types=("blast_freeze",),
                required_codes=(),
            )

    # -- required_codes --

    def test_required_codes_match_passes(self) -> None:
        _validate_caller_conflicts(
            caller_ctx={"required_codes": ["b", "a"]},
            product_category=None,
            product_type=None,
            zone_types=(),
            process_types=(),
            required_codes=("a", "b"),
        )

    def test_required_codes_conflict_raises(self) -> None:
        with pytest.raises(CoefficientResolutionError, match="required_codes"):
            _validate_caller_conflicts(
                caller_ctx={"required_codes": ["a", "c"]},
                product_category=None,
                product_type=None,
                zone_types=(),
                process_types=(),
                required_codes=("a", "b"),
            )

    def test_required_coefficient_codes_alias_works(self) -> None:
        """required_coefficient_codes alias should be recognized."""
        _validate_caller_conflicts(
            caller_ctx={"required_coefficient_codes": ["a", "b"]},
            product_category=None,
            product_type=None,
            zone_types=(),
            process_types=(),
            required_codes=("a", "b"),
        )

    def test_required_codes_empty_frozen_rejects_caller(self) -> None:
        """Frozen required_codes empty + caller non-empty → criteria_conflict."""
        with pytest.raises(CoefficientResolutionError, match="required_codes"):
            _validate_caller_conflicts(
                caller_ctx={"required_codes": ["a"]},
                product_category=None,
                product_type=None,
                zone_types=(),
                process_types=(),
                required_codes=(),
            )

    # -- self-attestation fields ignored --

    def test_approval_status_revision_self_attestation_ignored(self) -> None:
        """Fields in _IGNORED_CALLER_FIELDS should not trigger conflict checks."""
        _validate_caller_conflicts(
            caller_ctx={
                "approved_revision_ids": ["r1", "r2"],
                "status": "approved",
                "validity_status": "valid",
                "approved": True,
            },
            product_category="blueberry",
            product_type="IQF",
            zone_types=("freezer",),
            process_types=("blast_freeze",),
            required_codes=("a", "b"),
        )

    # -- type errors --

    def test_non_string_product_category_rejected(self) -> None:
        with pytest.raises(CoefficientResolutionError, match="must be str"):
            _validate_caller_conflicts(
                caller_ctx={"product_category": 123},
                product_category="blueberry",
                product_type=None,
                zone_types=(),
                process_types=(),
                required_codes=(),
            )

    def test_non_string_product_type_rejected(self) -> None:
        with pytest.raises(CoefficientResolutionError, match="must be str"):
            _validate_caller_conflicts(
                caller_ctx={"product_type": 123},
                product_category=None,
                product_type="IQF",
                zone_types=(),
                process_types=(),
                required_codes=(),
            )

    def test_non_list_required_codes_rejected(self) -> None:
        with pytest.raises(CoefficientResolutionError, match="must be list/tuple"):
            _validate_caller_conflicts(
                caller_ctx={"required_codes": "not_a_list"},
                product_category=None,
                product_type=None,
                zone_types=(),
                process_types=(),
                required_codes=("a",),
            )

    def test_zone_type_list_match_passes(self) -> None:
        """Zone type as a list in caller context should match frozen tuple."""
        _validate_caller_conflicts(
            caller_ctx={"zone_type": ["antechamber", "freezer"]},
            product_category=None,
            product_type=None,
            zone_types=("antechamber", "freezer"),
            process_types=(),
            required_codes=(),
        )

    def test_zone_type_list_conflict_raises(self) -> None:
        with pytest.raises(CoefficientResolutionError, match="zone_type"):
            _validate_caller_conflicts(
                caller_ctx={"zone_type": ["freezer", "loading_dock"]},
                product_category=None,
                product_type=None,
                zone_types=("antechamber", "freezer"),
                process_types=(),
                required_codes=(),
            )


# ── 4. _derive_frozen_criteria ────────────────────────────────────────────


class TestDeriveFrozenCriteria:
    """Tests for _derive_frozen_criteria()."""

    def test_snapshot_product_category_matches_project_record_passes(self) -> None:
        version = _make_version(
            project_product_category="blueberry",
            input_snapshot={"product_category": "blueberry"},
        )
        command = _make_command()
        criteria = _derive_frozen_criteria(command=command, version=version)
        assert criteria.product_category == "blueberry"

    def test_snapshot_product_category_conflicts_with_project_record_raises(
        self,
    ) -> None:
        version = _make_version(
            project_product_category="blueberry",
            input_snapshot={"product_category": "strawberry"},
        )
        command = _make_command()
        with pytest.raises(CoefficientResolutionError, match="product_category"):
            _derive_frozen_criteria(command=command, version=version)

    def test_snapshot_without_product_category_uses_project_record_authority(
        self,
    ) -> None:
        version = _make_version(
            project_product_category="blueberry",
            input_snapshot={},
        )
        command = _make_command()
        criteria = _derive_frozen_criteria(command=command, version=version)
        assert criteria.product_category == "blueberry"

    def test_snapshot_required_coefficient_codes_matching_authoritative_passes(
        self,
    ) -> None:
        from cold_storage.modules.orchestration.application.service import (
            _AUTHORITATIVE_REQUIRED_CODES,
        )

        version = _make_version(
            input_snapshot={
                "required_coefficient_codes": list(reversed(_AUTHORITATIVE_REQUIRED_CODES)),
            },
        )
        command = _make_command()
        criteria = _derive_frozen_criteria(command=command, version=version)
        assert criteria.required_codes == _AUTHORITATIVE_REQUIRED_CODES

    def test_snapshot_required_coefficient_codes_conflicting_raises(self) -> None:
        version = _make_version(
            input_snapshot={
                "required_coefficient_codes": ["fake_code_1", "fake_code_2"],
            },
        )
        command = _make_command()
        with pytest.raises(CoefficientResolutionError, match="required_coefficient_codes"):
            _derive_frozen_criteria(command=command, version=version)

    def test_empty_snapshot_required_coefficient_codes_cannot_erase_registry(
        self,
    ) -> None:
        """An empty list in the snapshot for required_coefficient_codes must fail
        because the authoritative registry is non-empty."""
        version = _make_version(
            input_snapshot={"required_coefficient_codes": []},
        )
        command = _make_command()
        with pytest.raises(CoefficientResolutionError, match="required_coefficient_codes"):
            _derive_frozen_criteria(command=command, version=version)

    def test_criteria_carries_project_id_and_version_id(self) -> None:
        version = _make_version()
        command = _make_command(project_id="proj-99", project_version_id="pv-99")
        criteria = _derive_frozen_criteria(command=command, version=version)
        assert criteria.project_id == "proj-99"
        assert criteria.project_version_id == "pv-99"

    def test_product_type_from_snapshot(self) -> None:
        version = _make_version(input_snapshot={"product_type": "IQF"})
        command = _make_command()
        criteria = _derive_frozen_criteria(command=command, version=version)
        assert criteria.product_type == "IQF"

    def test_zone_types_from_snapshot(self) -> None:
        version = _make_version(input_snapshot={"zone_types": ["freezer", "antechamber"]})
        command = _make_command()
        criteria = _derive_frozen_criteria(command=command, version=version)
        assert set(criteria.zone_types) == {"antechamber", "freezer"}

    def test_process_types_from_snapshot(self) -> None:
        version = _make_version(input_snapshot={"process_types": ["blast_freeze"]})
        command = _make_command()
        criteria = _derive_frozen_criteria(command=command, version=version)
        assert criteria.process_types == ("blast_freeze",)

    def test_caller_context_conflicts_detected(self) -> None:
        """Caller context that conflicts with frozen criteria should raise."""
        version = _make_version(
            project_product_category="blueberry",
            input_snapshot={},
        )
        command = _make_command(
            coefficient_resolution_context={"product_category": "strawberry"},
        )
        with pytest.raises(CoefficientResolutionError, match="product_category"):
            _derive_frozen_criteria(command=command, version=version)

    def test_caller_context_ignored_fields_stripped(self) -> None:
        """Ignored caller fields should not cause conflicts."""
        from cold_storage.modules.orchestration.application.service import (
            _AUTHORITATIVE_REQUIRED_CODES,
        )

        version = _make_version(input_snapshot={})
        command = _make_command(
            coefficient_resolution_context={
                "status": "approved",
                "validity_status": "valid",
                "approved_revision_ids": ["r1"],
                "approved": True,
            },
        )
        criteria = _derive_frozen_criteria(command=command, version=version)
        assert criteria.required_codes == _AUTHORITATIVE_REQUIRED_CODES

    def test_required_codes_are_authoritative(self) -> None:
        """The returned criteria must always carry the authoritative required codes."""
        from cold_storage.modules.orchestration.application.service import (
            _AUTHORITATIVE_REQUIRED_CODES,
        )

        version = _make_version(input_snapshot={})
        command = _make_command()
        criteria = _derive_frozen_criteria(command=command, version=version)
        assert criteria.required_codes == _AUTHORITATIVE_REQUIRED_CODES
        assert len(criteria.required_codes) > 0

    def test_snapshot_product_category_none_passes(self) -> None:
        """Snapshot without product_category should not conflict with ProjectRecord."""
        version = _make_version(
            project_product_category="blueberry",
            input_snapshot={"product_category": None},
        )
        command = _make_command()
        criteria = _derive_frozen_criteria(command=command, version=version)
        assert criteria.product_category == "blueberry"
