"""P2C candidate enumeration and P2D-filtered selection tests."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cold_storage.modules.layout.application import validated_candidate_selection as selection
from cold_storage.modules.layout.domain.placement import SitePlacementResultV1


class _FakeCandidateStream:
    def __init__(self, candidates: list[SitePlacementResultV1]) -> None:
        self._candidates = candidates
        self._provenance = {
            "search_tree_exhausted": True,
            "node_budget_exhausted": False,
            "complete_candidate_limit_stops_search": False,
            "node_budget_is_only_search_cutoff": True,
        }

    def iter_candidates(self):
        yield from self._candidates

    @property
    def candidate_count(self) -> int:
        return len(self._candidates)

    @property
    def search_tree_exhausted(self) -> bool:
        return True

    @property
    def node_budget_exhausted(self) -> bool:
        return False

    @property
    def provenance(self) -> dict[str, Any]:
        return dict(self._provenance)


class _FakeRoutedResult:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self._payload = dict(payload)

    def to_dict(self) -> dict[str, Any]:
        return dict(self._payload)


def _candidate(marker: str, should_count: int) -> SitePlacementResultV1:
    return SitePlacementResultV1.from_payload(
        {
            "schema_version": "1.0.0",
            "placement_result_identity": "site_constrained_factory_layout@1.0.0",
            "marker": marker,
            "placement_objective_vector": {
                "aggregation": "LEXICOGRAPHIC",
                "should_adjacency": {"satisfied_count": should_count},
                "loading_side": {"preferred_loading_side": "UNSPECIFIED"},
            },
        }
    )


def _result(*, valid: bool, marker: str) -> _FakeRoutedResult:
    return _FakeRoutedResult(
        {
            "result_identity": "site_access_routing@1.0.0",
            "marker": marker,
            "project_layout_validated": valid,
            "p2_complete": valid,
            "access_requirement_count": 12,
            "access_pass_count": 12 if valid else 11,
            "truck_route_validated": valid,
            "warnings": [] if valid else ["P2D_REJECTED_CANDIDATE"],
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


def test_selects_later_full_pass_using_existing_p2c_objective(monkeypatch) -> None:
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
        "P2C_OBJECTIVE_AMONG_P2D_FULL_PASS_CANDIDATES"
    )


def test_selection_is_deterministic_for_same_candidate_stream(monkeypatch) -> None:
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


def test_p2d_error_rejects_one_candidate_and_continues(monkeypatch) -> None:
    candidates = [_candidate("A", 4), _candidate("B", 3)]
    monkeypatch.setattr(
        selection,
        "enumerate_placement_candidates",
        lambda *args, **kwargs: _FakeCandidateStream(candidates),
    )

    def route(*args, **kwargs):
        if args[3].to_dict()["marker"] == "A":
            raise selection.LayoutAuthorityError("PACKAGING_SORTING_STRAIGHT_ROUTE_REQUIRED")
        return _result(valid=True, marker="B")

    monkeypatch.setattr(selection, "route_site_placement", route)
    zone_plan, handoff, geometry = _selection_inputs()

    body = selection.select_validated_placement(zone_plan, handoff, geometry).to_dict()
    assert body["validated_layout_selected"] is True
    assert body["selected_layout"]["marker"] == "B"
    assert body["candidate_validation_trace"][0]["error_code"] == (
        "PACKAGING_SORTING_STRAIGHT_ROUTE_REQUIRED"
    )
