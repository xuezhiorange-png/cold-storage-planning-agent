"""Architecture tests for V0.7 P0 data and logic trust-loop contract.

Enforces the frozen contract in
``docs/tasks/V0_7-P0-trust-loop-contract.md`` without introducing
engineering formula values or changing application behavior.

Contract authority SHA: ``f8a4b80a8a8fab26113b57d9f4ea666b8bc699ba``.
"""

from __future__ import annotations

import re
from itertools import combinations
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
CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V0_7-P0-trust-loop-contract.md"

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
    "TASK=V07_P0_TRUST_LOOP_CONTRACT_DEFINITION_R1",
    "PARENT_ISSUE=PENDING",
    "P0_TRACKING_ISSUE=PENDING",
    "DISPATCH_ISSUE=PENDING",
    "GOVERNANCE_OWNER=V0.7",
    "BASE_MAIN_SHA=f8a4b80a8a8fab26113b57d9f4ea666b8bc699ba",
    "BASE_TREE=23af6e60e4247394b2b12c50440d5fc03a819074",
    "PREVIOUS_RELEASE=v0.6.0",
    "TARGET_BRANCH=cursor/v07-p0-trust-loop-contract-6c68",
    "TARGET_PR_STATE=DRAFT",
    "CONTRACT_STATUS=DEFINITION_R1_DRAFT_FOR_INDEPENDENT_REVIEW",
    "V07_P0_IMPLEMENTATION_AUTHORIZED=YES",
    "V07_P1_IMPLEMENTATION_AUTHORIZED=NO",
    "V07_P2_IMPLEMENTATION_AUTHORIZED=NO",
    "V07_P3A_IMPLEMENTATION_AUTHORIZED=NO",
    "V07_P3B_IMPLEMENTATION_AUTHORIZED=NO",
    "V07_P4_IMPLEMENTATION_AUTHORIZED=NO",
    "V07_P5_IMPLEMENTATION_AUTHORIZED=NO",
    "V07_P6_IMPLEMENTATION_AUTHORIZED=NO",
    "V07_P7_IMPLEMENTATION_AUTHORIZED=NO",
    "READY_AUTHORIZED=NO",
    "MERGE_AUTHORIZED=NO",
    "CONTROLLED_ACCEPTANCE_EXECUTION_AUTHORIZED=NO",
    "TAG_PUBLICATION_AUTHORIZED=NO",
    "RELEASE_PUBLICATION_AUTHORIZED=NO",
    "FORMULA_RECUT_AUTHORIZED=NO",
    "COEFFICIENT_PROMOTION_AUTHORIZED=NO",
    "DEMO_COEFFICIENT_CONFLICT_RESOLUTION=NO",
    "LIVE_MODEL_PRODUCTION_ENABLEMENT_AUTHORIZED=NO",
    "AILY_LIVE_IMPLEMENTATION=NO",
    "PRODUCTION_DEPLOYMENT_AUTHORIZED=NO",
    "NO_STEP_IMPLIES_THE_NEXT=TRUE",
)

KNOWN_BASELINE_GAP_FRAGMENTS: tuple[str, ...] = (
    "V07-GAP-001",
    "_get_report_service",
    "project_summary",
    "V07-GAP-002",
    "source_mode=production",
    "scheme_comparison",
    "V07-GAP-003",
    "Surface A",
    "V07-GAP-004",
    "EngineeringInputBundleV1",
    "V07-GAP-005",
    "result_hash",
    "V07-GAP-006",
    "V07-GAP-007",
    "V07-GAP-008",
    "V07-GAP-009",
    "V07-GAP-010",
    "requires_review=true",
)

FORBIDDEN_CONTRACT_FRAGMENTS: tuple[str, ...] = (
    "utilization_factor",
    "reserve_factor",
)

WAVE1_ALLOWLIST_MARKERS: tuple[str, ...] = (
    "V07_P1_FILE_ALLOWLIST",
    "V07_P2_FILE_ALLOWLIST",
    "V07_P3A_FILE_ALLOWLIST",
    "V07_P3B_FILE_ALLOWLIST",
    "V07_P6_FILE_ALLOWLIST",
)

P0_EXISTING_ALLOWLIST_PATHS: tuple[str, ...] = (
    "docs/tasks/V0_7-P0-trust-loop-contract.md",
    "docs/audit/current-state.md",
    "docs/audit/gap-analysis.md",
    "docs/audit/validation-baseline.md",
    "docs/TECH_DEBT.md",
    "docs/roadmap/DEVELOPMENT_PLAN.md",
    "backend/tests/architecture/test_v07_p0_contract.py",
)

_ENGINEERING_VALUE_PATTERNS = (
    re.compile(r"\b\d+\.?\d*\s*kW\b", re.IGNORECASE),
    re.compile(r"\butilization_factor\s*=\s*0\.\d+"),
    re.compile(r"\breserve_factor\s*=\s*0\.\d+"),
    re.compile(r"\b\d{2,}_\d{3}\b"),
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


def test_v07_p0_contract_file_exists() -> None:
    """P0 contract document must exist at the authorized path."""
    assert CONTRACT_PATH.is_file()


def test_v07_p0_contract_governance_flags_present() -> None:
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


def test_v07_p0_contract_documents_inherited_report_source_mapping() -> None:
    """Contract must keep the V0.6 five-row persisted-calculator mapping."""
    contract = _read_contract()
    for calculator, attr, section in FROZEN_REPORT_SOURCE_MAPPING:
        assert calculator in contract, f"Mapping missing calculator: {calculator!r}"
        assert attr in contract, f"Mapping missing attr: {attr!r}"
        assert section in contract, f"Mapping missing section: {section!r}"
    assert "investment_result" in contract
    assert "investment_estimate" in contract
    assert "EngineeringInputBundleV1" in contract
    assert "Reports MUST NOT recalculate formulas" in contract
    assert "templates MUST NOT embed formulas" in contract


def test_v07_p0_contract_records_known_baseline_gaps() -> None:
    """Known remaining gaps must be recorded as gaps, not completed work."""
    contract = _read_contract()
    for fragment in KNOWN_BASELINE_GAP_FRAGMENTS:
        assert fragment in contract, f"Baseline gap documentation missing: {fragment!r}"
    assert "P0 does not fix" in contract or "does not fix" in contract


def test_v07_p0_wave1_allowlists_are_parseable_and_disjoint() -> None:
    """Wave 1 exclusive allowlists must parse from the contract and not overlap."""
    contract = _read_contract()
    parsed: dict[str, set[str]] = {
        marker: _extract_allowlist_paths(contract, marker) for marker in WAVE1_ALLOWLIST_MARKERS
    }
    for marker, paths in parsed.items():
        assert len(paths) >= 3, f"{marker} too small: {paths!r}"

    for left, right in combinations(WAVE1_ALLOWLIST_MARKERS, 2):
        overlap = parsed[left] & parsed[right]
        assert not overlap, f"{left} overlaps {right}: {sorted(overlap)!r}"

    p3a = parsed["V07_P3A_FILE_ALLOWLIST"]
    p3b = parsed["V07_P3B_FILE_ALLOWLIST"]
    assert "backend/src/cold_storage/bootstrap/app.py" in p3a
    assert "backend/src/cold_storage/bootstrap/app.py" not in p3b
    assert "backend/src/cold_storage/modules/schemes/api/routes.py" in p3b
    assert "backend/src/cold_storage/modules/schemes/api/routes.py" not in p3a
    assert "docs/contracts/aily/v0.7/**" in parsed["V07_P6_FILE_ALLOWLIST"]


def test_v07_p0_allowlist_existing_files_are_present() -> None:
    """P0 allowlist paths that should already exist must be on disk."""
    contract = _read_contract()
    p0_paths = _extract_allowlist_paths(contract, "V07_P0_FILE_ALLOWLIST")
    for path in P0_EXISTING_ALLOWLIST_PATHS:
        assert path in p0_paths, f"P0 allowlist missing {path!r}"
        assert (REPO_ROOT / path).is_file(), f"P0 allowlist file missing on disk: {path!r}"


def test_v07_p0_contract_documents_aily_boundary_and_expert_decisions() -> None:
    """Aily boundary and expert-decision register must be frozen."""
    contract = _read_contract()
    required_fragments = (
        "AILY_LIVE_IMPLEMENTATION=NO",
        "planning_context.get",
        "engineering_inputs.validate",
        "five_stage_execution.propose",
        "report_delivery.propose",
        "AGENT_TO_ENGINEERING_VALUE=NO",
        "PRODUCTION_RBAC_CLAIM=NO",
        "E1",
        "E11",
        "frozen_fruit_ratio",
        "mark_reviewed",
    )
    for fragment in required_fragments:
        assert fragment in contract, f"P0 contract missing required fragment: {fragment!r}"


def test_v07_p0_contract_documents_issue_mapping() -> None:
    """Issue #20 closed must be recorded; later-closure issues remain open."""
    contract = _read_contract()
    assert "Issue #20" in contract or "#20" in contract
    assert "CLOSED" in contract
    for issue_ref in ("#11", "#13", "#17", "#176"):
        assert issue_ref in contract, f"Issue mapping missing {issue_ref!r}"
    assert "Close later" in contract or "close later" in contract or "Remains open" in contract


def test_v07_p0_contract_documents_sqlite_postgresql_and_fail_closed() -> None:
    """Contract must document DB parity and fail-closed operator semantics."""
    contract = _read_contract()
    required_fragments = (
        "SQLite",
        "PostgreSQL",
        "five-stage-execution",
        "FORMAL_EXPORT_STATUSES",
        "requires_review=true",
        "fail-closed",
        "create_app",
    )
    for fragment in required_fragments:
        assert fragment in contract, f"P0 contract missing required fragment: {fragment!r}"


def test_v07_p0_living_docs_record_v07_umbrella() -> None:
    """Living docs must point at V0.7 without reopening delivered V0.6 mapping gaps."""
    living_docs = (
        REPO_ROOT / "docs" / "audit" / "current-state.md",
        REPO_ROOT / "docs" / "audit" / "gap-analysis.md",
        REPO_ROOT / "docs" / "audit" / "validation-baseline.md",
        REPO_ROOT / "docs" / "TECH_DEBT.md",
        REPO_ROOT / "docs" / "roadmap" / "DEVELOPMENT_PLAN.md",
    )
    for path in living_docs:
        text = path.read_text(encoding="utf-8")
        assert "V0.7" in text, f"{path} missing V0.7 truth-up"
        assert "v0.6.0" in text, f"{path} missing v0.6.0 baseline"
        assert "V0_7-P0-trust-loop-contract.md" in text, f"{path} missing P0 contract pointer"


def test_v07_p0_package_dag_is_frozen() -> None:
    """Wave DAG and P3A/P3B split must be explicit."""
    contract = _read_contract()
    assert "P0 → (P1 || P2 || P3A || P3B || P6) → (P4 || P5) → P7" in contract
    assert "P3A" in contract
    assert "P3B" in contract
    assert "production-scheme-runs" in contract


def test_v07_p0_contract_and_tests_contain_no_engineering_formula_values() -> None:
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
