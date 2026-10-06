# V2.2.2 P1A S4 CR4 — Forward-Check Witness Reuse

## Scope and recovery history

- **CR1** introduced access-critical construction intents for personnel ingress, Packaging-to-Sorting straight access, Secondary, Frozen, and Shipping/Truck interfaces. These remain construction intent only; existing authorities were not relaxed.
- **CR2** preserved both `ACCESS_AWARE_ORDER` and `S3_COMPATIBILITY_ORDER`, restored known structural-lane coverage, and staged Truck checks after complete-candidate formation and non-Truck Access assessment.
- **CR3** added an optimistic completion forward check sourced from the existing material-flow process graph. It treated already-placed rectangles as occupied, supported chain holes, and allowed pruning only after an exhaustive negative proof. Its positive witness was discarded before primary DFS could consume it.
- **CR4** adds an invocation-local, non-authoritative main-chain witness value and attempts to place a positive forward-check witness before ordinary anchors, with suffix inheritance and normal hard-check revalidation.

## Implementation boundary

`MainChainCompletionWitnessV1` is created only from a complete `PASS_TO_SEARCH` result. It is advisory search state: it is neither engineering nor validation authority, creates no hard reservation, and cannot bypass dimensions, site, obstacle, overlap, MUST-edge, or composition checks. A rejected witness falls through to the ordinary domain-derived and bounded generic search. Support geometry may invalidate a witness but cannot be rejected only because it overlaps witness geometry. Unknown probes continue without pruning; exhaustive negative-proof semantics remain those of CR3.

Witnesses live only for the current search invocation. The two CR2 search-order lanes, outer attempt schedule, 60,000 placement-node budget, 20,000 Access route budget, and 20,000 Truck budget remain unchanged. No historical candidate coordinates are injected into runtime.

## Xinzhao replay and result

The real Xinzhao replay did not create a reusable witness in the required known lane. For `LINEAR_BANDED:Y:POSITIVE:r1`, bank `+1`, `S3_COMPATIBILITY_ORDER`, the run reported maximum placed roles `5` and next role `coating_room`. Consequently there was no primary witness-reuse attempt, the lane did not advance beyond the CR3 threshold, and no complete 12-zone candidate was constructed. Access, Truck, and P2D validation therefore did not run for a newly constructed candidate.

The current replay's forward-check pass count was zero (CR3 had one); its 114 UNKNOWN outcomes are not an improvement over CR3's 113. This is an honest failed business outcome, not evidence of global infeasibility. The required CR4 gate fails at `KNOWN_LANE_FORWARD_WITNESS_REUSE_ATTEMPTED=false` / `KNOWN_LANE_MAX_PLACED<=5`; stop here and do not begin CR5.

The preserved historical control geometry was replayed on the current working tree through the existing Access/Truck authority. It remains 12 requirements, 7 pass, 5 fail, and `TRUCK_MANEUVER_SEARCH_EXHAUSTED` after 27 visited nodes; the node budget was not exhausted and the search tree was exhausted. It is a control only and is not injected into search.

Machine-readable replay, witness counters, attempt lanes, control result, and candidate status are recorded in `docs/tasks/evidence/v2_2_2_p1a_s4_cr4/xinzhao_forward_witness_reuse.json`.

## Validation and stop boundary

Focused CR4 unit and architecture tests exercise positive witness replay, suffix inheritance, support overlap invalidation without hard rejection, chain-hole reuse, non-authoritative witness semantics, and shared node accounting. The first broad run reported 88 passed and one failure: `test_xinzhao_candidate_runs_once_through_existing_access_truck_and_p2d` exposed that the new witness-provenance fields changed a no-intent candidate hash. The fields are now limited to the Access-aware path to preserve the no-intent candidate identity. Post-fix local replay attempts were interrupted before assertions because Python import stalled while reading backend source; the exact-head CI result is required to close this regression gate. The historical control geometry's current authority replay is independently recorded.

The task stops with `RESULT=FAIL`, `VALIDATION_PROGRESS_RESULT=FORWARD_WITNESS_NOT_EFFECTIVELY_CONSUMED`, and `COMPLETE_CANDIDATES_CONSTRUCTED=0`. `GLOBAL_INFEASIBILITY_PROVEN=false`. No CR5, P1-S5, selector, Tool 7, Ready, or Merge work is authorized by this result.
