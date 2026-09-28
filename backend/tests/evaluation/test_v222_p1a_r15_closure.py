"""Current R15 recovery invariants over the real unmocked Tool 7 chain."""

from __future__ import annotations

import os

from tests.evaluation.r15_truck_feasible_layout_delivery import (
    CONTROL_HASH,
    _diagnostics,
    _registry,
    _unique_preflight_rows,
    build_r15_closure_evidence,
    capture_cross_fixture_replay,
    capture_xinzhao_replays,
)


def test_r15_control_survives_full_chain_and_current_result_is_deterministic() -> None:
    replay = capture_xinzhao_replays()
    first = replay["first"]
    second = replay["second"]
    result = first["result"]
    second_result = second["result"]
    layout = result["layout"]
    internal = first["internal"]
    registry = _registry(internal)
    control = registry[CONTROL_HASH]

    assert result["project_layout_validated"] is True
    assert result["p2_complete"] is True
    assert result["zone_count"] == 12
    assert layout["access_pass_count"] == layout["access_requirement_count"] == 12
    assert layout["truck_route_validated"] is True
    assert bool(layout.get("building_footprint"))
    assert control["main_skeleton_truck_preflight"]["preflight_status"] == "PASS"
    assert control["tail_search_started"] is True
    assert control["p2d_reached"] is True
    assert control["p2d_full_pass_count"] >= 1

    full_pass_hashes = {
        skeleton_hash
        for skeleton_hash, row in registry.items()
        if int(row.get("p2d_full_pass_count", 0)) > 0
    }
    assert CONTROL_HASH in full_pass_hashes
    assert len(full_pass_hashes) >= 2
    assert _unique_preflight_rows(internal) == _unique_preflight_rows(second["internal"])
    assert (
        _diagnostics(internal)["r11_scheduler_trace"]
        == _diagnostics(second["internal"])["r11_scheduler_trace"]
    )
    assert result["layout"] == second_result["layout"]
    assert result["canonical_result_hash"] == second_result["canonical_result_hash"]
    assert result["drawing"]["svg"] == second_result["drawing"]["svg"]
    assert result["svg_sha256"] == second_result["svg_sha256"]

    serialized = str(result)
    assert "main_skeleton_truck_preflight_trace" not in serialized

    if os.environ.get("R15_WRITE_CLOSURE_EVIDENCE") == "1":
        cross_fixture = capture_cross_fixture_replay()
        evidence = build_r15_closure_evidence(replay, cross_fixture)
        assert evidence["cross_fixture_regression"]["no_previously_valid_fixture_regressed"] is True
