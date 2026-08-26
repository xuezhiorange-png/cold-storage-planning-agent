"""Architecture tests for V0.7 P1 data integrity proof contract.

Enforces the frozen contract in
``docs/tasks/V0_7-P1-data-integrity-contract.md`` without changing formulas
or embedding engineering values.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
P0_CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V0_7-P0-trust-loop-contract.md"
P1_CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V0_7-P1-data-integrity-contract.md"
MATRIX_PATH = REPO_ROOT / "docs" / "audit" / "data-integrity-matrix.md"

REQUIRED_GOVERNANCE_FLAGS: tuple[str, ...] = (
    "TASK=V07_P1_DATA_INTEGRITY_PROOF_R1",
    "PARENT_ISSUE=PENDING",
    "P1_TRACKING_ISSUE=PENDING",
    "GOVERNANCE_OWNER=V0.7",
    "BASE_MAIN_SHA=f8a4b80a8a8fab26113b57d9f4ea666b8bc699ba",
    "BASE_P0_SHA=468354dc13b7b5c5708095d4a766b4d42c9e3834",
    "PREVIOUS_RELEASE=v0.6.0",
    "TARGET_BRANCH=cursor/v07-p1-data-integrity-6c68",
    "TARGET_PR_STATE=DRAFT",
    "CONTRACT_STATUS=IMPLEMENTATION_R1",
    "V07_P1_IMPLEMENTATION_AUTHORIZED=YES",
    "READY_AUTHORIZED=NO",
    "MERGE_AUTHORIZED=NO",
    "FORMULA_RECUT_AUTHORIZED=NO",
    "COEFFICIENT_PROMOTION_AUTHORIZED=NO",
    "DEMO_COEFFICIENT_CONFLICT_RESOLUTION=NO",
    "TAG_PUBLICATION_AUTHORIZED=NO",
    "RELEASE_PUBLICATION_AUTHORIZED=NO",
    "NO_STEP_IMPLIES_THE_NEXT=TRUE",
)

P1_ALLOWLIST_PATHS: tuple[str, ...] = (
    "docs/tasks/V0_7-P1-data-integrity-contract.md",
    "docs/audit/coefficient-inventory.md",
    "docs/audit/data-integrity-matrix.md",
    "backend/tests/architecture/test_v07_p1_data_integrity_contract.py",
    "backend/tests/architecture/test_v07_p1_default_alignment_matrix.py",
    "backend/tests/architecture/test_v07_p1_coefficient_metadata_alignment.py",
    "backend/tests/integration/test_v07_p1_bundle_execution_traceability.py",
    "backend/tests/integration/test_v07_p1_version_snapshot_authority.py",
    "backend/tests/integration/test_v07_p1_seed_authority.py",
)

KNOWN_CONFLICT_IDS: tuple[str, ...] = ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8")

_ENGINEERING_VALUE_PATTERNS = (
    re.compile(r"\b\d+\.?\d*\s*kW\b", re.IGNORECASE),
    re.compile(r"\butilization_factor\s*=\s*0\.\d+"),
    re.compile(r"\breserve_factor\s*=\s*0\.\d+"),
)


def _read(path: Path) -> str:
    assert path.is_file(), f"Missing required file: {path}"
    return path.read_text(encoding="utf-8")


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


def test_v07_p1_contract_file_exists() -> None:
    assert P1_CONTRACT_PATH.is_file()


def test_v07_p1_contract_governance_flags_present() -> None:
    contract = _read(P1_CONTRACT_PATH)
    for flag in REQUIRED_GOVERNANCE_FLAGS:
        assert flag in contract, f"P1 contract missing governance flag: {flag!r}"


def test_v07_p1_contract_matches_p0_allowlist_entry() -> None:
    p0 = _read(P0_CONTRACT_PATH)
    p1_paths = _extract_allowlist_paths(p0, "V07_P1_FILE_ALLOWLIST")
    for path in P1_ALLOWLIST_PATHS:
        assert path in p1_paths, f"P0 P1 allowlist missing {path!r}"


def test_v07_p1_allowlist_files_exist_on_disk() -> None:
    contract = _read(P1_CONTRACT_PATH)
    allowlist = _extract_allowlist_paths(contract, "V07_P1_FILE_ALLOWLIST")
    assert allowlist == set(P1_ALLOWLIST_PATHS)
    for path in P1_ALLOWLIST_PATHS:
        assert (REPO_ROOT / path).is_file(), f"P1 allowlist file missing: {path!r}"


def test_v07_p1_documents_traceability_and_matrix() -> None:
    contract = _read(P1_CONTRACT_PATH)
    matrix = _read(MATRIX_PATH)
    required = (
        "EngineeringInputBundleV1",
        "project_execution_snapshot_from_bundle",
        "CalculationRunRecord",
        "KNOWN_CONFLICT",
        "seed_catalog",
        "seed_demo_coefficients",
        "consumer",
        "non_consumer",
        "FORMULA_RECUT_AUTHORIZED=NO",
    )
    for fragment in required:
        assert fragment in contract, f"P1 contract missing {fragment!r}"
    for expert_id in KNOWN_CONFLICT_IDS:
        assert expert_id in contract, f"P1 contract missing expert item {expert_id!r}"
        assert expert_id in matrix, f"Matrix missing expert item {expert_id!r}"


def test_v07_p1_coefficient_inventory_registers_e1_e8() -> None:
    inventory = _read(REPO_ROOT / "docs" / "audit" / "coefficient-inventory.md")
    assert "KNOWN_CONFLICT" in inventory
    for expert_id in KNOWN_CONFLICT_IDS:
        assert expert_id in inventory, f"Inventory missing {expert_id!r}"


def test_v07_p1_contract_and_tests_contain_no_engineering_formula_values() -> None:
    this_file = Path(__file__).read_text(encoding="utf-8")
    contract = _read(P1_CONTRACT_PATH)
    for label, content in (("contract", contract), ("test module", this_file)):
        for pattern in _ENGINEERING_VALUE_PATTERNS:
            match = pattern.search(content)
            assert match is None, (
                f"Engineering value pattern {pattern.pattern!r} in {label}: {match.group()!r}"
                if match
                else ""
            )
