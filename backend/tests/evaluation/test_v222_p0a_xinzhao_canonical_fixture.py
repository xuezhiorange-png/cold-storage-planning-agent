"""Canonical Xinzhao fixture integrity and v2.2.1 Tool 7 replay evidence."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cold_storage.modules.aily.application.site_layout_preview import (
    _validate_tool_input,
    preview_site_layout,
)
from tests.evaluation.v222_p0a_regularity_metrics import (
    building_geometry_facts,
    major_zone_grid_alignment_rate,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.json"
PROVENANCE = ROOT / "backend/tests/fixtures/v22/xinzhao_20t_site_layout_input_v3.provenance.json"
EXPECTED_RAW_SHA256 = "d03ecae9e1e2808cba346eb83a39f853c8a4b366acc103669af1cf868363901e"
EXPECTED_CANONICAL_RESULT_HASH = (
    "sha256:eaa791651fa3fdb20d707d18fa31620992ab17b1ade8dc89554b8b2331742b30"
)
EXPECTED_SVG_SHA256 = "sha256:db63fa7a6954820dd21dc0a7c70aba6f2cbfa7de6c5d2299027176100b109973"
_SENSITIVE_KEY = re.compile(
    r"password|passwd|token|secret|api[_-]?key|dsn|private[_-]?key|credential",
    re.IGNORECASE,
)


def _assert_no_sensitive_fields(value: object) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            assert not _SENSITIVE_KEY.search(str(key)), f"sensitive-looking key: {key}"
            _assert_no_sensitive_fields(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_sensitive_fields(child)
    elif isinstance(value, str):
        assert "-----BEGIN PRIVATE KEY-----" not in value
        assert not re.search(r"(?i)(gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})", value)
        assert not re.search(r"(?i)(postgres|mysql|mongodb)://[^\s]+:[^\s]+@", value)


def _read_fixture() -> tuple[bytes, dict[str, Any]]:
    raw = FIXTURE.read_bytes()
    assert len(raw) == 9552
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_RAW_SHA256
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)
    _assert_no_sensitive_fields(parsed)
    return raw, parsed


def test_canonical_fixture_bytes_provenance_and_tool7_contract() -> None:
    _, payload = _read_fixture()
    provenance = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    assert provenance["raw_size_bytes"] == 9552
    assert provenance["raw_sha256"] == EXPECTED_RAW_SHA256
    assert provenance["tool"] == "preview_site_layout"
    assert provenance["not_engineering_authority"] is True
    business, site, truck_access, truck_maneuver = _validate_tool_input(payload)
    assert set(business) == {
        "daily_inbound_mass_kg",
        "finished_storage_days",
        "frozen_storage_days",
        "main_packaging_storage_days",
        "auxiliary_packaging_storage_days",
    }
    assert all(isinstance(item, Mapping) for item in (site, truck_access, truck_maneuver))


def test_v221_canonical_input_replays_full_tool7_chain() -> None:
    _, payload = _read_fixture()
    result = preview_site_layout(payload)
    assert result["project_layout_validated"] is True
    assert result["p2_complete"] is True
    assert result["zone_count"] == 12
    assert result["layout"]["access_requirement_count"] == 12
    assert result["layout"]["access_pass_count"] == 12
    assert result["layout"]["truck_route_validated"] is True
    assert result["layout"].get("building_footprint")
    assert result["canonical_result_hash"] == EXPECTED_CANONICAL_RESULT_HASH
    assert result["svg_sha256"] == EXPECTED_SVG_SHA256

    matrix = json.loads(
        (ROOT / "docs/tasks/evidence/v2_2_2_p0a/regularity-calibration-matrix.json").read_text(
            encoding="utf-8"
        )
    )
    xinzhao_row = next(
        row
        for row in matrix["fixtures"]
        if row["fixture_id"] == "XINZHAO_20T_SITE_LAYOUT_INPUT_V3_OWNER_ACCEPTANCE"
    )
    facts = building_geometry_facts(result["layout"])
    assert (
        str(major_zone_grid_alignment_rate(result["layout"])) == xinzhao_row["grid_alignment_rate"]
    )
    assert str(facts["BOUNDING_RECTANGLE_OCCUPANCY"]) == xinzhao_row["bounding_rectangle_occupancy"]
    assert facts["EXTERIOR_REFLEX_CORNER_COUNT"] == xinzhao_row["exterior_reflex_corner_count"]
    assert facts["MAIN_BUILDING_COMPONENT_COUNT"] == xinzhao_row["main_building_component_count"]
