"""Keep P0A's missing-source and uncalibrated-threshold status explicit."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/tasks/V2_2_2-P0A-canonical-fixture-regularity-calibration.md"


def test_p0a_does_not_claim_missing_canonical_input_or_thresholds_are_ready() -> None:
    evidence = EVIDENCE.read_text(encoding="utf-8")

    required_facts = (
        "CANONICAL_FIXTURE_ACQUIRED=false",
        "XINZHAO_CANONICAL_INPUT_RAW_SHA256=NOT_COMPUTED",
        "XINZHAO_V221_REPLAY_RESULT=NOT_RUN",
        "MISSING_CANONICAL_FIXTURE=true",
        "DEPTH_ALIGNMENT_THRESHOLD_STATUS=NOT_READY",
        "PROPOSED_DEPTH_ALIGNMENT_PASS_THRESHOLD=NOT_READY",
        "COMPACTNESS_CLASSIFIER_STATUS=NOT_READY",
        "P1_ENTRY_CANONICAL_FIXTURE_READY=false",
        "P1_ENTRY_DEPTH_THRESHOLD_READY=false",
        "P1_ENTRY_COMPACTNESS_CLASSIFIER_READY=false",
        "P1_ENTRY_CALIBRATION_MATRIX_READY=false",
        "P1_IMPLEMENTATION_ENTRY_READY=false",
        "ORIGINAL_GOLDEN_SOURCE_AVAILABLE=false",
        "P1F also has two composition-only scenarios",
    )
    for fact in required_facts:
        assert fact in evidence, fact


def test_matching_historical_result_hash_is_not_claimed_as_input_identity() -> None:
    evidence = EVIDENCE.read_text(encoding="utf-8")

    assert "output-hash match does not establish" in evidence
    assert "input identity unproven" in evidence
    assert "No input was reconstructed" in evidence
