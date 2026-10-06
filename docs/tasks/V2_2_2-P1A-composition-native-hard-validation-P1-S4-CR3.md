# V2.2.2 P1A S4 CR3 — Whole-Building Completion Forward Check

## Scope and history

- CR1 introduced the five access-critical construction interfaces while preserving existing Access, Truck, P2D, dimension, and MUST-adjacency authorities. Its access-aware replay constructed no complete candidate.
- CR2 preserved CR1, restored the known-feasible composition/bank lane and the S3-compatible variable-order lane, and moved Truck preflight behind complete-candidate construction and the 11 non-Truck Access checks. Its real replay still constructed no complete candidate.
- CR3 adds an optimistic main-chain completion probe to the composition-native search. The chain is derived from the existing MATERIAL flows in `process_graph()`; no independent chain or adjacency authority was added.

## Implementation

The probe treats every already-placed rectangle—including support and personnel roles—as occupied, ignores only unplaced non-main-chain roles, and searches finite event-derived placements for missing main-chain roles. It supports holes in the chain, returns on the first witness, and can prune only after exhaustive exhaustion of its current finite search domain. Budget exhaustion and incomplete inputs remain UNKNOWN and never prune.

Primary DFS and forward-check expansions share the existing 60,000 placement-node cap. Each attempt exposes primary/forward node accounting and a bounded forward-check slice; unused total nodes remain available to primary search. The CR2 outer attempt schedule and both search-order lanes are unchanged. Forward checking has no engineering or validation authority.

Packaging `STRAIGHT_ONLY`, all existing hard authorities, the 20,000 Access route budget, and the 20,000 Truck budget are unchanged. No historical control or CR2 witness coordinates are used by runtime; partial geometries appear only in focused tests.

## Real Xinzhao replay

The final replay on this change set used 55,964 of 60,000 nodes: 47,702 primary-search nodes and 8,262 forward-check nodes. The accounting identity holds. The 13 scheduled attempts still cover all three families (Linear 5, Central 4, Spine 4) and both CR2 search-order lanes (Access-aware 7, S3-compatible 6).

The deterministic replay result hash is `sha256:bcfc6ac1c46e9556759115ec8226259a4cb94b4a6e5f717ab26d1aabc296535c`.

Forward checking recorded 124 invocations: one optimistic completion witness, 10 exhaustive negative proofs, and 113 UNKNOWN budget outcomes. Only the 10 exhaustive negatives pruned, all attributed to `coating_room`; UNKNOWN outcomes never pruned. Representative negative evidence identifies the still-unplaced `finished_goods_room` as the first unplaceable main-chain role with Shipping already fixed. Despite pruning proven-starved branches, the bounded search produced zero complete 12-zone candidates and therefore ran no Access, Truck, or P2D validation for new candidates.

This result is `FAIL` under the CR3 business gate. It is a failure of the current bounded composition-native search to produce a complete candidate, not a proof of global layout infeasibility. The historical S4 control remains the 7/12 Access control and its existing Truck search-exhausted result; control replay is preserved by regression tests.

Machine-readable attempt, forward-check, partial-witness, negative-proof, candidate, and control evidence is stored at `docs/tasks/evidence/v2_2_2_p1a_s4_cr3/xinzhao_whole_building_completion_forward_check.json`.

## Validation and stop boundary

Focused forward-check tests cover process-graph sourcing, fixed-rectangle occupancy, optimistic treatment of unplaced non-main roles, chain holes including Shipping-before-Finished, exhaustive negative proof, and UNKNOWN non-pruning. The required S1–S4, P2C, Access, Truck, P2D, selector, P1F, architecture, static checks, exact-head CI, and backend checks are tracked separately in the task result.

Local targeted regression results on the CR3 working tree: CR3 plus S4 access-aware tests 13 passed; S1/S2/S3 composition tests 56 passed; P2C, selector, Access, and Truck tests 103 passed; P2D routing tests 11 passed; P1F project-Truck-input tests 46 passed; and composition architecture-boundary tests 11 passed. Ruff, format, and mypy on the changed domain module passed. A whole-source `mypy src` invocation remained idle without output and was interrupted, so it is not claimed as a local full-source pass. A wider combined test collection was also interrupted while importing the P1F context-inset/P4 path during a third-party JSON Schema metaschema read; that interrupted invocation is not counted as passing. Exact-head CI remains the full-repository gate.

`COMPLETE_CANDIDATES_CONSTRUCTED=0`, so the task stops with `RESULT=FAIL` and `FAIL_STAGE=NO_COMPLETE_CANDIDATE`. `GLOBAL_INFEASIBILITY_PROVEN=false`. No CR4 or other follow-on implementation is authorized by this result.
