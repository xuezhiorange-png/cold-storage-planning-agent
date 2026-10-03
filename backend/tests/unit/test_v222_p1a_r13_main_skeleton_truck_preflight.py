"""Unit contracts for the necessary-only main-skeleton truck preflight."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from cold_storage.modules.layout.domain import placement
from cold_storage.modules.layout.domain.structural_composition import (
    MAIN_PROCESS_SKELETON_ZONE_CODES,
)


def _context(binding: object = "BOUND_TRUCK", budget: int = 5000) -> SimpleNamespace:
    return SimpleNamespace(
        truck_maneuver_binding=binding,
        truck_node_budget=budget,
        truck_maneuver_validator=None,
        site_body={
            "site": {"preferred_loading_side": "NORTH"},
            "entrances": {
                "truck_entrance": {
                    "start": {"x": 0, "y": 0},
                    "end": {"x": 0, "y": 1},
                }
            },
        },
        boundary=((0, 0), (10, 0), (10, 10), (0, 10)),
        obstacles=(((20, 20), (21, 20), (21, 21), (20, 21)),),
    )


def _skeleton() -> SimpleNamespace:
    return SimpleNamespace(
        main_process_skeleton_hash="sha256:test-skeleton",
        zone_rectangles=tuple(
            SimpleNamespace(
                zone_code=code,
                x=1,
                y=1,
                width_m=2,
                depth_m=1,
                rotation_deg=0,
            )
            for code in MAIN_PROCESS_SKELETON_ZONE_CODES
        ),
    )


def _truck_result(
    *,
    route_validated: bool = False,
    status: str = "TRUCK_MANEUVER_SEARCH_EXHAUSTED",
    tree_exhausted: bool = True,
    budget_exhausted: bool = False,
) -> dict[str, Any]:
    return {
        "truck_route_validated": route_validated,
        "status": status,
        "codes": [] if route_validated else [status],
        "search_profile_identity": "truck-maneuver-chain-search@1.0.0",
        "canonical_result_hash": "sha256:truck-result",
        "search_provenance": {
            "visited_nodes": 39,
            "node_budget": 5000,
            "node_budget_exhausted": budget_exhausted,
            "search_tree_exhausted": tree_exhausted,
        },
    }


def test_preflight_reuses_authoritative_validator_and_only_the_seven_zones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    face = ((1000, 2000), (9000, 2000))
    monkeypatch.setattr(
        placement,
        "_loading_face",
        lambda rectangle, site: ("NORTH", face, {"mode": "TEST"}, ()),
    )
    calls: list[dict[str, Any]] = []

    def validate(binding: object, **kwargs: Any) -> dict[str, Any]:
        calls.append({"binding": binding, **kwargs})
        return _truck_result(route_validated=True, status="PASS")

    context = _context()
    context.truck_maneuver_validator = validate
    row = placement._main_skeleton_truck_maneuver_preflight(context, _skeleton())

    assert row["preflight_status"] == "PASS"
    assert row["preflight_action"] == "ALLOW_TAIL_SEARCH"
    assert row["tail_search_started"] is False
    assert row["zones_checked"] == list(MAIN_PROCESS_SKELETON_ZONE_CODES)
    assert calls[0]["binding"] == "BOUND_TRUCK"
    assert set(calls[0]["zones"]) == set(MAIN_PROCESS_SKELETON_ZONE_CODES)
    assert calls[0]["shipping_loading_face"] == face
    assert calls[0]["node_budget"] == 5000


def test_only_exhausted_authoritative_no_route_rejects_the_skeleton() -> None:
    status, reason = placement._truck_maneuver_preflight_decision(
        _truck_result(status="TRUCK_MANEUVER_SEARCH_EXHAUSTED")
    )
    assert (status, reason) == ("REJECT", "TRUCK_MANEUVER_SEARCH_EXHAUSTED")


def test_budget_exhaustion_is_unresolved_not_geometric_infeasibility() -> None:
    status, reason = placement._truck_maneuver_preflight_decision(
        _truck_result(
            status="TRUCK_MANEUVER_SEARCH_EXHAUSTED",
            tree_exhausted=False,
            budget_exhausted=True,
        )
    )
    assert (status, reason) == ("UNRESOLVED", "TRUCK_MANEUVER_SEARCH_BUDGET_EXHAUSTED")


def test_missing_truck_authority_is_unresolved_not_geometric_infeasibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    face = ((1000, 2000), (9000, 2000))
    monkeypatch.setattr(
        placement,
        "_loading_face",
        lambda rectangle, site: ("NORTH", face, {"mode": "TEST"}, ()),
    )
    context = _context(binding=None)
    context.truck_maneuver_validator = lambda binding, **kwargs: {
        **_truck_result(
            status="BLOCKED_PROJECT_MANEUVER_INPUT_REQUIRED",
            tree_exhausted=False,
            budget_exhausted=False,
        ),
        "codes": ["BLOCKED_PROJECT_MANEUVER_INPUT_REQUIRED"],
    }

    row = placement._main_skeleton_truck_maneuver_preflight(context, _skeleton())
    assert row["preflight_status"] == "UNRESOLVED"
    assert row["preflight_action"] == "ALLOW_TAIL_SEARCH"
    assert row["failure_reason"] is None
