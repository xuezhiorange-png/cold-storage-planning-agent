"""P2C candidate enumeration and P2D-filtered selection tests."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest

from cold_storage.modules.layout.application import validated_candidate_selection as selection
from cold_storage.modules.layout.domain.placement import SitePlacementResultV1
from cold_storage.modules.layout.domain.structural_composition import (
    CENTRAL_PROCESS_HUB,
    LINEAR_PROCESS_BAND,
    StructuralCompositionFamilyV1,
)
from cold_storage.modules.layout.domain.structural_quality import StructuralQualityFactsV1


class _FakeCandidateStream:
    def __init__(
        self,
        candidates: list[SitePlacementResultV1],
        *,
        structured: Mapping[str, bool] | None = None,
    ) -> None:
        self._candidates = candidates
        self._structured = dict(structured or {})
        self._provenance = {
            "search_tree_exhausted": True,
            "node_budget_exhausted": False,
            "complete_candidate_limit_stops_search": False,
            "node_budget_is_only_search_cutoff": True,
        }
        self.structural_composition_family = StructuralCompositionFamilyV1(
            CENTRAL_PROCESS_HUB,
            "X",
            "UNRESOLVED",
            "SYNTHETIC_SELECTOR_TEST",
        )

    def iter_candidates(self):
        yield from self._candidates

    @property
    def candidate_count(self) -> int:
        return len(self._candidates)

    @property
    def visited_node_count(self) -> int:
        return 13 * len(self._candidates)

    @property
    def search_tree_exhausted(self) -> bool:
        return True

    @property
    def node_budget_exhausted(self) -> bool:
        return False

    @property
    def provenance(self) -> dict[str, Any]:
        return dict(self._provenance)

    def structurally_generated(self, candidate_hash: str) -> bool:
        return self._structured.get(candidate_hash, True)


class _FakeRoutedResult:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self._payload = dict(payload)

    def to_dict(self) -> dict[str, Any]:
        return dict(self._payload)


@pytest.fixture(autouse=True)
def _single_synthetic_lane(monkeypatch: pytest.MonkeyPatch) -> None:
    family = StructuralCompositionFamilyV1(
        CENTRAL_PROCESS_HUB,
        "X",
        "UNRESOLVED",
        "SYNTHETIC_SELECTOR_TEST",
    )
    monkeypatch.setattr(
        selection,
        "composition_family_candidates",
        lambda _site: (family,),
    )


def _candidate(marker: str, should_count: int) -> SitePlacementResultV1:
    return SitePlacementResultV1.from_payload(
        {
            "schema_version": "1.0.0",
            "placement_result_identity": "site_constrained_factory_layout@1.0.0",
            "marker": marker,
            "canonical_candidate_hash": f"candidate-{marker}",
            "placement_objective_vector": {
                "aggregation": "LEXICOGRAPHIC",
                "should_adjacency": {"satisfied_count": should_count},
                "loading_side": {"preferred_loading_side": "UNSPECIFIED"},
            },
        }
    )


def _result(*, valid: bool, marker: str, warnings: list[str] | None = None) -> _FakeRoutedResult:
    resolved_warnings = warnings
    if resolved_warnings is None:
        resolved_warnings = [] if valid else ["P2D_REJECTED_CANDIDATE"]
    return _FakeRoutedResult(
        {
            "result_identity": "site_access_routing@1.0.0",
            "marker": marker,
            "project_layout_validated": valid,
            "p2_complete": valid,
            "access_requirement_count": 12,
            "access_pass_count": 12 if valid else 11,
            "truck_route_validated": valid,
            "warnings": resolved_warnings,
            "truck_route_codes": [],
        }
    )


def _selection_inputs() -> tuple[dict[str, Any], dict[str, Any], object]:
    return (
        {"success": True, "calculator_name": "cold_room_zone_plan", "calculator_version": "1.0.0"},
        {},
        type(
            "Geometry",
            (),
            {"to_dict": lambda self: {"site": {"preferred_loading_side": "UNSPECIFIED"}}},
        )(),
    )


def _install_tied_structural_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        selection,
        "build_structural_quality_facts",
        lambda *_args, **_kwargs: StructuralQualityFactsV1("{}", (0,)),
    )


def test_selects_later_full_pass_using_existing_p2c_objective(monkeypatch) -> None:
    _install_tied_structural_facts(monkeypatch)
    first = _candidate("A", 3)
    later = _candidate("B", 4)
    stream = _FakeCandidateStream([first, later])
    calls: list[str] = []

    monkeypatch.setattr(selection, "enumerate_placement_candidates", lambda *args, **kwargs: stream)

    def route(*args, **kwargs):
        marker = args[3].to_dict()["marker"]
        calls.append(marker)
        return _result(valid=marker == "B", marker=marker)

    monkeypatch.setattr(selection, "route_site_placement", route)
    zone_plan, handoff, geometry = _selection_inputs()

    result = selection.select_validated_placement(zone_plan, handoff, geometry)
    body = result.to_dict()
    assert calls == ["A", "B"]
    assert body["validated_layout_selected"] is True
    assert body["selected_layout"]["marker"] == "B"
    assert body["p2c_candidate_count"] == 2
    assert body["p2d_full_pass_candidate_count"] == 1
    assert body["selection_provenance"]["selection_basis"] == (
        "P1A_STRUCTURAL_QUALITY_THEN_P2B2_AMONG_P2D_FULL_PASS_CANDIDATES"
    )


def test_selection_is_deterministic_for_same_candidate_stream(monkeypatch) -> None:
    _install_tied_structural_facts(monkeypatch)
    candidates = [_candidate("A", 3), _candidate("B", 4)]
    monkeypatch.setattr(
        selection,
        "enumerate_placement_candidates",
        lambda *args, **kwargs: _FakeCandidateStream(candidates),
    )
    monkeypatch.setattr(
        selection,
        "route_site_placement",
        lambda *args, **kwargs: _result(valid=True, marker=args[3].to_dict()["marker"]),
    )
    zone_plan, handoff, geometry = _selection_inputs()

    first = selection.select_validated_placement(zone_plan, handoff, geometry)
    second = selection.select_validated_placement(zone_plan, handoff, geometry)
    assert first.canonical_json() == second.canonical_json()
    assert first.canonical_result_hash == second.canonical_result_hash


def test_no_full_pass_reports_search_exhaustion_not_infeasibility(monkeypatch) -> None:
    stream = _FakeCandidateStream([_candidate("A", 3)])
    stream._provenance["search_tree_exhausted"] = False
    stream._provenance["node_budget_exhausted"] = True
    monkeypatch.setattr(selection, "enumerate_placement_candidates", lambda *args, **kwargs: stream)
    monkeypatch.setattr(
        selection,
        "route_site_placement",
        lambda *args, **kwargs: _result(valid=False, marker="A"),
    )
    zone_plan, handoff, geometry = _selection_inputs()

    body = selection.select_validated_placement(zone_plan, handoff, geometry).to_dict()
    assert body["status"] == "VALIDATED_LAYOUT_SEARCH_EXHAUSTED"
    assert body["project_layout_validated"] is False
    assert body["selection_provenance"]["objective_optimal_within_search_family"] is False
    assert body["layout_infeasible_proof_implemented"] is False
    assert "not a mathematical infeasibility proof" in body["warnings"][0]


def test_p2d_non_full_pass_rejects_one_candidate_and_continues(monkeypatch) -> None:
    _install_tied_structural_facts(monkeypatch)
    candidates = [_candidate("A", 4), _candidate("B", 3)]
    monkeypatch.setattr(
        selection,
        "enumerate_placement_candidates",
        lambda *args, **kwargs: _FakeCandidateStream(candidates),
    )

    def route(*args, **kwargs):
        if args[3].to_dict()["marker"] == "A":
            return _result(
                valid=False,
                marker="A",
                warnings=["PACKAGING_SORTING_STRAIGHT_ROUTE_REQUIRED"],
            )
        return _result(valid=True, marker="B")

    monkeypatch.setattr(selection, "route_site_placement", route)
    zone_plan, handoff, geometry = _selection_inputs()

    body = selection.select_validated_placement(zone_plan, handoff, geometry).to_dict()
    assert body["validated_layout_selected"] is True
    assert body["selected_layout"]["marker"] == "B"
    assert body["candidate_validation_trace"][0]["p2d_full_pass"] is False
    assert body["candidate_validation_trace"][0]["warnings"] == [
        "PACKAGING_SORTING_STRAIGHT_ROUTE_REQUIRED"
    ]


def test_p2d_authority_error_fails_fast(monkeypatch) -> None:
    candidates = [_candidate("A", 4), _candidate("B", 3)]
    monkeypatch.setattr(
        selection,
        "enumerate_placement_candidates",
        lambda *args, **kwargs: _FakeCandidateStream(candidates),
    )

    def route(*args, **kwargs):
        raise selection.LayoutAuthorityError("P2D_RESULT_INTEGRITY_MISMATCH")

    monkeypatch.setattr(selection, "route_site_placement", route)
    zone_plan, handoff, geometry = _selection_inputs()

    with pytest.raises(selection.LayoutAuthorityError) as caught:
        selection.select_validated_placement(zone_plan, handoff, geometry)

    assert caught.value.code == "P2D_RESULT_INTEGRITY_MISMATCH"


def test_hard_feasibility_precedes_structural_quality(monkeypatch) -> None:
    candidates = [_candidate("pretty-but-invalid", 5), _candidate("valid", 0)]
    stream = _FakeCandidateStream(candidates)
    monkeypatch.setattr(selection, "enumerate_placement_candidates", lambda *args, **kwargs: stream)
    evaluated: list[str] = []

    def facts(candidate, *_args, **_kwargs):
        marker = candidate["marker"]
        evaluated.append(marker)
        value = 100 if marker == "pretty-but-invalid" else 1
        return StructuralQualityFactsV1(
            json.dumps({"structurally_generated": True}, sort_keys=True), (value,)
        )

    monkeypatch.setattr(selection, "build_structural_quality_facts", facts)
    monkeypatch.setattr(
        selection,
        "route_site_placement",
        lambda *args, **kwargs: _result(
            valid=args[3].to_dict()["marker"] == "valid",
            marker=args[3].to_dict()["marker"],
        ),
    )
    zone_plan, handoff, geometry = _selection_inputs()

    body = selection.select_validated_placement(zone_plan, handoff, geometry).to_dict()
    assert body["selected_layout"]["marker"] == "valid"
    assert evaluated == ["valid"]


def test_structured_full_pass_precedes_legacy_fallback(monkeypatch) -> None:
    structured = _candidate("structured", 0)
    fallback = _candidate("fallback", 5)
    structured_hash = structured.to_dict()["canonical_candidate_hash"]
    fallback_hash = fallback.to_dict()["canonical_candidate_hash"]
    stream = _FakeCandidateStream(
        [fallback, structured], structured={fallback_hash: False, structured_hash: True}
    )
    monkeypatch.setattr(selection, "enumerate_placement_candidates", lambda *args, **kwargs: stream)
    monkeypatch.setattr(
        selection,
        "build_structural_quality_facts",
        lambda candidate, *_args, **_kwargs: StructuralQualityFactsV1(
            json.dumps(
                {"structurally_generated": candidate["marker"] == "structured"},
                sort_keys=True,
            ),
            (int(candidate["marker"] == "structured"),),
        ),
    )
    monkeypatch.setattr(
        selection,
        "route_site_placement",
        lambda *args, **kwargs: _result(valid=True, marker=args[3].to_dict()["marker"]),
    )
    zone_plan, handoff, geometry = _selection_inputs()

    result = selection.select_validated_placement(zone_plan, handoff, geometry)
    assert result.to_dict()["selected_layout"]["marker"] == "structured"
    assert result.internal_evaluation["structural_fallback_used"] is False


def test_exact_structural_tie_preserves_legacy_p2b2_tiebreak(monkeypatch) -> None:
    _install_tied_structural_facts(monkeypatch)
    candidates = [_candidate("lower", 3), _candidate("higher", 4)]
    monkeypatch.setattr(
        selection,
        "enumerate_placement_candidates",
        lambda *args, **kwargs: _FakeCandidateStream(candidates),
    )
    monkeypatch.setattr(
        selection,
        "route_site_placement",
        lambda *args, **kwargs: _result(valid=True, marker=args[3].to_dict()["marker"]),
    )
    zone_plan, handoff, geometry = _selection_inputs()

    result = selection.select_validated_placement(zone_plan, handoff, geometry)
    assert result.to_dict()["selected_layout"]["marker"] == "higher"
    assert result.internal_evaluation["p2b2_tiebreak_used"] is True
    assert result.internal_evaluation["first_decisive_component"] == "P2B2_FINAL_TIE_BREAK"


def test_selector_enumerates_both_linear_directions_and_central_hub(monkeypatch) -> None:
    lanes = (
        StructuralCompositionFamilyV1(LINEAR_PROCESS_BAND, "X", "POSITIVE", "LANE_TEST"),
        StructuralCompositionFamilyV1(LINEAR_PROCESS_BAND, "X", "NEGATIVE", "LANE_TEST"),
        StructuralCompositionFamilyV1(CENTRAL_PROCESS_HUB, "X", "UNRESOLVED", "LANE_TEST"),
    )
    monkeypatch.setattr(selection, "composition_family_candidates", lambda _site: lanes)
    seen: list[tuple[str, str]] = []

    def enumerate_lane(*_args, structural_family, search_phase, **_kwargs):
        seen.append((structural_family.family, structural_family.dominant_direction))
        marker = f"{structural_family.family}:{structural_family.dominant_direction}"
        return _FakeCandidateStream([_candidate(marker, 0)])

    monkeypatch.setattr(selection, "enumerate_placement_candidates", enumerate_lane)
    monkeypatch.setattr(
        selection,
        "build_structural_quality_facts",
        lambda *_args, **_kwargs: StructuralQualityFactsV1(
            json.dumps({"structurally_generated": True}, sort_keys=True), (1,)
        ),
    )
    monkeypatch.setattr(
        selection,
        "route_site_placement",
        lambda *args, **kwargs: _result(valid=True, marker=args[3].to_dict()["marker"]),
    )
    zone_plan, handoff, geometry = _selection_inputs()

    result = selection.select_validated_placement(
        zone_plan, handoff, geometry, placement_node_budget=45
    )

    assert set(seen) == {
        (LINEAR_PROCESS_BAND, "POSITIVE"),
        (LINEAR_PROCESS_BAND, "NEGATIVE"),
        (CENTRAL_PROCESS_HUB, "UNRESOLVED"),
    }
    assert len(seen) == 3
    assert result.internal_evaluation["distinct_full_pass_family_count"] == 3


def test_internal_explanation_reports_first_decisive_structural_component(monkeypatch) -> None:
    candidates = [_candidate("winner", 0), _candidate("runner-up", 5)]
    monkeypatch.setattr(
        selection,
        "enumerate_placement_candidates",
        lambda *args, **kwargs: _FakeCandidateStream(candidates),
    )
    monkeypatch.setattr(
        selection,
        "build_structural_quality_facts",
        lambda candidate, *_args, **_kwargs: StructuralQualityFactsV1(
            json.dumps({"structurally_generated": True}, sort_keys=True),
            (1, 1) if candidate["marker"] == "winner" else (0, 99),
        ),
    )
    monkeypatch.setattr(
        selection,
        "route_site_placement",
        lambda *args, **kwargs: _result(valid=True, marker=args[3].to_dict()["marker"]),
    )
    zone_plan, handoff, geometry = _selection_inputs()

    result = selection.select_validated_placement(zone_plan, handoff, geometry)
    explanation = result.internal_evaluation
    assert result.to_dict()["selected_layout"]["marker"] == "winner"
    assert explanation["runner_up_present"] is True
    assert explanation["first_decisive_component"] == "STRUCTURED_GENERATION"
    assert explanation["winner_value"] == 1
    assert explanation["runner_up_value"] == 0
    assert explanation["hard_feasibility_passed"] is True
