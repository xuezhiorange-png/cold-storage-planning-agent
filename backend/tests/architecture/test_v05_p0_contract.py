"""Architecture tests for V0.5 P0 five-stage workbench contract.

Enforces the frozen contract in
``docs/tasks/V0_5-P0-five-stage-workbench-contract.md`` without introducing
engineering formula values or changing application behavior.

Contract authority SHA: ``eec12b9d1ee956ce9f02e8c92bec32dfcf31308f``.
"""

from __future__ import annotations

import re
from pathlib import Path

from cold_storage.modules.orchestration.domain.dag import (
    CALCULATOR_BINDINGS,
    ORCHESTRATION_STAGE_ORDER,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V0_5-P0-five-stage-workbench-contract.md"

FROZEN_STAGE_ORDER: tuple[str, ...] = (
    "zone",
    "cooling_load",
    "equipment",
    "power",
    "investment",
)

FROZEN_CALCULATOR_IDENTITIES: dict[str, str] = {
    "zone": "cold_room_zone_plan",
    "cooling_load": "cooling_load",
    "equipment": "equipment",
    "power": "installed_power",
    "investment": "investment_estimate",
}

# Patterns that would indicate engineering formula values leaked into tests.
_ENGINEERING_VALUE_PATTERNS = (
    re.compile(r"\b\d+\.?\d*\s*kW\b", re.IGNORECASE),
    re.compile(r"\butilization_factor\s*=\s*0\.\d+"),
    re.compile(r"\breserve_factor\s*=\s*0\.\d+"),
    re.compile(r"\b\d{2,}_\d{3}\b"),  # grouped numeric literals
)


def _read_contract() -> str:
    assert CONTRACT_PATH.is_file(), f"P0 contract missing: {CONTRACT_PATH}"
    return CONTRACT_PATH.read_text(encoding="utf-8")


def test_orchestration_stage_order_is_exactly_five_frozen_stages() -> None:
    """ORCHESTRATION_STAGE_ORDER must match the frozen five-stage chain."""
    assert len(ORCHESTRATION_STAGE_ORDER) == 5
    assert ORCHESTRATION_STAGE_ORDER == FROZEN_STAGE_ORDER


def test_calculator_bindings_contain_five_canonical_identities() -> None:
    """CALCULATOR_BINDINGS must map each stage to its canonical calculator."""
    assert set(CALCULATOR_BINDINGS.keys()) == set(FROZEN_STAGE_ORDER)
    for stage, calculator_name in FROZEN_CALCULATOR_IDENTITIES.items():
        assert CALCULATOR_BINDINGS[stage] == calculator_name


def test_power_configuration_is_not_canonical_power_binding() -> None:
    """power_configuration must never satisfy the canonical power stage slot."""
    assert CALCULATOR_BINDINGS["power"] == "installed_power"
    assert CALCULATOR_BINDINGS["power"] != "power_configuration"
    for stage_name, calculator_name in CALCULATOR_BINDINGS.items():
        if stage_name != "power":
            assert calculator_name != "power_configuration", (
                f"power_configuration must not appear on stage {stage_name!r}"
            )


def test_p0_contract_documents_fail_closed_and_no_auto_feed() -> None:
    """Contract must freeze fail-closed, no-auto-feed, and auth boundaries."""
    contract = _read_contract()
    required_fragments = (
        "MISSING_ENGINEERING_PARAMETER",
        "ZONE_AREA_TO_COOLING_LOAD_AUTO_FEED=NO",
        "POWER_CONFIGURATION_TO_INSTALLED_POWER_AUTO_FEED=NO",
        "V05_P1_IMPLEMENTATION_AUTHORIZED=NO",
        "MERGE_AUTHORIZED=NO",
        "TAG_PUBLICATION_AUTHORIZED=NO",
        "RELEASE_PUBLICATION_AUTHORIZED=NO",
        "power_configuration",
        "installed_power",
        "Reports MUST read persisted calculation results",
    )
    for fragment in required_fragments:
        assert fragment in contract, f"P0 contract missing required fragment: {fragment!r}"


def test_p0_contract_documents_atomicity_idempotency_and_lineage() -> None:
    """Contract must document atomic commit, idempotency, and stale lineage."""
    contract = _read_contract()
    required_fragments = (
        "No partial five-stage chain is committed",
        "idempotency_key",
        "result_hash",
        "upstream_calculation_ids",
        "PROJECT_VERSION_LOCKED",
        "SQLite",
        "PostgreSQL",
        "EngineeringInputBundleV1",
    )
    for fragment in required_fragments:
        assert fragment in contract, f"P0 contract missing required fragment: {fragment!r}"


def test_p0_contract_and_tests_contain_no_engineering_formula_values() -> None:
    """Neither the contract file nor this test module may embed formula numbers."""
    this_file = Path(__file__).read_text(encoding="utf-8")
    contract = _read_contract()

    for label, content in (("contract", contract), ("test module", this_file)):
        for pattern in _ENGINEERING_VALUE_PATTERNS:
            match = pattern.search(content)
            assert match is None, (
                f"Engineering formula value pattern {pattern.pattern!r} "
                f"found in {label}: {match.group()!r}"
            )
