"""Harness-only tests for the V0.3 P5 controlled acceptance surface."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from cold_storage.evaluation.v03_controlled_acceptance import (
    EXECUTION_AUTHORIZATION_ENV,
    FIXTURE_PATHS,
    MAIN_REF,
    RUNBOOK_PATH,
    WORKFLOW_DISPATCH_EVENT,
    WORKFLOW_PATH,
    V03ControlledAcceptanceError,
    build_harness_status,
    execute_scenario,
    execution_authorized_from_env,
    ordinary_ci_is_controlled_acceptance,
    refuse_scenario_execution,
    validate_execution_authorization,
    validate_trusted_operator,
    validate_workflow_dispatch_gates,
    verify_harness_gates,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_FILE = REPO_ROOT / WORKFLOW_PATH
RUNBOOK_FILE = REPO_ROOT / RUNBOOK_PATH
RUNNER = Path(__file__).resolve().parent / "run_v03_controlled_acceptance.py"
FIXTURE_DATA_DIR = Path(__file__).resolve().parent / "data"

FIXTURE_SOURCE_DEFINITION_EVIDENCE = {
    "A": {
        "path": "backend/tests/pilot/data/v03-scenario-a-normal-formal-report.v1.json",
        "sha256": "b4227ea107c12571681d29ad7746175e73e05b0ffeb9e6d7fa5e61e0b9877d15",
    },
    "B": {
        "path": "backend/tests/pilot/data/v03-scenario-b-review-required-formal-report.v1.json",
        "sha256": "ff462cbaff0fadc77c809cd0a28917dd09ba0cea1ed73066d6fa1100f8552bbb",
    },
    "C": {
        "path": "backend/tests/pilot/data/v03-scenario-c-agent-knowledge-deterministic.v1.json",
        "sha256": "9ac8a43020bd6876909265e2e0e8286053bfb17c7152039d32b406f78fa9233a",
    },
}


def _fixture_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_fixture(scenario: str) -> dict[str, object]:
    fixture_path = FIXTURE_DATA_DIR / Path(FIXTURE_PATHS[scenario]).name
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def _runbook_fixture_hashes() -> dict[str, str]:
    text = RUNBOOK_FILE.read_text(encoding="utf-8")
    return {
        "A": re.search(r"SCENARIO_A_FIXTURE_SHA256=([0-9a-f]{64})", text).group(1),  # type: ignore[union-attr]
        "B": re.search(r"SCENARIO_B_FIXTURE_SHA256=([0-9a-f]{64})", text).group(1),  # type: ignore[union-attr]
        "C": re.search(r"SCENARIO_C_FIXTURE_SHA256=([0-9a-f]{64})", text).group(1),  # type: ignore[union-attr]
    }


def test_fixture_source_definition_files_exist_and_match_runbook() -> None:
    runbook_hashes = _runbook_fixture_hashes()
    for scenario, evidence in FIXTURE_SOURCE_DEFINITION_EVIDENCE.items():
        fixture_path = REPO_ROOT / evidence["path"]
        assert fixture_path.is_file()
        assert FIXTURE_PATHS[scenario] == evidence["path"]
        computed = _fixture_sha256(fixture_path)
        assert computed == evidence["sha256"]
        assert computed == runbook_hashes[scenario]


def test_scenario_a_fixture_is_review_not_required_path() -> None:
    fixture = _load_fixture("A")
    assert fixture["review_required"] is False
    assert fixture["workflow_goal"] == "FORMAL_REPORT"
    assert all(value is False for value in fixture["expected_requires_review"].values())


def test_scenario_b_fixture_requires_structured_review_and_blocks_formal_export() -> None:
    fixture = _load_fixture("B")
    assert fixture["review_required"] is True
    contract = fixture["review_reason_contract"]
    assert contract["structured_review_reason_required"] is True
    assert contract["source_type"] == "calculation_run"
    assert contract["formal_export_blocked_until_review_approval"] is True
    assert fixture["upstream_bindings"][0]["path"].endswith(
        "task011-followup-high-throughput-source.v1.json"
    )


def test_scenario_c_fixture_uses_fake_agent_and_page_level_provenance() -> None:
    fixture = _load_fixture("C")
    agent = fixture["agent_assistance"]
    assert agent["transport"] == "fake_or_mocked_gateway"
    assert agent["live_mimo_required"] is False
    assert agent["unavailable_blocks_core_workflow"] is False
    knowledge = fixture["knowledge_provenance"]
    assert knowledge["page_level_evidence_required"] is True
    assert "source_page_evidence_id" in knowledge["required_citation_fields"]
    assert "knowledge.search" in fixture["tool_sequence"]


def test_harness_status_is_not_authorized() -> None:
    status = build_harness_status()
    authorization = status["authorization"]
    assert authorization["CONTROLLED_ACCEPTANCE_AUTHORIZED"] == "NO"
    assert authorization["CONTROLLED_ACCEPTANCE_EXECUTED"] == "NO"
    assert authorization["SCENARIO_A_RUN_AUTHORIZED"] == "NO"
    assert authorization["SCENARIO_B_RUN_AUTHORIZED"] == "NO"
    assert authorization["SCENARIO_C_RUN_AUTHORIZED"] == "NO"
    assert authorization["FIXTURE_JSON_CREATE_AUTHORIZED"] == "NO"
    assert authorization["ORDINARY_PR_CI_IS_CONTROLLED_ACCEPTANCE"] == "NO"
    assert status["scenario_execution_implemented"] == "YES"
    assert status["scenario_execution_engine_round"] == "SCENARIO_EXECUTION_ENGINE_R1"


def test_ordinary_ci_is_not_controlled_acceptance() -> None:
    assert ordinary_ci_is_controlled_acceptance() is False


def test_execution_authorization_requires_explicit_flag() -> None:
    with pytest.raises(V03ControlledAcceptanceError) as exc_info:
        validate_execution_authorization("auth-record-1", execution_authorized=False)
    assert exc_info.value.code == "CONTROLLED_ACCEPTANCE_NOT_AUTHORIZED"


def test_execution_authorization_requires_record_id() -> None:
    with pytest.raises(V03ControlledAcceptanceError) as exc_info:
        validate_execution_authorization("", execution_authorized=True)
    assert exc_info.value.code == "CONTROLLED_ACCEPTANCE_AUTHORIZATION_RECORD_MISSING"


def test_rejected_operator_fails_closed() -> None:
    with pytest.raises(V03ControlledAcceptanceError) as exc_info:
        validate_trusted_operator("system")
    assert exc_info.value.code == "TRUSTED_OPERATOR_NOT_HUMAN"


def test_workflow_dispatch_gates_require_main_and_exact_source() -> None:
    result = validate_workflow_dispatch_gates(
        event_name=WORKFLOW_DISPATCH_EVENT,
        git_ref=MAIN_REF,
        checked_out_sha="abc123",
        checked_out_tree_sha="tree456",
        declared_source_sha="abc123",
        declared_source_tree_sha="tree456",
        authorization_record_id="auth-record-1",
        trusted_operator="controlled.operator",
    )
    assert result["execution_source_sha"] == "abc123"
    assert result["workflow_dispatch_only"] == "YES"


def test_workflow_dispatch_gates_reject_feature_branch() -> None:
    with pytest.raises(V03ControlledAcceptanceError) as exc_info:
        validate_workflow_dispatch_gates(
            event_name=WORKFLOW_DISPATCH_EVENT,
            git_ref="refs/heads/cursor/feature",
            checked_out_sha="abc123",
            checked_out_tree_sha="tree456",
            declared_source_sha="abc123",
            declared_source_tree_sha="tree456",
            authorization_record_id="auth-record-1",
            trusted_operator="controlled.operator",
        )
    assert exc_info.value.code == "WORKFLOW_MAIN_REF_REQUIRED"


def test_workflow_dispatch_gates_reject_non_dispatch_event() -> None:
    with pytest.raises(V03ControlledAcceptanceError) as exc_info:
        validate_workflow_dispatch_gates(
            event_name="pull_request",
            git_ref=MAIN_REF,
            checked_out_sha="abc123",
            checked_out_tree_sha="tree456",
            declared_source_sha="abc123",
            declared_source_tree_sha="tree456",
            authorization_record_id="auth-record-1",
            trusted_operator="controlled.operator",
        )
    assert exc_info.value.code == "WORKFLOW_DISPATCH_REQUIRED"


def test_refuse_scenario_execution_without_authorization_flag() -> None:
    with pytest.raises(V03ControlledAcceptanceError) as exc_info:
        refuse_scenario_execution(
            scenario="A",
            authorization_record_id="auth-record-1",
            trusted_operator="controlled.operator",
            execution_source_sha="abc123",
            execution_source_tree_sha="tree456",
            execution_authorized=False,
            backend="sqlite",
            run_index=1,
        )
    assert exc_info.value.code == "CONTROLLED_ACCEPTANCE_NOT_AUTHORIZED"


def test_refuse_scenario_execution_even_when_explicitly_authorized() -> None:
    with pytest.raises(V03ControlledAcceptanceError) as exc_info:
        refuse_scenario_execution(
            scenario="C",
            authorization_record_id="auth-record-1",
            trusted_operator="controlled.operator",
            execution_source_sha="abc123",
            execution_source_tree_sha="tree456",
            execution_authorized=True,
            backend="postgresql",
            run_index=1,
        )
    assert exc_info.value.code == "SCENARIO_DATABASE_URL_REQUIRED"


def test_verify_harness_gates_returns_status_payload() -> None:
    payload = verify_harness_gates(
        authorization_record_id="auth-record-1",
        trusted_operator="controlled.operator",
        execution_source_sha="abc123",
        execution_source_tree_sha="tree456",
    )
    assert payload["status"] == "PASS"
    assert payload["gate"] == "HARNESS_VERIFY"
    assert payload["harness"]["authorization"]["CONTROLLED_ACCEPTANCE_AUTHORIZED"] == "NO"


def test_execution_authorized_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(EXECUTION_AUTHORIZATION_ENV, raising=False)
    assert execution_authorized_from_env() is False
    monkeypatch.setenv(EXECUTION_AUTHORIZATION_ENV, "YES")
    assert execution_authorized_from_env() is True


def test_runner_run_command_fails_closed_without_execution_flag(tmp_path: Path) -> None:
    output = tmp_path / "blocked.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "run",
            "--scenario",
            "A",
            "--authorization-record-id",
            "auth-record-1",
            "--trusted-operator",
            "controlled.operator",
            "--execution-source-sha",
            "abc123",
            "--execution-source-tree-sha",
            "tree456",
            "--backend",
            "sqlite",
            "--run-index",
            "1",
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT / "backend",
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "BLOCKED"
    assert payload["error"]["code"] == "CONTROLLED_ACCEPTANCE_NOT_AUTHORIZED"


def test_runner_verify_gates_command_succeeds(tmp_path: Path) -> None:
    output = tmp_path / "verify.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "verify-gates",
            "--authorization-record-id",
            "auth-record-1",
            "--trusted-operator",
            "controlled.operator",
            "--execution-source-sha",
            "abc123",
            "--execution-source-tree-sha",
            "tree456",
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT / "backend",
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"


def test_workflow_is_dispatch_only_main_bound_and_production_operation_free() -> None:
    workflow_text = WORKFLOW_FILE.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow_text
    assert "pull_request:" not in workflow_text
    assert "push:" not in workflow_text
    assert 'if: github.ref == \'refs/heads/main\'' in workflow_text
    assert 'ref: main' in workflow_text
    assert 'test "${GITHUB_EVENT_NAME}" = "workflow_dispatch"' in workflow_text
    assert 'test "${GITHUB_REF}" = "refs/heads/main"' in workflow_text
    assert "DROP DATABASE" not in workflow_text
    assert "git push" not in workflow_text
    assert "gh release" not in workflow_text


def test_workflow_contains_scenario_backend_matrix_for_execution_authorized_yes() -> None:
    workflow_text = WORKFLOW_FILE.read_text(encoding="utf-8")
    assert 'default: "NO"' in workflow_text
    assert 'if [ "${EXECUTION_AUTHORIZED_INPUT}" = "YES" ]; then' in workflow_text
    assert 'for scenario in A B C; do' in workflow_text
    for scenario in ("A", "B", "C"):
        assert f'--scenario "${{scenario}}"' in workflow_text or f'--scenario "{scenario}"' in workflow_text
    assert '--backend sqlite' in workflow_text
    assert '--backend postgresql' in workflow_text
    assert "--execution-authorized" in workflow_text
    assert "--database-url" in workflow_text
    assert "pgvector/pgvector:pg16" in workflow_text
    assert "CONTROLLED_ACCEPTANCE_SCENARIO_MATRIX_EXECUTED=YES" in workflow_text
    assert "CONTROLLED_ACCEPTANCE_EXECUTION_REFUSED=YES" in workflow_text
    assert '--scenario A' in workflow_text
    assert "scenario execution must fail closed without explicit authorization" in workflow_text


def test_workflow_does_not_modify_p1_workflow_file() -> None:
    p1_workflow = (REPO_ROOT / ".github/workflows/v0-3-p1-review-formal-report-acceptance.yml").read_text(
        encoding="utf-8"
    )
    assert "v03-p1-review-formal-report-acceptance" in p1_workflow


def test_runner_respects_env_execution_authorization_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(EXECUTION_AUTHORIZATION_ENV, "YES")
    output = tmp_path / "blocked-authorized.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "run",
            "--scenario",
            "B",
            "--authorization-record-id",
            "auth-record-1",
            "--trusted-operator",
            "controlled.operator",
            "--execution-source-sha",
            "abc123",
            "--execution-source-tree-sha",
            "tree456",
            "--backend",
            "postgresql",
            "--run-index",
            "1",
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT / "backend",
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["error"]["code"] == "DATABASE_URL_REQUIRED"


def test_execute_scenario_a_on_fresh_sqlite(tmp_path: Path) -> None:
    from tests.pilot.run_v03_controlled_acceptance import (
        _build_scenario_execution_support,
        _provision_sqlite_database,
    )

    db_path = tmp_path / "scenario-a.db"
    database_url = _provision_sqlite_database(f"sqlite:///{db_path}")
    output_root = tmp_path / "scenario-a-output"
    evidence = execute_scenario(
        scenario="A",
        authorization_record_id="auth-record-scenario-a",
        trusted_operator="controlled.operator",
        execution_source_sha="abc123",
        execution_source_tree_sha="tree456",
        execution_authorized=True,
        backend="sqlite",
        run_index=1,
        database_url=database_url,
        output_root=output_root,
        repo_root=REPO_ROOT,
        execution_support=_build_scenario_execution_support(),
    )
    assert evidence["result"]["status"] == "PASS"
    assert evidence["scenario"] == "A"
    lifecycle = evidence["scenario_result"]["lifecycle"]
    assert lifecycle["review_actions"] == ["submit_review", "mark_reviewed", "approve"]
    assert set(lifecycle["artifacts"]) == {
        "zh-CN/docx",
        "zh-CN/pdf",
        "en-US/docx",
        "en-US/pdf",
    }
    assert evidence["scenario_result"]["scheme_authority"]["requires_review"] is False


def test_execute_scenario_a_fails_closed_when_report_stays_draft(tmp_path: Path) -> None:
    from tests.evaluation._seed_helpers import (
        SOURCE_BINDING_ID,
        WEIGHT_REVISION_ID,
        seed_a1_all_prereqs,
    )
    from tests.pilot.run_v03_controlled_acceptance import _provision_sqlite_database
    from cold_storage.evaluation.v03_controlled_acceptance import (
        ScenarioAExecutionBinding,
        ScenarioExecutionSupport,
        execute_scenario,
    )

    support = ScenarioExecutionSupport(
        scenario_a=ScenarioAExecutionBinding(
            source_binding_id=SOURCE_BINDING_ID,
            weight_set_revision_id=WEIGHT_REVISION_ID,
            seed_prereqs=seed_a1_all_prereqs,
        ),
        scenario_b_source_runtime=None,
    )
    db_path = tmp_path / "scenario-a-draft.db"
    database_url = _provision_sqlite_database(f"sqlite:///{db_path}")
    with pytest.raises(V03ControlledAcceptanceError) as exc_info:
        execute_scenario(
            scenario="A",
            authorization_record_id="auth-record-scenario-a-draft",
            trusted_operator="controlled.operator",
            execution_source_sha="abc123",
            execution_source_tree_sha="tree456",
            execution_authorized=True,
            backend="sqlite",
            run_index=1,
            database_url=database_url,
            output_root=tmp_path / "scenario-a-draft-output",
            repo_root=REPO_ROOT,
            execution_support=support,
        )
    assert exc_info.value.code == "REPORT_NOT_GENERATED"
    assert exc_info.value.details["report_status_after_generate_revision"] == "draft"
    blockers = exc_info.value.details["quality_blockers_after_generate_revision"]
    assert any(
        blocker.get("field_path") == "scheme_comparison.recommended_scheme"
        for blocker in blockers
    )


def test_execute_scenario_c_on_fresh_sqlite(tmp_path: Path) -> None:
    from tests.pilot.run_v03_controlled_acceptance import _provision_sqlite_database

    db_path = tmp_path / "scenario-c.db"
    database_url = _provision_sqlite_database(f"sqlite:///{db_path}")
    output_root = tmp_path / "scenario-c-output"
    evidence = execute_scenario(
        scenario="C",
        authorization_record_id="auth-record-scenario-c",
        trusted_operator="controlled.operator",
        execution_source_sha="abc123",
        execution_source_tree_sha="tree456",
        execution_authorized=True,
        backend="sqlite",
        run_index=1,
        database_url=database_url,
        output_root=output_root,
        repo_root=REPO_ROOT,
    )
    assert evidence["result"]["status"] == "PASS"
    assert evidence["scenario"] == "C"
    assert evidence["scenario_result"]["agent_assistance"]["clarification_observed"] is True
    assert evidence["scenario_result"]["knowledge_provenance"]["search_result_count"] >= 1


def test_resolve_database_url_auto_provisions_fresh_sqlite() -> None:
    from sqlalchemy import create_engine, inspect

    from tests.pilot.run_v03_controlled_acceptance import (
        _provision_sqlite_database,
        _resolve_database_url,
    )

    database_url = _resolve_database_url(backend="sqlite", database_url=None)
    assert database_url.startswith("sqlite:///")
    db_path = Path(database_url.removeprefix("sqlite:///"))
    assert db_path.is_file()
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    try:
        assert inspect(engine).has_table("projects")
    finally:
        engine.dispose()
    with pytest.raises(V03ControlledAcceptanceError) as exc_info:
        _provision_sqlite_database(database_url)
    assert exc_info.value.code == "DATABASE_URL_INVALID"
    assert "already exists" in str(exc_info.value)


def test_provision_sqlite_database_rejects_existing_file(tmp_path: Path) -> None:
    from tests.pilot.run_v03_controlled_acceptance import _provision_sqlite_database

    db_path = tmp_path / "existing.db"
    db_path.write_bytes(b"")
    with pytest.raises(V03ControlledAcceptanceError) as exc_info:
        _provision_sqlite_database(f"sqlite:///{db_path}")
    assert exc_info.value.code == "DATABASE_URL_INVALID"
    assert exc_info.value.details["database_path"] == str(db_path.resolve())


def test_runner_sqlite_auto_provision_passes_database_url_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.pilot.run_v03_controlled_acceptance import main

    captured: dict[str, str] = {}

    def _fake_execute_scenario(**kwargs: object) -> dict[str, object]:
        captured["database_url"] = str(kwargs["database_url"])
        return {"result": {"status": "PASS"}}

    monkeypatch.setattr(
        "tests.pilot.run_v03_controlled_acceptance.execute_scenario",
        _fake_execute_scenario,
    )
    output = tmp_path / "auto-provision.json"
    result = main(
        [
            "run",
            "--scenario",
            "A",
            "--authorization-record-id",
            "auth-record-auto-provision",
            "--trusted-operator",
            "controlled.operator",
            "--execution-source-sha",
            "abc123",
            "--execution-source-tree-sha",
            "tree456",
            "--backend",
            "sqlite",
            "--run-index",
            "1",
            "--execution-authorized",
            "--output",
            str(output),
        ]
    )
    assert result == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["result"]["status"] == "PASS"
    database_url = captured["database_url"]
    assert database_url.startswith("sqlite:///")
    assert Path(database_url.removeprefix("sqlite:///")).is_file()
