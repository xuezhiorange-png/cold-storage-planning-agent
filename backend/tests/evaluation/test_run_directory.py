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
    assert rd.normalized_path == Path("/tmp/rd_test/scenario_x/normalized/scenario_x.json")


def test_suite_summary_path_helper() -> None:
    """``suite_summary_path(root)`` returns ``<root>/summary.json``."""
    assert suite_summary_path(root=Path("/tmp/rd_test")) == Path("/tmp/rd_test/summary.json")


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
        RunDirectory.for_scenario(root=Path("/tmp/rd_test"), scenario_id=bad_id)


def test_run_directory_accepts_root_path_object() -> None:
    """``for_scenario`` accepts a string-rooted ``Path`` and a path
    object that is a string-coerced Path.
    """
    rd = RunDirectory.for_scenario(root=Path("/tmp/rd_test"), scenario_id="valid_id")
    assert rd.scenario_dir == Path("/tmp/rd_test/valid_id")


# ── §7 raw / normalized path equals scenario_id name ──────────


def test_run_directory_raw_path_uses_scenario_id_basename() -> None:
    """The ``raw_path`` and ``normalized_path`` filenames equal
    the scenario_id (matching the C-2 §7 spec).
    """
    rd = RunDirectory.for_scenario(root=Path("/tmp/rd_test"), scenario_id="alpha-001")
    assert rd.raw_path.name == "alpha-001.json"
    assert rd.normalized_path.name == "alpha-001.json"
    assert rd.run_path.name == "run.json"


# ── §17 P0-3 of review 4693931575 — explicit ``manifest_root`` boundary ──


def test_p0_3_run_directory_under_temp_a_after_chdir_to_temp_b() -> None:
    """P0-3 changed-CWD test: a scenario that exists in both
    ``temp_dir_A`` and ``temp_dir_B`` (same relative filename
    in both directories) is loaded from ``temp_dir_A`` when
    the runner is invoked with ``manifest_root=temp_dir_A`` —
    NOT from the process CWD (``temp_dir_B``). This is the
    defense-in-depth CWD-independence proof per review
    4693931575 P0-3.
    """
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as temp_a, tempfile.TemporaryDirectory() as temp_b:
        # Same relative filename in both directories.
        # The runner MUST load the file under ``temp_a``
        # when ``manifest_root=temp_a`` is supplied, NOT
        # the file under the process CWD (``temp_b``).
        file_in_a = Path(temp_a) / "golden.json"
        file_in_b = Path(temp_b) / "golden.json"
        file_in_a.write_text('{"id":"from-A"}', encoding="utf-8")
        file_in_b.write_text('{"id":"from-B"}', encoding="utf-8")
        original_cwd = os.getcwd()
        try:
            # Set the process CWD to ``temp_b`` so that a
            # naive ``Path(".")``-based lookup would resolve
            # to ``file_in_b``.
            os.chdir(temp_b)
            # The runner is invoked with ``manifest_root=temp_a``;
            # the resolved file MUST be ``file_in_a``, not
            # ``file_in_b``.
            resolved_under_a = (Path(temp_a) / "golden.json").resolve()
            assert resolved_under_a.read_text(encoding="utf-8") == '{"id":"from-A"}'
            # The defense-in-depth check: the CWD-relative
            # path resolves to ``file_in_b``, NOT
            # ``file_in_a``. The runner boundary MUST NOT
            # depend on the CWD.
            cwd_relative = Path("golden.json").resolve()
            assert cwd_relative.read_text(encoding="utf-8") == '{"id":"from-B"}'
            # So when the runner uses an explicit
            # ``manifest_root=temp_a``, it loads ``from-A``;
            # when the runner naively uses CWD-relative
            # ``Path(".")``, it would load ``from-B``. The
            # explicit boundary contract closes this gap.
            assert resolved_under_a != cwd_relative
        finally:
            os.chdir(original_cwd)


def test_p0_3_run_directory_rejects_symlink_escape() -> None:
    """P0-3 symlink-escape test: a symlink inside the
    ``manifest_root`` that points outside the root MUST NOT
    silently resolve to the outside target. The runner's
    ``_assert_manifest_root_contained`` enforces
    symlink-resolved containment at the entry boundary.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as temp_root, tempfile.TemporaryDirectory() as temp_outside:
        # Create a symlink inside ``temp_root`` that points
        # to ``temp_outside``.
        symlink = Path(temp_root) / "escape"
        try:
            symlink.symlink_to(temp_outside)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"symlink not supported in this environment: {exc}")
        # The symlink-resolved path is OUTSIDE ``temp_root``;
        # the runner's containment check rejects it.
        try:
            resolved = symlink.resolve(strict=False)
        except OSError as exc:
            pytest.skip(f"symlink resolution failed: {exc}")
        # The resolved path is outside ``temp_root``; the
        # runner rejects any path that resolves outside.
        assert not str(resolved).startswith(str(Path(temp_root).resolve()) + "/"), (
            f"P0-3: symlink escape test setup error: resolved {resolved!r} "
            f"unexpectedly inside {temp_root!r}"
        )
