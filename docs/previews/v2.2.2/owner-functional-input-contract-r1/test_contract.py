"""Offline Owner-rule tests. No production imports, solver, or external data calls."""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
import unittest
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("owner_functional_offline", HERE / "contract.py")
assert SPEC is not None and SPEC.loader is not None
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)


class OwnerInputContractTest(unittest.TestCase):
    documents: dict[str, Any]

    @classmethod
    def setUpClass(cls) -> None:
        cls.documents = contract.build()

    def calculate(self, first: Any, second: Any, **overrides: Any) -> dict[str, Any]:
        data = {
            "shift_1_kg": first,
            "shift_2_kg": second,
            "mass_basis": "PACKAGED_PRODUCT_MASS",
            "mass_source": "SYNTHETIC_TEST_EXPLICIT_PACKAGED_MASS_RECORD",
            **overrides,
        }
        return dict(contract.staffing(**data))

    def test_01_capacity_is_192_per_person_per_shift(self) -> None:
        self.assertEqual(contract.capacity_per_shift(), Fraction(15) * Fraction("1.6") * 8)
        self.assertEqual(contract.capacity_per_shift(), 192)
        self.assertEqual(contract.values()["PACKAGING_WORK_HOURS_PER_DAY"], 16)

    def test_02_each_shift_ceil_separately_at_exact_boundaries(self) -> None:
        result = self.calculate("192", "192.000001")
        self.assertEqual(result["SHIFT_1_WORKERS"], 1)
        self.assertEqual(result["SHIFT_2_WORKERS"], 2)
        self.assertEqual(result["LOCKER_COUNT"], 3)

    def test_03_lockers_are_sum_not_shared_between_shifts(self) -> None:
        result = self.calculate(800, 200)
        self.assertEqual((result["SHIFT_1_WORKERS"], result["SHIFT_2_WORKERS"]), (5, 2))
        self.assertEqual(result["LOCKER_COUNT"], 7)
        self.assertEqual(result["OTHER_JOB_USERS_ADDED"], 0)

    def test_04_simultaneous_is_whole_largest_shift(self) -> None:
        result = self.calculate(800, 200)
        self.assertEqual(result["SIMULTANEOUS_CHANGING_USERS"], 5)
        self.assertEqual(result["SHIFT_CHANGE_POLICY"], "NON_OVERLAPPING")
        changing = self.documents["functional-room-input-contract.json"]["changing_room"]
        self.assertFalse(changing["intra_shift_staggering_assumed"])

    def test_05_equal_and_unequal_allocations_can_change_totals(self) -> None:
        equal = self.calculate(500, 500, daily_packaged_kg=1000)
        unequal = self.calculate(800, 200, daily_packaged_kg=1000)
        self.assertEqual((equal["LOCKER_COUNT"], equal["SIMULTANEOUS_CHANGING_USERS"]), (6, 3))
        self.assertEqual((unequal["LOCKER_COUNT"], unequal["SIMULTANEOUS_CHANGING_USERS"]), (7, 5))
        self.assertTrue(self.documents["calculation-examples.json"]["equal_split_is_example_only"])

    def test_06_internal_separation_does_not_double_lockers(self) -> None:
        result = self.calculate(192, 192)
        self.assertTrue(result["LOCKER_INTERNAL_SEPARATION"])
        self.assertEqual(result["LOCKER_COUNT"], 2)
        self.assertFalse(contract.values()["LOCKER_SHARED_BETWEEN_SHIFTS"])

    def test_07_explicit_office_mapping(self) -> None:
        for size, staff in (("SMALL", 12), ("MEDIUM", 20), ("LARGE", 30)):
            with self.subTest(size=size):
                result = contract.office(size)
                self.assertEqual(result["OFFICE_DESIGN_STAFF"], staff)
                self.assertIsNone(result["classification_thresholds"])
                self.assertIsNone(result["functional_space_pass"])

    def test_08_unknown_scale_not_inferred_from_throughput_or_area(self) -> None:
        for size in (None, "UNKNOWN", "20t/day", "60m2", "small"):
            with self.subTest(size=size):
                result = contract.office(size)
                self.assertEqual(result["OFFICE_STAFF_STATUS"], "OWNER_INPUT_REQUIRED")
                self.assertNotIn("OFFICE_DESIGN_STAFF", result)
        office = self.documents["functional-room-input-contract.json"]["office"]
        self.assertIsNone(office["size_class_thresholds"])

    def test_09_film_design_is_all_entering_product_not_actual_fraction(self) -> None:
        for ratio in ("0", "0.5", "1"):
            result = contract.film_sealing(
                entering_product_kg=1000, mass_source="TEST", actual_ratio=ratio
            )
            self.assertEqual(result["DESIGN_FILM_SEALING_RATIO"], "1.0")
            self.assertEqual(result["design_load_kg"], {"numerator": 1000, "denominator": 1})
            self.assertIsNone(result["functional_space_pass"])

    def test_10_non_sealing_product_can_cross_same_independent_room(self) -> None:
        film = self.documents["functional-room-input-contract.json"]["coating_room"]
        self.assertEqual(film["process_type"], "PACKAGING_BOX_FILM_SEALING")
        self.assertEqual(film["room_type"], "INDEPENDENT")
        self.assertEqual(
            film["non_sealing_pass_through"],
            {
                "allowed": True,
                "inside_same_room": True,
                "uses_sealing_equipment": False,
                "independent_bypass_room_assumed": False,
            },
        )

    def test_11_unknown_equipment_has_no_invented_count_or_area(self) -> None:
        result = contract.film_sealing(entering_product_kg=1000, mass_source="TEST")
        for field in (
            "EQUIPMENT_MODEL",
            "EQUIPMENT_CAPACITY",
            "EQUIPMENT_COUNT",
            "EQUIPMENT_ENVELOPE",
        ):
            self.assertEqual(result[field], {"value": None, "status": "UNAVAILABLE"})
        self.assertNotIn("equipment_area_m2", result)
        self.assertEqual(
            result["EFFECTIVE_EQUIPMENT_RUNTIME_HOURS"],
            {"value": None, "status": "OWNER_INPUT_REQUIRED"},
        )
        self.assertFalse(contract.values()["SEALING_RUNTIME_INHERITS_PACKAGING_HOURS"])

    def test_12_historical_area_process_and_source_hashes_unchanged(self) -> None:
        integrity = self.documents["historical-integrity.json"]
        self.assertEqual(
            integrity["area_authority_m2"], {"office": 60, "changing_room": 40, "coating_room": 80}
        )
        for name, digest in integrity["protected_source_files_sha256"].items():
            self.assertEqual(contract.sha(contract.REPO / name), digest)
        prior = (
            contract.REPO
            / "docs/previews/v2.2.2/functional-room-dimension-calibration-01"
            / "functional-room-requirements.json"
        )
        authorities = json.loads(prior.read_text())
        for room, value in integrity["area_authority_m2"].items():
            self.assertEqual(Fraction(authorities[room]["current_area_authority_m2"]), value)
        sequence = self.documents["functional-room-input-contract.json"]["coating_room"][
            "existing_zone_sequence"
        ]
        self.assertEqual(
            sequence,
            [
                "sorting_packaging_room",
                "secondary_precooling_room",
                "coating_room",
                "finished_goods_room",
            ],
        )
        p0 = (
            contract.REPO / "docs/tasks/V2_2_2-P0-process-flow-layout-regularity-contract.md"
        ).read_text()
        self.assertIn("secondary_precooling_room -> coating_room -> finished_goods_room", p0)

    def test_13_raw_mass_and_missing_source_do_not_become_product_mass(self) -> None:
        raw = self.calculate(500, 500, mass_basis="RAW_INBOUND_FRUIT")
        self.assertEqual(raw["status"], "OWNER_INPUT_REQUIRED")
        self.assertIsNone(raw["result"])
        for source in (None, "", "  "):
            self.assertIn(
                "PACKAGING_PRODUCT_MASS_SOURCE",
                self.calculate(500, 500, mass_source=source)["missing_inputs"],
            )

    def test_14_same_inputs_and_regeneration_are_byte_identical(self) -> None:
        self.assertEqual(
            contract.encoded(self.calculate("500.01", 200)),
            contract.encoded(self.calculate("500.01", 200)),
        )
        before = {name: contract.sha(HERE / name) for name in self.documents}
        contract.build()
        self.assertEqual(before, {name: contract.sha(HERE / name) for name in self.documents})

    def test_15_no_default_shift_split_or_derived_missing_shift(self) -> None:
        result = self.calculate(None, None, daily_packaged_kg=1000)
        self.assertEqual(result["missing_inputs"], ["SHIFT_1_PACKAGING_KG", "SHIFT_2_PACKAGING_KG"])
        self.assertIsNone(result["result"])
        one = self.calculate(800, None, daily_packaged_kg=1000)
        self.assertEqual(one["missing_inputs"], ["SHIFT_2_PACKAGING_KG"])

    def test_16_daily_mass_consistency_not_silently_corrected(self) -> None:
        with self.assertRaisesRegex(ValueError, "SHIFT_PRODUCT_MASS_SUM_MISMATCH"):
            self.calculate(800, 200, daily_packaged_kg=999)

    def test_17_invalid_exact_quantities_fail_closed(self) -> None:
        for value in ("-1", "NaN", "Infinity", "bad", True, 1.6):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.calculate(value, 0)
        result = self.calculate(Decimal("192.000001"), 0)
        self.assertEqual(result["SHIFT_1_WORKERS"], 2)

    def test_18_all_confirmed_values_carry_metadata(self) -> None:
        records = self.documents["owner-confirmed-business-rules.json"]["rules"]
        keys = {
            "FIELD_NAME",
            "VALUE",
            "UNIT",
            "SOURCE",
            "CONFIRMATION_DATE",
            "APPLICABILITY",
            "CONTRACT_VERSION",
        }
        self.assertEqual(len(records), len({r["FIELD_NAME"] for r in records}))
        for record in records:
            self.assertTrue(keys.issubset(record))
            self.assertEqual(record["SOURCE"], "OWNER_CONFIRMED")
            self.assertEqual(record["CONFIRMATION_DATE"], "2026-10-19")
            self.assertEqual(record["CONTRACT_VERSION"], contract.VERSION)

    def test_19_no_functional_pass_or_privacy_waiver(self) -> None:
        result = self.calculate(500, 500)
        self.assertIsNone(result["functional_space_pass"])
        self.assertEqual(result["hygiene_privacy_compliance"], "PROFESSIONAL_REVIEW_REQUIRED")
        self.assertFalse(contract.values()["GENDER_INDEPENDENT_ZONING_PRESET"])
        self.assertFalse(
            self.documents["functional-room-input-contract.json"]["numeric_calibration_ready"]
        )

    def test_20_legacy_336_is_separately_preserved_not_overridden(self) -> None:
        legacy = self.documents["staffing-calculation-contract.json"]["legacy_rule"]
        self.assertEqual(legacy["person_daily_capacity_kg"], 336)
        self.assertEqual(legacy["status"], "PRESERVED_UNCHANGED_NOT_REPLACED")
        document = (contract.REPO / legacy["document"].split(":")[0]).read_text()
        self.assertIn("PACKING_PERSON_DAILY_CAPACITY_KG=336", document)
        self.assertIn("PACKING_HOURS=14", document)

    def test_21_zero_mass_does_not_create_non_packaging_staff(self) -> None:
        result = self.calculate(0, 0)
        self.assertEqual(result["LOCKER_COUNT"], 0)
        self.assertEqual(result["SIMULTANEOUS_CHANGING_USERS"], 0)
        self.assertEqual(result["OTHER_JOB_USERS_ADDED"], 0)

    def test_22_invalid_actual_ratio_rejected_and_missing_stays_missing(self) -> None:
        for ratio in ("-0.1", "1.0001"):
            with self.assertRaises(ValueError):
                contract.film_sealing(
                    entering_product_kg=100, mass_source="TEST", actual_ratio=ratio
                )
        result = contract.film_sealing(entering_product_kg=None, mass_source=None)
        self.assertIsNone(result["design_load_kg"])
        self.assertIsNone(result["ACTUAL_FILM_SEALING_RATIO"])

    def test_23_mass_source_reference_is_not_forged_file_verification(self) -> None:
        result = self.calculate(1, 1)
        self.assertEqual(
            result["source_reference_verification"], "REFERENCE_RECORDED_NOT_FILE_AUTHENTICATED"
        )
        self.assertNotIn("authoritative", result)

    def test_24_no_production_solver_or_network_imports(self) -> None:
        tree = ast.parse((HERE / "contract.py").read_text())
        imported = [
            node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        ]
        self.assertFalse(
            any(
                module.startswith(("cold_storage", "ortools", "requests", "urllib"))
                for module in imported
            )
        )
        self.assertNotIn("ortools", sys.modules)


if __name__ == "__main__":
    unittest.main(verbosity=2)
