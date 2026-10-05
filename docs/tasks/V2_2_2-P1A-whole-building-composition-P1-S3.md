# V2.2.2 P1A Reset P1-S3 — composition-constrained exact-placement MVP

## Scope and boundary

P1-S3 is the first attempt to translate a server-replayed
`StructuralCompositionPlacementHandoffV1` into exact room rectangles. The
public application entrypoint accepts the canonical zone plan, complete P1
handoff, and validated site geometry; it rebuilds the six compositions and
their handoffs on the server before invoking the independent composition
placement domain. A caller-provided composition handoff is not accepted.

The attempt is composition-first. It derives finite construction domains for
principal bands and all five peripheral domains before room search. Exact
placement then starts at the process core, materializes support/personnel
domains before extending both ends of the product chain, and preserves the
composition identity, family, process axis/direction, topology, and source
hashes in any emitted candidate. It is not the legacy main-first/tail-after
path.

The fixed MVP search budget is 60,000 placement nodes. The deterministic
family-first scheduler divides this into 20,000 nodes per family and bounded
variant slices; the observed run attempted four exact-placement variants per
family and used the entire budget. Closed no-build boundaries contribute
finite `+/- 1 mm` legal-offset events; no coordinate sweep is used.

## Hard scope

The engine checks only authoritative dimensions, site containment, closed
no-build obstacle clearance, non-overlap, and all seven current MUST
adjacencies. Construction domains organize candidate search and are not hard
engineering authority. Access remains `PENDING_ROUTE_VALIDATION`; Access
routing, Truck validation, P2D, footprint generation, scoring, candidate
selection, Tool 7, and production SVG are not performed or claimed.

The shared layout authority binding is now used by legacy placement and the
composition application boundary. Legacy placement's validation rules are
delegated without changing its search path or public API. Selector and Tool 7
are untouched.

## Observed result

The real Xinzhao authority chain was replayed through zone plan → P1 → validated
site → six compositions → six server-owned handoffs → exact-placement engine.
All three families received a first-round attempt. With 60,000 nodes, no
complete 12-zone composition-native candidate was emitted:

| Family | Attempts | Nodes | Deepest role reached | Search outcome |
| --- | ---: | ---: | --- | --- |
| `LINEAR_BANDED` | 4 | 20,000 | `office` | variant node allocations exhausted |
| `CENTRAL_PROCESS_CORE` | 4 | 20,000 | `finished_goods_room` | variant node allocations exhausted |
| `PROCESS_SPINE_WITH_PERIPHERAL_BANKS` | 4 | 20,000 | `office` | variant node allocations exhausted |

`COMPOSITION_NATIVE_COMPLETE_CANDIDATE_COUNT=0` and
`COMPLETE_12_ZONE_PLACEMENT_COUNT=0`. No legacy fallback was used to claim a
composition result. This is a bounded construction-search failure, not a
global site-infeasibility proof. Access, Truck, and P2D were not reached.

The exact-placement MVP acceptance gate therefore fails. This is the main
implementation attempt; no correction round is started by this task.

## Correction Round 1 — domain-driven anchors and coupled shipping/office

`MAIN_IMPLEMENTATION_RESULT=FAIL` remains the historical result above. The
Owner-authorized CR1 changed only the bounded construction/search semantics; it
did not raise the fixed `60,000` node budget or alter dimensions, site, MUST
adjacency, Access, Truck, P2D, selector, or Tool 7 authority.

CR1 makes each composition's finite band/peripheral domains the primary source
of room anchors, with physical-event generic anchors available only as a
bounded fallback. Packaging, Secondary, and Frozen anchors are derived from
their composition-assigned Processing Core/support faces; personnel anchors
come from the personnel domain. Shipping candidates receive an immediate
necessary Office-interface/MUST feasibility check. Capacity preflights remain
conservative construction diagnostics and are not engineering authority.

The real Xinzhao replay now emits one composition-native complete candidate:

| Family | Attempts | Nodes used | Deepest attempted | Deepest placed | Max placed roles |
| --- | ---: | ---: | --- | --- | ---: |
| `LINEAR_BANDED` | 3 | 10,621 | `office` | `office` | 12 |
| `CENTRAL_PROCESS_CORE` | 4 | 20,000 | `finished_goods_room` | `coating_room` | 6 |
| `PROCESS_SPINE_WITH_PERIPHERAL_BANKS` | 4 | 20,000 | `finished_goods_room` | `coating_room` | 6 |

Total nodes used were `50,621 / 60,000`. The first exact-placement round still
covered all three families. The emitted `LINEAR_BANDED` candidate has 12/12
roles, passes site/dimension/non-overlap checks and all 7/7 existing MUST
adjacencies, and preserves its composition intent. Access remains pending;
Access routing, Truck validation, and P2D were not run. This is an exact
placement hard-subset candidate, not a fully validated layout. No legacy
fallback was used.

The deterministic search reports domain-derived anchors as the primary path.
Bounded generic fallback consumed 606 nodes in Linear and 1,000 in Spine; it
consumed zero nodes in Central. Family totals and the per-attempt/per-role
funnel are in the CR1 evidence. The search stops at its existing finite
composition schedule; unused nodes are not a claim of global infeasibility.

CR1 evidence:
[`xinzhao_composition_exact_placements_cr1.json`](evidence/v2_2_2_p1a_reset_s3/xinzhao_composition_exact_placements_cr1.json),
[`xinzhao_s3_cr1_candidate.svg`](evidence/v2_2_2_p1a_reset_s3/xinzhao_s3_cr1_candidate.svg),
and [`xinzhao_s3_cr1_candidate.png`](evidence/v2_2_2_p1a_reset_s3/xinzhao_s3_cr1_candidate.png).

`CR1_RESULT` is recorded separately below. This remains an S3 MVP; it does not
complete P1. Correction Round 2 is not authorized and is not started.

## Evidence and verification

Machine-readable replay and per-family search evidence:
[`xinzhao_composition_exact_placements.json`](evidence/v2_2_2_p1a_reset_s3/xinzhao_composition_exact_placements.json).

S1 topology signatures remain the S1 evidence values. S2 authority binding and
handoff behavior is covered by the existing S2 tests. P2C deterministic
placement and the legacy validated candidate selection/P1F regressions are
run separately; a passing compatibility regression does not turn the S3
candidate gate into a pass.

## Next-stage boundary

P1-S3 does not complete P1A. A future correction round requires separate
Owner authorization and must address the recorded bounded-search blocker
without weakening dimension, site, overlap, or MUST authority. No Access,
Truck, P2D, selector, or Tool 7 integration is authorized by this task.

```ini
MAIN_IMPLEMENTATION_RESULT=FAIL
TASK_ID=V2_2_2_P1A_WHOLE_BUILDING_COMPOSITION_P1_S3
MODE=COMPOSITION_CONSTRAINED_EXACT_PLACEMENT_MVP
RESULT=FAIL
COMPOSITION_PLACEMENT_NODE_BUDGET=60000
FAMILY_COUNT=3
ALL_FAMILIES_EXACT_PLACEMENT_ATTEMPTED=true
FAMILY_FIRST_EXACT_PLACEMENT_ROUND_COMPLETE=true
COMPOSITION_NATIVE_COMPLETE_CANDIDATE_COUNT=0
COMPLETE_12_ZONE_PLACEMENT_COUNT=0
LEGACY_FALLBACK_USED_FOR_PASS=false
ACCESS_ROUTING_PERFORMED=false
TRUCK_VALIDATION_PERFORMED=false
P2D_PERFORMED=false
VALIDATED_CANDIDATE_SELECTOR_CHANGED=false
TOOL7_BEHAVIOR_CHANGED=false
P1_COMPLETE=false
RECOVERY_ROUND_USED=0
RECOVERY_ROUND_1_AUTHORIZED=false
RECOVERY_ROUND_2_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

```ini
TASK_ID=V2_2_2_P1A_WHOLE_BUILDING_COMPOSITION_P1_S3_CR1
MODE=COMPOSITION_DOMAIN_DRIVEN_ANCHOR_SYNTHESIS_AND_COUPLED_INTERFACE_PREFLIGHT
CR1_RESULT=PASS
RECOVERY_ROUND_USED=1
COMPOSITION_PLACEMENT_NODE_BUDGET=60000
NODES_USED=50621
DOMAIN_DRIVEN_ANCHOR_SYNTHESIS_IMPLEMENTED=true
SHIPPING_OFFICE_INTERFACE_PREFLIGHT_IMPLEMENTED=true
ALL_FAMILIES_EXACT_PLACEMENT_ATTEMPTED=true
FAMILY_FIRST_EXACT_PLACEMENT_ROUND_COMPLETE=true
COMPOSITION_NATIVE_COMPLETE_CANDIDATE_COUNT=1
COMPLETE_12_ZONE_PLACEMENT_COUNT=1
COMPLETE_CANDIDATE_FAMILY=LINEAR_BANDED
SITE_VALID=true
DIMENSION_VALID=true
NON_OVERLAP_VALID=true
MUST_ADJACENCY_VALID=true
MUST_ADJACENCY_SATISFIED_COUNT=7
COMPOSITION_INTENT_PRESERVED=true
LEGACY_FALLBACK_USED_FOR_PASS=false
ACCESS_ROUTING_PERFORMED=false
TRUCK_VALIDATION_PERFORMED=false
P2D_PERFORMED=false
CORRECTION_ROUND_2_AUTHORIZED=false
P1_COMPLETE=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
TAG_AUTHORIZED=false
RELEASE_AUTHORIZED=false
DEPLOYMENT_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```
