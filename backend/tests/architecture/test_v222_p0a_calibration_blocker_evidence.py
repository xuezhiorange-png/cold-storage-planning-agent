"""Keep P0A's acquired-source and uncalibrated-threshold status explicit."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/tasks/V2_2_2-P0A-canonical-fixture-regularity-calibration.md"


def test_p0a_records_verified_fixture_but_keeps_thresholds_and_entry_blocked() -> None:
    evidence = EVIDENCE.read_text(encoding="utf-8")

    required_facts = (
        "CANONICAL_FIXTURE_ACQUIRED=true",
        "CANONICAL_FIXTURE_VERIFIED=true",
        "RAW_SHA256=d03ecae9e1e2808cba346eb83a39f853c8a4b366acc103669af1cf868363901e",
        "TOOL7_INPUT_SCHEMA_ACCEPTANCE=PASS",
        "XINZHAO_V221_REPLAY_RESULT=PASS",
        "CANONICAL_RESULT_HASH_MATCH=true",
        "SVG_HASH_MATCH=true",
        "P1_ENTRY_CANONICAL_FIXTURE_READY=true",
        "OWNER_LABELLED_REGULARITY_POSITIVE_SAMPLES_UNAVAILABLE=true",
        "DEPTH_ALIGNMENT_THRESHOLD_STATUS=NOT_READY",
        "PROPOSED_DEPTH_ALIGNMENT_PASS_THRESHOLD=NOT_READY",
        "COMPACTNESS_CLASSIFIER_STATUS=NOT_READY",
        "P1_ENTRY_DEPTH_THRESHOLD_READY=false",
        "P1_ENTRY_COMPACTNESS_CLASSIFIER_READY=false",
        "P1_ENTRY_CALIBRATION_MATRIX_READY=false",
        "P1_IMPLEMENTATION_ENTRY_READY=false",
        "ORIGINAL_GOLDEN_SOURCE_AVAILABLE=false",
        "CALIBRATION_FIXTURE_COUNT=4",
        "OWNER_LABELLED_REGULARITY_POSITIVE_SAMPLES=0",
        "No Owner-labelled positive regularity sample",
    )
    for fact in required_facts:
        assert fact in evidence, fact


def test_canonical_fixture_artifacts_preserve_raw_provenance_and_uncertainty() -> None:
    fixture_dir = ROOT / "backend/tests/fixtures/v22"
    provenance = (fixture_dir / "xinzhao_20t_site_layout_input_v3.provenance.json").read_text()
    matrix = (
        ROOT / "docs/tasks/evidence/v2_2_2_p0a/regularity-calibration-matrix.json"
    ).read_text()

    assert '"raw_size_bytes": 9552' in provenance
    assert (
        '"raw_sha256": "d03ecae9e1e2808cba346eb83a39f853c8a4b366acc103669af1cf868363901e"'
        in provenance
    )
    assert '"not_engineering_authority": true' in provenance
    assert "input is not asserted byte-identical" in matrix
    assert '"owner_labelled_positive_sample_count": 0' in matrix
    assert '"depth_alignment_rate": "UNAVAILABLE"' in matrix
