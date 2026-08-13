from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODULE = PROJECT_ROOT / "backend/src/cold_storage/release/end_to_end_operational_acceptance.py"
FIXTURE = PROJECT_ROOT / "backend/src/cold_storage/bootstrap/s6_07_controlled_fixture.py"
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
    assert "async with app.router.lifespan_context(app):" in workflow
    assert "asyncio.run(collect_manifest())" in workflow
    assert "from fastapi.testclient import TestClient" not in workflow
    assert "starlette.testclient" not in workflow
    assert "httpx2" not in workflow
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


def test_s6_07_runtime_probe_is_production_compatible_and_cleanup_has_compose_env() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    job_env, _steps = workflow.split("    steps:", 1)

    assert "POSTGRES_PASSWORD: synthetic-only-s6-07-password" in job_env
    assert "POSTGRES_DB: cold_storage_s6_07" in job_env
    assert "POSTGRES_USER: cold_storage" in job_env

    cleanup = workflow.index("- name: Cleanup controlled runtime")
    teardown = workflow.index("docker compose -f docker-compose.production.yml", cleanup)
    assert "down -v --remove-orphans" in workflow[teardown:]


def test_s6_07_persists_compose_identity_across_steps() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    build_start = workflow.index("- name: Build and start synthetic strict runtime")
    exercise = workflow.index("- name: Exercise canonical HTTP and persistence surfaces")
    restart = workflow.index(
        'docker compose -f docker-compose.production.yml -f "${COMPOSE_OVERRIDE}" restart backend',
        exercise,
    )
    cleanup = workflow.index("- name: Cleanup controlled runtime")
    build_section = workflow[build_start:exercise]

    for name in (
        "COLD_STORAGE_BUILD_COMMIT_SHA",
        "COLD_STORAGE_BUILD_VERSION",
        "COLD_STORAGE_DEPLOYMENT_ID",
        "SOURCE_DATE_EPOCH",
        "COMPOSE_PROJECT_NAME",
    ):
        assert f"export {name}=" in build_section
        assert f'echo "{name}=${{{name}}}"' in build_section

    persistence = build_section.index(
        'echo "COLD_STORAGE_BUILD_COMMIT_SHA=${COLD_STORAGE_BUILD_COMMIT_SHA}"'
    )
    assert persistence < restart - build_start
    assert persistence < cleanup - build_start

    postgres_url_export = workflow.index("export S6_07_POSTGRES_URL=", build_start, exercise)
    postgres_url_persist = workflow.index(
        'echo "S6_07_POSTGRES_URL=${S6_07_POSTGRES_URL}"',
        postgres_url_export,
        exercise,
    )
    create_authority = workflow.index(
        "create-production-authority",
        exercise,
    )
    create_database_url = workflow.index(
        '--database-url "${S6_07_POSTGRES_URL}"',
        create_authority,
    )
    reload_authority = workflow.index("reload-production-authority", exercise)
    reload_database_url = workflow.index(
        '--database-url "${S6_07_POSTGRES_URL}"',
        reload_authority,
    )
    assert postgres_url_export < postgres_url_persist < create_authority
    assert create_authority < create_database_url < reload_authority < reload_database_url


def test_workflow_stages_refreshed_s6_06_metadata_after_exact_validation() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    run_api = workflow.index('"/repos/${GITHUB_REPOSITORY}/actions/runs/${S6_06_RUN_ID}"')
    artifact_api = workflow.index(
        '"/repos/${GITHUB_REPOSITORY}/actions/artifacts/${S6_06_ARTIFACT_ID}"'
    )
    run_validation = workflow.index('jq -e --arg sha "${SOURCE_SHA}"')
    artifact_validation = workflow.index('jq -e --arg digest "${S6_06_ARTIFACT_DIGEST}"')
    run_staging = workflow.index('cp "${RUN_ROOT}/s6-06-run.json"')
    artifact_staging = workflow.index('cp "${RUN_ROOT}/s6-06-artifact.json"')
    historical_runs = workflow.index("while IFS= read -r run_id; do")
    historical_artifacts = workflow.index("while IFS= read -r artifact_id; do")
    verifier = workflow.index("verify-s6-06-prerequisite")

    assert run_api < run_validation < run_staging < historical_runs < verifier
    assert artifact_api < artifact_validation < artifact_staging < historical_artifacts < verifier
    assert '"${S6_06_METADATA}/run-${S6_06_RUN_ID}.json"' in workflow
    assert '"${S6_06_METADATA}/artifact-${S6_06_ARTIFACT_ID}.json"' in workflow
    assert 'if [ "${run_id}" = "${S6_06_RUN_ID}" ]; then' in workflow
    assert 'if [ "${artifact_id}" = "${S6_06_ARTIFACT_ID}" ]; then' in workflow
    assert '"${RUN_ROOT}/s6-06-run.json"' in workflow
    assert '"${RUN_ROOT}/s6-06-artifact.json"' in workflow


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


def test_controlled_support_does_not_construct_production_output_orm() -> None:
    tree = ast.parse(FIXTURE.read_text(encoding="utf-8"))
    forbidden = {"CalculationRunRecord", "SourceBindingRecord"}
    calls = [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert forbidden.isdisjoint(calls)


def test_controlled_support_uses_canonical_production_execution_surface() -> None:
    content = FIXTURE.read_text(encoding="utf-8")
    source_binding = (
        PROJECT_ROOT
        / "backend/src/cold_storage/modules/orchestration/application/production_source_binding.py"
    ).read_text(encoding="utf-8")
    for required in (
        "OrchestrationService",
        "ProductionSourceBindingUseCase",
        "compose_production_source_binding_use_case_with_strict_resolver",
        "generate_production_scheme_run",
        "SqlAlchemyVerificationReadPort",
    ):
        assert required in content
    assert "execute_transaction_b" in source_binding


def test_controlled_support_is_outside_pure_release_package() -> None:
    release_root = PROJECT_ROOT / "backend/src/cold_storage/release"
    assert not (release_root / "s6_07_controlled_fixture.py").exists()
    fixture = FIXTURE.read_text(encoding="utf-8")
    assert "from sqlalchemy" in fixture
    assert "modules.infrastructure.orm" not in fixture


def test_strict_acceptance_sets_explicit_probe_timeouts() -> None:
    integration = INTEGRATION.read_text(encoding="utf-8")
    assert 'COLD_STORAGE_ENVIRONMENT_ID", "production"' in integration
    assert 'COLD_STORAGE_STARTUP_PROBE_TIMEOUT_SECONDS", "120"' in integration
    assert 'COLD_STORAGE_READINESS_PROBE_TIMEOUT_SECONDS", "30"' in integration


def test_workflow_requires_package3_and_base_lineage() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "git merge-base --is-ancestor" in workflow
    assert "5adda901285b8a567dac10460dd9e9fa72ea58a0" in workflow
    assert "c287aba48201ac9bfc0786f62911cd25fabf3fc4" in workflow
    assert '"${GITHUB_SHA}"' in workflow


def test_strict_acceptance_fixture_declares_resource_identity_and_storage_contract() -> None:
    integration = INTEGRATION.read_text(encoding="utf-8")
    for required in (
        'COLD_STORAGE_DATABASE_ENVIRONMENT_ID", "ci-strict"',
        'COLD_STORAGE_SECRET_ENVIRONMENT_ID", "ci-strict"',
        'COLD_STORAGE_ARTIFACT_ENVIRONMENT_ID", "ci-strict"',
        'COLD_STORAGE_ARTIFACT_STORAGE_DIR", str(artifact_dir)',
    ):
        assert required in integration


def test_s6_07_does_not_modify_investment_review_semantics() -> None:
    investment = (
        PROJECT_ROOT / "backend/src/cold_storage/modules/calculations/domain/investment.py"
    ).read_text(encoding="utf-8")
    assert "coefficient_overrides" not in investment
    assert '"DEMO_INVESTMENT_REQUIRES_REVIEW"' in investment
    assert "requires_review=True" in investment


def test_s6_07_has_no_cross_domain_coefficient_mapping() -> None:
    source_binding = (
        PROJECT_ROOT
        / "backend/src/cold_storage/modules/orchestration/application/source_binding_assembly.py"
    ).read_text(encoding="utf-8")
    assert "_controlled_coefficient_inputs" not in source_binding
    assert "controlled_bindings" not in source_binding
    assert "pallet.net_load_kg" not in source_binding
    assert 'Decimal("160")' not in source_binding
    assert "_investment_coefficients" not in source_binding


def test_s6_07_does_not_rewrite_calculator_provenance() -> None:
    source_binding = (
        PROJECT_ROOT
        / "backend/src/cold_storage/modules/orchestration/application/source_binding_assembly.py"
    ).read_text(encoding="utf-8")
    assert "replace(provenance" not in source_binding
    assert "controlled_bindings" not in source_binding
    assert "coefficient_context" in source_binding


def test_s6_07_fixture_does_not_insert_calculation_runs() -> None:
    tree = ast.parse(FIXTURE.read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.Name) and node.id == "CalculationRunRecord" for node in ast.walk(tree)
    )


def test_s6_07_fixture_does_not_insert_source_binding() -> None:
    tree = ast.parse(FIXTURE.read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.Name) and node.id == "SourceBindingRecord" for node in ast.walk(tree)
    )


def test_synthetic_business_inputs_are_allowed() -> None:
    fixture = FIXTURE.read_text(encoding="utf-8")
    assert '"product_category": "synthetic"' in fixture
    assert 'CONTROLLED_COEFFICIENT_CODE_PREFIX = "s6_07_operational_"' in fixture


def test_requires_review_true_is_not_operational_failure() -> None:
    acceptance = MODULE.read_text(encoding="utf-8")
    assert 'stage_mapping.get("requires_review") is True' not in acceptance
    assert '"requires_review" in stage_mapping' in acceptance


def test_business_warning_does_not_imply_operational_failure() -> None:
    unit = (
        PROJECT_ROOT / "backend/tests/unit/test_end_to_end_operational_acceptance.py"
    ).read_text(encoding="utf-8")
    assert "test_requires_review_warning_is_not_operational_failure" in unit
