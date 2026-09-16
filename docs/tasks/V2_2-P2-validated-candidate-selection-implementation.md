# V2.2 P2 validated candidate selection

This task closes the application boundary between the deterministic P2C
placement search and P2D access/truck validation. It does not change the
P2C placement objective, the P2D route rules, or the P4 MCP integration.

## Governance

```ini
TASK_ID=V2_2_P2_VALIDATED_CANDIDATE_SELECTION_IMPLEMENTATION_R1
BASE_MAIN_SHA=cd0a2cc16a9b49296a25b398d4a17dbd4f63b67b
REFERENCE_P4_PR=285
REFERENCE_P4_HEAD=6df0f4b023309b27509fe00861a090decce42377
P2C_RESPONSIBILITY_PRESERVED=YES
P2D_RESPONSIBILITY_PRESERVED=YES
P2C_CANDIDATE_ENUMERATION_IMPLEMENTED=YES
P2_APPLICATION_SELECTION_IMPLEMENTED=YES
NEW_ROUTE_OBJECTIVE_ADDED=NO
PACKAGING_SORTING_STRAIGHT_RULE_PRESERVED=YES
P4_CANDIDATE_SELECTION_IMPLEMENTED=NO
P4_PR_MODIFIED=NO
P2_COMPLETE=false
P4_AUTHORIZED=false
P5_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=TRUE
```

## Authority boundary

P2C remains responsible for deterministic complete-candidate generation, P2A
geometry hard constraints, the seven `MUST_ADJACENT` constraints, and the
existing P2B2 lexicographic ranking. Its public application boundary now
exposes a one-shot deterministic candidate stream that reuses the same
authority validation and search family as the original placement operation.
P2C still performs no portal, corridor, route, or truck validation.

P2D remains responsible for portal generation, access and corridor validation,
the packaging-material `STRAIGHT_ONLY` rule, truck maneuver validation,
personnel/truck interaction, building-footprint validation, and the final
`project_layout_validated`/`p2_complete` decision.

The new application selector consumes the P2C stream, sends every complete
candidate through the existing P2D route application, rejects candidates that
do not fully pass P2D, and selects the highest-ranked P2C candidate among the
P2D-full-pass candidates. It never scores route length and never adds a
weighted or route objective. P4 does not select candidates.

## Search and exhaustion semantics

The candidate stream does not use `complete_candidate_limit` as an early-stop
condition. The only search cutoff is the deterministic node budget; otherwise
the finite candidate tree is exhausted. The stream and selection result
record:

```ini
COMPLETE_CANDIDATE_LIMIT_STOPS_SEARCH=false
NODE_BUDGET_IS_ONLY_SEARCH_CUTOFF=true
SEARCH_TREE_EXHAUSTED
NODE_BUDGET_EXHAUSTED
OBJECTIVE_OPTIMAL_WITHIN_SEARCH_FAMILY
NO_MATHEMATICAL_INFEASIBILITY_PROOF=YES
```

If the node budget ends after one or more candidates, a found P2D-full-pass
candidate may still be returned, but its search-family optimum is explicitly
unproven. If no P2D-full-pass candidate is found, the result is an explicit
search-exhaustion result and not a mathematical infeasibility proof. Candidate
counts, P2D validation counts, selected hashes, and a compact per-candidate
validation trace remain in the canonical application evidence.

## Packaging-to-sorting boundary

The P1 requirement remains unchanged:

```ini
FROM=packaging_material_storage
FROM_EDGE=LONG_EDGE
TO=sorting_packaging_room
TO_EDGE=SHORT_EDGE_EXIT_SIDE
ROUTE_SHAPE=STRAIGHT_ONLY
```

The selector does not repair or relax that requirement. A candidate may pass
P2D through either the approved direct edge or the approved corridor-mediated
straight route. Making the two zones directly adjacent would not be an
equivalent correction because the frozen contract explicitly permits a
corridor-mediated `STRAIGHT_ONLY` connection.

## P4 boundary

PR #285 and its head are reference-only evidence for this task. No P4 source,
MCP, Skill, or integration file is modified. P4 may consume a future
validated-layout result, but candidate enumeration and selection remain in the
P2 application boundary.

## Verification intent

The focused tests prove that a first candidate which fails P2D does not stop
the search, and that a later candidate with a better frozen P2C objective is
selected. They also prove deterministic replay and bounded-search semantics.
P2C/P2D regression and layout architecture tests remain required before the
Draft Review gate.
