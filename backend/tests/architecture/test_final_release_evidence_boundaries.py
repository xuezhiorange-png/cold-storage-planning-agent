from __future__ import annotations

from pathlib import Path

from cold_storage.release.final_release_evidence import FINAL_BUNDLE_FILES, FINAL_JSON_FILES

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODULE = PROJECT_ROOT / "backend/src/cold_storage/release/final_release_evidence.py"
WORKFLOW = PROJECT_ROOT / ".github/workflows/task012-slice6-package3-release-evidence.yml"


def test_package3_has_exact_eight_file_contract() -> None:
    assert len(FINAL_JSON_FILES) == 6
    assert FINAL_BUNDLE_FILES == (
        "authority-index.json",
        "recovery-authority-summary.json",
        "release-evidence-summary.json",
        "release-provenance-summary.json",
        "runtime-readiness-summary.json",
        "source-identity.json",
        "SHA256SUMS",
        "SHA256SUMS.sha256",
    )


def test_package3_does_not_absorb_recovery_or_slice2_execution() -> None:
    content = MODULE.read_text(encoding="utf-8")
    for forbidden in (
        "from cold_storage.recovery",
        "import cold_storage.recovery",
        "from cold_storage.release.live_evidence_runner",
        "from cold_storage.release.evidence_collector",
        "from cold_storage.release.digest_verifier",
        "import subprocess",
        "from subprocess",
        "import requests",
        "import httpx",
        "import psycopg2",
        "production_client",
    ):
        assert forbidden not in content.lower(), f"forbidden dependency in {MODULE}: {forbidden}"
    assert "S6-07" in content
    assert "s6_07_required_for_s6_06_pass" in content


def test_package3_workflow_is_explicitly_gated_and_isolated() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "execute_final_release_evidence_assembly" in workflow
    assert "expected_source_sha" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "EXPECTED_SOURCE_SHA" in workflow
    assert "contents: read" in workflow
    assert "actions: read" in workflow
    assert "push:" not in workflow
    assert "pull_request:" not in workflow
    assert "execute_live_evidence_capture" not in workflow
    assert "assemble_live_evidence" not in workflow
    assert "controlled-recovery" not in workflow
    assert "S6-07" not in workflow


def test_package3_validation_is_in_ordinary_release_evidence_gate() -> None:
    makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
    ci = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for path in (
        "tests/unit/test_final_release_evidence.py",
        "tests/integration/test_final_release_evidence.py",
        "tests/architecture/test_final_release_evidence_boundaries.py",
    ):
        assert path in makefile
        assert path in ci
    assert "final_release_evidence.py" in makefile


def test_package3_cli_surfaces_are_explicit() -> None:
    content = MODULE.read_text(encoding="utf-8")
    assert 'add_parser("assemble-final-release-evidence")' in content
    assert 'add_parser("verify-final-release-evidence")' in content
    assert "verify_final_release_evidence(" in content
