"""Handover document for V1.0 session continuity must stay findable."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
HANDOVER = REPO_ROOT / "docs" / "handover" / "2026-08-28-v1.0.md"
AGENTS = REPO_ROOT / "AGENTS.md"


def test_v10_handover_document_exists_and_names_frozen_identities() -> None:
    text = HANDOVER.read_text(encoding="utf-8")
    assert "v1.0.0" in text
    assert "v0.9.0" in text
    assert "daily_inbound_mass_kg" in text
    assert "cold_room_zone_plan@1.0.0" in text
    assert "AILY_LIVE_IMPLEMENTATION=NO" in text
    assert "禁止移动" in text


def test_agents_md_points_at_v10_handover() -> None:
    text = AGENTS.read_text(encoding="utf-8")
    assert "docs/handover/2026-08-28-v1.0.md" in text
    assert "v1.0.0" in text
    assert "docs/handover/2026-08-29-v1.1.md" in text
