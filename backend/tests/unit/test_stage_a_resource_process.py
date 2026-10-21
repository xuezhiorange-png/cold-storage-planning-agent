"""Worker isolation does not relabel a failure or a skipped test as PASS."""

from __future__ import annotations

import os
import resource
import subprocess
import sys
from pathlib import Path

import pytest

from tests.stage_a_resource_process import WORKER_ENV, run_resource_test_worker


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
