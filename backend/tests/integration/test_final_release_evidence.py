from __future__ import annotations

import json
from pathlib import Path

from cold_storage.release.final_release_evidence import (
    EXPECTED_REPOSITORY,
    EXPECTED_SOURCE_SHA,
    EXPECTED_SOURCE_TREE_SHA,
    FINAL_BUNDLE_FILES,
    assemble_final_release_evidence,
    verify_final_release_evidence,
    write_frozen_authority_index,
)


def test_deterministic_final_release_evidence_cli_contract(tmp_path: Path) -> None:
    index_path = tmp_path / "authority-index.json"
    bundle_path = tmp_path / "bundle"
    write_frozen_authority_index(index_path)

    assemble_final_release_evidence(
        authority_index=index_path,
        output_dir=bundle_path,
        repository=EXPECTED_REPOSITORY,
        source_sha=EXPECTED_SOURCE_SHA,
        source_tree_sha=EXPECTED_SOURCE_TREE_SHA,
        generated_at="2026-08-11T00:00:00Z",
    )
    verify_final_release_evidence(
        bundle_dir=bundle_path,
        repository=EXPECTED_REPOSITORY,
        source_sha=EXPECTED_SOURCE_SHA,
        source_tree_sha=EXPECTED_SOURCE_TREE_SHA,
    )

    assert {path.name for path in bundle_path.iterdir()} == set(FINAL_BUNDLE_FILES)
    summary = json.loads(
        (bundle_path / "release-evidence-summary.json").read_text(encoding="utf-8")
    )
    assert summary["release_evidence_result"] == "PASS"
    assert summary["production_operation_performed"] is False
