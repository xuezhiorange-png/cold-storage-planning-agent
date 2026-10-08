"""R2 certificates and analytic negative coverage, independent of event completeness."""

import inspect
from dataclasses import replace
from itertools import product

import pytest

from cold_storage.modules.layout.domain import conditional_metric_support as c
from cold_storage.modules.layout.domain.authority_shapes import (
    AuthoritativeZoneShapeV1 as Shape,
)
from cold_storage.modules.layout.domain.metric_interface_reservation import (
    event_origins,
    face_origins,
    rectangle_at,
)
from cold_storage.modules.layout.domain.metric_reservation_consumption import (
    build_runtime_domain,
)
from cold_storage.modules.layout.domain.site_geometry import (
    rectangles_overlap,
    rectangles_share_positive_edge,
)

S = Shape(1, 1, 0)
B = ((0, 0), (4, 0), (4, 4), (0, 4))


def rect(role, x, y, shape=S):
    return rectangle_at(role, (x, y), shape)


def query(edges=(("a", "b"),), *, static_cap=256, dynamic_cap=256, intent=lambda p: True):
    domains = tuple(
        build_runtime_domain("edge:" + ":".join(e), e, ((S,), (S,)), B, ()) for e in edges
    )

    def origins(role, shape, placed):
        values = list(event_origins(shape, B, ()))
        for a, b in edges:
            other = b if a == role else a if b == role else None
            if other in placed:
                values = list(face_origins(placed[other], shape)) + values
        return tuple(dict.fromkeys(values))

    return c.ConditionalMetricSupportQueryV2(
        domains,
        edges,
        intent,
        shapes={r: (S,) for e in edges for r in e},
        boundary=B,
        obstacles=(),
        origin_provider=origins,
        provenance={"fixture": "integer-authority"},
        static_cap=static_cap,
        dynamic_cap=dynamic_cap,
    )


def test_non_p2_static_pair_can_be_certified():
    q = query()
    p = {"a": rect("a", 1, 1), "b": rect("b", 2, 1)}
    assert not any(s[:2] == (p["a"].bounds_mm, p["b"].bounds_mm) for s in q.domains[0].slots)
    states = q.update(p)
    assert q.consumed(p, states)
    assert states[0].certificate.source == "DIRECT_FINAL"


def test_dynamic_placed_endpoint_support():
    q = query(static_cap=0)
    p = {"a": rect("a", 1, 1)}
    state = q.update(p)[0]
    assert state.status == c.ConditionalSupportStatusV2.SUPPORTED
    assert state.certificate.slot[0] == p["a"].bounds_mm
    assert state.certificate.source == "DYNAMIC_POSITIVE"
    assert q.support_candidates("b", p, (state,))
    assert not q.support_candidates("b", {}, (state,))


def test_unanchored_dynamic_support():
    q = query(static_cap=0)
    state = q.update({})[0]
    assert state.status == c.ConditionalSupportStatusV2.SUPPORTED
    assert state.certificate.source == "DYNAMIC_POSITIVE"
    assert not q.support_candidates("a", {}, (state,))


def test_unknown_does_not_prune():
    q = query(static_cap=0, dynamic_cap=0)
    state = q.update({"a": rect("a", 1, 1)})[0]
    assert state.status == c.ConditionalSupportStatusV2.UNKNOWN
    assert state.negative_certificate is None


def test_unsound_negative_proof_rejected():
    q = query()
    d = q.domains[0]
    p = {"a": rect("a", 1, 1)}
    forged = c.NegativeGeometryCertificateV2(
        d.source_edge_identity,
        q.identity(d.source_edge_identity, p),
        "b",
        "EVENT_ENUMERATION_EMPTY",
        1,
    )
    with pytest.raises(ValueError, match="UNSOUND_OR_STALE"):
        q.verify_negative(forged, d, p)


def test_sound_zero_capacity_prunes_and_unrelated_room_last_slot_blocking():
    q = query()
    p = {"blocker": rect("blocker", 0, 0, Shape(4, 4, 0))}
    state = q.update(p)[0]
    assert state.status == c.ConditionalSupportStatusV2.NONE
    q.verify_negative(state.negative_certificate, q.domains[0], p)
    assert state.negative_certificate.proof_kind == "EMPTY_NECESSARY_ORIGIN_SPACE"


def test_shared_role_multi_edge_compatibility():
    q = query((("a", "b"), ("b", "c")))
    p = {"b": rect("b", 1, 1)}
    states = q.update(p)
    for state in states:
        assert state.status == c.ConditionalSupportStatusV2.SUPPORTED
        cert = state.certificate
        assert cert.slot[cert.roles.index("b")] == p["b"].bounds_mm
        assert not cert.joint_unplaced_role_capacity_proven
    assert all(not s.certificate.joint_unplaced_role_capacity_proven for s in q.update({}))


def test_domain_revision_cursor_invalidation_and_backtrack_state_restoration():
    q = query()
    parent = q.update({})
    p = {"blocker": rect("blocker", 0, 0, Shape(4, 4, 0))}
    child = q.update(p, parent)
    assert child[0].status == c.ConditionalSupportStatusV2.NONE
    sibling = q.update({}, child)
    assert sibling[0].status == c.ConditionalSupportStatusV2.SUPPORTED
    assert sibling[0].domain_identity != child[0].domain_identity
    assert parent[0].status == c.ConditionalSupportStatusV2.SUPPORTED
    with pytest.raises(ValueError, match="STALE"):
        q.verify_negative(child[0].negative_certificate, q.domains[0], {})


def test_no_role_specific_recovery():
    source = inspect.getsource(c)
    assert "office" not in source and "shipping_channel" not in source
    q = query((("a", "b"), ("b", "c"), ("c", "d")))
    assert len(q.update({})) == 3


def test_small_exhaustive_reference_has_no_false_negative():
    q = query(static_cap=0)
    for ax, ay, bx, by in product(range(4), repeat=4):
        p = {"a": rect("a", ax, ay), "blocker": rect("blocker", bx, by)}
        if rectangles_overlap(*p.values()):
            continue
        feasible = any(
            rectangles_share_positive_edge(p["a"], partner)
            and not any(rectangles_overlap(partner, other) for other in p.values())
            for x, y in product(range(4), repeat=2)
            for partner in (rect("b", x, y),)
        )
        state = q.update(p)[0]
        if state.status == c.ConditionalSupportStatusV2.NONE:
            assert not feasible
        if feasible:
            assert state.status != c.ConditionalSupportStatusV2.NONE


def test_necessary_relaxation_box_resource_limit_never_negative():
    assert c.necessary_origin_boxes("b", S, {"x": rect("x", 1, 1)}, B, (), box_cap=0) is None


def test_partial_intent_and_all_placed_must_neighbors():
    q = query((("a", "b"), ("b", "c")))
    p = {"a": rect("a", 0, 0), "c": rect("c", 3, 3)}
    assert q.update(p)[0].status == c.ConditionalSupportStatusV2.NONE
    q = query(intent=lambda p: False)
    assert q.update({})[0].status == c.ConditionalSupportStatusV2.UNKNOWN


def test_representatives_never_define_consumption():
    q = query()
    p = {"a": rect("a", 1, 1), "b": rect("b", 2, 1)}
    before = q.update(p)
    q.domains = tuple(replace(d, summary=replace(d.summary, witnesses=())) for d in q.domains)
    assert q.update(p) == before


def test_support_migration_does_not_lock_geometry():
    q = query()
    parent = q.update({})
    cert = parent[0].certificate
    blocked = cert.slot[0]
    child = q.update({"other": rect("other", *blocked[:2])}, parent)
    assert child[0].status == c.ConditionalSupportStatusV2.SUPPORTED
    assert child[0].certificate.slot != cert.slot
    assert parent[0].certificate == cert


def test_analytic_origin_cover_matches_independent_two_neighbor_enumeration():
    edges = (("left", "target"), ("target", "right"))
    for shape in (S, Shape(2, 1, 0), Shape(1, 2, 0)):
        for lx, ly, rx, ry in product(range(4), repeat=4):
            placed = {"left": rect("left", lx, ly), "right": rect("right", rx, ry)}
            boxes = c.necessary_origin_boxes("target", shape, placed, B, edges)
            assert boxes is not None
            covered = {
                (x, y)
                for x, y in product(range(4), repeat=2)
                if any(a <= x <= r and b <= y <= t for a, b, r, t in boxes)
            }
            reference = {
                (x, y)
                for x in range(5 - shape.world_width_mm)
                for y in range(5 - shape.world_depth_mm)
                for target in (rect("target", x, y, shape),)
                if all(
                    not rectangles_overlap(target, other)
                    and rectangles_share_positive_edge(target, other)
                    for other in placed.values()
                )
            }
            assert covered == reference


def test_query_evaluations_reconcile_by_source():
    q = query(static_cap=0)
    parent = q.update({})
    q.update({"a": rect("a", 1, 1)}, parent)
    q.update({"a": rect("a", 1, 1), "b": rect("b", 2, 1)}, parent)
    for counts in q.diagnostics.by_edge.values():
        assert counts["slot_evaluations"] == sum(
            counts.get(key, 0)
            for key in (
                "direct_pair_evaluations",
                "reuse_evaluations",
                "static_pair_evaluations",
                "dynamic_origin_evaluations",
                "dynamic_pair_evaluations",
            )
        )


def test_sound_zero_capacity_prunes_before_exact_recursion(monkeypatch):
    from tests.unit import test_v222_p1a_metric_reservation_consumption as fixture

    monkeypatch.setattr(fixture, "BOUNDARY", ((0, 0), (1000, 0), (1000, 1000), (0, 1000)))
    result = fixture.small_search(
        monkeypatch,
        fixture.domain(),
        {"shipping_channel": ((0, 0),), "office": ((0, 0),)},
    )
    assert result.solution is None
    assert result.diagnostics.metric_capacity["prunes"] == 1
    assert result.diagnostics.max_placed == 0
    assert result.diagnostics.funnel["office"]["role_attempt_count"] == 0
    assert any(c.get("proved_none", 0) for c in result.diagnostics.metric_support.by_edge.values())
