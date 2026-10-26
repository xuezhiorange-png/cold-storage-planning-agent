"""Worker isolation does not relabel a failure or a skipped test as PASS."""

from __future__ import annotations

import os
import resource
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.stage_a_resource_process import (
    RESOURCE_TEST_FILES,
    WORKER_ENV,
    run_resource_test_worker,
)

R9_RESOURCE_FILES = (
    "test_v222_stage_b_changing_frontage_corridor.py",
    "test_v222_stage_b_route_refinement.py",
    "test_v222_stage_b_route_resources.py",
    "test_v222_access_entrance_normals.py",
)


@pytest.mark.parametrize("filename", R9_RESOURCE_FILES)
def test_r9_resource_modules_dispatch_through_original_worker(monkeypatch, filename):
    from tests import conftest

    assert filename in RESOURCE_TEST_FILES
    calls, sections = [], []
    item = SimpleNamespace(
        path=Path("tests/unit") / filename,
        nodeid=f"tests/unit/{filename}::test_original[param]",
        add_report_section=lambda *args: sections.append(args),
    )
    monkeypatch.delenv(WORKER_ENV, raising=False)

    def dispatch(node_id):
        calls.append(node_id)
        return "worker evidence"

    # Dispatch-only test. Real memory and guard behavior is exercised below.
    monkeypatch.setattr(conftest, "run_resource_test_worker", dispatch)
    assert conftest.pytest_pyfunc_call(item) is True
    assert calls == [item.nodeid]
    assert sections == [("call", "isolated_resource_worker", "worker evidence")]
    monkeypatch.setenv(WORKER_ENV, "1")
    assert conftest.pytest_pyfunc_call(item) is None
    assert calls == [item.nodeid]  # No recursive worker nesting.


def _retain_actual_resident_pressure() -> tuple[bytearray, list[bytes]]:
    """Test setup only: allocation length is not the guard's measured RSS."""
    mib = 1024 * 1024
    pressure = bytearray(600 * mib)
    for offset in range(0, len(pressure), mib):
        pressure[offset : offset + mib] = os.urandom(mib)
    extra: list[bytes] = []
    while True:
        raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss = raw if sys.platform == "darwin" else raw * 1024
        print(
            f"WORKER_PRESSURE pid={os.getpid()} raw_ru_maxrss={raw} "
            f"peak_rss_bytes={rss} written_bytes={len(pressure) + len(extra) * mib}",
            flush=True,
        )
        if rss > 512 * mib:
            return pressure, extra
        if len(pressure) + len(extra) * mib >= 768 * mib:
            pytest.fail("ACTUAL_RSS_THRESHOLD_NOT_REACHED")
        extra.append(os.urandom(mib))


@pytest.mark.parametrize("child", ["<failure/>", "<error/>", "<skipped/>"])
def test_resource_worker_does_not_promote_nonpass(monkeypatch, child: str) -> None:
    def run(args, **kwargs):
        assert kwargs["env"][WORKER_ENV] == "1"
        report = Path(next(a.split("=", 1)[1] for a in args if a.startswith("--junitxml=")))
        report.write_text(
            f"<testsuites><testsuite><testcase>{child}</testcase></testsuite></testsuites>"
        )
        return subprocess.CompletedProcess(args, 0, "original worker output", "")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(pytest.fail.Exception, match="exactly one test"):
        run_resource_test_worker("tests/unit/example.py::test_case")


def test_resource_worker_failure_is_not_hidden(monkeypatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 1, "REAL_RESOURCE_LIMIT", ""),
    )
    with pytest.raises(pytest.fail.Exception, match="REAL_RESOURCE_LIMIT"):
        run_resource_test_worker("tests/unit/example.py::test_case")


@pytest.mark.physical_rss_linux
def test_resource_worker_excludes_parent_live_memory_not_worker_initialization() -> None:
    # Real touched memory: Linux must not inherit the full-suite parent's RSS
    # into the worker's process-lifetime budget. Never mock getrusage/guard.
    pressure, retained = _retain_actual_resident_pressure()
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    assert (raw if sys.platform == "darwin" else raw * 1024) > 512 * 1024 * 1024
    output = run_resource_test_worker(
        "tests/unit/test_v222_production_execution_policy.py::"
        "test_original_work_counters_share_task_limit"
    )
    assert "1 passed" in output
    assert len(pressure) == 600 * 1024 * 1024
    assert len(pressure) + sum(map(len, retained)) <= 768 * 1024 * 1024


@pytest.mark.physical_rss_linux
@pytest.mark.parametrize(
    "node_id",
    [
        "tests/unit/test_v222_stage_b_changing_frontage_corridor.py::"
        "test_r9_metadata_has_no_definitions_constraints_objective_or_hint_changes",
        "tests/unit/test_v222_stage_b_route_refinement.py::"
        "test_clone_scope_never_mutates_parent_and_keeps_original_hint",
        "tests/unit/test_v222_stage_b_route_resources.py::"
        "test_actual_unchanged_preparation_cost_is_bounded_and_not_reserved_as_fake_work",
        "tests/unit/test_v222_access_entrance_normals.py::"
        "test_complete_r3_alternatives_keep_original_engineering_acceptance",
    ],
)
def test_r9_workers_exclude_parent_peak_without_mocking_guard(node_id, record_property) -> None:
    # Real touched memory: Linux must not inherit the full-suite parent's RSS
    # into the worker's process-lifetime budget. Never mock getrusage/guard.
    pressure, retained = _retain_actual_resident_pressure()
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    assert (raw if sys.platform == "darwin" else raw * 1024) > 512 * 1024 * 1024
    output = run_resource_test_worker(node_id)
    assert "1 passed" in output
    record_property("parent_pid", os.getpid())
    record_property("parent_peak_rss_raw", raw)
    record_property("independent_worker_evidence", output)
    assert len(pressure) == 600 * 1024 * 1024
    assert len(pressure) + sum(map(len, retained)) <= 768 * 1024 * 1024


@pytest.mark.physical_rss_linux
def test_resource_worker_own_memory_limit_still_rejects() -> None:
    if os.environ.get(WORKER_ENV) != "1":
        output = run_resource_test_worker(
            "tests/unit/test_stage_a_resource_process.py::"
            "test_resource_worker_own_memory_limit_still_rejects"
        )
        assert "1 passed" in output
        return

    from cold_storage.modules.layout.application.global_composition_solver import StageALedger
    from cold_storage.modules.layout.domain.dimensioning import LayoutAuthorityError

    # The broker must not hide real memory consumed inside the guarded worker.
    pressure, retained = _retain_actual_resident_pressure()
    ledger = StageALedger()
    with pytest.raises(LayoutAuthorityError, match="^STAGE_A_RESOURCE_LIMIT$"):
        ledger.guard()
    assert ledger.peak_rss_bytes > 512 * 1024 * 1024
    assert ledger.model_work == ledger.native_host_work == 0
    assert len(pressure) == 600 * 1024 * 1024
    assert len(pressure) + sum(map(len, retained)) <= 768 * 1024 * 1024


@pytest.mark.physical_rss_linux
def test_unhandled_real_worker_rss_limit_is_a_failed_test(tmp_path, record_property) -> None:
    # The original guard really raises in a real worker. The broker must fail
    # too, preserve that failed JUnit and never turn isolation into a waiver.
    backend_tests = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="rss-failure-probe-", dir=backend_tests) as directory:
        probe = Path(directory) / "test_real_rss_failure.py"
        probe.write_text(
            "from cold_storage.modules.layout.application.global_composition_solver "
            "import StageALedger\n"
            "from tests.unit.test_stage_a_resource_process "
            "import _retain_actual_resident_pressure\n"
            "def test_real_overlimit():\n"
            "    pressure, retained = _retain_actual_resident_pressure()\n"
            "    StageALedger().guard()\n"
        )
        report = tmp_path / "real-failed-worker.xml"
        with pytest.raises(pytest.fail.Exception, match="STAGE_A_RESOURCE_LIMIT") as failure:
            run_resource_test_worker(f"{probe}::test_real_overlimit", report_copy=report)
        cases = ET.fromstring(report.read_text()).findall(".//testcase")
        assert len(cases) == 1
        assert cases[0].find("failure") is not None
        assert cases[0].find("skipped") is None
        assert "STAGE_A_RESOURCE_LIMIT" in ET.tostring(cases[0], encoding="unicode")
        record_property("real_failed_worker_junit", report.read_text())
        record_property("real_failed_worker_output", str(failure.value))
