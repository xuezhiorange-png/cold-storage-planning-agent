"""Negative-scenario tests for NR-01 … NR-20 (Section 12 of the contract).

Every frozen negative requirement maps to exactly one fixture that
exercises a release-evidence verifier with a crafted bad input.  Each
test asserts the precise ``RC_*`` error code from the frozen table —
no single broad test name covers multiple unasserted conditions.
"""

from __future__ import annotations

import pytest

from cold_storage.release.canonical_serialization import ReleaseEvidenceError
from cold_storage.release.negative_scenario_fixtures import all_negative_scenarios

SCENARIOS = {s.nr_id: s for s in all_negative_scenarios()}


def test_all_20_negative_scenarios_are_present() -> None:
    """The fixture registry must contain exactly NR-01 … NR-20."""
    assert len(SCENARIOS) == 20
    for i in range(1, 21):
        assert f"NR-{i:02d}" in SCENARIOS, f"missing NR-{i:02d}"


def test_every_error_code_is_independently_covered() -> None:
    """No two fixtures share an expected error code (one NR per code)."""
    codes = [s.expected_error_code for s in SCENARIOS.values()]
    assert len(codes) == len(set(codes)), "duplicate error code across fixtures"
    assert len(codes) == 20


def _run_and_assert(nr_id: str) -> None:
    scenario = SCENARIOS[nr_id]
    with pytest.raises(ReleaseEvidenceError) as exc_info:
        scenario.run()
    assert exc_info.value.failure_code == scenario.expected_error_code, (
        f"{nr_id}: expected {scenario.expected_error_code}, got {exc_info.value.failure_code}"
    )


@pytest.mark.parametrize("nr_id", [f"NR-{i:02d}" for i in range(1, 21)])
def test_negative_scenario_rejects_with_expected_error_code(nr_id: str) -> None:
    """Each NR fixture must be rejected with its frozen error code."""
    _run_and_assert(nr_id)


def test_negative_scenario_stage_mapping() -> None:
    """Each fixture's expected rejection stage matches the contract table."""
    expected_stages = {
        "NR-01": "BUILD",
        "NR-02": "BUILD",
        "NR-03": "BUILD",
        "NR-04": "BUILD",
        "NR-05": "BUILD",
        "NR-06": "BUILD",
        "NR-07": "REGISTRY",
        "NR-08": "ARTIFACT",
        "NR-09": "ARTIFACT",
        "NR-10": "ARTIFACT",
        "NR-11": "PROVENANCE",
        "NR-12": "PROVENANCE",
        "NR-13": "PROVENANCE",
        "NR-14": "PROVENANCE",
        "NR-15": "PROMOTION",
        "NR-16": "PROMOTION",
        "NR-17": "PROMOTION",
        "NR-18": "PROMOTION",
        "NR-19": "PROMOTION",
        "NR-20": "PROMOTION",
    }
    for nr_id, stage in expected_stages.items():
        assert SCENARIOS[nr_id].expected_stage == stage


# Explicit per-NR mapping output (machine-readable contract requirement).
NEGATIVE_REQUIREMENT_MAPPING = [
    ("NR-01", "NEG-01-DIFFERENT_COMMIT", "RC_SOURCE_COMMIT_MISMATCH", "BUILD"),
    ("NR-02", "NEG-02-BASE_IMAGE_DIGEST_DRIFT", "RC_BASE_IMAGE_DIGEST_MISMATCH", "BUILD"),
    ("NR-03", "NEG-03-LOCKFILE_DIGEST_MISMATCH", "RC_LOCKFILE_DIGEST_MISMATCH", "BUILD"),
    ("NR-04", "NEG-04-BUILD_ARG_MISMATCH", "RC_BUILD_ARG_MISMATCH", "BUILD"),
    ("NR-05", "NEG-05-FINAL_IMAGE_DIGEST_MISMATCH", "RC_FINAL_IMAGE_DIGEST_MISMATCH", "BUILD"),
    ("NR-06", "NEG-06-FINAL_IMAGE_DIGEST_MISSING", "RC_FINAL_IMAGE_DIGEST_MISSING", "BUILD"),
    ("NR-07", "NEG-07-REGISTRY_DIGEST_MISMATCH", "RC_REGISTRY_DIGEST_MISMATCH", "REGISTRY"),
    ("NR-08", "NEG-08-ARTIFACT_MANIFEST_MISSING", "RC_ARTIFACT_MANIFEST_MISSING", "ARTIFACT"),
    ("NR-09", "NEG-09-ARTIFACT_DUPLICATE_KEY", "RC_ARTIFACT_DUPLICATE_KEY", "ARTIFACT"),
    ("NR-10", "NEG-10-ARTIFACT_DIGEST_MISMATCH", "RC_ARTIFACT_DIGEST_MISMATCH", "ARTIFACT"),
    ("NR-11", "NEG-11-PROVENANCE_UNSIGNED", "RC_PROVENANCE_UNSIGNED", "PROVENANCE"),
    ("NR-12", "NEG-12-PROVENANCE_REPO_MISMATCH", "RC_PROVENANCE_REPO_MISMATCH", "PROVENANCE"),
    (
        "NR-13",
        "NEG-13-PROVENANCE_WORKFLOW_MISMATCH",
        "RC_PROVENANCE_WORKFLOW_MISMATCH",
        "PROVENANCE",
    ),
    ("NR-14", "NEG-14-PROVENANCE_SUBJECT_MISMATCH", "RC_PROVENANCE_SUBJECT_MISMATCH", "PROVENANCE"),
    ("NR-15", "NEG-15-PROMOTION_MUTABLE_TAG", "RC_PROMOTION_MUTABLE_TAG", "PROMOTION"),
    ("NR-16", "NEG-16-PROMOTION_REBUILD", "RC_PROMOTION_REBUILD", "PROMOTION"),
    ("NR-17", "NEG-17-PROMOTION_DIGEST_DRIFT", "RC_PROMOTION_DIGEST_DRIFT", "PROMOTION"),
    ("NR-18", "NEG-18-ENV_CONFIG_DIGEST_MISSING", "RC_ENV_CONFIG_DIGEST_MISSING", "PROMOTION"),
    ("NR-19", "NEG-19-APPROVER_MISSING", "RC_APPROVER_MISSING", "PROMOTION"),
    (
        "NR-20",
        "NEG-20-PROMOTION_RECORD_UNVERIFIABLE",
        "RC_PROMOTION_RECORD_UNVERIFIABLE",
        "PROMOTION",
    ),
]


def test_negative_requirement_mapping_matches_fixtures() -> None:
    for nr_id, fixture_id, error_code, stage in NEGATIVE_REQUIREMENT_MAPPING:
        scenario = SCENARIOS[nr_id]
        assert scenario.fixture_id == fixture_id
        assert scenario.expected_error_code == error_code
        assert scenario.expected_stage == stage
