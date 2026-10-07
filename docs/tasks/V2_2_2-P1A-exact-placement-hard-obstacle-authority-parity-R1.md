# V2.2.2 P1A — exact-placement hard-obstacle authority parity R1

## Authorization and scope

Start `f4961f1fcbbf41c70e8f11e54e30e5cead76fb06`, existing branch and Draft
PR #307. PR #306 remains frozen at `4823fae99958eefddd32dc0afe42b729df00f415`;
no code was copied. The checkout was clean, with no staged or untracked files.
Prior quarantine artifacts are outside scope and untouched.

This is authority remediation only. It does not consume metric reservations
and does not authorize P3. No Access, Truck or P2D production validation is run.

## Before / after

Before: exact placement parsed `obstacles.no_build_zones`, while P2 parsed
`obstacles.hard_obstacles`. Retained existing buildings could therefore be absent
from both exact candidate rejection and flexible-shape obstacle span events.

After: both use the pure domain function `validated_hard_obstacle_polygons`.
It requires an obstacles mapping and an explicit hard-obstacle list; each item
must be a mapping with `hard is True` and a normalizable footprint. Source order
is preserved. Missing/malformed authority fails closed, without a no-build
fallback. Retained/conditional classification remains owned by validated site
authority; this parser does not reinterpret it.

Production changes are limited to the parser and two caller replacements.
Effective buildable boundary, dimension authority, shape algorithm, candidate
hard predicates, search order, scheduler, fallback, ranking, budgets and all
P0/P1/P2 contract semantics remain unchanged. An AST digest locks all exact
search functions/classes except the enumeration boundary where input changes.

Search algorithm invariance is not global result invariance: retained-building
sites should reject previously admitted obstacle collisions and may have changed
shape/event domains. Canonical Xinzhao has three NO_BUILD obstacles and no
retained buildings, so its old/new authority polygons and results must match.

## Evidence strategy

The actual START-HEAD canonical exact-placement replay was captured before any
production modification: 11 attempts, 50,621 visited nodes, one candidate:
`sha256:4a4b8f6695526ea0bd1cf30238ae4c7c45b35e6d9677b0c4bd8f98228e8f3c47`.
The baseline includes full attempt/funnel diagnostics, allocation/visits,
deepest roles, family progress, failure taxonomy, shape counts, witness digests
and the full application result hash. It is not an Access or layout validation.

Final direct runner performs two canonical placement replays and two complete
P2 metric application replays. Placement summaries must exactly equal the new
START capture. Full serialized metric artifacts must exactly equal the immutable
P2 evidence produced on the pinned START HEAD (two actual completed P2 runs).
Historical evidence is not modified or used as runtime geometry seed.

Real validated retained/conditional fixtures also invoke both actual consumers.
Spies record unchanged input tuples/shapes and the existing search candidate
rejection. The fixture metric cap-zero mode is explicitly an authority plumbing
audit, not capacity evidence; full canonical P2 replays are separate and exhaustive.

Evidence: `evidence/v2_2_2_p1a_exact_placement_hard_obstacle_authority_parity_r1/hard_obstacle_authority_parity.json`.
Runner: `backend/tests/evaluation/v222_p1a_hard_obstacle_parity_evidence.py`.
Final SHA is bound through the evidence's containing commit and exact-head CI,
avoiding an impossible self-referential commit hash.

## Validation

Focused tests cover shared parser identity, fail-closed invalid schema, retained
candidate rejection, conditional removal, no-build regression, both callers'
real obstacle/shape input parity, unchanged search AST, canonical placement
baseline equality and terminal full metric replay equality. Existing shape
extraction, site, placement, P0/P1/P2 and architecture regressions remain required.

Initial local lint found test formatting/long lines; corrected without production
semantic changes. The first focused selection passed 35 tests. Final validation
and exact-head CI results are recorded in PR #307 and the final task response.

Final focused selection (including the terminal evidence parity test): 34 passed.
Two final exact-placement replays equal the START baseline, including 11 attempts,
50,621 nodes, the one unchanged candidate hash and full application result hash.
Two complete final metric replays equal the START serialized artifacts:
42 nonempty realizations, six ready gates, Office/Shipping 328,373 slots per domain;
all three metric result hashes are
`sha256:412a5ec8f51a84ceebddd4b663e89fe50a76d7cc8997c239b02dcb4c5dfc6677`.
The retained fixture returns `OBSTACLE`, conditional removal does not, and both
callers receive identical obstacle tuples and all twelve role shape domains.
Normal CI-scope Ruff/format passes (904 files), explicit evidence-runner checks
pass, and all-source mypy passes (400 files). An extra explicit scan of the pilot
directory reported two pre-existing format differences outside the normal CI
discovery scope; those unrelated tracked files were not edited.

The first combined regression run ended with 923 passed, 16 skipped, one
deselected and one infrastructure failure: a historical overlay's `git diff`
could not refresh `.git/index.lock` (`Operation timed out`, exit 128). No lock
was moved/deleted and no test was changed. The same complete suite is rerun
with `GIT_OPTIONAL_LOCKS=0`, disabling optional index refresh for read-only Git
checks while retaining their content comparisons. That full retry was interrupted
after 254 passes because source reads again stalled for a prolonged period;
only the owned pytest process received SIGINT, with no Git child active. The
sole first-run failed test was then rerun with optional locks disabled and passed
(1 passed, 20.01 seconds). Thus all originally selected tests have completed
passing results across the full run and the targeted retry, plus the final
focused evidence-record test. This is not represented as a single green local
full-suite invocation. Exact-head PR/Push CI remains the complete clean-environment
gate, recorded separately in the PR and final response.

## Stop

Closing this source parity gap removes that specific future-consumption blocker.
It does not prove whole-building feasibility or authorize metric-slot consumption.
P3, Ready, Merge, release and deployment remain unauthorized.
