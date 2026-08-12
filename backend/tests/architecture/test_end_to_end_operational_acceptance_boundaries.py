from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODULE = PROJECT_ROOT / "backend/src/cold_storage/release/end_to_end_operational_acceptance.py"
WORKFLOW = PROJECT_ROOT / ".github/workflows/task012-slice6-s7-e2e-operational-acceptance.yml"


def test_s6_07_module_reuses_s6_06_verifier_and_does_not_import_calculators() -> None:
    content = MODULE.read_text(encoding="utf-8")
    assert "verify_final_release_evidence" in content
    assert "modules.calculations" not in content
    assert "modules.schemes.domain" not in content
    assert "docker" not in content.lower()
    assert "production" in content


def test_s6_07_has_exact_nine_file_contract() -> None:
    content = MODULE.read_text(encoding="utf-8")
    assert '"acceptance-summary.json"' in content
    assert '"source-identity.json"' in content
    assert '"s6-06-authority.json"' in content
    assert '"runtime-lifecycle-observations.json"' in content
    assert '"production-http-scope-observations.json"' in content
    assert '"persistence-e2e-observations.json"' in content
    assert '"observability-security-observations.json"' in content
    assert '"SHA256SUMS"' in content
    assert '"SHA256SUMS.sha256"' in content
    assert "exactly nine files" in content


def test_workflow_is_dispatch_only_main_exact_and_read_only() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "github.sha == inputs.expected_source_sha" in workflow
    assert "contents: read" in workflow
    assert "actions: read" in workflow
    assert "packages: write" not in workflow
    assert "id-token: write" not in workflow
    assert "docker push" not in workflow
    assert "gh workflow run" not in workflow
    assert "gh run rerun" not in workflow
    assert "s6_06_run_id" in workflow
    assert "verify-s6-06-prerequisite" in workflow
    assert "assemble-s6-07-acceptance-evidence" in workflow
    assert "verify-s6-07-acceptance-evidence" in workflow


def test_workflow_does_not_dispatch_predecessor_or_production() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8").lower()
    for forbidden in (
        "gh workflow run",
        "dispatch package",
        "registry push",
        "cosign",
        "alembic downgrade",
        "production deploy",
        "production rollback",
    ):
        assert forbidden not in workflow
