"""Proof-first R4 regressions with an independent integer-mm reference."""

import ast
import inspect
from dataclasses import replace
from itertools import product

import pytest

from cold_storage.modules.layout.domain import joint_metric_capacity as joint
from cold_storage.modules.layout.domain.conditional_metric_support import (
    ConditionalSupportStatusV2 as Status,
)
from cold_storage.modules.layout.domain.site_geometry import (
    rectangle_inside_polygon,
    rectangle_intersects_closed_obstacle,
    rectangles_overlap,
    rectangles_share_positive_edge,
)
from tests.unit.test_v222_p1a_conditional_metric_support_r2 import S, query, rect


def engine(q, cap=256):
    return joint.JointMetricCapacityQueryV1(q, graph_identity="fixture-graph", evaluation_cap=cap)


def reference(q, fixed):
    roles = sorted(q.shapes)
    missing = [r for r in roles if r not in fixed]
    for coords in product(product(range(4), repeat=2), repeat=len(missing)):
        p = {**fixed, **{r: rect(r, *xy) for r, xy in zip(missing, coords, strict=True)}}
        rooms = list(p.values())
        if not all(rectangle_inside_polygon(v, q.boundary) for v in rooms):
            continue
        if any(rectangle_intersects_closed_obstacle(v, o) for v in rooms for o in q.obstacles):
            continue
        if any(rectangles_overlap(a, b) for i, a in enumerate(rooms) for b in rooms[i + 1 :]):
            continue
        if all(
            rectangles_share_positive_edge(p[a], p[b]) for a, b in q.must_edges
        ) and q.intent_possible(p):
            yield p


def test_dynamic_origin_coverage_mixed_corner_not_in_r3_diagonal_events():
    q = query(
        (("a", "b"),),
        static_cap=0,
        dynamic_cap=0,
        intent=lambda p: all(
            r not in p or p[r].bounds_mm[:2] == xy for r, xy in (("a", (0, 3)), ("b", (1, 3)))
        ),
    )
    q.origin_provider = lambda r, s, p: ()
    witnesses = list(reference(q, {}))
    assert witnesses
    e = engine(q)
    state = e.update({}, q.update({}))[0]
    assert state.status == Status.SUPPORTED
    assert e.verify(state.certificate, {})


@pytest.mark.parametrize("end", [(3, 0), (1, 2), (3, 3)])
def test_multineighbor_propagation_never_loses_independent_integer_witness(end):
    q = query((("a", "b"), ("b", "c"), ("c", "d")))
    fixed = {"a": rect("a", 0, 0), "d": rect("d", *end)}
    e = engine(q)
    spaces = e.positive_origin_spaces(e.components[0], fixed)
    solutions = list(reference(q, fixed))
    for p in solutions:
        for role in ("b", "c"):
            x, y = p[role].bounds_mm[:2]
            assert any(
                s == S and left <= x <= right and bottom <= y <= top
                for s, (left, bottom, right, top) in spaces[role]
            )
    state = e.update(fixed, q.update(fixed))[0]
    assert not (solutions and state.status == Status.NONE)
    if state.certificate:
        assert e.verify(state.certificate, fixed)


def test_obstacle_space_propagation_is_conservative_and_exact_positive_revalidated():
    q = query((("a", "b"), ("b", "c")))
    q.obstacles = (((1, 1), (2, 1), (2, 2), (1, 2)),)
    e = engine(q)
    spaces = e.positive_origin_spaces(e.components[0], {})
    for p in reference(q, {}):
        for role in q.shapes:
            x, y = p[role].bounds_mm[:2]
            assert any(
                s == S and left <= x <= right and bottom <= y <= top
                for s, (left, bottom, right, top) in spaces[role]
            )
    state = e.update({}, q.update({}))[0]
    assert state.certificate and e.verify(state.certificate, {})
    assert not e.verify(replace(state.certificate, authority_identity="forged"), {})


def test_nonrectangular_obstacle_bbox_is_not_subtracted_as_hard_space():
    q = query((("a", "b"),))
    q.obstacles = (((0, 0), (3, 0), (0, 3)),)
    e = engine(q)
    spaces = e.positive_origin_spaces(e.components[0], {})
    for p in reference(q, {}):
        for role in q.shapes:
            x, y = p[role].bounds_mm[:2]
            assert any(
                left <= x <= right and bottom <= y <= top
                for _, (left, bottom, right, top) in spaces[role]
            )


def test_same_caps_unknown_never_prunes_and_negative_certificate_soundness():
    q = query((("a", "b"), ("b", "c")), static_cap=0, dynamic_cap=0)
    e = engine(q, cap=0)
    assert e.event_cap == 1024
    state = e.update({}, q.update({}))[0]
    assert state.status == Status.UNKNOWN and not state.negative_certificate
    with pytest.raises(ValueError, match="UNSOUND"):
        e.verify_negative(replace(state, status=Status.NONE), {})
    assert engine(q).evaluation_cap == 256


def test_shared_role_consistency_and_graph_extension():
    q = query((("a", "b"), ("b", "c"), ("b", "d")))
    e = engine(q)
    state = e.update({}, q.update({}))[0]
    assert state.status == Status.SUPPORTED
    assert len(state.certificate.assignment) == len(q.shapes) == 4
    assert len({r for r, _, _ in state.certificate.assignment}) == 4
    assert len(state.certificate.hard_edges) == 3
    assert e.verify(state.certificate, {})


def test_domain_revision_parent_and_sibling_isolation(monkeypatch):
    q = query((("a", "b"), ("b", "c")))
    e = engine(q)
    parent = e.update({}, q.update({}))
    saved = parent[0].certificate
    blocker = {"blocker": rect("blocker", 0, 0, type(S)(4, 4, 0))}
    child = e.update(blocker, q.update(blocker), parent)[0]
    assert child.status == Status.NONE
    assert parent[0].certificate == saved
    sibling = e.update({}, q.update({}), parent)[0]
    assert sibling.status == Status.SUPPORTED and e.verify(sibling.certificate, {})
    monkeypatch.setattr(joint, "REVISION", "r4-test-revision")
    assert not e.verify(saved, {})
    assert e.update({}, q.update({}), parent)[0].status == Status.SUPPORTED


def test_no_role_specific_recovery_or_historical_seed_and_frozen_caps():
    source = inspect.getsource(joint)
    assert "office" not in source and "shipping_channel" not in source
    assert "representative_slots" not in source
    assert "32771" not in source and "historical" not in source.lower()
    assert "evaluation_cap: int = 256" in source and "event_cap: int = 1024" in source
    assert all(
        abs(node.value) <= 8192
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant) and type(node.value) is int
    )


def test_strip_coalescing_preserves_exact_integer_union():
    boxes = ((0, 0, 1, 1), (2, 0, 3, 1), (0, 2, 3, 2), (1, 1, 2, 3))
    actual = joint._coalesce_origin_spaces(tuple((S, box) for box in boxes))

    def points(values):
        return {
            (x, y)
            for left, bottom, right, top in values
            for x in range(left, right + 1)
            for y in range(bottom, top + 1)
        }

    assert points(boxes) == points([box for _, box in actual])


def test_evidence_observer_does_not_require_canonical_label_on_control(monkeypatch, tmp_path):
    from tests.evaluation import v222_p1a_joint_unknown_proof_r4_evidence as runner

    class EndDiagnostic(Exception):
        pass

    q = query((("a", "b"),))
    e = engine(q)

    def diagnostic_only(*args):
        assert e.update({}, q.update({}))[0].status == Status.SUPPORTED
        raise EndDiagnostic

    monkeypatch.setattr(runner.protocol, "capture", diagnostic_only)
    baseline = tmp_path / "input.json"
    baseline.write_text("{}")
    with pytest.raises(EndDiagnostic):
        runner.capture(baseline, baseline, tmp_path / "unused.json", False)


def test_evidence_observer_preserves_existing_public_api_signature(monkeypatch, tmp_path):
    from tests.evaluation import v222_p1a_joint_unknown_proof_r4_evidence as runner

    class EndDiagnostic(Exception):
        pass

    def diagnostic_only(*args):
        assert tuple(
            inspect.signature(runner.protocol.app.enumerate_composition_placements).parameters
        ) == ("canonical_zone_plan", "p1_handoff", "site_geometry", "node_budget")
        raise EndDiagnostic

    monkeypatch.setattr(runner.protocol, "capture", diagnostic_only)
    baseline = tmp_path / "input.json"
    baseline.write_text("{}")
    with pytest.raises(EndDiagnostic):
        runner.capture(baseline, baseline, tmp_path / "unused.json", False)
