"""S2 tail routing remains injected and distinct from final P2D validation."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLACEMENT_DOMAIN = (ROOT / "src/cold_storage/modules/layout/domain/placement.py").read_text(
    encoding="utf-8"
)
PLACEMENT_APPLICATION = (
    ROOT / "src/cold_storage/modules/layout/application/placement.py"
).read_text(encoding="utf-8")
P2D_ACCESS_APPLICATION = (
    ROOT / "src/cold_storage/modules/layout/application/access_routing.py"
).read_text(encoding="utf-8")


def test_structured_tail_uses_injected_exact_route_authority() -> None:
    assert "domain.access_routing" not in PLACEMENT_DOMAIN
    assert "route_access_requirement" not in PLACEMENT_DOMAIN
    assert "route_access_requirement(" in PLACEMENT_APPLICATION
    assert "access_route_validator=construction_access_route_validator" in PLACEMENT_APPLICATION
    assert "_tail_access_route_rows(" in PLACEMENT_DOMAIN
    assert '"tail_access_aware_admission": True' in PLACEMENT_DOMAIN
    assert '"revalidate_after_each_tail_extension": True' in PLACEMENT_DOMAIN


def test_final_p2d_still_runs_its_independent_access_routing_path() -> None:
    assert "route_access_requirement(" in P2D_ACCESS_APPLICATION
    assert "for requirement in non_truck_requirements" in P2D_ACCESS_APPLICATION
    assert "access_results.append(routed)" in P2D_ACCESS_APPLICATION
