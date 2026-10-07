# ADR-050: Project hard MUST interfaces into structural composition

Status: proposed; P0 contract only. P1 is not authorized.

## Context

PR #306 is a frozen diagnostic investigation, not this implementation's code
baseline. Its post-CR7 zero-modification audit found that all 11 physical
Shipping survivors had zero hard-valid Office attachments. The existing graph
already requires Office–Shipping adjacency, but functional group/domain
ownership did not expose this cross-group hard interface in the structural
contract. This is not proof of global geometric infeasibility.

## Decision

Project every edge of `process_graph().must_adjacencies`, in authority order,
into immutable `MandatoryHardInterfaceIntentV1` records. Both
`StructuralCompositionPlanV2` and `StructuralCompositionPlacementHandoffV1`
carry the complete typed tuple. The graph remains the sole hard-edge authority.

Each record identifies both roles, functional groups, bands and peripheral
domains, the intra/cross-group scope, graph/edge provenance, and the existing
`POSITIVE_SHARED_EDGE` requirement. Engineering and geometry authority are
explicitly false. The preservation policy is a future-phase obligation, not a
capacity computation, placement reservation or engineering validation result.

Aggregate validation rejects missing/extra/reversed-duplicate edges, order
drift, and incorrect endpoint ownership/provenance. Generation uses the source
graph rather than a second adjacency list or an Office-specific exception.

Functional ownership and spatial hard interfaces are independent: Office stays
in PERSONNEL_GROUP / PERSONNEL_INGRESS_DOMAIN while having a hard cross-group
interface with Shipping in FINISHED_SIDE_GROUP / SHIPPING_TRUCK_INTERFACE_DOMAIN.
Every family exposes every hard MUST edge before exact placement.

## Compatibility and consequences

This is an additive field on the existing plan/handoff contracts. Composition
identities and topology signatures remain unchanged, but canonical hashes of
serialized contracts change. Historical S1/S2 evidence is preserved verbatim;
regression tests reconstruct the pre-P0 field projection to verify its hashes.
New P0 evidence records current hashes separately.

No dimensions or coordinates are copied into an interface. Dimension authority
continues through the existing reference mechanism. No process graph, Access,
Packaging, Truck, P2D, selector, Tool 7 or exact-placement algorithm is changed.
No CR1–CR7 implementation is inherited. P0 does not prove attachment capacity
or recover a layout. A separately authorized P1 would consume the obligation.

## Verification

Focused tests cover full authority equality, 7/4/3 current classification,
Office/Shipping ownership, handoff preservation, coordinate-free serialization,
invalid contracts and deterministic canonical hashes. Lightweight canonical
Xinzhao projection runs twice without entering exact placement.
