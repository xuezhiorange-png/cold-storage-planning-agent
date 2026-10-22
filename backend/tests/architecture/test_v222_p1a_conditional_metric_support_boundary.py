"""R2 changes proof/consumption only, never the frozen engineering authorities."""

import ast
import inspect
import subprocess
from pathlib import Path

from cold_storage.modules.layout.domain import composition_placement as exact
from cold_storage.modules.layout.domain import conditional_metric_support as conditional

ROOT = Path(__file__).resolve().parents[3]
START = "ff4626fce1d88f9860b64cd183af3ce1db21a26a"


def test_r2_preserves_p0_p1_p2_r1_authority_files() -> None:
    paths = [
        "adjacency.py",
        "authority_shapes.py",
        "composition_handoff.py",
        "structural_composition.py",
        "validated_site_obstacles.py",
        "site_geometry.py",
        "metric_interface_reservation.py",
    ]
    for name in paths:
        path = "backend/src/cold_storage/modules/layout/domain/" + name
        original = subprocess.check_output(["git", "show", f"{START}:{path}"], cwd=ROOT, timeout=30)
        assert (ROOT / path).read_bytes() == original, name


def test_production_does_not_consume_legacy_static_membership_as_capacity() -> None:
    source = inspect.getsource(exact)
    assert "MetricReservationSupportQueryV1" not in source
    assert "ConditionalMetricSupportQueryV2(" in source
    assert "state.certificate.proof()" in source
    assert "domain.proof(state.support_index)" not in source


def test_conditional_consumer_has_no_role_specific_recovery_or_cursor() -> None:
    source = inspect.getsource(conditional)
    assert "shipping_channel" not in source and "office" not in source
    assert "bisect_left" not in source
    assert "previous.cursor" not in source
    assert "EMPTY_NECESSARY_ORIGIN_SPACE" in source
    assert "verify_negative(proof, domain, placed)" in source
    assert "representative_slots" not in source


def test_r2_preserves_scheduler_zone_order_and_all_normal_geometry_generators() -> None:
    path = "backend/src/cold_storage/modules/layout/domain/composition_placement.py"
    original = subprocess.check_output(["git", "show", f"{START}:{path}"], cwd=ROOT, timeout=30)

    def functions(source: str) -> dict[str, str]:
        return {
            node.name: ast.dump(node, include_attributes=False)
            for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name != "_search_one"
        }

    assert functions(original.decode()) == functions(inspect.getsource(exact))
