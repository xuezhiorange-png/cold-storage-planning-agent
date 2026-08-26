"""Architecture tests for V0.7 P2 cross-consumer consistency contract."""

from __future__ import annotations

import re
from itertools import combinations
from pathlib import Path

from cold_storage.modules.orchestration.domain.consumer_bindings import (
    STAGE_TO_CALCULATOR_NAME,
)
from cold_storage.modules.orchestration.domain.dag import ORCHESTRATION_STAGE_ORDER

REPO_ROOT = Path(__file__).resolve().parents[3]
P0_CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V0_7-P0-trust-loop-contract.md"
P2_CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V0_7-P2-cross-consumer-consistency-contract.md"

P2_EXISTING_ALLOWLIST_PATHS: tuple[str, ...] = (
    "docs/tasks/V0_7-P2-cross-consumer-consistency-contract.md",
    "backend/tests/integration/v07_p2_consistency_evidence.py",
    "backend/tests/integration/v07_p2_numeric_projection_map.py",
    "backend/tests/integration/test_v07_p2_cross_consumer_consistency_sqlite.py",
    "backend/tests/integration/test_v07_p2_cross_consumer_consistency_postgresql.py",
    "backend/tests/architecture/test_v07_p2_consumer_hash_alignment.py",
    "backend/tests/golden/v07_cross_consumer_v1.json",
)

P2_SAMPLE_GLOB = "samples/v07-consistency/**"

REQUIRED_P2_GOVERNANCE_FLAGS: tuple[str, ...] = (
    "TASK=V07_P2_CROSS_CONSUMER_CONSISTENCY_R1",
    "V07_P2_IMPLEMENTATION_AUTHORIZED=YES",
    "PRODUCTION_HASH_REPAIR_AUTHORIZED=NO",
    "FORMULA_RECUT_AUTHORIZED=NO",
    "KNOWN_DRIFT-WF-001",
    "KNOWN_DRIFT-SC-001",
    "V07-GAP-005",
    "MERGE_AUTHORIZED=NO",
    "DRAFT=YES",
)

KNOWN_DRIFT_FRAGMENTS: tuple[str, ...] = (
    "KNOWN_DRIFT-WF-001",
    "KNOWN_DRIFT-SC-001",
    "KNOWN_DRIFT-WF-002",
    "_result_hash",
    "_per_calc_hash",
    "fingerprint.result_hash",
    "do not repair in P2",
)

FORBIDDEN_PRODUCTION_PATH_FRAGMENTS: tuple[str, ...] = (
    "modules/calculations/**",
    "bootstrap/app.py",
    "schemes/api/routes.py",
)

P2_AC_FLAGS: tuple[str, ...] = (
    "API_BINDING_REPORT_SCHEME_AUTHORITATIVE_HASH_PARITY=PASS",
    "API_BINDING_REPORT_SCHEME_IDENTITY_PARITY=PASS",
    "WORKFLOW_SCHEME_HELPER_HASH_KNOWN_DRIFT_RECORDED=PASS",
    "MISSING_KEY_LEAF_FAIL_CLOSED=PASS",
    "SQLITE_POSTGRESQL_AUTHORITATIVE_HASH_PARITY=PASS",
    "NO_FORMULA_RECALC_IN_REPORT=PASS",
    "IDEMPOTENT_REPLAY_STABLE=PASS",
)

_ENGINEERING_VALUE_PATTERNS = (
    re.compile(r"\b\d+\.?\d*\s*kW\b", re.IGNORECASE),
    re.compile(r"\butilization_factor\s*=\s*0\.\d+"),
    re.compile(r"\breserve_factor\s*=\s*0\.\d+"),
)


def _read_contract(path: Path) -> str:
    assert path.is_file(), f"contract missing: {path}"
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


def test_v07_p2_contract_file_exists() -> None:
    assert P2_CONTRACT_PATH.is_file()


def test_v07_p2_contract_governance_and_known_drift() -> None:
    contract = _read_contract(P2_CONTRACT_PATH)
    for flag in REQUIRED_P2_GOVERNANCE_FLAGS:
        assert flag in contract, f"P2 contract missing governance flag: {flag!r}"
    for fragment in KNOWN_DRIFT_FRAGMENTS:
        assert fragment in contract, f"P2 contract missing drift fragment: {fragment!r}"


def test_v07_p2_allowlist_matches_p0_and_files_exist() -> None:
    p0_contract = _read_contract(P0_CONTRACT_PATH)
    p2_contract = _read_contract(P2_CONTRACT_PATH)
    p0_paths = _extract_allowlist_paths(p0_contract, "V07_P2_FILE_ALLOWLIST")
    p2_paths = _extract_allowlist_paths(p2_contract, "V07_P2_FILE_ALLOWLIST")
    assert p0_paths == p2_paths
    for path in P2_EXISTING_ALLOWLIST_PATHS:
        assert path in p2_paths, f"P2 allowlist missing {path!r}"
        full = REPO_ROOT / path
        assert full.is_file(), f"P2 allowlist file missing on disk: {path!r}"
    assert P2_SAMPLE_GLOB in p2_paths
    assert (REPO_ROOT / "samples" / "v07-consistency" / "manifest.json").is_file()


def test_v07_p2_allowlist_disjoint_from_other_wave1_packages() -> None:
    p0_contract = _read_contract(P0_CONTRACT_PATH)
    p2_paths = _extract_allowlist_paths(p0_contract, "V07_P2_FILE_ALLOWLIST")
    other_markers = (
        "V07_P1_FILE_ALLOWLIST",
        "V07_P3A_FILE_ALLOWLIST",
        "V07_P3B_FILE_ALLOWLIST",
        "V07_P6_FILE_ALLOWLIST",
    )
    for marker in other_markers:
        other_paths = _extract_allowlist_paths(p0_contract, marker)
        overlap = p2_paths & other_paths
        assert not overlap, f"P2 overlaps {marker}: {sorted(overlap)!r}"


def test_v07_p2_contract_documents_p2_ac() -> None:
    contract = _read_contract(P2_CONTRACT_PATH)
    for flag in P2_AC_FLAGS:
        assert flag in contract, f"P2 contract missing AC flag: {flag!r}"


def test_v07_p2_evidence_targets_all_canonical_stages() -> None:
    evidence_path = REPO_ROOT / "backend/tests/integration/v07_p2_consistency_evidence.py"
    text = evidence_path.read_text(encoding="utf-8")
    for stage in ORCHESTRATION_STAGE_ORDER:
        assert stage in text, f"evidence module missing stage {stage!r}"
        assert STAGE_TO_CALCULATOR_NAME[stage] in text or "calculator_for_stage" in text


def test_v07_p2_numeric_projection_map_is_test_only() -> None:
    map_path = REPO_ROOT / "backend/tests/integration/v07_p2_numeric_projection_map.py"
    text = map_path.read_text(encoding="utf-8")
    assert "backend/tests" in str(map_path)
    forbidden_roots = (
        "frontend/src",
        "modules/reports/renderers",
        "modules/reports/templates",
    )
    for root in forbidden_roots:
        assert root not in text


def test_v07_p2_contract_forbids_production_hash_repair_paths() -> None:
    contract = _read_contract(P2_CONTRACT_PATH)
    for fragment in FORBIDDEN_PRODUCTION_PATH_FRAGMENTS:
        assert fragment in contract, f"P2 contract must forbid {fragment!r}"


def test_v07_p2_contract_and_tests_contain_no_engineering_formula_values() -> None:
    this_file = Path(__file__).read_text(encoding="utf-8")
    contract = _read_contract(P2_CONTRACT_PATH)
    for label, content in (("contract", contract), ("test module", this_file)):
        for pattern in _ENGINEERING_VALUE_PATTERNS:
            match = pattern.search(content)
            assert match is None, (
                f"Engineering formula value pattern {pattern.pattern!r} "
                f"found in {label}: {match.group()!r}"
            )


def test_v07_p2_wave1_allowlists_pairwise_disjoint_subset() -> None:
    p0_contract = _read_contract(P0_CONTRACT_PATH)
    markers = (
        "V07_P1_FILE_ALLOWLIST",
        "V07_P2_FILE_ALLOWLIST",
        "V07_P3A_FILE_ALLOWLIST",
        "V07_P3B_FILE_ALLOWLIST",
        "V07_P6_FILE_ALLOWLIST",
    )
    parsed = {marker: _extract_allowlist_paths(p0_contract, marker) for marker in markers}
    for left, right in combinations(markers, 2):
        overlap = parsed[left] & parsed[right]
        assert not overlap, f"{left} overlaps {right}: {sorted(overlap)!r}"
