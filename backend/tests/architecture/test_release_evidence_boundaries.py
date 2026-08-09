"""Architecture boundary tests for release evidence (S2_GAP_03/04 path scope).

Enforces that:
* release-evidence code lives only under ``cold_storage.release``;
* the ``release`` package does not import framework/runtime layers
  (fastapi, sqlalchemy, redis, openai) — it is a pure verification layer;
* every error code in the frozen table is exercised by exactly one
  negative-scenario fixture;
* all 20 frozen NR scenarios map to distinct fixtures.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from cold_storage.release.negative_scenario_fixtures import all_negative_scenarios
from cold_storage.release.provenance_schema import ALL_ERROR_CODES

BACKEND_SRC = Path(__file__).resolve().parents[2] / "src" / "cold_storage"
RELEASE_DIR = BACKEND_SRC / "release"
PROJECT_ROOT = Path(__file__).resolve().parents[3]

_FORBIDDEN_IMPORTS = ("fastapi", "sqlalchemy", "redis", "openai", "uvicorn", "psycopg2", "alembic")


def _read_release_files() -> list[Path]:
    return [p for p in RELEASE_DIR.rglob("*.py") if "__pycache__" not in p.parts]


def test_release_module_exists() -> None:
    assert RELEASE_DIR.is_dir()
    files = _read_release_files()
    assert files, "release package must contain source files"


def test_release_package_does_not_import_framework_layers() -> None:
    """The release evidence layer is a pure verification layer."""
    files = _read_release_files()
    assert files
    for path in files:
        content = path.read_text()
        for forbidden in _FORBIDDEN_IMPORTS:
            assert f"import {forbidden}" not in content, f"{path} imports {forbidden}"
            assert f"from {forbidden}" not in content, f"{path} imports {forbidden}"


def test_release_evidence_does_not_leak_into_non_release_modules() -> None:
    """Non-release modules must not import from cold_storage.release."""
    non_release_files = [
        p
        for p in BACKEND_SRC.rglob("*.py")
        if "__pycache__" not in p.parts and "release" not in p.parts
    ]
    assert non_release_files
    for path in non_release_files:
        content = path.read_text()
        assert "cold_storage.release" not in content, (
            f"non-release module imports cold_storage.release: {path}"
        )


def test_all_20_error_codes_are_exercised() -> None:
    """Every frozen RC_* error code must appear in exactly one fixture."""
    scenarios = all_negative_scenarios()
    codes = [s.expected_error_code for s in scenarios]
    for code in ALL_ERROR_CODES:
        assert code in codes, f"error code not exercised by any fixture: {code}"
    assert len(codes) == len(set(codes)) == 20


def test_negative_scenario_fixture_ids_are_unique() -> None:
    scenarios = all_negative_scenarios()
    fixture_ids = [s.fixture_id for s in scenarios]
    assert len(fixture_ids) == len(set(fixture_ids)) == 20


@pytest.mark.parametrize("expected_code", ALL_ERROR_CODES)
def test_each_error_code_has_a_runnable_fixture(expected_code: str) -> None:
    scenarios = all_negative_scenarios()
    matching = [s for s in scenarios if s.expected_error_code == expected_code]
    assert len(matching) == 1, (
        f"expected exactly 1 fixture for {expected_code}, got {len(matching)}"
    )
    assert callable(matching[0].run)


def test_rc_source_identity_is_immutable_release_data() -> None:
    """RC source identity must not follow the evidence-tooling checkout HEAD."""
    schema = (RELEASE_DIR / "provenance_schema.py").read_text()
    assert 'EXPECTED_SOURCE_COMMIT_SHA = "043731fea4e60feb6b929c524c4b68e87ed67bd7"' in schema
    assert 'EXPECTED_SOURCE_TREE_SHA = "b456e77f07a0cef801c57d2f089a318c35c145c4"' in schema
    assert "EVIDENCE_TOOL_HEAD" in schema
    assert "git rev-parse HEAD" not in schema


def test_production_compose_requires_source_date_epoch() -> None:
    compose = (PROJECT_ROOT / "docker-compose.production.yml").read_text()
    assert "SOURCE_DATE_EPOCH: ${SOURCE_DATE_EPOCH:?source date epoch is required}" in compose
    assert "SOURCE_DATE_EPOCH:-0" not in compose
    assert "SOURCE_DATE_EPOCH: ${SOURCE_DATE_EPOCH:-0}" not in compose


def test_ci_source_timestamp_binding_preserves_event_source_semantics() -> None:
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    source_selection = "${{ github.event.pull_request.head.sha || github.sha }}"
    assert f'SOURCE_COMMIT_SHA="{source_selection}"' in workflow
    assert 'git cat-file -e "${SOURCE_COMMIT_SHA}^{commit}"' in workflow
    assert 'git show -s --format=%ct "${SOURCE_COMMIT_SHA}"' in workflow
    assert 'echo "SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}" >> "$GITHUB_ENV"' in workflow
    assert "date +%s" not in workflow
    assert "git show -s --format=%ct HEAD" not in workflow


def _backend_image_build_body() -> str:
    makefile = (PROJECT_ROOT / "Makefile").read_text()
    match = re.search(r"(?ms)^backend-image-build:\n(?P<body>.*?)(?=^\S|\Z)", makefile)
    assert match is not None, "backend-image-build target must exist"
    return match.group("body")


def test_make_backend_image_build_binds_context_and_source_timestamp() -> None:
    body = _backend_image_build_body()
    makefile = (PROJECT_ROOT / "Makefile").read_text()
    assert "RC_BUILD_CONTEXT ?= ." in makefile
    assert "cat-file -e" in body
    assert "rev-parse HEAD" in body
    assert "status --porcelain" in body
    assert "show -s --format=%ct" in body
    assert "''|*[!0-9]*)" in body
    assert "--build-arg SOURCE_DATE_EPOCH" in body
    assert '-f "$${context}/backend/Dockerfile"' in body
    assert '"$${context}"' in body
    assert "date +%s" not in body
    assert "format=%ct HEAD" not in body


def _git_run(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _make_test_context(root: Path, *, second_commit: bool = False) -> tuple[Path, str, str | None]:
    context = root / "rc-context"
    (context / "backend").mkdir(parents=True)
    (context / "backend" / "Dockerfile").write_text("FROM scratch\n")
    (context / "payload.txt").write_text("one\n")
    _git_run("init", "-q", cwd=context)
    _git_run("config", "user.email", "test@example.invalid", cwd=context)
    _git_run("config", "user.name", "test", cwd=context)
    _git_run("add", ".", cwd=context)
    _git_run("commit", "-qm", "initial", cwd=context)
    source_commit = _git_run("rev-parse", "HEAD", cwd=context)
    context_head = None
    if second_commit:
        (context / "payload.txt").write_text("two\n")
        _git_run("add", ".", cwd=context)
        _git_run("commit", "-qm", "second", cwd=context)
        context_head = _git_run("rev-parse", "HEAD", cwd=context)
    return context, source_commit, context_head


def _run_backend_image_build(
    context: Path,
    source_commit: str,
    mock_docker: Path,
    *,
    mock_docker_log: Path,
    version: str = "v0.2.0",
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "COLD_STORAGE_BUILD_COMMIT_SHA": source_commit,
            "COLD_STORAGE_BUILD_VERSION": version,
            "RC_BUILD_CONTEXT": str(context),
            "PATH": f"{mock_docker.parent}{os.pathsep}{env['PATH']}",
            "MOCK_DOCKER_LOG": str(mock_docker_log),
        }
    )
    return subprocess.run(
        ["make", "-C", str(PROJECT_ROOT), "backend-image-build"],
        env=env,
        capture_output=True,
        text=True,
    )


def _mock_docker(path: Path) -> Path:
    docker = path / "docker"
    docker.write_text('#!/bin/sh\nprintf \'%s\\n\' "$*" > "$MOCK_DOCKER_LOG"\n')
    docker.chmod(0o755)
    return docker


def test_make_backend_image_build_rejects_context_identity_mismatch(tmp_path: Path) -> None:
    context, source_commit, context_head = _make_test_context(tmp_path, second_commit=True)
    assert context_head is not None and context_head != source_commit
    (tmp_path / "bin").mkdir()
    mock_docker = _mock_docker(tmp_path / "bin")
    log = tmp_path / "docker.log"
    result = _run_backend_image_build(context, source_commit, mock_docker, mock_docker_log=log)
    assert result.returncode != 0
    assert "context HEAD" in result.stderr
    assert not log.exists()


def test_make_backend_image_build_rejects_dirty_context(tmp_path: Path) -> None:
    context, source_commit, _ = _make_test_context(tmp_path)
    (context / "dirty.txt").write_text("uncommitted\n")
    (tmp_path / "bin").mkdir()
    mock_docker = _mock_docker(tmp_path / "bin")
    log = tmp_path / "docker.log"
    result = _run_backend_image_build(context, source_commit, mock_docker, mock_docker_log=log)
    assert result.returncode != 0
    assert "dirty" in result.stderr
    assert not log.exists()


def test_make_backend_image_build_rejects_missing_source_commit(tmp_path: Path) -> None:
    context, _, _ = _make_test_context(tmp_path)
    (tmp_path / "bin").mkdir()
    mock_docker = _mock_docker(tmp_path / "bin")
    log = tmp_path / "docker.log"
    result = _run_backend_image_build(context, "f" * 40, mock_docker, mock_docker_log=log)
    assert result.returncode != 0
    assert "source commit" in result.stderr
    assert not log.exists()


def test_make_backend_image_build_forwards_source_derived_timestamp(tmp_path: Path) -> None:
    context, source_commit, _ = _make_test_context(tmp_path)
    (tmp_path / "bin").mkdir()
    mock_docker = _mock_docker(tmp_path / "bin")
    log = tmp_path / "docker.log"
    result = _run_backend_image_build(context, source_commit, mock_docker, mock_docker_log=log)
    assert result.returncode == 0, result.stderr
    invocation = log.read_text()
    expected_epoch = _git_run("show", "-s", "--format=%ct", source_commit, cwd=context)
    assert f"SOURCE_DATE_EPOCH={expected_epoch}" in invocation
    assert f"COLD_STORAGE_BUILD_COMMIT_SHA={source_commit}" in invocation


def test_live_runner_is_the_only_external_observation_adapter() -> None:
    runner = (RELEASE_DIR / "live_evidence_runner.py").read_text()
    collector = (RELEASE_DIR / "evidence_collector.py").read_text()
    verifier = (RELEASE_DIR / "digest_verifier.py").read_text()
    provenance = (RELEASE_DIR / "provenance_statement.py").read_text()
    assert "subprocess" in runner
    assert "collect_release_candidate_evidence" in runner
    assert "subprocess" not in collector
    assert "subprocess" not in verifier
    assert "subprocess" not in provenance
    assert "shell=True" not in runner
    assert "--push" not in runner
    assert "cosign" not in runner
    assert "id-token" not in runner


def test_live_runner_enforces_frozen_source_and_oci_observation_contract() -> None:
    runner = (RELEASE_DIR / "live_evidence_runner.py").read_text()
    assert "EXPECTED_SOURCE_COMMIT_SHA" in runner
    assert "EXPECTED_SOURCE_TREE_SHA" in runner
    assert '"worktree"' in runner
    assert '"add"' in runner
    assert '"--detach"' in runner
    assert "--ignored" in runner
    assert "--untracked-files=all" in runner
    assert "linux/amd64" in runner
    assert "--no-cache" in runner
    assert "type=oci,dest=" in runner
    assert "manifest_bytes_rehashed" in runner
    assert "sha256:" in runner
    assert "image_id_used" in runner
    assert "local_oci_manifest_digest" in runner


def test_live_runner_cli_and_workflow_dispatch_surface_are_gated() -> None:
    runner = (RELEASE_DIR / "live_evidence_runner.py").read_text()
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert 'subparsers.add_parser("capture-local")' in runner
    assert 'capture.add_argument("--execute-builds"' in runner
    assert 'capture.add_argument("--output-dir", required=True)' in runner
    assert '"TASK012_BUILD_A_B_AUTHORIZED"' in runner
    assert 'subparsers.add_parser("assemble")' in runner
    assert 'assemble.add_argument("--attestation-file", required=True)' in runner
    assert "workflow_dispatch:" in workflow
    assert "execute_live_evidence_capture" in workflow
    assert "expected_rc_source_sha" in workflow
    assert "default: false" in workflow
    assert "live-evidence-capture:" in workflow
    assert "github.event_name == 'workflow_dispatch'" in workflow
    assert "inputs.execute_live_evidence_capture == true" in workflow
    assert "refs/heads/main" in workflow
    assert "--execute-builds" in workflow


def test_release_evidence_make_target_includes_runner_tests() -> None:
    makefile = (PROJECT_ROOT / "Makefile").read_text()
    assert "tests/unit/test_live_evidence_runner.py" in makefile
    assert "tests/integration/test_live_evidence_runner.py" in makefile
