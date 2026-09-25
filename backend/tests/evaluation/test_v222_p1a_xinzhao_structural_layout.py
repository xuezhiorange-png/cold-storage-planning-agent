"""Unmocked Tool 7 P1A regression for the Owner-labelled Xinzhao fixture."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cold_storage.modules.aily.application.site_layout_preview import preview_site_layout
from cold_storage.modules.layout.domain.structural_quality import (
    _bounds,
    _group_edge_facts,
    _shared_edge_orientation,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json"
V221_BASELINE = ROOT / "docs/tasks/evidence/v2_2_2_p1a/xinzhao_v221_before_layout.json"
EXPECTED_INPUT_SHA256 = "d03ecae9e1e2808cba346eb83a39f853c8a4b366acc103669af1cf868363901e"
V221_RESULT_HASH = "sha256:eaa791651fa3fdb20d707d18fa31620992ab17b1ade8dc89554b8b2331742b30"
V221_SVG_SHA256 = "sha256:db63fa7a6954820dd21dc0a7c70aba6f2cbfa7de6c5d2299027176100b109973"
R2_LAYOUT = ROOT / "docs/tasks/evidence/v2_2_2_p1a/xinzhao_p1a_r2_after_layout.json"
R2_SVG = ROOT / "docs/tasks/evidence/v2_2_2_p1a/xinzhao_p1a_r2_after.svg"


def _zone_map(layout: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = layout.get("zones")
    assert isinstance(rows, list)
    return {
        str(row["zone_code"]): row
        for row in rows
        if isinstance(row, Mapping) and isinstance(row.get("zone_code"), str)
    }


def _direct_core_edges(zones: Mapping[str, Mapping[str, Any]]) -> int:
    return sum(
        int(_shared_edge_orientation(_bounds(zones[first]), _bounds(zones[second])) is not None)
        for first, second in (
            ("primary_precooling_room", "sorting_packaging_room"),
            ("sorting_packaging_room", "secondary_precooling_room"),
        )
    )


def test_xinzhao_real_tool7_structural_candidate_is_full_pass_and_deterministic() -> None:
    raw = FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_INPUT_SHA256
    payload = json.loads(raw)
    baseline = json.loads(V221_BASELINE.read_text(encoding="utf-8"))
    saved_r2_layout = json.loads(R2_LAYOUT.read_text(encoding="utf-8"))
    assert baseline["canonical_result_hash"] == V221_RESULT_HASH

    first = preview_site_layout(payload)
    second = preview_site_layout(payload)

    for result in (first, second):
        layout = result["layout"]
        assert result["project_layout_validated"] is True
        assert result["p2_complete"] is True
        assert result["validated_layout_selected"] is True
        assert result["zone_count"] == 12
        assert layout["access_requirement_count"] == 12
        assert layout["access_pass_count"] == 12
        assert layout["truck_route_validated"] is True
        assert layout.get("building_footprint")
        assert result["drawing"]["identity"] == "validated-layout-svg-projection@1.0.0"
        assert result["drawing"]["svg"]
        assert result["selection"]["p2d_full_pass_candidate_count"] >= 1
        lane_reports = result["selection"]["search_provenance"]["family_lanes"]
        assert {
            (row["composition_family"]["family"], row["composition_family"]["dominant_direction"])
            for row in lane_reports
        } == {
            ("LINEAR_PROCESS_BAND", "POSITIVE"),
            ("LINEAR_PROCESS_BAND", "NEGATIVE"),
            ("CENTRAL_PROCESS_HUB", "UNRESOLVED"),
        }
        assert result["selection"]["p2d_full_pass_candidate_count"] >= 2
        assert result["selection"]["search_provenance"]["node_budget"] == 120

    assert first["canonical_result_hash"] == second["canonical_result_hash"]
    assert first["layout"]["canonical_result_hash"] == second["layout"]["canonical_result_hash"]
    assert first["drawing"]["svg"] == second["drawing"]["svg"]
    assert first["drawing"]["svg"].encode("utf-8") == R2_SVG.read_bytes()
    assert first["layout"] == saved_r2_layout
    assert first["svg_sha256"] == second["svg_sha256"]
    assert hashlib.sha256(first["drawing"]["svg"].encode("utf-8")).hexdigest() == (
        first["svg_sha256"].removeprefix("sha256:")
    )
    assert first["canonical_result_hash"] != V221_RESULT_HASH
    assert first["svg_sha256"] != V221_SVG_SHA256

    old_zones = _zone_map(baseline)
    new_zones = _zone_map(first["layout"])
    old_groups = _group_edge_facts(old_zones)
    new_groups = _group_edge_facts(new_zones)
    assert old_groups["SUPPORT_GROUP"] == 0
    assert new_groups["SUPPORT_GROUP"] == 2
    # The core stays fully connected, but its direct-edge count does not
    # improve over the hard-valid v2.2.1 baseline and is reported as such.
    assert _direct_core_edges(old_zones) == 2
    assert _direct_core_edges(new_zones) == 2
    assert first["selection"]["search_provenance"]["node_budget"] == 120
    assert first["selection"]["search_provenance"]["node_budget_exhausted"] is True
