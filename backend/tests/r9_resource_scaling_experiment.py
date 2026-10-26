"""Finite new-policy synthetic regression. Old PR316 results are read-only.

Positive and reduced-Handoff-work negative cases each retain the same original
8s Native hard ceiling. No frozen20t Native, MAIN, real Grant or Claim exists.
"""

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from cold_storage.modules.layout.infrastructure.stage_b_route_refinement_resources import (
    StageBResourceBoundRouteRefinementFairSolver,
    _ResourceBoundRouteNative,
)
from tests import r9_route_refinement_experiment as original


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    positive = original.arm(
        args.output / "admitted-one-copy", StageBResourceBoundRouteRefinementFairSolver
    )
    original_refine = _ResourceBoundRouteNative.refine_routes
    original_stream = original.generate_global_composition_candidates
    lowered = []

    def lower_share(self, context, model, solver, record):
        if not lowered:
            spent = context.ledger.model_work + context.ledger.native_host_work - self.work_before
            # Test-only REDUCTION: cannot afford a ~66k preparation, but can
            # still afford the next original room solve and engineering check.
            self.work_share = spent + 65000
            lowered.append(dict(share=self.work_share, spent=spent, remaining=65000))
        yield from original_refine(self, context, model, solver, record)

    def stop_after_next_geometry(*a, **kw):
        gen = original_stream(*a, **kw)
        first = None
        try:
            for result in gen:
                geometry = result["proposal"].get("geometry_hash")
                if first is None and geometry:
                    first = geometry
                yield result
                if geometry and geometry != first:
                    return
        finally:
            gen.close()

    with (
        patch.object(_ResourceBoundRouteNative, "refine_routes", lower_share),
        patch.object(original, "generate_global_composition_candidates", stop_after_next_geometry),
    ):
        negative = original.arm(
            args.output / "skip-copy-continue-rooms", StageBResourceBoundRouteRefinementFairSolver
        )
    (args.output / "summary.json").write_text(
        json.dumps(
            dict(
                positive=positive,
                negative=negative,
                reduced_test_share=lowered,
                old_control_not_rerun=True,
            ),
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
