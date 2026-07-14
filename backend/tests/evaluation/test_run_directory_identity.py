"""Identity / regression tests for the C-2-extended ``RunDirectory``.

This file is the dedicated identity test (per §3.3 / §17). It
asserts the layout is bit-identical for the same inputs across
calls (a strict regression check on the deterministic-path
contract).
"""

from __future__ import annotations

from pathlib import Path

from cold_storage.evaluation.run_directory import (
    RunDirectory,
    suite_summary_path,
)


def test_for_scenario_is_pure_function_of_inputs() -> None:
    """``for_scenario`` is a pure function: same inputs → same outputs."""
    rd_a = RunDirectory.for_scenario(root=Path("/var/tmp/x"), scenario_id="scenario-001")
    rd_b = RunDirectory.for_scenario(root=Path("/var/tmp/x"), scenario_id="scenario-001")
    assert rd_a == rd_b


def test_for_scenario_paths_are_pathlib_path_objects() -> None:
    """All ``RunDirectory`` path fields are ``Path`` objects."""
    rd = RunDirectory.for_scenario(root=Path("/var/tmp/x"), scenario_id="scenario-001")
    for attr in (
        "scenario_dir",
        "raw_dir",
        "normalized_dir",
        "summary_path",
        "run_path",
        "raw_path",
        "normalized_path",
    ):
        assert isinstance(getattr(rd, attr), Path)


def test_suite_summary_path_is_root_relative() -> None:
    """``suite_summary_path`` returns a path directly under the root."""
    root = Path("/var/tmp/x")
    assert suite_summary_path(root=root) == root / "summary.json"


def test_different_scenario_ids_produce_different_layouts() -> None:
    """Two different scenario_ids produce two non-overlapping layouts."""
    rd_a = RunDirectory.for_scenario(root=Path("/var/tmp/x"), scenario_id="scenario-001")
    rd_b = RunDirectory.for_scenario(root=Path("/var/tmp/x"), scenario_id="scenario-002")
    assert rd_a.scenario_dir != rd_b.scenario_dir
    assert rd_a.run_path != rd_b.run_path
    assert rd_a.raw_path != rd_b.raw_path
    assert rd_a.normalized_path != rd_b.normalized_path


def test_run_path_distinct_from_summary_path() -> None:
    """``run_path`` (per-scenario) and ``summary_path`` (per-scenario
    legacy) are different files. ``run_path`` is the C-2
    managed record; ``summary_path`` is the C-1 legacy
    per-scenario summary (kept for compatibility).
    """
    rd = RunDirectory.for_scenario(root=Path("/var/tmp/x"), scenario_id="scenario-001")
    assert rd.run_path != rd.summary_path
    assert rd.run_path.name == "run.json"
    assert rd.summary_path.name == "summary.json"
