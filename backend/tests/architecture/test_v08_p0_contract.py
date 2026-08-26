"""Architecture tests for V0.8 P0 operator-minimal process-input contract.

Enforces the frozen contract in
``docs/tasks/V0_8-P0-operator-minimal-input-contract.md`` without introducing
engineering formula values or changing application behavior.

Contract authority SHA: ``0330d9be36db94a62190d5775612b361fff6da8d``.
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
CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V0_8-P0-operator-minimal-input-contract.md"
ADR_PATH = REPO_ROOT / "docs" / "architecture" / "ADR-028-operator-minimal-process-input.md"

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

OPERATOR_FIVE_KEY_LEAVES: tuple[str, ...] = (
    "zone_planning_inputs.daily_inbound_mass_kg",
    "zone_planning_inputs.working_time_h_per_day",
    "zone_planning_inputs.finished_storage_days",
    "zone_planning_inputs.packaging_storage_days",
    "zone_planning_inputs.precooling_required_ratio",
)

REQUIRED_GOVERNANCE_FLAGS: tuple[str, ...] = (
    "TASK=V08_P0_OPERATOR_MINIMAL_INPUT_CONTRACT_DEFINITION_R1",
    "PARENT_ISSUE=PENDING",
    "P0_TRACKING_ISSUE=PENDING",
    "DISPATCH_ISSUE=PENDING",
    "GOVERNANCE_OWNER=V0.8",
    "BASE_MAIN_SHA=0330d9be36db94a62190d5775612b361fff6da8d",
    "BASE_TREE=7bfcb0dcd88390ec196f67290a5e1cf363703c16",
    "PREVIOUS_RELEASE=v0.7.0",
    "TARGET_BRANCH=cursor/v08-p0-operator-minimal-input-6c68",
    "TARGET_PR_STATE=DRAFT",
    "CONTRACT_STATUS=DEFINITION_R1_DRAFT_FOR_INDEPENDENT_REVIEW",
    "V08_P0_IMPLEMENTATION_AUTHORIZED=YES",
    "V08_P1_IMPLEMENTATION_AUTHORIZED=NO",
    "V08_P2_IMPLEMENTATION_AUTHORIZED=NO",
    "V08_P3_IMPLEMENTATION_AUTHORIZED=NO",
    "V08_P4_IMPLEMENTATION_AUTHORIZED=NO",
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
    "V08-GAP-001",
    "EngineeringInputBundleForm.vue",
    "V08-GAP-002",
    "LineageAwareCalculatorPort",
    "V08-GAP-003",
    "ZoneCoolingLoadInput",
    "V08-GAP-004",
    "total_compressor_input_power_kw_e",
    "V08-GAP-005",
    "planning-run",
    "V07-GAP-004",
    "V07-GAP-006",
    "V07-GAP-007",
    "V07-GAP-010",
    "requires_review=true",
)

FORBIDDEN_CONTRACT_FRAGMENTS: tuple[str, ...] = (
    "utilization_factor",
    "reserve_factor",
)

PACKAGE_ALLOWLIST_MARKERS: tuple[str, ...] = (
    "V08_P1_FILE_ALLOWLIST",
    "V08_P2_FILE_ALLOWLIST",
    "V08_P3_FILE_ALLOWLIST",
    "V08_P4_FILE_ALLOWLIST",
)

P0_EXISTING_ALLOWLIST_PATHS: tuple[str, ...] = (
    "docs/tasks/V0_8-P0-operator-minimal-input-contract.md",
    "docs/architecture/ADR-028-operator-minimal-process-input.md",
    "docs/audit/current-state.md",
    "docs/audit/gap-analysis.md",
    "docs/audit/validation-baseline.md",
    "docs/TECH_DEBT.md",
    "docs/roadmap/DEVELOPMENT_PLAN.md",
    "backend/tests/architecture/test_v08_p0_contract.py",
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


def test_v08_p0_contract_file_exists() -> None:
    """P0 contract and ADR must exist at the authorized paths."""
    assert CONTRACT_PATH.is_file()
    assert ADR_PATH.is_file()


def test_v08_p0_contract_governance_flags_present() -> None:
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


def test_v08_p0_contract_documents_inherited_report_source_mapping() -> None:
    """Contract must keep the V0.6 five-row persisted-calculator mapping."""
    contract = _read_contract()
    for calculator, attr, section in FROZEN_REPORT_SOURCE_MAPPING:
        assert calculator in contract, f"Mapping missing calculator: {calculator!r}"
        assert attr in contract, f"Mapping missing attr: {attr!r}"
        assert section in contract, f"Mapping missing section: {section!r}"
    assert "Reports MUST NOT recalculate formulas" in contract


def test_v08_p0_contract_freezes_operator_five_key_leaves() -> None:
    """Operator-visible KEY surface must be exactly the five process leaves."""
    contract = _read_contract()
    assert "OperatorProcessInputV1" in contract
    for leaf in OPERATOR_FIVE_KEY_LEAVES:
        assert leaf in contract, f"Operator KEY leaf missing: {leaf!r}"
    assert "OPERATOR_PROCESS_INPUT_FIVE_KEY_LEAVES_ONLY=YES" in contract
    assert "DEMO_CATALOG_TO_EXPLICIT_BUNDLE_LEAF=YES" in contract
    assert "ZONE_RESULT_TO_COOLING_LOAD_ENVELOPE_AUTO_FEED=NO" in contract
    assert "ZONE_RESULT_TO_COOLING_LOAD_IDENTITY_AND_PLAN_AREA_LINEAGE=YES" in contract


def test_v08_p0_contract_records_known_baseline_gaps() -> None:
    """Known remaining gaps must be recorded as gaps, not completed work."""
    contract = _read_contract()
    for fragment in KNOWN_BASELINE_GAP_FRAGMENTS:
        assert fragment in contract, f"Baseline gap documentation missing: {fragment!r}"
    assert "P0 does not fix" in contract


def test_v08_p0_package_allowlists_are_parseable_and_disjoint() -> None:
    """P1–P4 exclusive allowlists must parse from the contract and not overlap."""
    contract = _read_contract()
    parsed: dict[str, set[str]] = {
        marker: _extract_allowlist_paths(contract, marker) for marker in PACKAGE_ALLOWLIST_MARKERS
    }
    for marker, paths in parsed.items():
        assert len(paths) >= 3, f"{marker} too small: {paths!r}"

    for left, right in combinations(PACKAGE_ALLOWLIST_MARKERS, 2):
        overlap = parsed[left] & parsed[right]
        assert not overlap, f"{left} overlaps {right}: {sorted(overlap)!r}"

    p1 = parsed["V08_P1_FILE_ALLOWLIST"]
    p2 = parsed["V08_P2_FILE_ALLOWLIST"]
    assert "backend/src/cold_storage/modules/projects/application/operator_process_input.py" in p1
    assert "frontend/src/features/five-stage/components/EngineeringInputBundleForm.vue" in p2
    assert "frontend/src/features/five-stage/components/EngineeringInputBundleForm.vue" not in p1
    assert "backend/src/cold_storage/modules/calculations/domain/**" not in p1
    assert "samples/v08-process-input/**" in parsed["V08_P3_FILE_ALLOWLIST"]


def test_v08_p0_allowlist_existing_files_are_present() -> None:
    """P0 allowlist paths that should already exist must be on disk."""
    contract = _read_contract()
    p0_paths = _extract_allowlist_paths(contract, "V08_P0_FILE_ALLOWLIST")
    for path in P0_EXISTING_ALLOWLIST_PATHS:
        assert path in p0_paths, f"P0 allowlist missing {path!r}"
        assert (REPO_ROOT / path).is_file(), f"P0 allowlist file missing on disk: {path!r}"


def test_v08_p0_contract_documents_expert_decisions_and_aily_boundary() -> None:
    """Expert-decision register and Aily live=NO must be frozen."""
    contract = _read_contract()
    required_fragments = (
        "AILY_LIVE_IMPLEMENTATION=NO",
        "AGENT_TO_ENGINEERING_VALUE=NO",
        "PRODUCTION_RBAC_CLAIM=NO",
        "E1",
        "E8",
        "frozen_fruit_ratio",
        "KNOWN_CONFLICT",
        "mark_reviewed",
    )
    for fragment in required_fragments:
        assert fragment in contract, f"P0 contract missing required fragment: {fragment!r}"


def test_v08_p0_contract_documents_closed_issues_and_fail_closed() -> None:
    """Closed leftover issues stay recorded; fail-closed semantics remain."""
    contract = _read_contract()
    assert "CLOSED" in contract
    for issue_ref in ("#11", "#13", "#17", "#176", "#20"):
        assert issue_ref in contract, f"Issue mapping missing {issue_ref!r}"
    required_fragments = (
        "SQLite",
        "PostgreSQL",
        "five-stage-execution",
        "requires_review=true",
        "fail-closed",
        "create_app",
        "MISSING_ENGINEERING_PARAMETER",
    )
    for fragment in required_fragments:
        assert fragment in contract, f"P0 contract missing required fragment: {fragment!r}"


def test_v08_p0_living_docs_record_v08_umbrella() -> None:
    """Living docs must point at V0.8 without dropping V0.7 delivered truth."""
    living_docs = (
        REPO_ROOT / "docs" / "audit" / "current-state.md",
        REPO_ROOT / "docs" / "audit" / "gap-analysis.md",
        REPO_ROOT / "docs" / "audit" / "validation-baseline.md",
        REPO_ROOT / "docs" / "TECH_DEBT.md",
        REPO_ROOT / "docs" / "roadmap" / "DEVELOPMENT_PLAN.md",
    )
    for path in living_docs:
        text = path.read_text(encoding="utf-8")
        assert "V0.8" in text, f"{path} missing V0.8 truth-up"
        assert "v0.7.0" in text, f"{path} missing v0.7.0 baseline"
        assert "V0_8-P0-operator-minimal-input-contract.md" in text, (
            f"{path} missing P0 contract pointer"
        )
        assert "V0.7" in text, f"{path} dropped V0.7 delivered record"
        assert "V0_7-P0-trust-loop-contract.md" in text, f"{path} dropped V0.7 P0 pointer"
        assert "v0.6.0" in text, f"{path} dropped v0.6.0 baseline"


def test_v08_p0_package_dag_is_frozen() -> None:
    """Wave DAG must be explicit and sequential on the assembler."""
    contract = _read_contract()
    assert "P0 → P1 → (P2 || P3) → P4" in contract
    assert "OperatorProcessInputV1" in contract
    assert "v07_sample_loader.py" in contract


def test_v08_p0_adr_records_three_leaf_sources() -> None:
    """ADR-028 must freeze user / persisted / catalog leaf sources."""
    adr = ADR_PATH.read_text(encoding="utf-8")
    assert "OperatorProcessInputV1" in adr
    assert "source_type" in adr
    assert "persisted" in adr
    assert "demo" in adr
    assert "not calculator formulas" in adr
    assert "modules/calculations/domain" in adr


def test_v08_p0_contract_and_tests_contain_no_engineering_formula_values() -> None:
    """Neither the contract file nor this test module may embed formula numbers."""
    this_file = Path(__file__).read_text(encoding="utf-8")
    contract = _read_contract()
    adr = ADR_PATH.read_text(encoding="utf-8")

    for label, content in (("contract", contract), ("adr", adr), ("test module", this_file)):
        if label in {"contract", "adr"}:
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
