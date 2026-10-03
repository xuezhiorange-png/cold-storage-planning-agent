"""Immutable layout/history checks; current R15 behavior is tested separately."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cold_storage.modules.layout.domain.structural_composition import (
    MAIN_PROCESS_SKELETON_ZONE_CODES,
)

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/tasks/evidence/v2_2_2_p1a"
FIXTURE = ROOT / "backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json"
EXPECTED_INPUT_SHA256 = "d03ecae9e1e2808cba346eb83a39f853c8a4b366acc103669af1cf868363901e"
HISTORICAL_LAYOUTS = (
    "xinzhao_v221_before_layout.json",
    "xinzhao_p1a_after_layout.json",
    "xinzhao_p1a_r2_after_layout.json",
    "xinzhao_p1a_r3_after_layout.json",
    "xinzhao_p1a_r5_selected_layout.json",
)


def _read(name: str) -> dict[str, Any]:
    value = json.loads((EVIDENCE / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _zone_map(layout: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = layout.get("zones")
    assert isinstance(rows, list)
    return {
        str(row["zone_code"]): row
        for row in rows
        if isinstance(row, Mapping) and isinstance(row.get("zone_code"), str)
    }


def _main_geometry(layout: Mapping[str, Any]) -> dict[str, tuple[Any, ...]]:
    zones = _zone_map(layout)
    return {
        code: tuple(
            zones[code].get(field) for field in ("x", "y", "width_m", "depth_m", "rotation_deg")
        )
        for code in MAIN_PROCESS_SKELETON_ZONE_CODES
    }


def test_frozen_pre_r6_layout_geometry_and_result_history_are_unchanged() -> None:
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == EXPECTED_INPUT_SHA256
    layouts = {name: _read(name) for name in HISTORICAL_LAYOUTS}
    geometry = {name: _main_geometry(value) for name, value in layouts.items()}
    first = geometry[HISTORICAL_LAYOUTS[0]]
    assert all(value == first for value in geometry.values())

    r3_metrics = _read("xinzhao_p1a_r3_metrics.json")
    r5_metrics = _read("xinzhao_p1a_r5_metrics.json")
    r6_metrics = _read("xinzhao_p1a_r6_metrics.json")
    r11_budget = _read("xinzhao_p1a_r11_budget_accounting.json")
    assert r3_metrics["result"] == "PARTIAL"
    assert r3_metrics["owner_xinzhao_p1a_r3_visual_review"] == "PENDING"
    assert r5_metrics["result"] == "PARTIAL"
    assert r5_metrics["owner_xinzhao_p1a_r5_visual_review"] == "PENDING"
    assert r5_metrics["distinct_p2d_full_pass_main_process_skeleton_count"] == 1
    assert r5_metrics["selected_main_process_geometry_changed_from_r3"] is False
    assert r5_metrics["r5_svg_hash_equals_r3"] is True
    assert r6_metrics["result"] == "PARTIAL"
    assert r11_budget["global_budget"] == 120
    assert r11_budget["selected_main_process_skeleton_hash"] == (
        "sha256:55589c20f3c3336c1c92a8c1ffc8b14a813ac558bac78871d4e6b1fa8ee9b953"
    )
