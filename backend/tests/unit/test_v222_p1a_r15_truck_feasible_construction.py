"""Unit contracts for truck-aware constructive main-skeleton admission."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from cold_storage.modules.layout.domain import placement
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1
from cold_storage.modules.layout.domain.structural_composition import (
    LINEAR_PROCESS_BAND,
    StructuralCompositionFamilyV1,
)


class _Family:
    family = placement.LINEAR_PROCESS_BAND
    dominant_axis = "Y"
    dominant_direction = "POSITIVE"

    def to_dict(self) -> dict[str, str]:
        return {"family": "LINEAR_PROCESS_BAND"}


def _skeleton(identity: str = "sha256:main-skeleton") -> SimpleNamespace:
    return SimpleNamespace(
        main_process_skeleton_hash=identity,
        topology="STRAIGHT_LINEAR_BAND",
        canonical_topology_owner="STRAIGHT_LINEAR_BAND",
        family=_Family(),
    )


def _context(registry: dict[str, dict[str, Any]]) -> SimpleNamespace:
    return SimpleNamespace(
        global_main_process_geometry_registry=registry,
        global_cross_topology_duplicate_trace=[],
        structural_topology="STRAIGHT_LINEAR_BAND",
    )


def _truck_row(status: str) -> dict[str, Any]:
    return {
        "main_skeleton_hash": "sha256:main-skeleton",
        "preflight_status": status,
        "preflight_action": "REJECT_SKELETON" if status == "REJECT" else "ALLOW_TAIL_SEARCH",
        "failure_reason": "TRUCK_MANEUVER_SEARCH_EXHAUSTED" if status == "REJECT" else None,
        "failure_codes": ["TRUCK_MANEUVER_SEARCH_EXHAUSTED"] if status == "REJECT" else [],
        "visited_nodes": 39 if status == "REJECT" else 3,
        "node_budget": 5000,
        "node_budget_exhausted": False,
        "search_tree_exhausted": True,
    }


def _install_packaging_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        placement,
        "_packaging_tail_slot_preflight",
        lambda _context, _skeleton: {
            "proof_mode": placement.EXACT_ORTHOGONAL_EVENT_ENUMERATION,
            "legal_slot_exists": True,
        },
    )


def test_exhaustive_truck_failure_is_pruned_before_skeleton_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_packaging_pass(monkeypatch)
    calls: list[str] = []

    def reject(_context: object, skeleton: object) -> dict[str, Any]:
        calls.append(skeleton.main_process_skeleton_hash)
        return _truck_row("REJECT")

    monkeypatch.setattr(placement, "_main_skeleton_truck_maneuver_preflight", reject)
    registry: dict[str, dict[str, Any]] = {}
    stats = placement._PlacementSearchStats()

    assert not placement._constructive_main_skeleton_tail_admission(
        _context(registry), stats, _skeleton()
    )
    # Rediscovery reuses the exact preflight result rather than spending more
    # truck-search work or admitting the failed geometry.
    assert not placement._constructive_main_skeleton_tail_admission(
        _context(registry), stats, _skeleton()
    )
    assert calls == ["sha256:main-skeleton"]
    assert registry["sha256:main-skeleton"]["tail_search_started"] is False
    assert (
        registry["sha256:main-skeleton"]["main_skeleton_truck_preflight"]["preflight_status"]
        == "REJECT"
    )
    assert len(stats.main_skeleton_truck_preflight_rows or []) == 2
    assert all(
        row["failure_reason"] == "TRUCK_MANEUVER_SEARCH_EXHAUSTED"
        for row in stats.main_skeleton_truck_preflight_rows or []
    )
    assert stats.skeleton_tail_lifecycle
    assert all(row["tail_search_started"] is False for row in stats.skeleton_tail_lifecycle)


def test_truck_pass_admits_geometry_once_and_outer_tail_owns_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_packaging_pass(monkeypatch)
    calls: list[str] = []

    def allow(_context: object, skeleton: object) -> dict[str, Any]:
        calls.append(skeleton.main_process_skeleton_hash)
        return _truck_row("PASS")

    monkeypatch.setattr(placement, "_main_skeleton_truck_maneuver_preflight", allow)
    registry: dict[str, dict[str, Any]] = {}
    context = _context(registry)
    stats = placement._PlacementSearchStats()
    candidate = _skeleton()

    assert placement._constructive_main_skeleton_tail_admission(context, stats, candidate)
    assert registry[candidate.main_process_skeleton_hash]["tail_search_started"] is False
    assert (
        registry[candidate.main_process_skeleton_hash]["main_skeleton_truck_preflight"][
            "preflight_status"
        ]
        == "PASS"
    )

    registry[candidate.main_process_skeleton_hash]["tail_search_started"] = True
    assert not placement._constructive_main_skeleton_tail_admission(context, stats, candidate)
    assert calls == [candidate.main_process_skeleton_hash]


def test_packaging_slot_rejection_does_not_run_truck_or_admit_tail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        placement,
        "_packaging_tail_slot_preflight",
        lambda _context, _skeleton: {
            "proof_mode": placement.EXACT_ORTHOGONAL_EVENT_ENUMERATION,
            "legal_slot_exists": False,
        },
    )
    monkeypatch.setattr(
        placement,
        "_main_skeleton_truck_maneuver_preflight",
        lambda *_args: pytest.fail("truck search must not run after exact slot rejection"),
    )
    registry: dict[str, dict[str, Any]] = {}
    stats = placement._PlacementSearchStats()

    assert not placement._constructive_main_skeleton_tail_admission(
        _context(registry), stats, _skeleton()
    )
    row = registry["sha256:main-skeleton"]
    assert row["packaging_preflight_status"] == "NO_LEGAL_SLOT"
    assert row["tail_admissible"] is False
    assert row["tail_search_started"] is False
    assert stats.main_skeleton_truck_preflight_rows is None


def test_raw_bank_options_interleave_attachment_faces_deterministically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        placement,
        "_adjacent_side",
        lambda _primary, option: option.side,
    )
    primary = object()
    west_first = SimpleNamespace(side="WEST", identity="west-1")
    west_second = SimpleNamespace(side="WEST", identity="west-2")
    east_first = SimpleNamespace(side="EAST", identity="east-1")

    options = placement._interleave_raw_bank_options(
        primary, (west_first, west_second, east_first), ("WEST", "EAST")
    )

    assert tuple(option.identity for option in options) == ("west-1", "east-1", "west-2")


def test_shipping_candidates_preserve_established_edge_order_before_dock_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(placement, "_dimension_variants", lambda *_args: ((6500, 7693, 0),))
    monkeypatch.setattr(
        placement,
        "_edge_anchors",
        lambda *_args: ((0, 33700), (1624, 33700)),
    )
    monkeypatch.setattr(placement, "_adjacent_side", lambda *_args: "EAST")
    monkeypatch.setattr(placement, "_must_neighbors", lambda *_args: ())
    monkeypatch.setattr(placement, "_geometry_rejection_reason", lambda *_args: None)
    monkeypatch.setattr(
        placement,
        "_rectangle_from_mm",
        lambda code, x, y, width, depth, rotation: SimpleNamespace(
            zone_code=code,
            bounds_mm=(x, y, x + width, y + depth),
            x=x,
            y=y,
            width_m=width / 1000,
            depth_m=depth / 1000,
            rotation_deg=rotation,
        ),
    )
    monkeypatch.setattr(
        placement,
        "_truck_segment",
        lambda _site: ((0, 33700), (0, 33701)),
    )
    context = SimpleNamespace(
        authorities={"shipping_channel": {"zone_code": "shipping_channel"}},
        boundary=(),
        graph=object(),
        structural_topology=placement.STRAIGHT_LINEAR_BAND,
        search_phase=placement.STRUCTURED_PHASE,
        site_body={},
    )

    options = placement._constructive_edge_options(
        context,
        "shipping_channel",
        {"finished_goods_room": object()},
        "finished_goods_room",
        prefer_truck_entrance=True,
        stats=placement._PlacementSearchStats(),
    )

    assert len(options) == 2
    assert options[0].bounds_mm[:2] == (0, 33700)


def test_exact_shipping_distance_order_uses_orthogonal_integer_geometry() -> None:
    near_vertical = SimpleNamespace(bounds_mm=(1624, 33700, 9317, 40200))
    far_vertical = SimpleNamespace(bounds_mm=(6100, 39153, 12600, 46846))
    near_horizontal = SimpleNamespace(bounds_mm=(2000, 34700, 9317, 41200))

    assert (
        placement._rectangle_distance_squared_to_entrance(near_vertical, ((0, 33700), (0, 33701)))
        == 1624**2
    )
    assert (
        placement._rectangle_distance_squared_to_entrance(far_vertical, ((0, 33700), (0, 33701)))
        == 6100**2 + (39153 - 33701) ** 2
    )
    assert (
        placement._rectangle_distance_squared_to_entrance(
            near_horizontal, ((0, 33700), (1624, 33700))
        )
        == 376**2 + 1000**2
    )


def test_shipping_order_wrapper_preserves_existing_candidate_order() -> None:
    passing_orientation = PlacedRectangleV1(
        "shipping_channel", Decimal("1.624"), Decimal("33.7"), Decimal("6.5"), Decimal("7.693"), 90
    )
    alternative_orientation = PlacedRectangleV1(
        "shipping_channel", Decimal("0.8"), Decimal("33.7"), Decimal("6.5"), Decimal("7.693"), 0
    )
    context = SimpleNamespace(
        site_body={
            "site": {"preferred_loading_side": "NEAREST_TRUCK_ENTRANCE"},
            "entrances": {
                "truck_entrance": {
                    "start": {"x": "0", "y": "33.7"},
                    "end": {"x": "0", "y": "33.701"},
                }
            },
        }
    )

    assert placement._shipping_loading_face_approach_axis_penalty(context, passing_orientation) == 0
    assert (
        placement._shipping_loading_face_approach_axis_penalty(context, alternative_orientation)
        == 1
    )
    assert placement._shipping_options_by_loading_face_approach(
        context, (alternative_orientation, passing_orientation)
    ) == (alternative_orientation, passing_orientation)


def test_finished_room_wrapper_preserves_established_candidate_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aligned_finished = PlacedRectangleV1(
        "finished_goods_room", Decimal("9.317"), Decimal("33.7"), Decimal("32.4"), Decimal("18.6")
    )
    later_finished = PlacedRectangleV1(
        "finished_goods_room", Decimal("9.317"), Decimal("39.75"), Decimal("32.4"), Decimal("18.6")
    )
    passing_shipping = PlacedRectangleV1(
        "shipping_channel", Decimal("1.624"), Decimal("33.7"), Decimal("6.5"), Decimal("7.693"), 90
    )
    rejected_shipping = PlacedRectangleV1(
        "shipping_channel", Decimal("0.8"), Decimal("39.75"), Decimal("6.5"), Decimal("7.693"), 0
    )
    monkeypatch.setattr(
        placement,
        "_constructive_edge_options",
        lambda _context, _code, placed, _neighbor, **_kwargs: (
            (passing_shipping,)
            if placed["finished_goods_room"].y == Decimal("33.7")
            else (rejected_shipping,)
        ),
    )
    context = SimpleNamespace(
        site_body={
            "site": {"preferred_loading_side": "NEAREST_TRUCK_ENTRANCE"},
            "entrances": {
                "truck_entrance": {
                    "start": {"x": "0", "y": "33.7"},
                    "end": {"x": "0", "y": "33.701"},
                }
            },
        }
    )

    assert placement._finished_options_by_shipping_approach(
        context,
        {},
        (later_finished, aligned_finished),
    ) == (later_finished, aligned_finished)


def test_finished_room_interleaves_one_dock_paired_branch_deterministically() -> None:
    established = PlacedRectangleV1(
        "finished_goods_room", Decimal("9"), Decimal("33"), Decimal("32"), Decimal("18"), 0
    )
    dock_paired = PlacedRectangleV1(
        "finished_goods_room", Decimal("7"), Decimal("33"), Decimal("32"), Decimal("18"), 0
    )
    later_established = PlacedRectangleV1(
        "finished_goods_room", Decimal("5"), Decimal("33"), Decimal("32"), Decimal("18"), 0
    )
    later_dock_paired = PlacedRectangleV1(
        "finished_goods_room", Decimal("3"), Decimal("33"), Decimal("32"), Decimal("18"), 0
    )
    options = (established, later_established, dock_paired, later_dock_paired)

    result = placement._interleave_finished_truck_interface_options(
        options, {dock_paired.bounds_mm, later_dock_paired.bounds_mm}
    )

    assert result == (established, dock_paired, later_established, later_dock_paired)


def _dock_template_binding() -> SimpleNamespace:
    template = SimpleNamespace(
        maneuver_class="DOCK_REVERSE",
        reference_frame={"entry_pose": {"x": "0", "y": "0", "rotation_deg": 0}},
        final_dock_pose={"x": "1.624", "y": "0", "rotation_deg": 180},
    )
    project = SimpleNamespace(template_set=SimpleNamespace(templates=(template,)))
    return SimpleNamespace(maneuver_project_input=project)


def test_authoritative_dock_template_and_entrance_generate_exact_dock_events() -> None:
    context = SimpleNamespace(
        truck_maneuver_binding=_dock_template_binding(),
        site_body={
            "entrances": {
                "truck_entrance": {
                    "start": {"x": "0", "y": "33.7"},
                    "end": {"x": "0", "y": "33.701"},
                }
            }
        },
    )

    assert (1624, 33700) in placement._truck_dock_points_at_entrance(context)
    assert placement._truck_dock_points_at_entrance(context) == tuple(
        sorted(set(placement._truck_dock_points_at_entrance(context)))
    )


def test_dock_event_generates_shipping_candidate_with_loading_face_at_dock_point(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        placement,
        "_dimension_variants",
        lambda *_args: ((6500, 7693, 90),),
    )
    boundary = ((0, 0), (100000, 0), (100000, 100000), (0, 100000))
    context = SimpleNamespace(
        truck_maneuver_binding=_dock_template_binding(),
        authorities={"shipping_channel": {"zone_code": "shipping_channel"}},
        boundary=boundary,
        boundary_bounds=(0, 0, 100000, 100000),
        obstacles=(),
        site_body={
            "site": {"preferred_loading_side": "UNSPECIFIED"},
            "entrances": {
                "truck_entrance": {
                    "start": {"x": "0", "y": "33.7"},
                    "end": {"x": "0", "y": "33.701"},
                }
            },
        },
    )

    candidates = placement._shipping_rectangles_for_dock_events(context)
    expected = PlacedRectangleV1(
        "shipping_channel", Decimal("1.624"), Decimal("33.7"), Decimal("6.5"), Decimal("7.693"), 90
    )
    boundary_aligned_loading_face = PlacedRectangleV1(
        "shipping_channel",
        Decimal("0"),
        Decimal("33.7"),
        Decimal("6.5"),
        Decimal("7.693"),
        90,
    )
    assert expected in candidates
    assert boundary_aligned_loading_face in candidates
    _, face, _, _ = placement._loading_face(boundary_aligned_loading_face, context.site_body)
    assert placement._on_segment((1624, 33700), face[0], face[1])


def test_loading_face_endpoint_dock_event_does_not_displace_established_branch_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint_dock = PlacedRectangleV1(
        "shipping_channel", Decimal("1.624"), Decimal("33.7"), Decimal("6.5"), Decimal("7.693"), 90
    )
    interior_dock = PlacedRectangleV1(
        "shipping_channel", Decimal("0.431"), Decimal("33.7"), Decimal("6.5"), Decimal("7.693"), 90
    )
    monkeypatch.setattr(
        placement, "_truck_dock_points_at_entrance", lambda _context: ((1624, 33700),)
    )
    context = SimpleNamespace(
        site_body={
            "site": {"preferred_loading_side": "NEAREST_TRUCK_ENTRANCE"},
            "entrances": {
                "truck_entrance": {
                    "start": {"x": "0", "y": "33.7"},
                    "end": {"x": "0", "y": "33.701"},
                }
            },
        }
    )

    assert placement._loading_face_dock_endpoint_penalty(context, endpoint_dock) == 0
    assert placement._loading_face_dock_endpoint_penalty(context, interior_dock) == 1
    assert placement._shipping_options_by_loading_face_approach(
        context, (interior_dock, endpoint_dock)
    ) == (interior_dock, endpoint_dock)


def test_rejected_shipping_seed_is_not_yielded_and_later_candidate_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    family = StructuralCompositionFamilyV1(
        family=LINEAR_PROCESS_BAND,
        dominant_axis="Y",
        dominant_direction="POSITIVE",
        generation_reason="R15_SEED_CONTROL_FLOW_REGRESSION",
    )
    zone_codes = (
        "raw_fruit_buffer",
        "primary_precooling_room",
        "sorting_packaging_room",
        "secondary_precooling_room",
        "coating_room",
        "finished_goods_room",
        "shipping_channel",
    )
    rectangles = {
        code: PlacedRectangleV1(
            code,
            Decimal(index * 10),
            Decimal("20"),
            Decimal("4"),
            Decimal("3"),
            0,
        )
        for index, code in enumerate(zone_codes, start=1)
    }
    invalid_shipping = PlacedRectangleV1(
        "shipping_channel", Decimal("70"), Decimal("1"), Decimal("4"), Decimal("3"), 0
    )
    options_by_zone = {code: (row,) for code, row in rectangles.items()}
    options_by_zone["shipping_channel"] = (rectangles["shipping_channel"], invalid_shipping)
    monkeypatch.setattr(
        placement,
        "_constructive_edge_options",
        lambda _context, zone_code, *_args, **_kwargs: options_by_zone[zone_code],
    )
    monkeypatch.setattr(placement, "_adjacent_side", lambda *_args: "WEST")
    monkeypatch.setattr(placement, "_finished_options_by_shipping_approach", lambda _c, _p, xs: xs)
    monkeypatch.setattr(placement, "_shipping_options_by_loading_face_approach", lambda _c, xs: xs)
    monkeypatch.setattr(placement, "_main_group_order_monotonic", lambda *_args: True)
    monkeypatch.setattr(placement, "_topology_geometry_valid", lambda *_args: True)
    monkeypatch.setattr(
        placement, "_constructive_main_skeleton_tail_admission", lambda *_args: True
    )
    monkeypatch.setattr(
        placement,
        "_packaging_tail_slot_preflight",
        lambda *_args: {
            "proof_mode": placement.EXACT_ORTHOGONAL_EVENT_ENUMERATION,
            "legal_slot_exists": True,
        },
    )
    monkeypatch.setattr(
        placement,
        "_main_skeleton_truck_maneuver_preflight",
        lambda *_args: _truck_row("PASS"),
    )

    def replay() -> tuple[str, ...]:
        classification_rows = iter(
            (
                SimpleNamespace(
                    canonical_owner=None,
                    matched_topologies=(),
                    process_axis=None,
                    process_direction=None,
                ),
                SimpleNamespace(
                    canonical_owner=placement.STRAIGHT_LINEAR_BAND,
                    matched_topologies=(placement.STRAIGHT_LINEAR_BAND,),
                    process_axis="Y",
                    process_direction="POSITIVE",
                ),
            )
        )
        monkeypatch.setattr(
            placement,
            "classify_main_process_topology_v1",
            lambda _placed: next(classification_rows),
        )
        context = SimpleNamespace(
            node_budget=120,
            structural_topology=placement.STRAIGHT_LINEAR_BAND,
            structural_composition_family=family,
            structural_skeleton=SimpleNamespace(ordering_axis="Y", family=family),
            site_body={},
            global_main_process_geometry_registry={},
            global_cross_topology_duplicate_trace=[],
        )
        output = list(
            placement._construct_face_skeletons(
                context,
                placement._PlacementSearchStats(),
                rectangles["sorting_packaging_room"],
                "WEST",
                "EAST",
                skeleton_node_limit=120,
                skeleton_limit=4,
            )
        )
        return tuple(
            item.main_process_skeleton_hash
            for item in output
            if isinstance(item, placement.MainProcessSkeletonCandidateV1)
        )

    first = replay()
    second = replay()
    assert len(first) == 1
    assert first == second
