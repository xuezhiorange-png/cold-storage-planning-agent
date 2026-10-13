"""Synthetic mechanism tests only; none certify real Xinzhao vehicle input."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from cold_storage.modules.layout.application.truck_preview import invoke_truck_preview
from cold_storage.modules.layout.domain.dimensioning import canonical_hash
from cold_storage.modules.layout.domain.truck_maneuver import (
    DOCK_REVERSE,
    STRAIGHT_APPROACH,
    TURN_90,
)
from tests.unit.test_v22_p1f_project_truck_input import truck_input
from tests.unit.test_v22_p2b1_truck_maneuver_templates import project_payload, template_payload


def rectangle(x: float, y: float, X: float, Y: float) -> dict[str, Any]:
    return {
        "type": "polygon",
        "points": [{"x": a, "y": b} for a, b in ((x, y), (X, y), (X, Y), (x, Y))],
    }


def segment(x: float, y: float, X: float, Y: float) -> dict[str, Any]:
    return {"start": {"x": x, "y": y}, "end": {"x": X, "y": Y}}


def example() -> dict[str, Any]:
    data = b"SYNTHETIC_TEST_ONLY: supplied envelope and gate evidence, not a real vehicle"
    digest = "sha256:" + sha256(data).hexdigest()
    p1f = truck_input()
    p1f.update(vehicle_width_m=2, vehicle_length_m=4)
    for name in ("turning_envelope", "straight_approach", "loading_operation_clearance"):
        p1f[name].update(reference="synthetic-document", content_sha256=digest)
    turn_shape = {
        "type": "polygon",
        "points": [
            {"x": x, "y": y}
            for x, y in ((0, -1), (14, -1), (14, 1), (11, 1), (11, 14), (9, 14), (9, 1), (0, 1))
        ],
    }
    shapes = [
        (STRAIGHT_APPROACH, rectangle(0, -1, 14, 1), (10, 0, 0)),
        (TURN_90, turn_shape, (10, 10, 90)),
        (DOCK_REVERSE, rectangle(0, -1, 4, 6), (0, 0, 0)),
    ]
    templates = []
    for kind, envelope, (x, y, rotation) in shapes:
        extra: dict[str, Any] = {}
        if kind == TURN_90:
            extra["turn_direction"] = "LEFT"
        if kind == DOCK_REVERSE:
            extra.update(
                dock_face_reference="shipping_channel.LONG_EDGE_LOADING_FACE",
                approach_pose={"x": 0, "y": 0, "rotation_deg": 0},
                final_dock_pose={"x": 0, "y": 5, "rotation_deg": 0},
            )
        templates.append(
            template_payload(
                kind,
                vehicle_width_m=2,
                vehicle_length_m=4,
                envelope_geometry=envelope,
                reference="synthetic-document",
                content_sha256=digest,
                reference_frame={
                    "reference_frame": "LOCAL_TEMPLATE_FRAME",
                    "forward_axis": "POSITIVE_X",
                    "origin_reference": "ENTRY_REFERENCE_POINT",
                    "vehicle_reference_point": {"x": 0, "y": 0},
                    "entry_pose": {"x": 0, "y": 0, "rotation_deg": 0},
                    "exit_pose": {"x": x, "y": y, "rotation_deg": rotation},
                },
                **extra,
            )
        )
    return dict(
        schema_version="1.0.0",
        mode="SYNTHETIC_TEST",
        vehicle_type="synthetic-rigid",
        vehicle_body=rectangle(0, -1, 4, 1),
        vehicle_source_reference="synthetic-document",
        truck_access=p1f,
        truck_maneuver=project_payload(templates, (STRAIGHT_APPROACH, TURN_90, DOCK_REVERSE)),
        entrance=dict(
            locator_segment=segment(0, 10, 0, 10.001),
            clear_opening_segment=segment(0, 7, 0, 13),
            clear_width_m=6,
            measurement_reference="synthetic-document",
            clearance_reference="synthetic-document",
        ),
        shipping_loading_face=segment(10, 20, 18, 20),
        loading_face_reference="synthetic-document",
        site_geometry=dict(
            effective_buildable_boundary=rectangle(0, 0, 60, 50),
            hard_obstacles=[],
            zones=[
                dict(zone_code="shipping_channel", x=10, y=16, width_m=8, depth_m=4, rotation_deg=0)
            ],
            personnel_corridors=[],
        ),
        evidence=[
            dict(
                reference="synthetic-document",
                content_sha256=digest,
                content_base64=base64.b64encode(data).decode(),
            )
        ],
        approval_reference="synthetic-document",
    )


def test_callable_native_chain_and_svg() -> None:
    result = invoke_truck_preview(example())
    assert result["status"] == "PASS", result
    assert result["SYNTHETIC_TEST_ONLY"] and not result["REAL_PROJECT_APPROVED"]
    assert len(result["truck"]["maneuver_chain"]) == 3
    assert result["truck"]["search_provenance"]["node_budget"] == 20000
    assert "<polygon" in result["svg"] and "SYNTHETIC_TEST_ONLY" in result["svg"]
    assert result == invoke_truck_preview(example())
    cli = subprocess.run(
        [sys.executable, str(Path(__file__).parents[2] / "scripts/preview_truck.py")],
        input=json.dumps(example(), default=str),
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(cli.stdout) == result


def test_missing_vehicle_and_owner_documents() -> None:
    p = example()
    del p["truck_access"]["vehicle_width_m"]
    assert invoke_truck_preview(p)["status"] == "PROJECT_INPUT_REQUIRED"
    p = example()
    p["mode"] = "OWNER_PROJECT"
    p["evidence"] = []
    r = invoke_truck_preview(p)
    assert r["status"] == "PROJECT_INPUT_REQUIRED" and not r["REAL_PROJECT_APPROVED"]
    assert invoke_truck_preview(example())["status"] == "PASS"


def test_content_and_declared_hashes_must_match_actual_bytes() -> None:
    p = example()
    p["evidence"][0]["content_base64"] = base64.b64encode(b"wrong").decode()
    assert invoke_truck_preview(p)["status"] == "TRUCK_SOURCE_CONTENT_HASH_MISMATCH"
    p = example()
    p["evidence"][0]["content_base64"] = "invalid==!!"
    assert invoke_truck_preview(p)["status"] == "INVALID_TRUCK_SOURCE_ENCODING"


def test_gate_width_measurement_and_swept_section() -> None:
    p = example()
    p["entrance"].update(clear_width_m=1, clear_opening_segment=segment(0, 10, 0, 11))
    assert invoke_truck_preview(p)["status"] == "TRUCK_ENTRANCE_CLEAR_WIDTH_INSUFFICIENT"
    p = example()
    p["entrance"]["measurement_reference"] = "missing"
    assert invoke_truck_preview(p)["status"] == "PROJECT_INPUT_REQUIRED"
    p = example()
    p["entrance"].update(clear_width_m=2, clear_opening_segment=segment(0, 10, 0, 12))
    r = invoke_truck_preview(p)
    assert r["status"] == "TRUCK_ENTRANCE_POSE_CLEARANCE_REJECTED" and "svg" not in r


def test_collision_does_not_generate_fake_route() -> None:
    p = example()
    p["site_geometry"]["hard_obstacles"] = [rectangle(0, 8, 8, 12)]
    r = invoke_truck_preview(p)
    assert r["status"] == "TRUCK_MANEUVER_SEARCH_EXHAUSTED"
    assert not r["truck"]["truck_route_validated"] and "svg" not in r


def test_personnel_contact_is_review_not_pass() -> None:
    p = example()
    p["site_geometry"]["personnel_corridors"] = [rectangle(1, 11, 5, 13)]
    r = invoke_truck_preview(p)
    assert r["status"] == "REQUIRES_ENGINEERING_REVIEW"
    assert r["personnel_truck_interaction"]["crossing_necessary"] == "UNDETERMINED"
    assert "svg" not in r


def test_bound_approval_record_cannot_be_reused_for_another_input() -> None:
    p = example()
    p["mode"] = "OWNER_PROJECT"
    p["approval_reference"] = "approval"
    record = dict(
        project_id="fixture-project",
        status="APPROVED",
        reviewed_by="synthetic-reviewer",
        approved_input_hash=canonical_hash({k: v for k, v in p.items() if k != "evidence"}),
    )
    raw = json.dumps(record).encode()
    p["evidence"].append(
        dict(
            reference="approval",
            content_sha256="sha256:" + sha256(raw).hexdigest(),
            content_base64=base64.b64encode(raw).decode(),
        )
    )
    r = invoke_truck_preview(p)
    assert r["status"] == "PASS" and r["owner_approval_record_matches_input"]
    assert not r[
        "approval_signature_authenticated"
    ]  # Synthetic approval, not project certification.
    changed = deepcopy(p)
    changed["vehicle_type"] = "different"
    assert invoke_truck_preview(changed)["status"] == "PROJECT_INPUT_REQUIRED"


@pytest.mark.parametrize("value", [None, [], {"unexpected": 1}])
def test_bad_input_fails_closed(value: object) -> None:
    assert invoke_truck_preview(value)["status"] != "PASS"


def test_template_body_and_duplicate_source_conflicts_fail_closed() -> None:
    p = example()
    p["vehicle_body"] = rectangle(0, -1, 3, 1)
    assert invoke_truck_preview(p)["status"] == "TRUCK_VEHICLE_BODY_DIMENSION_MISMATCH"
    p = example()
    p["truck_access"]["straight_approach"]["content_sha256"] = "sha256:" + "a" * 64
    assert invoke_truck_preview(p)["status"] == "TRUCK_SOURCE_CONTENT_HASH_MISMATCH"
    p = example()
    p["site_geometry"]["zones"].append(deepcopy(p["site_geometry"]["zones"][0]))
    assert invoke_truck_preview(p)["status"] == "DUPLICATE_TRUCK_CONTEXT_ZONE"


def test_exact_independent_cell_oracle_for_returned_swept_polygons() -> None:
    # Independent rational ray-casting at exact coordinate-compressed cells.
    # Applicable to this synthetic orthogonal example only, not a new Authority.
    raw = invoke_truck_preview(example())
    polygons = [
        [(Fraction(p["x"]), Fraction(p["y"])) for p in e["points"]]
        for e in raw["truck"]["truck_envelopes"]
    ]
    xs = sorted({Fraction(x) for poly in polygons for x, _ in poly} | {Fraction(10), Fraction(18)})
    ys = sorted({Fraction(y) for poly in polygons for _, y in poly} | {Fraction(16), Fraction(20)})

    def interior(x: Fraction, y: Fraction, poly: list[tuple[Fraction, Fraction]]) -> bool:
        crossing = 0
        for (a, b), (c, d) in zip(poly, poly[1:] + poly[:1], strict=True):
            if (b > y) != (d > y) and x < a + (y - b) * (c - a) / (d - b):
                crossing += 1
        return crossing % 2 == 1

    checked = 0
    for x, X in zip(xs, xs[1:], strict=False):
        for y, Y in zip(ys, ys[1:], strict=False):
            mx, my = (x + X) / 2, (y + Y) / 2
            if any(interior(mx, my, p) for p in polygons):
                assert 0 < mx < 60 and 0 < my < 50
                assert not (10 < mx < 18 and 16 < my < 20)
                checked += 1
    assert checked > 0
