"""Release closure evidence and immutable-scope guards for V2.2.1 P1G."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_MAIN_SHA = "a71347a7ca56c32b2facaa3b57e489427b9a7ea8"
P1G_ACCEPTED_HEAD_SHA = "83d43e6432165a2ef8d7b20683e10ac1103f50ee"
V2_2_0_TAG_SHA = "34cd6b56c1d79dde9730898c6bd46e295e423334"
P1F_MERGE_SHA = "a71347a7ca56c32b2facaa3b57e489427b9a7ea8"
P1F_HEAD_SHA = "aea30a6e6d0e640574451fd5f58bcf5d291fe278"
P1F_CI_RUN_ID = 35838403105
P1F_REPORT = "docs/tasks/V2_2_1-P1F-cross-fixture-drawing-robustness.md"
P1F_MATRIX = "docs/tasks/evidence/v2_2_1_p1f/acceptance-matrix.json"
P1G_REPORT = "docs/tasks/V2_2_1-P1G-release-closure.md"
P1G_EVIDENCE = "docs/tasks/evidence/v2_2_1_p1g/release-readiness.json"
VERSION_PLAN = "docs/tasks/V2_2-version-plan.md"
P1D_SCOPE_GUARD = "backend/tests/architecture/test_v221_p1d_drawing_lint.py"
P1E_SCOPE_GUARD = "backend/tests/architecture/test_v221_p1e_engineering_sheet_composition.py"
P1F_SCOPE_GUARD = (
    "backend/tests/architecture/test_v221_p1f_context_inset_loading_face_correction.py"
)
SELF = "backend/tests/architecture/test_v221_p1g_release_closure.py"
ALLOWED_PATHS = {
    P1D_SCOPE_GUARD,
    P1E_SCOPE_GUARD,
    P1F_SCOPE_GUARD,
    P1F_REPORT,
    P1G_REPORT,
    P1G_EVIDENCE,
    VERSION_PLAN,
    SELF,
}
EXPECTED_SVG_HASHES = {
    "PRESENTATION": "sha256:e89ca6e1f797fedca41780d2027e728b3a3f37db19c979c0fa9dc863531b2f1a",
    "MOBILE_PREVIEW": "sha256:dc0b5313113e69fdfc6c59b88f4bd911316d74b71762bae83768c1bdd70153f2",
    "ENGINEERING_SHEET": "sha256:96c82d7296d027a9b41b4b2d8198e7239bed61dbc0811259e0575e2ca3eb25d3",
    "ENGINEERING_REVIEW": "sha256:48ea97310b955b3e5b94ea68eebed49c377031c74cb4eeba9db003e36042f37d",
}
EXPECTED_SCENARIOS = {
    "P2D_REPRESENTATIVE_20T_RECTANGULAR_SITE",
    "P3_EXISTING_CONCAVE_SITE_VALIDATED_LAYOUT",
    "P4_REAL_SELECTOR_SITE_WITH_NO_BUILD_ZONES",
}
EXPECTED_PROFILES = {
    "PRESENTATION",
    "MOBILE_PREVIEW",
    "ENGINEERING_SHEET",
    "ENGINEERING_REVIEW",
}


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def _json(path: str) -> dict[str, Any]:
    value = json.loads((REPO_ROOT / path).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_p1g_is_based_on_the_immutable_release_candidate_and_docs_only_scope() -> None:
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASE_MAIN_SHA, P1G_ACCEPTED_HEAD_SHA],
        cwd=REPO_ROOT,
        check=True,
    )
    # Keep P1G's original scope assertion pinned to its accepted task head;
    # later, independently authorized tasks must not inherit this allowlist.
    changed = set(_git("diff", "--name-only", BASE_MAIN_SHA, P1G_ACCEPTED_HEAD_SHA).splitlines())
    assert changed <= ALLOWED_PATHS
    assert not any(
        path.startswith(("backend/src/", "frontend/src/", "backend/alembic/", ".github/"))
        for path in changed
    )


def test_previous_release_tag_and_candidate_lineage_are_immutable() -> None:
    assert _git("rev-parse", "v2.2.0^{commit}") == V2_2_0_TAG_SHA
    assert _git("rev-parse", BASE_MAIN_SHA) == P1F_MERGE_SHA
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", V2_2_0_TAG_SHA, BASE_MAIN_SHA],
        cwd=REPO_ROOT,
        check=True,
    )
    assert _git("rev-list", "--count", f"{V2_2_0_TAG_SHA}..{BASE_MAIN_SHA}") == "31"
    changed_files = _git("diff", "--name-only", V2_2_0_TAG_SHA, BASE_MAIN_SHA).splitlines()
    assert len(changed_files) == 59


def test_p1f_current_owner_status_and_final_ci_are_closed() -> None:
    assert _git("rev-parse", f"{P1F_HEAD_SHA}^{{tree}}") == _git(
        "rev-parse", f"{P1F_MERGE_SHA}^{{tree}}"
    )
    evidence = _json(P1G_EVIDENCE)
    assert evidence["p1f_matrix"]["merge_tree_matches_exact_ci_head"] is True
    report = (REPO_ROOT / P1F_REPORT).read_text(encoding="utf-8")
    plan = (REPO_ROOT / VERSION_PLAN).read_text(encoding="utf-8")
    current_report = report.split("## Current R2 rerun", 1)[0]
    current_plan = plan.split("## V2.2.1 P1F cross-fixture", 1)[1].split(
        "## V2.2.1 P1G release closure", 1
    )[0]
    for text in (current_report, current_plan):
        assert "OWNER_VISUAL_REVIEW=PASS" in text
        assert "P1F_ACCEPTANCE_COMPLETE=true" in text
        assert "P1F_BLOCKERS=NONE" in text
        assert f"P1F_FINAL_MERGE_SHA={P1F_MERGE_SHA}" in text
        assert f"P1F_FINAL_EXACT_HEAD_SHA={P1F_HEAD_SHA}" in text
        assert f"P1F_FINAL_EXACT_CI_RUN_ID={P1F_CI_RUN_ID}" in text
        assert "P1F_FINAL_EXACT_CI_RESULT=SUCCESS" in text


def test_previous_phase_scope_guards_pin_the_merged_phase_trees() -> None:
    p1d_guard = (REPO_ROOT / P1D_SCOPE_GUARD).read_text(encoding="utf-8")
    p1e_guard = (REPO_ROOT / P1E_SCOPE_GUARD).read_text(encoding="utf-8")
    p1f_guard = (REPO_ROOT / P1F_SCOPE_GUARD).read_text(encoding="utf-8")
    assert 'P1D_MERGE_SHA = "2154c869ed202beeeb1903d1875508122a4ed829"' in p1d_guard
    assert 'P1E_MERGE_SHA = "debda749966e7c890e2f8758f468fa582fb3def8"' in p1e_guard
    assert 'P1F_MERGE_SHA = "a71347a7ca56c32b2facaa3b57e489427b9a7ea8"' in p1f_guard
    assert "BASE_MAIN_SHA, P1D_MERGE_SHA" in p1d_guard
    assert "BASE_MAIN_SHA, P1E_MERGE_SHA" in p1e_guard
    assert "BASE_MAIN_SHA, P1F_MERGE_SHA" in p1f_guard


def test_representative_svg_hashes_and_p1f_matrix_match_release_baseline() -> None:
    evidence = _json(P1G_EVIDENCE)
    assert evidence["representative_svg_sha256"] == EXPECTED_SVG_HASHES

    matrix = _json(P1F_MATRIX)
    assert matrix["full_chain_authoritative_fixture_count"] == 3
    assert matrix["composition_only_fixture_count"] == 2
    assert matrix["scenario_count"] == 5
    assert matrix["p1f_acceptance_complete"] is True
    assert matrix["p1f_blocker"] is None
    rows = matrix["acceptance_matrix"]
    assert len(rows) == 12
    assert {row["scenario"] for row in rows} == EXPECTED_SCENARIOS
    assert {row["profile"] for row in rows} == EXPECTED_PROFILES
    assert all(row["result"] == "PASS" for row in rows)
    assert all(row["drawing_lint_gate"] == "PASS" for row in rows)
    assert all(row["errors"] == 0 and row["unavailable_facts"] == 0 for row in rows)
    assert all(row["determinism"] is True for row in rows)
    assert all(
        row["context_loading_face_endpoint_matches_authority"] is True
        for row in rows
        if row["context_inset_visible"]
    )
    representative = {
        row["profile"]: row["svg_hash"]
        for row in rows
        if row["scenario"] == "P2D_REPRESENTATIVE_20T_RECTANGULAR_SITE"
    }
    assert representative == EXPECTED_SVG_HASHES


def test_release_readiness_and_tool7_compatibility_are_explicit() -> None:
    evidence = _json(P1G_EVIDENCE)
    phase_status = evidence["phase_status"]
    assert set(
        phase_status[key]
        for key in (
            "P0_LAYOUT_DRAWING_STYLE_CONTRACT",
            "P1A_CANVAS_PAGE_COMPOSITION",
            "P1A2_PRESENTATION_MOBILE_FOCUS",
            "P1B_MONOCHROME_CAD_HIERARCHY",
            "P1C_ROOM_LABEL_ANNOTATION",
            "P1D_DRAWING_LINT_FOUNDATION",
            "P1E_ENGINEERING_SHEET_COMPOSITION",
            "P1F_CROSS_FIXTURE_DRAWING_ROBUSTNESS",
        )
    ) == {"PASS"}
    mcp = evidence["mcp_compatibility"]
    assert mcp["tool_count"] == 7
    assert mcp["tool_order"] == [
        "preview_zone_plan",
        "preview_cooling_load",
        "preview_equipment",
        "preview_installed_power",
        "preview_investment",
        "preview_factory_power",
        "preview_site_layout",
    ]
    assert mcp["existing_six_tool_order_preserved"] is True
    assert mcp["existing_six_tool_contract_preserved"] is True
    assert mcp["tool7_input_contract_changed"] is False
    assert mcp["unmocked_tool7_full_chain"] == "PASS"
    assert mcp["first_p2c_candidate_p2d_result"] == "REJECTED"
    assert mcp["later_full_pass_candidate_found"] is True

    report = (REPO_ROOT / P1G_REPORT).read_text(encoding="utf-8")
    normalized_report = " ".join(report.split())
    assert "v2.2.1 — CAD Drawing Projection & Engineering Sheet Quality" in report
    assert "P1G_EXACT_HEAD_CI_RUN_ID=PR_EXACT_HEAD_CHECK_REQUIRED" in report
    for forbidden_claim in (
        "construction-drawing readiness",
        "replace formal engineering design",
        "physical print scale",
        "PDF/DXF export",
    ):
        assert forbidden_claim in normalized_report
    for authorization in (
        "READY_AUTHORIZED=false",
        "MERGE_AUTHORIZED=false",
        "TAG_AUTHORIZED=false",
        "GITHUB_RELEASE_AUTHORIZED=false",
        "DEPLOYMENT_AUTHORIZED=false",
    ):
        assert authorization in report
