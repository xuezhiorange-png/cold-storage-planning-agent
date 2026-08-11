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
    assert "github.sha == inputs.expected_source_sha" in workflow
    assert "git rev-parse HEAD^{tree}" in workflow
    assert "git merge-base --is-ancestor" in workflow
    assert "15952da351c922939f82d5e32bdd60216537fcdb" in workflow
    assert "7b36d68afb94577db401b8825013cc14ab0943d7" in workflow
    assert "gh api" in workflow
    assert "/actions/runs/" in workflow
    assert "/actions/artifacts/" in workflow
    assert "github-metadata" in workflow
    assert "--github-metadata-dir" in workflow
    assert "verify-final-release-evidence" in workflow
    assert "continue-on-error" not in workflow
    assert "contents: read" in workflow
    assert "actions: read" in workflow
    assert "push:" not in workflow
    assert "pull_request:" not in workflow
    assert "execute_live_evidence_capture" not in workflow
    assert "assemble_live_evidence" not in workflow
    assert "controlled-recovery" not in workflow
    assert "S6-07" not in workflow


def test_workflow_does_not_hardcode_pre_merge_main_as_dispatch_source() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert (
        "inputs.expected_source_sha == '7b36d68afb94577db401b8825013cc14ab0943d7'" not in workflow
    )
    assert "EXPECTED_SOURCE_TREE_SHA" not in workflow


def test_workflow_requires_dynamic_source_and_lineage_checks() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "github.sha == inputs.expected_source_sha" in workflow
    assert 'SOURCE_TREE_SHA="$(git rev-parse HEAD^{tree})"' in workflow
    assert "git merge-base --is-ancestor" in workflow
    assert "PACKAGE3_IMPLEMENTATION_HEAD_SHA" in workflow
    assert "IMPLEMENTATION_BASE_SHA" in workflow


def test_workflow_fetches_upstream_metadata_before_both_verification_surfaces() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    fetch_offset = workflow.index("Fetch authoritative GitHub workflow-run metadata")
    assemble_offset = workflow.index("assemble-final-release-evidence")
    verify_offset = workflow.index("verify-final-release-evidence")
    assert fetch_offset < assemble_offset < verify_offset
    assert "GH_TOKEN: ${{ github.token }}" in workflow
    assert "--header 'Accept: application/vnd.github+json'" in workflow
    assert "actions/runs/" in workflow
    assert "actions/artifacts/" in workflow


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
    assert "--source-sha" in content
    assert "--source-tree-sha" in content
    assert 'add_argument("--github-metadata-dir", required=True' in content


def test_package3_source_identity_separates_history_from_current_release() -> None:
    content = MODULE.read_text(encoding="utf-8")
    assert 'IMPLEMENTATION_BASE_SHA = "7b36d68afb94577db401b8825013cc14ab0943d7"' in content
    assert 'IMPLEMENTATION_BASE_TREE_SHA = "a43c2686a5f2c91aae1b4966f31923648c5eff03"' in content
    assert (
        'PACKAGE3_IMPLEMENTATION_HEAD_SHA = "15952da351c922939f82d5e32bdd60216537fcdb"' in content
    )
    assert "EXPECTED_SOURCE_SHA" not in content
    assert "current_release_source_sha" in content
    assert "source_sha: str, source_tree_sha: str" in content
