"""Independent small geometric checks for connected-component proof scope."""

import inspect
from dataclasses import replace
from itertools import product

import pytest

from cold_storage.modules.layout.domain import joint_metric_capacity as joint
from cold_storage.modules.layout.domain.conditional_metric_support import (
    ConditionalSupportStatusV2 as Status,
)
from cold_storage.modules.layout.domain.site_geometry import rectangles_overlap
from tests.unit.test_v222_p1a_conditional_metric_support_r2 import S, query, rect


def assessor(q, *, cap=256):
    return joint.JointMetricCapacityQueryV1(q, graph_identity="fixture-graph", evaluation_cap=cap)


def test_joint_shared_role_certificate_and_role_geometry_identity():
    q = query((("a", "b"), ("b", "c")))
    engine = assessor(q)
    states = engine.update({}, q.update({}))
    assert len(states) == 1 and states[0].status == Status.SUPPORTED
    assert states[0].reason != "JOINT_ASSIGNMENT_UNPROVEN"
    cert = states[0].certificate
    assert cert.coverage_scope == "CONNECTED_HARD_COMPONENT_JOINTLY_SUPPORTED"
    assert len(cert.assignment) == 3
    assert len({r for r, _, _ in cert.assignment}) == 3
    assert len(cert.source_reservation_identities) == 2
    assert engine.verify(cert, {})
    proof = cert.proof()
    assert len(proof["edge_checks"]) == 2
    assert all(e["positive_shared_edge_valid"] for e in proof["edge_checks"])


def test_pairwise_support_is_not_joint_proof_and_multi_edge_conflict():
    def intent(p):
        return not (
            ("a" in p and "b" in p and p["b"].bounds_mm[:2] != (0, 0))
            or ("c" in p and "b" in p and p["b"].bounds_mm[:2] != (3, 3))
        )

    q = query((("a", "b"), ("b", "c")), intent=intent)
    pairwise = q.update({})
    assert all(s.status == Status.SUPPORTED for s in pairwise)
    state = assessor(q).update({}, pairwise)[0]
    assert state.status == Status.UNKNOWN
    assert state.certificate is None
    assert state.reason in {"JOINT_ASSIGNMENT_UNPROVEN", "POSITIVE_PROBE_CAP_EXHAUSTED"}


def test_connected_component_consistency_and_generic_graph_extension():
    for edges in ((("a", "b"),), (("a", "b"), ("b", "c")), (("a", "b"), ("c", "d"))):
        q = query(edges)
        engine = assessor(q)
        states = engine.update({}, q.update({}))
        covered = {e for s in states for e in s.source_reservation_identities}
        assert covered == {d.source_edge_identity for d in q.domains}
        assert all(s.status == Status.SUPPORTED for s in states)
        for s in states:
            assert engine.verify(s.certificate, {})
        # Separate components are not advertised as a globally non-overlapping assignment.
        assert engine.proof_scope == "PER_CONNECTED_HARD_COMPONENT"


def test_unrelated_room_blocks_joint_capacity_with_sound_negative():
    q = query((("a", "b"), ("b", "c")))
    p = {"blocker": rect("blocker", 0, 0, type(S)(4, 4, 0))}
    engine = assessor(q)
    states = engine.update(p, q.update(p))
    assert states[0].status == Status.NONE
    assert states[0].negative_certificate is not None
    engine.verify_negative(states[0], p)
    with pytest.raises(ValueError, match="STALE|UNSOUND"):
        engine.verify_negative(states[0], {})


def test_domain_revision_and_backtrack_state_restoration():
    q = query((("a", "b"), ("b", "c")))
    engine = assessor(q)
    parent = engine.update({}, q.update({}))
    original = parent[0].certificate
    p = {"blocker": rect("blocker", 0, 0, type(S)(4, 4, 0))}
    child = engine.update(p, q.update(p), parent)
    assert child[0].status == Status.NONE
    assert parent[0].certificate == original
    sibling = engine.update({}, q.update({}), parent)
    assert sibling[0].status == Status.SUPPORTED
    assert engine.verify(sibling[0].certificate, {})
    assert not engine.verify(original, p)
    assert engine.identity(parent[0].roles, {}) != engine.identity(parent[0].roles, p)


def test_unknown_never_pruned_and_unsound_negative_rejected():
    q = query((("a", "b"), ("b", "c")), static_cap=0, dynamic_cap=0)
    engine = assessor(q, cap=0)
    state = engine.update({}, q.update({}))[0]
    assert state.status == Status.UNKNOWN and state.negative_certificate is None
    with pytest.raises(ValueError, match="UNSOUND"):
        engine.verify_negative(replace(state, status=Status.NONE), {})


def test_fixed_geometry_and_direct_non_static_final_certificates():
    q = query((("a", "b"), ("b", "c")))
    p = {"a": rect("a", 1, 1), "b": rect("b", 2, 1), "c": rect("c", 3, 1)}
    engine = assessor(q, cap=0)
    state = engine.update(p, q.update(p))[0]
    assert state.status == Status.SUPPORTED
    assert dict((r, b) for r, b, _ in state.certificate.assignment) == {
        r: v.bounds_mm for r, v in p.items()
    }
    assert engine.verify(state.certificate, p)
    forged = replace(state.certificate, assignment=state.certificate.assignment[:-1])
    assert not engine.verify(forged, p)


def test_negative_certificate_soundness_against_independent_small_exhaustive_fixture():
    q = query((("a", "b"), ("b", "c")))
    for x, y in ((0, 0), (1, 1), (3, 3)):
        p = {"blocker": rect("blocker", x, y)}
        reference = False
        for coords in product(product(range(4), repeat=2), repeat=3):
            actual = {r: rect(r, *xy) for r, xy in zip(("a", "b", "c"), coords, strict=True)}
            rooms = [*p.values(), *actual.values()]
            if any(rectangles_overlap(a, b) for i, a in enumerate(rooms) for b in rooms[i + 1 :]):
                continue
            from cold_storage.modules.layout.domain.site_geometry import (
                rectangles_share_positive_edge,
            )

            if all(rectangles_share_positive_edge(actual[a], actual[b]) for a, b in q.must_edges):
                reference = True
                break
        state = assessor(q).update(p, q.update(p))[0]
        assert not (reference and state.status == Status.NONE)
        if state.certificate:
            assert assessor(q).verify(state.certificate, p)


def test_joint_consumer_has_no_role_specific_recovery_or_static_exclusion():
    source = inspect.getsource(joint)
    assert "office" not in source and "shipping_channel" not in source
    assert "representative_slots" not in source
    assert "NO_STATIC_EVENT_DOMAIN_MEMBER" not in source


def test_pairwise_positive_but_joint_area_contradiction_has_covered_negative():
    q = query((("a", "b"), ("b", "c")))
    q.boundary = ((0, 0), (2, 0), (2, 1), (0, 1))
    pairwise = q.update({})
    assert all(s.status == Status.SUPPORTED for s in pairwise)
    engine = assessor(q)
    state = engine.update({}, pairwise)[0]
    assert state.status == Status.NONE
    assert state.negative_certificate.proof_kind == "MINIMUM_COMPONENT_AREA_EXCEEDS_SITE_BBOX"
    engine.verify_negative(state, {})
    # Independent pigeonhole proof: three unit rooms cannot occupy two unit cells.
    assert 3 * S.world_width_mm * S.world_depth_mm > 2


def test_joined_edge_facts_with_non_neighbor_overlap_do_not_certify():
    q = query((("a", "b"), ("b", "c")))
    engine = assessor(q)
    assignment = (("a", (0, 0, 1, 1), S), ("b", (1, 0, 2, 1), S), ("c", (0, 0, 1, 1), S))
    assert engine.certificate(("a", "b", "c"), assignment, {}) is None


def test_relaxed_must_arc_negative_matches_independent_integer_exhaustion():
    from cold_storage.modules.layout.domain.site_geometry import rectangles_share_positive_edge

    q = query((("a", "b"), ("b", "c"), ("c", "d")))
    for end in ((3, 3), (3, 0), (1, 2)):
        fixed = {"a": rect("a", 0, 0), "d": rect("d", *end)}
        witnesses = []
        for b, c in product(product(range(4), repeat=2), repeat=2):
            assignment = {**fixed, "b": rect("b", *b), "c": rect("c", *c)}
            rooms = tuple(assignment.values())
            if any(rectangles_overlap(a, b) for i, a in enumerate(rooms) for b in rooms[i + 1 :]):
                continue
            if all(
                rectangles_share_positive_edge(assignment[a], assignment[b])
                for a, b in q.must_edges
            ):
                witnesses.append(assignment)
        engine = assessor(q)
        state = engine.update(fixed, q.update(fixed))[0]
        assert not (witnesses and state.status == Status.NONE)
        if end == (3, 3):
            assert not witnesses
            assert state.status == Status.NONE
            assert state.reason == "EMPTY_RELAXED_MUST_ARC_SPACE"
            engine.verify_negative(state, fixed)
        if state.certificate:
            assert engine.verify(state.certificate, fixed)


def test_joint_provenance_and_dynamic_event_revision_are_revalidated(monkeypatch):
    q = query((("a", "b"), ("b", "c")))
    engine = assessor(q)
    states = engine.update({}, q.update({}))
    original = states[0].certificate
    for field in (
        "source_graph_identity",
        "authority_identity",
        "partial_geometry_identity",
        "domain_identity",
    ):
        assert not engine.verify(replace(original, **{field: "tampered"}), {})
    assert not engine.verify(replace(original, source_reservation_identities=()), {})
    monkeypatch.setattr(joint, "REVISION", "independent-test-domain-revision")
    assert not engine.verify(original, {})
    following = engine.update({}, q.update({}), states)[0]
    assert following.status == Status.SUPPORTED
    assert following.domain_identity != states[0].domain_identity
    assert engine.verify(following.certificate, {})


def test_joint_positive_cache_migration_does_not_pollute_parent_or_sibling():
    q = query((("a", "b"), ("b", "c")))
    engine = assessor(q)
    parent = engine.update({}, q.update({}))
    original = parent[0].certificate
    _, occupied, shape = original.assignment[0]
    placed = {"blocker": rect("blocker", *occupied[:2], shape)}
    child = engine.update(placed, q.update(placed), parent)
    assert child[0].status == Status.SUPPORTED
    assert child[0].certificate.assignment != original.assignment
    assert engine.verify(child[0].certificate, placed)
    assert parent[0].certificate == original
    sibling = engine.update({}, q.update({}), parent)
    assert sibling[0].status == Status.SUPPORTED
    assert sibling[0].certificate.assignment == original.assignment
    assert engine.verify(sibling[0].certificate, {})
