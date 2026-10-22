"""SYNTHETIC_RESOURCE_STATE_TEST: receipt validation is NOT real RSS evidence."""

from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tests import linux_rss_gate
from tests.linux_rss_gate import LIMIT, NODE, verified_receipt
from tests.stage_a_resource_process import run_resource_test_worker


def receipt_xml(*, mutation=None, outcome=None):
    evidence = {
        "pid": 123,
        "platform": "linux",
        "guard_pid": 123,
        "guard_status": "STAGE_A_RESOURCE_LIMIT",
        "ledger_peak_rss_bytes": LIMIT + 1024,
        "written_bytes": 600 * 1024**2,
        "samples": [
            {"stage": stage, "pid": 123, "ru_maxrss": 524289, "rss_bytes": LIMIT + 1024}
            for stage in ("BEFORE_GUARD", "AFTER_GUARD_REJECTION")
        ],
    }
    if mutation:
        mutation(evidence)
    root = ET.Element("testsuites")
    case = ET.SubElement(ET.SubElement(root, "testsuite"), "testcase", name=NODE.split("::")[1])
    if outcome:
        ET.SubElement(case, outcome)
    ET.SubElement(
        ET.SubElement(case, "properties"),
        "property",
        name="actual_rss_pressure_evidence",
        value=json.dumps(evidence),
    )
    return ET.tostring(root, encoding="unicode")


def test_valid_synthetic_receipt_parser_not_real_rss_pass():
    assert verified_receipt(receipt_xml())["pid"] == 123


@pytest.mark.parametrize("outcome", ["failure", "error", "skipped"])
def test_nonpass_cannot_satisfy_required_gate(outcome):
    with pytest.raises(ValueError, match="REAL_PASS"):
        verified_receipt(receipt_xml(outcome=outcome))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda e: e.update(platform="darwin"),
        lambda e: e.update(guard_pid=124),
        lambda e: e.update(guard_status="NOT_EXECUTED"),
        lambda e: e.update(ledger_peak_rss_bytes=LIMIT),
        lambda e: e.update(written_bytes=769 * 1024**2),
        lambda e: e.update(samples=[]),
        lambda e: e["samples"][0].update(rss_bytes=LIMIT),
        lambda e: e["samples"][0].update(pid=124),
    ],
)
def test_incomplete_or_below_threshold_measurements_refused(mutation):
    with pytest.raises(ValueError, match="NOT_PROVEN"):
        verified_receipt(receipt_xml(mutation=mutation))


def test_missing_receipt_cannot_pass():
    root = ET.fromstring(receipt_xml())
    case = root.find(".//testcase")
    case.remove(case.find("properties"))
    with pytest.raises(ValueError, match="MISSING"):
        verified_receipt(ET.tostring(root, encoding="unicode"))


def test_two_reports_from_same_pid_do_not_pass(tmp_path, monkeypatch):
    reports = [tmp_path / name for name in ("first.xml", "second.xml")]
    for path in reports:
        path.write_text(receipt_xml())
    monkeypatch.setattr(sys, "argv", ["gate", "verify", *map(str, reports)])
    with pytest.raises(SystemExit, match="DISTINCT_WORKER_PIDS"):
        linux_rss_gate.main()


def test_two_independent_receipts_are_required(tmp_path, monkeypatch, capsys):
    first, second = tmp_path / "first.xml", tmp_path / "second.xml"
    first.write_text(receipt_xml())
    second.write_text(
        receipt_xml(
            mutation=lambda e: (
                e.update(pid=124, guard_pid=124),
                [s.update(pid=124) for s in e["samples"]],
            )
        )
    )
    monkeypatch.setattr(sys, "argv", ["gate", "verify", str(first), str(second)])
    linux_rss_gate.main()
    assert json.loads(capsys.readouterr().out)["linux_real_rss_gate"] == "PASS"


def test_run_cannot_silently_succeed_on_macos(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["gate", "run", str(tmp_path / "report")])
    monkeypatch.setattr(sys, "platform", "darwin")
    with pytest.raises(SystemExit, match="REQUIRES_LINUX"):
        linux_rss_gate.main()


def test_existing_required_job_contains_both_fixed_runs_and_functional_gate():
    root = Path(__file__).resolve().parents[3]
    workflow = (root / ".github/workflows/ci.yml").read_text()
    sqlite = workflow.split("  backend-sqlite:", 1)[1].split("  backend-postgresql:", 1)[0]
    assert "runs-on: ubuntu-latest" in sqlite
    for name in ("run-1", "run-2"):
        assert sqlite.count(f"tests.linux_rss_gate run artifacts/linux-rss/{name}") == 1
    assert "tests.linux_rss_gate verify artifacts/linux-rss/run-1.xml" in sqlite
    assert 'pytest -m "not physical_rss_linux"' in sqlite
    gate = sqlite.split("# Fixed two runs", 1)[1].split("Backend tests (SQLite)", 1)[0]
    assert "continue-on-error" not in gate and "|| true" not in gate
    assert "if-no-files-found: error" in gate
    assert "- backend-sqlite" in workflow.split("  ci-gate:", 1)[1].split("  compose-config:")[0]
    config = (root / "backend/pyproject.toml").read_text()
    assert "physical_rss_linux:" in config
    assert "addopts" not in config


def test_original_failed_worker_junit_is_preserved(tmp_path, monkeypatch):
    original = "<testsuites><testsuite><testcase><failure/></testcase></testsuite></testsuites>"

    def fail(args, **kwargs):
        report = Path(next(a.split("=", 1)[1] for a in args if a.startswith("--junitxml=")))
        report.write_text(original)
        return subprocess.CompletedProcess(args, 1, "ACTUAL_RSS_THRESHOLD_NOT_REACHED", "")

    monkeypatch.setattr(subprocess, "run", fail)
    saved = tmp_path / "original.xml"
    with pytest.raises(pytest.fail.Exception, match="ACTUAL_RSS_THRESHOLD_NOT_REACHED"):
        run_resource_test_worker(NODE, report_copy=saved)
    assert saved.read_text() == original
