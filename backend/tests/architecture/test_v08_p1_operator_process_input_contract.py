"""Architecture tests for V0.8 P1 operator process input assembler."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
P1_CONTRACT = REPO_ROOT / "docs" / "tasks" / "V0_8-P1-process-input-assembler-contract.md"
P1_ALLOWLIST = (
    "docs/tasks/V0_8-P1-process-input-assembler-contract.md",
    "backend/src/cold_storage/modules/projects/application/operator_process_input.py",
    "backend/src/cold_storage/modules/projects/application/engineering_input_bundle.py",
    "backend/src/cold_storage/modules/projects/application/five_stage_execution.py",
    "backend/src/cold_storage/bootstrap/app.py",
    "backend/tests/architecture/test_v08_p1_operator_process_input_contract.py",
    "backend/tests/unit/test_v08_p1_operator_process_input_assembler.py",
    "backend/tests/integration/test_v08_p1_five_field_execution_sqlite.py",
    "backend/tests/integration/test_v08_p1_five_field_execution_postgresql.py",
)

_ENGINEERING_LITERAL_PATTERNS = (
    re.compile(r"\b\d+\.?\d*\s*kW\b", re.IGNORECASE),
    re.compile(r"\butilization_factor\s*=\s*0\.\d+"),
    re.compile(r"\breserve_factor\s*=\s*0\.\d+"),
)

_APP_PATH = REPO_ROOT / "backend/src/cold_storage/bootstrap/app.py"
_BUNDLE_PATH = (
    REPO_ROOT / "backend/src/cold_storage/modules/projects/application/engineering_input_bundle.py"
)
_EXEC_PATH = (
    REPO_ROOT / "backend/src/cold_storage/modules/projects/application/five_stage_execution.py"
)
_OPERATOR_PATH = (
    REPO_ROOT / "backend/src/cold_storage/modules/projects/application/operator_process_input.py"
)


def test_p1_contract_exists() -> None:
    assert P1_CONTRACT.is_file()


def test_p1_allowlist_paths_exist() -> None:
    for path in P1_ALLOWLIST:
        assert (REPO_ROOT / path).is_file(), path


def test_app_py_has_no_engineering_formula_literals() -> None:
    content = _APP_PATH.read_text(encoding="utf-8")
    for pattern in _ENGINEERING_LITERAL_PATTERNS:
        match = pattern.search(content)
        assert match is None, f"Forbidden literal in app.py: {match.group() if match else ''}"


def test_v05_no_formula_guard_still_passes_on_bundle_and_execution_modules() -> None:
  result = subprocess.run(
      [
          "python3",
          "-m",
          "pytest",
          "tests/architecture/test_v05_p1_no_formula_values.py",
          "-q",
      ],
      cwd=REPO_ROOT / "backend",
      env={"PYTHONPATH": "src", **os.environ},
      capture_output=True,
      text=True,
      timeout=120,
  )
  assert result.returncode == 0, result.stdout + result.stderr


def test_operator_minimal_bundle_allows_lineage_pending_downstream_keys() -> None:
    from cold_storage.modules.projects.application.engineering_input_bundle import (
        LINEAGE_PENDING_STATE,
    )
    from cold_storage.modules.projects.application.operator_process_input import (
        assemble_engineering_input_bundle,
    )
    from cold_storage.modules.projects.domain.models import ProjectVersion

    bundle = assemble_engineering_input_bundle(
        operator_input={
            "schema_id": "OperatorProcessInputV1",
            "schema_version": "1.0.0",
            "zone_planning_inputs": {
                "daily_inbound_mass_kg": {"value": "20000", "unit": "kg/day", "state": "provided"},
                "working_time_h_per_day": {"value": "16", "unit": "h/day", "state": "provided"},
                "finished_storage_days": {"value": "7", "unit": "day", "state": "provided"},
                "packaging_storage_days": {"value": "1", "unit": "day", "state": "provided"},
                "precooling_required_ratio": {"value": "0.6", "unit": "ratio", "state": "provided"},
            },
        },
        project_id="p-arch",
        version=ProjectVersion(
            project_id="p-arch",
            version_number=1,
            change_summary="v1",
            id="pv-arch",
        ),
        actor="arch-test",
    )
    assert (
        bundle["equipment_inputs"]["systems"][0]["zones"][0]["design_cooling_load_kw_r"]["state"]
        == LINEAGE_PENDING_STATE
    )
    assert (
        bundle["installed_power_inputs"]["compressor_input_power_kw_e"]["state"]
        == LINEAGE_PENDING_STATE
    )


def test_full_bundle_still_requires_all_keys_at_submit() -> None:
    from tests.integration.v05_p1_bundle_fixtures import build_valid_engineering_input_bundle

    bundle = build_valid_engineering_input_bundle(
        project_id="p-1",
        project_version_id="pv-1",
        version_number=1,
    )
    bundle["installed_power_inputs"].pop("compressor_input_power_kw_e")
    from cold_storage.modules.projects.application.engineering_input_bundle import (
        EngineeringInputBundleValidationError,
        validate_engineering_input_bundle,
    )

    with pytest.raises(EngineeringInputBundleValidationError):
        validate_engineering_input_bundle(bundle, validation_mode="full")
