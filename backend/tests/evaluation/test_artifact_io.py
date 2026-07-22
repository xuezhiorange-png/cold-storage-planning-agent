from __future__ import annotations

import json
from pathlib import Path

import pytest

from cold_storage.evaluation.artifact_io import (
    assert_no_managed_artifacts,
    atomic_write_bytes,
    atomic_write_json,
    remove_managed_output_root,
)
from cold_storage.evaluation.errors import (
    EvaluationArtifactWriteError,
    EvaluationInfrastructureError,
    StaleEvaluationArtifactsError,
)


def test_atomic_write_json_is_strict_and_atomic(tmp_path: Path) -> None:
    target = tmp_path / "run" / "summary.json"
    atomic_write_json(path=target, data={"z": 2, "a": 1})
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1, "z": 2}
    assert not list(target.parent.glob("*.tmp"))

    with pytest.raises(EvaluationArtifactWriteError):
        atomic_write_json(path=target, data={"not_json": object()})


def test_atomic_write_bytes_rejects_coercion(tmp_path: Path) -> None:
    target = tmp_path / "artifact.bin"
    atomic_write_bytes(path=target, data=b"pilot")
    assert target.read_bytes() == b"pilot"
    with pytest.raises(EvaluationArtifactWriteError):
        atomic_write_bytes(path=target, data="pilot")  # type: ignore[arg-type]


def test_stale_detection_is_root_contained(tmp_path: Path) -> None:
    root = (tmp_path / "run").resolve()
    root.mkdir()
    (root / "pilot-run.json").write_text("{}", encoding="utf-8")
    with pytest.raises(StaleEvaluationArtifactsError) as caught:
        assert_no_managed_artifacts(
            root=root,
            managed_paths=(Path("pilot-run.json"), Path("pilot-summary.json")),
        )
    assert caught.value.details["stale_paths"] == [str(root / "pilot-run.json")]

    with pytest.raises(EvaluationInfrastructureError):
        assert_no_managed_artifacts(root=root, managed_paths=(Path("../escape.json"),))


def test_remove_managed_output_root_requires_owned_child(tmp_path: Path) -> None:
    parent = tmp_path.resolve()
    root = parent / "run-1"
    root.mkdir()
    (root / "pilot-run.json").write_text("{}", encoding="utf-8")
    (root / "payload").write_text("x", encoding="utf-8")

    remove_managed_output_root(root=root, allowed_parent=parent)
    assert not root.exists()

    unowned = parent / "run-2"
    unowned.mkdir()
    with pytest.raises(EvaluationInfrastructureError):
        remove_managed_output_root(root=unowned, allowed_parent=parent)
    assert unowned.exists()

    with pytest.raises(EvaluationInfrastructureError):
        remove_managed_output_root(root=parent, allowed_parent=parent)
