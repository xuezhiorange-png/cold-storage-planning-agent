"""Independent POST-V0.9 P4 oracles for Charles zone-area recut."""

from __future__ import annotations

from math import ceil

import pytest

from cold_storage.modules.calculations.domain.zone_planning import (
    COATING_AREA_BY_BAND_M2,
    FROZEN_FRUIT_RATIO,
    OFFICE_AREA_BY_BAND_M2,
    PACKAGING_K_BY_BAND,
    PACKAGING_POSITION_BASE_AREA_M2,
    PERSON_DAILY_CAPACITY_KG,
    PRECOOL_EIGHT_POSITION_ROOM_AREA_M2,
    PRECOOL_SIX_POSITION_ROOM_AREA_M2,
    RAW_AISLE_M,
    SECONDARY_FRUIT_RATIO,
    SECONDARY_FRUIT_STORAGE_DAYS,
    SHIPPING_PLATFORM_AREA_M2,
    ColdRoomZonePlanInput,
    ColdRoomZonePlanner,
    FORMULA_AUTHORITY,
)


def _throughput_band_area(mass_tons: float, areas: tuple[float, float, float]) -> float:
    if mass_tons < 25:
        return areas[0]
    if mass_tons < 50:
        return areas[1]
    return areas[2]


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
    six_area: float = PRECOOL_SIX_POSITION_ROOM_AREA_M2,
    eight_area: float = PRECOOL_EIGHT_POSITION_ROOM_AREA_M2,
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
        "required_area_m2": platform_count * SHIPPING_PLATFORM_AREA_M2,
    }


def _zone_by_code(zones: list[dict[str, object]], zone_code: str) -> dict[str, object]:
    return next(zone for zone in zones if zone["zone_code"] == zone_code)


def _oracle_total_area(
    *,
    office_area: float,
    changing_area: float,
    coating_area: float,
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
        office_area
        + changing_area
        + coating_area
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


SAMPLE_KEY_ORACLE: dict[str, float] = {
    "office": 60.00,
    "changing_room": 40.00,
    "primary_precooling_room": 126.00,
    "secondary_precooling_room": 84.00,
    "raw_fruit_buffer": 132.24,
    "sorting_packaging_room": 489.60,
    "coating_room": 80.00,
    "finished_goods_room": 602.64,
    "secondary_fruit_buffer": 57.96,
    "frozen_fruit_room": 88.56,
    "packaging_material_storage": 250.85,
    "shipping_channel": 50.00,
}
SAMPLE_KEY_TOTAL = 2061.85


def test_post_v09_p4_sample_key_oracle() -> None:
    """Charles sample KEY: 20 t/day, finished 7 d, frozen 10 d, main 4 d, aux 12 d."""
    planner = ColdRoomZonePlanner()
    result = planner.plan(
        ColdRoomZonePlanInput(
            daily_inbound_mass_kg=20_000,
            working_time_h_per_day=16,
            finished_storage_days=7,
            packaging_storage_days=3,
            precooling_required_ratio=1,
            frozen_storage_days=10,
            main_packaging_storage_days=4,
            auxiliary_packaging_storage_days=12,
        )
    )

    assert result.success is True
    assert result.result["planning_parameters"]["formula_authority"] == FORMULA_AUTHORITY
    zones = {zone["zone_code"]: zone for zone in result.result["zones"]}
    for zone_code, expected_area in SAMPLE_KEY_ORACLE.items():
        assert zones[zone_code]["required_area_m2"] == pytest.approx(expected_area, abs=0.01)
    assert result.result["total_area_m2"] == pytest.approx(SAMPLE_KEY_TOTAL, abs=0.01)


@pytest.mark.parametrize(
    ("daily_mass_kg", "expected_office", "expected_changing", "expected_coating", "expected_k"),
    [
        (24_999, 60, 40, 80, 2.4),
        (25_000, 80, 80, 120, 2.3),
        (49_999, 80, 80, 120, 2.3),
        (50_000, 100, 120, 200, 2.2),
    ],
)
def test_post_v09_p4_throughput_band_edges(
    daily_mass_kg: float,
    expected_office: float,
    expected_changing: float,
    expected_coating: float,
    expected_k: float,
) -> None:
    mass_tons = daily_mass_kg / 1000
    assert _throughput_band_area(mass_tons, OFFICE_AREA_BY_BAND_M2) == expected_office
    assert _throughput_band_area(mass_tons, COATING_AREA_BY_BAND_M2) == expected_coating
    assert _throughput_band_area(mass_tons, PACKAGING_K_BY_BAND) == expected_k

    planner = ColdRoomZonePlanner()
    result = planner.plan(
        ColdRoomZonePlanInput(
            daily_inbound_mass_kg=daily_mass_kg,
            working_time_h_per_day=16,
            finished_storage_days=3,
            packaging_storage_days=3,
            precooling_required_ratio=1,
        )
    )
    zones = {zone["zone_code"]: zone for zone in result.result["zones"]}
    assert zones["office"]["required_area_m2"] == pytest.approx(expected_office, abs=0.01)
    assert zones["changing_room"]["required_area_m2"] == pytest.approx(expected_changing, abs=0.01)
    assert zones["coating_room"]["required_area_m2"] == pytest.approx(expected_coating, abs=0.01)
    assert zones["packaging_material_storage"]["packaging_area_factor_k"] == pytest.approx(
        expected_k, abs=0.001
    )


@pytest.mark.parametrize(
    ("daily_mass_kg", "finished_storage_days", "frozen_storage_days"),
    [
        (25_000, 2.5, 5),
        (5_000, 2.0, 7),
    ],
)
def test_post_v09_p4_zone_planning_matches_independent_oracles(
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
    assert result.result["planning_parameters"]["formula_authority"] == FORMULA_AUTHORITY
    zones = result.result["zones"]
    mass_tons = daily_mass_kg / 1000

    office_area = _throughput_band_area(mass_tons, OFFICE_AREA_BY_BAND_M2)
    changing_area = _throughput_band_area(mass_tons, (40, 80, 120))
    coating_area = _throughput_band_area(mass_tons, COATING_AREA_BY_BAND_M2)
    packaging_k = _throughput_band_area(mass_tons, PACKAGING_K_BY_BAND)

    primary = _precool_oracle(daily_mass_kg, q_d_kg_day=220 * 6)
    secondary = _precool_oracle(daily_mass_kg, q_d_kg_day=3200)
    raw_need = ceil(daily_mass_kg * 0.40 / 220)
    raw_layout = _pack_rectangle_oracle(
        raw_need,
        lambda n_long, n_short: (n_long * 1.2 + RAW_AISLE_M + RAW_AISLE_M)
        * (n_short * 1.3 + RAW_AISLE_M),
    )
    worker_count = ceil(daily_mass_kg / PERSON_DAILY_CAPACITY_KG)
    table_need = ceil(worker_count / 3)
    sorting_layout = _pack_rectangle_oracle(
        table_need,
        lambda n_long, n_short: (
            max(n_long - 1, 0) * 5.6 + 8
        )
        * (max(n_short - 1, 0) * 3.0 + 7.6),
    )
    finished_mass = daily_mass_kg * (1 - FROZEN_FRUIT_RATIO) * finished_storage_days
    finished_need = ceil(finished_mass / 400)
    finished_layout = _pack_rectangle_oracle(
        finished_need,
        lambda n_long, n_short: (n_long * 1.2) * (n_short * 1.3 + 3),
    )
    secondary_mass = daily_mass_kg * SECONDARY_FRUIT_RATIO * SECONDARY_FRUIT_STORAGE_DAYS
    secondary_need = ceil(secondary_mass / 220)
    secondary_layout = _pack_rectangle_oracle(
        secondary_need,
        lambda n_long, n_short: (n_long * 1.2) * (n_short * 1.3 + 3),
    )
    frozen_mass = daily_mass_kg * FROZEN_FRUIT_RATIO * frozen_storage_days
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
    packaging_area = packaging_positions * PACKAGING_POSITION_BASE_AREA_M2 * packaging_k
    shipping = _shipping_oracle(daily_mass_kg)

    assert _zone_by_code(zones, "office")["required_area_m2"] == pytest.approx(
        office_area, abs=0.01
    )
    assert _zone_by_code(zones, "changing_room")["required_area_m2"] == pytest.approx(
        changing_area, abs=0.01
    )
    assert _zone_by_code(zones, "coating_room")["required_area_m2"] == pytest.approx(
        coating_area, abs=0.01
    )

    primary_zone = _zone_by_code(zones, "primary_precooling_room")
    assert primary_zone["raw_position_count"] == primary["n_need"]
    assert primary_zone["required_area_m2"] == pytest.approx(
        primary["six_position"]["required_area_m2"], abs=0.01
    )

    raw_zone = _zone_by_code(zones, "raw_fruit_buffer")
    assert raw_zone["required_area_m2"] == pytest.approx(raw_layout["required_area_m2"], abs=0.01)

    sorting_zone = _zone_by_code(zones, "sorting_packaging_room")
    assert sorting_zone["required_area_m2"] == pytest.approx(
        sorting_layout["required_area_m2"], abs=0.01
    )

    finished_zone = _zone_by_code(zones, "finished_goods_room")
    assert finished_zone["required_area_m2"] == pytest.approx(
        finished_layout["required_area_m2"], abs=0.01
    )

    secondary_zone_buffer = _zone_by_code(zones, "secondary_fruit_buffer")
    assert secondary_zone_buffer["secondary_fruit_storage_days"] == SECONDARY_FRUIT_STORAGE_DAYS
    assert secondary_zone_buffer["required_area_m2"] == pytest.approx(
        secondary_layout["required_area_m2"], abs=0.01
    )

    frozen_zone = _zone_by_code(zones, "frozen_fruit_room")
    assert frozen_zone["required_area_m2"] == pytest.approx(
        frozen_layout["required_area_m2"], abs=0.01
    )

    packaging_zone = _zone_by_code(zones, "packaging_material_storage")
    assert packaging_zone["required_area_m2"] == pytest.approx(packaging_area, abs=0.01)

    shipping_zone = _zone_by_code(zones, "shipping_channel")
    assert shipping_zone["required_area_m2"] == pytest.approx(
        shipping["required_area_m2"], abs=0.01
    )

    total_6 = _oracle_total_area(
        office_area=office_area,
        changing_area=changing_area,
        coating_area=coating_area,
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
    assert result.result["total_area_m2"] == pytest.approx(total_6, abs=0.01)
