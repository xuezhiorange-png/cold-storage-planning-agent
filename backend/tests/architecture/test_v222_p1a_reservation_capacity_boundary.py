"""Reservation is a topology obligation, not a hidden geometry/search engine."""

import ast
from pathlib import Path

MODULE = (
    Path(__file__).resolve().parents[2]
    / "src/cold_storage/modules/layout/domain/mandatory_interface_reservation.py"
)


def test_reservation_domain_is_isolated_from_metric_and_validation_runtime() -> None:
    source = MODULE.read_text()
    tree = ast.parse(source)
    imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    forbidden = (
        "application",
        "composition_placement",
        "access_routing",
        "truck",
        "sqlalchemy",
        "fastapi",
        "site_geometry",
        "dimensioning",
    )
    assert all(not any(marker in name for marker in forbidden) for name in imports)
    assert "office" not in source.lower()
    assert "shipping" not in source.lower()


def test_reservation_contract_has_no_implicit_generation_defaults() -> None:
    domain = MODULE.parent
    for filename, class_name in (
        ("structural_composition.py", "StructuralCompositionPlanV2"),
        ("composition_handoff.py", "StructuralCompositionPlacementHandoffV1"),
    ):
        tree = ast.parse((domain / filename).read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
        required = {"mandatory_interface_reservations", "structural_interface_capacity_gate"}
        declarations = {
            n.target.id: n
            for n in cls.body
            if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
        }
        assert all(declarations[field].value is None for field in required)
