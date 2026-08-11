from __future__ import annotations

import ast
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RECOVERY_ROOT = PROJECT_ROOT / "backend" / "src" / "cold_storage" / "recovery"
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"


def _source(name: str) -> str:
    return (RECOVERY_ROOT / name).read_text(encoding="utf-8")


def _workflow_job(name: str) -> str:
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(?P<body>.*?)(?=^  [a-z0-9-]+:|\Z)",
        source,
    )
    assert match is not None, f"workflow job is missing: {name}"
    return match.group("body")


def test_recovery_package_exists_with_operator_surfaces() -> None:
    assert (RECOVERY_ROOT / "backup_bundle.py").is_file()
    assert (RECOVERY_ROOT / "restore_runner.py").is_file()
    assert (RECOVERY_ROOT / "verification.py").is_file()
    assert (RECOVERY_ROOT / "cli.py").is_file()
    cli = _source("cli.py")
    assert '"backup"' in cli
    assert '"restore-isolated"' in cli
    assert '"verify-restore"' in cli


def test_recovery_core_has_no_web_or_release_boundary_dependency() -> None:
    for path in RECOVERY_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = [
            node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        names = []
        for node in imports:
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            else:
                names.append(node.module or "")
        assert not any(
            name.startswith(("fastapi", "uvicorn", "cold_storage.release")) for name in names
        )


def test_recovery_subprocess_boundary_is_explicit_and_non_shell() -> None:
    source = "\n".join(_source(name) for name in ("backup_bundle.py", "restore_runner.py"))
    assert "shell=True" not in source
    assert "os.system" not in source
    assert "shell=False" in source
    assert "pg_dump" in source
    assert "pg_restore" in source


def test_recovery_does_not_upload_or_deploy() -> None:
    source = "\n".join(
        _source(name) for name in ("backup_bundle.py", "restore_runner.py", "cli.py")
    )
    for forbidden in ("upload-artifact", "github.token", "docker push", "cosign", "promotion"):
        assert forbidden not in source


def test_controlled_recovery_dispatch_inputs_are_explicit_and_off_by_default() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    inputs = workflow.split("\njobs:", 1)[0]
    assert re.search(
        r"execute_controlled_recovery_acceptance:\n"
        r"\s+description:.*\n\s+required: true\n"
        r"\s+type: boolean\n\s+default: false",
        inputs,
    )
    assert re.search(
        r"expected_recovery_source_sha:\n"
        r"\s+description:.*\n\s+required: false\n"
        r"\s+type: string\n\s+default: \"\"",
        inputs,
    )


def test_controlled_recovery_job_is_exact_main_dispatch_only_and_least_privilege() -> None:
    job = _workflow_job("controlled-recovery-acceptance")
    required_guard = (
        "github.event_name == 'workflow_dispatch'",
        "inputs.execute_controlled_recovery_acceptance == true",
        "inputs.expected_recovery_source_sha != ''",
        "github.ref == 'refs/heads/main'",
    )
    for condition in required_guard:
        assert condition in job
    for excluded_input in (
        "execute_live_evidence_capture",
        "upload_live_evidence_artifact",
        "upload_verified_transport_handoff",
        "verify_live_evidence_artifact_transport",
        "verify_verified_transport_handoff",
        "create_live_evidence_attestation",
        "assemble_live_evidence",
    ):
        assert f"inputs.{excluded_input} != true" in job
    assert "GITHUB_SHA" in job
    assert "RECOVERY_SOURCE_SHA_MISMATCH" in job
    assert "permissions:\n      contents: read" in job
    assert "id-token: write" not in job
    assert "contents: write" not in job
    assert "packages: write" not in job
    assert "secrets." not in job


def test_controlled_recovery_reuses_canonical_cli_and_publishes_seven_file_evidence() -> None:
    job = _workflow_job("controlled-recovery-acceptance")
    for command in (
        "python -m cold_storage.recovery.cli backup",
        "python -m cold_storage.recovery.cli restore-isolated",
        "python -m cold_storage.recovery.cli verify-restore",
        "--execute-backup",
        "--execute-restore",
        "TASK012_BACKUP_AUTHORIZED: YES",
        "TASK012_ISOLATED_RESTORE_AUTHORIZED: YES",
    ):
        assert command in job
    for evidence_file in (
        "acceptance-summary.json",
        "backup-manifest.json",
        "database-inventory.json",
        "artifact-inventory.json",
        "restore-receipt.json",
        "SHA256SUMS",
        "SHA256SUMS.sha256",
    ):
        assert evidence_file in job
    assert "CONTROLLED_SYNTHETIC_DATA=YES" in job
    assert "REAL_PRODUCTION_DATA=NO" in job
    assert "TARGET_DATABASE_EMPTY=YES" in job
    assert "TARGET_ARTIFACT_STORAGE_EMPTY=YES" in job
    assert "SOURCE_DATABASE_MUTATION_DURING_RECOVERY=NO" in job
    assert "SOURCE_ARTIFACT_MUTATION_DURING_RECOVERY=NO" in job
    assert "actions/upload-artifact@v4" in job
    assert (
        "path: ${{ runner.temp }}/task012-controlled-recovery/controlled-recovery-evidence/" in job
    )
    assert "compression-level: 0" in job
    assert "overwrite: false" in job
    assert "retention-days: 30" in job
    assert "if-no-files-found: error" in job
    assert 'test "$(find "${EVIDENCE_DIR}" -maxdepth 1 -type f' in job
    assert "RAW_DATABASE_DUMP_UPLOADED=NO" in job
    assert "RAW_ARTIFACT_ARCHIVE_UPLOADED=NO" in job


def test_slice2_live_jobs_are_mutually_exclusive_with_controlled_recovery() -> None:
    for name in (
        "live-evidence-capture",
        "live-evidence-artifact-transport-verify",
        "live-evidence-attestation-create",
        "live-evidence-assembly",
        "live-evidence-verified-transport-handoff-verify",
    ):
        assert "inputs.execute_controlled_recovery_acceptance != true" in _workflow_job(name)
