"""Architecture tests for V1.1 P2 static 豆包工作伙伴 skill pack contract."""

from __future__ import annotations

import json
import re
from pathlib import Path

from cold_storage.modules.calculations.domain.zone_planning import VERSION
from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_V09_FIVE_KEY_FIELDS,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V1_1-P2-doubao-skill-contract.md"
ADR_PATH = REPO_ROOT / "docs" / "architecture" / "ADR-032-doubao-skill-pack.md"
SKILL_MD_PATH = REPO_ROOT / "docs" / "contracts" / "aily" / "v1.1" / "doubao-skill.v1.md"
SKILL_JSON_PATH = REPO_ROOT / "docs" / "contracts" / "aily" / "v1.1" / "doubao-skill.v1.json"
OPERATOR_PAYLOAD_PATH = (
    REPO_ROOT
    / "backend"
    / "src"
    / "cold_storage"
    / "modules"
    / "aily"
    / "application"
    / "operator_payload.py"
)

_ENGINEERING_FORMULA_PATTERNS = (
    re.compile(r"面积\s*=", re.IGNORECASE),
    re.compile(r"\*\s*620"),
    re.compile(r"\b\d+\s*m²\b", re.IGNORECASE),
    re.compile(r"\b\d+\.?\d*\s*kW\b", re.IGNORECASE),
)


def _read_skill_md() -> str:
    assert SKILL_MD_PATH.is_file(), f"P2 skill markdown missing: {SKILL_MD_PATH}"
    return SKILL_MD_PATH.read_text(encoding="utf-8")


def _read_skill_json() -> dict:
    assert SKILL_JSON_PATH.is_file(), f"P2 skill JSON missing: {SKILL_JSON_PATH}"
    return json.loads(SKILL_JSON_PATH.read_text(encoding="utf-8"))


def test_v11_p2_contract_files_exist() -> None:
    assert CONTRACT_PATH.is_file()
    assert ADR_PATH.is_file()
    assert SKILL_MD_PATH.is_file()
    assert SKILL_JSON_PATH.is_file()


def test_v11_p2_five_key_field_names_present() -> None:
    skill_md = _read_skill_md()
    skill_json = _read_skill_json()
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    json_fields = {entry["field"] for entry in skill_json["operator_keys"]}

    for field_name in OPERATOR_V09_FIVE_KEY_FIELDS:
        assert field_name in skill_md
        assert field_name in contract
        assert field_name in json_fields


def test_v11_p2_tonne_means_per_day() -> None:
    skill_md = _read_skill_md()
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    skill_json = _read_skill_json()

    assert skill_json["semantics"]["tonne_means"] == "per_day"
    for fragment in (
        "吨 = 每天",
        "吨/天",
        "吨 always means per day",
        "每天",
    ):
        assert fragment in skill_md or fragment in contract


def test_v11_p2_doubao_owns_nlp_system_does_not_parse_chat() -> None:
    skill_md = _read_skill_md()
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    skill_json = _read_skill_json()
    payload_text = OPERATOR_PAYLOAD_PATH.read_text(encoding="utf-8")

    assert skill_json["semantics"]["nlp_owner"] == "doubao"
    assert skill_json["semantics"]["system_parses_chat"] is False
    assert "豆包 owns" in contract or "豆包 owns semantics" in contract
    assert "does not parse chat" in contract
    assert "does not parse chat" in payload_text
    assert "本系统不解析" in skill_md or "不传聊天原文" in skill_md


def test_v11_p2_governance_flags() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    skill_md = _read_skill_md()
    skill_json = _read_skill_json()

    assert "AILY_OUTBOUND_LIVE_SESSION=NO" in contract
    assert "AILY_OUTBOUND_LIVE_SESSION=NO" in skill_md
    assert skill_json["governance"]["AILY_OUTBOUND_LIVE_SESSION"] == "NO"
    assert "DO_NOT_BUMP_ZONE_PLAN_VERSION=YES" in contract
    assert "AGENT_TO_ENGINEERING_VALUE=NO" in contract


def test_v11_p2_keeps_cold_room_zone_plan_version() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    skill_md = _read_skill_md()
    skill_json = _read_skill_json()

    assert VERSION == "1.0.0"
    assert "cold_room_zone_plan@1.0.0" in contract
    assert "cold_room_zone_plan@1.0.0" in skill_md
    assert skill_json["calculator_identity"]["version"] == "1.0.0"


def test_v11_p2_posts_zone_plan_endpoint() -> None:
    skill_md = _read_skill_md()
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    skill_json = _read_skill_json()

    endpoint = "POST /api/v1/aily/v1/zone-plan"
    assert endpoint in skill_md
    assert endpoint in contract
    assert skill_json["endpoint"]["path"] == "/api/v1/aily/v1/zone-plan"
    assert skill_json["endpoint"]["method"] == "POST"


def test_v11_p2_skill_has_no_engineering_formulas() -> None:
    skill_md = _read_skill_md()
    for pattern in _ENGINEERING_FORMULA_PATTERNS:
        match = pattern.search(skill_md)
        assert match is None, (
            f"Skill text must not contain engineering formula pattern "
            f"{pattern.pattern!r}: {match.group()!r} if match"
        )


def test_v11_p2_no_mark_reviewed_as_doubao_tool() -> None:
    skill_md = _read_skill_md()
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    skill_json = _read_skill_json()

    assert "MARK_REVIEWED_AS_MODEL_TOOL=NO" in contract
    assert "mark_reviewed" in skill_json["forbidden_model_tools"]
    assert "mark_reviewed" not in skill_md.lower().split("禁止")[0] or (
        "禁止" in skill_md and "mark_reviewed" in skill_md
    )
    # Skill may mention mark_reviewed only in forbidden context
    if "mark_reviewed" in skill_md:
        assert "禁止" in skill_md or "不得" in skill_md


def test_v11_p2_uses_operator_key_ask_labels() -> None:
    skill_md = _read_skill_md()
    payload_text = OPERATOR_PAYLOAD_PATH.read_text(encoding="utf-8")

    for label in (
        "每天进货量（公斤/天；1吨/天=1000公斤/天）",
        "成品存放天数",
        "冻果存放天数",
        "主包材存放天数",
        "辅包材存放天数",
    ):
        assert label in payload_text
        assert label in skill_md


def test_v11_p2_ton_conversion_before_post() -> None:
    skill_md = _read_skill_md()
    skill_json = _read_skill_json()

    assert "× 1000" in skill_md or "×1000" in skill_md or "multiply_by" in str(skill_json)
    mass_key = next(k for k in skill_json["operator_keys"] if k["field"] == "daily_inbound_mass_kg")
    assert mass_key["conversion"]["multiply_by"] == 1000


def test_v11_p2_response_handling_and_disclaimer() -> None:
    skill_md = _read_skill_md()
    skill_json = _read_skill_json()

    assert "markdown_table" in skill_md
    assert "extra_tables" in skill_md
    assert "ask_operator" in skill_md
    assert "missing_keys" in skill_md
    assert "概念设计" in skill_md
    assert "复核" in skill_md
    assert "施工图" in skill_md
    assert skill_json["response_handling"]["display_fields"] == ["markdown_table", "extra_tables"]
