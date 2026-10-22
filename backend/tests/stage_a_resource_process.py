"""Dedicated processes for tests of a process-lifetime memory contract.

The production guard intentionally reads ru_maxrss. Unrelated PDF rendering in
the shared pytest interpreter must not become this worker's memory history.
No production ledger, limit or clock is reset or patched by this test harness.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

WORKER_ENV = "COLD_STORAGE_STAGE_A_TEST_WORKER"
RESOURCE_TEST_FILES = frozenset(
    {
        "test_v222_execution_scope.py",
        "test_v222_global_cp_sat_stage_a.py",
        "test_v222_global_composition_pool.py",
        "test_v222_stage_b_pool_execution.py",
        "test_v222_stage_b_construction_guidance.py",
        "test_v222_stage_b_multi_solution.py",
        "test_v222_stage_b_fair_search.py",
        "test_v222_functional_shape_ab.py",
        "test_v222_feasibility_first_main_execution.py",
        "test_v222_balanced_main_execution.py",
        "test_v222_balanced_feedback_main_execution.py",
        "test_v222_stage_b_balanced_quality.py",
        "test_v222_multi_solution_execution.py",
        "test_v222_native_access_hints.py",
        "test_v222_production_execution_policy.py",
        "test_v222_stage_a_closure_c1.py",
    }
)


def run_resource_test_worker(node_id: str, *, report_copy: Path | None = None) -> str:
    """Run the same parametrized test; require one actual, non-skipped PASS."""
    import pytest

    backend = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="stage-a-resource-test-") as directory:
        report = Path(directory) / "junit.xml"
        env = dict(os.environ, **{WORKER_ENV: "1"})
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                str(time.monotonic() + 180),
                sys.executable,
                "-m",
                "pytest",
                node_id,
                "-q",
                "--tb=long",
                "-o",
                "addopts=",
                "-o",
                f"cache_dir={directory}/cache",
                f"--junitxml={report}",
            ],
            cwd=backend,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        output = result.stdout + result.stderr
        if report_copy is not None and report.is_file():
            report_copy.write_bytes(report.read_bytes())
        if result.returncode != 0 or not report.is_file():
            pytest.fail(f"Isolated resource worker failed ({result.returncode}):\n{output}")
        xml = report.read_text()
        cases = ET.fromstring(xml).findall(".//testcase")
        if len(cases) != 1 or any(
            case.find(tag) is not None for case in cases for tag in ("failure", "error", "skipped")
        ):
            pytest.fail(
                f"Worker must execute exactly one test without skip/xfail:\n{xml}\n{output}"
            )
        return f"{output}\nRAW_WORKER_JUNIT\n{xml}"


def _launch_worker() -> int:
    """Spawn pytest from a small interpreter, retaining the original deadline.

    Linux carries the parent's resident high-water mark across the first exec.
    A second spawn inherits this stdlib-only launcher's current resident set,
    rather than the full-suite pytest parent's live PDF/model allocations.
    The actual worker still loads all original plugins/conftest/fixtures and
    measures its own complete lifetime peak, including its own initialization.
    No production resource value, clock, guard or threshold is modified.
    """
    remaining = float(sys.argv[1]) - time.monotonic()
    if remaining <= 0:
        return 124
    try:
        return subprocess.run(sys.argv[2:], timeout=remaining, check=False).returncode
    except subprocess.TimeoutExpired:
        return 124


if __name__ == "__main__":
    raise SystemExit(_launch_worker())
