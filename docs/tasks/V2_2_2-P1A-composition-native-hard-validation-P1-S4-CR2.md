# V2.2.2 P1A S4 CR2 — Search-Space Monotonicity and Non-Truck-First Recovery

## Scope and prior result

CR1 added `AccessCriticalConstructionIntentV1` and the five access-critical construction interfaces. That implementation preserved the Access, Truck, P2D, dimension, MUST-adjacency, and composition authorities, but its Xinzhao replay produced zero complete candidates. Consequently, it performed zero Access, Truck, and P2D validations. CR1's business validation result remains **FAIL** and is not overwritten by this correction.

CR2 preserves those construction foundations and changes only composition-placement scheduling, construction search-order lanes, complete-candidate checkpoint accounting, and the point at which Truck preflight runs.

## CR2 implementation

- The fixed global placement allocation remains 60,000 nodes; access routing and Truck budgets remain 20,000 each.
- Family-first coverage is retained for `LINEAR_BANDED`, `CENTRAL_PROCESS_CORE`, and `PROCESS_SPINE_WITH_PERIPHERAL_BANKS`.
- The deterministic scheduler runs both `ACCESS_AWARE_ORDER` and `S3_COMPATIBILITY_ORDER`. The latter retains CR1 access-aware intent/anchors and changes only variable order.
- The known structural lane `whole-building-structural-composition@2.0.0:LINEAR_BANDED:Y:POSITIVE:r1`, bank `+1`, is explicitly scheduled. No historical coordinates or candidate hash are injected.
- Complete geometries, if found, are observed before access-score admission. All 11 non-Truck Access requirements are evaluated at the complete-candidate checkpoint. Truck necessary preflight is deferred until after ranking and cannot prune geometry or hide a complete candidate.
- Search-order choice remains a construction strategy, not engineering authority. Existing validators remain the only validation authority. No geometry repair or legacy fallback is used.

## Xinzhao replay evidence

Machine-readable evidence: [xinzhao_search_space_monotonicity_and_non_truck_recovery.json](evidence/v2_2_2_p1a_s4_cr2/xinzhao_search_space_monotonicity_and_non_truck_recovery.json).

The replay scheduled 13 attempts: Linear 5, Central 4, Spine 4; Access-aware order 7 and S3-compatibility order 6. The known Linear Y/positive/r1, bank `+1` lane received a 20,000-node attempt. Total scheduled allocation was exactly 60,000, while the search visited 55,964 nodes because some finite search trees ended before their allocation was consumed. The replay result hash was `sha256:1c01e1763b0f3d36d7b32389936afba00592c03bb4bd47b6475de102d60688b8`.

No attempt formed a complete 12-zone candidate. The best partials reached 10/12 for Linear, 9/12 for Central, and 9/12 for Spine. The required Linear Y/positive/r1, bank `+1` lane was attempted under the S3-compatible variable order but reached only five simultaneous roles; its next role was `coating_room`. Thus lane coverage is restored, but the known prior feasible lane did not yield a complete geometry under the preserved CR1 access-aware construction constraints.

The resulting checkpoint counts are all zero: complete candidates constructed, access-assessed, admitted, selected, Access validation attempts, Truck validation attempts, and P2D validation attempts. This is a search-progress failure, not a proof of site infeasibility. In particular, no non-Truck Access score can be inferred from the absence of a complete candidate.

Packaging partial preflight passed 30 times; no complete candidate reached Packaging final Access validation. The preserved S4 control remains the historical candidate `sha256:4a4b8f6695526ea0bd1cf30238ae4c7c45b35e6d9677b0c4bd8f98228e8f3c47`, with 7/12 total and 7/11 non-Truck Access passes, and `TRUCK_MANEUVER_SEARCH_EXHAUSTED` after 27 visited Truck nodes (20,000 budget, search tree exhausted, budget not exhausted). Existing CR1 control evidence is retained unchanged.

## Validation and outcome

The focused S1/S2/S3/S4, P2C, candidate-selection, P1F, Access/P2D, and architecture regression set passed: **176 passed**. Ruff, format, and mypy checks passed locally. Exact-head PR and push CI results are recorded in the PR after the final push.

`IMPLEMENTATION_RESULT=PASS` describes the bounded code and test changes only. `VALIDATION_PROGRESS_RESULT=NO_COMPLETE_CANDIDATE`; therefore the task's business gate is **FAIL** (`ACCESS_AWARE_COMPLETE_CANDIDATE_COUNT=0`). `GLOBAL_INFEASIBILITY_PROVEN=false`. Do not start CR3 or expand the budgets without separate Owner authorization.

## Frozen authorities and non-goals

No dimension, MUST adjacency, Access, Truck, P2D, composition, selector, or Tool 7 authority was changed. Placement remains bounded to 60,000 nodes; route and Truck budgets remain 20,000. There is no legacy-placement fallback, historical-coordinate reuse, or post-validation geometry repair. The preserved CR1 access-critical intent remains construction metadata (`engineering_authority=false`).
