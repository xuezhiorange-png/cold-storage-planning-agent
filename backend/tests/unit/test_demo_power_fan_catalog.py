"""Unit tests for the v05 evaporator/condenser fan demo catalog loader."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cold_storage.bootstrap.app import create_app
from cold_storage.modules.projects.application.demo_power_fan_catalog import (
    DEMO_POWER_FAN_SOURCE,
    POWER_FAN_DEMO_CATALOG_DISCLAIMER_ZH,
    demo_power_fan_manifest_path,
    fan_power_values_from_manifest,
    load_demo_power_fan_catalog,
    load_demo_power_fan_catalog_payload,
)


def test_loader_reads_v05_fan_leaves() -> None:
    catalog = load_demo_power_fan_catalog()
    assert Decimal(catalog.evaporator_fan_power_kw_e) == Decimal("10.0")
    assert Decimal(catalog.condenser_fan_power_kw_e) == Decimal("8.0")
    assert catalog.source == DEMO_POWER_FAN_SOURCE
    assert catalog.source_type == "demo"
    assert catalog.validity_status == "unverified"
    assert catalog.requires_review is True
    assert demo_power_fan_manifest_path().as_posix().endswith(DEMO_POWER_FAN_SOURCE)


def test_loader_payload_stamps_demo_honesty() -> None:
    payload = load_demo_power_fan_catalog_payload()
    assert payload["source"] == DEMO_POWER_FAN_SOURCE
    assert payload["source_type"] == "demo"
    assert payload["disclaimer_zh"] == POWER_FAN_DEMO_CATALOG_DISCLAIMER_ZH
    assert payload["evaporator_fan_power_kw_e"]["value"] == "10.0"
    assert payload["condenser_fan_power_kw_e"]["value"] == "8.0"
    assert payload["evaporator_fan_power_kw_e"]["source_type"] == "demo"
    assert "compressor_input_power_kw_e" not in payload


def test_http_demo_power_fan_catalog() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/demo/power-fan-catalog")
    assert response.status_code == 200
    payload = response.json()
    assert payload["requires_review"] is True
    assert Decimal(payload["evaporator_fan_power_kw_e"]["value"]) == Decimal("10")
    assert Decimal(payload["condenser_fan_power_kw_e"]["value"]) == Decimal("8")


def test_missing_manifest_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        demo_power_fan_manifest_path(start=tmp_path)


def test_missing_fan_leaf_fails_closed() -> None:
    with pytest.raises(ValueError, match="evaporator_fan_power_kw_e"):
        fan_power_values_from_manifest(
            {
                "engineering_input_bundle": {
                    "installed_power_inputs": {
                        "condenser_fan_power_kw_e": {"value": "8.0"},
                    }
                }
            }
        )


def test_zero_fan_leaf_fails_closed() -> None:
    with pytest.raises(ValueError, match="positive"):
        fan_power_values_from_manifest(
            {
                "engineering_input_bundle": {
                    "installed_power_inputs": {
                        "evaporator_fan_power_kw_e": {"value": "0"},
                        "condenser_fan_power_kw_e": {"value": "8.0"},
                    }
                }
            }
        )


def test_non_numeric_fan_leaf_fails_closed() -> None:
    with pytest.raises(ValueError, match="non-numeric"):
        fan_power_values_from_manifest(
            {
                "engineering_input_bundle": {
                    "installed_power_inputs": {
                        "evaporator_fan_power_kw_e": {"value": "abc"},
                        "condenser_fan_power_kw_e": {"value": "8.0"},
                    }
                }
            }
        )


def test_compressor_120_is_not_extracted_as_authority() -> None:
    values = fan_power_values_from_manifest(
        {
            "engineering_input_bundle": {
                "installed_power_inputs": {
                    "compressor_input_power_kw_e": {"value": "120.0"},
                    "evaporator_fan_power_kw_e": {"value": "10.0"},
                    "condenser_fan_power_kw_e": {"value": "8.0"},
                }
            }
        }
    )
    assert "compressor_input_power_kw_e" not in values
    assert values["evaporator_fan_power_kw_e"] == "10.0"
