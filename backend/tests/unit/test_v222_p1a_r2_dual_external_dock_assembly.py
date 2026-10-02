"""Contracts for exact dock-anchored structured site assembly."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from cold_storage.modules.layout.domain import placement
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1


def _dock_anchor(
    x_mm: int,
    *,
    dock_x_mm: int | None = None,
) -> placement.ShippingDockAnchorV1:
    rectangle = PlacedRectangleV1(
        "shipping_channel",
        Decimal(x_mm) / 1000,
        Decimal("0"),
        Decimal("10"),
        Decimal("10"),
    )
    face = ((x_mm, 0), (x_mm + 10_000, 0))
    return placement.ShippingDockAnchorV1(
        dock_point_mm=(dock_x_mm if dock_x_mm is not None else x_mm + 1_624, 0),
        shipping_rectangle=rectangle,
        loading_face_side="BOTTOM_LONG_EDGE",
        loading_face_segment_mm=face,
        shipping_rotation_deg=0,
        source_entry_point_mm=(0, 0),
        source_template_identity="template:DOCK_REVERSE",
        source_template_rotation_deg=0,
    )


def test_rotated_fixed_zone_keeps_authoritative_width_and_depth() -> None:
    authority = {
        "zone_code": "finished_goods_room",
        "dimension_mode": "FIXED_RECTANGLE",
        "required_area_m2": "566.64",
        "geometry": {
            "width_m": "30.4",
            "depth_m": "18.64",
            "required_area_m2": "566.656",
        },
    }
    context = SimpleNamespace(authorities={"finished_goods_room": authority})

    shapes = placement._local_dimension_shapes(context, "finished_goods_room")
    rotated_shape = next(shape for shape in shapes if shape[2] == 90)
    rectangle = placement._local_rectangle_at("finished_goods_room", rotated_shape, 0, 0)
    record = placement._zone_record(authority, rectangle)

    assert rotated_shape == (30_400, 18_640, 90, 18_640, 30_400)
    assert record["width_m"] == Decimal("30.4")
    assert record["depth_m"] == Decimal("18.64")
    assert rectangle.bounds_mm == (0, 0, 18_640, 30_400)


def test_shipping_dock_anchor_reuses_template_event_and_loading_face(
    monkeypatch,
) -> None:
    shipping = PlacedRectangleV1(
        "shipping_channel",
        Decimal("1.624"),
        Decimal("33.7"),
        Decimal("6.5"),
        Decimal("7.693"),
        90,
    )
    face = ((1_624, 33_700), (9_317, 33_700))
    event = {
        "dock_point_mm": (1_624, 33_700),
        "source_entry_point_mm": (0, 33_700),
        "source_template_identity": "bound:DOCK_REVERSE",
        "source_template_rotation_deg": 180,
    }
    monkeypatch.setattr(placement, "_truck_dock_events_at_entrance", lambda _ctx: (event,))
    monkeypatch.setattr(placement, "_shipping_rectangles_for_dock_events", lambda _ctx: (shipping,))
    monkeypatch.setattr(
        placement,
        "_loading_face",
        lambda _rect, _site: ("BOTTOM_LONG_EDGE", face, {}, ()),
    )
    context = SimpleNamespace(site_body={})

    rows = placement._shipping_dock_anchors_at_entrance(context)

    assert len(rows) == 1
    assert rows[0].dock_point_mm == (1_624, 33_700)
    assert rows[0].source_template_identity == "bound:DOCK_REVERSE"
    assert rows[0].source_template_rotation_deg == 180
    assert placement._on_segment(rows[0].dock_point_mm, *rows[0].loading_face_segment_mm)


def test_dock_backsolve_translates_the_frozen_finished_module_as_one_rigid_unit() -> None:
    module = {
        "secondary_precooling_room": PlacedRectangleV1(
            "secondary_precooling_room", Decimal("0"), Decimal("0"), Decimal("10"), Decimal("10")
        ),
        "coating_room": PlacedRectangleV1(
            "coating_room", Decimal("10"), Decimal("0"), Decimal("10"), Decimal("10")
        ),
        "finished_goods_room": PlacedRectangleV1(
            "finished_goods_room", Decimal("20"), Decimal("0"), Decimal("10"), Decimal("10")
        ),
        "shipping_channel": PlacedRectangleV1(
            "shipping_channel", Decimal("30"), Decimal("0"), Decimal("10"), Decimal("10")
        ),
    }
    anchor = _dock_anchor(100_000)

    translated = placement._dock_backsolved_finished_module(module, anchor)

    assert translated is not None
    assert translated["shipping_channel"].bounds_mm == anchor.shipping_rectangle.bounds_mm
    assert all(
        translated[code].bounds_mm[:2][0] - module[code].bounds_mm[:2][0] == 70_000
        for code in module
    )
    assert placement.rectangles_share_positive_edge(
        translated["secondary_precooling_room"], translated["coating_room"]
    )
    assert placement.rectangles_share_positive_edge(
        translated["coating_room"], translated["finished_goods_room"]
    )


def test_dock_backsolved_chain_is_synthesized_from_shipping_to_sorting() -> None:
    codes = (
        "secondary_precooling_room",
        "coating_room",
        "finished_goods_room",
    )
    context = SimpleNamespace(
        authorities={
            code: {
                "zone_code": code,
                "dimension_mode": "FIXED_RECTANGLE",
                "required_area_m2": 100,
                "geometry": {"width_m": 10, "depth_m": 10, "required_area_m2": 100},
            }
            for code in codes
        },
        boundary=((0, 0), (100_000, 0), (100_000, 100_000), (0, 100_000)),
        boundary_bounds=(0, 0, 100_000, 100_000),
        obstacles=(),
    )
    sorting = PlacedRectangleV1(
        "sorting_packaging_room", Decimal("20"), Decimal("0"), Decimal("10"), Decimal("10")
    )
    dock = _dock_anchor(60_000)

    chains = placement._dock_backsolved_finished_chains(
        context,
        dock,
        sorting,
        {},
        placement.LINEAR_3_BAND,
        "X",
        "POSITIVE",
    )

    assert chains
    assert all(
        chain["shipping_channel"].bounds_mm == dock.shipping_rectangle.bounds_mm
        if "shipping_channel" in chain
        else True
        for chain in chains
    )
    for chain in chains:
        assert placement.rectangles_share_positive_edge(
            chain["finished_goods_room"], dock.shipping_rectangle
        )
        assert placement.rectangles_share_positive_edge(
            chain["coating_room"], chain["finished_goods_room"]
        )
        assert placement.rectangles_share_positive_edge(
            chain["secondary_precooling_room"], chain["coating_room"]
        )
        assert placement._adjacent_side(sorting, chain["secondary_precooling_room"]) is not None


def test_dock_anchor_representatives_preserve_each_distinct_dock_event() -> None:
    anchors = tuple(
        placement.ShippingDockAnchorV1(
            dock_point_mm=(1_624, 33_700 + index),
            shipping_rectangle=PlacedRectangleV1(
                "shipping_channel",
                Decimal("1.624"),
                Decimal(33_700 + index) / 1000,
                Decimal("6.5"),
                Decimal("7.693"),
                90,
            ),
            loading_face_side="BOTTOM_LONG_EDGE",
            loading_face_segment_mm=((1_624, 33_700 + index), (9_317, 33_700 + index)),
            shipping_rotation_deg=90,
            source_entry_point_mm=(0, 33_700 + index),
            source_template_identity="bound:DOCK_REVERSE",
            source_template_rotation_deg=0,
        )
        for index in range(8)
    )

    representatives = placement._shipping_dock_anchor_construction_representatives(
        anchors, limit=12
    )

    assert placement._shipping_dock_anchor_construction_limit(anchors) == len(anchors)
    assert {row.dock_point_mm for row in representatives} == {row.dock_point_mm for row in anchors}
    assert (1_624, 33_700) in {row.dock_point_mm for row in representatives}


def test_dock_anchor_representatives_preserve_distinct_shipping_geometry_at_same_dock_point() -> (
    None
):
    dock_point = (1_624, 33_700)
    entry_point = (0, 33_700)
    control_face = ((1_624, 33_700), (9_317, 33_700))
    boundary_face = ((0, 33_700), (7_693, 33_700))
    control_geometry = placement.ShippingDockAnchorV1(
        dock_point_mm=dock_point,
        shipping_rectangle=PlacedRectangleV1(
            "shipping_channel",
            Decimal("1.624"),
            Decimal("33.7"),
            Decimal("6.5"),
            Decimal("7.693"),
            90,
        ),
        loading_face_side="BOTTOM_LONG_EDGE",
        loading_face_segment_mm=control_face,
        shipping_rotation_deg=90,
        source_entry_point_mm=entry_point,
        source_template_identity="bound:DOCK_REVERSE",
        source_template_rotation_deg=0,
    )
    boundary_geometry = placement.ShippingDockAnchorV1(
        dock_point_mm=dock_point,
        shipping_rectangle=PlacedRectangleV1(
            "shipping_channel",
            Decimal("0"),
            Decimal("33.7"),
            Decimal("6.5"),
            Decimal("7.693"),
            90,
        ),
        loading_face_side="BOTTOM_LONG_EDGE",
        loading_face_segment_mm=boundary_face,
        shipping_rotation_deg=90,
        source_entry_point_mm=entry_point,
        source_template_identity="bound:DOCK_REVERSE",
        source_template_rotation_deg=0,
    )

    representatives = placement._shipping_dock_anchor_construction_representatives(
        (boundary_geometry, control_geometry), limit=2
    )

    assert {row.shipping_rectangle.bounds_mm for row in representatives} == {
        boundary_geometry.shipping_rectangle.bounds_mm,
        control_geometry.shipping_rectangle.bounds_mm,
    }
    assert (
        representatives[0].shipping_rectangle.bounds_mm
        == control_geometry.shipping_rectangle.bounds_mm
    )


def test_dock_anchor_order_prefers_approach_normal_to_authoritative_entrance() -> None:
    horizontal = placement.ShippingDockAnchorV1(
        dock_point_mm=(1_624, 33_700),
        shipping_rectangle=PlacedRectangleV1(
            "shipping_channel",
            Decimal("1.624"),
            Decimal("33.7"),
            Decimal("6.5"),
            Decimal("7.693"),
            90,
        ),
        loading_face_side="BOTTOM_LONG_EDGE",
        loading_face_segment_mm=((1_624, 33_700), (9_317, 33_700)),
        shipping_rotation_deg=90,
        source_entry_point_mm=(0, 33_700),
        source_template_identity="bound:DOCK_REVERSE",
        source_template_rotation_deg=0,
    )
    vertical = placement.ShippingDockAnchorV1(
        dock_point_mm=(10_000, 35_324),
        shipping_rectangle=PlacedRectangleV1(
            "shipping_channel",
            Decimal("10"),
            Decimal("27.631"),
            Decimal("6.5"),
            Decimal("7.693"),
            0,
        ),
        loading_face_side="LEFT_LONG_EDGE",
        loading_face_segment_mm=((10_000, 27_631), (10_000, 35_324)),
        shipping_rotation_deg=0,
        source_entry_point_mm=(10_000, 33_700),
        source_template_identity="bound:DOCK_REVERSE",
        source_template_rotation_deg=270,
    )

    representatives = placement._shipping_dock_anchor_construction_representatives(
        (vertical, horizontal),
        limit=2,
        truck_entrance_segment=((0, 32_000), (0, 35_000)),
    )

    assert (
        representatives[0].shipping_rectangle.bounds_mm == horizontal.shipping_rectangle.bounds_mm
    )


def test_dock_anchor_order_does_not_prefer_face_parallelism_over_geometry_coverage() -> None:
    entrance = ((0, 33_700), (0, 33_701))
    prior_feasible_geometry = placement.ShippingDockAnchorV1(
        dock_point_mm=(1_624, 33_700),
        shipping_rectangle=PlacedRectangleV1(
            "shipping_channel",
            Decimal("1.624"),
            Decimal("26.007"),
            Decimal("6.5"),
            Decimal("7.693"),
            0,
        ),
        loading_face_side="LEFT_LONG_EDGE",
        loading_face_segment_mm=((1_624, 26_007), (1_624, 33_700)),
        shipping_rotation_deg=0,
        source_entry_point_mm=(0, 33_700),
        source_template_identity="bound:DOCK_REVERSE",
        source_template_rotation_deg=0,
    )
    parallel_face_geometry = placement.ShippingDockAnchorV1(
        dock_point_mm=(1_624, 33_700),
        shipping_rectangle=PlacedRectangleV1(
            "shipping_channel",
            Decimal("1.624"),
            Decimal("33.7"),
            Decimal("6.5"),
            Decimal("7.693"),
            90,
        ),
        loading_face_side="BOTTOM_LONG_EDGE",
        loading_face_segment_mm=((1_624, 33_700), (9_317, 33_700)),
        shipping_rotation_deg=90,
        source_entry_point_mm=(0, 33_700),
        source_template_identity="bound:DOCK_REVERSE",
        source_template_rotation_deg=0,
    )

    representatives = placement._shipping_dock_anchor_construction_representatives(
        (parallel_face_geometry, prior_feasible_geometry),
        limit=2,
        truck_entrance_segment=entrance,
    )

    assert representatives[0].shipping_rectangle.bounds_mm == (
        prior_feasible_geometry.shipping_rectangle.bounds_mm
    )


def test_both_external_anchors_change_the_sorting_root_candidate_set(monkeypatch) -> None:
    package = placement.PackagingAnchorV1(
        "package-A",
        "BAY-A",
        PlacedRectangleV1(
            "packaging_material_storage", Decimal("0"), Decimal("0"), Decimal("10"), Decimal("10")
        ),
    )
    roots = (
        (
            PlacedRectangleV1(
                "sorting_packaging_room", Decimal("10"), Decimal("0"), Decimal("10"), Decimal("10")
            ),
            "WEST",
            None,
            {},
        ),
        (
            PlacedRectangleV1(
                "sorting_packaging_room", Decimal("20"), Decimal("0"), Decimal("10"), Decimal("10")
            ),
            "WEST",
            None,
            {},
        ),
    )
    monkeypatch.setattr(placement, "_packaging_driven_sorting_roots", lambda *_a, **_kw: roots)

    def usable(_context, module, fixed):
        combined = [*module.values(), *fixed.values()]
        return all(
            not placement.rectangles_overlap(first, second)
            for index, first in enumerate(combined)
            for second in combined[index + 1 :]
        )

    monkeypatch.setattr(placement, "_site_module_is_usable", usable)
    first_dock = _dock_anchor(30_000)
    second_dock = _dock_anchor(20_000)
    context = SimpleNamespace()

    first_roots = placement._dual_interface_sorting_roots(
        context, package, first_dock, (), stats=None
    )
    second_roots = placement._dual_interface_sorting_roots(
        context, package, second_dock, (), stats=None
    )
    moved_package = placement.PackagingAnchorV1(
        "package-B",
        "BAY-A",
        PlacedRectangleV1(
            "packaging_material_storage", Decimal("10"), Decimal("0"), Decimal("10"), Decimal("10")
        ),
    )
    package_roots = placement._dual_interface_sorting_roots(
        context, moved_package, first_dock, (), stats=None
    )

    assert tuple(row[0].bounds_mm for row in first_roots) != tuple(
        row[0].bounds_mm for row in second_roots
    )
    assert tuple(row[0].bounds_mm for row in first_roots) != tuple(
        row[0].bounds_mm for row in package_roots
    )


def test_dock_backsolved_secondary_generates_joint_package_dock_sorting_roots(monkeypatch) -> None:
    package = placement.PackagingAnchorV1(
        "package-A",
        "BAY-A",
        PlacedRectangleV1(
            "packaging_material_storage", Decimal("0"), Decimal("0"), Decimal("10"), Decimal("10")
        ),
    )
    package_roots = tuple(
        (
            PlacedRectangleV1(
                "sorting_packaging_room",
                Decimal(x_mm) / 1000,
                Decimal("0"),
                Decimal("10"),
                Decimal("10"),
            ),
            "WEST",
            None,
            {"packaging_witness": True},
        )
        for x_mm in (10_000, 20_000, 40_000)
    )
    monkeypatch.setattr(
        placement,
        "_local_dimension_shapes",
        lambda _context, _zone: ((10_000, 10_000, 0, 10_000, 10_000),),
    )
    monkeypatch.setattr(placement, "_family_core_face_pairs", lambda *_args: (("WEST", "EAST"),))

    def usable(_context, module, fixed):
        combined = [*module.values(), *fixed.values()]
        return all(
            not placement.rectangles_overlap(first, second)
            for index, first in enumerate(combined)
            for second in combined[index + 1 :]
        )

    monkeypatch.setattr(placement, "_site_module_is_usable", usable)

    roots_by_shipping_origin = {}
    for shipping_x_mm in (30_000, 40_000):
        dock_anchor = _dock_anchor(shipping_x_mm)
        secondary_x_mm = shipping_x_mm - 10_000
        finished_module = {
            "secondary_precooling_room": PlacedRectangleV1(
                "secondary_precooling_room",
                Decimal(secondary_x_mm) / 1000,
                Decimal("0"),
                Decimal("10"),
                Decimal("10"),
            ),
            "shipping_channel": dock_anchor.shipping_rectangle,
        }
        roots = placement._dual_interface_sorting_roots(
            SimpleNamespace(),
            package,
            dock_anchor,
            (),
            packaging_roots=package_roots,
            dock_finished_module=finished_module,
            layout_family=placement.LINEAR_3_BAND,
        )
        roots_by_shipping_origin[shipping_x_mm] = tuple(row[0].bounds_mm for row in roots)

    assert roots_by_shipping_origin[30_000] == ((10_000, 0, 20_000, 10_000),)
    assert roots_by_shipping_origin[40_000] == ((20_000, 0, 30_000, 10_000),)


def test_joint_dock_pair_fairly_covers_external_pairs_before_second_root(monkeypatch) -> None:
    package = placement.PackagingAnchorV1(
        "package-A",
        "BAY-A",
        PlacedRectangleV1(
            "packaging_material_storage", Decimal("0"), Decimal("0"), Decimal("10"), Decimal("10")
        ),
    )
    docks = (_dock_anchor(80_000), _dock_anchor(90_000))
    roots_by_dock = {
        80_000: tuple(
            (
                PlacedRectangleV1(
                    "sorting_packaging_room",
                    Decimal(x_mm) / 1000,
                    Decimal("0"),
                    Decimal("10"),
                    Decimal("10"),
                ),
                "WEST",
                None,
                {"alignment": alignment},
            )
            for x_mm, alignment in ((20_000, "LOW"), (40_000, "HIGH"))
        ),
        90_000: tuple(
            (
                PlacedRectangleV1(
                    "sorting_packaging_room",
                    Decimal(x_mm) / 1000,
                    Decimal("0"),
                    Decimal("10"),
                    Decimal("10"),
                ),
                "WEST",
                None,
                {"alignment": alignment},
            )
            for x_mm, alignment in ((60_000, "CENTER"), (70_000, "HIGH"))
        ),
    }
    raw_module = {
        "primary_precooling_room": PlacedRectangleV1(
            "primary_precooling_room", Decimal("0"), Decimal("0"), Decimal("10"), Decimal("10")
        ),
        "raw_fruit_buffer": PlacedRectangleV1(
            "raw_fruit_buffer", Decimal("-10"), Decimal("0"), Decimal("10"), Decimal("10")
        ),
    }
    finished_module = {
        "finished_goods_room": PlacedRectangleV1(
            "finished_goods_room", Decimal("0"), Decimal("0"), Decimal("10"), Decimal("10")
        )
    }
    bays = (placement.BuildableBayV1("BAY-A", (0, 0, 100_000, 100_000), 10_000_000_000),)

    monkeypatch.setattr(placement, "_enumerate_packaging_site_anchors", lambda *_args: (package,))
    monkeypatch.setattr(
        placement,
        "_packaging_anchor_construction_representatives",
        lambda _context, _anchors, _bays, **_kwargs: (package,),
    )
    monkeypatch.setattr(placement, "_shipping_dock_anchors_at_entrance", lambda _context: docks)
    monkeypatch.setattr(
        placement,
        "_shipping_dock_anchor_construction_representatives",
        lambda anchors, **_kwargs: tuple(anchors),
    )
    monkeypatch.setattr(placement, "_packaging_driven_sorting_roots", lambda *_args, **_kwargs: ())
    monkeypatch.setattr(
        placement,
        "_dual_interface_sorting_roots",
        lambda _context, _package, dock_anchor, *_args, **_kwargs: roots_by_dock[
            dock_anchor.shipping_rectangle.bounds_mm[0]
        ],
    )
    monkeypatch.setattr(placement, "_site_assembly_module_variants", lambda module: (dict(module),))
    monkeypatch.setattr(
        placement,
        "_dock_backsolved_finished_chains",
        lambda _context, _dock, root, *_args, **_kwargs: (
            {
                "secondary_precooling_room": PlacedRectangleV1(
                    "secondary_precooling_room",
                    root.x + Decimal("10"),
                    root.y,
                    Decimal("10"),
                    Decimal("10"),
                ),
                "coating_room": PlacedRectangleV1(
                    "coating_room",
                    root.x + Decimal("20"),
                    root.y,
                    Decimal("10"),
                    Decimal("10"),
                ),
                "finished_goods_room": PlacedRectangleV1(
                    "finished_goods_room",
                    root.x + Decimal("30"),
                    root.y,
                    Decimal("10"),
                    Decimal("10"),
                ),
            },
        ),
    )
    monkeypatch.setattr(placement, "_site_module_is_usable", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(placement, "_family_core_face_pairs", lambda *_args: (("WEST", "EAST"),))
    monkeypatch.setattr(placement, "_adjacent_side", lambda *_args: "EAST")
    monkeypatch.setattr(
        placement,
        "_module_attached_to_zone",
        lambda module, _interface, target, _side, _alignment: placement._translate_module(
            module,
            target.bounds_mm[0] - module["primary_precooling_room"].bounds_mm[0] - 10_000,
            target.bounds_mm[1] - module["primary_precooling_room"].bounds_mm[1],
        ),
    )
    monkeypatch.setattr(placement, "_validate_main_process_skeleton_graph", lambda *_args: None)
    monkeypatch.setattr(
        placement,
        "_canonical_site_main_skeleton",
        lambda _context, main, **_kwargs: SimpleNamespace(
            main_process_skeleton_hash=f"root-{main['sorting_packaging_room'].bounds_mm[0]}"
        ),
    )
    preflight_order: list[str] = []
    context = SimpleNamespace(
        graph=object(),
        node_budget=10,
        structural_topology="OFFSET_LINEAR_BAND",
        global_main_process_geometry_registry={},
    )

    def preflight(ctx, _stats, seed, *, run_truck_preflight):
        assert run_truck_preflight is True
        preflight_order.append(seed.main_process_skeleton_hash)
        status = "REJECT" if seed.main_process_skeleton_hash == "root-20000" else "PASS"
        ctx.global_main_process_geometry_registry[seed.main_process_skeleton_hash] = {
            "main_skeleton_truck_preflight": {
                "preflight_status": status,
                "failure_codes": ["TRUCK_MANEUVER_SEARCH_EXHAUSTED"] if status == "REJECT" else [],
            }
        }
        return status == "PASS"

    monkeypatch.setattr(placement, "_constructive_main_skeleton_tail_admission", preflight)
    monkeypatch.setattr(placement, "_truck_dock_events_at_entrance", lambda _ctx: ())
    stats = placement._PlacementSearchStats(
        visited_nodes=1,
        site_module_variant_counts={},
        site_packaging_anchors=(package,),
        site_packaging_construction_anchors=(package,),
        site_shipping_dock_anchors=docks,
        site_shipping_dock_construction_anchors=docks,
        site_packaging_sorting_roots_by_anchor={},
    )

    candidates = tuple(
        placement._module_main_site_assemblies_dock_backsolved(
            context,
            (),
            placement.LINEAR_3_BAND,
            "X",
            "POSITIVE",
            bays,
            limit=2,
            source_pairs=((raw_module, finished_module),),
            stats=stats,
        )
    )
    admitted_candidates = tuple(candidate for candidate in candidates if candidate is not None)

    assert len(admitted_candidates) == 2
    assert candidates[0] is None
    assert preflight_order == ["root-20000", "root-40000", "root-60000"]
    assert {
        candidate["sorting_packaging_room"].bounds_mm[0] for candidate in admitted_candidates
    } == {
        40_000,
        60_000,
    }
    assert {candidate["shipping_channel"].bounds_mm[0] for candidate in admitted_candidates} == {
        80_000,
        90_000,
    }
