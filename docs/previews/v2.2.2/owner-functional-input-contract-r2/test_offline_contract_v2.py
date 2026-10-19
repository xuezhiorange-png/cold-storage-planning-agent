"""Owner V2 source-bound arithmetic and immutable V1/Legacy compatibility tests."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("owner_v2_offline", HERE / "offline_contract_v2.py")
assert SPEC and SPEC.loader
study = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(study)


class OwnerV2Test(unittest.TestCase):
    outputs: dict[str, Any]
    examples: list[dict[str, Any]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.outputs = study.build()
        cls.examples = cls.outputs["staffing-and-locker-calculation.json"]["examples"]

    def request(self, index: int = 0, **updates: Any) -> dict[str, Any]:
        return {**self.examples[index]["input"], **updates}

    def calculate(self, index: int = 0, **updates: Any) -> dict[str, Any]:
        return dict(study.calculate(self.request(index, **updates)))

    def test_01_default_equal_split_exact(self) -> None:
        result = self.calculate()
        self.assertEqual(result["allocation_mode"], "DEFAULT_EQUAL_SPLIT")
        for key in ("SHIFT_1_PACKAGING_KG", "SHIFT_2_PACKAGING_KG"):
            self.assertEqual(result["quantities"][key], {"numerator": 10000, "denominator": 1})

    def test_02_round_each_shift_up(self) -> None:
        counts = self.calculate()["staffing_and_tables"]
        self.assertEqual((counts["SHIFT_1_WORKERS"], counts["SHIFT_2_WORKERS"]), (53, 53))
        self.assertEqual(counts["TOTAL_WORKERS"], 106)

    def test_03_explicit_override_not_default(self) -> None:
        result = self.calculate(1)
        self.assertEqual(result["allocation_mode"], "EXPLICIT_SHIFT_OVERRIDE")
        counts = result["staffing_and_tables"]
        self.assertEqual((counts["SHIFT_1_WORKERS"], counts["SHIFT_2_WORKERS"]), (84, 21))
        self.assertEqual(counts["PACKING_TABLE_COUNT"], 28)
        self.assertEqual(counts["LOCKER_COUNT"], 105)

    def test_04_explicit_sum_mismatch_fails_closed(self) -> None:
        result = self.calculate(1, daily_packaged_kg="20001")
        self.assertEqual(result["reason"], "SHIFT_PRODUCT_MASS_SUM_MISMATCH")
        self.assertIsNone(result["staffing_and_tables"])

    def test_05_single_shift_rejected_even_with_daily_mass(self) -> None:
        for a, b in (("10000", None), (None, "10000"), ("0", None)):
            result = self.calculate(shift_1_packaging_kg=a, shift_2_packaging_kg=b)
            self.assertEqual(
                result["reason"], "PARTIAL_SHIFT_OVERRIDE_REJECTED_NO_REMAINDER_OR_DEFAULT"
            )

    def test_06_raw_inbound_cannot_become_q(self) -> None:
        result = self.calculate(daily_packaged_kg=None, daily_inbound_mass_kg="20000")
        self.assertEqual(result["reason"], "DAILY_PACKAGED_PRODUCT_MASS_REQUIRED")
        result = self.calculate(mass_basis="RAW_INBOUND_FRUIT")
        self.assertEqual(result["reason"], "PACKAGED_PRODUCT_MASS_REQUIRED_NO_RAW_DEFAULT")

    def test_07_no_source_means_no_default_calculation(self) -> None:
        result = self.calculate(mass_source=None)
        self.assertEqual(result["reason"], "PACKAGED_MASS_SOURCE_REQUIRED")
        self.assertIsNone(result["staffing_and_tables"])

    def test_08_three_workers_per_table(self) -> None:
        policy = self.outputs["packing-table-policy.json"]
        self.assertEqual(policy["WORKERS_PER_PACKING_TABLE"], 3)
        self.assertEqual(self.calculate()["staffing_and_tables"]["PACKING_TABLE_COUNT"], 18)

    def test_09_same_station_set_shared_across_shifts(self) -> None:
        counts = self.calculate()["staffing_and_tables"]
        self.assertTrue(counts["TABLE_SHARED_BETWEEN_SHIFTS"])
        self.assertEqual(counts["PACKING_TABLE_COUNT"], 18)
        self.assertNotEqual(counts["PACKING_TABLE_COUNT"], 36)

    def test_10_stations_use_peak_not_total(self) -> None:
        counts = self.calculate()["staffing_and_tables"]
        self.assertEqual(counts["PEAK_WORKERS"], 53)
        self.assertNotEqual(counts["PACKING_TABLE_COUNT"], (counts["TOTAL_WORKERS"] + 2) // 3)
        self.assertIsNone(counts["n_actual_grid_cells"])

    def test_11_total_employees_not_peak_concurrency(self) -> None:
        counts = self.calculate()["staffing_and_tables"]
        self.assertEqual((counts["TOTAL_WORKERS"], counts["PEAK_WORKERS"]), (106, 53))

    def test_12_lockers_sum_both_employee_sets(self) -> None:
        counts = self.calculate()["staffing_and_tables"]
        self.assertEqual(counts["LOCKER_COUNT"], 106)
        self.assertFalse(counts["LOCKER_SHARED_BETWEEN_SHIFTS"])
        self.assertEqual(counts["OTHER_JOB_STAFF_ADDED"], 0)

    def test_13_internal_partition_never_doubles_locker_count(self) -> None:
        counts = self.calculate()["staffing_and_tables"]
        self.assertTrue(counts["LOCKER_INTERNAL_SEPARATION"])
        self.assertEqual(counts["LOCKER_COUNT"], counts["TOTAL_WORKERS"])

    def test_14_whole_shift_changing_uses_peak(self) -> None:
        counts = self.calculate(1)["staffing_and_tables"]
        self.assertEqual(counts["SIMULTANEOUS_CHANGING_USERS"], 84)

    def test_15_twenty_tonne_product_business_result(self) -> None:
        counts = self.calculate()["staffing_and_tables"]
        self.assertEqual(
            [
                counts[k]
                for k in (
                    "SHIFT_1_WORKERS",
                    "SHIFT_2_WORKERS",
                    "TOTAL_WORKERS",
                    "PEAK_WORKERS",
                    "PACKING_TABLE_COUNT",
                    "LOCKER_COUNT",
                    "SIMULTANEOUS_CHANGING_USERS",
                )
            ],
            [53, 53, 106, 53, 18, 106, 53],
        )
        self.assertIsNone(self.calculate()["production_p1_area_m2"])

    def test_16_explicit_both_shifts_without_daily_mass(self) -> None:
        result = self.calculate(2)
        self.assertEqual(result["allocation_mode"], "EXPLICIT_SHIFT_OVERRIDE")
        self.assertEqual(
            result["quantities"]["DAILY_PACKAGED_KG"], {"numerator": 1000, "denominator": 1}
        )
        self.assertEqual(result["staffing_and_tables"]["PACKING_TABLE_COUNT"], 2)

    def test_17_one_192_384_kg_and_unrounded_half_kg(self) -> None:
        one = self.calculate(3)
        self.assertEqual(
            one["quantities"]["SHIFT_1_PACKAGING_KG"], {"numerator": 1, "denominator": 2}
        )
        for index in (3, 4, 5):
            counts = self.calculate(index)["staffing_and_tables"]
            self.assertEqual(
                (
                    counts["SHIFT_1_WORKERS"],
                    counts["SHIFT_2_WORKERS"],
                    counts["PACKING_TABLE_COUNT"],
                ),
                (1, 1, 1),
            )

    def test_18_no_unknown_equipment_or_area_invented(self) -> None:
        result = self.calculate()
        for field in (
            "EQUIPMENT_MODEL",
            "EQUIPMENT_CAPACITY",
            "EQUIPMENT_COUNT",
            "EQUIPMENT_ENVELOPE",
        ):
            self.assertEqual(
                result["film_sealing"][field], {"value": None, "status": "UNAVAILABLE"}
            )
        self.assertIsNone(result["film_sealing"]["functional_area_m2"])
        self.assertEqual(
            result["film_sealing"]["EFFECTIVE_RUNTIME_HOURS"]["status"], "OWNER_INPUT_REQUIRED"
        )

    def test_19_unknown_office_size_not_tonnage_derived(self) -> None:
        result = self.calculate()
        self.assertEqual(result["office"]["status"], "OWNER_INPUT_REQUIRED")
        self.assertIsNone(result["office"]["design_staff"])
        self.assertEqual(
            [
                self.calculate(factory_size=s)["office"]["design_staff"]
                for s in ("SMALL", "MEDIUM", "LARGE")
            ],
            [12, 20, 30],
        )

    def test_20_v1_rules_results_and_manifest_still_unchanged(self) -> None:
        old = study.load_previous(study.V1, "contract.py")
        self.assertEqual(old.values()["SHIFT_ALLOCATION_POLICY"], "EXPLICIT_INPUT_REQUIRED")
        self.assertEqual(
            old.staffing(
                shift_1_kg=None,
                shift_2_kg=None,
                daily_packaged_kg=1000,
                mass_basis="PACKAGED_PRODUCT_MASS",
                mass_source="TEST",
            )["status"],
            "OWNER_INPUT_REQUIRED",
        )
        records = json.loads((study.V1 / "calculation-examples.json").read_text())["examples"]
        for index, quantities in enumerate(((500, 500), (800, 200))):
            result = old.staffing(
                shift_1_kg=quantities[0],
                shift_2_kg=quantities[1],
                daily_packaged_kg=1000,
                mass_basis="PACKAGED_PRODUCT_MASS",
                mass_source="SYNTHETIC_EXAMPLE_EXPLICIT_PACKAGED_PRODUCT_QUANTITIES",
            )
            self.assertEqual(study.encode(result), study.encode(records[index]["output"]))

    def test_21_legacy_canonical_full_replay_and_p1_hash(self) -> None:
        previous = study.load_previous(study.READINESS, "offline_compatibility.py")
        replay = previous.legacy_replay()
        original = json.loads((study.READINESS / "legacy-canonical-replay.json").read_text())
        self.assertEqual(study.encode(replay), study.encode(original))
        result = replay["canonical_result"]["result"]
        sorting = next(r for r in result["zones"] if r["zone_code"] == "sorting_packaging_room")
        self.assertEqual(
            (sorting["worker_count"], sorting["table_count"], sorting["required_area_m2"]),
            (60, 20, 622.34),
        )
        self.assertEqual(result["total_area_m2"], 2194.59)
        self.assertEqual(
            replay["dimension_handoff_hash"],
            "sha256:7a41ba026375a1f7085106772d761b946c32c32661320bb4db8565e02848c468",
        )

    def test_22_v1_v2_identities_cannot_impersonate(self) -> None:
        for identity, version in (
            ("OwnerFactoryFunctionalInputsV1", "owner-factory-functional-inputs@1.0.0"),
            (study.IDENTITY, "owner-factory-functional-inputs@1.0.0"),
            ("OwnerFactoryFunctionalInputsV1", study.VERSION),
            (None, None),
        ):
            with self.subTest(identity=identity, version=version), self.assertRaises(ValueError):
                self.calculate(contract_identity=identity, contract_version=version)

    def test_23_file_hash_not_formal_source_or_p1_authority(self) -> None:
        result = self.calculate()
        self.assertEqual(
            result["mass_source_verification"], "LOCAL_CONTENT_MATCH_NOT_PROJECT_APPROVAL"
        )
        self.assertFalse(result["P1_AUTHORITY_PASS"])
        self.assertFalse(result["P1_PRODUCTION_ACTIVATED"])
        for key in ("verified", "authoritative", "authority_token"):
            self.assertEqual(
                self.calculate(**{key: True})["reason"], "CALLER_AUTHORITY_ASSERTION_NOT_ACCEPTED"
            )

    def test_24_repeated_bytes_and_result_hash_are_identical(self) -> None:
        first, second = self.calculate(), self.calculate()
        self.assertEqual(study.encode(first), study.encode(second))
        self.assertEqual(first["offline_result_sha256"], second["offline_result_sha256"])
        before = {name: study.sha(HERE / name) for name in self.outputs}
        study.build()
        self.assertEqual(before, {name: study.sha(HERE / name) for name in self.outputs})

    def test_25_confirmed_metadata_and_unchanged_v1_inheritance(self) -> None:
        rules = self.outputs["owner-confirmed-business-rules-v2.json"]["rules"]
        required = {
            "FIELD_NAME",
            "VALUE",
            "UNIT",
            "SOURCE",
            "CONFIRMATION_DATE",
            "APPLICABILITY",
            "CONTRACT_VERSION",
        }
        self.assertEqual(len(rules), len({r["FIELD_NAME"] for r in rules}))
        for record in rules:
            self.assertTrue(required.issubset(record))
            self.assertEqual(record["SOURCE"], "OWNER_CONFIRMED")
            self.assertEqual(record["CONTRACT_VERSION"], study.VERSION)
        current = {r["FIELD_NAME"]: r for r in rules}
        old = json.loads((study.V1 / "owner-confirmed-business-rules.json").read_text())
        for record in old["rules"]:
            if record["FIELD_NAME"] != "SHIFT_ALLOCATION_POLICY":
                self.assertEqual(current[record["FIELD_NAME"]]["VALUE"], record["VALUE"])

    def test_26_source_tampering_and_project_mismatch_rejected(self) -> None:
        original = self.request()["mass_source"]
        cases: list[tuple[dict[str, Any], str]] = [
            ({"mass_source": {**original, "sha256": "0" * 64}}, "SOURCE_CONTENT_HASH_MISMATCH"),
            ({"mass_source": {"path": "missing.json", "sha256": "0" * 64}}, "SOURCE_FILE_MISSING"),
            ({"project_id": "OTHER"}, "SOURCE_PROJECT_OR_PERIOD_MISMATCH"),
            ({"daily_packaged_kg": "19999"}, "SOURCE_QUANTITY_MISMATCH"),
        ]
        for updates, reason in cases:
            self.assertEqual(self.calculate(**updates)["reason"], reason)

    def test_27_fractional_boundaries_no_mass_prerounding(self) -> None:
        for daily, workers, tables in (
            ("384.000002", 2, 1),
            ("1152", 3, 1),
            ("1152.000001", 4, 2),
            ("0", 0, 0),
        ):
            with self.subTest(daily=daily), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = {**self.examples[0]["result"]["source_record"], "daily_packaged_kg": daily}
                path = root / "mass.json"
                path.write_bytes(study.encode(source))
                request = self.request(
                    daily_packaged_kg=daily,
                    mass_source={"path": path.name, "sha256": study.sha(path)},
                )
                result = study.calculate(request, evidence_root=root)
                counts = result["staffing_and_tables"]
                self.assertEqual(
                    (
                        counts["SHIFT_1_WORKERS"],
                        counts["SHIFT_2_WORKERS"],
                        counts["PACKING_TABLE_COUNT"],
                    ),
                    (workers, workers, tables),
                )

    def test_28_negative_nonfinite_float_and_inconsistent_source_rejected(self) -> None:
        for mass in ("-1", "NaN", "Infinity", 1.6, True):
            self.assertEqual(
                self.calculate(daily_packaged_kg=mass)["reason"],
                "INVALID_EXACT_NONNEGATIVE_PRODUCT_MASS",
            )

    def test_29_film_and_process_inheritance_no_compliance_claim(self) -> None:
        result = self.calculate()
        film = result["film_sealing"]
        self.assertEqual(
            film["process_sequence"],
            ["SORTING_PACKAGING", "SECONDARY_PRECOOLING", "COATING_ROOM", "FINISHED_GOODS"],
        )
        self.assertEqual(film["DESIGN_FILM_SEALING_RATIO"], "1.0")
        self.assertTrue(film["NON_SEALING_PRODUCT_PASS_THROUGH_ALLOWED"])
        self.assertFalse(film["PASS_THROUGH_USES_EQUIPMENT"])
        self.assertFalse(film["SEPARATE_BYPASS_ROOM_ASSUMED"])
        self.assertFalse(result["P1_AREA_CALIBRATION_READY"])

    def test_30_no_native_solver_or_new_area_projection(self) -> None:
        self.assertNotIn("ortools", sys.modules)
        self.assertNotIn(
            "cold_storage.modules.layout.infrastructure.global_cp_sat_model", sys.modules
        )
        self.assertIsNone(self.calculate()["production_p1_area_m2"])
        self.assertNotIn("area_projection", self.calculate())

    def test_31_default_cannot_silently_ignore_explicit_source_shifts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = {
                **self.examples[0]["result"]["source_record"],
                "shift_1_packaging_kg": "16000",
                "shift_2_packaging_kg": "4000",
            }
            path = root / "mass.json"
            path.write_bytes(study.encode(source))
            request = self.request(mass_source={"path": path.name, "sha256": study.sha(path)})
            blocked = study.calculate(request, evidence_root=root)
            self.assertEqual(
                blocked["reason"], "SOURCE_EXPLICIT_SHIFT_DATA_REQUIRES_EXPLICIT_REQUEST"
            )
            explicit = study.calculate(
                {**request, "shift_1_packaging_kg": "16000", "shift_2_packaging_kg": "4000"},
                evidence_root=root,
            )
            self.assertEqual(explicit["allocation_mode"], "EXPLICIT_SHIFT_OVERRIDE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
