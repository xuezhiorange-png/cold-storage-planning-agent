"""Unit coverage for the V2.1 factory-power Aily preview composition."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

import pytest

import cold_storage.modules.aily.application.factory_power_preview as preview_module
from cold_storage.modules.aily.application.factory_power_preview import (
    preview_factory_power,
)
from cold_storage.modules.aily.application.factory_power_table import (
    project_factory_power_table,
)
from cold_storage.modules.aily.application.preview_bundle import assemble_preview_context
from cold_storage.modules.aily.application.stage_preview import execute_zone_preview_authority
from cold_storage.modules.aily.domain.errors import AilyConnectorError
from cold_storage.modules.calculations.domain.factory_power_estimation import (
    FactoryPowerEstimationError,
    serialize_factory_power_result,
)
from cold_storage.modules.projects.application.factory_power_upstream_authority import (
    FactoryPowerUpstreamAuthorityError,
    calculate_factory_power_from_zone_plan,
)

_FIVE_KEYS: dict[str, Any] = {
    "daily_inbound_mass_kg": 20000,
    "finished_storage_days": 7,
    "frozen_storage_days": 10,
    "main_packaging_storage_days": 4,
    "auxiliary_packaging_storage_days": 12,
}
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def test_factory_power_preview_returns_shared_projected_result_and_markdown() -> None:
    body = preview_factory_power(_FIVE_KEYS, correlation_id="p2-unit")

    assert body["reply_kind"] == "factory_power_estimation_table"
    assert body["available"] is True
    assert body["calculator_name"] == "factory_power_estimation"
    assert body["calculator_version"] == "2.0.0-p2"
    assert body["calculator_identity"] == "factory_power_estimation@2.0.0-p2"
    assert _HASH_PATTERN.fullmatch(str(body["canonical_result_hash"]))
    assert body["requires_review"] is True
    assert body["persisted"] is False
    assert body["unit_semantics"]["power_unit"] == "kW"
    assert body["details"]
    assert body["summary"]
    assert body["table"]["rows"] == body["details"]
    assert body["markdown_table"]
    assert set(body["operator_keys"]) == set(_FIVE_KEYS)
    assert "factory_area_m2" not in body["operator_keys"]
    assert "cold_storage_area_m2" not in body["operator_keys"]


@pytest.mark.parametrize(
    "unexpected_key",
    [
        "factory_area_m2",
        "cold_storage_area_m2",
        "refrigerated_area_m2",
        "total_area_m2",
        "fake_area",
        "zone_plan",
        "chat_text",
    ],
)
def test_factory_power_preview_rejects_unknown_and_area_inputs(
    unexpected_key: str,
) -> None:
    payload = dict(_FIVE_KEYS)
    payload[unexpected_key] = 9999

    with pytest.raises(AilyConnectorError) as exc_info:
        preview_factory_power(payload)

    assert exc_info.value.code == "MCP_INPUT_SCHEMA_REJECTED"
    assert exc_info.value.missing_keys == ()
    assert exc_info.value.ask_operator == ""
    assert unexpected_key in exc_info.value.details["unexpected_keys"]


def test_factory_power_preview_preserves_missing_business_key_ask() -> None:
    payload = dict(_FIVE_KEYS)
    del payload["frozen_storage_days"]

    with pytest.raises(AilyConnectorError) as exc_info:
        preview_factory_power(payload)

    assert exc_info.value.code == "MISSING_ENGINEERING_PARAMETER"
    assert exc_info.value.missing_keys == ("frozen_storage_days",)
    assert "冻果存放天数" in exc_info.value.ask_operator
    assert "factory_area_m2" not in exc_info.value.ask_operator
    assert "cold_storage_area_m2" not in exc_info.value.ask_operator


def test_factory_power_preview_has_exact_canonical_parity_with_direct_p1_path() -> None:
    body = preview_factory_power(_FIVE_KEYS, correlation_id="mcp-parity")
    context = assemble_preview_context(_FIVE_KEYS, correlation_id="direct-parity")
    zone_result = execute_zone_preview_authority(context)
    zone_snapshot = preview_module._zone_plan_snapshot(zone_result)
    direct_result = calculate_factory_power_from_zone_plan(zone_snapshot)
    direct_projected = project_factory_power_table(serialize_factory_power_result(direct_result))

    assert body["canonical_result_hash"] == direct_projected["canonical_result_hash"]
    assert body["details"] == direct_projected["details"]
    assert body["summary"] == direct_projected["summary"]
    assert body["unit_semantics"] == direct_projected["unit_semantics"]
    assert body["review"] == direct_projected["review"]
    assert body["provenance"] == direct_projected["provenance"]
    assert body["assumptions"] == direct_projected["assumptions"]


def test_factory_power_preview_is_deterministic_across_correlation_ids() -> None:
    first = preview_factory_power(_FIVE_KEYS, correlation_id="first")
    second = preview_factory_power(_FIVE_KEYS, correlation_id="second")

    assert first["canonical_result_hash"] == second["canonical_result_hash"]
    assert first["details"] == second["details"]
    assert first["summary"] == second["summary"]
    assert first["factory_area_band"] == second["factory_area_band"]


@pytest.mark.parametrize(
    "error",
    [
        FactoryPowerUpstreamAuthorityError(
            "FACTORY_AREA_TOTAL_MISMATCH",
            "zone-plan total area does not match the exact zone-row sum",
            {"expected": "2500.00", "actual": "9999"},
        ),
        FactoryPowerEstimationError(
            "MISSING_MINIMUM_ESTIMATED_COOLING_LOAD_KW_R",
            "minimum cooling load is required",
            {"zone_code": "raw_fruit_buffer"},
        ),
    ],
)
def test_factory_power_preview_preserves_backend_authority_error(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    def fail(_: object) -> object:
        raise error

    monkeypatch.setattr(preview_module, "calculate_factory_power_from_zone_plan", fail)

    with pytest.raises(AilyConnectorError) as exc_info:
        preview_factory_power(_FIVE_KEYS)

    assert exc_info.value.code == error.code  # type: ignore[attr-defined]
    assert exc_info.value.message == str(error)
    assert dict(exc_info.value.details) == dict(error.details)  # type: ignore[attr-defined]
    assert exc_info.value.missing_keys == ()
    assert exc_info.value.ask_operator == ""


def test_factory_power_preview_fails_closed_when_projector_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        preview_module,
        "project_factory_power_table",
        lambda _source: {
            "available": False,
            "reply_kind": "factory_power_estimation_unavailable",
        },
    )

    with pytest.raises(AilyConnectorError) as exc_info:
        preview_factory_power(_FIVE_KEYS)

    assert exc_info.value.code == "V20_FACTORY_POWER_CANONICAL_RESULT_UNAVAILABLE"
    assert exc_info.value.missing_keys == ()
    assert exc_info.value.ask_operator == ""


def test_markdown_is_a_copy_of_projector_table_cells() -> None:
    body = preview_factory_power(_FIVE_KEYS)
    table = deepcopy(body["table"])
    columns = table["columns"]
    rows = table["rows"]
    lines = body["markdown_table"].splitlines()

    assert lines[0] == "| " + " | ".join(column["label"] for column in columns) + " |"
    for row, line in zip(rows, lines[2:], strict=True):
        expected_cells = [
            "—" if row[column["key"]] is None else str(row[column["key"]]) for column in columns
        ]
        assert line == "| " + " | ".join(expected_cells) + " |"
