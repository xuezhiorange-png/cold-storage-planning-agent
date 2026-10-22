"""Exercise actual pytest collection/execution receipts without a layout solve."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from tests.ci_partition import GROUPS, partition


def test_function_parameters_keep_fixture_affinity() -> None:
    assert partition("tests/unit/test_example.py::test_case[a]") == partition(
        "tests/unit/test_example.py::test_case[b]"
    )
    assert partition("tests/architecture/test_rules.py::test_rule") == "architecture"
    assert (
        partition("tests/unit/test_v222_p1a_composition_exact_placement.py::test_replay")
        == "composition"
    )


def test_partition_receipts_capture_actual_pass_failure_and_fixture_time(tmp_path: Path) -> None:
    test = tmp_path / "test_example.py"
    test.write_text(
        "import pytest\n"
        "@pytest.fixture\ndef prepared():\n    return 1\n"
        "def test_pass(prepared):\n    assert prepared == 1\n"
        "def test_fail():\n    assert False\n"
    )
    root = Path(__file__).resolve().parents[2]
    reports = []
    fixtures = []
    for group in GROUPS:
        receipt = tmp_path / f"{group}.json"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-p",
                "tests.ci_partition",
                "--confcutdir",
                str(tmp_path),
                "--rootdir",
                str(tmp_path),
                "--ci-partition",
                group,
                "--ci-backend",
                "sqlite",
                "--ci-manifest",
                str(receipt),
                str(test),
                "-q",
            ],
            cwd=tmp_path,
            env={**os.environ, "PYTHONPATH": str(root)},
            capture_output=True,
            text=True,
            check=False,
        )
        data = json.loads(receipt.read_text())
        assert result.returncode == data["exitstatus"]
        reports.extend(r for r in data["reports"] if r["when"] == "call")
        fixtures.extend(data["fixture_timings"])
    assert len(reports) == 2
    assert sorted(r["outcome"] for r in reports) == ["failed", "passed"]
    assert any(f["fixture"] == "prepared" and f["duration"] >= 0 for f in fixtures)
