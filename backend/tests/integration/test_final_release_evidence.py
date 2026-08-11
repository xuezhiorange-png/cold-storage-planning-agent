from __future__ import annotations

import json
from pathlib import Path

from cold_storage.release.final_release_evidence import (
    _FROZEN_AUTHORITY_ROWS,
    EXPECTED_REPOSITORY,
    FINAL_BUNDLE_FILES,
    assemble_final_release_evidence,
    verify_final_release_evidence,
    write_frozen_authority_index,
)

CURRENT_SOURCE_SHA = "2" * 40
CURRENT_SOURCE_TREE_SHA = "3" * 40


def _write_github_metadata(directory: Path) -> None:
    directory.mkdir()
    for row in _FROZEN_AUTHORITY_ROWS:
        if row["workflow_run_id"] is not None:
            (directory / f"run-{row['workflow_run_id']}.json").write_text(
                json.dumps(
                    {
                        "id": row["workflow_run_id"],
                        "event": row["workflow_event"],
                        "head_branch": "main",
                        "head_sha": row["workflow_head_sha"],
                        "run_attempt": row["workflow_run_attempt"],
                        "status": "completed",
                        "conclusion": "success",
                        "path": row["workflow_path"],
                        "name": row["workflow_name"],
                    }
                ),
                encoding="utf-8",
            )
        if row["artifact_id"] is not None:
            (directory / f"artifact-{row['artifact_id']}.json").write_text(
                json.dumps(
                    {
                        "id": row["artifact_id"],
                        "name": row["artifact_name"],
                        "expired": False,
                        "digest": row["artifact_digest"],
                        "workflow_run": {
                            "id": row["workflow_run_id"],
                            "head_branch": "main",
                            "head_sha": row["workflow_head_sha"],
                        },
                    }
                ),
                encoding="utf-8",
            )


def test_deterministic_final_release_evidence_cli_contract(tmp_path: Path) -> None:
    index_path = tmp_path / "authority-index.json"
    metadata_dir = tmp_path / "github-metadata"
    bundle_path = tmp_path / "bundle"
    write_frozen_authority_index(
        index_path,
        source_sha=CURRENT_SOURCE_SHA,
        source_tree_sha=CURRENT_SOURCE_TREE_SHA,
    )
    _write_github_metadata(metadata_dir)

    assemble_final_release_evidence(
        authority_index=index_path,
        output_dir=bundle_path,
        repository=EXPECTED_REPOSITORY,
        source_sha=CURRENT_SOURCE_SHA,
        source_tree_sha=CURRENT_SOURCE_TREE_SHA,
        generated_at="2026-08-11T00:00:00Z",
        github_metadata_dir=metadata_dir,
    )
    verify_final_release_evidence(
        bundle_dir=bundle_path,
        repository=EXPECTED_REPOSITORY,
        source_sha=CURRENT_SOURCE_SHA,
        source_tree_sha=CURRENT_SOURCE_TREE_SHA,
        github_metadata_dir=metadata_dir,
    )

    assert {path.name for path in bundle_path.iterdir()} == set(FINAL_BUNDLE_FILES)
    summary = json.loads(
        (bundle_path / "release-evidence-summary.json").read_text(encoding="utf-8")
    )
    assert summary["release_evidence_result"] == "PASS"
    assert summary["production_operation_performed"] is False
