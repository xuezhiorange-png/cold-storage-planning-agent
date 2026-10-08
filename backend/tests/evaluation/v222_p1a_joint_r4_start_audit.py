"""Read-only START replay using exact committed R3 joint module in a subprocess."""

import argparse
import inspect
import json
import subprocess
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from cold_storage.modules.layout.application import composition_placement as app
from cold_storage.modules.layout.domain import composition_placement as exact
from cold_storage.modules.layout.domain import conditional_metric_support as pair
from cold_storage.modules.layout.domain import joint_metric_capacity as joint
from cold_storage.modules.layout.domain.dimensioning import canonical_json
from tests.evaluation.v222_p1a_joint_metric_capacity_r3_evidence import independent_verify
from tests.unit.test_v222_p1a_composition_authority_handoff import _context

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
arguments = parser.parse_args()
REPO = Path(__file__).resolve().parents[3]
ROOT = arguments.output.parent
source = subprocess.check_output(
    [
        "git",
        "show",
        "9e566603ae217a3eb6a3c2969c0b646756a4df9d:backend/src/cold_storage/modules/layout/domain/joint_metric_capacity.py",
    ],
    cwd=REPO,
)
exec(compile(source, "<committed-R3-joint-module>", "exec"), vars(joint))
exact.JointMetricCapacityQueryV1 = joint.JointMetricCapacityQueryV1
original = joint.JointMetricCapacityQueryV1.update
original_init = pair.ConditionalMetricSupportQueryV2.__init__
records = []
contexts = []


def init(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    self.audit_provenance = kwargs["provenance"]


def observe(self, placed, states, parent=()):
    before = Counter(self.counts)
    old = (parent[0].certificate if parent else None) or self.positive_cache.get(self.components[0])
    result = original(self, placed, states, parent)
    for s in result:
        if s.certificate:
            assert independent_verify(self, s.certificate, placed)
        if s.negative_certificate:
            self.verify_negative(s, placed)  # Same observer work as committed R3 evidence.
    if any(s.status == "UNKNOWN_SUPPORT" for s in result):
        records.append(
            {
                "provenance": self.pairwise.audit_provenance,
                "bank": inspect.getclosurevars(self.pairwise.origin_provider).nonlocals[
                    "bank_sign"
                ],
                "placed": {r: asdict(v) for r, v in placed.items()},
                "shapes": {r: [asdict(s) for s in v] for r, v in self.pairwise.shapes.items()},
                "states": [asdict(s) for s in result if s.status == "UNKNOWN_SUPPORT"],
                "pairwise": [asdict(s) for s in states],
                "old_assignment": asdict(old)["assignment"] if old else [],
                "work": dict(self.counts - before),
                "admitted": bool(placed)
                and not any(s.status == "PROVED_NO_SUPPORT" for s in result),
            }
        )
    if not contexts:
        contexts.extend(self.pairwise.domains)
    return result


t = time.perf_counter()
with (
    patch.object(joint.JointMetricCapacityQueryV1, "update", observe),
    patch.object(pair.ConditionalMetricSupportQueryV2, "__init__", init),
):
    actual = app.enumerate_composition_placements(*_context())
body = json.loads(canonical_json(actual.placements.to_dict()))
expected = json.loads(
    (
        REPO
        / "docs/tasks/evidence/v2_2_2_p1a_p3_joint_metric_capacity_proof_r3"
        / "xinzhao_joint_metric_capacity.json"
    ).read_text()
)["replay_1"]
result = {
    "records": records,
    "placement": body,
    "seconds": time.perf_counter() - t,
    "comparison_differences": [k for k in body if body[k] != expected[k]],
    "source_head": "9e566603ae217a3eb6a3c2969c0b646756a4df9d",
}
arguments.output.write_text(canonical_json(result))
assert not result["comparison_differences"], result["comparison_differences"]
print("R4_START_AUDIT_REPAIRED_COMPLETE", len(records), flush=True)
