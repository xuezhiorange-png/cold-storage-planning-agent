"""Handover document for V1.1 release identity must stay findable."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
HANDOVER = REPO_ROOT / "docs" / "handover" / "2026-08-29-v1.1.md"
AGENTS = REPO_ROOT / "AGENTS.md"


def test_v11_handover_document_exists_and_names_frozen_identities() -> None:
    text = HANDOVER.read_text(encoding="utf-8")
    assert "v1.1.0" in text
    assert "v1.0.0" in text
    assert "v0.9.0" in text
    assert "7fd0a28659baca56570813f3380b8223a0114f57" in text
    assert "preview_zone_plan" in text
    assert "Streamable HTTP" in text
    assert "daily_inbound_mass_kg" in text or "五个" in text
    assert "cold_room_zone_plan@1.0.0" in text
    assert "AILY_OUTBOUND_LIVE_SESSION=NO" in text
    assert "禁止移动" in text


def test_agents_md_points_at_v11_release_identity() -> None:
    text = AGENTS.read_text(encoding="utf-8")
    assert "docs/handover/2026-08-29-v1.1.md" in text
    assert "docs/handover/2026-08-28-v1.0.md" in text
    assert "v1.1.0" in text
    assert "v1.0.0" in text
    assert "Do not move" in text
