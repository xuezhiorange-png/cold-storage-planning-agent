"""Evidence and arithmetic tests only: no production model or native solver import."""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
import unittest
from fractions import Fraction
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "functional_calibration_offline", HERE / "calibrate.py"
)
assert spec and spec.loader
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)


class FunctionalRoomCalibrationTest(unittest.TestCase):
    impact: dict[str, Any]
    sources: dict[str, Any]

    @classmethod
    def setUpClass(cls) -> None:
        cls.impact = study.build()
        cls.sources = json.loads((HERE / "engineering-sources.json").read_text())

    def test_01_source_records_have_required_metadata_and_no_guessed_dates(self) -> None:
        keys = {
            "SOURCE_TITLE",
            "SOURCE_URL",
            "PUBLISHER",
            "PUBLICATION_DATE",
            "STANDARD_VERSION",
            "CURRENT_VALIDITY",
            "APPLICABLE_ROOM",
            "RELEVANT_CLAUSE_OR_SECTION",
            "ENGINEERING_REQUIREMENT",
            "EVIDENCE_LEVEL",
            "LIMITATIONS",
        }
        self.assertEqual(len(self.sources["sources"]), 11)
        for source in self.sources["sources"]:
            self.assertTrue(keys.issubset(source))
            self.assertTrue(source["SOURCE_URL"].startswith("https://"))
        self.assertEqual(self.sources["sources"][0]["STANDARD_VERSION"], "GB 14881-2025")
        self.assertEqual(len(self.sources["unverified_requirements"]), 3)

    def test_02_exact_eight_geometries_twenty_four_rooms(self) -> None:
        rows = self.impact["rooms"]
        self.assertEqual(len(rows), 24)
        self.assertEqual(len({r["candidate_id"] for r in rows}), 8)
        for role in study.ROOMS:
            self.assertEqual(sum(r["zone_code"] == role for r in rows), 8)
        self.assertEqual(self.impact["meaningful_constructions"], 6)
        self.assertEqual(self.impact["major_families"], 4)

    def test_03_area_physical_sides_and_aspect_are_exact(self) -> None:
        for r in self.impact["rooms"]:
            self.assertEqual(
                Fraction(r["physical_width_m"]) * Fraction(r["physical_depth_m"]),
                Fraction(r["actual_area_m2"]),
            )
            self.assertEqual(
                Fraction(r["long_side_m"]) / Fraction(r["short_side_m"]),
                Fraction(r["aspect_exact"]),
            )
            self.assertTrue(r["current_area_requirement_met"])

    def test_04_staff_missing_cannot_be_inferred_from_area(self) -> None:
        for r in self.impact["rooms"]:
            self.assertEqual(r["STAFF_COUNT"], "UNAVAILABLE")
        result = study.office_module(
            people=None,
            rows=1,
            desk_width=1600,
            desk_depth=800,
            user_zone=None,
            through_aisle=None,
            side_storage=None,
            end_space=None,
        )
        self.assertEqual(result["status"], "OWNER_INPUT_REQUIRED")
        self.assertIsNone(result["value"])

    def test_05_explicit_synthetic_office_module_not_a_project_design(self) -> None:
        # Positive values here are synthetic arithmetic fixtures, not sourced design minima.
        result = study.office_module(
            people=3,
            rows=2,
            desk_width=1600,
            desk_depth=800,
            user_zone=111,
            through_aisle=222,
            side_storage=333,
            end_space=44,
        )
        self.assertEqual(result["cross_section_mm"], 2 * (800 + 111) + 222 + 333)
        self.assertEqual(result["length_mm"], 2 * 1600 + 2 * 44)
        self.assertFalse(result["project_approved"])

    def test_06_double_lockers_furniture_lower_bound_two_failures_only(self) -> None:
        rejected = [
            r
            for r in self.impact["rooms"]
            if r["conditional_screening"].get(
                "double_row_furniture_alone_impossible_under_this_scenario"
            )
        ]
        self.assertEqual(len(rejected), 2)
        self.assertEqual({r["short_side_m"] for r in rejected}, {"0.875", "0.977"})
        self.assertEqual(
            {
                r["conditional_screening"]["double_row_remaining_before_all_clearances_mm"]
                for r in rejected
            },
            {-125, -23},
        )
        for r in rejected:
            self.assertFalse(r["conditional_screening"]["formal_contract_violation"])

    def test_07_single_row_residual_is_not_an_approved_aisle(self) -> None:
        for r in self.impact["rooms"]:
            if r["zone_code"] == "changing_room" and r["short_side_m"] in {"0.875", "0.977"}:
                self.assertIn(
                    r["conditional_screening"]["single_row_remaining_before_all_clearances_mm"],
                    {375, 477},
                )
                self.assertIsNone(r["conditional_screening"]["actual_functional_pass"])

    def test_08_storage_and_simultaneous_users_not_defaulted(self) -> None:
        result = study.locker_module(
            users=None,
            rows=2,
            unit_width=322,
            unit_depth=500,
            slots_per_unit=1,
            front_service_zone=None,
            bench=None,
            independent_aisle=None,
            end_space=None,
        )
        self.assertEqual(result["status"], "OWNER_INPUT_REQUIRED")
        value = study.locker_module(
            users=5,
            rows=2,
            unit_width=322,
            unit_depth=500,
            slots_per_unit=1,
            front_service_zone=111,
            bench=222,
            independent_aisle=333,
            end_space=44,
        )
        self.assertEqual(value["unit_count"], 5)
        self.assertEqual(value["length_mm"], 3 * 322 + 88)
        self.assertEqual(value["cross_section_mm"], 1666)

    def test_09_equipment_is_not_operation_or_maintenance_envelope(self) -> None:
        result = study.envelope_state(
            equipment=[[0, 0, 2490, 1640]],
            operation=None,
            maintenance=None,
            material=None,
            mode="NORMAL",
        )
        self.assertEqual(result["status"], "OWNER_INPUT_REQUIRED")
        self.assertIsNone(result["bbox_mm"])

    def test_10_states_are_not_silently_added_or_omitted(self) -> None:
        args = dict(
            equipment=[[0, 0, 10, 10]],
            operation=[[10, 0, 12, 10]],
            maintenance=[[-5, 0, 0, 10]],
            material=[],
        )
        normal = study.envelope_state(**args, mode="NORMAL")
        maintenance = study.envelope_state(**args, mode="MAINTENANCE")
        self.assertEqual(normal["bbox_mm"], [0, 0, 12, 10])
        self.assertEqual(maintenance["bbox_mm"], [-5, 0, 10, 10])
        self.assertFalse(normal["project_approved"])

    def test_11_numeric_requirements_remain_unapproved_and_null(self) -> None:
        req = json.loads((HERE / "functional-room-requirements.json").read_text())
        for role in study.ROOMS:
            for key in [
                "functional_minimum_short_side_m",
                "functional_minimum_depth_m",
                "recommended_aspect_ratio_range",
                "staff_count",
            ]:
                self.assertIsNone(req[role][key])
            self.assertFalse(req[role]["formal_threshold_approved"])
        proposal = json.loads((HERE / "dimension-calibration-proposal.json").read_text())
        self.assertFalse(proposal["numeric_calibration_ready"])
        self.assertFalse(proposal["formal_thresholds_frozen"])

    def test_12_actual_fail_closed_guard_and_parent_constructor_preserved_statically(self) -> None:
        audit = study.source_audit()
        self.assertTrue(audit["guard_preserved"])
        self.assertEqual(len(audit["guard_fields"]), 5)
        path = (
            study.REPO
            / "backend/src/cold_storage/modules/layout/infrastructure/global_cp_sat_model.py"
        )
        tree = ast.parse(path.read_text())
        access = next(
            n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "AccessModel"
        )
        parent = access.bases[0]
        assert isinstance(parent, ast.Name)
        self.assertEqual(parent.id, "GlobalModel")
        segment = ast.get_source_segment(path.read_text(), access)
        assert segment is not None
        self.assertIn("super().__init__(c, h)", segment)

    def test_13_baseline_integrity_and_duplicate_organizations_not_changed(self) -> None:
        integrity = json.loads((HERE / "baseline-integrity.json").read_text())
        for path, expected in integrity["files"].items():
            self.assertEqual(study.sha(study.REPO / path), expected)
        for r in self.impact["rooms"]:
            if r["candidate_id"].startswith("guided-") and r["candidate_id"][-2:] in {"05", "06"}:
                self.assertFalse(r["v2_counted"])

    def test_14_invalid_negative_zero_and_fractional_inputs_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            study.require_numbers({"aisle": -1})
        with self.assertRaises(ValueError):
            study.mm("0.0001")
        with self.assertRaises(ValueError):
            study.office_module(
                people=0,
                rows=1,
                desk_width=1600,
                desk_depth=800,
                user_zone=0,
                through_aisle=0,
                side_storage=0,
                end_space=0,
            )

    def test_15_deterministic_source_bound_outputs(self) -> None:
        names = [
            "functional-room-requirements.json",
            "dimension-calibration-proposal.json",
            "existing-layout-impact.json",
            "existing-layout-impact.csv",
            "code-audit.json",
            "baseline-integrity.json",
        ]
        before = {name: study.sha(HERE / name) for name in names}
        study.build()
        self.assertEqual(before, {name: study.sha(HERE / name) for name in names})

    def test_16_no_production_or_solver_imports(self) -> None:
        tree = ast.parse((HERE / "calibrate.py").read_text())
        modules = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        self.assertFalse(any("cold_storage" in m or "ortools" in m for m in modules))
        self.assertNotIn("ortools", sys.modules)


if __name__ == "__main__":
    unittest.main(verbosity=2)
