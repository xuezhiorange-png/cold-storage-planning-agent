"""Tests for the C-2-extended ``RunDirectory`` (TASK-011C C-2 — §7).

Per §十七 the run-directory module MUST cover:

* deterministic paths;
* path traversal rejected;
* stale run.json rejected (covered in evaluate.py suite);
* stale normalized artifact rejected (covered in evaluate.py);
* stale suite summary rejected (covered in evaluate.py);
* atomic replacement (covered in evaluate.py);
* suite summary written last (covered in evaluate.py);
* failed scenario never emits overall pass (covered in evaluate.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cold_storage.evaluation.errors import InvalidEvaluationScenarioError
from cold_storage.evaluation.run_directory import (
    RunDirectory,
    suite_summary_path,
)


# ── §7 deterministic paths ──────────────────────────────────────


def test_run_directory_paths_are_deterministic() -> None:
    """Two ``RunDirectory.for_scenario`` calls with the same inputs
    return the same paths.
    """
    root = Path("/tmp/rd_test")
    a = RunDirectory.for_scenario(root=root, scenario_id="scenario_x")
    b = RunDirectory.for_scenario(root=root, scenario_id="scenario_x")
    assert a.scenario_dir == b.scenario_dir
    assert a.raw_dir == b.raw_dir
    assert a.normalized_dir == b.normalized_dir
    assert a.summary_path == b.summary_path
    assert a.run_path == b.run_path
    assert a.raw_path == b.raw_path
    assert a.normalized_path == b.normalized_path


def test_run_directory_extended_paths_match_spec() -> None:
    """The C-2 extended paths match the §7 specification.

    ``run_path`` = ``<root>/<scenario_id>/run.json``
    ``raw_path`` = ``<root>/<scenario_id>/raw/<scenario_id>.json``
    ``normalized_path`` = ``<root>/<scenario_id>/normalized/<scenario_id>.json``
    """
    root = Path("/tmp/rd_test")
    rd = RunDirectory.for_scenario(root=root, scenario_id="scenario_x")
    assert rd.run_path == Path("/tmp/rd_test/scenario_x/run.json")
    assert rd.raw_path == Path("/tmp/rd_test/scenario_x/raw/scenario_x.json")
    assert rd.normalized_path == Path(
        "/tmp/rd_test/scenario_x/normalized/scenario_x.json"
    )


def test_suite_summary_path_helper() -> None:
    """``suite_summary_path(root)`` returns ``<root>/summary.json``."""
    assert suite_summary_path(root=Path("/tmp/rd_test")) == Path(
        "/tmp/rd_test/summary.json"
    )


def test_suite_summary_path_accepts_string_root() -> None:
    """``suite_summary_path`` coerces a string root to a Path."""
    result = suite_summary_path(root="/tmp/rd_test")  # type: ignore[arg-type]
    assert result == Path("/tmp/rd_test/summary.json")


# ── §7 path traversal rejected ─────────────────────────────────


@pytest.mark.parametrize(
    "bad_id",
    [
        "../escape",
        "..",
        "/abs",
        "with/slash",
        "with\\backslash",
        "with space",
        "with\x00null",
        "",
        ".",
    ],
)
def test_run_directory_rejects_path_traversal_scenario_id(
    bad_id: str,
) -> None:
    """Path-traversal or otherwise invalid scenario IDs are rejected."""
    with pytest.raises(InvalidEvaluationScenarioError):
        RunDirectory.for_scenario(
            root=Path("/tmp/rd_test"), scenario_id=bad_id
        )


def test_run_directory_accepts_root_path_object() -> None:
    """``for_scenario`` accepts a string-rooted ``Path`` and a path
    object that is a string-coerced Path.
    """
    rd = RunDirectory.for_scenario(
        root=Path("/tmp/rd_test"), scenario_id="valid_id"
    )
    assert rd.scenario_dir == Path("/tmp/rd_test/valid_id")


# ── §7 raw / normalized path equals scenario_id name ──────────


def test_run_directory_raw_path_uses_scenario_id_basename() -> None:
    """The ``raw_path`` and ``normalized_path`` filenames equal
    the scenario_id (matching the C-2 §7 spec).
    """
    rd = RunDirectory.for_scenario(
        root=Path("/tmp/rd_test"), scenario_id="alpha-001"
    )
    assert rd.raw_path.name == "alpha-001.json"
    assert rd.normalized_path.name == "alpha-001.json"
    assert rd.run_path.name == "run.json"
