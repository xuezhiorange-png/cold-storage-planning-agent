"""Architecture locks for the V2.0 P2 read-only consumer alignment."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from cold_storage.modules.orchestration.domain.contracts import CalculationType

REPO_ROOT = Path(__file__).resolve().parents[3]
P0_CONTRACT_PATH = (
    REPO_ROOT / "docs" / "tasks" / "V2_0-P0-factory-power-estimation-and-presentation-contract.md"
)
P1_TASK_PATH = (
    REPO_ROOT
    / "docs"
    / "tasks"
    / "V2_0-P1-factory-power-estimation-canonical-result-implementation.md"
)
P2_TASK_PATH = (
    REPO_ROOT / "docs" / "tasks" / "V2_0-P2-factory-power-read-only-presentation-alignment.md"
)
VERSION_PLAN_PATH = REPO_ROOT / "docs" / "tasks" / "V2_0-version-plan.md"
ADR_PATH = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "ADR-042-factory-power-estimation-and-presentation-contract.md"
)
P1_CALCULATOR_PATH = (
    REPO_ROOT
    / "backend"
    / "src"
    / "cold_storage"
    / "modules"
    / "calculations"
    / "domain"
    / "factory_power_estimation.py"
)
SHARED_PRESENTATION_PATH = (
    REPO_ROOT
    / "backend"
    / "src"
    / "cold_storage"
    / "modules"
    / "calculations"
    / "application"
    / "factory_power_presentation.py"
)
AILY_PROJECTOR_PATH = (
    REPO_ROOT
    / "backend"
    / "src"
    / "cold_storage"
    / "modules"
    / "aily"
    / "application"
    / "factory_power_table.py"
)
FRONTEND_MAPPER_PATH = (
    REPO_ROOT
    / "frontend"
    / "src"
    / "features"
    / "calculations"
    / "model"
    / "mapFactoryPowerPresentation.ts"
)
FRONTEND_COMPONENT_PATH = (
    REPO_ROOT
    / "frontend"
    / "src"
    / "features"
    / "calculations"
    / "components"
    / "FactoryPowerEstimationResults.vue"
)

P2_ALLOWED_PATHS = {
    "backend/tests/architecture/test_v20_release_closure_readiness.py",
    "backend/src/cold_storage/modules/aily/application/factory_power_table.py",
    "backend/src/cold_storage/modules/calculations/application/factory_power_presentation.py",
    "backend/src/cold_storage/modules/projects/application/factory_power_presentation.py",
    "backend/src/cold_storage/modules/projects/application/service.py",
    "backend/src/cold_storage/modules/projects/infrastructure/database.py",
    "backend/tests/architecture/test_v20_p0_factory_power_estimation_and_presentation_contract.py",
    "backend/tests/architecture/test_v20_p1_factory_power_estimation_canonical_result.py",
    "backend/tests/architecture/test_v20_p2_factory_power_read_only_presentation.py",
    "backend/tests/golden/v20_factory_power_canonical_result_v1.json",
    "backend/tests/unit/test_v20_p2_factory_power_read_only_presentation.py",
    "docs/architecture/ADR-042-factory-power-estimation-and-presentation-contract.md",
    "docs/tasks/V2_0-P1-factory-power-estimation-canonical-result-implementation.md",
    "docs/tasks/V2_0-P2-factory-power-read-only-presentation-alignment.md",
    "docs/tasks/V2_0-release-closure-readiness.md",
    "docs/tasks/V2_0-version-plan.md",
    "frontend/src/api/contracts/calculations.ts",
    "frontend/src/api/contracts/factoryPower.ts",
    "frontend/src/features/calculations/components/CalculationsPage.vue",
    "frontend/src/features/calculations/components/FactoryPowerEstimationResults.test.ts",
    "frontend/src/features/calculations/components/FactoryPowerEstimationResults.vue",
    "frontend/src/features/calculations/architecture/test_v20_p2_factory_power_read_only_presentation.test.ts",
    "frontend/src/features/calculations/model/mapFactoryPowerPresentation.test.ts",
    "frontend/src/features/calculations/model/mapFactoryPowerPresentation.ts",
}


def _changed_paths() -> set[str]:
    merge_base = subprocess.run(
        ["git", "merge-base", "origin/main", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    tracked = subprocess.run(
        ["git", "diff", "--name-only", merge_base, "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return {
        path
        for path in [*tracked, *untracked]
        if path and not path.startswith("backend/artifacts/local/")
    }


def _source_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_v20_p2_scope_is_additive_and_has_no_schema_or_release_change() -> None:
    changed = _changed_paths()
    assert changed <= P2_ALLOWED_PATHS
    assert not any(path.startswith("backend/alembic/") for path in changed)
    assert not any(
        path.endswith("/power_table.py")
        and path != "backend/src/cold_storage/modules/aily/application/factory_power_table.py"
        for path in changed
    )
    assert (
        "backend/src/cold_storage/modules/calculations/domain/factory_power_estimation.py"
        not in changed
    )
    assert not any(path.startswith(".github/") and "release" in path.lower() for path in changed)


def test_p2_authorization_is_separate_and_p0_p1_history_remains_present() -> None:
    p0_text = P0_CONTRACT_PATH.read_text(encoding="utf-8")
    p1_text = P1_TASK_PATH.read_text(encoding="utf-8")
    p2_text = P2_TASK_PATH.read_text(encoding="utf-8")
    version_plan_text = VERSION_PLAN_PATH.read_text(encoding="utf-8")
    adr_text = ADR_PATH.read_text(encoding="utf-8")

    assert "P2_AUTHORIZED=NO" in p0_text
    assert "P2_AUTHORIZED=NO" in p1_text
    assert "V20_P2_IMPLEMENTATION_AUTHORIZED=YES" in p2_text
    assert "V20_P2_IMPLEMENTATION_EXECUTED=YES" in p2_text
    assert "P1_IMPLEMENTATION_MERGED=YES" in p2_text
    assert "V20_P2_IMPLEMENTATION_AUTHORIZED=YES" in version_plan_text
    assert "V20_P2_IMPLEMENTATION_AUTHORIZED=YES" in adr_text
    for text in (p0_text, p1_text, p2_text, version_plan_text, adr_text):
        assert "OUTBOUND_LIVE_AILY_SESSION_AUTHORIZED=YES" not in text
        assert "NO_STEP_IMPLIES_THE_NEXT=TRUE" in text
    assert "MERGE_AUTHORIZED=NO" in p2_text
    assert "TAG_AUTHORIZED=NO" in p2_text
    assert "RELEASE_AUTHORIZED=NO" in p2_text


def test_v2_identity_is_separate_and_five_stage_calculation_type_is_unchanged() -> None:
    assert str(CalculationType.ZONE) == "zone"
    assert str(CalculationType.COOLING_LOAD) == "cooling_load"
    assert str(CalculationType.EQUIPMENT) == "equipment"
    assert str(CalculationType.POWER) == "power"
    assert str(CalculationType.INVESTMENT) == "investment"
    assert len(CalculationType) == 5

    shared_text = SHARED_PRESENTATION_PATH.read_text(encoding="utf-8")
    aily_text = AILY_PROJECTOR_PATH.read_text(encoding="utf-8")
    assert "factory_power_estimation@2.0.0-p1" in shared_text
    assert "installed_power@1.0.0" not in shared_text
    assert "power_configuration" not in shared_text
    assert "project_factory_power_table" in aily_text
    assert "source: Mapping[str, Any] | None" in aily_text
    assert "FactoryPowerPresentation |" not in aily_text
    assert "FactoryPowerPresentation," not in aily_text
    assert "isinstance(source" not in aily_text
    assert "build_factory_power_presentation_from_read_model" not in aily_text
    assert "return build_factory_power_presentation(source)" in aily_text
    assert "installed_power@1.0.0" not in aily_text
    assert "power_configuration" not in aily_text
    assert (
        "cold_storage.modules.calculations.domain.factory_power_estimation"
        not in _source_imports(AILY_PROJECTOR_PATH)
    )


def test_consumers_only_copy_validate_and_label() -> None:
    shared_text = SHARED_PRESENTATION_PATH.read_text(encoding="utf-8")
    aily_text = AILY_PROJECTOR_PATH.read_text(encoding="utf-8")
    frontend_text = FRONTEND_MAPPER_PATH.read_text(encoding="utf-8")
    component_text = FRONTEND_COMPONENT_PATH.read_text(encoding="utf-8")

    for text in (shared_text, aily_text, frontend_text, component_text):
        assert "Math.ceil" not in text
        assert "Decimal" not in text
        assert "sum(" not in text
        assert "multiply" not in text.lower()
    assert "canonical_result_hash" in shared_text
    assert "public.electric_sliding_door" in shared_text
    assert "冷库电动平移门" in shared_text
    assert "installed_power@1.0.0" not in frontend_text
    assert "power_configuration" not in frontend_text
    assert "估算工厂电功率（V2.0）" in component_text


def test_p1_calculator_and_legacy_aily_power_preview_are_untouched() -> None:
    unchanged = subprocess.run(
        [
            "git",
            "diff",
            "--quiet",
            "origin/main",
            "--",
            str(P1_CALCULATOR_PATH.relative_to(REPO_ROOT)),
        ],
        cwd=REPO_ROOT,
        check=False,
    )
    assert unchanged.returncode == 0

    legacy_power_path = (
        REPO_ROOT
        / "backend"
        / "src"
        / "cold_storage"
        / "modules"
        / "aily"
        / "application"
        / "power_table.py"
    )
    legacy_stage_path = legacy_power_path.with_name("stage_preview.py")
    assert "def project_power_table" in legacy_power_path.read_text(encoding="utf-8")
    stage_text = legacy_stage_path.read_text(encoding="utf-8")
    assert 'POWER_CALCULATOR_NAME = "installed_power"' in stage_text
    assert 'POWER_CALCULATOR_VERSION = "1.0.0"' in stage_text
