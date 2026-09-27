"""R11 resumable-search quantum invariants."""

from __future__ import annotations

from types import SimpleNamespace

from cold_storage.modules.layout.domain import placement as placement_domain


def test_quantum_yield_preserves_generator_cursor_without_prefix_replay(monkeypatch) -> None:
    visited_cursors: list[int] = []

    def resumable_walk(_context, stats):
        for cursor in range(5):
            visited_cursors.append(cursor)
            stats.visited_nodes += 1
            stats.current_work_item = {"cursor": cursor}
            quantum = placement_domain._quantum_checkpoint(stats)
            if quantum is not None:
                yield quantum

    monkeypatch.setattr(placement_domain, "_walk_complete_candidate_payloads", resumable_walk)
    stream = placement_domain.PlacementCandidateEnumerationV1(
        SimpleNamespace(node_budget=120, structural_topology="STRAIGHT_LINEAR_BAND")
    )

    first = stream.advance_quantum(2)
    second = stream.advance_quantum(2)
    third = stream.advance_quantum(2)

    assert first.status == "QUANTUM_EXHAUSTED"
    assert second.status == "QUANTUM_EXHAUSTED"
    assert first.search_exhausted is False
    assert second.search_exhausted is False
    assert third.status == "SEARCH_EXHAUSTED"
    assert third.search_exhausted is True
    assert [first.nodes_visited, second.nodes_visited, third.nodes_visited] == [2, 2, 1]
    assert visited_cursors == [0, 1, 2, 3, 4]
    assert stream.visited_node_count == sum(
        advance.nodes_visited for advance in (first, second, third)
    )


def test_existing_internal_caps_are_fairness_quanta_not_global_budget_growth() -> None:
    assert placement_domain.CONSTRUCTIVE_SORTING_ROOT_NODE_BUDGET == 16
    assert placement_domain.CONSTRUCTIVE_FACE_PAIR_NODE_BUDGET == 20
    assert placement_domain.PLACEMENT_SEARCH_QUANTUM_NODES == 16
    assert placement_domain.DEFAULT_NODE_BUDGET == 50_000
    assert placement_domain.CONSTRUCTIVE_SKELETON_COMPLETION_LIMIT == 2
