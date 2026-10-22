"""Run scoped offline regressions and preserve genuine logs outside the repository."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import build_project_evidence as build
import offline_project_input_adapter as adapter

HERE, REPO = build.HERE, build.REPO
LEGACY = [
    "backend/tests/unit/test_zone_planner.py",
    "backend/tests/unit/test_post_v09_p4_zone_area_recut.py",
    "backend/tests/unit/test_v22_p1c_sorting_dimensioning.py",
    "backend/tests/unit/test_v22_p1d3_hybrid_handoff.py",
    "backend/tests/architecture/test_v22_p1c_sorting_dimensioning.py",
    "backend/tests/architecture/test_v22_p1d3_hybrid_handoff.py",
    "backend/tests/architecture/test_v222_p0c_golden_layout_abstraction.py",
]


def validate(evidence: Path, project_files: Path) -> None:
    evidence.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    venv = REPO / "backend/.venv"
    env.update(
        VIRTUAL_ENV=str(venv),
        PATH=str(venv / "bin") + os.pathsep + env["PATH"],
        PYTHONPATH=str(REPO / "backend/src") + os.pathsep + str(REPO / "backend/tests/evaluation"),
        DATABASE_BACKEND="sqlite",
    )
    python = str(venv / "bin/python3")
    report: dict[str, Any] = {
        "task": build.TASK,
        "reference_head": build.REFERENCE,
        "production_changes": False,
        "real_factory_solves": 0,
        "native_solver_calls": 0,
        "new_owner_grant": False,
    }

    def execute(label: str, command: list[str]) -> dict[str, Any]:
        result = subprocess.run(command, cwd=REPO, env=env, capture_output=True, check=False)
        raw = result.stdout + result.stderr
        path = evidence / (label + ".log")
        path.write_bytes(raw)
        data = {
            "command": [
                v.replace(str(REPO), "REPOSITORY").replace(str(evidence), "LOCAL_EVIDENCE")
                for v in command
            ],
            "exit_code": result.returncode,
            "log": path.name,
            "log_sha256": adapter.sha(raw),
        }
        report[label] = data
        build.write("validation.json", report)
        assert result.returncode == 0, label + " failed; inspect preserved log"
        return data

    for label, paths, expected in (
        ("offline_tests", [str((HERE / "test_project_input_adapter.py").relative_to(REPO))], None),
        (
            "old_station_module",
            [str((adapter.R1 / "test_offline_station_geometry.py").relative_to(REPO))],
            57,
        ),
        ("existing_contract_regression", LEGACY, 73),
    ):
        xml = evidence / (label + ".xml")
        data = execute(label, [python, "-m", "pytest", "-q", *paths, "--junitxml=" + str(xml)])
        root = ET.fromstring(xml.read_bytes())
        cases = root.findall(".//testcase")
        node_ids = []
        for case in cases:
            classname = case.attrib["classname"]
            matches = []
            for path in paths:
                for variant in (path, path.removeprefix("backend/")):
                    prefix = variant[:-3].replace("/", ".")
                    if classname == prefix or classname.startswith(prefix + "."):
                        suffix = classname[len(prefix) :].strip(".").replace(".", "::")
                        matches.append(
                            path + "::" + (suffix + "::" if suffix else "") + case.attrib["name"]
                        )
            assert matches and len(set(matches)) == 1, "Cannot map JUnit identity to test source"
            node_ids.append(matches[0])
        data.update(
            total=len(cases),
            passed=sum(
                not list(c) or all(x.tag not in ("failure", "error", "skipped") for x in c)
                for c in cases
            ),
            failed=len(root.findall(".//failure")),
            errors=len(root.findall(".//error")),
            skipped=len(root.findall(".//skipped")),
            node_ids=node_ids,
            node_id_basis="Repository-relative original test file plus JUnit class/test identity",
            junit_sha256=adapter.sha(xml.read_bytes()),
        )
        assert data["failed"] == data["errors"] == data["skipped"] == 0
        assert expected is None or data["total"] == expected
        build.write("validation.json", report)
    target = str(HERE.relative_to(REPO))
    pyfiles = [str(p.relative_to(REPO)) for p in sorted(HERE.glob("*.py"))]
    execute("ruff", [str(venv / "bin/ruff"), "check", "--config", "backend/pyproject.toml", target])
    execute(
        "format",
        [str(venv / "bin/ruff"), "format", "--check", "--config", "backend/pyproject.toml", target],
    )
    execute(
        "mypy",
        [str(venv / "bin/mypy"), "--strict", "--config-file", "backend/pyproject.toml", *pyfiles],
    )
    execute("diff_check", ["git", "diff", "--check"])
    integrity = build.protected_history()
    build.write("historical-evidence-integrity.json", integrity)
    replay = build.legacy_replay()
    build.write("legacy-canonical-replay.json", replay)
    report.update(
        historical_evidence="PASS",
        historical_protected_file_count=len(integrity["FILES"]),
        legacy_canonical_replay=replay["status"],
        canonical_hash=replay["canonical_result_hash"],
        p1_dimension_hash=replay["dimension_handoff_hash"],
    )
    # Determinism uses the same explicitly bounded metadata search and no solver.
    before = {
        p.name: adapter.sha(p.read_bytes())
        for p in HERE.glob("*.json")
        if p.name not in ("validation.json", "source_manifest.json")
    }
    build.build(project_files)
    after = {
        p.name: adapter.sha(p.read_bytes())
        for p in HERE.glob("*.json")
        if p.name not in ("validation.json", "source_manifest.json")
    }
    assert before == after, "Offline evidence regeneration drift"
    report.update(
        determinism="PASS_REPEATED_OFFLINE_ARTIFACT_BYTES_IDENTICAL",
        project_input_admission="BLOCKED",
        project_selected_equipment="UNAVAILABLE",
        real_project_module_validated=False,
        formal_module_dimensions_approved=False,
        packaging_area_calibration_ready=False,
        status="PASS_OFFLINE_SCOPE_ONLY",
    )
    build.write("validation.json", report)
    build.manifest()
    print(
        adapter.encode(
            {
                "status": report["status"],
                "passed": {
                    key: report[key]["passed"]
                    for key in (
                        "offline_tests",
                        "old_station_module",
                        "existing_contract_regression",
                    )
                },
            }
        ).decode()
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--project-files", type=Path, required=True)
    args = parser.parse_args()
    validate(args.evidence, args.project_files)
