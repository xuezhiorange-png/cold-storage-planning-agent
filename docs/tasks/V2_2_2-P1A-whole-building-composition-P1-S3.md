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
