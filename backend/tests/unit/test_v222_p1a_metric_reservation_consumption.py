"""Complete-domain support, never a sampled slot or role-specific reservation."""

from dataclasses import replace
from hashlib import sha256
from itertools import product
from types import MappingProxyType

import pytest

from cold_storage.modules.layout.domain.authority_shapes import AuthoritativeZoneShapeV1 as Shape
from cold_storage.modules.layout.domain.metric_interface_reservation import (
    PairwiseMetricDomainResultV1,
    evaluate_pair_domain,
    rectangle_at,
)
from cold_storage.modules.layout.domain.metric_reservation_consumption import (
    MetricReservationSupportQueryV1 as Query,
)
from cold_storage.modules.layout.domain.metric_reservation_consumption import (
    MetricSupportStatusV1 as Status,
)
from cold_storage.modules.layout.domain.metric_reservation_consumption import (
    RuntimeMetricReservationDomainV1 as Domain,
)
from cold_storage.modules.layout.domain.metric_reservation_consumption import (
    _edge,
    _overlap,
    build_runtime_domain,
)
from cold_storage.modules.layout.domain.site_geometry import (
    rectangles_overlap,
    rectangles_share_positive_edge,
)

SHAPE = Shape(1000, 1000, 0)
BOUNDARY = ((0, 0), (10000, 0), (10000, 10000), (0, 10000))


def rect(role, x, y):
    return rectangle_at(role, (x, y), SHAPE)


def domain(roles=("office", "shipping_channel"), origins=(((0, 0), (1000, 0)),), complete=True):
    slots = tuple(
        (rect(roles[0], *a).bounds_mm, rect(roles[1], *b).bounds_mm, SHAPE, SHAPE)
        for a, b in origins
    )
    digest = sha256()
    indexes = ({}, {})
    for index, (a, b, _, _) in enumerate(slots):
        digest.update((str((a, b)) + "\n").encode("ascii"))
        for i, bounds in enumerate((a, b)):
            indexes[i].setdefault(bounds, []).append(index)
    summary = PairwiseMetricDomainResultV1(
        roles,
        "small-declared-domain",
        complete,
        len(slots),
        len(slots),
        "sha256:" + digest.hexdigest(),
        (),
        (),
        (),
        None,
    )
    return Domain(
        "edge:" + ":".join(roles),
        summary,
        slots,
        tuple(MappingProxyType({k: tuple(v) for k, v in ix.items()}) for ix in indexes),
    )


def query(d=None, intent=lambda placed: True, edges=None):
    d = d or domain()
    return Query((d,), edges or (d.summary.roles,), intent)


def test_runtime_domain_p2_digest_parity():
    runtime = build_runtime_domain("edge:a:b", ("a", "b"), ((SHAPE,), (SHAPE,)), BOUNDARY, ())
    p2 = evaluate_pair_domain(("a", "b"), ((SHAPE,), (SHAPE,)), BOUNDARY, ())
    assert runtime.summary == p2
    assert len(runtime.slots) == p2.valid_count
    with pytest.raises(ValueError, match="PARITY"):
        replace(runtime, slots=runtime.slots[:-1])


def test_representative_slot_sample_not_used_for_consumption():
    d = domain(origins=(((0, 0), (1000, 0)), ((0, 4000), (1000, 4000))))
    altered = replace(d, summary=replace(d.summary, witnesses=(), orientations=()))
    placed = {"unrelated": rect("unrelated", 0, 0)}
    assert query(d).update(placed) == query(altered).update(placed)
    assert query(altered).update(placed)[0].support_index == 1


def test_office_shipping_zero_capacity_prunes_shipping():
    q = query()
    parent = q.update({})
    child = q.update(
        {"shipping_channel": rect("shipping_channel", 1000, 0), "blocker": rect("blocker", 0, 0)},
        parent,
    )
    assert child[0].status == Status.NONE


def test_office_shipping_positive_capacity_preserves_branch():
    q = query()
    placed = {"shipping_channel": rect("shipping_channel", 1000, 0)}
    states = q.update(placed, q.update({}))
    assert states[0].status == Status.SUPPORTED
    assert q.support_candidates("office", placed, states) == ((SHAPE, (0, 0)),)
    assert q.support_candidates("office", {}, q.update({})) == ()


def test_unrelated_room_cannot_consume_last_interface_slot():
    q = query()
    assert q.update({"other": rect("other", 0, 0)}, q.update({}))[0].status == Status.NONE


def test_support_migrates_without_hard_lock_and_backtrack_restores_parent():
    q = query(domain(origins=(((0, 0), (1000, 0)), ((0, 4000), (1000, 4000)))))
    parent = q.update({})
    child = q.update({"other": rect("other", 0, 0)}, parent)
    assert child[0].support_index == 1
    assert parent[0].support_index == 0
    sibling = q.update({"other": rect("other", 0, 4000)}, parent)
    assert sibling[0].support_index == 0 and sibling[0].support_reused
    assert q.diagnostics.by_edge[q.domains[0].source_edge_identity]["migrations"] == 1


def test_placed_endpoint_exact_slot_match():
    q = query(domain(origins=(((0, 0), (1000, 0)), ((0, 4000), (1000, 4000)))))
    placed = {"shipping_channel": rect("shipping_channel", 1000, 4000)}
    states = q.update(placed, q.update({}))
    assert states[0].support_index == 1
    assert q.domains[0].slots[1][1] == placed["shipping_channel"].bounds_mm


def test_final_pair_outside_p2_domain_rejected():
    q = query()
    placed = {
        "office": rect("office", 0, 3000),
        "shipping_channel": rect("shipping_channel", 1000, 3000),
    }
    assert rectangles_share_positive_edge(*placed.values())
    states = q.update(placed)
    assert states[0].status == Status.NONE and not q.consumed(placed, states)


def test_multi_edge_shared_role_intersection():
    a = domain()
    b = domain(("finished_goods_room", "shipping_channel"), (((2000, 0), (1000, 0)),))
    q = Query((a, b), (a.summary.roles, b.summary.roles), lambda placed: True)
    placed = {
        "shipping_channel": rect("shipping_channel", 1000, 0),
        "other": rect("other", 2000, 0),
    }
    states = q.update(placed)
    assert [s.status for s in states] == [Status.SUPPORTED, Status.NONE]


def test_metric_slot_composition_intent_compatibility():
    q = query(intent=lambda placed: placed["office"].bounds_mm[1] > 0)
    assert q.update({})[0].status == Status.NONE


def test_metric_support_all_placed_must_neighbors():
    q = query(edges=(("office", "shipping_channel"), ("office", "another")))
    assert q.update({"another": rect("another", 4000, 4000)})[0].status == Status.NONE
    assert q.update({"another": rect("another", 0, 1000)})[0].status == Status.SUPPORTED


def test_unknown_metric_support_does_not_prune():
    q = query(domain(complete=False))
    states = q.update({"other": rect("other", 0, 0)})
    assert states[0].status == Status.UNKNOWN
    assert all(s.status != Status.NONE for s in states)


def test_support_query_no_false_negative_exhaustive_small_branches():
    d = build_runtime_domain("edge:a:b", ("a", "b"), ((SHAPE,), (SHAPE,)), BOUNDARY, ())
    q = query(d)
    parent = q.update({})
    for x, y in product((0, 1000, 4000, 9000), repeat=2):
        placed = {"other": rect("other", x, y)}
        child = q.update(placed, parent)
        expected = any(q.compatible(d, i, placed) for i in range(len(d.slots)))
        assert (child[0].status == Status.SUPPORTED) == expected
        for role in ("a", "b"):
            for bounds in list(d.endpoint_indexes[d.summary.roles.index(role)])[:8]:
                extended = {**placed, role: rect(role, *bounds[:2])}
                grandchild = q.update(extended, child)
                expected = any(q.compatible(d, i, extended) for i in range(len(d.slots)))
                assert (grandchild[0].status == Status.SUPPORTED) == expected


def test_integer_predicates_identical_to_existing_exact_relations():
    a = rect("a", 1000, 1000)
    for x, y in product((0, 1, 999, 1000, 1999, 2000, 2001), repeat=2):
        b = rect("b", x, y)
        assert _edge(a.bounds_mm, b.bounds_mm) == rectangles_share_positive_edge(a, b)
        assert _overlap(a.bounds_mm, b.bounds_mm) == rectangles_overlap(a, b)


def test_complete_candidate_all_reservations_consumed():
    q = query()
    placed = {"office": rect("office", 0, 0), "shipping_channel": rect("shipping_channel", 1000, 0)}
    states = q.update(placed)
    assert q.consumed(placed, states)
    assert q.domains[0].proof(states[0].support_index)["p2_domain_member"]
    domains = tuple(
        domain((f"r{i}", f"r{i + 1}"), ((((i * 1000, 0)), (((i + 1) * 1000, 0))),))
        for i in range(7)
    )
    all_rooms = {f"r{i}": rect(f"r{i}", i * 1000, 0) for i in range(8)}
    all_edges = Query(domains, tuple(d.summary.roles for d in domains), lambda p: True)
    assert len(all_edges.update(all_rooms)) == 7
    assert all_edges.consumed(all_rooms, all_edges.update(all_rooms))


def small_search(monkeypatch, d, origins, rejection=None):
    from types import SimpleNamespace

    from cold_storage.modules.layout.domain import composition_placement as exact
    from cold_storage.modules.layout.domain.adjacency import ZONE_CODES
    from tests.unit.test_v222_p1a_composition_authority_handoff import _result

    handoff = _result().placement_handoffs[0]
    monkeypatch.setattr(exact, "_zone_order", lambda h: ("shipping_channel", "office"))
    monkeypatch.setattr(
        exact,
        "process_graph",
        lambda: SimpleNamespace(identity="fixture-hard-graph", must_adjacencies=(d.summary.roles,)),
    )
    monkeypatch.setattr(exact, "_authority_area_mm2", lambda a: 1)
    monkeypatch.setattr(exact, "_capacity_preflight_status", lambda *a: "UNKNOWN")
    monkeypatch.setattr(exact, "_domain_interval", lambda *a: ("X", None))
    monkeypatch.setattr(exact, "_domain_derived_anchors", lambda role, *a: origins.get(role, ()))
    monkeypatch.setattr(exact, "_generic_fallback_anchors", lambda role, *a: origins.get(role, ()))
    monkeypatch.setattr(exact, "_partial_intent_possible", lambda *a: True)
    monkeypatch.setattr(exact, "_intent_preserved", lambda *a: True)
    monkeypatch.setattr(
        exact, "_shipping_office_seed", lambda *a: pytest.fail("legacy seed called")
    )
    if rejection:
        normal = exact._candidate_rejection
        monkeypatch.setattr(
            exact, "_candidate_rejection", lambda c, *a: rejection(c) or normal(c, *a)
        )
    shapes = {role: (SHAPE,) for role in ZONE_CODES}
    return exact._search_one(
        handoff, shapes, shapes, {r: {} for r in ZONE_CODES}, BOUNDARY, (), (), 1, 50, (d,)
    )


def test_support_candidate_failure_preserves_normal_fallback(monkeypatch):
    d = domain(origins=(((0, 0), (1000, 0)), ((1000, 1000), (1000, 0))))
    outcome = small_search(
        monkeypatch,
        d,
        {"shipping_channel": ((1000, 0),), "office": ((0, 0), (1000, 1000))},
        lambda c: "SITE" if c.zone_code == "office" and c.bounds_mm[:2] == (0, 0) else None,
    )
    assert outcome.solution is not None
    assert outcome.solution["office"].bounds_mm[:2] == (1000, 1000)
    assert outcome.diagnostics.nodes == 3


def test_reservation_support_candidate_dedup_and_node_accounting(monkeypatch):
    outcome = small_search(
        monkeypatch,
        domain(),
        {"shipping_channel": ((1000, 0),), "office": ((0, 0),)},
        lambda c: "SITE" if c.zone_code == "office" else None,
    )
    assert outcome.solution is None
    assert outcome.diagnostics.nodes == 2
    assert (
        sum(f["candidate_rectangle_attempt_count"] for f in outcome.diagnostics.funnel.values())
        == 2
    )


def test_static_absence_is_not_a_zero_capacity_proof(monkeypatch):
    outcome = small_search(
        monkeypatch, domain(), {"shipping_channel": ((4000, 4000),), "office": ((0, 0),)}
    )
    assert outcome.solution is None
    # R2: a missing static endpoint is not a geometric no-capacity proof.
    assert outcome.diagnostics.max_placed == 1
    assert outcome.diagnostics.funnel["office"]["role_attempt_count"] == 1
    assert outcome.diagnostics.metric_capacity["prunes"] == 0
    assert outcome.diagnostics.metric_capacity["accepted_partial_with_pairwise_unknown"] > 0
    # R3's necessary-origin events independently recover a fully verified joint witness.
    assert outcome.diagnostics.metric_capacity["accepted_partial_with_joint_certificate"] > 0


def test_incomplete_runtime_capacity_does_not_prune_recursion(monkeypatch):
    outcome = small_search(
        monkeypatch,
        domain(origins=(), complete=False),
        {"shipping_channel": ((4000, 4000),), "office": ((0, 0),)},
    )
    assert outcome.diagnostics.max_placed == 1
    assert outcome.diagnostics.funnel["office"]["role_attempt_count"] == 1
    assert outcome.diagnostics.metric_capacity["prunes"] == 0


def test_incomplete_static_domain_does_not_prevent_direct_final_certificate(monkeypatch):
    outcome = small_search(
        monkeypatch,
        domain(origins=(), complete=False),
        {"shipping_channel": ((1000, 0),), "office": ((0, 0),)},
    )
    assert outcome.solution is not None
    assert outcome.diagnostics.max_placed == 2
    assert outcome.diagnostics.metric_capacity["prunes"] == 0
    proofs = outcome.diagnostics.metric_capacity["final_consumed"]
    assert len(proofs) == 1
    assert proofs[0]["certificate_source"] == "DIRECT_FINAL"


def test_p3_derives_from_mandatory_reservation_authority(monkeypatch):
    from cold_storage.modules.layout.application.layout_authority_binding import (
        bind_layout_authority,
    )
    from cold_storage.modules.layout.application.structural_composition import (
        build_structural_compositions,
    )
    from cold_storage.modules.layout.domain import metric_reservation_consumption as runtime
    from cold_storage.modules.layout.domain import structural_composition as structural
    from cold_storage.modules.layout.domain.adjacency import process_graph
    from tests.unit.test_v222_p1a_composition_authority_handoff import _context

    graph = process_graph()
    extended = replace(
        graph, must_adjacencies=(*graph.must_adjacencies, ("office", "raw_fruit_buffer"))
    )
    monkeypatch.setattr(structural, "process_graph", lambda: extended)
    context = _context()
    handoffs = build_structural_compositions(*context).placement_handoffs
    binding = bind_layout_authority(*context)
    original = runtime.build_runtime_domain
    calls = []

    def bounded(edge, roles, shapes, boundary, obstacles):
        calls.append(edge)
        return original(edge, roles, ((SHAPE,), (SHAPE,)), BOUNDARY, ())

    monkeypatch.setattr(runtime, "build_runtime_domain", bounded)
    result = runtime.build_metric_runtime_context(
        handoffs, binding.dimension_authorities, context[2].to_dict(), binding.site_geometry_hash
    )
    assert len(calls) == len(set(calls)) == len(result.domains) == 8
    query = Query(result.domains, extended.must_adjacencies, lambda p: True)
    assert len(query.update({})) == 8


def test_no_office_specific_consumption_branch_and_no_representative_sample():
    import inspect

    from cold_storage.modules.layout.domain import composition_placement as exact
    from cold_storage.modules.layout.domain import metric_reservation_consumption as runtime

    source = inspect.getsource(runtime)
    assert '"office"' not in source and '"shipping_channel"' not in source
    assert "representative_slots" not in source
    search = inspect.getsource(exact._search_one)
    assert "_shipping_office_seed(" not in search
    assert "support_query.update(placed, support_states)" in search
    assert search.index("support_query.update(placed, support_states)") < search.index(
        "solution = recurse(index + 1"
    )


def test_real_composition_predicate_filters_site_valid_metric_slot():
    from cold_storage.modules.layout.domain import composition_placement as exact
    from tests.unit.test_v222_p1a_composition_authority_handoff import _result

    handoff = _result().placement_handoffs[0]
    d = domain(("office", "shipping_channel"), (((5000, 5000), (6000, 5000)),))
    # Both pair rectangles are exact site-valid. Office on Sorting's wrong
    # personnel side cannot become composition-compatible support.
    faces = exact._domain_faces(handoff, 1)
    axis, sign = faces["office"]
    sorting = rect(
        "sorting_packaging_room",
        5000 + (sign * 3000 if axis == "X" else 0),
        5000 + (sign * 3000 if axis == "Y" else 0),
    )
    q = Query(
        (d,),
        (d.summary.roles,),
        lambda p: exact._partial_intent_possible(handoff, p, faces),
    )
    assert q.update({"sorting_packaging_room": sorting})[0].status == Status.NONE


def test_invalid_budget_rejected_before_runtime_domain_construction(monkeypatch):
    from cold_storage.modules.layout.application import composition_placement as app

    monkeypatch.setattr(
        app, "build_metric_runtime_context", lambda *a: pytest.fail("invalid request built runtime")
    )
    with pytest.raises(ValueError, match="INVALID_COMPOSITION_PLACEMENT_NODE_BUDGET"):
        app.enumerate_composition_placements({}, {}, None, node_budget=60001)
