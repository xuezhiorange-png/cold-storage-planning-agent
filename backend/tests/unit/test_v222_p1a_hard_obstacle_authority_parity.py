"""R1 source alignment: real caller inputs, unchanged search and canonical replay."""

from __future__ import annotations

import inspect
import json
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from cold_storage.modules.layout.application import metric_interface_reservation as metric_app
from cold_storage.modules.layout.application.composition_placement import (
    enumerate_composition_placements,
)
from cold_storage.modules.layout.application.layout_authority_binding import bind_layout_authority
from cold_storage.modules.layout.application.site_geometry import validate_site_geometry
from cold_storage.modules.layout.application.structural_composition import (
    build_structural_compositions,
)
from cold_storage.modules.layout.domain import composition_placement as exact
from cold_storage.modules.layout.domain.authority_shapes import (
    AuthoritativeZoneShapeV1,
    authoritative_zone_shapes,
    canonical_construction_shapes,
)
from cold_storage.modules.layout.domain.dimensioning import (
    LayoutAuthorityError,
    canonical_hash,
    canonical_json,
)
from cold_storage.modules.layout.domain.metric_interface_reservation import (
    evaluate_pair_domain,
    rectangle_at,
)
from cold_storage.modules.layout.domain.site_geometry import (
    validated_hard_obstacle_polygons,
)
from tests.unit.test_v222_p1a_composition_authority_handoff import FIXTURE, _context

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = (
    ROOT
    / "docs/tasks/evidence/v2_2_2_p1a_exact_placement_hard_obstacle_authority_parity_r1"
    / "hard_obstacle_authority_parity.json"
)


def placement_summary() -> dict[str, Any]:
    result = enumerate_composition_placements(*_context())
    body = result.placements.to_dict()
    attempts = []
    for attempt in body["search_attempts"]:
        item = dict(attempt)
        item["construction_domains_hash"] = canonical_hash(item.pop("construction_domains"))
        item["best_partial_placement_witness_hash"] = canonical_hash(
            item.pop("best_partial_placement_witness")
        )
        attempts.append(item)
    summary = {
        k: v
        for k, v in body.items()
        if k not in ("candidates", "search_attempts", "best_partial_placement_witness_by_family")
    }
    summary.update(
        application_result_hash=result.canonical_result_hash,
        candidate_hashes=[c.canonical_result_hash for c in result.placements.candidates],
        candidate_count=len(result.placements.candidates),
        search_attempts=attempts,
    )
    return json.loads(canonical_json(summary))


def fixture_context(retained: bool) -> tuple[Any, Any, Any]:
    z, p, _ = _context()
    project = deepcopy(json.loads(FIXTURE.read_text()))
    project = {k: project[k] for k in ("site_constraints", "truck_access")}
    project["site_constraints"]["existing_buildings"] = [
        {
            "id": "r1-existing-building",
            "name": "R1 validated fixture",
            "retained": retained,
            "footprint": {
                "type": "polygon",
                "points": [
                    {"x": 20, "y": 20},
                    {"x": 23, "y": 20},
                    {"x": 23, "y": 23},
                    {"x": 20, "y": 23},
                ],
            },
        }
    ]
    return z, p, validate_site_geometry(project, z, p1_handoff=p)


def fixture_audit(retained: bool) -> dict[str, Any]:
    """Run both actual consumers, spying only on unchanged inputs to their search.

    Metric cap zero is explicit here: this fixture audits authority plumbing,
    not metric capacity. Canonical metric evidence separately exhausts the domain.
    """
    context = fixture_context(retained)
    payload = context[2].to_dict()
    expected = validated_hard_obstacle_polygons(payload)
    captured: dict[str, Any] = {}
    original_search = exact._search_one

    def shape_capture(label: str):
        def capture(authorities, boundary, obstacles):
            captured[label + "_obstacles"] = tuple(obstacles)
            shapes = authoritative_zone_shapes(authorities, boundary, obstacles)
            captured[label + "_shapes"] = {
                role: {
                    "authority_count": len(values),
                    "authority_hash": canonical_hash([asdict(s) for s in values]),
                    "construction_hash": canonical_hash(
                        [asdict(s) for s in canonical_construction_shapes(values)]
                    ),
                    "rotations": sorted({s.rotation_deg for s in values}),
                }
                for role, values in shapes.items()
            }
            return shapes

        return capture

    def search_capture(*args, **kwargs):
        values = inspect.signature(original_search).bind(*args, **kwargs).arguments
        assert tuple(values["obstacles"]) == expected
        probe = rectangle_at("office", (20500, 20500), AuthoritativeZoneShapeV1(1000, 1000, 0))
        captured["actual_search_candidate_rejection"] = exact._candidate_rejection(
            probe, {}, values["boundary"], values["obstacles"]
        )
        return original_search(*args, **kwargs)

    def bounded_domain(roles, shapes, boundary, obstacles):
        assert tuple(obstacles) == expected
        return evaluate_pair_domain(roles, shapes, boundary, obstacles, evaluation_cap=0)

    with (
        patch.object(exact, "_authority_shapes", shape_capture("exact")),
        patch.object(exact, "_search_one", search_capture),
        patch.object(metric_app, "authoritative_zone_shapes", shape_capture("p2")),
        patch.object(metric_app, "evaluate_pair_domain", bounded_domain),
    ):
        enumerate_composition_placements(*context, node_budget=3)
        metric_app.realize_metric_interface_reservations(*context)
    assert captured["exact_obstacles"] == captured["p2_obstacles"] == expected
    assert captured["exact_shapes"] == captured["p2_shapes"]
    assert captured["actual_search_candidate_rejection"] == ("OBSTACLE" if retained else None)
    return json.loads(
        canonical_json(
            {
                "retained": retained,
                "source_hard_obstacles": payload["obstacles"]["hard_obstacles"],
                "conditional_removal_footprints": payload["obstacles"][
                    "conditional_removal_footprints"
                ],
                "polygon_hashes": [canonical_hash(p) for p in expected],
                "candidate_rejection": captured["actual_search_candidate_rejection"],
                "p2_exact_obstacle_tuple_equal": True,
                "shape_domain_equal": True,
                "shape_domains": captured["exact_shapes"],
                "metric_fixture_mode": "CAP_ZERO_AUTHORITY_INPUT_AUDIT_ONLY",
            }
        )
    )


@pytest.mark.parametrize("retained", [True, False])
def test_real_validated_callers_retained_rejection_and_shape_parity(retained: bool) -> None:
    audit = fixture_audit(retained)
    buildings = [
        o for o in audit["source_hard_obstacles"] if o["kind"] == "RETAINED_EXISTING_BUILDING"
    ]
    assert len(buildings) == int(retained)
    assert any(o["kind"] == "NO_BUILD_ZONE" for o in audit["source_hard_obstacles"])
    if retained:
        assert buildings[0]["id"] == "r1-existing-building"
        assert buildings[0]["hard"] is True
    assert len(audit["conditional_removal_footprints"]) == int(not retained)


def test_no_build_obstacle_rejection_unchanged() -> None:
    poly = {
        "type": "polygon",
        "points": [
            {"x": 2, "y": 2},
            {"x": 3, "y": 2},
            {"x": 3, "y": 3},
            {"x": 2, "y": 3},
        ],
    }
    obstacles = validated_hard_obstacle_polygons(
        {
            "obstacles": {
                "hard_obstacles": [{"kind": "NO_BUILD_ZONE", "hard": True, "footprint": poly}],
            }
        }
    )
    probe = rectangle_at("office", (2500, 2500), AuthoritativeZoneShapeV1(100, 100, 0))
    assert (
        exact._candidate_rejection(
            probe, {}, ((0, 0), (10000, 0), (10000, 10000), (0, 10000)), obstacles
        )
        == "OBSTACLE"
    )


@pytest.mark.parametrize(
    "obstacles",
    [
        None,
        {},
        {"no_build_zones": []},
        {"hard_obstacles": None},
        {"hard_obstacles": {}},
        {"hard_obstacles": [None]},
        {"hard_obstacles": [{"hard": True}]},
        {"hard_obstacles": [{"hard": False, "footprint": {}}]},
        {"hard_obstacles": [{"hard": 1, "footprint": {}}]},
        {"hard_obstacles": [{"hard": True, "footprint": {}}]},
    ],
)
def test_missing_or_malformed_authority_fails_at_exact_domain_boundary(obstacles: Any) -> None:
    z, p, g = _context()
    binding = bind_layout_authority(z, p, g)
    handoffs = build_structural_compositions(z, p, g).placement_handoffs
    body = g.to_dict()
    body["obstacles"] = obstacles
    with pytest.raises(LayoutAuthorityError, match="INVALID_SITE_GEOMETRY_RESULT"):
        exact.enumerate_composition_placements(
            handoffs,
            binding.dimension_authorities,
            body,
            source_zone_plan_hash=binding.canonical_zone_plan_hash,
            source_p1_handoff_hash=binding.p1_handoff_hash,
            source_site_geometry_hash=binding.site_geometry_hash,
            node_budget=3,
        )


def test_empty_explicit_hard_authority_has_no_fallback() -> None:
    assert (
        validated_hard_obstacle_polygons(
            {
                "obstacles": {
                    "hard_obstacles": [],
                    "no_build_zones": ["must not be parsed"],
                }
            }
        )
        == ()
    )


def test_start_final_canonical_placement_parity() -> None:
    baseline = json.loads(EVIDENCE.read_text())["canonical_start_placement"]
    assert placement_summary() == baseline


def test_metric_parity_record_matches_actual_full_replays() -> None:
    """The direct evidence runner performs the expensive production calls.

    Require its terminal full-artifact comparison, not a mocked metric result.
    """
    record = json.loads(EVIDENCE.read_text())
    parity = record["p2_metric_parity"]
    assert parity["full_serialized_artifacts_equal"]
    assert parity["start_result_hash"] == parity["final_result_hash"]
    assert parity["final_result_hash"] == parity["final_second_result_hash"]
    assert parity["realization_count"] == 42
    assert len(parity["compositions"]) == 6
    for composition in parity["compositions"]:
        assert len(composition["interfaces"]) == 7
        assert composition["gate"]["status"] == "PASS_METRIC_RESERVATIONS_TO_FUTURE_PLACEMENT"
        assert all(i["finite_domain_complete"] for i in composition["interfaces"])
    assert record["canonical_start_placement"] == record["canonical_final_placement"]
    assert (
        canonical_hash(record["canonical_final_placement"])
        == record["canonical_final_second_placement_hash"]
    )
