"""Fixed Linux RSS gate: real worker once per invocation, never retry or solve."""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from tests.stage_a_resource_process import run_resource_test_worker

NODE = (
    "tests/unit/test_v222_stage_b_pool_execution.py::"
    "test_actual_resident_memory_is_rejected_without_mocking_rss"
)
LIMIT = 536870912


def verified_receipt(xml: str) -> dict:
    """Require one actual PASS plus original same-process Linux measurements."""
    cases = ET.fromstring(xml).findall(".//testcase")
    if len(cases) != 1 or cases[0].get("name") != NODE.split("::")[1]:
        raise ValueError("RSS_GATE_REQUIRES_EXACTLY_ONE_ORIGINAL_NODE")
    case = cases[0]
    if any(case.find(tag) is not None for tag in ("failure", "error", "skipped")):
        raise ValueError("RSS_GATE_REQUIRES_REAL_PASS")
    props = case.findall("./properties/property")
    receipts = [p for p in props if p.get("name") == "actual_rss_pressure_evidence"]
    if len(receipts) != 1:
        raise ValueError("RSS_GATE_MISSING_OR_DUPLICATE_MEASUREMENTS")
    evidence = json.loads(receipts[0].attrib["value"])
    samples = evidence["samples"]
    pid = evidence["pid"]
    if (
        evidence["platform"] != "linux"
        or type(pid) is not int
        or pid <= 0
        or evidence["guard_pid"] != pid
        or evidence["guard_status"] != "STAGE_A_RESOURCE_LIMIT"
        or evidence["ledger_peak_rss_bytes"] <= LIMIT
        or not 600 * 1024**2 <= evidence["written_bytes"] <= 768 * 1024**2
        or not samples
        or any(s["pid"] != pid or s["ru_maxrss"] * 1024 != s["rss_bytes"] for s in samples)
        or not any(s["stage"] == "BEFORE_GUARD" and s["rss_bytes"] > LIMIT for s in samples)
        or not any(s["stage"] == "AFTER_GUARD_REJECTION" for s in samples)
    ):
        raise ValueError("RSS_GATE_ACTUAL_LINUX_OVERLIMIT_NOT_PROVEN")
    return evidence


def main() -> None:
    if sys.argv[1] == "run" and len(sys.argv) == 3:
        if sys.platform != "linux":
            raise SystemExit("RSS_GATE_REQUIRES_LINUX")
        prefix = Path(sys.argv[2])
        prefix.parent.mkdir(parents=True, exist_ok=True)
        try:
            output = run_resource_test_worker(NODE, report_copy=prefix.with_suffix(".xml"))
        except BaseException as exc:
            prefix.with_suffix(".log").write_text(str(exc))
            raise
        prefix.with_suffix(".log").write_text(output)
        xml = output.split("\nRAW_WORKER_JUNIT\n", 1)[1]
        prefix.with_suffix(".xml").write_text(xml)
        receipt = verified_receipt(xml)
        print(json.dumps(receipt, sort_keys=True), flush=True)
    elif sys.argv[1] == "verify" and len(sys.argv) == 4:
        receipts = [verified_receipt(Path(p).read_text()) for p in sys.argv[2:]]
        if receipts[0]["pid"] == receipts[1]["pid"]:
            raise SystemExit("RSS_GATE_REQUIRES_TWO_DISTINCT_WORKER_PIDS")
        print(json.dumps({"linux_real_rss_gate": "PASS", "workers": receipts}, sort_keys=True))
    else:
        raise SystemExit("usage: linux_rss_gate run PREFIX | verify FIRST.xml SECOND.xml")


if __name__ == "__main__":
    main()
