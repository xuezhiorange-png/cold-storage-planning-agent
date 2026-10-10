# V2.2.2 P1A — Structural hard-interface reservation P0

Task: V2_2_2_P1A_STRUCTURAL_HARD_INTERFACE_RESERVATION_P0

Baseline: `a0ef560de778770e4c26c4d027a239afe78eeadd` (clean main only).
Branch: `codex/v2.2.2-p1a-structural-hard-interface-reservation-p0`.

## Diagnostic input, not inherited implementation

PR #306 remains a frozen Draft at
`4823fae99958eefddd32dc0afe42b729df00f415`. CR1–CR7 diagnosed the
11/12 construction failure. The subsequent zero-modification audit found
11/11 Shipping physical survivors with zero hard-valid Office attachments.
StructuralComposition did not expose/preserve the Office–Shipping cross-group
hard interface. These are diagnostic inputs; no #306 commit or runtime search
implementation was cherry-picked or copied. This is not CR8.

## P0 delivery

`MandatoryHardInterfaceIntentV1` projects every current MUST edge from
`charles-v22-process-flow@1.1.0` into each plan and placement handoff.
There are currently 7 interfaces: 4 intra-group and 3 cross-group. Coverage is
exact set equality, with deterministic source-authority order. Interfaces carry
role/group/band/domain references and graph/edge provenance, not geometry.

Office remains PERSONNEL_GROUP / PERSONNEL_INGRESS_DOMAIN. Shipping remains
FINISHED_SIDE_GROUP / SHIPPING_TRUCK_INTERFACE_DOMAIN. Their interface is
CROSS_GROUP / POSITIVE_SHARED_EDGE. The other cross-group interfaces are
Primary Precooling–Sorting and Coating–Finished Goods.

Engineering/geometry authority is false. The existing graph remains sole hard
authority. Preservation of at least one feasible attachment path is an explicit
future-phase obligation; P0 neither computes it nor asserts feasibility.

See [ADR-050](../architecture/ADR-050-structural-hard-interface-projection.md).

## Validation and evidence

83 focused/S1/S2/architecture tests passed locally. Tests cover missing and extra
edges, same/reversed duplicates, unknown roles, incorrect group/band/domain
references, authority weakening, deterministic serialization and unchanged
functional ownership. Historical S1/S2 evidence remains unmodified; tests
compare its exact pre-addition field projection. New full contract hashes are
recorded separately.

[Contract evidence](evidence/v2_2_2_p1a_structural_hard_interface_reservation_p0/xinzhao_mandatory_hard_interface_contract.json)
records all 6 canonical compositions, their interfaces, Plan→Handoff equality,
source graph/ownership maps and two equal deterministic build hashes.
No full exact-placement search or engineering validation was performed as P0
acceptance. Exact-head CI is reported in the PR and final receipt.

## Frozen scope

Process graph, dimensions, Access, Packaging STRAIGHT_ONLY, Truck, P2D,
ValidatedSiteGeometry, selector, Tool 7 and exact-placement search are unchanged.
PR #306 is untouched. No geometry recovery or capacity propagation is included.
P1_AUTHORIZED=false; NEXT_PHASE_AUTHORIZED=false. Stop after P0 review delivery.

## Workspace observation

The checkout gate was clean. Unrelated untracked duplicate ` 2.*` files appeared
later and were preserved, not staged or removed. They are not part of this PR.
