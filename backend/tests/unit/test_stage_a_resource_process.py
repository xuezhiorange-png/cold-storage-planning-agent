"""Worker isolation does not relabel a failure or a skipped test as PASS."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.stage_a_resource_process import WORKER_ENV, run_resource_test_worker


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
