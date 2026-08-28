"""Architecture tests for V1.1 P3 Aily connector transport auth."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V1_1-P3-aily-connector-auth-contract.md"
AUTH_DOC_PATH = REPO_ROOT / "docs" / "contracts" / "aily" / "v1.1" / "aily-connector-auth.v1.md"
AILY_API = REPO_ROOT / "backend" / "src" / "cold_storage" / "modules" / "aily" / "api" / "routes.py"
CONNECTOR_AUTH = (
    REPO_ROOT
    / "backend"
    / "src"
    / "cold_storage"
    / "modules"
    / "aily"
    / "application"
    / "connector_auth.py"
)
ENV_MODEL = REPO_ROOT / "backend" / "src" / "cold_storage" / "bootstrap" / "environment_model.py"
SETTINGS = REPO_ROOT / "backend" / "src" / "cold_storage" / "bootstrap" / "settings.py"
ENV_EXAMPLE = REPO_ROOT / ".env.example"


def test_v11_p3_contract_files_exist() -> None:
    assert CONTRACT_PATH.is_file()
    assert AUTH_DOC_PATH.is_file()
    assert CONNECTOR_AUTH.is_file()


def test_v11_p3_documents_transport_auth_not_rbac() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    auth_doc = AUTH_DOC_PATH.read_text(encoding="utf-8")
    assert "PRODUCTION_RBAC_CLAIM=NO" in contract
    assert "X-Aily-Connector-Key" in contract
    assert "AILY_CONNECTOR_UNAUTHORIZED" in contract
    assert "COLD_STORAGE_AILY_CONNECTOR_SHARED_SECRET" in contract
    assert "not production rbac" in auth_doc.lower()


def test_v11_p3_canonical_key_registered() -> None:
    env_text = ENV_MODEL.read_text(encoding="utf-8")
    settings_text = SETTINGS.read_text(encoding="utf-8")
    example_text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "AILY_CONNECTOR_SHARED_SECRET" in env_text
    assert "_SENSITIVE_KEYS" in env_text
    assert "aily_connector_shared_secret" in settings_text
    assert "COLD_STORAGE_AILY_CONNECTOR_SHARED_SECRET" in settings_text
    assert "COLD_STORAGE_AILY_CONNECTOR_SHARED_SECRET" in example_text
    assert "X-Aily-Connector-Key" in example_text


def test_v11_p3_api_uses_application_auth_without_calculations_import() -> None:
    api_text = AILY_API.read_text(encoding="utf-8")
    auth_text = CONNECTOR_AUTH.read_text(encoding="utf-8")
    assert "cold_storage.modules.calculations" not in api_text
    assert "connector_auth" in api_text
    assert "verify_connector_key" in api_text
    assert "hmac.compare_digest" in auth_text
    assert "AILY_CONNECTOR_UNAUTHORIZED" in auth_text
