"""P1-S4 composition-native candidate replay and existing P2D bridge tests."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from cold_storage.modules.layout.application.composition_placement import (
    CompositionPlacementApplicationResultV1,
    enumerate_composition_placements,
)
from cold_storage.modules.layout.application.layout_authority_binding import bind_layout_authority
from cold_storage.modules.layout.application.site_geometry import ValidatedSiteGeometryV1
from cold_storage.modules.layout.domain.composition_placement import (
    DEFAULT_COMPOSITION_PLACEMENT_NODE_BUDGET,
    CompositionPlacementCandidateV1,
)
from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError
from cold_storage.modules.layout.domain.truck_maneuver import (
    BoundTruckManeuverProjectInputV1,
    validate_truck_maneuver_project_binding,
)
from tests.unit.test_v222_p1a_composition_authority_handoff import _context

ROOT = Path(__file__).resolve().parents[3]
XINZHAO_FIXTURE = ROOT / "backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json"


@pytest.fixture(scope="module")
def xinzhao_server_replay() -> tuple[
    dict[str, Any],
    Any,
    ValidatedSiteGeometryV1,
    BoundTruckManeuverProjectInputV1,
    CompositionPlacementApplicationResultV1,
    CompositionPlacementCandidateV1,
]:
    zone_plan, p1_handoff, site_geometry = _context()
    source = json.loads(XINZHAO_FIXTURE.read_text())
    truck_binding = validate_truck_maneuver_project_binding(
        source["truck_access"], source["truck_maneuver"]
    )
    replay = enumerate_composition_placements(zone_plan, p1_handoff, site_geometry)
    assert replay.placements.candidates
    return (
        zone_plan,
        p1_handoff,
        site_geometry,
        truck_binding,
        replay,
        replay.placements.candidates[0],
    )


def _geometry(rows: list[dict[str, Any]]) -> dict[str, tuple[object, ...]]:
    return {
        row["zone_code"]: (
            Decimal(str(row["x"])),
            Decimal(str(row["y"])),
            Decimal(str(row["width_m"])),
            Decimal(str(row["depth_m"])),
            int(row["rotation_deg"]),
        )
        for row in rows
    }


@pytest.fixture(scope="module")
def xinzhao_validation_result(
    xinzhao_server_replay: tuple[
        dict[str, Any],
        Any,
        ValidatedSiteGeometryV1,
        BoundTruckManeuverProjectInputV1,
        CompositionPlacementApplicationResultV1,
        CompositionPlacementCandidateV1,
    ],
) -> Any:
    from cold_storage.modules.layout.application.composition_candidate_validation import (
        validate_composition_candidate,
    )

    zone_plan, p1_handoff, site_geometry, truck_binding, _replay, candidate = xinzhao_server_replay
    return validate_composition_candidate(
        zone_plan,
        p1_handoff,
        site_geometry,
        truck_binding,
        candidate.canonical_result_hash,
    )


def test_s4_public_api_only_accepts_candidate_hash_not_caller_candidate() -> None:
    import cold_storage.modules.layout.application.composition_candidate_validation as bridge

    zone_plan, p1_handoff, site_geometry = _context()
    source = json.loads(XINZHAO_FIXTURE.read_text())
    truck_binding = validate_truck_maneuver_project_binding(
        source["truck_access"], source["truck_maneuver"]
    )
    with pytest.raises(LayoutAuthorityError, match="COMPOSITION_CANDIDATE_REFERENCE_INVALID"):
        bridge.validate_composition_candidate(
            zone_plan,
            p1_handoff,
            site_geometry,
            truck_binding,
            object(),  # type: ignore[arg-type]
        )


def test_s4_rejects_a_stale_candidate_hash_from_server_replay(
    xinzhao_server_replay: tuple[
        dict[str, Any],
        Any,
        ValidatedSiteGeometryV1,
        BoundTruckManeuverProjectInputV1,
        CompositionPlacementApplicationResultV1,
        CompositionPlacementCandidateV1,
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import cold_storage.modules.layout.application.composition_candidate_validation as bridge

    zone_plan, p1_handoff, site_geometry, truck_binding, replay, _candidate = xinzhao_server_replay
    monkeypatch.setattr(bridge, "enumerate_composition_placements", lambda *args, **kwargs: replay)
    with pytest.raises(LayoutAuthorityError, match="COMPOSITION_CANDIDATE_REPLAY_MISMATCH"):
        bridge.validate_composition_candidate(
            zone_plan,
            p1_handoff,
            site_geometry,
            truck_binding,
            "sha256:" + "0" * 64,
        )


def test_adapter_preserves_candidate_geometry_dimensions_roles_and_provenance(
    xinzhao_server_replay: tuple[
        dict[str, Any],
        Any,
        ValidatedSiteGeometryV1,
        BoundTruckManeuverProjectInputV1,
        CompositionPlacementApplicationResultV1,
        CompositionPlacementCandidateV1,
    ],
) -> None:
    from cold_storage.modules.layout.application.composition_candidate_validation import (
        _adapt_candidate_to_existing_placement,
    )

    zone_plan, p1_handoff, site_geometry, _truck_binding, replay, candidate = xinzhao_server_replay
    binding = bind_layout_authority(zone_plan, p1_handoff, site_geometry)
    adapted = _adapt_candidate_to_existing_placement(
        candidate,
        dimension_authorities=binding.dimension_authorities,
        site_body=site_geometry.to_dict(),
        source_zone_plan_hash=replay.source_zone_plan_hash,
        source_p1_handoff_hash=replay.source_p1_handoff_hash,
        source_site_geometry_hash=replay.source_site_geometry_hash,
    ).to_dict()
    expected = _geometry([zone.to_dict() for zone in candidate.zones])
    assert _geometry(adapted["zones"]) == expected
    assert set(expected) == set(adapted["zone_code"] for adapted in adapted["zones"])
    assert adapted["source_zone_plan_hash"] == replay.source_zone_plan_hash
    assert adapted["source_p1_handoff_hash"] == replay.source_p1_handoff_hash
    assert adapted["source_site_geometry_hash"] == replay.source_site_geometry_hash
    assert (
        adapted["composition_native_provenance"]["candidate_hash"]
        == candidate.canonical_result_hash
    )
    assert adapted["search_provenance"]["geometry_repair_performed"] is False
    assert replay.placements.node_budget == DEFAULT_COMPOSITION_PLACEMENT_NODE_BUDGET == 60_000


def test_xinzhao_candidate_runs_once_through_existing_access_truck_and_p2d(
    xinzhao_server_replay: tuple[
        dict[str, Any],
        Any,
        ValidatedSiteGeometryV1,
        BoundTruckManeuverProjectInputV1,
        CompositionPlacementApplicationResultV1,
        CompositionPlacementCandidateV1,
    ],
    xinzhao_validation_result: Any,
) -> None:
    _zone_plan, _p1_handoff, _site_geometry, _truck_binding, _replay, candidate = (
        xinzhao_server_replay
    )
    result = xinzhao_validation_result.to_dict()
    validation = result["existing_validation_result"]
    assert result["implementation_result"] == "PASS"
    assert result["server_side_candidate_replay_enforced"] is True
    assert result["candidate_hash"] == candidate.canonical_result_hash
    assert result["validated_composition_candidate_count"] >= 1
    assert result["family"] == "LINEAR_BANDED"
    assert result["process_axis"] == "Y"
    assert result["process_direction"] == "POSITIVE"
    assert result["adapter_geometry_changed"] is False
    assert result["adapter_dimension_changed"] is False
    assert result["adapter_role_set_changed"] is False
    assert result["adapter_provenance_preserved"] is True
    assert result["existing_access_authority_used"] is True
    assert result["access_routing_performed"] is True
    assert result["access_requirement_count"] == 12
    assert result["candidate_hash"] == (
        "sha256:4a4b8f6695526ea0bd1cf30238ae4c7c45b35e6d9677b0c4bd8f98228e8f3c47"
    )
    assert result["access_pass_count"] == 7
    assert result["access_fail_count"] == 5
    assert result["access_pass_count"] + result["access_fail_count"] == 12
    access_statuses = {
        row["requirement_identity"]: (row["status"], tuple(row.get("codes", [])))
        for row in validation["access_results"]
    }
    assert access_statuses == {
        "access:changing_room->sorting_packaging_room@1.0.0": ("PASS", ()),
        "access:coating_room->finished_goods_room@1.0.0": ("PASS", ()),
        "access:finished_goods_room->shipping_channel@1.0.0": ("PASS", ()),
        "access:main_entrance->changing_room@1.0.0": (
            "BLOCKED",
            ("ROUTE_SEARCH_EXHAUSTED",),
        ),
        "access:packaging_material_storage->sorting_packaging_room@1.0.0": (
            "FAIL",
            ("PACKAGING_SORTING_STRAIGHT_ROUTE_REQUIRED",),
        ),
        "access:primary_precooling_room->sorting_packaging_room@1.0.0": ("PASS", ()),
        "access:raw_fruit_buffer->primary_precooling_room@1.0.0": ("PASS", ()),
        "access:secondary_precooling_room->coating_room@1.0.0": ("PASS", ()),
        "access:sorting_packaging_room->frozen_fruit_room@1.0.0": (
            "BLOCKED",
            ("ROUTE_SEARCH_EXHAUSTED",),
        ),
        "access:sorting_packaging_room->secondary_fruit_buffer@1.0.0": (
            "BLOCKED",
            ("ROUTE_SEARCH_EXHAUSTED",),
        ),
        "access:sorting_packaging_room->secondary_precooling_room@1.0.0": ("PASS", ()),
        "access:truck_entrance->shipping_channel@1.0.0": (
            "BLOCKED",
            ("TRUCK_MANEUVER_SEARCH_EXHAUSTED",),
        ),
    }
    assert result["portal_validation_performed"] is True
    assert result["existing_truck_authority_used"] is True
    assert result["truck_validation_performed"] is True
    assert result["truck_route_status"] == "TRUCK_MANEUVER_SEARCH_EXHAUSTED"
    assert validation["truck_search_provenance"] == {
        "node_budget": 20_000,
        "node_budget_exhausted": False,
        "search_tree_exhausted": True,
        "template_reuse_allowed": False,
        "visited_nodes": 27,
    }
    assert result["loading_face_validated"] is True
    assert result["existing_p2d_authority_used"] is True
    assert result["p2d_performed"] is True
    assert result["no_geometry_repair_performed"] is True
    assert len(validation["access_results"]) == 12
    assert _geometry(validation["zones"]) == _geometry(result["adapter_placement_result"]["zones"])
    assert result["project_layout_validated"] is validation["project_layout_validated"]
    assert result["p2_complete"] is validation["p2_complete"]
    assert result["p2d_result_hash"] == validation["canonical_result_hash"]
    if result["p2_complete"] is not True:
        assert result["failure_stage"] != "NONE"
        assert result["failure_codes"]
        assert result["global_infeasibility_proven"] is False


def test_validation_result_hash_is_deterministic_for_replayed_candidate(
    xinzhao_validation_result: Any,
) -> None:
    from cold_storage.modules.layout.application.composition_candidate_validation import (
        CompositionCandidateValidationResultV1,
    )

    first = xinzhao_validation_result
    second = CompositionCandidateValidationResultV1(first.to_dict())
    assert first.canonical_result_hash == second.canonical_result_hash
