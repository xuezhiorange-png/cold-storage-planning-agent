"""Architecture tests for V0.9 P1 operator KEY assembler.

Enforces docs/tasks/V0_9-P1-operator-key-assembler-contract.md without
embedding engineering formulas or editing zone_planning.py.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from cold_storage.modules.projects.application.engineering_input_bundle import (
    OPERATOR_PROCESS_SCHEMA_VERSION,
    OPERATOR_PROCESS_SCHEMA_VERSION_V09,
    OPERATOR_V08_FIVE_KEY_FIELDS,
    OPERATOR_V09_FIVE_KEY_FIELDS,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
P1_CONTRACT = REPO_ROOT / "docs" / "tasks" / "V0_9-P1-operator-key-assembler-contract.md"
P0_CONTRACT = REPO_ROOT / "docs" / "tasks" / "V0_9-P0-version-contract.md"
ZONE_PLANNING = REPO_ROOT / "backend/src/cold_storage/modules/calculations/domain/zone_planning.py"
OPERATOR_FORM = (
    REPO_ROOT / "frontend/src/features/five-stage/components/EngineeringInputBundleForm.vue"
)
OPERATOR_PAGE = REPO_ROOT / "frontend/src/features/five-stage/components/EngineeringInputsPage.vue"
APP_PATH = REPO_ROOT / "backend/src/cold_storage/bootstrap/app.py"
OPERATOR_ASSEMBLER = (
    REPO_ROOT / "backend/src/cold_storage/modules/projects/application/operator_process_input.py"
)

P1_ALLOWLIST = (
    "docs/tasks/V0_9-P1-operator-key-assembler-contract.md",
    "backend/src/cold_storage/modules/projects/application/operator_process_input.py",
    "backend/src/cold_storage/modules/projects/application/engineering_input_bundle.py",
    "backend/src/cold_storage/modules/projects/application/five_stage_execution.py",
    "backend/src/cold_storage/bootstrap/app.py",
    "frontend/src/features/five-stage/components/EngineeringInputBundleForm.vue",
    "frontend/src/features/five-stage/components/EngineeringInputsPage.vue",
    "frontend/src/features/five-stage/model/engineeringInputForm.ts",
    "frontend/src/stores/fiveStageExecution.ts",
    "frontend/src/features/five-stage/api/fiveStageApi.ts",
    "frontend/src/api/contracts/fiveStage.ts",
    "backend/tests/architecture/test_v09_p1_operator_key_contract.py",
    "backend/tests/unit/test_v09_p1_operator_process_input_assembler.py",
    "backend/tests/integration/test_v09_p1_five_field_execution_sqlite.py",
    "backend/tests/integration/test_v09_p1_five_field_execution_postgresql.py",
    "frontend/src/features/five-stage/architecture/test_v09_p1_five_key_operator_form.test.ts",
)

OPERATOR_V09_KEY_LEAVES: tuple[str, ...] = (
    "zone_planning_inputs.daily_inbound_mass_kg",
    "zone_planning_inputs.finished_storage_days",
    "zone_planning_inputs.frozen_storage_days",
    "zone_planning_inputs.main_packaging_storage_days",
    "zone_planning_inputs.auxiliary_packaging_storage_days",
)

REMOVED_OPERATOR_FORM_FRAGMENTS: tuple[str, ...] = (
    "precooling_required_ratio",
    "working_time_h_per_day",
    "workingTimeHPerDay",
    "precoolingRequiredRatio",
)

_INTERESTING_PREFIXES = (
    "docs/",
    "backend/src/",
    "backend/tests/",
    "frontend/src/",
)

_ENGINEERING_LITERAL_PATTERNS = (
    re.compile(r"\b\d+\.?\d*\s*kW\b", re.IGNORECASE),
    re.compile(r"\butilization_factor\s*=\s*0\.\d+"),
    re.compile(r"\breserve_factor\s*=\s*0\.\d+"),
)


def _extract_allowlist_paths(contract: str, marker: str) -> set[str]:
    start = contract.index(marker)
    fence_start = contract.rfind("```", 0, start)
    fence_end = contract.index("```", start)
    block = contract[fence_start + 3 : fence_end].strip()
    if block.startswith("text"):
        block = block.split("\n", 1)[1].strip()
    paths: set[str] = set()
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped == marker:
            continue
        paths.add(stripped)
    return paths


def _changed_interesting_paths() -> set[str]:
    diff = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    names = {line.strip() for line in diff.stdout.splitlines() if line.strip()}
    names |= {line.strip() for line in untracked.stdout.splitlines() if line.strip()}
    return {name for name in names if name.startswith(_INTERESTING_PREFIXES)}


def test_p1_contract_exists_and_authorizes_implementation() -> None:
    assert P1_CONTRACT.is_file()
    text = P1_CONTRACT.read_text(encoding="utf-8")
    assert "BASE_MAIN_SHA=d8474855ee0815552865ea36d98631a33111d674" in text
    assert "V09_P1_IMPLEMENTATION_AUTHORIZED=YES" in text
    assert "FORMULA_RECUT_AUTHORIZED=NO" in text
    assert "schema_version: 1.1.0" in text
    assert "omitted-as-V0.8" in text
    assert "shipping_channel" in text
    assert "deferred to P2" in text.lower() or "DEFERRED_TO_P2" in text


def test_p1_allowlist_matches_p0_and_files_exist() -> None:
    p0 = P0_CONTRACT.read_text(encoding="utf-8")
    p1 = P1_CONTRACT.read_text(encoding="utf-8")
    p0_paths = _extract_allowlist_paths(p0, "V09_P1_FILE_ALLOWLIST")
    p1_paths = _extract_allowlist_paths(p1, "V09_P1_FILE_ALLOWLIST")
    assert p0_paths == p1_paths
    assert set(P1_ALLOWLIST) == p1_paths
    for path in P1_ALLOWLIST:
        assert (REPO_ROOT / path).is_file(), path


def test_v09_operator_five_key_list_present() -> None:
    assert OPERATOR_V09_FIVE_KEY_FIELDS == (
        "daily_inbound_mass_kg",
        "finished_storage_days",
        "frozen_storage_days",
        "main_packaging_storage_days",
        "auxiliary_packaging_storage_days",
    )
    assert OPERATOR_PROCESS_SCHEMA_VERSION_V09 == "1.1.0"
    assert OPERATOR_PROCESS_SCHEMA_VERSION == "1.0.0"
    assert OPERATOR_V08_FIVE_KEY_FIELDS == (
        "daily_inbound_mass_kg",
        "working_time_h_per_day",
        "finished_storage_days",
        "packaging_storage_days",
        "precooling_required_ratio",
    )
    contract = P1_CONTRACT.read_text(encoding="utf-8")
    for leaf in OPERATOR_V09_KEY_LEAVES:
        assert leaf in contract, leaf


def test_operator_form_does_not_expose_removed_v08_keys() -> None:
    form = OPERATOR_FORM.read_text(encoding="utf-8")
    page = OPERATOR_PAGE.read_text(encoding="utf-8")
    for fragment in REMOVED_OPERATOR_FORM_FRAGMENTS:
        assert fragment not in form, fragment
        assert fragment not in page, fragment
    assert "working_time_h_per_day" not in form
    assert "precooling_required_ratio" not in form
    assert "zonePlanning.frozenStorageDays" in form
    assert "zonePlanning.mainPackagingStorageDays" in form
    assert "zonePlanning.auxiliaryPackagingStorageDays" in form


def test_p1_diff_stays_on_allowlist_and_does_not_edit_zone_planning() -> None:
    changed = _changed_interesting_paths()
    allowlist = set(P1_ALLOWLIST)
    extra = sorted(changed - allowlist)
    assert extra == [], f"P1 diff off allowlist: {extra}"
    zone_rel = "backend/src/cold_storage/modules/calculations/domain/zone_planning.py"
    assert zone_rel not in changed
    zone_diff = subprocess.run(
        ["git", "diff", "origin/main", "--", str(ZONE_PLANNING.relative_to(REPO_ROOT))],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert zone_diff.stdout.strip() == ""


def test_shipping_channel_not_added_to_refrigerated_registry() -> None:
    assembler = OPERATOR_ASSEMBLER.read_text(encoding="utf-8")
    assert '"shipping_channel"' not in assembler
    assert "'shipping_channel'" not in assembler
    assert "deferred to P2" in assembler


def test_app_py_has_no_engineering_formula_literals() -> None:
    content = APP_PATH.read_text(encoding="utf-8")
    for pattern in _ENGINEERING_LITERAL_PATTERNS:
        match = pattern.search(content)
        assert match is None, f"Forbidden literal in app.py: {match.group() if match else ''}"
