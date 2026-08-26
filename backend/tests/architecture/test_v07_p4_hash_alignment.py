"""Architecture tests for V0.7 P4 targeted hash repair contract."""

from __future__ import annotations

import re
from pathlib import Path

from cold_storage.modules.orchestration.domain.consumer_bindings import (
    STAGE_TO_CALCULATOR_NAME,
)
from cold_storage.modules.orchestration.domain.dag import ORCHESTRATION_STAGE_ORDER

REPO_ROOT = Path(__file__).resolve().parents[3]
P0_CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V0_7-P0-trust-loop-contract.md"
P4_CONTRACT_PATH = REPO_ROOT / "docs" / "tasks" / "V0_7-P4-targeted-repair-contract.md"

P4_EXISTING_ALLOWLIST_PATHS: tuple[str, ...] = (
    "docs/tasks/V0_7-P4-targeted-repair-contract.md",
    "backend/src/cold_storage/modules/workflow/application/service.py",
    "backend/src/cold_storage/modules/schemes/application/canonical_source_reads.py",
    "backend/tests/architecture/test_v07_p4_hash_alignment.py",
    "backend/tests/integration/test_v07_p4_consumer_hash_repair_sqlite.py",
    "backend/tests/integration/test_v07_p4_consumer_hash_repair_postgresql.py",
)

REQUIRED_P4_GOVERNANCE_FLAGS: tuple[str, ...] = (
    "TASK=V07_P4_TARGETED_HASH_REPAIR_R1",
    "V07_P4_IMPLEMENTATION_AUTHORIZED=YES",
    "PRODUCTION_HASH_REPAIR_AUTHORIZED=YES",
    "FORMULA_RECUT_AUTHORIZED=NO",
    "COEFFICIENT_PROMOTION_AUTHORIZED=NO",
    "V07-GAP-005",
    "P4-REP-001",
    "P4-REP-002",
    "P4-REP-003",
    "MERGE_AUTHORIZED=NO",
    "DRAFT=YES",
)

P4_REPAIR_FRAGMENTS: tuple[str, ...] = (
    "_project_calculations",
    "record.result_hash",
    "indexed[stage].result_hash",
    "combined_source_hash",
    "SourceBinding.combined_source_hash",
    "_result_hash()",
    "_per_calc_hash()",
)

FORBIDDEN_PRODUCTION_PATH_FRAGMENTS: tuple[str, ...] = (
    "modules/calculations/**",
    "bootstrap/app.py",
    "schemes/api/routes.py",
    "v06_sample_loader.py",
)

P4_AC_FLAGS: tuple[str, ...] = (
    "WORKFLOW_RUNS_USE_PERSISTED_RESULT_HASH=PASS",
    "SCHEME_CANONICAL_READS_USE_PERSISTED_RESULT_HASH=PASS",
    "WORKFLOW_STALE_USES_COMBINED_SOURCE_HASH=PASS",
    "V07_GAP_005_CLOSED=PASS",
    "SQLITE_POSTGRESQL_CONSUMER_HASH_PARITY=PASS",
    "NO_FALSE_SCHEME_SOURCE_SNAPSHOT_MISMATCH_WHEN_ALIGNED=PASS",
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


def test_v07_p4_contract_file_exists() -> None:
    assert P4_CONTRACT_PATH.is_file()


def test_v07_p4_contract_governance_and_repairs() -> None:
    contract = _read_contract(P4_CONTRACT_PATH)
    for flag in REQUIRED_P4_GOVERNANCE_FLAGS:
        assert flag in contract, f"P4 contract missing governance flag: {flag!r}"
    for fragment in P4_REPAIR_FRAGMENTS:
        assert fragment in contract, f"P4 contract missing repair fragment: {fragment!r}"


def test_v07_p4_allowlist_files_exist_and_are_disjoint_from_wave1() -> None:
    p0_contract = _read_contract(P0_CONTRACT_PATH)
    p4_contract = _read_contract(P4_CONTRACT_PATH)
    p4_paths = _extract_allowlist_paths(p4_contract, "V07_P4_FILE_ALLOWLIST")
    for path in P4_EXISTING_ALLOWLIST_PATHS:
        assert path in p4_paths, f"P4 allowlist missing {path!r}"
        full = REPO_ROOT / path
        assert full.is_file(), f"P4 allowlist file missing on disk: {path!r}"
    wave1_markers = (
        "V07_P1_FILE_ALLOWLIST",
        "V07_P2_FILE_ALLOWLIST",
        "V07_P3A_FILE_ALLOWLIST",
        "V07_P3B_FILE_ALLOWLIST",
        "V07_P6_FILE_ALLOWLIST",
    )
    for marker in wave1_markers:
        other_paths = _extract_allowlist_paths(p0_contract, marker)
        overlap = p4_paths & other_paths
        assert not overlap, f"P4 overlaps {marker}: {sorted(overlap)!r}"


def test_v07_p4_contract_documents_p4_ac() -> None:
    contract = _read_contract(P4_CONTRACT_PATH)
    for flag in P4_AC_FLAGS:
        assert flag in contract, f"P4 contract missing AC flag: {flag!r}"


def test_v07_p4_contract_forbids_out_of_scope_paths() -> None:
    contract = _read_contract(P4_CONTRACT_PATH)
    for fragment in FORBIDDEN_PRODUCTION_PATH_FRAGMENTS:
        assert fragment in contract, f"P4 contract must forbid {fragment!r}"


def test_v07_p4_production_code_uses_persisted_hashes() -> None:
    workflow_path = REPO_ROOT / "backend/src/cold_storage/modules/workflow/application/service.py"
    scheme_path = (
        REPO_ROOT / "backend/src/cold_storage/modules/schemes/application/canonical_source_reads.py"
    )
    workflow_text = workflow_path.read_text(encoding="utf-8")
    scheme_text = scheme_path.read_text(encoding="utf-8")

    assert '_result_hash(record.get("result_snapshot"))' not in workflow_text
    assert 'record.get("result_hash")' in workflow_text
    assert "def _result_hash(" in workflow_text

    assert "_per_calc_hash(indexed[stage].result_snapshot" not in scheme_text
    assert "indexed[stage].result_hash" in scheme_text
    assert "def _per_calc_hash(" in scheme_text


def test_v07_p4_stale_reasons_use_combined_source_hash() -> None:
    workflow_path = REPO_ROOT / "backend/src/cold_storage/modules/workflow/application/service.py"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    stale_fn_start = workflow_text.index("def _collect_stale_reasons(")
    stale_fn_end = workflow_text.index("\ndef _collect_blockers(", stale_fn_start)
    stale_fn = workflow_text[stale_fn_start:stale_fn_end]
    assert "binding_combined_source_hash" in stale_fn
    assert "combined_source_hash" in stale_fn
    assert "json.dumps" not in stale_fn


def test_v07_p4_contract_and_tests_contain_no_engineering_formula_values() -> None:
    this_file = Path(__file__).read_text(encoding="utf-8")
    contract = _read_contract(P4_CONTRACT_PATH)
    for label, content in (("contract", contract), ("test module", this_file)):
        for pattern in _ENGINEERING_VALUE_PATTERNS:
            match = pattern.search(content)
            assert match is None, (
                f"Engineering formula value pattern {pattern.pattern!r} "
                f"found in {label}: {match.group()!r}"
            )


def test_v07_p4_targets_all_canonical_stages() -> None:
    scheme_path = (
        REPO_ROOT / "backend/src/cold_storage/modules/schemes/application/canonical_source_reads.py"
    )
    scheme_text = scheme_path.read_text(encoding="utf-8")
    for stage in ORCHESTRATION_STAGE_ORDER:
        assert stage in scheme_text or STAGE_TO_CALCULATOR_NAME[stage] in scheme_text
