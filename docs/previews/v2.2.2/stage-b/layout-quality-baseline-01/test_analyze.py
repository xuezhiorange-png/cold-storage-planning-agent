"""Portable evidence/math regression tests; no production solve or grant imports."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("layout_quality_offline", HERE / "analyze.py")
assert spec and spec.loader
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class QualityFactsTest(unittest.TestCase):
    sources: dict[str, Any]
    inputs: list[dict[str, Any]]
    results: list[dict[str, Any]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = json.loads((HERE / "sources.json").read_text())
        cls.inputs = [
            json.loads((HERE / row["input"]).read_text()) for row in cls.sources["candidates"]
        ]
        cls.results = [audit.analyze(data) for data in cls.inputs]

    def test_01_all_eight_sealed_sources_and_authority(self) -> None:
        self.assertEqual(len(self.inputs), 8)
        for row, data in zip(self.sources["candidates"], self.inputs, strict=True):
            self.assertEqual(
                audit.sha((HERE / row["input"]).read_bytes()), row["projection_sha256"]
            )
            self.assertEqual(
                row["raw_candidate_sha256"], data["provenance"]["raw_candidate_sha256"]
            )
            self.assertTrue(data["independent_validation"]["pass"])
            self.assertTrue(data["native_independent_validation"]["pass"])
        self.assertEqual(
            audit.sha((HERE / "inputs/server_authorities.json").read_bytes()),
            self.sources["authority_sha256"],
        )
        self.assertTrue(
            all(a["candidate_bytes_match_archive_and_manifest"] for a in self.sources["archives"])
        )

    def test_02_ninety_six_areas_and_rotations(self) -> None:
        count = 0
        for data in self.inputs:
            for z in data["engineering_validation"]["zones"]:
                x0, y0, x1, y1 = audit.box(z)
                self.assertEqual(
                    Fraction((x1 - x0) * (y1 - y0), 1000000), Fraction(z["actual_area_m2"])
                )
                count += 1
        self.assertEqual(count, 96)

    def test_03_aspect_and_short_side_extreme_samples(self) -> None:
        rows = self.results[4]["METRICS"]["ROOM_DIMENSION_FACTS"]["VALUE"]
        changing = next(r for r in rows if r["zone"] == "changing_room")
        self.assertEqual(changing["min_side_m"], "0.875")
        self.assertEqual(Fraction(changing["aspect_exact"]), Fraction(45759, 875))
        coating = next(
            r
            for r in self.results[2]["METRICS"]["ROOM_DIMENSION_FACTS"]["VALUE"]
            if r["zone"] == "coating_room"
        )
        self.assertEqual((coating["width_m"], coating["depth_m"]), ("41.026", "1.95"))

    def test_04_outline_rectangle_l_and_multireflex(self) -> None:
        rectangle = audit.outline([(0, 0), (4, 0), (4, 3), (0, 3)])
        self.assertEqual(
            (
                rectangle["area_mm2"],
                rectangle["perimeter_mm"],
                rectangle["reflex"],
                rectangle["notches"],
            ),
            (12, 14, 0, 0),
        )
        vertices = [(0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4)]
        facts = audit.outline(vertices)
        self.assertEqual((facts["area_mm2"], facts["reflex"], facts["notches"]), (7, 1, 1))
        self.assertEqual(facts, audit.outline(list(reversed(vertices))))
        self.assertNotEqual(facts["reflex"], facts["turns"])

    def test_05_grid_requires_actual_positive_shared_wall(self) -> None:
        separated = {role: (i * 10, 0, i * 10 + 2, 2) for i, role in enumerate(audit.MAJOR)}
        self.assertEqual(audit.grid_facts(separated)["aligned_incidences"], 0)
        separated[audit.MAJOR[1]] = (2, 0, 4, 2)
        self.assertEqual(audit.grid_facts(separated)["primary_x_axes_mm"], [2])

    def test_06_missing_complete_process_route_abstains(self) -> None:
        for result in self.results:
            for key in (
                "MAIN_FLOW_TURN_COUNT",
                "MAIN_FLOW_BACKTRACK_COUNT",
                "PROCESS_FLOW_ORDER_PASS",
                "MAIN_PROCESS_ROUTE_LENGTH_M",
                "PROCESS_ROUTE_EFFICIENCY_RATIO",
            ):
                metric = result["METRICS"][key]
                self.assertEqual(metric["STATUS"], "UNAVAILABLE")
                self.assertIsNone(metric["VALUE"])

    def test_07_adjacency_directions_are_not_route_turns(self) -> None:
        original = self.inputs[0]
        modified = deepcopy(original)
        modified["composition_handoff"]["process_direction"] = "NEGATIVE"
        a, b = audit.analyze(original), audit.analyze(modified)
        self.assertEqual(
            a["METRICS"]["MAIN_FLOW_BACKTRACK_COUNT"], b["METRICS"]["MAIN_FLOW_BACKTRACK_COUNT"]
        )
        self.assertEqual(len(a["ROOM_ADJACENCY_DIRECTIONS_NOT_ROUTE_TURNS"]), 6)

    def test_08_historical_and_latest_independent_counts(self) -> None:
        self.assertEqual(len({r["SOURCE_GEOMETRY_HASH"] for r in self.results}), 8)
        self.assertNotEqual(self.results[0]["SOURCE_HEAD"], self.results[2]["SOURCE_HEAD"])
        self.assertEqual(sum(r["V2_MEANINGFUL_CONSTRUCTION"] for r in self.results), 6)
        self.assertEqual(len({r["MAJOR_FAMILY_HASH"] for r in self.results}), 4)

    def test_09_latest_five_six_do_not_add_organizations(self) -> None:
        self.assertTrue(self.results[5]["V2_MEANINGFUL_CONSTRUCTION"])
        for r in self.results[6:]:
            self.assertFalse(r["V2_MEANINGFUL_CONSTRUCTION"])
            self.assertEqual(r["V2_MEANINGFUL_HASH"], self.results[5]["V2_MEANINGFUL_HASH"])

    def test_10_uncalibrated_metrics_do_not_pass(self) -> None:
        for r in self.results:
            self.assertFalse(r["NUMERIC_CALIBRATION_READY"])
            self.assertFalse(r["QUALITY_RANKING_PERFORMED"])
            self.assertEqual(r["METRICS"]["LAYOUT_REGULARITY_VALIDATED"]["STATUS"], "UNAVAILABLE")
            self.assertFalse(r["METRICS"]["P2D_FULL_PASS"]["VALUE"])

    def test_11_deterministic_facts_bytes_and_hash(self) -> None:
        for original, expected in zip(self.inputs, self.results, strict=True):
            self.assertEqual(
                audit.encoded(audit.analyze(deepcopy(original))), audit.encoded(expected)
            )
            self.assertEqual(
                audit.sha(audit.encoded(audit.analyze(original))),
                audit.sha(audit.encoded(expected)),
            )

    def test_12_metric_metadata_complete_no_null_as_zero(self) -> None:
        def check(value: Any) -> None:
            if isinstance(value, dict):
                if "STATUS" in value:
                    self.assertTrue(
                        {
                            "VALUE",
                            "UNIT",
                            "STATUS",
                            "SOURCE",
                            "CALCULATION_METHOD",
                            "DEFINITION_VERSION",
                            "EVIDENCE_HASH",
                            "UNAVAILABLE_REASON",
                        }.issubset(value)
                    )
                    if value["STATUS"] in {"UNAVAILABLE", "NOT_APPLICABLE"}:
                        self.assertIsNone(value["VALUE"])
                        self.assertTrue(value["UNAVAILABLE_REASON"])
                for v in value.values():
                    check(v)
            elif isinstance(value, list):
                for v in value:
                    check(v)

        check(self.results)

    def test_13_personnel_actual_centerline_and_no_indoor_inference(self) -> None:
        self.assertEqual(self.results[0]["METRICS"]["PERSONNEL_ROUTE_LENGTH_M"]["VALUE"], "58.629")
        self.assertEqual(self.results[1]["METRICS"]["PERSONNEL_ROUTE_LENGTH_M"]["VALUE"], "11.214")
        for r in self.results:
            self.assertEqual(
                r["METRICS"]["PERSONNEL_LOGISTICS_SEPARATION"]["STATUS"], "UNAVAILABLE"
            )

    def test_14_mm_grid_has_no_rounding_tolerance(self) -> None:
        self.assertEqual(audit.mm("0.007"), 7)
        with self.assertRaises(ValueError):
            audit.mm("0.0001")

    def test_15_source_secondary_ownership_is_current_p1a(self) -> None:
        for r in self.results:
            rooms = r["METRICS"]["ROOM_DIMENSION_FACTS"]["VALUE"]
            secondary = next(x for x in rooms if x["zone"] == "secondary_precooling_room")
            self.assertEqual(secondary["group"], "PROCESSING_CORE_GROUP")

    def test_16_no_solver_or_production_imports(self) -> None:
        import ast

        tree = ast.parse((HERE / "analyze.py").read_text())
        imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        self.assertFalse(any(x and ("cold_storage" in x or "ortools" in x) for x in imports))
        self.assertNotIn("ortools", sys.modules)

    def test_17_zero_eligible_depth_pairs_are_not_a_numeric_rate(self) -> None:
        for result in self.results:
            depth = result["DEPTH_PAIR_ELIGIBILITY"]
            self.assertEqual(depth["eligible_pair_count"], 0)
            self.assertEqual(len(depth["excluded_pairs"]), 10)
            metric = result["METRICS"]["MAJOR_ZONE_DEPTH_ALIGNMENT_RATE"]
            self.assertEqual(metric["STATUS"], "NOT_APPLICABLE")
            self.assertIsNone(metric["VALUE"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
