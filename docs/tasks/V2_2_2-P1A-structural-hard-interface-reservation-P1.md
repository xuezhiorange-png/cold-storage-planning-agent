# V2.2.2 P1A — structural hard interface reservation P1

Task: `V2_2_2_P1A_STRUCTURAL_HARD_INTERFACE_RESERVATION_P1`.
Mode: `TOPOLOGICAL_MANDATORY_INTERFACE_RESERVATION_AND_CAPACITY_GATE`.
Start: `aa9556369af3917825b5ee56a6011ee3747e74b2` on existing P0 branch / Draft PR #307.
Base main: `a0ef560de778770e4c26c4d027a239afe78eeadd`.
PR #306 remains frozen diagnostic evidence at
`4823fae99958eefddd32dc0afe42b729df00f415`; no code reused or cherry-picked.

## Outcome and semantic boundary

P0 made hard interfaces visible. P1 makes every hard interface reserve a
structural attachment slot before exact placement. P1 still does not prove
site-exact metric feasibility. The only capacity scope is
`TOPOLOGICAL_RESERVATION_ONLY`; metric attachment and complete layout are unproven.

Six canonical compositions contain 42 reservations and 42 assessments, seven
per plan. All six structural gates permit `PASS_TO_EXACT_PLACEMENT`.
Office/Shipping is a generic CROSS_CONTAINER_MANDATORY_BRIDGE in all families,
with PERSONNEL_INGRESS_DOMAIN and SHIPPING_TRUCK_INTERFACE_DOMAIN hosts.
Office stays PERSONNEL_GROUP and Shipping stays FINISHED_SIDE_GROUP.
The 7 existing hard edges, 4 intra-group and 3 cross-group, are unchanged.

## Implementation

- Independent frozen reservation, typed host, assessment and gate contracts.
- Deterministic authority-order derivation from existing band/domain topology.
- Topological family policy explicitly supports mandatory bridges; it does not
  assert existing geometric adjacency or site space.
- Independent Plan/Handoff validation recomputes source-edge coverage,
  provenance, host binding, assessments and aggregate status.
- Missing, extra, reversed duplicate, endpoint drift and authority escalation
  are rejected. Unknown topology never passes.
- Required downstream consumption is explicit but metric/DFS consumption is
  deliberately not implemented in this phase.

Architecture decision: ADR-050 (P1 addendum).
`RESERVATION_SIGNATURE_POLICY=DERIVED_NOT_INCLUDED`.
`SCHEMA_VERSION_DECISION=PRESERVE_INTERNAL_ADDITIVE` after consumer audit.
Stable identities/signatures stay unchanged; current serialization hashes change.

## Verification and reproducibility

Focused tests: `backend/tests/unit/test_v222_p1a_structural_interface_reservations.py`.
Boundary tests: `backend/tests/architecture/test_v222_p1a_reservation_capacity_boundary.py`.
Keep P0, S1, S2 tests green, including immutable historical serialization checks.
Two independent canonical builds compare composition/interface/reservation/
assessment order, gate, serialized handoffs and canonical hashes.

Local focused/P0/S1/S2/boundary selection: 124 passed. Ruff and format pass.
Mypy passes all 397 source files using an isolated cache (the previous local
cache produced a mypy internal error). Frozen dependencies were installed into
an external `/tmp` Python 3.12 environment to avoid slow local dependency reads.
The first full architecture run had 750 passed / 16 skipped / 1 environment
failure: a legacy subprocess used system `python3` without pytest. Its rerun
puts the same locked Python environment on PATH; no source/test workaround was
introduced for that failure. Final terminal outcomes belong to the final receipt.

Lightweight evidence runner (from backend):

```sh
PYTHONPATH=src:. python -m tests.evaluation.v222_p1a_reservation_capacity_evidence
```

This calls the canonical upstream fixture and actual production composition
builder, stopping at Plan/Handoff; no placement/routing entrypoint is invoked.
Evidence: `evidence/v2_2_2_p1a_structural_hard_interface_reservation_p1/xinzhao_structural_interface_reservation_capacity_gate.json`.

The evidence's containing commit binds its final SHA, avoiding an impossible
self-referential embedded commit hash. The final receipt and PR body record the
literal final pushed SHA and both exact-head CI runs. Local test/CI outcomes are
reported separately; terminal exact-head PR and Push success is required.

## Scope freeze

No process graph, dimensions, site, Access, Packaging STRAIGHT_ONLY, Truck, P2D,
candidate selector, Tool 7 or exact-placement search algorithm changed.
P0 MandatoryHardInterfaceIntentV1 semantics/fields remain unchanged. Its
builder integration is additive. The old duplicate quarantine is out of scope
and has not been inspected or changed.

No full 13-attempt production search or Access/Truck/P2D evidence replay was run.
P2 concept only: METRIC_INTERFACE_RESERVATION_REALIZATION.
`P2_AUTHORIZED=false`; `NEXT_PHASE_AUTHORIZED=false`.
No Ready, merge, tag, release or deployment is authorized.
