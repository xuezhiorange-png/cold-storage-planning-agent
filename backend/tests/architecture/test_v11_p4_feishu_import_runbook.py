"""Architecture tests for V1.1 P4 Feishu custom-connector import runbook."""

from __future__ import annotations

from pathlib import Path

from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_V09_FIVE_KEY_FIELDS,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "v11-doubao-aily-connector.md"
CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V1_1-P4-feishu-import-runbook-contract.md"
OPENAPI_PATH = (
    REPO_ROOT / "docs" / "contracts" / "aily" / "v1.1" / "aily-to-system-zone-plan.openapi.yaml"
)
V07_AILY_DIR = REPO_ROOT / "docs" / "contracts" / "aily" / "v0.7"


def test_v11_p4_runbook_file_exists() -> None:
    assert RUNBOOK_PATH.is_file()
    assert CONTRACT_PATH.is_file()
    assert OPENAPI_PATH.is_file()


def test_v11_p4_runbook_documents_five_keys_and_endpoint() -> None:
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")
    for leaf in OPERATOR_V09_FIVE_KEY_FIELDS:
        assert leaf in runbook
    assert "POST /api/v1/aily/v1/zone-plan" in runbook
    assert "/api/v1/aily/v1/zone-plan" in runbook


def test_v11_p4_runbook_documents_tonne_to_kg_per_day_example() -> None:
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")
    assert "吨" in runbook
    assert "kg/day" in runbook or "kg/天" in runbook
    assert "20000" in runbook
    assert "daily_inbound_mass_kg" in runbook


def test_v11_p4_runbook_documents_markdown_table_and_review() -> None:
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")
    assert "markdown_table" in runbook
    assert "extra_tables" in runbook
    assert "requires_review" in runbook
    assert "ask_operator" in runbook


def test_v11_p4_contract_keeps_outbound_session_no() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "AILY_OUTBOUND_LIVE_SESSION=NO" in contract


def test_v11_p4_openapi_path_and_calculator_version_unchanged() -> None:
    openapi = OPENAPI_PATH.read_text(encoding="utf-8")
    assert "/api/v1/aily/v1/zone-plan" in openapi
    assert "operationId: previewZonePlan" in openapi
    assert 'calculator_version:\n          const: "1.0.0"' in openapi
    assert "five_key_flat" in openapi
    assert "tonne_unit_leaf" in openapi
    assert "missing_frozen_storage_days" in openapi
    assert "ask_operator" in openapi
    assert "missing_keys" in openapi


def test_v11_p4_v07_aily_artifacts_still_exist() -> None:
    assert V07_AILY_DIR.is_dir()
    assert (V07_AILY_DIR / "README.md").is_file()
