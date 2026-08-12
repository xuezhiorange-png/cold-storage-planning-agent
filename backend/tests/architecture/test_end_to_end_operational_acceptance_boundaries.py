from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODULE = PROJECT_ROOT / "backend/src/cold_storage/release/end_to_end_operational_acceptance.py"
FIXTURE = PROJECT_ROOT / "backend/src/cold_storage/release/s6_07_controlled_fixture.py"
WORKFLOW = PROJECT_ROOT / ".github/workflows/task012-slice6-s7-e2e-operational-acceptance.yml"
INTEGRATION = PROJECT_ROOT / "backend/tests/integration/test_end_to_end_operational_acceptance.py"


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
    assert "if: >-" not in workflow.split("    runs-on:", 1)[0]
    assert 'if [ "${GITHUB_REF}" != "refs/heads/main" ]' in workflow
    assert 'if [ "${GITHUB_SHA}" != "${EXPECTED_SOURCE_SHA}"' in workflow
    assert "ERROR_CODE=S6_07_EXECUTION_NOT_AUTHORIZED" in workflow
    assert "ERROR_CODE=S6_07_SOURCE_SHA_MISMATCH" in workflow
    assert "ERROR_CODE=S6_07_SOURCE_TREE_INVALID" in workflow
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
    assert 'observation_type:"raw"' in workflow
    assert "task012-s6-07-operational-observation-v2" in workflow
    assert "if $scheme_status" not in workflow
    assert "persisted:($scheme[0].body // {})" not in workflow
    assert "source_binding:(($scheme[0].body.source_binding // {}))" not in workflow
    assert "composition-manifest.json" in workflow
    assert "composition_manifest_tokens" in workflow
    assert "TestClient(create_app())" in workflow
    assert "production-authority.json" in workflow
    assert "scheme-http-readback-before-restart.json" in workflow
    assert "scheme-http-readback-after-restart.json" in workflow
    assert "production-authority-after-restart.json" in workflow
    assert "resource-identities.yml" in workflow
    assert "COLD_STORAGE_DATABASE_ENVIRONMENT_ID: ci-strict" in workflow
    assert "COLD_STORAGE_SECRET_ENVIRONMENT_ID: ci-strict" in workflow
    assert "COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID: ci-strict" in workflow
    assert "migration:{exit_code:0" not in workflow
    assert 'database:{backend:"postgresql"' not in workflow
    assert 'parseable_record_count="${structured_record_count}"' not in workflow
    for forbidden_self_attestation in (
        "canonical_database_engine:",
        "canonical_artifact_storage:",
        "strict_capability_audit:",
        "coefficient_backend:",
        "fake_agent_gateway_constructed_in_strict_mode:",
        "no_demo_coefficient_used:",
        "no_latest_row_fallback:",
        "no_partial_source_binding:",
        "power_authority_binding:",
        "source_archive_verification:",
    ):
        assert forbidden_self_attestation not in workflow


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


def test_s6_07_workflow_is_not_a_normal_ci_surface() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request:" not in workflow
    assert "push:" not in workflow
    assert "on:\n  workflow_dispatch:" in workflow


def test_observation_and_verifier_boundaries_are_explicit() -> None:
    content = MODULE.read_text(encoding="utf-8")
    assert "S6_07_RAW_OBSERVATION_SCHEMA" in content
    assert "_derive_assertions" in content
    assert '"observation_type": "raw"' in content
    assert "_validate_observations" in content
    assert "scheme_status" not in content
    assert "fake_agent_gateway_constructed_in_strict_mode" not in content


def test_ci_contains_a_real_focused_postgresql_acceptance_surface() -> None:
    ci = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "S6-07 PostgreSQL persistence acceptance" in ci
    assert "tests/integration/test_end_to_end_operational_acceptance.py" in ci
    assert "S6_07_POSTGRES_URL" in ci


def test_persistence_probe_uses_canonical_persisted_read_ports() -> None:
    module = MODULE.read_text(encoding="utf-8")
    integration = INTEGRATION.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "canonical_persistence" in module
    assert "source_binding_after_restart" in module
    assert "source_archive_verification_after_restart" in module
    assert "independent_rehash" in module
    for required in (
        "s6_07_controlled_fixture",
        "create_controlled_production_authority",
        "read_production_authority",
        "test_postgresql_production_authority_survives_fresh_engine_reload",
    ):
        assert required in integration
    for forbidden in ("tests.integration", "tests.evaluation", "test_postgresql_"):
        assert forbidden not in workflow
    assert "seed-startup-readiness" in workflow
    assert "create-production-authority" in workflow
    assert "reload-production-authority" in workflow
    assert "scheme_create_response" not in integration
    assert "source_binding = scheme_create_response" not in integration


def test_controlled_workflow_seeds_readiness_before_strict_backend_start() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    seed_index = workflow.index("seed-startup-readiness")
    backend_index = workflow.index("up -d backend")
    assert seed_index < backend_index
    assert "STARTUP_REQUIRED_STAGE_COUNT" in workflow
    assert "STARTUP_SEEDED_STAGE_COUNT" in workflow
    assert "READINESS_SEED_BEFORE_BACKEND_START=PASS" in workflow


def test_controlled_fixture_is_formal_non_production_support_boundary() -> None:
    fixture = FIXTURE.read_text(encoding="utf-8")
    assert "seed_startup_readiness" in fixture
    assert "create_controlled_production_authority" in fixture
    assert "read_production_authority" in fixture
    assert "tests.integration" not in fixture
    assert "tests.evaluation" not in fixture
    production_root = PROJECT_ROOT / "backend/src/cold_storage"
    production_files = [path for path in production_root.rglob("*.py") if path != FIXTURE]
    assert all(
        "s6_07_controlled_fixture" not in path.read_text(encoding="utf-8")
        for path in production_files
    )


def test_strict_acceptance_fixture_declares_resource_identity_and_storage_contract() -> None:
    integration = INTEGRATION.read_text(encoding="utf-8")
    for required in (
        'COLD_STORAGE_DATABASE_ENVIRONMENT_ID", "ci-strict"',
        'COLD_STORAGE_SECRET_ENVIRONMENT_ID", "ci-strict"',
        'COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID", "ci-strict"',
        'COLD_STORAGE_ARTIFACT_STORAGE_DIR", str(artifact_dir)',
    ):
        assert required in integration
