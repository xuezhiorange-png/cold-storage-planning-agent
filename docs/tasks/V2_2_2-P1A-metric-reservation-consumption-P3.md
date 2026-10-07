# V2.2.2 P1A — dynamic metric reservation consumption (P3)

Task: `V2_2_2_P1A_METRIC_RESERVATION_CONSUMPTION_P3`.
Start: `112f30115d201dd8ef2daf541f5352b92d2154fe`; base main:
`a0ef560de778770e4c26c4d027a239afe78eeadd`. Continue existing Draft PR #307
and `codex/v2.2.2-p1a-structural-hard-interface-reservation-p0`.
PR #306 stays diagnostic-only and frozen at
`4823fae99958eefddd32dc0afe42b729df00f415`; no runtime code copied.
Quarantined files are outside this task and untouched.

## Baseline captured before production modifications

The clean exact checkout gate passed. Two independent START production placement
calls captured the same baseline: 11 attempts, 50,621 nodes, one complete control
candidate `sha256:4a4b8f6695526ea0bd1cf30238ae4c7c45b35e6d9677b0c4bd8f98228e8f3c47`.
The full P2 public realization was then executed with read-only instrumentation
of its existing valid-pair hook. All seven domains were exhausted before source
modifications. The control candidate consumes **0/7** P2 exact pairs. This is
not a failure of engineering MUST validation: a valid shared edge need not belong
to the explicitly declared finite construction reservation domain.

The actual START P2 public result retained the expected hash
`sha256:412a5ec8f51a84ceebddd4b663e89fe50a76d7cc8997c239b02dcb4c5dfc6677`.
No historical candidate is injected into runtime or preserved by weakening P3.

## Implementation and semantics

The server-owned placement application rebuilds/replays all structural handoffs
and constructs seven unique immutable runtime domains from the P2 evaluator.
An optional internal valid-slot sink collects exact bounds and authoritative
shapes without changing P2's count, digest, representative samples or serialization.
The 642,482 valid alternatives are indexed by endpoint footprint, reused across
composition handoffs, and never persisted as a full slot list.

Every ordinary hard-valid candidate updates all reservations before recursion.
Each placed endpoint must match its exact slot footprint; provisional partners
must avoid placed rooms, satisfy all placed MUST neighbors and pass the unchanged
composition-intent predicate. Only complete-domain proved-none support rejects;
UNKNOWN does not prune. Final acceptance also requires all exact pairs consumed,
in addition to the existing final MUST and composition checks.

Support witnesses may migrate, not reserve geometry. Immutable parent states
make cursors/backtracking safe. A support candidate is offered only for exactly
one placed endpoint; it is ordinarily validated and charged once, with generic
fallback preserved. The legacy Shipping/Office seed has no production call path.
The coarse bbox preflight remains diagnostic-only, never reservation proof.
Fixed placed-room bounds are computed once per support update, not once per
slot. The exhaustive small-fixture comparison independently uses the ordinary
compatibility entry point, checking the hoisted-bounds optimization as well as
cursor/index answers against full-domain scans.

Engineering authorities, P0/P1/P2 contracts, shape algorithm, zone order,
scheduler and 60,000 placement-node budget are frozen. No Access/Truck/P2D
production replay or candidate selection is introduced.

## Schema and historical regression audit

Runtime indexes/support states remain internal/non-serialized. Exact-placement
attempt/enumeration diagnostics are internal additive fields; stable Plan/Handoff
and candidate schema are not extended with runtime geometry. P2 serialization
is unchanged. Historical evidence files remain immutable.
Production-consumer audit found the enumeration type/identity only in its owning
domain/application; the candidate-validation bridge hashes the full placement
dictionary rather than enforcing a closed diagnostics-field schema. P2 imports
only the existing server-replay guard. The additive diagnostics therefore remain
internal; their replay hash intentionally changes, while P0/P1/P2 schemas do not.

R1's unchanged-search AST test is pinned to the actual R1 final Git object;
R1's completed actual START/FINAL parity remains checked in its immutable evidence.
P3 is separately authorized to change lifecycle results. A new current-code AST
boundary locks unchanged zone order, allocation/schedule, ordinary anchors,
shape ordering, site/obstacle/overlap rejection and composition predicates.
R1 retained/conditional integration fixtures explicitly use a cap-zero runtime
builder for authority-plumbing audits only; complete canonical runtime capacity
is independently executed in the P3 evidence runner.

## Validation disclosure

Initial integration call exposed an incorrect P1 field name; corrected to
`interface_source_edge_identity` before the complete replay. An early typecheck
captured that error; the subsequent changed-source typecheck passed.
A composition-side fixture initially assumed a fixed axis; it now derives the
actual Office side from the handoff. Current focused/boundary suite: 25 passed;
combined P3/R1 suite: 44 passed. An earlier pre-hoist P0/P1/P2/architecture
selection passed 887 tests with 16 skipped; it is not substituted for the
final-source terminal selection below. Backend Ruff, format (908 files) and Mypy (402 files)
passed. A final-unconsumed UNKNOWN fixture also locks its distinct diagnostic
classification instead of mislabeling it composition-intent failure.
An initial capture was interrupted before a complete replay to correct that
diagnostic. A second capture, a first exploratory full probe and an in-progress
exact-placement pytest run were interrupted to hoist repeated fixed-bounds
conversion after CPU sampling identified it. Only agent-owned Python processes
were interrupted, with no child processes; no Git process was interrupted and
no manual Git-metadata recovery or lock manipulation was performed.
All interrupted captures are excluded from final determinism evidence.
No failed exploratory run is claimed as final evidence.

The first complete final-code production replay finished: 12 attempts, 6,838
placement nodes, 1,778 reservation prunes, 28 accepted partials and zero complete
candidates. All six compositions (both bank attempts) have seven supported root
reservations; no root is UNKNOWN or proved-none. Family maxima are LINEAR=0,
CENTRAL=1, SPINE=0. The accepted-zero-capacity counter is zero. Seven runtime
domains are complete, contain 642,482 slots, and retain the P2 counts/digests.
Two complete final-code production replays now agree field-for-field, including
all support/prune sequence digests, attempt schedule, node accounting, hashes,
and consumed proofs (both have none). Both application result hashes are
`sha256:80fe8cdbaa666a944546dd59dbceffae09b8e91cd9dbe3a0425f9f14b97f0cc9`.
Both fail the complete-candidate business gate. Two independent public P2
replays now exactly match all 42 serialized historical artifacts and the
`sha256:412a5ec8f51a84ceebddd4b663e89fe50a76d7cc8997c239b02dcb4c5dfc6677`
result hash, with full runtime count/digest parity for all seven edges.
Exact-head verification remains pending.
The existing canonical-complete-candidate regression assertion is deliberately
not weakened or replaced by a fixture/evidence assertion. Any failure remains
visible in local regression and exact-head CI results.

The complete existing exact-placement suite has now terminated: **10 passed,
2 failed** (6,547.68 seconds). Failures are the unchanged canonical complete-
candidate assertion and the legacy seed test indexing `candidates[0]` when no
candidate exists. Neither assertion was rewritten. Therefore the required
regression acceptance gate fails, independently of the focused mechanism tests.
`RESULT=FAIL`; `IMPLEMENTATION_RESULT=FAIL`;
`VALIDATION_PROGRESS_RESULT=METRIC_RESERVATION_CAPACITY_PRESERVED_BUT_NO_COMPLETE_CANDIDATE`.
The lower node count is early construction-domain rejection, not a business
improvement. No globally infeasible geometry claim or follow-on recovery is made.

The final-source P0/P1/P2/architecture selection terminated after 7,820.04 seconds:
887 passed, 16 skipped, one failure. The failure is the unchanged historical
GD003 isolation test: its `git diff --quiet` for the GD002 files exited 128 with
`index.lock write error: Operation timed out`, not a content-difference exit 1.
The remaining Git children completed normally and released their locks. No Git
process was interrupted, no lock was moved/deleted, and no metadata recovery
was attempted. This failed invocation remains disclosed; no all-green final
local regression invocation is claimed. Final-source P3/R1 focused/boundary
refresh passed 44 tests (22.20 seconds), and Ruff/908-file formatting passed
again; the ignored direct runner separately passed Ruff/format.
An additional read-only two-commit comparison of the GD002 paths against
`7799442d20bd502fe10b4e18c0bac64e996c1b72` returned exit 0. This confirms their
committed blobs did not drift; it does not relabel the failed worktree/index-
refresh pytest invocation as passing.

Evidence: `evidence/v2_2_2_p1a_metric_reservation_consumption_p3/xinzhao_dynamic_metric_reservation_consumption.json`.
Architecture: ADR-050 P3 decision. Final results and terminal exact-head CI will
be recorded after actual complete replays. A containing-commit binding avoids a
self-referential literal commit hash inside its own committed evidence.

## Stop boundary

P3 is construction consistency, not global feasibility or engineering approval.
No budget/order tuning is authorized if the complete-candidate business gate fails.
After this task: no next phase, Access, Truck, P2D, selection, Ready, Merge,
tag, release or deployment without separate Owner authorization.
