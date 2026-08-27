"""Independent §4 oracles for V0.9 P2 zone formula recut."""

from __future__ import annotations

from math import ceil

import pytest

from cold_storage.modules.calculations.domain.zone_planning import (
    PACKAGING_AREA_FACTOR,
    PACKAGING_POSITION_BASE_AREA_M2,
    SECONDARY_FRUIT_RATIO,
    SECONDARY_FRUIT_STORAGE_DAYS,
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
)

FIXED_SUPPORT_AREA_M2 = 60 + 100 + 120


def _pack_rectangle_oracle(
    n_need: int,
    area_fn,
    *,
    aspect_min: float = 1.67,
    aspect_max: float = 2.40,
) -> dict[str, float | int]:
    if n_need <= 0:
        return {
            "n_need": 0,
            "n_long": 0,
            "n_short": 0,
            "n_actual": 0,
            "unused_cells": 0,
            "required_area_m2": 0.0,
        }
    best: tuple[tuple[int, int, float, float], int, int] | None = None
    for n_long in range(1, n_need + 200):
        for n_short in range(1, n_long + 1):
            n_actual = n_long * n_short
            if n_actual < n_need:
                continue
            ratio = n_long / n_short
            in_band = aspect_min <= ratio <= aspect_max
            unused_cells = n_actual - n_need
            area = area_fn(n_long, n_short)
            rank = (0 if in_band else 1, unused_cells, abs(ratio - 2.0), area)
            if best is None or rank < best[0]:
                best = (rank, n_long, n_short)
    assert best is not None
    _, n_long, n_short = best
    n_actual = n_long * n_short
    return {
        "n_need": n_need,
        "n_long": n_long,
        "n_short": n_short,
        "n_actual": n_actual,
        "unused_cells": n_actual - n_need,
        "required_area_m2": area_fn(n_long, n_short),
    }


def _precool_oracle(
    daily_mass_kg: float,
    *,
    q_d_kg_day: float,
    six_area: float = 52,
    eight_area: float = 68,
) -> dict[str, object]:
    n_need = ceil(daily_mass_kg / q_d_kg_day)
    six_rooms = ceil(n_need / 6)
    eight_rooms = ceil(n_need / 8)
    return {
        "n_need": n_need,
        "six_position": {
            "room_count": six_rooms,
            "position_count": six_rooms * 6,
            "required_area_m2": six_rooms * six_area,
        },
        "eight_position": {
            "room_count": eight_rooms,
            "position_count": eight_rooms * 8,
            "required_area_m2": eight_rooms * eight_area,
        },
    }


def _packaging_position_oracle(
    daily_mass_kg: float,
    *,
    main_days: float,
    aux_days: float,
) -> int:
    main_coefficients = [
        1 / (1.5 * 1600 * 2),
        1 / (125 * 16 * 2),
        1 / (360 * 20),
        1 / (360 * 60),
        0.3 / 12000,
    ]
    auxiliary_coefficients = [
        4 / (360 * 1450),
        3 / (360 * 250 * 2),
        1.6 / (360 * 800),
        0.1 / (10 * 300 * 2),
        2 / (360 * 900),
    ]
    raw_positions = daily_mass_kg * (
        main_days * sum(main_coefficients) + aux_days * sum(auxiliary_coefficients)
    )
    return ceil(raw_positions)


def _shipping_oracle(daily_mass_kg: float) -> dict[str, int | float]:
    pallet_count = ceil(daily_mass_kg / 400)
    truck_count = ceil(pallet_count / 16)
    platform_count = ceil(truck_count / 4)
    return {
        "pallet_count": pallet_count,
        "truck_count": truck_count,
        "platform_count": platform_count,
        "required_area_m2": platform_count * 55,
    }


def _zone_by_code(zones: list[dict[str, object]], zone_code: str) -> dict[str, object]:
    return next(zone for zone in zones if zone["zone_code"] == zone_code)


def _oracle_total_area(
    *,
    primary_six_area: float,
    secondary_six_area: float,
    raw_area: float,
    sorting_area: float,
    finished_area: float,
    secondary_fruit_area: float,
    frozen_area: float,
    packaging_area: float,
    shipping_area: float,
) -> float:
    return round(
        FIXED_SUPPORT_AREA_M2
        + primary_six_area
        + secondary_six_area
        + raw_area
        + sorting_area
        + finished_area
        + secondary_fruit_area
        + frozen_area
        + packaging_area
        + shipping_area,
        2,
    )


@pytest.mark.parametrize(
    ("daily_mass_kg", "finished_storage_days", "frozen_storage_days"),
    [
        (25_000, 2.5, 5),
        (5_000, 2.0, 7),
    ],
)
def test_v09_p2_zone_planning_matches_section4_oracles(
    daily_mass_kg: float,
    finished_storage_days: float,
    frozen_storage_days: float,
) -> None:
    planner = ColdRoomZonePlanner()
    result = planner.plan(
        ColdRoomZonePlanInput(
            daily_inbound_mass_kg=daily_mass_kg,
            working_time_h_per_day=16,
            finished_storage_days=finished_storage_days,
            packaging_storage_days=3,
            precooling_required_ratio=1,
            frozen_storage_days=frozen_storage_days,
        )
    )

    assert result.success is True
    assert result.calculator_version == "1.1.0"
    zones = result.result["zones"]

    primary = _precool_oracle(daily_mass_kg, q_d_kg_day=220 * 6)
    secondary = _precool_oracle(daily_mass_kg, q_d_kg_day=200 * 16)
    raw_need = ceil(daily_mass_kg * 0.40 / 220)
    raw_layout = _pack_rectangle_oracle(
        raw_need,
        lambda n_long, n_short: (n_long * 1.2 + 6) * (n_short * 1.3 + 3),
    )
    worker_count = ceil(daily_mass_kg / (16 * 1.5 * 16))
    table_need = ceil(worker_count / 3)
    sorting_layout = _pack_rectangle_oracle(
        table_need,
        lambda n_long, n_short: (n_long * 5.5 + 8) * (n_short * 3.5 + 8),
    )
    finished_need = ceil(daily_mass_kg * finished_storage_days / 400)
    finished_layout = _pack_rectangle_oracle(
        finished_need,
        lambda n_long, n_short: (n_long * 1.2 + 6) * (n_short * 1.3 + 3),
    )
    secondary_mass = daily_mass_kg * SECONDARY_FRUIT_RATIO * SECONDARY_FRUIT_STORAGE_DAYS
    secondary_need = ceil(secondary_mass / 220)
    secondary_layout = _pack_rectangle_oracle(
        secondary_need,
        lambda n_long, n_short: (n_long * 1.2) * (n_short * 1.3 + 3),
    )
    frozen_mass = daily_mass_kg * 0.10 * frozen_storage_days
    frozen_need = ceil(frozen_mass / 600)
    frozen_layout = _pack_rectangle_oracle(
        frozen_need,
        lambda n_long, n_short: (n_long * 1.2) * (n_short * 1.3 + 3),
    )
    packaging_positions = _packaging_position_oracle(
        daily_mass_kg,
        main_days=3,
        aux_days=30,
    )
    packaging_area = packaging_positions * PACKAGING_POSITION_BASE_AREA_M2 * PACKAGING_AREA_FACTOR
    shipping = _shipping_oracle(daily_mass_kg)

    primary_zone = _zone_by_code(zones, "primary_precooling_room")
    secondary_zone = _zone_by_code(zones, "secondary_precooling_room")
    assert primary_zone["raw_position_count"] == primary["n_need"]
    assert secondary_zone["raw_position_count"] == secondary["n_need"]
    assert primary_zone["reporting_scheme_id"] == "6_position"
    assert primary_zone["position_count"] == primary["six_position"]["position_count"]
    assert primary_zone["required_area_m2"] == pytest.approx(
        primary["six_position"]["required_area_m2"],
        abs=0.01,
    )
    six_scheme = next(
        scheme for scheme in primary_zone["schemes"] if scheme["scheme_id"] == "6_position"
    )
    eight_scheme = next(
        scheme for scheme in primary_zone["schemes"] if scheme["scheme_id"] == "8_position"
    )
    assert primary_zone["required_area_m2"] == six_scheme["required_area_m2"]
    assert eight_scheme["required_area_m2"] == pytest.approx(
        primary["eight_position"]["required_area_m2"],
        abs=0.01,
    )
    assert len(primary_zone["schemes"]) == 2
    assert {scheme["scheme_id"] for scheme in primary_zone["schemes"]} == {
        "6_position",
        "8_position",
    }

    raw_zone = _zone_by_code(zones, "raw_fruit_buffer")
    assert raw_zone["n_need"] == raw_layout["n_need"]
    assert raw_zone["n_long"] == raw_layout["n_long"]
    assert raw_zone["n_short"] == raw_layout["n_short"]
    assert raw_zone["position_count"] == raw_layout["n_actual"]
    assert raw_zone["required_area_m2"] == pytest.approx(raw_layout["required_area_m2"], abs=0.01)
    assert "area_basis" not in raw_zone

    sorting_zone = _zone_by_code(zones, "sorting_packaging_room")
    assert sorting_zone["table_count"] == table_need
    assert sorting_zone["position_count"] == sorting_layout["n_actual"]
    assert sorting_zone["required_area_m2"] == pytest.approx(
        sorting_layout["required_area_m2"],
        abs=0.01,
    )

    finished_zone = _zone_by_code(zones, "finished_goods_room")
    assert finished_zone["required_area_m2"] == pytest.approx(
        finished_layout["required_area_m2"],
        abs=0.01,
    )

    secondary_zone_buffer = _zone_by_code(zones, "secondary_fruit_buffer")
    assert secondary_zone_buffer["design_storage_mass_kg"] == pytest.approx(
        secondary_mass, abs=0.01
    )
    assert secondary_zone_buffer["secondary_fruit_ratio"] == SECONDARY_FRUIT_RATIO
    assert secondary_zone_buffer["secondary_fruit_storage_days"] == SECONDARY_FRUIT_STORAGE_DAYS
    assert secondary_zone_buffer["required_area_m2"] == pytest.approx(
        secondary_layout["required_area_m2"],
        abs=0.01,
    )

    frozen_zone = _zone_by_code(zones, "frozen_fruit_room")
    assert frozen_zone["design_storage_mass_kg"] == pytest.approx(frozen_mass, abs=0.01)
    assert frozen_zone["frozen_storage_days"] == frozen_storage_days
    assert frozen_zone["required_area_m2"] == pytest.approx(
        frozen_layout["required_area_m2"], abs=0.01
    )

    packaging_zone = _zone_by_code(zones, "packaging_material_storage")
    assert packaging_zone["position_count"] == packaging_positions
    assert packaging_zone["required_area_m2"] == pytest.approx(packaging_area, abs=0.01)
    assert packaging_zone["packaging_position_area_m2"] == pytest.approx(3.9, abs=0.0001)

    shipping_zone = _zone_by_code(zones, "shipping_channel")
    assert shipping_zone["pallet_count"] == shipping["pallet_count"]
    assert shipping_zone["truck_count"] == shipping["truck_count"]
    assert shipping_zone["platform_count"] == shipping["platform_count"]
    assert shipping_zone["position_count"] == shipping["platform_count"]
    assert shipping_zone["required_area_m2"] == pytest.approx(
        shipping["required_area_m2"], abs=0.01
    )

    total_6 = _oracle_total_area(
        primary_six_area=float(primary["six_position"]["required_area_m2"]),
        secondary_six_area=float(secondary["six_position"]["required_area_m2"]),
        raw_area=float(raw_layout["required_area_m2"]),
        sorting_area=float(sorting_layout["required_area_m2"]),
        finished_area=float(finished_layout["required_area_m2"]),
        secondary_fruit_area=float(secondary_layout["required_area_m2"]),
        frozen_area=float(frozen_layout["required_area_m2"]),
        packaging_area=packaging_area,
        shipping_area=float(shipping["required_area_m2"]),
    )
    total_8 = _oracle_total_area(
        primary_six_area=float(primary["eight_position"]["required_area_m2"]),
        secondary_six_area=float(secondary["eight_position"]["required_area_m2"]),
        raw_area=float(raw_layout["required_area_m2"]),
        sorting_area=float(sorting_layout["required_area_m2"]),
        finished_area=float(finished_layout["required_area_m2"]),
        secondary_fruit_area=float(secondary_layout["required_area_m2"]),
        frozen_area=float(frozen_layout["required_area_m2"]),
        packaging_area=packaging_area,
        shipping_area=float(shipping["required_area_m2"]),
    )
    assert result.result["total_area_m2"] == pytest.approx(total_6, abs=0.01)
    assert result.result["total_area_m2_8_position_scheme"] == pytest.approx(total_8, abs=0.01)

    for zone in zones:
        assert "precooling_position_area_m2" not in zone
        assert zone.get("required_area_m2") != pytest.approx(5.6, abs=0.001)


def test_v09_p2_zone_list_includes_shipping_channel_after_packaging() -> None:
    planner = ColdRoomZonePlanner()
    result = planner.plan(
        ColdRoomZonePlanInput(
            daily_inbound_mass_kg=10_000,
            working_time_h_per_day=16,
            finished_storage_days=2,
            packaging_storage_days=3,
            precooling_required_ratio=1,
        )
    )
    zone_codes = [zone["zone_code"] for zone in result.result["zones"]]
    assert zone_codes.index("packaging_material_storage") < zone_codes.index("shipping_channel")
    assert zone_codes[-1] == "shipping_channel"
