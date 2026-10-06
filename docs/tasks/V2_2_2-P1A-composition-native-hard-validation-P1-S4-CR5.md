# V2.2.2 P1A Composition-Native Hard Validation — S4 CR5

TASK_ID=V2_2_2_P1A_COMPOSITION_NATIVE_HARD_VALIDATION_P1_S4_CR5
MODE=REPLAYABLE_MAIN_CHAIN_WITNESS_DISCOVERY_AND_COMPOSITION_INTENT_CONSTRAINT_PROPAGATION
PR_NUMBER=306
BRANCH=codex/v2.2.2-p1a-s4-cr1-access-aware-placement
START_HEAD=83c7d3ff8d42614c166d7c97ad3f539cb2162324

## Scope and outcome

CR5 adds a conservative, non-authoritative composition-intent projection
prefilter to the existing bounded main-chain forward probe. It derives only
necessary signed-projection bounds from the same family-specific composition
intent already checked by `_partial_intent_possible`. A proven conflict may
skip an anchor before physical candidate expansion; every survivor still goes
through the existing site, obstacle, overlap, MUST, and exact partial-intent
checks. The CR4 witness implementation and both CR2 ordering lanes remain in
place.

CR5's required Xinzhao lane did **not** cross its discovery gate. The fixed
1,666-node `LINEAR_BANDED:Y:POSITIVE:r1`, bank `+1`,
`S3_COMPATIBILITY_ORDER` probe ended `UNKNOWN_BUDGET_EXHAUSTED`. It evaluated
9,142 finite anchor records, rejected 7,438 by proven intent bounds, retained
1,704, and used the entire allowed slice on physical checks. No late
`_partial_intent_possible` rejection occurred in this probe; the remaining
cost was site/obstacle/overlap rejection and incomplete probe coverage. Thus
there was no positive witness to hand to CR4 reuse, and no claim of layout
feasibility or global infeasibility is made.

Overall result: `FAIL` — `REPLAYABLE_WITNESS_DISCOVERY_NOT_RECOVERED`.
This is a bounded-search result, not a global infeasibility proof. Do not start
CR6 without separate Owner authorization.

## CR1–CR4 progression preserved

- CR1 introduced five Access-critical construction interfaces; their
  engineering authority remains false and the existing Access validator stays
  authoritative.
- CR2 restored structural search-lane coverage and non-Truck-first candidate
  assessment; Truck preflight still cannot prevent complete-candidate
  formation.
- CR3 introduced optimistic main-chain completion checks, chain-hole support,
  and exhaustive-negative-only pruning under the shared 60,000-node budget.
- CR4 added invocation-local constructive witness creation, witness-first
  replay, hard revalidation, suffix inheritance, support-geometry
  compatibility, and ordinary-search fallback. It is retained in CR5.
- CR5 adds no family, role-order lane, dimension, MUST, Access, Truck, or P2D
  rule. It does not load prior evidence or historical coordinates as runtime
  geometry.

## Propagation semantics

| Family | Existing predicate projected | Safe rejection condition |
| --- | --- | --- |
| `LINEAR_BANDED` | signed RAW group center `<` signed CORE group center | Minimum feasible RAW center is at least the maximum feasible CORE center |
| `LINEAR_BANDED` | signed CORE group center `<` signed FINISHED group center | Minimum feasible CORE center is at least the maximum feasible FINISHED center |
| `CENTRAL_PROCESS_CORE` | signed RAW group center `<` Sorting center; Sorting center `<` signed FINISHED group center | Existing central-rule feasible interval is empty |
| `PROCESS_SPINE_WITH_PERIPHERAL_BANKS` | Existing material-chain projections are monotone nondecreasing | A fixed predecessor/successor pair is already inverted |

Future-role projection ranges use the effective-site-boundary bounding interval,
which is a permissive superset, with authoritative shapes and already-fixed
MUST-neighbor facts only where they safely narrow a necessary range. Slack is
ordering-only. `_partial_intent_possible` remains the exact final predicate.
`PROVABLY_INCOMPATIBLE` is the only propagation state that filters; uncertain
or merely low-slack states are retained.

## Xinzhao known-lane probe

| Stage | Anchor records | Result/count |
| --- | ---: | ---: |
| Coating raw anchors | 7,962 | 7,323 proven incompatible; 639 retained |
| Coating physical checks | — | site 213; obstacle 216; overlap 200; MUST 0; late intent 0; 7 partial placements |
| Finished raw anchors | 1,180 | 115 proven incompatible; 1,065 retained |
| Finished physical checks before cap | — | site 496; obstacle 485; overlap 49; MUST 0; late intent 0; 0 partial placements |
| Probe total | 9,142 | 7,438 rejected by propagation; 1,704 retained; 1,666 geometry expansions; UNKNOWN at the frozen cap |

The sequence hash is
`5c7ded58a9a36ec2e193400279a52ee4ce433da71eb03fab0b2e8dc3d22cb271`.
The first recorded cap-stop candidate was a potentially compatible Finished
Goods rectangle `[13068,6984,31668,39384]`; it was not validated because the
shared probe slice was exhausted. The CR3 663-node witness remains a negative
regression only: site/MUST plausibility did not establish the full composition
intent, so it is not restored or injected.

## Verification and limitations

- CR5/CR3/CR4 focused test file: 21 passed.
- S1/S2/S3 and architecture-boundary regressions: 72 passed.
- S4 integration test items: all 7 printed `PASSED`, including bounded
  family-first search and deterministic replay. The pytest process then stalled
  during teardown/source reporting and was interrupted, so it did not provide
  a clean terminal summary or an exportable full-run aggregate.
- A separate full-replay capture retry stalled before test collection while
  importing pytest/Pygments; it was interrupted before tests ran. No complete
  CR5 attempt/candidate/access aggregate is inferred from this missing capture.
- Ruff check, Ruff format check, and `git diff --check`: PASS. Local mypy did
  not complete; exact-head CI is required to settle that gate.
- Evidence JSON: [xinzhao_replayable_witness_constraint_propagation.json](evidence/v2_2_2_p1a_s4_cr5/xinzhao_replayable_witness_constraint_propagation.json).

The focused known-lane probe used the real Xinzhao authority-derived geometry
and the existing CR2 partial witness fixture. It is not a complete 13-attempt
replay. `complete_candidates_constructed`, Access assessment counts, and
candidate hashes for a CR5 whole-search run remain uncaptured and are recorded
as unavailable rather than zero. The known-lane status itself is captured and
fails the mandatory CR5 gate.

## Frozen boundaries

`PLACEMENT_BUDGET=60000`; `ACCESS_ROUTE_BUDGET=20000`;
`TRUCK_BUDGET=20000`. No global or forward-probe slice increase was made.
Zone dimensions, MUST adjacency, Access, Packaging `STRAIGHT_ONLY`, Truck, P2D,
composition contracts, selectors, and Tool 7 are unchanged. No production
selector/Tool 7 integration, post-validation repair, legacy R2 recovery,
historical geometry reuse, or runtime coordinate template was added.

## Next-stage boundary

CR5 stops at the failed known-lane forward-witness discovery gate. The observed
remaining issue is the large surviving finite anchor set and the physical
site/obstacle/overlap work it consumes, not late composition-intent rejection.
No CR6 or other recovery round is authorized by this record.
