"""Architecture tests for V0.5 P5 controlled acceptance contract."""

from __future__ import annotations

import re
from pathlib import Path

from cold_storage.bootstrap.v05_local_sample import (
    EXPECTED_CANONICAL_CALCULATORS,
    load_manifest,
)
from cold_storage.modules.orchestration.domain.consumer_bindings import CANONICAL_CALCULATOR_NAMES
from cold_storage.modules.orchestration.domain.dag import CALCULATOR_BINDINGS

REPO_ROOT = Path(__file__).resolve().parents[3]
P5_CONTRACT = REPO_ROOT / "docs" / "tasks" / "V0_5-P5-controlled-acceptance-contract.md"
P5_RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "v05-controlled-acceptance.md"
V05_SAMPLE_LOADER = (
    REPO_ROOT / "backend" / "src" / "cold_storage" / "bootstrap" / "v05_local_sample.py"
)
P5_ARCHITECTURE_TEST = (
    REPO_ROOT
    / "backend"
    / "tests"
    / "architecture"
    / "test_v05_p5_controlled_acceptance_contract.py"
)
P5_SQLITE_TEST = (
    REPO_ROOT / "backend" / "tests" / "integration" / "test_v05_p5_controlled_acceptance_sqlite.py"
)
P5_POSTGRESQL_TEST = (
    REPO_ROOT
    / "backend"
    / "tests"
    / "integration"
    / "test_v05_p5_controlled_acceptance_postgresql.py"
)
P5_RELEASE_SCAN_FILES: tuple[Path, ...] = (
    P5_CONTRACT,
    P5_RUNBOOK,
    REPO_ROOT / "backend" / "tests" / "integration" / "v05_p5_acceptance_evidence.py",
)

BASE_MAIN_SHA = "7e187d52198d708bdaa5006ca48c7da880983286"
BASE_TREE = "3a2497b025a2413c3b9c2f4af9b6a6628714aea6"

FORBIDDEN_RELEASE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"TAG_PUBLICATION_AUTHORIZED=YES"),
    re.compile(r"RELEASE_PUBLICATION_AUTHORIZED=YES"),
    re.compile(r"P5_CREATES_TAG_NOW=YES"),
    re.compile(r"P5_CREATES_GITHUB_RELEASE_NOW=YES"),
    re.compile(r"^\s*git\s+tag\s+", re.MULTILINE),
    re.compile(r"^\s*gh\s+release\s+create\b", re.MULTILINE | re.IGNORECASE),
)


def test_p5_contract_and_runbook_exist_with_source_identity_fields() -> None:
    assert P5_CONTRACT.is_file()
    assert P5_RUNBOOK.is_file()

    contract = P5_CONTRACT.read_text(encoding="utf-8")
    runbook = P5_RUNBOOK.read_text(encoding="utf-8")

    assert f"BASE_MAIN_SHA={BASE_MAIN_SHA}" in contract
    assert f"BASE_TREE={BASE_TREE}" in contract
    assert "CI_GATE" in contract or "CI green" in contract

    assert f"BASE_MAIN_SHA={BASE_MAIN_SHA}" in runbook
    assert f"BASE_TREE={BASE_TREE}" in runbook
    assert "make verify-v05-p5-controlled-acceptance" in runbook
    assert "#169" in runbook


def test_p5_sample_loader_does_not_call_planning_run() -> None:
    loader_source = V05_SAMPLE_LOADER.read_text(encoding="utf-8")
    assert "/planning-run" not in loader_source
    assert "planning_run" not in loader_source
    assert "five-stage-execution" in loader_source
    assert "-m alembic" not in loader_source
    assert "alembic upgrade" not in loader_source


def test_p5_canonical_calculator_names_frozen() -> None:
    assert tuple(EXPECTED_CANONICAL_CALCULATORS) == (
        "cold_room_zone_plan",
        "cooling_load",
        "equipment",
        "installed_power",
        "investment_estimate",
    )
    assert frozenset(EXPECTED_CANONICAL_CALCULATORS) == CANONICAL_CALCULATOR_NAMES
    assert CALCULATOR_BINDINGS["power"] == "installed_power"
    assert "power_configuration" not in CALCULATOR_BINDINGS.values()


def test_p5_manifest_demo_coefficients_remain_unverified_and_review_required() -> None:
    manifest = load_manifest()
    bundle = manifest["engineering_input_bundle"]
    demo_leaves = bundle["coefficient_context"].get("demo_coefficient_leaves") or []
    assert demo_leaves
    for leaf in demo_leaves:
        assert leaf["source_type"] == "demo"
        assert leaf["validity_status"] in {"unverified", "conflict"}
        assert leaf["requires_review"] is True


def test_p5_evidence_module_reuses_p4_fixtures_not_planning_run() -> None:
    evidence_source = (
        REPO_ROOT / "backend" / "tests" / "integration" / "v05_p5_acceptance_evidence.py"
    ).read_text(encoding="utf-8")
    assert "v05_p4_acceptance_fixtures" in evidence_source
    assert "seed_sample_project" in evidence_source
    assert "planning-run" not in evidence_source
    assert "planning_run" not in evidence_source


def test_p5_implementation_allowlist_files_exist() -> None:
    for path in (
        P5_CONTRACT,
        P5_RUNBOOK,
        P5_ARCHITECTURE_TEST,
        P5_SQLITE_TEST,
        P5_POSTGRESQL_TEST,
        REPO_ROOT / "backend" / "tests" / "integration" / "v05_p5_acceptance_evidence.py",
    ):
        assert path.is_file(), f"missing allowlisted P5 file: {path}"


def test_p5_allowlisted_files_do_not_authorize_tag_or_release() -> None:
    for path in P5_RELEASE_SCAN_FILES:
        assert path.is_file(), f"missing allowlisted P5 file: {path}"
        content = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_RELEASE_PATTERNS:
            assert not pattern.search(content), (
                f"{path.relative_to(REPO_ROOT)} must not match forbidden release pattern "
                f"{pattern.pattern!r}"
            )
