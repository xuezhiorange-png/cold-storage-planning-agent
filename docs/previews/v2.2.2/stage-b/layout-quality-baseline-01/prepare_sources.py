"""Extract read-only evidence projections; never imports production or solver code."""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def prepare(root: Path) -> None:
    latest = root / "stage-b-real-guided-fair-validation-02"
    history = root / "stage-b-real-multi-solution-validation-01"
    archives = [
        (
            history,
            "stage-b-real-multi-solution-validation-01-20261018T083040Z.tar.gz",
            "3fb5357af44c6a0142c757469920a5a5ac12d22b48748d8e52b25234408ef6ca",
        ),
        (
            latest,
            "stage-b-real-guided-fair-validation-02-completed-20261019T061910Z.tar.gz",
            "32ea66618d683784a5369fbbe7068a95b5370d50f9fe9454606f5a18357f3326",
        ),
    ]
    archive_evidence = []
    sealed: dict[str, bytes] = {}
    for directory, name, expected in archives:
        archive = root / "archives" / name
        assert digest(archive.read_bytes()) == expected, name
        members: dict[str, bytes] = {}
        with tarfile.open(archive) as tf:
            for member in tf:
                if member.isfile() and any(
                    member.name.endswith(suffix)
                    for suffix in (
                        "/candidate.json",
                        "/server_authorities.json",
                        "/source_manifest.json",
                        "/full_artifact_manifest.json",
                        "/cross_run_comparison.json",
                    )
                ):
                    stream = tf.extractfile(member)
                    assert stream is not None
                    members[member.name] = stream.read()
        manifest_path = (
            directory / "source_manifest.json"
            if directory == history
            else directory / "completed-delivery/full_artifact_manifest.json"
        )
        manifest_bytes = manifest_path.read_bytes()
        assert manifest_bytes in members.values(), "manifest not identical to archive"
        manifest = json.loads(manifest_bytes)["files"]
        if directory == latest:
            for source in (
                "real-execution/server_authorities.json",
                "completed-delivery/cross_run_comparison.json",
            ):
                original = (directory / source).read_bytes()
                assert digest(original) == manifest[source]["sha256"]
                assert original in members.values()
        count = 2 if directory == history else 6
        for i in range(1, count + 1):
            rel = f"real-execution/main/candidate-{i:02}/candidate.json"
            raw = (directory / rel).read_bytes()
            assert digest(raw) == manifest[rel]["sha256"]
            assert raw in members.values(), "candidate differs from sealed archive"
            sealed[f"{directory.name}/{rel}"] = raw
        archive_evidence.append(
            {
                "archive": name,
                "sha256": expected,
                "manifest_sha256": digest(manifest_bytes),
                "candidate_bytes_match_archive_and_manifest": True,
            }
        )
    cross_path = latest / "completed-delivery/cross_run_comparison.json"
    cross = json.loads(cross_path.read_text())
    records = []
    for row in cross["rows"]:
        old = row["source"] == "HISTORICAL"
        directory = history if old else latest
        candidate = Path(row["path"]).name
        rel = f"real-execution/main/{candidate}/candidate.json"
        raw = sealed[f"{directory.name}/{rel}"]
        original = json.loads(raw)
        cid = (
            f"{'multi-solution-validation-01' if old else 'guided-fair-validation-02'}/{candidate}"
        )
        projection = {
            key: original[key]
            for key in (
                "engineering_validation",
                "composition_handoff",
                "independent_validation",
                "native_independent_validation",
                "canonical_result_hash",
            )
        }
        projection["provenance"] = {
            "candidate_id": cid,
            "raw_candidate_sha256": digest(raw),
            "source_head": (
                "4b67e01336b9b2cf73a90e0a91bda7202c73560d"
                if old
                else "953009a9b61cea818b0b9d37b15e2c9951a752a1"
            ),
            "geometry_hash": row["geometry_hash"],
            "family_hash": row["major_family_hash"],
            "meaningful_hash": row["meaningful_hash"],
            "v2_counted": row["cross_run_counted"],
            "archive": archives[0 if old else 1][1],
        }
        output = HERE / "inputs" / f"{'historical' if old else 'guided'}-{candidate}.json"
        write(output, projection)
        svg_rel = f"docs/previews/v2.2.2/stage-b/{cid}/layout.svg"
        svg = REPO / svg_rel
        assert svg.is_file()
        records.append(
            {
                "candidate_id": cid,
                "input": str(output.relative_to(HERE)),
                "projection_sha256": digest(output.read_bytes()),
                "raw_candidate_sha256": digest(raw),
                "svg_path": svg_rel,
                "svg_sha256": digest(svg.read_bytes()),
                "svg_url": "https://github.com/xuezhiorange-png/"
                "cold-storage-planning-agent/blob/2219ab6ce8ae4f1a493d083810c29b0364b5efc6/"
                + svg_rel,
            }
        )
    authority_raw = (latest / "real-execution/server_authorities.json").read_bytes()
    # Preserve the exact authority bytes, not a freshly built server object.
    authority_target = HERE / "inputs/server_authorities.json"
    authority_target.write_bytes(authority_raw)
    contracts = [
        "docs/tasks/V2_2_2-version-plan.md",
        "docs/tasks/V2_2_2-P0-process-flow-layout-regularity-contract.md",
        "docs/tasks/V2_2_2-P0C-golden-layout-abstraction-and-calibration.md",
        "docs/tasks/V2_2_2-multi-structural-construction-stage-b.md",
        "docs/tasks/V2_2_2-stage-b-guided-fair-validation-02.md",
        "docs/architecture/ADR-047-process-flow-layout-regularity-authority.md",
        "backend/src/cold_storage/modules/layout/domain/structural_composition.py",
        "backend/tests/evaluation/v222_p0a_regularity_metrics.py",
        "backend/tests/evaluation/v222_p0c_golden_layout_metrics.py",
    ]
    write(
        HERE / "sources.json",
        {
            "reference_head": "2219ab6ce8ae4f1a493d083810c29b0364b5efc6",
            "archives": archive_evidence,
            "candidates": records,
            "authority_sha256": digest(authority_raw),
            "cross_run_receipt_sha256": digest(cross_path.read_bytes()),
            "contracts": {p: digest((REPO / p).read_bytes()) for p in contracts},
            "projection_rule": "Exact selected JSON subtrees; no geometry edits; "
            "raw bytes in named archives",
            "counts": {"physical": 8, "meaningful": 6, "major_families": 4},
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_root", type=Path)
    prepare(parser.parse_args().artifact_root)
