# ADR-050: Project hard MUST interfaces into structural composition

Status: proposed; P0 projection and authorized P1 topological reservation.
P2 metric realization is not authorized.

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
or recover a layout. P1 below consumes the obligation at the topology layer only.

## P1: structural attachment slots and capacity gate

Every projected hard interface receives exactly one immutable
`MandatoryInterfaceReservationV1`. The source-edge identity is the slot identity;
it references the existing graph and never creates a new edge. Endpoint group,
band and domain ownership is copied as provenance, not reassigned. Hosts are
typed references to actual principal bands, peripheral domains or (only as a
fallback) functional-group structural context. No dimensions or coordinates are
stored. Required attachment remains `POSITIVE_SHARED_EDGE`, without invented
edge-length, door-width or portal metrics.

Reservation derivation is generic and deterministic:

1. A common band hosts an intra-container slot, even across functional groups.
2. Consecutive LINEAR process bands or CENTRAL organizer/face contacts host
   adjacent-band slots; these follow existing sequence/organizer topology.
3. Otherwise prefer endpoint domains, then bands, then functional context.
   An existing cross-group hard interface with no established container contact
   becomes an explicit mandatory bridge, not an assertion of existing contact.
   Same-group domain/domain and band/domain attachments retain distinct kinds.

All three existing families accept mandatory bridges as construction obligations.
This is a topological modeling decision, **not** evidence of physical room
capacity. Office/Shipping naturally binds PERSONNEL_INGRESS_DOMAIN to
SHIPPING_TRUCK_INTERFACE_DOMAIN in every family, including SPINE. Neither role
changes functional or domain ownership. No Office-specific generation branch
exists. Adding an authority MUST produces an additional slot automatically.

Each interface gets a `MandatoryInterfaceCapacityAssessmentV1`:
`PASS_STRUCTURAL_CAPACITY_RESERVED` requires a unique exact-provenance slot,
real hosts and an accepting family policy. An absent host or prohibited kind is
`PROVED_NO_STRUCTURAL_RESERVATION_CAPACITY`. Missing/duplicate/drifting slots
are structural contract rejection diagnostics, not physical infeasibility
proofs. Unknown family policy is `UNKNOWN_STRUCTURAL_CAPACITY`, never PASS.
The aggregate gate rejects any negative or malformed coverage, otherwise
propagates UNKNOWN, otherwise permits `PASS_TO_EXACT_PLACEMENT`.

Plan and Handoff independently recompute reservations and assessments, enforcing
source-edge 1:1 coverage, authority order and gate aggregate. Handoff includes the
same frozen reservation tuple and typed gate (which contains all assessments).
It cannot legally omit the downstream consumption obligation. This phase does
not implement DFS/metric consumption; P2 must realize and preserve these slots.

### Signature policy: DERIVED_NOT_INCLUDED

Reservations are a deterministic projection of the existing authority plus
already-signed band/domain/family topology. They add no selectable topology or
diversity dimension. Keep existing composition identities and signatures. Any
future selectable reservation topology needs a fresh signature/version decision.
Current Plan/Handoff canonical serialization hashes intentionally change.

### Schema audit: PRESERVE_INTERNAL_ADDITIVE

Repository-wide symbol/identity/serialization usage was inspected in backend,
scripts, frontend and tests. Production construction is in
`layout/application/structural_composition.py`. Consumers are internal typed
objects in domain/application composition placement. The public replay boundary
rebuilds the server composition from upstream inputs and compares entire typed
handoffs and canonical hashes; it does not deserialize client-supplied historical
Plan/Handoff JSON. No strict external schema or persisted Plan/Handoff decoder
was found. Therefore retain Plan 2.0.0 / Handoff 1.0.0, following P0's internal
additive convention. New Python fields are required and cannot default to
silently regenerated slots. Historical JSON is evidence, not runtime input.

Historical S1/S2/P0 evidence stays immutable. Regression/evidence capture removes
only P1 additive fields to check old P0 plan/handoff hashes; S1/S2 projections
also remove P0 interfaces. Never relabel historical hashes as current hashes.
Canonical result/Plan/Handoff hashes change, not structural diversity identity.

### Non-claims and next boundary

`STRUCTURAL_CAPACITY_GATE_SCOPE=TOPOLOGICAL_RESERVATION_ONLY`.
`METRIC_GEOMETRIC_ATTACHMENT_CAPACITY_PROVEN=false`.
`COMPLETE_LAYOUT_PROVEN=false`.

P1 runs no full placement, Access, Truck or P2D replay. The exact-placement
algorithm and all engineering authorities stay untouched. Existing CI regression
tests remain required; they do not constitute a new production layout proof.
Future concept: METRIC_INTERFACE_RESERVATION_REALIZATION. P2 is not authorized.

## Verification

Focused tests cover full authority equality, 7/4/3 current classification,
Office/Shipping ownership, handoff preservation, coordinate-free serialization,
invalid contracts and deterministic canonical hashes. Lightweight canonical
Xinzhao projection runs twice without entering exact placement.
