from cold_storage.modules.layout.domain.placement import (
    _PlacementSearchStats,
    _quantum_checkpoint,
)


def test_constructive_quantum_is_independent_per_layout_family() -> None:
    stats = _PlacementSearchStats(quantum_node_limit=2)
    stats.current_work_item = {
        "topology": "STRAIGHT_LINEAR_BAND",
        "band_family": "LINEAR_3_BAND",
    }
    assert _quantum_checkpoint(stats) is None

    stats.current_work_item = {
        "topology": "STRAIGHT_LINEAR_BAND",
        "band_family": "CENTRAL_PROCESS_WITH_SIDE_BANKS",
    }
    assert _quantum_checkpoint(stats) is None

    stats.current_work_item = {
        "topology": "STRAIGHT_LINEAR_BAND",
        "band_family": "LINEAR_3_BAND",
    }
    checkpoint = _quantum_checkpoint(stats)

    assert checkpoint is not None
    assert checkpoint.work_item == stats.current_work_item
    assert stats.quantum_nodes_by_layout_family == {
        "STRAIGHT_LINEAR_BAND:LINEAR_3_BAND": 0,
        "STRAIGHT_LINEAR_BAND:CENTRAL_PROCESS_WITH_SIDE_BANKS": 1,
    }
