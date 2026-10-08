"""Compare positive probes on real START UNKNOWN states; not placement replay.

This diagnostic passes graph/edge metadata only because probe/verify do not
enumerate P2 slots. It makes no runtime-domain parity claim. The full production
replays separately build and verify all seven actual P2 runtime domains.
"""

import argparse
import json
from collections import Counter
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from cold_storage.modules.layout.application.layout_authority_binding import bind_layout_authority
from cold_storage.modules.layout.application.structural_composition import (
    build_structural_compositions,
)
from cold_storage.modules.layout.domain import composition_placement as exact
from cold_storage.modules.layout.domain.authority_shapes import AuthoritativeZoneShapeV1 as Shape
from cold_storage.modules.layout.domain.conditional_metric_support import (
    ConditionalMetricSupportQueryV2,
)
from cold_storage.modules.layout.domain.dimensioning import canonical_hash, canonical_json
from cold_storage.modules.layout.domain.joint_metric_capacity import JointMetricCapacityQueryV1
from cold_storage.modules.layout.domain.site_geometry import PlacedRectangleV1, normalize_polygon
from cold_storage.modules.layout.domain.validated_site_obstacles import (
    validated_hard_obstacle_polygons,
)
from tests.evaluation.v222_p1a_joint_metric_capacity_r3_evidence import independent_verify
from tests.unit.test_v222_p1a_composition_authority_handoff import _context

parser = argparse.ArgumentParser()
parser.add_argument("--audit", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
arguments = parser.parse_args()
start = json.loads(arguments.audit.read_text())
args = _context()
binding = bind_layout_authority(*args)
composition = build_structural_compositions(*args)
handoffs = {h.canonical_result_hash: h for h in composition.placement_handoffs}
payload = args[2].to_dict()
boundary = normalize_polygon(
    payload["site"]["effective_buildable_boundary"], allow_numeric_string=True
)
obstacles = validated_hard_obstacle_polygons(payload)
base_shapes = {
    r: exact._canonical_construction_shapes(v)
    for r, v in exact._authority_shapes(binding.dimension_authorities, boundary, obstacles).items()
}
edges = exact.process_graph().must_adjacencies
cursor = -1
rows = []
counts = Counter()
samples = {}
for index, record in enumerate(start["records"]):
    handoff = handoffs[record["provenance"]["handoff_hash"]]
    if not record["placed"]:
        cursor = next(
            i
            for i in range(cursor + 1, len(start["placement"]["search_attempts"]))
            if start["placement"]["search_attempts"][i]["composition_identity"]
            == handoff.composition_identity
        )
    bank = record["bank"]
    shapes = exact._composition_shape_order(handoff, base_shapes, bank)
    assert {r: [asdict(s) for s in v] for r, v in shapes.items()} == record["shapes"]
    domains = exact._domain_arrangement(handoff, bank, boundary, binding.dimension_authorities)
    faces = exact._domain_faces(handoff, bank)

    def origins(role, shape, placed, handoff=handoff, domains=domains, bank=bank):
        return tuple(
            dict.fromkeys(
                (
                    *exact._domain_derived_anchors(
                        role, shape, handoff, domains, bank, placed, boundary, obstacles
                    ),
                    *exact._generic_fallback_anchors(role, shape, placed, boundary, obstacles),
                )
            )
        )

    metadata = tuple(
        SimpleNamespace(
            source_edge_identity=i.source_edge_identity,
            summary=SimpleNamespace(roles=(i.endpoint_a_role, i.endpoint_b_role)),
        )
        for i in handoff.mandatory_hard_interfaces
    )
    q = ConditionalMetricSupportQueryV2(
        metadata,
        edges,
        lambda p, handoff=handoff, faces=faces: exact._partial_intent_possible(handoff, p, faces),
        shapes=shapes,
        boundary=boundary,
        obstacles=obstacles,
        origin_provider=origins,
        provenance=record["provenance"],
    )
    e = JointMetricCapacityQueryV1(q, graph_identity=exact.process_graph().identity)
    placed = {
        r: PlacedRectangleV1(
            **{
                k: Decimal(v) if k in ("x", "y", "width_m", "depth_m") else v
                for k, v in data.items()
            }
        )
        for r, data in record["placed"].items()
    }
    assert (
        canonical_hash(
            (
                "connected-hard-component-positive-proof@1.0.0",
                exact.process_graph().identity,
                e.components[0],
                q.identity("joint", placed),
            )
        )
        == record["states"][0]["domain_identity"]
    )
    hints = []
    by_role = {}
    conflicts = Counter()
    for state in record["pairwise"]:
        cert = state["certificate"]
        if cert is None:
            continue
        for role, bounds, shape in zip(
            cert["roles"], cert["slot"][:2], cert["slot"][2:], strict=True
        ):
            value = (tuple(bounds), Shape(**shape))
            if role in by_role and by_role[role] != value:
                conflicts[
                    "SHAPE_DISAGREEMENT"
                    if by_role[role][1] != value[1]
                    else "COORDINATE_DISAGREEMENT"
                ] += 1
            by_role[role] = value
            hints.append((role, *value))
    old_assignment = tuple(
        (role, tuple(bounds), Shape(**shape)) for role, bounds, shape in record["old_assignment"]
    )
    cert, checked, reason = e.probe(e.components[0], placed, old_assignment + tuple(hints))
    if cert:
        assert independent_verify(e, cert, placed)
    row = {
        "index": index,
        "attempt": cursor + 1,
        "composition": handoff.composition_identity,
        "bank": bank,
        "depth": len(placed),
        "admitted": record["admitted"],
        "r3_reason": record["states"][0]["reason"],
        "r3_work": record["work"],
        "pairwise_witness_disagreements": dict(conflicts),
        "r4_reason": reason,
        "r4_checked": checked,
        "r4_work": dict(e.counts),
        "classification": "WITNESS_EXISTS_NOT_FOUND_BY_R3"
        if cert
        else "UNRESOLVED_NOT_PROVED_INFEASIBLE",
    }
    rows.append(row)
    counts[row["classification"]] += 1
    if cert and record["admitted"]:
        counts["ACCEPTED_UNKNOWN_WITH_NEW_WITNESS"] += 1
    key = str((row["classification"], row["r3_reason"], row["composition"], row["depth"]))
    samples.setdefault(
        key, {**row, "placed": record["placed"], "certificate": cert.proof() if cert else None}
    )
    if index % 25 == 0:
        print("R4_PARTIAL_PROBE", index, dict(counts), flush=True)
arguments.output.write_text(
    canonical_json(
        {
            "scope": "POSITIVE_PROBE_DIAGNOSTIC_WITH_ACTUAL_START_PARTIALS_NO_PARENT_CACHE",
            "counts": dict(counts),
            "rows": rows,
            "representatives": samples,
        }
    )
)
print("R4_PARTIAL_PROBE_COMPLETE", dict(counts), flush=True)
