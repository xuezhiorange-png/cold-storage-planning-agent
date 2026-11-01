from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAYOUT = ROOT / "src/cold_storage/modules/layout"


def test_opt_in_generation_does_not_import_native_store_or_database():
    files = [
        LAYOUT / "application/autonomous_factory_layout.py",
        LAYOUT / "domain/autonomous_room_search.py",
        LAYOUT / "domain/autonomous_equipment.py",
    ]
    for path in files:
        text = path.read_text()
        for token in (
            "import ortools",
            "cp_model",
            "approved_",
            "MainStore",
            "PoolLease",
            "sqlalchemy",
            "requests",
            "httpx",
            "subprocess",
        ):
            assert token not in text, (path, token)


def test_projection_reads_only_generated_result_not_owner_layout():
    text = (LAYOUT / "infrastructure/autonomous_layout_export.py").read_text()
    assert 'candidate["rooms"]' in text
    assert 'candidate["equipment"]' in text
    assert "get_drawings" not in text
    assert "owner-plan" not in text


def test_production_bootstrap_and_mcp_do_not_select_the_opt_in_entry():
    for folder in (ROOT / "src/cold_storage/bootstrap", ROOT / "src/cold_storage/mcp"):
        if folder.exists():
            assert not any(
                "generate_autonomous_layouts" in p.read_text() for p in folder.rglob("*.py")
            )
