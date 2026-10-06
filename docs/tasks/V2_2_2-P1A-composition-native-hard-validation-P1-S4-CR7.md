# V2.2.2 P1A S4 Correction Round 7

TASK_ID=V2_2_2_P1A_COMPOSITION_NATIVE_HARD_VALIDATION_P1_S4_CR7
MODE=EXACT_SUCCESSOR_FREE_SPACE_DOMAIN_PROPAGATION_AND_PHYSICAL_BLOCKER_ATTRIBUTION
BASE_MAIN_SHA=a0ef560de778770e4c26c4d027a239afe78eeadd
CR8_AUTHORIZED=false

## Scope and history

This round continues the existing Draft PR #306, starting at
`22fa1ff0efc87820d7d6def72449826095e4ff90`. It neither rebuilds CR1 nor
creates a replacement branch/PR. CR1–CR6 business failures remain historical
facts: Access-critical construction, search-lane/staging correction, optimistic
completion probes, witness inheritance/replay, composition projection bounds,
and mandatory-edge successor domains are all preserved.

CR7 adds exact successor free-space domain subtraction and physical blocker
attribution. It does not implement conflict-directed backjumping, a recovery
mode, another search order/family, geometry repair, or CR8.

## Domain propagation and authority

For each authoritative shape, the existing finite origin union and exact MUST
edge filter remain in place, followed by CR5's necessary projection bounds.
The remaining origin set is classified using the unchanged exact site,
closed-obstacle, and positive-area room-overlap predicates. All simultaneous
blockers are retained, with a separate exclusive SITE → OBSTACLE → OVERLAP
classification for count reconciliation. Obstacle identities are canonical
polygon hashes; evidence maps them to the actual fixed polygons. Room groups
come from the bound composition handoff, not an independent grouping policy.

For exactly axis-aligned rectangular polygons, classification is integer
origin-interval subtraction: boundary containment is inclusive, closed
obstacle contact is excluded, and room overlap is strictly positive-area.
Nonrectangular polygons use the unchanged exact polygon predicates, never a
bbox approximation. Rotation, concave boundary, triangular obstacle, and
touching cases are covered by equivalence tests. Primitive diagnostic records
use direct canonical JSON digests equivalent to the existing canonical hash;
this avoids repeated engineering-number normalization of diagnostic integer
trees. Authority and candidate hashes still use the existing authority code.

Only physical exclusions are subtracted. Surviving origins still enter the
existing budgeted recursive probe, exact hard/intent checks, and CR4 witness
machinery. Empty domains prove no support only in this fixed finite search
domain. UNKNOWN remains non-pruning. Construction-domain classification is
not recursive search and has its own operation/cardinality counters; it adds
no origins or hidden recursive allowance. All primary and forward recursive
expansions remain charged to the same 60,000-node budget. Access and Truck
remain 20,000 each. The outer 13-attempt schedule and two order lanes are
unchanged. Domain predicates and validator authority are not weakened.

`SuccessorDomainConflictSet` diagnostics record the union of blockers covering
all excluded candidates; they do not claim a minimal conflict set or global
infeasibility and do not direct backjumping. Single non-MUST blocker release
diagnostics examine the same finite origins while releasing exactly one room
footprint. They do not release site/obstacle/MUST facts, move rooms, reserve
geometry, or authorize recovery. A restored physical origin would not prove
Access, a suffix, or a complete layout.

## CR6 diagnostic debt closed

The diagnostic runner reconstructs the seven recorded CR6 Coating partials
only for evidence/fixtures. Production search never loads historical evidence
or uses these bounds as seeds. Both Finished shape orientations and the
existing origin union yield 1,157 projection-compatible origins across the
seven profiles, all now classified: 580 SITE, 528 OBSTACLE, 49 OVERLAP, zero
physical free-space origins. All overlapping rooms/groups and obstacle hashes
are recorded, including simultaneous blockers hidden by the exclusive funnel.

The historical ordering and budget-stop sample independently identify all
127 previously unexpanded candidates. Their complete attribution is 84 SITE,
36 OBSTACLE, and 7 OVERLAP, with no unclassified remainder. Adding these to
CR6's 496/492/42 expanded counts yields exactly 580/528/49. Every single
non-MUST room release restores zero physical origins in these seven profiles.
These are fixed-partial finite-domain facts, not global impossibility.

| CR6 Coating bounds (mm) | Finished origins after projection | SITE | OBSTACLE | OVERLAP | Free |
| --- | ---: | ---: | ---: | ---: | ---: |
| [29398,31768,40198,45368] | 167 | 84 | 76 | 7 | 0 |
| [30917,31768,41717,45368] | 167 | 84 | 76 | 7 | 0 |
| [29398,31768,39448,45368] | 161 | 80 | 74 | 7 | 0 |
| [31667,31768,41717,45368] | 167 | 84 | 76 | 7 | 0 |
| [29398,31768,39447,45368] | 164 | 82 | 75 | 7 | 0 |
| [29399,31768,39448,45368] | 164 | 82 | 75 | 7 | 0 |
| [31668,31768,41717,45368] | 167 | 84 | 76 | 7 | 0 |

## Verification

CR7 focused tests: 10 passed, including exact equivalence with unchanged
physical predicates, simultaneous blocker/group attribution, diagnostic-only
single releases, protection of MUST neighbors, closed obstacle vs room-edge
semantics, determinism, nonrectangular fallback, canonical diagnostic digest
equivalence, and the full historical 127-candidate debt. The final CR3–CR6
forward/witness suite plus CR7 focused tests passed 39 tests.
One earlier run failed an obsolete assertion that negative proof must consume
recursive nodes; it was replaced by exhaustive-classification assertions,
without changing the expected proof status. Ruff, format, changed-module
mypy, and diff-check passed. Full local architecture collection was interrupted
after 174 seconds in a filesystem read, with no tests run; it is not reported
as a PASS. Scoped composition boundaries and S1–S3 regressions and exact-head
CI are separate gates. Scoped composition architecture boundaries and S1–S3
regressions passed 67 tests. Five selected CR1/CR2 interface and non-Truck-first
staging tests also passed; two full-search tests were deselected in that local
command because full production/determinism capture is performed directly.

The unchanged control was replayed on CR7 runtime source and retained 12
requirements, 7 PASS / 5 FAIL, and `TRUCK_MANEUVER_SEARCH_EXHAUSTED`. No control
geometry or engineering authority was modified.

## Terminal production replay and outcome

Two independent full production replays terminated normally. Both captured
all 13 attempts, with byte-identical unabridged output SHA256
`0b303c46502486a22a39280d8e14d0fe08a5d3baf788250de024f8ab1c6b6d66`.
The evidence retains the detailed first replay and the independently completed
second replay's schedule, node totals and sequence hashes. Compaction happened
only after full output equality was verified. Every attempt, propagation,
free-space, capacity, forward/witness, candidate and Access sequence is equal.

Both runs used 52,353 primary plus 3,611 forward nodes, totaling 55,964,
within the unchanged 60,000 limit. Allocations still total 60,000. Family maximum
placed counts are Linear 11, Central 6 and Spine 9. No complete candidate
was constructed or Access-assessed; new-candidate Truck/P2D attempts are zero.

The known Y/POSITIVE Linear bank +1 S3-order attempt now finds a dynamically
generated, composition-compatible witness in 40 forward nodes. The existing
CR4 primary replay accepts all three witness rectangles without mismatch:

| Role | Witness bounds (mm) | Primary replay |
| --- | --- | --- |
| Coating | [32771,31768,41717,45368] | ACCEPTED |
| Finished Goods | [371,33951,32771,52551] | ACCEPTED |
| Shipping | [32771,45368,40464,51868] | ACCEPTED |

The lane reaches 11 roles and stops at Office. Its 19,565 Office attempts
reconcile exactly: 6,526 site rejections, 6,897 obstacle rejections and 6,142
overlap rejections, zero accepted placements. The finite attempt allocation
is exhausted; this is not an exhaustive global Office infeasibility proof.
No new Office recovery or order change was introduced.

The current-code control replay retains 7/12 total and 7/11 non-Truck PASS.
Truck remains `TRUCK_MANEUVER_SEARCH_EXHAUSTED`, visited 27, tree exhausted,
node budget not exhausted, loading face validated. No control geometry changed.

`RESULT=FAIL`: physical blocker attribution is complete and structural
progress is real, but complete candidates remain zero. The validation progress
is `PHYSICAL_BLOCKER_ATTRIBUTION_COMPLETE_NO_COMPLETE_CANDIDATE`.
`ARCHITECTURE_DECISION_POINT_REQUIRED=true`; `CR8_AUTHORIZED=false`.
Exact-head CI is verified after commit/push and recorded in the PR/final receipt;
the pre-commit task record does not assert a future CI conclusion.
