"""Observational R2 audit; run this script against an independent R2 checkout.

Example: PYTHONPATH=src:. python /path/to/this/script --output /tmp/r2-audit.json
No production predicates, ordering, caps or geometry inputs are replaced.
"""

import argparse
import json
import subprocess
import time
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from cold_storage.modules.layout.application.composition_placement import (
    enumerate_composition_placements,
)
from cold_storage.modules.layout.domain import conditional_metric_support as c
from tests.unit.test_v222_p1a_composition_authority_handoff import _context


def capture(output: Path) -> None:
    start = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, timeout=30).strip()
    assert start == "8c921b0f654d5d00e8664cf19650a278d558a7a0", "REQUIRES_R2_CHECKOUT"
    original_init = c.ConditionalMetricSupportQueryV2.__init__
    original_update = c.ConditionalMetricSupportQueryV2.update
    records = []

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.audit_handoff = kwargs["provenance"]["handoff_hash"]

    def update(self, placed, parent=()):
        before = {k: dict(v) for k, v in self.diagnostics.by_edge.items()}
        states = original_update(self, placed, parent)
        admitted = not any(s.status == c.ConditionalSupportStatusV2.NONE for s in states)
        for domain, state in zip(self.domains, states, strict=True):
            if state.status != c.ConditionalSupportStatusV2.UNKNOWN:
                continue
            edge = domain.source_edge_identity
            after = self.diagnostics.by_edge[edge]
            delta = {k: v - before.get(edge, {}).get(k, 0) for k, v in after.items()}
            dynamic = delta.get("dynamic_origin_evaluations", 0) + delta.get(
                "dynamic_pair_evaluations", 0
            )
            records.append(
                {
                    "edge": edge,
                    "composition": self.audit_handoff,
                    "depth": len(placed),
                    "fixed": sum(r in placed for r in domain.summary.roles),
                    "reason": "POSITIVE_PROBE_CAP_EXHAUSTED"
                    if dynamic >= self.dynamic_cap
                    else "DYNAMIC_ORIGIN_DOMAIN_INCOMPLETE",
                    "static_domain_not_covered": len(domain.candidates(placed)) == 0,
                    "fixed_endpoint_multi_neighbor_constraint": any(
                        r not in placed
                        and sum(
                            r in e and any(n in placed for n in e if n != r)
                            for e in self.must_edges
                        )
                        > 1
                        for r in domain.summary.roles
                    ),
                    "accepted_partial": admitted,
                    "evaluations": delta,
                    "placed": {r: p.bounds_mm for r, p in placed.items()},
                }
            )
        return states

    started = time.perf_counter()
    with (
        patch.object(c.ConditionalMetricSupportQueryV2, "__init__", init),
        patch.object(c.ConditionalMetricSupportQueryV2, "update", update),
    ):
        result = enumerate_composition_placements(*_context())
    report = {
        "records": records,
        "placement": result.placements.to_dict(),
        "seconds": time.perf_counter() - started,
        "unknown_by_edge": dict(Counter(r["edge"] for r in records)),
        "unknown_by_composition": dict(Counter(r["composition"] for r in records)),
        "unknown_by_depth": dict(Counter(r["depth"] for r in records)),
        "unknown_by_reason": dict(Counter(r["reason"] for r in records)),
        "unknown_with_fixed_endpoint_count": sum(r["fixed"] > 0 for r in records),
        "unknown_with_both_endpoints_unplaced_count": sum(r["fixed"] == 0 for r in records),
    }
    output.write_text(json.dumps(report, default=str))
    print(json.dumps({k: v for k, v in report.items() if k not in {"records", "placement"}}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    capture(parser.parse_args().output)
