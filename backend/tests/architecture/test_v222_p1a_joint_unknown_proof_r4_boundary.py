"""R4 proof queries cannot modify frozen placement or engineering policy."""

import inspect
import subprocess
from pathlib import Path

from cold_storage.modules.layout.domain import joint_metric_capacity as joint

ROOT = Path(__file__).resolve().parents[3]
START = "9e566603ae217a3eb6a3c2969c0b646756a4df9d"


def test_r4_frozen_placement_and_authority_bytes():
    directory = "backend/src/cold_storage/modules/layout/"
    for suffix in (
        "domain/composition_placement.py",
        "application/composition_placement.py",
        "domain/adjacency.py",
        "domain/authority_shapes.py",
        "domain/site_geometry.py",
        "domain/validated_site_obstacles.py",
        "domain/composition_handoff.py",
        "domain/structural_composition.py",
        "domain/mandatory_interface_reservation.py",
        "domain/metric_interface_reservation.py",
        "application/metric_interface_reservation.py",
        "domain/conditional_metric_support.py",
        "domain/metric_reservation_consumption.py",
    ):
        path = directory + suffix
        assert (ROOT / path).read_bytes() == subprocess.check_output(
            ["git", "show", f"{START}:{path}"], cwd=ROOT, timeout=30
        ), path


def test_r4_caps_and_positive_only_propagation():
    e = inspect.signature(joint.JointMetricCapacityQueryV1)
    assert e.parameters["evaluation_cap"].default == 256
    assert e.parameters["event_cap"].default == 1024
    source = inspect.getsource(joint)
    assert "office" not in source and "shipping_channel" not in source
    assert "representative_slots" not in source
    assert "historical" not in source.lower()
    negative = inspect.getsource(joint.JointMetricCapacityQueryV1.negative)
    assert "positive_origin_spaces" not in negative
