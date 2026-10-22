"""R3 is a generic proof layer; engineering and placement policy stay frozen."""

import ast
import inspect
import subprocess
from pathlib import Path

from cold_storage.modules.layout.domain import composition_placement as exact
from cold_storage.modules.layout.domain import joint_metric_capacity as joint

ROOT = Path(__file__).resolve().parents[3]
START = "8c921b0f654d5d00e8664cf19650a278d558a7a0"


def test_r3_preserves_frozen_authority_and_p2_policy():
    for name in (
        "adjacency.py",
        "authority_shapes.py",
        "composition_handoff.py",
        "structural_composition.py",
        "mandatory_interface_reservation.py",
        "validated_site_obstacles.py",
        "site_geometry.py",
        "metric_interface_reservation.py",
        "conditional_metric_support.py",
        "metric_reservation_consumption.py",
    ):
        path = "backend/src/cold_storage/modules/layout/domain/" + name
        assert (ROOT / path).read_bytes() == subprocess.check_output(
            ["git", "show", f"{START}:{path}"], cwd=ROOT, timeout=30
        ), name


def test_r3_preserves_zone_order_scheduler_and_normal_domain_fallback():
    path = "backend/src/cold_storage/modules/layout/domain/composition_placement.py"
    before = subprocess.check_output(["git", "show", f"{START}:{path}"], cwd=ROOT, timeout=30)

    def functions(source):
        return {
            n.name: ast.dump(n, include_attributes=False)
            for n in ast.parse(source).body
            if isinstance(n, ast.FunctionDef) and n.name != "_search_one"
        }

    assert functions(before.decode()) == functions(inspect.getsource(exact))
    source = inspect.getsource(exact._search_one)
    assert "ConditionalMetricSupportQueryV2(" in source
    assert "JointMetricCapacityQueryV1(" in source
    assert "support_query.support_candidates" in source
    assert "_domain_derived_anchors" in source and "_generic_fallback_anchors" in source
    assert "joint_query.support_candidates" not in source
    assert "_shipping_office_seed(" not in source


def test_r3_no_role_specific_recovery_or_unsafe_enumeration_negative():
    source = inspect.getsource(joint)
    assert "office" not in source and "shipping_channel" not in source
    assert "representative_slots" not in source
    assert "JOINT_ASSIGNMENT_UNPROVEN" in source
    assert "verify_negative(state, placed)" in source
    assert "self.pairwise.verify_negative" in source
    assert "UNKNOWN" in source
