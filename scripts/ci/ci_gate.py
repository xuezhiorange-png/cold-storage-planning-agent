"""Stable final status: selected jobs must succeed; classifier failures fail closed."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any

from classify_changes import REGULAR_JOBS, SCOPE_JOBS, Plan

MANUAL_JOBS = (
    "live-evidence-capture",
    "live-evidence-artifact-transport-verify",
    "live-evidence-attestation-create",
    "live-evidence-assembly",
    "live-evidence-verified-transport-handoff-verify",
    "controlled-recovery-acceptance",
)


def gate_errors(needs: Mapping[str, Any]) -> list[str]:
    classifier = needs.get("classify-changes", {})
    if not isinstance(classifier, Mapping) or classifier.get("result") != "success":
        return ["classify-changes did not succeed"]
    outputs = classifier.get("outputs", {})
    if not isinstance(outputs, Mapping) or outputs.get("scope") not in SCOPE_JOBS:
        return ["missing or invalid classification"]
    scope = outputs["scope"]
    expected = Plan(scope, "").outputs()
    errors = [
        f"invalid {key} output"
        for key, value in expected.items()
        if key not in {"reason", "base", "head"} and outputs.get(key) != value
    ]
    for job in (*REGULAR_JOBS, *MANUAL_JOBS):
        info = needs.get(job, {})
        result = info.get("result") if isinstance(info, Mapping) else None
        if job in SCOPE_JOBS[scope]:
            if result != "success":
                errors.append(f"required {job}: {result}")
        elif result not in {"success", "skipped"}:
            errors.append(f"unexpected failure or missing status for {job}: {result}")
    return errors


def main() -> None:
    try:
        needs = json.loads(os.environ["CI_NEEDS"])
        errors = gate_errors(needs) if isinstance(needs, dict) else ["invalid needs payload"]
    except (ValueError, KeyError):
        errors = ["missing or invalid needs payload"]
    if errors:
        raise SystemExit("CI gate failed: " + "; ".join(errors))
    print("CI gate passed: every required job succeeded")


if __name__ == "__main__":
    main()
