"""Architecture tests for V0.6 P0 five-stage report delivery contract.

Enforces the frozen contract in
``docs/tasks/V0_6-P0-five-stage-report-delivery-contract.md`` without introducing
engineering formula values or changing application behavior.

Contract authority SHA: ``06a446501b83f75ba42b3920d912d980c51d7fe5``.
"""

from __future__ import annotations

import re
from pathlib import Path

from cold_storage.modules.orchestration.domain.consumer_bindings import (
    STAGE_TO_CALCULATOR_NAME,
    SUPPLEMENTAL_ONLY_CALCULATOR_NAMES,
)
from cold_storage.modules.orchestration.domain.dag import (
    CALCULATOR_BINDINGS,
    ORCHESTRATION_STAGE_ORDER,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V0_6-P0-five-stage-report-delivery-contract.md"

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

FROZEN_REPORT_SOURCE_MAPPING: tuple[tuple[str, str, str], ...] = (
    ("cold_room_zone_plan", "throughput_result", "throughput_inventory_area"),
    ("cooling_load", "cooling_load_result", "cooling_load"),
    ("equipment", "equipment_result", "equipment_selection"),
    ("installed_power", "power_result", "electrical_and_energy"),
    ("investment_estimate", "investment_result", "investment_estimate"),
)

REQUIRED_GOVERNANCE_FLAGS: tuple[str, ...] = (
    "TASK=V06_P0_REPORT_DELIVERY_CONTRACT_DEFINITION_R1",
    "PARENT_ISSUE=176",
    "P0_TRACKING_ISSUE=180",
    "DISPATCH_ISSUE=184",
    "GOVERNANCE_OWNER=V0.6",
    "BASE_MAIN_SHA=06a446501b83f75ba42b3920d912d980c51d7fe5",
    "BASE_TREE=633c9712a5a558bc6d6df183303733d90540dc24",
    "PREVIOUS_RELEASE=v0.5.0",
    "TARGET_BRANCH=cursor/v06-p0-report-delivery-contract-6c68",
    "TARGET_PR_STATE=DRAFT",
    "CONTRACT_STATUS=DEFINITION_R1_DRAFT_FOR_INDEPENDENT_REVIEW",
    "V06_P0_IMPLEMENTATION_AUTHORIZED=YES",
    "V06_P1_IMPLEMENTATION_AUTHORIZED=NO",
    "V06_P2_IMPLEMENTATION_AUTHORIZED=NO",
    "V06_P3_IMPLEMENTATION_AUTHORIZED=NO",
    "V06_P4A_IMPLEMENTATION_AUTHORIZED=NO",
    "V06_P4B_IMPLEMENTATION_AUTHORIZED=NO",
    "V06_P5_IMPLEMENTATION_AUTHORIZED=NO",
    "READY_AUTHORIZED=NO",
    "MERGE_AUTHORIZED=NO",
    "CONTROLLED_ACCEPTANCE_EXECUTION_AUTHORIZED=NO",
    "TAG_PUBLICATION_AUTHORIZED=NO",
    "RELEASE_PUBLICATION_AUTHORIZED=NO",
    "FORMULA_RECUT_AUTHORIZED=NO",
    "COEFFICIENT_PROMOTION_AUTHORIZED=NO",
    "LIVE_MODEL_PRODUCTION_ENABLEMENT_AUTHORIZED=NO",
    "PRODUCTION_DEPLOYMENT_AUTHORIZED=NO",
    "NO_STEP_IMPLIES_THE_NEXT=TRUE",
)

KNOWN_BASELINE_GAP_FRAGMENTS: tuple[str, ...] = (
    "V06-GAP-001",
    "persisted_calculation_reads.py",
    "investment_result",
    "V06-GAP-002",
    "_REPORT_SECTIONS",
    "V06-GAP-003",
    "input_conditions",
    "assumptions",
    "V06-GAP-004",
    "V0.5 as active unfinished umbrella",
    "V06-GAP-005",
    "Issue #20 CLOSED",
)

FORBIDDEN_CONTRACT_FRAGMENTS: tuple[str, ...] = (
    "utilization_factor",
    "reserve_factor",
)

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


def _extract_allowlist_paths(contract: str, marker: str) -> set[str]:
    start = contract.index(marker)
    fence_start = contract.rfind("```", 0, start)
    fence_end = contract.index("```", start)
    block = contract[fence_start + 3 : fence_end].strip()
    if block.startswith("text"):
        block = block.split("\n", 1)[1].strip()
    paths: set[str] = set()
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped == marker:
            continue
        paths.add(stripped)
    return paths


def test_v06_p0_contract_file_exists() -> None:
    """P0 contract document must exist at the authorized path."""
    assert CONTRACT_PATH.is_file()


def test_v06_p0_contract_governance_flags_present() -> None:
    """Governance identity block must match authorized constants exactly."""
    contract = _read_contract()
    for flag in REQUIRED_GOVERNANCE_FLAGS:
        assert flag in contract, f"P0 contract missing governance flag: {flag!r}"


def test_orchestration_stage_order_is_exactly_five_frozen_stages() -> None:
    """ORCHESTRATION_STAGE_ORDER must match the frozen five-stage chain."""
    assert len(ORCHESTRATION_STAGE_ORDER) == 5
    assert ORCHESTRATION_STAGE_ORDER == FROZEN_STAGE_ORDER


def test_calculator_bindings_contain_five_canonical_identities() -> None:
    """CALCULATOR_BINDINGS must map each stage to its canonical calculator."""
    assert set(CALCULATOR_BINDINGS.keys()) == set(FROZEN_STAGE_ORDER)
    for stage, calculator_name in FROZEN_CALCULATOR_IDENTITIES.items():
        assert CALCULATOR_BINDINGS[stage] == calculator_name
        assert STAGE_TO_CALCULATOR_NAME[stage] == calculator_name


def test_power_configuration_is_not_canonical_power_binding() -> None:
    """power_configuration must never satisfy the canonical power stage slot."""
    assert CALCULATOR_BINDINGS["power"] == "installed_power"
    assert CALCULATOR_BINDINGS["power"] != "power_configuration"
    assert "power_configuration" in SUPPLEMENTAL_ONLY_CALCULATOR_NAMES
    for stage_name, calculator_name in CALCULATOR_BINDINGS.items():
        if stage_name != "power":
            assert calculator_name != "power_configuration", (
                f"power_configuration must not appear on stage {stage_name!r}"
            )


def test_v06_p0_contract_documents_five_row_report_source_mapping() -> None:
    """Contract must freeze all five persisted-calculator to report-section rows."""
    contract = _read_contract()
    for calculator, attr, section in FROZEN_REPORT_SOURCE_MAPPING:
        assert calculator in contract, f"Mapping missing calculator: {calculator!r}"
        assert attr in contract, f"Mapping missing attr: {attr!r}"
        assert section in contract, f"Mapping missing section: {section!r}"
    assert "investment_result" in contract
    assert "investment_estimate" in contract


def test_v06_p0_contract_documents_input_and_assumption_rules() -> None:
    """Contract must freeze input_conditions and assumptions authority rules."""
    contract = _read_contract()
    required_fragments = (
        "EngineeringInputBundleV1",
        "input_conditions",
        "assumptions",
        "source_result_id",
        "source_tool",
        "source_tool_version",
        "calculation_id",
        "result_hash",
        "calculator_version",
        "MISSING_CANONICAL_SOURCE",
        "REPORT_QUALITY_BLOCKER",
        "Reports MUST NOT recalculate formulas",
        "templates MUST NOT embed formulas",
    )
    for fragment in required_fragments:
        assert fragment in contract, f"P0 contract missing required fragment: {fragment!r}"


def test_v06_p0_contract_documents_fail_closed_and_review_lifecycle() -> None:
    """Contract must freeze review/formal-export and fail-closed lifecycle."""
    contract = _read_contract()
    required_fragments = (
        "FORMAL_EXPORT_STATUSES",
        "requires_review=true",
        "mark_reviewed",
        "high_throughput_review",
        "content_hash",
        "template version",
        "locale",
        "source provenance",
        "V06_P1_IMPLEMENTATION_AUTHORIZED=NO",
        "MERGE_AUTHORIZED=NO",
        "TAG_PUBLICATION_AUTHORIZED=NO",
        "RELEASE_PUBLICATION_AUTHORIZED=NO",
        "FORMULA_RECUT_AUTHORIZED=NO",
        "COEFFICIENT_PROMOTION_AUTHORIZED=NO",
        "LIVE_MODEL_PRODUCTION_ENABLEMENT_AUTHORIZED=NO",
        "PRODUCTION_DEPLOYMENT_AUTHORIZED=NO",
        "AGENT_TO_ENGINEERING_VALUE=NO",
        "power_configuration",
        "installed_power",
    )
    for fragment in required_fragments:
        assert fragment in contract, f"P0 contract missing required fragment: {fragment!r}"


def test_v06_p0_contract_records_known_baseline_gaps() -> None:
    """Known baseline gaps must be recorded as gaps, not completed work."""
    contract = _read_contract()
    for fragment in KNOWN_BASELINE_GAP_FRAGMENTS:
        assert fragment in contract, f"Baseline gap documentation missing: {fragment!r}"
    assert "V06-GAP-001" in contract
    assert "P0 does not fix" in contract or "does not fix" in contract


def test_v06_p0_p1_and_p2_allowlists_are_parseable_and_disjoint() -> None:
    """P1 and P2 file allowlists must parse from contract and not overlap."""
    contract = _read_contract()
    p1_paths = _extract_allowlist_paths(contract, "V06_P1_FILE_ALLOWLIST")
    p2_paths = _extract_allowlist_paths(contract, "V06_P2_FILE_ALLOWLIST")
    assert len(p1_paths) >= 5, f"P1 allowlist too small: {p1_paths!r}"
    assert len(p2_paths) >= 4, f"P2 allowlist too small: {p2_paths!r}"
    overlap = p1_paths & p2_paths
    assert not overlap, f"P1/P2 allowlists overlap: {sorted(overlap)!r}"


def test_v06_p0_contract_documents_issue_mapping() -> None:
    """Issue #20 closed must be recorded; later-closure issues remain open."""
    contract = _read_contract()
    assert "Issue #20" in contract
    assert "CLOSED" in contract
    for issue_ref in ("#11", "#13", "#17", "#72"):
        assert issue_ref in contract, f"Issue mapping missing {issue_ref!r}"
    assert "Close later" in contract or "close later" in contract


def test_v06_p0_contract_documents_sqlite_postgresql_and_api_compat() -> None:
    """Contract must document DB parity and API compatibility."""
    contract = _read_contract()
    required_fragments = (
        "SQLite",
        "PostgreSQL",
        "five-stage-execution",
        "no new required breaking fields",
    )
    for fragment in required_fragments:
        assert fragment in contract, f"P0 contract missing required fragment: {fragment!r}"


def test_v06_p0_contract_and_tests_contain_no_engineering_formula_values() -> None:
    """Neither the contract file nor this test module may embed formula numbers."""
    this_file = Path(__file__).read_text(encoding="utf-8")
    contract = _read_contract()

    for label, content in (("contract", contract), ("test module", this_file)):
        if label == "contract":
            for fragment in FORBIDDEN_CONTRACT_FRAGMENTS:
                assert fragment not in content, (
                    f"Forbidden engineering fragment {fragment!r} found in {label}"
                )
        for pattern in _ENGINEERING_VALUE_PATTERNS:
            match = pattern.search(content)
            assert match is None, (
                f"Engineering formula value pattern {pattern.pattern!r} "
                f"found in {label}: {match.group()!r}"
            )
