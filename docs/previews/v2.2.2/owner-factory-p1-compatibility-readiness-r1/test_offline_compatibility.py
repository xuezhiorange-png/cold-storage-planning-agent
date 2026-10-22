"""Deterministic offline compatibility tests; no layout solve or authority activation."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "offline_p1_compatibility", HERE / "offline_compatibility.py"
)
assert SPEC and SPEC.loader
study = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(study)


class P1CompatibilityTest(unittest.TestCase):
    outputs: dict[str, Any]

    @classmethod
    def setUpClass(cls) -> None:
        cls.outputs = study.build()

    def scenario(self, index: int = 0) -> dict[str, Any]:
        return dict(
            self.outputs["staffing-and-table-compatibility.json"]["scenarios"][index]["output"]
        )

    def test_01_full_legacy_20t_bytes_and_hashes_unchanged(self) -> None:
        old = self.outputs["legacy-canonical-replay.json"]
        self.assertTrue(old["project_canonical_bytes_equal"])
        self.assertTrue(old["sorted_compact_json_bytes_equal"])
        self.assertEqual(
            old["canonical_result_hash"],
            "sha256:61b59f8e6bd8e81c8b43751bd58ce52df82d349b82346bbfd6585a891139cddd",
        )
        self.assertEqual(
            old["dimension_handoff_hash"],
            "sha256:7a41ba026375a1f7085106772d761b946c32c32661320bb4db8565e02848c468",
        )
        result = old["canonical_result"]["result"]
        self.assertEqual(result["total_area_m2"], 2194.59)
        self.assertEqual(
            result["planning_parameters"]["sorting_packaging_required_area_m2"], 622.34
        )

    def test_02_legacy_336_still_actual_production_parameter(self) -> None:
        constants = self.outputs["legacy-current-rule-audit.json"]["constants"]
        self.assertEqual(
            [
                constants[k]
                for k in (
                    "PACKING_PIECES_PER_PERSON_HOUR",
                    "PACKING_WEIGHT_PER_PIECE_KG",
                    "PACKING_WORKING_HOURS_PER_DAY",
                    "PERSON_DAILY_CAPACITY_KG",
                )
            ],
            [16, 1.5, 14, 336.0],
        )

    def test_03_new_192_is_separate_rule_and_version(self) -> None:
        owner = study.owner_module()
        self.assertEqual(owner.capacity_per_shift(), 192)
        self.assertEqual(owner.VERSION, "owner-factory-functional-inputs@1.0.0")
        self.assertNotEqual(self.scenario()["mode"], "LEGACY_CANONICAL")

    def test_04_round_each_shift_not_total(self) -> None:
        owner = study.owner_module()
        result = owner.staffing(
            shift_1_kg=500,
            shift_2_kg=500,
            mass_basis="PACKAGED_PRODUCT_MASS",
            mass_source="EXPLICIT_SYNTHETIC",
        )
        self.assertEqual((result["SHIFT_1_WORKERS"], result["SHIFT_2_WORKERS"]), (3, 3))
        self.assertEqual(result["LOCKER_COUNT"], 6)

    def test_05_total_and_peak_are_separate(self) -> None:
        tables = self.scenario()["table_policy"]
        self.assertEqual(tables["total_shift_workers"], 106)
        self.assertEqual(tables["peak_concurrent_packaging_workers"], 53)

    def test_06_lockers_sum_not_concurrent_or_internal_compartments(self) -> None:
        staffing = self.scenario()["staffing_and_lockers"]
        self.assertEqual(staffing["LOCKER_COUNT"], 106)
        self.assertEqual(staffing["SIMULTANEOUS_CHANGING_USERS"], 53)
        self.assertTrue(staffing["LOCKER_INTERNAL_SEPARATION"])

    def test_07_table_policy_not_total_employee_division(self) -> None:
        shared = study.table_sensitivity(53, 53, reuse_between_shifts=True)
        dedicated = study.table_sensitivity(53, 53, reuse_between_shifts=False)
        self.assertEqual(shared["proposal_table_count"], 18)
        self.assertEqual(dedicated["proposal_table_count"], 36)
        self.assertNotEqual(shared["proposal_table_count"], (106 + 2) // 3)
        self.assertIsNone(shared["formal_p1_table_count"])

    def test_08_equal_and_unequal_change_peak_and_sensitivity(self) -> None:
        equal, uneven = self.scenario(), self.scenario(1)
        self.assertEqual(equal["table_policy"]["proposal_table_count"], 18)
        self.assertEqual(uneven["table_policy"]["proposal_table_count"], 28)
        self.assertEqual(equal["table_policy"]["area_projection"]["reported_area_m2"], 538.56)
        self.assertEqual(uneven["table_policy"]["area_projection"]["reported_area_m2"], 759.62)
        self.assertEqual(uneven["staffing_and_lockers"]["LOCKER_COUNT"], 105)

    def test_09_missing_allocations_fail_closed(self) -> None:
        result = study.evaluate("OWNER_V1_PROPOSED")
        self.assertIsNone(result["staffing_and_lockers"])
        self.assertIsNone(result["table_policy"])
        self.assertFalse(result["P1_PRODUCTION_ACTIVATED"])

    def test_10_raw_mass_not_implicitly_packaged(self) -> None:
        scenario = self.outputs["staffing-and-table-compatibility.json"]["scenarios"][0]
        payload = {**scenario["input"], "mass_basis": "RAW_INBOUND_FRUIT"}
        result = study.proposed(payload, evidence_root=HERE)
        self.assertEqual(result["source_verification"], "PACKAGED_PRODUCT_MASS_KG_REQUIRED")
        self.assertIsNone(result["staffing_and_lockers"])

    def test_11_actual_product_bytes_checked_but_not_owner_approval(self) -> None:
        result = self.scenario()
        self.assertEqual(
            result["source_verification"], "ACTUAL_LOCAL_BYTES_AND_QUANTITIES_MATCH_NOT_APPROVAL"
        )
        self.assertEqual(result["source_record"]["mass_basis"], "PACKAGED_PRODUCT_MASS")
        self.assertEqual(
            result["formal_source_admission"], "BLOCKED_NOT_IMPLEMENTED_BY_OFFLINE_CONTENT_CHECK"
        )

    def test_12_unknown_factory_size_never_inferred(self) -> None:
        self.assertEqual(self.scenario()["office"]["OFFICE_STAFF_STATUS"], "OWNER_INPUT_REQUIRED")
        self.assertNotIn("OFFICE_DESIGN_STAFF", self.scenario()["office"])

    def test_13_actual_25_and_50_tonne_boundaries_preserved(self) -> None:
        rows = self.outputs["legacy-current-rule-audit.json"]["band_boundary_replays"]
        self.assertEqual(
            [(r["raw_kg_day"], r["office"], r["changing_room"], r["coating_room"]) for r in rows],
            [
                (24999, 60, 40, 80),
                (25000, 80, 80, 120),
                (49999, 80, 80, 120),
                (50000, 100, 120, 200),
            ],
        )

    def test_14_office_staff_classes_do_not_use_tonnage(self) -> None:
        owner = study.owner_module()
        self.assertEqual(
            [owner.office(k)["OFFICE_DESIGN_STAFF"] for k in ("SMALL", "MEDIUM", "LARGE")],
            [12, 20, 30],
        )
        self.assertEqual(owner.office("25t")["status"], "OWNER_INPUT_REQUIRED")

    def test_15_unknown_lockers_never_generate_area_pass(self) -> None:
        result = self.scenario()
        self.assertIsNone(result["new_functional_area_m2"]["changing_room"])
        self.assertIsNone(result["staffing_and_lockers"]["functional_space_pass"])

    def test_16_unknown_equipment_has_no_count_or_area(self) -> None:
        film = self.scenario()["film_sealing"]
        for key in (
            "EQUIPMENT_MODEL",
            "EQUIPMENT_CAPACITY",
            "EQUIPMENT_COUNT",
            "EQUIPMENT_ENVELOPE",
        ):
            self.assertEqual(film[key], {"value": None, "status": "UNAVAILABLE"})
        self.assertIsNone(self.scenario()["new_functional_area_m2"]["coating_room"])

    def test_17_design_ratio_not_reduced_by_actual_ratio(self) -> None:
        film = study.owner_module().film_sealing(
            entering_product_kg=100, mass_source="SYNTHETIC", actual_ratio="0.2"
        )
        self.assertEqual(film["DESIGN_FILM_SEALING_RATIO"], "1.0")
        self.assertEqual(film["design_load_kg"], {"numerator": 100, "denominator": 1})

    def test_18_packaging_16_hours_not_sealing_runtime(self) -> None:
        self.assertEqual(
            self.scenario()["film_sealing"]["EFFECTIVE_EQUIPMENT_RUNTIME_HOURS"],
            {"value": None, "status": "OWNER_INPUT_REQUIRED"},
        )

    def test_19_business_roles_map_to_p0_ordered_roles(self) -> None:
        mapping = self.outputs["role-and-field-alias-mapping.json"]
        self.assertEqual(
            [mapping["roles"][r] for r in mapping["ordered_business_roles"]],
            mapping["ordered_p0_roles"],
        )
        self.assertEqual(
            mapping["ordered_p0_roles"],
            ["SORTING_PACKAGING", "SECONDARY_PRECOOL", "COATING", "FINISHED_STORAGE"],
        )

    def test_20_gender_field_ambiguity_mapped_without_rewriting_history(self) -> None:
        migration = self.outputs["role-and-field-alias-mapping.json"]["field_migration"]
        self.assertEqual(migration["historical_field"], "GENDER_INDEPENDENT_ZONING_PRESET")
        self.assertEqual(migration["proposed_field"], "SEPARATE_GENDER_ZONES_PRESET")
        self.assertFalse(migration["historical_value"])
        self.assertFalse(migration["proposed_value"])
        self.assertEqual(
            migration["professional_review"], "HYGIENE_PRIVACY_AND_APPLICABLE_CODES_REQUIRED"
        )
        study.owner_module()  # verifies every old contract file against its sealed manifest

    def test_21_original_dimension_and_source_identity_still_frozen(self) -> None:
        old = study.legacy_replay()
        self.assertFalse(old["identity_changed"])
        self.assertFalse(old["authority_changed"])
        self.assertEqual(
            old["dimension_handoff_hash"],
            self.outputs["legacy-canonical-replay.json"]["dimension_handoff_hash"],
        )

    def test_22_explicit_modes_cannot_override_or_impersonate(self) -> None:
        with self.assertRaisesRegex(ValueError, "EXPLICIT_COMPATIBILITY_MODE_REQUIRED"):
            study.evaluate("")
        with self.assertRaisesRegex(ValueError, "OWNER_INPUT_CANNOT_OVERRIDE_LEGACY_CANONICAL"):
            study.evaluate("LEGACY_CANONICAL", {"packing_working_hours_per_day": 16})
        self.assertIsNone(self.scenario()["canonical_p1_result"])
        self.assertFalse(self.scenario()["server_authority_created"])

    def test_23_missing_forged_and_mismatched_sources_fail_closed(self) -> None:
        original = self.outputs["staffing-and-table-compatibility.json"]["scenarios"][0]["input"]
        cases = [
            (
                {**original, "mass_source": {"path": "no-such-source.json", "sha256": "0" * 64}},
                "SOURCE_FILE_MISSING",
            ),
            (
                {**original, "mass_source": {**original["mass_source"], "sha256": "0" * 64}},
                "SOURCE_CONTENT_HASH_MISMATCH",
            ),
            ({**original, "verified": True}, "CALLER_AUTHORITY_ASSERTION_NOT_ACCEPTED"),
            ({**original, "project_id": "OTHER"}, "SOURCE_PROJECT_OR_PERIOD_MISMATCH"),
            ({**original, "period_id": "OTHER"}, "SOURCE_PROJECT_OR_PERIOD_MISMATCH"),
            ({**original, "shift_1_packaging_kg": "9999"}, "SOURCE_SHIFT_QUANTITY_MISMATCH"),
            (
                {**original, "shift_1_packaging_kg": None},
                "EXPLICIT_BOTH_SHIFT_ALLOCATIONS_REQUIRED",
            ),
            (
                {**original, "mass_source": {"path": "../outside.json", "sha256": "0" * 64}},
                "SOURCE_PATH_OUTSIDE_OFFLINE_EVIDENCE_ROOT",
            ),
        ]
        for payload, expected in cases:
            with self.subTest(expected=expected):
                result = study.proposed(payload, evidence_root=HERE)
                self.assertEqual(result["source_verification"], expected)
                self.assertIsNone(result["staffing_and_lockers"])
                self.assertFalse(result["P1_PRODUCTION_ACTIVATED"])

    def test_24_identical_inputs_and_generated_bytes_deterministic(self) -> None:
        payload = self.outputs["staffing-and-table-compatibility.json"]["scenarios"][0]["input"]
        self.assertEqual(
            study.encoded(study.proposed(payload, evidence_root=HERE)),
            study.encoded(study.proposed(payload, evidence_root=HERE)),
        )
        before = {name: study.sha(HERE / name) for name in self.outputs}
        study.build()
        self.assertEqual(before, {name: study.sha(HERE / name) for name in self.outputs})

    def test_25_fixed_area_fields_validate_but_do_not_select_areas(self) -> None:
        audit = self.outputs["legacy-current-rule-audit.json"]["fixed_area_input_audit"]
        self.assertEqual(
            audit["defaults"],
            {
                "office_fixed_area_m2": 60,
                "changing_fixed_area_m2": 100,
                "coating_fixed_area_m2": 120,
            },
        )
        self.assertTrue(audit["positive_override_1_2_3_result_unchanged"])
        self.assertTrue(audit["positive_override_full_snapshot_hash_changed"])
        self.assertTrue(audit["zero_still_rejected_by_generic_validation"])

    def test_26_unknown_reuse_means_no_table_or_area_even_if_staff_known(self) -> None:
        result = study.table_sensitivity(53, 53, reuse_between_shifts=None)
        self.assertIsNone(result["proposal_table_count"])
        self.assertIsNone(result["area_projection"])
        self.assertEqual(result["status"], "ENGINEERING_PROPOSAL_NOT_APPROVED")

    def test_27_no_new_total_or_formal_area_and_no_algorithm_quality_claim(self) -> None:
        result = self.scenario()
        self.assertEqual(result["COMPARISON_STATUS"], "NOT_COMPARABLE")
        self.assertIsNone(result["table_policy"]["formal_p1_area_m2"])
        self.assertIsNone(result["table_policy"]["new_total_factory_area_m2"])
        self.assertFalse(result["P1_INTEGRATION_IMPLEMENTATION_READY"])

    def test_28_grid_cells_not_required_tables_or_equipment_inventory(self) -> None:
        source = self.outputs["legacy-canonical-replay.json"]["canonical_result"]
        sorting = next(
            row for row in source["result"]["zones"] if row["zone_code"] == "sorting_packaging_room"
        )
        self.assertEqual(
            (
                sorting["worker_count"],
                sorting["table_count"],
                sorting["position_count"],
                sorting["unused_cells"],
            ),
            (60, 20, 21, 1),
        )

    def test_29_authentic_hash_of_synthetic_content_is_not_project_approval(self) -> None:
        original = self.outputs["staffing-and-table-compatibility.json"]["scenarios"][0]["input"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = dict(self.scenario()["source_record"])
            data["declared_owner_approved"] = True
            path = root / "synthetic.json"
            path.write_bytes(study.encoded(data))
            payload = {**original, "mass_source": {"path": path.name, "sha256": study.sha(path)}}
            result = study.proposed(payload, evidence_root=root)
            self.assertIsNotNone(result["staffing_and_lockers"])
            self.assertFalse(result["P1_PRODUCTION_ACTIVATED"])
            self.assertFalse(result["P1_INTEGRATION_IMPLEMENTATION_READY"])
            self.assertFalse(result["server_authority_created"])

    def test_30_no_native_solver_loaded(self) -> None:
        self.assertNotIn("ortools", sys.modules)
        self.assertNotIn(
            "cold_storage.modules.layout.infrastructure.global_cp_sat_model", sys.modules
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
